"""Per-track transcription boundary (seconds relative to the rendered WAV start)."""

from __future__ import annotations

import math
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from o_editor.errors import CancelledError, OEditorError
from o_editor.infrastructure.audio.signal import TrackSignal
from o_editor.infrastructure.transcription.base import CancellationToken, TranscriptionProgress
from o_editor.infrastructure.transcription.local_model import local_model_identity


class TrackTranscriptionError(OEditorError):
    """Transcription of a rendered track failed."""


@dataclass(frozen=True, slots=True)
class TimedWord:
    text: str
    start: float
    end: float
    probability: float | None = None


@dataclass(frozen=True, slots=True)
class TimedSegment:
    start: float
    end: float
    text: str
    words: tuple[TimedWord, ...] = ()
    avg_logprob: float | None = None
    no_speech_prob: float | None = None

    @property
    def confidence(self) -> float | None:
        if self.words:
            probabilities = [
                word.probability for word in self.words if word.probability is not None
            ]
            if probabilities:
                return sum(probabilities) / len(probabilities)
        if self.avg_logprob is not None:
            return math.exp(self.avg_logprob)
        return None


@dataclass(frozen=True, slots=True)
class TrackTranscriptionResult:
    segments: tuple[TimedSegment, ...]
    language: str | None
    provider: str
    model: str
    device: str | None = None
    fallback_reason: str | None = None


class TrackTranscriber(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    def transcribe_track(
        self,
        audio_path: Path,
        *,
        language: str | None,
        progress: TranscriptionProgress | None = None,
        cancellation: CancellationToken | None = None,
    ) -> TrackTranscriptionResult: ...


def register_cuda_dll_directories() -> tuple[str, ...]:
    """Expose NVIDIA wheels (cuBLAS/cuDNN) to ctranslate2 on Windows.

    ``pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`` installs the DLLs under
    ``site-packages/nvidia/*/bin``; Windows does not search there by default, which is
    the reason for the ``cublas64_12.dll`` failure recorded in the validation report.
    """

    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return ()
    registered: list[str] = []
    for base in {Path(item) for item in sys.path if item}:
        nvidia = base / "nvidia"
        if not nvidia.is_dir():
            continue
        for candidate in nvidia.glob("*/bin"):
            try:
                os.add_dll_directory(str(candidate))
            except OSError:
                continue
            os.environ["PATH"] = str(candidate) + os.pathsep + os.environ.get("PATH", "")
            registered.append(str(candidate))
    return tuple(registered)


class FasterWhisperTrackTranscriber:
    """faster-whisper with VAD and anti-hallucination settings; model loaded once."""

    def __init__(
        self,
        *,
        model_path: Path | None,
        configured_model_name: str,
        device: str = "auto",
        compute_type: str = "auto",
        device_index: int = 0,
        beam_size: int = 5,
        vad_filter: bool = True,
    ) -> None:
        self._model_path = model_path
        self._model_name = configured_model_name
        self._device = device
        self._compute_type = compute_type
        self._device_index = device_index
        self._beam_size = beam_size
        self._vad_filter = vad_filter
        self._model: Any = None
        self._model_device: str | None = None
        self._fallback_reason: str | None = None

    @property
    def name(self) -> str:
        return "faster-whisper"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def cache_identity(self) -> str:
        return local_model_identity(self._model_path, self._model_name)

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        if self._model_path is None or not self._model_path.is_dir():
            raise TrackTranscriptionError(
                "O modelo Whisper não está disponível localmente. Configure "
                "transcription.model_path em %APPDATA%\\O Editor\\config.json; "
                "nenhum download foi iniciado."
            )
        register_cuda_dll_directories()
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise TrackTranscriptionError(
                'faster-whisper não está instalado. Execute: pip install -e ".[whisper]"'
            ) from exc
        device = self._device
        if device == "auto":
            try:
                import ctranslate2

                device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            except ImportError:
                device = "cpu"
        compute = self._compute_type
        try:
            self._model = WhisperModel(
                str(self._model_path),
                device=device,
                device_index=self._device_index,
                compute_type=compute,
                local_files_only=True,
            )
            self._model_device = device
        except (OSError, RuntimeError, ValueError) as exc:
            if device != "cuda" or self._device != "auto":
                raise TrackTranscriptionError(
                    "Não foi possível carregar o modelo Whisper."
                ) from exc
            self._fallback_reason = (
                f"CUDA indisponível ({exc}); usando CPU. Instale nvidia-cublas-cu12 e "
                "nvidia-cudnn-cu12 no ambiente do O Editor para usar a GPU."
            )
            self._model = WhisperModel(
                str(self._model_path), device="cpu", compute_type="int8", local_files_only=True
            )
            self._model_device = "cpu"
        return self._model

    def transcribe_track(
        self,
        audio_path: Path,
        *,
        language: str | None,
        progress: TranscriptionProgress | None = None,
        cancellation: CancellationToken | None = None,
    ) -> TrackTranscriptionResult:
        model = self._load()
        if cancellation and cancellation.cancelled:
            raise CancelledError("A transcrição foi cancelada.")
        try:
            segments, info = model.transcribe(
                str(audio_path),
                language=language,
                beam_size=self._beam_size,
                word_timestamps=True,
                vad_filter=self._vad_filter,
                vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 200},
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
                log_prob_threshold=-1.0,
                compression_ratio_threshold=2.4,
            )
            duration = float(getattr(info, "duration", 0.0) or 0.0)
            result: list[TimedSegment] = []
            for segment in segments:
                if cancellation and cancellation.cancelled:
                    raise CancelledError("A transcrição foi cancelada.")
                words = tuple(
                    TimedWord(
                        text=str(word.word).strip(),
                        start=float(word.start),
                        end=float(word.end),
                        probability=float(word.probability),
                    )
                    for word in (segment.words or ())
                    if str(word.word).strip()
                )
                result.append(
                    TimedSegment(
                        start=float(segment.start),
                        end=float(segment.end),
                        text=str(segment.text).strip(),
                        words=words,
                        avg_logprob=float(getattr(segment, "avg_logprob", 0.0)),
                        no_speech_prob=float(getattr(segment, "no_speech_prob", 0.0)),
                    )
                )
                if progress and duration > 0:
                    progress(min(0.99, float(segment.end) / duration), "Transcrevendo")
        except CancelledError:
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            raise TrackTranscriptionError(f"A transcrição local falhou: {exc}") from exc
        if progress:
            progress(1.0, "Transcrição concluída")
        return TrackTranscriptionResult(
            segments=tuple(result),
            language=str(getattr(info, "language", language or "")) or language,
            provider=self.name,
            model=self._model_name,
            device=self._model_device,
            fallback_reason=self._fallback_reason,
        )


