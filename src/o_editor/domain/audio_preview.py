"""Read-only projections of the final Rough Cut plan; no editorial decisions."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise

from o_editor.domain.enums import TrackType
from o_editor.domain.intervals import Interval, normalize
from o_editor.domain.rough_cut import RoughCutPlan, TrackPolicy
from o_editor.domain.timecode import frames_to_timecode
from o_editor.domain.timeline_layout import TimelineLayout


class RegionKind(StrEnum):
    KEEP = "MANTER"
    CUT = "CORTAR"
    MUTE = "DESATIVAR"


@dataclass(frozen=True, slots=True)
class PreviewRegion:
    start_frame: int
    end_frame: int
    kind: RegionKind
    muted_under_cut: bool = False


def operation_source_bounds(plan: RoughCutPlan, keep_index: int, start: int, end: int) -> Interval:
    keep = plan.keep_ranges[keep_index]
    return (
        keep.source_start + start - keep.record_start,
        keep.source_start + end - keep.record_start,
    )


def active_ranges(plan: RoughCutPlan, track_index: int) -> tuple[Interval, ...]:
    """Exactly the enabled audio operations the executor will insert."""
    track = plan.layout.track(TrackType.AUDIO, track_index)
    if track is None or track.enabled is False:
        return ()
    return normalize(
        operation_source_bounds(plan, op.keep_index, op.record_start, op.record_end)
        for op in plan.operations
        if op.track_type == TrackType.AUDIO and op.track_index == track_index and op.enabled
    )


def muted_ranges(plan: RoughCutPlan, track_index: int) -> tuple[Interval, ...]:
    track = plan.layout.track(TrackType.AUDIO, track_index)
    if (track is not None and track.enabled is False) or plan.track_policies.get(
        f"A{track_index}"
    ) == TrackPolicy.OMIT:
        return ((plan.layout.start_frame, plan.layout.end_frame),)
    return normalize(
        [
            (mute.start_frame, mute.end_frame)
            for mute in plan.microphone_mutes
            if mute.track_index == track_index
        ]
        + [
            operation_source_bounds(plan, op.keep_index, op.record_start, op.record_end)
            for op in plan.operations
            if op.track_type == TrackType.AUDIO and op.track_index == track_index and not op.enabled
        ]
    )


def regions_for_track(plan: RoughCutPlan, track_index: int) -> tuple[PreviewRegion, ...]:
    """Red takes precedence, while overlapping per-track mutes remain inspectable."""
    cuts = tuple((r.start_frame, r.end_frame) for r in plan.removed_ranges)
    mutes = muted_ranges(plan, track_index)
    kept = tuple((r.source_start, r.source_end) for r in plan.keep_ranges)
    boundaries = sorted(
        {point for group in (cuts, mutes, kept) for span in group for point in span}
    )
    starts = [[a for a, _ in group] for group in (cuts, mutes, kept)]
    result: list[PreviewRegion] = []
    for a, b in pairwise(boundaries):
        flags = []
        for group, begin in zip((cuts, mutes, kept), starts, strict=True):
            index = bisect_right(begin, a) - 1
            flags.append(index >= 0 and a < group[index][1])
        cut, muted, keep = flags
        if not (cut or muted or keep):
            continue
        kind = RegionKind.CUT if cut else RegionKind.MUTE if muted else RegionKind.KEEP
        under = cut and muted
        if (
            result
            and result[-1].end_frame == a
            and result[-1].kind == kind
            and result[-1].muted_under_cut == under
        ):
            previous = result.pop()
            result.append(PreviewRegion(previous.start_frame, b, kind, under))
        else:
            result.append(PreviewRegion(a, b, kind, under))
    return tuple(result)


def original_to_result(plan: RoughCutPlan, frame: int) -> int:
    """A seek inside a removed span lands on the next preserved boundary."""
    for keep in plan.keep_ranges:
        if frame < keep.source_start:
            return keep.record_start
        if frame < keep.source_end:
            return keep.record_start + frame - keep.source_start
    return plan.layout.start_frame + plan.stats.new_frames


def result_to_original(plan: RoughCutPlan, frame: int) -> int:
    for keep in plan.keep_ranges:
        if frame < keep.record_start + keep.duration_frames:
            return keep.source_start + max(0, frame - keep.record_start)
    return plan.keep_ranges[-1].source_end if plan.keep_ranges else plan.layout.start_frame


def original_to_sample(plan: RoughCutPlan, frame: int, sample_rate: int) -> int:
    """Sample position in the concatenated preview, including per-cut rounding."""
    origin, fps = plan.layout.start_frame, plan.layout.fps
    source_sample = round((frame - origin) * sample_rate / fps)
    cursor = 0
    for keep in plan.keep_ranges:
        first = round((keep.source_start - origin) * sample_rate / fps)
        last = round((keep.source_end - origin) * sample_rate / fps)
        if source_sample < first:
            return cursor
        if source_sample < last:
            return cursor + source_sample - first
        cursor += last - first
    return cursor


def sample_to_original(plan: RoughCutPlan, sample: int, sample_rate: int) -> int:
    """Inverse of the actual PCM concatenation; no cumulative fractional-FPS drift."""
    origin, fps = plan.layout.start_frame, plan.layout.fps
    cursor = 0
    for keep in plan.keep_ranges:
        first = round((keep.source_start - origin) * sample_rate / fps)
        last = round((keep.source_end - origin) * sample_rate / fps)
        if sample < cursor + last - first:
            return origin + round((first + max(0, sample - cursor)) * fps / sample_rate)
        cursor += last - first
    return plan.keep_ranges[-1].source_end if plan.keep_ranges else origin


def timeline_timecode(layout: TimelineLayout, frame: int) -> str:
    """Anchor the ruler to captured start TC, even when absolute frame origins differ."""
    nominal = round(layout.fps)
    drop = layout.drop_frame or ";" in layout.start_timecode
    try:
        hours, minutes, seconds, frames = (
            int(value) for value in layout.start_timecode.replace(";", ":").split(":")
        )
        start = ((hours * 60 + minutes) * 60 + seconds) * nominal + frames
        if drop:
            elapsed_minutes = hours * 60 + minutes
            start -= (nominal // 15) * (elapsed_minutes - elapsed_minutes // 10)
    except ValueError:
        start = layout.start_frame
    return frames_to_timecode(
        max(0, start + frame - layout.start_frame), layout.fps, drop_frame=drop
    )
