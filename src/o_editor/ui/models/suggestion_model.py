"""Editable Qt model for suggestion review."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    Qt,
)

from o_editor.domain.models import Suggestion, TextSuggestion
from o_editor.domain.timecode import frames_to_timecode

INVALID_INDEX = QModelIndex()
ModelIndex = QModelIndex | QPersistentModelIndex


class SuggestionTableModel(QAbstractTableModel):
    COLUMNS = (
        "Aprovado",
        "Timecode",
        "Tipo",
        "Conteúdo",
        "Intensidade",
        "Duração",
        "Confiança",
        "Motivo",
        "Conflito",
    )

    def __init__(
        self,
        suggestions: tuple[Suggestion, ...] = (),
        *,
        fps: float = 30.0,
        drop_frame: bool = False,
    ) -> None:
        super().__init__()
        self._suggestions = list(suggestions)
        self._fps = fps
        self._drop_frame = drop_frame

    @property
    def suggestions(self) -> tuple[Suggestion, ...]:
        return tuple(self._suggestions)

    def replace_suggestions(
        self,
        suggestions: tuple[Suggestion, ...],
        *,
        fps: float,
        drop_frame: bool,
    ) -> None:
        self.beginResetModel()
        self._suggestions = list(suggestions)
        self._fps = fps
        self._drop_frame = drop_frame
        self.endResetModel()

    def rowCount(self, parent: ModelIndex = INVALID_INDEX) -> int:
        return 0 if parent.isValid() else len(self._suggestions)

    def columnCount(self, parent: ModelIndex = INVALID_INDEX) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        if (
            orientation is Qt.Orientation.Horizontal
            and role == int(Qt.ItemDataRole.DisplayRole)
            and 0 <= section < len(self.COLUMNS)
        ):
            return self.COLUMNS[section]
        return super().headerData(section, orientation, role)

    def data(
        self,
        index: ModelIndex,
        role: int = int(Qt.ItemDataRole.DisplayRole),
    ) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._suggestions):
            return None
        suggestion = self._suggestions[index.row()]
        column = index.column()
        if role == int(Qt.ItemDataRole.CheckStateRole) and column == 0:
            return Qt.CheckState.Checked if suggestion.approved else Qt.CheckState.Unchecked
        if role not in (
            int(Qt.ItemDataRole.DisplayRole),
            int(Qt.ItemDataRole.EditRole),
        ):
            return None
        values: tuple[Any, ...] = (
            "",
            frames_to_timecode(
                suggestion.timeline_start_frame,
                self._fps,
                drop_frame=self._drop_frame,
            ),
            f"{suggestion.kind.value}: {suggestion.subtype}",
            suggestion.text if isinstance(suggestion, TextSuggestion) else "Zoom dinâmico",
            suggestion.parameter_map.get("zoom_peak", "—"),
            f"{(suggestion.timeline_end_frame - suggestion.timeline_start_frame) / self._fps:.2f}s",
            f"{suggestion.confidence:.0%}",
            ", ".join(suggestion.reason_codes) or "—",
            suggestion.conflict_reason or "—",
        )
        return values[column]

    def flags(self, index: ModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = super().flags(index) | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 0:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        if index.column() == 3 and isinstance(self._suggestions[index.row()], TextSuggestion):
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(
        self,
        index: ModelIndex,
        value: Any,
        role: int = int(Qt.ItemDataRole.EditRole),
    ) -> bool:
        if not index.isValid() or not 0 <= index.row() < len(self._suggestions):
            return False
        suggestion = self._suggestions[index.row()]
        if role == int(Qt.ItemDataRole.CheckStateRole) and index.column() == 0:
            suggestion = suggestion.with_approval(value == Qt.CheckState.Checked)
        elif (
            role == int(Qt.ItemDataRole.EditRole)
            and index.column() == 3
            and isinstance(suggestion, TextSuggestion)
        ):
            text = str(value).strip()
            if not text:
                return False
            suggestion = suggestion.with_text(text)
        else:
            return False
        self._suggestions[index.row()] = suggestion
        self.dataChanged.emit(index, index, [role])
        return True

    def set_all_approved(self, approved: bool, *, kind: str | None = None) -> None:
        if not self._suggestions:
            return
        self._suggestions = [
            suggestion.with_approval(approved)
            if kind is None or suggestion.kind.value == kind
            else suggestion
            for suggestion in self._suggestions
        ]
        top_left = self.index(0, 0)
        bottom_right = self.index(len(self._suggestions) - 1, 0)
        self.dataChanged.emit(
            top_left,
            bottom_right,
            [int(Qt.ItemDataRole.CheckStateRole)],
        )

    def suggestion_at(self, row: int) -> Suggestion | None:
        return self._suggestions[row] if 0 <= row < len(self._suggestions) else None
