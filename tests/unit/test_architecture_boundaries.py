"""Enforce the project-wide pure-domain boundary mandated by the specification."""

from __future__ import annotations

import ast
from pathlib import Path


def test_domain_has_no_ui_native_or_media_dependencies():
    domain = Path(__file__).resolve().parents[2] / "src/o_editor/domain"
    forbidden = (
        "PySide6",
        "faster_whisper",
        "ctranslate2",
        "ffmpeg",
        "DaVinciResolveScript",
        "o_editor.infrastructure",
        "o_editor.ui",
        "o_editor.application",
    )
    violations = []
    for path in domain.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else ([node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            )
            for name in names:
                if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden):
                    violations.append(f"{path.name}:{node.lineno}: {name}")
    assert violations == []
