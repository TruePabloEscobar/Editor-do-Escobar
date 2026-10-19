"""Opt-out, preference persistence and preview invalidation use real Qt controls."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from o_editor.domain.timeline_layout import TimelineLayout
from o_editor.infrastructure.config import load_config
from o_editor.ui.main_window import MainWindow
from o_editor.ui.qt_runtime import configure_headless_qt_environment
from tests.unit.test_microphone_cleanup import session

ROOT = Path(__file__).resolve().parents[2]


def test_cleanup_toggle_invalidates_preview_and_persists(tmp_path):
    configure_headless_qt_environment()
    app = QApplication.instance() or QApplication([])
    window = MainWindow(
        config=load_config(ROOT / "config/defaults.json"), root=tmp_path, use_mock=True
    )
    panel = window._transcript_panel
    value = session()
    panel._layout = TimelineLayout.from_dict(dict(value.layout))
    panel._set_session(value)
    panel._preview()
    assert panel.cleanup_microphones.isChecked()
    assert panel._plan is not None and panel._plan.microphone_cleanup.enabled
    panel.cleanup_microphones.click()
    assert panel._plan is None
    panel._preview()
    assert panel._plan is not None and not panel._plan.microphone_cleanup.enabled
    assert panel._plan.microphone_mutes == ()
    panel._pending_plan_id = "a" * 32
    panel._pending_mode = "VALIDATE"
    panel._update_buttons()
    assert not panel.cleanup_microphones.isEnabled()
    panel._pending_plan_id = None
    window.close()
    app.processEvents()
    second = MainWindow(
        config=load_config(ROOT / "config/defaults.json"), root=tmp_path, use_mock=True
    )
    assert not second._transcript_panel.cleanup_microphones.isChecked()
    second.close()
    app.processEvents()
