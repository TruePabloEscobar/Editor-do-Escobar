"""Stdlib-only launcher for Workspace > Scripts > Utility > O Editor."""

from __future__ import print_function

import ctypes
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import uuid
from contextlib import suppress
from datetime import datetime


def _app_data_dir():
    app_data = os.environ.get("APPDATA")
    if not app_data:
        raise RuntimeError("APPDATA não está disponível.")
    return os.path.join(app_data, "O Editor")


def _log(message):
    directory = _app_data_dir()
    with suppress(OSError):
        if not os.path.isdir(directory):
            os.makedirs(directory)
        path = os.path.join(directory, "launcher.log")
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("{0} {1}\n".format(datetime.now().isoformat(timespec="seconds"), message))


def _show_error(message):
    _log("ERRO: " + message)
    print("O Editor: " + message)
    if os.name == "nt":
        with suppress(AttributeError, OSError):
            ctypes.windll.user32.MessageBoxW(0, message, "O Editor", 0x10)


def _load_config():
    path = os.path.join(_app_data_dir(), "launcher.json")
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError) as exc:
        raise RuntimeError("Configuração do launcher inválida: {0}".format(exc)) from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise RuntimeError("launcher.json possui schema_version incompatível.")
    for key in ("project_root", "python_executable", "module"):
        if not isinstance(value.get(key), str) or not value[key]:
            raise RuntimeError("launcher.json não contém {0} válido.".format(key))
    if not os.path.isdir(value["project_root"]):
        raise RuntimeError("A raiz configurada do projeto não existe.")
    if not os.path.isfile(value["python_executable"]):
        raise RuntimeError("O Python configurado não existe.")
    return value


def _api_roots():
    roots = []
    configured = os.environ.get("RESOLVE_SCRIPT_API")
    if configured:
        roots.append(configured)
    program_data = os.environ.get("PROGRAMDATA")
    if program_data:
        roots.append(
            os.path.join(
                program_data,
                "Blackmagic Design",
                "DaVinci Resolve",
                "Support",
                "Developer",
                "Scripting",
            )
        )
    return roots


def _load_api():
    for root in _api_roots():
        for module_path in (
            os.path.join(root, "DaVinciResolveScript.py"),
            os.path.join(root, "Modules", "DaVinciResolveScript.py"),
        ):
            if not os.path.isfile(module_path):
                continue
            spec = importlib.util.spec_from_file_location("DaVinciResolveScript", module_path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise RuntimeError("A API de scripting não foi encontrada.")


def _process_exists(pid):
    if pid <= 0:
        return False
    if os.name == "nt":
        process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if process:
            ctypes.windll.kernel32.CloseHandle(process)
            return True
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _existing_process():
    path = os.path.join(_app_data_dir(), "launcher.pid")
    try:
        with open(path, encoding="ascii") as handle:
            pid = int(handle.read().strip())
    except (OSError, ValueError):
        return None
    if _process_exists(pid):
        return pid
    with suppress(OSError):
        os.remove(path)
    return None


def _write_pid(pid):
    path = os.path.join(_app_data_dir(), "launcher.pid")
    with open(path, "w", encoding="ascii") as handle:
        handle.write(str(pid))


def _optional_call(target, method_name):
    method = getattr(target, method_name, None)
    if not callable(method):
        return None
    try:
        value = method()
    except (OSError, RuntimeError, TypeError, ValueError):
        return None
    return str(value) if value else None


def _write_context(resolve, project, timeline):
    base = os.path.join(tempfile.gettempdir(), "o-editor")
    if not os.path.isdir(base):
        os.makedirs(base)
    path = os.path.join(base, "launch-context-{0}.json".format(uuid.uuid4()))
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "schema_version": 1,
                "project_name": str(project.GetName()),
                "timeline_name": str(timeline.GetName()),
                "timeline_id": _optional_call(timeline, "GetUniqueId"),
                "resolve_version": _optional_call(resolve, "GetVersionString"),
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )
    return path


def main():
    try:
        existing = _existing_process()
        if existing is not None:
            _log("Aplicativo já está em execução (PID {0}).".format(existing))
            return 0
        config = _load_config()
        module = _load_api()
        resolve = module.scriptapp("Resolve")
        if resolve is None:
            raise RuntimeError("O DaVinci Resolve não respondeu.")
        project_manager = resolve.GetProjectManager()
        project = project_manager.GetCurrentProject() if project_manager else None
        if project is None:
            raise RuntimeError("Abra um projeto antes de iniciar O Editor.")
        timeline = project.GetCurrentTimeline()
        if timeline is None:
            raise RuntimeError("Abra uma timeline antes de iniciar O Editor.")
        context_path = _write_context(resolve, project, timeline)
        environment = os.environ.copy()
        source_path = os.path.join(config["project_root"], "src")
        environment["PYTHONPATH"] = os.pathsep.join(
            part for part in (source_path, environment.get("PYTHONPATH", "")) if part
        )
        process = subprocess.Popen(
            [
                config["python_executable"],
                "-m",
                config["module"],
                "--launch-context",
                context_path,
            ],
            cwd=config["project_root"],
            env=environment,
            close_fds=True,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        _write_pid(process.pid)
        _log("Aplicativo iniciado (PID {0}).".format(process.pid))
        return 0
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        _show_error(str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
