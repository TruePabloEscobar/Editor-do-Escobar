from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from o_editor.application.build_plan import (
    build_application_plan,
    generate_timeline_name,
)
from o_editor.domain.enums import CapabilityStatus
from o_editor.domain.models import CapabilityResult, Suggestion
from o_editor.errors import CapabilityGateError, TimelineChangedError
from o_editor.infrastructure.analysis.heuristic import HeuristicAnalyzer
from o_editor.infrastructure.config import load_config
from o_editor.infrastructure.resolve.fusion_title_backend import (
    REQUIRED_TITLE_CAPABILITIES,
)
from o_editor.infrastructure.resolve.fusion_zoom_backend import (
    REQUIRED_ZOOM_CAPABILITIES,
)
from o_editor.infrastructure.resolve.mock_adapter import interview_timeline_fixture
from o_editor.infrastructure.transcription.mock import MockTranscriptionProvider


def _supported(name: str) -> CapabilityResult:
    return CapabilityResult(
        name=name,
        status=CapabilityStatus.SUPPORTED,
        method=f"mock.{name}",
        return_value=True,
        exception=None,
        notes="teste",
        impact="teste",
        fallback="nenhum",
    )


def _suggestions(tmp_path) -> tuple[Suggestion, ...]:
    config = load_config(Path("config/defaults.json"))
    snapshot = interview_timeline_fixture()
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"mock")
    transcript = MockTranscriptionProvider().transcribe(
        audio,
        fps=snapshot.fps,
        timeline_start_frame=snapshot.start_frame,
        language="pt",
    )
    return tuple(
        item.with_approval(True)
        for item in HeuristicAnalyzer(
            zoom=config.zoom,
            text=config.text,
            configured_keywords=config.analysis.keywords,
        ).analyze(snapshot, transcript)
    )


def test_plan_blocks_changed_timeline(tmp_path) -> None:
    snapshot = interview_timeline_fixture()
    changed = replace(snapshot, end_frame=snapshot.end_frame + 1)
    with pytest.raises(TimelineChangedError):
        build_application_plan(
            analysis_id="analysis",
            analyzed_snapshot=snapshot,
            current_snapshot=changed,
            suggestions=_suggestions(tmp_path),
            capabilities=(),
            dry_run=True,
        )


def test_real_plan_requires_duplicate_capability(tmp_path) -> None:
    snapshot = interview_timeline_fixture()
    with pytest.raises(CapabilityGateError, match="duplicação"):
        build_application_plan(
            analysis_id="analysis",
            analyzed_snapshot=snapshot,
            current_snapshot=snapshot,
            suggestions=_suggestions(tmp_path),
            capabilities=(),
            dry_run=False,
        )


def test_dry_run_builds_without_real_backends(tmp_path) -> None:
    snapshot = interview_timeline_fixture()
    result = build_application_plan(
        analysis_id="analysis",
        analyzed_snapshot=snapshot,
        current_snapshot=snapshot,
        suggestions=_suggestions(tmp_path),
        capabilities=(),
        dry_run=True,
    )
    assert result.plan.dry_run
    assert result.accepted_suggestion_ids
    assert all(operation.backend == "dry_run" for operation in result.plan.operations)


def test_real_plan_accepts_fully_validated_mock_capabilities(tmp_path) -> None:
    snapshot = interview_timeline_fixture()
    names = (
        "duplicate_timeline",
        *REQUIRED_ZOOM_CAPABILITIES,
        *REQUIRED_TITLE_CAPABILITIES,
    )
    result = build_application_plan(
        analysis_id="analysis",
        analyzed_snapshot=snapshot,
        current_snapshot=snapshot,
        suggestions=_suggestions(tmp_path),
        capabilities=tuple(_supported(name) for name in dict.fromkeys(names)),
        dry_run=False,
    )
    assert result.accepted_suggestion_ids
    assert not result.rejected_suggestion_ids


def test_timeline_name_increments() -> None:
    assert (
        generate_timeline_name(
            "Entrevista",
            "_OE_EDIT",
            ("Entrevista_OE_EDIT_001",),
        )
        == "Entrevista_OE_EDIT_002"
    )
