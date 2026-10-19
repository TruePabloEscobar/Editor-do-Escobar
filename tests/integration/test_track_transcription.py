"""Tests A and B: per-track rendering + transcription with absolute timeline time."""

from __future__ import annotations

import shutil
import wave
from pathlib import Path

import pytest

from o_editor.application.transcribe_tracks import TranscribeTracks
from o_editor.domain.enums import ChannelMode
from o_editor.domain.speech import SegmentFlag, TranscriptSession
from o_editor.domain.voice_tracks import SelectedVoiceTrack
from o_editor.infrastructure.audio.track_renderer import TrackAudioRenderer
from o_editor.infrastructure.cache import JsonCache
from o_editor.infrastructure.ffmpeg.runner import FFmpegRunner
from o_editor.infrastructure.transcript_sessions import SessionStore
from o_editor.infrastructure.transcription.track import SignalMockTranscriber
from tests.fixtures.podcast import (
    BURSTS,
    DURATION_SECONDS,
    PHRASES,
    SPEAKERS,
    frames,
    phrase_for_frequency,
    write_podcast_media,
)

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
pytestmark = pytest.mark.skipif(
    FFMPEG is None or FFPROBE is None, reason="FFmpeg/FFprobe não disponíveis"
)


def _resolver(frequency: float) -> str:
    return PHRASES[phrase_for_frequency(frequency)][1]


@pytest.fixture(scope="module")
def transcribed(tmp_path_factory: pytest.TempPathFactory) -> tuple[TranscriptSession, Path]:
    root = tmp_path_factory.mktemp("podcast")
    layout = write_podcast_media(root / "media")
    assert FFMPEG and FFPROBE
    runner = FFmpegRunner(ffmpeg_path=Path(FFMPEG), ffprobe_path=Path(FFPROBE))
    service = TranscribeTracks(
        layout=layout,
        selected_tracks=tuple(
            SelectedVoiceTrack(index, name, ChannelMode.MONO) for index, name in SPEAKERS.items()
        ),
        renderer=TrackAudioRenderer(runner, root / "cache"),
        transcriber=SignalMockTranscriber(_resolver),
        transcript_cache=JsonCache(root / "cache"),
        session_store=SessionStore(root / "sessions"),
        language="pt",
    )
    return service.execute(), root


def test_a_four_tracks_produce_four_separate_transcripts(
    transcribed: tuple[TranscriptSession, Path],
) -> None:
    session, _root = transcribed
    assert [track.name for track in session.tracks] == ["Pablo", "Jessica", "Mileni", "Renne"]
    for index, name in SPEAKERS.items():
        own = [item for item in session.segments_for_track(index) if not item.is_bleed]
        expected = {
            PHRASES[burst.phrase][1]
            for burst in BURSTS
            if burst.track == index and burst.amplitude > 0.1
        }
        assert {item.text for item in own} == expected, name
        assert all(item.speaker == name for item in own)


def test_b_speech_at_minute_15_has_absolute_timeline_time(
    transcribed: tuple[TranscriptSession, Path],
) -> None:
    session, _root = transcribed
    minute_15 = [item for item in session.segments if item.text == PHRASES["p4"][1]]
    assert len(minute_15) == 1
    segment = minute_15[0]
    # The source file holds this phrase at 40 s, the clip starts at 14:50 with a
    # 30 s in-point: the timeline position must be 15:00 regardless of the file.
    assert abs(segment.start_frame - frames(900.0)) <= 1
    assert abs(segment.end_frame - frames(904.0)) <= 7  # activity hangover


def test_overlap_and_bleed_are_flagged(transcribed: tuple[TranscriptSession, Path]) -> None:
    session, _root = transcribed
    pablo_overlap = next(item for item in session.segments if item.text == PHRASES["p2"][1])
    jessica_overlap = next(item for item in session.segments if item.text == PHRASES["j2"][1])
    assert SegmentFlag.OVERLAP in pablo_overlap.flags
    assert SegmentFlag.OVERLAP in jessica_overlap.flags
    leaked = [item for item in session.segments_for_track(3) if item.text == PHRASES["p3"][1]]
    assert len(leaked) == 1
    assert leaked[0].is_bleed
    assert not leaked[0].protects_audio
    original = session.segment(leaked[0].related_segment_id or "")
    assert original is not None and original.track_index == 1


def test_no_speech_is_invented_over_silence(transcribed: tuple[TranscriptSession, Path]) -> None:
    session, _root = transcribed
    expected = len(BURSTS)
    assert len(session.segments) == expected
    assert all(item.start_frame >= session.start_frame for item in session.segments)
    for item in session.segments:
        assert item.segment_id.startswith("SEG_")
    ids = [item.segment_id for item in session.segments]
    assert ids == sorted(ids)


def test_rendered_tracks_are_sample_aligned(transcribed: tuple[TranscriptSession, Path]) -> None:
    session, root = transcribed
    for track in session.tracks:
        assert track.audio_cache_key
        path = root / "cache" / "tracks" / track.audio_cache_key / "track.wav"
        with wave.open(str(path), "rb") as handle:
            assert handle.getframerate() == 16_000
            assert handle.getnframes() == DURATION_SECONDS * 16_000


def test_session_is_persisted_and_reloadable(transcribed: tuple[TranscriptSession, Path]) -> None:
    session, root = transcribed
    reloaded = SessionStore(root / "sessions").load(session.session_id)
    assert reloaded == session
    assert set(reloaded.activity) == {1, 2, 3, 4}
