"""SynthID research lab service: baseline, per-condition results, export."""
from __future__ import annotations

from app.analyzers.synthid_analyzer import analyze_synthid, compare_synthid  # noqa: F401
from app.models.experiment import Experiment
from app.models.synthid import DEFAULT_LIMITATION, UNAVAILABLE_REASON


def synthid_summary(exp: Experiment, engine_status: dict | None = None) -> dict:
    rows = []
    for t in exp.transformations:
        if t.status != "COMPLETE":
            continue
        layer = next((lay for lay in t.layers if lay.get("layer") == "SynthID"), {})
        rows.append({"transformation_id": t.transformation_id, "label": t.label,
                     "before": (t.synthid_before or {}).get("state", "UNAVAILABLE"),
                     "after": (t.synthid_after or {}).get("state", "UNAVAILABLE"),
                     "state": layer.get("state", "UNAVAILABLE"), "observation": layer.get("observation", ""),
                     "experiment_type": "TRANSFORMATION EXPERIMENT"})
    externals = [e.__dict__ for e in exp.external_classifications if getattr(e, "layer", "") == "SYNTHID"]
    return {
        "layer": "SynthID / EMBEDDED SIGNAL LAYER",
        "engine": engine_status or {"available": False, "detail": UNAVAILABLE_REASON},
        "baseline": exp.synthid_baseline,
        "conditions": rows,
        "external_user_recorded": externals,
        "limitation": DEFAULT_LIMITATION,
        "policy": "Results exist only when produced by a local engine. No result is fabricated or inferred from metadata. "
                  "Removal is never claimed.",
    }
