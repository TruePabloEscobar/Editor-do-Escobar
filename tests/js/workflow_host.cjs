"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(process.argv[2], "utf8");

async function scenario(mode) {
  const calls = [];
  const resolve = {};
  let ready = false;
  const integration = {
    Initialize: async (id) => {
      calls.push(["Initialize", id]);
      await Promise.resolve();
      ready = mode !== "init_false";
      return ready;
    },
    SetAPITimeout: (seconds) => {
      calls.push(["SetAPITimeout", seconds]);
      assert.equal(calls[0][0], "Initialize");
      assert.equal(ready, true, "Initialize deve concluir antes do timeout");
      return true;
    },
    GetResolve: async () => {
      calls.push(["GetResolve"]);
      return mode === "no_resolve" ? null : resolve;
    },
    RegisterCallback: (name) => { calls.push(["RegisterCallback", name]); return true; },
  };
  const fakeElectron = {
    app: { whenReady: () => ({ then: () => {} }), on: () => {} },
    BrowserWindow: class {},
    ipcMain: { handle: () => {} },
  };
  const sandbox = {
    require: (name) => name === "electron" ? fakeElectron :
      name === "./WorkflowIntegration.node" ? integration : require(name),
    process: { env: { APPDATA: "/test" }, pid: 1 },
    __dirname: "/test",
    setInterval: () => {}, clearInterval: () => {},
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox, { filename: "main.js" });
  if (mode === "ok") {
    assert.equal(await sandbox.initializeResolve(), resolve);
    assert.deepEqual(calls.map(c => c[0]), ["Initialize", "SetAPITimeout", "GetResolve", "RegisterCallback"]);
    assert.equal(calls[0][1], "com.oeditor.resolve.internalhost");
    assert.equal(calls[1][1], 10);
  } else {
    await assert.rejects(sandbox.initializeResolve());
    assert.equal(calls.some(c => c[0] === "RegisterCallback"), false);
    if (mode === "init_false") assert.deepEqual(calls.map(c => c[0]), ["Initialize"]);
  }
}
(async () => {
  for (const mode of ["ok", "init_false", "no_resolve"]) await scenario(mode);
  console.log("Inicialização do plugin: três cenários simulados aprovados.");
})().catch(error => { console.error(error); process.exitCode = 1; });
