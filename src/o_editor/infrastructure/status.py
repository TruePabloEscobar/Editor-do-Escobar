"""Independent operational component states for consolidated readiness."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ComponentState(StrEnum):
    PASSED = "PASSED"
    READY = "READY"
    PENDING = "PENDING"
    DISABLED = "DISABLED"
    UNVERIFIED = "UNVERIFIED"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


class OverallStatus(StrEnum):
    READY_INTERNAL = "READY_INTERNAL"
    READY_OFFLINE = "READY_OFFLINE"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class OperationalStatus:
    core_app: ComponentState = ComponentState.PASSED
    mock: ComponentState = ComponentState.PASSED
    internal_launcher: ComponentState = ComponentState.READY
    internal_context: ComponentState = ComponentState.UNVERIFIED
    external_fusionscript_bridge: ComponentState = ComponentState.DISABLED
    ffmpeg: ComponentState = ComponentState.PENDING
    whisper: ComponentState = ComponentState.PENDING
    analysis: ComponentState = ComponentState.READY
    plan_export: ComponentState = ComponentState.READY
    plan_application: ComponentState = ComponentState.UNVERIFIED

    @property
    def overall(self) -> OverallStatus:
        if self.core_app is ComponentState.FAILED:
            return OverallStatus.FAILED
        if self.internal_launcher in (
            ComponentState.PASSED,
            ComponentState.READY,
        ) and self.internal_context in (ComponentState.PASSED, ComponentState.READY):
            return OverallStatus.READY_INTERNAL
        if self.mock in (ComponentState.PASSED, ComponentState.READY):
            return OverallStatus.READY_OFFLINE
        return OverallStatus.DEGRADED

    def to_dict(self) -> dict[str, str]:
        return {
            "CORE_APP": self.core_app.value,
            "MOCK": self.mock.value,
            "INTERNAL_LAUNCHER": self.internal_launcher.value,
            "INTERNAL_CONTEXT": self.internal_context.value,
            "EXTERNAL_FUSIONSCRIPT_BRIDGE": self.external_fusionscript_bridge.value,
            "FFMPEG": self.ffmpeg.value,
            "WHISPER": self.whisper.value,
            "ANALYSIS": self.analysis.value,
            "PLAN_EXPORT": self.plan_export.value,
            "PLAN_APPLICATION": self.plan_application.value,
            "OVERALL": self.overall.value,
        }
