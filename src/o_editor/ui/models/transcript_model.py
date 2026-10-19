"""Qt model for reviewing and correcting the multi-track transcript."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
)

from o_editor.domain.speech import SegmentFlag, SegmentState, SpeechSegment, TranscriptSession
from o_editor.domain.timecode import frames_to_clock, frames_to_timecode

COLUMNS = ("Manter", "ID", "Participante", "Faixa", "Início", "Fim", "TC", "Marcações", "Texto")
KEEP_COLUMN = 0
TEXT_COLUMN = 8
ModelIndex = QModelIndex | QPersistentModelIndex


class TranscriptTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._session: TranscriptSession | None = None
        self._rows: list[SpeechSegment] = []

    @property
    def session(self) -> TranscriptSession | None:
        return self._session

    def set_session(self, session: TranscriptSession | None) -> None:
        self.beginResetModel()
        self._session = session
        self._rows = (
            sorted(session.segments, key=lambda item: (item.start_frame, item.track_index))
            if session
            else []
        )
        self.endResetModel()

    def segments(self) -> tuple[SpeechSegment, ...]:
        return tuple(self._rows)

    def segment_at(self, row: int) -> SpeechSegment | None:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def rowCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: ModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index: ModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or self._session is None:
            return None
        segment = self._rows[index.row()]
        session = self._session
        column = index.column()
        if role == Qt.ItemDataRole.CheckStateRole and column == KEEP_COLUMN:
            return (
                Qt.CheckState.Checked
                if segment.state == SegmentState.KEEP
                else Qt.CheckState.Unchecked
            )
        if role == Qt.ItemDataRole.UserRole:
            return segment.track_index
        if role == Qt.ItemDataRole.ToolTipRole:
            if segment.is_bleed and segment.related_segment_id:
                return f"Vazamento da fala {segment.related_segment_id}; não protege o intervalo."
            if segment.text_corrected:
                return f"Texto original: {segment.original_text}"
            return None
        if role not in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return None
        if column == KEEP_COLUMN:
            return segment.state.value
        if column == 1:
            return segment.segment_id
        if column == 2:
            return session.speaker_name(segment.track_index)
        if column == 3:
            return segment.track_key
        if column == 4:
            return frames_to_clock(segment.start_frame - session.start_frame, session.fps)
        if column == 5:
            return frames_to_clock(segment.end_frame - session.start_frame, session.fps)
        if column == 6:
            return frames_to_timecode(
                segment.start_frame, session.fps, drop_frame=session.drop_frame
            )
        if column == 7:
            return ", ".join(sorted(flag.value for flag in segment.flags))
        if column == TEXT_COLUMN:
            return segment.text
        return None

    def flags(self, index: ModelIndex) -> Qt.ItemFlag:
        base = super().flags(index)
        if not index.isValid():
            return base
        if index.column() == KEEP_COLUMN:
            return base | Qt.ItemFlag.ItemIsUserCheckable
        if index.column() == TEXT_COLUMN:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def setData(self, index: ModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or self._session is None:
            return False
        row = index.row()
        segment = self._rows[row]
        if index.column() == KEEP_COLUMN and role == Qt.ItemDataRole.CheckStateRole:
            checked = value in (Qt.CheckState.Checked, Qt.CheckState.Checked.value, 2, True)
            updated = segment.with_state(SegmentState.KEEP if checked else SegmentState.CUT)
        elif index.column() == TEXT_COLUMN and role == Qt.ItemDataRole.EditRole:
            text = " ".join(str(value).split())
            if not text:
                return False
            updated = replace(segment, text=text)
        else:
            return False
        if updated == segment:
            return False
        self._rows[row] = updated
        lookup = {item.segment_id: item for item in self._rows}
        self._session = replace(
            self._session,
            segments=tuple(lookup.get(item.segment_id, item) for item in self._session.segments),
        )
        self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMNS) - 1))
        return True


class TranscriptFilterModel(QSortFilterProxyModel):
    """Filter by participant track, free text, and bleed visibility."""

    def __init__(self) -> None:
        super().__init__()
        self._track: int | None = None
        self._text = ""
        self._show_bleed = False

    def set_track(self, track: int | None) -> None:
        self._track = track
        self.invalidateFilter()

    def set_text(self, text: str) -> None:
        self._text = text.casefold().strip()
        self.invalidateFilter()

    def set_show_bleed(self, show: bool) -> None:
        self._show_bleed = show
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: ModelIndex) -> bool:
        model = self.sourceModel()
        if not isinstance(model, TranscriptTableModel):
            return True
        segment = model.segment_at(source_row)
        if segment is None:
            return False
        if self._track is not None and segment.track_index != self._track:
            return False
        if (
            segment.is_bleed
            and not self._show_bleed
            and self._track is None
            and SegmentFlag.BLEED in segment.flags
        ):
            return False
        if self._text and self._text not in segment.text.casefold():
            return self._text in segment.segment_id.casefold()
        return True
