"""Settings persist the selected engine without overwriting other local configuration."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from itertools import pairwise
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from o_editor.infrastructure.config import load_config
from o_editor.ui.duration_control import DurationKnob
from o_editor.ui.main_window import MainWindow
from o_editor.ui.qt_runtime import configure_headless_qt_environment
from o_editor.ui.settings_window import SettingsDialog

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def app():
    configure_headless_qt_environment()
    return QApplication.instance() or QApplication([])


def model_folder(root: Path) -> Path:
    path = root / "new-whisper-model"
    path.mkdir()
    (path / "model.bin").write_bytes(b"synthetic-model")
    (path / "config.json").write_text("{}")
    (path / "tokenizer.json").write_text("{}")
    return path


def test_settings_save_reload_gpu_model_and_preserve_other_keys(app, tmp_path):
    path = tmp_path / "config.json"
    original = {"ffmpeg": {"ffmpeg_path": "C:/ffmpeg.exe"}, "custom": {"keep": True}}
    path.write_text(json.dumps(original), encoding="utf-8")
    config = load_config(ROOT / "config/defaults.json")
    dialog = SettingsDialog(config, config_path=path, discover=False)
    model = model_folder(tmp_path)
    dialog.model_path.setText(str(model))
    dialog.set_devices([{"index": 0, "name": "CUDA"}, {"index": 1, "name": "CUDA"}])
    dialog.device_combo.setCurrentIndex(dialog.device_combo.findData("cuda:1"))
    dialog._save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["ffmpeg"] == original["ffmpeg"]
    assert saved["custom"] == original["custom"]
    assert saved["transcription"]["model_path"] == str(model.resolve())
    assert saved["transcription"]["device_index"] == 1
    assert dialog.selected_config.transcription.device == "cuda"
    reloaded = load_config(ROOT / "config/defaults.json", path)
    assert reloaded.transcription == dialog.selected_config.transcription
    dialog.close()


def test_invalid_model_and_cancel_never_write_settings(app, tmp_path):
    config = load_config(ROOT / "config/defaults.json")
    target = tmp_path / "config.json"
    dialog = SettingsDialog(config, config_path=target, discover=False)
    dialog.model_path.setText(str(tmp_path))
    dialog._save()
    assert "model.bin" in dialog.error_label.text()
    assert dialog.selected_config is None and not target.exists()
    dialog.model_path.setText(str(model_folder(tmp_path)))
    dialog.reject()
    assert dialog.selected_config is None and not target.exists()


def test_saving_from_gear_updates_next_job_and_keeps_session_and_report(app, tmp_path, monkeypatch):
    from PySide6.QtCore import QTimer

    from tests.fixtures.podcast import podcast_layout, podcast_session

    config = load_config(ROOT / "config/defaults.json")
    window = MainWindow(config=config, root=tmp_path, use_mock=True)
    panel = window._transcript_panel
    panel._layout = podcast_layout()
    panel._set_session(podcast_session())
    session = panel._session
    window._report.setPlainText("Existing diagnostic result")
    model = model_folder(tmp_path)
    path = tmp_path / "saved-config.json"

    class Dialog(SettingsDialog):
        def __init__(self, config, parent, **kwargs):
            super().__init__(config, parent, config_path=path, discover=False, **kwargs)
            QTimer.singleShot(0, self._submit)

        def _submit(self):
            self.model_path.setText(str(model))
            self.device_combo.setCurrentIndex(self.device_combo.findData("cpu:0"))
            self._save()

    monkeypatch.setattr("o_editor.ui.main_window.SettingsDialog", Dialog)
    window._settings_button.click()
    app.processEvents()
    assert panel._config.transcription.model_path == str(model.resolve())
    assert panel._config is window._config
    assert panel._session is session
    assert window._report.toPlainText() == "Existing diagnostic result"
    assert (
        load_config(ROOT / "config/defaults.json", path).transcription
        == panel._config.transcription
    )
    window.close()
    app.processEvents()


def test_missing_saved_gpu_requires_explicit_new_choice(app, tmp_path):
    config = load_config(ROOT / "config/defaults.json")
    config = replace(
        config, transcription=replace(config.transcription, device="cuda", device_index=3)
    )
    target = tmp_path / "config.json"
    dialog = SettingsDialog(config, config_path=target, discover=False)
    dialog.model_path.setText(str(model_folder(tmp_path)))
    dialog._save()
    assert "GPU selecionada não está disponível" in dialog.error_label.text()
    assert not target.exists()
    dialog.device_combo.setCurrentIndex(dialog.device_combo.findData("cpu:0"))
    dialog._save()
    assert dialog.selected_config.transcription.device == "cpu"
    dialog.close()


@pytest.mark.parametrize("size", [(1000, 680), (1280, 820)])
def test_horizontal_stages_centered_brand_and_top_knobs_fit(app, tmp_path, size):
    window = MainWindow(
        config=load_config(ROOT / "config/defaults.json"), root=tmp_path, use_mock=True
    )
    window.show()
    window.resize(*size)
    window._navigate(3)
    app.processEvents()
    buttons = [*window._workflow_buttons, window._settings_button]
    positions = [button.mapTo(window, button.rect().topLeft()) for button in buttons]
    assert len({point.y() for point in positions}) == 1
    assert all(left.x() < right.x() for left, right in pairwise(positions))
    brand = window.findChild(QLabel, "brandTitle")
    center = brand.mapTo(window, brand.rect().center())
    assert abs(center.x() - window.width() // 2) < 3
    panel = window._transcript_panel
    for control in (panel.minimum_silence, panel.keep_before, panel.keep_after):
        assert isinstance(control.knob, DurationKnob)
        assert control.editor.y() > control.knob.y()
        assert (
            control.mapTo(panel, control.rect().bottomRight()).y()
            < panel.preview_text.mapTo(panel, panel.preview_text.rect().topLeft()).y()
        )
        assert control.geometry().bottom() <= control.parentWidget().height()
    window._busy = True
    window._update_refresh_availability()
    assert not window._settings_button.isEnabled()
    window.close()
    app.processEvents()


def test_knob_drag_keyboard_and_reset_keep_numeric_value_in_sync(app):
    from o_editor.ui.duration_control import DurationControl

    control = DurationControl(0, 3000, 250, "Antes da fala")
    control.show()
    knob = control.knob
    start = knob.rect().center()
    QTest.mousePress(knob, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(knob, start + type(start)(0, -25))
    QTest.mouseRelease(knob, Qt.MouseButton.LeftButton)
    assert control.value() > 250
    assert knob.value() == control.value()
    control.set_display(True, 24)
    previous = knob.value()
    QTest.keyClick(knob, Qt.Key.Key_Up)
    assert knob.value() == previous + 1
    assert control.editor.text() == f"{knob.value()} frames"
    QTest.mouseDClick(knob, Qt.MouseButton.LeftButton)
    assert control.value() == 250
    control.close()


@pytest.mark.parametrize("size", [(1000, 680), (1280, 820)])
def test_track_selection_actions_do_not_cover_the_table(app, tmp_path, size):
    window = MainWindow(
        config=load_config(ROOT / "config/defaults.json"), root=tmp_path, use_mock=True
    )
    window.resize(*size)
    window.show()
    app.processEvents()
    selector = window._voice_selector
    assert selector.table.geometry().bottom() < selector.select_all_button.y()
    assert selector.select_all_button.geometry().bottom() < selector.summary_label.y()
    window.close()
    app.processEvents()
