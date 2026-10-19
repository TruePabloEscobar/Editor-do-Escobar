from __future__ import annotations

import pytest

from o_editor.domain.scoring import (
    ImportanceSignals,
    score_importance,
    select_by_frequency,
)
from o_editor.domain.timecode import frames_to_timecode, seconds_to_frames


def test_seconds_to_frames_uses_half_up_rounding() -> None:
    assert seconds_to_frames(1.5, 29.97) == 45
    assert seconds_to_frames(1.0, 24, timeline_start_frame=100) == 124


def test_non_drop_timecode() -> None:
    assert frames_to_timecode(108_000, 30) == "01:00:00:00"


def test_drop_frame_timecode() -> None:
    assert frames_to_timecode(107_892, 29.97, drop_frame=True) == "01:00:00;00"


def test_invalid_drop_frame_rate_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"29\.97"):
        frames_to_timecode(100, 24, drop_frame=True)


def test_importance_is_deterministic_and_bounded() -> None:
    strong = score_importance(
        ImportanceSignals(
            numeric=True,
            conclusion=True,
            contrast=True,
            configured_keyword=True,
            pause_before_seconds=4,
        )
    )
    repeated = score_importance(ImportanceSignals(conclusion=True, repetition_count=5))
    assert strong == 1.0
    assert 0 <= repeated < strong


def test_frequency_selects_best_non_conflicting_candidates() -> None:
    selected = select_by_frequency(
        [(0, 0.8), (24, 0.95), (300, 0.7)],
        fps=24,
        minimum_gap_seconds=5,
        maximum_per_minute=10,
        duration_frames=1_440,
    )
    assert selected == {24, 300}
