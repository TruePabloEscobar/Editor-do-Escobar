"""Microphone decisions preserve simultaneous voices, reactions and source time."""

from dataclasses import replace

from o_editor.application.rough_cut import prepare_rough_cut
from o_editor.domain.microphone_cleanup import MicrophoneCleanupSettings
from o_editor.domain.rough_cut import SilenceSettings
from o_editor.domain.speech import RawSegment, build_segments
from tests.fixtures.podcast import podcast_session


def session():
    base = podcast_session()
    segments = build_segments(
        [
            RawSegment(1, 100, 200, "Vamos começar o programa agora", energy_db=-15),
            RawSegment(2, 100, 200, "Vamos começar o programa agora", energy_db=-35),
            RawSegment(1, 300, 400, "Uma pergunta diferente", energy_db=-15),
            RawSegment(2, 320, 420, "Eu tenho outra resposta", energy_db=-32),
            RawSegment(3, 140, 160, "(risos)", energy_db=-30),
            RawSegment(1, 500, 600, "Sim", energy_db=-20),
            RawSegment(2, 500, 600, "Sim", energy_db=-21),
        ],
        {1: "Pablo", 2: "Jessica", 3: "Mileni", 4: "Renne"},
    )
    return replace(
        base,
        segments=tuple(
            replace(
                x,
                start_frame=x.start_frame + base.start_frame,
                end_frame=x.end_frame + base.start_frame,
            )
            for x in segments
        ),
        activity={
            1: ((100, 200), (300, 400), (500, 600)),
            2: ((100, 200), (320, 420), (500, 600)),
            3: ((140, 160),),
            4: (),
        },
    )


def plan(s=None, *, enabled=True):
    value = s or session()
    value = replace(
        value,
        activity={
            k: tuple((lo + value.start_frame, hi + value.start_frame) for lo, hi in ranges)
            for k, ranges in value.activity.items()
        },
    )
    return prepare_rough_cut(
        value,
        silence=SilenceSettings(enabled=False),
        microphone_cleanup=MicrophoneCleanupSettings(
            enabled=enabled, guard_before_ms=0, guard_after_ms=0
        ),
    )


def active(p, track, frame):
    frame += p.layout.start_frame
    return any(
        o.enabled
        for o in p.operations
        if o.track_type.value == "audio"
        and o.track_index == track
        and o.record_start <= frame < o.record_end
    )


def test_duplicate_weak_voice_is_disabled_while_distinct_overlap_stays():
    p = plan()
    assert not p.blocked
    assert active(p, 1, 120) and not active(p, 2, 120)
    assert not active(p, 4, 120)
    assert active(p, 1, 350) and active(p, 2, 350)
    assert active(p, 1, 550) and active(p, 2, 550)  # uncertain primary: keep both
    assert active(p, 4, 250)  # no speaker: no unsolicited muting
    assert p.stats.removed_frames == 0
    assert p.stats.new_frames == p.stats.original_frames


def test_laughter_and_untranscribed_sounds_survive_but_bleed_does_not():
    s = session()
    s = replace(s, activity={**s.activity, 4: ((170, 190),)})
    p = plan(s)
    assert active(p, 3, 150) and active(p, 4, 180)
    assert not active(p, 2, 150)


def test_off_preserves_all_original_operations_and_music():
    p = plan(enabled=False)
    assert p.microphone_mutes == ()
    assert all(o.enabled for o in p.operations)
    p = plan()
    assert all(o.enabled for o in p.operations if o.track_index == 5)
    assert p.to_dict()["microphone_cleanup"]["enabled"] is True


def test_missing_activity_is_conservative_and_different_similar_words_survive():
    s = session()
    segs = build_segments(
        [
            RawSegment(1, 100, 200, "Eu concordo com isso", energy_db=-10),
            RawSegment(2, 100, 200, "Eu não concordo com isso", energy_db=-40),
        ],
        {1: "A", 2: "B"},
    )
    p = plan(
        replace(
            s,
            segments=tuple(
                replace(
                    x,
                    start_frame=x.start_frame + s.start_frame,
                    end_frame=x.end_frame + s.start_frame,
                )
                for x in segs
            ),
            activity={},
        )
    )
    assert active(p, 1, 150) and active(p, 2, 150) and active(p, 4, 150)


def test_all_native_siblings_share_split_boundaries_and_source_offsets():
    p = plan()
    for o in p.operations:
        assert o.record_end - o.record_start == o.source_end - o.source_start
    # At a common camera/microphone source boundary, global timing stays aligned.
    assert all(o.record_end > o.record_start for o in p.operations)
    assert p.stats.new_frames == p.layout.duration_frames


def test_old_loose_bleed_flag_cannot_delete_different_speech_tail():
    from o_editor.domain.intervals import intersect
    from o_editor.domain.speech import SegmentFlag

    s = session()
    start = s.start_frame
    segments = build_segments(
        [
            RawSegment(1, start + 100, start + 200, "Eu concordo com a ideia", energy_db=-10),
            RawSegment(2, start + 100, start + 250, "Eu não concordo com a ideia", energy_db=-30),
        ],
        {1: "A", 2: "B"},
    )
    segments = (segments[0], replace(segments[1], flags=segments[1].flags | {SegmentFlag.BLEED}))
    s = replace(
        s,
        segments=segments,
        activity={1: ((start + 100, start + 200),), 2: ((start + 100, start + 250),)},
    )
    p = prepare_rough_cut(
        s,
        silence=SilenceSettings(protect_untranscribed_sound=False),
        microphone_cleanup=MicrophoneCleanupSettings(enabled=True),
    )
    assert not intersect(
        ((start + 200, start + 250),), ((x.start_frame, x.end_frame) for x in p.removed_ranges)
    )
    assert not any(
        m.track_index == 2 and m.start_frame < start + 250 and m.end_frame > start + 100
        for m in p.microphone_mutes
    )
