"""Per-project and timeline persistence for confirmed voice-track selection."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from o_editor.domain.voice_tracks import (
    AudioTrackSnapshot,
    SelectedVoiceTrack,
    validate_voice_selection,
)
from o_editor.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class RestoredVoiceTrackSettings:
    selected_voice_tracks: tuple[SelectedVoiceTrack, ...]
    manual_wav: Path | None
    warnings: tuple[str, ...]


class VoiceTrackSettingsStore:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root or _default_root()

    def path_for(self, project: str, timeline: str) -> Path:
        identity = f"{project.strip()}\x1f{timeline.strip()}".encode()
        context_hash = hashlib.sha256(identity).hexdigest()[:24]
        return self._root / context_hash / "timeline-settings.json"

    def save(
        self,
        *,
        project: str,
        timeline: str,
        timeline_fingerprint: str,
        selected_voice_tracks: tuple[SelectedVoiceTrack, ...],
        manual_wav: Path | None,
    ) -> Path:
        path = self.path_for(project, timeline)
        payload = {
            "schema_version": 1,
            "project": project,
            "timeline": timeline,
            "timeline_fingerprint": timeline_fingerprint,
            "selected_voice_tracks": [item.to_dict() for item in selected_voice_tracks],
            "manual_wav": str(manual_wav) if manual_wav else None,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        _write_json_atomic(path, payload)
        return path

    def load(
        self,
        *,
        project: str,
        timeline: str,
        timeline_fingerprint: str,
        audio_tracks: tuple[AudioTrackSnapshot, ...],
    ) -> RestoredVoiceTrackSettings:
        path = self.path_for(project, timeline)
        if not path.exists():
            return RestoredVoiceTrackSettings((), None, ())
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ConfigurationError("A seleção salva de faixas de voz está inválida.") from exc
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise ConfigurationError("A seleção salva possui schema incompatível.")
        if value.get("project") != project or value.get("timeline") != timeline:
            raise ConfigurationError("A seleção salva pertence a outro projeto ou timeline.")
        raw_selected = value.get("selected_voice_tracks", [])
        if not isinstance(raw_selected, list):
            raise ConfigurationError("A seleção salva de faixas é inválida.")
        try:
            selected = tuple(
                SelectedVoiceTrack.from_dict(item)
                for item in raw_selected
                if isinstance(item, dict)
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError("A seleção salva contém uma faixa inválida.") from exc
        valid, selection_warnings = validate_voice_selection(audio_tracks, selected)
        warnings = list(selection_warnings)
        if value.get("timeline_fingerprint") != timeline_fingerprint:
            warnings.append("A timeline mudou desde a última seleção; confirme as faixas de voz.")
        manual_value = value.get("manual_wav")
        manual_wav = Path(manual_value) if isinstance(manual_value, str) else None
        if manual_wav is not None and not manual_wav.is_file():
            warnings.append("O WAV manual salvo não está mais disponível.")
            manual_wav = None
        return RestoredVoiceTrackSettings(valid, manual_wav, tuple(warnings))


def _default_root() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise ConfigurationError("APPDATA não está disponível para salvar as faixas de voz.")
    return Path(appdata) / "O Editor" / "projects"


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix="voice-settings-", suffix=".tmp", dir=path.parent
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ConfigurationError("Não foi possível salvar a seleção de faixas de voz.") from exc
