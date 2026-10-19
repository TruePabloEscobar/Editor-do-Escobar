"""Signal-level analysis of rendered 16-bit mono WAV tracks (numpy)."""

from __future__ import annotations

import hashlib
import math
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from o_editor.errors import OEditorError

SILENCE_DB = -120.0


class SignalAnalysisError(OEditorError):
    """The rendered track could not be analysed."""


def _numpy() -> Any:
    try:
        import numpy
    except ImportError as exc:  # pragma: no cover - numpy ships with faster-whisper
        raise SignalAnalysisError(
            'numpy não está instalado. Execute: pip install -e ".[whisper]"'
        ) from exc
    return numpy


@dataclass(frozen=True, slots=True)
class ActivitySettings:
    window_ms: int = 20
    minimum_threshold_db: float = -50.0
    margin_above_floor_db: float = 10.0
    hangover_ms: int = 250
    minimum_active_ms: int = 80


class TrackSignal:
    """Windowed RMS levels of one rendered track aligned to timeline frames."""

    def __init__(
        self,
        levels_db: Any,
        *,
        sample_rate: int,
        window_samples: int,
        fps: float,
        timeline_start_frame: int,
        samples: Any,
    ) -> None:
        self._levels = levels_db
        self._sample_rate = sample_rate
        self._window = window_samples
        self._fps = fps
        self._start_frame = timeline_start_frame
        self._samples = samples

    @classmethod
    def load(
        cls,
        path: Path,
        *,
        fps: float,
        timeline_start_frame: int,
        window_ms: int = 20,
    ) -> TrackSignal:
        np = _numpy()
        try:
            with wave.open(str(path), "rb") as handle:
                if handle.getsampwidth() != 2 or handle.getnchannels() != 1:
                    raise SignalAnalysisError("A análise de sinal exige WAV PCM 16 bits mono.")
                sample_rate = handle.getframerate()
                data = handle.readframes(handle.getnframes())
        except (OSError, wave.Error, EOFError) as exc:
            raise SignalAnalysisError(f"Não foi possível ler o áudio da faixa: {path}") from exc
        samples = np.frombuffer(data, dtype="<i2")
        window = max(1, round(sample_rate * window_ms / 1000))
        usable = (len(samples) // window) * window
        if usable == 0:
            levels = np.full(0, SILENCE_DB, dtype="float32")
        else:
            blocks = samples[:usable].astype("float32").reshape(-1, window) / 32768.0
            power = (blocks * blocks).mean(axis=1)
            with np.errstate(divide="ignore"):
                levels = np.where(power > 0, 10.0 * np.log10(power), SILENCE_DB).astype("float32")
        return cls(
            levels,
            sample_rate=sample_rate,
            window_samples=window,
            fps=fps,
            timeline_start_frame=timeline_start_frame,
            samples=samples,
        )

    @property
    def duration_seconds(self) -> float:
        return len(self._samples) / self._sample_rate

    def fingerprint(self) -> str | None:
        """Identity of complete aligned PCM; silent tracks supply no duplicate proof."""
        np = _numpy()
        if not np.any(self._samples):
            return None
        digest = hashlib.sha256(f"pcm16-mono-v1:{self._sample_rate}:{len(self._samples)}".encode())
        digest.update(memoryview(self._samples))
        return digest.hexdigest()

    def _window_range(self, start_frame: int, end_frame: int) -> tuple[int, int]:
        window_seconds = self._window / self._sample_rate
        first = math.floor((start_frame - self._start_frame) / self._fps / window_seconds)
        last = math.ceil((end_frame - self._start_frame) / self._fps / window_seconds)
        first = max(0, min(first, len(self._levels)))
        last = max(first, min(last, len(self._levels)))
        return first, last

    def level_db(self, start_frame: int, end_frame: int) -> float:
        """RMS level (dBFS) of the interval; -120 for digital silence."""

        np = _numpy()
        first, last = self._window_range(start_frame, end_frame)
        if last <= first:
            return SILENCE_DB
        powers = np.power(10.0, self._levels[first:last] / 10.0)
        powers = np.where(self._levels[first:last] <= SILENCE_DB, 0.0, powers)
        mean = float(powers.mean())
        return 10.0 * math.log10(mean) if mean > 0 else SILENCE_DB

    def noise_floor_db(self) -> float:
        np = _numpy()
        audible = self._levels[self._levels > SILENCE_DB]
        if audible.size == 0:
            return SILENCE_DB
        # Clamp: a track with only loud content (or a noisy room) must still leave a
        # usable threshold; digital silence in gaps is excluded from the estimate.
        return float(min(-45.0, max(-90.0, float(np.percentile(audible, 15)))))

    def activity(self, settings: ActivitySettings | None = None) -> tuple[tuple[int, int], ...]:
        """Timeline-frame intervals with signal above the adaptive threshold."""

        settings = settings or ActivitySettings()
        np = _numpy()
        floor = self.noise_floor_db()
        threshold = max(settings.minimum_threshold_db, floor + settings.margin_above_floor_db)
        active = self._levels > threshold
        if not active.any():
            return ()
        window_seconds = self._window / self._sample_rate
        hangover = max(0, round(settings.hangover_ms / 1000 / window_seconds))
        minimum = max(1, round(settings.minimum_active_ms / 1000 / window_seconds))
        padded = np.concatenate(([False], active, [False]))
        changes = np.flatnonzero(padded[1:] != padded[:-1])
        runs = list(zip(changes[0::2], changes[1::2], strict=False))
        merged: list[list[int]] = []
        for start, end in runs:
            if merged and start - merged[-1][1] <= hangover:
                merged[-1][1] = int(end)
            else:
                merged.append([int(start), int(end)])
        intervals: list[tuple[int, int]] = []
        for start, end in merged:
            if end - start < minimum:
                continue
            start_frame = self._start_frame + math.floor(start * window_seconds * self._fps)
            end_frame = self._start_frame + math.ceil(end * window_seconds * self._fps)
            intervals.append((start_frame, max(start_frame + 1, end_frame)))
        return tuple(intervals)

    def active_fraction(
        self, start_frame: int, end_frame: int, settings: ActivitySettings | None = None
    ) -> float:
        settings = settings or ActivitySettings()
        floor = self.noise_floor_db()
        threshold = max(settings.minimum_threshold_db, floor + settings.margin_above_floor_db)
        first, last = self._window_range(start_frame, end_frame)
        if last <= first:
            return 0.0
        segment = self._levels[first:last]
        return float((segment > threshold).mean())

    def dominant_frequency(self, start_frame: int, end_frame: int) -> float:
        """Dominant frequency (FFT peak) of an interval; used by the signal mock."""

        np = _numpy()
        first = round((start_frame - self._start_frame) / self._fps * self._sample_rate)
        last = round((end_frame - self._start_frame) / self._fps * self._sample_rate)
        chunk = self._samples[max(0, first) : max(0, last)].astype("float32")
        if chunk.size < 16:
            return 0.0
        spectrum = np.abs(np.fft.rfft(chunk * np.hanning(chunk.size)))
        spectrum[0] = 0.0
        peak = int(np.argmax(spectrum))
        return float(peak * self._sample_rate / chunk.size)


def fingerprint_wav(path: Path, *, duration_seconds: float) -> str | None:
    """Read legacy cache in bounded blocks, without loading hours of PCM into RAM."""
    np = _numpy()
    try:
        with wave.open(str(path), "rb") as handle:
            if handle.getsampwidth() != 2 or handle.getnchannels() != 1:
                raise SignalAnalysisError("A identidade exige WAV PCM 16 bits mono.")
            rate, count = handle.getframerate(), handle.getnframes()
            if abs(count - round(duration_seconds * rate)) > 1:
                raise SignalAnalysisError("O cache não cobre a duração da timeline.")
            digest = hashlib.sha256(f"pcm16-mono-v1:{rate}:{count}".encode())
            nonzero, read = False, 0
            while chunk := handle.readframes(1 << 19):
                digest.update(chunk)
                read += len(chunk) // 2
                if not nonzero:
                    nonzero = bool(np.any(np.frombuffer(chunk, dtype="<i2")))
            if read != count:
                raise SignalAnalysisError("O cache de áudio está truncado.")
            return digest.hexdigest() if nonzero else None
    except (OSError, wave.Error, EOFError, ValueError) as exc:
        raise SignalAnalysisError(
            "Não foi possível conferir a identidade do áudio em cache."
        ) from exc
