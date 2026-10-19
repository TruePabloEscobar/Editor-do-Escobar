"""Optional alpha-overlay fallback. Disabled unless explicitly authorized."""

from __future__ import annotations

from o_editor.domain.models import ApplicationOperation
from o_editor.errors import CapabilityGateError
from o_editor.infrastructure.resolve.adapter import AdapterOperationResult


class AlphaTitleBackend:
    def __init__(self, *, allowed: bool = False) -> None:
        self._allowed = allowed

    @property
    def enabled(self) -> bool:
        return self._allowed

    def apply(self, operation: ApplicationOperation) -> AdapterOperationResult:
        del operation
        if not self._allowed:
            raise CapabilityGateError("O fallback AlphaTitle está desabilitado por padrão.")
        raise CapabilityGateError(
            "O fallback AlphaTitle requer um renderizador de overlay explicitamente configurado."
        )
