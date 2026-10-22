"""Requested layout (2026-10-22): Frames first/default; microphones inside Silêncios."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from o_editor.infrastructure.config import load_config
from o_editor.ui.main_window import MainWindow
from tests.fixtures.podcast import podcast_layout, podcast_session

ROOT = Path(__file__).resolve().parents[2]


def _window(tmp_path: Path) -> MainWindow:
    QApplication.instance() or QApplication([])
    return MainWindow(
        config=load_config(ROOT / "config/defaults.json"), root=tmp_path, use_mock=False
    )


def test_frames_is_first_and_selected_when_timeline_is_loaded(tmp_path: Path) -> None:
    window = _window(tmp_path)
    panel = window._transcript_panel
    row = panel.duration_units.layout()
    assert row.itemAt(0).widget() is panel.frame_units_button
    assert row.itemAt(1).widget() is panel.time_units_button
    # Without FPS the values are shown in time, but Frames stays the preference.
    assert not panel.frame_units_button.isEnabled()
    assert panel.time_units_button.isChecked()
    panel._layout = podcast_layout()
    panel._duration_units_changed()
    assert panel.frame_units_button.isChecked()
    assert panel.minimum_silence.editor.text().endswith("frames")
    # An explicit choice of Tempo survives a timeline refresh.
    panel.time_units_button.click()
    panel._duration_units_changed()
    assert panel.time_units_button.isChecked()
    assert panel.minimum_silence.editor.text().endswith(("ms", "s"))
    panel.frame_units_button.click()
    assert panel.frame_units_button.isChecked()
    window.close()


def test_microphone_cleanup_is_inside_the_silence_tab(tmp_path: Path) -> None:
    window = _window(tmp_path)
    panel = window._transcript_panel
    tabs = panel.preview_controls
    titles = [tabs.tabText(index) for index in range(tabs.count())]
    assert titles == ["Silêncios", "Faixas na cópia"]
    silence_page = tabs.widget(0)
    assert silence_page.isAncestorOf(panel.cleanup_microphones)
    assert silence_page.isAncestorOf(panel.protect_sounds)
    window.close()


def test_preview_still_uses_the_microphone_option(tmp_path: Path) -> None:
    window = _window(tmp_path)
    panel = window._transcript_panel
    panel._layout = podcast_layout()
    panel._set_session(replace(podcast_session(), layout_fingerprint=panel._layout.fingerprint))
    panel._preview()
    assert panel._plan is not None
    enabled = panel._plan.microphone_cleanup.enabled
    panel.cleanup_microphones.click()
    assert panel._plan is None
    panel._preview()
    assert panel._plan is not None and panel._plan.microphone_cleanup.enabled is not enabled
    window.close()
