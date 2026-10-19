"""Safe Qt runtime environment adjustments for headless validation."""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path


def configure_headless_qt_environment(
    environment: MutableMapping[str, str] | None = None,
) -> None:
    target = environment if environment is not None else os.environ
    target.setdefault("QT_QPA_PLATFORM", "offscreen")
    if target.get("QT_QPA_FONTDIR"):
        return
    windows_directory = target.get("WINDIR")
    if not windows_directory:
        return
    font_directory = Path(windows_directory) / "Fonts"
    if font_directory.is_dir():
        target["QT_QPA_FONTDIR"] = str(font_directory)
