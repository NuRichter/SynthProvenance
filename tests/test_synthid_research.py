import hashlib
import json
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

from app.core import synthid_source_manager as SM
from app.core.synthetic import make_png
from app.core.synthid_benchmark import (DatasetItem, auc_mann_whitney, confusion, evaluate, load_dataset, roc_curve,
                                        run_benchmark, wilson)
from app.core.synthid_detector_registry import BASE_METHODS, MethodRegistry, validate_spec
from app.core.synthid_engine import SynthIDEngine
from app.core.synthid_local_verifier import LocalVerifier
from app.core.synthid_online import (DESTINATIONS, Destination, OnlineGate, OnlinePolicyError, check_destination)
from app.core.synthid_research_engine import MATRIX_COLUMNS, RUN_ID_RE, ResearchStore
from app.services.synthid_paper_export import export_paper_zip

ROOT = Path(__file__).resolve().parents[1]

# Test double: a local engine following the tools/synthid contract. It reads the score from the file name
# ("s0.85_x.png" -> score 0.85), so expected metrics are known exactly. It is not a detector.
FAKE_ENGINE = r'''
import json, re, sys
path = sys.argv[sys.argv.index("--input") + 1]
m = re.search(r"s(\d\.\d+)", path.replace("\\", "/").rsplit("/", 1)[-1])
if "modify" in path:
    open(path, "ab").write(b"x")
if not m:
    print(json.dumps({"engine": "fake", "version": "0", "state": "UNCERTAIN"}))
else:
    s = float(m.group(1))
    st = "DETECTED" if s >= 0.7 else "POSSIBLY_DETECTED" if s >= 0.5 else "NOT_DETECTED"
    print(json.dumps({"engine": "fake", "version": "0.1", "model_version": "m1", "state": st, "confidence": 0.8,
                      "score": s}))
'''


def fake_engine(tmp_path) -> SynthIDEngine:
    script = tmp_path / "fake_engine.py"
    script.write_text(FAKE_ENGINE, encoding="utf-8")
    return SynthIDEngine([sys.executable, str(script)], "test")


