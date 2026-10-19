"""Transcribe every selected timeline track individually and merge chronologically."""

from __future__ import annotations

import logging
import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from o_editor.domain.enums import TrackType
from o_editor.domain.speech import (
    RawSegment,
    SpeechSegment,
    SpeechWord,
    TranscribedTrack,
    TranscriptSession,
    build_segments,
    detect_bleed,
)
from o_editor.domain.timeline_layout import TimelineLayout
from o_editor.domain.voice_tracks import SelectedVoiceTrack
from o_editor.errors import CancelledError, OEditorError
from o_editor.infrastructure.audio.signal import ActivitySettings, TrackSignal
from o_editor.infrastructure.audio.track_renderer import RenderedTrack, TrackAudioRenderer
from o_editor.infrastructure.cache import JsonCache
from o_editor.infrastructure.transcript_sessions import SessionStore
from o_editor.infrastructure.transcription.base import CancellationToken
from o_editor.infrastructure.transcription.track import (
    TimedSegment,
    TimedWord,
    TrackTranscriber,
    TrackTranscriptionResult,
)

LOGGER = logging.getLogger("o_editor.transcribe_tracks")
TRANSCRIPT_CACHE_VERSION = "track-transcript-1"
ProgressCallback = Callable[[float, str], None]
# A transcribed segment must overlap real signal on its own track; otherwise it is
# treated as a hallucination over silence and discarded (never shown as speech).
MINIMUM_ACTIVE_FRACTION = 0.15


@dataclass(frozen=True, slots=True)
class TrackOutcome:
    track: TranscribedTrack
    raw_segments: tuple[RawSegment, ...]
    activity: tuple[tuple[int, int], ...]


