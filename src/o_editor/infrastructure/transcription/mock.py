"""Deterministic transcription provider used by tests and demos."""

from __future__ import annotations

from pathlib import Path

from o_editor.domain.models import Transcript, TranscriptSegment, TranscriptWord
from o_editor.errors import CancelledError
from o_editor.infrastructure.transcription.base import (
    CancellationToken,
    TranscriptionProgress,
)


class MockTranscriptionProvider:
    @property
    def name(self) -> str:
        return "mock"

    def transcribe(
        self,
        audio_path: Path,
        *,
        fps: float,
        timeline_start_frame: int,
        language: str | None,
        progress: TranscriptionProgress | None = None,
        cancellation: CancellationToken | None = None,
    ) -> Transcript:
        if not audio_path.exists():
            raise FileNotFoundError(audio_path)
        specs = (
            (2.0, 5.0, "O problema começou em 2024.", 2.0),
            (10.0, 13.0, "Mas reduzimos o tempo em 50 por cento.", 5.0),
            (22.0, 25.0, "Qual foi o resultado?", 9.0),
            (34.0, 38.0, "Em resumo, economizamos duas horas por semana.", 9.0),
            (48.0, 51.0, "O mais importante é manter a qualidade.", 10.0),
        )
        segments: list[TranscriptSegment] = []
        for index, (start, end, text, pause) in enumerate(specs):
            if cancellation and cancellation.cancelled:
                raise CancelledError("A transcrição foi cancelada.")
            start_frame = timeline_start_frame + round(start * fps)
            end_frame = timeline_start_frame + round(end * fps)
            words = _mock_words(text, start_frame, end_frame)
            segments.append(
                TranscriptSegment.create(
                    start_frame=start_frame,
                    end_frame=end_frame,
                    text=text,
                    words=words,
                    pause_before_frames=round(pause * fps),
                )
            )
            if progress:
                progress((index + 1) / len(specs), "Transcrição simulada")
        return Transcript(
            language=language or "pt",
            fps=fps,
            timeline_start_frame=timeline_start_frame,
            segments=tuple(segments),
            provider=self.name,
            model="mock-interview-v1",
        )


def _mock_words(text: str, start_frame: int, end_frame: int) -> tuple[TranscriptWord, ...]:
    tokens = text.split()
    width = max(1, (end_frame - start_frame) // len(tokens))
    result: list[TranscriptWord] = []
    for index, token in enumerate(tokens):
        word_start = start_frame + index * width
        word_end = end_frame if index == len(tokens) - 1 else min(end_frame, word_start + width)
        result.append(
            TranscriptWord(
                text=token,
                start_frame=word_start,
                end_frame=word_end,
                probability=0.99,
            )
        )
    return tuple(result)
