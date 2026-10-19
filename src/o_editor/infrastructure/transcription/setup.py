"""Explicit local faster-whisper download, configuration, and smoke test."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import wave
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from o_editor.infrastructure.transcription.faster_whisper import FasterWhisperProvider

MODEL_REPOSITORIES = {
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    "small": "Systran/faster-whisper-small",
}


def _default_app_data() -> Path:
    value = os.environ.get("APPDATA")
    if not value:
        raise RuntimeError("APPDATA não está definido.")
    return Path(value) / "O Editor"


def _default_local_app_data() -> Path:
    value = os.environ.get("LOCALAPPDATA")
    if not value:
        raise RuntimeError("LOCALAPPDATA não está definido.")
    return Path(value) / "O Editor"


def _read_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"O JSON deve conter um objeto: {path}")
    return value


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _configure(config_path: Path, *, model: str, model_path: Path) -> None:
    config = _read_object(config_path)
    transcription = config.setdefault("transcription", {})
    if not isinstance(transcription, dict):
        raise RuntimeError("transcription deve ser um objeto na configuração.")
    transcription.update(
        {
            "provider": "faster-whisper",
            "model": model,
            "model_path": str(model_path.resolve()),
            "device": "auto",
            "compute_type": "auto",
            "language": "pt",
            "word_timestamps": True,
        }
    )
    _write_json_atomic(config_path, config)


def _write_silence(path: Path) -> None:
    sample_rate = 16_000
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(b"\0\0" * sample_rate)


def _cuda_device_count() -> int:
    import ctranslate2

    return int(ctranslate2.get_cuda_device_count())


def _test_model(model_path: Path, model: str) -> dict[str, Any]:
    provider = FasterWhisperProvider(
        model_path=model_path,
        configured_model_name=model,
        device="auto",
        compute_type="auto",
    )
    with tempfile.TemporaryDirectory(prefix="o-editor-whisper-") as directory:
        audio_path = Path(directory) / "silence-1s.wav"
        _write_silence(audio_path)
        transcript = provider.transcribe(
            audio_path,
            fps=30.0,
            timeline_start_frame=0,
            language="pt",
        )
    return {
        "status": "PASSED",
        "audio": "PCM mono, 16000 Hz, 1 segundo de silêncio",
        "device_used": provider.last_device,
        "fallback_reason": provider.last_fallback_reason,
        "language": transcript.language,
        "segments": len(transcript.segments),
        "words": sum(len(segment.words) for segment in transcript.segments),
        "word_timestamps": True,
        "transcript_content_logged": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preparar faster-whisper local explicitamente")
    parser.add_argument("--download", action="store_true", help="autorizar o download do modelo")
    parser.add_argument("--test", action="store_true", help="executar inferência local curta")
    parser.add_argument("--model", choices=tuple(MODEL_REPOSITORIES), default="large-v3-turbo")
    parser.add_argument("--model-path", type=Path)
    parser.add_argument("--config-path", type=Path)
    parser.add_argument("--report-path", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    started_at = datetime.now(UTC)
    model_path = args.model_path or (_default_local_app_data() / "models" / args.model)
    config_path = args.config_path or (_default_app_data() / "config.json")
    report_path = args.report_path or (_default_app_data() / "reports" / "whisper-setup.json")
    report: dict[str, Any] = {
        "schema_version": 1,
        "started_at": started_at.isoformat(),
        "model": args.model,
        "repository": MODEL_REPOSITORIES[args.model],
        "model_path": str(model_path),
        "config_path": str(config_path),
        "download_requested": args.download,
        "test_requested": args.test,
    }
    try:
        import faster_whisper
        import huggingface_hub

        report["faster_whisper_version"] = getattr(faster_whisper, "__version__", "unknown")
        report["huggingface_hub_version"] = getattr(huggingface_hub, "__version__", "unknown")
        report["cuda_device_count"] = _cuda_device_count()
        if args.download:
            from huggingface_hub import snapshot_download

            print(
                f"Baixando {MODEL_REPOSITORIES[args.model]} para {model_path}",
                flush=True,
            )
            snapshot_download(
                repo_id=MODEL_REPOSITORIES[args.model],
                local_dir=model_path,
            )
        if not model_path.is_dir() or not (model_path / "model.bin").is_file():
            raise RuntimeError(
                "Modelo local ausente ou incompleto. Execute novamente com --download."
            )
        _configure(config_path, model=args.model, model_path=model_path)
        report["model_size_bytes"] = _directory_size(model_path)
        report["configuration_status"] = "PASSED"
        if args.test:
            report["inference_test"] = _test_model(model_path, args.model)
        else:
            report["inference_test"] = {"status": "SKIPPED"}
        report["status"] = "PASSED"
        exit_code = 0
    except (ImportError, OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        report["status"] = "FAILED"
        report["error"] = f"{type(exc).__name__}: {exc}"
        print(f"Falha ao preparar Whisper: {exc}", file=sys.stderr)
        exit_code = 2
    report["finished_at"] = datetime.now(UTC).isoformat()
    _write_json_atomic(report_path, report)
    print(f"Relatório Whisper: {report_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
