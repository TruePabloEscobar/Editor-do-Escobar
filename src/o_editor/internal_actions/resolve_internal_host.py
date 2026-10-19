"""File protocol for the persistent Resolve Workflow Integration host."""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from o_editor.errors import ConfigurationError

HostAction = Literal["ping", "export_voice_audio", "cancel"]
HostStatus = Literal[
    "PENDING",
    "CLAIMED",
    "RUNNING",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
    "UNSUPPORTED",
]


@dataclass(frozen=True, slots=True)
class ResolveInternalHostPaths:
    root: Path

    @classmethod
    def default(cls) -> ResolveInternalHostPaths:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise ConfigurationError("APPDATA não está disponível para o host interno.")
        return cls(Path(appdata) / "O Editor" / "resolve-internal-host")

    @property
    def requests(self) -> Path:
        return self.root / "requests"

    @property
    def jobs(self) -> Path:
        return self.root / "jobs"

    @property
    def responses(self) -> Path:
        return self.root / "responses"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    def ensure(self) -> None:
        for directory in (self.requests, self.jobs, self.responses, self.logs):
            directory.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True, slots=True)
class ResolveInternalHostRequest:
    request_id: str
    action: HostAction
    created_at: str
    payload: dict[str, Any] = field(default_factory=dict)
    schema_version: int = 1

    @classmethod
    def create(
        cls,
        action: HostAction,
        *,
        payload: dict[str, Any] | None = None,
    ) -> ResolveInternalHostRequest:
        return cls(
            request_id=str(uuid.uuid4()),
            action=action,
            created_at=datetime.now(UTC).isoformat(),
            payload=dict(payload or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "action": self.action,
            "created_at": self.created_at,
            "status": "PENDING",
            "payload": self.payload,
        }


@dataclass(frozen=True, slots=True)
class ResolveInternalHostResponse:
    request_id: str
    action: HostAction
    status: HostStatus
    created_at: str
    started_at: str | None
    finished_at: str
    host: dict[str, Any]
    result: dict[str, Any]
    error: str | None
    schema_version: int = 1

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> ResolveInternalHostResponse:
        try:
            status = str(value["status"])
            action = str(value["action"])
            if status not in {
                "SUCCEEDED",
                "FAILED",
                "CANCELLED",
                "UNSUPPORTED",
            }:
                raise ValueError("status final inválido")
            if action not in {"ping", "export_voice_audio", "cancel"}:
                raise ValueError("ação inválida")
            host = value.get("host", {})
            result = value.get("result", {})
            if not isinstance(host, dict) or not isinstance(result, dict):
                raise ValueError("host/result inválido")
            return cls(
                schema_version=int(value["schema_version"]),
                request_id=str(value["request_id"]),
                action=action,  # type: ignore[arg-type]
                status=status,  # type: ignore[arg-type]
                created_at=str(value["created_at"]),
                started_at=(
                    str(value["started_at"]) if value.get("started_at") is not None else None
                ),
                finished_at=str(value["finished_at"]),
                host=host,
                result=result,
                error=str(value["error"]) if value.get("error") is not None else None,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError("Resposta do host interno inválida.") from exc


class ResolveInternalHostClient:
    def __init__(self, paths: ResolveInternalHostPaths | None = None) -> None:
        self.paths = paths or ResolveInternalHostPaths.default()
        self.paths.ensure()

    def submit(self, request: ResolveInternalHostRequest) -> Path:
        path = self.paths.requests / f"host-request-{request.request_id}.json"
        _write_json_atomic(path, request.to_dict())
        return path

    def wait(
        self,
        request: ResolveInternalHostRequest,
        *,
        timeout_seconds: float,
        poll_interval_seconds: float = 0.1,
    ) -> ResolveInternalHostResponse | None:
        response_path = self.paths.responses / f"host-response-{request.request_id}.json"
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if response_path.is_file():
                try:
                    value = json.loads(response_path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                    raise ConfigurationError("Resposta do host interno não pôde ser lida.") from exc
                if not isinstance(value, dict):
                    raise ConfigurationError("Resposta do host interno deve ser um objeto JSON.")
                response = ResolveInternalHostResponse.from_dict(value)
                if response.request_id != request.request_id:
                    raise ConfigurationError("Resposta do host interno não corresponde à request.")
                return response
            time.sleep(poll_interval_seconds)
        return None

    def ping(self, *, timeout_seconds: float = 5.0) -> ResolveInternalHostResponse | None:
        request = ResolveInternalHostRequest.create("ping")
        self.submit(request)
        return self.wait(request, timeout_seconds=timeout_seconds)


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix="host-", suffix=".tmp", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise ConfigurationError("Não foi possível gravar o protocolo do host interno.") from exc
