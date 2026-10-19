from __future__ import annotations

from o_editor.infrastructure.resolve.loader import discover_resolve_api


def test_loader_prefers_configured_paths(monkeypatch, tmp_path) -> None:
    root = tmp_path / "api"
    module_dir = root / "Modules"
    module_dir.mkdir(parents=True)
    module = module_dir / "DaVinciResolveScript.py"
    module.write_text("def scriptapp(name): return object()\n", encoding="utf-8")
    library = tmp_path / "fusionscript.dll"
    library.write_bytes(b"mock")
    monkeypatch.delenv("RESOLVE_SCRIPT_API", raising=False)
    monkeypatch.delenv("RESOLVE_SCRIPT_LIB", raising=False)
    result = discover_resolve_api(
        configured_api_paths=(str(root),),
        configured_library_paths=(str(library),),
    )
    assert result.module_path == module
    assert result.library_path == library


def test_loader_respects_environment(monkeypatch, tmp_path) -> None:
    root = tmp_path / "api"
    root.mkdir()
    module = root / "DaVinciResolveScript.py"
    module.write_text("def scriptapp(name): return object()\n", encoding="utf-8")
    monkeypatch.setenv("RESOLVE_SCRIPT_API", str(root))
    result = discover_resolve_api()
    assert result.module_path == module
    assert any(path == module for path in result.searched_module_paths)


def test_loader_reports_missing_module(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("RESOLVE_SCRIPT_API", str(tmp_path / "missing"))
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "programdata"))
    result = discover_resolve_api()
    assert result.module_path is None
    assert any("não encontrado" in item for item in result.diagnostics)


def test_loader_uses_native_module_exposed_by_official_wrapper(monkeypatch, tmp_path):
    import sys

    from o_editor.infrastructure.resolve.loader import _load_module

    monkeypatch.delitem(sys.modules, "_o_editor_davinci_resolve_script", raising=False)
    module = tmp_path / "DaVinciResolveScript.py"
    module.write_text(
        "from types import ModuleType\n"
        "script_module = ModuleType('fake_native')\n"
        "script_module.scriptapp = lambda name: name\n",
        encoding="utf-8",
    )
    loaded = _load_module(module)
    try:
        assert loaded.scriptapp("Fusion") == "Fusion"
        assert _load_module(module) is loaded
    finally:
        sys.modules.pop("_o_editor_davinci_resolve_script", None)
