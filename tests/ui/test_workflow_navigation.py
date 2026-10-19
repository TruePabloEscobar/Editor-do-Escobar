"""Navigation must preserve editable state and keep application gated."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from o_editor.infrastructure.config import load_config
from o_editor.ui.main_window import MainWindow
from o_editor.ui.qt_runtime import configure_headless_qt_environment

ROOT = Path(__file__).resolve().parents[2]


def test_steps_fit_compact_window_and_keep_disabled_apply(tmp_path: Path) -> None:
    configure_headless_qt_environment()
    app = QApplication.instance() or QApplication([])
    window = MainWindow(
        config=load_config(ROOT / "config/defaults.json"), root=tmp_path, use_mock=False
    )
    window.show()
    window.resize(1024, 720)
    app.processEvents()
    panel = window._transcript_panel
    for step in range(6):
        window._workflow_buttons[step].click()
        app.processEvents()
        assert window.width() == 1024 and window.height() == 720
        assert window._workflow_buttons[step].isChecked()
        assert not panel.apply_button.isEnabled()
        assert not window._apply_button.isEnabled()
        assert window._dry_run.isChecked()
        if 1 <= step <= 3:
            assert panel.pages.currentIndex() == step - 1
    window.close()
    app.processEvents()


def test_navigation_preserves_transcript_edits_and_plan(tmp_path: Path, monkeypatch) -> None:
    from dataclasses import replace

    from PySide6.QtCore import Qt

    from o_editor.domain.speech import SegmentState
    from tests.fixtures.podcast import podcast_layout, podcast_session

    configure_headless_qt_environment()
    app = QApplication.instance() or QApplication([])
    window = MainWindow(
        config=load_config(ROOT / "config/defaults.json"), root=tmp_path, use_mock=True
    )
    panel = window._transcript_panel
    session = podcast_session()
    panel._layout = podcast_layout()
    panel._set_session(replace(session, layout_fingerprint=panel._layout.fingerprint))
    panel._update_buttons()
    window._navigate(2)
    assert panel._model.setData(
        panel._model.index(0, 0), Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole
    )
    panel._save_timer.stop()
    edited = panel._session
    assert edited is not None and edited.segments[0].state == SegmentState.CUT
    for step in (0, 1, 5, 4, 3, 2):
        window._navigate(step)
        assert panel._session is edited
    panel._preview()
    plan = panel._plan
    assert plan is not None
    for step in (0, 1, 2, 4, 5, 3):
        window._navigate(step)
        assert panel._plan is plan
    panel.detail_columns.setChecked(True)
    assert not panel.table.isColumnHidden(1)
    panel.detail_columns.setChecked(False)
    assert panel.table.isColumnHidden(1)
    from PySide6.QtWidgets import QFileDialog

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path / "txt"))
    panel._export()
    assert "Transcrição exportada" in panel.status_label.text()
    window.close()
    app.processEvents()
