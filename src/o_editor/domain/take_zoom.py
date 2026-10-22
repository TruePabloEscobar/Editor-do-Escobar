"""Zoom per take ("punch-in"): pure rules, no Resolve access.

A *take* is each stretch between cuts. One take in every N gets a fixed zoom for its
whole duration; N and the zoom can be fixed values or ranges drawn reproducibly
from a seed. Values are absolute: 100% is the normal full-frame size in Resolve,
below 100% shrinks the picture. The zoom point defaults to the centre of the frame
(offset 0, 0) and can be moved in pixels (Inspector "Anchor Point").
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from itertools import pairwise
from typing import Any

from o_editor.domain.enums import TrackType
from o_editor.domain.rough_cut import RoughCutPlan
from o_editor.domain.timeline_layout import TimelineLayout

TAKE_ZOOM_SCHEMA_VERSION = 1
# Resolve TimelineItem ZoomX/ZoomY accept 0.0-100.0 where 1.0 is 100% (README 21.1).
ZOOM_MIN_PERCENT = 1.0
ZOOM_MAX_PERCENT = 10000.0
# AnchorPointX/Y accept +/- 4x the timeline width/height; keep a generous fixed bound.
OFFSET_LIMIT_PIXELS = 32768.0
FREQUENCY_MAX = 99
ZOOM_PROPERTY_KEYS = ("ZoomX", "ZoomY", "AnchorPointX", "AnchorPointY")
# Readback tolerance: Resolve stores these as floats.
ZOOM_TOLERANCE = 0.0005
ANCHOR_TOLERANCE = 0.01


class TakeZoomError(ValueError):
    """Invalid take-zoom settings or inputs."""


@dataclass(frozen=True, slots=True)
class ValueRange:
    """Closed interval; ``minimum == maximum`` means a fixed value."""

    minimum: float
    maximum: float

    @classmethod
    def fixed(cls, value: float) -> ValueRange:
        return cls(value, value)

    @property
    def is_fixed(self) -> bool:
        return self.minimum == self.maximum

    def ordered(self) -> ValueRange:
        if self.minimum <= self.maximum:
            return self
        return ValueRange(self.maximum, self.minimum)

    def to_dict(self) -> dict[str, float]:
        return {"minimum": self.minimum, "maximum": self.maximum}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ValueRange:
        return cls(float(value["minimum"]), float(value["maximum"])).ordered()


@dataclass(frozen=True, slots=True)
class TakeZoomSettings:
    enabled: bool = False
    scale: ValueRange = field(default_factory=lambda: ValueRange(110.0, 130.0))
    every: ValueRange = field(default_factory=lambda: ValueRange.fixed(2))
    # Size of the takes without zoom; ``None`` leaves them as they are.
    base_scale: float | None = 100.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    video_tracks: tuple[int, ...] = (1,)
    seed: int = 1

    def problems(self) -> tuple[str, ...]:
        result: list[str] = []
        scale = self.scale.ordered()
        if scale.minimum < ZOOM_MIN_PERCENT or scale.maximum > ZOOM_MAX_PERCENT:
            result.append(
                f"O zoom deve ficar entre {ZOOM_MIN_PERCENT:g}% e {ZOOM_MAX_PERCENT:g}% "
                "(limite do DaVinci Resolve)."
            )
        if self.base_scale is not None and not (
            ZOOM_MIN_PERCENT <= self.base_scale <= ZOOM_MAX_PERCENT
        ):
            result.append("O tamanho dos takes sem zoom está fora do limite do Resolve.")
        every = self.every.ordered()
        if (
            every.minimum < 1
            or every.maximum > FREQUENCY_MAX
            or every.minimum != int(every.minimum)
            or every.maximum != int(every.maximum)
        ):
            result.append(f"A frequência deve ser um número inteiro de 1 a {FREQUENCY_MAX}.")
        if abs(self.offset_x) > OFFSET_LIMIT_PIXELS or abs(self.offset_y) > OFFSET_LIMIT_PIXELS:
            result.append("O deslocamento do ponto de zoom é grande demais.")
        if not self.video_tracks or any(index < 1 for index in self.video_tracks):
            result.append("Escolha pelo menos uma faixa de vídeo para o zoom.")
        return tuple(result)

    def validated(self) -> TakeZoomSettings:
        problems = self.problems()
        if problems:
            raise TakeZoomError(" ".join(problems))
        return self

    @property
    def reference_track(self) -> int:
        return min(self.video_tracks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TAKE_ZOOM_SCHEMA_VERSION,
            "enabled": self.enabled,
            "scale": self.scale.to_dict(),
            "every": self.every.to_dict(),
            "base_scale": self.base_scale,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "video_tracks": list(self.video_tracks),
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TakeZoomSettings:
        base = value.get("base_scale", 100.0)
        tracks = tuple(sorted({int(item) for item in value.get("video_tracks") or (1,)}))
        return cls(
            enabled=bool(value.get("enabled", False)),
            scale=ValueRange.from_dict(value.get("scale") or {"minimum": 110, "maximum": 130}),
            every=ValueRange.from_dict(value.get("every") or {"minimum": 2, "maximum": 2}),
            base_scale=None if base is None else float(base),
            offset_x=float(value.get("offset_x", 0.0)),
            offset_y=float(value.get("offset_y", 0.0)),
            video_tracks=tracks or (1,),
            seed=int(value.get("seed", 1)),
        )


@dataclass(frozen=True, slots=True)
class Take:
    index: int
    start_frame: int
    end_frame: int

    @property
    def duration_frames(self) -> int:
        return self.end_frame - self.start_frame


@dataclass(frozen=True, slots=True)
class TakeAssignment:
    take: Take
    # Percentage for zoomed takes; ``None`` means "take without zoom".
    scale: float | None

    @property
    def zoomed(self) -> bool:
        return self.scale is not None


@dataclass(frozen=True, slots=True)
class ItemZoomTarget:
    """Values one timeline item must end up with (Resolve property units)."""

    item_id: str
    track_index: int
    take_index: int
    start_frame: int
    end_frame: int
    zoom: float
    anchor_x: float
    anchor_y: float

    @property
    def properties(self) -> dict[str, float]:
        return zoom_properties(self.zoom * 100.0, self.anchor_x, self.anchor_y)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "track_index": self.track_index,
            "take_index": self.take_index,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "set": self.properties,
        }


def zoom_properties(scale_percent: float, anchor_x: float, anchor_y: float) -> dict[str, float]:
    zoom = round(scale_percent / 100.0, 6)
    return {"ZoomX": zoom, "ZoomY": zoom, "AnchorPointX": anchor_x, "AnchorPointY": anchor_y}


def takes_from_bounds(bounds: Iterable[tuple[int, int]]) -> tuple[Take, ...]:
    ordered = sorted((int(start), int(end)) for start, end in bounds if int(end) > int(start))
    return tuple(Take(index, start, end) for index, (start, end) in enumerate(ordered, start=1))


def takes_from_layout(
    layout: TimelineLayout,
    reference_track: int,
    *,
    boundaries: Sequence[int] | None = None,
) -> tuple[Take, ...]:
    """Takes of an existing timeline.

    With ``boundaries`` (take start frames saved when O Editor built the timeline)
    the takes are exactly the original cuts. Without them each item of the
    reference video track is one take.
    """

    clips = layout.clips_in_track(TrackType.VIDEO, reference_track)
    if not clips:
        return ()
    if not boundaries or not cut_points_match(layout, reference_track, boundaries):
        return takes_from_bounds((clip.start_frame, clip.end_frame) for clip in clips)
    start = min(clip.start_frame for clip in clips)
    end = max(clip.end_frame for clip in clips)
    cuts = sorted({int(item) for item in boundaries if start < int(item) < end})
    edges = [start, *cuts, end]
    return takes_from_bounds(pairwise(edges))


def cut_points_match(
    layout: TimelineLayout, reference_track: int, boundaries: Sequence[int]
) -> bool:
    """Saved cut points still fall on item edges (no blade exists to split items)."""

    clips = layout.clips_in_track(TrackType.VIDEO, reference_track)
    if not clips:
        return False
    start = min(clip.start_frame for clip in clips)
    end = max(clip.end_frame for clip in clips)
    edges = {clip.start_frame for clip in clips} | {clip.end_frame for clip in clips}
    return all(int(value) in edges for value in boundaries if start < int(value) < end)


def assign_takes(takes: Sequence[Take], settings: TakeZoomSettings) -> tuple[TakeAssignment, ...]:
    """Pick which takes get zoom and how much; same seed gives the same result."""

    settings.validated()
    scale = settings.scale.ordered()
    every = settings.every.ordered()
    frequency_random = random.Random(f"o-editor-take-zoom:{settings.seed}:every")
    scale_random = random.Random(f"o-editor-take-zoom:{settings.seed}:scale")

    def next_gap() -> int:
        if every.is_fixed:
            return int(every.minimum)
        return frequency_random.randint(int(every.minimum), int(every.maximum))

    def next_scale() -> float:
        if scale.is_fixed:
            return scale.minimum
        drawn = round(scale_random.uniform(scale.minimum, scale.maximum))
        return float(min(max(drawn, scale.minimum), scale.maximum))

    result: list[TakeAssignment] = []
    next_zoom = next_gap()
    for position, take in enumerate(takes, start=1):
        if position == next_zoom:
            result.append(TakeAssignment(take, next_scale()))
            next_zoom = position + next_gap()
        else:
            result.append(TakeAssignment(take, None))
    return tuple(result)


def item_targets(
    layout: TimelineLayout,
    assignments: Sequence[TakeAssignment],
    settings: TakeZoomSettings,
) -> tuple[ItemZoomTarget, ...]:
    """Map each take onto the video items of the chosen tracks it covers."""

    targets: list[ItemZoomTarget] = []
    for track_index in sorted(set(settings.video_tracks)):
        for clip in layout.clips_in_track(TrackType.VIDEO, track_index):
            best: TakeAssignment | None = None
            best_overlap = 0
            for assignment in assignments:
                overlap = min(clip.end_frame, assignment.take.end_frame) - max(
                    clip.start_frame, assignment.take.start_frame
                )
                if overlap > best_overlap:
                    best, best_overlap = assignment, overlap
            if best is None:
                continue
            scale = best.scale if best.scale is not None else settings.base_scale
            if scale is None:
                continue
            targets.append(
                ItemZoomTarget(
                    item_id=clip.item_id,
                    track_index=track_index,
                    take_index=best.take.index,
                    start_frame=clip.start_frame,
                    end_frame=clip.end_frame,
                    zoom=round(scale / 100.0, 6),
                    anchor_x=settings.offset_x,
                    anchor_y=settings.offset_y,
                )
            )
    return tuple(targets)


def operation_zoom(
    keep_count: int, settings: TakeZoomSettings
) -> tuple[tuple[TakeAssignment, ...], dict[int, dict[str, float]]]:
    """Zoom of each kept range of a rough cut (one take per kept range).

    Returns the assignments and, by ``keep_index``, the properties to set on the
    selected video tracks; takes without zoom with ``base_scale=None`` are absent.
    """

    takes = tuple(Take(index + 1, index, index + 1) for index in range(keep_count))
    assignments = assign_takes(takes, settings)
    by_keep: dict[int, dict[str, float]] = {}
    for assignment in assignments:
        scale = assignment.scale if assignment.scale is not None else settings.base_scale
        if scale is None:
            continue
        by_keep[assignment.take.index - 1] = zoom_properties(
            scale, settings.offset_x, settings.offset_y
        )
    return assignments, by_keep


def values_match(current: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    """Compare Resolve readback with planned values using float tolerances."""

    for key, value in expected.items():
        reading = current.get(key)
        if not isinstance(reading, int | float) or isinstance(reading, bool):
            return False
        tolerance = ZOOM_TOLERANCE if key.startswith("Zoom") else ANCHOR_TOLERANCE
        if abs(float(reading) - float(value)) > tolerance:
            return False
    return True


def summarize(assignments: Sequence[TakeAssignment]) -> dict[str, Any]:
    zoomed = [item.scale for item in assignments if item.scale is not None]
    return {
        "takes": len(assignments),
        "zoomed": len(zoomed),
        "minimum": min(zoomed) if zoomed else None,
        "maximum": max(zoomed) if zoomed else None,
    }


def with_take_zoom(plan: RoughCutPlan, settings: TakeZoomSettings) -> RoughCutPlan:
    """Rough-cut plan whose video operations also carry the zoom of their take."""

    settings.validated()
    assignments, by_keep = operation_zoom(len(plan.keep_ranges), settings)
    tracks = set(settings.video_tracks)
    operations = tuple(
        replace(operation, zoom=by_keep.get(operation.keep_index))
        if operation.track_type == TrackType.VIDEO and operation.track_index in tracks
        else replace(operation, zoom=None)
        for operation in plan.operations
    )
    return replace(
        plan,
        operations=operations,
        take_zoom={"settings": settings.to_dict(), "summary": summarize(assignments)},
    )


def without_take_zoom(plan: RoughCutPlan) -> RoughCutPlan:
    """Same rough-cut plan with no zoom per take."""

    if plan.take_zoom is None and all(item.zoom is None for item in plan.operations):
        return plan
    return replace(
        plan,
        operations=tuple(replace(item, zoom=None) for item in plan.operations),
        take_zoom=None,
    )
