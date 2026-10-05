"""Local SynthID verification adapter (method SID-M1).

Wraps the subprocess engine contract (app/core/synthid_engine.py) and turns
each call into an auditable record: detector and model versions, verification
state, source, timestamp and image hashes. The input file is hashed before and
after the engine runs; any change is reported, because an engine must never
modify its input. Without an engine every record is UNAVAILABLE.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from app.core.hashing import blake3_file, sha256_file
from app.core.synthid_engine import SynthIDEngine
from app.models.experiment import utc_now
from app.models.synthid import UNAVAILABLE_REASON
from app.utils.serialization import jsonable

METHOD_ID = "SID-M1"
# Ordinal score used for ROC/AUC only when the engine reports no explicit "score".
STATE_SCORE = {"DETECTED": 1.0, "POSSIBLY DETECTED": 0.5, "NOT DETECTED": 0.0}


@dataclass
class VerificationRecord:
    image: str
    image_sha256: str
    image_blake3: str
    state: str
    detector: str = "none"
    detector_version: str = ""
    model_version: str = ""
    confidence: float | None = None
    score: float | None = None
    score_basis: str = "none"
    source: str = ""
    method_id: str = METHOD_ID
    timestamp: str = ""
    runtime_ms: float = 0.0
    detail: str = ""
    input_unchanged: bool = True

    def to_dict(self) -> dict:
        return jsonable(self)


class LocalVerifier:
    def __init__(self, engine: SynthIDEngine | None) -> None:
        self.engine = engine or SynthIDEngine()

    @property
    def available(self) -> bool:
        return self.engine.available

    def status(self) -> dict:
        return self.engine.status()

    def verify(self, path: Path) -> VerificationRecord:
        path = Path(path)
        sha_before, b3_before = sha256_file(path), blake3_file(path) or ""
        st = self.engine.status()
        rec = VerificationRecord(image=path.name, image_sha256=sha_before, image_blake3=b3_before, state="UNAVAILABLE",
                                 source=f"{st.get('origin') or '-'}: {st.get('command') or '-'}", timestamp=utc_now())
        if not self.available:
            rec.detail = self.engine.detail or UNAVAILABLE_REASON
            return rec
        t0 = time.perf_counter()
        res = self.engine.analyze(path, "ORIGINAL")
        rec.runtime_ms = (time.perf_counter() - t0) * 1000.0
        rec.state, rec.detector, rec.detector_version = res.state, res.engine, res.engine_version
        rec.model_version, rec.confidence, rec.detail = res.model_version, res.confidence, res.detail
        if res.score is not None:
            rec.score, rec.score_basis = res.score, "engine score"
        elif res.state in STATE_SCORE:
            rec.score, rec.score_basis = STATE_SCORE[res.state], "ordinal state (DETECTED=1, POSSIBLY=0.5, NOT=0)"
        if sha256_file(path) != sha_before:
            rec.input_unchanged = False
            rec.state = "INVALID"
            rec.detail = "INTEGRITY FAILURE: the engine modified its input file. Result discarded. " + rec.detail
        return rec
