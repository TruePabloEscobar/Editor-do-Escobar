from __future__ import annotations

from pathlib import Path

from o_editor.application.apply_plan import ApplyPlan
from o_editor.application.build_plan import build_application_plan
from o_editor.application.generate_report import (
    load_application_plan,
    save_application_plan,
    save_application_report,
)
from o_editor.domain.enums import CapabilityStatus, OperationStatus
from o_editor.domain.models import CapabilityResult, Suggestion
from o_editor.infrastructure.analysis.heuristic import HeuristicAnalyzer
from o_editor.infrastructure.config import load_config
from o_editor.infrastructure.resolve.fusion_title_backend import (
    REQUIRED_TITLE_CAPABILITIES,
)
from o_editor.infrastructure.resolve.fusion_zoom_backend import (
    REQUIRED_ZOOM_CAPABILITIES,
)
from o_editor.infrastructure.resolve.mock_adapter import MockResolveAdapter
from o_editor.infrastructure.transcription.base import CancellationToken
from o_editor.infrastructure.transcription.mock import MockTranscriptionProvider


def _supported(name: str) -> CapabilityResult:
    return CapabilityResult(
        name=name,
        status=CapabilityStatus.SUPPORTED,
        method=f"MockResolveAdapter.{name}",
        return_value=True,
        exception=None,
        notes="teste",
        impact="teste",
        fallback="nenhum",
    )


def _approved_suggestions(tmp_path, adapter: MockResolveAdapter) -> tuple[Suggestion, ...]:
    config = load_config(Path("config/defaults.json"))
    snapshot = adapter.get_active_snapshot()
    audio = tmp_path / "mock.wav"
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


def test_mock_application_duplicates_applies_and_verifies(tmp_path) -> None:
    adapter = MockResolveAdapter()
    snapshot = adapter.get_active_snapshot()
    capabilities = tuple(
        _supported(name)
        for name in dict.fromkeys(
            (
                "duplicate_timeline",
                *REQUIRED_ZOOM_CAPABILITIES,
                *REQUIRED_TITLE_CAPABILITIES,
            )
        )
    )
    result = build_application_plan(
        analysis_id="analysis",
        analyzed_snapshot=snapshot,
        current_snapshot=snapshot,
        suggestions=_approved_suggestions(tmp_path, adapter),
        capabilities=capabilities,
        dry_run=False,
        existing_timeline_names=adapter.timeline_names,
    )
    plan_path = save_application_plan(result.plan, tmp_path)
    report = ApplyPlan(adapter, text_track_name="OE - TEXTOS").execute(result.plan)
    report_paths = save_application_report(report, tmp_path)
    assert load_application_plan(plan_path) == result.plan
    assert snapshot.timeline_name in adapter.timeline_names
    assert report.target_timeline_name == result.plan.target_timeline_name
    assert all(
        operation.status is OperationStatus.APPLIED and operation.verified
        for operation in report.operations
    )
    assert all(path.is_file() for path in report_paths)


def test_dry_run_never_duplicates_or_applies(tmp_path) -> None:
    adapter = MockResolveAdapter()
    snapshot = adapter.get_active_snapshot()
    result = build_application_plan(
        analysis_id="analysis",
        analyzed_snapshot=snapshot,
        current_snapshot=snapshot,
        suggestions=_approved_suggestions(tmp_path, adapter),
        capabilities=(),
        dry_run=True,
    )
    report = ApplyPlan(adapter, text_track_name="OE - TEXTOS").execute(result.plan)
    assert adapter.timeline_names == (snapshot.timeline_name,)
    assert not adapter.applied_operations
    assert all(operation.status is OperationStatus.SKIPPED for operation in report.operations)


def test_pre_cancelled_application_does_not_duplicate(tmp_path) -> None:
    adapter = MockResolveAdapter()
    snapshot = adapter.get_active_snapshot()
    result = build_application_plan(
        analysis_id="analysis",
        analyzed_snapshot=snapshot,
        current_snapshot=snapshot,
        suggestions=_approved_suggestions(tmp_path, adapter),
        capabilities=(),
        dry_run=True,
    )
    cancellation = CancellationToken()
    cancellation.cancel()
    report = ApplyPlan(adapter, text_track_name="OE - TEXTOS").execute(
        result.plan,
        cancellation=cancellation,
    )
    assert adapter.timeline_names == (snapshot.timeline_name,)
    assert all(operation.status is OperationStatus.SKIPPED for operation in report.operations)
