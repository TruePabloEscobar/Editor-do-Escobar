"""Resolve Capability Probe.

Read-only checks run by default. Mutating checks require both an explicit flag
and an exact project-name confirmation; every temporary object uses OE_PROBE.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from o_editor.domain.enums import CapabilityStatus
from o_editor.domain.models import CapabilityResult
from o_editor.errors import ConfigurationError, OEditorError, ResolveUnavailableError
from o_editor.infrastructure.config import load_config
from o_editor.infrastructure.resolve.loader import (
    LoadedResolveApi,
    discover_resolve_api,
    load_resolve_api,
)

CAPABILITY_NAMES = (
    "connect",
    "active_project",
    "active_timeline",
    "resolve_version",
    "read_video_items",
    "read_audio_items",
    "read_clip_properties",
    "create_marker",
    "delete_marker",
    "add_video_track",
    "rename_track",
    "duplicate_timeline",
    "export_import_timeline",
    "fusion_comp_access",
    "fusion_node_creation",
    "fusion_node_connections",
    "fusion_transform_keyframes",
    "fusion_keyframe_readback",
    "insert_fusion_title",
    "position_fusion_title",
    "set_fusion_title_duration",
    "insert_title_on_named_track",
    "edit_text_plus",
    "verify_title",
    "export_audio",
    "read_write_markers",
    "save_project",
)

EXIT_SUCCESS = 0
EXIT_ARGUMENT = 1
EXIT_CONNECTION = 2
EXIT_NO_PROJECT = 3
EXIT_NO_TIMELINE = 4
EXIT_CAPABILITY_FAILED = 5
EXIT_INTERNAL = 6
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProbeReport:
    generated_at: str
    resolve_version: str | None
    product_name: str | None
    operating_system: str
    python_version: str
    documentation_path: str | None
    mutation_mode: bool
    project_name: str | None
    timeline_name: str | None
    results: tuple[CapabilityResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "generated_at": self.generated_at,
            "resolve_version": self.resolve_version,
            "product_name": self.product_name,
            "operating_system": self.operating_system,
            "python_version": self.python_version,
            "documentation_path": self.documentation_path,
            "mutation_mode": self.mutation_mode,
            "project_name": self.project_name,
            "timeline_name": self.timeline_name,
            "environment": {
                "RESOLVE_SCRIPT_API": _redact_path(os.environ.get("RESOLVE_SCRIPT_API")),
                "RESOLVE_SCRIPT_LIB": _redact_path(os.environ.get("RESOLVE_SCRIPT_LIB")),
                "PYTHONPATH_configured": bool(os.environ.get("PYTHONPATH")),
            },
            "results": [result.to_dict() for result in self.results],
        }


class CapabilityProbe:
    def __init__(self, loaded: LoadedResolveApi, *, allow_mutations: bool = False) -> None:
        self._loaded = loaded
        self._resolve = loaded.resolve
        self._allow_mutations = allow_mutations
        self._results: dict[str, CapabilityResult] = {}
        self._project_manager: Any = None
        self._project: Any = None
        self._timeline: Any = None

    def run(self) -> ProbeReport:
        self._supported("connect", "DaVinciResolveScript.scriptapp", True)
        self._run_read("active_project", "GetProjectManager/GetCurrentProject", self._read_project)
        self._run_read("active_timeline", "Project.GetCurrentTimeline", self._read_timeline)
        self._run_read("resolve_version", "Resolve.GetVersionString", self._read_version)
        self._run_read("read_video_items", "Timeline.GetItemListInTrack", self._read_video_items)
        self._run_read("read_audio_items", "Timeline.GetItemListInTrack", self._read_audio_items)
        self._run_read(
            "read_clip_properties",
            "TimelineItem.GetProperty",
            self._read_clip_properties,
        )
        self._run_read("read_write_markers", "Timeline.GetMarkers", self._read_markers)

        if self._allow_mutations and self._timeline is not None:
            self._probe_marker_lifecycle()
            self._probe_track_lifecycle()
            self._probe_duplicate_lifecycle()
        else:
            self._mark_mutations_unverified()

        self._mark_unverified(
            "export_import_timeline",
            "Timeline.Export/MediaPool.ImportTimelineFromFile",
            "A alternativa DRT é documentada, mas não foi executada.",
            "Fallback de duplicação desabilitado.",
        )
        self._mark_fusion_unverified()
        self._mark_title_limitations()
        self._mark_unverified(
            "export_audio",
            "Project render API",
            "Nenhum render WAV temporário foi executado e verificado.",
            "Seleção manual de WAV.",
        )
        self._mark_unverified(
            "save_project",
            "ProjectManager.SaveProject",
            "Salvar o projeto não é necessário para o probe seguro.",
            "Salvar manualmente após revisão.",
        )
        for name in CAPABILITY_NAMES:
            if name not in self._results:
                self._mark_unverified(name, None, "Não executado.", "Operação desabilitada.")
        return ProbeReport(
            generated_at=datetime.now(UTC).isoformat(),
            resolve_version=self._safe_string(self._resolve, "GetVersionString"),
            product_name=self._safe_string(self._resolve, "GetProductName"),
            operating_system=platform.platform(),
            python_version=sys.version.split()[0],
            documentation_path=(
                str(self._loaded.discovery.documentation_path)
                if self._loaded.discovery.documentation_path
                else None
            ),
            mutation_mode=self._allow_mutations,
            project_name=self._safe_string(self._project, "GetName"),
            timeline_name=self._safe_string(self._timeline, "GetName"),
            results=tuple(self._results[name] for name in CAPABILITY_NAMES),
        )

    def _read_project(self) -> str:
        self._project_manager = self._resolve.GetProjectManager()
        if self._project_manager is None:
            raise RuntimeError("GetProjectManager retornou None")
        self._project = self._project_manager.GetCurrentProject()
        if self._project is None:
            raise RuntimeError("Nenhum projeto ativo")
        return str(self._project.GetName())

    def _read_timeline(self) -> str:
        if self._project is None:
            self._read_project()
        self._timeline = self._project.GetCurrentTimeline()
        if self._timeline is None:
            raise RuntimeError("Nenhuma timeline ativa")
        return str(self._timeline.GetName())

    def _read_version(self) -> str:
        value = self._resolve.GetVersionString()
        if not value:
            raise RuntimeError("GetVersionString retornou vazio")
        return str(value)

    def _read_video_items(self) -> int:
        return self._read_items("video")

    def _read_audio_items(self) -> int:
        return self._read_items("audio")

    def _read_items(self, track_type: str) -> int:
        timeline = self._require_timeline()
        count = int(timeline.GetTrackCount(track_type))
        return sum(
            len(timeline.GetItemListInTrack(track_type, index) or ())
            for index in range(1, count + 1)
        )

    def _read_clip_properties(self) -> int:
        timeline = self._require_timeline()
        for index in range(1, int(timeline.GetTrackCount("video")) + 1):
            items = timeline.GetItemListInTrack("video", index) or ()
            if items:
                properties = items[0].GetProperty()
                if not isinstance(properties, dict):
                    raise RuntimeError("GetProperty não retornou um dicionário")
                return len(properties)
        return 0

    def _read_markers(self) -> int:
        markers = self._require_timeline().GetMarkers()
        if not isinstance(markers, dict):
            raise RuntimeError("GetMarkers não retornou um dicionário")
        return len(markers)

    def _probe_marker_lifecycle(self) -> None:
        timeline = self._require_timeline()
        frame = int(timeline.GetStartFrame())
        custom_data = f"OE_PROBE_{datetime.now(UTC).timestamp()}"
        created = False
        try:
            created = bool(
                timeline.AddMarker(
                    frame,
                    "Blue",
                    "OE_PROBE",
                    "Marcador temporário do capability probe",
                    1,
                    custom_data,
                )
            )
            marker = timeline.GetMarkerByCustomData(custom_data)
            if not created or not marker:
                raise RuntimeError("o marcador não pôde ser verificado")
            self._supported("create_marker", "Timeline.AddMarker/GetMarkerByCustomData", True)
            deleted = bool(timeline.DeleteMarkerByCustomData(custom_data))
            if not deleted or timeline.GetMarkerByCustomData(custom_data):
                raise RuntimeError("o marcador temporário não foi removido")
            self._supported(
                "delete_marker",
                "Timeline.DeleteMarkerByCustomData/GetMarkerByCustomData",
                True,
            )
            self._supported(
                "read_write_markers",
                "Timeline.AddMarker/GetMarkerByCustomData/DeleteMarkerByCustomData",
                True,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._failed("create_marker", "Timeline.AddMarker", exc)
            self._failed("delete_marker", "Timeline.DeleteMarkerByCustomData", exc)
        finally:
            if created:
                try:
                    cleaned = bool(timeline.DeleteMarkerByCustomData(custom_data))
                    if not cleaned and timeline.GetMarkerByCustomData(custom_data):
                        raise RuntimeError("a limpeza final do marcador falhou")
                except (OSError, RuntimeError, TypeError, ValueError) as cleanup_exc:
                    self._failed(
                        "delete_marker",
                        "Timeline.DeleteMarkerByCustomData (cleanup)",
                        cleanup_exc,
                    )

    def _probe_track_lifecycle(self) -> None:
        timeline = self._require_timeline()
        before = int(timeline.GetTrackCount("video"))
        created_index = before + 1
        try:
            if not timeline.AddTrack("video"):
                raise RuntimeError("AddTrack retornou False")
            after = int(timeline.GetTrackCount("video"))
            if after != created_index:
                raise RuntimeError("a nova track não foi confirmada")
            self._supported("add_video_track", "Timeline.AddTrack/GetTrackCount", after)
            if not timeline.SetTrackName("video", created_index, "OE_PROBE"):
                raise RuntimeError("SetTrackName retornou False")
            if str(timeline.GetTrackName("video", created_index)) != "OE_PROBE":
                raise RuntimeError("o nome da track não foi confirmado")
            self._supported(
                "rename_track",
                "Timeline.SetTrackName/GetTrackName",
                "OE_PROBE",
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._failed("add_video_track", "Timeline.AddTrack", exc)
            self._failed("rename_track", "Timeline.SetTrackName", exc)
        finally:
            try:
                if int(timeline.GetTrackCount("video")) > before and not timeline.DeleteTrack(
                    "video", created_index
                ):
                    raise RuntimeError("DeleteTrack retornou False durante a limpeza")
                if int(timeline.GetTrackCount("video")) != before:
                    raise RuntimeError("a quantidade de tracks não foi restaurada")
            except (OSError, RuntimeError, TypeError, ValueError) as cleanup_exc:
                self._failed(
                    "add_video_track",
                    "Timeline.DeleteTrack (cleanup)",
                    cleanup_exc,
                )

    def _probe_duplicate_lifecycle(self) -> None:
        timeline = self._require_timeline()
        project = self._project
        target_name = f"OE_PROBE_{datetime.now(UTC).strftime('%H%M%S%f')}"
        duplicate: Any = None
        try:
            duplicate = timeline.DuplicateTimeline(target_name)
            if duplicate is None or str(duplicate.GetName()) != target_name:
                raise RuntimeError("DuplicateTimeline não retornou a cópia esperada")
            names = {
                str(project.GetTimelineByIndex(index).GetName())
                for index in range(1, int(project.GetTimelineCount()) + 1)
            }
            if str(timeline.GetName()) not in names or target_name not in names:
                raise RuntimeError("original e cópia não foram confirmadas")
            self._supported(
                "duplicate_timeline",
                "Timeline.DuplicateTimeline/Project.GetTimelineByIndex",
                target_name,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._failed("duplicate_timeline", "Timeline.DuplicateTimeline", exc)
        finally:
            if duplicate is not None:
                try:
                    if not project.SetCurrentTimeline(timeline):
                        raise RuntimeError("a timeline original não pôde ser reativada")
                    if not project.GetMediaPool().DeleteTimelines([duplicate]):
                        raise RuntimeError("a timeline OE_PROBE não pôde ser removida")
                except (OSError, RuntimeError, TypeError, ValueError) as cleanup_exc:
                    self._failed(
                        "duplicate_timeline",
                        "MediaPool.DeleteTimelines (cleanup)",
                        cleanup_exc,
                    )

    def _mark_mutations_unverified(self) -> None:
        for name, method in (
            ("create_marker", "Timeline.AddMarker"),
            ("delete_marker", "Timeline.DeleteMarkerByCustomData"),
            ("add_video_track", "Timeline.AddTrack"),
            ("rename_track", "Timeline.SetTrackName"),
            ("duplicate_timeline", "Timeline.DuplicateTimeline"),
        ):
            self._mark_unverified(
                name,
                method,
                "Modo somente leitura: a operação não foi executada.",
                "Backend correspondente desabilitado.",
            )

    def _mark_fusion_unverified(self) -> None:
        methods = {
            "fusion_comp_access": "TimelineItem.AddFusionComp/GetFusionCompCount",
            "fusion_node_creation": None,
            "fusion_node_connections": None,
            "fusion_transform_keyframes": None,
            "fusion_keyframe_readback": None,
        }
        for name, method in methods.items():
            self._mark_unverified(
                name,
                method,
                "O README instalado não comprova sozinho nodes, conexões e keyframes.",
                "Zoom automático desabilitado; exportar plano/markers.",
            )

    def _mark_title_limitations(self) -> None:
        self._mark_unverified(
            "insert_fusion_title",
            "Timeline.InsertFusionTitleIntoTimeline",
            "Método documentado, mas não executado no probe seguro.",
            "Exportar plano de texto.",
        )
        for name, note in (
            (
                "position_fusion_title",
                "A API documentada insere no playhead, sem prova de posicionamento verificável.",
            ),
            (
                "set_fusion_title_duration",
                "Não há assinatura de duração confirmada no README instalado.",
            ),
            (
                "insert_title_on_named_track",
                "Não há seleção documentada e confiável de track por nome para inserção.",
            ),
            ("edit_text_plus", "A edição Text+ exige API Fusion ainda não comprovada."),
            ("verify_title", "Posição, duração e texto não foram lidos após inserção."),
        ):
            self._unsupported(name, None, note, "Exportar plano; AlphaTitle desabilitado.")

    def _run_read(self, name: str, method: str, operation: Callable[[], Any]) -> None:
        try:
            value = operation()
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._failed(name, method, exc)
        else:
            self._supported(name, method, _safe_json_value(value))

    def _supported(self, name: str, method: str, value: Any) -> None:
        self._results[name] = CapabilityResult(
            name=name,
            status=CapabilityStatus.SUPPORTED,
            method=method,
            return_value=_safe_json_value(value),
            exception=None,
            notes="Operação executada e retorno verificado.",
            impact="Capacidade disponível para o gate correspondente.",
            fallback="Nenhum.",
        )

    def _failed(self, name: str, method: str, exc: Exception) -> None:
        self._results[name] = CapabilityResult(
            name=name,
            status=CapabilityStatus.FAILED,
            method=method,
            return_value=None,
            exception=f"{type(exc).__name__}: {exc}",
            notes="A operação foi executada, mas falhou.",
            impact="Backend correspondente desabilitado.",
            fallback="Fluxo offline/dry-run.",
        )

    def _unsupported(
        self,
        name: str,
        method: str | None,
        notes: str,
        fallback: str,
    ) -> None:
        self._results[name] = CapabilityResult(
            name=name,
            status=CapabilityStatus.UNSUPPORTED,
            method=method,
            return_value=None,
            exception=None,
            notes=notes,
            impact="Backend correspondente desabilitado.",
            fallback=fallback,
        )

    def _mark_unverified(
        self,
        name: str,
        method: str | None,
        notes: str,
        fallback: str,
    ) -> None:
        if name in self._results:
            return
        self._results[name] = CapabilityResult(
            name=name,
            status=CapabilityStatus.UNVERIFIED,
            method=method,
            return_value=None,
            exception=None,
            notes=notes,
            impact="Não pode habilitar o backend correspondente.",
            fallback=fallback,
        )

    def _require_timeline(self) -> Any:
        if self._timeline is None:
            self._read_timeline()
        return self._timeline

    @staticmethod
    def _safe_string(target: Any, method_name: str) -> str | None:
        if target is None:
            return None
        method = getattr(target, method_name, None)
        if not callable(method):
            return None
        try:
            value = method()
        except (OSError, RuntimeError, TypeError, ValueError):
            return None
        return str(value) if value else None


def run_probe(
    *,
    root: Path,
    allow_mutations: bool = False,
    confirmed_project_name: str | None = None,
) -> ProbeReport:
    config = load_config(root / "config" / "defaults.json")
    loaded = load_resolve_api(
        configured_api_paths=config.resolve.api_paths,
        configured_library_paths=config.resolve.library_paths,
        configured_documentation_paths=config.resolve.documentation_paths,
    )
    if allow_mutations:
        project_manager = loaded.resolve.GetProjectManager()
        project = project_manager.GetCurrentProject() if project_manager else None
        actual_name = str(project.GetName()) if project else None
        if not confirmed_project_name or confirmed_project_name != actual_name:
            raise ResolveUnavailableError(
                "Para testes temporários, informe --confirm-project-name exatamente igual "
                f"ao projeto ativo ({actual_name!r})."
            )
    return CapabilityProbe(loaded, allow_mutations=allow_mutations).run()


def write_probe_report(report: ProbeReport, json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(report), encoding="utf-8")


def failed_probe_report(error: OEditorError) -> ProbeReport:
    discovery = discover_resolve_api()
    results = [
        CapabilityResult(
            name="connect",
            status=CapabilityStatus.FAILED,
            method="DaVinciResolveScript.scriptapp",
            return_value=None,
            exception=f"{type(error).__name__}: {error}",
            notes="A API não pôde ser carregada ou conectada.",
            impact="Todas as capacidades reais permanecem desabilitadas.",
            fallback="Fluxo offline/mock e seleção manual de WAV.",
        )
    ]
    results.extend(
        CapabilityResult(
            name=name,
            status=CapabilityStatus.UNVERIFIED,
            method=None,
            return_value=None,
            exception=None,
            notes="Não executado porque a conexão falhou.",
            impact="Backend correspondente desabilitado.",
            fallback="Fluxo offline/dry-run.",
        )
        for name in CAPABILITY_NAMES
        if name != "connect"
    )
    return ProbeReport(
        generated_at=datetime.now(UTC).isoformat(),
        resolve_version=None,
        product_name=None,
        operating_system=platform.platform(),
        python_version=sys.version.split()[0],
        documentation_path=(
            str(discovery.documentation_path) if discovery.documentation_path else None
        ),
        mutation_mode=False,
        project_name=None,
        timeline_name=None,
        results=tuple(results),
    )


def _render_markdown(report: ProbeReport) -> str:
    lines = [
        "# Relatório de capacidades do DaVinci Resolve",
        "",
        f"- Gerado em: `{report.generated_at}`",
        f"- Resolve: `{report.resolve_version or 'não disponível'}`",
        f"- Produto: `{report.product_name or 'não disponível'}`",
        f"- Projeto: `{report.project_name or 'não disponível'}`",
        f"- Timeline: `{report.timeline_name or 'não disponível'}`",
        f"- Sistema: `{report.operating_system}`",
        f"- Python: `{report.python_version}`",
        f"- Modo com mutações temporárias: `{report.mutation_mode}`",
        f"- Documentação local: `{report.documentation_path or 'não encontrada'}`",
        "",
        "| Capacidade | Estado | Método executado/encontrado | Impacto | Fallback |",
        "|---|---|---|---|---|",
    ]
    for result in report.results:
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(value)
                for value in (
                    result.name,
                    result.status.value,
                    result.method or "—",
                    result.impact,
                    result.fallback,
                )
            )
            + " |"
        )
    lines.extend(
        (
            "",
            "## Observações",
            "",
            "Uma capacidade só aparece como `SUPPORTED` quando foi executada e verificada. "
            "A presença de um método por introspecção não é tratada como prova.",
            "",
        )
    )
    return "\n".join(lines)


def _safe_json_value(value: Any) -> str | int | float | bool | None:
    return value if value is None or isinstance(value, str | int | float | bool) else repr(value)


def _redact_path(value: str | None) -> str | None:
    return Path(value).name if value else None


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capability probe seguro do DaVinci Resolve")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--read-only",
        action="store_true",
        help="executar somente leituras (padrão)",
    )
    mode.add_argument(
        "--allow-temporary-mutations",
        action="store_true",
        help="permitir recursos temporários OE_PROBE com limpeza",
    )
    parser.add_argument(
        "--confirm-project-name",
        help="nome exato do projeto ativo exigido para mutações temporárias",
    )
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    print("O Editor — Resolve Capability Probe", flush=True)
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return EXIT_SUCCESS if exc.code == 0 else EXIT_ARGUMENT

    del args.no_color  # A saída é sempre texto simples e adequada para logs.
    root = args.root.resolve()
    _configure_logging(root, verbose=args.verbose)
    json_path = (
        args.json_output.resolve()
        if args.json_output
        else root / "runtime" / "resolve_capabilities.json"
    )
    markdown_path = (
        args.markdown_output.resolve()
        if args.markdown_output
        else root / "docs" / "RESOLVE_CAPABILITY_REPORT.md"
    )
    if not args.worker:
        return _run_isolated(args, root, json_path, markdown_path)
    report: ProbeReport
    exit_code = EXIT_SUCCESS
    try:
        LOGGER.info(
            "Iniciando probe em modo %s.",
            "mutação temporária" if args.allow_temporary_mutations else "somente leitura",
        )
        report = run_probe(
            root=root,
            allow_mutations=args.allow_temporary_mutations,
            confirmed_project_name=args.confirm_project_name,
        )
        exit_code = determine_exit_code(report)
    except ConfigurationError as exc:
        LOGGER.error("Configuração inválida: %s", exc)
        report = failed_probe_report(exc)
        exit_code = EXIT_ARGUMENT
    except ResolveUnavailableError as exc:
        LOGGER.error("Conexão indisponível: %s", exc)
        report = failed_probe_report(exc)
        exit_code = EXIT_CONNECTION
    except OEditorError as exc:
        LOGGER.error("Falha controlada: %s", exc)
        report = failed_probe_report(exc)
        exit_code = EXIT_CAPABILITY_FAILED
    except Exception as exc:  # pragma: no cover - proteção do processo de diagnóstico
        LOGGER.exception("Erro interno no capability probe.")
        report = failed_probe_report(ResolveUnavailableError(str(exc)))
        exit_code = EXIT_INTERNAL

    try:
        write_probe_report(report, json_path, markdown_path)
    except OSError as exc:
        LOGGER.error("Não foi possível gravar os relatórios: %s", exc)
        exit_code = EXIT_INTERNAL
    _print_summary(report, json_path, markdown_path, exit_code)
    return exit_code


def determine_exit_code(report: ProbeReport) -> int:
    statuses = {result.name: result.status for result in report.results}
    if statuses.get("connect") is CapabilityStatus.FAILED:
        return EXIT_CONNECTION
    if statuses.get("active_project") is CapabilityStatus.FAILED:
        return EXIT_NO_PROJECT
    if statuses.get("active_timeline") is CapabilityStatus.FAILED:
        return EXIT_NO_TIMELINE
    if any(status is CapabilityStatus.FAILED for status in statuses.values()):
        return EXIT_CAPABILITY_FAILED
    return EXIT_SUCCESS


def _print_summary(
    report: ProbeReport,
    json_path: Path,
    markdown_path: Path,
    exit_code: int,
) -> None:
    counts = {
        status.value: sum(result.status is status for result in report.results)
        for status in CapabilityStatus
    }
    print(f"Python: {report.python_version}", flush=True)
    print(f"Resolve: {report.resolve_version or 'não disponível'}", flush=True)
    print(f"Projeto: {report.project_name or 'não disponível'}", flush=True)
    print(f"Timeline: {report.timeline_name or 'não disponível'}", flush=True)
    print(
        "Capacidades: " + ", ".join(f"{name}={value}" for name, value in counts.items()),
        flush=True,
    )
    print(f"JSON: {json_path}", flush=True)
    print(f"Markdown: {markdown_path}", flush=True)
    print(f"Exit code: {exit_code}", flush=True)


def _run_isolated(
    args: argparse.Namespace,
    root: Path,
    json_path: Path,
    markdown_path: Path,
) -> int:
    previous_mtime = json_path.stat().st_mtime_ns if json_path.exists() else None
    command = [
        sys.executable,
        "-m",
        "o_editor.infrastructure.resolve.capabilities",
        "--root",
        str(root),
        "--json-output",
        str(json_path),
        "--markdown-output",
        str(markdown_path),
        "--worker",
        "--no-color",
    ]
    if args.allow_temporary_mutations:
        command.append("--allow-temporary-mutations")
        if args.confirm_project_name:
            command.extend(("--confirm-project-name", args.confirm_project_name))
    else:
        command.append("--read-only")
    if args.verbose:
        command.append("--verbose")
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        detail = f"O worker do probe não pôde ser executado: {exc}"
    else:
        if completed.stdout:
            print(completed.stdout.rstrip(), flush=True)
        if completed.stderr:
            print(completed.stderr.rstrip(), file=sys.stderr, flush=True)
        changed = json_path.exists() and (
            previous_mtime is None or json_path.stat().st_mtime_ns != previous_mtime
        )
        if changed and completed.returncode in {
            EXIT_SUCCESS,
            EXIT_ARGUMENT,
            EXIT_CONNECTION,
            EXIT_NO_PROJECT,
            EXIT_NO_TIMELINE,
            EXIT_CAPABILITY_FAILED,
            EXIT_INTERNAL,
        }:
            return completed.returncode
        detail = (
            "A ponte nativa do Resolve encerrou o worker antes de produzir o relatório "
            f"(return code {completed.returncode})."
        )
    LOGGER.error(detail)
    error = ResolveUnavailableError(detail)
    report = failed_probe_report(error)
    try:
        write_probe_report(report, json_path, markdown_path)
    except OSError as exc:
        print(f"Falha ao gravar relatório supervisionado: {exc}", file=sys.stderr, flush=True)
        return EXIT_INTERNAL
    _print_summary(report, json_path, markdown_path, EXIT_CONNECTION)
    return EXIT_CONNECTION


def _configure_logging(root: Path, *, verbose: bool) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    log_directory = root / "runtime" / "logs"
    try:
        log_directory.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.FileHandler(
                log_directory / "capability-probe.log",
                encoding="utf-8",
            )
        )
    except OSError:
        pass
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
