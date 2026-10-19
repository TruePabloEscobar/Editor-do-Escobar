"""Four-person demo podcast with known speech positions on the timeline.

Used by the mock mode of the UI and by the automated tests (tests/fixtures).

Every speech burst is defined in *timeline seconds* (relative to the timeline start).
``write_podcast_media`` writes source WAV files so that, once the clips are placed
with their source in-points, each burst lands exactly at its timeline position.
Each phrase uses its own tone frequency so the signal-based mock transcriber can
recover the phrase identity (and therefore detect bleed between microphones).
"""

from __future__ import annotations

import math
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path

from o_editor.domain.enums import TrackType
from o_editor.domain.speech import (
    RawSegment,
    TranscribedTrack,
    TranscriptSession,
    build_segments,
    detect_bleed,
)
from o_editor.domain.timeline_layout import ClipInfo, TimelineLayout, TrackInfo

FPS = 24.0
START_FRAME = 86_400  # 01:00:00:00
DURATION_SECONDS = 960
SAMPLE_RATE = 16_000
SPEAKERS = {1: "Pablo", 2: "Jessica", 3: "Mileni", 4: "Renne"}


@dataclass(frozen=True, slots=True)
class Burst:
    track: int
    start: float
    end: float
    phrase: str
    amplitude: float = 0.3


# Phrase identifier -> (tone frequency in Hz, transcript text)
PHRASES: dict[str, tuple[float, str]] = {
    "p1": (220.0, "Então, hoje vamos conversar sobre inteligência artificial."),
    "p2": (260.0, "É interessante porque existem várias possibilidades."),
    "p3": (300.0, "Não, espera, deixa eu começar essa parte novamente."),
    "p4": (340.0, "Essa fala acontece no minuto quinze da timeline."),
    "j1": (380.0, "Eu estava pensando justamente nisso ontem."),
    "j2": (420.0, "Concordo, falando ao mesmo tempo que você."),
    "j3": (460.0, "Voltando depois do corte na minha faixa."),
    "m1": (500.0, "Eu queria acrescentar um exemplo prático."),
    "r1": (540.0, "Vamos para a próxima pergunta."),
}

BURSTS: tuple[Burst, ...] = (
    Burst(1, 2.0, 6.0, "p1"),
    Burst(2, 7.0, 11.0, "j1"),
    Burst(1, 20.0, 24.0, "p2"),
    Burst(2, 22.0, 26.0, "j2"),
    Burst(1, 40.0, 44.0, "p3"),
    Burst(3, 40.0, 44.0, "p3", amplitude=0.05),  # Pablo leaking into Mileni's mic
    Burst(3, 50.0, 54.0, "m1"),
    Burst(4, 60.0, 63.0, "r1"),
    Burst(2, 330.0, 334.0, "j3"),
    Burst(1, 900.0, 904.0, "p4"),
)


def frames(seconds: float) -> int:
    return START_FRAME + round(seconds * FPS)


def _clip(
    item_id: str,
    track_type: TrackType,
    track: int,
    item_index: int,
    *,
    timeline_start: float,
    timeline_end: float,
    source_in: float,
    file_name: str,
    media_dir: Path | None,
    media_id: str,
    linked: tuple[str, ...] = (),
) -> ClipInfo:
    start = frames(timeline_start)
    end = frames(timeline_end)
    source_start = round(source_in * FPS)
    path = str(media_dir / file_name) if media_dir else f"D:\\podcast\\{file_name}"
    mapping = (
        '{"track_mapping":{"1":{"channel_idx":[1],"mute":false,"type":"mono"}}}'
        if track_type == TrackType.AUDIO
        else None
    )
    return ClipInfo(
        item_id=item_id,
        track_type=track_type,
        track_index=track,
        item_index=item_index,
        name=file_name,
        item_type=track_type.value,
        start_frame=start,
        end_frame=end,
        source_start_frame=source_start,
        source_end_frame=source_start + (end - start),
        source_start_seconds=source_start / FPS,
        source_end_seconds=(source_start + end - start) / FPS,
        left_offset_frames=float(source_start),
        right_offset_frames=None,
        media_pool_item_id=media_id,
        file_path=path,
        media_fps=FPS,
        linked_item_ids=linked,
        audio_channel_mapping=mapping,
    )


