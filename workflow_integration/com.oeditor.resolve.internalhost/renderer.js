"use strict";

function renderStatus(value) {
  const labels = { READY: "Conectado", STARTING: "Conectando", FAILED: "Falha na integração", STOPPED: "Encerrado" };
  document.getElementById("status").textContent = labels[value.status] || "Aguardando conexão";
  document.getElementById("detail").textContent = value.detail || "";
  document.getElementById("metadata").textContent =
    `EDE ${value.host_version || "0.2.0"} · Integração local`;
}

window.addEventListener("DOMContentLoaded", async () => {
  renderStatus(await window.oEditorHost.getStatus());
  window.oEditorHost.onStatus(renderStatus);
  const button = document.getElementById("open-editor");
  const detail = document.getElementById("editor-detail");
  function editorStatus(value) {
    detail.textContent = value.detail || "";
    button.disabled = ["STARTING", "OPENING"].includes(value.status);
    button.textContent = "Abrir ou trazer o EDE para frente";
  }
  window.oEditorHost.onEditorStatus(editorStatus);
  editorStatus(await window.oEditorHost.getEditorStatus());
  button.addEventListener("click", async () => {
    button.disabled = true;
    detail.textContent = "Solicitando a abertura do EDE…";
    try {
      editorStatus(await window.oEditorHost.openEditor());
    } catch (error) {
      editorStatus({ detail: String(error.message || error) });
    }
  });
});
