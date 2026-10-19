from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from o_editor.domain.enums import TrackType
from o_editor.domain.timeline_layout import (
    ClipInfo,
    LayoutError,
    TimelineLayout,
    parse_track_key,
    track_key,
)
from tests.fixtures.podcast import podcast_layout
from tests.lua_runner import lua_command

ROOT = Path(__file__).resolve().parents[2]
LUA = lua_command()


def test_layout_reports_tracks_clips_and_gaps() -> None:
    layout = podcast_layout()
    assert [track.display_name for track in layout.tracks_of(TrackType.AUDIO)][:4] == [
        "A1: Pablo",
        "A2: Jessica",
        "A3: Mileni",
        "A4: Renne",
    ]
    jessica = layout.clips_in_track(TrackType.AUDIO, 2)
    assert len(jessica) == 2
    assert layout.gaps(TrackType.AUDIO, 2) == (
        (jessica[0].end_frame, jessica[1].start_frame),
        (jessica[1].end_frame, layout.end_frame),
    )
    assert layout.validate() == ()


def test_track_name_is_not_media_file_name() -> None:
    layout = podcast_layout()
    pablo_track = layout.track(TrackType.AUDIO, 1)
    pablo_clip = layout.clips_in_track(TrackType.AUDIO, 1)[0]
    assert pablo_track is not None
    assert pablo_track.name == "Pablo"
    assert pablo_clip.file_path is not None
    assert pablo_clip.file_path.endswith("mic_01.wav")


def test_source_mapping_and_channel_routing() -> None:
    clip = ClipInfo(
        item_id="x",
        track_type=TrackType.AUDIO,
        track_index=1,
        item_index=1,
        name="poly.wav",
        item_type="audio",
        start_frame=100,
        end_frame=200,
        source_start_frame=1000,
        source_end_frame=1100,
        media_pool_item_id="m",
        audio_channel_mapping='{"track_mapping":{"1":{"channel_idx":[3],"mute":false,"type":"mono"}}}',
    )
    assert clip.is_unit_speed
    assert clip.source_frame_at(150) == 1050
    assert clip.source_channel_indices() == (3,)
    with pytest.raises(LayoutError):
        clip.source_frame_at(250)


def test_overlap_inside_track_is_reported() -> None:
    layout = podcast_layout()
    first = layout.clips_in_track(TrackType.AUDIO, 1)[0]
    overlapping = ClipInfo.from_dict(
        {**first.to_dict(), "item_id": "dup", "start_frame": first.start_frame + 10}
    )
    broken = TimelineLayout.from_dict(
        {**layout.to_dict(), "clips": [*layout.to_dict()["clips"], overlapping.to_dict()]}
    )
    assert any("se sobrepõem" in problem for problem in broken.validate())


def test_round_trip_and_fingerprint_are_stable() -> None:
    layout = podcast_layout()
    clone = TimelineLayout.from_dict(json.loads(json.dumps(layout.to_dict())))
    assert clone == layout
    assert clone.fingerprint == layout.fingerprint


def test_track_keys() -> None:
    assert track_key(TrackType.AUDIO, 3) == "A3"
    assert parse_track_key("v2") == (TrackType.VIDEO, 2)
    with pytest.raises(LayoutError):
        parse_track_key("X1")


def test_missing_layout_in_context_has_actionable_message() -> None:
    with pytest.raises(LayoutError, match="O EDITOR"):
        TimelineLayout.from_internal_context({"project_name": "P", "timeline_name": "T"})


@pytest.mark.skipif(LUA is None, reason="interpretador Lua 5.1 não disponível")
def test_lua_capture_layout_against_fake_resolve() -> None:
    assert LUA is not None
    output = subprocess.run(
        [
            *LUA,
            str(ROOT / "tests" / "lua" / "run_capture.lua"),
            str(ROOT / "launcher"),
            str(ROOT / "tests" / "lua"),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    context = json.loads(output)
    assert context["schema_version"] == 3
    layout = TimelineLayout.from_internal_context(context)
    assert layout.start_frame == 86400
    assert [track.name for track in layout.tracks_of(TrackType.AUDIO)] == [
        "Pablo",
        "Jessica",
        "Mileni",
        "Renne",
        "Musica",
    ]
    pablo = layout.clips_in_track(TrackType.AUDIO, 1)[0]
    assert pablo.source_start_frame == 1000
    assert pablo.left_offset_frames == 1000
    assert pablo.linked_item_ids == ("v1-cam",)
    assert pablo.source_channel_indices() == (1,)
    assert layout.validate() == ()


def test_source_inpoint_prefers_agreeing_offset_and_rational_time():
    from dataclasses import replace

    clip = podcast_layout().clips[0]
    clip = replace(
        clip,
        start_frame=0,
        end_frame=7512,
        source_start_frame=14233,
        source_end_frame=21746,
        left_offset_frames=14234.0,
        source_start_seconds=14234 / (24000 / 1001),
        media_fps=23.976,
    )
    assert clip.source_frame_at(0, timeline_fps=23.976) == 14234
    assert clip.source_frame_at(1145, timeline_fps=23.976) == 15379


def test_short_native_clip_with_truncated_end_requires_independent_time():
    from dataclasses import replace

    from o_editor.domain.enums import TrackType
    from o_editor.domain.timeline_layout import ClipInfo

    clip = ClipInfo(
        item_id="short",
        track_type=TrackType.AUDIO,
        track_index=1,
        item_index=1,
        name="mic",
        item_type="audio",
        start_frame=36,
        end_frame=54,
        source_start_frame=36,
        source_end_frame=53,
        source_start_seconds=1.5015,
        source_end_seconds=2.25225,
        left_offset_frames=36,
        media_fps=23.976,
        speed_percent=100,
    )
    assert clip.is_unit_speed
    assert clip.source_frame_at(54, timeline_fps=23.976) == 54
    assert not replace(clip, source_end_seconds=None).is_unit_speed
    assert not replace(clip, source_end_seconds=2.1).is_unit_speed
    assert not replace(clip, speed_percent=150).is_unit_speed
    assert not replace(clip, source_end_frame=52).is_unit_speed
