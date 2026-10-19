"""Reproducible source-plugin ZIP; excludes local media, sessions and environments."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREES = (
    "src",
    "config",
    "launcher",
    "scripts",
    "tests",
    "docs",
    "qa",
    "leis",
    ".github",
    "requirements",
)
ROOT_FILES = (
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "pyproject.toml",
    "AGENTS.md",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    "Instalar EDE.bat",
    "Publicar EDE no GitHub.bat",
    "Preparar pacote EDE.bat",
    "O Editor.cmd",
    "O Editor - Mock.cmd",
    "O Editor - Testes.cmd",
    "O Editor - Validar.cmd",
    "O Editor - Instalar no DaVinci.cmd",
    "O Editor - Preparar e Testar.cmd",
)
SUFFIXES = {".py", ".ps1", ".lua", ".json", ".md", ".svg", ".js", ".yml", ".yaml", ".txt"}
EXCLUDED = {"__pycache__", ".pytest_cache", "node_modules", ".venv", "runtime", ".git"}


def release_files(root: Path) -> dict[str, bytes]:
    """Explicit roots and extensions prevent accidentally shipping private runtime data."""
    paths = [root / name for name in ROOT_FILES if (root / name).is_file()]
    for name in TREES:
        base = root / name
        if base.is_dir():
            paths.extend(
                p
                for p in base.rglob("*")
                if p.is_file()
                and p.suffix in SUFFIXES
                and not EXCLUDED.intersection(p.relative_to(root).parts)
                and not any(part.endswith(".egg-info") for part in p.relative_to(root).parts)
            )
    result = {}
    for path in sorted(paths):
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Arquivo fora da origem: {path}")
        result[path.relative_to(root).as_posix()] = path.read_bytes()
    required = {
        "pyproject.toml",
        "config/defaults.json",
        "src/o_editor/__main__.py",
        "launcher/O EDITOR.lua",
        "scripts/install_release.ps1",
        "Instalar EDE.bat",
    }
    if not required.issubset(result):
        raise ValueError(f"Pacote incompleto: {required - result.keys()}")
    return result


def package_release(root: Path, output: Path) -> Path:
    files = release_files(root)
    version = re.search(r'^version = "([^"]+)"', files["pyproject.toml"].decode(), re.M)
    if version is None:
        raise ValueError("Versão ausente")
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    identity = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    manifest = {"format": 1, "version": version[1], "build": identity[:12], "files": hashes}
    files["package-manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"Editor-do-Escobar-{version[1]}-{identity[:12]}-Windows.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo("Editor-do-Escobar/" + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix(".zip.sha256").write_text(f"{checksum}  {target.name}\n", encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Preparar plugin EDE para distribuição Windows")
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    print(package_release(ROOT, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
