"""Per-execution zoom choice, with Cancel as the safe default."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from o_editor.ui.theme import label


class RoughCutConfirmation(QDialog):
    def __init__(self, target: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Aplicar Rough Cut")
        self.choice: str | None = None
        layout = QVBoxLayout(self)
        layout.addWidget(label("Como deseja aplicar os zooms nos takes da nova timeline?"))
        notice = label(f"Nova timeline: {target}\nA timeline original será preservada.", "muted")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        row = QHBoxLayout()
        self.apply_button = QPushButton("APLICAR")
        self.apply_button.setProperty("role", "primary")
        self.apply_button.setToolTip("Aplica o zoom por take junto aos cortes.")
        self.review_button = QPushButton("REVISAR")
        self.review_button.setToolTip(
            "Aplica somente os cortes, para que você ajuste o zoom posteriormente."
        )
        self.cancel_button = QPushButton("CANCELAR")
        self.cancel_button.setDefault(True)
        for button, name in ((self.apply_button, "apply"), (self.review_button, "review")):
            button.clicked.connect(lambda _checked=False, value=name: self._choose(value))
            row.addWidget(button)
        row.addWidget(self.cancel_button)
        self.cancel_button.clicked.connect(self.reject)
        layout.addLayout(row)

    def _choose(self, choice: str) -> None:
        self.choice = choice
        self.accept()
