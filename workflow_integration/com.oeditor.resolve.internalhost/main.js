"use strict";

const { app, BrowserWindow, ipcMain } = require("electron");
const fs = require("fs");
const os = require("os");
const path = require("path");
const WorkflowIntegration = require("./WorkflowIntegration.node");

const PLUGIN_ID = "com.oeditor.resolve.internalhost";
const POLL_INTERVAL_MS = 500;
const HOST_VERSION = "0.1.0";
const TERMINAL_STATES = new Set(["SUCCEEDED", "FAILED", "CANCELLED", "UNSUPPORTED"]);
const root = path.join(process.env.APPDATA, "O Editor", "resolve-internal-host");
const directories = {
  requests: path.join(root, "requests"),
  jobs: path.join(root, "jobs"),
  responses: path.join(root, "responses"),
  logs: path.join(root, "logs"),
};

let mainWindow = null;
let resolveObject = null;
let pollTimer = null;
let stopping = false;
let busy = false;

function now() {
  return new Date().toISOString();
}

function ensureDirectories() {
  Object.values(directories).forEach((directory) => {
    fs.mkdirSync(directory, { recursive: true });
  });
}

function appendLog(message) {
  ensureDirectories();
  fs.appendFileSync(
    path.join(directories.logs, "workflow-integration.log"),
    `${now()} ${String(message).replace(/[\r\n]+/g, " ")}\n`,
    "utf8",
  );
}

function writeJsonAtomic(target, value) {
  const temporary = `${target}.${process.pid}.tmp`;
  fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  fs.renameSync(temporary, target);
}

function publishStatus(status, detail) {
  const value = {
    status,
    detail,
    host_version: HOST_VERSION,
    plugin_id: PLUGIN_ID,
    pid: process.pid,
    poll_interval_ms: POLL_INTERVAL_MS,
    updated_at: now(),
  };
  writeJsonAtomic(path.join(root, "host-status.json"), value);
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("host:status", value);
  }
}

async function initializeResolve() {
  // Initialize must come first: the 15/10 log showed "SetAPITimeout: Not initialized".
  const initialized = await WorkflowIntegration.Initialize(PLUGIN_ID);
  if (!initialized) {
    throw new Error("WorkflowIntegration.Initialize retornou false.");
  }
  WorkflowIntegration.SetAPITimeout(10);
  resolveObject = await WorkflowIntegration.GetResolve();
  if (!resolveObject) {
    throw new Error("WorkflowIntegration.GetResolve não retornou o Resolve.");
  }
  WorkflowIntegration.RegisterCallback("ResolveQuit", stopHost);
  return resolveObject;
}

async function readContext() {
  const projectManager = await resolveObject.GetProjectManager();
  const project = projectManager ? await projectManager.GetCurrentProject() : null;
  const timeline = project ? await project.GetCurrentTimeline() : null;
  return {
    resolve_version: String((await resolveObject.GetVersionString()) || ""),
    project: project ? String((await project.GetName()) || "") : null,
    timeline: timeline ? String((await timeline.GetName()) || "") : null,
    timeline_id: timeline ? String((await timeline.GetUniqueId()) || "") : null,
  };
}

function validateRequest(value, filename) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("A request deve ser um objeto JSON.");
  }
  if (value.schema_version !== 1 || typeof value.request_id !== "string") {
    throw new Error("Schema ou request_id inválido.");
  }
  if (!filename.includes(value.request_id)) {
    throw new Error("O nome da request não corresponde ao request_id.");
  }
  if (!["ping", "export_voice_audio", "cancel"].includes(value.action)) {
    throw new Error("Ação não permitida.");
  }
  return value;
}

function responseFor(request, status, result, error, startedAt) {
  return {
    schema_version: 1,
    request_id: request.request_id,
    action: request.action,
    status,
    created_at: request.created_at,
    started_at: startedAt,
    finished_at: now(),
    host: {
      plugin_id: PLUGIN_ID,
      host_version: HOST_VERSION,
      pid: process.pid,
      platform: os.platform(),
      arch: os.arch(),
      workflow_integration: WorkflowIntegration.GetInfo(),
    },
    result,
    error,
    mutations_executed: false,
  };
}

