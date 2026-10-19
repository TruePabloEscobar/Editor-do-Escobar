"""Application composition root."""

from __future__ import annotations

import os
from pathlib import Path

from o_editor.errors import OEditorError
from o_editor.infrastructure.config import AppConfig, load_config
from o_editor.infrastructure.logging import configure_logging


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def user_config_path() -> Path | None:
    """%APPDATA%\\O Editor\\config.json, used when O_EDITOR_CONFIG is not set.

    The setup scripts write FFmpeg and Whisper paths there; without this fallback the
    application launched from Resolve ignored them when the variable was missing.
    """

    if os.environ.get("O_EDITOR_CONFIG"):
        return None
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    candidate = Path(appdata) / "O Editor" / "config.json"
    return candidate if candidate.is_file() else None


def bootstrap() -> AppConfig:
    root = project_root()
    config = load_config(root / "config" / "defaults.json", user_config_path())
    configure_logging(root / "runtime" / "logs", config.app.log_level)
    return config


def run_headless(*, use_mock: bool, context_path: str | None) -> int:
    """Run a safe diagnostic/demo workflow without a Qt event loop."""
    del context_path
    config = bootstrap()
    if not use_mock:
        print("Use --mock para o fluxo headless; o backend real exige diagnóstico.")
        return 2
    try:
        from o_editor.application.analyze_timeline import analyze_with_mock

        result = analyze_with_mock(config, project_root() / "runtime")
    except OEditorError as exc:
        print(f"Falha: {exc}")
        return 1
    print(
        f"Análise concluída em dry-run: {len(result.suggestions)} sugestões, "
        f"fingerprint {result.snapshot.fingerprint[:12]}."
    )
    return 0
