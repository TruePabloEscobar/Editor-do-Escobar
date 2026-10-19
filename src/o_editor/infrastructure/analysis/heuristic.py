"""Deterministic, local editorial suggestion engine."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from o_editor.domain.enums import TextSubtype, ZoomSubtype
from o_editor.domain.models import (
    Suggestion,
    TextSuggestion,
    TimelineItemSnapshot,
    TimelineSnapshot,
    Transcript,
    TranscriptSegment,
    ZoomSuggestion,
)
from o_editor.domain.scoring import (
    ImportanceSignals,
    score_importance,
    select_by_frequency,
)
from o_editor.infrastructure.config import TextSection, ZoomSection

NUMBER_PATTERN = re.compile(
    r"\b(?:\d{1,4}(?:[.,]\d+)?%?|\d+\s+por\s+cento)\b",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{4})\b",
    re.IGNORECASE,
)
CONCLUSION_TERMS = ("em resumo", "por isso", "a conclusão", "concluindo")
CONTRAST_TERMS = ("mas", "porém", "entretanto", "contudo")
WORD_PATTERN = re.compile(r"\b[\wÀ-ÿ%.-]+\b", re.UNICODE)


@dataclass(frozen=True, slots=True)
class AnalyzedSegment:
    segment: TranscriptSegment
    signals: ImportanceSignals
    importance: float
    reason_codes: tuple[str, ...]
    repetition_count: int


class HeuristicAnalyzer:
    def __init__(
        self,
        *,
        zoom: ZoomSection,
        text: TextSection,
        configured_keywords: tuple[str, ...] = (),
    ) -> None:
        self._zoom = zoom
        self._text = text
        self._configured_keywords = tuple(_normalize(value) for value in configured_keywords)

    def analyze(
        self,
        snapshot: TimelineSnapshot,
        transcript: Transcript,
    ) -> tuple[Suggestion, ...]:
        analyzed = self._score_segments(transcript)
        suggestions: list[Suggestion] = []
        if self._zoom.enabled:
            suggestions.extend(self._zoom_suggestions(snapshot, analyzed))
        if self._text.enabled:
            suggestions.extend(self._text_suggestions(snapshot, analyzed))
        return tuple(
            sorted(
                suggestions,
                key=lambda item: (item.timeline_start_frame, item.kind.value, item.id),
            )
        )

    def _score_segments(self, transcript: Transcript) -> tuple[AnalyzedSegment, ...]:
        seen_terms: dict[str, int] = {}
        result: list[AnalyzedSegment] = []
        for segment in transcript.segments:
            normalized = _normalize(segment.text)
            terms = {
                term
                for term in WORD_PATTERN.findall(normalized)
                if len(term) >= 5 and not term.isdigit()
            }
            repetition = max((seen_terms.get(term, 0) for term in terms), default=0) + 1
            for term in terms:
                seen_terms[term] = seen_terms.get(term, 0) + 1
            signals = ImportanceSignals(
                numeric=bool(NUMBER_PATTERN.search(normalized)),
                question="?" in segment.text,
                conclusion=any(term in normalized for term in CONCLUSION_TERMS),
                contrast=any(
                    re.search(rf"\b{re.escape(term)}\b", normalized) for term in CONTRAST_TERMS
                ),
                configured_keyword=any(
                    keyword in normalized for keyword in self._configured_keywords
                ),
                pause_before_seconds=segment.pause_before_frames / transcript.fps,
                repetition_count=repetition,
            )
            reasons = tuple(
                code
                for condition, code in (
                    (signals.numeric, "NUMBER"),
                    (bool(DATE_PATTERN.search(normalized)), "DATE"),
                    (signals.question, "QUESTION"),
                    (signals.conclusion, "CONCLUSION"),
                    (signals.contrast, "CONTRAST"),
                    (signals.configured_keyword, "CONFIGURED_KEYWORD"),
                    (signals.pause_before_seconds >= 1.5, "PAUSE_BEFORE"),
                    (signals.repetition_count > 1, "REPETITION"),
                )
                if condition
            )
            result.append(
                AnalyzedSegment(
                    segment=segment,
                    signals=signals,
                    importance=score_importance(signals),
                    reason_codes=reasons,
                    repetition_count=repetition,
                )
            )
        return tuple(result)

    def _zoom_suggestions(
        self,
        snapshot: TimelineSnapshot,
        analyzed: tuple[AnalyzedSegment, ...],
    ) -> list[ZoomSuggestion]:
        candidates = [
            (item.segment.start_frame, item.importance)
            for item in analyzed
            if item.importance >= 0.42 and snapshot.item_at(item.segment.start_frame)
        ]
        selected = select_by_frequency(
            candidates,
            fps=snapshot.fps,
            minimum_gap_seconds=self._zoom.minimum_gap_seconds,
            maximum_per_minute=self._zoom.maximum_per_minute,
            duration_frames=snapshot.duration_frames,
        )
        result: list[ZoomSuggestion] = []
        for item in analyzed:
            if item.segment.start_frame not in selected:
                continue
            clip = snapshot.item_at(item.segment.start_frame)
            if clip is None or not _supports_zoom(clip, item.segment):
                continue
            start = max(clip.start_frame, item.segment.start_frame)
            end = min(clip.end_frame, item.segment.end_frame)
            if end - start < round(snapshot.fps):
                continue
            subtype = _zoom_subtype(item.signals)
            peak = _zoom_peak(self._zoom.intensity, self._zoom.max_zoom)
            result.append(
                ZoomSuggestion.create(
                    subtype=subtype,
                    timeline_start_frame=start,
                    timeline_end_frame=end,
                    confidence=min(0.98, 0.55 + item.importance * 0.4),
                    importance=item.importance,
                    reason_codes=item.reason_codes,
                    source_segment_ids=(item.segment.id,),
                    clip_id=clip.id,
                    clip_local_start_frame=start - clip.start_frame,
                    clip_local_end_frame=end - clip.start_frame,
                    parameters=(
                        ("zoom_start", 1.0),
                        ("zoom_peak", peak),
                        ("center_x", 0.5),
                        ("center_y", 0.5),
                        ("attack_frames", max(4, round(snapshot.fps / 3))),
                        ("hold_frames", max(1, end - start - round(snapshot.fps))),
                        ("release_frames", max(4, round(snapshot.fps / 3))),
                    ),
                )
            )
        return result

    def _text_suggestions(
        self,
        snapshot: TimelineSnapshot,
        analyzed: tuple[AnalyzedSegment, ...],
    ) -> list[TextSuggestion]:
        candidates = [
            (item.segment.start_frame, item.importance)
            for item in analyzed
            if _text_subtype(item) is not None and item.importance >= 0.4
        ]
        selected = select_by_frequency(
            candidates,
            fps=snapshot.fps,
            minimum_gap_seconds=self._text.minimum_gap_seconds,
            maximum_per_minute=self._text.maximum_per_minute,
            duration_frames=snapshot.duration_frames,
        )
        result: list[TextSuggestion] = []
        duration = round(
            min(
                self._text.maximum_duration_seconds,
                max(self._text.minimum_duration_seconds, 2.0),
            )
            * snapshot.fps
        )
        for item in analyzed:
            if item.segment.start_frame not in selected:
                continue
            subtype = _text_subtype(item)
            if subtype is None:
                continue
            content = _short_text(
                item.segment.text,
                subtype,
                minimum_words=self._text.minimum_words,
                maximum_words=self._text.maximum_words,
            )
            if content is None:
                continue
            start = item.segment.start_frame
            end = min(snapshot.end_frame, start + duration)
            result.append(
                TextSuggestion.create(
                    subtype=subtype,
                    timeline_start_frame=start,
                    timeline_end_frame=end,
                    confidence=min(0.99, 0.6 + item.importance * 0.35),
                    importance=item.importance,
                    reason_codes=item.reason_codes,
                    source_segment_ids=(item.segment.id,),
                    text=content,
                    parameters=(
                        ("style", "keyword"),
                        ("position", "lower_center"),
                        ("entry_frames", max(4, round(snapshot.fps * 0.27))),
                        ("exit_frames", max(4, round(snapshot.fps * 0.27))),
                    ),
                )
            )
        return result


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _supports_zoom(clip: TimelineItemSnapshot, segment: TranscriptSegment) -> bool:
    return (
        clip.enabled
        and not clip.is_multicam
        and clip.fusion_comp_count == 0
        and not clip.has_transition_before
        and not clip.has_transition_after
        and segment.start_frame >= clip.start_frame
        and segment.end_frame <= clip.end_frame
    )


def _zoom_subtype(signals: ImportanceSignals) -> ZoomSubtype:
    if signals.question:
        return ZoomSubtype.PUNCH_IN
    if signals.conclusion:
        return ZoomSubtype.PUSH_AND_RETURN
    return ZoomSubtype.PUSH_IN


def _zoom_peak(intensity: str, maximum: float) -> float:
    defaults = {"very_soft": 1.04, "soft": 1.07, "medium": 1.10, "strong": 1.14}
    return round(min(maximum, defaults.get(intensity, 1.10)), 4)


def _text_subtype(item: AnalyzedSegment) -> TextSubtype | None:
    normalized = _normalize(item.segment.text)
    if DATE_PATTERN.search(normalized):
        return TextSubtype.DATE
    if item.signals.numeric:
        return TextSubtype.NUMBER
    if item.signals.conclusion:
        return TextSubtype.CONCLUSION
    if item.signals.contrast:
        return TextSubtype.CONTRAST
    if item.signals.configured_keyword:
        return TextSubtype.KEYWORD
    return None


def _short_text(
    source: str,
    subtype: TextSubtype,
    *,
    minimum_words: int,
    maximum_words: int,
) -> str | None:
    tokens = WORD_PATTERN.findall(source)
    if len(tokens) < minimum_words:
        return None
    normalized_tokens = [_normalize(token) for token in tokens]
    anchor = 0
    if subtype in (TextSubtype.NUMBER, TextSubtype.DATE):
        for index, token in enumerate(tokens):
            if NUMBER_PATTERN.fullmatch(token) or DATE_PATTERN.fullmatch(token):
                anchor = max(0, index - 2)
                break
    elif subtype is TextSubtype.CONCLUSION:
        connector_words = {"em", "resumo", "por", "isso", "concluindo", "a", "conclusao"}
        while anchor < len(tokens) and normalized_tokens[anchor] in connector_words:
            anchor += 1
    elif subtype is TextSubtype.CONTRAST and normalized_tokens[0] in CONTRAST_TERMS:
        anchor = 1
    selected = tokens[anchor : anchor + maximum_words]
    if len(selected) < minimum_words:
        selected = tokens[:maximum_words]
    if not minimum_words <= len(selected) <= maximum_words:
        return None
    return " ".join(selected)
