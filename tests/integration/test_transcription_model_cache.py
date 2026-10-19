"""Switching local models must invalidate text caches, while retaining audio."""

from pathlib import Path
from types import SimpleNamespace

from o_editor.application.transcribe_tracks import TranscribeTracks
from o_editor.infrastructure.cache import JsonCache
from o_editor.infrastructure.transcription.track import TimedSegment, TrackTranscriptionResult


def test_same_named_models_in_different_directories_do_not_share_transcripts(tmp_path: Path):
    calls = []

    class Transcriber:
        name = "faster-whisper"
        model_name = "same-label"

        def __init__(self, identity):
            self.cache_identity = identity

        def transcribe_track(self, path, **kwargs):
            calls.append(self.cache_identity)
            return TrackTranscriptionResult(
                (TimedSegment(0, 1, self.cache_identity),), "pt", self.name, self.model_name
            )

    service = object.__new__(TranscribeTracks)
    service._cache = JsonCache(tmp_path)
    service._language = "pt"
    rendered = SimpleNamespace(cache_key="same-audio", path=tmp_path / "audio.wav")
    service._transcriber = Transcriber("model-folder-A")
    first = service._transcribe(rendered, False, None, None)
    service._transcriber = Transcriber("model-folder-B")
    second = service._transcribe(rendered, False, None, None)
    again = service._transcribe(rendered, False, None, None)
    assert first.segments[0].text == "model-folder-A"
    assert second.segments[0].text == "model-folder-B"
    assert again == second
    assert calls == ["model-folder-A", "model-folder-B"]


def test_analysis_model_switch_reuses_audio_but_retranscribes_text(tmp_path):
    from o_editor.application.analyze_timeline import AnalyzeTimeline
    from o_editor.infrastructure.analysis.heuristic import HeuristicAnalyzer
    from o_editor.infrastructure.config import load_config
    from o_editor.infrastructure.resolve.audio_exporter import MockAudioExporter
    from o_editor.infrastructure.resolve.mock_adapter import MockResolveAdapter
    from o_editor.infrastructure.transcription.mock import MockTranscriptionProvider

    config = load_config(Path("config/defaults.json"))
    adapter = MockResolveAdapter()
    calls = []

    class Provider(MockTranscriptionProvider):
        def __init__(self, identity):
            self.cache_identity = identity

        def transcribe(self, *args, **kwargs):
            from dataclasses import replace

            calls.append(self.cache_identity)
            return replace(super().transcribe(*args, **kwargs), model=self.cache_identity)

    service = AnalyzeTimeline(
        adapter=adapter,
        audio_exporter=MockAudioExporter(adapter),
        transcription_provider=Provider("A"),
        analyzer=HeuristicAnalyzer(zoom=config.zoom, text=config.text, configured_keywords=()),
        cache=JsonCache(tmp_path / "cache"),
        allow_manual_without_tracks=True,
    )
    first = service.execute(tmp_path, language="pt")
    service._transcription_provider = Provider("B")
    second = service.execute(tmp_path, language="pt")
    third = service.execute(tmp_path, language="pt")
    assert (first.transcript.model, second.transcript.model, third.transcript.model) == (
        "A",
        "B",
        "B",
    )
    assert first.audio_cache_key == second.audio_cache_key
    assert second.audio_origin == "cache"
    assert calls == ["A", "B"]
