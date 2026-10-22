"""Publish a checked source snapshot and a public GitHub release, without force-push."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from importlib.metadata import version
from pathlib import Path

from package_release import ROOT, package_release, public_files

REPOSITORY = "TruePabloEscobar/Editor-do-Escobar"


def run(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True, encoding="utf-8", errors="replace")


def validation_asset(package: Path) -> Path:
    report = json.loads((ROOT / "runtime/regression/latest.json").read_text(encoding="utf-8"))
    if report["status"] != "PASSED":
        raise RuntimeError("O gate mais recente não passou; publicação recusada.")
    run_directory = Path(report["run_directory"])
    suites = ET.parse(run_directory / "junit.xml").getroot()
    counts = {
        key: sum(int(s.get(key, 0)) for s in suites.iter("testsuite"))
        for key in ("tests", "failures", "errors", "skipped")
    }
    if counts["failures"] or counts["errors"] or counts["skipped"]:
        raise RuntimeError("Resultados incompletos; publicação recusada.")
    coverage = ET.parse(run_directory / "coverage.xml").getroot()
    summary = {
        "status": "PASSED",
        **counts,
        "coverage_line_rate": float(coverage.get("line-rate", "0")),
        "coverage_branch_rate": float(coverage.get("branch-rate", "0")),
        "tools": {
            n: version(n) for n in ("PySide6", "faster-whisper", "ctranslate2", "pytest", "ruff")
        },
        "timeline_mutations": False,
        "resolve_api_this_run": "UNVERIFIED",
        "human_audio_review": "PENDING",
    }
    target = package.with_suffix(".validation.json")
    target.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return target


def stage_snapshot(checkout: Path, names: list[str]) -> None:
    """Stage only the approved tree; remove obsolete entries from the index only."""
    tracked = run("git", "ls-files", "-z", cwd=checkout).split("\0")
    obsolete = [name for name in tracked if name and name not in names]
    if obsolete:
        # A clone may have CRLF-normalized files. Their disk contents are irrelevant:
        # only the exact approved names can enter the public index.
        run("git", "rm", "--cached", "--", *obsolete, cwd=checkout)
    run("git", "add", "--", *names, cwd=checkout)


def publish(package: Path) -> str:
    """Only publish a completed gate for this exact working snapshot."""
    if not shutil.which("gh") or not shutil.which("git"):
        raise RuntimeError("Instale Git e GitHub CLI (gh auth login).")
    validation = validation_asset(package)
    if run("gh", "api", f"repos/{REPOSITORY}", "--jq", ".permissions.push").strip() != "true":
        raise RuntimeError("A conta autenticada não tem permissão para enviar este repositório.")
    output = ROOT / "runtime/publishing"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="source-", dir=output) as folder:
        checkout = Path(folder) / "repository"
        run(
            "git",
            "-c",
            "core.autocrlf=false",
            "clone",
            f"https://github.com/{REPOSITORY}.git",
            str(checkout),
        )
        run("git", "config", "core.autocrlf", "false", cwd=checkout)
        with zipfile.ZipFile(package) as archive:
            manifest = json.loads(archive.read("Editor-do-Escobar/package-manifest.json"))
            names = [*manifest["files"], "package-manifest.json"]
            for name in names:
                target = checkout / name
                if not target.resolve().is_relative_to(checkout.resolve()):
                    raise ValueError("Caminho inseguro no pacote")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read("Editor-do-Escobar/" + name))
        run("git", "config", "user.name", "Pablo Escobar", cwd=checkout)
        run(
            "git",
            "config",
            "user.email",
            "161873772+TruePabloEscobar@users.noreply.github.com",
            cwd=checkout,
        )
        stage_snapshot(checkout, names)
        if run("git", "diff", "--cached", "--name-only", cwd=checkout).strip():
            run(
                "git",
                "commit",
                "-m",
                f"Release EDE {manifest['version']} ({manifest['build']})",
                cwd=checkout,
            )
        # No reset, no forced update, and no mutation of the developer's dirty checkout.
        run("git", "push", "origin", "HEAD:main", cwd=checkout)
        commit = run("git", "rev-parse", "HEAD", cwd=checkout).strip()
        tag = f"v{manifest['version']}-{manifest['build']}"
        notes = output / f"{tag}.md"
        notes.write_text(
            "Editor Do Escobar — EDE\n\n"
            "Plugin via script para DaVinci Resolve Studio 21 / Windows x64.\n"
            "Baixe o ZIP e confira o SHA-256; extraia e execute Instalar EDE.bat.\n"
            "Requer Python 3.11 x64 e FFmpeg no PATH. Dependências são instaladas pela internet.\n"
            "Modelos são baixados somente pelo botão nas configurações; mídia permanece local.\n"
            "Leia docs/DISTRIBUICAO.md para limites e validação.\n"
            "Fontes e testes sintéticos; sem dados de produção ou relatórios internos.\n",
            encoding="utf-8",
        )
        existing = subprocess.run(
            ["gh", "release", "view", tag, "--repo", REPOSITORY, "--json", "url"],
            capture_output=True,
            text=True,
            check=False,
        )
        if existing.returncode == 0:
            raise RuntimeError(
                "Esta release ja existe; confira os assets no GitHub antes de repetir."
            )
        return run(
            "gh",
            "release",
            "create",
            tag,
            str(package),
            str(package.with_suffix(".zip.sha256")),
            str(validation),
            "--repo",
            REPOSITORY,
            "--target",
            commit,
            "--title",
            f"Editor Do Escobar {manifest['version']}",
            "--notes-file",
            str(notes),
        ).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Publicar EDE testado, sem dados locais")
    parser.add_argument("--check", action="store_true", help="Conferir arquivos sem publicar")
    args = parser.parse_args()
    before = public_files(ROOT)
    if args.check:
        print(f"Snapshot publico: {len(before)} arquivos; nenhuma publicacao realizada.")
        return 0
    environment = {**os.environ, "PYTHONUTF8": "1"}
    gate = subprocess.run(
        [sys.executable, "scripts/run_regression.py"], cwd=ROOT, env=environment, check=False
    )
    if gate.returncode:
        print("Publicacao interrompida: o gate de regressao falhou.")
        return 1
    if public_files(ROOT) != before:
        print("Publicacao interrompida: as fontes mudaram durante os testes. Execute novamente.")
        return 1
    package = package_release(ROOT, ROOT / "dist", public=True)
    print(publish(package))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
