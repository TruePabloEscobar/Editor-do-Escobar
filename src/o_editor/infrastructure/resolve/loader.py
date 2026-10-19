"""Robust Windows loader for the installed DaVinci Resolve scripting API."""

from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from o_editor.errors import ResolveUnavailableError

MODULE_FILENAME = "DaVinciResolveScript.py"


@dataclass(frozen=True, slots=True)
class ResolveApiDiscovery:
    module_path: Path | None
    library_path: Path | None
    documentation_path: Path | None
    searched_module_paths: tuple[Path, ...]
    searched_library_paths: tuple[Path, ...]
    diagnostics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LoadedResolveApi:
    module: ModuleType
    resolve: Any
    discovery: ResolveApiDiscovery


def discover_resolve_api(
    *,
    configured_api_paths: tuple[str, ...] = (),
    configured_library_paths: tuple[str, ...] = (),
    configured_documentation_paths: tuple[str, ...] = (),
) -> ResolveApiDiscovery:
    diagnostics: list[str] = []
    api_roots = _unique_paths(
        (
            *configured_api_paths,
            os.environ.get("RESOLVE_SCRIPT_API"),
            *_python_paths(),
            _expand_env(
                r"%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"
            ),
        )
    )
    module_candidates: list[Path] = []
    documentation_candidates: list[Path] = []
    for root in api_roots:
        module_candidates.extend((root / MODULE_FILENAME, root / "Modules" / MODULE_FILENAME))
        documentation_candidates.extend((root / "README.txt", root.parent / "README.txt"))
    documentation_candidates.extend(Path(path) for path in configured_documentation_paths)

    library_candidates = _unique_paths(
        (
            *configured_library_paths,
            os.environ.get("RESOLVE_SCRIPT_LIB"),
            _expand_env(r"%PROGRAMFILES%\Blackmagic Design\DaVinci Resolve\fusionscript.dll"),
        )
    )
    module_path = next((path for path in module_candidates if path.is_file()), None)
    library_path = next((path for path in library_candidates if path.is_file()), None)
    documentation_path = next(
        (path for path in _deduplicate(documentation_candidates) if path.is_file()),
        None,
    )

    diagnostics.append(
        f"Módulo Resolve: {module_path}" if module_path else "Módulo Resolve não encontrado."
    )
    diagnostics.append(
        f"Biblioteca Resolve: {library_path}"
        if library_path
        else "Biblioteca fusionscript não encontrada."
    )
    diagnostics.append(
        f"Documentação local: {documentation_path}"
        if documentation_path
        else "Documentação de scripting não encontrada."
    )
    return ResolveApiDiscovery(
        module_path=module_path,
        library_path=library_path,
        documentation_path=documentation_path,
        searched_module_paths=tuple(_deduplicate(module_candidates)),
        searched_library_paths=tuple(library_candidates),
        diagnostics=tuple(diagnostics),
    )


def load_resolve_api(
    *,
    configured_api_paths: tuple[str, ...] = (),
    configured_library_paths: tuple[str, ...] = (),
    configured_documentation_paths: tuple[str, ...] = (),
) -> LoadedResolveApi:
    discovery = discover_resolve_api(
        configured_api_paths=configured_api_paths,
        configured_library_paths=configured_library_paths,
        configured_documentation_paths=configured_documentation_paths,
    )
    if discovery.module_path is None:
        searched = "\n".join(str(path) for path in discovery.searched_module_paths)
        raise ResolveUnavailableError(
            "A API de scripting do Resolve não foi encontrada. Caminhos verificados:\n" + searched
        )
    if discovery.library_path and not os.environ.get("RESOLVE_SCRIPT_LIB"):
        os.environ["RESOLVE_SCRIPT_LIB"] = str(discovery.library_path)
    module = _load_module(discovery.module_path)
    scriptapp = getattr(module, "scriptapp", None)
    if not callable(scriptapp):
        raise ResolveUnavailableError(
            f"O módulo {discovery.module_path.name} não expõe scriptapp()."
        )
    try:
        resolve = scriptapp("Resolve")
    except (OSError, RuntimeError, SystemError) as exc:
        raise ResolveUnavailableError(
            "A API foi carregada, mas não foi possível conectar ao DaVinci Resolve."
        ) from exc
    if resolve is None:
        raise ResolveUnavailableError(
            "DaVinci Resolve não respondeu. Confirme que está aberto e que o acesso "
            "por scripts está habilitado nas preferências."
        )
    return LoadedResolveApi(module=module, resolve=resolve, discovery=discovery)


def _load_module(path: Path) -> ModuleType:
    module_name = "_o_editor_davinci_resolve_script"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ResolveUnavailableError(f"Não foi possível preparar o módulo da API: {path}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except (ImportError, OSError, RuntimeError, SystemError) as exc:
        raise ResolveUnavailableError(
            "Falha ao carregar a biblioteca de scripting do DaVinci Resolve."
        ) from exc
    # The installed wrapper exposes its dynamically loaded native module here.
    native = getattr(module, "script_module", None)
    if isinstance(native, ModuleType) and callable(getattr(native, "scriptapp", None)):
        module = native
    sys.modules[module_name] = module
    return module


def _python_paths() -> tuple[str, ...]:
    value = os.environ.get("PYTHONPATH", "")
    return tuple(part for part in value.split(os.pathsep) if part)


def _expand_env(value: str) -> str:
    return os.path.expandvars(value)


def _unique_paths(values: tuple[str | None, ...]) -> list[Path]:
    return _deduplicate(Path(value).expanduser() for value in values if value)


def _deduplicate(values: Any) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for raw in values:
        path = Path(raw)
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result
