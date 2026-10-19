"""Optional future semantic analysis boundary."""

from __future__ import annotations

from typing import Protocol

from o_editor.domain.models import Suggestion, TimelineSnapshot, Transcript


class SemanticAnalyzer(Protocol):
    @property
    def name(self) -> str: ...

    def analyze(
        self,
        snapshot: TimelineSnapshot,
        transcript: Transcript,
    ) -> tuple[Suggestion, ...]: ...
