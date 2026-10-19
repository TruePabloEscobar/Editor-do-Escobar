"""faster-whisper provider that never downloads models implicitly."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from o_editor.domain.models import Transcript, TranscriptSegment, TranscriptWord
from o_editor.domain.timecode import seconds_to_frames
from o_editor.errors import CancelledError, OEditorError
from o_editor.infrastructure.transcription.base import (
    CancellationToken,
    TranscriptionProgress,
)
from o_editor.infrastructure.transcription.local_model import local_model_identity
from o_editor.infrastructure.transcription.track import register_cuda_dll_directories


class TranscriptionError(OEditorError):
    """Local transcription failed or is not configured."""


class FasterWhisperProvider:
    def __init__(
        self,
        *,
        model_path: Path | None,
        configured_model_name: str,
        device: str = "auto",
        compute_type: str = "auto",
        device_index: int = 0,
    ) -> None:
        self._model_path = model_path
        self._configured_model_name = configured_model_name
        self._device = device
        self._compute_type = compute_type
        self._device_index = device_index
        self._last_device: str | None = None
        self._last_fallback_reason: str | None = None

    @property
    def name(self) -> str:
        return "faster-whisper"

    @property
    def cache_identity(self) -> str:
        return local_model_identity(self._model_path, self._configured_model_name)

    @property
    def last_device(self) -> str | None:
        """Device that completed the most recent transcription."""

        return self._last_device

    @property
    def last_fallback_reason(self) -> str | None:
        """Readable reason for the latest automatic CPU fallback."""

        return self._last_fallback_reason

    def transcribe(
        self,
        audio_path: Path,
        *,
        fps: float,
        timeline_start_frame: int,
        language: str | None,
        progress: TranscriptionProgress | None = None,
        cancellation: CancellationToken | None = None,
    ) -> Transcript:
        if self._model_path is None or not self._model_path.is_dir():
            raise TranscriptionError(
                "O modelo Whisper não está disponível localmente. Baixe-o com consentimento "
                "explícito e configure transcription.model_path; nenhum download foi iniciado."
            )
        register_cuda_dll_directories()
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise TranscriptionError(
                'faster-whisper não está instalado. Execute: pip install -e ".[whisper]"'
            ) from exc

        if cancellation and cancellation.cancelled:
            raise CancelledError("A transcrição foi cancelada.")
        self._last_device = None
        self._last_fallback_reason = None
        device = self._resolve_device()
        try:
            normalized, info = self._run_model(
                WhisperModel,
                audio_path,
                device=device,
                compute_type=self._compute_type,
                fps=fps,
                timeline_start_frame=timeline_start_frame,
                language=language,
                progress=progress,
                cancellation=cancellation,
            )
            self._last_device = device
        except CancelledError:
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            if device == "cuda" and self._device == "auto":
                self._last_fallback_reason = (
                    "O runtime CUDA não concluiu a inferência; fallback automático em CPU."
                )
                if progress:
                    progress(0.02, "CUDA indisponível; tentando fallback em CPU")
                try:
                    normalized, info = self._run_model(
                        WhisperModel,
                        audio_path,
                        device="cpu",
                        compute_type="int8",
                        fps=fps,
                        timeline_start_frame=timeline_start_frame,
                        language=language,
                        progress=progress,
                        cancellation=cancellation,
                    )
                    self._last_device = "cpu"
                except CancelledError:
                    raise
                except (OSError, RuntimeError, ValueError) as cpu_exc:
                    raise TranscriptionError(
                        "A transcrição falhou em CUDA e no fallback em CPU."
                    ) from cpu_exc
            else:
                raise TranscriptionError("A transcrição local falhou.") from exc

        detected_language = str(getattr(info, "language", language or "unknown"))
        return Transcript(
            language=detected_language,
            fps=fps,
            timeline_start_frame=timeline_start_frame,
            segments=normalized,
            provider=self.name,
            model=self._configured_model_name,
        )

    def _run_model(
        self,
        model_type: Any,
        audio_path: Path,
        *,
        device: str,
        compute_type: str,
        fps: float,
        timeline_start_frame: int,
        language: str | None,
        progress: TranscriptionProgress | None,
        cancellation: CancellationToken | None,
    ) -> tuple[tuple[TranscriptSegment, ...], Any]:
        model = model_type(
            str(self._model_path),
            device=device,
            device_index=self._device_index if device == "cuda" else 0,
            compute_type=compute_type,
            local_files_only=True,
        )
        segments, info = model.transcribe(
            str(audio_path),
            language=language,
            word_timestamps=True,
        )
        normalized = self._normalize(
            segments,
            fps=fps,
            timeline_start_frame=timeline_start_frame,
            progress=progress,
            cancellation=cancellation,
        )
        return normalized, info

    def _resolve_device(self) -> str:
        if self._device != "auto":
            return self._device
        try:
            import ctranslate2

            return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except ImportError:
            return "cpu"

    @staticmethod
    def _normalize(
        source_segments: Any,
        *,
        fps: float,
        timeline_start_frame: int,
        progress: TranscriptionProgress | None,
        cancellation: CancellationToken | None,
    ) -> tuple[TranscriptSegment, ...]:
        result: list[TranscriptSegment] = []
        previous_end = timeline_start_frame
        for index, segment in enumerate(source_segments):
            if cancellation and cancellation.cancelled:
                raise CancelledError("A transcrição foi cancelada.")
            start = seconds_to_frames(
                float(segment.start),
                fps,
                timeline_start_frame=timeline_start_frame,
            )
            end = seconds_to_frames(
                float(segment.end),
                fps,
                timeline_start_frame=timeline_start_frame,
            )
            words = tuple(
                TranscriptWord(
                    text=str(word.word).strip(),
                    start_frame=seconds_to_frames(
                        float(word.start),
                        fps,
                        timeline_start_frame=timeline_start_frame,
                    ),
                    end_frame=seconds_to_frames(
                        float(word.end),
                        fps,
                        timeline_start_frame=timeline_start_frame,
                    ),
                    probability=float(word.probability),
                )
                for word in (segment.words or ())
                if str(word.word).strip()
            )
            result.append(
                TranscriptSegment.create(
                    start_frame=start,
                    end_frame=max(start + 1, end),
                    text=str(segment.text).strip(),
                    words=words,
                    pause_before_frames=max(0, start - previous_end),
                )
            )
            previous_end = end
            if progress:
                progress(min(0.99, 0.05 + index * 0.02), "Transcrevendo localmente")
        if progress:
            progress(1.0, "Transcrição concluída")
        return tuple(result)
