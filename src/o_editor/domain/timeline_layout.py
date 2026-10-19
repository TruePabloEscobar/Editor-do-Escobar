"""Pure clip-level model of a Resolve timeline captured by the internal host.

All positions are timeline frames (absolute, as reported by ``TimelineItem.GetStart``).
The layout is read-only evidence: it never talks to Resolve and is used to
reconstruct per-track audio and to plan non-destructive rough cuts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from o_editor.domain.enums import TrackType
from o_editor.domain.timecode import source_time_matches_frame

LAYOUT_SCHEMA_VERSION = 1
REBUILDABLE_ITEM_TYPES = frozenset({"video", "audio"})
# Source/timeline frame ratios closer than this to 1.0 are treated as exactly 1.0.
UNIT_RATIO_TOLERANCE = 0.005


class LayoutError(ValueError):
    """The captured layout is structurally invalid."""


@dataclass(frozen=True, slots=True)
class TrackInfo:
    track_type: TrackType
    index: int
    name: str
    subtype: str | None = None
    enabled: bool | None = None
    locked: bool | None = None

    def __post_init__(self) -> None:
        if self.index < 1:
            raise LayoutError("track index must be at least 1")

    @property
    def key(self) -> str:
        return track_key(self.track_type, self.index)

    @property
    def display_name(self) -> str:
        return f"{self.key}: {self.name}" if self.name else self.key

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_type": self.track_type.value,
            "index": self.index,
            "name": self.name,
            "subtype": self.subtype,
            "enabled": self.enabled,
            "locked": self.locked,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> TrackInfo:
        return cls(
            track_type=TrackType(str(value["track_type"])),
            index=int(value["index"]),
            name=str(value.get("name") or ""),
            subtype=_optional_str(value.get("subtype")),
            enabled=_optional_bool(value.get("enabled")),
            locked=_optional_bool(value.get("locked")),
        )


@dataclass(frozen=True, slots=True)
class ClipInfo:
    """One timeline item with the evidence needed to locate its source media."""

    item_id: str
    track_type: TrackType
    track_index: int
    item_index: int
    name: str
    item_type: str
    start_frame: int
    end_frame: int
    source_start_frame: int | None = None
    source_end_frame: int | None = None
    source_start_seconds: float | None = None
    source_end_seconds: float | None = None
    left_offset_frames: float | None = None
    right_offset_frames: float | None = None
    media_pool_item_id: str | None = None
    file_path: str | None = None
    media_fps: float | None = None
    enabled: bool = True
    linked_item_ids: tuple[str, ...] = ()
    audio_channel_mapping: str | None = None
    fusion_comp_count: int = 0
    speed_percent: float | None = None
    subframe_start: float | None = None
    subframe_end: float | None = None

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            raise LayoutError("item_id must not be empty")
        if self.track_index < 1 or self.item_index < 1:
            raise LayoutError("track and item indices must be at least 1")
        if self.end_frame <= self.start_frame:
            raise LayoutError(f"clip {self.item_id} has an empty or inverted range")

    @property
    def track_key(self) -> str:
        return track_key(self.track_type, self.track_index)

    @property
    def duration_frames(self) -> int:
        return self.end_frame - self.start_frame

    @property
    def has_source_range(self) -> bool:
        return (
            self.source_start_frame is not None
            and self.source_end_frame is not None
            and self.source_end_frame > self.source_start_frame
        )

    @property
    def source_ratio(self) -> float | None:
        """Source frames consumed per timeline frame (1.0 for normal speed)."""

        if not self.has_source_range:
            return None
        assert self.source_start_frame is not None and self.source_end_frame is not None
        return (self.source_end_frame - self.source_start_frame) / self.duration_frames

    @property
    def is_unit_speed(self) -> bool:
        ratio = self.source_ratio
        if ratio is None:
            return False
        speed_ok = self.speed_percent is None or abs(self.speed_percent - 100.0) < 0.01
        if not speed_ok:
            return False
        if abs(ratio - 1.0) <= UNIT_RATIO_TOLERANCE:
            return True
        # Short native clips amplify a one-frame getter truncation into a false
        # speed change. Both independent source times and explicit 100% are needed.
        left = self.left_offset_frames
        if (
            self.speed_percent is None
            or left is None
            or not float(left).is_integer()
            or self.media_fps is None
            or self.media_fps <= 0
            or self.source_start_seconds is None
            or self.source_end_seconds is None
            or self.source_start_frame is None
            or self.source_end_frame is None
        ):
            return False
        end = int(left) + self.duration_frames
        return (
            abs(self.source_start_frame - left) <= 1
            and abs(self.source_end_frame - end) <= 1
            and source_time_matches_frame(self.source_start_seconds, int(left), self.media_fps)
            and source_time_matches_frame(self.source_end_seconds, end, self.media_fps)
        )

    @property
    def is_rebuildable(self) -> bool:
        return (
            self.item_type in REBUILDABLE_ITEM_TYPES
            and self.media_pool_item_id is not None
            and self.has_source_range
        )

    def source_frame_at(self, timeline_frame: int, *, timeline_fps: float | None = None) -> int:
        """Map a timeline frame inside (or at the end of) this clip to a source frame."""

        if not self.has_source_range:
            raise LayoutError(f"clip {self.item_id} has no source range")
        if not self.start_frame <= timeline_frame <= self.end_frame:
            raise LayoutError(f"frame {timeline_frame} is outside clip {self.item_id}")
        assert self.source_start_frame is not None
        offset = timeline_frame - self.start_frame
        if self.is_unit_speed:
            origin = self.source_start_frame
            left = self.left_offset_frames
            if (
                timeline_fps is not None
                and self.media_fps is not None
                and abs(timeline_fps - self.media_fps) < 0.001
                and left is not None
                and left >= 0
                and float(left).is_integer()
                and abs(left - origin) <= 1
                and self.source_start_seconds is not None
                and source_time_matches_frame(self.source_start_seconds, int(left), self.media_fps)
            ):
                origin = int(left)
            return origin + offset
        ratio = self.source_ratio
        assert ratio is not None
        return self.source_start_frame + round(offset * ratio)

    def source_channel_indices(self) -> tuple[int, ...] | None:
        """1-based physical source channels routed to this timeline item, if known."""

        if not self.audio_channel_mapping:
            return None
        try:
            value = json.loads(self.audio_channel_mapping)
        except (TypeError, ValueError):
            return None
        if not isinstance(value, dict):
            return None
        mapping = value.get("track_mapping")
        if not isinstance(mapping, dict) or not mapping:
            return None
        first_key = sorted(mapping, key=lambda item: str(item))[0]
        track = mapping[first_key]
        if not isinstance(track, dict):
            return None
        channels = track.get("channel_idx")
        if not isinstance(channels, list):
            return None
        try:
            parsed = tuple(int(item) for item in channels)
        except (TypeError, ValueError):
            return None
        if track.get("mute") is True:
            return ()
        return tuple(item for item in parsed if item > 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "track_type": self.track_type.value,
            "track_index": self.track_index,
            "item_index": self.item_index,
            "name": self.name,
            "item_type": self.item_type,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "source_start_frame": self.source_start_frame,
            "source_end_frame": self.source_end_frame,
            "source_start_seconds": self.source_start_seconds,
            "source_end_seconds": self.source_end_seconds,
            "left_offset_frames": self.left_offset_frames,
            "right_offset_frames": self.right_offset_frames,
            "media_pool_item_id": self.media_pool_item_id,
            "file_path": self.file_path,
            "media_fps": self.media_fps,
            "enabled": self.enabled,
            "linked_item_ids": list(self.linked_item_ids),
            "audio_channel_mapping": self.audio_channel_mapping,
            "fusion_comp_count": self.fusion_comp_count,
            "speed_percent": self.speed_percent,
            "subframe_start": self.subframe_start,
            "subframe_end": self.subframe_end,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ClipInfo:
        linked = value.get("linked_item_ids") or ()
        if not isinstance(linked, list | tuple):
            linked = ()
        return cls(
            item_id=str(value["item_id"]),
            track_type=TrackType(str(value["track_type"])),
            track_index=int(value["track_index"]),
            item_index=int(value["item_index"]),
            name=str(value.get("name") or ""),
            item_type=str(value.get("item_type") or "unknown").casefold(),
            start_frame=int(value["start_frame"]),
            end_frame=int(value["end_frame"]),
            source_start_frame=_optional_int(value.get("source_start_frame")),
            source_end_frame=_optional_int(value.get("source_end_frame")),
            source_start_seconds=_optional_float(value.get("source_start_seconds")),
            source_end_seconds=_optional_float(value.get("source_end_seconds")),
            left_offset_frames=_optional_float(value.get("left_offset_frames")),
            right_offset_frames=_optional_float(value.get("right_offset_frames")),
            media_pool_item_id=_optional_str(value.get("media_pool_item_id")),
            file_path=_optional_str(value.get("file_path")),
            media_fps=_optional_float(value.get("media_fps")),
            enabled=value.get("enabled") is not False,
            linked_item_ids=tuple(str(item) for item in linked if item not in (None, "")),
            audio_channel_mapping=_optional_str(value.get("audio_channel_mapping")),
            fusion_comp_count=max(0, int(value.get("fusion_comp_count") or 0)),
            speed_percent=_optional_float(value.get("speed_percent")),
            subframe_start=_optional_float(value.get("subframe_start")),
            subframe_end=_optional_float(value.get("subframe_end")),
        )


@dataclass(frozen=True, slots=True)
class TimelineLayout:
    project_name: str
    timeline_name: str
    timeline_id: str | None
    fps: float
    start_frame: int
    end_frame: int
    start_timecode: str
    drop_frame: bool
    tracks: tuple[TrackInfo, ...]
    clips: tuple[ClipInfo, ...]
    resolve_version: str | None = None
    captured_at: str | None = None
    capture_warnings: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        if not self.project_name.strip() or not self.timeline_name.strip():
            raise LayoutError("project and timeline names are required")
        if self.fps <= 0:
            raise LayoutError("fps must be positive")
        if self.end_frame <= self.start_frame:
            raise LayoutError("timeline range is empty")
        keys = [track.key for track in self.tracks]
        if len(keys) != len(set(keys)):
            raise LayoutError("duplicate track keys")
        ids = [clip.item_id for clip in self.clips]
        if len(ids) != len(set(ids)):
            raise LayoutError("duplicate clip ids")

    @property
    def duration_frames(self) -> int:
        return self.end_frame - self.start_frame

    def track(self, track_type: TrackType, index: int) -> TrackInfo | None:
        for item in self.tracks:
            if item.track_type == track_type and item.index == index:
                return item
        return None

    def tracks_of(self, track_type: TrackType) -> tuple[TrackInfo, ...]:
        return tuple(
            sorted(
                (item for item in self.tracks if item.track_type == track_type),
                key=lambda item: item.index,
            )
        )

    def clips_in_track(self, track_type: TrackType, index: int) -> tuple[ClipInfo, ...]:
        return tuple(
            sorted(
                (
                    clip
                    for clip in self.clips
                    if clip.track_type == track_type and clip.track_index == index
                ),
                key=lambda clip: (clip.start_frame, clip.item_index),
            )
        )

    def clip_by_id(self, item_id: str) -> ClipInfo | None:
        for clip in self.clips:
            if clip.item_id == item_id:
                return clip
        return None

    def gaps(self, track_type: TrackType, index: int) -> tuple[tuple[int, int], ...]:
        """Empty ranges of one track inside the timeline bounds."""

        cursor = self.start_frame
        result: list[tuple[int, int]] = []
        for clip in self.clips_in_track(track_type, index):
            if clip.start_frame > cursor:
                result.append((cursor, clip.start_frame))
            cursor = max(cursor, clip.end_frame)
        if cursor < self.end_frame:
            result.append((cursor, self.end_frame))
        return tuple(result)

    def validate(self) -> tuple[str, ...]:
        """Return structural problems in Portuguese; empty means consistent."""

        problems: list[str] = []
        for track in self.tracks:
            previous: ClipInfo | None = None
            for clip in self.clips_in_track(track.track_type, track.index):
                if clip.start_frame < self.start_frame or clip.end_frame > self.end_frame:
                    problems.append(
                        f"O clipe {clip.name or clip.item_id} em {clip.track_key} "
                        "está fora dos limites da timeline."
                    )
                if previous is not None and clip.start_frame < previous.end_frame:
                    problems.append(
                        f"Os clipes {previous.name or previous.item_id} e "
                        f"{clip.name or clip.item_id} se sobrepõem em {clip.track_key}."
                    )
                previous = clip
        known = {track.key for track in self.tracks}
        for clip in self.clips:
            if clip.track_key not in known:
                problems.append(
                    f"O clipe {clip.item_id} referencia a faixa ausente {clip.track_key}."
                )
        return tuple(problems)

    @property
    def fingerprint(self) -> str:
        payload = {
            "project": self.project_name,
            "timeline": self.timeline_name,
            "timeline_id": self.timeline_id,
            "fps": self.fps,
            "start": self.start_frame,
            "end": self.end_frame,
            "tracks": [track.to_dict() for track in sorted(self.tracks, key=lambda t: t.key)],
            "clips": [
                [
                    clip.item_id,
                    clip.track_key,
                    clip.start_frame,
                    clip.end_frame,
                    clip.source_start_frame,
                    clip.source_end_frame,
                    clip.media_pool_item_id,
                    clip.file_path,
                    clip.enabled,
                ]
                for clip in sorted(self.clips, key=lambda c: (c.track_key, c.start_frame))
            ],
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LAYOUT_SCHEMA_VERSION,
            "project_name": self.project_name,
            "timeline_name": self.timeline_name,
            "timeline_id": self.timeline_id,
            "fps": self.fps,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "start_timecode": self.start_timecode,
            "drop_frame": self.drop_frame,
            "tracks": [track.to_dict() for track in self.tracks],
            "clips": [clip.to_dict() for clip in self.clips],
            "resolve_version": self.resolve_version,
            "captured_at": self.captured_at,
            "capture_warnings": list(self.capture_warnings),
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> TimelineLayout:
        try:
            return cls(
                project_name=str(value["project_name"]),
                timeline_name=str(value["timeline_name"]),
                timeline_id=_optional_str(value.get("timeline_id")),
                fps=float(value["fps"]),
                start_frame=int(value["start_frame"]),
                end_frame=int(value["end_frame"]),
                start_timecode=str(value.get("start_timecode") or ""),
                drop_frame=bool(value.get("drop_frame", False)),
                tracks=tuple(
                    TrackInfo.from_dict(item)
                    for item in value.get("tracks", ())
                    if isinstance(item, dict)
                ),
                clips=tuple(
                    ClipInfo.from_dict(item)
                    for item in value.get("clips", ())
                    if isinstance(item, dict)
                ),
                resolve_version=_optional_str(value.get("resolve_version")),
                captured_at=_optional_str(value.get("captured_at")),
                capture_warnings=tuple(str(item) for item in value.get("capture_warnings", ())),
            )
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, LayoutError):
                raise
            raise LayoutError(f"layout inválido: {exc}") from exc

    @classmethod
    def from_internal_context(cls, context: dict[str, Any]) -> TimelineLayout:
        """Build from the internal host context (schema 3 with a ``layout`` object)."""

        raw = context.get("layout")
        if not isinstance(raw, dict):
            raise LayoutError(
                "O contexto não contém os clipes da timeline. Execute "
                "'O EDITOR' novamente com a versão atual dos scripts."
            )
        start_timecode = str(context.get("start_timecode") or "")
        merged = {
            "project_name": context.get("project_name"),
            "timeline_name": context.get("timeline_name"),
            "timeline_id": context.get("timeline_id"),
            "fps": context.get("fps"),
            "start_frame": context.get("start_frame"),
            "end_frame": context.get("end_frame"),
            "start_timecode": start_timecode,
            "drop_frame": ";" in start_timecode or bool(raw.get("drop_frame")),
            "tracks": raw.get("tracks", []),
            "clips": raw.get("clips", []),
            "resolve_version": context.get("resolve_version"),
            "captured_at": context.get("timestamp"),
            "capture_warnings": raw.get("warnings", []),
        }
        return cls.from_dict(merged)


def track_key(track_type: TrackType, index: int) -> str:
    prefix = {TrackType.VIDEO: "V", TrackType.AUDIO: "A", TrackType.SUBTITLE: "S"}[track_type]
    return f"{prefix}{index}"


def parse_track_key(value: str) -> tuple[TrackType, int]:
    text = value.strip().upper()
    mapping = {"V": TrackType.VIDEO, "A": TrackType.AUDIO, "S": TrackType.SUBTITLE}
    if len(text) < 2 or text[0] not in mapping or not text[1:].isdigit():
        raise LayoutError(f"faixa inválida: {value}")
    index = int(text[1:])
    if index < 1:
        raise LayoutError(f"faixa inválida: {value}")
    return mapping[text[0]], index


def _optional_str(value: Any) -> str | None:
    if value is None or value == "" or isinstance(value, dict | list):
        return None
    return str(value)


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "" or isinstance(value, bool | dict | list):
        return None
    try:
        return round(float(value))
    except (TypeError, ValueError):
        return None


def _optional_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool | dict | list):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
