"""Single-instance UI runtime for internal Resolve menu actions."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPushButton,
)

from o_editor.bootstrap import bootstrap, project_root
from o_editor.errors import OEditorError
from o_editor.internal_actions.ipc import LocalIpcServer, send_ipc_message, server_name
from o_editor.internal_actions.presentation import render_internal_action
from o_editor.internal_actions.request import (
    InternalActionRequest,
    app_data_root,
    load_internal_action_request,
    mark_request_processed,
    processed_marker_path,
)
from o_editor.ui.main_window import MainWindow, _load_context


class InternalActionMainWindow(MainWindow):
    """Main window extended with request display and IPC activation."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._processed_request_ids: set[str] = set()
        self._active_internal_request: InternalActionRequest | None = None
        self._active_report_path: Path | None = None
        self._active_log_path: Path | None = None
        self._add_internal_action_controls()
        self._reply_polling_enabled = True
        self._reply_scan_started = time.time() - 1.0
        self._reply_timer = QTimer(self)
        self._reply_timer.setInterval(500)
        self._reply_timer.timeout.connect(self._poll_rough_cut_replies)
        self._reply_timer.start()

    def _poll_rough_cut_replies(self) -> None:
        """Receive durable replies even if the auxiliary launcher cannot deliver IPC."""
        if not self._reply_polling_enabled:
            return
        try:
            paths = list((app_data_root() / "requests").glob("request-*.json"))
            for path in paths:
                try:
                    if path.stat().st_mtime < self._reply_scan_started:
                        continue
                    request = load_internal_action_request(path)
                    if (
                        request.action != "apply_rough_cut"
                        or request.request_id in self._processed_request_ids
                        or processed_marker_path(path, request.request_id).exists()
                    ):
                        continue
                    self._display_internal_action_request(path)
                    self._activate_from_ipc()
                except (OEditorError, OSError):
                    # Lua writes the file before launching the client; retry partial writes.
                    continue
        except (OEditorError, OSError):
            return

    def closeEvent(self, event: Any) -> None:
        super().closeEvent(event)
        if event.isAccepted():
            self._reply_polling_enabled = False
            self._reply_timer.stop()

    def _add_internal_action_controls(self) -> None:
        layout = self._diagnostics_layout
        actions = QHBoxLayout()
        self._open_action_report_button = QPushButton("Abrir relatório")
        self._open_action_log_button = QPushButton("Abrir log")
        self._copy_action_button = QPushButton("Copiar diagnóstico")
        for button in (
            self._open_action_report_button,
            self._open_action_log_button,
            self._copy_action_button,
        ):
            button.setVisible(False)
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        self._open_action_report_button.clicked.connect(
            lambda: self._open_local_file(self._active_report_path)
        )
        self._open_action_log_button.clicked.connect(
            lambda: self._open_local_file(self._active_log_path)
        )
        self._copy_action_button.clicked.connect(self._copy_internal_action)

    def handle_ipc_message(self, message: dict[str, Any]) -> dict[str, Any]:
        message_type = str(message.get("type", ""))
        if message_type == "activate":
            self._activate_from_ipc()
            return {"handled": "activate"}
        if message_type == "internal_action_request":
            request_path = Path(str(message["path"]))
            response = self._display_internal_action_request(request_path)
            self._activate_from_ipc()
            return response
        if message_type == "launch_context":
            context = _load_context(
                str(message["path"]),
                use_mock=self._use_mock,
                config=self._config,
                root=self._root,
                internal_host=message.get("internal_host") is True,
            )
            if context:
                self._apply_context(context)
            self._activate_from_ipc()
            return {"handled": "launch_context"}
        if message_type == "show_message":
            self._report.setPlainText(str(message["message"]))
            self._show_diagnostics()
            self._activate_from_ipc()
            return {"handled": "show_message"}
        if message_type in {
            "show_report",
            "diagnostic_result",
            "capability_result",
            "apply_result",
        }:
            path = Path(str(message["path"]))
            self._display_result_file(path, message_type)
            self._activate_from_ipc()
            return {"handled": message_type, "path": str(path)}
        raise OEditorError(f"Mensagem IPC não suportada: {message_type}")

    def _display_internal_action_request(self, path: Path) -> dict[str, Any]:
        request = load_internal_action_request(path)
        marker = processed_marker_path(path, request.request_id)
        duplicate = request.request_id in self._processed_request_ids or marker.exists()
        self._processed_request_ids.add(request.request_id)
        self._active_internal_request = request
        self._active_report_path = Path(request.report_file) if request.report_file else None
        self._active_log_path = Path(request.log_file) if request.log_file else None
        context = request.details.get("context")
        if isinstance(context, dict) and request.action != "apply_rough_cut":
            self._apply_context(
                {
                    **context,
                    "integration_mode": "internal_resolve_host",
                    "connection_status": "Ação recebida do host interno do DaVinci Resolve.",
                }
            )
        else:
            if request.project:
                self._project_label.setText(request.project)
            if request.timeline:
                self._timeline_label.setText(request.timeline)
        rendered = render_internal_action(request)
        if duplicate:
            rendered += "\n\nEsta request já havia sido processada; o resultado foi reapresentado."
        self._report.setPlainText(rendered)
        if request.action == "apply_rough_cut":
            if self._transcript_panel.display_rough_cut_result(request):
                self._navigate(3)
        elif request.action != "open":
            self._show_diagnostics()
        self._open_action_report_button.setVisible(
            self._active_report_path is not None and self._active_report_path.is_file()
        )
        self._open_action_log_button.setVisible(
            self._active_log_path is not None and self._active_log_path.is_file()
        )
        self._copy_action_button.setVisible(request.action == "diagnostic")
        self.statusBar().showMessage(f"Ação interna: {request.action} — {request.status}")
        if not duplicate:
            mark_request_processed(path, request)
        return {
            "handled": "internal_action_request",
            "request_id": request.request_id,
            "action": request.action,
            "status": request.status,
            "duplicate": duplicate,
        }

    def _display_result_file(self, path: Path, result_type: str) -> None:
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            self._report.setPlainText(f"Não foi possível abrir {path}: {exc}")
            return
        self._active_report_path = path
        self._open_action_report_button.setVisible(True)
        self._report.setPlainText(f"{result_type}\n\n{content}")
        self._show_diagnostics()

    def _activate_from_ipc(self) -> None:
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()

    def _open_local_file(self, path: Path | None) -> None:
        if path is None or not path.is_file():
            self.statusBar().showMessage("O arquivo solicitado não está disponível.")
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.statusBar().showMessage(f"Não foi possível abrir: {path}")

    def _copy_internal_action(self) -> None:
        QApplication.clipboard().setText(self._report.toPlainText())
        self.statusBar().showMessage("Diagnóstico copiado.")


