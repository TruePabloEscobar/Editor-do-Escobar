from __future__ import annotations

import pytest

from o_editor.domain.enums import ChannelMode, TrackType
from o_editor.domain.source_timing import SourceTimingError, resolve_source_timing
from o_editor.domain.speech import (
    RawSegment,
    SegmentFlag,
    build_segments,
    detect_bleed,
    text_similarity,
)
from o_editor.domain.timeline_layout import ClipInfo
from o_editor.infrastructure.audio.track_renderer import channel_filter


def _clip(**overrides: object) -> ClipInfo:
    values: dict[str, object] = {
        "item_id": "c",
        "track_type": TrackType.AUDIO,
        "track_index": 1,
        "item_index": 1,
        "name": "mic.wav",
        "item_type": "audio",
        "start_frame": 1000,
        "end_frame": 1240,
        "source_start_frame": 240,
        "source_end_frame": 480,
        "source_start_seconds": 10.0,
        "left_offset_frames": 240.0,
        "media_pool_item_id": "m",
        "file_path": "x.wav",
        "media_fps": 24.0,
    }
    values.update(overrides)
    return ClipInfo(**values)  # type: ignore[arg-type]


def test_source_timing_requires_agreement() -> None:
    timing = resolve_source_timing(_clip(), timeline_fps=24.0, media_duration_seconds=60.0)
    assert timing.offset_seconds == pytest.approx(10.0)
    assert timing.duration_seconds == pytest.approx(10.0)
    with pytest.raises(SourceTimingError, match="divergentes"):
        resolve_source_timing(
            _clip(left_offset_frames=0.0, source_start_seconds=3600.0),
            timeline_fps=24.0,
            media_duration_seconds=None,
        )


def test_source_timing_rejects_range_beyond_media_and_speed_changes() -> None:
    with pytest.raises(SourceTimingError, match="ultrapassa"):
        resolve_source_timing(_clip(), timeline_fps=24.0, media_duration_seconds=12.0)
    with pytest.raises(SourceTimingError, match="velocidade"):
        resolve_source_timing(
            _clip(speed_percent=150.0), timeline_fps=24.0, media_duration_seconds=None
        )


def test_channel_filter_prefers_resolve_mapping() -> None:
    assert channel_filter(4, (3,), ChannelMode.BOTH) == ("pan=mono|c0=c2", ())
    assert channel_filter(1, None, ChannelMode.MONO) == (None, ())
    left, _ = channel_filter(2, None, ChannelMode.LEFT)
    assert left == "pan=mono|c0=c0"
    both, _ = channel_filter(2, None, ChannelMode.BOTH)
    assert both == "pan=mono|c0=0.500000*c0+0.500000*c1"
    _expr, warnings = channel_filter(6, None, ChannelMode.BOTH)
    assert warnings


def test_build_segments_sorts_across_tracks_with_stable_ids() -> None:
    raw = [
        RawSegment(2, 500, 600, "segunda"),
        RawSegment(1, 100, 200, "primeira"),
        RawSegment(1, 550, 650, "sobreposta"),
        RawSegment(3, 700, 720, "(risos)"),
    ]
    segments = build_segments(raw, {1: "Pablo", 2: "Jessica", 3: "Mileni"})
    assert [item.segment_id for item in segments] == [
        "SEG_0001",
        "SEG_0002",
        "SEG_0003",
        "SEG_0004",
    ]
    assert [item.speaker for item in segments] == ["Pablo", "Jessica", "Pablo", "Mileni"]
    assert SegmentFlag.OVERLAP in segments[1].flags and SegmentFlag.OVERLAP in segments[2].flags
    assert SegmentFlag.OVERLAP not in segments[0].flags
    assert SegmentFlag.NON_SPEECH in segments[3].flags


