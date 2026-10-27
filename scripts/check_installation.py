"""Offline runtime probe: no Resolve access, model downloads or user media."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    import av
    import ctranslate2
    import faster_whisper
    import numpy
    import onnxruntime
    from PySide6.QtCore import QLibraryInfo, QPluginLoader
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtWidgets import QApplication

    from o_editor.infrastructure.ffmpeg.runner import FFmpegRunner
    from o_editor.ui.main_window import MainWindow

    application = QApplication.instance() or QApplication(["EDE", "-platform", "offscreen"])
    assert application and MainWindow and QAudioOutput and QMediaPlayer and faster_whisper
    plugin = (
        Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)) / "platforms/qwindows.dll"
    )
    loader = QPluginLoader(str(plugin))
    if not loader.load():
        raise RuntimeError("Plugin Windows do Qt indisponivel: " + loader.errorString())
    runner = FFmpegRunner()
    ffmpeg, ffprobe = runner.version(), runner.probe_version()
    if not ffmpeg or not ffprobe:
        raise RuntimeError("FFmpeg/ffprobe integrados nao responderam.")
    print(
        json.dumps(
            {
                "status": "PASSED",
                "python": sys.version.split()[0],
                "numpy": numpy.__version__,
                "av": av.__version__,
                "onnxruntime": onnxruntime.__version__,
                "cpu_compute_types": sorted(ctranslate2.get_supported_compute_types("cpu")),
                "qt_windows_plugin": True,
                "ffmpeg": ffmpeg,
                "ffprobe": ffprobe,
                "resolve_access": False,
                "model_downloads": False,
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
