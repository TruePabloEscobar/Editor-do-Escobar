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
    "workflow_integration",
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
SUFFIXES = {
    ".py",
    ".ps1",
    ".lua",
    ".json",
    ".md",
    ".svg",
    ".js",
    ".cjs",
    ".yml",
    ".yaml",
    ".txt",
    ".html",
    ".css",
    ".xml",
}
EXCLUDED = {"__pycache__", ".pytest_cache", "node_modules", ".venv", "runtime", ".git"}


PUBLIC_DOCS = {
    "ARCHITECTURE.md",
    "AUTOMATIC_VOICE_EXPORT.md",
    "DISTRIBUICAO.md",
    "EDE_SETTINGS.md",
    "INSTALL_WINDOWS.md",
    "MICROPHONE_CLEANUP.md",
    "REGRESSION_TESTS.md",
    "RESOLVE_INTERNAL_ACTIONS.md",
    "TAKE_ZOOM.md",
    "TRANSCRIPT_ROUGH_CUT.md",
    "TROUBLESHOOTING.md",
    "UI_WORKFLOW.md",
}
PRIVATE_PARTS = {"secrets", "credentials", "sessions", "logs", "reports", "media"}
SECRET_PATTERNS = (
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{30,}"),
    re.compile(rb"AKIA[A-Z0-9]{16}"),
    re.compile(rb"AIza[A-Za-z0-9_-]{35}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(
        rb"(?i)(?:password|api_key|access_token)\s*[:=]\s*[\"'](?![\"'])[A-Za-z0-9_+/=-]{16,}[\"']"
    ),
)


def validate_public_files(files: dict[str, bytes]) -> None:
    """Refuse recognizable credentials without printing their contents."""
    for name, data in files.items():
        if PRIVATE_PARTS.intersection(part.lower() for part in Path(name).parts):
            raise ValueError(f"Caminho privado recusado: {name}")
        if any(pattern.search(data) for pattern in SECRET_PATTERNS):
            raise ValueError(f"Possivel credencial recusada: {name}")


def public_files(root: Path) -> dict[str, bytes]:
    """Software sources and synthetic tests only; never local audits or user settings."""
    selected = {}
    for name, data in release_files(root).items():
        path = Path(name)
        top = path.parts[0]
        allowed = (
            (len(path.parts) == 1 and name not in {"AGENTS.md"})
            or (top == "src" and path.suffix in {".py", ".svg"})
            or (top in {"scripts", "launcher"} and path.suffix in {".py", ".ps1", ".lua"})
            or (top == "tests" and path.suffix in {".py", ".lua", ".cjs"})
            or name == "tests/golden/interview_suggestions.json"
            or name in {"config/defaults.json", "config/styles.example.json"}
            or name == "requirements/runtime-windows.txt"
            or (top == "docs" and path.name in PUBLIC_DOCS and len(path.parts) == 2)
            or top == "workflow_integration"
            or name == ".github/workflows/regression.yml"
        )
        if allowed:
            selected[name] = data
    validate_public_files(selected)
    return selected


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
        "requirements/runtime-windows.txt",
        "tests/js/workflow_host.cjs",
        "workflow_integration/com.oeditor.resolve.internalhost/main.js",
        "workflow_integration/com.oeditor.resolve.internalhost/manifest.xml",
    }
    if not required.issubset(result):
        raise ValueError(f"Pacote incompleto: {required - result.keys()}")
    return result


def package_release(root: Path, output: Path, *, public: bool = False) -> Path:
    files = public_files(root) if public else release_files(root)
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
    parser.add_argument("--public", action="store_true", help="Excluir documentos internos")
    args = parser.parse_args()
    print(package_release(ROOT, args.output, public=args.public))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
