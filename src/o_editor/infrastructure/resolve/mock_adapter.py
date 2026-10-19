"""Configurable in-memory Resolve adapter for offline tests."""

from __future__ import annotations

import wave
from dataclasses import replace
from pathlib import Path

from o_editor.domain.enums import CapabilityStatus, TrackType
from o_editor.domain.models import (
    ApplicationOperation,
    CapabilityResult,
    TimelineItemSnapshot,
    TimelineSnapshot,
    stable_id,
)
from o_editor.domain.voice_tracks import AudioTrackSnapshot
from o_editor.errors import OperationVerificationError, ResolveUnavailableError
from o_editor.infrastructure.resolve.adapter import AdapterOperationResult


class MockResolveAdapter:
    def __init__(
        self,
        snapshot: TimelineSnapshot | None = None,
        *,
        fail_operations: set[str] | None = None,
        fail_verification: set[str] | None = None,
        connected: bool = True,
    ) -> None:
        original = snapshot or interview_timeline_fixture()
        self._timelines = {original.timeline_name: original}
        self._active_name = original.timeline_name
        self._connected = connected
        self._fail_operations = fail_operations or set()
        self._fail_verification = fail_verification or set()
        self._applied: dict[str, ApplicationOperation] = {}
        self._text_tracks: dict[str, int] = {}
        self._playhead = original.start_frame

    def connect(self) -> None:
        if not self._connected:
            raise ResolveUnavailableError("O mock foi configurado para falhar na conexão.")

    @property
    def resolve_version(self) -> str:
        return "MOCK-21.0"

    @property
    def original_snapshot(self) -> TimelineSnapshot:
        return next(iter(self._timelines.values()))

    @property
    def active_timeline_name(self) -> str:
        return self._active_name

    @property
    def timeline_names(self) -> tuple[str, ...]:
        return tuple(self._timelines)

    @property
    def applied_operations(self) -> tuple[ApplicationOperation, ...]:
        return tuple(self._applied.values())

    def get_active_snapshot(self) -> TimelineSnapshot:
        self.connect()
        return self._timelines[self._active_name]

    def export_audio(
        self,
        destination: Path,
        *,
        sample_rate: int,
        channels: int,
    ) -> Path:
        self.connect()
        if "export_audio" in self._fail_operations:
            raise ResolveUnavailableError("Falha simulada ao exportar áudio.")
        if sample_rate not in (16_000, 48_000) or channels not in (1, 2):
            raise ValueError("mock audio supports 16/48 kHz and mono/stereo")
        destination.parent.mkdir(parents=True, exist_ok=True)
        duration_seconds = min(self.get_active_snapshot().duration_frames / 30, 5)
        with wave.open(str(destination), "wb") as output:
            output.setnchannels(channels)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes(b"\0\0" * channels * round(duration_seconds * sample_rate))
        return destination

    def duplicate_timeline(self, target_name: str) -> TimelineSnapshot:
        self.connect()
        if "duplicate_timeline" in self._fail_operations:
            raise ResolveUnavailableError("Falha simulada ao duplicar a timeline.")
        if target_name in self._timelines:
            raise ResolveUnavailableError("Já existe uma timeline com o nome solicitado.")
        source = self.get_active_snapshot()
        duplicate = replace(
            source,
            timeline_name=target_name,
            timeline_id=stable_id("timeline", (source.timeline_id, target_name)),
        )
        self._timelines[target_name] = duplicate
        self._active_name = target_name
        if source.timeline_name not in self._timelines:
            raise OperationVerificationError("A timeline original desapareceu após a duplicação.")
        return duplicate

    def ensure_text_track(self, name: str) -> int:
        self.connect()
        if "ensure_text_track" in self._fail_operations:
            raise ResolveUnavailableError("Falha simulada ao criar a track de textos.")
        if self._active_name == self.original_snapshot.timeline_name:
            raise ResolveUnavailableError("A track não pode ser criada na timeline original.")
        if name not in self._text_tracks:
            self._text_tracks[name] = self.get_active_snapshot().video_track_count + 1
        return self._text_tracks[name]

    def apply_operation(self, operation: ApplicationOperation) -> AdapterOperationResult:
        self.connect()
        if self._active_name == self.original_snapshot.timeline_name:
            return AdapterOperationResult(False, "A timeline original está ativa.")
        if operation.id in self._fail_operations or operation.kind.value in self._fail_operations:
            return AdapterOperationResult(False, "Falha simulada configurada.")
        self._applied[operation.id] = operation
        return AdapterOperationResult(True, "Operação simulada aceita.")

    def verify_operation(self, operation: ApplicationOperation) -> bool:
        return operation.id in self._applied and operation.id not in self._fail_verification

    def set_playhead(self, frame: int) -> bool:
        snapshot = self.get_active_snapshot()
        if not snapshot.start_frame <= frame < snapshot.end_frame:
            return False
        self._playhead = frame
        return True

    def capability_results(self) -> tuple[CapabilityResult, ...]:
        names = (
            "connect",
            "active_project",
            "active_timeline",
            "timeline_snapshot",
            "export_audio",
            "duplicate_timeline",
            "add_video_track",
            "rename_track",
            "apply_mock_operation",
            "verify_mock_operation",
        )
        return tuple(
            CapabilityResult(
                name=name,
                status=CapabilityStatus.SUPPORTED,
                method=f"MockResolveAdapter.{name}",
                return_value=True,
                exception=None,
                notes="Capacidade simulada; não prova suporte no Resolve real.",
                impact="Permite testes offline.",
                fallback="Nenhum.",
            )
            for name in names
        )


def interview_timeline_fixture() -> TimelineSnapshot:
    clips = (
        TimelineItemSnapshot.create(
            track_type=TrackType.VIDEO,
            track_index=1,
            start_frame=0,
            end_frame=900,
            source_start_frame=0,
            source_end_frame=900,
            name="Entrevista_Camera_A",
            media_id="mock-media-a",
            source_path="mock://interview-a.mov",
        ),
        TimelineItemSnapshot.create(
            track_type=TrackType.VIDEO,
            track_index=1,
            start_frame=900,
            end_frame=1_800,
            source_start_frame=900,
            source_end_frame=1_800,
            name="Entrevista_Camera_A",
            media_id="mock-media-a",
            source_path="mock://interview-a.mov",
        ),
        TimelineItemSnapshot.create(
            track_type=TrackType.AUDIO,
            track_index=1,
            start_frame=0,
            end_frame=1_800,
            source_start_frame=0,
            source_end_frame=1_800,
            name="Entrevista_Audio",
            media_id="mock-audio-a",
            source_path="mock://interview.wav",
        ),
    )
    return TimelineSnapshot(
        project_name="Projeto Mock",
        timeline_name="Entrevista Mock",
        timeline_id="mock-timeline-interview",
        fps=30.0,
        drop_frame=False,
        start_frame=0,
        end_frame=1_800,
        video_track_count=1,
        audio_track_count=5,
        items=clips,
        audio_tracks=(
            AudioTrackSnapshot(1, "A1", "Áudio da câmera", audio_type="stereo", item_count=1),
            AudioTrackSnapshot(2, "A2", "Lapela Pablo", audio_type="mono", item_count=1),
            AudioTrackSnapshot(3, "A3", "Lapela convidado", audio_type="mono", item_count=1),
            AudioTrackSnapshot(4, "A4", "Música", audio_type="stereo", item_count=1),
            AudioTrackSnapshot(5, "A5", "Efeitos", audio_type="stereo", item_count=1),
        ),
    )
