"""Read-only evidence upgrade for transcripts created before PCM fingerprints."""

from __future__ import annotations

import re
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from o_editor.domain.speech import TranscriptSession
from o_editor.errors import OEditorError
from o_editor.infrastructure.audio.signal import SignalAnalysisError, fingerprint_wav
from o_editor.infrastructure.cache import default_app_cache_root


def with_cached_signal_fingerprints(session: TranscriptSession) -> TranscriptSession:
    """Enrich an in-memory copy; keep original transcript/history/cache untouched."""
    try:
        root = default_app_cache_root()
    except OEditorError:
        return session
    tracks = []
    duration = (session.end_frame - session.start_frame) / session.fps
    for track in session.tracks:
        key = track.audio_cache_key
        if track.signal_fingerprint or not key or not re.fullmatch(r"[0-9a-f]{64}", key):
            tracks.append(track)
            continue
        path = root / "tracks" / key / "track.wav"
        try:
            stat = path.stat()
            fingerprint = _cached_fingerprint(
                str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, duration
            )
        except (OSError, SignalAnalysisError):
            fingerprint = None  # Without signal proof, preserve the existing conservative rule.
        tracks.append(replace(track, signal_fingerprint=fingerprint))
    return replace(session, tracks=tuple(tracks))


@lru_cache(maxsize=64)
def _cached_fingerprint(
    path: str, size: int, modified: int, created: int, duration: float
) -> str | None:
    value = fingerprint_wav(Path(path), duration_seconds=duration)
    stat = Path(path).stat()
    if (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns) != (size, modified, created):
        raise SignalAnalysisError("O cache mudou durante a comparação.")
    return value
