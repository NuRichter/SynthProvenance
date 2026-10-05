"""SynthID local verification engine adapter.

SynthProvenance ships NO SynthID detector: no compatible local engine for
images is publicly available, and online verification services would require
uploading the image, which violates the LOCAL-ONLY policy.

A researcher may provide a local engine that follows this contract:

    <engine> --input <image path> --json
    stdout: {"engine": "...", "version": "...",
             "state": "DETECTED" | "NOT_DETECTED" | "POSSIBLY_DETECTED" | "UNCERTAIN" | "ERROR",
             "confidence": 0.0-1.0 or null, "detail": "...",
             optional: "model_version": "...", "score": 0.0-1.0 (watermark likelihood, used for ROC/AUC)}

Discovery order: Settings > SynthID engine command, then tools/synthid/
synthid_verifier(.exe). The engine runs as a subprocess with an argument
list (no shell), a timeout and bounded output.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from app.models.synthid import TIER_LOCAL_ENGINE, UNAVAILABLE_REASON, SynthIDResult
from app.utils.paths import tool_search_dirs
from app.utils.system import ToolError, run_tool

ENGINE_NAMES = (("synthid_verifier.exe", "synthid-verifier.exe") if sys.platform.startswith("win")
                else ("synthid_verifier", "synthid-verifier", "synthid_verifier.py"))
STATE_MAP = {"DETECTED": "DETECTED", "NOT_DETECTED": "NOT DETECTED", "NOT DETECTED": "NOT DETECTED",
             "POSSIBLY_DETECTED": "POSSIBLY DETECTED", "POSSIBLY DETECTED": "POSSIBLY DETECTED",
             "UNCERTAIN": "UNKNOWN", "UNKNOWN": "UNKNOWN", "ERROR": "INVALID"}


class SynthIDEngine:
    def __init__(self, command: list[str] | None = None, origin: str = "", detail: str = "") -> None:
        self.command = list(command or [])
        self.origin = origin
        self.detail = detail or ("" if self.command else UNAVAILABLE_REASON)

    @classmethod
    def discover(cls, configured=None) -> "SynthIDEngine":
        if configured:
            raw = configured if isinstance(configured, (list, tuple)) else [configured]
            cmd = [str(c) for c in raw if str(c).strip()]
            if cmd and Path(cmd[0]).is_file():
                return cls(cmd, "configured")
            if cmd:
                return cls([], "", f"{UNAVAILABLE_REASON} (configured engine not found: {cmd[0]})")
        for base in tool_search_dirs():
            for name in ENGINE_NAMES:
                p = base / "synthid" / name
                if p.is_file() and not name.endswith(".py"):
                    return cls([str(p)], "tools/synthid")
        return cls([], "", UNAVAILABLE_REASON)

    @property
    def available(self) -> bool:
        return bool(self.command)

    def status(self) -> dict:
        return {"name": "SynthID local verification engine", "available": self.available,
                "command": " ".join(self.command), "origin": self.origin,
                "detail": "ready" if self.available else self.detail}

    def analyze(self, path: Path, condition: str = "ORIGINAL") -> SynthIDResult:
        if not self.available:
            return SynthIDResult("UNAVAILABLE", detail=self.detail or UNAVAILABLE_REASON,
                                 method="No measurement performed (no local engine).", condition=condition)
        t0 = time.perf_counter()
        try:
            res = run_tool([*self.command, "--input", str(path), "--json"], timeout=180)
        except ToolError as exc:
            return SynthIDResult("INVALID", engine=Path(self.command[0]).name, detail=f"Engine failed: {exc}",
                                 method="local engine subprocess", condition=condition, tier=TIER_LOCAL_ENGINE)
        try:
            out = json.loads(res.stdout.decode("utf-8", "replace") or "{}")
            if not isinstance(out, dict):
                raise ValueError("not a JSON object")
        except ValueError as exc:
            return SynthIDResult("INVALID", engine=Path(self.command[0]).name,
                                 detail=f"Engine output is not valid JSON ({exc}); exit code {res.returncode}.",
                                 method="local engine subprocess", condition=condition, tier=TIER_LOCAL_ENGINE)
        state = STATE_MAP.get(str(out.get("state", "")).upper().strip(), "UNKNOWN")
        conf = out.get("confidence")
        conf = float(conf) if isinstance(conf, (int, float)) and 0.0 <= float(conf) <= 1.0 else None
        score = out.get("score")
        score = float(score) if isinstance(score, (int, float)) and 0.0 <= float(score) <= 1.0 else None
        engine = str(out.get("engine") or Path(self.command[0]).name)[:120]
        version = str(out.get("version") or "")[:60]
        return SynthIDResult(
            state=state, engine=engine, engine_version=version, model_version=str(out.get("model_version") or "")[:60],
            confidence=conf, score=score,
            detail=str(out.get("detail") or "")[:1000],
            method=f"Local engine '{engine}' {version} run as a subprocess on the file bytes (no upload by SynthProvenance).",
            condition=condition, tier=TIER_LOCAL_ENGINE, duration_ms=(time.perf_counter() - t0) * 1000.0)
