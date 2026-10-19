"""Tests C and D plus robustness of the TXT round trip (AI edits, truncation, tampering)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from o_editor.application.transcript_exchange import (
    TranscriptExchangeError,
    confirm_import,
    decide_missing,
    export_transcripts,
    preview_import,
)
from o_editor.domain.speech import SegmentState, TranscriptSession
from o_editor.domain.timecode import frames_to_clock, parse_clock
from o_editor.domain.transcript_document import Severity
from o_editor.infrastructure.transcript_sessions import SessionStore
from tests.fixtures.podcast import PHRASES, podcast_session


@pytest.fixture()
def exported(tmp_path: Path) -> tuple[TranscriptSession, SessionStore, dict[str, Path]]:
    store = SessionStore(tmp_path / "sessions")
    session = podcast_session()
    store.save(session)
    result = export_transcripts(session, tmp_path / "out", store, base_name="Podcast")
    files = {path.name: path for path in result.files}
    return result.session, store, files


def _codes(preview_issues: object) -> set[str]:
    return {issue.code for issue in preview_issues}  # type: ignore[attr-defined]


def test_export_creates_individual_and_consolidated_files(
    exported: tuple[TranscriptSession, SessionStore, dict[str, Path]],
) -> None:
    session, _store, files = exported
    assert set(files) == {
        "Podcast_Pablo.txt",
        "Podcast_Jessica.txt",
        "Podcast_Mileni.txt",
        "Podcast_Renne.txt",
        "Podcast_Completo.txt",
    }
    complete = files["Podcast_Completo.txt"].read_text(encoding="utf-8")
    assert "NÃO altere" in complete
    assert "@SESSION 0123456789abcdef" in complete
    headers = re.findall(
        r"^\[(SEG_\d+)\] \[(A\d): (\w+)\] \[([\d:.]+) --> ([\d:.]+)\] \[KEEP\]",
        complete,
        re.MULTILINE,
    )
    assert headers[0][1:3] == ("A1", "Pablo")
    assert headers[0][3] == "00:00:02.000"
    # Consolidated file is chronological and omits the bleed duplicate.
    assert [item[3] for item in headers] == sorted(item[3] for item in headers)
    assert complete.count(PHRASES["p3"][1]) == 1
    mileni = files["Podcast_Mileni.txt"].read_text(encoding="utf-8")
    assert "VAZAMENTO" in mileni
    assert len(session.exports) == 5


def test_c_unchanged_round_trip_removes_nothing(
    exported: tuple[TranscriptSession, SessionStore, dict[str, Path]],
) -> None:
    _session, store, files = exported
    preview = preview_import(files["Podcast_Completo.txt"], store)
    assert not preview.blocked
    assert preview.review.cut_ids == ()
    assert preview.review.missing == ()
    assert preview.review.corrections == {}
    updated = confirm_import(preview, store)
    assert all(item.state == SegmentState.KEEP for item in updated.segments)


def test_d_marking_cut_targets_exactly_that_segment(
    exported: tuple[TranscriptSession, SessionStore, dict[str, Path]],
) -> None:
    session, store, files = exported
    path = files["Podcast_Completo.txt"]
    target = next(item for item in session.segments if item.text == PHRASES["p3"][1])
    text = path.read_text(encoding="utf-8")
    edited = re.sub(rf"(\[{target.segment_id}\].*?)\[KEEP\]", r"\1[CUT]", text, count=1)
    path.write_text(edited, encoding="utf-8")
    preview = preview_import(path, store)
    assert not preview.blocked
    assert preview.review.cut_ids == (target.segment_id,)
    updated = confirm_import(preview, store)
    cut = [item for item in updated.segments if item.state == SegmentState.CUT]
    assert [(item.segment_id, item.start_frame, item.end_frame) for item in cut] == [
        (target.segment_id, target.start_frame, target.end_frame)
    ]


def test_text_correction_and_speaker_rename_keep_binding(
    exported: tuple[TranscriptSession, SessionStore, dict[str, Path]],
) -> None:
    _session, store, files = exported
    path = files["Podcast_Completo.txt"]
    text = path.read_text(encoding="utf-8")
    text = text.replace("inteligência artificial", "Inteligência Artificial (IA)")
    text = text.replace("[A2: Jessica]", "[A2: Jéssica Souza]")
    path.write_text(text, encoding="utf-8")
    preview = preview_import(path, store)
    assert not preview.blocked
    assert "SPEAKER" in _codes(preview.review.issues)
    updated = confirm_import(preview, store)
    corrected = next(item for item in updated.segments if "(IA)" in item.text)
    assert corrected.track_index == 1
    assert corrected.original_text == PHRASES["p1"][1]
    assert all(item.track_index == 2 for item in updated.segments if item.speaker == "Jessica")


def test_ai_style_wrapping_is_tolerated(
    exported: tuple[TranscriptSession, SessionStore, dict[str, Path]],
) -> None:
    _session, store, files = exported
    path = files["Podcast_Completo.txt"]
    original = path.read_text(encoding="utf-8")
    body = original.replace(" --> ", " → ").replace("[KEEP]", "[keep]", 1)
    wrapped = (
        "Claro! Aqui está o arquivo revisado:\n\n```text\n" + body + "\n```\nEspero ter ajudado."
    )
    path.write_text(wrapped, encoding="utf-8")
    preview = preview_import(path, store)
    assert not preview.blocked, preview.summary_lines()


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        (lambda text: text.split("\n@END")[0], "TRUNCATED"),
        (lambda text: text.replace("00:00:02.000 --> ", "00:00:01.000 --> ", 1), "TIME"),
        (lambda text: text.replace("[SEG_0001] [A1:", "[SEG_9999] [A1:", 1), "UNKNOWN_ID"),
        (lambda text: text.replace("[SEG_0001] [A1:", "[SEG_0001] [A2:", 1), "TRACK"),
        (lambda text: re.sub(r"(\[SEG_0001\][^\n]*)\[KEEP\]", r"\1[TALVEZ]", text), "STATE"),
        (lambda text: re.sub(r"@REVISION \d+", "@REVISION 7", text), "REVISION"),
        (lambda text: re.sub(r"@CHECKSUM \w+", "@CHECKSUM abc", text), "CHECKSUM"),
        (lambda text: text.replace("[SEG_0002]", "[SEG_0001]", 1), "DUPLICATE_ID"),
        (
            lambda text: text.replace("[SEG_0001] [A1: Pablo] [", "[SEG_0001] [A1: Pablo] {", 1),
            "MALFORMED_SEGMENT",
        ),
    ],
)
def test_invalid_edits_block_application(
    exported: tuple[TranscriptSession, SessionStore, dict[str, Path]],
    mutation: object,
    code: str,
) -> None:
    session, store, files = exported
    path = files["Podcast_Completo.txt"]
    path.write_text(mutation(path.read_text(encoding="utf-8")), encoding="utf-8")  # type: ignore[operator]
    preview = preview_import(path, store)
    assert preview.blocked
    assert code in {
        issue.code for issue in preview.review.issues if issue.severity == Severity.BLOCKER
    }
    with pytest.raises(TranscriptExchangeError):
        confirm_import(preview, store)
    assert store.load(session.session_id).segments == session.segments


def test_missing_segment_requires_explicit_confirmation(
    exported: tuple[TranscriptSession, SessionStore, dict[str, Path]],
) -> None:
    session, store, files = exported
    path = files["Podcast_Completo.txt"]
    text = path.read_text(encoding="utf-8")
    victim = next(item for item in session.segments if item.text == PHRASES["r1"][1])
    pattern = rf"\[{victim.segment_id}\][^\n]*\n[^\n]*\n\n"
    path.write_text(re.sub(pattern, "", text, count=1), encoding="utf-8")
    preview = preview_import(path, store)
    assert not preview.blocked
    assert preview.review.missing == (victim.segment_id,)
    updated = confirm_import(preview, store)
    assert updated.pending_missing == (victim.segment_id,)
    still = updated.segment(victim.segment_id)
    assert still is not None and still.state == SegmentState.KEEP
    resolved = decide_missing(updated, store, remove=True)
    assert resolved.pending_missing == ()
    removed = resolved.segment(victim.segment_id)
    assert removed is not None and removed.state == SegmentState.CUT


def test_individual_track_file_only_touches_its_track(
    exported: tuple[TranscriptSession, SessionStore, dict[str, Path]],
) -> None:
    _session, store, files = exported
    path = files["Podcast_Renne.txt"]
    path.write_text(path.read_text(encoding="utf-8").replace("[KEEP]", "[CUT]"), encoding="utf-8")
    preview = preview_import(path, store)
    assert not preview.blocked
    updated = confirm_import(preview, store)
    assert {item.track_index for item in updated.segments if item.state == SegmentState.CUT} == {4}


def test_clock_round_trip() -> None:
    assert frames_to_clock(24 * 3600 + 12, 24.0) == "01:00:00.500"
    assert parse_clock("01:00:00.500") == pytest.approx(3600.5)
    assert parse_clock("00:15:00,250") == pytest.approx(900.25)
    with pytest.raises(ValueError):
        parse_clock("aa:bb")
