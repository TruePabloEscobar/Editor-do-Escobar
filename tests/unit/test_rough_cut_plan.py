"""Tests E, F and G (plan level): silence, simultaneous speech and global sync."""

from __future__ import annotations

from dataclasses import replace

import pytest

from o_editor.domain.enums import TrackType
from o_editor.domain.intervals import intersect, normalize, subtract, total, union
from o_editor.domain.rough_cut import (
    CutSettings,
    RoughCutPlan,
    SilencePreset,
    SilenceSettings,
    TrackPolicy,
    build_rough_cut_plan,
)
from o_editor.domain.speech import SegmentState, TranscriptSession
from tests.fixtures.podcast import PHRASES, frames, podcast_layout, podcast_session

NO_SILENCE = SilenceSettings(enabled=False)


def _plan(
    session: TranscriptSession,
    *,
    silence: SilenceSettings = NO_SILENCE,
    policies: dict[str, TrackPolicy] | None = None,
) -> RoughCutPlan:
    return build_rough_cut_plan(
        session,
        podcast_layout(),
        silence=silence,
        cut=CutSettings(),
        track_policies=policies,
        target_timeline_name="Episodio 1_OE_ROUGHCUT_001",
        plan_id="plan-test",
        created_at="2026-10-17T23:00:00+00:00",
    )


def _cut(session: TranscriptSession, phrase: str) -> TranscriptSession:
    return replace(
        session,
        segments=tuple(
            item.with_state(SegmentState.CUT)
            if item.text == PHRASES[phrase][1] and not item.is_bleed
            else item
            for item in session.segments
        ),
    )


def _removed(plan: RoughCutPlan) -> tuple[tuple[int, int], ...]:
    return tuple((item.start_frame, item.end_frame) for item in plan.removed_ranges)


def test_intervals_algebra() -> None:
    assert normalize([(5, 7), (1, 3), (2, 4)]) == ((1, 4), (5, 7))
    assert subtract([(0, 10)], [(2, 3), (5, 6)]) == ((0, 2), (3, 5), (6, 10))
    assert intersect([(0, 5), (8, 12)], [(4, 9)]) == ((4, 5), (8, 9))
    assert union([(0, 1)], [(1, 2)]) == ((0, 2),)
    assert total([(0, 2), (1, 4)]) == 4


def test_unchanged_transcript_without_silence_rule_removes_nothing() -> None:
    plan = _plan(podcast_session())
    assert not plan.blocked
    assert plan.removed_ranges == ()
    assert plan.stats.new_frames == plan.stats.original_frames
    clip_count = sum(1 for clip in podcast_layout().clips)
    assert len(plan.operations) == clip_count


def test_cut_segment_produces_exactly_that_range() -> None:
    plan = _plan(_cut(podcast_session(), "p3"))
    assert _removed(plan) == ((frames(40.0), frames(44.0)),)
    assert plan.removed_ranges[0].reasons == ("TEXTO_CUT",)
    assert plan.stats.removed_segments == 1


def test_e_silence_between_speakers_is_removed_with_margins() -> None:
    session = podcast_session()
    plan = _plan(session, silence=SilenceSettings.from_preset(SilencePreset.MEDIUM))
    assert not plan.blocked
    fps = 24.0
    long_pause = (frames(63.0) + round(0.35 * fps), frames(330.0) - round(0.25 * fps))
    assert long_pause in _removed(plan)
    removed = _removed(plan)
    for segment in session.segments:
        assert total(intersect([(segment.start_frame, segment.end_frame)], removed)) == 0
    # leading and trailing silence trimmed with margins
    assert removed[0] == (frames(0.0), frames(2.0) - round(0.25 * fps))
    assert removed[-1][1] == podcast_layout().end_frame
    assert plan.stats.silence_frames == plan.stats.removed_frames


def test_short_pauses_are_preserved() -> None:
    plan = _plan(podcast_session(), silence=SilenceSettings.from_preset(SilencePreset.LIGHT))
    # 6 s -> 7 s between Pablo and Jessica is shorter than the 2 s minimum: untouched.
    assert total(intersect([(frames(6.0), frames(7.0))], _removed(plan))) == 0


def test_f_simultaneous_speech_is_never_cut() -> None:
    session = _cut(podcast_session(), "p2")  # Pablo 20-24 while Jessica speaks 22-26
    plan = _plan(session, silence=SilenceSettings.from_preset(SilencePreset.STRONG))
    jessica = next(item for item in session.segments if item.text == PHRASES["j2"][1])
    removed = _removed(plan)
    assert total(intersect([(jessica.start_frame, jessica.end_frame)], removed)) == 0
    guard = round(0.1 * 24.0)
    pablo_only = (frames(20.0), jessica.start_frame - guard)
    assert total(intersect([pablo_only], removed)) == pablo_only[1] - pablo_only[0]
    assert total(intersect([(jessica.start_frame - guard, jessica.start_frame)], removed)) == 0
    assert any("parcialmente" in issue.message for issue in plan.issues)


