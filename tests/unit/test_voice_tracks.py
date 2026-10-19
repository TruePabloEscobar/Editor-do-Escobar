from __future__ import annotations

import json
import wave
from dataclasses import replace
from pathlib import Path

import pytest

from o_editor.application.analyze_timeline import AnalyzeTimeline
from o_editor.domain.enums import ChannelMode
from o_editor.domain.voice_tracks import (
    AudioTrackSnapshot,
    SelectedVoiceTrack,
    score_voice_track,
    suggest_voice_tracks,
    validate_voice_selection,
    voice_audio_cache_key,
)
from o_editor.errors import CancelledError, OEditorError
from o_editor.infrastructure.analysis.heuristic import HeuristicAnalyzer
from o_editor.infrastructure.cache import JsonCache
from o_editor.infrastructure.config import load_config
from o_editor.infrastructure.resolve.audio_exporter import (
    AudioExportError,
    InternalVoiceAudioExporter,
    MockAudioExporter,
)
from o_editor.infrastructure.resolve.mock_adapter import MockResolveAdapter
from o_editor.infrastructure.transcription.base import CancellationToken
from o_editor.infrastructure.transcription.mock import MockTranscriptionProvider
from o_editor.infrastructure.voice_audio_cache import VoiceAudioCache
from o_editor.infrastructure.voice_track_settings import VoiceTrackSettingsStore
from o_editor.internal_actions.voice_audio import (
    VoiceAudioExportRequest,
    VoiceAudioExportResponse,
    save_voice_audio_request,
)


def _tracks() -> tuple[AudioTrackSnapshot, ...]:
    return (
        AudioTrackSnapshot(1, "A1", "Áudio da câmera", audio_type="stereo", item_count=1),
        AudioTrackSnapshot(2, "A2", "Lapela Pablo", audio_type="mono", item_count=2),
        AudioTrackSnapshot(3, "A3", "Lapela convidado", audio_type="mono", item_count=2),
        AudioTrackSnapshot(4, "A4", "Música", audio_type="stereo", item_count=1),
        AudioTrackSnapshot(5, "A5", "Efeitos", audio_type="stereo", item_count=0),
    )


def _selected(index: int, mode: ChannelMode = ChannelMode.BOTH) -> SelectedVoiceTrack:
    track = _tracks()[index - 1]
    return SelectedVoiceTrack(track.index, track.name, mode)


def _cache_key(
    selected: tuple[SelectedVoiceTrack, ...],
    *,
    fingerprint: str = "fingerprint",
    backend: str = "mock",
) -> str:
    return voice_audio_cache_key(
        project="Projeto",
        timeline="Timeline",
        timeline_fingerprint=fingerprint,
        selected_voice_tracks=selected,
        sample_rate=48_000,
        export_backend=backend,
        app_version="0.1.0",
    )


def test_audio_track_contract_and_display() -> None:
    track = _tracks()[1]
    assert track.display_name == "A2 — Lapela Pablo"
    assert track.to_dict()["audio_type"] == "mono"
    assert AudioTrackSnapshot.from_dict(track.to_dict()) == track
    with pytest.raises(ValueError, match="label"):
        replace(track, label="A9")


def test_voice_name_suggestions_include_lapelas_and_exclude_music() -> None:
    assert suggest_voice_tracks(_tracks()) == (2, 3)
    assert score_voice_track(_tracks()[1]) > 0
    assert score_voice_track(_tracks()[3]) < 0


@pytest.mark.parametrize("indices", [(2,), (2, 3), (1, 2, 3)])
def test_one_or_multiple_voice_tracks_are_validated(indices: tuple[int, ...]) -> None:
    selected = tuple(_selected(index) for index in indices)
    valid, warnings = validate_voice_selection(_tracks(), selected)
    assert tuple(item.index for item in valid) == indices
    assert not warnings


def test_removed_and_renamed_tracks_generate_warnings() -> None:
    selected = (
        SelectedVoiceTrack(2, "Nome antigo", ChannelMode.MONO),
        SelectedVoiceTrack(9, "Ausente", ChannelMode.BOTH),
    )
    valid, warnings = validate_voice_selection(_tracks(), selected)
    assert valid == (SelectedVoiceTrack(2, "Lapela Pablo", ChannelMode.MONO),)
    assert any("mudou de nome" in warning for warning in warnings)
    assert any("não existe mais" in warning for warning in warnings)


@pytest.mark.parametrize(
    ("audio_type", "requested", "expected"),
    [
        ("stereo", ChannelMode.LEFT, ChannelMode.LEFT),
        ("stereo", ChannelMode.RIGHT, ChannelMode.RIGHT),
        ("stereo", ChannelMode.BOTH, ChannelMode.BOTH),
        ("mono", ChannelMode.BOTH, ChannelMode.MONO),
        ("unknown", ChannelMode.LEFT, ChannelMode.BOTH),
    ],
)
def test_channel_mode_is_validated(
    audio_type: str,
    requested: ChannelMode,
    expected: ChannelMode,
) -> None:
    track = AudioTrackSnapshot(1, "A1", "Voz", audio_type=audio_type, item_count=1)
    valid, _warnings = validate_voice_selection(
        (track,),
        (SelectedVoiceTrack(1, "Voz", requested),),
    )
    assert valid[0].channel_mode is expected


