"use strict";

const { contextBridge, ipcRenderer } = require("electron/renderer");

contextBridge.exposeInMainWorld("oEditorHost", {
  getStatus: () => ipcRenderer.invoke("host:getStatus"),
  onStatus: (callback) => ipcRenderer.on("host:status", (_event, value) => callback(value)),
});
