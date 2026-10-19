"""Settings, asynchronous download outcomes and tutorial survive cancel/reopen."""

import json
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QApplication

from o_editor.infrastructure.config import load_config
from o_editor.infrastructure.transcription.download import models_directory
from o_editor.ui.about_window import DEVELOPER_URL
from o_editor.ui.qt_runtime import configure_headless_qt_environment
from o_editor.ui.settings_window import SettingsDialog
from tests.integration.test_model_download import model


def test_settings_download_success_requires_save_and_about_has_credits(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    configure_headless_qt_environment()
    app = QApplication.instance() or QApplication([])
    config = load_config(Path(__file__).resolve().parents[2] / "config/defaults.json")
    settings = SettingsDialog(config, discover=False, config_path=tmp_path / "config.json")
    settings.show()
    settings.about_button.click()
    app.processEvents()
    about = settings._about_dialog
    assert about is not None and about.isVisible()
    assert "Pablo Escobar" in about.content.toPlainText()
    assert DEVELOPER_URL in about.content.toHtml()
    assert "Atualizar timeline" in about.content.toPlainText()
    assert "Aplicar Rough Cut" in about.content.toPlainText()
    about.reject()
    settings.download_button.click()
    app.processEvents()
    dialog = settings._download_dialog
    assert dialog is not None and dialog.isVisible()
    assert dialog._process.state() == QProcess.ProcessState.NotRunning
    path = models_directory() / "tiny"
    model(path)
    dialog._output.extend(json.dumps({"ok": True, "path": str(path)}).encode())
    dialog._finished(0)
    assert settings.model_path.text() == str(path)
    assert not (tmp_path / "config.json").exists()
    assert settings.selected_config is None
    # A later download can be started; old success must not leave the button disabled.
    settings.download_button.click()
    assert dialog.start_button.isEnabled()
    settings.reject()
    assert not dialog.isVisible()


def test_cancel_stops_child_and_failure_keeps_current_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    configure_headless_qt_environment()
    app = QApplication.instance() or QApplication([])
    settings = SettingsDialog(
        load_config(Path(__file__).resolve().parents[2] / "config/defaults.json"), discover=False
    )
    settings.show()
    before = settings.model_path.text()
    settings.download_button.click()
    dialog = settings._download_dialog
    assert dialog is not None
    dialog._output.extend(b'{"ok":false}')
    dialog._finished(1)
    assert "Não foi possível" in dialog.status.text()
    assert settings.model_path.text() == before
    dialog._process.start(sys.executable, ["-c", "import time; time.sleep(30)"])
    assert dialog._process.waitForStarted(3000)
    dialog.reject()
    assert (
        dialog._process.waitForFinished(3000)
        or dialog._process.state() == QProcess.ProcessState.NotRunning
    )
    assert settings.model_path.text() == before
    settings.reject()
    app.processEvents()


@pytest.mark.parametrize(
    "payload",
    [
        b"[]",
        b'"unexpected"',
        b'{"ok":true}',
        b"not json",
        b'{"ok":true,"path":null}',
        b'{"ok":true,"path":[]}',
    ],
)
def test_malformed_child_output_is_reported_without_replacing_model(tmp_path, monkeypatch, payload):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    configure_headless_qt_environment()
    app = QApplication.instance() or QApplication([])
    settings = SettingsDialog(
        load_config(Path(__file__).resolve().parents[2] / "config/defaults.json"), discover=False
    )
    before = settings.model_path.text()
    settings.download_button.click()
    dialog = settings._download_dialog
    assert dialog is not None
    dialog._output.extend(payload)
    dialog._finished(0)
    assert "Não foi possível" in dialog.status.text()
    assert settings.model_path.text() == before
    settings.reject()
    app.processEvents()
