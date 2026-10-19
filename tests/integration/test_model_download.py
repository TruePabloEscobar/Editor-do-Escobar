"""Explicit download preserves old models and never selects incomplete data."""

import json
from pathlib import Path

import pytest

from o_editor.errors import ConfigurationError
from o_editor.infrastructure.transcription.download import MODEL_FILES, download_model


def model(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "model.bin").write_bytes(b"synthetic test weights")
    (path / "config.json").write_text("{}", encoding="utf-8")
    (path / "tokenizer.json").write_text("{}", encoding="utf-8")


def test_download_is_explicit_data_only_and_does_not_overwrite(tmp_path, monkeypatch):
    calls = []

    def fetch(repo, **kwargs):
        calls.append((repo, kwargs))
        model(Path(kwargs["local_dir"]))

    monkeypatch.setattr("huggingface_hub.snapshot_download", fetch)
    assert list(tmp_path.iterdir()) == []
    path = download_model("tiny", tmp_path)
    assert path == tmp_path / "tiny"
    assert len(calls) == 1
    assert calls[0][1]["token"] is False
    assert set(calls[0][1]["allow_patterns"]) == set(MODEL_FILES)
    before = (path / "model.bin").read_bytes()
    assert download_model("tiny", tmp_path) == path
    assert len(calls) == 1 and (path / "model.bin").read_bytes() == before


@pytest.mark.parametrize("failure", ["network", "incomplete", "bad_config"])
def test_failed_download_cannot_replace_old_model_or_publish_partial(
    tmp_path, monkeypatch, failure
):
    model(tmp_path / "small")
    old = (tmp_path / "small/model.bin").read_bytes()

    def fetch(repo, **kwargs):
        stage = Path(kwargs["local_dir"])
        (stage / "model.bin").write_bytes(b"partial")
        if failure == "network":
            raise OSError("synthetic disconnect")
        if failure == "bad_config":
            model(stage)
            (stage / "config.json").write_text(json.dumps([]), encoding="utf-8")

    monkeypatch.setattr("huggingface_hub.snapshot_download", fetch)
    with pytest.raises((ConfigurationError, OSError)):
        download_model("tiny", tmp_path)
    assert not (tmp_path / "tiny").exists()
    assert (tmp_path / "small/model.bin").read_bytes() == old


def test_existing_invalid_folder_is_preserved_and_unknown_repo_refused(tmp_path, monkeypatch):
    (tmp_path / "tiny").mkdir()
    (tmp_path / "tiny/user.txt").write_text("preserve", encoding="utf-8")
    monkeypatch.setattr("huggingface_hub.snapshot_download", lambda *a, **k: pytest.fail("network"))
    for preset in ("tiny", "../../other", "untrusted/repository"):
        with pytest.raises(ConfigurationError):
            download_model(preset, tmp_path)
    assert (tmp_path / "tiny/user.txt").read_text() == "preserve"
