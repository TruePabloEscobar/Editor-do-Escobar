"""Exercise the actual release ZIP, manifest and PowerShell validation in isolation."""

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

from scripts.package_release import ROOT, package_release


def unpack(tmp_path):
    package = package_release(ROOT, tmp_path / "output")
    with zipfile.ZipFile(package) as archive:
        archive.extractall(tmp_path / "extracted")
    return package, tmp_path / "extracted/Editor-do-Escobar"


def test_zip_reproducible_private_files_excluded_and_hashes_correct(tmp_path):
    first, source = unpack(tmp_path)
    second = package_release(ROOT, tmp_path / "second")
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


def test_installer_validates_extracted_package_and_refuses_tamper(tmp_path):
    _, source = unpack(tmp_path)
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
