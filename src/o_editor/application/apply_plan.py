"""Safe application use case: revalidate, duplicate, apply, verify, report."""

from __future__ import annotations

from datetime import UTC, datetime

from o_editor.domain.enums import OperationStatus, SuggestionKind
from o_editor.domain.models import (
    ApplicationOperation,
    ApplicationPlan,
    ApplicationReport,
)
from o_editor.errors import OEditorError, OperationVerificationError, TimelineChangedError
from o_editor.infrastructure.resolve.adapter import ResolveAdapter
from o_editor.infrastructure.transcription.base import CancellationToken


class ApplyPlan:
    def __init__(self, adapter: ResolveAdapter, *, text_track_name: str) -> None:
        self._adapter = adapter
        self._text_track_name = text_track_name

    def execute(
        self,
        plan: ApplicationPlan,
        *,
        cancellation: CancellationToken | None = None,
    ) -> ApplicationReport:
        started = datetime.now(UTC).isoformat()
        self._adapter.connect()
        current = self._adapter.get_active_snapshot()
        if current.fingerprint != plan.source_fingerprint:
            raise TimelineChangedError(
                "A timeline mudou desde a análise. A aplicação foi bloqueada."
            )

        if cancellation and cancellation.cancelled:
            operations = _cancel_remaining(plan.operations, [])
            return self._report(plan, current.project_name, started, operations, None)

        if plan.dry_run:
            operations = tuple(
                operation.with_result(
                    OperationStatus.SKIPPED,
                    detail=operation.detail or "Dry-run: nenhuma alteração foi enviada ao Resolve.",
                )
                for operation in plan.operations
            )
            return self._report(plan, current.project_name, started, operations, None)

        try:
            duplicate = self._adapter.duplicate_timeline(plan.target_timeline_name)
        except OEditorError as exc:
            operations = tuple(
                operation.with_result(
                    OperationStatus.FAILED,
                    detail=f"Duplicação falhou: {exc}",
                )
                if operation.status is OperationStatus.PENDING
                else operation
                for operation in plan.operations
            )
            return self._report(plan, current.project_name, started, operations, None)
        if duplicate.timeline_name != plan.target_timeline_name:
            raise OperationVerificationError("A timeline duplicada não foi confirmada.")
        if any(
            operation.kind is SuggestionKind.TEXT and operation.status is OperationStatus.PENDING
            for operation in plan.operations
        ):
            try:
                self._adapter.ensure_text_track(self._text_track_name)
            except OEditorError as exc:
                operations = tuple(
                    operation.with_result(
                        OperationStatus.FAILED,
                        detail=f"Track de textos indisponível: {exc}",
                    )
                    if operation.kind is SuggestionKind.TEXT
                    and operation.status is OperationStatus.PENDING
                    else operation
                    for operation in plan.operations
                )
                return self._report(
                    plan,
                    current.project_name,
                    started,
                    operations,
                    duplicate.timeline_name,
                )

        completed: list[ApplicationOperation] = []
        for operation in plan.operations:
            if cancellation and cancellation.cancelled:
                completed.extend(_cancel_remaining(plan.operations, completed))
                break
            if operation.status is not OperationStatus.PENDING:
                completed.append(operation)
                continue
            try:
                response = self._adapter.apply_operation(operation)
            except OEditorError as exc:
                completed.append(
                    operation.with_result(
                        OperationStatus.FAILED,
                        detail=f"Falha do backend: {exc}",
                    )
                )
                continue
            if not response.accepted:
                completed.append(
                    operation.with_result(OperationStatus.FAILED, detail=response.detail)
                )
                continue
            verified = self._adapter.verify_operation(operation)
            if verified:
                completed.append(
                    operation.with_result(
                        OperationStatus.APPLIED,
                        detail="Aplicada e verificada.",
                        verified=True,
                    )
                )
            else:
                completed.append(
                    operation.with_result(
                        OperationStatus.FAILED,
                        detail="A API aceitou a operação, mas a verificação falhou.",
                    )
                )
        return self._report(
            plan,
            current.project_name,
            started,
            tuple(completed),
            duplicate.timeline_name,
        )

    def _report(
        self,
        plan: ApplicationPlan,
        project_name: str,
        started: str,
        operations: tuple[ApplicationOperation, ...],
        target_name: str | None,
    ) -> ApplicationReport:
        capabilities_used = tuple(
            sorted(
                {
                    operation.backend
                    for operation in operations
                    if operation.status is OperationStatus.APPLIED
                }
            )
        )
        return ApplicationReport(
            analysis_id=plan.analysis_id,
            project_name=project_name,
            source_timeline_name=plan.source_timeline_name,
            target_timeline_name=target_name,
            resolve_version=self._adapter.resolve_version,
            started_at=started,
            finished_at=datetime.now(UTC).isoformat(),
            operations=operations,
            capabilities_used=capabilities_used,
        )


def _cancel_remaining(
    operations: tuple[ApplicationOperation, ...],
    completed: list[ApplicationOperation],
) -> tuple[ApplicationOperation, ...]:
    completed_ids = {operation.id for operation in completed}
    return tuple(
        operation.with_result(
            OperationStatus.SKIPPED,
            detail="Não executada porque a aplicação foi cancelada.",
        )
        for operation in operations
        if operation.id not in completed_ids
    )
