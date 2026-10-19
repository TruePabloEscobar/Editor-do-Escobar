from __future__ import annotations

import wave
from pathlib import Path

import pytest

from o_editor.domain.models import TimelineSnapshot
from o_editor.errors import CancelledError
from o_editor.infrastructure.resolve.audio_exporter import (
    AudioExportError,
    ManualAudioExporter,
    validate_wav,
)
from o_editor.infrastructure.transcription.base import CancellationToken


def _write_pcm(
    path: Path,
    *,
    seconds: int = 1,
    sample_rate: int = 16_000,
    channels: int = 1,
) -> None:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(b"\0\0" * sample_rate * seconds * channels)


def _snapshot(*, duration_frames: int = 30) -> TimelineSnapshot:
    return TimelineSnapshot(
        project_name="Projeto",
        timeline_name="Timeline",
        timeline_id="timeline-1",
        fps=30.0,
        drop_frame=False,
        start_frame=0,
        end_frame=duration_frames,
        video_track_count=1,
        audio_track_count=1,
        items=(),
    )


def test_manual_pcm_wav_is_validated_and_copied(tmp_path: Path) -> None:
    source = tmp_path / "manual source.wav"
    destination = tmp_path / "cache" / "audio.wav"
    _write_pcm(source)
    progress: list[tuple[float, str]] = []

    result = ManualAudioExporter(source, offset_frames=15).export(
        _snapshot(),
        destination,
        progress=lambda value, message: progress.append((value, message)),
    )

    assert result == destination
    assert destination.read_bytes() == source.read_bytes()
    assert validate_wav(destination) == pytest.approx(1.0)
    assert progress == [(1.0, "VALIDATING_AUDIO")]


def test_manual_wav_rejects_unsupported_sample_rate(tmp_path: Path) -> None:
    source = tmp_path / "invalid-rate.wav"
    _write_pcm(source, sample_rate=44_100)

    with pytest.raises(AudioExportError, match="16 kHz ou 48 kHz"):
        validate_wav(source)


def test_manual_wav_rejects_duration_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "short.wav"
    _write_pcm(source)

    with pytest.raises(AudioExportError, match="Confirme o arquivo e o offset"):
        ManualAudioExporter(source, tolerance_seconds=0.1).export(
            _snapshot(duration_frames=300),
            tmp_path / "unused.wav",
        )


def test_manual_wav_honors_pre_cancelled_token(tmp_path: Path) -> None:
    source = tmp_path / "manual.wav"
    _write_pcm(source)
    cancellation = CancellationToken()
    cancellation.cancel()

    with pytest.raises(CancelledError):
        ManualAudioExporter(source).export(
            _snapshot(),
            tmp_path / "unused.wav",
            cancellation=cancellation,
        )
