"""Plugin regressions using its actual JavaScript and isolated installer copies."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = "com.oeditor.resolve.internalhost"


def test_workflow_initialization_contract() -> None:
    node = os.environ.get("O_EDITOR_NODE") or shutil.which("node")
    assert node, "Instale Node.js para testar a inicialização real do JavaScript."
    result = subprocess.run(
        [
            node,
            str(ROOT / "tests/js/workflow_host.cjs"),
            str(ROOT / "workflow_integration" / PLUGIN / "main.js"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("drift", ["main.js", "WorkflowIntegration.node"])
def test_workflow_installer_detects_stale_artifacts(tmp_path: Path, drift: str) -> None:
    powershell = shutil.which("powershell.exe")
    assert powershell, "Esta validação do instalador exige Windows PowerShell."
    developer = tmp_path / "Developer"
    sample = developer / "Examples/SamplePlugin"
    sample.mkdir(parents=True)
    (sample / "WorkflowIntegration.node").write_bytes(b"fake-official-module")
    destination = tmp_path / "Installed"
    command = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ROOT / "scripts/install_workflow_integration.ps1"),
        "-ProjectRoot",
        str(ROOT),
        "-DeveloperRoot",
        str(developer),
        "-Destination",
        str(destination),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for source in (ROOT / "workflow_integration" / PLUGIN).iterdir():
        if source.is_file():
            assert (destination / source.name).read_bytes() == source.read_bytes()
    assert (destination / "WorkflowIntegration.node").read_bytes() == b"fake-official-module"
    (destination / drift).write_bytes(b"stale")
    result = subprocess.run(
        [*command, "-VerifyOnly"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    assert result.returncode != 0
    assert "diverg" in (result.stdout + result.stderr).casefold()


def test_workflow_installer_rejects_locked_upgrade_before_copying(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe")
    assert powershell, "Esta validação do instalador exige Windows PowerShell."
    developer = tmp_path / "Developer"
    sample = developer / "Examples/SamplePlugin"
    sample.mkdir(parents=True)
    (sample / "WorkflowIntegration.node").write_bytes(b"new-official-module")
    destination = tmp_path / "Installed"
    shutil.copytree(ROOT / "workflow_integration" / PLUGIN, destination)
    main = destination / "main.js"
    main.write_bytes(b"old-javascript")
    module = destination / "WorkflowIntegration.node"
    module.write_bytes(b"old-module")
    with module.open("rb"):
        result = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "scripts/install_workflow_integration.ps1"),
                "-ProjectRoot",
                str(ROOT),
                "-DeveloperRoot",
                str(developer),
                "-Destination",
                str(destination),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    assert result.returncode != 0
    assert "em uso" in result.stdout + result.stderr
    assert main.read_bytes() == b"old-javascript"
    assert module.read_bytes() == b"old-module"
