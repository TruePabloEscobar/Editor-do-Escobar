"""Export editable TXT transcripts and import edited ones back into the session."""

from __future__ import annotations

import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from o_editor.domain.speech import TranscriptSession
from o_editor.domain.transcript_document import (
    SCOPE_ALL,
    ImportReview,
    Issue,
    Severity,
    apply_review,
    parse_transcript,
    record_export,
    render_transcript,
    resolve_missing,
    review_import,
)
from o_editor.errors import OEditorError
from o_editor.infrastructure.transcript_sessions import SessionStore, SessionStoreError

MAX_IMPORT_BYTES = 50 * 1024 * 1024


class TranscriptExchangeError(OEditorError):
    """Export or import of a transcript failed."""


@dataclass(frozen=True, slots=True)
class ExportResult:
    session: TranscriptSession
    files: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class ImportPreview:
    path: Path
    session: TranscriptSession
    review: ImportReview

    @property
    def blocked(self) -> bool:
        return self.review.blocked

    def summary_lines(self) -> tuple[str, ...]:
        review = self.review
        newly_cut = review.newly_cut(self.session)
        restored = review.restored(self.session)
        lines = [
            f"Arquivo: {self.path.name}",
            f"Escopo: {'todas as faixas' if review.scope == SCOPE_ALL else review.scope}",
            f"Trechos esperados: {review.expected_count}; lidos: {len(review.states)}",
            f"Marcados como CUT: {len(review.cut_ids)} (novos: {len(newly_cut)})",
            f"Restaurados para KEEP: {len(restored)}",
            f"Correções de texto: {len(review.corrections)}",
            f"Ausentes (exigem confirmação): {len(review.missing)}",
        ]
        if review.blocked:
            lines.append("IMPORTAÇÃO BLOQUEADA — resolva os problemas abaixo; nada foi alterado.")
        lines.extend(issue.render() for issue in review.issues)
        return tuple(lines)


def export_transcripts(
    session: TranscriptSession,
    directory: Path,
    store: SessionStore,
    *,
    base_name: str | None = None,
) -> ExportResult:
    """Write one TXT per transcribed track plus the chronological consolidated file."""

    directory.mkdir(parents=True, exist_ok=True)
    base = safe_file_part(base_name or session.timeline_name) or "Transcricao"
    now = datetime.now(UTC).isoformat()
    files: list[Path] = []
    updated = session
    targets: list[tuple[str, str]] = [
        (f"A{track.track_index}", f"{base}_{safe_file_part(track.name) or track.key}.txt")
        for track in session.tracks
    ]
    targets.append((SCOPE_ALL, f"{base}_Completo.txt"))
    used: set[str] = set()
    for scope, name in targets:
        file_name = name
        counter = 2
        while file_name.casefold() in used:
            file_name = name.replace(".txt", f"_{counter}.txt")
            counter += 1
        used.add(file_name.casefold())
        content, ids, checksum = render_transcript(updated, scope, include_bleed=scope != SCOPE_ALL)
        path = directory / file_name
        _atomic_text(path, content)
        updated = record_export(
            updated,
            file_name=file_name,
            scope=scope,
            segment_ids=ids,
            checksum=checksum,
            exported_at=now,
        )
        files.append(path)
    store.save(updated)
    return ExportResult(session=updated, files=tuple(files))


def preview_import(path: Path, store: SessionStore) -> ImportPreview:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise TranscriptExchangeError(f"Não foi possível abrir {path}.") from exc
    if size > MAX_IMPORT_BYTES:
        raise TranscriptExchangeError("O arquivo é grande demais para ser uma transcrição.")
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("cp1252")
        except UnicodeDecodeError as exc:
            raise TranscriptExchangeError(
                "O arquivo não está em UTF-8 nem em Windows-1252."
            ) from exc
    except OSError as exc:
        raise TranscriptExchangeError(f"Não foi possível ler {path}.") from exc
    document = parse_transcript(text)
    session_id = document.session_id
    if not session_id:
        raise TranscriptExchangeError(
            "O arquivo não contém a linha @SESSION. Ele não foi exportado pelo O Editor ou o "
            "cabeçalho foi removido."
        )
    try:
        session = store.load(session_id)
    except SessionStoreError as exc:
        raise TranscriptExchangeError(str(exc)) from exc
    review = review_import(document, session)
    if text != raw.decode("utf-8-sig", errors="ignore"):
        review = ImportReview(
            session_id=review.session_id,
            revision=review.revision,
            scope=review.scope,
            issues=(
                *review.issues,
                Issue(Severity.WARNING, "ENCODING", "O arquivo foi lido como Windows-1252."),
            ),
            states=review.states,
            corrections=review.corrections,
            flag_changes=review.flag_changes,
            missing=review.missing,
            expected_count=review.expected_count,
        )
    return ImportPreview(path=path, session=session, review=review)


def confirm_import(preview: ImportPreview, store: SessionStore) -> TranscriptSession:
    if preview.blocked:
        raise TranscriptExchangeError(
            "A importação está bloqueada; nenhuma alteração foi aplicada."
        )
    current = store.load(preview.session.session_id)
    if (
        current.revision != preview.session.revision
        or current.updated_at != preview.session.updated_at
    ):
        raise TranscriptExchangeError(
            "A sessão foi alterada depois da prévia. Importe o arquivo novamente."
        )
    updated = apply_review(
        current,
        preview.review,
        imported_at=datetime.now(UTC).isoformat(),
        source_name=preview.path.name,
    )
    store.save(updated)
    return updated


def decide_missing(
    session: TranscriptSession, store: SessionStore, *, remove: bool
) -> TranscriptSession:
    updated = resolve_missing(session, remove=remove, updated_at=datetime.now(UTC).isoformat())
    store.save(updated)
    return updated


def safe_file_part(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(char for char in decomposed if not unicodedata.combining(char))
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", ascii_text).strip("_")
    return cleaned[:60]


def _atomic_text(path: Path, content: str) -> None:
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=".oe-", suffix=".tmp", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\r\n") as handle:
            handle.write(content)
        os.replace(temporary, path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise TranscriptExchangeError(f"Não foi possível gravar {path}.") from exc
