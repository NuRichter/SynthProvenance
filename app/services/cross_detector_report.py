"""Cross-Detector Research Report (HTML / PDF / JSON), rendered by report_service writers.

Built as typed sections so every format carries the same content. The report never declares
the external detector wrong or SynthProvenance correct; it reports an evidence profile under
the tested condition and names the ground-truth level.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app import __app_name__, __motto__, __org__, __subtitle__, __version__
from app.models.experiment import utc_now
from app.research import cross_detector as XD
from app.services.report_service import GLOBAL_STATEMENT, _f, write_html, write_json_report, write_pdf

OBJECTIVE = ("Compare an external AI-image detector's result with SynthProvenance's independent, local, descriptive "
             "forensic evidence for one image, identify agreement and disagreement across evidence categories, and "
             "state what can and cannot be concluded given the ground-truth level. One detector is an opinion; "
             "multiple independent measurements create evidence.")

LIMITATIONS = [
    "The external result is USER-SUPPLIED and imported; SynthProvenance did not contact the external service or upload "
    "the image. The external field names must be re-verified against the detector's current documentation.",
    "SynthProvenance does not emit an AI/human verdict from pixels; its local evidence is descriptive. A dimension that "
    "'leans' a direction is a cue, not a conclusion.",
    "Neither system is declared correct unless the ground-truth level is 3 or higher, and then only as 'matches / does "
    "not match the known ground truth'.",
    "Learned-representation detectors (CLIP/ViT/DINO) and diffusion-reconstruction detectors (DIRE/AEROBLADE) are "
    "UNAVAILABLE in this build (no bundled model); their evidence rows read NOT EVALUATED.",
    "Controlled-surrogate results concern a keyed local laboratory signal with known ground truth and do not generalise "
    "to real generators or real watermarks.",
    "Heatmap overlap (IoU / correlation) measures where two maps agree spatially; overlap is not correctness.",
]


def build_report(run, questions: tuple = XD.RESEARCH_QUESTIONS) -> dict:
    ext = run.external or {}
    local = run.local_evidence or {}
    cmp = run.comparison or {}
    inp = run.input or {}
    sections: list[dict] = []

    def sec(title, **kw):
        sections.append({"title": title, **kw})

    sec("1. Research Objective", text=[OBJECTIVE])
    sec("2. Image Information", kv=[
        ["File", inp.get("name", "-")], ["Resolution", inp.get("resolution", "-")], ["Mode", inp.get("mode", "-")],
        ["Bytes", _f(inp.get("bytes"))], ["SHA-256", inp.get("sha256", "-")], ["BLAKE3", inp.get("blake3", "-")],
        ["Original unchanged", str(run.original_unchanged)]])
    sec("3. Ground Truth", kv=[
        ["Ground-truth level", f"LEVEL {run.ground_truth_level}"],
        ["Meaning", XD.GROUND_TRUTH_LEVELS.get(run.ground_truth_level, "Unknown origin")],
        ["Ground-truth direction", run.ground_truth_direction],
        ["Decisive?", "yes (>= LEVEL 3): matches/does-not-match statements allowed" if run.ground_truth_level >= 3
         else "no (< LEVEL 3): neither system can be called correct"]],
        list=[f"LEVEL {k}: {v}" for k, v in XD.GROUND_TRUTH_LEVELS.items()])
    sec("4. SynthProvenance Findings (independent, local)", kv=[
        ["Overall local direction", cmp.get("local_direction", "DESCRIPTIVE")],
        ["Note", local.get("note", "")]],
        table={"columns": ["Dimension", "Family", "Direction", "Strength", "Observation", "Method"], "rows": [
            [d.get("name"), d.get("family"), d.get("direction"), d.get("strength"), d.get("observation"),
             d.get("method")] for d in (local.get("dimensions") or [])]})
    sec("5. TruthScan (external detector) Findings — USER-SUPPLIED", kv=[
        ["Detector", ext.get("detector", "-")], ["Source", ext.get("source", XD.SOURCE_EXTERNAL)],
        ["Final result", ext.get("final_result", "not imported")],
        ["Direction", ext.get("direction", XD.UNKNOWN)],
        ["Confidence", f"{float(ext['confidence']):.0%}" if ext.get("confidence") is not None else "-"],
        ["Detection step", {1: "1 = metadata only", 2: "2 = metadata + OCR/watermark",
                            3: "3 = metadata + OCR/watermark + ML model"}.get(ext.get("detection_step"), "not reported")],
        ["Metadata stage", ext.get("metadata_state", "-")], ["OCR / watermark stage", ext.get("ocr_watermark_state", "-")],
        ["ML stage", ext.get("ml_state", "-")], ["Warnings", "; ".join(ext.get("warnings") or []) or "none"],
        ["Heatmap reference", ext.get("heatmap_ref") or "none"],
        ["External submission id", ext.get("external_submission_id") or "-"],
        ["External timestamp", ext.get("timestamp") or "-"]])
    sec("6. Evidence Comparison", table={"columns": ["Dimension", "Family", "Local direction", "vs external",
                                                     "Observation"], "rows": [
        [r.get("dimension"), r.get("family"), r.get("local_direction"), r.get("vs_external"), r.get("observation")]
        for r in (cmp.get("dimension_rows") or [])]})
    sec("7. Detector Agreement", kv=[["Outcome", cmp.get("outcome", XD.INSUFFICIENT)],
                                     ["Consistent dimensions", ", ".join(cmp.get("agreements") or []) or "none"]])
    sec("8. Detector Disagreement", text=[cmp.get("statement", "No external result imported.")], kv=[
        ["Inconsistent dimensions", ", ".join(cmp.get("disagreements") or []) or "none"],
        ["No independent evidence", ", ".join(cmp.get("unknowns") or []) or "none"],
        ["External vs ground truth", cmp.get("external_vs_truth", "-")],
        ["Local vs ground truth", cmp.get("local_vs_truth", "-")]])
    sec("9. Fingerprint Analysis (evidence map)", table={
        "columns": ["Evidence", "Family", "Representation", "Method", "Observation", "Reference", "Validation"],
        "rows": [[e.get("evidence_id"), e.get("family"), e.get("representation"), e.get("method"),
                  e.get("observation"), e.get("source_reference"), e.get("validation_status")]
                 for e in (local.get("evidence_items") or [])]})
    sec("10. Transformation Analysis", text=[
        "Transformation (robustness) study is run from Expert Mode's Fingerprint Research Lab on a controlled surrogate "
        "with known ground truth. It characterises how a known signal persists under standard transformations; it is "
        "not an evasion search."])
    heat = run.heatmap or {}
    if heat:
        sec("11. Heatmap Analysis", kv=[["Best local match", heat.get("best_match", "-")],
                                        ["Best agreement", heat.get("best_agreement", "-")]],
            table={"columns": ["Local map", "Pearson", "IoU", "Dice", "Region consistency", "Agreement"], "rows": [
                [k, v.get("pearson"), v.get("iou"), v.get("dice"), v.get("region_consistency"), v.get("agreement")]
                for k, v in (heat.get("by_map") or {}).items() if "iou" in v]})
    else:
        sec("11. Heatmap Analysis", text=["No external heatmap was imported for this study."])
    sc = run.scorecard or {}
    sec("12. Independent Evidence Scorecard", kv=[["Combined 'truth score'", "deliberately NOT computed"],
                                                 ["Note", sc.get("note", "")]],
        table={"columns": ["Evidence dimension", "Direction", "Strength", "Observation"], "rows": [
            [k, v.get("direction"), v.get("strength"), v.get("observation")]
            for k, v in (sc.get("dimensions") or {}).items()]})
    sec("13. Reproducibility", kv=[["Run id", run.run_id], ["Created (UTC)", run.created],
                                   ["Software", f"{__app_name__} {__version__}"],
                                   ["Environment", str((run.environment or {}).get("os", "-"))],
                                   ["Network", "LOCAL-ONLY (no upload, no API call, no telemetry)"],
                                   ["External result", "USER-SUPPLIED / IMPORTED"]],
        list=["Research questions:"] + [f"Q{i+1}. {q}" for i, q in enumerate(questions)])
    sec("14. Limitations & References", list=[GLOBAL_STATEMENT] + LIMITATIONS + [
        "References: see the Research Foundations view (papers, methods, taxonomy) and docs/CROSS_DETECTOR_RESEARCH.md, "
        "docs/TRUTHSCAN_RESEARCH.md, docs/FINGERPRINT_EVIDENCE_MODEL.md."])
    return {"title": f"{__app_name__} Cross-Detector Research Report", "subtitle": f"{__subtitle__} | {run.run_id}",
            "organisation": __org__, "motto": __motto__, "experiment_id": run.run_id, "generated": utc_now(),
            "sections": sections}


def write_cross_detector_report(run, out_dir: Path, copy_to: str | Path | None = None) -> dict[str, Path]:
    report = build_report(run)
    out_dir = Path(out_dir)
    stem = f"{run.run_id}_cross_detector_report"
    paths = {"html": write_html(report, out_dir / f"{stem}.html"),
             "json": write_json_report(report, out_dir / f"{stem}.json")}
    try:
        paths["pdf"] = write_pdf(report, out_dir / f"{stem}.pdf")
    except Exception:  # noqa: BLE001 - HTML/JSON stay authoritative if the PDF engine fails
        pass
    # benchmark CSV for this single study
    from app.core.cross_detector_lab import write_benchmark_csv
    paths["csv"] = write_benchmark_csv([run.benchmark_row], out_dir / f"{stem}_matrix.csv")
    if copy_to:
        dest = Path(copy_to)
        dest.mkdir(parents=True, exist_ok=True)
        copied = {}
        for k, p in paths.items():
            copied[k] = Path(shutil.copy2(p, dest / p.name))
        paths = {**{f"run_{k}": v for k, v in paths.items()}, **copied}
    return paths
