"""Single-instance local IPC based on Qt local sockets."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from o_editor.errors import ConfigurationError

IPC_MESSAGE_TYPES = frozenset(
    {
        "activate",
        "launch_context",
        "internal_action_request",
        "show_report",
        "show_message",
        "diagnostic_result",
        "capability_result",
        "apply_result",
    }
)
IpcHandler = Callable[[dict[str, Any]], dict[str, Any]]


def server_name(root: Path) -> str:
    identity = str(root.resolve()).casefold().encode("utf-8")
    return "o-editor-" + hashlib.sha256(identity).hexdigest()[:20]


def send_ipc_message(
    name: str,
    message: dict[str, Any],
    *,
    timeout_ms: int = 1500,
) -> dict[str, Any] | None:
    _validate_message(message)
    socket = QLocalSocket()
    socket.connectToServer(name)
    if not socket.waitForConnected(timeout_ms):
        socket.abort()
        return None
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    socket.write(payload + b"\n")
    if not socket.waitForBytesWritten(timeout_ms):
        socket.abort()
        return None
    if not socket.waitForReadyRead(timeout_ms):
        socket.abort()
        return None
    response_data = bytes(socket.readAll().data()).splitlines()[0]
    socket.disconnectFromServer()
    try:
        response = json.loads(response_data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError("A resposta IPC local é inválida.") from exc
    if not isinstance(response, dict):
        raise ConfigurationError("A resposta IPC local deve ser um objeto JSON.")
    return response


class LocalIpcServer(QObject):
    def __init__(
        self,
        name: str,
        handler: IpcHandler,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._name = name
        self._handler = handler
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._accept_connections)
        self._buffers: dict[QLocalSocket, bytearray] = {}

    @property
    def name(self) -> str:
        return self._name

    def listen(self) -> bool:
        if self._server.listen(self._name):
            return True
        probe = QLocalSocket()
        probe.connectToServer(self._name)
        if probe.waitForConnected(200):
            probe.disconnectFromServer()
            return False
        QLocalServer.removeServer(self._name)
        if not self._server.listen(self._name):
            raise ConfigurationError(
                f"Não foi possível iniciar o IPC local: {self._server.errorString()}"
            )
        return True

    def close(self) -> None:
        self._server.close()

    def _accept_connections(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                continue
            self._buffers[socket] = bytearray()
            socket.readyRead.connect(lambda current=socket: self._read_socket(current))
            socket.disconnected.connect(lambda current=socket: self._discard_socket(current))
            if socket.bytesAvailable():
                self._read_socket(socket)

    def _read_socket(self, socket: QLocalSocket) -> None:
        buffer = self._buffers.setdefault(socket, bytearray())
        buffer.extend(bytes(socket.readAll().data()))
        while b"\n" in buffer:
            raw, _, remainder = buffer.partition(b"\n")
            buffer[:] = remainder
            response: dict[str, Any]
            try:
                value = json.loads(raw.decode("utf-8"))
                if not isinstance(value, dict):
                    raise ConfigurationError("A mensagem IPC deve ser um objeto JSON.")
                _validate_message(value)
                response = {"ok": True, **self._handler(value)}
            except (UnicodeError, json.JSONDecodeError, ConfigurationError, OSError) as exc:
                response = {"ok": False, "error": str(exc)}
            except Exception as exc:
                response = {"ok": False, "error": f"Falha interna no IPC: {exc}"}
            socket.write(
                json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                + b"\n"
            )
            socket.flush()

    def _discard_socket(self, socket: QLocalSocket) -> None:
        self._buffers.pop(socket, None)
        socket.deleteLater()


def _validate_message(message: dict[str, Any]) -> None:
    message_type = message.get("type")
    if message_type not in IPC_MESSAGE_TYPES:
        raise ConfigurationError(f"Tipo de mensagem IPC inválido: {message_type}")
    if message_type in {
        "launch_context",
        "internal_action_request",
        "show_report",
        "diagnostic_result",
        "capability_result",
        "apply_result",
    }:
        path = message.get("path")
        if not isinstance(path, str) or not path:
            raise ConfigurationError("A mensagem IPC não contém path válido.")
    if message_type == "show_message":
        text = message.get("message")
        if not isinstance(text, str) or not text.strip():
            raise ConfigurationError("A mensagem IPC não contém texto válido.")
