"""Cancellable background jobs; replies carry a revision to reject stale results."""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from o_editor.errors import CancelledError


class PreviewSignals(QObject):
    finished = Signal(int, object)
    failed = Signal(int, str)
    progress = Signal(int, str)


class PreviewJob(QRunnable):
    def __init__(self, revision: int, work: Callable[[], object]) -> None:
        super().__init__()
        self.revision = revision
        self.signals = PreviewSignals()
        self._work = work

    @Slot()
    def run(self) -> None:
        try:
            result = self._work()
        except CancelledError as exc:
            self.signals.failed.emit(self.revision, str(exc))
        except Exception as exc:
            logging.getLogger(__name__).exception("preview_failed")
            self.signals.failed.emit(self.revision, str(exc))
        else:
            self.signals.finished.emit(self.revision, result)