class TranscribeTracks:
    def __init__(
        self,
        *,
        layout: TimelineLayout,
        selected_tracks: tuple[SelectedVoiceTrack, ...],
        renderer: TrackAudioRenderer,
        transcriber: TrackTranscriber,
        transcript_cache: JsonCache,
        session_store: SessionStore,
        language: str | None,
        previous_session: TranscriptSession | None = None,
        force_tracks: frozenset[int] = frozenset(),
        activity_settings: ActivitySettings | None = None,
    ) -> None:
        self._layout = layout
        self._selected = selected_tracks
        self._renderer = renderer
        self._transcriber = transcriber
        self._cache = transcript_cache
        self._store = session_store
        self._language = language
        self._previous = previous_session
        self._force = force_tracks
        self._activity_settings = activity_settings or ActivitySettings()

    def execute(
        self,
        *,
        progress: ProgressCallback | None = None,
        cancellation: CancellationToken | None = None,
    ) -> TranscriptSession:
        if not self._selected:
            raise OEditorError("Selecione pelo menos uma faixa de áudio para transcrever.")
        problems = [
            problem
            for problem in self._layout.validate()
            if any(f"A{item.index}" in problem for item in self._selected)
        ]
        if problems:
            raise OEditorError("A timeline capturada é inconsistente: " + " ".join(problems))
        outcomes: list[TrackOutcome] = []
        count = len(self._selected)
        for position, selected in enumerate(self._selected):
            if cancellation and cancellation.cancelled:
                raise CancelledError("A transcrição foi cancelada.")
            base = position / count
            span = 1.0 / count
            outcomes.append(
                self._process_track(
                    selected,
                    progress=_scaled(progress, base, base + span),
                    cancellation=cancellation,
                )
            )
        speakers = {item.track.track_index: item.track.name for item in outcomes}
        segments = build_segments((raw for item in outcomes for raw in item.raw_segments), speakers)
        segments, bleed_notes = detect_bleed(
            segments,
            signal_fingerprints={
                item.track.track_index: item.track.signal_fingerprint
                for item in outcomes
                if item.track.signal_fingerprint
            },
        )
        session = self._make_session(outcomes, segments, bleed_notes)
        self._store.save(session)
        if progress:
            progress(1.0, "Transcrição de todas as faixas concluída")
        return session

    def _process_track(
        self,
        selected: SelectedVoiceTrack,
        *,
        progress: ProgressCallback | None,
        cancellation: CancellationToken | None,
    ) -> TrackOutcome:
        layout = self._layout
        track_info = layout.track(TrackType.AUDIO, selected.index)
        if track_info is None:
            raise OEditorError(f"A faixa A{selected.index} não existe mais na timeline.")
        name = track_info.name or f"A{selected.index}"
        forced = selected.index in self._force
        rendered: RenderedTrack = self._renderer.render(
            layout,
            selected.index,
            selected.channel_mode,
            progress=_scaled(progress, 0.0, 0.3),
            cancellation=cancellation,
            use_cache=not forced,
        )
        signal = TrackSignal.load(
            rendered.path, fps=layout.fps, timeline_start_frame=layout.start_frame
        )
        activity = signal.activity(self._activity_settings)
        result = self._transcribe(rendered, forced, _scaled(progress, 0.3, 0.95), cancellation)
        raw: list[RawSegment] = []
        dropped = 0
        for segment in result.segments:
            converted = self._to_raw(selected.index, segment)
            if converted is None:
                continue
            if (
                signal.active_fraction(
                    converted.start_frame, converted.end_frame, self._activity_settings
                )
                < MINIMUM_ACTIVE_FRACTION
            ):
                dropped += 1
                continue
            raw.append(
                replace(
                    converted,
                    energy_db=round(signal.level_db(converted.start_frame, converted.end_frame), 2),
                )
            )
        warnings = list(rendered.warnings)
        if dropped:
            warnings.append(
                f"{dropped} trecho(s) transcrito(s) sobre silêncio em {track_info.display_name} "
                "foram descartados (possível alucinação)."
            )
        if result.fallback_reason:
            warnings.append(result.fallback_reason)
        if track_info.enabled is False:
            warnings.append(f"{track_info.display_name} está desabilitada (muda) na timeline.")
        if progress:
            progress(1.0, f"{track_info.display_name}: {len(raw)} trechos")
        LOGGER.info(
            "track_transcribed track=A%s segments=%s dropped=%s device=%s",
            selected.index,
            len(raw),
            dropped,
            result.device,
        )
        return TrackOutcome(
            track=TranscribedTrack(
                track_index=selected.index,
                name=name,
                channel_mode=selected.channel_mode.value,
                audio_cache_key=rendered.cache_key,
                segment_count=len(raw),
                dropped_hallucinations=dropped,
                device=result.device,
                warnings=tuple(warnings),
                signal_fingerprint=signal.fingerprint(),
            ),
            raw_segments=tuple(raw),
            activity=activity,
        )

    def _transcribe(
        self,
        rendered: RenderedTrack,
        forced: bool,
        progress: ProgressCallback | None,
        cancellation: CancellationToken | None,
    ) -> TrackTranscriptionResult:
        key = JsonCache.make_key(
            TRANSCRIPT_CACHE_VERSION,
            rendered.cache_key,
            self._transcriber.name,
            self._transcriber.model_name,
            str(getattr(self._transcriber, "cache_identity", self._transcriber.model_name)),
            self._language or "auto",
        )
        if not forced:
            cached = self._cache.load("track_transcripts", key)
            if cached is not None:
                try:
                    return _result_from_cache(cached)
                except (KeyError, TypeError, ValueError):
                    LOGGER.warning("invalid_track_transcript_cache key=%s", key[:12])
        result = self._transcriber.transcribe_track(
            rendered.path,
            language=self._language,
            progress=progress,
            cancellation=cancellation,
        )
        self._cache.save("track_transcripts", key, _result_to_cache(result))
        return result

    def _to_raw(self, track_index: int, segment: TimedSegment) -> RawSegment | None:
        layout = self._layout
        start_seconds = segment.start
        end_seconds = segment.end
        if segment.words:
            start_seconds = min(word.start for word in segment.words)
            end_seconds = max(word.end for word in segment.words)
        start = layout.start_frame + math.floor(max(0.0, start_seconds) * layout.fps)
        end = layout.start_frame + math.ceil(max(0.0, end_seconds) * layout.fps)
        start = max(layout.start_frame, min(start, layout.end_frame - 1))
        end = max(start + 1, min(end, layout.end_frame))
        if not segment.text.strip():
            return None
        words: list[SpeechWord] = []
        for word in segment.words:
            word_start = layout.start_frame + math.floor(max(0.0, word.start) * layout.fps)
            word_end = layout.start_frame + math.ceil(max(0.0, word.end) * layout.fps)
            word_start = max(start, min(word_start, end - 1))
            word_end = max(word_start + 1, min(word_end, end))
            words.append(SpeechWord(word.text, word_start, word_end, word.probability))
        return RawSegment(
            track_index=track_index,
            start_frame=start,
            end_frame=end,
            text=segment.text.strip(),
            words=tuple(words),
            confidence=segment.confidence,
            no_speech_prob=segment.no_speech_prob,
        )

    def _make_session(
        self,
        outcomes: list[TrackOutcome],
        segments: tuple[SpeechSegment, ...],
        notes: tuple[str, ...],
    ) -> TranscriptSession:
        now = datetime.now(UTC).isoformat()
        layout = self._layout
        previous = self._previous
        reuse = (
            previous is not None
            and previous.project_name == layout.project_name
            and previous.timeline_name == layout.timeline_name
            and previous.layout_fingerprint == layout.fingerprint
        )
        if reuse and previous is not None:
            segments = _carry_over_edits(previous, segments)
        warnings = [warning for item in outcomes for warning in item.track.warnings]
        warnings.extend(notes)
        warnings.extend(layout.capture_warnings)
        return TranscriptSession(
            session_id=previous.session_id if reuse and previous else uuid.uuid4().hex[:16],
            revision=(previous.revision + 1) if reuse and previous else 1,
            created_at=previous.created_at if reuse and previous else now,
            updated_at=now,
            project_name=layout.project_name,
            timeline_name=layout.timeline_name,
            timeline_id=layout.timeline_id,
            fps=layout.fps,
            start_frame=layout.start_frame,
            end_frame=layout.end_frame,
            start_timecode=layout.start_timecode,
            drop_frame=layout.drop_frame,
            layout_fingerprint=layout.fingerprint,
            layout=layout.to_dict(),
            tracks=tuple(item.track for item in outcomes),
            segments=segments,
            activity={item.track.track_index: item.activity for item in outcomes},
            language=self._language,
            provider=self._transcriber.name,
            model=self._transcriber.model_name,
            warnings=tuple(dict.fromkeys(warnings)),
        )


