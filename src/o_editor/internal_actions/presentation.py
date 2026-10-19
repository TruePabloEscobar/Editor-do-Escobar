"""Portuguese UI rendering for Resolve internal action results."""

from __future__ import annotations

from typing import Any

from o_editor.internal_actions.request import InternalActionRequest


def render_internal_action(request: InternalActionRequest) -> str:
    header = {
        "open": "O Editor aberto pelo DaVinci Resolve.",
        "menu_test": "Teste de menu concluído.",
        "diagnostic": "Diagnóstico interno concluído.",
        "capability_probe": "Capability probe interno concluído.",
        "apply_plan": "Preflight de aplicação concluído.",
        "apply_rough_cut": "Rough cut processado pelo DaVinci Resolve.",
    }[request.action]
    lines = [
        header,
        "",
        request.message,
        "",
        f"Status: {request.status}",
        f"Data: {request.created_at}",
        f"Projeto: {request.project or 'não disponível'}",
        f"Timeline: {request.timeline or 'não disponível'}",
    ]
    if request.action == "menu_test":
        lines.extend(
            [
                "",
                "O DaVinci Resolve executou corretamente o script interno.",
                f"Arquivo de confirmação: {_detail(request.details, 'confirmation_file')}",
            ]
        )
    elif request.action == "diagnostic":
        lines.extend(["", "Verificações:"])
        lines.extend(_render_checks(request.details.get("checks")))
    elif request.action == "capability_probe":
        lines.extend(["", "Capabilities somente leitura:"])
        lines.extend(_render_capabilities(request.details.get("results")))
    elif request.action == "apply_plan":
        lines.extend(
            [
                "",
                f"Resultado do preflight: {_detail(request.details, 'preflight_status')}",
                "A timeline original não foi alterada.",
            ]
        )
        missing = request.details.get("missing_capabilities")
        if isinstance(missing, list) and missing:
            lines.append("Capabilities ausentes: " + ", ".join(str(item) for item in missing))
    elif request.action == "apply_rough_cut":
        lines.extend(_render_rough_cut(request))
    if request.report_file:
        lines.append(f"Relatório: {request.report_file}")
    if request.log_file:
        lines.append(f"Log: {request.log_file}")
    lines.extend(
        [
            "",
            f"Request: {request.request_id}",
            (
                "Mutações na timeline: executadas somente na cópia"
                if request.action == "apply_rough_cut" and request.details.get("created_timeline")
                else "Mutações na timeline: não executadas"
            ),
        ]
    )
    return "\n".join(lines)


def _render_checks(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["- UNVERIFIED — nenhuma verificação foi informada."]
    output = []
    for item in value:
        if not isinstance(item, dict):
            continue
        output.append(
            f"- {item.get('status', 'UNVERIFIED')} — {item.get('name', 'verificação')}: "
            f"{item.get('value') or item.get('error') or item.get('detail') or ''}"
        )
    return output or ["- UNVERIFIED — nenhuma verificação válida foi informada."]


def _render_capabilities(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["- UNVERIFIED — nenhuma capability foi informada."]
    output = []
    for item in value:
        if not isinstance(item, dict):
            continue
        output.append(
            f"- {item.get('status', 'UNVERIFIED')} — {item.get('name', 'capability')}: "
            f"{item.get('notes') or item.get('error') or item.get('method') or ''}"
        )
    return output or ["- UNVERIFIED — nenhuma capability válida foi informada."]


def _detail(details: dict[str, Any], key: str) -> str:
    value = details.get(key)
    return str(value) if value not in (None, "") else "não disponível"


def _render_rough_cut(request: InternalActionRequest) -> list[str]:
    details = request.details
    lines = [""]
    created = details.get("created_timeline")
    if created:
        lines.append(f"Nova timeline: {created}")
    lines.append(
        f"Itens criados e conferidos: {details.get('operations_applied', 0)} de "
        f"{details.get('operations_total', 0)}"
    )
    lines.append(
        "Mutações executadas: "
        + ("sim (somente na nova timeline)" if details.get("created_timeline") else "não")
    )
    if details.get("original_verified_after") is True:
        lines.append("Timeline original conferida após a aplicação: intacta.")
    calibration = details.get("calibration")
    if isinstance(calibration, dict) and calibration:
        lines.append(
            "Convenção do AppendToTimeline detectada: endFrame inclusivo="
            f"{calibration.get('end_frame_inclusive')}, recordFrame relativo="
            f"{calibration.get('record_frame_relative')}"
        )
    lines.append("")
    lines.append("Verificações:")
    lines.extend(_render_checks(details.get("checks")))
    warnings = details.get("warnings")
    if isinstance(warnings, list) and warnings:
        lines.append("")
        lines.append("Avisos:")
        lines.extend(f"- {item}" for item in warnings)
    return lines