def img(path: Path, size=(32, 24)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(make_png(size=size))
    return path


# ---------------------------------------------------------------- source discovery / validation
def test_bundled_source_catalogue_is_valid_and_discoverable(tmp_path):
    sources, problems = SM.discover(tmp_path)
    assert not problems, problems
    ids = {s.source_id for s in sources}
    assert {"DEEPMIND-SYNTHID", "GOOGLE-SYNTHID-DETECTOR", "ARXIV-2510.09263", "GOOGLE-GEMINI-HELP"} <= ids
    assert all(s.url.startswith("https://") for s in sources)
    assert "| ID |" in SM.to_markdown(sources)
    doc = (ROOT / "docs" / "SYNTHID_RESEARCH_SOURCES.md").read_text(encoding="utf-8")
    for s in sources:  # every catalogued source is recorded in the documentation
        assert s.url in doc, s.url


def test_source_validation_rejects_bad_entries(tmp_path):
    bad = [{"source_id": "A1", "title": "x", "url": "http://example.org", "kind": "OFFICIAL", "publisher": "p",
            "accessed": "2026-10-02", "status": "VERIFIED", "relevance": "r"},
           {"source_id": "A2", "title": "x", "url": "https://u:p@example.org/", "kind": "OFFICIAL", "publisher": "p",
            "accessed": "2026-10-02", "status": "VERIFIED", "relevance": "r"},
           {"source_id": "A3", "title": "x", "url": "https://example.org/", "kind": "BLOG", "publisher": "p",
            "accessed": "yesterday", "status": "TRUSTED", "relevance": ""},
           {"source_id": "DEEPMIND-SYNTHID", "title": "dup", "url": "https://example.org/", "kind": "PAPER",
            "publisher": "p", "accessed": "2026-10-02", "status": "VERIFIED", "relevance": "r"},
           {"source_id": "OK-1", "title": "fine", "url": "https://example.org/x", "kind": "PAPER", "publisher": "p",
            "accessed": "2026-10-02", "status": "UNVERIFIED", "relevance": "r"}]
    (tmp_path / "synthid_sources.json").write_text(json.dumps({"sources": bad}), encoding="utf-8")
    sources, problems = SM.discover(tmp_path)
    ids = {s.source_id for s in sources}
    assert "OK-1" in ids and not ids & {"A1", "A2", "A3"}
    text = "\n".join(problems)
    for frag in ("https", "credentials", "unknown kind", "unknown status", "YYYY-MM-DD", "duplicate"):
        assert frag in text, frag


# ---------------------------------------------------------------- registry
def test_registry_specs_valid_and_honest():
    assert not [p for m in BASE_METHODS for p in validate_spec(m)]
    reg = MethodRegistry({"available": False})
    m1 = reg.get("SID-M1")
    assert m1.scientific_status == "UNAVAILABLE" and m1.validation_status == "NO ENGINE"
    for m in reg.all():
        for f in ("method_id", "method_name", "source", "version", "license", "local_only", "requires_gpu",
                  "requires_training", "requires_reference_images", "input_formats", "output", "scientific_status",
                  "validation_status"):
            assert hasattr(m, f)
        if not m.implemented:
            assert m.scientific_status == "UNAVAILABLE"
        if m.scientific_status == "AUTHORITATIVE":
            assert m.online  # nothing local is ever authoritative
    reg.update_engine({"available": True, "command": "x.exe", "origin": "configured"})
    assert reg.get("SID-M1").scientific_status == "UNVERIFIED"
    reg.update_engine({"available": True, "command": "x.exe"}, {"status": "COMPLETE", "run_id": "R", "auc_text": "0.9",
                                                                "n_scored": 10})
    assert reg.get("SID-M1").scientific_status == "RESEARCH" and "BENCHMARKED" in reg.get("SID-M1").validation_status
    with pytest.raises(KeyError):
        reg.get("NOPE")


# ---------------------------------------------------------------- local verifier adapter
def test_local_verifier_unavailable_without_engine(tmp_path):
    rec = LocalVerifier(SynthIDEngine()).verify(img(tmp_path / "a.png"))
    assert rec.state == "UNAVAILABLE" and rec.score is None and rec.input_unchanged
    assert rec.image_sha256 == hashlib.sha256((tmp_path / "a.png").read_bytes()).hexdigest()


def test_local_verifier_adapter_contract(tmp_path):
    v = LocalVerifier(fake_engine(tmp_path))
    det = v.verify(img(tmp_path / "s0.90_a.png"))
    assert (det.state, det.score, det.score_basis, det.model_version, det.detector) == (
        "DETECTED", 0.9, "engine score", "m1", "fake")
    assert v.verify(img(tmp_path / "s0.55_b.png")).state == "POSSIBLY DETECTED"
    assert v.verify(img(tmp_path / "s0.10_c.png")).state == "NOT DETECTED"
    unk = v.verify(img(tmp_path / "plain.png"))
    assert unk.state == "UNKNOWN" and unk.score is None
    bad = v.verify(img(tmp_path / "s0.90_modify.png"))
    assert bad.state == "INVALID" and not bad.input_unchanged and "INTEGRITY FAILURE" in bad.detail


# ---------------------------------------------------------------- benchmark metrics
def test_metrics_known_values():
    assert auc_mann_whitney([1, 1, 0, 0], [0.9, 0.4, 0.4, 0.1]) == pytest.approx(0.875)
    assert auc_mann_whitney([1, 0], [0.5, 0.5]) == pytest.approx(0.5)
    assert auc_mann_whitney([1, 1], [0.1, 0.2]) is None
    lo, hi = wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-4) and hi == pytest.approx(0.7634, abs=1e-4)
    c = confusion([1, 1, 1, 0, 0, 0], [0.9, 0.8, 0.3, 0.6, 0.2, 0.1], 0.5)
    assert (c["tp"], c["fp"], c["tn"], c["fn"]) == (2, 1, 2, 1)
    assert c["precision"] == pytest.approx(2 / 3) and c["f1"] == pytest.approx(2 / 3)
    roc = roc_curve([1, 0], [0.8, 0.2])
    assert roc[0][:2] == [0.0, 0.0] and roc[-1][:2] == [1.0, 1.0]
    ev = evaluate([1, 1, 1, 0, 0, 0], [0.9, 0.8, 0.3, 0.6, 0.2, 0.1], ["p", "p", "p", "real", "real", "gen"], seed=1)
    assert ev["metrics"]["auc"] == pytest.approx(8 / 9)
    lo, hi = ev["metrics"]["auc_ci95"]
    assert 0.0 <= lo <= ev["metrics"]["auc"] <= hi <= 1.0
    assert {g["group"]: g["kind"] for g in ev["groups"]} == {"p": "positive", "real": "negative", "gen": "negative"}
    assert evaluate([1, 0, 1, 0], [0.9, 0.1, 0.8, 0.2], seed=7)["metrics"]["auc_ci95"] == \
        evaluate([1, 0, 1, 0], [0.9, 0.1, 0.8, 0.2], seed=7)["metrics"]["auc_ci95"]  # seeded, reproducible


