"""SynthID research records.

SynthID is treated as an EMBEDDED SIGNAL LAYER carried in pixel values, never
as metadata. Results exist only when a compatible local verification engine
produced them; otherwise the state is UNAVAILABLE.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.utils.serialization import jsonable

SYNTHID_LAYER = "EMBEDDED SIGNAL LAYER"
UNAVAILABLE_REASON = "No compatible local verification engine is currently available."
DEFAULT_LIMITATION = (
    "SynthID is an imperceptible signal embedded in pixel values, not in file metadata. Editing or removing "
    "metadata says nothing about it. A NOT DETECTED result from any engine does not establish that a signal was "
    "never present, and never verifies removal."
)
TIER_LOCAL_ENGINE = "LOCAL ENGINE OUTPUT"
TIER_UNAVAILABLE = "NOT MEASURED"
# Verification states reported by the SynthID Research Lab (INVALID = engine error / unreadable output).
VERIFICATION_STATES = ("DETECTED", "NOT DETECTED", "POSSIBLY DETECTED", "UNKNOWN", "UNAVAILABLE", "INVALID")


@dataclass
class SynthIDResult:
    state: str
    engine: str = "none"
    engine_version: str = ""
    model_version: str = ""
    confidence: float | None = None
    score: float | None = None  # optional engine-reported watermark likelihood (0-1), used for ROC/AUC
    detail: str = ""
    method: str = ""
    condition: str = "ORIGINAL"
    limitation: str = DEFAULT_LIMITATION
    tier: str = TIER_UNAVAILABLE
    context: list[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return jsonable(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "SynthIDResult":
        d = d or {}
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        known.setdefault("state", "UNAVAILABLE")
        return cls(**known)