async function processRequest(requestPath) {
  const filename = path.basename(requestPath);
  const raw = fs.readFileSync(requestPath, "utf8");
  const request = validateRequest(JSON.parse(raw), filename);
  const jobPath = path.join(directories.jobs, `host-job-${request.request_id}.json`);
  fs.renameSync(requestPath, jobPath);
  const startedAt = now();
  writeJsonAtomic(jobPath, { ...request, status: "RUNNING", started_at: startedAt });

  let response;
  try {
    if (request.action === "ping") {
      const context = await readContext();
      response = responseFor(
        request,
        "SUCCEEDED",
        { pong: true, context },
        null,
        startedAt,
      );
    } else if (request.action === "cancel") {
      response = responseFor(
        request,
        "CANCELLED",
        { cancelled: true },
        null,
        startedAt,
      );
    } else {
      response = responseFor(
        request,
        "UNSUPPORTED",
        {
          backend: "workflow_integration",
          capability: "export_voice_audio",
          capability_status: "UNVERIFIED",
        },
        "Render automático bloqueado até prova mutável manual em projeto OE_TEST_.",
        startedAt,
      );
    }
  } catch (error) {
    response = responseFor(request, "FAILED", {}, String(error), startedAt);
  }
  if (!TERMINAL_STATES.has(response.status)) {
    throw new Error("O host tentou publicar um estado não terminal.");
  }
  writeJsonAtomic(
    path.join(directories.responses, `host-response-${request.request_id}.json`),
    response,
  );
  writeJsonAtomic(jobPath, { ...request, status: response.status, finished_at: now() });
  appendLog(`request=${request.request_id} action=${request.action} status=${response.status}`);
}

async function pollRequests() {
  if (busy || stopping) {
    return;
  }
  busy = true;
  try {
    ensureDirectories();
    const files = fs
      .readdirSync(directories.requests)
      .filter((name) => /^host-request-[0-9a-f-]{36}\.json$/i.test(name))
      .sort();
    for (const filename of files) {
      await processRequest(path.join(directories.requests, filename));
    }
  } catch (error) {
    appendLog(`poll_failed=${String(error)}`);
    publishStatus("FAILED", String(error));
  } finally {
    busy = false;
  }
}

async function startHost() {
  ensureDirectories();
  await initializeResolve();
  publishStatus("READY", "Host persistente aguardando requests locais.");
  pollTimer = setInterval(pollRequests, POLL_INTERVAL_MS);
  await pollRequests();
}

async function stopHost() {
  if (stopping) {
    return;
  }
  stopping = true;
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  try {
    WorkflowIntegration.DeregisterCallback("ResolveQuit");
    WorkflowIntegration.CleanUp();
  } catch (error) {
    appendLog(`cleanup_failed=${String(error)}`);
  }
  publishStatus("STOPPED", "Host encerrado com cleanup solicitado.");
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 620,
    height: 340,
    useContentSize: true,
    webPreferences: {
      contextIsolation: true,
      sandbox: true,
      preload: path.join(__dirname, "preload.js"),
    },
  });
  mainWindow.setMenu(null);
  mainWindow.loadFile("index.html");
  mainWindow.on("close", async () => {
    await stopHost();
  });
}

ipcMain.handle("host:getStatus", () => {
  const statusPath = path.join(root, "host-status.json");
  return fs.existsSync(statusPath)
    ? JSON.parse(fs.readFileSync(statusPath, "utf8"))
    : { status: "STARTING", detail: "Inicializando host." };
});

app.whenReady().then(async () => {
  createWindow();
  try {
    await startHost();
  } catch (error) {
    appendLog(`startup_failed=${String(error)}`);
    publishStatus("FAILED", String(error));
  }
});

app.on("before-quit", async () => {
  await stopHost();
});

app.on("window-all-closed", () => {
  app.quit();
});
