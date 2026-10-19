from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from o_editor.domain.enums import SuggestionKind, TextSubtype, TrackType
from o_editor.domain.models import (
    TextSuggestion,
    TimelineItemSnapshot,
    TimelineSnapshot,
)


def make_snapshot() -> TimelineSnapshot:
    item = TimelineItemSnapshot.create(
        track_type=TrackType.VIDEO,
        track_index=1,
        start_frame=100,
        end_frame=400,
        source_start_frame=0,
        source_end_frame=300,
        name="Entrevista A",
        media_id="media-1",
    )
    return TimelineSnapshot(
        project_name="Projeto",
        timeline_name="Entrevista",
        timeline_id="timeline-1",
        fps=29.97,
        drop_frame=True,
        start_frame=100,
        end_frame=1000,
        video_track_count=1,
        audio_track_count=1,
        items=(item,),
    )


def test_fingerprint_is_stable_and_sensitive() -> None:
    first = make_snapshot()
    second = make_snapshot()
    changed = TimelineSnapshot(
        project_name=first.project_name,
        timeline_name=first.timeline_name,
        timeline_id=first.timeline_id,
        fps=first.fps,
        drop_frame=first.drop_frame,
        start_frame=first.start_frame,
        end_frame=first.end_frame + 1,
        video_track_count=first.video_track_count,
        audio_track_count=first.audio_track_count,
        items=first.items,
    )
    assert first.fingerprint == second.fingerprint
    assert first.fingerprint != changed.fingerprint


def test_snapshot_round_trip_json() -> None:
    snapshot = make_snapshot()
    rebuilt = TimelineSnapshot.from_dict(snapshot.to_dict())
    assert rebuilt == snapshot
    assert rebuilt.to_dict()["schema_version"] == "1.0"


def test_models_are_immutable() -> None:
    snapshot = make_snapshot()
    with pytest.raises(FrozenInstanceError):
        snapshot.timeline_name = "Mudou"  # type: ignore[misc]


def test_text_suggestion_edit_returns_new_revision() -> None:
    suggestion = TextSuggestion.create(
        subtype=TextSubtype.NUMBER,
        timeline_start_frame=120,
        timeline_end_frame=180,
        confidence=0.9,
        importance=0.85,
        reason_codes=("NUMBER",),
        source_segment_ids=("seg_1",),
        text="50% menos tempo",
        parameters=(("style", "keyword"),),
    )
    edited = suggestion.with_text("50% de economia")
    assert suggestion.kind is SuggestionKind.TEXT
    assert suggestion.text == "50% menos tempo"
    assert edited.text == "50% de economia"
    assert edited.edited_by_user


def test_invalid_suggestion_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="end_frame"):
        TextSuggestion.create(
            subtype=TextSubtype.KEYWORD,
            timeline_start_frame=100,
            timeline_end_frame=100,
            confidence=0.5,
            importance=0.5,
            reason_codes=(),
            source_segment_ids=("seg_1",),
            text="Ideia central",
            parameters=(),
        )
