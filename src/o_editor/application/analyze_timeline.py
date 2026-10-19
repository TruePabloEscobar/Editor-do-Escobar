"""Analyze timeline use case with voice-track-aware cache and cancellation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from o_editor import __version__
from o_editor.domain.enums import ChannelMode
from o_editor.domain.models import Suggestion, TimelineSnapshot, Transcript, stable_id
from o_editor.domain.voice_tracks import (
    SelectedVoiceTrack,
    suggest_voice_tracks,
    validate_voice_selection,
    voice_audio_cache_key,
)
from o_editor.errors import OEditorError
from o_editor.infrastructure.analysis.heuristic import HeuristicAnalyzer
from o_editor.infrastructure.cache import JsonCache
from o_editor.infrastructure.config import AppConfig
from o_editor.infrastructure.resolve.adapter import ResolveAdapter
from o_editor.infrastructure.resolve.audio_exporter import AudioExporter, MockAudioExporter
from o_editor.infrastructure.resolve.mock_adapter import MockResolveAdapter
from o_editor.infrastructure.transcription.base import CancellationToken, TranscriptionProvider
from o_editor.infrastructure.transcription.mock import MockTranscriptionProvider
from o_editor.infrastructure.voice_audio_cache import VoiceAudioCache

AnalysisProgress = Callable[[float, str], None]


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    analysis_id: str
    snapshot: TimelineSnapshot
    transcript: Transcript
    suggestions: tuple[Suggestion, ...]
    audio_path: Path
    selected_voice_tracks: tuple[SelectedVoiceTrack, ...]
    audio_cache_key: str
    audio_backend: str
    audio_origin: str


class AnalyzeTimeline:
    def __init__(
        self,
        *,
        adapter: ResolveAdapter,
        audio_exporter: AudioExporter,
        transcription_provider: TranscriptionProvider,
        analyzer: HeuristicAnalyzer,
        cache: JsonCache,
        selected_voice_tracks: tuple[SelectedVoiceTrack, ...] = (),
        audio_backend: str = "resolve",
        allow_manual_without_tracks: bool = False,
        sample_rate: int = 48_000,
    ) -> None:
        self._adapter = adapter
        self._audio_exporter = audio_exporter
        self._transcription_provider = transcription_provider
        self._analyzer = analyzer
        self._cache = cache
        self._selected_voice_tracks = selected_voice_tracks
        self._audio_backend = audio_backend
        self._allow_manual_without_tracks = allow_manual_without_tracks
        self._sample_rate = sample_rate

    def execute(
        self,
        runtime_dir: Path,
        *,
        language: str | None,
        progress: AnalysisProgress | None = None,
        cancellation: CancellationToken | None = None,
    ) -> AnalysisResult:
        self._adapter.connect()
        snapshot = self._adapter.get_active_snapshot()
        selected = self._selection_for(snapshot)
        if not selected and not self._allow_manual_without_tracks:
            raise OEditorError("Selecione pelo menos uma faixa de voz ou forneça um WAV manual.")
        cache_key = voice_audio_cache_key(
            project=snapshot.project_name,
            timeline=snapshot.timeline_name,
            timeline_fingerprint=snapshot.fingerprint,
            selected_voice_tracks=selected,
            sample_rate=self._sample_rate,
            export_backend=self._audio_backend,
            app_version=__version__,
        )
        analysis_id = stable_id("analysis", (snapshot.fingerprint, cache_key))
        voice_cache = VoiceAudioCache(self._cache.root)
        audio_path = voice_cache.audio_path(cache_key)
        metadata = {
            "schema_version": 1,
            "project": snapshot.project_name,
            "timeline": snapshot.timeline_name,
            "timeline_fingerprint": snapshot.fingerprint,
            "selected_voice_tracks": [item.to_dict() for item in selected],
            "sample_rate": self._sample_rate,
            "export_backend": self._audio_backend,
            "app_version": __version__,
        }
        cache_hit = voice_cache.is_hit(cache_key, metadata)
        if cache_hit:
            if progress:
                progress(0.25, "Áudio de voz reutilizado do cache")
        else:
            self._audio_exporter.export(
                snapshot,
                audio_path,
                progress=_scale_progress(progress, 0.0, 0.25),
                cancellation=cancellation,
                selected_voice_tracks=selected,
            )
            voice_cache.save_metadata(cache_key, metadata)
        if progress:
            progress(0.25, "TRANSCRIBING")
        transcript_key = JsonCache.make_key(
            cache_key,
            self._transcription_provider.name,
            str(getattr(self._transcription_provider, "cache_identity", "default")),
            language or "auto",
        )
        cached = self._cache.load("transcripts", transcript_key)
        if cached:
            transcript = Transcript.from_dict(cached)
            if progress:
                progress(0.7, "Transcrição recuperada do cache")
        else:
            transcript = self._transcription_provider.transcribe(
                audio_path,
                fps=snapshot.fps,
                timeline_start_frame=snapshot.start_frame,
                language=language,
                progress=_scale_progress(progress, 0.25, 0.7),
                cancellation=cancellation,
            )
            self._cache.save("transcripts", transcript_key, transcript.to_dict())
        if progress:
            progress(0.8, "GENERATING_SUGGESTIONS")
        suggestions = self._analyzer.analyze(snapshot, transcript)
        if progress:
            progress(1.0, "READY_FOR_REVIEW")
        return AnalysisResult(
            analysis_id=analysis_id,
            snapshot=snapshot,
            transcript=transcript,
            suggestions=suggestions,
            audio_path=audio_path,
            selected_voice_tracks=selected,
            audio_cache_key=cache_key,
            audio_backend=self._audio_backend,
            audio_origin="cache" if cache_hit else self._audio_backend,
        )

    def _selection_for(self, snapshot: TimelineSnapshot) -> tuple[SelectedVoiceTrack, ...]:
        selected = self._selected_voice_tracks
        valid, warnings = validate_voice_selection(snapshot.audio_tracks, selected)
        if warnings and not valid and selected:
            raise OEditorError(" ".join(warnings))
        return valid


def _scale_progress(
    callback: AnalysisProgress | None,
    start: float,
    end: float,
) -> AnalysisProgress | None:
    if callback is None:
        return None

    def scaled(value: float, message: str) -> None:
        callback(start + max(0.0, min(1.0, value)) * (end - start), message)

    return scaled


def analyze_with_mock(config: AppConfig, runtime_dir: Path) -> AnalysisResult:
    adapter = MockResolveAdapter()
    suggested = set(suggest_voice_tracks(adapter.original_snapshot.audio_tracks))
    selected = tuple(
        SelectedVoiceTrack(
            track.index,
            track.name,
            ChannelMode.MONO if track.audio_type == "mono" else ChannelMode.BOTH,
        )
        for track in adapter.original_snapshot.audio_tracks
        if track.index in suggested
    )
    service = AnalyzeTimeline(
        adapter=adapter,
        audio_exporter=MockAudioExporter(adapter),
        transcription_provider=MockTranscriptionProvider(),
        analyzer=HeuristicAnalyzer(
            zoom=config.zoom,
            text=config.text,
            configured_keywords=config.analysis.keywords,
        ),
        cache=JsonCache(runtime_dir / "cache"),
        selected_voice_tracks=selected,
        audio_backend="mock_voice_tracks",
    )
    return service.execute(runtime_dir, language=config.transcription.language)
