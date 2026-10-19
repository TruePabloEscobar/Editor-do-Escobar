"""Local transcription settings with asynchronous hardware discovery."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from o_editor.errors import ConfigurationError
from o_editor.infrastructure.config import (
    AppConfig,
    save_transcription_settings,
    settings_config_path,
)
from o_editor.infrastructure.transcription.local_model import validate_local_model
from o_editor.ui.about_window import AboutDialog
from o_editor.ui.model_download_window import ModelDownloadDialog


class SettingsDialog(QDialog):
    def __init__(
        self,
        config: AppConfig,
        parent: QWidget | None = None,
        *,
        config_path: Path | None = None,
        discover: bool = True,
        diagnostics: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._config_path = config_path
        self.selected_config: AppConfig | None = None
        self._discover = discover
        self._editable = True
        self._download_dialog: ModelDownloadDialog | None = None
        self._about_dialog: AboutDialog | None = None
        self.setWindowTitle("Configurações — EDE")
        self.setMinimumWidth(620)
        outer = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.config_page = QWidget()
        layout = QVBoxLayout(self.config_page)
        self.tabs.addTab(self.config_page, "Transcrição")
        if diagnostics is not None:
            self.tabs.addTab(diagnostics, "Diagnóstico")
            self.setMinimumSize(760, 600)
        outer.addWidget(self.tabs, 1)
        form = QFormLayout()
        self.model_path = QLineEdit(config.transcription.model_path or "")
        self.model_path.setAccessibleName("Pasta do modelo local")
        self.model_path.setToolTip(config.transcription.model_path or "")
        self.model_path.textChanged.connect(self.model_path.setToolTip)
        self.model_path.setPlaceholderText("Pasta faster-whisper / CTranslate2")
        browse = QPushButton("Carregar modelo…")
        browse.clicked.connect(self._browse_model)
        model_row = QHBoxLayout()
        model_row.addWidget(self.model_path, 1)
        model_row.addWidget(browse)
        form.addRow("Modelo local", model_row)
        hint = QLabel(
            "Selecione a pasta com model.bin, config.json e tokenizer.json.\n"
            "Whisper convertido para CTranslate2. O download só começa se você solicitar."
        )
        hint.setWordWrap(True)
        form.addRow(hint)
        self.download_button = QPushButton("Baixar modelo…")
        self.download_button.clicked.connect(self._open_download)
        form.addRow(self.download_button)
        self.device_combo = QComboBox()
        self.device_combo.setAccessibleName("Processamento da transcrição")
        self.device_combo.addItem("Automático (GPU disponível / CPU)", "auto:0")
        self.device_combo.addItem("CPU", "cpu:0")
        configured = config.transcription
        requested = f"{configured.device}:{configured.device_index}"
        self._devices_ready = False
        if configured.device == "cuda":
            self.device_combo.addItem(f"GPU {configured.device_index} — verificando…", requested)
        self.device_combo.setCurrentIndex(max(0, self.device_combo.findData(requested)))
        form.addRow("Dispositivo", self.device_combo)
        self.device_status = QLabel("Verificando GPUs CUDA…")
        self.device_status.setWordWrap(True)
        form.addRow(self.device_status)
        layout.addLayout(form)
        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        note = QLabel(
            "As alterações valem para a próxima transcrição. Sessões anteriores são preservadas."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Salvar")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        self.buttons.accepted.connect(self._save)
        self.buttons.rejected.connect(self.reject)
        footer = QHBoxLayout()
        self.about_button = QPushButton("Sobre")
        self.about_button.clicked.connect(self._open_about)
        footer.addWidget(self.about_button)
        footer.addStretch()
        footer.addWidget(self.buttons)
        outer.addLayout(footer)
        self.tabs.currentChanged.connect(self._update_save_button)
        self._probe = QProcess(self)
        self._probe.finished.connect(self._discovery_finished)
        self._probe.errorOccurred.connect(self._discovery_failed)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._discovery_failed)
        self.finished.connect(self._stop_probe)
        self.finished.connect(self._close_download)
        if discover:
            self.refresh_devices()
        else:
            self.set_devices([])

    def refresh_devices(self) -> None:
        if self._discover and self._probe.state() == QProcess.ProcessState.NotRunning:
            self._devices_ready = False
            self.device_status.setText("Verificando GPUs CUDA…")
            self._probe.start(
                sys.executable, ["-m", "o_editor.infrastructure.transcription.devices"]
            )
            self._timeout.start(8000)

    def reset_config(self, config: AppConfig) -> None:
        self._config = config
        self.selected_config = None
        self.error_label.clear()
        self.model_path.setText(config.transcription.model_path or "")
        selected = f"{config.transcription.device}:{config.transcription.device_index}"
        position = self.device_combo.findData(selected)
        if position < 0:
            self.device_combo.addItem(
                f"GPU {config.transcription.device_index} — verificando…", selected
            )
            position = self.device_combo.count() - 1
        self.device_combo.setCurrentIndex(position)

    def set_editable(self, editable: bool) -> None:
        self._editable = editable
        self.config_page.setEnabled(editable)
        self._update_save_button()

    def _update_save_button(self) -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setEnabled(
            self._editable and self.tabs.currentWidget() is self.config_page
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(
            "Cancelar" if self.tabs.currentWidget() is self.config_page else "Fechar"
        )

    def _browse_model(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Carregar modelo local", self.model_path.text()
        )
        if path:
            self.model_path.setText(path)

    def _open_download(self) -> None:
        if not self._editable:
            return
        if self._download_dialog is None:
            self._download_dialog = ModelDownloadDialog(self)
            self._download_dialog.model_ready.connect(self.model_path.setText)
        self._download_dialog.open()

    def _close_download(self) -> None:
        if self._download_dialog is not None:
            self._download_dialog.reject()

    def _open_about(self) -> None:
        if self._about_dialog is None:
            self._about_dialog = AboutDialog(self)
        self._about_dialog.open()

    def set_devices(self, devices: list[dict[str, Any]]) -> None:
        selected = self.device_combo.currentData()
        self.device_combo.clear()
        self.device_combo.addItem("Automático (GPU disponível / CPU)", "auto:0")
        self.device_combo.addItem("CPU", "cpu:0")
        for device in devices:
            index = int(device["index"])
            self.device_combo.addItem(f"GPU {index} — {device['name']}", f"cuda:{index}")
        position = self.device_combo.findData(selected)
        if position < 0 and selected and selected.startswith("cuda:"):
            self.device_combo.addItem(f"GPU {selected.split(':')[1]} — indisponível", selected)
            position = self.device_combo.count() - 1
            cast(QStandardItemModel, self.device_combo.model()).item(position).setEnabled(False)
        self.device_combo.setCurrentIndex(max(0, position))
        self._devices_ready = True
        self.device_status.setText(
            "GPUs NVIDIA CUDA disponíveis. Outros aceleradores não são suportados por este motor."
            if devices
            else "Nenhuma GPU CUDA detectada. Use CPU ou Automático."
        )

    def _discovery_finished(self) -> None:
        self._timeout.stop()
        try:
            data = json.loads(bytes(self._probe.readAllStandardOutput().data()).decode())
            self.set_devices(data["devices"])
        except (ValueError, KeyError, TypeError):
            self.set_devices([])

    def _discovery_failed(self) -> None:
        self._stop_probe()
        self.set_devices([])

    def _stop_probe(self) -> None:
        self._timeout.stop()
        if self._probe.state() != QProcess.ProcessState.NotRunning:
            self._probe.kill()
            self._probe.waitForFinished(500)

    def _save(self) -> None:
        if not self._editable or self.tabs.currentWidget() is not self.config_page:
            return
        try:
            path = validate_local_model(Path(self.model_path.text().strip()))
            selection = str(self.device_combo.currentData() or "")
            device, _, ordinal = selection.partition(":")
            index = int(ordinal)
            item = cast(QStandardItemModel, self.device_combo.model()).item(
                self.device_combo.currentIndex()
            )
            if device == "cuda" and (not self._devices_ready or not item.isEnabled()):
                raise ConfigurationError(
                    "A GPU selecionada não está disponível. Escolha CPU ou Automático."
                )
            old = self._config.transcription
            same_path = old.model_path and Path(old.model_path).resolve() == path
            section = replace(
                old,
                model_path=str(path),
                model=old.model if same_path else path.name,
                device=device,
                device_index=index,
                compute_type=old.compute_type if device == old.device else "auto",
            )
            save_transcription_settings(section, self._config_path or settings_config_path())
            self.selected_config = replace(self._config, transcription=section)
        except (ConfigurationError, OSError, ValueError) as exc:
            self.error_label.setText(str(exc))
            return
        self.accept()