def _dataset(root: Path) -> Path:
    for n in ("s0.90_p1", "s0.80_p2", "s0.30_p3"):
        img(root / "positive" / f"{n}.png")
    img(root / "negative" / "real_controls" / "s0.60_n1.png")
    img(root / "negative" / "real_controls" / "s0.20_n2.png")
    img(root / "negative" / "other_generator" / "s0.10_n3.png")
    img(root / "negative" / "other_generator" / "unscored.png")
    return root


def test_dataset_loading_and_manifest_safety(tmp_path):
    items = load_dataset(_dataset(tmp_path / "ds"))
    assert len(items) == 7 and sum(i.label for i in items) == 3
    assert {i.group for i in items if i.label == 0} == {"real_controls", "other_generator"}
    assert all(i.split == "held-out" for i in items)
    (tmp_path / "ds" / "manifest.csv").write_text("path,label,group\n../outside.png,1,x\n", encoding="utf-8")
    img(tmp_path / "outside.png")
    with pytest.raises(ValueError):
        load_dataset(tmp_path / "ds")
    with pytest.raises(ValueError):
        load_dataset(tmp_path / "empty_missing")


def test_benchmark_with_engine_and_held_out_controls(tmp_path):
    items = load_dataset(_dataset(tmp_path / "ds"))
    res = run_benchmark(items, LocalVerifier(fake_engine(tmp_path)), threshold=0.5, seed=3)
    assert res.status == "COMPLETE" and res.n_scored == 6 and res.n_abstained == 1
    assert res.metrics["auc"] == pytest.approx(8 / 9)
    assert (res.metrics["tp"], res.metrics["fp"]) == (2, 1)
    groups = {g["group"]: g for g in res.groups}
    assert groups["real_controls"]["fpr"] == pytest.approx(0.5) and groups["other_generator"]["fpr"] == 0.0
    assert res.score_basis == ["engine score"]


def test_benchmark_unavailable_or_insufficient(tmp_path):
    items = [DatasetItem(str(img(tmp_path / "s0.9_a.png")), 1)]
    assert run_benchmark(items, LocalVerifier(SynthIDEngine())).status == "UNAVAILABLE"
    assert run_benchmark(items, LocalVerifier(fake_engine(tmp_path))).status == "INSUFFICIENT DATA"


# ---------------------------------------------------------------- research runs / serialization
def test_detection_run_preserves_original_and_serializes(tmp_path):
    src = img(tmp_path / "in" / "original.png", (64, 48))
    before = src.read_bytes()
    store, reg = ResearchStore(tmp_path / "sr"), MethodRegistry()
    r1 = store.run_detection([src], LocalVerifier(SynthIDEngine()), reg)
    r2 = store.run_detection([src], LocalVerifier(SynthIDEngine()), reg)
    assert RUN_ID_RE.match(r1.run_id) and re.fullmatch(r"SPX-SID-\d{8}-\d{6}", r1.run_id)
    assert int(r2.run_id[-6:]) == int(r1.run_id[-6:]) + 1
    assert r1.status == "UNAVAILABLE" and r1.original_unchanged is True and src.read_bytes() == before
    assert "nothing was inferred" in r1.detail
    d = store.run_dir(r1.run_id)
    for sub in ("source", "output", "metrics", "config", "logs"):
        assert (d / sub).is_dir()
    assert (d / r1.inputs[0]["copy"]).read_bytes() == before
    loaded = store.load(r1.run_id)
    assert loaded.to_dict() == r1.to_dict()
    for key in ("software", "os", "python", "gpu", "cuda_version", "libraries"):
        assert key in loaded.environment
    assert loaded.inputs[0]["sha256"] and loaded.inputs[0]["blake3"] is not None and loaded.seed == 0
    assert set(loaded.matrix[0]) == set(MATRIX_COLUMNS) and loaded.matrix[0]["LPIPS"] == "NOT COMPUTED"
    assert [r["run_id"] for r in store.list_runs()] == [r2.run_id, r1.run_id]
    with pytest.raises(Exception):
        store.run_dir("../../evil")


