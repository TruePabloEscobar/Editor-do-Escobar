from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from o_editor.application.approved_plan import save_approved_plan
from o_editor.domain.enums import ZoomSubtype
from o_editor.domain.models import Suggestion, ZoomSuggestion
from o_editor.errors import CapabilityGateError
from o_editor.infrastructure.resolve.internal_adapter import InternalContextAdapter
from o_editor.infrastructure.resolve.mock_adapter import interview_timeline_fixture
from o_editor.infrastructure.status import (
    ComponentState,
    OperationalStatus,
    OverallStatus,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_internal_adapter_builds_read_only_snapshot() -> None:
    adapter = InternalContextAdapter(
        {
            "project_name": "Projeto",
            "timeline_name": "Timeline",
            "timeline_id": "id",
            "resolve_version": "21",
            "fps": 30,
            "start_frame": 0,
            "end_frame": 900,
            "start_timecode": "01:00:00:00",
            "track_counts": {"video": 2, "audio": 1, "subtitle": 0},
        }
    )

    snapshot = adapter.get_active_snapshot()
    assert snapshot.project_name == "Projeto"
    assert snapshot.video_track_count == 2
    assert snapshot.items == ()
    assert adapter.set_playhead(10) is False
    with pytest.raises(CapabilityGateError, match="duplicação"):
        adapter.duplicate_timeline("cópia")


def test_external_bridge_failure_does_not_fail_overall_status() -> None:
    status = OperationalStatus(
        internal_context=ComponentState.READY,
        external_fusionscript_bridge=ComponentState.FAILED,
    )
    assert status.overall is OverallStatus.READY_INTERNAL

    offline = OperationalStatus(
        internal_context=ComponentState.UNVERIFIED,
        external_fusionscript_bridge=ComponentState.FAILED,
    )
    assert offline.overall is OverallStatus.READY_OFFLINE


def test_approved_plan_is_saved_as_latest_and_versioned(tmp_path: Path) -> None:
    snapshot = interview_timeline_fixture()
    suggestion = snapshot.item_at(10)
    assert suggestion is not None
    approved: Suggestion = ZoomSuggestion.create(
        subtype=ZoomSubtype.PUSH_IN,
        timeline_start_frame=10,
        timeline_end_frame=60,
        confidence=0.9,
        importance=0.9,
        reason_codes=("TEST",),
        source_segment_ids=("segment",),
        clip_id=suggestion.id,
        clip_local_start_frame=10,
        clip_local_end_frame=60,
        parameters=(("zoom_peak", 1.05),),
    ).with_approval(True)

    latest, versioned = save_approved_plan(
        snapshot=snapshot,
        suggestions=(approved,),
        source_context={
            "context_kind": "internal_resolve_host",
            "start_timecode": "01:00:00:00",
        },
        app_data=tmp_path,
    )

    assert latest.exists()
    assert versioned.exists()
    assert latest != versioned
    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert payload["status"] == "APPROVED_NOT_APPLIED"
    assert payload["expected_backend"] == "internal_resolve_lua"
    assert payload["approved_suggestions"][0]["approved"] is True
    assert payload["zooms"]


def test_ui_import_graph_contains_no_native_resolve_imports() -> None:
    entrypoints = (
        PROJECT_ROOT / "src" / "o_editor" / "__main__.py",
        PROJECT_ROOT / "src" / "o_editor" / "ui" / "main_window.py",
        PROJECT_ROOT / "src" / "o_editor" / "infrastructure" / "resolve" / "internal_adapter.py",
    )
    prohibited = {"DaVinciResolveScript", "fusionscript"}
    for path in entrypoints:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        assert all(
            all(value.casefold() not in name.casefold() for value in prohibited)
            for name in imported
        )
        assert "DaVinciResolveScript" not in source
        assert "fusionscript.dll" not in source.casefold()
