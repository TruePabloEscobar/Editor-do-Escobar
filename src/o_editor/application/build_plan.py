"""Immutable, capability-gated application plan builder."""

from __future__ import annotations

from dataclasses import dataclass

from o_editor.domain.enums import (
    CapabilityStatus,
    OperationStatus,
    SuggestionKind,
    SuggestionStatus,
)
from o_editor.domain.models import (
    ApplicationOperation,
    ApplicationPlan,
    CapabilityResult,
    JsonValue,
    Suggestion,
    TextSuggestion,
    TimelineSnapshot,
    stable_id,
)
from o_editor.errors import CapabilityGateError, TimelineChangedError
from o_editor.infrastructure.resolve.fusion_title_backend import (
    REQUIRED_TITLE_CAPABILITIES,
)
from o_editor.infrastructure.resolve.fusion_zoom_backend import (
    REQUIRED_ZOOM_CAPABILITIES,
)


@dataclass(frozen=True, slots=True)
class PlanBuildResult:
    plan: ApplicationPlan
    accepted_suggestion_ids: tuple[str, ...]
    rejected_suggestion_ids: tuple[str, ...]


def build_application_plan(
    *,
    analysis_id: str,
    analyzed_snapshot: TimelineSnapshot,
    current_snapshot: TimelineSnapshot,
    suggestions: tuple[Suggestion, ...],
    capabilities: tuple[CapabilityResult, ...],
    dry_run: bool,
    duplicate_suffix: str = "_OE_EDIT",
    existing_timeline_names: tuple[str, ...] = (),
) -> PlanBuildResult:
    if current_snapshot.fingerprint != analyzed_snapshot.fingerprint:
        raise TimelineChangedError(
            "A timeline mudou desde a análise. Faça uma nova análise antes de aplicar."
        )
    capability_statuses = {result.name: result.status for result in capabilities}
    if not dry_run and capability_statuses.get("duplicate_timeline") is not (
        CapabilityStatus.SUPPORTED
    ):
        raise CapabilityGateError(
            "A aplicação está bloqueada porque a duplicação da timeline não foi validada."
        )

    approved = tuple(suggestion for suggestion in suggestions if suggestion.approved)
    target_name = generate_timeline_name(
        analyzed_snapshot.timeline_name,
        duplicate_suffix,
        existing_timeline_names,
    )
    operations: list[ApplicationOperation] = []
    accepted: list[str] = []
    rejected: list[str] = []
    occupied: list[Suggestion] = []

    for suggestion in approved:
        rejection = _validate_suggestion(
            suggestion,
            analyzed_snapshot,
            occupied,
            capability_statuses,
            dry_run=dry_run,
        )
        status = OperationStatus.SKIPPED if rejection else OperationStatus.PENDING
        backend = (
            "dry_run"
            if dry_run
            else "fusion_zoom"
            if suggestion.kind is SuggestionKind.ZOOM
            else "fusion_title"
        )
        operation = ApplicationOperation(
            id=stable_id("op", (analysis_id, suggestion.id, backend)),
            suggestion_id=suggestion.id,
            kind=suggestion.kind,
            backend=backend,
            timeline_start_frame=suggestion.timeline_start_frame,
            timeline_end_frame=suggestion.timeline_end_frame,
            target_item_id=suggestion.clip_id,
            parameters=_operation_parameters(suggestion),
            status=status,
            detail=rejection or "",
        )
        operations.append(operation)
        if rejection:
            rejected.append(suggestion.id)
        else:
            accepted.append(suggestion.id)
            occupied.append(suggestion)

    plan = ApplicationPlan.create(
        analysis_id=analysis_id,
        source_fingerprint=analyzed_snapshot.fingerprint,
        source_timeline_name=analyzed_snapshot.timeline_name,
        target_timeline_name=target_name,
        dry_run=dry_run,
        operations=tuple(operations),
    )
    return PlanBuildResult(
        plan=plan,
        accepted_suggestion_ids=tuple(accepted),
        rejected_suggestion_ids=tuple(rejected),
    )


def generate_timeline_name(
    source_name: str,
    duplicate_suffix: str,
    existing_names: tuple[str, ...],
) -> str:
    existing = set(existing_names)
    for number in range(1, 10_000):
        candidate = f"{source_name}{duplicate_suffix}_{number:03d}"
        if candidate not in existing:
            return candidate
    raise CapabilityGateError("Não foi possível gerar um nome livre para a cópia da timeline.")


def _validate_suggestion(
    suggestion: Suggestion,
    snapshot: TimelineSnapshot,
    occupied: list[Suggestion],
    statuses: dict[str, CapabilityStatus],
    *,
    dry_run: bool,
) -> str | None:
    if suggestion.status is SuggestionStatus.CONFLICT or suggestion.conflict_reason:
        return suggestion.conflict_reason or "Sugestão marcada com conflito."
    if any(_conflicts(suggestion, existing) for existing in occupied):
        return "Conflito temporal com outra sugestão aprovada."
    required: tuple[str, ...]
    if suggestion.kind is SuggestionKind.ZOOM:
        if not suggestion.clip_id:
            return "O item de timeline da sugestão não foi identificado."
        item = next((item for item in snapshot.items if item.id == suggestion.clip_id), None)
        if item is None:
            return "O item da sugestão não existe mais na timeline."
        if item.fusion_comp_count > 0:
            return "O clip já possui Fusion e será preservado."
        required = REQUIRED_ZOOM_CAPABILITIES
    else:
        if not isinstance(suggestion, TextSuggestion):
            return "A sugestão de texto não contém um contrato TextSuggestion válido."
        required = REQUIRED_TITLE_CAPABILITIES
    if not dry_run:
        missing = [
            name for name in required if statuses.get(name) is not CapabilityStatus.SUPPORTED
        ]
        if missing:
            return "Backend obrigatório não validado: " + ", ".join(missing)
    return None


def _operation_parameters(suggestion: Suggestion) -> tuple[tuple[str, JsonValue], ...]:
    if isinstance(suggestion, TextSuggestion):
        return (*suggestion.parameters, ("text", suggestion.text))
    return suggestion.parameters


def _conflicts(first: Suggestion, second: Suggestion) -> bool:
    if first.kind is not second.kind:
        return False
    if first.kind is SuggestionKind.ZOOM and first.clip_id != second.clip_id:
        return False
    return (
        first.timeline_start_frame < second.timeline_end_frame
        and second.timeline_start_frame < first.timeline_end_frame
    )
