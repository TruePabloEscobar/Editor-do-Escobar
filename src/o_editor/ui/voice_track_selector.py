"""Voice-track selection widget for the main review interface."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from o_editor.domain.enums import ChannelMode
from o_editor.domain.voice_tracks import AudioTrackSnapshot, SelectedVoiceTrack


class VoiceTrackSelector(QGroupBox):
    selection_changed = Signal()

    def __init__(self) -> None:
        super().__init__("Faixas usadas para voz")
        self._tracks: tuple[AudioTrackSnapshot, ...] = ()
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(("Faixa de áudio", "Canal"))
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setMinimumHeight(110)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, 1)
        buttons = QHBoxLayout()
        self.select_all_button = QPushButton("Selecionar todas")
        self.clear_button = QPushButton("Limpar seleção")
        buttons.addWidget(self.select_all_button)
        buttons.addWidget(self.clear_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.suggestion_label = QLabel("Sugestão: nenhuma candidata clara")
        self.suggestion_label.setWordWrap(True)
        self.summary_label = QLabel("Voz: nenhuma faixa selecionada")
        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.hide()
        layout.addWidget(self.suggestion_label)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.warning_label)
        self.table.itemChanged.connect(lambda _item: self._emit_selection_changed())
        self.select_all_button.clicked.connect(self.select_all)
        self.clear_button.clicked.connect(self.clear_selection)

    @property
    def tracks(self) -> tuple[AudioTrackSnapshot, ...]:
        return self._tracks

    def set_tracks(
        self,
        tracks: tuple[AudioTrackSnapshot, ...],
        *,
        selected: tuple[SelectedVoiceTrack, ...] = (),
        suggested_indices: tuple[int, ...] = (),
        warnings: tuple[str, ...] = (),
    ) -> None:
        selected_map = {item.index: item for item in selected}
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self._tracks = tracks
        for row, track in enumerate(tracks):
            self.table.insertRow(row)
            label = QTableWidgetItem(_track_label(track))
            label.setData(Qt.ItemDataRole.UserRole, track.index)
            label.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            label.setCheckState(
                Qt.CheckState.Checked if track.index in selected_map else Qt.CheckState.Unchecked
            )
            if track.index in suggested_indices:
                label.setToolTip("Candidata sugerida pelo nome; confirme antes de analisar.")
            self.table.setItem(row, 0, label)
            combo = _channel_combo(track)
            restored = selected_map.get(track.index)
            if restored is not None:
                index = combo.findData(restored.channel_mode.value)
                combo.setCurrentIndex(max(0, index))
            combo.currentIndexChanged.connect(lambda _index: self._emit_selection_changed())
            self.table.setCellWidget(row, 1, combo)
        self.table.blockSignals(False)
        suggested_labels = [
            track.display_name for track in tracks if track.index in suggested_indices
        ]
        self.suggestion_label.setText(
            "Sugestão: " + ", ".join(suggested_labels)
            if suggested_labels
            else "Sugestão: nenhuma candidata clara"
        )
        self.warning_label.setText("\n".join(warnings))
        self.warning_label.setVisible(bool(warnings))
        self._update_summary()

    def selected_tracks(self) -> tuple[SelectedVoiceTrack, ...]:
        selected: list[SelectedVoiceTrack] = []
        tracks = {track.index: track for track in self._tracks}
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            index = int(item.data(Qt.ItemDataRole.UserRole))
            track = tracks.get(index)
            if track is None:
                continue
            combo = self.table.cellWidget(row, 1)
            value = combo.currentData() if isinstance(combo, QComboBox) else "both"
            selected.append(SelectedVoiceTrack(index, track.name, ChannelMode(str(value))))
        return tuple(selected)

    def select_indices(self, indices: set[int]) -> None:
        available = {track.index for track in self._tracks}
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is None:
                continue
            index = int(item.data(Qt.ItemDataRole.UserRole))
            item.setCheckState(
                Qt.CheckState.Checked
                if index in indices and index in available
                else Qt.CheckState.Unchecked
            )
        self._emit_selection_changed()

    def select_all(self) -> None:
        self.select_indices({track.index for track in self._tracks})

    def clear_selection(self) -> None:
        self.select_indices(set())

    def _emit_selection_changed(self) -> None:
        self._update_summary()
        self.selection_changed.emit()

    def _update_summary(self) -> None:
        labels = [f"A{item.index}" for item in self.selected_tracks()]
        self.summary_label.setText(
            "Voz: " + ", ".join(labels) if labels else "Voz: nenhuma faixa selecionada"
        )


def _track_label(track: AudioTrackSnapshot) -> str:
    states: list[str] = []
    if track.muted is True or track.enabled is False:
        states.append("mutada")
    if track.item_count == 0:
        states.append("vazia")
    if track.locked is True:
        states.append("bloqueada")
    suffix = f" — {', '.join(states)}" if states else ""
    return track.display_name + suffix


def _channel_combo(track: AudioTrackSnapshot) -> QComboBox:
    combo = QComboBox()
    if track.audio_type == "mono":
        combo.addItem("Mono", ChannelMode.MONO.value)
        return combo
    combo.addItem("Ambos", ChannelMode.BOTH.value)
    if track.audio_type == "stereo":
        combo.addItem("Esquerdo", ChannelMode.LEFT.value)
        combo.addItem("Direito", ChannelMode.RIGHT.value)
        combo.addItem("Converter para mono", ChannelMode.MONO.value)
    else:
        combo.setToolTip("Seleção L/R indisponível: tipo da faixa não confirmado.")
    return combo
