"""Fingerprint-keyed JSON cache with atomic writes."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from o_editor.errors import OEditorError


class CacheError(OEditorError):
    """Cache data could not be safely read or written."""


class JsonCache:
    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        return self._root

    @staticmethod
    def make_key(*parts: str) -> str:
        normalized = "\x1f".join(parts)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def path_for(self, namespace: str, key: str) -> Path:
        safe_namespace = "".join(char for char in namespace if char.isalnum() or char in "-_")
        if not safe_namespace:
            raise CacheError("Namespace de cache inválido.")
        return self._root / safe_namespace / f"{key}.json"

    def load(self, namespace: str, key: str) -> dict[str, Any] | None:
        path = self.path_for(namespace, key)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CacheError(f"Cache inválido: {path.name}") from exc
        if not isinstance(value, dict):
            raise CacheError(f"Cache inválido: {path.name}")
        return value

    def save(self, namespace: str, key: str, value: dict[str, Any]) -> Path:
        path = self.path_for(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            descriptor, temp_name = tempfile.mkstemp(
                prefix="oe_cache_",
                suffix=".tmp",
                dir=path.parent,
            )
            temporary = Path(temp_name)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(path)
        except OSError as exc:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise CacheError(f"Não foi possível gravar o cache: {path.name}") from exc
        return path


def default_app_cache_root() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise CacheError("APPDATA não está disponível para o cache local.")
    return Path(appdata) / "O Editor" / "cache"
