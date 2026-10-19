from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _run_installer(
    *,
    source_root: Path,
    destination: Path,
    app_data: Path,
    raw_root: str | None = None,
) -> subprocess.CompletedProcess[str]:
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        pytest.skip("PowerShell não está disponível.")
    return subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(Path.cwd() / "scripts" / "install_launcher.ps1"),
            "-ProjectRoot",
            raw_root or str(source_root),
            "-PythonExecutable",
            sys.executable,
            "-Destination",
            str(destination),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "APPDATA": str(app_data)},
        timeout=30,
    )


@pytest.mark.parametrize("variant", ["trailing_separator", "wrapped", "unmatched_quote"])
def test_launcher_installer_normalizes_paths_with_spaces(tmp_path: Path, variant: str) -> None:
    source_root = tmp_path / "Projeto de teste com espaços"
    shutil.copytree(Path.cwd() / "launcher", source_root / "launcher")
    raw_root = str(source_root) + os.sep
    if variant == "wrapped":
        raw_root = f'"{raw_root}"'
    elif variant == "unmatched_quote":
        raw_root += '"'
    destination = tmp_path / "Scripts Resolve com espaços" / "Utility"
    app_data = tmp_path / "App Data com espaços"
    completed = _run_installer(
        source_root=source_root,
        destination=destination,
        app_data=app_data,
        raw_root=raw_root,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert not (destination / "O Editor.py").exists()
    for name in (
        "O Editor - Teste de Menu.lua",
        "O Editor - Diagnóstico.lua",
        "O Editor - Abrir.lua",
        "O Editor - Capability Probe.lua",
        "O Editor - Aplicar Plano.lua",
        "O Editor - Aplicar Rough Cut.lua",
    ):
        installed = app_data / "O Editor" / "internal-scripts" / name
        assert installed.is_file()
        assert installed.read_bytes() == (source_root / "launcher" / name).read_bytes()
        assert not installed.read_bytes().startswith(b"\xef\xbb\xbf")
    assert (destination / "O EDITOR.lua").read_bytes() == (
        source_root / "launcher" / "O EDITOR.lua"
    ).read_bytes()
    assert [p.name for p in destination.glob("*.lua")] == ["O EDITOR.lua"]
    configuration_path = app_data / "O Editor" / "launcher.json"
    configuration = json.loads(configuration_path.read_text(encoding="utf-8"))
    assert Path(configuration["project_root"]) == source_root.resolve()
    assert Path(configuration["python_executable"]) == Path(sys.executable).resolve()
    assert configuration["internal_host_enabled"] is True
    assert configuration["external_bridge_enabled"] is False
    assert configuration["artifacts"]
    assert (app_data / "O Editor" / "launch-editor.cmd").is_file()
    assert (app_data / "O Editor" / "internal_common.lua").is_file()
    for directory in ("requests", "logs", "plans", "reports"):
        assert (app_data / "O Editor" / directory).is_dir()


def test_launcher_installer_moves_legacy_python_launcher(tmp_path: Path) -> None:
    source_root = tmp_path / "Projeto"
    shutil.copytree(Path.cwd() / "launcher", source_root / "launcher")
    destination = tmp_path / "Utility"
    destination.mkdir()
    legacy_content = b"broken legacy launcher"
    (destination / "O Editor.py").write_bytes(legacy_content)
    app_data = tmp_path / "App Data"
    completed = _run_installer(
        source_root=source_root,
        destination=destination,
        app_data=app_data,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert not (destination / "O Editor.py").exists()
    assert (app_data / "O Editor" / "legacy" / "O Editor.py").read_bytes() == legacy_content


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", "pode ser vazio"),
        ("M:\\inválido\rpath", "CR, LF ou TAB"),
        ("M:\\inválido\npath", "CR, LF ou TAB"),
        ("M:\\inválido\tpath", "CR, LF ou TAB"),
        ('M:\\invá"lido', "aspas incorporadas"),
        ("M:\\caminho-que-não-existe", "encontrado"),
    ],
)
def test_launcher_installer_rejects_invalid_project_paths(
    tmp_path: Path,
    value: str,
    expected: str,
) -> None:
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        pytest.skip("PowerShell não está disponível.")
    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(Path.cwd() / "scripts" / "install_launcher.ps1"),
            "-ProjectRoot",
            value,
            "-PythonExecutable",
            sys.executable,
            "-Destination",
            str(tmp_path / "Destino"),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "APPDATA": str(tmp_path / "App Data")},
        timeout=30,
    )
    assert completed.returncode != 0
    assert expected.casefold() in (completed.stdout + completed.stderr).casefold()


def test_launcher_installer_rejects_accidental_path_array(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        pytest.skip("PowerShell não está disponível.")
    script = Path.cwd() / "scripts" / "install_launcher.ps1"
    command = "& '" + str(script).replace("'", "''") + "' -ProjectRoot @('M:\\a','M:\\b')"
    completed = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            command,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "APPDATA": str(tmp_path / "App Data")},
        timeout=30,
    )
    assert completed.returncode != 0
    assert "recebeu um array" in (completed.stdout + completed.stderr)


def test_reinstallation_keeps_one_menu_and_preserves_other_scripts(tmp_path: Path) -> None:
    source_root = tmp_path / "Project"
    shutil.copytree(Path.cwd() / "launcher", source_root / "launcher")
    destination = tmp_path / "Utility"
    destination.mkdir()
    for name in (
        "O Editor - Abrir.lua",
        "O Editor - Aplicar Rough Cut.lua",
        "O Editor - Capability Probe.lua",
        "Other.lua",
    ):
        (destination / name).write_text("-- old", encoding="utf-8")
    for _ in range(2):
        result = _run_installer(
            source_root=source_root, destination=destination, app_data=tmp_path / "App Data"
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert sorted(p.name for p in destination.glob("*.lua")) == ["O EDITOR.lua", "Other.lua"]
        assert (destination / "Other.lua").read_text("utf-8") == "-- old"


def test_installer_manifest_tracks_source_release_instead_of_stale_constant(tmp_path: Path) -> None:
    source_root = tmp_path / "release"
    shutil.copytree(Path.cwd() / "launcher", source_root / "launcher")
    for lua in (source_root / "launcher").glob("*.lua"):
        text = (
            lua.read_text(encoding="utf-8")
            .replace("2.4.0", "9.9.9")
            .replace("microphone-clip-state-20261019", "fixture-release")
        )
        lua.write_text(text, encoding="utf-8")
    app_data = tmp_path / "profile"
    completed = _run_installer(
        source_root=source_root, destination=tmp_path / "Utility", app_data=app_data
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    config = json.loads((app_data / "O Editor/launcher.json").read_text(encoding="utf-8"))
    assert config["script_version"] == "9.9.9"
    assert config["build_hash"] == "fixture-release"
