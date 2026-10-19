"""Runtime-only FFmpeg discovery."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from o_editor.errors import OEditorError


class FFmpegError(OEditorError):
    """FFmpeg is unavailable or failed."""


class FFmpegRunner:
    def __init__(
        self,
        configured_paths: tuple[Path, ...] = (),
        *,
        ffmpeg_path: Path | None = None,
        ffprobe_path: Path | None = None,
    ) -> None:
        self._configured_paths = configured_paths
        self._ffmpeg_path = ffmpeg_path
        self._ffprobe_path = ffprobe_path

    def find(self) -> Path | None:
        return self._find_executable("ffmpeg", "FFMPEG_PATH", self._ffmpeg_path)

    def find_probe(self) -> Path | None:
        return self._find_executable("ffprobe", "FFPROBE_PATH", self._ffprobe_path)

    def _find_executable(
        self,
        name: str,
        environment_name: str,
        explicit_path: Path | None,
    ) -> Path | None:
        candidates: list[Path] = []
        if explicit_path:
            candidates.append(explicit_path)
        configured = os.environ.get(environment_name)
        if configured:
            candidates.append(Path(configured))
        for configured_path in self._configured_paths:
            candidates.append(
                configured_path / f"{name}.exe"
                if configured_path.is_dir()
                else configured_path.with_name(f"{name}.exe")
            )
        discovered = shutil.which(name)
        if discovered:
            candidates.append(Path(discovered))
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()
        return None

    def version(self) -> str | None:
        return self._version(self.find(), "FFmpeg")

    def probe_version(self) -> str | None:
        return self._version(self.find_probe(), "FFprobe")

    @staticmethod
    def _version(executable: Path | None, label: str) -> str | None:
        if executable is None:
            return None
        try:
            result = subprocess.run(
                [str(executable), "-version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise FFmpegError(f"O {label} foi encontrado, mas não respondeu.") from exc
        first_line = result.stdout.splitlines()
        return first_line[0] if result.returncode == 0 and first_line else None
