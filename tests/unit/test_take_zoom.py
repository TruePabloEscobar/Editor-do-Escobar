"""Zoom per take: which takes get zoom, how much, and on which items."""

from __future__ import annotations

from dataclasses import replace
from itertools import pairwise

import pytest

from o_editor.domain.enums import TrackType
from o_editor.domain.take_zoom import (
    Take,
    TakeZoomError,
    TakeZoomSettings,
    ValueRange,
    assign_takes,
    item_targets,
    operation_zoom,
    takes_from_bounds,
    takes_from_layout,
    values_match,
)
from o_editor.domain.timeline_layout import ClipInfo, TimelineLayout, TrackInfo


def _takes(count: int) -> tuple[Take, ...]:
    return takes_from_bounds((index * 100, index * 100 + 100) for index in range(count))


def _layout(v1: list[tuple[int, int]], v2: list[tuple[int, int]] | None = None) -> TimelineLayout:
    clips = []
    for track, ranges in ((1, v1), (2, v2 or [])):
        for number, (start, end) in enumerate(ranges, start=1):
            clips.append(
                ClipInfo(
                    item_id=f"v{track}-{number}",
                    track_type=TrackType.VIDEO,
                    track_index=track,
                    item_index=number,
                    name=f"cam{track}",
                    item_type="video",
                    start_frame=start,
                    end_frame=end,
                )
            )
    tracks = [TrackInfo(TrackType.VIDEO, 1, "Cam A"), TrackInfo(TrackType.VIDEO, 2, "Cam B")]
    return TimelineLayout(
        project_name="Podcast",
        timeline_name="Episodio_OE_ROUGHCUT_001",
        timeline_id="tl-copy",
        fps=24,
        start_frame=0,
        end_frame=max(end for _start, end in v1 + (v2 or [])),
        start_timecode="00:00:00:00",
        drop_frame=False,
        tracks=tuple(tracks),
        clips=tuple(clips),
    )


def test_fixed_frequency_and_fixed_scale_zoom_every_second_take() -> None:
    settings = TakeZoomSettings(
        enabled=True, scale=ValueRange.fixed(130), every=ValueRange.fixed(2)
    )
    result = assign_takes(_takes(7), settings)
    assert [item.scale for item in result] == [None, 130, None, 130, None, 130, None]


def test_every_take_and_shrinking_below_full_frame_are_allowed() -> None:
    settings = TakeZoomSettings(scale=ValueRange.fixed(50), every=ValueRange.fixed(1))
    assert {item.scale for item in assign_takes(_takes(4), settings)} == {50}
    # No artificial ceiling: anything Resolve accepts (up to 10000%) is valid.
    assert not replace(settings, scale=ValueRange.fixed(900)).problems()


def test_scale_range_draws_whole_percent_inside_bounds_and_is_reproducible() -> None:
    settings = TakeZoomSettings(scale=ValueRange(100, 150), every=ValueRange.fixed(1), seed=7)
    first = assign_takes(_takes(60), settings)
    again = assign_takes(_takes(60), settings)
    scales = [item.scale for item in first]
    assert scales == [item.scale for item in again]
    assert all(value is not None and 100 <= value <= 150 for value in scales)
    assert all(value == int(value) for value in scales if value is not None)
    assert len(set(scales)) > 5
    other = assign_takes(_takes(60), replace(settings, seed=8))
    assert [item.scale for item in other] != scales


def test_frequency_range_keeps_gaps_inside_bounds() -> None:
    settings = TakeZoomSettings(scale=ValueRange.fixed(120), every=ValueRange(2, 4), seed=3)
    result = assign_takes(_takes(200), settings)
    positions = [index for index, item in enumerate(result, start=1) if item.zoomed]
    gaps = [positions[0], *(b - a for a, b in pairwise(positions))]
    assert set(gaps) <= {2, 3, 4}
    assert len(set(gaps)) == 3


def test_changing_the_scale_range_keeps_the_same_zoomed_takes() -> None:
    base = TakeZoomSettings(scale=ValueRange(100, 150), every=ValueRange(2, 5), seed=11)
    zoomed = [item.zoomed for item in assign_takes(_takes(50), base)]
    other = replace(base, scale=ValueRange(60, 80))
    assert [item.zoomed for item in assign_takes(_takes(50), other)] == zoomed


