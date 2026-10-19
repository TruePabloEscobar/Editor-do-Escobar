"""Verify Windows shortcut targets without launching applications."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def test_shortcut_opens_editor_without_console(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe")
    assert powershell, "Esta validação de atalho exige Windows PowerShell."
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(root / "scripts/install_shortcuts.ps1"),
            "-ProjectRoot",
            str(root),
            "-DestinationDirectories",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    shortcut = tmp_path / "O EDITOR.lnk"
    assert shortcut.is_file()
    script = (
        "$link = (New-Object -ComObject WScript.Shell).CreateShortcut('"
        + str(shortcut).replace("'", "''")
        + "'); @{target=$link.TargetPath; arguments=$link.Arguments; "
        "directory=$link.WorkingDirectory} | ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        [powershell, "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=True,
    )
    value = json.loads(result.stdout)
    assert Path(value["target"]) == root / ".venv/Scripts/pythonw.exe"
    assert value["arguments"] == "-m o_editor"
    assert Path(value["directory"]) == root
