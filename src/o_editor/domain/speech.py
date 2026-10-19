"""Speaker-attributed, multi-track transcript contracts (pure domain).

Each track is transcribed on its own; the participant is the *track name* captured at
transcription time and the binding to the timeline is ``track_index`` plus the absolute
frame range. Text may be corrected later without touching timing or identity.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Any

SESSION_SCHEMA_VERSION = 1
SEGMENT_ID_PATTERN = re.compile(r"^SEG_\d{4,6}$")


class SegmentState(StrEnum):
    KEEP = "KEEP"
    CUT = "CUT"


class SegmentFlag(StrEnum):
    OVERLAP = "SOBREPOSTO"
    BLEED = "VAZAMENTO"
    LOW_CONFIDENCE = "BAIXA_CONFIANCA"
    NON_SPEECH = "SOM"


@dataclass(frozen=True, slots=True)
class SpeechWord:
    text: str
    start_frame: int
    end_frame: int
    probability: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "probability": self.probability,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SpeechWord:
        probability = value.get("probability")
        return cls(
            text=str(value["text"]),
            start_frame=int(value["start_frame"]),
            end_frame=int(value["end_frame"]),
            probability=float(probability) if probability is not None else None,
        )


@dataclass(frozen=True, slots=True)
class RawSegment:
    """Transcriber output already converted to absolute timeline frames."""

    track_index: int
    start_frame: int
    end_frame: int
    text: str
    words: tuple[SpeechWord, ...] = ()
    confidence: float | None = None
    no_speech_prob: float | None = None
    energy_db: float | None = None


@dataclass(frozen=True, slots=True)
class SpeechSegment:
    segment_id: str
    track_index: int
    speaker: str
    start_frame: int
    end_frame: int
    text: str
    original_text: str
    words: tuple[SpeechWord, ...] = ()
    state: SegmentState = SegmentState.KEEP
    flags: frozenset[SegmentFlag] = field(default_factory=frozenset)
    confidence: float | None = None
    no_speech_prob: float | None = None
    energy_db: float | None = None
    related_segment_id: str | None = None

    def __post_init__(self) -> None:
        if not SEGMENT_ID_PATTERN.match(self.segment_id):
            raise ValueError(f"segment id inválido: {self.segment_id}")
        if self.track_index < 1:
            raise ValueError("track_index must be at least 1")
        if self.start_frame < 0 or self.end_frame <= self.start_frame:
            raise ValueError(f"intervalo inválido em {self.segment_id}")

    @property
    def track_key(self) -> str:
        return f"A{self.track_index}"

    @property
    def duration_frames(self) -> int:
        return self.end_frame - self.start_frame

    @property
    def is_bleed(self) -> bool:
        return SegmentFlag.BLEED in self.flags

    @property
    def protects_audio(self) -> bool:
        """Valid speech that must never be removed by automatic cuts."""

        return self.state == SegmentState.KEEP and not self.is_bleed

    @property
    def text_corrected(self) -> bool:
        return self.text != self.original_text

    def overlaps(self, other: SpeechSegment) -> bool:
        return self.start_frame < other.end_frame and other.start_frame < self.end_frame

    def with_state(self, state: SegmentState) -> SpeechSegment:
        return replace(self, state=state)

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "track_index": self.track_index,
            "speaker": self.speaker,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "text": self.text,
            "original_text": self.original_text,
            "words": [word.to_dict() for word in self.words],
            "state": self.state.value,
            "flags": sorted(flag.value for flag in self.flags),
            "confidence": self.confidence,
            "no_speech_prob": self.no_speech_prob,
            "energy_db": self.energy_db,
            "related_segment_id": self.related_segment_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SpeechSegment:
        return cls(
            segment_id=str(value["segment_id"]),
            track_index=int(value["track_index"]),
            speaker=str(value.get("speaker") or ""),
            start_frame=int(value["start_frame"]),
            end_frame=int(value["end_frame"]),
            text=str(value.get("text") or ""),
            original_text=str(value.get("original_text") or value.get("text") or ""),
            words=tuple(SpeechWord.from_dict(item) for item in value.get("words", ())),
            state=SegmentState(str(value.get("state") or "KEEP")),
            flags=frozenset(SegmentFlag(item) for item in value.get("flags", ())),
            confidence=_optional_float(value.get("confidence")),
            no_speech_prob=_optional_float(value.get("no_speech_prob")),
            energy_db=_optional_float(value.get("energy_db")),
            related_segment_id=value.get("related_segment_id") or None,
        )


@dataclass(frozen=True, slots=True)
class TranscribedTrack:
    track_index: int
    name: str
    channel_mode: str
    audio_cache_key: str | None = None
    segment_count: int = 0
    dropped_hallucinations: int = 0
    device: str | None = None
    warnings: tuple[str, ...] = ()
    signal_fingerprint: str | None = None

    @property
    def key(self) -> str:
        return f"A{self.track_index}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_index": self.track_index,
            "name": self.name,
            "channel_mode": self.channel_mode,
            "audio_cache_key": self.audio_cache_key,
            "segment_count": self.segment_count,
            "dropped_hallucinations": self.dropped_hallucinations,
            "device": self.device,
            "warnings": list(self.warnings),
            "signal_fingerprint": self.signal_fingerprint,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TranscribedTrack:
        return cls(
            track_index=int(value["track_index"]),
            name=str(value.get("name") or ""),
            channel_mode=str(value.get("channel_mode") or "both"),
            audio_cache_key=value.get("audio_cache_key") or None,
            segment_count=int(value.get("segment_count") or 0),
            dropped_hallucinations=int(value.get("dropped_hallucinations") or 0),
            device=value.get("device") or None,
            warnings=tuple(str(item) for item in value.get("warnings", ())),
            signal_fingerprint=str(value["signal_fingerprint"])
            if value.get("signal_fingerprint")
            else None,
        )


FrameRange = tuple[int, int]


@dataclass(frozen=True, slots=True)
class TranscriptSession:
    """Everything needed to export, re-import and cut without asking Resolve again."""

    session_id: str
    revision: int
    created_at: str
    updated_at: str
    project_name: str
    timeline_name: str
    timeline_id: str | None
    fps: float
    start_frame: int
    end_frame: int
    start_timecode: str
    drop_frame: bool
    layout_fingerprint: str
    layout: Mapping[str, Any]
    tracks: tuple[TranscribedTrack, ...]
    segments: tuple[SpeechSegment, ...]
    activity: Mapping[int, tuple[FrameRange, ...]] = field(default_factory=dict)
    language: str | None = None
    provider: str = ""
    model: str = ""
    warnings: tuple[str, ...] = ()
    exports: tuple[Mapping[str, Any], ...] = ()
    imports: tuple[Mapping[str, Any], ...] = ()
    pending_missing: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ids = [segment.segment_id for segment in self.segments]
        if len(ids) != len(set(ids)):
            raise ValueError("segment ids must be unique")
        if self.revision < 1:
            raise ValueError("revision must be at least 1")

    def segment(self, segment_id: str) -> SpeechSegment | None:
        for item in self.segments:
            if item.segment_id == segment_id:
                return item
        return None

    def segments_for_track(self, track_index: int) -> tuple[SpeechSegment, ...]:
        return tuple(item for item in self.segments if item.track_index == track_index)

    def speaker_name(self, track_index: int) -> str:
        for track in self.tracks:
            if track.track_index == track_index:
                return track.name or f"A{track_index}"
        return f"A{track_index}"

    def with_segments(
        self, segments: Iterable[SpeechSegment], *, updated_at: str
    ) -> TranscriptSession:
        return replace(self, segments=tuple(segments), updated_at=updated_at)

    def structure_checksum(self, segment_ids: Iterable[str] | None = None) -> str:
        """Hash of identity and timing only (text and state are editable)."""

        wanted = set(segment_ids) if segment_ids is not None else None
        rows = [
            [item.segment_id, item.track_index, item.start_frame, item.end_frame]
            for item in self.segments
            if wanted is None or item.segment_id in wanted
        ]
        payload = json.dumps(
            [self.session_id, self.revision, rows], separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SESSION_SCHEMA_VERSION,
            "session_id": self.session_id,
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "project_name": self.project_name,
            "timeline_name": self.timeline_name,
            "timeline_id": self.timeline_id,
            "fps": self.fps,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "start_timecode": self.start_timecode,
            "drop_frame": self.drop_frame,
            "layout_fingerprint": self.layout_fingerprint,
            "layout": dict(self.layout),
            "tracks": [track.to_dict() for track in self.tracks],
            "segments": [segment.to_dict() for segment in self.segments],
            "activity": {
                str(index): [list(item) for item in ranges]
                for index, ranges in sorted(self.activity.items())
            },
            "language": self.language,
            "provider": self.provider,
            "model": self.model,
            "warnings": list(self.warnings),
            "exports": [dict(item) for item in self.exports],
            "imports": [dict(item) for item in self.imports],
            "pending_missing": list(self.pending_missing),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TranscriptSession:
        if value.get("schema_version") != SESSION_SCHEMA_VERSION:
            raise ValueError("schema de sessão incompatível")
        activity_raw = value.get("activity") or {}
        activity: dict[int, tuple[FrameRange, ...]] = {}
        if isinstance(activity_raw, dict):
            for key, ranges in activity_raw.items():
                activity[int(key)] = tuple((int(item[0]), int(item[1])) for item in ranges)
        return cls(
            session_id=str(value["session_id"]),
            revision=int(value["revision"]),
            created_at=str(value["created_at"]),
            updated_at=str(value.get("updated_at") or value["created_at"]),
            project_name=str(value["project_name"]),
            timeline_name=str(value["timeline_name"]),
            timeline_id=value.get("timeline_id") or None,
            fps=float(value["fps"]),
            start_frame=int(value["start_frame"]),
            end_frame=int(value["end_frame"]),
            start_timecode=str(value.get("start_timecode") or ""),
            drop_frame=bool(value.get("drop_frame")),
            layout_fingerprint=str(value.get("layout_fingerprint") or ""),
            layout=dict(value.get("layout") or {}),
            tracks=tuple(TranscribedTrack.from_dict(item) for item in value.get("tracks", ())),
            segments=tuple(SpeechSegment.from_dict(item) for item in value.get("segments", ())),
            activity=activity,
            language=value.get("language") or None,
            provider=str(value.get("provider") or ""),
            model=str(value.get("model") or ""),
            warnings=tuple(str(item) for item in value.get("warnings", ())),
            exports=tuple(dict(item) for item in value.get("exports", ())),
            imports=tuple(dict(item) for item in value.get("imports", ())),
            pending_missing=tuple(str(item) for item in value.get("pending_missing", ())),
        )


# --------------------------------------------------------------------------- merging


NON_SPEECH_PATTERN = re.compile(
    r"^\s*[\[\(\uff08]?\s*(risos?|risadas?|aplausos?|música|musica|laughs?|laughter|"
    r"applause|music|tosse|suspiro)\s*[\]\)\uff09]?\s*[.!]*\s*$",
    re.IGNORECASE,
)


def build_segments(
    raw_segments: Iterable[RawSegment],
    speakers: Mapping[int, str],
    *,
    low_confidence_threshold: float = 0.45,
) -> tuple[SpeechSegment, ...]:
    """Sort chronologically across tracks and assign stable sequential identifiers."""

    ordered = sorted(
        (item for item in raw_segments if item.text.strip() and item.end_frame > item.start_frame),
        key=lambda item: (item.start_frame, item.track_index, item.end_frame),
    )
    width = max(4, len(str(len(ordered))))
    result: list[SpeechSegment] = []
    for number, item in enumerate(ordered, start=1):
        flags: set[SegmentFlag] = set()
        if item.confidence is not None and item.confidence < low_confidence_threshold:
            flags.add(SegmentFlag.LOW_CONFIDENCE)
        if NON_SPEECH_PATTERN.match(item.text):
            flags.add(SegmentFlag.NON_SPEECH)
        text = " ".join(item.text.split())
        result.append(
            SpeechSegment(
                segment_id=f"SEG_{number:0{width}d}",
                track_index=item.track_index,
                speaker=speakers.get(item.track_index, f"A{item.track_index}"),
                start_frame=item.start_frame,
                end_frame=item.end_frame,
                text=text,
                original_text=text,
                words=item.words,
                flags=frozenset(flags),
                confidence=item.confidence,
                no_speech_prob=item.no_speech_prob,
                energy_db=item.energy_db,
            )
        )
    return mark_overlaps(result)


def mark_overlaps(segments: Iterable[SpeechSegment]) -> tuple[SpeechSegment, ...]:
    """Flag segments that overlap valid speech on a *different* track."""

    items = list(segments)
    ordered = sorted(range(len(items)), key=lambda index: items[index].start_frame)
    overlapping: set[int] = set()
    active: list[int] = []
    for index in ordered:
        current = items[index]
        active = [other for other in active if items[other].end_frame > current.start_frame]
        for other in active:
            first, second = items[other], current
            if first.track_index == second.track_index:
                continue
            if first.is_bleed or second.is_bleed:
                continue
            overlapping.update((other, index))
        active.append(index)
    result: list[SpeechSegment] = []
    for index, item in enumerate(items):
        flags = set(item.flags)
        if index in overlapping:
            flags.add(SegmentFlag.OVERLAP)
        else:
            flags.discard(SegmentFlag.OVERLAP)
        result.append(replace(item, flags=frozenset(flags)))
    return tuple(result)


def detect_bleed(
    segments: Iterable[SpeechSegment],
    *,
    minimum_similarity: float = 0.6,
    minimum_overlap: float = 0.5,
    minimum_level_difference_db: float = 6.0,
    signal_fingerprints: Mapping[int, str] | None = None,
) -> tuple[tuple[SpeechSegment, ...], tuple[str, ...]]:
    """Flag duplicated transcriptions caused by microphone leakage.

    Similar overlapping text needs a clearly higher level. An exact whole-PCM
    identity can also prove duplication at equal levels, retaining the first
    track. It must cover the entire copied ASR segment before removing its global
    protection; otherwise its speech tail remains protected. Without either kind
    of evidence both voices remain active.
    """

    items = sorted(segments, key=lambda item: (item.start_frame, item.track_index))
    flagged: dict[int, str] = {}
    notes: list[str] = []
    for left_index, left in enumerate(items):
        for right_index in range(left_index + 1, len(items)):
            right = items[right_index]
            if right.start_frame >= left.end_frame:
                break
            if left.track_index == right.track_index or not left.overlaps(right):
                continue
            shared = min(left.end_frame, right.end_frame) - max(left.start_frame, right.start_frame)
            shorter = min(left.duration_frames, right.duration_frames)
            if shorter <= 0 or shared / shorter < minimum_overlap:
                continue
            fingerprints = signal_fingerprints or {}
            fingerprint = fingerprints.get(left.track_index)
            identical = bool(
                fingerprint
                and re.fullmatch(r"[0-9a-f]{64}", fingerprint)
                and fingerprint == fingerprints.get(right.track_index)
            )
            if identical:
                # The complete aligned PCM is identical, even if ASR split/worded it
                # differently. Keep the first selected track deterministically.
                duplicate, source = (
                    (right_index, left)
                    if left.track_index < right.track_index
                    else (left_index, right)
                )
                copied = items[duplicate]
                # A whole BLEED segment stops protecting global cuts. Leave an
                # unmatched ASR tail as speech; local gating can still mute the
                # proven overlapping part without deleting that editorial time.
                if (
                    source.start_frame <= copied.start_frame
                    and source.end_frame >= copied.end_frame
                ):
                    flagged[duplicate] = source.segment_id
                continue
            if text_similarity(left.text, right.text) < minimum_similarity:
                continue
            if left.energy_db is None or right.energy_db is None:
                notes.append(
                    f"{left.segment_id} e {right.segment_id} têm texto semelhante, mas sem "
                    "nível de sinal para confirmar vazamento; ambos foram mantidos."
                )
                continue
            difference = left.energy_db - right.energy_db
            if abs(difference) < minimum_level_difference_db:
                notes.append(
                    f"{left.segment_id} e {right.segment_id} parecem a mesma fala com níveis "
                    "próximos; verifique manualmente."
                )
                continue
            if difference > 0:
                flagged[right_index] = left.segment_id
            else:
                flagged[left_index] = right.segment_id
    result = []
    for index, item in enumerate(items):
        if index in flagged:
            result.append(
                replace(
                    item,
                    flags=frozenset({*item.flags, SegmentFlag.BLEED}),
                    related_segment_id=flagged[index],
                )
            )
        else:
            result.append(item)
    return mark_overlaps(result), tuple(notes)


def text_similarity(left: str, right: str) -> float:
    a, b = normalize_text(left), normalize_text(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    letters = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^\w\s]", " ", letters).split())


def chronological(segments: Iterable[SpeechSegment]) -> tuple[SpeechSegment, ...]:
    return tuple(sorted(segments, key=lambda item: (item.start_frame, item.track_index)))


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
