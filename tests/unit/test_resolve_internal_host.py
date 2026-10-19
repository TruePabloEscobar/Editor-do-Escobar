from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from o_editor.internal_actions.host_spike import run_spike
from o_editor.internal_actions.resolve_internal_host import (
    ResolveInternalHostClient,
    ResolveInternalHostPaths,
    ResolveInternalHostRequest,
    ResolveInternalHostResponse,
)


def test_host_paths_and_atomic_request(tmp_path: Path) -> None:
    paths = ResolveInternalHostPaths(tmp_path / "host")
    client = ResolveInternalHostClient(paths)
    request = ResolveInternalHostRequest.create("ping")

    request_path = client.submit(request)

    payload = json.loads(request_path.read_text(encoding="utf-8"))
    assert payload["action"] == "ping"
    assert payload["status"] == "PENDING"
    assert request.request_id in request_path.name
    assert paths.jobs.is_dir()
    assert paths.responses.is_dir()


def test_client_accepts_matching_terminal_response(tmp_path: Path) -> None:
    paths = ResolveInternalHostPaths(tmp_path / "host")
    client = ResolveInternalHostClient(paths)
    request = ResolveInternalHostRequest.create("ping")
    client.submit(request)
    response = {
        "schema_version": 1,
        "request_id": request.request_id,
        "action": "ping",
        "status": "SUCCEEDED",
        "created_at": request.created_at,
        "started_at": datetime.now(UTC).isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "host": {"plugin_id": "com.oeditor.resolve.internalhost"},
        "result": {"pong": True},
        "error": None,
    }
    path = paths.responses / f"host-response-{request.request_id}.json"
    path.write_text(json.dumps(response), encoding="utf-8")

    parsed = client.wait(request, timeout_seconds=0.2)

    assert isinstance(parsed, ResolveInternalHostResponse)
    assert parsed.status == "SUCCEEDED"
    assert parsed.result["pong"] is True


def test_client_timeout_is_non_blocking_and_safe(tmp_path: Path) -> None:
    client = ResolveInternalHostClient(ResolveInternalHostPaths(tmp_path / "host"))
    request = ResolveInternalHostRequest.create("ping")
    client.submit(request)
    started = time.monotonic()

    assert client.wait(request, timeout_seconds=0.05, poll_interval_seconds=0.01) is None
    assert time.monotonic() - started < 0.5


def test_spike_reports_supported_only_after_host_response(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    paths = ResolveInternalHostPaths.default()

    def fake_host() -> None:
        paths.ensure()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            requests = list(paths.requests.glob("host-request-*.json"))
            if requests:
                payload = json.loads(requests[0].read_text(encoding="utf-8"))
                response_path = paths.responses / f"host-response-{payload['request_id']}.json"
                response_path.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "request_id": payload["request_id"],
                            "action": "ping",
                            "status": "SUCCEEDED",
                            "created_at": payload["created_at"],
                            "started_at": datetime.now(UTC).isoformat(),
                            "finished_at": datetime.now(UTC).isoformat(),
                            "host": {"plugin_id": "com.oeditor.resolve.internalhost"},
                            "result": {"pong": True},
                            "error": None,
                        }
                    ),
                    encoding="utf-8",
                )
                return
            time.sleep(0.01)

    thread = threading.Thread(target=fake_host)
    thread.start()
    report = run_spike(timeout_seconds=1.0)
    thread.join(timeout=2)

    assert report["status"] == "SUPPORTED"
    assert report["mutations_executed"] is False


def test_workflow_plugin_is_sandboxed_and_blocks_export() -> None:
    root = (
        Path(__file__).resolve().parents[2]
        / "workflow_integration"
        / "com.oeditor.resolve.internalhost"
    )
    main = (root / "main.js").read_text(encoding="utf-8")
    html = (root / "index.html").read_text(encoding="utf-8")

    assert "sandbox: true" in main
    assert "contextIsolation: true" in main
    assert 'RegisterCallback("ResolveQuit"' in main
    assert "WorkflowIntegration.CleanUp()" in main
    assert '"UNSUPPORTED"' in main
    assert "mutations_executed: false" in main
    assert "Content-Security-Policy" in html
    assert not (root / "WorkflowIntegration.node").exists()
