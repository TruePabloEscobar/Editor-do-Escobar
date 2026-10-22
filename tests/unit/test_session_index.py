"""BUG-0030: opening a timeline must not deserialize every stored session.

The real profile had a single 11.8 MB session of another timeline; it was fully
parsed (JSON + 49k word objects) on every startup/context change before the fix.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from o_editor.domain.speech import TranscriptSession
from o_editor.infrastructure.transcript_sessions import SessionStore
from tests.fixtures.podcast import podcast_session


def _session(index: int, timeline: str, updated: str) -> TranscriptSession:
    return replace(
        podcast_session(session_id=f"{index:016x}"),
        timeline_name=timeline,
        updated_at=updated,
    )


@pytest.fixture()
def store(tmp_path: Path) -> SessionStore:
    store = SessionStore(tmp_path / "sessions")
    for index, (timeline, updated) in enumerate(
        [
            ("Outra A", "2026-10-19T10:00:00+00:00"),
            ("Episodio 1", "2026-10-19T11:00:00+00:00"),
            ("Outra B", "2026-10-19T12:00:00+00:00"),
            ("Episodio 1", "2026-10-19T13:00:00+00:00"),
            ("Outra C", "2026-10-19T14:00:00+00:00"),
        ],
        start=1,
    ):
        store.save(_session(index, timeline, updated))
    return store


def _count_from_dict(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls = [0]
    original = TranscriptSession.from_dict.__func__  # type: ignore[attr-defined]

    def counting(cls: type[TranscriptSession], value: object) -> TranscriptSession:
        calls[0] += 1
        return original(cls, value)  # type: ignore[no-any-return]

    monkeypatch.setattr(TranscriptSession, "from_dict", classmethod(counting))
    return calls


def test_latest_session_loads_only_the_chosen_one(
    store: SessionStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _count_from_dict(monkeypatch)
    found = store.latest_for("Podcast", "Episodio 1")
    assert found is not None and found.session_id == f"{4:016x}"
    assert calls[0] == 1
    assert store.latest_for("Podcast", "Inexistente") is None
    assert calls[0] == 1


def test_index_heals_from_external_changes(store: SessionStore, tmp_path: Path) -> None:
    index = store.root / "index.json"
    # Session written by an older version (no index update) is still found.
    newer = _session(9, "Episodio 1", "2026-10-20T09:00:00+00:00")
    directory = store.root / newer.session_id
    directory.mkdir(parents=True)
    (directory / "session.json").write_text(json.dumps(newer.to_dict()), encoding="utf-8")
    assert store.latest_for("Podcast", "Episodio 1") == newer
    # An edited session (new mtime) is re-read; a corrupt index is rebuilt.
    edited = replace(newer, timeline_name="Renomeada")
    path = directory / "session.json"
    path.write_text(json.dumps(edited.to_dict()), encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    assert store.latest_for("Podcast", "Renomeada") == edited
    assert store.latest_for("Podcast", "Episodio 1").session_id == f"{4:016x}"
    index.write_text("{corrompido", encoding="utf-8")
    assert store.latest_for("Podcast", "Episodio 1").session_id == f"{4:016x}"
    assert json.loads(index.read_text(encoding="utf-8"))["schema_version"] == 1


def test_corrupt_session_is_skipped(store: SessionStore) -> None:
    (store.root / f"{4:016x}" / "session.json").write_text("{", encoding="utf-8")
    found = store.latest_for("Podcast", "Episodio 1")
    assert found is not None and found.session_id == f"{2:016x}"
