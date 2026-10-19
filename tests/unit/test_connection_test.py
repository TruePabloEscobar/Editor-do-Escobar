from __future__ import annotations

from pathlib import Path

from o_editor.errors import ResolveUnavailableError
from o_editor.infrastructure.resolve.connection_test import (
    EXIT_CONNECTION,
    EXIT_NO_PROJECT,
    EXIT_NO_TIMELINE,
    EXIT_SUCCESS,
    run_connection_test,
    write_connection_report,
)
from o_editor.infrastructure.resolve.loader import LoadedResolveApi, ResolveApiDiscovery


class FakeTimeline:
    def GetName(self):
        return "Timeline Teste"


class FakeProject:
    def __init__(self, timeline=True):
        self._timeline = timeline

    def GetName(self):
        return "Projeto Teste"

    def GetCurrentTimeline(self):
        return FakeTimeline() if self._timeline else None


class FakeManager:
    def __init__(self, project=True, timeline=True):
        self._project = project
        self._timeline = timeline

    def GetCurrentProject(self):
        return FakeProject(self._timeline) if self._project else None


class FakeResolve:
    def __init__(self, project=True, timeline=True):
        self._project = project
        self._timeline = timeline

    def GetVersionString(self):
        return "21.0"

    def GetProjectManager(self):
        return FakeManager(self._project, self._timeline)


def _install_fake_loader(monkeypatch, tmp_path: Path, *, project=True, timeline=True) -> None:
    module = tmp_path / "DaVinciResolveScript.py"
    library = tmp_path / "fusionscript.dll"
    module.write_text("# mock", encoding="utf-8")
    library.write_bytes(b"mock")
    discovery = ResolveApiDiscovery(
        module_path=module,
        library_path=library,
        documentation_path=None,
        searched_module_paths=(module,),
        searched_library_paths=(library,),
        diagnostics=(),
    )
    loaded = LoadedResolveApi(
        module=object(),  # type: ignore[arg-type]
        resolve=FakeResolve(project=project, timeline=timeline),
        discovery=discovery,
    )
    monkeypatch.setattr(
        "o_editor.infrastructure.resolve.connection_test.discover_resolve_api",
        lambda **_kwargs: discovery,
    )
    monkeypatch.setattr(
        "o_editor.infrastructure.resolve.connection_test.load_resolve_api",
        lambda **_kwargs: loaded,
    )


def test_connection_reports_closed_resolve() -> None:
    report = run_connection_test(Path.cwd(), process_checker=lambda: False)
    assert report.exit_code == EXIT_CONNECTION
    assert report.checks[-1].name == "resolve_process"


def test_connection_distinguishes_project_and_timeline(monkeypatch, tmp_path) -> None:
    _install_fake_loader(monkeypatch, tmp_path, project=False)
    no_project = run_connection_test(Path.cwd(), process_checker=lambda: True)
    assert no_project.exit_code == EXIT_NO_PROJECT

    _install_fake_loader(monkeypatch, tmp_path, timeline=False)
    no_timeline = run_connection_test(Path.cwd(), process_checker=lambda: True)
    assert no_timeline.exit_code == EXIT_NO_TIMELINE


def test_connection_success_writes_reports(monkeypatch, tmp_path) -> None:
    _install_fake_loader(monkeypatch, tmp_path)
    report = run_connection_test(Path.cwd(), process_checker=lambda: True)
    assert report.exit_code == EXIT_SUCCESS
    json_path = tmp_path / "relatórios" / "connection.json"
    markdown_path = tmp_path / "relatórios" / "connection.md"
    write_connection_report(report, json_path, markdown_path)
    assert '"status": "PASSED"' in json_path.read_text(encoding="utf-8")
    assert "Timeline Teste" in markdown_path.read_text(encoding="utf-8")


def test_connection_distinguishes_missing_dll(monkeypatch, tmp_path) -> None:
    module = tmp_path / "DaVinciResolveScript.py"
    module.write_text("# mock", encoding="utf-8")
    discovery = ResolveApiDiscovery(
        module_path=module,
        library_path=None,
        documentation_path=None,
        searched_module_paths=(module,),
        searched_library_paths=(),
        diagnostics=(),
    )
    monkeypatch.setattr(
        "o_editor.infrastructure.resolve.connection_test.discover_resolve_api",
        lambda **_kwargs: discovery,
    )
    report = run_connection_test(Path.cwd(), process_checker=lambda: True)
    assert report.exit_code == EXIT_CONNECTION
    assert report.checks[-1].name == "resolve_library"


def test_connection_distinguishes_bridge_load_and_scriptapp_none(
    monkeypatch,
    tmp_path,
) -> None:
    _install_fake_loader(monkeypatch, tmp_path)

    def fail_with(message: str):
        def failure(**_kwargs):
            raise ResolveUnavailableError(message)

        return failure

    monkeypatch.setattr(
        "o_editor.infrastructure.resolve.connection_test.load_resolve_api",
        fail_with("Falha ao carregar a biblioteca de scripting."),
    )
    library_failure = run_connection_test(Path.cwd(), process_checker=lambda: True)
    assert library_failure.checks[-1].name == "resolve_library_load"

    monkeypatch.setattr(
        "o_editor.infrastructure.resolve.connection_test.load_resolve_api",
        fail_with("DaVinci Resolve não respondeu; scriptapp retornou None."),
    )
    scriptapp_none = run_connection_test(Path.cwd(), process_checker=lambda: True)
    assert scriptapp_none.checks[-1].name == "scriptapp"
