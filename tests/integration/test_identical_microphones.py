"""Same-level digital returns require audio proof, not just matching words."""

from __future__ import annotations

import wave
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from o_editor.application.rough_cut import prepare_rough_cut
from o_editor.domain.microphone_cleanup import MicrophoneCleanupSettings
from o_editor.domain.rough_cut import SilenceSettings, TrackPolicy
from o_editor.domain.speech import RawSegment, TranscribedTrack, build_segments
from tests.fixtures.podcast import podcast_session


def cached_session(tmp_path: Path, monkeypatch, *, identical: bool = True):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    base = podcast_session()
    start, fps, length = base.start_frame, base.fps, 240
    clips = []
    seen = set()
    for clip in base.layout["clips"]:
        key = (clip["track_type"], clip["track_index"])
        if key in seen or clip["track_index"] > 3:
            continue
        seen.add(key)
        clips.append(
            {
                **clip,
                "start_frame": start,
                "end_frame": start + length,
                "source_start_frame": 0,
                "source_end_frame": length,
                "source_start_seconds": 0.0,
                "source_end_seconds": length / fps,
                "left_offset_frames": 0.0,
                "right_offset_frames": None,
            }
        )
    from o_editor.domain.timeline_layout import TimelineLayout

    layout = TimelineLayout.from_dict({**base.layout, "end_frame": start + length, "clips": clips})
    tracks = []
    rng = np.random.default_rng(20)
    voice = rng.integers(-5000, 5000, 160_000, dtype=np.int16)
    for index in (1, 2, 3):
        key = f"{index:064x}"
        tracks.append(TranscribedTrack(index, f"Mic {index}", "mono", audio_cache_key=key))
        folder = tmp_path / "O Editor/cache/tracks" / key
        folder.mkdir(parents=True)
        samples = (
            voice
            if index == 1 or (index == 3 and identical)
            else rng.integers(-5000, 5000, 160_000, dtype=np.int16)
        )
        with wave.open(str(folder / "track.wav"), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16000)
            handle.writeframes(samples.tobytes())
    segments = build_segments(
        [
            RawSegment(1, start + 24, start + 216, "Vamos começar o programa agora", energy_db=-21),
            RawSegment(3, start + 24, start + 216, "Vamos começar o programa agora", energy_db=-21),
            RawSegment(2, start + 72, start + 96, "Eu tenho uma pergunta diferente", energy_db=-21),
        ],
        {t.track_index: t.name for t in tracks},
    )
    return replace(
        base,
        end_frame=start + length,
        layout=layout.to_dict(),
        layout_fingerprint=layout.fingerprint,
        tracks=tuple(tracks),
        segments=segments,
        activity={i: ((start, start + length),) for i in (1, 2, 3)},
    )


def enabled(plan, index, frame):
    return any(
        o.enabled
        for o in plan.operations
        if o.track_type.value == "audio"
        and o.track_index == index
        and o.record_start <= frame < o.record_end
    )


def test_identical_same_level_return_is_muted_but_another_voice_survives(tmp_path, monkeypatch):
    session = cached_session(tmp_path, monkeypatch)
    plan = prepare_rough_cut(
        session,
        silence=SilenceSettings(enabled=False),
        microphone_cleanup=MicrophoneCleanupSettings(enabled=True),
    )
    frame = session.start_frame + 80
    assert not plan.blocked
    assert enabled(plan, 1, frame)
    assert enabled(plan, 2, frame)
    assert not enabled(plan, 3, frame)
    assert plan.stats.new_frames == plan.stats.original_frames
    assert all(c["enabled"] for c in session.layout["clips"])


def test_same_words_and_levels_without_identical_signal_keep_both(tmp_path, monkeypatch):
    session = cached_session(tmp_path, monkeypatch, identical=False)
    plan = prepare_rough_cut(
        session,
        silence=SilenceSettings(enabled=False),
        microphone_cleanup=MicrophoneCleanupSettings(enabled=True),
    )
    assert enabled(plan, 1, session.start_frame + 80)
    assert enabled(plan, 3, session.start_frame + 80)


