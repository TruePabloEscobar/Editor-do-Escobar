"use strict";

const { contextBridge, ipcRenderer } = require("electron/renderer");

contextBridge.exposeInMainWorld("oEditorHost", {
  getStatus: () => ipcRenderer.invoke("host:getStatus"),
  onStatus: (callback) => ipcRenderer.on("host:status", (_event, value) => callback(value)),
  openEditor: () => ipcRenderer.invoke("editor:open"),
  getEditorStatus: () => ipcRenderer.invoke("editor:getStatus"),
  onEditorStatus: (callback) => ipcRenderer.on("editor:status", (_event, value) => callback(value)),
});
