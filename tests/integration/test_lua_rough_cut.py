"""Phase 5 / tests G and H: the Lua engine against an in-memory Resolve (Lua 5.1).

What is real here: the exact Lua code installed in Resolve, the plan produced by the
Python planner, and a fake object model implementing the documented API methods.
What is NOT proven here: the behaviour of the real DaVinci Resolve API (manual test).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from o_editor.application.rough_cut import prepare_rough_cut, save_plan_for_resolve
from o_editor.domain.rough_cut import SilencePreset, SilenceSettings, TrackPolicy
from o_editor.domain.speech import (
    RawSegment,
    SegmentState,
    TranscribedTrack,
    TranscriptSession,
    build_segments,
)
from o_editor.domain.timeline_layout import TimelineLayout
from tests.lua_runner import lua_command

ROOT = Path(__file__).resolve().parents[2]
LUA = lua_command()
pytestmark = pytest.mark.skipif(LUA is None, reason="interpretador Lua 5.1 não disponível")
START = 86_400


def _run(tmp_path: Path, plan_path: Path | None, options: dict[str, Any]) -> dict[str, Any]:
    assert LUA is not None
    options_path = tmp_path / f"options-{len(list(tmp_path.glob('options-*')))}.json"
    options_path.write_text(json.dumps(options), encoding="utf-8")
    output = subprocess.run(
        [
            *LUA,
            str(ROOT / "tests" / "lua" / "run_apply.lua"),
            str(ROOT / "launcher"),
            str(ROOT / "tests" / "lua"),
            str(plan_path or options_path),
            str(options_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    return json.loads(output)


def _layout(tmp_path: Path) -> TimelineLayout:
    return TimelineLayout.from_internal_context(_run(tmp_path, None, {"capture_only": True}))


def _session(layout: TimelineLayout) -> TranscriptSession:
    specs = [
        (1, 48, 144, "Olá, bem-vindos ao episódio.", SegmentState.KEEP),
        (2, 600, 700, "Errei, vou repetir essa parte.", SegmentState.CUT),
        (3, 1500, 1600, "Uma pergunta importante.", SegmentState.KEEP),
        (4, 2000, 2100, "E a resposta final.", SegmentState.KEEP),
    ]
    names = {1: "Pablo", 2: "Jessica", 3: "Mileni", 4: "Renne"}
    segments = build_segments(
        [
            RawSegment(track, START + start, START + end, text)
            for track, start, end, text, _ in specs
        ],
        names,
    )
    states = {text: state for *_rest, text, state in specs}
    segments = tuple(replace(item, state=states[item.text]) for item in segments)
    return TranscriptSession(
        session_id="feedfacecafebeef",
        revision=1,
        created_at="2026-10-17T22:00:00+00:00",
        updated_at="2026-10-17T22:00:00+00:00",
        project_name=layout.project_name,
        timeline_name=layout.timeline_name,
        timeline_id=layout.timeline_id,
        fps=layout.fps,
        start_frame=layout.start_frame,
        end_frame=layout.end_frame,
        start_timecode=layout.start_timecode,
        drop_frame=False,
        layout_fingerprint=layout.fingerprint,
        layout=layout.to_dict(),
        tracks=tuple(TranscribedTrack(index, name, "mono") for index, name in names.items()),
        segments=segments,
        activity={track: ((START + start, START + end),) for track, start, end, *_ in specs},
    )


def _plan_file(tmp_path: Path, *, apply: bool = True, **overrides: Any) -> tuple[Path, Any]:
    layout = _layout(tmp_path)
    plan = prepare_rough_cut(
        _session(layout),
        silence=SilenceSettings.from_preset(SilencePreset.MEDIUM),
        track_policies=overrides.pop("policies", None),
    )
    assert not plan.blocked, [issue.render() for issue in plan.issues]
    path = save_plan_for_resolve(plan, apply=apply, directory=tmp_path / "plans")
    if overrides:
        value = json.loads(path.read_text(encoding="utf-8"))
        value.update(overrides)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path, plan


def _timeline(output: dict[str, Any], name: str) -> dict[str, Any]:
    return next(item for item in output["timelines"] if item["name"] == name)


@pytest.mark.parametrize(
    "conventions",
    [
        {},
        {"end_inclusive": True},
        {"record_relative": True},
        {"end_inclusive": True, "record_relative": True},
    ],
)
def test_rough_cut_builds_new_synced_timeline(tmp_path: Path, conventions: dict[str, bool]) -> None:
    before = _run(tmp_path, None, {"capture_only": True})
    path, plan = _plan_file(tmp_path)
    output = _run(tmp_path, path, conventions)
    result = output["result"]
    assert result["status"] == "SUCCESS", (result["message"], output["logs"])
    assert result["mutations"] is True
    new_name = "Episodio 1_OE_ROUGHCUT_001"
    assert output["current"] == new_name
    created = _timeline(output, new_name)
    original = _timeline(output, "Episodio 1")

    # Test H: the original timeline is untouched and was only used as a source.
    assert original["mutation_log"] == ["DuplicateTimeline(source)"]
    assert result["details"]["original_verified_after"] is True
    original_layout = TimelineLayout.from_internal_context(before)
    assert len(original["items"]) == len(original_layout.clips)

    # Every planned operation exists exactly once at its planned position and source.
    items = {
        (item["track_type"], item["track_index"], item["start"]): item for item in created["items"]
    }
    assert len(created["items"]) == len(plan.operations)
    for operation in plan.operations:
        item = items[(operation.track_type.value, operation.track_index, operation.record_start)]
        assert item["finish"] == operation.record_end
        assert item["src_start"] == operation.source_start
        assert item["src_end"] - item["src_start"] == operation.source_end - operation.source_start

    # Test G: in each kept range all tracks share the same timeline shift.
    shifts: dict[int, set[int]] = {}
    for operation in plan.operations:
        clip = original_layout.clip_by_id(operation.source_item_id)
        assert clip is not None and clip.source_start_frame is not None
        original_position = clip.start_frame + operation.source_start - clip.source_start_frame
        shifts.setdefault(operation.keep_index, set()).add(
            operation.record_start - original_position
        )
    assert all(len(values) == 1 for values in shifts.values())
    total_new = sum(item.duration_frames for item in plan.keep_ranges)
    video = [item for item in created["items"] if item["track_type"] == "video"]
    assert sum(item["finish"] - item["start"] for item in video) == total_new

    # Linked camera/mic pieces, copied attributes and channel mapping.
    for keep_index in range(len(plan.keep_ranges)):
        keep = plan.keep_ranges[keep_index]
        v1 = items[("video", 1, keep.record_start)]
        a1 = items[("audio", 1, keep.record_start)]
        assert v1["link_group"] and v1["link_group"] == a1["link_group"]
    assert all(item["props"].get("ZoomX") == 1.1 for item in video)
    assert all(
        '"channel_idx":[1]' in item["mapping"]
        for item in created["items"]
        if item["track_type"] == "audio" and item["track_index"] <= 4
    )
    marker_frames = sorted(marker["frame"] for marker in created["markers"])
    assert marker_frames == [100 - 42]


def test_validate_mode_never_mutates(tmp_path: Path) -> None:
    path, _plan = _plan_file(tmp_path, apply=False)
    output = _run(tmp_path, path, {})
    assert output["result"]["status"] == "SUCCESS"
    assert output["result"]["mutations"] is False
    assert len(output["timelines"]) == 1
    assert output["timelines"][0]["mutation_log"] == []


def test_changed_timeline_blocks_before_any_mutation(tmp_path: Path) -> None:
    path, _plan = _plan_file(tmp_path)
    output = _run(tmp_path, path, {"tamper": True})
    assert output["result"]["status"] == "BLOCKED"
    assert output["result"]["mutations"] is False
    assert len(output["timelines"]) == 1
    assert output["timelines"][0]["mutation_log"] == []


def test_expired_or_unconfirmed_plan_is_not_applied(tmp_path: Path) -> None:
    path, _plan = _plan_file(tmp_path, created_at="2020-01-01T00:00:00Z")
    output = _run(tmp_path, path, {})
    assert output["result"]["status"] == "BLOCKED"
    assert len(output["timelines"]) == 1
    path, _plan = _plan_file(tmp_path, confirmed_by_user=False)
    output = _run(tmp_path, path, {})
    assert output["result"]["mutations"] is False
    assert len(output["timelines"]) == 1


def test_omitted_track_is_left_empty(tmp_path: Path) -> None:
    path, _plan = _plan_file(tmp_path, policies={"A5": TrackPolicy.OMIT})
    output = _run(tmp_path, path, {})
    assert output["result"]["status"] == "SUCCESS"
    created = _timeline(output, "Episodio 1_OE_ROUGHCUT_001")
    assert not any(
        item["track_type"] == "audio" and item["track_index"] == 5 for item in created["items"]
    )


def test_extra_items_created_by_multitrack_media_are_removed(tmp_path: Path) -> None:
    path, plan = _plan_file(tmp_path)
    output = _run(tmp_path, path, {"poly_audio_tracks": 2})
    result = output["result"]
    assert result["status"] == "SUCCESS", result["message"]
    assert result["details"]["counters"]["extras_removed"] > 0
    created = _timeline(output, "Episodio 1_OE_ROUGHCUT_001")
    assert len(created["items"]) == len(plan.operations)
    positions = [
        (item["track_type"], item["track_index"], item["start"]) for item in created["items"]
    ]
    assert len(positions) == len(set(positions))


def test_unreported_audio_items_do_not_block_following_operations(tmp_path: Path) -> None:
    path, plan = _plan_file(tmp_path)
    output = _run(tmp_path, path, {"poly_audio_tracks": 4, "hidden_poly_audio": True})
    assert output["result"]["status"] == "SUCCESS", output["result"]["message"]
    created = _timeline(output, "Episodio 1_OE_ROUGHCUT_001")
    assert len(created["items"]) == len(plan.operations)
    assert output["result"]["details"]["original_verified_after"]


@pytest.mark.parametrize("time_bias,expected", [(0, "SUCCESS"), (0.1, "FAILED")])
def test_source_frame_rounding_requires_independent_agreement(
    tmp_path: Path, time_bias: float, expected: str
) -> None:
    path, plan = _plan_file(tmp_path)
    output = _run(tmp_path, path, {"source_readback_bias": -1, "source_time_bias": time_bias})
    assert output["result"]["status"] == expected, output["result"]["message"]
    if expected == "SUCCESS":
        assert output["result"]["details"]["original_verified_after"]
        assert output["result"]["details"]["counters"]["source_frame_rounding"] == len(
            plan.operations
        )


@pytest.mark.parametrize("omit_second", [False, True])
@pytest.mark.parametrize(
    "conventions",
    [
        {},
        {"end_inclusive": True},
        {"record_relative": True},
        {"end_inclusive": True, "record_relative": True},
    ],
)
def test_poly_audio_preserves_native_stream_provenance(
    tmp_path: Path, omit_second: bool, conventions: dict[str, bool]
) -> None:
    options = {"shared_poly_source": True, "hidden_poly_audio": True, **conventions}
    layout = TimelineLayout.from_internal_context(
        _run(tmp_path, None, {**options, "capture_only": True})
    )
    policies = {"A2": TrackPolicy.OMIT} if omit_second else None
    plan = prepare_rough_cut(
        _session(layout),
        silence=SilenceSettings.from_preset(SilencePreset.MEDIUM),
        track_policies=policies,
    )
    assert not plan.blocked
    path = save_plan_for_resolve(plan, apply=True, directory=tmp_path / "plans")
    output = _run(tmp_path, path, options)
    assert output["result"]["status"] == "SUCCESS", output["result"]
    created = _timeline(output, "Episodio 1_OE_ROUGHCUT_001")
    audio = [
        item
        for item in created["items"]
        if item["track_type"] == "audio" and item["media"] == "mpi-shared"
    ]
    assert audio
    for item in audio:
        # This checks the native source, independently of the mutable mapping JSON.
        assert item["effective_stream"] == item["track_index"], item
    if omit_second:
        assert not any(item["track_index"] == 2 for item in audio)
    assert output["result"]["details"]["counters"]["native_audio_reused"] > 0
    assert output["result"]["details"]["counters"]["channel_mappings"] == 0
    assert output["result"]["details"]["original_verified_after"] is True


@pytest.mark.parametrize("position", [15378, 100000, 1000000])
@pytest.mark.parametrize("time_bias", [0, 0.1])
@pytest.mark.parametrize("nominal", [24, 30, 60, 120])
def test_long_fractional_source_uses_rational_time_agreement(
    tmp_path: Path, position: int, time_bias: float, nominal: int
):
    options = {
        "fixture_fps": round(nominal * 1000 / 1001, 3),
        "fixture_source_start": position,
        "source_readback_bias": -1,
        "source_time_fps": nominal * 1000 / 1001,
        "source_time_bias": time_bias,
    }
    layout = TimelineLayout.from_internal_context(
        _run(tmp_path, None, {**options, "capture_only": True})
    )
    plan = prepare_rough_cut(
        _session(layout), silence=SilenceSettings.from_preset(SilencePreset.MEDIUM)
    )
    assert not plan.blocked
    path = save_plan_for_resolve(plan, apply=True, directory=tmp_path / "plans")
    output = _run(tmp_path, path, options)
    assert output["result"]["status"] == ("FAILED" if time_bias else "SUCCESS"), output["result"][
        "message"
    ]


@pytest.mark.parametrize("option", ["slip_source", "reroute_source"])
def test_source_slip_or_routing_change_blocks_before_copy(tmp_path: Path, option: str):
    path, _ = _plan_file(tmp_path)
    output = _run(tmp_path, path, {option: True})
    assert output["result"]["status"] == "BLOCKED", output["result"]["message"]
    assert output["result"]["mutations"] is False
    assert len(output["timelines"]) == 1


def test_failure_returns_to_verified_original_instead_of_incomplete_copy(tmp_path: Path):
    path, _ = _plan_file(tmp_path)
    output = _run(tmp_path, path, {"source_readback_bias": -1, "source_time_bias": 0.1})
    assert output["result"]["status"] == "FAILED"
    assert output["current"] == "Episodio 1"
    assert output["result"]["details"]["original_verified_after"] is True


@pytest.mark.parametrize("reject", [False, True])
def test_microphone_clip_states_are_verified_and_original_is_intact(
    tmp_path: Path, reject: bool
) -> None:
    from o_editor.domain.microphone_cleanup import MicrophoneCleanupSettings

    layout = _layout(tmp_path)
    session = replace(_session(layout), activity={i: () for i in range(1, 5)})
    plan = prepare_rough_cut(
        session,
        silence=SilenceSettings(enabled=False),
        microphone_cleanup=MicrophoneCleanupSettings(enabled=True),
    )
    assert any(not op.enabled for op in plan.operations)
    path = save_plan_for_resolve(plan, apply=True, directory=tmp_path / "plans")
    output = _run(tmp_path, path, {"reject_clip_disable": reject})
    assert output["result"]["status"] == ("FAILED" if reject else "SUCCESS")
    assert output["result"]["details"]["original_verified_after"] is True
    if not reject:
        created = output["timelines"][-1]["items"]
        assert sum(not x["enabled"] for x in created) == sum(
            not op.enabled for op in plan.operations
        )
        assert all(x["enabled"] for x in created if x["track_type"] == "video")


def test_rough_cut_can_apply_zoom_per_take_together(tmp_path: Path) -> None:
    from o_editor.domain.take_zoom import TakeZoomSettings, ValueRange, with_take_zoom

    layout = _layout(tmp_path)
    plan = prepare_rough_cut(
        _session(layout), silence=SilenceSettings.from_preset(SilencePreset.MEDIUM)
    )
    settings = TakeZoomSettings(
        enabled=True, scale=ValueRange.fixed(140), every=ValueRange.fixed(2), offset_x=25.0
    )
    plan = with_take_zoom(plan, settings)
    assert len(plan.keep_ranges) >= 2
    path = save_plan_for_resolve(plan, apply=True, directory=tmp_path / "plans")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["take_zoom"]["summary"]["zoomed"] == len(plan.keep_ranges) // 2
    assert all("zoom" not in op for op in saved["operations"] if op["track_type"] == "audio")
    output = _run(tmp_path, path, {})
    result = output["result"]
    assert result["status"] == "SUCCESS", (result["message"], output["logs"])
    created = _timeline(output, "Episodio 1_OE_ROUGHCUT_001")
    starts = [keep.record_start for keep in plan.keep_ranges]
    for item in created["items"]:
        if item["track_type"] != "video":
            assert "ZoomX" not in item["props"]
            continue
        take = starts.index(item["start"]) + 1
        expected = 1.4 if take % 2 == 0 else 1.0
        assert item["props"]["ZoomX"] == expected and item["props"]["ZoomY"] == expected
        assert item["props"]["AnchorPointX"] == 25.0
    details = result["details"]
    assert details["take_starts"] == starts
    assert details["take_zoom"]["failures"] == 0
    assert len(details["take_zoom"]["journal"]) == len(plan.keep_ranges)
    assert details["take_zoom"]["journal"][0]["before"]["ZoomX"] == 1.1
    original = _timeline(output, "Episodio 1")
    assert original["mutation_log"] == ["DuplicateTimeline(source)"]
    assert all(
        item["props"].get("ZoomX") == 1.1
        for item in original["items"]
        if item["track_type"] == "video"
    )
