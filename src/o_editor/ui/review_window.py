"""Optional standalone review dialog using the shared suggestion model."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QTableView, QVBoxLayout, QWidget

from o_editor.ui.models.suggestion_model import SuggestionTableModel


class ReviewWindow(QDialog):
    def __init__(
        self,
        model: SuggestionTableModel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Revisar sugestões")
        self.resize(1000, 560)
        layout = QVBoxLayout(self)
        table = QTableView()
        table.setModel(model)
        table.resizeColumnsToContents()
        layout.addWidget(table)
