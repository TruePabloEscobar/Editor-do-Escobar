from __future__ import annotations

import json
from pathlib import Path

from o_editor.domain.enums import SuggestionKind
from o_editor.domain.models import TextSuggestion
from o_editor.infrastructure.analysis.heuristic import HeuristicAnalyzer
from o_editor.infrastructure.config import load_config
from o_editor.infrastructure.resolve.mock_adapter import interview_timeline_fixture
from o_editor.infrastructure.transcription.mock import MockTranscriptionProvider


def test_interview_suggestions_match_golden(tmp_path) -> None:
    config = load_config(Path("config/defaults.json"))
    snapshot = interview_timeline_fixture()
    audio = tmp_path / "mock.wav"
    audio.write_bytes(b"mock")
    transcript = MockTranscriptionProvider().transcribe(
        audio,
        fps=snapshot.fps,
        timeline_start_frame=snapshot.start_frame,
        language="pt",
    )
    suggestions = HeuristicAnalyzer(
        zoom=config.zoom,
        text=config.text,
        configured_keywords=config.analysis.keywords,
    ).analyze(snapshot, transcript)
    actual = {
        "counts": {
            kind.value: sum(item.kind is kind for item in suggestions) for kind in SuggestionKind
        },
        "texts": [item.text for item in suggestions if isinstance(item, TextSuggestion)],
        "timeline_frames": sorted({item.timeline_start_frame for item in suggestions}),
        "zoom_subtypes": [item.subtype for item in suggestions if item.kind is SuggestionKind.ZOOM],
    }
    expected = json.loads(
        Path("tests/golden/interview_suggestions.json").read_text(encoding="utf-8")
    )
    assert actual == expected
