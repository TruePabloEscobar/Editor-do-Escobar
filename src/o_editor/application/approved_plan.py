"""Persistence contract consumed by the internal Resolve plan applicator."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from o_editor import __version__
from o_editor.domain.enums import SuggestionKind
from o_editor.domain.models import Suggestion, TimelineSnapshot
from o_editor.errors import ConfigurationError
from o_editor.infrastructure.resolve.fusion_title_backend import (
    REQUIRED_TITLE_CAPABILITIES,
)
from o_editor.infrastructure.resolve.fusion_zoom_backend import (
    REQUIRED_ZOOM_CAPABILITIES,
)


def save_approved_plan(
    *,
    snapshot: TimelineSnapshot,
    suggestions: tuple[Suggestion, ...],
    source_context: dict[str, Any],
    app_data: Path | None = None,
) -> tuple[Path, Path]:
    approved = tuple(item for item in suggestions if item.approved)
    generated = datetime.now(UTC)
    required = sorted(
        {
            capability
            for suggestion in approved
            for capability in (
                REQUIRED_ZOOM_CAPABILITIES
                if suggestion.kind is SuggestionKind.ZOOM
                else REQUIRED_TITLE_CAPABILITIES
            )
        }
    )
    payload = {
        "schema_version": 1,
        "o_editor_version": __version__,
        "created_at": generated.isoformat(),
        "status": "APPROVED_NOT_APPLIED",
        "project": snapshot.project_name,
        "timeline": snapshot.timeline_name,
        "timeline_fingerprint": snapshot.fingerprint,
        "fps": snapshot.fps,
        "start_frame": snapshot.start_frame,
        "start_timecode": source_context.get("start_timecode"),
        "source_context": _safe_context(source_context),
        "approved_suggestions": [item.to_dict() for item in approved],
        "zooms": [item.to_dict() for item in approved if item.kind is SuggestionKind.ZOOM],
        "texts": [item.to_dict() for item in approved if item.kind is SuggestionKind.TEXT],
        "required_capabilities": required,
        "expected_backend": "internal_resolve_lua",
    }
    root = app_data or _default_app_data()
    plan_directory = root / "O Editor" / "plans"
    plan_directory.mkdir(parents=True, exist_ok=True)
    latest = plan_directory / "latest-approved-plan.json"
    versioned = plan_directory / (
        f"{_safe_name(snapshot.project_name)}_{_safe_name(snapshot.timeline_name)}_"
        f"{generated.strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    _atomic_write(latest, content)
    _atomic_write(versioned, content)
    return latest, versioned


def _default_app_data() -> Path:
    value = os.environ.get("APPDATA")
    if not value:
        raise ConfigurationError("APPDATA não está disponível para salvar o plano aprovado.")
    return Path(value)


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return normalized.strip("._") or "timeline"


def _safe_context(context: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "context_kind",
        "timestamp",
        "resolve_version",
        "product_name",
        "project_name",
        "timeline_name",
        "timeline_id",
        "fps",
        "start_frame",
        "end_frame",
        "duration_frames",
        "start_timecode",
        "track_counts",
        "integration_mode",
        "selected_voice_tracks",
        "audio_backend",
        "audio_cache_key",
        "audio_file",
        "audio_duration_seconds",
        "audio_sample_rate",
        "audio_origin",
    }
    return {key: value for key, value in context.items() if key in allowed}


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise ConfigurationError(f"Não foi possível salvar o plano aprovado: {path}") from exc
