from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from o_editor.errors import ConfigurationError, ResolveBridgeCrashedError
from o_editor.infrastructure.config import load_config
from o_editor.infrastructure.resolve.launch_context import consume_launch_context
from o_editor.ui.main_window import _load_context

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_launch_context_is_consumed_and_removed_safely(tmp_path) -> None:
    directory = tmp_path / "o-editor"
    directory.mkdir()
    path = directory / "launch-context-123.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_name": "Projeto",
                "timeline_name": "Timeline",
                "timeline_id": "abc",
                "resolve_version": "21",
            }
        ),
        encoding="utf-8",
    )
    context = consume_launch_context(path)
    assert context.project_name == "Projeto"
    assert context.timeline_id == "abc"
    assert not path.exists()


def test_launch_context_does_not_delete_arbitrary_file(tmp_path) -> None:
    path = tmp_path / "other.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        consume_launch_context(path)
    assert path.exists()


def test_ui_keeps_launcher_context_without_starting_disabled_bridge(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tmp_path / "o-editor"
    directory.mkdir()
    path = directory / "launch-context-crash.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "project_name": "Projeto preservado",
                "timeline_name": "Timeline preservada",
                "timeline_id": "timeline-1",
                "resolve_version": "21",
            }
        ),
        encoding="utf-8",
    )

    def crash(*args, **kwargs):
        del args, kwargs
        raise ResolveBridgeCrashedError("access violation (0xC0000005)")

    monkeypatch.setattr("o_editor.ui.main_window.reconcile_launch_context", crash)
    result = _load_context(
        str(path),
        use_mock=False,
        config=load_config(PROJECT_ROOT / "config" / "defaults.json"),
        root=tmp_path,
    )

    assert result is not None
    assert result["project_name"] == "Projeto preservado"
    assert result["timeline_name"] == "Timeline preservada"
    assert result["real_integration_available"] is False
    assert "Ponte externa desabilitada" in result["connection_status"]
    assert not path.exists()


def _internal_context(**overrides):
    value = {
        "schema_version": 1,
        "context_kind": "internal_resolve_host",
        "timestamp": datetime.now(UTC).isoformat(),
        "launched_from_resolve": True,
        "project_name": "Projeto Interno",
        "timeline_name": "Timeline Interna",
        "timeline_id": "timeline-internal",
        "resolve_version": "21.1",
        "product_name": "DaVinci Resolve Studio",
        "fps": 30,
        "start_frame": 0,
        "end_frame": 1800,
        "duration_frames": 1800,
        "start_timecode": "01:00:00:00",
        "track_counts": {"video": 2, "audio": 1, "subtitle": 0},
    }
    value.update(overrides)
    return value


def test_internal_context_is_validated_without_external_bridge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    directory = tmp_path / "pasta com espaços" / "o-editor"
    directory.mkdir(parents=True)
    path = directory / "launch-context-internal.json"
    path.write_text(json.dumps(_internal_context()), encoding="utf-8")

    def forbidden(*args, **kwargs):
        del args, kwargs
        raise AssertionError("A bridge externa não pode iniciar em --internal-host")

    monkeypatch.setattr("o_editor.ui.main_window.reconcile_launch_context", forbidden)
    result = _load_context(
        str(path),
        use_mock=False,
        config=load_config(PROJECT_ROOT / "config" / "defaults.json"),
        root=tmp_path,
        internal_host=True,
    )

    assert result is not None
    assert result["integration_mode"] == "internal_resolve_host"
    assert result["project_name"] == "Projeto Interno"
    assert result["track_counts"]["video"] == 2
    assert not path.exists()


def test_schema_two_context_exposes_audio_tracks(tmp_path: Path) -> None:
    directory = tmp_path / "o-editor"
    directory.mkdir()
    path = directory / "launch-context-audio.json"
    context = _internal_context(
        schema_version=2,
        audio_track_count=2,
        audio_tracks=[
            {
                "index": 1,
                "label": "A1",
                "name": "Áudio da câmera",
                "track_type": "audio",
                "audio_type": "stereo",
                "enabled": True,
                "muted": False,
                "locked": False,
                "item_count": 1,
            },
            {
                "index": 2,
                "label": "A2",
                "name": "Lapela Pablo",
                "track_type": "audio",
                "audio_type": "mono",
                "enabled": True,
                "muted": False,
                "locked": False,
                "item_count": 2,
            },
        ],
        track_counts={"video": 2, "audio": 2, "subtitle": 0},
    )
    path.write_text(json.dumps(context), encoding="utf-8")

    parsed = consume_launch_context(path, require_internal_host=True)

    assert parsed.audio_track_count == 2
    assert parsed.audio_tracks[1].display_name == "A2 — Lapela Pablo"
    assert parsed.to_dict()["audio_tracks"][0]["audio_type"] == "stereo"


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema_version": 4},
        {"context_kind": "external"},
        {"timestamp": "inválido"},
        {"fps": 0},
        {"duration_frames": 1799},
        {"track_counts": None},
    ],
)
def test_invalid_internal_context_is_rejected_and_removed(
    tmp_path: Path,
    overrides: dict[str, object],
) -> None:
    directory = tmp_path / "o-editor"
    directory.mkdir()
    path = directory / "launch-context-invalid.json"
    path.write_text(json.dumps(_internal_context(**overrides)), encoding="utf-8")

    with pytest.raises(ConfigurationError):
        consume_launch_context(path, require_internal_host=True)

    assert not path.exists()


def test_expired_internal_context_is_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "o-editor"
    directory.mkdir()
    path = directory / "launch-context-expired.json"
    expired = datetime.now(UTC) - timedelta(minutes=30)
    path.write_text(
        json.dumps(_internal_context(timestamp=expired.isoformat())),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="expirou"):
        consume_launch_context(path, require_internal_host=True)


def test_context_path_must_use_expected_filename(tmp_path: Path) -> None:
    path = tmp_path / "context.json"
    path.write_text(json.dumps(_internal_context()), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="caminho"):
        consume_launch_context(path, require_internal_host=True)

    assert path.exists()


def test_context_path_must_use_expected_temporary_directory(tmp_path: Path) -> None:
    directory = tmp_path / "outro-diretorio"
    directory.mkdir()
    path = directory / "launch-context-valid-name.json"
    path.write_text(json.dumps(_internal_context()), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="caminho"):
        consume_launch_context(path, require_internal_host=True)

    assert path.exists()


def test_lua_captures_identity_before_enumerating_audio_tracks() -> None:
    source = (Path(__file__).resolve().parents[2] / "launcher" / "internal_common.lua").read_text(
        encoding="utf-8"
    )

    project_capture = source.index('M.safe_call("Project.GetName"')
    audio_capture = source.index("capture_audio_tracks(timeline)", project_capture)
    identity_readback = source.index('M.safe_call("Project.GetName readback"')

    assert project_capture < audio_capture < identity_readback
    assert "A identidade do projeto/timeline mudou durante a captura" in source
