"""Read-only adapter backed by context captured inside DaVinci Resolve."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from o_editor.domain.models import (
    ApplicationOperation,
    CapabilityResult,
    TimelineSnapshot,
)
from o_editor.domain.voice_tracks import AudioTrackSnapshot
from o_editor.errors import CapabilityGateError, ResolveUnavailableError
from o_editor.infrastructure.resolve.adapter import AdapterOperationResult


class InternalContextAdapter:
    def __init__(self, context: dict[str, Any]) -> None:
        self._context = context
        self._snapshot = _snapshot_from_context(context)

    def connect(self) -> None:
        return

    @property
    def resolve_version(self) -> str | None:
        value = self._context.get("resolve_version")
        return str(value) if value else None

    def get_active_snapshot(self) -> TimelineSnapshot:
        return self._snapshot

    def export_audio(
        self,
        destination: Path,
        *,
        sample_rate: int,
        channels: int,
    ) -> Path:
        del destination, sample_rate, channels
        raise CapabilityGateError(
            "A exportação interna de áudio ainda não foi validada. Selecione um WAV manual."
        )

    def duplicate_timeline(self, target_name: str) -> TimelineSnapshot:
        del target_name
        raise CapabilityGateError("Aplicação bloqueada: duplicação da timeline não validada.")

    def ensure_text_track(self, name: str) -> int:
        del name
        raise CapabilityGateError("Criação interna de track ainda não validada.")

    def apply_operation(self, operation: ApplicationOperation) -> AdapterOperationResult:
        del operation
        return AdapterOperationResult(
            False,
            "O aplicativo externo apenas exporta o plano; a aplicação pertence ao host interno.",
        )

    def verify_operation(self, operation: ApplicationOperation) -> bool:
        del operation
        return False

    def set_playhead(self, frame: int) -> bool:
        del frame
        return False

    def capability_results(self) -> tuple[CapabilityResult, ...]:
        return ()


def _snapshot_from_context(context: dict[str, Any]) -> TimelineSnapshot:
    try:
        project_name = str(context["project_name"])
        timeline_name = str(context["timeline_name"])
        fps = float(context["fps"])
        start_frame = int(context["start_frame"])
        end_frame = int(context["end_frame"])
        track_counts = context["track_counts"]
        if not isinstance(track_counts, dict):
            raise TypeError("track_counts")
        video_tracks = int(track_counts.get("video", 0))
        audio_tracks = int(track_counts.get("audio", 0))
    except (KeyError, TypeError, ValueError) as exc:
        raise ResolveUnavailableError(
            "O contexto interno não contém metadados suficientes da timeline."
        ) from exc
    timeline_id_value = context.get("timeline_id")
    return TimelineSnapshot(
        project_name=project_name,
        timeline_name=timeline_name,
        timeline_id=str(timeline_id_value) if timeline_id_value else None,
        fps=fps,
        drop_frame=";" in str(context.get("start_timecode", "")),
        start_frame=start_frame,
        end_frame=end_frame,
        video_track_count=video_tracks,
        audio_track_count=audio_tracks,
        items=(),
        audio_tracks=tuple(
            AudioTrackSnapshot.from_dict(item)
            for item in context.get("audio_tracks", ())
            if isinstance(item, dict)
        ),
    )
