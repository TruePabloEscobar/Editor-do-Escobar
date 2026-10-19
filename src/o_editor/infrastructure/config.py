"""Typed configuration loading."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from o_editor.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class AppSection:
    language: str
    theme: str
    log_level: str


@dataclass(frozen=True, slots=True)
class ResolveSection:
    target_major_version: int
    require_studio: bool
    text_track_name: str
    duplicate_suffix: str
    add_audit_markers: bool
    internal_host_enabled: bool
    external_bridge_enabled: bool
    api_paths: tuple[str, ...]
    library_paths: tuple[str, ...]
    documentation_paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FFmpegSection:
    ffmpeg_path: str | None
    ffprobe_path: str | None


@dataclass(frozen=True, slots=True)
class TranscriptionSection:
    provider: str
    model: str
    model_path: str | None
    device: str
    compute_type: str
    language: str | None
    word_timestamps: bool
    device_index: int = 0

    def __post_init__(self) -> None:
        if self.device not in {"auto", "cpu", "cuda"}:
            raise ValueError("Dispositivo de transcrição inválido.")
        if type(self.device_index) is not int or self.device_index < 0:
            raise ValueError("O índice da GPU deve ser um inteiro não negativo.")


@dataclass(frozen=True, slots=True)
class SuggestionSection:
    enabled: bool
    frequency: str
    minimum_gap_seconds: float
    maximum_per_minute: int


@dataclass(frozen=True, slots=True)
class ZoomSection(SuggestionSection):
    intensity: str
    max_zoom: float


@dataclass(frozen=True, slots=True)
class TextSection(SuggestionSection):
    minimum_words: int
    maximum_words: int
    minimum_duration_seconds: float
    maximum_duration_seconds: float


@dataclass(frozen=True, slots=True)
class SafetySection:
    dry_run_default: bool
    require_timeline_duplicate: bool
    skip_existing_fusion_comps: bool
    allow_gui_automation: bool
    allow_alpha_title_fallback: bool


@dataclass(frozen=True, slots=True)
class AnalysisSection:
    keywords: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AppConfig:
    schema_version: str
    app: AppSection
    resolve: ResolveSection
    ffmpeg: FFmpegSection
    transcription: TranscriptionSection
    zoom: ZoomSection
    text: TextSection
    safety: SafetySection
    analysis: AnalysisSection


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Não foi possível ler a configuração: {path}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError("A raiz da configuração deve ser um objeto JSON.")
    return value


def load_config(default_path: Path, user_path: Path | None = None) -> AppConfig:
    data = _read_json(default_path)
    configured = os.environ.get("O_EDITOR_CONFIG")
    override = user_path or (Path(configured) if configured else None)
    if override and override.exists():
        data = _deep_merge(data, _read_json(override))

    try:
        app = data["app"]
        resolve = data["resolve"]
        ffmpeg = data["ffmpeg"]
        transcription = data["transcription"]
        zoom = data["zoom"]
        text = data["text"]
        safety = data["safety"]
        analysis = data["analysis"]
        return AppConfig(
            schema_version=str(data["schema_version"]),
            app=AppSection(**app),
            resolve=ResolveSection(
                **{key: value for key, value in resolve.items() if not key.endswith("_paths")},
                api_paths=tuple(resolve.get("api_paths", [])),
                library_paths=tuple(resolve.get("library_paths", [])),
                documentation_paths=tuple(resolve.get("documentation_paths", [])),
            ),
            ffmpeg=FFmpegSection(**ffmpeg),
            transcription=TranscriptionSection(**transcription),
            zoom=ZoomSection(**zoom),
            text=TextSection(**text),
            safety=SafetySection(**safety),
            analysis=AnalysisSection(keywords=tuple(analysis.get("keywords", []))),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigurationError("A configuração possui campos ausentes ou inválidos.") from exc


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def settings_config_path() -> Path:
    """Keep the established storage directory and honor explicit overrides."""
    configured = os.environ.get("O_EDITOR_CONFIG")
    if configured:
        return Path(configured)
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise ConfigurationError("APPDATA indisponível; informe O_EDITOR_CONFIG.")
    return Path(appdata) / "O Editor" / "config.json"


def save_transcription_settings(section: TranscriptionSection, path: Path) -> None:
    """Atomically patch only transcription; malformed existing files stay untouched."""
    data = _read_json(path) if path.exists() else {}
    data = _deep_merge(data, {"transcription": asdict(section)})
    temporary: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".ede-config-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise ConfigurationError(f"Não foi possível salvar as configurações: {exc}") from exc
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
