"""Simulate Resolve internal action requests without DaVinci Resolve."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from collections.abc import MutableMapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from o_editor.internal_actions.ipc import LocalIpcServer, send_ipc_message
from o_editor.internal_actions.presentation import render_internal_action
from o_editor.internal_actions.request import (
    app_data_root,
    create_internal_action_request,
    load_internal_action_request,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simular uma ação interna do O Editor")
    parser.add_argument(
        "action",
        nargs="?",
        choices=("menu_test", "diagnostic", "capability_probe", "apply_plan"),
    )
    parser.add_argument("--receiver", help=argparse.SUPPRESS)
    parser.add_argument("--request", help=argparse.SUPPRESS)
    parser.add_argument("--ready", help=argparse.SUPPRESS)
    parser.add_argument("--result", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.receiver:
        if not args.request or not args.ready or not args.result:
            return 2
        return _run_receiver(
            server=args.receiver,
            request_path=Path(args.request),
            ready_path=Path(args.ready),
            result_path=Path(args.result),
        )
    if args.action is None:
        build_parser().print_help()
        return 2
    return _run_simulation(args.action)


def _run_simulation(action: str) -> int:
    root = app_data_root()
    for directory in ("requests", "reports", "logs", "plans"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    result_file = root / "reports" / f"simulation-{action}-{timestamp}.json"
    report_file = root / "reports" / f"SIMULATION_{action.upper()}_{timestamp}.md"
    log_file = root / "logs" / f"simulation-{action}.log"
    status, message, details = _simulated_result(action)
    if action == "capability_probe":
        capability_file = root / "internal-capabilities.simulated.json"
        capability_file.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "generated_at": datetime.now(UTC).isoformat(),
                    "mode": "READ_ONLY",
                    "mutations_executed": False,
                    "project": "Projeto simulado",
                    "timeline": "Timeline simulada",
                    "resolve_version": None,
                    "script_version": None,
                    "build_hash": None,
                    "common_version": None,
                    "common_hash": None,
                    "results": details["results"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        details["capability_file"] = str(capability_file)
    result_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "action": action,
                "status": status,
                "message": message,
                "details": details,
                "mutations_executed": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    report_file.write_text(
        f"# Simulação de ação interna\n\n- Ação: `{action}`\n- Status: `{status}`\n\n"
        f"{message}\n\nA timeline original não foi alterada.\n",
        encoding="utf-8",
    )
    log_file.write_text(
        f"{datetime.now(UTC).isoformat()} simulation action={action} status={status}\n",
        encoding="utf-8",
    )
    request_path = create_internal_action_request(
        action,
        status=status,
        message=message,
        project="Projeto simulado",
        timeline="Timeline simulada",
        result_file=result_file,
        report_file=report_file,
        log_file=log_file,
        details=details,
        requests_directory=root / "requests",
    )
    server = f"o-editor-simulation-{uuid.uuid4().hex}"
    temporary = Path(os.environ.get("TEMP", str(root))) / "o-editor"
    temporary.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex
    ready_path = temporary / f"simulation-ready-{run_id}.json"
    ipc_result_path = temporary / f"simulation-result-{run_id}.json"
    environment = os.environ.copy()
    environment.setdefault("QT_QPA_PLATFORM", "offscreen")
    _configure_font_environment(environment)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "o_editor.internal_actions.simulate",
            "--receiver",
            server,
            "--request",
            str(request_path),
            "--ready",
            str(ready_path),
            "--result",
            str(ipc_result_path),
        ],
        env=environment,
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        _wait_for_path(ready_path, process, timeout_seconds=8)
        response = send_ipc_message(
            server,
            {"type": "internal_action_request", "path": str(request_path)},
            timeout_ms=5000,
        )
        if response is None or response.get("ok") is not True:
            raise RuntimeError(f"O IPC não confirmou a request: {response}")
        _wait_for_path(ipc_result_path, process, timeout_seconds=5)
        receiver_result = json.loads(ipc_result_path.read_text(encoding="utf-8"))
        process.terminate()
        process.communicate(timeout=5)
        request = load_internal_action_request(request_path)
        print(render_internal_action(request))
        print(f"IPC: PASSED ({receiver_result.get('request_id')})")
        print(f"Request: {request_path}")
        return 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        process.kill()
        process.communicate()
        print(f"Simulação falhou: {exc}")
        return 1
    finally:
        ready_path.unlink(missing_ok=True)
        ipc_result_path.unlink(missing_ok=True)


def _run_receiver(
    *,
    server: str,
    request_path: Path,
    ready_path: Path,
    result_path: Path,
) -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _configure_font_environment(os.environ)
    from PySide6.QtWidgets import QApplication

    from o_editor.bootstrap import bootstrap, project_root
    from o_editor.ui.internal_action_runtime import InternalActionMainWindow

    app = QApplication.instance() or QApplication([])
    window = InternalActionMainWindow(
        config=bootstrap(),
        root=project_root(),
        use_mock=False,
    )

    def handler(message: dict[str, Any]) -> dict[str, Any]:
        response = window.handle_ipc_message(message)
        temporary_result = result_path.with_suffix(result_path.suffix + ".tmp")
        temporary_result.write_text(
            json.dumps(response, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary_result, result_path)
        app.exit(0)
        return response

    ipc_server = LocalIpcServer(server, handler, window)
    if not ipc_server.listen():
        return 3
    ready_path.write_text(
        json.dumps({"server": server, "request": str(request_path)}),
        encoding="utf-8",
    )
    window.show()
    exit_code = int(app.exec())
    ipc_server.close()
    window.close()
    return exit_code


def _simulated_result(action: str) -> tuple[str, str, dict[str, Any]]:
    if action == "menu_test":
        confirmation = app_data_root() / "menu-test-success.txt"
        confirmation.write_text("simulation=true\n", encoding="utf-8")
        return (
            "SUCCESS",
            "Teste de menu concluído.",
            {"confirmation_file": str(confirmation), "simulation": True},
        )
    if action == "diagnostic":
        return (
            "SUCCESS",
            "Diagnóstico somente leitura simulado.",
            {
                "simulation": True,
                "checks": [
                    {"name": "resolve", "status": "UNVERIFIED", "detail": "simulação sem Resolve"},
                    {"name": "launcher", "status": "PASSED", "value": "request válida"},
                ],
            },
        )
    if action == "capability_probe":
        return (
            "SUCCESS",
            "Capability probe somente leitura simulado.",
            {
                "simulation": True,
                "mode": "READ_ONLY",
                "results": [
                    {
                        "name": "resolve_object",
                        "status": "UNVERIFIED",
                        "notes": "Simulação sem DaVinci Resolve.",
                    },
                    {
                        "name": "timeline_mutation",
                        "status": "UNVERIFIED",
                        "notes": "Nenhuma mutação foi executada.",
                    },
                ],
            },
        )
    return (
        "BLOCKED",
        "Aplicação bloqueada. Nenhum plano aprovado foi encontrado.",
        {
            "simulation": True,
            "preflight_status": "NO_PLAN",
            "mutations_executed": False,
            "missing_capabilities": [],
        },
    )


def _wait_for_path(path: Path, process: subprocess.Popen[str], *, timeout_seconds: int) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.exists() and path.stat().st_size > 0:
            return
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise RuntimeError(
                f"O receptor terminou antes de iniciar: {process.returncode}\n{stdout}\n{stderr}"
            )
        time.sleep(0.05)
    raise RuntimeError("O receptor IPC não iniciou dentro do prazo.")


def _configure_font_environment(environment: MutableMapping[str, str]) -> None:
    if environment.get("QT_QPA_FONTDIR"):
        return
    windows_directory = environment.get("WINDIR")
    if windows_directory:
        font_directory = Path(windows_directory) / "Fonts"
        if font_directory.is_dir():
            environment["QT_QPA_FONTDIR"] = str(font_directory)


if __name__ == "__main__":
    raise SystemExit(main())
