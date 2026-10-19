from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from o_editor.domain.enums import SuggestionKind, ZoomSubtype
from o_editor.domain.models import TextSuggestion, TimelineSnapshot
from o_editor.infrastructure.analysis.heuristic import HeuristicAnalyzer
from o_editor.infrastructure.config import load_config
from o_editor.infrastructure.resolve.mock_adapter import interview_timeline_fixture
from o_editor.infrastructure.transcription.mock import MockTranscriptionProvider


def _transcript(snapshot: TimelineSnapshot, tmp_path: Path):
    audio = tmp_path / "mock.wav"
    audio.write_bytes(b"mock")
    return MockTranscriptionProvider().transcribe(
        audio,
        fps=snapshot.fps,
        timeline_start_frame=snapshot.start_frame,
        language="pt",
    )


def test_question_signal_can_generate_punch_in(tmp_path) -> None:
    config = load_config(Path("config/defaults.json"))
    snapshot = interview_timeline_fixture()
    analyzer = HeuristicAnalyzer(
        zoom=replace(
            config.zoom,
            minimum_gap_seconds=0,
            maximum_per_minute=10,
        ),
        text=replace(config.text, enabled=False),
        configured_keywords=config.analysis.keywords,
    )
    suggestions = analyzer.analyze(snapshot, _transcript(snapshot, tmp_path))
    assert any(
        item.kind is SuggestionKind.ZOOM and item.subtype == ZoomSubtype.PUNCH_IN.value
        for item in suggestions
    )


def test_existing_fusion_comp_is_skipped_for_zoom(tmp_path) -> None:
    config = load_config(Path("config/defaults.json"))
    original = interview_timeline_fixture()
    items = (
        replace(original.items[0], fusion_comp_count=1),
        *original.items[1:],
    )
    snapshot = replace(original, items=items)
    suggestions = HeuristicAnalyzer(
        zoom=config.zoom,
        text=replace(config.text, enabled=False),
        configured_keywords=config.analysis.keywords,
    ).analyze(snapshot, _transcript(snapshot, tmp_path))
    assert all(item.clip_id != items[0].id for item in suggestions)


def test_generated_text_uses_only_source_words_and_respects_length(tmp_path) -> None:
    config = load_config(Path("config/defaults.json"))
    snapshot = interview_timeline_fixture()
    transcript = _transcript(snapshot, tmp_path)
    suggestions = HeuristicAnalyzer(
        zoom=replace(config.zoom, enabled=False),
        text=config.text,
        configured_keywords=config.analysis.keywords,
    ).analyze(snapshot, transcript)
    segments = {segment.id: segment for segment in transcript.segments}
    for suggestion in suggestions:
        assert isinstance(suggestion, TextSuggestion)
        words = suggestion.text.casefold().split()
        assert config.text.minimum_words <= len(words) <= config.text.maximum_words
        source = segments[suggestion.source_segment_ids[0]].text.casefold()
        assert all(word.strip(".,?!") in source for word in words)
