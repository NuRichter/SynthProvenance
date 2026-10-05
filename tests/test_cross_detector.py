"""Cross-detector research: external-result import, the comparison engine (agreement /
disagreement / ground-truth hierarchy), the independent-evidence scorecard, heatmap overlap,
the hard-case benchmark, the lab store + report, the consent-gated hand-off (no upload), and
the Expert view."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import numpy as np
import pytest

from app.core.audit_engine import AuditLog
from app.core.cross_detector_lab import (ALLOWED_HOSTS, BENCHMARK_COLUMNS, CrossDetectorLab, ExternalDetectorGate,
                                         XD_PolicyError, benchmark_row, write_benchmark_csv)
from app.core.easy_mode_orchestrator import EasyModeOrchestrator, EasyModeRequest
from app.core.experiment_engine import Workspace
from app.core.synthid_engine import SynthIDEngine
from app.research import cross_detector as XD
from app.research import hardcases
from app.research import heatmap_compare as HM
from app.research import procedural as P
from app.research.imaging import from_float

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def scene(tmp_path):
    p = tmp_path / "in" / "scene.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    from_float(P.scene(224, 288, seed=11)).save(p)
    return p


@pytest.fixture()
def easy(tmp_path, scene):
    ws = Workspace(tmp_path / "ws")
    res = EasyModeOrchestrator(ws, AuditLog(), SynthIDEngine(), workers=2).run(EasyModeRequest(str(scene), "PNG", False))
    assert res.ok
    return ws, res.to_dict()


# ------------------------------------------------------------------ external import
def test_external_result_from_json_is_tolerant():
    blob = {"result": {"final_result": "AI Generated", "confidence_score": 97, "detection_step": 3,
            "metadata": {"state": "no camera metadata"}, "ocr": False,
            "ml_model": {"label": "synthetic", "score": 0.97}, "warnings": ["no EXIF"],
            "heatmap": {"url": "heat.png"}}, "id": "ts_42", "timestamp": "2026-10-05T10:00:00Z"}
    e = XD.ExternalResult.from_json(blob)
    assert e.source == XD.SOURCE_EXTERNAL and e.detector == "TruthScan"
    assert e.direction == XD.LEANS_SYNTHETIC and abs(e.confidence - 0.97) < 1e-9 and e.detection_step == 3
    assert e.metadata_state == "no camera metadata" and e.ml_state in ("synthetic", "REPORTED")
    assert e.ocr_watermark_state == "NOT DETECTED" and e.warnings == ["no EXIF"]
    assert e.external_submission_id == "ts_42" and e.heatmap_ref == "heat.png" and e.raw == blob
    # alternate spellings and a flat object, percent string, human label
    flat = XD.ExternalResult.from_json({"label": "Likely human", "probability": "12%", "step": 1})
    assert flat.direction == XD.LEANS_AUTHENTIC and abs(flat.confidence - 0.12) < 1e-9 and flat.detection_step == 1
    # manual entry
    m = XD.ExternalResult.from_fields(final_result="AI Generated", confidence="0.8", detection_step=2)
    assert m.direction == XD.LEANS_SYNTHETIC and abs(m.confidence - 0.8) < 1e-9 and m.detection_step == 2
    with pytest.raises(ValueError):
        XD.ExternalResult.from_json([1, 2, 3])


def test_label_and_confidence_normalisation():
    assert XD.label_direction("Uncertain") == XD.DESCRIPTIVE
    assert XD.label_direction("") == XD.UNKNOWN
    assert XD.label_direction("deepfake detected") == XD.LEANS_SYNTHETIC
    assert XD._to_confidence("high") == 0.85 and XD._to_confidence(97) == 0.97 and XD._to_confidence(0.5) == 0.5
    assert XD._to_confidence(None) is None and XD._to_confidence(True) is None


# ------------------------------------------------------------------ comparison + ground truth
def test_local_evidence_is_descriptive_not_a_verdict(easy):
    _ws, easy_dict = easy
    local = XD.local_evidence_from_easy(easy_dict, 0)
    assert local.dimensions and local.evidence_items
    # no pixel-domain dimension declares an origin; provenance may lean, others are descriptive/not-evaluated
    for d in local.dimensions:
        assert d.direction in (XD.DESCRIPTIVE, XD.LEANS_SYNTHETIC, XD.LEANS_AUTHENTIC, XD.NOT_EVALUATED, XD.UNKNOWN)
    assert local.dimension("Learned representation (CLIP/ViT/DINO)").direction == XD.NOT_EVALUATED
    # every evidence item maps to a known fingerprint family and carries a reference
    for e in local.evidence_items:
        assert e.family in XD.FAMILIES and e.source_reference


def test_comparison_outcomes_and_never_declares_a_winner(easy):
    _ws, easy_dict = easy
    ext_ai = XD.ExternalResult.from_fields(final_result="AI Generated", confidence=0.97)
    # descriptive local evidence vs an AI label -> INSUFFICIENT (not a disagreement, not a verdict)
    local = XD.local_evidence_from_easy(easy_dict, 0)
    cmp = XD.compare(local, ext_ai, 0)
    assert cmp.outcome == XD.INSUFFICIENT
    assert "No conclusion" in cmp.statement or "does not by itself" in cmp.statement
    assert "wrong" not in cmp.statement.lower() and "more accurate" not in cmp.statement.lower()
    # a camera-provenance image (C2PA MATCH, no AI declaration) contradicts an AI label -> DISAGREEMENT
    cam = dict(easy_dict)
    cam["provenance"] = {"c2pa_state": "PRESENT", "c2pa_hard_binding": "MATCH", "ai_declaration": "NOT OBSERVED",
                         "synthid_state": "UNAVAILABLE"}
    cmp2 = XD.compare(XD.local_evidence_from_easy(cam, 0), ext_ai, 0)
    assert cmp2.outcome == XD.DISAGREEMENT and "Provenance (C2PA / metadata)" in cmp2.disagreements
    assert "Neither system is declared correct" in cmp2.statement
    # an unclear external label -> INSUFFICIENT
    assert XD.compare(local, XD.ExternalResult.from_fields(final_result="weird blob"), 0).outcome == XD.INSUFFICIENT


def test_ground_truth_hierarchy_gates_matches_statements(easy):
    _ws, easy_dict = easy
    assert set(XD.GROUND_TRUTH_LEVELS) == set(range(6))
    ext = XD.ExternalResult.from_fields(final_result="AI Generated", confidence=0.9)
    local = XD.local_evidence_from_easy(easy_dict, 5)
    # below LEVEL 3: no "matches ground truth" statement
    low = XD.compare(local, ext, 2, XD.LEANS_SYNTHETIC)
    assert "not evaluable" in low.external_vs_truth
    # LEVEL 5 synthetic, external says AI -> external matches the known ground truth (still no verdict on the system)
    high = XD.compare(local, ext, 5, XD.LEANS_SYNTHETIC)
    assert high.external_vs_truth == "matches the known ground truth"
    # LEVEL 5 synthetic, external says human -> does not match
    miss = XD.compare(local, XD.ExternalResult.from_fields(final_result="Likely human"), 5, XD.LEANS_SYNTHETIC)
    assert miss.external_vs_truth == "does not match the known ground truth"


def test_scorecard_has_no_combined_truth_score(easy):
    _ws, easy_dict = easy
    local = XD.local_evidence_from_easy(easy_dict, 3)
    sc = XD.scorecard(local, XD.ExternalResult.from_fields(final_result="AI Generated", confidence=0.9), 3)
    assert sc["combined_score"] is None
    assert set(sc["dimensions"]) == set(XD.SCORECARD_DIMENSIONS)
    assert "Ground Truth Quality" in sc["dimensions"] and "LEVEL 3" in sc["dimensions"]["Ground Truth Quality"]["strength"]


# ------------------------------------------------------------------ heatmap overlap
def test_heatmap_overlap_metrics_and_resample():
    ext = np.zeros((64, 64), np.float32)
    ext[20:40, 20:40] = 1.0
    loc = np.zeros((128, 128), np.float32)
    loc[40:80, 40:80] = 1.0           # same region at 2x scale
    m = HM.compare_maps(ext, loc)
    assert m["shape"] == [128, 128] and m["iou"] > 0.9 and m["dice"] > 0.9 and abs(m["pearson"]) > 0.9
    assert HM.agreement_label(m) == "STRONG SPATIAL AGREEMENT"
    disjoint = np.zeros((128, 128), np.float32)
    disjoint[0:20, 0:20] = 1.0
    assert HM.compare_maps(ext, disjoint)["iou"] < 0.05
    multi = HM.compare_against_local_maps(ext, {"fft": loc, "residual": disjoint})
    assert multi["best_match"] == "fft"


# ------------------------------------------------------------------ hard-case benchmark
def test_hardcase_benchmark_is_labelled_with_ground_truth(tmp_path):
    cases = hardcases.generate(tmp_path / "bench", n_each=1, seed=7)
    assert len(cases) == 6
    labels = {c.label for c in cases}
    assert "SYNTHETIC + SURROGATE WATERMARK" in labels and "NATURAL-LIKE CONTROL" in labels
    for c in cases:
        assert c.ground_truth_level in XD.GROUND_TRUTH_LEVELS
        assert (tmp_path / "bench" / c.file).is_file()
    nat = next(c for c in cases if c.label == "NATURAL-LIKE CONTROL")
    assert "NOT a real photograph" in nat.notes and nat.ground_truth_level == 3   # honest about synthesis
    wm = next(c for c in cases if "SURROGATE" in c.label)
    assert wm.ground_truth_level == 4 and wm.surrogate.get("key")


# ------------------------------------------------------------------ lab store + benchmark matrix + report
def test_lab_records_study_and_keeps_original(easy, scene, tmp_path):
    ws, easy_dict = easy
    sha = hashlib.sha256(scene.read_bytes()).hexdigest()
    lab = CrossDetectorLab(ws.root / "cross_detector")
    ext = XD.ExternalResult.from_json({"result": {"final_result": "AI Generated", "confidence": 0.97,
                                                   "detection_step": 3}})
    run = lab.record_study(scene, easy_dict, ext, ground_truth_level=5, ground_truth_direction=XD.LEANS_SYNTHETIC)
    assert run.run_id.startswith("SPX-XD-") and run.original_unchanged is True
    assert hashlib.sha256(scene.read_bytes()).hexdigest() == sha
    assert run.comparison and run.scorecard["combined_score"] is None
    assert lab.load(run.run_id).run_id == run.run_id and lab.list_runs()[0]["run_id"] == run.run_id
    row = benchmark_row(run)
    assert set(row) == set(BENCHMARK_COLUMNS) and row["TRUTHSCAN"].startswith("AI Generated")
    assert "LEVEL 5" in row["GROUND TRUTH"]
    csv_path = write_benchmark_csv([row], tmp_path / "matrix.csv")
    assert csv_path.is_file() and "FINAL RESEARCH STATUS" in csv_path.read_text(encoding="utf-8").splitlines()[0]
    # report
    from app.services.cross_detector_report import write_cross_detector_report
    paths = write_cross_detector_report(run, lab.run_dir(run.run_id) / "report")
    html = Path(paths["html"]).read_text(encoding="utf-8")
    for needle in ("Research Objective", "Ground Truth", "SynthProvenance Findings", "TruthScan", "Evidence Comparison",
                   "Detector Agreement", "Detector Disagreement", "Fingerprint Analysis", "Heatmap Analysis",
                   "Independent Evidence Scorecard", "Reproducibility", "USER-SUPPLIED"):
        assert needle in html, needle
    assert "defeated" not in html.lower() and "more accurate" not in html.lower()


def test_study_without_external_result_is_local_only(easy, scene):
    ws, easy_dict = easy
    lab = CrossDetectorLab(ws.root / "cross_detector")
    run = lab.record_study(scene, easy_dict, None, ground_truth_level=0)
    assert run.outcome == XD.INSUFFICIENT and run.local_evidence and not run.external


# ------------------------------------------------------------------ consent-gated hand-off (never uploads)
def test_external_gate_is_off_by_default_and_never_uploads(scene):
    opened = []
    gate = ExternalDetectorGate(opener=lambda url: opened.append(url) or True, reveal=lambda p: None)
    assert gate.enabled is False
    with pytest.raises(XD_PolicyError):
        gate.plan(scene)                       # OFF by default
    with pytest.raises(XD_PolicyError):
        gate.enable(False)                     # needs explicit confirmation
    gate.enable(True)
    plan = gate.plan(scene)
    assert plan.url.startswith("https://") and "truthscan.com" in plan.url
    assert "truthscan.com" in ALLOWED_HOSTS
    with pytest.raises(XD_PolicyError):
        gate.execute(plan, consent=False)      # needs explicit consent
    entry = gate.execute(plan, consent=True)
    assert entry["uploaded_by_synthprovenance"] is False and opened == [plan.url]
    assert plan.image_sha256 == hashlib.sha256(scene.read_bytes()).hexdigest()


def test_cross_detector_is_local_only(easy, scene):
    from app.utils import netguard
    netguard.install()
    ws, easy_dict = easy
    before = len(netguard.blocked_attempts())
    lab = CrossDetectorLab(ws.root / "cross_detector")
    lab.record_study(scene, easy_dict, XD.ExternalResult.from_fields(final_result="AI Generated"), 0)
    hardcases.generate(ws.root / "bench", n_each=1)
    assert len(netguard.blocked_attempts()) == before


# ------------------------------------------------------------------ controller + Expert view
def _app():
    from PySide6.QtWidgets import QApplication
    from app.ui import theme
    app = QApplication.instance() or QApplication([])
    theme.apply(app)
    return app


def test_controller_import_run_and_view(tmp_path, scene):
    from app.ui.controller import AppController
    from app.ui.main_window import MainWindow
    from app.utils.config import Settings

    app = _app()
    st = Settings(tmp_path / "settings.json")
    st.set("workspace", str(tmp_path / "ws"))
    ctl = AppController(st)
    win = MainWindow(ctl, quiet=True)
    assert "TruthScan Cross-Detector Lab" in win.views

    def wait():
        t = time.time()
        while ctl.busy or time.time() - t < 0.2:
            app.processEvents()
            time.sleep(0.01)
            assert time.time() - t < 120

    ctl.open_image(str(scene))
    wait()
    assert ctl.import_external_result(blob={"result": {"final_result": "AI Generated", "confidence": 0.95,
                                                       "detection_step": 3}})
    assert ctl.last_external is not None and ctl.last_external.direction == XD.LEANS_SYNTHETIC
    ctl.run_cross_detector(ground_truth_level=5, ground_truth_direction=XD.LEANS_SYNTHETIC)
    wait()
    run = ctl.last_xd_run
    assert run is not None and run.outcome in (XD.INSUFFICIENT, XD.AGREEMENT, XD.PARTIAL, XD.DISAGREEMENT)
    assert run.comparison.get("external_vs_truth") == "matches the known ground truth"
    view = win.views["TruthScan Cross-Detector Lab"]
    view._do_refresh()
    assert view.local_table.rowCount() > 0 and view.cmp_table.rowCount() > 0
    assert view.runs.rowCount() >= 1
    # the hand-off stays off unless explicitly enabled; enabling needs confirmation
    assert ctl.xd_gate.enabled is False
    ctl.set_truthscan_mode(True, confirmed=True)
    assert ctl.xd_gate.enabled is True
    win.close()


# ------------------------------------------------------------------ v6: markdown/csv import + execution matrix
def test_markdown_archive_imports_as_reference_only():
    md = ("# TruthScan research\n\n### Tahap 2 — watermark\n`final_result` `detection_step` `ocr` `synthid` `ml_model`\n"
          "[FAKTA] documented stage\n[INFERENSI] reconstructed logic\n"
          "```json\n{\"final_result\": \"Grok\", \"detection_step\": 2, \"confidence\": 95}\n```\n")
    e = XD.ExternalResult.from_markdown(md)
    # a whole archive is methodological context: never a per-image label, even with a fenced example block
    assert e.direction == XD.UNKNOWN and "methodological reference" in e.final_result
    assert e.raw.get("archive_reference") is True
    assert "final_result" in e.raw["documented_fields"] and "synthid" in e.raw["documented_fields"]
    assert e.raw["documented_stages"] and e.raw["facts_sample"] and e.raw["inferences_sample"]
    assert "not independently validated" in e.raw["caveat"]
    # a comparison with a reference-only import is INSUFFICIENT, never a verdict
    local = XD.local_evidence_from_easy({"provenance": {}, "methods": []}, 0)
    assert XD.compare(local, e, 0).outcome == XD.INSUFFICIENT


def test_real_truthscan_archive_imports():
    archive = ROOT / "TruthScan Archives" / "TruthScan Deteksi Gambar AI (Riset 5 Oktober 2026).md"
    if not archive.is_file():
        pytest.skip("archive not present")
    e = XD.ExternalResult.from_markdown(archive.read_text(encoding="utf-8", errors="replace"))
    assert e.direction == XD.UNKNOWN and e.raw.get("archive_reference")
    assert {"final_result", "detection_step", "ocr", "synthid", "ml_model"} <= set(e.raw["documented_fields"])


def test_csv_import():
    e = XD.ExternalResult.from_csv("final_result,confidence,detection_step\nAI Generated,0.9,3")
    assert e.direction == XD.LEANS_SYNTHETIC and abs(e.confidence - 0.9) < 1e-9 and e.detection_step == 3
    with pytest.raises(ValueError):
        XD.ExternalResult.from_csv("")


def test_execution_matrix_is_bundled_and_consistent():
    import json as _json
    p = ROOT / "data" / "fingerprint_execution_matrix.json"
    assert p.is_file()
    m = _json.loads(p.read_text(encoding="utf-8"))
    assert m["n_methods"] == 64 and len(m["methods"]) == 64
    from app.research.methods import MethodRegistry
    reg = MethodRegistry()
    for row in m["methods"]:
        meth = reg.get(row["method_id"])
        assert row["capabilities"] == meth.capability_flags()      # matrix matches the live registry
        if "SEPARATION" in row["classification"]:
            assert meth.capability.startswith("sep:")
        assert (row["availability"] == "READY") == meth.runnable
    assert (ROOT / "docs" / "UPGRADE_V6_IMPLEMENTATION_AUDIT.md").is_file()
