"""Typed and serializable domain contracts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar, Self

from o_editor.domain.enums import (
    CapabilityStatus,
    OperationStatus,
    SuggestionKind,
    SuggestionStatus,
    TextSubtype,
    TrackType,
    ZoomSubtype,
)
from o_editor.domain.validation import (
    require_frame_range,
    require_non_empty,
    require_unique,
    require_unit_interval,
)
from o_editor.domain.voice_tracks import AudioTrackSnapshot

SCHEMA_VERSION = "1.0"
JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]


def _to_json_value(value: Any) -> JsonValue:
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple | list):
        return [_to_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if is_dataclass(value):
        return {
            item.name: _to_json_value(getattr(value, item.name))
            for item in fields(value)
            if not item.name.startswith("_")
        }
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        _to_json_value(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def stable_id(prefix: str, value: Any, length: int = 20) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


class JsonModel:
    """Small JSON contract shared by domain dataclasses."""

    schema_version: ClassVar[str] = SCHEMA_VERSION

    def to_dict(self) -> dict[str, JsonValue]:
        value = _to_json_value(self)
        if not isinstance(value, dict):
            raise TypeError("JSON model must serialize to an object")
        return {"schema_version": self.schema_version, **value}

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent, sort_keys=True)


@dataclass(frozen=True, slots=True)
class TimelineItemSnapshot(JsonModel):
    id: str
    track_type: TrackType
    track_index: int
    start_frame: int
    end_frame: int
    source_start_frame: int
    source_end_frame: int
    name: str
    media_id: str | None = None
    source_path: str | None = None
    enabled: bool = True
    fusion_comp_count: int = 0
    is_multicam: bool = False
    has_transition_before: bool = False
    has_transition_after: bool = False
    properties: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        require_non_empty(self.id, "id")
        require_non_empty(self.name, "name")
        require_frame_range(self.start_frame, self.end_frame)
        if self.track_index < 1:
            raise ValueError("track_index must be at least 1")
        if self.source_end_frame < self.source_start_frame:
            raise ValueError("source_end_frame must not precede source_start_frame")
        if self.fusion_comp_count < 0:
            raise ValueError("fusion_comp_count must be non-negative")

    @classmethod
    def create(
        cls,
        *,
        track_type: TrackType,
        track_index: int,
        start_frame: int,
        end_frame: int,
        source_start_frame: int,
        source_end_frame: int,
        name: str,
        media_id: str | None = None,
        source_path: str | None = None,
        **flags: Any,
    ) -> Self:
        identity = {
            "track_type": track_type,
            "track_index": track_index,
            "start_frame": start_frame,
            "end_frame": end_frame,
            "source_start_frame": source_start_frame,
            "source_end_frame": source_end_frame,
            "name": name,
            "media_id": media_id,
            "source_path": source_path,
        }
        return cls(
            id=stable_id("clip", identity),
            track_type=track_type,
            track_index=track_index,
            start_frame=start_frame,
            end_frame=end_frame,
            source_start_frame=source_start_frame,
            source_end_frame=source_end_frame,
            name=name,
            media_id=media_id,
            source_path=source_path,
            **flags,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        values = dict(data)
        values.pop("schema_version", None)
        values["track_type"] = TrackType(values["track_type"])
        values["properties"] = tuple(tuple(item) for item in values.get("properties", ()))
        return cls(**values)


@dataclass(frozen=True, slots=True)
class TimelineSnapshot(JsonModel):
    project_name: str
    timeline_name: str
    timeline_id: str | None
    fps: float
    drop_frame: bool
    start_frame: int
    end_frame: int
    video_track_count: int
    audio_track_count: int
    items: tuple[TimelineItemSnapshot, ...]
    audio_tracks: tuple[AudioTrackSnapshot, ...] = ()

    def __post_init__(self) -> None:
        require_non_empty(self.project_name, "project_name")
        require_non_empty(self.timeline_name, "timeline_name")
        require_frame_range(self.start_frame, self.end_frame)
        if self.fps <= 0:
            raise ValueError("fps must be positive")
        if self.video_track_count < 0 or self.audio_track_count < 0:
            raise ValueError("track counts must be non-negative")
        require_unique((item.id for item in self.items), "items")
        require_unique((str(track.index) for track in self.audio_tracks), "audio_tracks")
        if self.audio_tracks and len(self.audio_tracks) != self.audio_track_count:
            raise ValueError("audio_tracks must match audio_track_count")
        for item in self.items:
            if item.start_frame < self.start_frame or item.end_frame > self.end_frame:
                raise ValueError("timeline item is outside timeline bounds")

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(canonical_json(self._fingerprint_payload()).encode()).hexdigest()

    @property
    def duration_frames(self) -> int:
        return self.end_frame - self.start_frame

    def _fingerprint_payload(self) -> dict[str, JsonValue]:
        return {
            "project_name": self.project_name,
            "timeline_name": self.timeline_name,
            "timeline_id": self.timeline_id,
            "fps": self.fps,
            "drop_frame": self.drop_frame,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "video_track_count": self.video_track_count,
            "audio_track_count": self.audio_track_count,
            "items": [_to_json_value(item) for item in self.items],
            "audio_tracks": [_to_json_value(track) for track in self.audio_tracks],
        }

    def item_at(self, frame: int) -> TimelineItemSnapshot | None:
        return next(
            (
                item
                for item in self.items
                if item.track_type is TrackType.VIDEO
                and item.enabled
                and item.start_frame <= frame < item.end_frame
            ),
            None,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        values = dict(data)
        values.pop("schema_version", None)
        values["items"] = tuple(TimelineItemSnapshot.from_dict(item) for item in values["items"])
        values["audio_tracks"] = tuple(
            AudioTrackSnapshot.from_dict(item) for item in values.get("audio_tracks", ())
        )
        return cls(**values)


@dataclass(frozen=True, slots=True)
class TranscriptWord(JsonModel):
    text: str
    start_frame: int
    end_frame: int
    probability: float | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.text, "text")
        require_frame_range(self.start_frame, self.end_frame)
        if self.probability is not None:
            require_unit_interval(self.probability, "probability")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        values = dict(data)
        values.pop("schema_version", None)
        return cls(**values)


@dataclass(frozen=True, slots=True)
class TranscriptSegment(JsonModel):
    id: str
    start_frame: int
    end_frame: int
    text: str
    words: tuple[TranscriptWord, ...] = ()
    pause_before_frames: int = 0

    def __post_init__(self) -> None:
        require_non_empty(self.id, "id")
        require_non_empty(self.text, "text")
        require_frame_range(self.start_frame, self.end_frame)
        if self.pause_before_frames < 0:
            raise ValueError("pause_before_frames must be non-negative")
        for word in self.words:
            if word.start_frame < self.start_frame or word.end_frame > self.end_frame:
                raise ValueError("word is outside segment bounds")

    @classmethod
    def create(
        cls,
        *,
        start_frame: int,
        end_frame: int,
        text: str,
        words: tuple[TranscriptWord, ...] = (),
        pause_before_frames: int = 0,
    ) -> Self:
        identity = {"start_frame": start_frame, "end_frame": end_frame, "text": text}
        return cls(
            id=stable_id("seg", identity),
            start_frame=start_frame,
            end_frame=end_frame,
            text=text,
            words=words,
            pause_before_frames=pause_before_frames,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        values = dict(data)
        values.pop("schema_version", None)
        values["words"] = tuple(TranscriptWord.from_dict(item) for item in values.get("words", ()))
        return cls(**values)


@dataclass(frozen=True, slots=True)
class Transcript(JsonModel):
    language: str
    fps: float
    timeline_start_frame: int
    segments: tuple[TranscriptSegment, ...]
    provider: str
    model: str

    def __post_init__(self) -> None:
        require_non_empty(self.language, "language")
        require_non_empty(self.provider, "provider")
        require_non_empty(self.model, "model")
        if self.fps <= 0:
            raise ValueError("fps must be positive")
        require_unique((segment.id for segment in self.segments), "segments")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        values = dict(data)
        values.pop("schema_version", None)
        values["segments"] = tuple(
            TranscriptSegment.from_dict(item) for item in values.get("segments", ())
        )
        return cls(**values)


@dataclass(frozen=True, slots=True)
class Suggestion(JsonModel):
    id: str
    kind: SuggestionKind
    subtype: str
    timeline_start_frame: int
    timeline_end_frame: int
    confidence: float
    importance: float
    reason_codes: tuple[str, ...]
    source_segment_ids: tuple[str, ...]
    clip_id: str | None = None
    clip_local_start_frame: int | None = None
    clip_local_end_frame: int | None = None
    parameters: tuple[tuple[str, JsonValue], ...] = ()
    approved: bool = False
    edited_by_user: bool = False
    status: SuggestionStatus = SuggestionStatus.PENDING
    conflict_reason: str | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.id, "id")
        require_non_empty(self.subtype, "subtype")
        require_frame_range(self.timeline_start_frame, self.timeline_end_frame)
        require_unit_interval(self.confidence, "confidence")
        require_unit_interval(self.importance, "importance")
        require_unique(self.reason_codes, "reason_codes")
        require_unique(self.source_segment_ids, "source_segment_ids")
        if (self.clip_local_start_frame is None) != (self.clip_local_end_frame is None):
            raise ValueError("clip local frame range must be complete")
        if (
            self.clip_local_start_frame is not None
            and self.clip_local_end_frame is not None
            and self.clip_local_end_frame <= self.clip_local_start_frame
        ):
            raise ValueError("clip local frame range is invalid")

    @property
    def parameter_map(self) -> dict[str, JsonValue]:
        return dict(self.parameters)

    def with_approval(self, approved: bool) -> Self:
        return replace(self, approved=approved)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Suggestion:
        values = dict(data)
        values.pop("schema_version", None)
        values["kind"] = SuggestionKind(values["kind"])
        values["status"] = SuggestionStatus(values.get("status", SuggestionStatus.PENDING))
        values["reason_codes"] = tuple(values.get("reason_codes", ()))
        values["source_segment_ids"] = tuple(values.get("source_segment_ids", ()))
        values["parameters"] = tuple(tuple(item) for item in values.get("parameters", ()))
        target: type[Suggestion]
        if values["kind"] is SuggestionKind.ZOOM:
            target = ZoomSuggestion
        elif values["kind"] is SuggestionKind.TEXT:
            target = TextSuggestion
        else:
            target = Suggestion
        return target(**values)


@dataclass(frozen=True, slots=True)
class ZoomSuggestion(Suggestion):
    def __post_init__(self) -> None:
        super(ZoomSuggestion, self).__post_init__()
        if self.kind is not SuggestionKind.ZOOM:
            raise ValueError("ZoomSuggestion kind must be zoom")
        ZoomSubtype(self.subtype)

    @classmethod
    def create(
        cls,
        *,
        subtype: ZoomSubtype,
        timeline_start_frame: int,
        timeline_end_frame: int,
        confidence: float,
        importance: float,
        reason_codes: tuple[str, ...],
        source_segment_ids: tuple[str, ...],
        clip_id: str,
        clip_local_start_frame: int,
        clip_local_end_frame: int,
        parameters: tuple[tuple[str, JsonValue], ...],
    ) -> Self:
        payload = {
            "kind": SuggestionKind.ZOOM,
            "subtype": subtype,
            "start": timeline_start_frame,
            "end": timeline_end_frame,
            "clip_id": clip_id,
            "segments": source_segment_ids,
        }
        return cls(
            id=stable_id("sug", payload),
            kind=SuggestionKind.ZOOM,
            subtype=subtype.value,
            timeline_start_frame=timeline_start_frame,
            timeline_end_frame=timeline_end_frame,
            confidence=confidence,
            importance=importance,
            reason_codes=reason_codes,
            source_segment_ids=source_segment_ids,
            clip_id=clip_id,
            clip_local_start_frame=clip_local_start_frame,
            clip_local_end_frame=clip_local_end_frame,
            parameters=parameters,
        )


@dataclass(frozen=True, slots=True)
class TextSuggestion(Suggestion):
    text: str = ""

    def __post_init__(self) -> None:
        super(TextSuggestion, self).__post_init__()
        if self.kind is not SuggestionKind.TEXT:
            raise ValueError("TextSuggestion kind must be text")
        TextSubtype(self.subtype)
        require_non_empty(self.text, "text")

    def with_text(self, text: str) -> Self:
        require_non_empty(text, "text")
        return replace(self, text=text, edited_by_user=True)

    @classmethod
    def create(
        cls,
        *,
        subtype: TextSubtype,
        timeline_start_frame: int,
        timeline_end_frame: int,
        confidence: float,
        importance: float,
        reason_codes: tuple[str, ...],
        source_segment_ids: tuple[str, ...],
        text: str,
        parameters: tuple[tuple[str, JsonValue], ...],
    ) -> Self:
        payload = {
            "kind": SuggestionKind.TEXT,
            "subtype": subtype,
            "start": timeline_start_frame,
            "end": timeline_end_frame,
            "text": text,
            "segments": source_segment_ids,
        }
        return cls(
            id=stable_id("sug", payload),
            kind=SuggestionKind.TEXT,
            subtype=subtype.value,
            timeline_start_frame=timeline_start_frame,
            timeline_end_frame=timeline_end_frame,
            confidence=confidence,
            importance=importance,
            reason_codes=reason_codes,
            source_segment_ids=source_segment_ids,
            text=text,
            parameters=parameters,
        )


@dataclass(frozen=True, slots=True)
class ApplicationOperation(JsonModel):
    id: str
    suggestion_id: str
    kind: SuggestionKind
    backend: str
    timeline_start_frame: int
    timeline_end_frame: int
    target_item_id: str | None
    parameters: tuple[tuple[str, JsonValue], ...]
    status: OperationStatus = OperationStatus.PENDING
    detail: str = ""
    verified: bool = False

    def __post_init__(self) -> None:
        require_non_empty(self.id, "id")
        require_non_empty(self.suggestion_id, "suggestion_id")
        require_non_empty(self.backend, "backend")
        require_frame_range(self.timeline_start_frame, self.timeline_end_frame)
        if self.status is OperationStatus.APPLIED and not self.verified:
            raise ValueError("an applied operation must be verified")

    def with_result(
        self,
        status: OperationStatus,
        *,
        detail: str,
        verified: bool = False,
    ) -> Self:
        return replace(self, status=status, detail=detail, verified=verified)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        values = dict(data)
        values.pop("schema_version", None)
        values["kind"] = SuggestionKind(values["kind"])
        values["status"] = OperationStatus(values.get("status", OperationStatus.PENDING))
        values["parameters"] = tuple(tuple(item) for item in values.get("parameters", ()))
        return cls(**values)


@dataclass(frozen=True, slots=True)
class ApplicationPlan(JsonModel):
    id: str
    analysis_id: str
    source_fingerprint: str
    source_timeline_name: str
    target_timeline_name: str
    dry_run: bool
    operations: tuple[ApplicationOperation, ...]
    created_at: str

    def __post_init__(self) -> None:
        require_non_empty(self.id, "id")
        require_non_empty(self.analysis_id, "analysis_id")
        require_non_empty(self.source_fingerprint, "source_fingerprint")
        require_non_empty(self.source_timeline_name, "source_timeline_name")
        require_non_empty(self.target_timeline_name, "target_timeline_name")
        require_unique((operation.id for operation in self.operations), "operations")

    @classmethod
    def create(
        cls,
        *,
        analysis_id: str,
        source_fingerprint: str,
        source_timeline_name: str,
        target_timeline_name: str,
        dry_run: bool,
        operations: tuple[ApplicationOperation, ...],
    ) -> Self:
        payload = {
            "analysis_id": analysis_id,
            "source_fingerprint": source_fingerprint,
            "target_timeline_name": target_timeline_name,
            "dry_run": dry_run,
            "operations": operations,
        }
        return cls(
            id=stable_id("plan", payload),
            analysis_id=analysis_id,
            source_fingerprint=source_fingerprint,
            source_timeline_name=source_timeline_name,
            target_timeline_name=target_timeline_name,
            dry_run=dry_run,
            operations=operations,
            created_at=datetime.now(UTC).isoformat(),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        values = dict(data)
        values.pop("schema_version", None)
        values["operations"] = tuple(
            ApplicationOperation.from_dict(item) for item in values.get("operations", ())
        )
        return cls(**values)


@dataclass(frozen=True, slots=True)
class CapabilityResult(JsonModel):
    name: str
    status: CapabilityStatus
    method: str | None
    return_value: JsonValue
    exception: str | None
    notes: str
    impact: str
    fallback: str

    def __post_init__(self) -> None:
        require_non_empty(self.name, "name")
        if self.status is CapabilityStatus.SUPPORTED and not self.method:
            raise ValueError("supported capability must record the executed method")
        if self.status is CapabilityStatus.FAILED and not self.exception:
            raise ValueError("failed capability must record an exception")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        values = dict(data)
        values.pop("schema_version", None)
        values["status"] = CapabilityStatus(values["status"])
        return cls(**values)


@dataclass(frozen=True, slots=True)
class ApplicationReport(JsonModel):
    analysis_id: str
    project_name: str
    source_timeline_name: str
    target_timeline_name: str | None
    resolve_version: str | None
    started_at: str
    finished_at: str
    operations: tuple[ApplicationOperation, ...]
    capabilities_used: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_non_empty(self.analysis_id, "analysis_id")
        require_non_empty(self.project_name, "project_name")
        require_non_empty(self.source_timeline_name, "source_timeline_name")

    @property
    def counts(self) -> dict[str, int]:
        return {
            status.value: sum(operation.status is status for operation in self.operations)
            for status in OperationStatus
        }
