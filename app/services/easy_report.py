"""Easy Mode research report (HTML / PDF / JSON).

The Easy screen stays simple; the full detail lives here. The report is assembled in the
same typed-section format as the experiment report and rendered by the same writers in
``report_service``, so both modes produce one consistent document style.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app import __app_name__, __motto__, __org__, __subtitle__, __version__
from app.models.experiment import utc_now
from app.services.report_service import GLOBAL_STATEMENT, LIMITATIONS, _f, write_html, write_json_report, write_pdf

ARM_TEXT = [
    "REAL IMAGE OBSERVATION - the selected image. Only observation is performed on it: metadata and C2PA provenance "
    "analysis, SynthID status from a local verification engine (never online), and descriptive fingerprint statistics "
    "computed on a native-resolution analysis region. No signal is estimated out of, or removed from, the real image. "
    "The result image is a pixel-preserving re-encoding of the decoded original in the selected format, verified "
    "against it.",
    "CONTROLLED SURROGATE RESEARCH - a transparent, keyed laboratory signal (not SynthID, not any real watermark) is "
    "embedded into a native-resolution tile of the image used as the clean host, so the ground truth is known. "
    "Separation and reconstruction methods are scored against that known signal. These results are measurements "
    "reported here; they never become the result image and do not generalise to real generators or real watermarks.",
]
EASY_LIMITATIONS = [
    "Fingerprint statistics are descriptive. They are not an AI/human verdict and not an attribution.",
    "The fingerprint analysis region is a native-resolution centre tile (no resampling) for large images; cues outside "
    "it are not measured.",
    "Methods that need a deep-learning runtime and trained weights are UNAVAILABLE in this build and were not run; "
    "detector-evasion methods are NOT IMPLEMENTED by design.",
    "Controlled-surrogate recovery and fidelity figures describe the keyed laboratory signal on this host tile only.",
    "Methods sharing an identical implementation and input are executed once; the shared execution is stated per method.",
]


def _counts_rows(res) -> list:
    c = res.counts()
    return [["Methods in registry", c["total"]], ["Executed (complete)", c["executed"]],
            ["Ran, insufficient data", c["insufficient"]], ["Failed / not run", c["failed"]],
            ["Skipped (unavailable, not implemented, data not present, incompatible)",
             c["skipped"] - c["not_in_easy_pipeline"]],
            ["Not part of the Easy pipeline (Expert-only / redundant)", c["not_in_easy_pipeline"]]]


def _readout_text(m, n: int = 3) -> str:
    items = list((m.readouts or {}).items())[:n]
    return "; ".join(f"{k}: {_f(v, 3)}" for k, v in items) or "-"


def build_easy_report(res) -> dict:
    inp, out, prov = res.input or {}, res.output or {}, res.provenance or {}
    sections: list[dict] = []

    def sec(title, **kw):
        sections.append({"title": title, **kw})

    sec("1. Experiment Identification", kv=[
        ["Experiment ID", res.experiment_id or "-"], ["Mode", "Easy Mode (01 PILIH > 02 RUN > 03 OUTPUT)"],
        ["Status", res.status], ["Created (UTC)", res.created], ["Finished (UTC)", res.finished or utc_now()],
        ["Runtime", f"{res.runtime_s:.1f} s"], ["Application", f"{__app_name__} {__version__}"],
        ["Experiment folder", res.experiment_dir or "-"], ["Network", "LOCAL-ONLY: no network access, no upload, "
                                                                     "no telemetry"]])
    sec("2. Research Arms", text=ARM_TEXT)
    sec("3. Input Image", kv=[
        ["File name", inp.get("name")], ["Path", inp.get("path")], ["Format", inp.get("format") or inp.get("container")],
        ["Resolution", f"{inp.get('width')} x {inp.get('height')}"], ["Mode / bit depth",
                                                                      f"{inp.get('mode')} / {inp.get('bit_depth')}"],
        ["File size", f"{_f(inp.get('bytes'))} bytes"], ["SHA-256 (before run)", inp.get("sha256")],
        ["SHA-256 (after run)", inp.get("sha256_after", "-")], ["BLAKE3", inp.get("blake3")],
        ["Pixel SHA-256", inp.get("pixel_sha256")],
        ["Original unchanged", {True: "YES (re-hashed after the run)", False: "NO - INTEGRITY FAILURE",
                                None: "not verified"}[res.original_unchanged]]])
    sec("4. Output Image", kv=[
        ["File", out.get("path", "-")], ["Format", f"{out.get('format', '-')} ({out.get('easy_format', '-')})"],
        ["Resolution", f"{out.get('width')} x {out.get('height')}" if out else "-"],
        ["File size", f"{_f(out.get('bytes'))} bytes" if out else "-"], ["SHA-256", out.get("sha256", "-")],
        ["Transformation", out.get("transformation_id", "-")], ["Content", out.get("content", "-")],
        ["Encoding", str(out.get("encoding", "-"))], ["Flags", "; ".join(out.get("flags") or []) or "none"]])
    sec("5. Pixel Integrity", kv=[
        ["Pixel status", out.get("pixel_status", "-")], ["Verdict", out.get("pixel_verdict", "-")],
        ["Changed pixels", f"{_f(out.get('changed_pixels'))} ({_f(out.get('changed_pixel_pct'), 4)} %)"],
        ["MAE", _f(out.get("mae"))], ["PSNR", "inf (identical)" if out.get("psnr_infinite") else
                                      f"{_f(out.get('psnr_db'), 2)} dB"], ["SSIM", _f(out.get("ssim"))]],
        list=list(out.get("actions") or []) + list(out.get("notes") or []))
    sec("6. Provenance", kv=[
        ["C2PA", f"{prov.get('c2pa_state', '-')}: {prov.get('c2pa_summary', '')}"],
        ["C2PA hard binding", prov.get("c2pa_hard_binding", "-")], ["C2PA validity / trust",
                                                                    f"{prov.get('c2pa_validity')} / {prov.get('c2pa_trust')}"],
        ["C2PA engine", prov.get("c2pa_engine", "-")], ["C2PA in result", out.get("c2pa_after", "-")],
        ["AI-content declaration (metadata)", f"{prov.get('ai_declaration', '-')}: {prov.get('ai_declaration_statement', '')}"],
        ["SynthID", f"{prov.get('synthid_state', '-')}: {prov.get('synthid_detail', '')}"],
        ["SynthID policy", prov.get("synthid_policy", "-")], ["Provenance separation", prov.get("separation", "-")]])
    sec("7. Fingerprint Families Investigated", table={
        "columns": ["Code", "Taxonomy family", "Category", "Taxonomy entries", "Investigated by"],
        "rows": [[f["code"], f["family"], f["category"], f["taxonomy_entries"], ", ".join(f["methods"])]
                 for f in res.families]})
    region = res.analysis_region or {}
    sec("8. Methods Executed", kv=_counts_rows(res) + [
        ["Analysis region", f"{region.get('width')} x {region.get('height')} - {region.get('note', '-')}"]],
        table={"columns": ["Method", "Name", "Stage", "Arm", "Status", "Runtime s", "Key readouts", "Execution"],
               "rows": [[m.method_id, m.name, m.stage, m.arm, m.status, f"{m.runtime_s:.2f}", _readout_text(m),
                         f"shared with {m.shared_with}" if m.shared_with else "own"]
                        for m in res.methods if m.decision == "RUN"]})
    sec("9. Methods Skipped", table={"columns": ["Method", "Name", "Status", "Reason"], "rows": [
        [m.method_id, m.name, m.status, m.reason] for m in res.methods if m.decision == "SKIP"]})
    failed = [m for m in res.methods if m.decision == "RUN" and m.status not in ("COMPLETE", "SIGNAL PERSISTED")]
    sec("10. Methods Failed or Without a Measurement", table={"columns": ["Method", "Name", "Status", "Detail"], "rows": [
        [m.method_id, m.name, m.status, m.detail] for m in failed]})
    cc = res.controlled_case or {}
    sec("11. Controlled Surrogate Case", kv=[
        ["Host region", f"{cc.get('width')} x {cc.get('height')} at {cc.get('region_box')}" if cc else "not run"],
        ["Surrogate", str((cc.get("surrogate") or {})) if cc else "-"],
        ["Detector z (clean host)", _f(cc.get("detector_z_clean"), 2)],
        ["Detector z (embedded)", _f(cc.get("detector_z_embedded"), 2)],
        ["Valid ground truth", _f(cc.get("valid_ground_truth"))], ["Note", cc.get("note", "-")]])
    from app.core.easy_mode_orchestrator import CANDIDATE_GATES, CANDIDATE_WEIGHTS
    sec("12. Reconstruction Candidates", kv=[
        ["Reconstruction status", res.reconstruction_status],
        ["Best validated research output", res.best_candidate or "none - NO VALIDATED RECONSTRUCTION"],
        ["Validation criteria", "; ".join(f"{k} = {v}" for k, v in CANDIDATE_GATES.items())],
        ["Ranking weights", "; ".join(f"{k} {v}" for k, v in CANDIDATE_WEIGHTS.items())],
        ["Ranking note", "Candidates are ranked by recovery of the KNOWN surrogate signal and content fidelity. The "
                         "surrogate detector's score is reported but never used for ranking."]],
        table={"columns": ["Rank", "Method", "Recovery corr", "PSNR dB", "SSIM", "Agreement", "Score", "Validated",
                           "Gate failures"],
               "rows": [[c.rank, f"{c.method_id} {c.name}", _f(c.metrics.get("candidate_vs_known_corr"), 3),
                         _f(c.metrics.get("recon_psnr_db"), 2), _f(c.metrics.get("recon_ssim"), 4),
                         _f(c.metrics.get("method_agreement"), 3), _f(c.total, 3), "YES" if c.passed else "NO",
                         "; ".join(c.gate_failures) or "-"] for c in res.candidates]})
    cons = res.consensus or {}
    sec("13. Validation Metrics & Consensus", kv=[
        ["Candidate agreement (mean pairwise corr)", _f(cons.get("candidate_agreement_mean"), 3)],
        ["Method disagreement (Method 61, real image)", f"{_f(cons.get('method_disagreement'), 3)} "
                                                        f"{cons.get('method_disagreement_verdict') or ''}"]] + [
        [f"Family: {k}", f"{v['complete']}/{v['methods']} complete"] for k, v in
        (cons.get("real_image_families") or {}).items()])
    sec("14. Pipeline Stages", table={"columns": ["#", "Stage", "Phase", "Status", "Runtime s", "Detail"], "rows": [
        [f"{s.number:02d}", s.label, s.phase, s.status, f"{s.runtime_s:.2f}", s.detail] for s in res.stages]})
    sec("15. Limitations", list=[GLOBAL_STATEMENT] + EASY_LIMITATIONS + LIMITATIONS)
    notes = list(res.notes) + [f"Warning: {w}" for w in res.warnings]
    if res.error:
        notes.insert(0, f"Run stopped: {res.error} ({res.error_detail})")
    sec("16. Research Notes", list=notes or ["No warnings were raised."])
    refs = []
    reg_ids = {m.method_id for m in res.methods if m.decision == "RUN"}
    from app.research.methods import MethodRegistry
    for mid in sorted(reg_ids):
        r = MethodRegistry().get(mid).source_reference
        if r and r not in refs:
            refs.append(r)
    sec("17. Source References", list=refs)
    if res.figures:
        sec("18. Figures", images=[{"file": f["file"], "path": f["path"], "caption": f["caption"]} for f in res.figures])
    return {"title": f"{__app_name__} Easy Mode Research Report", "subtitle": f"{__subtitle__} | {res.experiment_id}",
            "organisation": __org__, "motto": __motto__, "experiment_id": res.experiment_id or "-",
            "generated": utc_now(), "sections": sections}


def write_easy_report(res, out_dir: Path, copy_to: str | Path | None = None) -> dict[str, Path]:
    """Write HTML + PDF + JSON into the experiment's report folder; optionally copy them (and figures) elsewhere."""
    report = build_easy_report(res)
    out_dir = Path(out_dir)
    stem = f"{res.experiment_id}_easy_research_report"
    paths = {"html": write_html(report, out_dir / f"{stem}.html"),
             "json": write_json_report(report, out_dir / f"{stem}.json")}
    try:
        paths["pdf"] = write_pdf(report, out_dir / f"{stem}.pdf")
    except Exception as exc:  # noqa: BLE001 - HTML/JSON remain authoritative if the PDF engine fails
        res.warnings.append(f"PDF report not written: {type(exc).__name__}: {exc}")
    if copy_to:
        dest = Path(copy_to)
        dest.mkdir(parents=True, exist_ok=True)
        copied = {}
        for k, p in paths.items():
            copied[k] = Path(shutil.copy2(p, dest / p.name))
        if (out_dir / "figures").is_dir():
            shutil.copytree(out_dir / "figures", dest / "figures", dirs_exist_ok=True)
        paths = {**{f"experiment_{k}": v for k, v in paths.items()}, **copied}
    return paths
