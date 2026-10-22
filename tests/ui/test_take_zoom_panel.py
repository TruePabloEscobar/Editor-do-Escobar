"""Zoom step (2026-10-22): optional, fixed zoom per take, together or after the cuts."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from o_editor.application.take_zoom import TimelineRegistry, ZoomHistory
from o_editor.domain.take_zoom import ValueRange
from o_editor.infrastructure.config import load_config
from o_editor.internal_actions.request import InternalActionRequest
from o_editor.ui.main_window import MainWindow
from o_editor.ui.take_zoom_panel import TakeZoomPanel
from tests.fixtures.podcast import START_FRAME, podcast_layout, podcast_session

ROOT = Path(__file__).resolve().parents[2]
COPY = "Episodio 1_OE_ROUGHCUT_001"


@pytest.fixture
def window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    value = MainWindow(
        config=load_config(ROOT / "config/defaults.json"), root=tmp_path, use_mock=False
    )
    value.show()
    app.processEvents()
    yield value
    value.close()
    app.processEvents()


def _plans(tmp_path: Path) -> Path:
    return tmp_path / "appdata" / "O Editor" / "plans"


TAKE_STARTS = [START_FRAME + seconds * 24 for seconds in (0, 200, 400, 600, 800)]


def _copy_context(timeline_id: str = "tl-copy", name: str = COPY) -> dict[str, Any]:
    """The demo podcast as rebuilt by O Editor: one V1 item per take."""
    base = podcast_layout()
    camera = next(clip for clip in base.clips if clip.item_id == "v1-cam")
    edges = [*TAKE_STARTS, camera.end_frame]
    pieces = tuple(
        replace(
            camera,
            item_id=f"v1-take{number}",
            item_index=number,
            start_frame=start,
            end_frame=end,
            source_start_frame=None,
            source_end_frame=None,
        )
        for number, (start, end) in enumerate(pairwise(edges), start=1)
    )
    clips = tuple(clip for clip in base.clips if clip.item_id != "v1-cam") + pieces
    layout = replace(base, timeline_name=name, timeline_id=timeline_id, clips=clips)
    return {
        "project_name": layout.project_name,
        "timeline_name": layout.timeline_name,
        "timeline_id": layout.timeline_id,
        "fps": layout.fps,
        "start_frame": layout.start_frame,
        "end_frame": layout.end_frame,
        "start_timecode": layout.start_timecode,
        "layout": {
            "tracks": [track.to_dict() for track in layout.tracks],
            "clips": [clip.to_dict() for clip in layout.clips],
        },
    }


def _request(details: dict[str, Any], status: str = "SUCCESS") -> InternalActionRequest:
    return InternalActionRequest(
        schema_version=1,
        request_id="00000000-0000-4000-8000-000000000001",
        action="apply_take_zoom",
        created_at="2026-10-22T15:00:00Z",
        status=status,
        project="Podcast",
        timeline=COPY,
        result_file=None,
        report_file=None,
        log_file=None,
        message="ok",
        details=details,
    )


def _enable(panel: TakeZoomPanel, *, with_cut: bool = False) -> None:
    panel.enabled_check.setChecked(True)
    panel.with_cut_check.setChecked(with_cut)
    panel.refresh_preview()


def test_zoom_step_is_optional_and_off_by_default(window: MainWindow) -> None:
    window._navigate(4)
    panel = window._take_zoom_panel
    assert window._tabs.currentWidget() is panel
    assert not panel.enabled_check.isChecked()
    assert not panel.controls.isEnabled()
    assert "desligada" in panel.status_label.text()
    assert not panel.apply_button.isEnabled()
    assert panel.settings_for_rough_cut() is None
    assert panel.table.rowCount() == 0


def test_fixed_or_range_controls_and_settings_persist(window: MainWindow, tmp_path: Path) -> None:
    panel = window._take_zoom_panel
    _enable(panel)
    panel.scale_field.fixed_button.click()
    assert not panel.scale_field.maximum_spin.isVisibleTo(panel)
    panel.scale_field.range_button.click()
    assert panel.scale_field.maximum_spin.isVisibleTo(panel)
    panel.scale_field.minimum_spin.setValue(50)
    panel.scale_field.maximum_spin.setValue(150)
    panel.every_field.range_button.click()
    panel.every_field.minimum_spin.setValue(2)
    panel.every_field.maximum_spin.setValue(4)
    panel.offset_x.setValue(-30)
    settings = panel.settings()
    assert settings.scale == ValueRange(50, 150)
    assert settings.every == ValueRange(2, 4)
    assert (settings.offset_x, settings.offset_y) == (-30, 0)
    panel.center_button.click()
    assert (panel.settings().offset_x, panel.settings().offset_y) == (0, 0)
    seed = panel.settings().seed
    panel.redraw_button.click()
    assert panel.settings().seed != seed
    other = TakeZoomPanel(
        config=window._config, root=tmp_path, use_mock=False, plan_provider=lambda: None
    )
    assert other.settings() == panel.settings()
    other.deleteLater()


def test_together_with_rough_cut_updates_the_current_preview(window: MainWindow) -> None:
    transcript = window._transcript_panel
    transcript._layout = podcast_layout()
    transcript._set_session(
        replace(podcast_session(), layout_fingerprint=transcript._layout.fingerprint)
    )
    transcript._preview()
    plan = transcript.plan
    assert plan is not None and plan.take_zoom is None
    panel = window._take_zoom_panel
    _enable(panel, with_cut=True)
    panel.every_field.minimum_spin.setValue(1)
    panel.scale_field.fixed_button.click()
    panel.scale_field.minimum_spin.setValue(125)
    zoomed = transcript.plan
    assert zoomed is not None and zoomed.plan_id == plan.plan_id
    assert zoomed.take_zoom is not None
    assert zoomed.take_zoom["summary"]["zoomed"] == len(plan.keep_ranges)
    assert all(
        op.zoom == {"ZoomX": 1.25, "ZoomY": 1.25, "AnchorPointX": 0.0, "AnchorPointY": 0.0}
        for op in zoomed.operations
        if op.track_type.value == "video"
    )
    assert all(op.zoom is None for op in zoomed.operations if op.track_type.value == "audio")
    assert "Zoom por take (junto)" in transcript.preview_text.toPlainText()
    panel.refresh_preview()
    assert panel.table.rowCount() == len(plan.keep_ranges)
    assert "junto ao Rough Cut" in panel.status_label.text()
    panel.enabled_check.setChecked(False)
    assert transcript.plan is not None and transcript.plan.take_zoom is None
    assert all(op.zoom is None for op in transcript.plan.operations)


def test_only_o_editor_timelines_can_receive_zoom_afterwards(window: MainWindow) -> None:
    panel = window._take_zoom_panel
    _enable(panel)
    panel.load_context(_copy_context(name="Episodio 1"))
    assert panel._layout is None
    assert "não foi criada pelo O Editor" in panel.result_label.text()
    assert not panel.apply_button.isEnabled()


def test_apply_after_cuts_then_undo_with_ctrl_z(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plans = _plans(tmp_path)
    TimelineRegistry(plans).record(
        timeline_id="tl-copy",
        timeline_name=COPY,
        project_name="Podcast",
        take_starts=TAKE_STARTS,
        plan_id=None,
    )
    panel = window._take_zoom_panel
    _enable(panel)
    panel.scale_field.fixed_button.click()
    panel.scale_field.minimum_spin.setValue(140)
    panel.every_field.fixed_button.click()
    panel.every_field.minimum_spin.setValue(2)
    panel.load_context(_copy_context())
    panel.refresh_preview()
    assert panel.table.rowCount() == 5
    assert "cortes do O Editor" in panel.status_label.text()
    assert [panel.table.item(row, 3).text() for row in range(5)] == [
        "100% (sem zoom)",
        "140%",
        "100% (sem zoom)",
        "140%",
        "100% (sem zoom)",
    ]
    assert panel.apply_button.isEnabled() and not panel.undo_button.isEnabled()
    dispatched: list[str] = []
    monkeypatch.setattr(panel, "_start_dispatch", lambda: dispatched.append("go"))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    panel.apply()
    request = json.loads((plans / "menu-action.json").read_text(encoding="utf-8"))
    pending = json.loads((plans / "take-zoom-pending.json").read_text(encoding="utf-8"))
    assert request["action"] == "take_zoom" and request["plan_id"] == pending["plan_id"]
    assert pending["purpose"] == "apply" and pending["timeline"]["timeline_id"] == "tl-copy"
    assert {item["set"]["ZoomX"] for item in pending["items"]} == {1.0, 1.4}
    assert dispatched == ["go"]
    assert panel.request_pending and not panel.apply_button.isEnabled()
    # A Rough Cut cannot use the single request slot meanwhile.
    assert window._transcript_panel._external_busy()

    journal = [
        {
            "item_id": "v1-cam",
            "track_index": 1,
            "take_index": 2,
            "start_frame": 0,
            "end_frame": 960,
            "before": {"ZoomX": 1.0, "ZoomY": 1.0, "AnchorPointX": 0.0, "AnchorPointY": 0.0},
            "after": {"ZoomX": 1.4, "ZoomY": 1.4, "AnchorPointX": 0.0, "AnchorPointY": 0.0},
        }
    ]
    panel.display_result(
        _request(
            {
                "plan_id": pending["plan_id"],
                "purpose": "apply",
                "timeline_id": "tl-copy",
                "timeline_name": COPY,
                "journal": journal,
            }
        )
    )
    assert not panel.request_pending
    assert ZoomHistory(plans).depth("tl-copy") == 1
    assert panel.undo_button.isEnabled() and panel.undo_button.text().endswith("· 1")
    assert "Zoom aplicado" in panel.result_label.text()

    window._navigate(4)
    QApplication.processEvents()
    panel.table.setFocus()
    QTest.keyClick(panel.table, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    undo = json.loads((plans / "take-zoom-pending.json").read_text(encoding="utf-8"))
    assert undo["purpose"] == "undo" and undo["undo_of"] == pending["plan_id"]
    assert undo["items"][0]["set"]["ZoomX"] == 1.0
    assert undo["items"][0]["expect"]["ZoomX"] == 1.4
    panel.display_result(
        _request(
            {
                "plan_id": undo["plan_id"],
                "purpose": "undo",
                "undo_of": pending["plan_id"],
                "timeline_id": "tl-copy",
            }
        )
    )
    assert ZoomHistory(plans).depth("tl-copy") == 0
    assert not panel.undo_button.isEnabled()
    assert "Zoom desfeito" in panel.result_label.text()


def test_pending_rough_cut_blocks_zoom_and_cancel_releases(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    panel = window._take_zoom_panel
    _enable(panel)
    panel.load_context(_copy_context())
    window._transcript_panel._pending_plan_id = "f" * 32
    panel.busy_changed()
    assert not panel.apply_button.isEnabled()
    window._transcript_panel._pending_plan_id = None
    panel.busy_changed()
    assert panel.apply_button.isEnabled()
    monkeypatch.setattr(panel, "_start_dispatch", lambda: None)
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    panel.apply()
    assert panel.cancel_button.isVisibleTo(panel)
    panel.cancel_button.click()
    assert not panel.request_pending
    assert not (_plans(tmp_path) / "menu-action.json").exists()
    assert "cancelado" in panel.result_label.text()


@pytest.mark.parametrize("size", [(1000, 680), (1280, 820)])
def test_zoom_panel_fits_the_window(window: MainWindow, size: tuple[int, int]) -> None:
    window.resize(*size)
    window._navigate(4)
    panel = window._take_zoom_panel
    _enable(panel)
    QApplication.processEvents()
    for widget in (panel.apply_button, panel.undo_button, panel.read_button, panel.redraw_button):
        assert widget.isVisible()
        right = widget.mapTo(window, widget.rect().topRight()).x()
        assert right <= window.width()
    assert panel.table.height() >= 120


def test_resolve_replies_reach_the_zoom_step_and_register_created_timelines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from o_editor.internal_actions.request import create_internal_action_request
    from o_editor.ui.internal_action_runtime import InternalActionMainWindow

    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    app = QApplication.instance() or QApplication([])
    window = InternalActionMainWindow(
        config=load_config(ROOT / "config/defaults.json"), root=tmp_path, use_mock=False
    )
    plans = _plans(tmp_path)
    # Rough cut created a timeline with zoom applied together.
    create_internal_action_request(
        "apply_rough_cut",
        status="SUCCESS",
        message="Rough cut criado",
        project="Podcast",
        details={
            "plan_id": "a" * 32,
            "mode": "APPLY",
            "created_timeline": COPY,
            "created_timeline_id": "tl-copy",
            "take_starts": TAKE_STARTS,
            "take_zoom": {"applied": 0, "failures": 0, "journal": []},
        },
    )
    window._poll_rough_cut_replies()
    assert TimelineRegistry(plans).get("tl-copy")["take_starts"] == TAKE_STARTS
    path = create_internal_action_request(
        "apply_take_zoom",
        status="BLOCKED",
        message="A timeline ativa não é a do zoom.",
        details={"plan_id": "b" * 32, "purpose": "apply", "timeline_id": "tl-copy"},
    )
    window._poll_rough_cut_replies()
    assert window._workflow_buttons[4].isChecked()
    assert "BLOCKED" in window._take_zoom_panel.result_label.text()
    assert "Zoom por take processado" in window._report.toPlainText()
    assert ZoomHistory(plans).depth("tl-copy") == 0
    window._poll_rough_cut_replies()
    assert path.exists()
    window.close()
    app.processEvents()
