"""Scripted cross-detector smoke run (used by ``SynthProvenance --smoke-cross`` and the build verifier).

Drives the real controller + Expert view, with no mouse automation: open the demo fixture, import an external
result and a Markdown research archive (reference-only), run the cross-detector study against local evidence, and
verify the comparison, the exported report and that the original image is unchanged. Everything stays LOCAL-ONLY.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import time
from pathlib import Path


def run(app, win, ctl, output) -> None:
    from PySide6.QtCore import QTimer

    from app.research import cross_detector as XD
    from app.utils import netguard

    t0 = time.perf_counter()
    result = {"ok": False, "steps": [], "errors": win.errors}
    state = {"phase": "open"}

    def done(ok, why=""):
        if state.get("fin"):
            return
        state["fin"] = True
        result["ok"] = bool(ok)
        result["reason"] = why
        result["duration_s"] = round(time.perf_counter() - t0, 2)
        result["network_attempts"] = netguard.blocked_attempts()
        if output:
            Path(output).write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        QTimer.singleShot(200, app.quit)

    def on_source():
        if state["phase"] != "open":
            return
        state["phase"] = "import"
        win.go("TruthScan Cross-Detector Lab")
        app.processEvents()
        md = "\n".join(["### Tahap 3 - Classifier ML",
                        "`final_result` `detection_step` `ocr` `synthid` `ml_model`",
                        "[FAKTA] documented stage", "[INFERENSI] reconstructed logic"])
        ok_md = ctl.import_external_result(markdown=md)
        if not ok_md or ctl.last_external.direction != XD.UNKNOWN:
            done(False, "Markdown archive did not import as reference-only")
            return
        result["steps"].append("imported Markdown archive as methodological reference (direction UNKNOWN)")
        ctl.import_external_result(blob={"result": {"final_result": "AI Generated", "confidence": 0.97,
                                                     "detection_step": 3}})
        if ctl.last_external.direction != XD.LEANS_SYNTHETIC:
            done(False, "JSON result import failed")
            return
        result["steps"].append("imported TruthScan JSON result (AI Generated, 97%, step 3)")
        state["sha"] = hashlib.sha256(ctl.research_image().read_bytes()).hexdigest()
        state["phase"] = "run"
        ctl.run_cross_detector(ground_truth_level=5, ground_truth_direction=XD.LEANS_SYNTHETIC)

    def on_cross():
        if state["phase"] != "run" or ctl.last_xd_run is None:
            return
        state["phase"] = "done"
        run_ = ctl.last_xd_run
        same = hashlib.sha256(ctl.research_image().read_bytes()).hexdigest() == state["sha"]
        result["steps"].append(f"{run_.run_id} {run_.outcome}; external vs truth: "
                               f"{run_.comparison.get('external_vs_truth')}; original unchanged "
                               f"{run_.original_unchanged and same}")
        if not (run_.original_unchanged and same):
            done(False, "original changed during cross-detector study")
            return
        if run_.scorecard.get("combined_score") is not None:
            done(False, "scorecard was collapsed into a single score")
            return
        if run_.comparison.get("external_vs_truth") != "matches the known ground truth":
            done(False, f"ground-truth phrasing wrong: {run_.comparison.get('external_vs_truth')}")
            return
        win.views["TruthScan Cross-Detector Lab"]._do_refresh()
        app.processEvents()
        dest = Path(tempfile.mkdtemp(prefix="xd_report_"))
        state["dest"] = dest
        state["phase"] = "export"
        ctl.export_cross_detector(run_.run_id, str(dest))

    def on_info(msg):
        if state["phase"] == "export" and "exported" in str(msg).lower():
            state["phase"] = "end"
            html = list(state["dest"].glob("*_cross_detector_report.html"))
            result["steps"].append(f"exported cross-detector report ({len(list(state['dest'].iterdir()))} files)")
            if not html:
                done(False, "report HTML not exported")
                return
            if netguard.blocked_attempts():
                done(False, f"network attempts: {netguard.blocked_attempts()}")
                return
            done(True, "cross-detector study: archive + result imported, local evidence compared, report exported, "
                       "original unchanged, LOCAL-ONLY")

    ctl.sourceChanged.connect(on_source)
    ctl.crossDetectorChanged.connect(on_cross)
    ctl.info.connect(on_info)
    ctl.error.connect(lambda t, m: state["phase"] in ("open", "import", "run") and done(False, f"{t}: {m}"))
    QTimer.singleShot(300, ctl.open_demo_fixture)
    QTimer.singleShot(180_000, lambda: done(False, "timeout"))
