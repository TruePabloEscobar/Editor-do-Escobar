from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from o_editor.infrastructure.transcription.faster_whisper import FasterWhisperProvider


def test_automatic_cuda_failure_falls_back_to_cpu(
    monkeypatch,
    tmp_path: Path,
) -> None:
    attempts: list[tuple[str, str]] = []

    class FakeModel:
        def __init__(
            self,
            model_path: str,
            *,
            device: str,
            device_index: int,
            compute_type: str,
            local_files_only: bool,
        ) -> None:
            assert Path(model_path) == tmp_path
            assert local_files_only is True
            assert device_index == 0
            attempts.append((device, compute_type))
            if device == "cuda":
                raise RuntimeError("CUDA runtime unavailable")

        def transcribe(
            self,
            audio_path: str,
            *,
            language: str | None,
            word_timestamps: bool,
        ) -> tuple[tuple[object, ...], object]:
            assert Path(audio_path).name == "sample.wav"
            assert language == "pt"
            assert word_timestamps is True
            return (), SimpleNamespace(language="pt")

    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=FakeModel),
    )
    monkeypatch.setitem(
        sys.modules,
        "ctranslate2",
        SimpleNamespace(get_cuda_device_count=lambda: 1),
    )
    provider = FasterWhisperProvider(
        model_path=tmp_path,
        configured_model_name="test",
    )

    transcript = provider.transcribe(
        tmp_path / "sample.wav",
        fps=30.0,
        timeline_start_frame=0,
        language="pt",
    )

    assert transcript.language == "pt"
    assert provider.last_device == "cpu"
    assert provider.last_fallback_reason is not None
    assert attempts == [("cuda", "auto"), ("cpu", "int8")]
