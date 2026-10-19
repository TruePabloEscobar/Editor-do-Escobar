"""Exercise the preview/send/review lifecycle through actual Qt buttons."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton

from o_editor.infrastructure.config import load_config
from o_editor.ui.internal_action_runtime import InternalActionMainWindow
from tests.fixtures.podcast import podcast_layout, podcast_session

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def editor(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_kw: QMessageBox.StandardButton.Yes)
    app = QApplication.instance() or QApplication([])
    window = InternalActionMainWindow(
        config=load_config(ROOT / "config/defaults.json"), root=tmp_path, use_mock=False
    )
    panel = window._transcript_panel
    panel._layout = podcast_layout()
    panel._set_session(replace(podcast_session(), layout_fingerprint=panel._layout.fingerprint))
    panel._fill_policies()
    panel._update_buttons()
    window._navigate(3)
    window.show()
    panel.preview_button.click()
    yield window, panel, tmp_path / "O Editor/plans"
    window.close()
    app.processEvents()


def test_pending_request_keeps_waiting_visible_and_cannot_replace_preview(editor):
    _window, panel, plans = editor
    plan = panel._plan
    panel.validate_button.click()
    request = (plans / "menu-action.json").read_bytes()
    panel._update_status()  # same refresh used by an incoming Open action
    assert "Aguardando" in panel.status_label.text()
    assert not panel.preview_button.isEnabled()
    panel._preview()  # queued activation must be guarded too
    assert panel._plan is plan
    assert (plans / "menu-action.json").read_bytes() == request
    assert not panel.preset_combo.isEnabled()


@pytest.mark.parametrize("apply", [False, True])
def test_cancel_waiting_request_releases_review_and_never_leaves_an_apply_request(editor, apply):
    _window, panel, plans = editor
    (panel.apply_button if apply else panel.validate_button).click()
    cancel = panel.findChild(QPushButton, "cancelResolveRequest")
    assert cancel is not None and cancel.isVisible()
    cancel.click()
    assert not (plans / "menu-action.json").exists()
    assert list(plans.glob("menu-action-*.cancelled.json"))
    from tests.integration.test_single_menu import _run as run_menu

    assert not run_menu(plans.parent)["handled"]
    assert panel.preview_button.isEnabled() and panel.apply_button.isEnabled()
    old = panel._plan
    panel.preview_button.click()
    assert panel._plan is not old


@pytest.mark.parametrize("setting", ["protect", "edges", "policy"])
def test_all_preview_inputs_invalidate_the_plan_and_explain_how_to_continue(editor, setting):
    _window, panel, _ = editor
    assert panel.apply_button.isEnabled()
    if setting == "protect":
        panel.protect_sounds.click()
    elif setting == "edges":
        panel.trim_edges.click()
    else:
        panel.policy_table.cellWidget(0, 1).setCurrentIndex(1)
    assert not panel.apply_button.isEnabled()
    assert "prévia" in panel.status_label.text().lower()
    panel.preview_button.click()
    assert panel.apply_button.isEnabled()


def test_consumed_request_cannot_be_cancelled_as_if_it_had_not_started(editor):
    _window, panel, plans = editor
    panel.validate_button.click()
    request = plans / "menu-action.json"
    request.rename(plans / "menu-action-test.consumed.json")
    cancel = panel.findChild(QPushButton, "cancelResolveRequest")
    assert cancel is not None
    cancel.click()
    assert not panel.apply_button.isEnabled()
    assert "recebida" in panel.status_label.text().lower()


def test_buttons_complete_preview_validate_apply_and_repreview(editor):
    from o_editor.internal_actions.request import create_internal_action_request
    from tests.integration.test_lua_rough_cut import _layout, _run, _session

    window, panel, plans = editor
    work = plans.parent.parent
    layout = _layout(work)
    panel._layout = layout
    panel._set_session(_session(layout))
    panel._fill_policies()
    panel.preview_button.click()
    for apply in (False, True):
        (panel.apply_button if apply else panel.validate_button).click()
        plan_file = plans / "rough-cut-pending.json"
        saved = json.loads(plan_file.read_text(encoding="utf-8"))
        assert saved["confirmed_by_user"] is apply
        output = _run(work, plan_file, {})
        result = output["result"]
        assert result["status"] == "SUCCESS", result["message"]
        assert result["mutations"] is apply
        create_internal_action_request(
            "apply_rough_cut",
            status=result["status"],
            message=result["message"],
            details=result["details"],
        )
        window._poll_rough_cut_replies()
        assert "SUCCESS" in panel.status_label.text()
        assert panel.apply_button.isEnabled() is (not apply)
    assert result["details"]["original_verified_after"]
    assert panel.preview_button.isEnabled()
    panel.preview_button.click()
    assert panel.apply_button.isEnabled()
    assert "pronta" in panel.status_label.text()


def test_cancellation_preserves_a_request_for_a_different_plan(editor):
    from o_editor.application.rough_cut import RoughCutError, cancel_plan_for_resolve

    _window, panel, plans = editor
    panel.validate_button.click()
    request = plans / "menu-action.json"
    before = request.read_bytes()
    with pytest.raises(RoughCutError, match="não corresponde"):
        cancel_plan_for_resolve(plan_id="different", mode="VALIDATE", directory=plans)
    assert request.read_bytes() == before


@pytest.mark.parametrize("apply,receipt_failure", [(False, False), (True, False), (True, True)])
def test_confirmed_button_dispatches_script_and_receives_result_without_menu(
    editor, monkeypatch, apply, receipt_failure
):
    import shutil
    import time
    from types import SimpleNamespace

    from lupa.lua51 import LuaRuntime

    from o_editor.infrastructure.resolve.native_bridge import NativeResolveBridge
    from o_editor.infrastructure.resolve.native_bridge_worker import _run_worker, build_parser
    from tests.integration.test_lua_rough_cut import _layout, _session

    window, panel, plans = editor
    work = plans.parent.parent
    layout = _layout(work)
    panel._layout = layout
    panel._set_session(_session(layout))
    panel._fill_policies()
    panel.preview_button.click()
    (work / "launcher").mkdir()
    shutil.copy2(ROOT / "launcher/internal_common.lua", work / "launcher/internal_common.lua")
    base = plans.parent
    for folder in ["reports", "logs", "requests", "internal-scripts"]:
        (base / folder).mkdir(exist_ok=True)
    shutil.copy2(ROOT / "launcher/internal_common.lua", base / "internal_common.lua")
    shutil.copy2(
        ROOT / "launcher/O Editor - Aplicar Rough Cut.lua",
        base / "internal-scripts/O Editor - Aplicar Rough Cut.lua",
    )
    calls = []

    def start(self, *, plan_id, mode):
        # Native transport is simulated, while command generation, Lua, helper,
        # one-use request and engine are the actual production implementations.
        runtime = LuaRuntime(unpack_returned_tuples=True)
        fake = runtime.eval("dofile")((ROOT / "tests/lua/fake_resolve.lua").as_posix())
        resolve, _project, _original = fake.podcast_fixture(runtime.table())
        runtime.globals().resolve = resolve
        runtime.globals().qa_appdata = str(work)
        runtime.execute(
            "local original=os.getenv;os.getenv=function(k) "
            'if k=="APPDATA" then return qa_appdata end return original(k) end;'
            "os.execute=function() return 0 end"
        )
        if receipt_failure:
            runtime.execute(
                "local original=io.open;io.open=function(path,mode) "
                'if mode=="wb" and path:find("applied",1,true) '
                'then return nil,"QA receipt failure" end return original(path,mode) end'
            )
        loaded = SimpleNamespace(
            module=SimpleNamespace(scriptapp=lambda name: SimpleNamespace(Execute=runtime.execute)),
            resolve=resolve,
        )
        monkeypatch.setattr(
            "o_editor.infrastructure.resolve.loader.load_resolve_api", lambda **kwargs: loaded
        )

        def runner(command, cwd, timeout):
            args = build_parser().parse_args(command[command.index("--operation") :])
            code = _run_worker(args)
            import subprocess

            return subprocess.CompletedProcess(command, code, "", "")

        bridge = NativeResolveBridge(root=work, config=window._config.resolve, runner=runner)
        calls.append((plan_id, mode))
        return NativeResolveBridge.start_rough_cut_original(bridge, plan_id=plan_id, mode=mode)

    monkeypatch.setattr(
        NativeResolveBridge,
        "start_rough_cut_original",
        NativeResolveBridge.start_rough_cut,
        raising=False,
    )
    monkeypatch.setattr(NativeResolveBridge, "start_rough_cut", start)
    (panel.apply_button if apply else panel.validate_button).click()
    deadline = time.monotonic() + 8
    while (
        panel._dispatch_thread is not None or panel._pending_plan_id is not None
    ) and time.monotonic() < deadline:
        QApplication.processEvents()
        window._poll_rough_cut_replies()
        time.sleep(0.01)
    assert panel._dispatch_thread is None
    assert panel._pending_plan_id is None
    assert "SUCCESS" in panel.status_label.text(), panel.preview_text.toPlainText()
    assert len(calls) == 1 and calls[0][1] == ("APPLY" if apply else "VALIDATE")
    assert not (plans / "menu-action.json").exists()
    assert (
        "Script acionado automaticamente" in panel.preview_text.toPlainText()
        or "SUCCESS" in panel.status_label.text()
    )


def test_closed_window_stops_polling_and_does_not_steal_another_reply(tmp_path, monkeypatch):
    from o_editor.internal_actions.request import (
        create_internal_action_request,
        processed_marker_path,
    )

    monkeypatch.setenv("APPDATA", str(tmp_path))
    app = QApplication.instance() or QApplication([])
    window = InternalActionMainWindow(
        config=load_config(ROOT / "config/defaults.json"), root=tmp_path, use_mock=False
    )
    window.show()
    window.close()
    path = create_internal_action_request(
        "apply_rough_cut",
        status="SUCCESS",
        message="Teste",
        details={"plan_id": "new-plan", "mode": "VALIDATE"},
    )
    request = json.loads(path.read_text(encoding="utf-8"))
    window._poll_rough_cut_replies()
    assert not window._reply_timer.isActive()
    assert not processed_marker_path(path, request["request_id"]).exists()
    app.processEvents()
