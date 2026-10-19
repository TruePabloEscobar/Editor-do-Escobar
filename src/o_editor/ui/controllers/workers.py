"""QObject workers that keep heavy operations off the UI thread."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from o_editor.application.analyze_timeline import AnalyzeTimeline
from o_editor.application.apply_plan import ApplyPlan
from o_editor.application.generate_report import save_application_report
from o_editor.application.transcribe_tracks import TranscribeTracks
from o_editor.domain.models import ApplicationPlan
from o_editor.infrastructure.resolve.native_bridge import NativeResolveBridge
from o_editor.infrastructure.transcription.base import CancellationToken

LOGGER = logging.getLogger("o_editor.ui.workers")


class AnalysisWorker(QObject):
    progress = Signal(float, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service: AnalyzeTimeline,
        runtime_dir: Path,
        language: str | None,
        cancellation: CancellationToken,
    ) -> None:
        super().__init__()
        self._service = service
        self._runtime_dir = runtime_dir
        self._language = language
        self._cancellation = cancellation

    @Slot()
    def run(self) -> None:
        try:
            result = self._service.execute(
                self._runtime_dir,
                language=self._language,
                progress=self.progress.emit,
                cancellation=self._cancellation,
            )
        except Exception as exc:
            LOGGER.exception("analysis_failed")
            self.failed.emit(_safe_error(exc))
        else:
            self.finished.emit(result)


class ApplyWorker(QObject):
    finished = Signal(object, object)
    failed = Signal(str)

    def __init__(
        self,
        service: ApplyPlan,
        plan: ApplicationPlan,
        runtime_dir: Path,
        cancellation: CancellationToken,
    ) -> None:
        super().__init__()
        self._service = service
        self._plan = plan
        self._runtime_dir = runtime_dir
        self._cancellation = cancellation

    @Slot()
    def run(self) -> None:
        try:
            report = self._service.execute(
                self._plan,
                cancellation=self._cancellation,
            )
            paths = save_application_report(report, self._runtime_dir)
        except Exception as exc:
            LOGGER.exception("application_failed")
            self.failed.emit(_safe_error(exc))
        else:
            self.finished.emit(report, paths)


class TranscriptionWorker(QObject):
    """Render, analyse and transcribe each selected track off the UI thread."""

    progress = Signal(float, str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, service: TranscribeTracks, cancellation: CancellationToken) -> None:
        super().__init__()
        self._service = service
        self._cancellation = cancellation

    @Slot()
    def run(self) -> None:
        try:
            session = self._service.execute(
                progress=self.progress.emit,
                cancellation=self._cancellation,
            )
        except Exception as exc:
            LOGGER.exception("track_transcription_failed")
            self.failed.emit(_safe_error(exc))
        else:
            self.finished.emit(session)


def _safe_error(error: Exception) -> str:
    text = str(error).strip()
    return text if text else f"Falha inesperada ({type(error).__name__})."


class ContextRefreshWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, bridge: NativeResolveBridge) -> None:
        super().__init__()
        self._bridge = bridge

    @Slot()
    def run(self) -> None:
        try:
            context = self._bridge.read_internal_context()
        except Exception as exc:
            LOGGER.exception("timeline_refresh_failed")
            self.failed.emit(_safe_error(exc))
        else:
            self.finished.emit(context)


class RoughCutDispatchWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, bridge: NativeResolveBridge, plan_id: str, mode: str) -> None:
        super().__init__()
        self._bridge, self._plan_id, self._mode = bridge, plan_id, mode

    @Slot()
    def run(self) -> None:
        try:
            result = self._bridge.start_rough_cut(plan_id=self._plan_id, mode=self._mode)
        except Exception as exc:
            LOGGER.exception("rough_cut_dispatch_failed")
            self.failed.emit(_safe_error(exc))
        else:
            self.finished.emit(result)
