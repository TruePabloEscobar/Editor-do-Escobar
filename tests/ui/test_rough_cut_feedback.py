"""Resolve results belong in the preview where the user requested them."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication

from o_editor.infrastructure.config import load_config
from o_editor.internal_actions.request import create_internal_action_request
from o_editor.ui.internal_action_runtime import InternalActionMainWindow

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("status", ["SUCCESS", "BLOCKED", "FAILED"])
def test_rough_cut_reply_is_visible_in_preview(tmp_path: Path, monkeypatch, status: str) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    window = InternalActionMainWindow(
        config=load_config(ROOT / "config/defaults.json"), root=tmp_path, use_mock=False
    )
    path = create_internal_action_request(
        "apply_rough_cut",
        status=status,
        message="Resultado da validação real",
        details={"plan_id": "p1", "mode": "VALIDATE"},
        requests_directory=tmp_path / "requests",
    )
    window.handle_ipc_message({"type": "internal_action_request", "path": str(path)})
    assert window._workflow_buttons[3].isChecked()
    assert "Resultado da validação real" in window._transcript_panel.preview_text.toPlainText()
    assert status in window._transcript_panel.status_label.text()
    window.close()
    app.processEvents()


def test_pending_request_cannot_be_overwritten_and_ignores_stale_reply(tmp_path, monkeypatch):
    import json
    from dataclasses import replace

    from tests.fixtures.podcast import podcast_layout, podcast_session

    monkeypatch.setenv("APPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    window = InternalActionMainWindow(
        config=load_config(ROOT / "config/defaults.json"), root=tmp_path, use_mock=False
    )
    panel = window._transcript_panel
    panel._layout = podcast_layout()
    panel._set_session(replace(podcast_session(), layout_fingerprint=panel._layout.fingerprint))
    panel._preview()
    plan = panel._plan
    assert plan is not None and not plan.blocked
    panel._send_plan(apply=False)
    request_file = tmp_path / "O Editor/plans/menu-action.json"
    original = request_file.read_bytes()
    assert not panel.apply_button.isEnabled() and not panel.validate_button.isEnabled()
    panel._send_plan(apply=False)
    assert request_file.read_bytes() == original
    request = json.loads(original)
    for plan_id in ("stale", plan.plan_id):
        reply = create_internal_action_request(
            "apply_rough_cut",
            status="SUCCESS",
            message="Plano conferido",
            details={"plan_id": plan_id, "mode": request["mode"]},
            requests_directory=tmp_path / "requests",
        )
        window.handle_ipc_message({"type": "internal_action_request", "path": str(reply)})
        assert panel.apply_button.isEnabled() == (plan_id == plan.plan_id)
    assert panel._layout is not None and panel._session is not None
    assert panel._plan is plan
    window.close()
    app.processEvents()


def test_pending_request_expiration_is_visible_and_allows_retry(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    window = InternalActionMainWindow(
        config=load_config(ROOT / "config/defaults.json"), root=tmp_path, use_mock=False
    )
    panel = window._transcript_panel
    panel._pending_plan_id = "expired"
    panel._pending_mode = "VALIDATE"
    panel._resolve_request_expired()
    assert panel._pending_plan_id is None
    assert "não confirmou" in panel.status_label.text()
    assert "não confirmou" in panel.preview_text.toPlainText()
    window.close()
    app.processEvents()


def test_result_file_is_received_even_when_launcher_ipc_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    window = InternalActionMainWindow(
        config=load_config(ROOT / "config/defaults.json"), root=tmp_path, use_mock=False
    )
    path = create_internal_action_request(
        "apply_rough_cut",
        status="SUCCESS",
        message="Resultado recebido por arquivo",
        details={"plan_id": "p1", "mode": "VALIDATE"},
    )
    window._poll_rough_cut_replies()
    text = window._transcript_panel.preview_text.toPlainText()
    assert "Resultado recebido por arquivo" in text
    assert window._workflow_buttons[3].isChecked()
    window._poll_rough_cut_replies()
    assert window._transcript_panel.preview_text.toPlainText() == text
    assert path.exists()
    window.close()
    app.processEvents()
