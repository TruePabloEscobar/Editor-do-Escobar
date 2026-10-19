from __future__ import annotations

import subprocess
from pathlib import Path

from o_editor.domain.enums import CapabilityStatus
from o_editor.infrastructure.resolve.capabilities import (
    EXIT_CAPABILITY_FAILED,
    EXIT_NO_PROJECT,
    EXIT_NO_TIMELINE,
    CapabilityProbe,
    ProbeReport,
    determine_exit_code,
    main,
    write_probe_report,
)
from o_editor.infrastructure.resolve.loader import LoadedResolveApi, ResolveApiDiscovery


class FakeItem:
    def GetProperty(self):
        return {"ZoomX": 1.0}


class FakeTimeline:
    def GetName(self):
        return "Timeline Teste"

    def GetTrackCount(self, track_type):
        return 1

    def GetItemListInTrack(self, track_type, index):
        return [FakeItem()]

    def GetMarkers(self):
        return {}


class FakeProject:
    def GetName(self):
        return "Projeto Teste"

    def GetCurrentTimeline(self):
        return FakeTimeline()


class FakeProjectManager:
    def GetCurrentProject(self):
        return FakeProject()


class FakeResolve:
    def GetProjectManager(self):
        return FakeProjectManager()

    def GetVersionString(self):
        return "21.0.0.1"

    def GetProductName(self):
        return "DaVinci Resolve Studio"


def _loaded(tmp_path: Path) -> LoadedResolveApi:
    discovery = ResolveApiDiscovery(
        module_path=tmp_path / "DaVinciResolveScript.py",
        library_path=tmp_path / "fusionscript.dll",
        documentation_path=tmp_path / "README.txt",
        searched_module_paths=(),
        searched_library_paths=(),
        diagnostics=(),
    )
    return LoadedResolveApi(module=object(), resolve=FakeResolve(), discovery=discovery)  # type: ignore[arg-type]


def test_read_only_probe_does_not_claim_mutations(tmp_path) -> None:
    report = CapabilityProbe(_loaded(tmp_path), allow_mutations=False).run()
    statuses = {result.name: result.status for result in report.results}
    assert statuses["connect"] is CapabilityStatus.SUPPORTED
    assert statuses["active_project"] is CapabilityStatus.SUPPORTED
    assert statuses["create_marker"] is CapabilityStatus.UNVERIFIED
    assert statuses["duplicate_timeline"] is CapabilityStatus.UNVERIFIED
    assert statuses["position_fusion_title"] is CapabilityStatus.UNSUPPORTED


def test_probe_writes_json_and_markdown(tmp_path) -> None:
    report = CapabilityProbe(_loaded(tmp_path), allow_mutations=False).run()
    json_path = tmp_path / "runtime" / "resolve_capabilities.json"
    markdown_path = tmp_path / "docs" / "RESOLVE_CAPABILITY_REPORT.md"
    write_probe_report(report, json_path, markdown_path)
    assert '"status": "SUPPORTED"' in json_path.read_text(encoding="utf-8")
    assert "Uma capacidade só aparece" in markdown_path.read_text(encoding="utf-8")


def test_probe_cli_is_observable_and_honors_output_paths(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    report = CapabilityProbe(_loaded(tmp_path), allow_mutations=False).run()
    monkeypatch.setattr(
        "o_editor.infrastructure.resolve.capabilities.run_probe",
        lambda **_kwargs: report,
    )
    json_path = tmp_path / "saída com espaço" / "probe.json"
    markdown_path = tmp_path / "saída com espaço" / "probe.md"
    exit_code = main(
        [
            "--root",
            str(tmp_path),
            "--read-only",
            "--json-output",
            str(json_path),
            "--markdown-output",
            str(markdown_path),
            "--no-color",
            "--worker",
        ]
    )
    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Python:" in output
    assert "SUPPORTED=" in output
    assert "Exit code: 0" in output
    assert json_path.is_file()
    assert markdown_path.is_file()


def test_probe_exit_codes_for_missing_context(tmp_path) -> None:
    base = CapabilityProbe(_loaded(tmp_path), allow_mutations=False).run()

    def with_failed(name: str) -> ProbeReport:
        results = tuple(
            (
                type(result)(
                    name=result.name,
                    status=CapabilityStatus.FAILED,
                    method=result.method,
                    return_value=None,
                    exception="RuntimeError: ausente",
                    notes=result.notes,
                    impact=result.impact,
                    fallback=result.fallback,
                )
                if result.name == name
                else result
            )
            for result in base.results
        )
        return ProbeReport(
            generated_at=base.generated_at,
            resolve_version=base.resolve_version,
            product_name=base.product_name,
            operating_system=base.operating_system,
            python_version=base.python_version,
            documentation_path=base.documentation_path,
            mutation_mode=base.mutation_mode,
            project_name=base.project_name,
            timeline_name=base.timeline_name,
            results=results,
        )

    assert determine_exit_code(with_failed("active_project")) == EXIT_NO_PROJECT
    assert determine_exit_code(with_failed("active_timeline")) == EXIT_NO_TIMELINE
    assert determine_exit_code(with_failed("read_video_items")) == EXIT_CAPABILITY_FAILED


def test_probe_supervisor_reports_native_worker_crash(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    monkeypatch.setattr(
        "o_editor.infrastructure.resolve.capabilities.subprocess.run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=3221225477,
            stdout="worker iniciou\n",
            stderr="",
        ),
    )
    exit_code = main(["--root", str(tmp_path), "--read-only"])
    output = capsys.readouterr().out
    assert exit_code == 2
    assert "Exit code: 2" in output
    assert (tmp_path / "runtime" / "resolve_capabilities.json").is_file()
