"""Read-only ping spike for the persistent Resolve host."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from o_editor.internal_actions.resolve_internal_host import ResolveInternalHostClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Testar o host persistente do Resolve")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--report", type=Path)
    return parser


def run_spike(*, timeout_seconds: float) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    client = ResolveInternalHostClient()
    response = client.ping(timeout_seconds=timeout_seconds)
    if response is None:
        status = "UNVERIFIED"
        detail = (
            "A request foi gravada, mas nenhum Workflow Integration ativo respondeu "
            "dentro do timeout."
        )
        response_payload = None
    elif response.status == "SUCCEEDED":
        status = "SUPPORTED"
        detail = "O Workflow Integration respondeu ao ping somente leitura."
        response_payload = {
            "request_id": response.request_id,
            "status": response.status,
            "host": response.host,
            "result": response.result,
            "error": response.error,
        }
    else:
        status = "FAILED"
        detail = response.error or "O host respondeu sem confirmar o ping."
        response_payload = response.result
    return {
        "schema_version": 1,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "status": status,
        "detail": detail,
        "mutations_executed": False,
        "response": response_payload,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_spike(timeout_seconds=args.timeout)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "SUPPORTED" else 2


if __name__ == "__main__":
    sys.exit(main())
