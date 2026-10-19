"""Local regression gate: isolated synthetic data, no Resolve or model downloads."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    """Run all mandatory offline checks and write machine-readable evidence."""
    run = (
        ROOT
        / "runtime/regression"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    )
    run.mkdir(parents=True)
    environment = os.environ.copy()
    for variable, folder in [
        ("APPDATA", "appdata"),
        ("LOCALAPPDATA", "localappdata"),
        ("TEMP", "temp"),
        ("TMP", "temp"),
    ]:
        target = run / folder
        target.mkdir(exist_ok=True)
        environment[variable] = str(target)
    environment.pop("O_EDITOR_CONFIG", None)
    environment.update(
        PYTHONUTF8="1",
        QT_QPA_PLATFORM="offscreen",
        HF_HUB_OFFLINE="1",
        HF_HUB_DISABLE_TELEMETRY="1",
    )
    environment["PYTHONPATH"] = os.pathsep.join([str(ROOT / "src"), str(ROOT)])
    if os.name == "nt":
        environment["PSModulePath"] = os.pathsep.join(
            [
                str(Path(os.environ["WINDIR"]) / "System32/WindowsPowerShell/v1.0/Modules"),
                str(Path(os.environ["PROGRAMFILES"]) / "WindowsPowerShell/Modules"),
            ]
        )
    steps: list[dict[str, object]] = []
    missing = [
        name
        for name in ["ruff", "mypy", "pytest", "pytest_cov", "PySide6", "numpy", "lupa"]
        if importlib.util.find_spec(name) is None
    ]
    missing += [
        name for name in ["node", "ffmpeg", "ffprobe", "powershell.exe"] if not shutil.which(name)
    ]
    if sys.version_info[:2] != (3, 11):
        missing.append("Python 3.11")
    if missing:
        steps.append({"name": "pré-requisitos", "status": "FAILED", "missing": missing})
        print("Pré-requisitos ausentes: " + ", ".join(missing), flush=True)
    else:
        commands = [
            ("ruff check", [sys.executable, "-m", "ruff", "check", "."], 120),
            ("ruff format", [sys.executable, "-m", "ruff", "format", "--check", "."], 120),
            ("mypy", [sys.executable, "-m", "mypy", "src"], 180),
            ("dependências", [sys.executable, "-m", "pip", "check"], 120),
            (
                "pytest",
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-ra",
                    "-m",
                    "not resolve",
                    "-p",
                    "no:cacheprovider",
                    "--basetemp",
                    str(run / "pytest"),
                    "--junitxml",
                    str(run / "junit.xml"),
                    "--cov=o_editor.domain",
                    "--cov=o_editor.application",
                    "--cov-report=term-missing",
                    "--cov-report=xml:" + str(run / "coverage.xml"),
                ],
                600,
            ),
            ("mock", [sys.executable, "-m", "o_editor", "--mock", "--headless"], 60),
            ("self-test", [sys.executable, "-m", "o_editor", "--self-test"], 60),
        ]
        environment["COVERAGE_FILE"] = str(run / ".coverage")
        for index, (name, command, timeout) in enumerate(commands):
            started = time.monotonic()
            log = run / f"{index:02d}.log"
            try:
                with log.open("w", encoding="utf-8") as output:
                    result = subprocess.run(
                        command,
                        cwd=ROOT,
                        env=environment,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        timeout=timeout,
                        check=False,
                    )
                code = result.returncode
                detail = ""
                if name == "pytest" and code == 0:
                    suites = ET.parse(run / "junit.xml").getroot()
                    skipped = sum(int(s.get("skipped", "0")) for s in suites.iter("testsuite"))
                    if skipped:
                        code = 1
                        detail = f"{skipped} testes pulados: validação incompleta."
            except (OSError, subprocess.TimeoutExpired, ET.ParseError) as exc:
                code, detail = 1, str(exc)
            status = "PASSED" if code == 0 else "FAILED"
            steps.append(
                {
                    "name": name,
                    "status": status,
                    "exit_code": code,
                    "seconds": round(time.monotonic() - started, 2),
                    "log": str(log),
                    "detail": detail,
                }
            )
            print(f"[{status}] {name} {detail}", flush=True)
    passed = bool(steps) and all(step["status"] == "PASSED" for step in steps)
    report = {
        "status": "PASSED" if passed else "FAILED",
        "steps": steps,
        "run_directory": str(run),
        "resolve_api": "UNVERIFIED",
        "hardware_inference": "UNVERIFIED",
        "timeline_mutations": False,
        "data": "isolated_synthetic",
        "generated_at": datetime.now(UTC).isoformat(),
    }
    report_path = run / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "runtime/regression/latest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Relatório: {report_path}", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