def _carry_over_edits(
    previous: TranscriptSession, segments: tuple[SpeechSegment, ...]
) -> tuple[SpeechSegment, ...]:
    """Keep state and text corrections for segments whose timing did not change."""

    index = {
        (item.track_index, item.start_frame, item.end_frame, item.original_text): item
        for item in previous.segments
    }
    result: list[SpeechSegment] = []
    for item in segments:
        old = index.get((item.track_index, item.start_frame, item.end_frame, item.original_text))
        if old is not None:
            result.append(replace(item, state=old.state, text=old.text))
        else:
            result.append(item)
    return tuple(result)


def _result_to_cache(result: TrackTranscriptionResult) -> dict[str, object]:
    return {
        "version": TRANSCRIPT_CACHE_VERSION,
        "language": result.language,
        "provider": result.provider,
        "model": result.model,
        "device": result.device,
        "segments": [
            {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "avg_logprob": segment.avg_logprob,
                "no_speech_prob": segment.no_speech_prob,
                "words": [
                    [word.text, word.start, word.end, word.probability] for word in segment.words
                ],
            }
            for segment in result.segments
        ],
    }


def _result_from_cache(value: dict[str, object]) -> TrackTranscriptionResult:
    if value.get("version") != TRANSCRIPT_CACHE_VERSION:
        raise ValueError("cache version")
    raw_segments = value["segments"]
    if not isinstance(raw_segments, list):
        raise TypeError("segments")
    segments = tuple(
        TimedSegment(
            start=float(item["start"]),
            end=float(item["end"]),
            text=str(item["text"]),
            avg_logprob=item.get("avg_logprob"),
            no_speech_prob=item.get("no_speech_prob"),
            words=tuple(
                TimedWord(str(word[0]), float(word[1]), float(word[2]), word[3])
                for word in item.get("words", ())
            ),
        )
        for item in raw_segments
    )
    language = value.get("language")
    device = value.get("device")
    return TrackTranscriptionResult(
        segments=segments,
        language=language if isinstance(language, str) else None,
        provider=str(value.get("provider") or ""),
        model=str(value.get("model") or ""),
        device=device if isinstance(device, str) else None,
    )


def _scaled(callback: ProgressCallback | None, start: float, end: float) -> ProgressCallback | None:
    if callback is None:
        return None

    def scaled(value: float, message: str) -> None:
        callback(start + max(0.0, min(1.0, value)) * (end - start), message)

    return scaled
