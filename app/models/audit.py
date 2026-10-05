"""Audit event record."""
from __future__ import annotations

from dataclasses import dataclass

from app.utils.serialization import jsonable

SEVERITIES = ("DEBUG", "INFO", "NOTICE", "WARNING", "ERROR")


@dataclass
class AuditEvent:
    timestamp: str
    event: str
    severity: str
    experiment_id: str
    detail: str = ""
    sequence: int = 0

    def to_dict(self) -> dict:
        return jsonable(self)

    def to_line(self) -> str:
        return f"{self.timestamp}  {self.severity:<7}  {self.experiment_id:<24}  {self.event}" + (
            f"  | {self.detail}" if self.detail else ""
        )
