"""SynthID layer analysis and before/after comparison (never inferred from metadata)."""
from __future__ import annotations

from pathlib import Path

from app.models.provenance import LAYER_KIND, LAYER_SYNTHID
from app.models.synthid import DEFAULT_LIMITATION, UNAVAILABLE_REASON, SynthIDResult


def context_notes(analysis: dict | None) -> list[str]:
    notes = ["SynthID is carried in pixel values. A verified pixel-exact metadata-only operation leaves that carrier "
             "unchanged. Metadata declarations below are NOT SynthID evidence."]
    if not analysis:
        return notes
    ev = (analysis.get("signal") or {}).get("evidence") or []
    if ev:
        notes.append(f"Provenance metadata declares AI generation ({len(ev)} declaration(s), C2PA/XMP/generator records). "
                     "This is the provenance layer, not a SynthID measurement.")
    for m in (analysis.get("c2pa") or {}).get("manifests") or []:
        if "google" in str(m.get("claim_generator", "")).lower():
            notes.append("A C2PA claim generator names Google. That is a Content Credential statement, not a SynthID "
                         "detection.")
            break
    return notes


def analyze_synthid(engine, path: Path | None, condition: str, analysis: dict | None = None) -> SynthIDResult:
    if engine is not None and engine.available and path is not None:
        res = engine.analyze(Path(path), condition)
    else:
        detail = (engine.detail if engine is not None else "") or UNAVAILABLE_REASON
        res = SynthIDResult("UNAVAILABLE", detail=detail, method="No measurement performed (no local engine).",
                            condition=condition)
    res.context = context_notes(analysis)
    return res


def compare_synthid(before: dict, after: dict, condition: str) -> dict:
    sb = (before or {}).get("state", "UNAVAILABLE")
    sa = (after or {}).get("state", "UNAVAILABLE")
    method = (after or {}).get("method") or (before or {}).get("method") or "No measurement performed."
    if "UNAVAILABLE" in (sb, sa):
        state = "UNAVAILABLE"
        obs = f"SynthID layer not measured under this condition: {UNAVAILABLE_REASON} Nothing is inferred."
    elif sb == "DETECTED" and sa == "DETECTED":
        state, obs = "PERSISTED", "The local engine reported the signal as DETECTED before and after the transformation."
    elif sb == "DETECTED" and sa == "NOT DETECTED":
        state = "NOT DETECTED"
        obs = ("The local engine reported DETECTED before and NOT DETECTED after this TRANSFORMATION EXPERIMENT. "
               "This is not verified removal: a detector miss is not proof of absence.")
    elif sb == "NOT DETECTED" and sa == "NOT DETECTED":
        state = "NOT DETECTED"
        obs = "Not detected under either condition. This does not establish that a signal was never present."
    elif sb == "NOT DETECTED" and sa == "DETECTED":
        state, obs = "DETECTED", "Detected only after the transformation. Unexpected; review engine reliability."
    elif "INVALID" in (sb, sa):
        state, obs = "INVALID", "The engine returned an error or unreadable output for at least one condition."
    else:
        state, obs = "UNKNOWN", f"Engine states: before {sb}, after {sa}."
    return {"layer": LAYER_SYNTHID, "kind": LAYER_KIND[LAYER_SYNTHID], "before": sb, "after": sa, "state": state,
            "observation": obs, "method": method, "condition": condition, "limitation": DEFAULT_LIMITATION}
