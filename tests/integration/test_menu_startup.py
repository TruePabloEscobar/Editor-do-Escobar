"""BUG-0029: the menu script must not spawn one cmd.exe per log line or file write.

Real logs (2026-10-22) showed about 8 s between "bootstrap started" and "completed";
the simulated run below counted 28 os.execute spawns before the fix. On Windows each
spawn of cmd.exe inside Resolve costs a fraction of a second.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from tests.lua_runner import lua_command

ROOT = Path(__file__).resolve().parents[2]


def _run(runs: int = 2) -> dict[str, Any]:
    command = lua_command()
    assert command is not None, "Lua 5.1 (ou lupa) é obrigatório para o gate"
    output = subprocess.run(
        [
            *command,
            str(ROOT / "tests/lua/run_open_startup.lua"),
            str(ROOT / "launcher"),
            str(ROOT / "tests/lua"),
            str(runs),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    return json.loads(output)


def test_open_spawns_only_the_launcher_once_directories_exist() -> None:
    result = _run()
    first, second = result["runs"]
    # First run on an empty profile: create each needed directory once, launch once.
    assert first["launched"] == 1
    mkdirs = [item for item in first["commands"] if "mkdir" in item]
    assert len(mkdirs) == len(set(mkdirs))
    assert first["spawned"] <= 5, first["commands"]
    # Steady state: the external editor launch is the only process created.
    assert second["spawned"] == 1, second["commands"]
    assert second["launched"] == 1
    # Behaviour is preserved: the request is still written and the log is complete.
    assert second["requests"] == 2
    assert result["open_log_lines"] >= 2 * 15