def test_cleanup_off_preserves_even_proven_digital_copies(tmp_path, monkeypatch):
    session = cached_session(tmp_path, monkeypatch)
    plan = prepare_rough_cut(
        session,
        silence=SilenceSettings(enabled=False),
        microphone_cleanup=MicrophoneCleanupSettings(enabled=False),
    )
    assert enabled(plan, 3, session.start_frame + 80)
    assert plan.microphone_mutes == ()


@pytest.mark.parametrize("source_state", ["omitted", "disabled"])
def test_reference_that_will_not_be_audible_cannot_mute_remaining_copy(
    tmp_path, monkeypatch, source_state
):
    from o_editor.domain.timeline_layout import TimelineLayout

    session = cached_session(tmp_path, monkeypatch)
    policies = {}
    if source_state == "omitted":
        policies["A1"] = TrackPolicy.OMIT
    else:
        layout = TimelineLayout.from_dict(dict(session.layout))
        layout = replace(
            layout,
            tracks=tuple(replace(t, enabled=False) if t.key == "A1" else t for t in layout.tracks),
        )
        session = replace(session, layout=layout.to_dict(), layout_fingerprint=layout.fingerprint)
    original = session.to_dict()
    plan = prepare_rough_cut(
        session,
        silence=SilenceSettings(enabled=False),
        track_policies=policies,
        microphone_cleanup=MicrophoneCleanupSettings(enabled=True),
    )
    assert not plan.blocked
    assert enabled(plan, 3, session.start_frame + 50)
    assert enabled(plan, 3, session.start_frame + 150)
    assert session.to_dict() == original


def test_explicit_reactions_and_uncovered_speech_tails_stay_audible(tmp_path, monkeypatch):
    from o_editor.domain.speech import SegmentFlag

    session = cached_session(tmp_path, monkeypatch)
    start = session.start_frame
    reaction = build_segments([RawSegment(3, start + 110, start + 130, "(risos)")], {3: "C"})[0]
    reaction = replace(reaction, segment_id="SEG_0099")
    assert SegmentFlag.NON_SPEECH in reaction.flags
    session = replace(session, segments=(*session.segments, reaction))
    plan = prepare_rough_cut(
        session,
        silence=SilenceSettings(enabled=False),
        microphone_cleanup=MicrophoneCleanupSettings(enabled=True),
    )
    assert enabled(plan, 3, start + 120)
    assert not enabled(plan, 3, start + 160)
    # ASR can give the copy a longer phrase: do not drop the uncovered tail globally.
    session = replace(
        session,
        segments=(
            replace(session.segments[0], end_frame=start + 100),
            replace(session.segments[1], end_frame=start + 180),
        ),
    )
    plan = prepare_rough_cut(
        session,
        silence=SilenceSettings(protect_untranscribed_sound=False),
        microphone_cleanup=MicrophoneCleanupSettings(enabled=True),
    )
    assert any(k.source_start <= start + 160 < k.source_end for k in plan.keep_ranges)
    assert enabled(
        plan,
        3,
        next(
            k.record_start + start + 160 - k.source_start
            for k in plan.keep_ranges
            if k.source_start <= start + 160 < k.source_end
        ),
    )


@pytest.mark.parametrize("fault", ["missing", "truncated", "corrupt", "truncated_data"])
def test_invalid_or_absent_cache_is_not_proof_of_return(tmp_path, monkeypatch, fault):
    session = cached_session(tmp_path, monkeypatch)
    for track in session.tracks:
        if track.track_index not in (1, 3):
            continue
        path = tmp_path / "O Editor/cache/tracks" / track.audio_cache_key / "track.wav"
        if fault == "missing":
            path.unlink()
        elif fault == "corrupt":
            path.write_bytes(b"same-but-invalid")
        elif fault == "truncated_data":
            path.write_bytes(path.read_bytes()[:-1])
        else:
            with wave.open(str(path), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(16000)
                handle.writeframes(b"\x01\x00" * 160)
    plan = prepare_rough_cut(
        session,
        silence=SilenceSettings(enabled=False),
        microphone_cleanup=MicrophoneCleanupSettings(enabled=True),
    )
    assert enabled(plan, 1, session.start_frame + 80)
    assert enabled(plan, 3, session.start_frame + 80)
