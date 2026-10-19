"""Application plan/report persistence and Markdown rendering."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from o_editor.domain.enums import OperationStatus
from o_editor.domain.models import ApplicationPlan, ApplicationReport
from o_editor.errors import OEditorError


class ReportError(OEditorError):
    """Plan or report could not be persisted."""


def save_application_plan(plan: ApplicationPlan, runtime_dir: Path) -> Path:
    report_dir = runtime_dir / "reports" / plan.analysis_id
    path = report_dir / "application_plan.json"
    _atomic_text(path, plan.to_json())
    return path


def save_application_report(report: ApplicationReport, runtime_dir: Path) -> tuple[Path, Path]:
    report_dir = runtime_dir / "reports" / report.analysis_id
    json_path = report_dir / "application_report.json"
    markdown_path = report_dir / "APPLICATION_REPORT.md"
    _atomic_text(json_path, report.to_json())
    _atomic_text(markdown_path, render_application_report(report))
    return json_path, markdown_path


def render_application_report(report: ApplicationReport) -> str:
    counts = report.counts
    lines = [
        "# Relatório de aplicação — O Editor",
        "",
        f"- Análise: `{report.analysis_id}`",
        f"- Projeto: `{report.project_name}`",
        f"- Timeline original: `{report.source_timeline_name}`",
        f"- Timeline de destino: `{report.target_timeline_name or 'não criada'}`",
        f"- Resolve: `{report.resolve_version or 'não disponível'}`",
        f"- Início: `{report.started_at}`",
        f"- Fim: `{report.finished_at}`",
        f"- Operações: `{len(report.operations)}`",
        f"- Aplicadas e verificadas: `{counts[OperationStatus.APPLIED.value]}`",
        f"- Ignoradas: `{counts[OperationStatus.SKIPPED.value]}`",
        f"- Não suportadas: `{counts[OperationStatus.UNSUPPORTED.value]}`",
        f"- Falhas: `{counts[OperationStatus.FAILED.value]}`",
        "",
        "| Operação | Tipo | Backend | Estado | Verificada | Detalhe |",
        "|---|---|---|---|---:|---|",
    ]
    for operation in report.operations:
        lines.append(
            "| "
            + " | ".join(
                _cell(value)
                for value in (
                    operation.id,
                    operation.kind.value,
                    operation.backend,
                    operation.status.value,
                    "sim" if operation.verified else "não",
                    operation.detail or "—",
                )
            )
            + " |"
        )
    lines.extend(
        (
            "",
            "## Capacidades usadas",
            "",
            *(
                [f"- `{name}`" for name in report.capabilities_used]
                if report.capabilities_used
                else ["- Nenhuma capacidade real usada (dry-run/mock)."]
            ),
            "",
        )
    )
    return "\n".join(lines)


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix="oe_report_",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except OSError as exc:
        if temporary:
            temporary.unlink(missing_ok=True)
        raise ReportError(f"Não foi possível salvar {path.name}.") from exc


def load_application_plan(path: Path) -> ApplicationPlan:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError("Não foi possível ler o plano de aplicação.") from exc
    if not isinstance(value, dict):
        raise ReportError("O plano de aplicação não contém um objeto JSON.")
    return ApplicationPlan.from_dict(value)


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
