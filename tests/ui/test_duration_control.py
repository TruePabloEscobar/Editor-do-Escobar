from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from o_editor.ui.duration_control import DurationControl
from o_editor.ui.qt_runtime import configure_headless_qt_environment


@pytest.fixture
def app():
    configure_headless_qt_environment()
    return QApplication.instance() or QApplication([])


def test_duration_editor_accepts_seconds_and_syncs_slider(app):
    control = DurationControl(0, 20_000, 999, "Duração")
    control.show()
    assert control.editor.text() == "999 ms"
    control.slider.setValue(1000)
    assert control.value() == 1000
    assert control.editor.text() == "1 s"
    control.editor.lineEdit().selectAll()
    QTest.keyClicks(control.editor.lineEdit(), "1,25 s")
    QTest.keyClick(control.editor.lineEdit(), Qt.Key.Key_Return)
    assert control.value() == 1250
    assert control.slider.value() == 1250
    assert control.editor.text() == "1,25 s"
    control.setValue(350)
    assert control.editor.text() == "350 ms"
    control.close()


@pytest.mark.parametrize("fps", [23.976, 24, 25, 29.97, 30, 59.94, 60])
def test_unit_toggle_preserves_ms_and_frame_edits_round_trip(app, fps):
    control = DurationControl(0, 20_000, 1200, "Duração")
    changes = []
    control.valueChanged.connect(changes.append)
    for _ in range(4):
        control.set_display(True, fps)
        assert control.editor.text() == f"{round(1200 * fps / 1000)} frames"
        control.editor.interpretText()
        control.set_display(False, fps)
        assert control.value() == 1200
    assert changes == []
    control.set_display(True, fps)
    control.slider.setValue(24)
    assert round(control.value() * fps / 1000) == 24
    assert control.editor.text() == "24 frames"
    control.editor.stepBy(1)
    assert round(control.value() * fps / 1000) == 25
    assert control.slider.value() == 25
    control.editor.lineEdit().selectAll()
    QTest.keyClicks(control.editor.lineEdit(), "48")
    QTest.keyClick(control.editor.lineEdit(), Qt.Key.Key_Return)
    assert round(control.value() * fps / 1000) == 48
    assert control.slider.value() == 48
    control.close()


def test_units_do_not_invalidate_preview_but_slider_does(app, tmp_path):
    from dataclasses import replace

    from o_editor.infrastructure.config import load_config
    from o_editor.ui.main_window import MainWindow
    from tests.fixtures.podcast import podcast_layout, podcast_session

    root = Path(__file__).resolve().parents[2]
    window = MainWindow(
        config=load_config(root / "config/defaults.json"), root=tmp_path, use_mock=True
    )
    panel = window._transcript_panel
    panel._layout = podcast_layout()
    panel._set_session(replace(podcast_session(), layout_fingerprint=panel._layout.fingerprint))
    panel._duration_units_changed()
    panel._preview()
    plan = panel._plan
    assert plan is not None
    settings = panel.silence_settings()
    panel.frame_units_button.click()
    panel.time_units_button.click()
    assert panel.silence_settings() == settings
    assert panel._plan is plan
    panel.minimum_silence.slider.setValue(1600)
    assert panel._plan is None
    assert panel.preset_combo.currentData() == "CUSTOM"
    assert panel.silence_settings().minimum_silence_ms == 1600
    panel._pending_plan_id = "pending"
    panel._update_buttons()
    assert not panel.frame_units_button.isEnabled()
    assert not panel.minimum_silence.slider.isEnabled()
    window.close()
    app.processEvents()
