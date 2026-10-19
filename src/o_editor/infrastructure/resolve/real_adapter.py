"""Real Resolve adapter restricted to isolated, capability-gated operations."""

from __future__ import annotations

from pathlib import Path

from o_editor.domain.models import (
    ApplicationOperation,
    CapabilityResult,
    TimelineSnapshot,
)
from o_editor.errors import CapabilityGateError
from o_editor.infrastructure.config import ResolveSection
from o_editor.infrastructure.resolve.adapter import AdapterOperationResult
from o_editor.infrastructure.resolve.native_bridge import (
    NativeResolveBridge,
    ResolveContext,
)


class RealResolveAdapter:
    def __init__(
        self,
        config: ResolveSection,
        capabilities: tuple[CapabilityResult, ...] = (),
        *,
        root: Path,
        bridge: NativeResolveBridge | None = None,
    ) -> None:
        self._capabilities = capabilities
        self._bridge = bridge or NativeResolveBridge(root=root, config=config)
        self._context: ResolveContext | None = None

    def connect(self) -> None:
        if self._context is None:
            self._context = self._bridge.read_context()

    @property
    def resolve_version(self) -> str | None:
        self.connect()
        return self._context.resolve_version if self._context else None

    def get_active_snapshot(self) -> TimelineSnapshot:
        return self._bridge.read_snapshot()

    def export_audio(
        self,
        destination: Path,
        *,
        sample_rate: int,
        channels: int,
    ) -> Path:
        del destination, sample_rate, channels
        raise CapabilityGateError(
            "A exportação de áudio real permanece bloqueada até um render WAV ser "
            "executado e verificado pelo capability probe. Use seleção manual de WAV."
        )

    def duplicate_timeline(self, target_name: str) -> TimelineSnapshot:
        del target_name
        raise CapabilityGateError(
            "A duplicação real permanece bloqueada: a ponte isolada da interface "
            "expõe somente operações de leitura."
        )

    def ensure_text_track(self, name: str) -> int:
        del name
        raise CapabilityGateError(
            "Criação de track real bloqueada até o probe confirmar criação e renomeação."
        )

    def apply_operation(self, operation: ApplicationOperation) -> AdapterOperationResult:
        del operation
        return AdapterOperationResult(
            False,
            "Nenhum backend real foi integralmente validado pelo capability probe.",
        )

    def verify_operation(self, operation: ApplicationOperation) -> bool:
        del operation
        return False

    def set_playhead(self, frame: int) -> bool:
        del frame
        return False

    def capability_results(self) -> tuple[CapabilityResult, ...]:
        return self._capabilities
