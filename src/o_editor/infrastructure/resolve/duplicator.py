"""Capability-gated safe timeline duplication strategies."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Protocol

from o_editor.domain.enums import CapabilityStatus
from o_editor.domain.models import CapabilityResult
from o_editor.errors import CapabilityGateError, OperationVerificationError


class DuplicationStrategy(Protocol):
    capability_name: str

    def duplicate(self, target_name: str) -> Any: ...


class DocumentedDuplicateStrategy:
    capability_name = "duplicate_timeline"

    def __init__(self, project: Any, source_timeline: Any) -> None:
        self._project = project
        self._source = source_timeline

    def duplicate(self, target_name: str) -> Any:
        original_name = str(self._source.GetName())
        duplicate = self._source.DuplicateTimeline(target_name)
        if duplicate is None:
            raise OperationVerificationError("DuplicateTimeline() não criou uma timeline.")
        if str(duplicate.GetName()) != target_name:
            raise OperationVerificationError("A timeline duplicada recebeu um nome inesperado.")
        timelines = tuple(
            self._project.GetTimelineByIndex(index)
            for index in range(1, int(self._project.GetTimelineCount()) + 1)
        )
        names = {str(timeline.GetName()) for timeline in timelines if timeline is not None}
        if original_name not in names or target_name not in names:
            raise OperationVerificationError(
                "Não foi possível confirmar a original e a cópia no projeto."
            )
        if not self._project.SetCurrentTimeline(duplicate):
            raise OperationVerificationError("A cópia existe, mas não pôde ser ativada.")
        current = self._project.GetCurrentTimeline()
        if current is None or str(current.GetName()) != target_name:
            raise OperationVerificationError("A cópia não ficou ativa após a duplicação.")
        return duplicate


class DrtExportImportStrategy:
    capability_name = "export_import_timeline"

    def __init__(self, resolve: Any, project: Any, source_timeline: Any) -> None:
        self._resolve = resolve
        self._project = project
        self._source = source_timeline

    def duplicate(self, target_name: str) -> Any:
        media_pool = self._project.GetMediaPool()
        with tempfile.TemporaryDirectory(prefix="OE_DUPLICATE_") as temporary:
            path = Path(temporary) / "timeline.drt"
            export_type = getattr(self._resolve, "EXPORT_DRT", None)
            if export_type is None:
                raise CapabilityGateError("A instalação não expõe a constante EXPORT_DRT.")
            if not self._source.Export(str(path), export_type):
                raise OperationVerificationError("A exportação DRT falhou.")
            duplicate = media_pool.ImportTimelineFromFile(str(path))
            if duplicate is None:
                raise OperationVerificationError("A importação DRT não criou uma timeline.")
            if not duplicate.SetName(target_name):
                raise OperationVerificationError("A cópia DRT não pôde ser renomeada.")
            if not self._project.SetCurrentTimeline(duplicate):
                raise OperationVerificationError("A cópia DRT não pôde ser ativada.")
            return duplicate


class TimelineDuplicator:
    def __init__(
        self,
        strategies: tuple[DuplicationStrategy, ...],
        capabilities: tuple[CapabilityResult, ...],
    ) -> None:
        self._strategies = strategies
        self._capabilities = {result.name: result.status for result in capabilities}

    def duplicate(self, target_name: str) -> Any:
        errors: list[str] = []
        for strategy in self._strategies:
            if self._capabilities.get(strategy.capability_name) is not CapabilityStatus.SUPPORTED:
                continue
            try:
                return strategy.duplicate(target_name)
            except (CapabilityGateError, OperationVerificationError) as exc:
                errors.append(str(exc))
        detail = "; ".join(errors) if errors else "nenhuma estratégia foi validada pelo probe"
        raise CapabilityGateError(f"Duplicação segura indisponível: {detail}.")
