"use strict";

const { app, BrowserWindow, ipcMain } = require("electron");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { randomUUID } = require("crypto");
const WorkflowIntegration = require("./WorkflowIntegration.node");

const PLUGIN_ID = "com.oeditor.resolve.internalhost";
const POLL_INTERVAL_MS = 500;
const HOST_VERSION = "0.2.0";
const TERMINAL_STATES = new Set(["SUCCEEDED", "FAILED", "CANCELLED", "UNSUPPORTED"]);
const root = path.join(process.env.APPDATA, "O Editor", "resolve-internal-host");
const directories = {
  requests: path.join(root, "requests"),
  jobs: path.join(root, "jobs"),
  responses: path.join(root, "responses"),
  logs: path.join(root, "logs"),
  launches: path.join(root, "launches"),
};

let mainWindow = null;
let resolveObject = null;
let pollTimer = null;
let stopping = false;
let busy = false;
let openingEditor = false;
let editorStatus = { status: "STARTING", detail: "Preparando a abertura do editor…" };

function publishEditorStatus(value) {
  editorStatus = value;
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send("editor:status", value);
}

// Long brackets preserve Unicode and cannot interpret paths as Lua code.
function luaLiteral(value) {
  let separator = "";
  while (value.includes(`]${separator}]`)) separator += "=";
  return `[${separator}[${value}]${separator}]`;
}

async function openEditor() {
  if (openingEditor) throw new Error("A abertura do EDE já está em andamento.");
  if (!resolveObject || stopping) throw new Error("A integração com o Resolve não está pronta.");
  openingEditor = true;
  publishEditorStatus({ status: "OPENING", detail: "Solicitando a abertura do EDE…" });
  try {
    const configPath = path.join(process.env.APPDATA, "O Editor", "launcher.json");
    const config = JSON.parse(fs.readFileSync(configPath, "utf8").replace(/^\uFEFF/, ""));
    if (config.schema_version !== 1 || config.internal_host_enabled !== true ||
        typeof config.project_root !== "string" || !fs.existsSync(config.project_root) ||
        typeof config.python_executable !== "string" || !fs.existsSync(config.python_executable)) {
      throw new Error("Instalação do EDE incompleta. Execute novamente o instalador offline.");
    }
    ensureDirectories();
    const launchId = randomUUID();
    const receipt = path.join(directories.launches, `${launchId}.json`);
    const entry = path.join(__dirname, "open-editor.lua").replace(/\\/g, "/");
    const fusion = await resolveObject.Fusion();
    if (!fusion) throw new Error("O Resolve não disponibilizou o host Fusion para abrir o EDE.");
    // Read-only bootstrap only. Never consume a pending editorial plan on startup.
    await fusion.Execute(`local open=dofile(${luaLiteral(entry)}); ` +
      `open(${luaLiteral(receipt.replace(/\\/g, "/"))},${luaLiteral(launchId)})`);
    const deadline = Date.now() + 15000;
    while (Date.now() < deadline && !stopping) {
      if (fs.existsSync(receipt)) {
        const result = JSON.parse(fs.readFileSync(receipt, "utf8"));
        if (result.schema_version !== 1 || result.launch_id !== launchId || result.launched !== true) {
          throw new Error(result.error || "O host não confirmou a abertura do EDE.");
        }
        appendLog(`editor_launch=${launchId} status=DISPATCHED`);
        return { status: "DISPATCHED", detail: result.status === "SUCCESS"
          ? "Pedido enviado ao EDE. Continue na janela do editor."
          : "Pedido enviado ao EDE com diagnóstico. Abra um projeto e uma timeline no Resolve." };
      }
      await new Promise((done) => setTimeout(done, 100));
    }
    throw new Error("O Resolve não confirmou a abertura em 15 segundos. Consulte o diagnóstico antes de tentar novamente.");
  } finally {
    openingEditor = false;
  }
}

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
  publishStatus("READY", "Integração conectada ao DaVinci Resolve.");
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
    title: "EDE — Editor Do Escobar",
    width: 620,
    height: 400,
    minWidth: 480,
    minHeight: 360,
    useContentSize: true,
    webPreferences: {
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      preload: path.join(__dirname, "preload.js"),
    },
  });
  mainWindow.setMenu(null);
  mainWindow.loadFile(path.join(__dirname, "index.html"));
  mainWindow.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  mainWindow.webContents.on("will-navigate", (event) => event.preventDefault());
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

function requireEditorWindow(event) {
  if (!mainWindow || event.sender !== mainWindow.webContents) {
    throw new Error("Origem da solicitação não permitida.");
  }
}

ipcMain.handle("editor:getStatus", (event) => {
  requireEditorWindow(event);
  return editorStatus;
});

ipcMain.handle("editor:open", async (event) => {
  requireEditorWindow(event);
  try {
    const result = await openEditor();
    publishEditorStatus(result);
    return result;
  } catch (error) {
    appendLog(`editor_launch_failed=${String(error)}`);
    const result = { status: "FAILED", detail: String(error.message || error) };
    publishEditorStatus(result);
    return result;
  }
});

app.whenReady().then(async () => {
  createWindow();
  try {
    await startHost();
  } catch (error) {
    appendLog(`startup_failed=${String(error)}`);
    publishStatus("FAILED", String(error));
    publishEditorStatus({ status: "FAILED", detail: String(error.message || error) });
    return;
  }
  try {
    publishEditorStatus(await openEditor());
  } catch (error) {
    appendLog(`editor_launch_failed=${String(error)}`);
    publishEditorStatus({ status: "FAILED", detail: String(error.message || error) });
  }
});

app.on("before-quit", async () => {
  await stopHost();
});

app.on("window-all-closed", () => {
  app.quit();
});
