"""Validated hand-off from an internal Resolve script to the external UI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from o_editor.domain.voice_tracks import AudioTrackSnapshot
from o_editor.errors import ConfigurationError
from o_editor.infrastructure.config import ResolveSection
from o_editor.infrastructure.resolve.native_bridge import NativeResolveBridge


@dataclass(frozen=True, slots=True)
class LaunchContext:
    project_name: str
    timeline_name: str
    timeline_id: str | None
    resolve_version: str | None
    timestamp: str | None = None
    context_kind: str | None = None
    product_name: str | None = None
    fps: float | None = None
    start_frame: int | None = None
    end_frame: int | None = None
    duration_frames: int | None = None
    start_timecode: str | None = None
    track_counts: dict[str, int] | None = None
    audio_tracks: tuple[AudioTrackSnapshot, ...] = ()
    audio_track_count: int = 0
    launched_from_resolve: bool = False
    layout: dict[str, Any] | None = None

    @property
    def is_internal(self) -> bool:
        return self.context_kind == "internal_resolve_host" and self.launched_from_resolve

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_name": self.project_name,
            "timeline_name": self.timeline_name,
            "timeline_id": self.timeline_id,
            "resolve_version": self.resolve_version,
            "timestamp": self.timestamp,
            "context_kind": self.context_kind,
            "product_name": self.product_name,
            "fps": self.fps,
            "start_frame": self.start_frame,
            "end_frame": self.end_frame,
            "duration_frames": self.duration_frames,
            "start_timecode": self.start_timecode,
            "track_counts": self.track_counts,
            "audio_tracks": [track.to_dict() for track in self.audio_tracks],
            "audio_track_count": self.audio_track_count,
            "launched_from_resolve": self.launched_from_resolve,
            "layout": self.layout,
        }


def consume_launch_context(
    path: Path,
    *,
    require_internal_host: bool = False,
    maximum_age_seconds: int = 600,
) -> LaunchContext:
    _validate_context_path(path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ConfigurationError("O contexto de lançamento deve ser um objeto JSON.")
        if value.get("schema_version") not in {1, 2, 3}:
            raise ConfigurationError("O contexto possui schema_version incompatível.")
        context = _parse_context(value)
        if require_internal_host:
            _validate_internal_context(context, maximum_age_seconds=maximum_age_seconds)
        return context
    except UnicodeError as exc:
        raise ConfigurationError("O contexto de lançamento não está em UTF-8 válido.") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Não foi possível ler o contexto: {path}") from exc
    finally:
        _remove_if_safe(path)


def reconcile_launch_context(
    context: LaunchContext,
    resolve_config: ResolveSection,
    *,
    root: Path,
    bridge: NativeResolveBridge | None = None,
) -> dict[str, Any]:
    active = (bridge or NativeResolveBridge(root=root, config=resolve_config)).read_context()
    project_name = active.project_name
    timeline_name = active.timeline_name
    timeline_id = active.timeline_id
    matches = (
        project_name == context.project_name
        and timeline_name == context.timeline_name
        and (context.timeline_id is None or timeline_id == context.timeline_id)
    )
    return {
        **context.to_dict(),
        "project_name": project_name,
        "timeline_name": timeline_name,
        "timeline_id": timeline_id,
        "context_matches": matches,
        "real_integration_available": True,
        "integration_mode": "external_fusionscript_bridge",
        "connection_status": (
            "Contexto reconectado e confirmado."
            if matches
            else "O projeto ou a timeline mudou após o acionamento do launcher."
        ),
    }


def _parse_context(value: dict[str, Any]) -> LaunchContext:
    project_name = value.get("project_name")
    timeline_name = value.get("timeline_name")
    if not isinstance(project_name, str) or not project_name.strip():
        raise ConfigurationError("O contexto não contém um projeto válido.")
    if not isinstance(timeline_name, str) or not timeline_name.strip():
        raise ConfigurationError("O contexto não contém uma timeline válida.")
    track_counts_value = value.get("track_counts")
    track_counts: dict[str, int] | None = None
    if isinstance(track_counts_value, dict):
        try:
            track_counts = {
                name: int(track_counts_value.get(name, 0))
                for name in ("video", "audio", "subtitle")
            }
        except (TypeError, ValueError) as exc:
            raise ConfigurationError("O contexto contém contagens de tracks inválidas.") from exc
    raw_audio_tracks = value.get("audio_tracks", [])
    if not isinstance(raw_audio_tracks, list):
        raise ConfigurationError("O contexto contém faixas de áudio inválidas.")
    try:
        audio_tracks = tuple(
            AudioTrackSnapshot.from_dict(item)
            for item in raw_audio_tracks
            if isinstance(item, dict)
        )
        audio_track_count = int(value.get("audio_track_count", len(audio_tracks)))
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigurationError(
            "O contexto contém metadados inválidos de faixa de áudio."
        ) from exc
    if audio_tracks and audio_track_count != len(audio_tracks):
        raise ConfigurationError("A contagem de faixas de áudio não corresponde à lista.")
    return LaunchContext(
        project_name=project_name.strip(),
        timeline_name=timeline_name.strip(),
        timeline_id=_optional_string(value.get("timeline_id")),
        resolve_version=_optional_string(value.get("resolve_version")),
        timestamp=_optional_string(value.get("timestamp")),
        context_kind=_optional_string(value.get("context_kind")),
        product_name=_optional_string(value.get("product_name")),
        fps=_optional_float(value.get("fps")),
        start_frame=_optional_int(value.get("start_frame")),
        end_frame=_optional_int(value.get("end_frame")),
        duration_frames=_optional_int(value.get("duration_frames")),
        start_timecode=_optional_string(value.get("start_timecode")),
        track_counts=track_counts,
        audio_tracks=audio_tracks,
        audio_track_count=audio_track_count,
        launched_from_resolve=value.get("launched_from_resolve") is True,
        layout=value.get("layout") if isinstance(value.get("layout"), dict) else None,
    )


def _validate_internal_context(
    context: LaunchContext,
    *,
    maximum_age_seconds: int,
) -> None:
    if not context.is_internal:
        raise ConfigurationError("O contexto não foi criado pelo host interno do Resolve.")
    if context.timestamp is None:
        raise ConfigurationError("O contexto interno não contém timestamp.")
    try:
        parsed = datetime.fromisoformat(context.timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConfigurationError("O timestamp do contexto interno é inválido.") from exc
    if parsed.tzinfo is None:
        raise ConfigurationError("O timestamp do contexto interno não possui fuso horário.")
    age = (datetime.now(UTC) - parsed.astimezone(UTC)).total_seconds()
    if age > maximum_age_seconds:
        raise ConfigurationError("O contexto interno expirou.")
    if age < -60:
        raise ConfigurationError("O contexto interno possui timestamp no futuro.")
    if (
        context.fps is None
        or context.fps <= 0
        or context.start_frame is None
        or context.end_frame is None
        or context.end_frame <= context.start_frame
        or context.duration_frames != context.end_frame - context.start_frame
        or context.track_counts is None
        or (context.audio_tracks and context.audio_track_count != len(context.audio_tracks))
    ):
        raise ConfigurationError("O contexto interno contém metadados de timeline inválidos.")


def _validate_context_path(path: Path) -> None:
    if (
        path.parent.name.casefold() == "o-editor"
        and path.name.startswith("launch-context-")
        and path.suffix.casefold() == ".json"
    ):
        return
    raise ConfigurationError("O caminho do contexto de lançamento não é permitido.")


def _optional_string(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("O contexto contém frame rate inválido.") from exc


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("O contexto contém frame inválido.") from exc


def _remove_if_safe(path: Path) -> None:
    if path.parent.name.casefold() != "o-editor":
        return
    if not path.name.startswith("launch-context-") or path.suffix.casefold() != ".json":
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return
