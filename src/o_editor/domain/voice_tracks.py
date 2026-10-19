"""Pure contracts and scoring for timeline voice-track selection."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from typing import Any

from o_editor.domain.enums import ChannelMode

VOICE_TERMS = (
    "voz",
    "voice",
    "dialog",
    "dialogue",
    "fala",
    "mic",
    "microfone",
    "lapela",
    "lavalier",
    "boom",
    "pablo",
    "host",
    "guest",
    "entrevista",
)
NON_VOICE_TERMS = (
    "music",
    "musica",
    "sfx",
    "efeitos",
    "ambiente",
    "room",
    "master",
    "mix",
    "soundtrack",
)


@dataclass(frozen=True, slots=True)
class AudioTrackSnapshot:
    """Read-only metadata for one audio track in the active timeline."""

    index: int
    label: str
    name: str
    track_type: str = "audio"
    audio_type: str = "unknown"
    enabled: bool | None = None
    muted: bool | None = None
    locked: bool | None = None
    item_count: int = 0

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError("audio track index must be at least 1")
        if self.label != f"A{self.index}":
            raise ValueError("audio track label must match its index")
        if self.track_type != "audio":
            raise ValueError("voice selection only accepts audio tracks")
        if self.audio_type not in {"mono", "stereo", "adaptive", "unknown"}:
            raise ValueError("unsupported audio track type")
        if self.item_count < 0:
            raise ValueError("audio track item_count must be non-negative")

    @property
    def display_name(self) -> str:
        return f"{self.label} — {self.name}" if self.name else self.label

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "label": self.label,
            "name": self.name,
            "track_type": self.track_type,
            "audio_type": self.audio_type,
            "enabled": self.enabled,
            "muted": self.muted,
            "locked": self.locked,
            "item_count": self.item_count,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> AudioTrackSnapshot:
        index = int(value["index"])
        audio_type = str(value.get("audio_type") or "unknown").casefold()
        if audio_type not in {"mono", "stereo", "adaptive"}:
            audio_type = "unknown"
        return cls(
            index=index,
            label=str(value.get("label") or f"A{index}"),
            name=str(value.get("name") or ""),
            track_type=str(value.get("track_type") or "audio"),
            audio_type=audio_type,
            enabled=_optional_bool(value.get("enabled")),
            muted=_optional_bool(value.get("muted")),
            locked=_optional_bool(value.get("locked")),
            item_count=max(0, int(value.get("item_count") or 0)),
        )


@dataclass(frozen=True, slots=True)
class SelectedVoiceTrack:
    """User-confirmed voice source and optional stereo channel policy."""

    index: int
    name: str
    channel_mode: ChannelMode = ChannelMode.BOTH

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError("selected voice track index must be at least 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "name": self.name,
            "channel_mode": self.channel_mode.value,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SelectedVoiceTrack:
        return cls(
            index=int(value["index"]),
            name=str(value.get("name") or ""),
            channel_mode=ChannelMode(str(value.get("channel_mode") or "both")),
        )


def score_voice_track(track: AudioTrackSnapshot) -> int:
    normalized = _normalize(track.name)
    positive = sum(3 for term in VOICE_TERMS if term in normalized)
    negative = sum(4 for term in NON_VOICE_TERMS if term in normalized)
    if track.item_count == 0:
        negative += 2
    if track.enabled is False or track.muted is True:
        negative += 1
    return positive - negative


def suggest_voice_tracks(tracks: tuple[AudioTrackSnapshot, ...]) -> tuple[int, ...]:
    """Return clear name-based candidates without mutating user selection."""

    scored = tuple((track.index, score_voice_track(track)) for track in tracks)
    return tuple(index for index, score in scored if score >= 3)


def validate_voice_selection(
    tracks: tuple[AudioTrackSnapshot, ...],
    selected: tuple[SelectedVoiceTrack, ...],
) -> tuple[tuple[SelectedVoiceTrack, ...], tuple[str, ...]]:
    available = {track.index: track for track in tracks}
    valid: list[SelectedVoiceTrack] = []
    warnings: list[str] = []
    seen: set[int] = set()
    for item in selected:
        track = available.get(item.index)
        if track is None:
            warnings.append(f"A faixa A{item.index} selecionada não existe mais.")
            continue
        if item.index in seen:
            continue
        seen.add(item.index)
        if item.name and track.name and item.name != track.name:
            warnings.append(f"A faixa A{item.index} mudou de nome: {item.name} → {track.name}.")
        mode = item.channel_mode
        if track.audio_type == "mono":
            mode = ChannelMode.MONO
        elif track.audio_type != "stereo" and mode in {ChannelMode.LEFT, ChannelMode.RIGHT}:
            mode = ChannelMode.BOTH
            warnings.append(
                f"A seleção L/R de A{item.index} foi redefinida para Ambos: tipo não confirmado."
            )
        valid.append(SelectedVoiceTrack(item.index, track.name, mode))
    return tuple(valid), tuple(warnings)


def voice_audio_cache_key(
    *,
    project: str,
    timeline: str,
    timeline_fingerprint: str,
    selected_voice_tracks: tuple[SelectedVoiceTrack, ...],
    sample_rate: int,
    export_backend: str,
    app_version: str,
) -> str:
    payload = {
        "project": project,
        "timeline": timeline,
        "timeline_fingerprint": timeline_fingerprint,
        "selected_voice_tracks": [item.to_dict() for item in selected_voice_tracks],
        "sample_rate": sample_rate,
        "export_backend": export_backend,
        "app_version": app_version,
    }
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None
