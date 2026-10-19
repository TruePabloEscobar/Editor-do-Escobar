from __future__ import annotations

import json
from pathlib import Path

import pytest

from o_editor.infrastructure.cache import CacheError, JsonCache, default_app_cache_root


def test_cache_round_trip_is_atomic(tmp_path) -> None:
    cache = JsonCache(tmp_path)
    key = cache.make_key("timeline", "fingerprint")
    path = cache.save("transcripts", key, {"value": 42})
    assert cache.load("transcripts", key) == {"value": 42}
    assert path.is_file()
    assert not list(path.parent.glob("*.tmp"))


def test_invalid_cache_is_reported(tmp_path) -> None:
    cache = JsonCache(tmp_path)
    key = cache.make_key("broken")
    path = cache.path_for("transcripts", key)
    path.parent.mkdir(parents=True)
    path.write_text("{", encoding="utf-8")
    with pytest.raises(CacheError, match="Cache inválido"):
        cache.load("transcripts", key)


def test_cache_file_contains_valid_json(tmp_path) -> None:
    cache = JsonCache(tmp_path)
    path = cache.save("analysis", "abc", {"schema_version": "1.0"})
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == "1.0"


def test_default_cache_root_uses_appdata(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))

    assert default_app_cache_root() == tmp_path / "O Editor" / "cache"
