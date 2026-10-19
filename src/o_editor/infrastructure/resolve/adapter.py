"""Resolve integration boundary. Domain code never imports the vendor module."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from o_editor.domain.models import (
    ApplicationOperation,
    CapabilityResult,
    TimelineSnapshot,
)


@dataclass(frozen=True, slots=True)
class AdapterOperationResult:
    accepted: bool
    detail: str


class ResolveAdapter(Protocol):
    def connect(self) -> None: ...

    @property
    def resolve_version(self) -> str | None: ...

    def get_active_snapshot(self) -> TimelineSnapshot: ...

    def export_audio(
        self,
        destination: Path,
        *,
        sample_rate: int,
        channels: int,
    ) -> Path: ...

    def duplicate_timeline(self, target_name: str) -> TimelineSnapshot: ...

    def ensure_text_track(self, name: str) -> int: ...

    def apply_operation(self, operation: ApplicationOperation) -> AdapterOperationResult: ...

    def verify_operation(self, operation: ApplicationOperation) -> bool: ...

    def set_playhead(self, frame: int) -> bool: ...

    def capability_results(self) -> tuple[CapabilityResult, ...]: ...
