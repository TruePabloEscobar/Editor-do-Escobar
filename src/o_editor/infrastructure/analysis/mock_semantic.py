"""Disabled-by-default semantic analyzer placeholder."""

from __future__ import annotations

from o_editor.domain.models import Suggestion, TimelineSnapshot, Transcript


class MockSemanticAnalyzer:
    @property
    def name(self) -> str:
        return "mock-semantic"

    def analyze(
        self,
        snapshot: TimelineSnapshot,
        transcript: Transcript,
    ) -> tuple[Suggestion, ...]:
        del snapshot, transcript
        return ()
