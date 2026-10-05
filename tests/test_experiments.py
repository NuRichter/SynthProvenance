import json
import re
import sys
import zipfile

import pytest

from app.core.experiment_engine import Workspace
from app.core.synthid_engine import SynthIDEngine
from app.analyzers.synthid_analyzer import compare_synthid
from app.models.synthid import UNAVAILABLE_REASON
from app.services.export_service import export_bundle
from app.services.report_service import write_all
from app.services.transformation_service import experiment_matrix


def test_experiment_ids_sequential(tmp_path):
    ws = Workspace(tmp_path)
    a = ws.create("a.png", b"x").experiment_id
    b = ws.create("b.png", b"y").experiment_id
    assert re.fullmatch(r"SPX-\d{4}-\d{4}-\d{6}", a)
    assert int(b[-6:]) == int(a[-6:]) + 1
    assert ws.load(a).input_name == "a.png"
    for sub in ("experiments", "reports", "cache", "logs", "exports"):
        assert (tmp_path / sub).is_dir()


def test_battery_and_matrix(lab):
    L = lab()
    recs = L["svc"].run_battery(L["exp"], L["src"], {"mode": "METADATA-ONLY", "profile": "MAXIMUM PRIVACY"})
    assert all(r.status == "COMPLETE" for r in recs)
    by = {r.operation: r for r in recs}
    assert by["metadata_sanitize"].pixel_metrics["changed_pixels"] == 0
    assert by["c2pa_separation"].pixel_metrics["verdict"] == "PIXEL-EXACT"
    assert any(f.startswith("DIMENSION CHANGE DETECTED") for f in by["resize"].flags)
    layers = {x["layer"]: x for x in by["metadata_sanitize"].layers}
    assert layers["C2PA"]["state"] == "REMOVED" and layers["SynthID"]["state"] == "UNAVAILABLE"
    for x in by["jpeg_reencode"].layers:
        assert set(x) >= {"observation", "method", "condition", "limitation"}
    rows = {r["row"]: r for r in experiment_matrix(L["exp"])}
    assert rows["METADATA SANITIZED"]["cells"]["Pixels"][0] == "\u2713"
    assert rows["JPEG RE-ENCODE"]["cells"]["Pixels"][0] == "ALTERED"
    assert rows["RESIZE"]["cells"]["Resolution"][0] == "\u2715"
    assert rows["ORIGINAL"]["cells"]["SynthID"][0] == "UNAVAILABLE"
    assert L["ws"].original_file(L["exp"]).read_bytes() == L["src"].data  # original never modified


def test_refused_and_failed_are_recorded(lab, fx):
    L = lab("fixture_16bit.png")
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.open(io.BytesIO(fx["fixture_plain.png"])).save(buf, "TIFF")
    L2 = lab("x.tif", buf.getvalue())
    r = L2["svc"].run(L2["exp"], L2["src"], "metadata_sanitize", {"profile": "BALANCED"})
    assert r.status == "REFUSED" and "re-encoding" in r.error
    r2 = L["svc"].run(L["exp"], L["src"], "format_conversion", {"format": "TIFF", "source": "T999"})
    assert r2.status == "FAILED"


def test_format_chain_and_external(lab, tmp_path, fx):
    L = lab()
    r = L["svc"].run(L["exp"], L["src"], "format_chain", {"steps": "PNG > JPEG:LOSSY:85 > PNG"})
    assert r.status == "COMPLETE" and len(r.steps) == 3
    assert r.steps[0]["vs_original"]["verdict"] == "PIXEL-EXACT"
    assert r.steps[1]["vs_original"]["verdict"] == "TRANSFORMATION DETECTED"
    ext = tmp_path / "roundtrip.png"
    ext.write_bytes(fx["fixture_plain.png"])
    r2 = L["svc"].run(L["exp"], L["src"], "external_comparison", {"path": str(ext)})
    assert r2.status == "COMPLETE" and r2.parameters["file_name"] == "roundtrip.png"


def test_audit_log_and_carry(tmp_path):
    from app.core.audit_engine import AuditLog, read_jsonl

    log = AuditLog()
    log.log("IMAGE LOADED")
    log.bind("SPX-2026-0101-000001", tmp_path / "a.jsonl", carry_unbound=True)
    log.log("TRANSFORMATION STARTED")
    evs = read_jsonl(tmp_path / "a.jsonl")
    assert [e.event for e in evs] == ["IMAGE LOADED", "TRANSFORMATION STARTED"]
    assert all(e.experiment_id == "SPX-2026-0101-000001" for e in evs)


def test_synthid_unavailable_is_honest(tmp_path):
    eng = SynthIDEngine.discover(None)
    assert not eng.available
    res = eng.analyze(tmp_path / "x.png")
    assert res.state == "UNAVAILABLE" and res.detail == UNAVAILABLE_REASON


def _fake_engine(tmp_path, state):
    script = tmp_path / f"engine_{state}.py"
    script.write_text("import json,sys\nprint(json.dumps({'engine':'fake','version':'0','state':%r,'confidence':0.9}))\n" % state)
    return SynthIDEngine([sys.executable, str(script)], "test")


def test_synthid_engine_contract_and_no_removal_claim(tmp_path):
    img = tmp_path / "x.png"
    img.write_bytes(b"\x89PNG")
    det = _fake_engine(tmp_path, "DETECTED").analyze(img).to_dict()
    nd = _fake_engine(tmp_path, "NOT_DETECTED").analyze(img).to_dict()
    assert det["state"] == "DETECTED" and nd["state"] == "NOT DETECTED" and det["confidence"] == 0.9
    c = compare_synthid(det, nd, "T001")
    assert c["state"] == "NOT DETECTED" and "not verified removal" in c["observation"]
    for b in (det, nd):
        for a in (det, nd):
            assert compare_synthid(b, a, "T")["state"] != "REMOVED"
    bad = tmp_path / "bad.py"
    bad.write_text("print('garbage')\n")
    assert SynthIDEngine([sys.executable, str(bad)]).analyze(img).state == "INVALID"


def test_reports_and_bundle(lab, tmp_path):
    L = lab()
    L["svc"].run(L["exp"], L["src"], "metadata_sanitize", {"profile": "BALANCED"})
    L["svc"].run(L["exp"], L["src"], "format_conversion", {"format": "WEBP", "compression": "LOSSY", "quality": 70})
    paths = write_all(L["exp"], tmp_path / "rep", L["audit"].events())
    assert paths["pdf"].read_bytes().startswith(b"%PDF")
    assert paths["png"].read_bytes().startswith(b"\x89PNG")
    rep = json.loads(paths["json"].read_text())
    titles = [s["title"] for s in rep["sections"]]
    for t in ("C2PA Findings", "SynthID Findings", "Format Conversion Results", "Observable Signal Changes", "Audit Log"):
        assert any(t in x for x in titles)
    txt = paths["json"].read_text()
    assert "is now non-AI" not in txt and "does not establish whether the image is AI-generated" in txt
    z = export_bundle(L["exp"], L["ws"], L["audit"], tmp_path / "e.zip")
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        assert "experiment/synthid/synthid.json" in names and "experiment/hashes.txt" in names
        assert all(n.startswith("experiment/") and ".." not in n for n in names)
