"""Atomic JSON persistence for transcript sessions (the TXT round-trip manifest)."""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from pathlib import Path

from o_editor.domain.speech import TranscriptSession
from o_editor.errors import OEditorError

_SESSION_ID = re.compile(r"^[0-9a-f]{12,64}$")
INDEX_NAME = "index.json"
INDEX_SCHEMA = 1


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
        self._remember(session, path)
        return path

    def _remember(self, session: TranscriptSession, path: Path) -> None:
        """Keep the index current after our own writes (best effort)."""

        index_path = self._root / INDEX_NAME
        try:
            value = json.loads(index_path.read_text(encoding="utf-8"))
            sessions = value.get("sessions") if isinstance(value, dict) else None
            if not isinstance(value, dict) or value.get("schema_version") != INDEX_SCHEMA:
                return
            if not isinstance(sessions, dict):
                return
            stat = path.stat()
            sessions[session.session_id] = {
                "project_name": session.project_name,
                "timeline_name": session.timeline_name,
                "updated_at": session.updated_at,
                "mtime_ns": stat.st_mtime_ns,
                "size": stat.st_size,
            }
            _atomic_write(index_path, json.dumps(value, ensure_ascii=False, sort_keys=True))
        except (OSError, UnicodeError, json.JSONDecodeError, SessionStoreError):
            return

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
        """Most recent session of a timeline, deserializing only the chosen one.

        A small index (``index.json``) keeps project, timeline and update time per
        session; entries are re-read only when ``session.json`` changed on disk
        (size or mtime), so sessions written by older versions are still found.
        """

        entries = self._refresh_index()
        candidates = sorted(
            (
                (str(entry["updated_at"]), session_id)
                for session_id, entry in entries.items()
                if entry.get("project_name") == project_name
                and entry.get("timeline_name") == timeline_name
            ),
            reverse=True,
        )
        for _updated, session_id in candidates:
            try:
                session = self.load(session_id)
            except SessionStoreError:
                continue
            if session.project_name == project_name and session.timeline_name == timeline_name:
                return session
        return None

    def _refresh_index(self) -> dict[str, dict[str, object]]:
        if not self._root.is_dir():
            return {}
        index_path = self._root / INDEX_NAME
        stored: dict[str, dict[str, object]] = {}
        try:
            value = json.loads(index_path.read_text(encoding="utf-8"))
            if isinstance(value, dict) and value.get("schema_version") == INDEX_SCHEMA:
                raw = value.get("sessions")
                if isinstance(raw, dict):
                    stored = {str(key): item for key, item in raw.items() if isinstance(item, dict)}
        except (OSError, UnicodeError, json.JSONDecodeError):
            stored = {}
        entries: dict[str, dict[str, object]] = {}
        changed = False
        for directory in self._root.iterdir():
            path = directory / "session.json"
            if not _SESSION_ID.match(directory.name) or not path.is_file():
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            previous = stored.get(directory.name)
            if (
                previous is not None
                and previous.get("mtime_ns") == stat.st_mtime_ns
                and previous.get("size") == stat.st_size
            ):
                entries[directory.name] = previous
                continue
            header = _read_header(path)
            changed = True
            if header is None:
                continue
            entries[directory.name] = {**header, "mtime_ns": stat.st_mtime_ns, "size": stat.st_size}
        if changed or set(entries) != set(stored):
            payload = json.dumps(
                {"schema_version": INDEX_SCHEMA, "sessions": entries},
                ensure_ascii=False,
                sort_keys=True,
            )
            # The index is only an accelerator; a failed write is rebuilt later.
            with contextlib.suppress(SessionStoreError):
                _atomic_write(index_path, payload)
        return entries

    def write_artifact(self, session_id: str, name: str, content: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
        path = self.directory(session_id) / safe
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, content)
        return path


def _read_header(path: Path) -> dict[str, object] | None:
    """Identity fields of a session file without building the domain objects."""

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    try:
        return {
            "project_name": str(value["project_name"]),
            "timeline_name": str(value["timeline_name"]),
            "updated_at": str(value.get("updated_at") or value["created_at"]),
        }
    except KeyError:
        return None


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
