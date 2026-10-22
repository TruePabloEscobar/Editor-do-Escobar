"""Requested 2026-10-22: fixed, centred credit with link at the bottom of the window."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from o_editor.infrastructure.config import load_config
from o_editor.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[2]
URL = "https://pabloescobardj.web.app/Wikipedia-Pablo-Escobar.html"


@pytest.mark.parametrize("size", [(1000, 680), (1280, 820)])
def test_credit_is_fixed_centred_and_linked_on_every_step(tmp_path: Path, size) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(
        config=load_config(ROOT / "config/defaults.json"), root=tmp_path, use_mock=True
    )
    window.show()
    window.resize(*size)
    credit = window._credit_label
    assert "Desenvolvido por:" in credit.text()
    assert f'href="{URL}">Pablo Escobar</a>' in credit.text()
    assert credit.openExternalLinks()
    assert credit.alignment() & Qt.AlignmentFlag.AlignHCenter
    for step in range(len(window._workflow_buttons)):
        window._navigate(step)
        app.processEvents()
        assert credit.isVisible()
        assert not window._workspace.isAncestorOf(credit)
        top = credit.mapTo(window, credit.rect().topLeft()).y()
        workspace_bottom = window._workspace.mapTo(
            window, window._workspace.rect().bottomLeft()
        ).y()
        assert top > workspace_bottom
        centre = credit.mapTo(window, credit.rect().center()).x()
        assert abs(centre - window.width() / 2) <= 2
    window.close()
    app.processEvents()
