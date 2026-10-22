"""Repeatable startup profile: menu-script spawns, window phases and session lookup.

Synthetic data only: no Resolve, no user media and no network. Run from the repo root:

    .venv\\Scripts\\python.exe scripts/benchmark_startup.py --runs 5

Real launches also log "startup_timing" lines in runtime/logs/o-editor.log.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def menu_spawns() -> dict[str, object]:
    from tests.lua_runner import lua_command

    command = lua_command()
    if command is None:
        return {"status": "UNVERIFIED", "reason": "Lua 5.1/lupa indisponível"}
    output = subprocess.run(
        [
            *command,
            str(ROOT / "tests/lua/run_open_startup.lua"),
            str(ROOT / "launcher"),
            str(ROOT / "tests/lua"),
            "2",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    runs = json.loads(output)["runs"]
    return {"first_run_spawns": runs[0]["spawned"], "steady_state_spawns": runs[1]["spawned"]}


def window_phases(runs: int) -> dict[str, object]:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from o_editor.bootstrap import bootstrap, project_root
    from o_editor.demo_podcast import podcast_layout
    from o_editor.ui.internal_action_runtime import InternalActionMainWindow

    app = QApplication.instance() or QApplication([])
    config = bootstrap()
    layout = podcast_layout()
    context = {
        "schema_version": 3,
        "context_kind": "internal_resolve_host",
        "launched_from_resolve": True,
        "project_name": layout.project_name,
        "timeline_name": layout.timeline_name,
        "timeline_id": layout.timeline_id,
        "fps": layout.fps,
        "start_frame": layout.start_frame,
        "end_frame": layout.end_frame,
        "duration_frames": layout.duration_frames,
        "start_timecode": layout.start_timecode,
        "track_counts": {"video": 1, "audio": 5, "subtitle": 0},
        "audio_track_count": 0,
        "audio_tracks": [],
        "layout": {
            "tracks": [t.to_dict() for t in layout.tracks],
            "clips": [c.to_dict() for c in layout.clips],
        },
    }
    samples: dict[str, list[float]] = {"window_ms": [], "request_ms": []}
    requests = Path(os.environ["APPDATA"]) / "O Editor" / "requests"
    requests.mkdir(parents=True, exist_ok=True)
    for _ in range(runs):
        request_id = str(uuid.uuid4())
        path = requests / f"request-{request_id}.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "request_id": request_id,
                    "action": "open",
                    "created_at": datetime.now(UTC).isoformat(),
                    "status": "SUCCESS",
                    "message": "benchmark",
                    "details": {"context": context},
                }
            ),
            encoding="utf-8",
        )
        started = time.perf_counter()
        window = InternalActionMainWindow(config=config, root=project_root(), use_mock=False)
        built = time.perf_counter()
        window.handle_ipc_message({"type": "internal_action_request", "path": str(path)})
        handled = time.perf_counter()
        samples["window_ms"].append((built - started) * 1000)
        samples["request_ms"].append((handled - built) * 1000)
        window.close()
        app.processEvents()
    return {key: round(statistics.median(values), 1) for key, values in samples.items()}


def session_lookup(runs: int) -> dict[str, object]:
    from o_editor.demo_podcast import podcast_session
    from o_editor.domain.speech import SpeechWord
    from o_editor.infrastructure.transcript_sessions import SessionStore

    base = podcast_session()
    big_segments = (
        tuple(
            replace(
                segment,
                words=tuple(
                    SpeechWord(f"w{index}", segment.start_frame, segment.start_frame + 1, 0.9)
                    for index in range(200)
                ),
            )
            for segment in base.segments
        )
        * 1
    )
    with tempfile.TemporaryDirectory() as directory:
        store = SessionStore(Path(directory))
        store.save(
            replace(
                base, session_id="aaaaaaaaaaaaaaaa", timeline_name="Outra", segments=big_segments
            )
        )
        store.save(replace(base, session_id="bbbbbbbbbbbbbbbb"))
        timings = []
        for _ in range(runs):
            started = time.perf_counter()
            store.latest_for(base.project_name, base.timeline_name)
            timings.append((time.perf_counter() - started) * 1000)
    return {
        "first_ms": round(timings[0], 2),
        "warm_median_ms": round(statistics.median(timings[1:] or timings), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as appdata:
        os.environ["APPDATA"] = appdata
        report = {
            "generated_at": datetime.now(UTC).isoformat(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "runs": args.runs,
            "menu_script": menu_spawns(),
            "window": window_phases(args.runs),
            "session_lookup": session_lookup(args.runs),
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
