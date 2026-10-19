"""Domain enumerations."""

from __future__ import annotations

from enum import StrEnum


class TrackType(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"
    SUBTITLE = "subtitle"


class ChannelMode(StrEnum):
    BOTH = "both"
    LEFT = "left"
    RIGHT = "right"
    MONO = "mono"


class SuggestionKind(StrEnum):
    ZOOM = "zoom"
    TEXT = "text"


class ZoomSubtype(StrEnum):
    PUSH_IN = "push_in"
    PUSH_AND_RETURN = "push_and_return"
    PUNCH_IN = "punch_in"


class TextSubtype(StrEnum):
    KEYWORD = "keyword"
    NUMBER = "number"
    DATE = "date"
    NAME = "name"
    CONCLUSION = "conclusion"
    CONTRAST = "contrast"
    CALLOUT = "callout"


class SuggestionStatus(StrEnum):
    PENDING = "PENDING"
    CONFLICT = "CONFLICT"
    APPLIED = "APPLIED"
    UNAPPLIED = "UNAPPLIED"
    SKIPPED = "SKIPPED"


class OperationStatus(StrEnum):
    PENDING = "PENDING"
    APPLIED = "APPLIED"
    SKIPPED = "SKIPPED"
    UNSUPPORTED = "UNSUPPORTED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class CapabilityStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNVERIFIED = "UNVERIFIED"
    FAILED = "FAILED"


class AppState(StrEnum):
    IDLE = "IDLE"
    CONNECTING = "CONNECTING"
    READY = "READY"
    ANALYZING = "ANALYZING"
    TRANSCRIBING = "TRANSCRIBING"
    GENERATING_SUGGESTIONS = "GENERATING_SUGGESTIONS"
    REVIEWING = "REVIEWING"
    VALIDATING = "VALIDATING"
    APPLYING = "APPLYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
