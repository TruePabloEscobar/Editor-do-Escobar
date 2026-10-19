"""Fusion zoom backend, deliberately gated until every operation is proven."""

from __future__ import annotations

from o_editor.domain.enums import CapabilityStatus
from o_editor.domain.models import ApplicationOperation, CapabilityResult
from o_editor.errors import CapabilityGateError
from o_editor.infrastructure.resolve.adapter import AdapterOperationResult

REQUIRED_ZOOM_CAPABILITIES = (
    "fusion_comp_access",
    "fusion_node_creation",
    "fusion_node_connections",
    "fusion_transform_keyframes",
    "fusion_keyframe_readback",
)


class FusionZoomBackend:
    def __init__(self, capabilities: tuple[CapabilityResult, ...]) -> None:
        self._statuses = {result.name: result.status for result in capabilities}

    @property
    def enabled(self) -> bool:
        return all(
            self._statuses.get(name) is CapabilityStatus.SUPPORTED
            for name in REQUIRED_ZOOM_CAPABILITIES
        )

    def apply(self, operation: ApplicationOperation) -> AdapterOperationResult:
        del operation
        if not self.enabled:
            missing = [
                name
                for name in REQUIRED_ZOOM_CAPABILITIES
                if self._statuses.get(name) is not CapabilityStatus.SUPPORTED
            ]
            raise CapabilityGateError(
                "Zoom Fusion bloqueado; capacidades não verificadas: " + ", ".join(missing)
            )
        raise CapabilityGateError(
            "O probe ainda não registrou assinaturas Fusion suficientes para uma "
            "implementação sem métodos presumidos."
        )