def podcast_layout(media_dir: Path | None = None) -> TimelineLayout:
    clips = (
        _clip(
            "v1-cam",
            TrackType.VIDEO,
            1,
            1,
            timeline_start=0,
            timeline_end=960,
            source_in=10,
            file_name="camera.mov",
            media_dir=media_dir,
            media_id="mpi-cam",
        ),
        _clip(
            "a1-c1",
            TrackType.AUDIO,
            1,
            1,
            timeline_start=0,
            timeline_end=600,
            source_in=10,
            file_name="mic_01.wav",
            media_dir=media_dir,
            media_id="mpi-mic1",
        ),
        _clip(
            "a1-c2",
            TrackType.AUDIO,
            1,
            2,
            timeline_start=890,
            timeline_end=960,
            source_in=30,
            file_name="mic_01b.wav",
            media_dir=media_dir,
            media_id="mpi-mic1b",
        ),
        _clip(
            "a2-c1",
            TrackType.AUDIO,
            2,
            1,
            timeline_start=0,
            timeline_end=300,
            source_in=10,
            file_name="mic_02.wav",
            media_dir=media_dir,
            media_id="mpi-mic2",
        ),
        _clip(
            "a2-c2",
            TrackType.AUDIO,
            2,
            2,
            timeline_start=320,
            timeline_end=600,
            source_in=330,
            file_name="mic_02.wav",
            media_dir=media_dir,
            media_id="mpi-mic2",
        ),
        _clip(
            "a3-c1",
            TrackType.AUDIO,
            3,
            1,
            timeline_start=0,
            timeline_end=600,
            source_in=10,
            file_name="mic_03.wav",
            media_dir=media_dir,
            media_id="mpi-mic3",
        ),
        _clip(
            "a4-c1",
            TrackType.AUDIO,
            4,
            1,
            timeline_start=0,
            timeline_end=600,
            source_in=10,
            file_name="mic_04.wav",
            media_dir=media_dir,
            media_id="mpi-mic4",
        ),
        _clip(
            "a5-c1",
            TrackType.AUDIO,
            5,
            1,
            timeline_start=0,
            timeline_end=30,
            source_in=0,
            file_name="music.wav",
            media_dir=media_dir,
            media_id="mpi-music",
        ),
    )
    tracks = (
        TrackInfo(TrackType.VIDEO, 1, "Camera"),
        *(
            TrackInfo(TrackType.AUDIO, index, name, "mono", True, False)
            for index, name in SPEAKERS.items()
        ),
        TrackInfo(TrackType.AUDIO, 5, "Musica", "stereo", True, False),
    )
    return TimelineLayout(
        project_name="Podcast",
        timeline_name="Episodio 1",
        timeline_id="tl-original",
        fps=FPS,
        start_frame=START_FRAME,
        end_frame=frames(DURATION_SECONDS),
        start_timecode="01:00:00:00",
        drop_frame=False,
        tracks=tracks,
        clips=clips,
        resolve_version="21.1.0",
        captured_at="2026-10-17T22:00:00Z",
    )


def write_podcast_media(media_dir: Path, layout: TimelineLayout | None = None) -> TimelineLayout:
    """Write mono 16 kHz source files for every audio clip of the fixture."""

    media_dir.mkdir(parents=True, exist_ok=True)
    layout = layout or podcast_layout(media_dir)
    files: dict[str, list[tuple[float, float, float, float]]] = {}
    lengths: dict[str, float] = {}
    for clip in layout.clips:
        if clip.track_type != TrackType.AUDIO or clip.file_path is None:
            continue
        assert clip.source_start_frame is not None and clip.source_end_frame is not None
        path = clip.file_path
        source_in = clip.source_start_frame / FPS
        source_out = clip.source_end_frame / FPS
        lengths[path] = max(lengths.get(path, 0.0), source_out + 5.0)
        files.setdefault(path, [])
        clip_start = (clip.start_frame - START_FRAME) / FPS
        clip_end = (clip.end_frame - START_FRAME) / FPS
        for burst in BURSTS:
            if burst.track != clip.track_index:
                continue
            if burst.start >= clip_start and burst.end <= clip_end:
                file_start = source_in + (burst.start - clip_start)
                file_end = source_in + (burst.end - clip_start)
                frequency = PHRASES[burst.phrase][0]
                files[path].append((file_start, file_end, frequency, burst.amplitude))
    for path, bursts in files.items():
        _write_tone_file(Path(path), lengths[path], bursts)
    return layout


def _write_tone_file(
    path: Path,
    length_seconds: float,
    bursts: list[tuple[float, float, float, float]],
) -> None:
    total = round(length_seconds * SAMPLE_RATE)
    samples = array("h", bytes(total * 2))
    for start, end, frequency, amplitude in bursts:
        first = round(start * SAMPLE_RATE)
        last = min(total, round(end * SAMPLE_RATE))
        peak = int(32767 * amplitude)
        step = 2.0 * math.pi * frequency / SAMPLE_RATE
        for index in range(first, last):
            samples[index] = int(peak * math.sin(step * (index - first)))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(samples.tobytes())


def phrase_for_frequency(frequency: float) -> str:
    phrase, _ = min(PHRASES.items(), key=lambda item: abs(item[1][0] - frequency))
    return phrase


def podcast_session(session_id: str = "0123456789abcdef") -> TranscriptSession:
    """A transcript session equivalent to transcribing the fixture (no audio needed)."""

    layout = podcast_layout()
    raw = [
        RawSegment(
            track_index=burst.track,
            start_frame=frames(burst.start),
            end_frame=frames(burst.end),
            text=PHRASES[burst.phrase][1],
            confidence=0.95,
            energy_db=-13.0 if burst.amplitude > 0.1 else -29.0,
        )
        for burst in BURSTS
    ]
    segments, _notes = detect_bleed(build_segments(raw, SPEAKERS))
    activity = {
        index: tuple(
            (frames(burst.start), frames(burst.end)) for burst in BURSTS if burst.track == index
        )
        for index in SPEAKERS
    }
    return TranscriptSession(
        session_id=session_id,
        revision=1,
        created_at="2026-10-17T22:00:00+00:00",
        updated_at="2026-10-17T22:00:00+00:00",
        project_name=layout.project_name,
        timeline_name=layout.timeline_name,
        timeline_id=layout.timeline_id,
        fps=layout.fps,
        start_frame=layout.start_frame,
        end_frame=layout.end_frame,
        start_timecode=layout.start_timecode,
        drop_frame=False,
        layout_fingerprint=layout.fingerprint,
        layout=layout.to_dict(),
        tracks=tuple(
            TranscribedTrack(index, name, "mono", segment_count=0)
            for index, name in SPEAKERS.items()
        ),
        segments=segments,
        activity=activity,
        language="pt",
        provider="mock",
        model="mock",
    )


def demo_phrase_resolver(frequency: float) -> str:
    return PHRASES[phrase_for_frequency(frequency)][1]
