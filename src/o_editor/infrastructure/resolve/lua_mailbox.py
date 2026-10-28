"""Data-only file mailbox for manually started Resolve Scripts-menu Lua hosts.

Fusion.prefs is READ ONLY here. Only the running host saves its own namespace.
No native SDK, sockets, subprocess, or executable request source is used.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from o_editor.domain.timeline_layout import TimelineLayout
from o_editor.errors import ResolveUnavailableError

LOGGER = logging.getLogger(__name__)
MAX_BYTES = 1048576
GUID = re.compile(r"[0-9a-f]{32}")
HELP = (
    "Abra o EDE separadamente e inicie Workspace > Scripts > EDE Bridge no Resolve. "
    "Depois clique em Atualizar timeline."
)


def integration_mode() -> str:
    """Read the explicit installation choice, never infer Free from an SDK failure."""
    path = Path(os.environ.get("APPDATA", "")) / "O Editor/integration.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return "Free" if value.get("edition") == "Free" else "Studio"
    except (OSError, ValueError, AttributeError):
        return "Studio"


def frame_timecode(frame: int, context: dict[str, Any]) -> str:
    """Map absolute editorial frames using the host's actual starting timecode."""
    from o_editor.domain.timecode import frames_to_timecode

    start, end = int(context["start_frame"]), int(context["end_frame"])
    fps = float(context["fps"])
    if isinstance(frame, bool) or not isinstance(frame, int) or not start <= frame < end:
        raise ResolveUnavailableError("Frame fora dos limites da timeline.")
    tc = str(context.get("start_timecode", ""))
    match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2})([:;])(\d{2})", tc)
    if not match:
        raise ResolveUnavailableError("Timecode inicial não confirmado pelo Resolve.")
    hours, minutes, seconds, sep, frames = match.groups()
    rate = round(fps)
    total_minutes = int(hours) * 60 + int(minutes)
    origin = (total_minutes * 60 + int(seconds)) * rate + int(frames)
    drop = sep == ";"
    if drop:
        if rate not in (30, 60) or abs(fps - rate * 1000 / 1001) > 0.001:
            raise ResolveUnavailableError("FPS incompatível com drop-frame.")
        origin -= (2 if rate == 30 else 4) * (total_minutes - total_minutes // 10)
    return frames_to_timecode(origin + frame - start, fps, drop_frame=drop)


class LuaMailboxBridge:
    """Serialize bounded requests and require correlated, live-session responses."""

    def __init__(
        self,
        *,
        directory: Path | None = None,
        prefs_root: Path | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        base = Path(os.environ.get("APPDATA", ""))
        self.directory = directory or base / "O Editor/free-bridge"
        self.prefs_root = (
            prefs_root or base / "Blackmagic Design/DaVinci Resolve/Support/Fusion/Profiles"
        )
        self.timeout = min(max(timeout_seconds, 0.05), 30.0)
        self.client_session = uuid4().hex
        self.bridge_session = ""

    @contextmanager
    def _lock(self) -> Iterator[None]:
        """OS-owned mutex releases on crash; stale diagnostic files never own the slot."""
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / "client.lock"
        if os.name != "nt":
            raise ResolveUnavailableError(
                "EDE Bridge: transporte validável apenas no Windows nesta versão."
            )
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        key = hashlib.sha256(str(self.directory.resolve()).casefold().encode()).hexdigest()
        handle = kernel.CreateMutexW(None, False, "Local\\EDEBridge-" + key)
        if not handle:
            raise ResolveUnavailableError("Não foi possível reservar o EDE Bridge.")
        acquired = kernel.WaitForSingleObject(handle, 0) in (0, 128)
        try:
            if not acquired:
                raise ResolveUnavailableError("Outra operação do EDE Bridge está em andamento.")
            path.write_text(self.client_session, encoding="ascii")
            yield
        finally:
            try:
                if acquired:
                    try:
                        path.unlink(missing_ok=True)
                    finally:
                        kernel.ReleaseMutex(handle)
            finally:
                kernel.CloseHandle(handle)

    def _exchange(self, command: str, arguments: dict[str, Any]) -> dict[str, Any]:
        request_id = uuid4().hex
        request = dict(
            protocol=1,
            id=request_id,
            client_session=self.client_session,
            bridge_session=self.bridge_session,
            command=command,
            expires_at=time.time() + self.timeout,
            arguments=arguments,
        )
        data = json.dumps(
            request, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        if len(data) > MAX_BYTES:
            raise ResolveUnavailableError("Pedido excede o limite de 1 MiB.")
        path = self.directory / "request.lua"
        temporary = self.directory / f".{request_id}.tmp"
        # This exact literal is inspected as compiler output, NEVER called by Lua.
        temporary.write_text('return "EDE1_' + data.hex() + '_END"', encoding="ascii")
        temporary.replace(path)
        deadline = time.monotonic() + self.timeout
        LOGGER.info("bridge_request command=%s id=%s", command, request_id)
        try:
            while time.monotonic() < deadline:
                response = self._response(request_id)
                if response is not None:
                    if (
                        response.get("client_session") != self.client_session
                        or response.get("protocol") != 1
                    ):
                        raise ResolveUnavailableError("Resposta pertence a outra sessão do EDE.")
                    session = response.get("bridge_session")
                    if not isinstance(session, str) or not session:
                        raise ResolveUnavailableError("Resposta sem sessão do Bridge.")
                    if self.bridge_session and session != self.bridge_session:
                        raise ResolveUnavailableError("O Bridge reiniciou. Atualize a timeline.")
                    self.bridge_session = session
                    if response.get("ok") is not True:
                        raise ResolveUnavailableError(
                            str(response.get("error") or "Falha no EDE Bridge.")
                        )
                    result = response.get("result")
                    if not isinstance(result, dict):
                        raise ResolveUnavailableError("Resposta inválida do Bridge.")
                    LOGGER.info("bridge_response command=%s id=%s", command, request_id)
                    return result
                time.sleep(0.05)
        finally:
            path.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)
        LOGGER.warning("bridge_timeout command=%s id=%s", command, request_id)
        raise ResolveUnavailableError(
            "Desconectado: o EDE Bridge não respondeu dentro do prazo. " + HELP
        )

    def _response(self, request_id: str) -> dict[str, Any] | None:
        pattern = re.compile(r'EDEResponse\s*=\s*"' + request_id + r':([0-9a-f]+)"')
        for path in self.prefs_root.rglob("Fusion.prefs"):
            try:
                if path.stat().st_size > 16 * MAX_BYTES:
                    continue
                text = path.read_text(encoding="utf-8-sig")
                match = pattern.search(text)
                if not match or len(match[1]) > 2 * MAX_BYTES:
                    continue
                value = json.loads(bytes.fromhex(match[1]).decode("utf-8"))
                if isinstance(value, dict) and value.get("id") == request_id:
                    return value
            except (OSError, UnicodeError, ValueError):
                continue  # SavePrefs may be in the middle of an atomic/profile save.
        return None

    def request(self, command: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock():
            self.bridge_session = ""
            hello = self._exchange("hello", {})
            if hello.get("protocol") != 1:
                raise ResolveUnavailableError("Incompatível: versão de protocolo do Bridge.")
            return self._exchange(command, arguments or {})

    def read_internal_context(self) -> dict[str, Any]:
        context = self.request("capture")
        TimelineLayout.from_internal_context(context)
        return {**context, "connection_status": "Conectado pelo EDE Bridge Lua."}

    def set_playhead(self, frame: int, context: dict[str, Any]) -> bool:
        with self._lock():
            self.bridge_session = ""
            self._exchange("hello", {})
            self._exchange("probe_playhead", {"context": context})
            result = self._exchange(
                "set_playhead", {"context": context, "timecode": frame_timecode(frame, context)}
            )
        return result.get("verified") is True

    def start_rough_cut(self, *, plan_id: str, mode: str) -> dict[str, Any]:
        """Claim the existing one-use plan; Free writes remain physically unverified."""
        from o_editor.internal_actions.request import app_data_root, create_internal_action_request

        if GUID.fullmatch(plan_id) is None or mode not in {"VALIDATE", "APPLY"}:
            raise ResolveUnavailableError("Identificador ou modo do pedido inválido.")
        base = app_data_root()
        request_path = base / "plans/menu-action.json"
        claimed = base / f"plans/menu-action-{uuid4().hex}.bridge.json"
        with self._lock():
            request_path.rename(claimed)
            pending: dict[str, Any] = {}
            try:
                raw = json.loads(claimed.read_text(encoding="utf-8"))
                if not isinstance(raw, dict) or raw.get("schema_version") != 1:
                    raise ResolveUnavailableError("Pedido editorial inválido.")
                pending = raw
                if (
                    pending.get("plan_id") != plan_id
                    or pending.get("mode") != mode
                    or pending.get("action") not in {"rough_cut", "take_zoom"}
                ):
                    # Preserve a different request without overwriting a newer one.
                    with request_path.open("x", encoding="utf-8") as handle:
                        json.dump(pending, handle)
                    raise ResolveUnavailableError("A solicitação pertence a outro plano.")
                created = datetime.fromisoformat(
                    str(pending.get("created_at", "")).replace("Z", "+00:00")
                )
                age = (datetime.now(UTC) - created).total_seconds()
                if not 0 <= age <= 300:
                    raise ResolveUnavailableError("Pedido editorial expirado. Gere outra prévia.")
                action = pending["action"]
                self.bridge_session = ""
                self._exchange("hello", {})
                result: dict[str, Any]
                if mode == "APPLY" or action != "rough_cut":
                    result = {
                        "status": "BLOCKED",
                        "message": (
                            "Rough Cut e Zoom no Free: escrita NÃO VALIDADA em instalação real. "
                            "A prévia e a revisão continuam disponíveis."
                        ),
                        "details": {},
                        "mutations_executed": False,
                    }
                else:
                    plan = json.loads(
                        (base / "plans/rough-cut-pending.json").read_text(encoding="utf-8")
                    )
                    if plan.get("plan_id") != plan_id or plan.get("mode") != mode:
                        raise ResolveUnavailableError("O plano pendente mudou.")
                    context = self._exchange("capture", {})
                    result = self._exchange(
                        "validate_rough_cut", {"context": context, "plan": plan}
                    )
            except (OSError, ValueError, TypeError, ResolveUnavailableError) as exc:
                result = {
                    "status": "FAILED",
                    "message": str(exc),
                    "details": {},
                    "mutations_executed": False,
                }
            details = {
                **result.get("details", {}),
                "plan_id": plan_id,
                "mode": mode,
                "mutations_executed": result.get("mutations_executed") is True,
            }
            create_internal_action_request(
                "apply_rough_cut" if pending.get("action") == "rough_cut" else "apply_take_zoom",
                status=str(result.get("status", "FAILED")),
                message=str(result.get("message", "Falha no Bridge.")),
                details=details,
            )
            return {"plan_id": plan_id, "mode": mode, "status": "DISPATCHED"}
