from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from o_editor.errors import ResolveBridgeCrashedError
from o_editor.infrastructure.config import load_config
from o_editor.infrastructure.resolve.mock_adapter import interview_timeline_fixture
from o_editor.infrastructure.resolve.native_bridge import NativeResolveBridge

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_access_violation_is_contained_and_logged(tmp_path: Path) -> None:
    root = tmp_path / "Projeto com espaços"
    config = load_config(PROJECT_ROOT / "config" / "defaults.json")

    def crashed_runner(
        command: list[str],
        cwd: Path,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[str]:
        assert cwd == root.resolve()
        assert timeout_seconds == 30.0
        return subprocess.CompletedProcess(command, 0xC0000005, "", "")

    bridge = NativeResolveBridge(
        root=root,
        config=config.resolve,
        runner=crashed_runner,
    )

    with pytest.raises(ResolveBridgeCrashedError, match="0xC0000005"):
        bridge.read_context()

    log = root / "runtime" / "logs" / "resolve-bridge.log"
    assert log.exists()
    assert "access violation" in log.read_text(encoding="utf-8")


def test_bridge_preserves_paths_with_spaces_as_single_arguments(tmp_path: Path) -> None:
    root = tmp_path / "Projeto com espaços"
    config = load_config(PROJECT_ROOT / "config" / "defaults.json")
    snapshot = interview_timeline_fixture()
    observed_commands: list[list[str]] = []

    def successful_runner(
        command: list[str],
        cwd: Path,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, timeout_seconds
        observed_commands.append(command)
        output = Path(command[command.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "ok": True,
                    "result": snapshot.to_dict(),
                    "error": None,
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    bridge = NativeResolveBridge(
        root=root,
        config=config.resolve,
        runner=successful_runner,
    )

    assert bridge.read_snapshot() == snapshot
    output_argument = observed_commands[0][observed_commands[0].index("--output") + 1]
    assert "Projeto com espaços" in output_argument
    assert Path(output_argument).parent == root.resolve() / "runtime" / "bridge"
    assert not Path(output_argument).exists()


def test_refresh_worker_captures_layout_with_real_lua_and_atomic_file(tmp_path, monkeypatch):
    from argparse import Namespace
    from types import SimpleNamespace

    from lupa.lua51 import LuaRuntime

    from o_editor.infrastructure.resolve.native_bridge_worker import _run_worker

    runtime = LuaRuntime(unpack_returned_tuples=True)
    fixture = runtime.eval("dofile")((PROJECT_ROOT / "tests/lua/fake_resolve.lua").as_posix())
    resolve, _project, original = fixture.podcast_fixture(runtime.table())
    runtime.globals().resolve = resolve
    fusion = SimpleNamespace(Execute=runtime.execute)
    loaded = SimpleNamespace(module=SimpleNamespace(scriptapp=lambda name: fusion), resolve=resolve)
    monkeypatch.setattr(
        "o_editor.infrastructure.resolve.loader.load_resolve_api", lambda **kwargs: loaded
    )
    path = tmp_path / "capture.json"
    args = Namespace(
        operation="refresh_context",
        api_path=[],
        library_path=[],
        documentation_path=[],
        output=path,
        common_path=PROJECT_ROOT / "launcher/internal_common.lua",
    )
    assert _run_worker(args) == 0
    result = json.loads(path.read_text(encoding="utf-8"))
    assert result["ok"]
    assert result["result"]["timeline_name"] == "Episodio 1"
    assert len(result["result"]["layout"]["clips"]) == 6
    assert not list(tmp_path.glob("*.capture"))
    assert len(original.mutation_log) == 0


@pytest.mark.parametrize("confirmed,match", [(True, True), (False, True), (True, False)])
def test_dispatch_worker_correlates_consumes_once_and_requires_confirmation(
    tmp_path, monkeypatch, confirmed, match
):
    from types import SimpleNamespace

    from lupa.lua51 import LuaRuntime

    from o_editor.infrastructure.resolve.native_bridge_worker import _run_worker, build_parser
    from tests.integration.test_single_menu import _prepare

    _prepare(tmp_path, mode="APPLY")
    plan_path = tmp_path / "plans/rough-cut-pending.json"
    plan = json.loads(plan_path.read_text())
    plan.update(mode="APPLY", confirmed_by_user=confirmed)
    plan_path.write_text(json.dumps(plan))
    scripts = tmp_path / "internal-scripts"
    scripts.mkdir()
    marker = tmp_path / "called.txt"
    (scripts / "O Editor - Aplicar Rough Cut.lua").write_text(
        "local f=assert(io.open("
        + json.dumps(marker.as_posix())
        + ',"ab"));f:write("called");f:close()',
        encoding="utf-8",
    )
    runtime = LuaRuntime(unpack_returned_tuples=True)
    fusion = SimpleNamespace(Execute=runtime.execute)
    monkeypatch.setattr(
        "o_editor.infrastructure.resolve.loader.load_resolve_api",
        lambda **kwargs: SimpleNamespace(
            module=SimpleNamespace(scriptapp=lambda name: fusion), resolve=None
        ),
    )
    for number in range(2):
        path = tmp_path / f"reply-{number}.json"
        args = build_parser().parse_args(
            [
                "--operation",
                "dispatch_plan",
                "--output",
                str(path),
                "--common-path",
                str(PROJECT_ROOT / "launcher/internal_common.lua"),
                "--action-base",
                str(tmp_path),
                "--plan-id",
                "p1" if match else "other",
                "--mode",
                "APPLY",
            ]
        )
        assert _run_worker(args) == 0
        reply = json.loads(path.read_text(encoding="utf-8"))
        assert reply["ok"] is (confirmed and match and number == 0)
    assert marker.exists() is (confirmed and match)
    if marker.exists():
        assert marker.read_text() == "called"
    assert (tmp_path / "plans/menu-action.json").exists() is (not match)