def test_cut_fully_covered_by_other_speaker_is_reported_not_removed() -> None:
    session = podcast_session()
    jessica = next(item for item in session.segments if item.text == PHRASES["j2"][1])
    session = replace(
        session,
        segments=tuple(
            replace(
                item,
                start_frame=jessica.start_frame + 5,
                end_frame=jessica.end_frame - 5,
                state=SegmentState.CUT,
            )
            if item.text == PHRASES["p2"][1]
            else item
            for item in session.segments
        ),
    )
    plan = _plan(session)
    assert plan.removed_ranges == ()
    assert any("não foi removido" in issue.message for issue in plan.issues)


def test_g_every_track_uses_the_same_global_ranges() -> None:
    session = _cut(_cut(podcast_session(), "p3"), "r1")
    plan = _plan(session, silence=SilenceSettings.from_preset(SilencePreset.MEDIUM))
    assert not plan.blocked
    offsets: dict[int, set[int]] = {}
    for operation in plan.operations:
        keep = plan.keep_ranges[operation.keep_index]
        shift = keep.record_start - keep.source_start
        layout_clip = podcast_layout().clip_by_id(operation.source_item_id)
        assert layout_clip is not None
        timeline_start = layout_clip.start_frame + (
            operation.source_start - (layout_clip.source_start_frame or 0)
        )
        assert operation.record_start - timeline_start == shift
        assert (
            operation.record_end - operation.record_start
            == operation.source_end - operation.source_start
        )
        offsets.setdefault(operation.keep_index, set()).add(operation.record_start - timeline_start)
    assert all(len(values) == 1 for values in offsets.values())
    # The camera (V1) covers every kept range exactly like the microphones.
    video = [item for item in plan.operations if item.track_type == TrackType.VIDEO]
    assert sum(item.record_end - item.record_start for item in video) == plan.stats.new_frames
    # New timeline is contiguous.
    cursor = podcast_layout().start_frame
    for keep in plan.keep_ranges:
        assert keep.record_start == cursor
        cursor += keep.duration_frames


def test_track_policy_omit_skips_music() -> None:
    plan = _plan(podcast_session(), policies={"A5": TrackPolicy.OMIT})
    assert not any(
        item.track_type == TrackType.AUDIO and item.track_index == 5 for item in plan.operations
    )
    assert plan.track_policies["A5"] == TrackPolicy.OMIT


def test_pending_missing_and_changed_timeline_block_the_plan() -> None:
    session = replace(podcast_session(), pending_missing=("SEG_0003",))
    assert _plan(session).blocked
    other = replace(podcast_session(), layout_fingerprint="different")
    assert _plan(other).blocked


@pytest.mark.parametrize("preset", list(SilencePreset))
def test_presets_never_touch_protected_speech(preset: SilencePreset) -> None:
    session = podcast_session()
    plan = _plan(session, silence=SilenceSettings.from_preset(preset))
    removed = _removed(plan)
    for segment in session.segments:
        if segment.protects_audio:
            assert total(intersect([(segment.start_frame, segment.end_frame)], removed)) == 0


def test_unsupported_audio_clip_blocks_but_video_only_warns() -> None:
    layout = podcast_layout()
    clips = tuple(
        replace(clip, speed_percent=150.0) if clip.item_id in {"a4-c1", "v1-cam"} else clip
        for clip in layout.clips
    )
    changed = replace(layout, clips=clips)
    session = replace(podcast_session(), layout_fingerprint=changed.fingerprint)
    plan = build_rough_cut_plan(
        session,
        changed,
        silence=NO_SILENCE,
        cut=CutSettings(),
        target_timeline_name="x",
        plan_id="p",
        created_at="2026-10-17T23:00:00Z",
    )
    assert plan.blocked
    assert any("A4" in issue.message and issue.severity == "BLOQUEIO" for issue in plan.issues)
    assert any("V1" in issue.message and issue.severity == "AVISO" for issue in plan.issues)
    omitted = build_rough_cut_plan(
        session,
        changed,
        silence=NO_SILENCE,
        cut=CutSettings(),
        track_policies={"A4": TrackPolicy.OMIT},
        target_timeline_name="x",
        plan_id="p",
        created_at="2026-10-17T23:00:00Z",
    )
    assert not omitted.blocked
