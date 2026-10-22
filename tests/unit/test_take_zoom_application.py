"""Zoom per take: one-use requests, created-timeline registry and undo history."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from o_editor.application.rough_cut import cancel_plan_for_resolve
from o_editor.application.take_zoom import (
    HISTORY_LEVELS,
    TakeZoomApplicationError,
    ZoomHistory,
    build_undo_plan,
    is_o_editor_timeline,
    record_take_zoom_outcome,
    save_request,
)

BEFORE = {"ZoomX": 1.0, "ZoomY": 1.0, "AnchorPointX": 0.0, "AnchorPointY": 0.0}
AFTER = {"ZoomX": 1.3, "ZoomY": 1.3, "AnchorPointX": 5.0, "AnchorPointY": 0.0}


def _plan(name: str = "Ep_OE_ROUGHCUT_001") -> dict[str, object]:
    return {
        "schema_version": 1,
        "kind": "take_zoom",
        "purpose": "apply",
        "plan_id": "c" * 32,
        "mode": "APPLY",
        "confirmed_by_user": True,
        "timeline": {"project_name": "P", "timeline_name": name, "timeline_id": "tl"},
        "items": [],
    }


def _entry(application_id: str) -> dict[str, object]:
    return {
        "application_id": application_id,
        "timeline_id": "tl",
        "timeline_name": "Ep_OE_ROUGHCUT_001",
        "journal": [
            {
                "item_id": "i1",
                "track_index": 1,
                "take_index": 2,
                "start_frame": 10,
                "end_frame": 20,
                "before": BEFORE,
                "after": AFTER,
            }
        ],
    }


@pytest.mark.parametrize(
    ("name", "allowed"),
    [
        ("Episodio_OE_ROUGHCUT_001", True),
        ("Episodio_OE_ROUGHCUT_002", True),
        ("Episodio_OE_ROUGHCUT_001_FALHOU", False),
        ("Episodio 1", False),
        (None, False),
    ],
)
def test_only_o_editor_timelines_are_eligible(name: str | None, allowed: bool) -> None:
    assert is_o_editor_timeline(name) is allowed


def test_request_is_one_use_and_refuses_original_timelines(tmp_path: Path) -> None:
    pending = save_request(_plan(), directory=tmp_path)
    request = json.loads((tmp_path / "menu-action.json").read_text(encoding="utf-8"))
    assert request["action"] == "take_zoom" and request["plan_id"] == "c" * 32
    assert request["mode"] == "APPLY" and len(request["request_id"]) == 32
    assert json.loads(pending.read_text(encoding="utf-8"))["kind"] == "take_zoom"
    assert (tmp_path / "applied").is_dir()
    assert cancel_plan_for_resolve(
        plan_id="c" * 32, mode="APPLY", directory=tmp_path, action="take_zoom"
    )
    assert not (tmp_path / "menu-action.json").exists()
    with pytest.raises(TakeZoomApplicationError):
        save_request(_plan("Episodio 1"), directory=tmp_path)
    assert not (tmp_path / "menu-action.json").exists()


def test_undo_plan_restores_before_values_and_expects_after_values() -> None:
    plan = build_undo_plan(_entry("a" * 32), project_name="P")
    assert plan["purpose"] == "undo" and plan["undo_of"] == "a" * 32
    assert plan["items"][0]["set"] == BEFORE
    assert plan["items"][0]["expect"] == AFTER
    assert plan["timeline"] == {
        "project_name": "P",
        "timeline_name": "Ep_OE_ROUGHCUT_001",
        "timeline_id": "tl",
    }
    with pytest.raises(TakeZoomApplicationError):
        build_undo_plan({**_entry("x"), "journal": []}, project_name="P")


def test_history_is_a_capped_stack_per_timeline(tmp_path: Path) -> None:
    history = ZoomHistory(tmp_path)
    for number in range(HISTORY_LEVELS + 5):
        assert history.push(_entry(f"{number:032x}"))
    assert history.depth("tl") == HISTORY_LEVELS
    assert not history.push(_entry(f"{HISTORY_LEVELS + 4:032x}"))  # duplicate result
    last = history.last("tl")
    assert last is not None and last["application_id"] == f"{HISTORY_LEVELS + 4:032x}"
    # Only the most recent application can be popped.
    assert not history.pop("tl", f"{HISTORY_LEVELS:032x}")
    assert history.pop("tl", f"{HISTORY_LEVELS + 4:032x}")
    assert history.depth("tl") == HISTORY_LEVELS - 1
    assert history.depth("other") == 0


def test_outcomes_update_history_only_on_success(tmp_path: Path) -> None:
    details = {
        "plan_id": "b" * 32,
        "timeline_id": "tl",
        "timeline_name": "Ep_OE_ROUGHCUT_001",
        "purpose": "apply",
        "journal": _entry("b")["journal"],
    }
    assert record_take_zoom_outcome("FAILED", details, directory=tmp_path) == "unchanged"
    assert record_take_zoom_outcome("SUCCESS", details, directory=tmp_path) == "applied"
    assert record_take_zoom_outcome("SUCCESS", details, directory=tmp_path) == "unchanged"
    undo = {"timeline_id": "tl", "purpose": "undo", "undo_of": "b" * 32}
    assert record_take_zoom_outcome("BLOCKED", undo, directory=tmp_path) == "unchanged"
    assert record_take_zoom_outcome("SUCCESS", undo, directory=tmp_path) == "undone"
    assert record_take_zoom_outcome("SUCCESS", undo, directory=tmp_path) == "unchanged"


def test_corrupt_history_file_is_treated_as_empty(tmp_path: Path) -> None:
    (tmp_path / "take-zoom-history.json").write_text("{corrompido", encoding="utf-8")
    history = ZoomHistory(tmp_path)
    assert history.depth("tl") == 0
    assert history.push(_entry("a" * 32))
    assert history.depth("tl") == 1
