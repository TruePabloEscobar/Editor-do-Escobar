"""Transcription boundary and cancellation primitives."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Protocol

from o_editor.domain.models import Transcript

TranscriptionProgress = Callable[[float, str], None]


class CancellationToken:
    def __init__(self) -> None:
        self._event = Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()


class TranscriptionProvider(Protocol):
    @property
    def name(self) -> str: ...

    def transcribe(
        self,
        audio_path: Path,
        *,
        fps: float,
        timeline_start_frame: int,
        language: str | None,
        progress: TranscriptionProgress | None = None,
        cancellation: CancellationToken | None = None,
    ) -> Transcript: ...
