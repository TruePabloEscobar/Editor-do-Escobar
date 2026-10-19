"""Read-only, staged DaVinci Resolve connection diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import platform
import struct
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from o_editor.errors import ConfigurationError, ResolveUnavailableError
from o_editor.infrastructure.config import load_config
from o_editor.infrastructure.resolve.loader import discover_resolve_api, load_resolve_api

EXIT_SUCCESS = 0
EXIT_ARGUMENT = 1
EXIT_CONNECTION = 2
EXIT_NO_PROJECT = 3
EXIT_NO_TIMELINE = 4
EXIT_INTERNAL = 6


@dataclass(frozen=True, slots=True)
class ConnectionCheck:
    name: str
    status: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "status": self.status, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class ConnectionReport:
    generated_at: str
    status: str
    exit_code: int
    python_version: str
    python_bits: int
    resolve_version: str | None
    project_name: str | None
    timeline_name: str | None
    checks: tuple[ConnectionCheck, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "generated_at": self.generated_at,
            "status": self.status,
            "exit_code": self.exit_code,
            "python_version": self.python_version,
            "python_bits": self.python_bits,
            "resolve_version": self.resolve_version,
            "project_name": self.project_name,
            "timeline_name": self.timeline_name,
            "checks": [check.to_dict() for check in self.checks],
        }


def is_resolve_running() -> bool:
    if os.name != "nt":
        return False
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq Resolve.exe", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0 and "Resolve.exe" in completed.stdout


def run_connection_test(
    root: Path,
    *,
    process_checker: Callable[[], bool] = is_resolve_running,
) -> ConnectionReport:
    checks: list[ConnectionCheck] = []
    python_version = platform.python_version()
    python_bits = struct.calcsize("P") * 8
    if sys.version_info[:2] != (3, 11) or python_bits != 64:
        checks.append(
            ConnectionCheck(
                "python",
                "FAILED",
                f"Exigido Python 3.11 x64; encontrado {python_version} ({python_bits} bits).",
            )
        )
        return _report(checks, EXIT_ARGUMENT)
    checks.append(ConnectionCheck("python", "PASSED", f"{python_version}, {python_bits} bits"))

    if not process_checker():
        checks.append(
            ConnectionCheck(
                "resolve_process",
                "FAILED",
                "Resolve.exe não está em execução; integração real não executada.",
            )
        )
        return _report(checks, EXIT_CONNECTION)
    checks.append(ConnectionCheck("resolve_process", "PASSED", "Resolve.exe em execução"))

    try:
        config = load_config(root / "config" / "defaults.json")
    except ConfigurationError as exc:
        checks.append(ConnectionCheck("configuration", "FAILED", str(exc)))
        return _report(checks, EXIT_ARGUMENT)

    discovery = discover_resolve_api(
        configured_api_paths=config.resolve.api_paths,
        configured_library_paths=config.resolve.library_paths,
        configured_documentation_paths=config.resolve.documentation_paths,
    )
    if discovery.module_path is None:
        checks.append(
            ConnectionCheck("resolve_module", "FAILED", "DaVinciResolveScript.py ausente.")
        )
        return _report(checks, EXIT_CONNECTION)
    checks.append(ConnectionCheck("resolve_module", "PASSED", str(discovery.module_path)))

    if discovery.library_path is None:
        checks.append(ConnectionCheck("resolve_library", "FAILED", "fusionscript.dll ausente."))
        return _report(checks, EXIT_CONNECTION)
    checks.append(ConnectionCheck("resolve_library", "PASSED", str(discovery.library_path)))

    environment_names = ("RESOLVE_SCRIPT_API", "RESOLVE_SCRIPT_LIB", "PYTHONPATH")
    original_environment = {name: os.environ.get(name) for name in environment_names}
    try:
        os.environ["RESOLVE_SCRIPT_API"] = str(discovery.module_path.parent)
        os.environ["RESOLVE_SCRIPT_LIB"] = str(discovery.library_path)
        python_path = os.environ.get("PYTHONPATH", "")
        module_parent = str(discovery.module_path.parent)
        if module_parent not in python_path.split(os.pathsep):
            os.environ["PYTHONPATH"] = os.pathsep.join(
                part for part in (module_parent, python_path) if part
            )
        loaded = load_resolve_api(
            configured_api_paths=config.resolve.api_paths,
            configured_library_paths=config.resolve.library_paths,
            configured_documentation_paths=config.resolve.documentation_paths,
        )
    except ResolveUnavailableError as exc:
        detail = str(exc)
        stage = "scriptapp"
        if "biblioteca" in detail.casefold():
            stage = "resolve_library_load"
        checks.append(ConnectionCheck(stage, "FAILED", detail))
        return _report(checks, EXIT_CONNECTION)
    finally:
        for name, value in original_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    checks.append(ConnectionCheck("module_import", "PASSED", discovery.module_path.name))
    checks.append(ConnectionCheck("scriptapp", "PASSED", "Resolve respondeu"))

    resolve = loaded.resolve
    resolve_version = _call_string(resolve, "GetVersionString")
    if resolve_version is None:
        checks.append(ConnectionCheck("resolve_version", "FAILED", "Versão não retornada."))
        return _report(checks, EXIT_CONNECTION)
    checks.append(ConnectionCheck("resolve_version", "PASSED", resolve_version))

    project_manager = resolve.GetProjectManager()
    if project_manager is None:
        checks.append(
            ConnectionCheck("project_manager", "FAILED", "GetProjectManager retornou None.")
        )
        return _report(checks, EXIT_CONNECTION, resolve_version=resolve_version)
    checks.append(ConnectionCheck("project_manager", "PASSED", "Disponível"))

    project = project_manager.GetCurrentProject()
    if project is None:
        checks.append(ConnectionCheck("active_project", "FAILED", "Nenhum projeto ativo."))
        return _report(checks, EXIT_NO_PROJECT, resolve_version=resolve_version)
    project_name = _call_string(project, "GetName")
    checks.append(ConnectionCheck("active_project", "PASSED", project_name or "sem nome"))

    timeline = project.GetCurrentTimeline()
    if timeline is None:
        checks.append(ConnectionCheck("active_timeline", "FAILED", "Nenhuma timeline ativa."))
        return _report(
            checks,
            EXIT_NO_TIMELINE,
            resolve_version=resolve_version,
            project_name=project_name,
        )
    timeline_name = _call_string(timeline, "GetName")
    checks.append(ConnectionCheck("active_timeline", "PASSED", timeline_name or "sem nome"))
    return _report(
        checks,
        EXIT_SUCCESS,
        resolve_version=resolve_version,
        project_name=project_name,
        timeline_name=timeline_name,
    )


def _call_string(target: Any, method_name: str) -> str | None:
    method = getattr(target, method_name, None)
    if not callable(method):
        return None
    try:
        value = method()
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    return str(value) if value else None


def _report(
    checks: list[ConnectionCheck],
    exit_code: int,
    *,
    resolve_version: str | None = None,
    project_name: str | None = None,
    timeline_name: str | None = None,
) -> ConnectionReport:
    return ConnectionReport(
        generated_at=datetime.now(UTC).isoformat(),
        status="PASSED" if exit_code == EXIT_SUCCESS else "FAILED",
        exit_code=exit_code,
        python_version=platform.python_version(),
        python_bits=struct.calcsize("P") * 8,
        resolve_version=resolve_version,
        project_name=project_name,
        timeline_name=timeline_name,
        checks=tuple(checks),
    )


def write_connection_report(
    report: ConnectionReport,
    json_path: Path,
    markdown_path: Path,
) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    lines = [
        "# Teste de conexão com o DaVinci Resolve",
        "",
        f"- Status: `{report.status}`",
        f"- Exit code: `{report.exit_code}`",
        f"- Python: `{report.python_version}` ({report.python_bits} bits)",
        f"- Resolve: `{report.resolve_version or 'não disponível'}`",
        f"- Projeto: `{report.project_name or 'não disponível'}`",
        f"- Timeline: `{report.timeline_name or 'não disponível'}`",
        "",
        "| Etapa | Status | Detalhe |",
        "|---|---|---|",
    ]
    lines.extend(
        f"| {check.name} | {check.status} | {_markdown_cell(check.detail)} |"
        for check in report.checks
    )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Teste somente leitura da conexão com o Resolve")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    print("O Editor — teste de conexão com o Resolve", flush=True)
    try:
        args = build_parser().parse_args(argv)
        root = args.root.resolve()
        json_path = (
            args.json_output.resolve()
            if args.json_output
            else root / "runtime" / "reports" / "resolve_connection_test.json"
        )
        markdown_path = (
            args.markdown_output.resolve()
            if args.markdown_output
            else root / "runtime" / "reports" / "RESOLVE_CONNECTION_TEST.md"
        )
        if not args.worker:
            return _run_isolated(root, json_path, markdown_path)
        report = run_connection_test(root)
        write_connection_report(report, json_path, markdown_path)
    except SystemExit as exc:
        return EXIT_SUCCESS if exc.code == 0 else EXIT_ARGUMENT
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Erro interno no teste de conexão: {exc}", file=sys.stderr, flush=True)
        return EXIT_INTERNAL
    print(f"Status: {report.status}", flush=True)
    print(f"Resolve: {report.resolve_version or 'não disponível'}", flush=True)
    print(f"Projeto: {report.project_name or 'não disponível'}", flush=True)
    print(f"Timeline: {report.timeline_name or 'não disponível'}", flush=True)
    print(f"JSON: {json_path}", flush=True)
    print(f"Markdown: {markdown_path}", flush=True)
    print(f"Exit code: {report.exit_code}", flush=True)
    return report.exit_code


def _run_isolated(root: Path, json_path: Path, markdown_path: Path) -> int:
    previous_mtime = json_path.stat().st_mtime_ns if json_path.exists() else None
    command = [
        sys.executable,
        "-m",
        "o_editor.infrastructure.resolve.connection_test",
        "--root",
        str(root),
        "--json-output",
        str(json_path),
        "--markdown-output",
        str(markdown_path),
        "--worker",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        failure_detail = f"O worker de conexão não pôde ser executado: {exc}"
    else:
        if completed.stdout:
            print(completed.stdout.rstrip(), flush=True)
        if completed.stderr:
            print(completed.stderr.rstrip(), file=sys.stderr, flush=True)
        changed = json_path.exists() and (
            previous_mtime is None or json_path.stat().st_mtime_ns != previous_mtime
        )
        if changed and completed.returncode in {
            EXIT_SUCCESS,
            EXIT_ARGUMENT,
            EXIT_CONNECTION,
            EXIT_NO_PROJECT,
            EXIT_NO_TIMELINE,
            EXIT_INTERNAL,
        }:
            return completed.returncode
        failure_detail = (
            "A ponte nativa do Resolve encerrou o worker antes de produzir um relatório "
            f"(return code {completed.returncode})."
        )
    fallback = _native_failure_report(root, failure_detail)
    write_connection_report(fallback, json_path, markdown_path)
    print(f"Status: {fallback.status}", flush=True)
    print(f"Falha: {failure_detail}", flush=True)
    print(f"JSON: {json_path}", flush=True)
    print(f"Markdown: {markdown_path}", flush=True)
    print(f"Exit code: {EXIT_CONNECTION}", flush=True)
    return EXIT_CONNECTION


def _native_failure_report(root: Path, detail: str) -> ConnectionReport:
    checks = [
        ConnectionCheck(
            "python",
            "PASSED",
            f"{platform.python_version()}, {struct.calcsize('P') * 8} bits",
        ),
        ConnectionCheck(
            "resolve_process",
            "PASSED" if is_resolve_running() else "FAILED",
            "Resolve.exe em execução"
            if is_resolve_running()
            else "Resolve.exe não está em execução",
        ),
    ]
    try:
        config = load_config(root / "config" / "defaults.json")
        discovery = discover_resolve_api(
            configured_api_paths=config.resolve.api_paths,
            configured_library_paths=config.resolve.library_paths,
            configured_documentation_paths=config.resolve.documentation_paths,
        )
    except ConfigurationError as exc:
        checks.append(ConnectionCheck("configuration", "FAILED", str(exc)))
    else:
        checks.append(
            ConnectionCheck(
                "resolve_module",
                "PASSED" if discovery.module_path else "FAILED",
                str(discovery.module_path or "DaVinciResolveScript.py ausente"),
            )
        )
        checks.append(
            ConnectionCheck(
                "resolve_library",
                "PASSED" if discovery.library_path else "FAILED",
                str(discovery.library_path or "fusionscript.dll ausente"),
            )
        )
    checks.append(ConnectionCheck("native_bridge", "FAILED", detail))
    return _report(checks, EXIT_CONNECTION)


if __name__ == "__main__":
    raise SystemExit(main())