def test_detection_with_engine_and_condition_import(tmp_path, lab):
    store = ResearchStore(tmp_path / "sr")
    run = store.run_detection([img(tmp_path / "s0.80_x.png")], LocalVerifier(fake_engine(tmp_path)), MethodRegistry())
    assert run.status == "COMPLETE" and run.records[0]["state"] == "DETECTED" and run.model_version == "m1"
    L = lab()
    L["svc"].run(L["exp"], L["src"], "jpeg_reencode", {"quality": 80})
    store.import_conditions(run, L["exp"])
    row = store.load(run.run_id).matrix[-1]
    assert row["Method"] == "TRANSFORMATION" and row["Before"] == "UNAVAILABLE" and row["MAE"] not in (None, "-")


# ---------------------------------------------------------------- paper export
def test_paper_export_zip_hashes(tmp_path):
    store = ResearchStore(tmp_path / "sr")
    items = load_dataset(_dataset(tmp_path / "ds"))
    run = store.run_benchmark(items, LocalVerifier(fake_engine(tmp_path)), MethodRegistry(), seed=5)
    assert run.status == "COMPLETE" and run.original_unchanged is True
    z = export_paper_zip(store, run, tmp_path / "paper.zip")
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        for req in ("experiment/run.json", "experiment/config/parameters.json", "experiment/logs/run.log",
                    "experiment/metrics/benchmark.json", "experiment/hashes_sha256.txt", "experiment/hashes_blake3.txt"):
            assert req in names, req
        for ext in ("_paper.pdf", "_paper.png", "_paper.json", "_paper_matrix.csv", "_paper_metrics.csv"):
            assert any(n.startswith("experiment/report/") and n.endswith(ext) for n in names), ext
        sha = zf.read("experiment/hashes_sha256.txt").decode().splitlines()[1:]
        assert len(sha) >= 8
        for line in sha:
            digest, name = line.split("  ", 1)
            assert hashlib.sha256(zf.read("experiment/" + name)).hexdigest() == digest, name
        from app.core.hashing import BLAKE3_AVAILABLE, blake3_bytes

        if BLAKE3_AVAILABLE:
            for line in zf.read("experiment/hashes_blake3.txt").decode().splitlines()[1:]:
                digest, name = line.split("  ", 1)
                assert blake3_bytes(zf.read("experiment/" + name)) == digest, name
        csv_text = zf.read(next(n for n in names if n.endswith("_paper_matrix.csv"))).decode()
        assert csv_text.splitlines()[0] == "run_id," + ",".join(MATRIX_COLUMNS)
        assert zf.read(next(n for n in names if n.endswith(".pdf")))[:5] == b"%PDF-"


# ---------------------------------------------------------------- online-mode safeguards
def test_online_gate_off_by_default_and_requires_consent(tmp_path):
    opened = []
    gate = OnlineGate(opener=lambda url: opened.append(url) or True)
    p = img(tmp_path / "a.png")
    assert gate.enabled is False
    with pytest.raises(OnlinePolicyError):
        gate.plan("GEMINI-APP", p)
    with pytest.raises(OnlinePolicyError):
        gate.enable(confirmed=False)
    gate.enable(confirmed=True)
    plan = gate.plan("GEMINI-APP", p)
    assert plan.url == "https://gemini.google.com/" and plan.image_sha256 in plan.confirmation_text()
    assert "will NOT upload" in plan.confirmation_text()
    with pytest.raises(OnlinePolicyError):
        gate.execute(plan, consent=False)
    assert opened == []
    entry = gate.execute(plan, consent=True)
    assert opened == [plan.url] and entry["uploaded_by_synthprovenance"] is False
    gate.disable()
    with pytest.raises(OnlinePolicyError):
        gate.execute(plan, consent=True)
    assert len(opened) == 1


