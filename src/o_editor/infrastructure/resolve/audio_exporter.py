"""Audio exporter contracts and safe implementations."""

from __future__ import annotations

import shutil
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from o_editor.domain.models import TimelineSnapshot
from o_editor.domain.voice_tracks import SelectedVoiceTrack
from o_editor.errors import CancelledError, OEditorError
from o_editor.infrastructure.resolve.adapter import ResolveAdapter
from o_editor.infrastructure.transcription.base import CancellationToken
from o_editor.internal_actions.voice_audio import (
    VoiceAudioExportRequest,
    save_voice_audio_request,
)

ProgressCallback = Callable[[float, str], None]


class AudioExportError(OEditorError):
    """Timeline audio could not be obtained safely."""


class AudioExporter(Protocol):
    def export(
        self,
        snapshot: TimelineSnapshot,
        destination: Path,
        *,
        progress: ProgressCallback | None = None,
        cancellation: CancellationToken | None = None,
        selected_voice_tracks: tuple[SelectedVoiceTrack, ...] = (),
    ) -> Path: ...


class ResolveAudioExporter:
    def __init__(self, adapter: ResolveAdapter) -> None:
        self._adapter = adapter

    def export(
        self,
        snapshot: TimelineSnapshot,
        destination: Path,
        *,
        progress: ProgressCallback | None = None,
        cancellation: CancellationToken | None = None,
        selected_voice_tracks: tuple[SelectedVoiceTrack, ...] = (),
    ) -> Path:
        del snapshot, selected_voice_tracks
        _raise_if_cancelled(cancellation)
        if progress:
            progress(0.05, "EXPORTING_VOICE_TRACKS")
        result = self._adapter.export_audio(destination, sample_rate=16_000, channels=1)
        _raise_if_cancelled(cancellation)
        if progress:
            progress(1.0, "VALIDATING_AUDIO")
        return result


class InternalVoiceAudioExporter:
    """Prepare a host request but keep export blocked until every capability is proven."""

    backend_name = "internal_resolve_lua_unverified"

    def __init__(self, request_root: Path | None = None) -> None:
        self._request_root = request_root
        self.last_request_path: Path | None = None

    def export(
        self,
        snapshot: TimelineSnapshot,
        destination: Path,
        *,
        progress: ProgressCallback | None = None,
        cancellation: CancellationToken | None = None,
        selected_voice_tracks: tuple[SelectedVoiceTrack, ...] = (),
    ) -> Path:
        _raise_if_cancelled(cancellation)
        if not selected_voice_tracks:
            raise AudioExportError("Selecione pelo menos uma faixa de voz.")
        if progress:
            progress(0.05, "PREPARING_AUDIO")
        request = VoiceAudioExportRequest.create(
            project=snapshot.project_name,
            timeline=snapshot.timeline_name,
            timeline_fingerprint=snapshot.fingerprint,
            selected_tracks=selected_voice_tracks,
            output_path=destination,
        )
        self.last_request_path = save_voice_audio_request(request, self._request_root)
        raise AudioExportError(
            "Exportação automática das faixas de voz indisponível: as capabilities de "
            "seleção/render ainda estão UNVERIFIED. A request de preflight foi salva em "
            f"{self.last_request_path}. Selecione um WAV exportado da mesma timeline."
        )


class ManualAudioExporter:
    def __init__(
        self,
        source: Path,
        *,
        offset_frames: int = 0,
        tolerance_seconds: float = 2.0,
    ) -> None:
        self._source = source
        self.offset_frames = offset_frames
        self._tolerance_seconds = tolerance_seconds

    def export(
        self,
        snapshot: TimelineSnapshot,
        destination: Path,
        *,
        progress: ProgressCallback | None = None,
        cancellation: CancellationToken | None = None,
        selected_voice_tracks: tuple[SelectedVoiceTrack, ...] = (),
    ) -> Path:
        del selected_voice_tracks
        _raise_if_cancelled(cancellation)
        duration = validate_wav(self._source)
        expected = snapshot.duration_frames / snapshot.fps
        if abs(duration - expected) > self._tolerance_seconds:
            raise AudioExportError(
                f"O WAV tem {duration:.1f}s, mas a timeline tem {expected:.1f}s. "
                "Confirme o arquivo e o offset."
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self._source, destination)
        if progress:
            progress(1.0, "VALIDATING_AUDIO")
        return destination


class MockAudioExporter(ResolveAudioExporter):
    """Semantic name for mock-backed audio export."""


def validate_wav(path: Path) -> float:
    if not path.is_file():
        raise AudioExportError(f"Arquivo WAV não encontrado: {path}")
    try:
        with wave.open(str(path), "rb") as source:
            if source.getsampwidth() not in (2, 3, 4):
                raise AudioExportError("O WAV deve usar PCM de 16, 24 ou 32 bits.")
            if source.getframerate() not in (16_000, 48_000):
                raise AudioExportError("O WAV deve usar 16 kHz ou 48 kHz.")
            if source.getnchannels() not in (1, 2):
                raise AudioExportError("O WAV deve ser mono ou estéreo.")
            return source.getnframes() / source.getframerate()
    except (wave.Error, EOFError) as exc:
        raise AudioExportError("O arquivo selecionado não é um WAV PCM válido.") from exc


def _raise_if_cancelled(cancellation: CancellationToken | None) -> None:
    if cancellation and cancellation.cancelled:
        raise CancelledError("A operação foi cancelada.")
