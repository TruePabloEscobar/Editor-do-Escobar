"""Conservative, frame-based microphone gating; never removes editorial time."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, replace
from typing import Any

from o_editor.domain.intervals import clip_to, expand, intersect, subtract, union
from o_editor.domain.speech import (
    SegmentFlag,
    SegmentState,
    SpeechSegment,
    TranscriptSession,
    detect_bleed,
)


@dataclass(frozen=True, slots=True)
class MicrophoneCleanupSettings:
    enabled: bool = False
    protect_sounds: bool = True
    guard_before_ms: int = 100
    guard_after_ms: int = 180

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MicrophoneMute:
    track_index: int
    start_frame: int
    end_frame: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def microphone_mutes(
    session: TranscriptSession,
    settings: MicrophoneCleanupSettings,
) -> tuple[MicrophoneMute, ...]:
    if not settings.enabled:
        return ()
    speech = [
        s
        for s in confirmed_microphone_segments(session)
        if s.state == SegmentState.KEEP and SegmentFlag.NON_SPEECH not in s.flags
    ]
    primary = [s for s in speech if not s.is_bleed]
    before = max(0, round(settings.guard_before_ms * session.fps / 1000))
    after = max(0, round(settings.guard_after_ms * session.fps / 1000))
    bounds = (session.start_frame, session.end_frame)
    sources = identical_audio_sources(session)
    speaking = clip_to(
        expand(((s.start_frame, s.end_frame) for s in primary), before, after), bounds
    )
    result = []
    for track in session.tracks:
        index = track.track_index
        own = [s for s in primary if s.track_index == index]
        active = expand(((s.start_frame, s.end_frame) for s in own), before, after)
        digital_returns = clip_to(
            expand(
                (
                    (s.start_frame, s.end_frame)
                    for s in primary
                    if s.track_index == sources.get(index)
                ),
                before,
                after,
            ),
            bounds,
        )
        reactions = union(
            (s.start_frame, s.end_frame)
            for s in session.segments
            if s.track_index == index
            and s.state == SegmentState.KEEP
            and SegmentFlag.NON_SPEECH in s.flags
        )
        if settings.protect_sounds:
            # Exclude transcribed intervals from VAD so a confirmed return cannot
            # protect itself. Explicit reactions and unidentified activity remain.
            transcribed = union(
                (s.start_frame, s.end_frame) for s in session.segments if s.track_index == index
            )
            sounds = subtract(session.activity.get(index, ()), transcribed)
            active = union(active, expand(union(sounds, reactions), before, after))
        if index not in session.activity:
            # Older/unanalysed tracks have no proof of quiet: only confirmed echoes.
            quiet = intersect(
                speaking,
                (
                    (s.start_frame, s.end_frame)
                    for s in speech
                    if s.track_index == index and s.is_bleed
                ),
            )
        else:
            quiet = subtract(speaking, active)
        # VAD activity belonging to the proven digital copy is not independent
        # speech/noise. Explicit reactions remain protected, even in this case.
        protected_reactions = expand(reactions, before, after) if settings.protect_sounds else ()
        quiet = union(quiet, subtract(digital_returns, protected_reactions))
        echoes = union(
            (s.start_frame, s.end_frame) for s in speech if s.track_index == index and s.is_bleed
        )
        for lo, hi in quiet:
            reason = (
                "RETORNO_AUDIO_IDENTICO"
                if intersect(((lo, hi),), digital_returns)
                else "RETORNO"
                if intersect(((lo, hi),), echoes)
                else "SEM_FALA_OU_SOM"
            )
            result.append(MicrophoneMute(index, lo, hi, reason))
    return tuple(result)


def confirmed_microphone_segments(session: TranscriptSession) -> tuple[SpeechSegment, ...]:
    """Reassess old BLEED flags conservatively after text edits and for global cuts."""
    clean = [
        replace(s, flags=s.flags - {SegmentFlag.BLEED}, related_segment_id=None)
        for s in session.segments
    ]
    candidates = [
        s for s in clean if s.state == SegmentState.KEEP and SegmentFlag.NON_SPEECH not in s.flags
    ]
    confirmed, _ = detect_bleed(
        candidates,
        minimum_similarity=1.0,
        signal_fingerprints={
            t.track_index: t.signal_fingerprint for t in session.tracks if t.signal_fingerprint
        },
    )
    by_id = {s.segment_id: s for s in confirmed}
    return tuple(by_id.get(s.segment_id, s) for s in clean)


def identical_audio_sources(session: TranscriptSession) -> dict[int, int]:
    """Only exact, non-silent aligned PCM identities can break an equal-level tie."""
    first: dict[str, int] = {}
    sources: dict[int, int] = {}
    for track in sorted(session.tracks, key=lambda item: item.track_index):
        fingerprint = track.signal_fingerprint
        if not fingerprint or not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            continue
        if fingerprint in first:
            sources[track.track_index] = first[fingerprint]
        else:
            first[fingerprint] = track.track_index
    return sources
