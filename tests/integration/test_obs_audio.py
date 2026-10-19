"""BUG-0001/0002: real FFmpeg MOV streams, EOF padding and channel identity."""

from __future__ import annotations

import json
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from o_editor.domain.enums import ChannelMode, TrackType
from o_editor.domain.timeline_layout import ClipInfo, TimelineLayout, TrackInfo
from o_editor.infrastructure.audio.track_renderer import TrackAudioRenderer, TrackRenderError
from o_editor.infrastructure.ffmpeg.runner import FFmpegRunner

FPS = 23.976


@pytest.fixture(scope="module")
def obs_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg, "FFmpeg é obrigatório para esta regressão."
    target = tmp_path_factory.mktemp("obs") / "recording.mov"
    subprocess.run(
        [
            ffmpeg,
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=black:s=16x16:r=24000/1001:d=18.351667",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=18.282667",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:sample_rate=48000:duration=18.282667",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-map",
            "2:a:0",
            "-c:v",
            "mpeg4",
            "-c:a",
            "pcm_s16le",
            "-ac",
            "2",
            str(target),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return target


def _layout(source: Path, frames: int, channels: list[int]) -> TimelineLayout:
    clip = ClipInfo(
        item_id="audio",
        track_type=TrackType.AUDIO,
        track_index=1,
        item_index=1,
        name="recording.mov",
        item_type="audio",
        start_frame=0,
        end_frame=frames,
        source_start_frame=0,
        source_end_frame=frames - 1,
        source_start_seconds=0,
        source_end_seconds=frames / FPS,
        left_offset_frames=0,
        right_offset_frames=0,
        file_path=str(source),
        media_fps=FPS,
        speed_percent=100,
        audio_channel_mapping=json.dumps(
            {"track_mapping": {"1": {"channel_idx": channels, "mute": False}}}
        ),
    )
    return TimelineLayout(
        "Synthetic",
        "OBS",
        "test",
        FPS,
        0,
        frames,
        "00:00:00:00",
        False,
        (TrackInfo(TrackType.AUDIO, 1, "Microphone"),),
        (clip,),
    )


def test_short_audio_tail_keeps_timeline_alignment(obs_file: Path, tmp_path: Path) -> None:
    renderer = TrackAudioRenderer(FFmpegRunner(), tmp_path)
    rendered = renderer.render(_layout(obs_file, 442, [1, 2]), 1, ChannelMode.BOTH)
    with wave.open(str(rendered.path), "rb") as wav:
        samples = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
        assert wav.getnframes() == round(442 / FPS * 16000)
    assert np.max(np.abs(samples[:16000])) > 100
    assert np.max(np.abs(samples[-1600:])) == 0
    assert rendered.warnings


@pytest.mark.parametrize("channels,frequency", [([1, 2], 440), ([3, 4], 880), ([1, 3], None)])
def test_mapping_uses_actual_embedded_stream(
    obs_file: Path, tmp_path: Path, channels: list[int], frequency: int | None
) -> None:
    rendered = TrackAudioRenderer(FFmpegRunner(), tmp_path).render(
        _layout(obs_file, 240, channels), 1, ChannelMode.BOTH
    )
    with wave.open(str(rendered.path), "rb") as wav:
        signal = np.frombuffer(wav.readframes(16000), dtype=np.int16).astype(float)
    spectrum = np.abs(np.fft.rfft(signal))
    if frequency is not None:
        assert int(np.argmax(spectrum)) == frequency
    else:
        assert spectrum[440] > 1_000_000 and spectrum[880] > 1_000_000
    assert not any("inexistentes" in message for message in rendered.warnings)


def test_large_range_overrun_stays_blocked(obs_file: Path, tmp_path: Path) -> None:
    with pytest.raises(TrackRenderError, match="ultrapassa"):
        TrackAudioRenderer(FFmpegRunner(), tmp_path).render(
            _layout(obs_file, 480, [1, 2]), 1, ChannelMode.BOTH
        )
