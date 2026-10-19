"""Schema for safe voice-audio export requests and responses."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from o_editor.domain.voice_tracks import SelectedVoiceTrack
from o_editor.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class VoiceAudioExportRequest:
    request_id: str
    project: str
    timeline: str
    timeline_fingerprint: str
    selected_tracks: tuple[SelectedVoiceTrack, ...]
    output_path: Path
    sample_rate: int = 48_000
    action: str = "export_voice_audio"
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not self.request_id or not self.project or not self.timeline:
            raise ValueError("voice export request identity is incomplete")
        if not self.selected_tracks:
            raise ValueError("voice export request requires selected tracks")
        if self.sample_rate not in {16_000, 48_000}:
            raise ValueError("voice export sample rate must be 16 or 48 kHz")

    @classmethod
    def create(
        cls,
        *,
        project: str,
        timeline: str,
        timeline_fingerprint: str,
        selected_tracks: tuple[SelectedVoiceTrack, ...],
        output_path: Path,
        sample_rate: int = 48_000,
    ) -> VoiceAudioExportRequest:
        return cls(
            request_id=str(uuid.uuid4()),
            project=project,
            timeline=timeline,
            timeline_fingerprint=timeline_fingerprint,
            selected_tracks=selected_tracks,
            output_path=output_path,
            sample_rate=sample_rate,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "action": self.action,
            "request_id": self.request_id,
            "project": self.project,
            "timeline": self.timeline,
            "timeline_fingerprint": self.timeline_fingerprint,
            "selected_tracks": [item.to_dict() for item in self.selected_tracks],
            "output_path": str(self.output_path),
            "audio_settings": {"format": "wav", "sample_rate": self.sample_rate},
        }


@dataclass(frozen=True, slots=True)
class VoiceAudioExportResponse:
    status: str
    output_path: Path | None
    duration_seconds: float | None
    sample_rate: int | None
    channels: int | None
    backend: str
    restoration_verified: bool
    message: str

    def __post_init__(self) -> None:
        if self.status not in {"SUCCESS", "FAILED", "UNSUPPORTED", "CANCELLED"}:
            raise ValueError("invalid voice export response status")
        if self.status == "SUCCESS" and self.output_path is None:
            raise ValueError("successful voice export requires an output path")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "output_path": str(self.output_path) if self.output_path else None,
            "duration_seconds": self.duration_seconds,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "backend": self.backend,
            "restoration_verified": self.restoration_verified,
            "message": self.message,
        }


def save_voice_audio_request(request: VoiceAudioExportRequest, root: Path | None = None) -> Path:
    directory = root or _default_request_root()
    path = directory / f"voice-export-request-{request.request_id}.json"
    _write_atomic(path, request.to_dict())
    return path


def _default_request_root() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise ConfigurationError("APPDATA não está disponível para a request de áudio.")
    return Path(appdata) / "O Editor" / "requests"


def _write_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix="voice-request-", suffix=".tmp", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ConfigurationError("Não foi possível salvar a request de áudio de voz.") from exc
