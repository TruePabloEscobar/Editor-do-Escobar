"""A real Qt local socket must consume each frame exactly once and stay responsive."""

from __future__ import annotations

import os
import subprocess
import sys


def test_ipc_fragmented_and_batched_frames_are_delivered_once() -> None:
    script = r"""import json, uuid
from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtNetwork import QLocalSocket
from o_editor.internal_actions.ipc import LocalIpcServer
app = QCoreApplication([])
received = []
server = LocalIpcServer("test-o-editor-" + uuid.uuid4().hex, lambda msg: received.append(msg) or {})
assert server.listen()
client = QLocalSocket()
responses = bytearray()
payload = b'{"type":"activate"}\n{"type":"show_message","message":"ok"}\n'
client.connected.connect(lambda: client.write(payload + b'{"type":"activ'))
def finish():
    assert [item["type"] for item in received] == ["activate", "show_message", "activate"], received
    print("DELIVERED_ONCE_AND_RESPONSIVE", flush=True)
    server.close()
    app.quit()
def read():
    responses.extend(bytes(client.readAll()))
    if responses.count(b"\n") == 2:
        client.write(b'ate"}\n')
    elif responses.count(b"\n") == 3:
        QTimer.singleShot(20, finish)
client.readyRead.connect(read)
client.connectToServer(server.name)
QTimer.singleShot(3000, lambda: app.exit(2))
raise SystemExit(app.exec())
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "DELIVERED_ONCE_AND_RESPONSIVE" in result.stdout
