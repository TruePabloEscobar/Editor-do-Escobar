"""Separate editing scopes and diagnostics inside reusable settings, without blocking IPC."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialogButtonBox

from o_editor.application.analyze_timeline import analyze_with_mock
from o_editor.domain.enums import SuggestionKind
from o_editor.infrastructure.config import load_config
from o_editor.ui.internal_action_runtime import InternalActionMainWindow
from o_editor.ui.qt_runtime import configure_headless_qt_environment
from o_editor.ui.settings_window import SettingsDialog

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def window(tmp_path, monkeypatch):
    configure_headless_qt_environment()
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("APPDATA", str(tmp_path))

    class Dialog(SettingsDialog):
        def __init__(self, config, parent, **kwargs):
            super().__init__(config, parent, discover=False, **kwargs)

    monkeypatch.setattr("o_editor.ui.main_window.SettingsDialog", Dialog)
    config = load_config(ROOT / "config/defaults.json")
    value = InternalActionMainWindow(config=config, root=tmp_path, use_mock=True)
    value.show()
    app.processEvents()
    yield value, app
    value.close()
    app.processEvents()


@pytest.mark.parametrize("width", [1000, 1280])
def test_zoom_and_captions_approve_and_export_only_their_own_scope(window, tmp_path, width):
    value, app = window
    value.resize(width, 680)
    result = analyze_with_mock(value._config, tmp_path / "analysis")
    value._analysis_finished(result)
    assert [b.text() for b in value._workflow_buttons][-2:] == ["Zoom", "Legendas"]
    assert all("Diagnóstico" not in b.text() for b in value._workflow_buttons)
    value._workflow_buttons[4].click()
    app.processEvents()
    assert value._zoom_intensity.isVisible()
    assert not value._text_frequency.isVisible()
    assert value._proxy.rowCount() > 0
    value._approve_suggestions_button.click()
    zoom_approvals = {
        s.id: s.approved for s in value._model.suggestions if s.kind == SuggestionKind.ZOOM
    }
    assert all(zoom_approvals.values())
    assert not any(s.approved for s in value._model.suggestions if s.kind == SuggestionKind.TEXT)
    saved = tmp_path / "O Editor/plans/latest-approved-plan.json"
    assert json.loads(saved.read_text(encoding="utf-8"))["texts"] == []
    value._workflow_buttons[5].click()
    app.processEvents()
    button = value._workflow_buttons[5]
    assert button.width() >= button.fontMetrics().horizontalAdvance(button.text()) + 16
    assert value._text_frequency.isVisible()
    assert not value._zoom_intensity.isVisible()
    assert all(s.kind == SuggestionKind.TEXT for s in value._current_suggestions())
    value._approve_suggestions_button.click()
    captions = json.loads(saved.read_text(encoding="utf-8"))
    assert captions["texts"] and captions["zooms"] == []
    # The explicit apply/save path also excludes approved zooms hidden in the other section.
    from o_editor.infrastructure.resolve.mock_adapter import MockResolveAdapter

    value._adapter = MockResolveAdapter()
    value._use_mock = False  # Exercise the save-for-host branch; do not dispatch a worker.
    value._start_apply()
    captions = json.loads(saved.read_text(encoding="utf-8"))
    assert captions["texts"] and captions["zooms"] == []
    assert {
        s.id: s.approved for s in value._model.suggestions if s.kind == SuggestionKind.ZOOM
    } == zoom_approvals
    value._reject_suggestions_button.click()
    assert not any(s.approved for s in value._current_suggestions())
    value._workflow_buttons[4].click()
    assert all(s.approved for s in value._current_suggestions())


def test_diagnostics_is_inside_settings_and_closing_keeps_reports(window):
    value, app = window
    value._settings_button.click()
    app.processEvents()
    dialog = value._settings_dialog
    assert dialog.tabs.tabText(1) == "Diagnóstico"
    dialog.tabs.setCurrentIndex(1)
    app.processEvents()
    assert value._report.isVisible()
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled()
    value._report.setPlainText("Saved diagnostic")
    dialog.reject()
    value._settings_button.click()
    app.processEvents()
    assert value._settings_dialog is dialog
    assert value._report.toPlainText() == "Saved diagnostic"
    assert dialog.tabs.currentIndex() == 0
    dialog.reject()


def test_incoming_diagnostic_ack_returns_while_settings_is_open(window):
    value, app = window
    # A blocking exec() would wait for this fallback and leave the dialog closed.
    QTimer.singleShot(100, lambda: value._settings_dialog.reject())
    reply = value.handle_ipc_message({"type": "show_message", "message": "Controlled failure"})
    dialog = value._settings_dialog
    assert reply["handled"] == "show_message"
    assert dialog.isVisible()
    assert dialog.tabs.currentWidget() is value._diagnostics_page
    assert value._report.toPlainText() == "Controlled failure"
    dialog.reject()
    app.processEvents()