PhraseResolver = Callable[[float], str]


class SignalMockTranscriber:
    """Deterministic offline transcriber: one segment per burst of signal.

    Used by the mock mode and the automated tests. The optional resolver maps the
    dominant frequency of a burst to a phrase so fixtures can encode text in audio.
    """

    def __init__(self, phrase_resolver: PhraseResolver | None = None) -> None:
        self._resolver = phrase_resolver

    @property
    def name(self) -> str:
        return "mock-signal"

    @property
    def model_name(self) -> str:
        return "mock-signal-v1"

    def transcribe_track(
        self,
        audio_path: Path,
        *,
        language: str | None,
        progress: TranscriptionProgress | None = None,
        cancellation: CancellationToken | None = None,
    ) -> TrackTranscriptionResult:
        fps = 1000.0
        signal = TrackSignal.load(audio_path, fps=fps, timeline_start_frame=0)
        segments: list[TimedSegment] = []
        intervals = signal.activity()
        for number, (start, end) in enumerate(intervals, start=1):
            if cancellation and cancellation.cancelled:
                raise CancelledError("A transcrição foi cancelada.")
            frequency = signal.dominant_frequency(start, end)
            text = self._resolver(frequency) if self._resolver else f"Fala simulada {number}."
            tokens = text.split()
            span = (end - start) / fps
            width = span / max(1, len(tokens))
            words = tuple(
                TimedWord(
                    text=token,
                    start=start / fps + index * width,
                    end=start / fps + (index + 1) * width,
                    probability=0.95,
                )
                for index, token in enumerate(tokens)
            )
            segments.append(
                TimedSegment(
                    start=start / fps,
                    end=end / fps,
                    text=text,
                    words=words,
                    avg_logprob=-0.1,
                    no_speech_prob=0.01,
                )
            )
            if progress:
                progress(number / max(1, len(intervals)), "Transcrição simulada")
        return TrackTranscriptionResult(
            segments=tuple(segments),
            language=language or "pt",
            provider=self.name,
            model=self.model_name,
            device="cpu",
        )
