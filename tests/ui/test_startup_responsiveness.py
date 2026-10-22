"""BUG-0031: the FFmpeg version probe must not block the first paint of the window."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from o_editor.infrastructure.config import load_config
from o_editor.infrastructure.ffmpeg.runner import FFmpegRunner
from o_editor.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[2]


def test_ffmpeg_probe_runs_off_the_ui_thread(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = QApplication.instance() or QApplication([])
    release = threading.Event()
    calls: list[str] = []

    def slow_version(self: FFmpegRunner) -> str | None:
        calls.append(threading.current_thread().name)
        release.wait(5)
        return "ffmpeg version test"

    monkeypatch.setattr(FFmpegRunner, "version", slow_version)
    started = time.perf_counter()
    window = MainWindow(
        config=load_config(ROOT / "config/defaults.json"), root=tmp_path, use_mock=True
    )
    elapsed = time.perf_counter() - started
    assert elapsed < 4, "a janela esperou a verificação do FFmpeg"
    assert window._ffmpeg_label.text() == "PENDING"
    release.set()
    deadline = time.monotonic() + 5
    while window._ffmpeg_label.text() != "READY" and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window._ffmpeg_label.text() == "READY"
    assert calls and calls[0] != threading.main_thread().name
    window.close()
    app.processEvents()
