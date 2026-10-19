from __future__ import annotations

from pathlib import Path

from o_editor.application.analyze_timeline import AnalyzeTimeline
from o_editor.domain.enums import ChannelMode, SuggestionKind
from o_editor.domain.voice_tracks import SelectedVoiceTrack
from o_editor.infrastructure.analysis.heuristic import HeuristicAnalyzer
from o_editor.infrastructure.cache import JsonCache
from o_editor.infrastructure.config import load_config
from o_editor.infrastructure.resolve.audio_exporter import MockAudioExporter
from o_editor.infrastructure.resolve.mock_adapter import MockResolveAdapter
from o_editor.infrastructure.transcription.mock import MockTranscriptionProvider


def test_mock_analysis_pipeline_and_cache(tmp_path) -> None:
    config = load_config(Path("config/defaults.json"))
    adapter = MockResolveAdapter()
    service = AnalyzeTimeline(
        adapter=adapter,
        audio_exporter=MockAudioExporter(adapter),
        transcription_provider=MockTranscriptionProvider(),
        analyzer=HeuristicAnalyzer(
            zoom=config.zoom,
            text=config.text,
            configured_keywords=config.analysis.keywords,
        ),
        cache=JsonCache(tmp_path / "cache"),
        selected_voice_tracks=(
            SelectedVoiceTrack(2, "Lapela Pablo", ChannelMode.MONO),
            SelectedVoiceTrack(3, "Lapela convidado", ChannelMode.MONO),
        ),
        audio_backend="mock_voice_tracks",
    )
    first = service.execute(tmp_path, language="pt")
    second = service.execute(tmp_path, language="pt")
    assert first.snapshot.fingerprint == second.snapshot.fingerprint
    assert first.transcript == second.transcript
    assert first.suggestions == second.suggestions
    assert {item.kind for item in first.suggestions} == {
        SuggestionKind.ZOOM,
        SuggestionKind.TEXT,
    }
    assert first.audio_path.is_file()
    assert adapter.original_snapshot.timeline_name == "Entrevista Mock"
