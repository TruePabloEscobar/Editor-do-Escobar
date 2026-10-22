"""Startup phases are logged so real launches on Windows can be measured."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from o_editor.ui.internal_action_runtime import StartupTimer


def test_startup_timer_logs_phases_and_request_age(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    request = tmp_path / "request.json"
    created = (datetime.now(UTC) - timedelta(seconds=2)).isoformat()
    request.write_text(json.dumps({"created_at": created}), encoding="utf-8")
    timer = StartupTimer()
    timer.mark("qapplication")
    timer.mark("window")
    with caplog.at_level(logging.INFO, logger="o_editor.startup"):
        timer.log("first_event_loop", {"type": "internal_action_request", "path": str(request)})
    message = caplog.records[-1].getMessage()
    assert "qapplication=" in message and "window=" in message and "first_event_loop=" in message
    age = int(message.rsplit("request_age_ms=", 1)[1])
    assert 1500 <= age <= 60_000


def test_request_age_is_optional() -> None:
    timer = StartupTimer()
    timer.log("first_event_loop", {"type": "activate"})
