from __future__ import annotations

import re
from pathlib import Path

from o_editor.__main__ import main
from o_editor.self_test import SelfTestCheck


def test_self_test_cli(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "o_editor.self_test.run_self_test",
        lambda _root, include_resolve: (
            SelfTestCheck("mock", "PASSED", f"resolve={include_resolve}"),
        ),
    )
    assert main(["--self-test"]) == 0
    assert "Self-test: PASSED" in capsys.readouterr().out


def test_resolve_flag_requires_self_test(capsys) -> None:
    assert main(["--resolve"]) == 1
    assert "--resolve só pode" in capsys.readouterr().out


def test_double_click_files_are_self_locating() -> None:
    root = Path.cwd()
    for name in (
        "O Editor.cmd",
        "O Editor - Mock.cmd",
        "O Editor - Validar.cmd",
        "O Editor - Instalar no DaVinci.cmd",
        "O Editor - Preparar e Testar.cmd",
    ):
        text = (root / name).read_text(encoding="utf-8")
        assert "%~dp0" in text


def test_internal_lua_launchers_are_safe_and_complete() -> None:
    root = Path.cwd() / "launcher"
    expected = (
        "O Editor - Teste de Menu.lua",
        "O Editor - Diagnóstico.lua",
        "O Editor - Abrir.lua",
        "O Editor - Capability Probe.lua",
        "O Editor - Aplicar Plano.lua",
        "O Editor - Aplicar Rough Cut.lua",
    )
    for name in expected:
        path = root / name
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        lowered = text.casefold()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert "fusionscript.dll" not in lowered
        assert "davinciresolvescript" not in lowered
        assert "scriptapp" not in lowered
        assert "pyside6" not in lowered
        assert "faster_whisper" not in lowered
        assert "ctranslate2" not in lowered
        assert "SCRIPT_VERSION" in text
        assert "BUILD_HASH" in text
        assert "xpcall" in text
        assert "run_internal_action" in text
        assert "common.script_path(2)" in text
        assert "common.script_path(1)" not in text
    assert not (root / "O Editor.py").exists()
    assert (root / "legacy" / "O Editor.py").exists()
    assert "menu_test" in (root / expected[0]).read_text(encoding="utf-8")
    assert "--internal-action-request" in (root / "internal_common.lua").read_text(encoding="utf-8")
    capability_text = (root / "O Editor - Capability Probe.lua").read_text(encoding="utf-8")
    apply_text = (root / "O Editor - Aplicar Plano.lua").read_text(encoding="utf-8")
    common_text = (root / "internal_common.lua").read_text(encoding="utf-8")
    script_versions = {
        re.search(r'local SCRIPT_VERSION = "([^"]+)"', (root / name).read_text("utf-8"))[1]
        for name in expected
    }
    build_hashes = {
        re.search(r'local BUILD_HASH = "([^"]+)"', (root / name).read_text("utf-8"))[1]
        for name in expected
    }
    assert script_versions == {"2.4.0"}
    assert build_hashes == {"microphone-clip-state-20261019"}
    assert 'M.COMMON_VERSION = "2.4.0"' in common_text
    assert 'M.COMMON_HASH = "microphone-clip-state-20261019"' in common_text
    assert "schema_version = layout and 3 or 2" in common_text
    assert "function M.capture_layout(timeline)" in common_text
    assert "audio_track_count = audio_track_count" in common_text
    assert "audio_tracks = audio_tracks" in common_text
    for documented_method in (
        "GetTrackName",
        "GetTrackSubType",
        "GetIsTrackEnabled",
        "GetIsTrackLocked",
        "GetItemListInTrack",
    ):
        assert documented_method in common_text
    assert "select_multiple_audio_tracks_for_render" in capability_text
    assert "restore_original_track_state" in capability_text
    assert "ipairs(items)" in capability_text
    assert " in pairs(items)" not in capability_text
    diagnostic_text = (root / "O Editor - Diagnóstico.lua").read_text(encoding="utf-8")
    assert "ipairs(items)" in diagnostic_text
    assert " in pairs(items)" not in diagnostic_text
    assert "READ_ONLY" in capability_text
    assert "internal-capabilities.json" in capability_text
    assert "common.write_json(capability_path" in capability_text
    assert "schema_version == 1" in apply_text
    assert "mutations_executed == false" in apply_text
    assert "capabilities.script_version == SCRIPT_VERSION" in apply_text
    assert "capabilities.project == runtime.context.project_name" in apply_text
    assert "duplicação segura da timeline ainda não foi validada" in apply_text


def test_single_public_entry_opens_current_app_and_dispatches_only_explicit_requests() -> None:
    text = (Path.cwd() / "launcher/O EDITOR.lua").read_text("utf-8")
    assert 'common.run_internal_action("open"' in text
    assert "common.dispatch_menu_action(base)" in text
    assert "capture_layout = true" in text
    assert "DaVinciResolveScript" not in text
    assert "fusionscript.dll" not in text
