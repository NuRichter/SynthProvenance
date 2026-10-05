"""Thread-safe audit log.

Every event is kept in memory, appended to ``logs/audit.jsonl`` of the bound
experiment workspace, and forwarded to subscribers (the GUI forwards them to
the Qt thread through a queued signal).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Callable

from app.models.audit import SEVERITIES, AuditEvent
from app.models.experiment import utc_now
from app.utils.logging import get_logger

# Canonical event names used across the application.
IMAGE_LOADED = "IMAGE LOADED"
BASELINE_COMPLETE = "BASELINE FORENSIC ANALYSIS COMPLETE"
C2PA_COMPLETE = "C2PA ANALYSIS COMPLETE"
SYNTHID_COMPLETE = "SYNTHID ANALYSIS COMPLETE"
FILE_EXPORTED = "FILE EXPORTED"
NETWORK_BLOCKED = "NETWORK ACCESS BLOCKED"
METADATA_COMPLETE = "METADATA ANALYSIS COMPLETE"
PROVENANCE_COMPLETE = "PROVENANCE ANALYSIS COMPLETE"
STATISTICS_COMPLETE = "FORENSIC STATISTICS COMPLETE"
EXPERIMENT_STARTED = "EXPERIMENT STARTED"
EXPERIMENT_LOADED = "EXPERIMENT LOADED"
TRANSFORMATION_STARTED = "TRANSFORMATION STARTED"
TRANSFORMATION_COMPLETE = "TRANSFORMATION COMPLETE"
TRANSFORMATION_FAILED = "TRANSFORMATION FAILED"
TRANSFORMATION_REFUSED = "TRANSFORMATION REFUSED"
PIXEL_VERIFICATION_COMPLETE = "PIXEL VERIFICATION COMPLETE"
EXTERNAL_CLASSIFICATION = "EXTERNAL CLASSIFICATION RECORDED"
REPORT_GENERATED = "REPORT GENERATED"
BUNDLE_EXPORTED = "EXPERIMENT BUNDLE EXPORTED"
SYNTHID_RESEARCH_RUN = "SYNTHID RESEARCH RUN COMPLETE"
SYNTHID_PAPER_EXPORTED = "SYNTHID PAPER EXPORT"
FINGERPRINT_RUN = "FINGERPRINT RESEARCH RUN COMPLETE"
FINGERPRINT_PAPER_EXPORTED = "FINGERPRINT PAPER EXPORT"
EASY_RUN_STARTED = "EASY MODE RUN STARTED"
EASY_STAGE = "EASY MODE STAGE"
EASY_RUN_COMPLETE = "EASY MODE RUN COMPLETE"
UI_MODE_CHANGED = "APPLICATION MODE CHANGED"
ONLINE_MODE_CHANGED = "ONLINE VERIFICATION MODE CHANGED"
ONLINE_VERIFIER_OPENED = "OFFICIAL VERIFIER OPENED (user-confirmed, no upload by SynthProvenance)"
ERROR = "ERROR"

_log = get_logger("audit")


class AuditLog:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: list[AuditEvent] = []
        self._subscribers: list[Callable[[AuditEvent], None]] = []
        self._path: Path | None = None
        self._experiment_id = "-"
        self._seq = 0

    # -- binding ---------------------------------------------------------
    def bind(self, experiment_id: str, jsonl_path: Path | None, load_existing: bool = False,
             carry_unbound: bool = False) -> None:
        with self._lock:
            pending = [e for e in self._events if e.experiment_id == "-"] if carry_unbound else []
            self._experiment_id = experiment_id or "-"
            self._path = Path(jsonl_path) if jsonl_path else None
            self._events = []
            self._seq = 0
            if load_existing and self._path and self._path.is_file():
                for ev in read_jsonl(self._path):
                    self._events.append(ev)
                    self._seq = max(self._seq, ev.sequence)
        for ev in pending:
            self.log(ev.event, ev.severity, ev.detail + " (recorded before experiment start)")

    @property
    def experiment_id(self) -> str:
        return self._experiment_id

    def subscribe(self, callback: Callable[[AuditEvent], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    # -- logging ---------------------------------------------------------
    def log(self, event: str, severity: str = "INFO", detail: str = "", experiment_id: str | None = None) -> AuditEvent:
        if severity not in SEVERITIES:
            severity = "INFO"
        with self._lock:
            self._seq += 1
            ev = AuditEvent(utc_now(), event, severity, experiment_id or self._experiment_id, str(detail)[:2000], self._seq)
            self._events.append(ev)
            if self._path is not None:
                try:
                    self._path.parent.mkdir(parents=True, exist_ok=True)
                    with self._path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps(ev.to_dict(), ensure_ascii=False) + "\n")
                except OSError as exc:  # audit persistence failure is reported, never fatal
                    _log.warning("Audit log write failed: %s", exc)
            subscribers = list(self._subscribers)
        _log.info("%s %s %s", ev.severity, ev.event, ev.detail)
        for cb in subscribers:
            try:
                cb(ev)
            except Exception as exc:  # noqa: BLE001 - a broken subscriber must not break auditing
                _log.warning("Audit subscriber failed: %s", exc)
        return ev

    def events(self) -> list[AuditEvent]:
        with self._lock:
            return list(self._events)

    def to_text(self) -> str:
        return "\n".join(ev.to_line() for ev in self.events()) + "\n"

    def write_text(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_text(), encoding="utf-8")
        return path


def read_jsonl(path: Path, max_lines: int = 200_000) -> list[AuditEvent]:
    events: list[AuditEvent] = []
    with Path(path).open("r", encoding="utf-8", errors="replace") as fh:
        for n, line in enumerate(fh):
            if n >= max_lines:
                break
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                events.append(AuditEvent(**{k: d[k] for k in AuditEvent.__dataclass_fields__ if k in d}))
            except (ValueError, TypeError):
                continue
    return events
