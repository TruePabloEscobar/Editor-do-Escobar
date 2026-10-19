"""The single menu never replays a stale or unrequested editorial operation."""

from __future__ import annotations

import json
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.lua_runner import lua_command

ROOT = Path(__file__).resolve().parents[2]


def _run(base: Path) -> dict[str, object]:
    command = lua_command()
    assert command is not None
    result = subprocess.run(
        [
            *command,
            str(ROOT / "tests/lua/run_menu.lua"),
            str(ROOT / "launcher/internal_common.lua"),
            str(base),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=15,
    )
    return json.loads(result.stdout.splitlines()[-1])


def _prepare(base: Path, **changes: object) -> None:
    plans = base / "plans"
    plans.mkdir(exist_ok=True)
    plan = {"plan_id": "p1", "mode": "VALIDATE", "confirmed_by_user": False}
    request = {
        "schema_version": 1,
        "request_id": uuid.uuid4().hex,
        "action": "rough_cut",
        "plan_id": "p1",
        "mode": "VALIDATE",
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    request.update(changes)
    (plans / "rough-cut-pending.json").write_text(json.dumps(plan), encoding="utf-8")
    (plans / "menu-action.json").write_text(json.dumps(request), encoding="utf-8")


def test_leftover_plan_without_ui_request_only_opens_editor(tmp_path: Path) -> None:
    _prepare(tmp_path)
    (tmp_path / "plans/menu-action.json").unlink()
    result = _run(tmp_path)
    assert result["ok"] and not result["handled"] and not result["dispatched"]


def test_explicit_request_is_consumed_exactly_once(tmp_path: Path) -> None:
    _prepare(tmp_path)
    result = _run(tmp_path)
    assert result["ok"] and result["handled"]
    assert str(result["dispatched"]).endswith("internal-scripts/O Editor - Aplicar Rough Cut.lua")
    again = _run(tmp_path)
    assert again["ok"] and not again["handled"] and not again["dispatched"]


def test_expired_request_does_not_apply(tmp_path: Path) -> None:
    _prepare(
        tmp_path,
        created_at=(datetime.now(UTC) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    result = _run(tmp_path)
    assert result["ok"] and not result["handled"] and not result["dispatched"]


@pytest.mark.parametrize(
    "changes",
    [{"plan_id": "other"}, {"mode": "APPLY"}, {"action": "other"}, {"request_id": "../escape"}],
)
def test_invalid_or_unconfirmed_request_never_dispatches(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    _prepare(tmp_path, **changes)
    result = _run(tmp_path)
    assert not result["ok"] and not result["dispatched"]
