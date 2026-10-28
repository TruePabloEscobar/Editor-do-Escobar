"""Process-isolated, read-only access to the native Resolve scripting bridge."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn
from uuid import uuid4

from o_editor.domain.models import TimelineSnapshot
from o_editor.errors import (
    ResolveBridgeCrashedError,
    ResolveUnavailableError,
)
from o_editor.infrastructure.config import ResolveSection

BRIDGE_SCHEMA_VERSION = 1
ACCESS_VIOLATION = 0xC0000005
BridgeRunner = Callable[
    [list[str], Path, float],
    subprocess.CompletedProcess[str],
]


@dataclass(frozen=True, slots=True)
class ResolveContext:
    project_name: str
    timeline_name: str
    timeline_id: str | None
    resolve_version: str | None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "project_name": self.project_name,
            "timeline_name": self.timeline_name,
            "timeline_id": self.timeline_id,
            "resolve_version": self.resolve_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResolveContext:
        project_name = data.get("project_name")
        timeline_name = data.get("timeline_name")
        if not isinstance(project_name, str) or not project_name:
            raise ResolveUnavailableError("A ponte não retornou um projeto válido.")
        if not isinstance(timeline_name, str) or not timeline_name:
            raise ResolveUnavailableError("A ponte não retornou uma timeline válida.")
        timeline_id = data.get("timeline_id")
        resolve_version = data.get("resolve_version")
        return cls(
            project_name=project_name,
            timeline_name=timeline_name,
            timeline_id=str(timeline_id) if timeline_id else None,
            resolve_version=str(resolve_version) if resolve_version else None,
        )


class NativeResolveBridge:
    """Supervise disposable workers so native faults cannot terminate the UI."""

    def __init__(
        self,
        *,
        root: Path,
        config: ResolveSection,
        runner: BridgeRunner | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        from o_editor.infrastructure.resolve.lua_mailbox import LuaMailboxBridge, integration_mode

        self._lua_bridge = (
            LuaMailboxBridge(timeout_seconds=timeout_seconds)
            if integration_mode() == "Free"
            else None
        )
        self._root = root.resolve()
        self._config = config
        self._runner = runner or _run_process
        self._timeout_seconds = timeout_seconds

    def read_context(self) -> ResolveContext:
        if self._lua_bridge is not None:
            return ResolveContext.from_dict(self._lua_bridge.read_internal_context())
        return ResolveContext.from_dict(self._request("context"))

    def read_internal_context(self) -> dict[str, Any]:
        """Capture fresh layout inside Resolve; never enables mutation backends."""
        from o_editor.domain.timeline_layout import TimelineLayout

        if self._lua_bridge is not None:
            return self._lua_bridge.read_internal_context()
        result = self._request("refresh_context")
        TimelineLayout.from_internal_context(result)
        return {
            **result,
            "integration_mode": "internal_resolve_host",
            "connection_status": "Timeline atualizada do DaVinci Resolve.",
        }

    def start_rough_cut(self, *, plan_id: str, mode: str) -> dict[str, Any]:
        """Start exactly the confirmed one-use request; never replay or retry it."""
        if self._lua_bridge is not None:
            return self._lua_bridge.start_rough_cut(plan_id=plan_id, mode=mode)
        from o_editor.internal_actions.request import app_data_root

        if not re.fullmatch(r"[0-9a-f]{32}", plan_id) or mode not in {"VALIDATE", "APPLY"}:
            raise ResolveUnavailableError("Identificador ou modo do pedido inválido.")
        if not (self._root / "launcher/internal_common.lua").is_file():
            raise ResolveUnavailableError(
                "O capturador interno não foi encontrado nesta instalação."
            )
        return self._request(
            "dispatch_plan",
            arguments=(
                "--plan-id",
                plan_id,
                "--mode",
                mode,
                "--action-base",
                str(app_data_root()),
            ),
        )

    def set_bridge_playhead(self, frame: int, context: dict[str, Any]) -> bool:
        if self._lua_bridge is None:
            raise ResolveUnavailableError("A navegação pelo Bridge Lua não está selecionada.")
        return self._lua_bridge.set_playhead(frame, context)

    def read_snapshot(self) -> TimelineSnapshot:
        if self._lua_bridge is not None:
            raise ResolveUnavailableError(
                "Use Atualizar timeline para ler o contexto pelo EDE Bridge."
            )
        try:
            return TimelineSnapshot.from_dict(self._request("snapshot"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ResolveUnavailableError(
                "A ponte retornou um snapshot de timeline inválido."
            ) from exc

    def _request(self, operation: str, *, arguments: tuple[str, ...] = ()) -> dict[str, Any]:
        bridge_directory = self._root / "runtime" / "bridge"
        try:
            bridge_directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ResolveUnavailableError(
                "Não foi possível preparar o diretório da ponte do Resolve."
            ) from exc
        output_path = bridge_directory / f"bridge-{uuid4().hex}.json"
        command = self._worker_command(operation, output_path)
        command.extend(arguments)
        try:
            completed = self._runner(command, self._root, self._timeout_seconds)
        except (OSError, subprocess.SubprocessError) as exc:
            detail = f"A ponte isolada do Resolve não pôde ser executada: {exc}"
            self._log_failure(detail)
            raise ResolveUnavailableError(detail) from exc

        try:
            payload = _read_response(output_path)
        finally:
            with suppress(OSError):
                output_path.unlink(missing_ok=True)

        if payload is None:
            self._raise_missing_response(completed.returncode)
        if not payload.get("ok"):
            detail = str(payload.get("error") or "Falha não especificada na ponte do Resolve.")
            self._log_failure(detail)
            raise ResolveUnavailableError(detail)
        result = payload.get("result")
        if not isinstance(result, dict):
            detail = "A ponte do Resolve retornou uma resposta inválida."
            self._log_failure(detail)
            raise ResolveUnavailableError(detail)
        return result

    def _worker_command(self, operation: str, output_path: Path) -> list[str]:
        command = [
            sys.executable,
            "-m",
            "o_editor.infrastructure.resolve.native_bridge_worker",
            "--operation",
            operation,
            "--output",
            str(output_path),
        ]
        if operation in {"refresh_context", "dispatch_plan"}:
            command.extend(("--common-path", str(self._root / "launcher" / "internal_common.lua")))
        for value in self._config.api_paths:
            command.extend(("--api-path", value))
        for value in self._config.library_paths:
            command.extend(("--library-path", value))
        for value in self._config.documentation_paths:
            command.extend(("--documentation-path", value))
        return command

    def _raise_missing_response(self, returncode: int) -> NoReturn:
        unsigned_code = returncode & 0xFFFFFFFF
        if unsigned_code == ACCESS_VIOLATION:
            detail = (
                "A ponte nativa do Resolve falhou com access violation "
                "(0xC0000005). A integração real foi desativada nesta execução; "
                "O Editor pode continuar em modo seguro."
            )
            self._log_failure(detail)
            raise ResolveBridgeCrashedError(detail)
        detail = (
            "A ponte nativa do Resolve encerrou antes de responder "
            f"(return code {returncode}). A integração real foi desativada nesta execução."
        )
        self._log_failure(detail)
        raise ResolveBridgeCrashedError(detail)

    def _log_failure(self, detail: str) -> None:
        path = self._root / "runtime" / "logs" / "resolve-bridge.log"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                timestamp = datetime.now(UTC).isoformat()
                stream.write(f"{timestamp} ERROR {detail}\n")
        except OSError:
            pass


def _run_process(
    command: list[str],
    cwd: Path,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def _read_response(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResolveUnavailableError("A resposta da ponte do Resolve está corrompida.") from exc
    if not isinstance(value, dict) or value.get("schema_version") != BRIDGE_SCHEMA_VERSION:
        raise ResolveUnavailableError("A resposta da ponte do Resolve é incompatível.")
    return value
