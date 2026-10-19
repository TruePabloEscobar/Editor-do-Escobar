from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox

from o_editor.domain.enums import ChannelMode
from o_editor.domain.voice_tracks import AudioTrackSnapshot, SelectedVoiceTrack
from o_editor.infrastructure.config import load_config
from o_editor.ui.main_window import MainWindow
from o_editor.ui.voice_track_selector import VoiceTrackSelector

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_main_window_starts_with_mock_voice_tracks_in_safe_dry_run_mode(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(
        config=load_config(PROJECT_ROOT / "config" / "defaults.json"),
        root=tmp_path,
        use_mock=True,
    )
    assert window.windowTitle() == "Editor Do Escobar — EDE"
    assert window._dry_run.isChecked()
    assert not window._apply_button.isEnabled()
    assert window._zoom_intensity.currentText() == "Média"
    assert window._zoom_frequency.currentText() == "Média"
    assert window._text_frequency.currentText() == "Baixa"
    assert window._external_bridge_label.text() == "DISABLED"
    assert window._overall_status_label.text() == "READY_OFFLINE"
    assert window._voice_selector.table.rowCount() == 5
    assert tuple(item.index for item in window._voice_selector.selected_tracks()) == (2, 3)
    assert window._voice_selector.summary_label.text() == "Voz: A2, A3"
    assert window._analyze_button.isEnabled()
    window.close()
    app.processEvents()


def test_analysis_button_requires_track_or_manual_wav(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(
        config=load_config(PROJECT_ROOT / "config" / "defaults.json"),
        root=tmp_path,
        use_mock=True,
    )
    window._voice_selector.clear_selection()
    assert not window._analyze_button.isEnabled()
    assert "Selecione pelo menos" in window._analyze_button.toolTip()
    window.close()
    app.processEvents()


def test_voice_track_selector_shows_states_and_channel_modes() -> None:
    app = QApplication.instance() or QApplication([])
    selector = VoiceTrackSelector()
    tracks = (
        AudioTrackSnapshot(
            1,
            "A1",
            "Boom",
            audio_type="stereo",
            enabled=False,
            muted=True,
            locked=True,
            item_count=0,
        ),
        AudioTrackSnapshot(2, "A2", "Lapela", audio_type="mono", item_count=1),
    )
    selector.set_tracks(
        tracks,
        selected=(SelectedVoiceTrack(1, "Boom", ChannelMode.LEFT),),
        suggested_indices=(1, 2),
    )
    label = selector.table.item(0, 0)
    assert label.checkState() == Qt.CheckState.Checked
    assert "mutada" in label.text()
    assert "vazia" in label.text()
    assert "bloqueada" in label.text()
    stereo_combo = selector.table.cellWidget(0, 1)
    mono_combo = selector.table.cellWidget(1, 1)
    assert isinstance(stereo_combo, QComboBox)
    assert isinstance(mono_combo, QComboBox)
    assert stereo_combo.findData("left") >= 0
    assert stereo_combo.findData("right") >= 0
    assert mono_combo.currentData() == "mono"
    selector.close()
    app.processEvents()
