"""Exercise the actual release ZIP, manifest and PowerShell validation in isolation."""

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.package_release import ROOT, package_release, public_files, release_files


def unpack(tmp_path, *, public=False):
    package = package_release(ROOT, tmp_path / "output", public=public)
    with zipfile.ZipFile(package) as archive:
        archive.extractall(tmp_path / "extracted")
    return package, tmp_path / "extracted/Editor-do-Escobar"


@pytest.mark.parametrize("public", [False, True])
def test_zip_reproducible_private_files_excluded_and_hashes_correct(tmp_path, public):
    first, source = unpack(tmp_path, public=public)
    second = package_release(ROOT, tmp_path / "second", public=public)
    assert first.read_bytes() == second.read_bytes()
    manifest = json.loads((source / "package-manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"]
    for name, expected in manifest["files"].items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected
        assert not {".venv", "runtime", "__pycache__", ".git"}.intersection(Path(name).parts)
        assert not any(part.endswith(".egg-info") for part in Path(name).parts)
        assert Path(name).suffix not in {".wav", ".mov", ".mp4", ".bin", ".env"}
    # The ZIP is a separate installation: parent pytest-cov must not count its
    # copied source tree as a second, mostly unexecuted application. Its actual
    # startup/result is still asserted here; the main source coverage is unchanged.
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COV_CORE_", "COVERAGE_"))
    }
    environment.update(
        PYTHONPATH=str(source / "src"), APPDATA=str(tmp_path / "appdata"), PYTHONUTF8="1"
    )
    result = subprocess.run(
        [sys.executable, "-m", "o_editor", "--mock", "--headless"],
        cwd=source,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "dry-run" in result.stdout


@pytest.mark.parametrize("public", [False, True])
def test_installer_validates_extracted_package_and_refuses_tamper(tmp_path, public):
    _, source = unpack(tmp_path, public=public)
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(source / "scripts/install_release.ps1"),
        "-ValidateOnly",
    ]
    good = subprocess.run(command, capture_output=True, timeout=30, check=False)
    assert good.returncode == 0, good.stdout + good.stderr
    (source / "src/o_editor/__main__.py").write_text("tampered", encoding="utf-8")
    bad = subprocess.run(command, capture_output=True, timeout=30, check=False)
    assert bad.returncode != 0
    assert b"__main__.py" in bad.stderr


def test_technical_host_contract_runs_from_extracted_release(tmp_path):
    _, source = unpack(tmp_path)
    result = subprocess.run(
        [
            "node",
            str(source / "tests/js/workflow_host.cjs"),
            str(source / "workflow_integration/com.oeditor.resolve.internalhost/main.js"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "aprovados" in result.stdout
    for name in ("manifest.xml", "index.html", "styles.css", "preload.js", "renderer.js"):
        assert (source / "workflow_integration/com.oeditor.resolve.internalhost" / name).is_file()


def test_public_snapshot_excludes_local_reports_settings_and_rejects_credentials(tmp_path):
    root = tmp_path / "source"
    for name, data in release_files(ROOT).items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    for name in ("config/personal.json", "docs/AUDITORIA_PRIVATE.md", "runtime/session.json"):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("PRIVATE_" + "SENTINEL", encoding="utf-8")
    files = public_files(root)
    assert all((b"PRIVATE_" + b"SENTINEL") not in data for data in files.values())
    assert not any(name.startswith(("qa/", "leis/")) for name in files)
    assert "AGENTS.md" not in files
    assert "Publicar EDE no GitHub.bat" in files
    (root / "src/o_editor/accidental.py").write_text(
        'credential = "' + "ghp_" + "A" * 36 + '"', encoding="utf-8"
    )
    with pytest.raises(
        ValueError, match=r"Possivel credencial recusada: src/o_editor/accidental\.py"
    ):
        public_files(root)
