"""Human/AI-editable TXT transcript format: rendering, tolerant parsing and review.

The identifiers and the original frame ranges stored in the session are the only
reference for editing. Text may be corrected freely; timing, IDs and track binding
may not change. Anything ambiguous blocks the import instead of cutting silently.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from o_editor.domain.speech import (
    SegmentFlag,
    SegmentState,
    SpeechSegment,
    TranscriptSession,
    chronological,
    mark_overlaps,
)
from o_editor.domain.timecode import frames_to_clock, parse_clock

FORMAT_VERSION = "1"
SCOPE_ALL = "ALL"

STATE_SYNONYMS = {
    "KEEP": SegmentState.KEEP,
    "MANTER": SegmentState.KEEP,
    "MANTIDO": SegmentState.KEEP,
    "MANTEM": SegmentState.KEEP,
    "CUT": SegmentState.CUT,
    "CORTAR": SegmentState.CUT,
    "CORTE": SegmentState.CUT,
    "REMOVER": SegmentState.CUT,
    "REMOVE": SegmentState.CUT,
    "DELETE": SegmentState.CUT,
}
FLAG_SYNONYMS = {flag.value: flag for flag in SegmentFlag}

INSTRUCTIONS = (
    "INSTRUÇÕES PARA EDIÇÃO (pessoas e inteligências artificiais):",
    "1. Cada trecho começa com uma linha de cabeçalho:",
    "   [ID] [FAIXA: Participante] [início --> fim] [ESTADO]",
    "   seguida pelo texto falado na(s) linha(s) abaixo.",
    "2. Para remover um trecho, troque [KEEP] por [CUT]. Para mantê-lo, deixe [KEEP].",
    "3. NÃO altere, NÃO crie e NÃO apague IDs (SEG_0001...), faixas (A1, A2...) nem tempos.",
    "4. NÃO reordene, NÃO junte e NÃO divida trechos.",
    "5. Você pode corrigir palavras do texto. Corrigir o texto NÃO altera o áudio.",
    "6. Não apague trechos inteiros: marque-os como [CUT]. Trechos ausentes exigirão",
    "   confirmação manual antes de qualquer corte.",
    "7. Mantenha todas as linhas que começam com @ exatamente como estão, incluindo @END.",
    "8. Linhas que começam com # são comentários e são ignoradas.",
    "9. Devolva o arquivo completo, em texto puro, sem resumir.",
    "Sugestão de pedido para uma IA: 'Marque como [CUT] repetições, falsos começos,",
    "erros de gravação e assuntos irrelevantes. Preserve todo o restante do arquivo.'",
)


class Severity(StrEnum):
    BLOCKER = "BLOQUEIO"
    WARNING = "AVISO"
    INFO = "INFO"


@dataclass(frozen=True, slots=True)
class Issue:
    severity: Severity
    code: str
    message: str
    segment_id: str | None = None
    line: int | None = None

    def render(self) -> str:
        where = f" (linha {self.line})" if self.line else ""
        return f"[{self.severity.value}] {self.message}{where}"


# --------------------------------------------------------------------------- rendering


def scope_segments(
    session: TranscriptSession, scope: str, *, include_bleed: bool | None = None
) -> tuple[SpeechSegment, ...]:
    if scope == SCOPE_ALL:
        bleed_allowed = False if include_bleed is None else include_bleed
        return tuple(
            item for item in chronological(session.segments) if bleed_allowed or not item.is_bleed
        )
    track_index = _scope_track(scope)
    return tuple(
        item for item in chronological(session.segments) if item.track_index == track_index
    )


def render_transcript(
    session: TranscriptSession,
    scope: str = SCOPE_ALL,
    *,
    include_bleed: bool | None = None,
) -> tuple[str, tuple[str, ...], str]:
    """Return (text, exported segment ids, checksum)."""

    segments = scope_segments(session, scope, include_bleed=include_bleed)
    ids = tuple(item.segment_id for item in segments)
    checksum = session.structure_checksum(ids)
    participants = "; ".join(f"{track.key}={track.name}" for track in session.tracks)
    omitted = 0
    if scope == SCOPE_ALL and not include_bleed:
        omitted = sum(1 for item in session.segments if item.is_bleed)
    lines: list[str] = ["# O EDITOR — TRANSCRIÇÃO EDITÁVEL", "#" + "=" * 70]
    lines.extend(f"# {line}" for line in INSTRUCTIONS)
    lines.append("#" + "=" * 70)
    lines.append(
        "# Os tempos são posições na timeline contadas a partir do início dela "
        f"(início da timeline = TC {session.start_timecode or '00:00:00:00'})."
    )
    if omitted:
        lines.append(
            f"# {omitted} trecho(s) identificado(s) como vazamento entre microfones foram "
            "omitidos aqui; eles aparecem nos arquivos individuais de cada faixa."
        )
    lines.extend(
        [
            f"@OE_TRANSCRIPT {FORMAT_VERSION}",
            f"@SESSION {session.session_id}",
            f"@REVISION {session.revision}",
            f"@PROJECT {session.project_name}",
            f"@TIMELINE {session.timeline_name}",
            f"@TIMELINE_ID {session.timeline_id or '-'}",
            f"@FPS {session.fps:g}",
            f"@TIMELINE_START {session.start_timecode or '-'}",
            f"@SCOPE {scope}",
            f"@PARTICIPANTS {participants}",
            f"@SEGMENTS {len(segments)}",
            f"@CHECKSUM {checksum}",
            "@BEGIN",
            "",
        ]
    )
    for segment in segments:
        lines.append(segment_header(session, segment))
        lines.append(segment.text or "")
        lines.append("")
    lines.append(f"@END {len(segments)}")
    lines.append("")
    return "\n".join(lines), ids, checksum


def segment_header(session: TranscriptSession, segment: SpeechSegment) -> str:
    start = frames_to_clock(segment.start_frame - session.start_frame, session.fps)
    end = frames_to_clock(segment.end_frame - session.start_frame, session.fps)
    speaker = session.speaker_name(segment.track_index)
    header = (
        f"[{segment.segment_id}] [{segment.track_key}: {speaker}] "
        f"[{start} --> {end}] [{segment.state.value}]"
    )
    visible_flags = sorted(flag.value for flag in segment.flags)
    if visible_flags:
        header += f" [FLAGS: {', '.join(visible_flags)}]"
    return header


# --------------------------------------------------------------------------- parsing


_HEADER_LINE = re.compile(r"^@([A-Z_]+)\s*(.*)$")
_SEGMENT_START = re.compile(r"^\s*\[\s*(?:ID\s*:\s*)?SEG", re.IGNORECASE)
_SEGMENT_LINE = re.compile(
    r"^\s*\[\s*(?:ID\s*:\s*)?(?P<id>SEG_\d+)\s*\]\s*"
    r"\[\s*(?P<track>[AaVv]\d+)\s*(?::\s*(?P<speaker>[^\]]*))?\]\s*"
    r"\[\s*(?P<start>[0-9:.,]+)\s*(?:-->|->|\u2192|\u2014>|=>|\u2013|\u2014|-)\s*(?P<end>[0-9:.,]+)\s*\]\s*"
    r"\[\s*(?P<state>[^\]]+?)\s*\]\s*"
    r"(?:\[\s*FLAGS?\s*:\s*(?P<flags>[^\]]*)\]\s*)?"
    r"(?P<rest>.*)$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class ParsedSegment:
    segment_id: str
    track_key: str
    speaker: str
    start_text: str
    end_text: str
    state_text: str
    flags_text: str | None
    text: str
    line: int


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    header: Mapping[str, str]
    segments: tuple[ParsedSegment, ...]
    has_begin: bool
    has_end: bool
    end_count: int | None
    issues: tuple[Issue, ...]

    @property
    def session_id(self) -> str | None:
        return self.header.get("SESSION")


def parse_transcript(text: str) -> ParsedDocument:
    issues: list[Issue] = []
    header: dict[str, str] = {}
    segments: list[ParsedSegment] = []
    has_begin = False
    has_end = False
    end_count: int | None = None
    current: dict[str, Any] | None = None
    body_lines: list[str] = []
    ignored_outside = 0

    def flush() -> None:
        nonlocal current, body_lines
        if current is not None:
            segments.append(
                ParsedSegment(
                    segment_id=current["id"],
                    track_key=current["track"],
                    speaker=current["speaker"],
                    start_text=current["start"],
                    end_text=current["end"],
                    state_text=current["state"],
                    flags_text=current["flags"],
                    text=" ".join(" ".join(body_lines).split()),
                    line=current["line"],
                )
            )
        current = None
        body_lines = []

    cleaned = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    for number, original in enumerate(cleaned.split("\n"), start=1):
        line = original.strip()
        if line.startswith("```"):
            continue
        candidate = _strip_markdown(line)
        if not candidate:
            continue
        if candidate.startswith("#"):
            continue
        header_match = _HEADER_LINE.match(candidate)
        if header_match:
            key, value = header_match.group(1).upper(), header_match.group(2).strip()
            if key == "BEGIN":
                if has_begin:
                    issues.append(
                        Issue(
                            Severity.BLOCKER,
                            "DUPLICATE_BEGIN",
                            "@BEGIN aparece mais de uma vez.",
                            line=number,
                        )
                    )
                has_begin = True
                continue
            if key == "END":
                flush()
                if has_end:
                    issues.append(
                        Issue(
                            Severity.BLOCKER,
                            "DUPLICATE_END",
                            "@END aparece mais de uma vez.",
                            line=number,
                        )
                    )
                has_end = True
                try:
                    end_count = int(value) if value else None
                except ValueError:
                    end_count = None
                continue
            if has_begin and not has_end:
                issues.append(
                    Issue(
                        Severity.WARNING,
                        "HEADER_IN_BODY",
                        f"Linha @{key} dentro do corpo foi ignorada.",
                        line=number,
                    )
                )
                continue
            header[key] = value
            continue
        if has_end:
            ignored_outside += 1
            continue
        if _SEGMENT_START.match(candidate):
            flush()
            match = _SEGMENT_LINE.match(candidate)
            if not match:
                issues.append(
                    Issue(
                        Severity.BLOCKER,
                        "MALFORMED_SEGMENT",
                        f"Cabeçalho de trecho malformado: {candidate[:80]}",
                        line=number,
                    )
                )
                continue
            if not has_begin:
                issues.append(
                    Issue(
                        Severity.BLOCKER,
                        "SEGMENT_BEFORE_BEGIN",
                        "Trecho encontrado antes de @BEGIN.",
                        line=number,
                    )
                )
            current = {
                "id": match.group("id").upper(),
                "track": match.group("track").upper(),
                "speaker": (match.group("speaker") or "").strip(),
                "start": match.group("start"),
                "end": match.group("end"),
                "state": match.group("state").strip(),
                "flags": match.group("flags"),
                "line": number,
            }
            rest = (match.group("rest") or "").strip()
            if rest:
                body_lines.append(rest)
            continue
        if current is not None:
            body_lines.append(line)
        elif has_begin:
            issues.append(
                Issue(
                    Severity.WARNING,
                    "ORPHAN_TEXT",
                    "Texto fora de qualquer trecho foi ignorado.",
                    line=number,
                )
            )
        else:
            ignored_outside += 1
    flush()
    if ignored_outside:
        issues.append(
            Issue(
                Severity.INFO,
                "OUTSIDE_TEXT",
                f"{ignored_outside} linha(s) fora do bloco @BEGIN/@END foram ignoradas.",
            )
        )
    return ParsedDocument(
        header=header,
        segments=tuple(segments),
        has_begin=has_begin,
        has_end=has_end,
        end_count=end_count,
        issues=tuple(issues),
    )


def _strip_markdown(line: str) -> str:
    value = line.replace("**", "").replace("__", "").strip()
    value = re.sub(r"^(?:[-*+]\s+|>\s*)", "", value)
    if value.startswith("`") and value.endswith("`") and len(value) > 1:
        value = value.strip("`")
    return value.strip()


# --------------------------------------------------------------------------- review


@dataclass(frozen=True, slots=True)
class ImportReview:
    session_id: str
    revision: int
    scope: str
    issues: tuple[Issue, ...]
    states: Mapping[str, SegmentState] = field(default_factory=dict)
    corrections: Mapping[str, str] = field(default_factory=dict)
    flag_changes: Mapping[str, frozenset[SegmentFlag]] = field(default_factory=dict)
    missing: tuple[str, ...] = ()
    expected_count: int = 0

    @property
    def blocked(self) -> bool:
        return any(issue.severity == Severity.BLOCKER for issue in self.issues)

    @property
    def cut_ids(self) -> tuple[str, ...]:
        return tuple(key for key, value in self.states.items() if value == SegmentState.CUT)

    def newly_cut(self, session: TranscriptSession) -> tuple[str, ...]:
        result = []
        for key, value in self.states.items():
            segment = session.segment(key)
            if segment is not None and value == SegmentState.CUT and segment.state != value:
                result.append(key)
        return tuple(result)

    def restored(self, session: TranscriptSession) -> tuple[str, ...]:
        result = []
        for key, value in self.states.items():
            segment = session.segment(key)
            if segment is not None and value == SegmentState.KEEP and segment.state != value:
                result.append(key)
        return tuple(result)


def review_import(
    document: ParsedDocument,
    session: TranscriptSession,
    *,
    tolerance_frames: float = 1.0,
) -> ImportReview:
    issues = list(document.issues)
    header = document.header
    scope = header.get("SCOPE", "").upper() or SCOPE_ALL

    def block(
        code: str, message: str, segment_id: str | None = None, line: int | None = None
    ) -> None:
        issues.append(Issue(Severity.BLOCKER, code, message, segment_id, line))

    def warn(
        code: str, message: str, segment_id: str | None = None, line: int | None = None
    ) -> None:
        issues.append(Issue(Severity.WARNING, code, message, segment_id, line))

    if header.get("OE_TRANSCRIPT") != FORMAT_VERSION:
        block(
            "FORMAT",
            "O arquivo não é uma transcrição exportada pelo O Editor (linha "
            "@OE_TRANSCRIPT ausente ou alterada).",
        )
    if header.get("SESSION") != session.session_id:
        block("SESSION", "O arquivo pertence a outra sessão de transcrição.")
    revision_text = header.get("REVISION", "")
    if revision_text != str(session.revision):
        block(
            "REVISION",
            f"O arquivo foi exportado da revisão {revision_text or '?'} da transcrição, mas a "
            f"sessão está na revisão {session.revision}. Exporte novamente.",
        )
    if not document.has_begin:
        block("NO_BEGIN", "A linha @BEGIN está ausente.")
    if not document.has_end:
        block("TRUNCATED", "A linha final @END está ausente: o arquivo pode estar truncado.")
    export = _find_export(session, header.get("CHECKSUM", ""), scope)
    if export is None:
        block(
            "CHECKSUM",
            "O arquivo não corresponde a nenhuma exportação registrada desta sessão "
            "(@CHECKSUM ou @SCOPE alterado).",
        )
        expected_ids: tuple[str, ...] = (
            tuple(item.segment_id for item in scope_segments(session, scope))
            if _valid_scope(scope)
            else ()
        )
    else:
        expected_ids = tuple(str(item) for item in export.get("segment_ids", ()))
    declared = header.get("SEGMENTS")
    if declared is not None and declared != str(len(expected_ids)):
        block("COUNT", "A contagem @SEGMENTS foi alterada.")
    if document.end_count is not None and document.end_count != len(expected_ids):
        block("END_COUNT", "A contagem em @END não corresponde à exportação original.")

    expected_set = set(expected_ids)
    seen: dict[str, ParsedSegment] = {}
    states: dict[str, SegmentState] = {}
    corrections: dict[str, str] = {}
    flag_changes: dict[str, frozenset[SegmentFlag]] = {}
    previous_order = -1
    order_warned = False
    for parsed in document.segments:
        segment = session.segment(parsed.segment_id)
        if parsed.segment_id in seen:
            block(
                "DUPLICATE_ID",
                f"O ID {parsed.segment_id} aparece mais de uma vez.",
                parsed.segment_id,
                parsed.line,
            )
            continue
        seen[parsed.segment_id] = parsed
        if segment is None:
            block(
                "UNKNOWN_ID",
                f"O ID {parsed.segment_id} não existe nesta transcrição.",
                parsed.segment_id,
                parsed.line,
            )
            continue
        if parsed.segment_id not in expected_set:
            block(
                "OUT_OF_SCOPE",
                f"O ID {parsed.segment_id} não fazia parte deste arquivo.",
                parsed.segment_id,
                parsed.line,
            )
            continue
        position = expected_ids.index(parsed.segment_id)
        if position < previous_order and not order_warned:
            warn(
                "ORDER",
                "A ordem dos trechos foi alterada; a ordem original será usada.",
                parsed.segment_id,
                parsed.line,
            )
            order_warned = True
        previous_order = max(previous_order, position)
        if parsed.track_key != segment.track_key:
            block(
                "TRACK",
                f"A faixa de {parsed.segment_id} foi alterada de {segment.track_key} "
                f"para {parsed.track_key}.",
                parsed.segment_id,
                parsed.line,
            )
            continue
        speaker = session.speaker_name(segment.track_index)
        if parsed.speaker and parsed.speaker.casefold() != speaker.casefold():
            warn(
                "SPEAKER",
                f"O nome do participante em {parsed.segment_id} foi alterado para "
                f"'{parsed.speaker}'; o vínculo com {segment.track_key} foi mantido.",
                parsed.segment_id,
                parsed.line,
            )
        if not _times_match(parsed, segment, session, tolerance_frames):
            block(
                "TIME",
                f"Os tempos de {parsed.segment_id} foram alterados.",
                parsed.segment_id,
                parsed.line,
            )
            continue
        state = STATE_SYNONYMS.get(_ascii_upper(parsed.state_text))
        if state is None:
            block(
                "STATE",
                f"Estado inválido em {parsed.segment_id}: '{parsed.state_text}'. Use KEEP ou CUT.",
                parsed.segment_id,
                parsed.line,
            )
            continue
        states[parsed.segment_id] = state
        if parsed.text and parsed.text != segment.text:
            corrections[parsed.segment_id] = parsed.text
        elif not parsed.text:
            warn(
                "EMPTY_TEXT",
                f"O texto de {parsed.segment_id} foi apagado; o texto anterior foi mantido.",
                parsed.segment_id,
                parsed.line,
            )
        flags, unknown = _parse_flags(parsed.flags_text)
        for item in unknown:
            warn(
                "FLAG",
                f"Marcação desconhecida '{item}' em {parsed.segment_id} ignorada.",
                parsed.segment_id,
                parsed.line,
            )
        if (SegmentFlag.BLEED in segment.flags) != (SegmentFlag.BLEED in flags):
            new_flags = set(segment.flags)
            if SegmentFlag.BLEED in flags:
                new_flags.add(SegmentFlag.BLEED)
            else:
                new_flags.discard(SegmentFlag.BLEED)
            flag_changes[parsed.segment_id] = frozenset(new_flags)
            warn(
                "BLEED_CHANGED",
                f"A marcação de vazamento de {parsed.segment_id} foi alterada.",
                parsed.segment_id,
                parsed.line,
            )
    missing = tuple(item for item in expected_ids if item not in seen)
    if expected_ids and not document.segments:
        block("EMPTY", "Nenhum trecho foi encontrado no arquivo.")
    elif expected_ids and len(missing) > len(expected_ids) / 2:
        block(
            "MOSTLY_MISSING",
            f"{len(missing)} de {len(expected_ids)} trechos estão ausentes: o arquivo parece "
            "truncado ou reescrito. Peça à IA para devolver o arquivo completo.",
        )
    elif missing:
        warn(
            "MISSING",
            f"{len(missing)} trecho(s) não aparecem no arquivo importado. Eles serão candidatos à "
            "remoção somente após sua confirmação explícita.",
        )
    if corrections:
        issues.append(
            Issue(
                Severity.INFO,
                "CORRECTIONS",
                f"{len(corrections)} correção(ões) de texto (não alteram o áudio).",
            )
        )
    return ImportReview(
        session_id=session.session_id,
        revision=session.revision,
        scope=scope,
        issues=tuple(issues),
        states=states,
        corrections=corrections,
        flag_changes=flag_changes,
        missing=missing,
        expected_count=len(expected_ids),
    )


def apply_review(
    session: TranscriptSession,
    review: ImportReview,
    *,
    imported_at: str,
    source_name: str,
) -> TranscriptSession:
    if review.blocked:
        raise ValueError("uma importação bloqueada não pode ser aplicada")
    if review.session_id != session.session_id or review.revision != session.revision:
        raise ValueError("a revisão da sessão mudou desde a análise da importação")
    segments: list[SpeechSegment] = []
    for segment in session.segments:
        updated = segment
        if segment.segment_id in review.states:
            updated = replace(updated, state=review.states[segment.segment_id])
        if segment.segment_id in review.corrections:
            updated = replace(updated, text=review.corrections[segment.segment_id])
        if segment.segment_id in review.flag_changes:
            updated = replace(updated, flags=review.flag_changes[segment.segment_id])
        segments.append(updated)
    pending = tuple(dict.fromkeys((*session.pending_missing, *review.missing)))
    record = {
        "imported_at": imported_at,
        "source": source_name,
        "scope": review.scope,
        "cut": list(review.cut_ids),
        "corrections": len(review.corrections),
        "missing": list(review.missing),
        "warnings": [issue.render() for issue in review.issues if issue.severity != Severity.INFO],
    }
    return replace(
        session,
        segments=mark_overlaps(segments),
        updated_at=imported_at,
        imports=(*session.imports, record),
        pending_missing=pending,
    )


def resolve_missing(
    session: TranscriptSession,
    *,
    remove: bool,
    updated_at: str,
) -> TranscriptSession:
    """Explicit user decision for segments that disappeared from an imported TXT."""

    pending = set(session.pending_missing)
    if not pending:
        return session
    segments = [
        replace(item, state=SegmentState.CUT if remove else SegmentState.KEEP)
        if item.segment_id in pending
        else item
        for item in session.segments
    ]
    record = {
        "resolved_at": updated_at,
        "missing_resolution": "CUT" if remove else "KEEP",
        "segments": sorted(pending),
    }
    return replace(
        session,
        segments=tuple(segments),
        pending_missing=(),
        updated_at=updated_at,
        imports=(*session.imports, record),
    )


def record_export(
    session: TranscriptSession,
    *,
    file_name: str,
    scope: str,
    segment_ids: Iterable[str],
    checksum: str,
    exported_at: str,
) -> TranscriptSession:
    record = {
        "file": file_name,
        "scope": scope,
        "segment_ids": list(segment_ids),
        "checksum": checksum,
        "revision": session.revision,
        "exported_at": exported_at,
    }
    return replace(session, exports=(*session.exports, record))


def _find_export(session: TranscriptSession, checksum: str, scope: str) -> Mapping[str, Any] | None:
    for record in reversed(session.exports):
        if (
            record.get("checksum") == checksum
            and str(record.get("scope", "")).upper() == scope
            and record.get("revision", session.revision) == session.revision
        ):
            return record
    return None


def _times_match(
    parsed: ParsedSegment,
    segment: SpeechSegment,
    session: TranscriptSession,
    tolerance_frames: float,
) -> bool:
    try:
        start = parse_clock(parsed.start_text)
        end = parse_clock(parsed.end_text)
    except ValueError:
        return False
    tolerance = tolerance_frames / session.fps + 0.0015
    expected_start = (segment.start_frame - session.start_frame) / session.fps
    expected_end = (segment.end_frame - session.start_frame) / session.fps
    return abs(start - expected_start) <= tolerance and abs(end - expected_end) <= tolerance


def _parse_flags(value: str | None) -> tuple[set[SegmentFlag], list[str]]:
    flags: set[SegmentFlag] = set()
    unknown: list[str] = []
    if not value:
        return flags, unknown
    for item in re.split(r"[,;]", value):
        token = _ascii_upper(item)
        if not token:
            continue
        flag = FLAG_SYNONYMS.get(token)
        if flag is None:
            unknown.append(item.strip())
        else:
            flags.add(flag)
    return flags, unknown


def _ascii_upper(value: str) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", value.strip().upper())
    return "".join(char for char in decomposed if not unicodedata.combining(char)).replace(" ", "_")


def _scope_track(scope: str) -> int:
    match = re.fullmatch(r"A(\d+)", scope.strip().upper())
    if not match:
        raise ValueError(f"escopo inválido: {scope}")
    return int(match.group(1))


def _valid_scope(scope: str) -> bool:
    return scope == SCOPE_ALL or re.fullmatch(r"A\d+", scope) is not None
