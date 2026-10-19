"""Atomic JSON persistence for transcript sessions (the TXT round-trip manifest)."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from o_editor.domain.speech import TranscriptSession
from o_editor.errors import OEditorError

_SESSION_ID = re.compile(r"^[0-9a-f]{12,64}$")


class SessionStoreError(OEditorError):
    """A transcript session could not be read or written."""


def default_sessions_root() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise SessionStoreError("APPDATA não está disponível para salvar a sessão de transcrição.")
    return Path(appdata) / "O Editor" / "sessions"


class SessionStore:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or default_sessions_root()

    @property
    def root(self) -> Path:
        return self._root

    def directory(self, session_id: str) -> Path:
        if not _SESSION_ID.match(session_id):
            raise SessionStoreError("Identificador de sessão inválido.")
        return self._root / session_id

    def save(self, session: TranscriptSession) -> Path:
        directory = self.directory(session.session_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "session.json"
        history = directory / "history" / f"rev-{session.revision:04d}.json"
        payload = json.dumps(session.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        _atomic_write(path, payload)
        history.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(history, payload)
        return path

    def load(self, session_id: str) -> TranscriptSession:
        path = self.directory(session_id) / "session.json"
        if not path.is_file():
            raise SessionStoreError(
                "A sessão de transcrição deste TXT não foi encontrada neste computador. "
                "Importe o TXT na mesma instalação em que ele foi exportado."
            )
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return TranscriptSession.from_dict(value)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise SessionStoreError(f"A sessão {session_id} está corrompida.") from exc

    def latest_for(self, project_name: str, timeline_name: str) -> TranscriptSession | None:
        if not self._root.is_dir():
            return None
        best: TranscriptSession | None = None
        for path in self._root.glob("*/session.json"):
            try:
                session = TranscriptSession.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
            if session.project_name != project_name or session.timeline_name != timeline_name:
                continue
            if best is None or session.updated_at > best.updated_at:
                best = session
        return best

    def write_artifact(self, session_id: str, name: str, content: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
        path = self.directory(session_id) / safe
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, content)
        return path


def _atomic_write(path: Path, content: str) -> None:
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=".oe-", suffix=".tmp", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise SessionStoreError(f"Não foi possível gravar {path.name}.") from exc
