from __future__ import annotations

from pathlib import Path

from o_editor.infrastructure.ffmpeg.runner import FFmpegRunner


def test_explicit_ffmpeg_and_ffprobe_directory_is_detected(tmp_path: Path) -> None:
    ffmpeg = tmp_path / "ffmpeg.exe"
    ffprobe = tmp_path / "ffprobe.exe"
    ffmpeg.touch()
    ffprobe.touch()

    runner = FFmpegRunner((tmp_path,))

    assert runner.find() == ffmpeg.resolve()
    assert runner.find_probe() == ffprobe.resolve()


def test_explicit_binary_paths_are_detected(tmp_path: Path) -> None:
    ffmpeg = tmp_path / "custom-ffmpeg.exe"
    ffprobe = tmp_path / "custom-ffprobe.exe"
    ffmpeg.touch()
    ffprobe.touch()

    runner = FFmpegRunner(ffmpeg_path=ffmpeg, ffprobe_path=ffprobe)

    assert runner.find() == ffmpeg.resolve()
    assert runner.find_probe() == ffprobe.resolve()


def test_missing_ffmpeg_and_ffprobe_return_none(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.delenv("FFPROBE_PATH", raising=False)
    monkeypatch.setattr("shutil.which", lambda _name: None)

    runner = FFmpegRunner((tmp_path / "missing",))

    assert runner.find() is None
    assert runner.find_probe() is None
