"""Planner work must scale with relevant track intervals, not all mutes per clip."""

import random
from dataclasses import replace

from o_editor.domain.microphone_cleanup import MicrophoneMute
from o_editor.domain.rough_cut import KeepRange, _operations
from scripts.benchmark_planner import scenario


def test_mute_lookup_preserves_decisions_without_rescanning_all_intervals():
    _session, layout = scenario(200)
    reads = []

    class CountedMute(MicrophoneMute):
        def __getattribute__(self, name):
            if name == "track_index":
                reads.append(1)
            return super().__getattribute__(name)

    mutes = tuple(
        CountedMute(track, start, start + 30, "test")
        for start in range(0, layout.end_frame, 60)
        for track in (2, 3, 4, 5)
    )
    keeps = tuple(KeepRange(start, start + 30, start) for start in range(0, layout.end_frame, 30))
    result = _operations(layout, keeps, {}, [], mutes)
    work = len(reads)
    expected = tuple(
        not any(
            m.track_index == operation.track_index
            and m.start_frame <= operation.record_start
            and operation.record_end <= m.end_frame
            for m in mutes
        )
        if operation.media_type == 2
        else True
        for operation in result
    )
    assert tuple(o.enabled for o in result) == expected
    # Bound inspected mute identities, a deterministic cost metric, not wall-clock speed.
    assert work <= len(mutes) * 2 + len(result) * 2


def test_mute_index_matches_old_rule_for_nested_intervals_and_disabled_sources():
    _session, layout = scenario(8)
    layout = replace(
        layout,
        clips=tuple(replace(c, enabled=False) if c.track_index == 5 else c for c in layout.clips),
    )
    rng = random.Random(17)
    mutes = [MicrophoneMute(2, 0, 900, "long"), MicrophoneMute(2, 10, 20, "nested")]
    for _ in range(150):
        start = rng.randrange(900)
        mutes.append(
            MicrophoneMute(rng.randrange(1, 6), start, start + rng.randrange(1, 80), "test")
        )
    keeps = tuple(KeepRange(n, n + 10, n) for n in range(0, 950, 10))
    result = _operations(layout, keeps, {}, [], tuple(mutes))
    for operation in result:
        clip = layout.clip_by_id(operation.source_item_id)
        assert clip is not None
        expected = clip.enabled and not any(
            operation.media_type == 2
            and m.track_index == operation.track_index
            and m.start_frame <= operation.record_start
            and operation.record_end <= m.end_frame
            for m in mutes
        )
        assert operation.enabled == expected