def run_ui(
    *,
    use_mock: bool,
    context_path: str | None,
    internal_host: bool = False,
    internal_action_request: str | None = None,
    show_report: str | None = None,
    show_message: str | None = None,
    diagnostic_result: str | None = None,
    capability_result: str | None = None,
    apply_result: str | None = None,
) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    config = bootstrap()
    root = project_root()
    startup_message = _startup_ipc_message(
        context_path=context_path,
        internal_host=internal_host,
        internal_action_request=internal_action_request,
        show_report=show_report,
        show_message=show_message,
        diagnostic_result=diagnostic_result,
        capability_result=capability_result,
        apply_result=apply_result,
    )
    ipc_name = server_name(root)
    response = send_ipc_message(ipc_name, startup_message)
    if response is not None:
        if response.get("ok") is not True:
            print(f"O Editor: a instância existente recusou a ação: {response.get('error')}")
            return 1
        return 0
    window = InternalActionMainWindow(
        config=config,
        root=root,
        use_mock=use_mock,
        context=(
            _load_context(
                context_path,
                use_mock=use_mock,
                config=config,
                root=root,
                internal_host=internal_host,
            )
            if context_path
            else None
        ),
    )
    ipc_server = LocalIpcServer(ipc_name, window.handle_ipc_message, window)
    if not ipc_server.listen():
        response = send_ipc_message(ipc_name, startup_message, timeout_ms=3000)
        if response is not None and response.get("ok") is True:
            window.close()
            return 0
        print("O Editor: outra instância iniciou, mas não confirmou a ação.")
        window.close()
        return 1
    if not context_path or startup_message["type"] != "launch_context":
        try:
            window.handle_ipc_message(startup_message)
        except OEditorError as exc:
            window._report.setPlainText(f"Falha controlada ao abrir a ação interna: {exc}")
    window.show()
    exit_code = int(app.exec())
    ipc_server.close()
    return exit_code


def _startup_ipc_message(
    *,
    context_path: str | None,
    internal_host: bool,
    internal_action_request: str | None,
    show_report: str | None,
    show_message: str | None,
    diagnostic_result: str | None,
    capability_result: str | None,
    apply_result: str | None,
) -> dict[str, Any]:
    if internal_action_request:
        return {"type": "internal_action_request", "path": internal_action_request}
    if context_path:
        return {
            "type": "launch_context",
            "path": context_path,
            "internal_host": internal_host,
        }
    for message_type, path in (
        ("show_report", show_report),
        ("diagnostic_result", diagnostic_result),
        ("capability_result", capability_result),
        ("apply_result", apply_result),
    ):
        if path:
            return {"type": message_type, "path": path}
    if show_message:
        return {"type": "show_message", "message": show_message}
    return {"type": "activate"}