def test_selection_settings_round_trip_and_timeline_warning(tmp_path: Path) -> None:
    store = VoiceTrackSettingsStore(tmp_path / "projects")
    wav = tmp_path / "voice.wav"
    _write_wav(wav)
    path = store.save(
        project="Projeto",
        timeline="Timeline",
        timeline_fingerprint="fp-1",
        selected_voice_tracks=(_selected(2, ChannelMode.MONO), _selected(3, ChannelMode.MONO)),
        manual_wav=wav,
    )
    restored = store.load(
        project="Projeto",
        timeline="Timeline",
        timeline_fingerprint="fp-2",
        audio_tracks=_tracks(),
    )
    assert path.name == "timeline-settings.json"
    assert tuple(item.index for item in restored.selected_voice_tracks) == (2, 3)
    assert restored.manual_wav == wav
    assert any("timeline mudou" in warning for warning in restored.warnings)


def test_missing_manual_wav_is_not_restored(tmp_path: Path) -> None:
    store = VoiceTrackSettingsStore(tmp_path)
    store.save(
        project="Projeto",
        timeline="Timeline",
        timeline_fingerprint="fp",
        selected_voice_tracks=(_selected(2),),
        manual_wav=tmp_path / "missing.wav",
    )
    restored = store.load(
        project="Projeto",
        timeline="Timeline",
        timeline_fingerprint="fp",
        audio_tracks=_tracks(),
    )
    assert restored.manual_wav is None
    assert any("não está mais disponível" in warning for warning in restored.warnings)


def test_cache_key_changes_with_selection_channel_timeline_and_backend() -> None:
    base = _cache_key((_selected(2),))
    assert base != _cache_key((_selected(2), _selected(3)))
    assert base != _cache_key((_selected(2, ChannelMode.LEFT),))
    assert base != _cache_key((_selected(2),), fingerprint="changed")
    assert base != _cache_key((_selected(2),), backend="manual_wav")


def test_voice_audio_cache_hit_and_miss(tmp_path: Path) -> None:
    cache = VoiceAudioCache(tmp_path)
    key = _cache_key((_selected(2),))
    metadata = {"selection": [2]}
    assert not cache.is_hit(key, metadata)
    audio = cache.audio_path(key)
    _write_wav(audio)
    cache.save_metadata(key, metadata)
    assert cache.is_hit(key, metadata)
    assert not cache.is_hit(key, {"selection": [3]})


def test_voice_audio_request_and_response_schema(tmp_path: Path) -> None:
    request = VoiceAudioExportRequest.create(
        project="Projeto",
        timeline="Timeline",
        timeline_fingerprint="fp",
        selected_tracks=(_selected(2),),
        output_path=tmp_path / "voice.wav",
    )
    path = save_voice_audio_request(request, tmp_path / "requests")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["action"] == "export_voice_audio"
    assert payload["selected_tracks"][0]["index"] == 2
    assert payload["audio_settings"]["sample_rate"] == 48_000
    response = VoiceAudioExportResponse(
        status="UNSUPPORTED",
        output_path=None,
        duration_seconds=None,
        sample_rate=None,
        channels=None,
        backend="internal_resolve_lua_unverified",
        restoration_verified=False,
        message="Capability ausente.",
    )
    assert response.to_dict()["status"] == "UNSUPPORTED"


def test_internal_exporter_writes_preflight_but_never_mutates(tmp_path: Path) -> None:
    adapter = MockResolveAdapter()
    exporter = InternalVoiceAudioExporter(tmp_path / "requests")
    with pytest.raises(AudioExportError, match="UNVERIFIED"):
        exporter.export(
            adapter.original_snapshot,
            tmp_path / "voice.wav",
            selected_voice_tracks=(_selected(2),),
        )
    assert exporter.last_request_path is not None
    assert exporter.last_request_path.is_file()
    assert not (tmp_path / "voice.wav").exists()


def test_internal_exporter_honors_cancellation(tmp_path: Path) -> None:
    token = CancellationToken()
    token.cancel()
    with pytest.raises(CancelledError):
        InternalVoiceAudioExporter(tmp_path).export(
            MockResolveAdapter().original_snapshot,
            tmp_path / "voice.wav",
            selected_voice_tracks=(_selected(2),),
            cancellation=token,
        )


def test_analysis_requires_confirmed_voice_source(tmp_path: Path) -> None:
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
    )
    with pytest.raises(OEditorError, match="Selecione pelo menos"):
        service.execute(tmp_path, language="pt")


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(48_000)
        output.writeframes(b"\0\0" * 48_000)