def test_inverted_ranges_are_normalised_and_invalid_values_rejected() -> None:
    settings = TakeZoomSettings(scale=ValueRange(150, 100), every=ValueRange(4, 2))
    assert not settings.problems()
    assert all(
        item.scale is None or 100 <= item.scale <= 150
        for item in assign_takes(_takes(20), settings)
    )
    for invalid in (
        replace(settings, scale=ValueRange.fixed(0.5)),
        replace(settings, scale=ValueRange.fixed(10001)),
        replace(settings, every=ValueRange.fixed(0)),
        replace(settings, every=ValueRange(1.5, 2)),
        replace(settings, video_tracks=()),
    ):
        assert invalid.problems()
        with pytest.raises(TakeZoomError):
            assign_takes(_takes(3), invalid)


def test_settings_round_trip() -> None:
    settings = TakeZoomSettings(
        enabled=True,
        scale=ValueRange(90, 140),
        every=ValueRange(2, 3),
        base_scale=None,
        offset_x=-120.5,
        offset_y=40,
        video_tracks=(2, 1),
        seed=99,
    )
    restored = TakeZoomSettings.from_dict(settings.to_dict())
    assert restored == replace(settings, video_tracks=(1, 2))


def test_takes_from_layout_use_items_or_saved_cut_points() -> None:
    layout = _layout([(0, 100), (100, 250), (250, 300)])
    assert [(t.start_frame, t.end_frame) for t in takes_from_layout(layout, 1)] == [
        (0, 100),
        (100, 250),
        (250, 300),
    ]
    # Original clip boundary at 100 is not a cut: the saved cut points win.
    takes = takes_from_layout(layout, 1, boundaries=[0, 250])
    assert [(t.index, t.start_frame, t.end_frame) for t in takes] == [(1, 0, 250), (2, 250, 300)]
    assert takes_from_layout(layout, 2) == ()
    # Cut points that no longer fall on item edges (timeline edited) are ignored.
    takes = takes_from_layout(layout, 1, boundaries=[0, 120])
    assert [(t.start_frame, t.end_frame) for t in takes] == [(0, 100), (100, 250), (250, 300)]


def test_item_targets_cover_selected_tracks_with_centre_default_and_offset() -> None:
    layout = _layout([(0, 100), (100, 200), (200, 300)], v2=[(0, 300)])
    settings = TakeZoomSettings(scale=ValueRange.fixed(125), every=ValueRange.fixed(2))
    assignments = assign_takes(takes_from_layout(layout, 1), settings)
    targets = item_targets(layout, assignments, settings)
    assert [(t.item_id, t.zoom, t.anchor_x, t.anchor_y) for t in targets] == [
        ("v1-1", 1.0, 0.0, 0.0),
        ("v1-2", 1.25, 0.0, 0.0),
        ("v1-3", 1.0, 0.0, 0.0),
    ]
    moved = replace(settings, offset_x=-80, offset_y=35.5, video_tracks=(1, 2))
    targets = item_targets(layout, assign_takes(takes_from_layout(layout, 1), moved), moved)
    assert {t.item_id for t in targets} == {"v1-1", "v1-2", "v1-3", "v2-1"}
    assert all((t.anchor_x, t.anchor_y) == (-80, 35.5) for t in targets)
    assert targets[0].properties == {
        "ZoomX": 1.0,
        "ZoomY": 1.0,
        "AnchorPointX": -80,
        "AnchorPointY": 35.5,
    }


def test_keep_current_size_for_takes_without_zoom() -> None:
    layout = _layout([(0, 100), (100, 200), (200, 300), (300, 400)])
    settings = TakeZoomSettings(
        scale=ValueRange.fixed(140), every=ValueRange.fixed(2), base_scale=None
    )
    targets = item_targets(layout, assign_takes(takes_from_layout(layout, 1), settings), settings)
    assert [(t.item_id, t.zoom) for t in targets] == [("v1-2", 1.4), ("v1-4", 1.4)]


def test_operation_zoom_maps_each_kept_range_to_one_take() -> None:
    settings = TakeZoomSettings(scale=ValueRange.fixed(115), every=ValueRange.fixed(3))
    assignments, by_keep = operation_zoom(6, settings)
    assert [item.zoomed for item in assignments] == [False, False, True, False, False, True]
    assert by_keep[2]["ZoomX"] == pytest.approx(1.15)
    assert by_keep[0]["ZoomX"] == 1.0
    _assignments, only_zoomed = operation_zoom(6, replace(settings, base_scale=None))
    assert sorted(only_zoomed) == [2, 5]


def test_values_match_uses_tolerance_and_rejects_missing_readback() -> None:
    expected = {"ZoomX": 1.25, "ZoomY": 1.25, "AnchorPointX": 10.0, "AnchorPointY": 0.0}
    assert values_match({**expected, "ZoomX": 1.2500001}, expected)
    assert not values_match({**expected, "ZoomX": 1.3}, expected)
    assert not values_match({"ZoomX": 1.25}, expected)
