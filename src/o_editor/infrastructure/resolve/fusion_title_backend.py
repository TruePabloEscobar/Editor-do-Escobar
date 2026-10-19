"""Fusion title backend with an explicit all-capabilities gate."""

from __future__ import annotations

from o_editor.domain.enums import CapabilityStatus
from o_editor.domain.models import ApplicationOperation, CapabilityResult
from o_editor.errors import CapabilityGateError
from o_editor.infrastructure.resolve.adapter import AdapterOperationResult

REQUIRED_TITLE_CAPABILITIES = (
    "insert_fusion_title",
    "position_fusion_title",
    "set_fusion_title_duration",
    "insert_title_on_named_track",
    "edit_text_plus",
    "verify_title",
)


class FusionTitleBackend:
    def __init__(self, capabilities: tuple[CapabilityResult, ...]) -> None:
        self._statuses = {result.name: result.status for result in capabilities}

    @property
    def enabled(self) -> bool:
        return all(
            self._statuses.get(name) is CapabilityStatus.SUPPORTED
            for name in REQUIRED_TITLE_CAPABILITIES
        )

    def apply(self, operation: ApplicationOperation) -> AdapterOperationResult:
        del operation
        if not self.enabled:
            raise CapabilityGateError(
                "Título Fusion bloqueado: posicionamento, duração, track e Text+ "
                "precisam ser comprovados pelo probe."
            )
        raise CapabilityGateError(
            "A assinatura de aplicação de título ainda não foi comprovada nesta instalação."
        )
