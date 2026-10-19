from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if not os.environ.get("QT_QPA_FONTDIR") and os.environ.get("WINDIR"):
    candidate = Path(os.environ["WINDIR"]) / "Fonts"
    if candidate.is_dir():
        os.environ["QT_QPA_FONTDIR"] = str(candidate)

from PySide6.QtWidgets import QApplication

from o_editor.__main__ import build_parser
from o_editor.errors import ConfigurationError
from o_editor.infrastructure.config import load_config
from o_editor.internal_actions.ipc import IPC_MESSAGE_TYPES, server_name
from o_editor.internal_actions.presentation import render_internal_action
from o_editor.internal_actions.request import (
    create_internal_action_request,
    load_internal_action_request,
    mark_request_processed,
    processed_marker_path,
)
from o_editor.ui.internal_action_runtime import InternalActionMainWindow

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _request(
    tmp_path: Path,
    action: str = "menu_test",
    *,
    status: str = "SUCCESS",
) -> Path:
    root = tmp_path / "App Data com espaços e acentos" / "O Editor"
    report = root / "reports" / "relatório com espaços.md"
    log = root / "logs" / "ação.log"
    report.parent.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("# Relatório\n", encoding="utf-8")
    log.write_text("log\n", encoding="utf-8")
    return create_internal_action_request(
        action,
        status=status,
        message="Teste de menu concluído." if action == "menu_test" else "Resultado interno.",
        project="Projeto T:",
        timeline="Timeline 1",
        report_file=report,
        log_file=log,
        details={
            "confirmation_file": str(root / "menu-test-success.txt"),
            "preflight_status": "NO_PLAN",
            "context": {
                "project_name": "Projeto T:",
                "timeline_name": "Timeline 1",
                "fps": 23.976,
                "duration_frames": 240,
            },
        },
        requests_directory=root / "requests",
    )


def test_request_schema_paths_and_processed_marker(tmp_path: Path) -> None:
    path = _request(tmp_path)
    request = load_internal_action_request(path)
    assert request.schema_version == 1
    assert request.action == "menu_test"
    assert request.project == "Projeto T:"
    assert not path.read_bytes().startswith(b"\xef\xbb\xbf")
    marker = mark_request_processed(path, request)
    assert marker == processed_marker_path(path, request.request_id)
    with pytest.raises(ConfigurationError, match="já foi processada"):
        load_internal_action_request(path, reject_processed=True)


def test_expired_request_is_rejected(tmp_path: Path) -> None:
    path = _request(tmp_path)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["created_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="expirou"):
        load_internal_action_request(path)


def test_request_filename_and_schema_are_validated(tmp_path: Path) -> None:
    path = _request(tmp_path)
    value = json.loads(path.read_text(encoding="utf-8"))
    value["schema_version"] = 2
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="schema_version"):
        load_internal_action_request(path)
    arbitrary = tmp_path / "request.json"
    arbitrary.write_text("{}", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="caminho"):
        load_internal_action_request(arbitrary)


def test_internal_action_window_processes_sequence_and_duplicate(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    window = InternalActionMainWindow(
        config=load_config(PROJECT_ROOT / "config" / "defaults.json"),
        root=PROJECT_ROOT,
        use_mock=False,
    )
    first = _request(tmp_path / "primeira")
    second = _request(tmp_path / "segunda", "apply_plan", status="BLOCKED")
    first_response = window.handle_ipc_message(
        {"type": "internal_action_request", "path": str(first)}
    )
    assert first_response["duplicate"] is False
    assert "Teste de menu concluído" in window._report.toPlainText()
    assert window._project_label.text() == "Projeto T:"
    second_response = window.handle_ipc_message(
        {"type": "internal_action_request", "path": str(second)}
    )
    assert second_response["action"] == "apply_plan"
    assert "NO_PLAN" in window._report.toPlainText()
    duplicate = window.handle_ipc_message({"type": "internal_action_request", "path": str(first)})
    assert duplicate["duplicate"] is True
    assert "reapresentado" in window._report.toPlainText()
    window.close()
    app.processEvents()


def test_presentation_reports_no_timeline_mutation(tmp_path: Path) -> None:
    request = load_internal_action_request(_request(tmp_path, "apply_plan", status="BLOCKED"))
    rendered = render_internal_action(request)
    assert "A timeline original não foi alterada" in rendered
    assert "Mutações na timeline: não executadas" in rendered


def test_cli_and_ipc_contract_accept_all_internal_payloads() -> None:
    parser = build_parser()
    parsed = parser.parse_args(["--internal-action-request", "request.json"])
    assert parsed.internal_action_request == "request.json"
    assert {
        "launch_context",
        "internal_action_request",
        "show_report",
        "show_message",
        "diagnostic_result",
        "capability_result",
        "apply_result",
    }.issubset(IPC_MESSAGE_TYPES)
    assert server_name(Path("T:/O editor APP")).startswith("o-editor-")


@pytest.mark.parametrize(
    "action",
    ("menu_test", "diagnostic", "capability_probe", "apply_plan"),
)
def test_simulator_exercises_ipc_without_resolve(tmp_path: Path, action: str) -> None:
    environment = os.environ.copy()
    environment["APPDATA"] = str(tmp_path / "App Data")
    environment["QT_QPA_PLATFORM"] = "offscreen"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "o_editor.internal_actions.simulate",
            action,
        ],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "IPC: PASSED" in completed.stdout
    app_root = tmp_path / "App Data" / "O Editor"
    assert list((app_root / "requests").glob("request-*.json"))
    if action == "capability_probe":
        snapshot = json.loads(
            (app_root / "internal-capabilities.simulated.json").read_text("utf-8")
        )
        assert snapshot["mode"] == "READ_ONLY"
        assert snapshot["mutations_executed"] is False
        assert snapshot["results"]


def test_lua_actions_are_read_only_and_use_common_wrapper() -> None:
    launcher = PROJECT_ROOT / "launcher"
    common = (launcher / "internal_common.lua").read_text(encoding="utf-8")
    for path in launcher.glob("O Editor - *.lua"):
        text = path.read_text(encoding="utf-8")
        assert "run_internal_action" in text
        assert "xpcall" in text
        if path.name == "O Editor - Aplicar Rough Cut.lua":
            # The only mutating action: it delegates every mutation to the verified engine.
            assert "common.apply_rough_cut" in text
            for mutation in ("DuplicateTimeline", "AppendToTimeline", "DeleteClips"):
                assert mutation not in text
            continue
        for mutation in ("DuplicateTimeline", "AppendToTimeline", "DeleteClips", "SetTrackEnable"):
            assert mutation not in text
    assert "mutations_executed = action_result.mutations_executed == true" in common
    engine = common[common.index("function M.apply_rough_cut") :]
    assert engine.index("DuplicateTimeline") > engine.index('plan.mode ~= "APPLY"')
    assert "guard_target()" in engine
    assert "SetTrackEnable" not in common
    apply_text = (launcher / "O Editor - Aplicar Plano.lua").read_text(encoding="utf-8")
    for mutation in ("AddTrack", "DuplicateTimeline", "AppendToTimeline", "SetProperty"):
        assert mutation not in apply_text
