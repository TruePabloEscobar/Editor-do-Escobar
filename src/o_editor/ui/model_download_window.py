"""Cancelable model download outside the GUI and Resolve processes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from o_editor.errors import ConfigurationError
from o_editor.infrastructure.transcription.download import MODEL_REPOSITORIES, models_directory
from o_editor.infrastructure.transcription.local_model import validate_local_model


class ModelDownloadDialog(QDialog):
    model_ready = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Baixar modelo — EDE")
        self.setMinimumWidth(520)
        self._closing = False
        self._output = bytearray()
        layout = QVBoxLayout(self)
        self.preset = QComboBox()
        for name in MODEL_REPOSITORIES:
            self.preset.addItem(name, name)
        layout.addWidget(QLabel("Modelo de transcrição"))
        layout.addWidget(self.preset)
        note = QLabel(
            "Download do Hugging Face. Modelos maiores podem ocupar vários GB.\n"
            "Depois de baixar, clique em Salvar nas configurações para usá-lo.\n"
            "Seus áudios não são enviados."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        self.status = QLabel("Pronto para baixar.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        row = QHBoxLayout()
        self.start_button = QPushButton("Baixar modelo")
        self.start_button.clicked.connect(self._start)
        row.addWidget(self.start_button)
        self.cancel_button = QPushButton("Fechar")
        self.cancel_button.clicked.connect(self.reject)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)
        self._process = QProcess(self)
        self._process.readyReadStandardOutput.connect(self._read_output)
        self._process.readyReadStandardError.connect(self._drain_errors)
        self._process.finished.connect(self._finished)
        self._process.errorOccurred.connect(self._failed)

    def _start(self) -> None:
        if self._process.state() != QProcess.ProcessState.NotRunning:
            return
        self._output.clear()
        self._closing = False
        self.start_button.setEnabled(False)
        self.preset.setEnabled(False)
        self.cancel_button.setText("Cancelar download")
        self.progress.setRange(0, 0)
        self.status.setText("Baixando… Você pode cancelar sem alterar o modelo atual.")
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("HF_HUB_DISABLE_TELEMETRY", "1")
        environment.insert("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
        self._process.setProcessEnvironment(environment)
        self._process.start(
            sys.executable,
            [
                "-m",
                "o_editor.infrastructure.transcription.download",
                "--preset",
                str(self.preset.currentData()),
            ],
        )

    def _read_output(self) -> None:
        self._output.extend(bytes(self._process.readAllStandardOutput().data()))
        del self._output[:-16384]

    def _drain_errors(self) -> None:
        self._process.readAllStandardError()  # Drain progress without retaining huge logs.

    def _finished(self, code: int) -> None:
        if self._closing:
            return
        self._read_output()
        try:
            result = json.loads(self._output.decode("utf-8").strip().splitlines()[-1])
            if code or not isinstance(result, dict) or result.get("ok") is not True:
                raise ValueError("download incompleto")
            raw_path = result.get("path")
            if not isinstance(raw_path, str) or not raw_path:
                raise ValueError("destino inválido")
            path = validate_local_model(Path(raw_path))
            # A subprocess result is data, not authority to select an arbitrary folder.
            if path.parent != models_directory().resolve():
                raise ValueError("destino inesperado")
        except (ConfigurationError, ValueError, KeyError, IndexError, OSError):
            self._failed()
            return
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.status.setText("Modelo baixado. Salve as configurações para selecioná-lo.")
        self.cancel_button.setText("Fechar")
        self.start_button.setEnabled(True)
        self.preset.setEnabled(True)
        self.model_ready.emit(str(path))
        self.accept()

    def _failed(self) -> None:
        if self._closing:
            return
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.status.setText(
            "Não foi possível concluir. Verifique internet, espaço em disco e a instalação "
            "das dependências de transcrição. Seu modelo atual foi preservado."
        )
        self.start_button.setEnabled(True)
        self.preset.setEnabled(True)
        self.cancel_button.setText("Fechar")

    def reject(self) -> None:
        self._closing = True
        if self._process.state() != QProcess.ProcessState.NotRunning:
            self._process.kill()
            self._process.waitForFinished(500)
        super().reject()
