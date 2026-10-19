"""Directory cache for selected voice-track audio and metadata."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from o_editor.infrastructure.cache import CacheError


class VoiceAudioCache:
    def __init__(self, root: Path) -> None:
        self._root = root

    def directory(self, key: str) -> Path:
        if len(key) != 64 or any(character not in "0123456789abcdef" for character in key):
            raise CacheError("Chave de cache de áudio de voz inválida.")
        return self._root / "audio" / key

    def audio_path(self, key: str) -> Path:
        return self.directory(key) / "voice.wav"

    def metadata_path(self, key: str) -> Path:
        return self.directory(key) / "metadata.json"

    def is_hit(self, key: str, expected_metadata: dict[str, Any]) -> bool:
        audio = self.audio_path(key)
        metadata = self.metadata_path(key)
        if not audio.is_file() or audio.stat().st_size <= 44 or not metadata.is_file():
            return False
        try:
            value = json.loads(metadata.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return False
        return bool(value == expected_metadata)

    def save_metadata(self, key: str, metadata: dict[str, Any]) -> Path:
        path = self.metadata_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            descriptor, name = tempfile.mkstemp(
                prefix="voice-cache-", suffix=".tmp", dir=path.parent
            )
            temporary = Path(name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(metadata, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(path)
        except OSError as exc:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise CacheError("Não foi possível salvar os metadados do áudio de voz.") from exc
        return path
