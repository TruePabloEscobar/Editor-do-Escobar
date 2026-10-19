from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from o_editor.infrastructure.config import load_config
from o_editor.ui.internal_action_runtime import InternalActionMainWindow
from o_editor.ui.qt_runtime import configure_headless_qt_environment
from tests.fixtures.podcast import podcast_layout, podcast_session

ROOT = Path(__file__).resolve().parents[2]


def test_refresh_updates_same_timeline_and_invalidates_preview(tmp_path, monkeypatch):
    configure_headless_qt_environment()
    app = QApplication.instance() or QApplication([])
    layout = podcast_layout()
    context = {
        **layout.to_dict(),
        "layout": layout.to_dict(),
        "duration_frames": layout.end_frame - layout.start_frame,
        "integration_mode": "internal_resolve_host",
        "audio_tracks": [],
    }
    window = InternalActionMainWindow(
        config=load_config(ROOT / "config/defaults.json"),
        root=tmp_path,
        use_mock=False,
        context=context,
    )
    panel = window._transcript_panel
    panel._set_session(replace(podcast_session(), layout_fingerprint=layout.fingerprint))
    panel._preview()
    assert panel._plan is not None
    changed = replace(layout, end_frame=layout.end_frame + 240)
    fresh = {
        **context,
        "layout": changed.to_dict(),
        "end_frame": changed.end_frame,
        "duration_frames": changed.end_frame - changed.start_frame,
    }
    monkeypatch.setattr(
        "o_editor.infrastructure.resolve.native_bridge.NativeResolveBridge.read_internal_context",
        lambda self: fresh,
    )
    button = window.findChild(QPushButton, "refreshTimeline")
    assert button is not None
    window.show()
    window.resize(1024, 720)
    button.click()
    assert not button.isEnabled()
    import time

    deadline = time.monotonic() + 5
    while window._refresh_thread is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window._refresh_thread is None
    assert window.statusBar().currentMessage().startswith("Timeline atualizada")
    assert window._context["duration_frames"] == fresh["duration_frames"]
    assert panel._layout.fingerprint == changed.fingerprint
    assert panel._plan is None
    assert not panel.apply_button.isEnabled()
    assert button.isEnabled()
    assert window.width() == 1024
    window.close()
    app.processEvents()


def test_refresh_failure_preserves_context_and_pending_blocks_refresh(tmp_path, monkeypatch):
    from o_editor.errors import ResolveUnavailableError

    configure_headless_qt_environment()
    app = QApplication.instance() or QApplication([])
    layout = podcast_layout()
    context = {
        **layout.to_dict(),
        "layout": layout.to_dict(),
        "audio_tracks": [],
        "integration_mode": "internal_resolve_host",
    }
    window = InternalActionMainWindow(
        config=load_config(ROOT / "config/defaults.json"),
        root=tmp_path,
        use_mock=False,
        context=context,
    )
    panel = window._transcript_panel
    panel._set_session(replace(podcast_session(), layout_fingerprint=layout.fingerprint))
    panel._preview()
    plan = panel._plan
    calls = []

    def unavailable(self):
        calls.append(True)
        raise ResolveUnavailableError("Resolve indisponível neste teste")

    monkeypatch.setattr(
        "o_editor.infrastructure.resolve.native_bridge.NativeResolveBridge.read_internal_context",
        unavailable,
    )
    panel._pending_plan_id = "pending"
    panel._update_buttons()
    assert not window._refresh_timeline_button.isEnabled()
    window._refresh_timeline()
    assert not calls and window._refresh_thread is None
    panel._pending_plan_id = None
    panel._update_buttons()
    window._refresh_timeline_button.click()
    import time

    deadline = time.monotonic() + 5
    while window._refresh_thread is not None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert window._refresh_thread is None
    assert window._context == context
    assert panel._plan is plan
    assert "indisponível" in window._source_notice.text()
    assert window._refresh_timeline_button.isEnabled()
    window.close()
    app.processEvents()
