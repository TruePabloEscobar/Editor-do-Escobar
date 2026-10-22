"""Public snapshots exclude old local reports even with changed checkout line endings."""

import importlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_stage_snapshot_excludes_modified_private_files_without_deleting_them(
    tmp_path, monkeypatch
):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    publisher = importlib.import_module("publish_release")
    checkout = tmp_path / "repository"
    checkout.mkdir()

    def git(*args):
        return subprocess.check_output(["git", *args], cwd=checkout)

    git("init")
    git("config", "user.name", "Synthetic Test")
    git("config", "user.email", "test@example.invalid")
    git("config", "core.autocrlf", "false")
    (checkout / "README.md").write_text("Old app")
    private = checkout / "internal-report.md"
    private.write_text("Old report")
    git("add", "README.md", "internal-report.md")
    git("commit", "-m", "Synthetic initial snapshot")
    private.write_text("Unpublished local change")
    (checkout / "README.md").write_text("Current app")
    publisher.stage_snapshot(checkout, ["README.md"])
    assert git("ls-files").decode().splitlines() == ["README.md"]
    assert git("show", ":README.md") == b"Current app"
    assert private.read_text() == "Unpublished local change"
    assert b"D\tinternal-report.md" in git("diff", "--cached", "--name-status")
