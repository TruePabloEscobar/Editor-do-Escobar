"""Zoom per take: the real Lua engine against the in-memory Resolve (Lua 5.1).

Proven here: the installed Lua code, the plans produced by the Python application
layer, readback, rollback and the undo guard. NOT proven: the real Resolve API
behaviour of ZoomX/ZoomY/AnchorPoint (manual test in Resolve 21.1).
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from o_editor.application.take_zoom import (
    ZoomHistory,
    build_apply_plan,
    build_undo_plan,
    preview_take_zoom,
    record_rough_cut_outcome,
    record_take_zoom_outcome,
)
from o_editor.domain.take_zoom import TakeZoomSettings, ValueRange
from o_editor.domain.timeline_layout import TimelineLayout
from tests.lua_runner import lua_command

ROOT = Path(__file__).resolve().parents[2]
LUA = lua_command()
BASE = {"ZoomX": 1.1, "ZoomY": 1.1, "AnchorPointX": 0.0, "AnchorPointY": 0.0}


def _run(tmp_path: Path, options: dict[str, Any], plan: dict[str, Any] | None = None) -> Any:
    assert LUA is not None, "Lua 5.1 (ou lupa) é obrigatório para o gate"
    count = len(list(tmp_path.glob("zoom-options-*")))
    options_path = tmp_path / f"zoom-options-{count}.json"
    options_path.write_text(json.dumps(options), encoding="utf-8")
    arguments = [str(options_path)]
    if plan is not None:
        plan_path = tmp_path / f"zoom-plan-{count}.json"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        arguments.append(str(plan_path))
    output = subprocess.run(
        [
            *LUA,
            str(ROOT / "tests/lua/run_take_zoom.lua"),
            str(ROOT / "launcher"),
            str(ROOT / "tests/lua"),
            *arguments,
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    return json.loads(output)


def _layout(tmp_path: Path, **options: Any) -> TimelineLayout:
    return TimelineLayout.from_internal_context(_run(tmp_path, options))


def _settings(**changes: Any) -> TakeZoomSettings:
    values: dict[str, Any] = {
        "enabled": True,
        "scale": ValueRange.fixed(130),
        "every": ValueRange.fixed(2),
        "offset_x": -40.0,
        "offset_y": 12.0,
        "video_tracks": (1, 2),
    }
    values.update(changes)
    return TakeZoomSettings(**values)


def _apply_plan(tmp_path: Path, **changes: Any) -> dict[str, Any]:
    layout = _layout(tmp_path)
    # The copy was built from two cuts: 86400-86500 and 86500-86700 (clip edge at 86650).
    preview = preview_take_zoom(layout, _settings(**changes), take_starts=[86400, 86500])
    return build_apply_plan(preview)


def _zoom(props: dict[str, Any]) -> tuple[float, float, float, float]:
    return (props["ZoomX"], props["ZoomY"], props["AnchorPointX"], props["AnchorPointY"])


def test_apply_sets_verified_values_only_on_the_o_editor_copy(tmp_path: Path) -> None:
    plan = _apply_plan(tmp_path)
    output = _run(tmp_path, {}, plan)
    result = output["result"]
    assert result["status"] == "SUCCESS", result
    copy = output["copy"]["props"]
    # Take 1 (no zoom) -> 100%; take 2 (zoom 130%) covers two clips of V1 and V2 overlap.
    assert _zoom(copy["c-v1-1"]) == (1.0, 1.0, -40.0, 12.0)
    assert _zoom(copy["c-v1-2"]) == (1.3, 1.3, -40.0, 12.0)
    assert _zoom(copy["c-v1-3"]) == (1.3, 1.3, -40.0, 12.0)
    assert _zoom(copy["c-v2-1"]) == (1.3, 1.3, -40.0, 12.0)
    assert copy["c-a1-1"] == {"AudioVolume": -3.0}
    assert output["original"]["props"]["orig-v1"] == BASE
    assert output["original"]["mutation_log"] == []
    journal = result["details"]["journal"]
    assert [entry["item_id"] for entry in journal] == ["c-v1-1", "c-v1-2", "c-v1-3", "c-v2-1"]
    assert journal[0]["before"] == BASE
    assert journal[3]["before"] == {
        "ZoomX": 1.0,
        "ZoomY": 1.0,
        "AnchorPointX": 0,
        "AnchorPointY": 0,
    }


def test_centre_is_the_default_zoom_point(tmp_path: Path) -> None:
    plan = _apply_plan(tmp_path, offset_x=0.0, offset_y=0.0, video_tracks=(1,))
    output = _run(tmp_path, {}, plan)
    assert output["result"]["status"] == "SUCCESS"
    assert _zoom(output["copy"]["props"]["c-v1-2"]) == (1.3, 1.3, 0.0, 0.0)
    assert "ZoomX" not in output["copy"]["props"]["c-v2-1"]


def test_multi_level_undo_restores_previous_values_in_order(tmp_path: Path) -> None:
    history_dir = tmp_path / "history"
    first = _apply_plan(tmp_path)
    out1 = _run(tmp_path, {}, first)
    assert record_take_zoom_outcome(
        "SUCCESS", out1["result"]["details"], directory=history_dir
    ) == ("applied")
    second = _apply_plan(tmp_path, scale=ValueRange.fixed(50), every=ValueRange.fixed(1))
    out2 = _run(tmp_path, {"props": out1["copy"]["props"]}, second)
    assert out2["result"]["status"] == "SUCCESS"
    assert _zoom(out2["copy"]["props"]["c-v1-1"]) == (0.5, 0.5, -40.0, 12.0)
    record_take_zoom_outcome("SUCCESS", out2["result"]["details"], directory=history_dir)
    history = ZoomHistory(history_dir)
    assert history.depth("tl-copy") == 2

    undo2 = build_undo_plan(history.last("tl-copy"), project_name="Podcast")
    back1 = _run(tmp_path, {"props": out2["copy"]["props"]}, undo2)
    assert back1["result"]["status"] == "SUCCESS", back1["result"]
    assert back1["copy"]["props"] == out1["copy"]["props"]
    assert record_take_zoom_outcome(
        "SUCCESS", back1["result"]["details"], directory=history_dir
    ) == ("undone")
    undo1 = build_undo_plan(history.last("tl-copy"), project_name="Podcast")
    back0 = _run(tmp_path, {"props": back1["copy"]["props"]}, undo1)
    assert back0["result"]["status"] == "SUCCESS"
    for item in ("c-v1-1", "c-v1-2", "c-v1-3"):
        assert back0["copy"]["props"][item] == BASE
    record_take_zoom_outcome("SUCCESS", back0["result"]["details"], directory=history_dir)
    assert history.depth("tl-copy") == 0


def test_undo_is_cancelled_when_a_take_was_changed_by_hand(tmp_path: Path) -> None:
    plan = _apply_plan(tmp_path)
    applied = _run(tmp_path, {}, plan)
    record_take_zoom_outcome("SUCCESS", applied["result"]["details"], directory=tmp_path / "h")
    entry = ZoomHistory(tmp_path / "h").last("tl-copy")
    edited = json.loads(json.dumps(applied["copy"]["props"]))
    edited["c-v1-2"]["ZoomX"] = 1.7
    output = _run(tmp_path, {"props": edited}, build_undo_plan(entry, project_name="Podcast"))
    assert output["result"]["status"] == "BLOCKED"
    assert not output["result"]["mutations"]
    assert output["copy"]["props"] == edited


@pytest.mark.parametrize(
    ("options", "fragment"),
    [
        ({"current": "original"}, "não é a do zoom"),
        ({"move_item": "c-v1-2"}, "mudou desde a prévia"),
    ],
)
def test_wrong_timeline_or_changed_layout_blocks_without_changes(
    tmp_path: Path, options: dict[str, Any], fragment: str
) -> None:
    plan = _apply_plan(tmp_path)
    output = _run(tmp_path, options, plan)
    assert output["result"]["status"] == "BLOCKED"
    assert fragment in output["result"]["message"]
    assert output["copy"]["props"]["c-v1-2"] == BASE
    assert output["original"]["props"]["orig-v1"] == BASE


@pytest.mark.parametrize("name", ["Episodio 1 copia manual", "Episodio 1_OE_ROUGHCUT_001_FALHOU"])
def test_only_timelines_created_by_o_editor_are_changed(tmp_path: Path, name: str) -> None:
    layout = _layout(tmp_path, copy_name=name)
    preview = preview_take_zoom(layout, _settings())
    plan = build_apply_plan(preview)
    output = _run(tmp_path, {"copy_name": name}, plan)
    assert output["result"]["status"] == "BLOCKED"
    assert "criadas pelo O Editor" in output["result"]["message"]
    assert output["copy"]["props"]["c-v1-1"] == BASE


def test_expired_or_unconfirmed_request_is_refused(tmp_path: Path) -> None:
    plan = _apply_plan(tmp_path)
    old = (datetime.now(UTC) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert _run(tmp_path, {}, {**plan, "created_at": old})["result"]["status"] == "BLOCKED"
    unconfirmed = _run(tmp_path, {}, {**plan, "confirmed_by_user": False})
    assert unconfirmed["result"]["status"] == "BLOCKED"
    assert unconfirmed["copy"]["props"]["c-v1-1"] == BASE


@pytest.mark.parametrize(
    "options",
    [{"ignore_item": "c-v1-3", "ignore_calls": 99}, {"switch_after_calls": 2}],
)
def test_unconfirmed_value_or_switched_timeline_rolls_everything_back(
    tmp_path: Path, options: dict[str, Any]
) -> None:
    plan = _apply_plan(tmp_path)
    output = _run(tmp_path, options, plan)
    result = output["result"]
    assert result["status"] == "FAILED"
    assert result["details"]["rolled_back"] is True
    for item in ("c-v1-1", "c-v1-2", "c-v1-3"):
        assert output["copy"]["props"][item] == BASE
    assert output["original"]["props"]["orig-v1"] == BASE


def test_rough_cut_result_registers_timeline_and_zoom_history(tmp_path: Path) -> None:
    details = {
        "plan_id": "a" * 32,
        "created_timeline": "Episodio 1_OE_ROUGHCUT_001",
        "created_timeline_id": "tl-copy",
        "take_starts": [86400, 86500],
        "take_zoom": {
            "applied": 1,
            "failures": 0,
            "journal": [
                {
                    "item_id": "c-v1-2",
                    "track_index": 1,
                    "take_index": 2,
                    "start_frame": 86500,
                    "end_frame": 86650,
                    "before": BASE,
                    "after": {**BASE, "ZoomX": 1.3, "ZoomY": 1.3},
                }
            ],
        },
    }
    record_rough_cut_outcome(details, project_name="Podcast", directory=tmp_path)
    record_rough_cut_outcome(details, project_name="Podcast", directory=tmp_path)
    from o_editor.application.take_zoom import TimelineRegistry

    assert TimelineRegistry(tmp_path).get("tl-copy")["take_starts"] == [86400, 86500]
    assert ZoomHistory(tmp_path).depth("tl-copy") == 1
    failed = {
        **details,
        "created_timeline": "Episodio 1_OE_ROUGHCUT_002_FALHOU",
        "created_timeline_id": "tl-x",
    }
    record_rough_cut_outcome(failed, project_name="Podcast", directory=tmp_path)
    assert TimelineRegistry(tmp_path).get("tl-x") is None
