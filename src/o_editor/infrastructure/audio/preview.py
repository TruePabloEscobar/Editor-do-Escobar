"""Cached PCM previews from rendered tracks and the authoritative Rough Cut plan."""

from __future__ import annotations

import hashlib
import json
import os
import wave
from bisect import bisect_right
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass
from itertools import islice
from pathlib import Path
from typing import Any

from o_editor.domain.audio_preview import active_ranges
from o_editor.domain.enums import ChannelMode, TrackType
from o_editor.domain.rough_cut import RoughCutPlan
from o_editor.domain.speech import TranscriptSession
from o_editor.errors import CancelledError, OEditorError
from o_editor.infrastructure.audio.signal import _numpy
from o_editor.infrastructure.audio.track_renderer import RenderedTrack, TrackAudioRenderer
from o_editor.infrastructure.transcription.base import CancellationToken

PEAK_SAMPLES = 256
BLOCK_SAMPLES = 16384


@dataclass(frozen=True, slots=True)
class WaveTrack:
    index: int
    name: str
    sample_rate: int
    sample_count: int
    peaks: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class PreviewAudio:
    tracks: tuple[WaveTrack, ...]
    original_path: Path
    edited_path: Path
    warnings: tuple[str, ...]


def _check(cancellation: CancellationToken) -> None:
    if cancellation.cancelled:
        raise CancelledError("Atualização da prévia cancelada.")


def waveform(track: RenderedTrack, cancellation: CancellationToken) -> WaveTrack:
    target = track.path.parent / "waveform-v1.json"
    signature = [track.path.stat().st_size, track.path.stat().st_mtime_ns]
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if data["signature"] == signature:
            return WaveTrack(
                track.track_index,
                "",
                track.sample_rate,
                track.sample_count,
                tuple((int(a), int(b)) for a, b in data["peaks"]),
            )
    except (OSError, ValueError, KeyError, TypeError):
        data = None
    np = _numpy()
    peaks: list[tuple[int, int]] = []
    with wave.open(str(track.path), "rb") as handle:
        while chunk := handle.readframes(BLOCK_SAMPLES):
            _check(cancellation)
            samples = np.frombuffer(chunk, dtype="<i2")
            remainder = len(samples) % PEAK_SAMPLES
            if remainder:
                samples = np.pad(samples, (0, PEAK_SAMPLES - remainder))
            rows = samples.reshape(-1, PEAK_SAMPLES)
            peaks.extend(
                (int(a), int(b)) for a, b in zip(rows.min(axis=1), rows.max(axis=1), strict=True)
            )
    _atomic_json(target, {"signature": signature, "peaks": peaks})
    return WaveTrack(track.track_index, "", track.sample_rate, track.sample_count, tuple(peaks))


def _atomic_json(target: Path, data: dict[str, Any]) -> None:
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    os.replace(temporary, target)


def build_preview_audio(
    plan: RoughCutPlan,
    session: TranscriptSession,
    renderer: TrackAudioRenderer,
    cache_root: Path,
    cancellation: CancellationToken,
    progress: Callable[[str], None] | None = None,
) -> PreviewAudio:
    """No transcription, VAD, Resolve access or new cut decisions happen here."""
    from dataclasses import replace

    modes = {t.track_index: ChannelMode(t.channel_mode) for t in session.tracks}
    rendered: list[RenderedTrack] = []
    waves: list[WaveTrack] = []
    warnings: list[str] = []
    for track in plan.layout.tracks_of(TrackType.AUDIO):
        _check(cancellation)
        if progress:
            progress(f"Preparando waveform e áudio de {track.key}…")
        audio = renderer.render(
            plan.layout,
            track.index,
            modes.get(track.index, ChannelMode.BOTH),
            cancellation=cancellation,
        )
        rendered.append(audio)
        waves.append(replace(waveform(audio, cancellation), name=track.display_name))
        warnings.extend(audio.warnings)
    if not rendered:
        raise OEditorError("A timeline não tem faixas de áudio para ouvir.")
    original_key = hashlib.sha256(
        json.dumps(
            [
                (
                    t.cache_key,
                    t.path.stat().st_mtime_ns,
                    next(
                        info.enabled
                        for info in plan.layout.tracks_of(TrackType.AUDIO)
                        if info.index == t.track_index
                    ),
                )
                for t in rendered
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    edit_key = hashlib.sha256(
        json.dumps(
            [
                original_key,
                [(k.source_start, k.source_end) for k in plan.keep_ranges],
                [(t.track_index, active_ranges(plan, t.track_index)) for t in rendered],
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()
    directory = cache_root / "audio-previews-v1"
    directory.mkdir(parents=True, exist_ok=True)
    original = directory / f"{original_key}-original.wav"
    edited = directory / f"{edit_key}-edited.wav"
    if progress:
        progress("Preparando reprodução original e simulação dos cortes…")
    _mix(plan, rendered, original, edited=False, cancellation=cancellation)
    _mix(plan, rendered, edited, edited=True, cancellation=cancellation)
    return PreviewAudio(tuple(waves), original, edited, tuple(dict.fromkeys(warnings)))


def _mix(
    plan: RoughCutPlan,
    tracks: list[RenderedTrack],
    target: Path,
    *,
    edited: bool,
    cancellation: CancellationToken,
) -> None:
    if target.is_file():
        return
    np = _numpy()
    rate = tracks[0].sample_rate
    origin = plan.layout.start_frame

    def sample(frame: int) -> int:
        return round((frame - origin) * rate / plan.layout.fps)

    spans = (
        [(sample(k.source_start), sample(k.source_end)) for k in plan.keep_ranges]
        if edited
        else [(0, sample(plan.layout.end_frame))]
    )
    active = {
        track.track_index: tuple(
            (sample(a), sample(b)) for a, b in active_ranges(plan, track.track_index)
        )
        for track in tracks
    }
    starts = {index: [a for a, _ in ranges] for index, ranges in active.items()}
    temporary = target.with_suffix(".partial")
    try:
        with ExitStack() as stack:
            readers = [stack.enter_context(wave.open(str(t.path), "rb")) for t in tracks]
            output = stack.enter_context(wave.open(str(temporary), "wb"))
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(rate)
            for first, last in spans:
                for cursor in range(first, last, BLOCK_SAMPLES):
                    _check(cancellation)
                    count = min(BLOCK_SAMPLES, last - cursor)
                    mixed = np.zeros(count, dtype="int64")
                    for track, reader in zip(tracks, readers, strict=True):
                        info = plan.layout.track(TrackType.AUDIO, track.track_index)
                        if info is not None and info.enabled is False:
                            continue
                        reader.setpos(min(cursor, reader.getnframes()))
                        raw = reader.readframes(count)
                        values = np.frombuffer(raw, dtype="<i2").astype("int64")
                        if edited:
                            masked = np.zeros(count, dtype="int64")
                            ranges = active[track.track_index]
                            pos = max(0, bisect_right(starts[track.track_index], cursor) - 1)
                            for a, b in islice(ranges, pos, None):
                                if a >= cursor + count:
                                    break
                                lo, hi = max(0, a - cursor), min(len(values), b - cursor)
                                if hi > lo:
                                    masked[lo:hi] = values[lo:hi]
                            mixed += masked
                        else:
                            mixed[: len(values)] += values
                    # Fixed gain for both modes, so cuts/mutes never cause gain pumping.
                    output.writeframes(
                        (mixed // len(tracks)).clip(-32768, 32767).astype("<i2").tobytes()
                    )
        _check(cancellation)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
