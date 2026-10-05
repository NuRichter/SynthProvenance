"""QThreadPool worker: heavy work never runs on the GUI thread."""
from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QRunnable, Signal

from app.utils.logging import get_logger

_log = get_logger("worker")


class WorkerSignals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int, str)


class Worker(QRunnable):
    def __init__(self, fn, *args) -> None:
        super().__init__()
        self.fn, self.args = fn, args
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            result = self.fn(*self.args, progress=self._progress)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, logged with traceback
            _log.error("Background job failed:\n%s", traceback.format_exc())
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.signals.done.emit(result)

    def _progress(self, pct: int, text: str) -> None:
        self.signals.progress.emit(int(pct), str(text))