def test_bleed_requires_level_evidence() -> None:
    raw = [
        RawSegment(1, 100, 200, "Vamos começar agora", energy_db=-18.0),
        RawSegment(2, 102, 198, "vamos começar agora", energy_db=-40.0),
    ]
    segments, notes = detect_bleed(build_segments(raw, {1: "A", 2: "B"}))
    assert notes == ()
    assert segments[1].is_bleed and segments[1].related_segment_id == "SEG_0001"
    assert SegmentFlag.OVERLAP not in segments[0].flags
    no_level = [
        RawSegment(1, 100, 200, "Vamos começar agora"),
        RawSegment(2, 102, 198, "vamos começar agora"),
    ]
    kept, notes = detect_bleed(build_segments(no_level, {1: "A", 2: "B"}))
    assert not any(item.is_bleed for item in kept)
    assert notes


def test_text_similarity_ignores_case_and_accents() -> None:
    assert text_similarity("Inteligência Artificial!", "inteligencia artificial") == 1.0
    assert text_similarity("abc", "") == 0.0


def test_source_eof_padding_is_bounded_and_preserves_duration() -> None:
    timing = resolve_source_timing(
        _clip(right_offset_frames=0), timeline_fps=24.0, media_duration_seconds=19.92
    )
    assert timing.offset_seconds == 10.0
    assert timing.duration_seconds == 10.0
    assert timing.warnings
    with pytest.raises(SourceTimingError, match="ultrapassa"):
        resolve_source_timing(
            _clip(right_offset_frames=0), timeline_fps=24.0, media_duration_seconds=19.8
        )


@pytest.mark.parametrize("right_offset", [None, 1])
def test_source_interior_range_cannot_use_eof_padding(right_offset: int | None) -> None:
    with pytest.raises(SourceTimingError, match="ultrapassa"):
        resolve_source_timing(
            _clip(right_offset_frames=right_offset),
            timeline_fps=24.0,
            media_duration_seconds=19.92,
        )


@pytest.mark.parametrize("nominal", [24, 30, 60, 120])
def test_long_ntsc_eof_uses_independent_end_time_for_clock_drift(nominal: int) -> None:
    fps = round(nominal * 1000 / 1001, 3)
    exact_fps = nominal * 1000 / 1001
    frames = round(13237 * exact_fps)
    clip = _clip(
        start_frame=0,
        end_frame=frames,
        source_start_frame=0,
        source_end_frame=frames - 2,
        source_start_seconds=0.0,
        source_end_seconds=frames / exact_fps,
        left_offset_frames=0,
        right_offset_frames=0,
        media_fps=fps,
    )
    timing = resolve_source_timing(
        clip,
        timeline_fps=fps,
        media_duration_seconds=(frames - 2) / exact_fps,
    )
    assert timing.offset_seconds == 0
    assert timing.duration_seconds == frames / fps
    assert timing.warnings
    # Extra loss beyond the existing two-frame / 50 ms bound must stay blocked.
    with pytest.raises(SourceTimingError, match="ultrapassa"):
        resolve_source_timing(
            clip,
            timeline_fps=fps,
            media_duration_seconds=frames / exact_fps - max(3 / exact_fps, 0.1),
        )


@pytest.mark.parametrize(
    "end_time,right_offset",
    [(None, 0), (13000.0, 0), (13237.432541667, None), (13237.432541667, 1)],
)
def test_long_eof_clock_allowance_requires_matching_time_and_eof(
    end_time: float | None,
    right_offset: int | None,
) -> None:
    with pytest.raises(SourceTimingError, match="ultrapassa"):
        resolve_source_timing(
            _clip(
                start_frame=0,
                end_frame=317381,
                source_start_frame=0,
                source_end_frame=317379,
                source_start_seconds=0.0,
                source_end_seconds=end_time,
                left_offset_frames=0,
                right_offset_frames=right_offset,
                media_fps=23.976,
            ),
            timeline_fps=23.976,
            media_duration_seconds=13237.349125,
        )
