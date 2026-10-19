"""Disposable worker that alone may import the external Resolve bridge."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from o_editor.errors import OEditorError, ResolveUnavailableError

BRIDGE_SCHEMA_VERSION = 1


def _write_response(path: Path, *, result: dict[str, Any] | None, error: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".tmp")
    temporary_path.write_text(
        json.dumps(
            {
                "schema_version": BRIDGE_SCHEMA_VERSION,
                "ok": error is None,
                "result": result,
                "error": error,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _read_native_context(resolve: Any) -> dict[str, str | None]:
    project_manager = resolve.GetProjectManager()
    project = project_manager.GetCurrentProject() if project_manager else None
    if project is None:
        raise ResolveUnavailableError("Nenhum projeto está ativo no DaVinci Resolve.")
    timeline = project.GetCurrentTimeline()
    if timeline is None:
        raise ResolveUnavailableError("Nenhuma timeline está ativa no DaVinci Resolve.")
    version_method = getattr(resolve, "GetVersionString", None)
    timeline_id_method = getattr(timeline, "GetUniqueId", None)
    version = version_method() if callable(version_method) else None
    timeline_id = timeline_id_method() if callable(timeline_id_method) else None
    return {
        "project_name": str(project.GetName()),
        "timeline_name": str(timeline.GetName()),
        "timeline_id": str(timeline_id) if timeline_id else None,
        "resolve_version": str(version) if version else None,
    }


def _run_worker(args: argparse.Namespace) -> int:
    try:
        from o_editor.infrastructure.resolve.loader import load_resolve_api

        loaded = load_resolve_api(
            configured_api_paths=tuple(args.api_path),
            configured_library_paths=tuple(args.library_path),
            configured_documentation_paths=tuple(args.documentation_path),
        )
        result: dict[str, Any]
        if args.operation == "dispatch_plan":
            if (
                args.common_path is None
                or args.action_base is None
                or args.plan_id is None
                or args.mode is None
            ):
                raise ResolveUnavailableError("O pedido de execução está incompleto.")
            fusion = loaded.module.scriptapp("Fusion")
            if fusion is None:
                raise ResolveUnavailableError(
                    "O Resolve não está disponível para executar o pedido."
                )
            common_path = json.dumps(args.common_path.resolve().as_posix(), ensure_ascii=False)
            base = json.dumps(args.action_base.resolve().as_posix(), ensure_ascii=False)
            plan_id, mode = json.dumps(args.plan_id), json.dumps(args.mode)
            output_path = json.dumps(args.output.resolve().as_posix(), ensure_ascii=False)
            temporary_path = json.dumps(
                args.output.resolve().as_posix() + ".started", ensure_ascii=False
            )
            fusion.Execute(
                f"local c=dofile({common_path}); "
                f"local function reply(value) c.write_json({temporary_path},value); "
                f"assert(os.rename({temporary_path},{output_path})) end; "
                f"local ok,handled=pcall(c.dispatch_menu_action,{base},{plan_id},{mode},function() "
                f"reply({{schema_version=1,ok=true,result={{started=true,plan_id={plan_id},mode={mode}"
                "}}) end); "
                f"if not c.file_exists({output_path}) then reply({{schema_version=1,ok=false,"
                "error=ok and 'Solicitação ausente ou expirada.' or tostring(handled)}) end"
            )
            deadline = time.monotonic() + 10
            while not args.output.is_file() and time.monotonic() < deadline:
                time.sleep(0.05)
            if not args.output.is_file():
                raise ResolveUnavailableError(
                    "O Resolve não confirmou o início; o pedido não será reenviado automaticamente."
                )
            return 0
        if args.operation == "refresh_context":
            fusion = loaded.module.scriptapp("Fusion")
            if fusion is None or args.common_path is None or not args.common_path.is_file():
                raise ResolveUnavailableError("A captura interna do Resolve não está disponível.")
            common_path = json.dumps(args.common_path.resolve().as_posix(), ensure_ascii=False)
            output_path = json.dumps(args.output.resolve().as_posix(), ensure_ascii=False)
            temporary_path = json.dumps(
                args.output.resolve().as_posix() + ".capture", ensure_ascii=False
            )
            fusion.Execute(
                f"local c=dofile({common_path}); "
                "local ok,ctx=pcall(c.capture_context,nil,{capture_layout=true}); "
                f"c.write_json({temporary_path},{{schema_version=1,ok=ok,"
                "result=ok and ctx or nil,error=not ok and tostring(ctx) or nil}); "
                f"assert(os.rename({temporary_path},{output_path}))"
            )
            deadline = time.monotonic() + 10
            while not args.output.is_file() and time.monotonic() < deadline:
                time.sleep(0.05)
            if not args.output.is_file():
                raise ResolveUnavailableError("O Resolve não retornou a captura atual da timeline.")
            return 0
        if args.operation == "context":
            result = _read_native_context(loaded.resolve)
        else:
            from o_editor.infrastructure.resolve.timeline_reader import (
                read_timeline_snapshot,
            )

            result = read_timeline_snapshot(loaded.resolve).to_dict()
        _write_response(args.output, result=result, error=None)
        return 0
    except OEditorError as exc:
        _write_response(args.output, result=None, error=str(exc))
        return 2
    except Exception as exc:  # pragma: no cover - native containment boundary
        _write_response(
            args.output,
            result=None,
            error=f"Falha interna controlada na ponte do Resolve: {type(exc).__name__}: {exc}",
        )
        return 3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Worker experimental da ponte externa")
    parser.add_argument(
        "--operation",
        choices=("context", "snapshot", "refresh_context", "dispatch_plan"),
        required=True,
    )
    parser.add_argument("--plan-id")
    parser.add_argument("--mode", choices=("VALIDATE", "APPLY"))
    parser.add_argument("--action-base", type=Path)
    parser.add_argument("--common-path", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--api-path", action="append", default=[])
    parser.add_argument("--library-path", action="append", default=[])
    parser.add_argument("--documentation-path", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return _run_worker(build_parser().parse_args(argv))


if __name__ == "__main__":
    code = main()
    # Native scripting can fault during interpreter finalization. Response is durable.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
