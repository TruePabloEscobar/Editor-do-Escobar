"use strict";

function renderStatus(value) {
  document.getElementById("status").textContent = value.status || "UNVERIFIED";
  document.getElementById("detail").textContent = value.detail || "";
  document.getElementById("metadata").textContent =
    `Plugin ${value.plugin_id || "com.oeditor.resolve.internalhost"} · ` +
    `host ${value.host_version || "?"} · PID ${value.pid || "?"}`;
}

window.addEventListener("DOMContentLoaded", async () => {
  renderStatus(await window.oEditorHost.getStatus());
  window.oEditorHost.onStatus(renderStatus);
});
