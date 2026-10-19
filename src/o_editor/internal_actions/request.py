"""Validated persistence contract for actions created inside DaVinci Resolve."""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from o_editor.errors import ConfigurationError

ACTION_NAMES = frozenset(
    {
        "open",
        "menu_test",
        "diagnostic",
        "capability_probe",
        "apply_plan",
        "apply_rough_cut",
    }
)
REQUEST_STATUSES = frozenset({"SUCCESS", "BLOCKED", "FAILED", "CANCELLED", "UNSUPPORTED"})
_REQUEST_NAME = re.compile(
    r"^request-(?P<request_id>[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12})\.json$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class InternalActionRequest:
    schema_version: int
    request_id: str
    action: str
    created_at: str
    status: str
    project: str | None
    timeline: str | None
    result_file: str | None
    report_file: str | None
    log_file: str | None
    message: str
    details: dict[str, Any]
    script_version: str | None = None
    build_hash: str | None = None
    common_version: str | None = None
    common_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "action": self.action,
            "created_at": self.created_at,
            "status": self.status,
            "project": self.project,
            "timeline": self.timeline,
            "result_file": self.result_file,
            "report_file": self.report_file,
            "log_file": self.log_file,
            "message": self.message,
            "details": self.details,
            "script_version": self.script_version,
            "build_hash": self.build_hash,
            "common_version": self.common_version,
            "common_hash": self.common_hash,
        }


def app_data_root() -> Path:
    app_data = os.environ.get("APPDATA")
    if not app_data:
        raise ConfigurationError("APPDATA não está disponível para ações internas.")
    return Path(app_data) / "O Editor"


def create_internal_action_request(
    action: str,
    *,
    status: str,
    message: str,
    project: str | None = None,
    timeline: str | None = None,
    result_file: Path | None = None,
    report_file: Path | None = None,
    log_file: Path | None = None,
    details: dict[str, Any] | None = None,
    requests_directory: Path | None = None,
) -> Path:
    if action not in ACTION_NAMES:
        raise ConfigurationError(f"Ação interna desconhecida: {action}")
    if status not in REQUEST_STATUSES:
        raise ConfigurationError(f"Status de ação interna desconhecido: {status}")
    request_id = str(uuid.uuid4())
    request = InternalActionRequest(
        schema_version=1,
        request_id=request_id,
        action=action,
        created_at=datetime.now(UTC).isoformat(),
        status=status,
        project=project,
        timeline=timeline,
        result_file=str(result_file) if result_file else None,
        report_file=str(report_file) if report_file else None,
        log_file=str(log_file) if log_file else None,
        message=message,
        details=details or {},
    )
    directory = requests_directory or app_data_root() / "requests"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"request-{request_id}.json"
    _atomic_json_write(path, request.to_dict())
    return path


def load_internal_action_request(
    path: Path,
    *,
    maximum_age_seconds: int = 600,
    reject_processed: bool = False,
) -> InternalActionRequest:
    _validate_request_path(path)
    try:
        raw = path.read_text(encoding="utf-8")
        if raw.startswith("\ufeff"):
            raise ConfigurationError("A request interna contém UTF-8 BOM.")
        value = json.loads(raw)
    except UnicodeError as exc:
        raise ConfigurationError("A request interna não está em UTF-8 válido.") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Não foi possível ler a request interna: {path}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError("A request interna deve ser um objeto JSON.")
    request = _parse_request(value)
    expected_id = _request_id_from_name(path)
    if request.request_id.casefold() != expected_id.casefold():
        raise ConfigurationError("O request_id não corresponde ao nome do arquivo.")
    _validate_age(request.created_at, maximum_age_seconds)
    if reject_processed and processed_marker_path(path, request.request_id).exists():
        raise ConfigurationError("A request interna já foi processada.")
    return request


def mark_request_processed(
    path: Path,
    request: InternalActionRequest,
    *,
    outcome: str = "DISPLAYED",
) -> Path:
    marker = processed_marker_path(path, request.request_id)
    marker.parent.mkdir(parents=True, exist_ok=True)
    _atomic_json_write(
        marker,
        {
            "schema_version": 1,
            "request_id": request.request_id,
            "action": request.action,
            "processed_at": datetime.now(UTC).isoformat(),
            "outcome": outcome,
        },
    )
    return marker


def processed_marker_path(path: Path, request_id: str) -> Path:
    return path.parent / "processed" / f"{request_id}.json"


def _parse_request(value: dict[str, Any]) -> InternalActionRequest:
    if value.get("schema_version") != 1:
        raise ConfigurationError("A request interna possui schema_version incompatível.")
    request_id = value.get("request_id")
    try:
        canonical_request_id = str(uuid.UUID(str(request_id)))
    except (ValueError, AttributeError) as exc:
        raise ConfigurationError("A request interna possui request_id inválido.") from exc
    action = value.get("action")
    if action not in ACTION_NAMES:
        raise ConfigurationError("A request interna possui action inválida.")
    status = value.get("status")
    if status not in REQUEST_STATUSES:
        raise ConfigurationError("A request interna possui status inválido.")
    message = value.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ConfigurationError("A request interna não contém uma mensagem válida.")
    details = value.get("details")
    if not isinstance(details, dict):
        raise ConfigurationError("A request interna não contém details válido.")
    created_at = value.get("created_at")
    if not isinstance(created_at, str):
        raise ConfigurationError("A request interna não contém created_at válido.")
    return InternalActionRequest(
        schema_version=1,
        request_id=canonical_request_id,
        action=str(action),
        created_at=created_at,
        status=str(status),
        project=_optional_string(value.get("project")),
        timeline=_optional_string(value.get("timeline")),
        result_file=_optional_string(value.get("result_file")),
        report_file=_optional_string(value.get("report_file")),
        log_file=_optional_string(value.get("log_file")),
        message=message.strip(),
        details=details,
        script_version=_optional_string(value.get("script_version")),
        build_hash=_optional_string(value.get("build_hash")),
        common_version=_optional_string(value.get("common_version")),
        common_hash=_optional_string(value.get("common_hash")),
    )


def _validate_age(created_at: str, maximum_age_seconds: int) -> None:
    try:
        timestamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ConfigurationError("A request interna possui created_at inválido.") from exc
    if timestamp.tzinfo is None:
        raise ConfigurationError("A request interna possui created_at sem fuso horário.")
    age = (datetime.now(UTC) - timestamp.astimezone(UTC)).total_seconds()
    if age > maximum_age_seconds:
        raise ConfigurationError("A request interna expirou.")
    if age < -60:
        raise ConfigurationError("A request interna possui timestamp no futuro.")


def _validate_request_path(path: Path) -> None:
    if path.parent.name.casefold() != "requests":
        raise ConfigurationError("O caminho da request interna não é permitido.")
    _request_id_from_name(path)


def _request_id_from_name(path: Path) -> str:
    match = _REQUEST_NAME.fullmatch(path.name)
    if not match:
        raise ConfigurationError("O nome da request interna não é permitido.")
    return match.group("request_id")


def _optional_string(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise ConfigurationError(f"Não foi possível gravar a request interna: {path}") from exc
