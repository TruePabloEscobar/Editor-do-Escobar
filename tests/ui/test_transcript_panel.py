from __future__ import annotations

import os
import shutil
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from o_editor.application.transcript_exchange import export_transcripts
from o_editor.demo_podcast import SPEAKERS
from o_editor.domain.enums import ChannelMode
from o_editor.domain.speech import SegmentState
from o_editor.domain.voice_tracks import SelectedVoiceTrack
from o_editor.infrastructure.config import AppConfig, FFmpegSection, load_config
from o_editor.ui.main_window import MainWindow
from o_editor.ui.models.transcript_model import KEEP_COLUMN

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")


def _config() -> AppConfig:
    config = load_config(PROJECT_ROOT / "config" / "defaults.json")
    from dataclasses import replace

    return replace(config, ffmpeg=FFmpegSection(ffmpeg_path=FFMPEG, ffprobe_path=FFPROBE))


def test_panel_is_present_and_safe_without_timeline(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(config=_config(), root=tmp_path, use_mock=False)
    panel = window._transcript_panel
    assert window._tabs.tabText(0) == "Transcrição e Rough Cut"
    assert not panel.transcribe_button.isEnabled()
    assert not panel.apply_button.isEnabled()
    assert "O EDITOR" in panel.status_label.text()
    window.close()
    app.processEvents()


@pytest.mark.skipif(FFMPEG is None or FFPROBE is None, reason="FFmpeg não disponível")
def test_mock_flow_transcribe_edit_preview(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(config=_config(), root=tmp_path, use_mock=True)
    panel = window._transcript_panel
    assert panel.transcribe_button.isEnabled()
    selected = tuple(SelectedVoiceTrack(i, n, ChannelMode.MONO) for i, n in SPEAKERS.items())
    session = panel._make_service(selected, force=False).execute()
    panel._transcription_finished(session)
    assert panel._model.rowCount() == len(session.segments)
    assert panel.view_combo.count() == 1 + len(SPEAKERS)
    # Individual participant view.
    panel.view_combo.setCurrentIndex(1)
    assert all(panel._proxy.index(row, 3).data() == "A1" for row in range(panel._proxy.rowCount()))
    panel.view_combo.setCurrentIndex(0)
    # Uncheck "Manter" on the first row -> CUT, persisted in the session.
    first = panel._model.index(0, KEEP_COLUMN)
    assert panel._model.setData(first, Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
    panel._save_session_edits()
    assert panel._session is not None
    assert panel._session.segments[0].state == SegmentState.CUT
    reloaded = panel._store.load(panel._session.session_id)
    assert reloaded.segments[0].state == SegmentState.CUT
    export = export_transcripts(panel._session, tmp_path / "txt", panel._store)
    assert len(export.files) == len(SPEAKERS) + 1
    panel._preview()
    assert panel._plan is not None and not panel._plan.blocked
    assert "PRÉVIA DO ROUGH CUT" in panel.preview_text.toPlainText()
    assert panel.apply_button.isEnabled()
    window.close()
    app.processEvents()
