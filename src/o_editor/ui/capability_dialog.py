"""Non-blocking capability report viewer and probe launcher."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class CapabilityDialog(QDialog):
    def __init__(self, root: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._root = root
        self._process = QProcess(self)
        self.setWindowTitle("Diagnóstico de capacidades")
        self.resize(900, 620)
        layout = QVBoxLayout(self)
        self._status = QLabel("Relatório salvo mais recente")
        self._content = QTextEdit()
        self._content.setReadOnly(True)
        actions = QHBoxLayout()
        run_button = QPushButton("Executar probe somente leitura")
        close_button = QPushButton("Fechar")
        actions.addWidget(run_button)
        actions.addStretch()
        actions.addWidget(close_button)
        layout.addWidget(self._status)
        layout.addWidget(self._content)
        layout.addLayout(actions)
        run_button.clicked.connect(self._run_probe)
        close_button.clicked.connect(self.accept)
        self._process.finished.connect(self._probe_finished)
        self._load_report()

    def _load_report(self) -> None:
        path = self._root / "docs" / "RESOLVE_CAPABILITY_REPORT.md"
        if not path.exists():
            self._content.setPlainText("Nenhum relatório foi gerado.")
            return
        try:
            self._content.setPlainText(path.read_text(encoding="utf-8"))
        except OSError as exc:
            self._content.setPlainText(f"Não foi possível ler o relatório: {exc}")

    def _run_probe(self) -> None:
        if self._process.state() != QProcess.ProcessState.NotRunning:
            return
        self._status.setText("Executando probe somente leitura…")
        self._process.setWorkingDirectory(str(self._root))
        self._process.start(
            sys.executable,
            [
                "-m",
                "o_editor.infrastructure.resolve.capabilities",
                "--root",
                str(self._root),
            ],
        )

    def _probe_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        self._status.setText(
            "Probe concluído." if exit_code == 0 else "Probe concluído com limitações."
        )
        self._load_report()
