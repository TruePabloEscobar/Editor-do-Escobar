"""Application self-test without editorial mutations."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from o_editor.application.analyze_timeline import analyze_with_mock
from o_editor.infrastructure.cache import JsonCache
from o_editor.infrastructure.config import load_config
from o_editor.infrastructure.resolve.connection_test import (
    EXIT_SUCCESS,
)
from o_editor.infrastructure.resolve.connection_test import (
    main as connection_test_main,
)


@dataclass(frozen=True, slots=True)
class SelfTestCheck:
    name: str
    status: str
    detail: str


def run_self_test(root: Path, *, include_resolve: bool = False) -> tuple[SelfTestCheck, ...]:
    checks: list[SelfTestCheck] = []
    config = load_config(root / "config" / "defaults.json")
    checks.append(SelfTestCheck("config", "PASSED", config.schema_version))

    with tempfile.TemporaryDirectory(prefix="o-editor-self-test-") as temporary:
        temp_root = Path(temporary)
        cache = JsonCache(temp_root / "cache")
        key = cache.make_key("self-test")
        cache.save("checks", key, {"ok": True})
        if cache.load("checks", key) != {"ok": True}:
            raise RuntimeError("O cache não confirmou a leitura após a escrita.")
        checks.append(SelfTestCheck("cache_write", "PASSED", "leitura confirmada"))

        result = analyze_with_mock(config, temp_root / "runtime")
        if not result.suggestions:
            raise RuntimeError("O fluxo mock não gerou sugestões.")
        checks.append(SelfTestCheck("mock", "PASSED", f"{len(result.suggestions)} sugestões"))

    from o_editor.ui.qt_runtime import configure_headless_qt_environment

    configure_headless_qt_environment()
    from PySide6.QtWidgets import QApplication

    from o_editor.ui.internal_action_runtime import InternalActionMainWindow

    app = QApplication.instance() or QApplication([])
    window = InternalActionMainWindow(config=config, root=root, use_mock=True)
    title = window.windowTitle()
    window.close()
    app.processEvents()
    if title != "Editor Do Escobar — EDE":
        raise RuntimeError("A interface básica não foi criada corretamente.")
    checks.append(SelfTestCheck("ui", "PASSED", "janela básica criada e fechada"))

    from o_editor.internal_actions.ipc import IPC_MESSAGE_TYPES, server_name

    if "internal_action_request" not in IPC_MESSAGE_TYPES or not server_name(root):
        raise RuntimeError("O contrato de IPC local não foi carregado.")
    checks.append(SelfTestCheck("internal_actions_ipc", "PASSED", "contrato local carregado"))

    if include_resolve:
        exit_code = connection_test_main(["--root", str(root)])
        report_path = root / "runtime" / "reports" / "resolve_connection_test.json"
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            report = {}
        status = "PASSED" if exit_code == EXIT_SUCCESS else "FAILED"
        checks.append(
            SelfTestCheck(
                "resolve_read_only",
                status,
                f"exit_code={exit_code}; projeto={report.get('project_name') or 'ausente'}; "
                f"timeline={report.get('timeline_name') or 'ausente'}",
            )
        )
    return tuple(checks)
