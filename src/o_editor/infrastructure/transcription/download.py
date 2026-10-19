"""Explicit, subprocess-only downloads of data-only CTranslate2 models."""

from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path

from o_editor.errors import ConfigurationError
from o_editor.infrastructure.transcription.local_model import validate_local_model

MODEL_REPOSITORIES = {
    "large-v3-turbo": "dropbox-dash/faster-whisper-large-v3-turbo",
    "large-v3": "Systran/faster-whisper-large-v3",
    "medium": "Systran/faster-whisper-medium",
    "small": "Systran/faster-whisper-small",
    "base": "Systran/faster-whisper-base",
    "tiny": "Systran/faster-whisper-tiny",
}
MODEL_FILES = (
    "model.bin",
    "config.json",
    "tokenizer.json",
    "preprocessor_config.json",
    "vocabulary.json",
    "vocabulary.txt",
)


def models_directory() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    if not value:
        raise ConfigurationError("LOCALAPPDATA não está disponível para guardar modelos.")
    return Path(value) / "Editor Do Escobar" / "models"


def download_model(preset: str, directory: Path) -> Path:
    """Download only on explicit invocation; publish a complete folder atomically.

    Failed/interrupted staging folders are preserved, never selected as models.
    An existing model is never overwritten, including an incomplete user folder.
    """
    if preset not in MODEL_REPOSITORIES:
        raise ConfigurationError("Modelo não disponível no catálogo de download.")
    directory = directory.expanduser().resolve()
    target = directory / preset
    if target.exists():
        return validate_local_model(target)
    directory.mkdir(parents=True, exist_ok=True)
    stage = directory / f".{preset}-download-{uuid.uuid4().hex}"
    stage.mkdir()
    from huggingface_hub import snapshot_download

    snapshot_download(
        MODEL_REPOSITORIES[preset],
        local_dir=str(stage),
        allow_patterns=list(MODEL_FILES),
        token=False,
        max_workers=2,
    )
    validate_local_model(stage)
    # rename must refuse a concurrent installation rather than replace its files.
    stage.rename(target)
    return validate_local_model(target)


def main() -> int:
    parser = argparse.ArgumentParser(description="Download de modelo solicitado pelo usuário")
    parser.add_argument("--preset", required=True, choices=MODEL_REPOSITORIES)
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    try:
        path = download_model(args.preset, args.directory or models_directory())
    except Exception as exc:
        # Subprocess boundary: no raw remote response, token, or traceback in the UI.
        print(json.dumps({"ok": False, "error_type": type(exc).__name__}), flush=True)
        return 1
    print(json.dumps({"ok": True, "path": str(path)}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