def test_online_destinations_are_official_https_only():
    for d in DESTINATIONS:
        check_destination(d)
        assert d.machine_api is False
    for bad in (Destination("X", "x", "x", "https://evil.example/upload", "a"),
                Destination("Y", "y", "y", "http://gemini.google.com/", "a"),
                Destination("Z", "z", "z", "https://gemini.google.com/", "a", machine_api=True)):
        with pytest.raises(OnlinePolicyError):
            check_destination(bad)


def test_local_mode_makes_no_network_request(tmp_path):
    """Full local research pipeline under the LOCAL-ONLY guard: zero network attempts, outbound still blocked."""
    code = f'''
import socket, sys
from pathlib import Path
sys.path.insert(0, {str(ROOT)!r})
from app.utils import netguard
netguard.install()
from app.core.synthetic import make_png
from app.core.synthid_engine import SynthIDEngine
from app.core.synthid_local_verifier import LocalVerifier
from app.core.synthid_detector_registry import MethodRegistry
from app.core.synthid_research_engine import ResearchStore
from app.core import synthid_source_manager as SM
from app.services.synthid_paper_export import export_paper_zip
tmp = Path({str(tmp_path)!r})
p = tmp / "x.png"; p.write_bytes(make_png(size=(40, 30)))
SM.discover(tmp)
st = ResearchStore(tmp / "sr")
run = st.run_detection([p], LocalVerifier(SynthIDEngine()), MethodRegistry())
export_paper_zip(st, run, tmp / "p.zip")
assert netguard.blocked_attempts() == [], netguard.blocked_attempts()
try:
    socket.create_connection(("203.0.113.5", 443), timeout=1)
except netguard.NetworkPolicyError:
    sys.exit(0)
sys.exit(3)
'''
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=180)
    assert r.returncode == 0, r.stderr.decode()[-2000:]


# ---------------------------------------------------------------- GUI
def test_research_lab_gui(fx):
    from PySide6.QtWidgets import QApplication
    from app.ui import theme
    from app.ui.controller import AppController
    from app.ui.main_window import MainWindow
    from app.ui.views.base import REFRESH_ERRORS

    app = QApplication.instance() or QApplication([])
    theme.apply(app)
    ctl = AppController()
    win = MainWindow(ctl, quiet=True)
    win.show()

    def wait():
        t = time.time()
        while ctl.busy or time.time() - t < 0.2:
            app.processEvents()
            time.sleep(0.01)
            assert time.time() - t < 120

    ctl.open_demo_fixture()
    wait()
    ctl.start_experiment()
    wait()
    win.go("SynthID Research Lab")
    view = win.views["SynthID Research Lab"]
    app.processEvents()
    assert [view.tabs.tabText(i) for i in range(view.tabs.count())] == [
        "Detection", "Local Methods", "Research Sources", "Benchmark", "Comparison", "Online Verification", "Experiments"]
    view.b_online.click()  # quiet mode never auto-confirms: must stay LOCAL
    app.processEvents()
    assert ctl.online.enabled is False and view.b_local.isChecked()
    original = ctl.research_image()
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    assert ctl.run_synthid_detection()
    wait()
    run = ctl.last_research_run
    assert run is not None and run.status == "UNAVAILABLE" and run.original_unchanged is True
    assert hashlib.sha256(original.read_bytes()).hexdigest() == digest
    view._do_refresh()
    assert view.r_run.value.text() == run.run_id and view.runs.rowCount() >= 1
    assert view.method.count() == len(BASE_METHODS)
    assert not REFRESH_ERRORS, REFRESH_ERRORS
    assert not win.errors, win.errors
    win.close()
