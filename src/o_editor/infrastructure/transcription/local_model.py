"""Local CTranslate2 model validation and cheap, file-aware cache identity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from o_editor.errors import ConfigurationError


def validate_local_model(path: Path) -> Path:
    """Require self-contained files so tokenizer fallback cannot trigger a download."""
    path = path.expanduser().resolve()
    for name in ("model.bin", "config.json", "tokenizer.json"):
        candidate = path / name
        if not candidate.is_file() or candidate.stat().st_size == 0:
            raise ConfigurationError(f"Selecione uma pasta faster-whisper/CTranslate2 com {name}.")
    try:
        config = json.loads((path / "config.json").read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("config.json deve conter um objeto")
    except (OSError, ValueError) as exc:
        raise ConfigurationError("O config.json do modelo é inválido.") from exc
    return path


def local_model_identity(path: Path | None, name: str) -> str:
    """Invalidate after a path or model-file replacement, without reading model weights."""
    parts = [name, str(path.resolve()) if path else "unconfigured"]
    if path:
        for filename in ("model.bin", "config.json", "tokenizer.json", "preprocessor_config.json"):
            try:
                stat = (path / filename).stat()
                parts.append(f"{filename}:{stat.st_size}:{stat.st_mtime_ns}:{stat.st_ctime_ns}")
            except OSError:
                parts.append(f"{filename}:missing")
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()
