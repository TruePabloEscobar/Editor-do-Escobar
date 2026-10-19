"""Local model identity, atomic configuration and selected CUDA ordinals."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from o_editor.errors import ConfigurationError
from o_editor.infrastructure.config import (
    load_config,
    save_transcription_settings,
    settings_config_path,
)
from o_editor.infrastructure.transcription.faster_whisper import (
    FasterWhisperProvider,
    TranscriptionError,
)
from o_editor.infrastructure.transcription.local_model import local_model_identity
from o_editor.infrastructure.transcription.track import (
    FasterWhisperTrackTranscriber,
    TrackTranscriptionError,
)


@pytest.mark.parametrize("kind", ["track", "provider"])
def test_selected_cuda_ordinal_reaches_model_and_explicit_failure_never_falls_back(
    monkeypatch, tmp_path, kind
):
    calls = []

    class Model:
        def __init__(self, path, **kwargs):
            calls.append(kwargs)
            assert kwargs["device_index"] == 2
            assert kwargs["local_files_only"] is True
            raise RuntimeError("Unavailable requested CUDA adapter")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model))
    options = dict(
        model_path=tmp_path, configured_model_name="local", device="cuda", device_index=2
    )
    if kind == "track":
        engine = FasterWhisperTrackTranscriber(**options)
        with pytest.raises(TrackTranscriptionError):
            engine._load()
    else:
        provider = FasterWhisperProvider(**options)
        with pytest.raises(TranscriptionError):
            provider.transcribe(
                tmp_path / "audio.wav", fps=24, timeline_start_frame=0, language="pt"
            )
    assert len(calls) == 1 and calls[0]["device"] == "cuda"


def test_model_replacement_invalidates_identity_without_reading_weights(tmp_path):
    path = tmp_path / "model.bin"
    path.write_bytes(b"first")
    first = local_model_identity(tmp_path, "same-name")
    assert local_model_identity(tmp_path, "same-name") == first
    path.write_bytes(b"second-revision")
    assert local_model_identity(tmp_path, "same-name") != first
    other = tmp_path / "other"
    other.mkdir()
    assert local_model_identity(other, "same-name") != first


def test_failed_atomic_save_and_invalid_existing_json_preserve_original(monkeypatch, tmp_path):
    config = load_config(Path("config/defaults.json"))
    target = tmp_path / "config.json"
    original = b'{"custom": 42}'
    target.write_bytes(original)

    def fail_replace(*args):
        raise PermissionError("test locked file")

    monkeypatch.setattr("o_editor.infrastructure.config.os.replace", fail_replace)
    with pytest.raises(ConfigurationError):
        save_transcription_settings(config.transcription, target)
    assert target.read_bytes() == original
    assert list(tmp_path.glob("*.tmp")) == []
    target.write_bytes(b"invalid-json")
    with pytest.raises(ConfigurationError):
        save_transcription_settings(config.transcription, target)
    assert target.read_bytes() == b"invalid-json"


def test_override_location_and_legacy_config_default_gpu_index(monkeypatch, tmp_path):
    monkeypatch.setenv("O_EDITOR_CONFIG", str(tmp_path / "chosen.json"))
    assert settings_config_path() == tmp_path / "chosen.json"
    config = load_config(Path("config/defaults.json"))
    assert config.transcription.device_index == 0
    with pytest.raises(ValueError):
        replace(config.transcription, device_index=-1)
    with pytest.raises(ValueError):
        replace(config.transcription, device_index=True)
