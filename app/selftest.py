"""Headless self-test used by the build verifier and by `SynthProvenance --self-test`.

Runs the real pipeline on deterministic fixtures in a temporary workspace and
writes a JSON result. Exit code 0 only when every check passes.
"""
from __future__ import annotations

import hashlib
import importlib
import io
import json
import os
import pkgutil
import platform
import socket
import sys
import tempfile
import time
import traceback
import zipfile
from pathlib import Path


def run_self_test(output: str | None = None) -> int:
    t0 = time.perf_counter()
    checks: list[dict] = []

    def check(name, fn):
        try:
            detail = fn()
            checks.append({"name": name, "passed": True, "detail": str(detail or "ok")[:500]})
        except Exception as exc:  # noqa: BLE001
            checks.append({"name": name, "passed": False, "detail": f"{type(exc).__name__}: {exc}",
                           "trace": traceback.format_exc()[-2000:]})

    tmp = tempfile.mkdtemp(prefix="synthprovenance_selftest_")
    os.environ["SYNTHPROVENANCE_HOME"] = tmp
    import app
    from app.utils import netguard

    netguard.install()

    def imports():
        n = 0
        for m in pkgutil.walk_packages(app.__path__, "app."):
            if m.name.startswith("app.ui") and os.environ.get("QT_QPA_PLATFORM") is None and sys.platform.startswith("linux") \
                    and not os.environ.get("DISPLAY"):
                os.environ["QT_QPA_PLATFORM"] = "offscreen"
            importlib.import_module(m.name)
            n += 1
        return f"{n} modules imported"
    check("imports", imports)

    def network_blocked():
        try:
            socket.create_connection(("203.0.113.7", 9), timeout=1)
        except netguard.NetworkPolicyError:
            return "outbound connection blocked by LOCAL-ONLY guard"
        raise AssertionError("network connection was not blocked")
    check("local_only_network_guard", network_blocked)

    from app.core.audit_engine import AuditLog
    from app.core.experiment_engine import Workspace
    from app.core.image_loader import open_image_bytes, to_array
    from app.core.metadata_engine import analyze_bytes
    from app.core.pixel_integrity import compare_images
    from app.core.synthetic import all_fixtures, pattern
    from app.core.synthid_engine import SynthIDEngine
    from app.analyzers.synthid_analyzer import analyze_synthid
    from app.services.export_service import export_bundle
    from app.services.transformation_service import SourceContext, TransformationService

    fx = all_fixtures()
    state: dict = {}

    def baseline():
        a = analyze_bytes(fx["fixture_ai_c2pa.jpg"], "", "fixture_ai_c2pa.jpg")
        assert a.c2pa.present and a.c2pa.hard_binding == "MATCH", a.c2pa.summary
        assert a.signal.state == "OBSERVED", a.signal.state
        state["a"] = a
        return f"C2PA {a.c2pa.hard_binding}, signal {a.signal.state}, {len(a.groups)} groups"
    check("baseline_analysis_c2pa", baseline)

    def pipeline():
        ws, audit, eng = Workspace(), AuditLog(), SynthIDEngine.discover()
        a = state["a"]
        ad = a.to_dict()
        exp = ws.create("fixture_ai_c2pa.jpg", fx["fixture_ai_c2pa.jpg"], baseline=ad)
        audit.bind(exp.experiment_id, ws.audit_path(exp))
        sid = analyze_synthid(eng, ws.original_file(exp), "ORIGINAL", ad).to_dict()
        assert sid["state"] in ("UNAVAILABLE", "DETECTED", "NOT DETECTED", "UNKNOWN", "INVALID")
        exp.synthid_baseline = sid
        svc = TransformationService(ws, audit, eng)
        src = SourceContext(ws.original_file(exp), a, ad, sid)
        r1 = svc.run(exp, src, "metadata_sanitize", {"mode": "METADATA-ONLY", "profile": "MAXIMUM PRIVACY"})
        assert r1.status == "COMPLETE" and r1.pixel_metrics["verdict"] == "PIXEL-EXACT", r1.error
        assert r1.pixel_metrics["changed_pixels"] == 0
        assert r1.provenance_differences["c2pa_after"] == "ABSENT"
        r2 = svc.run(exp, src, "c2pa_separation", {})
        assert r2.pixel_metrics["verdict"] == "PIXEL-EXACT"
        r3 = svc.run(exp, src, "jpeg_reencode", {"quality": 70})
        assert r3.pixel_metrics["verdict"] == "TRANSFORMATION DETECTED"
        for fmt, mode in (("PNG", "LOSSLESS"), ("JPEG", "LOSSY"), ("WEBP", "LOSSLESS"), ("TIFF", "LOSSLESS"), ("BMP", "LOSSLESS")):
            r = svc.run(exp, src, "format_conversion", {"format": fmt, "compression": mode})
            assert r.status == "COMPLETE" and r.output_format == fmt, (fmt, r.error)
            if mode == "LOSSLESS":
                assert r.pixel_metrics["verdict"] == "PIXEL-EXACT", (fmt, r.pixel_metrics["verdict"])
        state.update(ws=ws, audit=audit, exp=exp, eng=eng)
        return f"{len(exp.transformations)} transformations; metadata-only changed_pixels=0; 5 export formats"
    check("transformation_pipeline", pipeline)

    def high_res():
        img = pattern(3000, 2000)
        buf = io.BytesIO()
        img.save(buf, "PNG", compress_level=1)
        a = open_image_bytes(buf.getvalue())
        assert a.size == (3000, 2000)
        r = compare_images(a, img)
        assert r.verdict == "PIXEL-EXACT"
        assert to_array(a).shape == (2000, 3000, 3)
        return "6 MP loaded at full resolution and verified"
    check("high_resolution", high_res)

    def reports_and_bundle():
        ws, exp = state["ws"], state["exp"]
        dest = ws.exports_dir / f"{exp.experiment_id}_experiment.zip"
        export_bundle(exp, ws, state["audit"], dest, state["eng"].status())
        with zipfile.ZipFile(dest) as zf:
            names = zf.namelist()
            for req in ("experiment/experiment.json", "experiment/hashes.txt", "experiment/metadata/metadata.json",
                        "experiment/provenance/provenance.json", "experiment/synthid/synthid.json",
                        "experiment/metrics/metrics.json", "experiment/logs/audit.log"):
                assert req in names, req
            for ext in (".pdf", ".json", ".csv", ".html", ".png"):
                assert any(n.startswith("experiment/report/") and n.endswith(ext) for n in names), ext
            hashes = zf.read("experiment/hashes.txt").decode().splitlines()[1:]
            for line in hashes:
                digest, name = line.split("  ", 1)
                assert hashlib.sha256(zf.read("experiment/" + name)).hexdigest() == digest, name
        return f"{len(names)} bundle files, {len(hashes)} hashes verified"
    check("reports_and_bundle", reports_and_bundle)

    def synthid_research_lab():
        from app.core import synthid_source_manager as SM
        from app.core.synthid_benchmark import evaluate
        from app.core.synthid_detector_registry import BASE_METHODS, MethodRegistry, validate_spec
        from app.core.synthid_local_verifier import LocalVerifier
        from app.core.synthid_online import DESTINATIONS, OnlineGate, OnlinePolicyError, check_destination
        from app.core.synthid_research_engine import RUN_ID_RE, ResearchStore
        from app.services.synthid_paper_export import export_paper_zip

        attempts0 = len(netguard.blocked_attempts())  # the guard probe above already recorded one deliberate attempt
        assert not [p for m in BASE_METHODS for p in validate_spec(m)]
        sources, problems = SM.discover(None)
        assert sources and not problems, problems
        ev = evaluate([1, 1, 0, 0], [0.9, 0.4, 0.4, 0.1], seed=1)["metrics"]
        assert abs(ev["auc"] - 0.875) < 1e-12, ev["auc"]
        ws = state["ws"]
        src = ws.original_file(state["exp"])
        before = hashlib.sha256(src.read_bytes()).hexdigest()
        store = ResearchStore(ws.root / "synthid_research")
        run = store.run_detection([src], LocalVerifier(state["eng"]), MethodRegistry(state["eng"].status()))
        assert RUN_ID_RE.match(run.run_id) and run.original_unchanged is True
        assert hashlib.sha256(src.read_bytes()).hexdigest() == before
        if not state["eng"].available:
            assert run.status == "UNAVAILABLE" and run.records[0]["state"] == "UNAVAILABLE"
        dest = export_paper_zip(store, run, ws.exports_dir / f"{run.run_id}_paper.zip")
        with zipfile.ZipFile(dest) as zf:
            lines = zf.read("experiment/hashes_sha256.txt").decode().splitlines()[1:]
            for line in lines:
                digest, name = line.split("  ", 1)
                assert hashlib.sha256(zf.read("experiment/" + name)).hexdigest() == digest, name
            assert any(n.endswith("_paper.pdf") for n in zf.namelist())
        gate = OnlineGate(opener=lambda url: (_ for _ in ()).throw(AssertionError("opener must not run")))
        assert gate.enabled is False
        try:
            gate.plan("GEMINI-APP", src)
            raise AssertionError("online plan allowed while OFF")
        except OnlinePolicyError:
            pass
        for d in DESTINATIONS:
            check_destination(d)
        assert len(netguard.blocked_attempts()) == attempts0, netguard.blocked_attempts()[attempts0:]
        return (f"{len(BASE_METHODS)} methods, {len(sources)} sources validated, {run.run_id} {run.status}, original "
                f"unchanged, paper ZIP {len(lines)} hashes verified, online OFF by default, 0 network attempts")
    check("synthid_research_lab", synthid_research_lab)

    def fingerprint_lab():
        from app.core.fingerprint_lab import FingerprintLab
        from app.research import taxonomy as TAX
        from app.research import library as LIB
        from app.research.methods import MethodRegistry, validate
        from app.research.surrogate import SurrogateConfig
        from app.services.fingerprint_paper_export import export_fingerprint_zip

        attempts0 = len(netguard.blocked_attempts())
        assert validate() == []
        reg = MethodRegistry()
        assert len(reg.all()) == 64 and len(reg.ready()) >= 40
        assert len(TAX.load()["entries"]) >= 100 and len(LIB.all_items()) >= 60
        ws = state["ws"]
        src = ws.original_file(state["exp"])
        before = hashlib.sha256(src.read_bytes()).hexdigest()
        lab = FingerprintLab(ws.root / "fingerprint_research")
        r_desc = lab.run_method("Method 13", [src])          # descriptive FFT
        r_sep = lab.run_method("Method 34", [src], surrogate_cfg=SurrogateConfig(family="spatial", strength=4.0))
        assert r_desc.status == "COMPLETE" and r_desc.original_unchanged is True
        assert r_sep.status in ("COMPLETE", "SIGNAL PERSISTED") and r_sep.original_unchanged is True
        assert r_sep.result["ground_truth"].get("candidate_vs_known_corr") is not None
        assert hashlib.sha256(src.read_bytes()).hexdigest() == before
        dest = export_fingerprint_zip(lab, lab.load(r_sep.run_id), ws.exports_dir / f"{r_sep.run_id}_paper.zip")
        with zipfile.ZipFile(dest) as zf:
            lines = zf.read("experiment/hashes_sha256.txt").decode().splitlines()[1:]
            for line in lines:
                digest, name = line.split("  ", 1)
                assert hashlib.sha256(zf.read("experiment/" + name)).hexdigest() == digest, name
            assert any(n.endswith("_paper.pdf") for n in zf.namelist())
        assert len(netguard.blocked_attempts()) == attempts0, netguard.blocked_attempts()[attempts0:]
        return (f"{len(reg.ready())}/{len(reg.all())} methods ready, {len(TAX.load()['entries'])} taxonomy entries, "
                f"{len(LIB.all_items())} references, {r_sep.run_id} {r_sep.status}, original unchanged, "
                f"paper ZIP {len(lines)} hashes verified, 0 network attempts")
    check("fingerprint_research_lab", fingerprint_lab)

    def v4_integration():
        from app.core.method_composer import preset, run_pipeline
        from app.core.research_assistant import GOALS, ResearchAssistant
        from app.core.unified_signal_decomposition import CapabilityError, UnifiedSignalDecomposition
        from app.i18n import LANG_CODES, Translator
        from app.research import procedural as PROC
        from app.research import surrogate as SUR
        from app.research.imaging import luminance
        from app.research.methods import MethodRegistry, validate

        assert validate() == [] and len(MethodRegistry().all()) == 64
        clean = PROC.scene(160, 192, seed=5)
        cfg = SUR.SurrogateConfig(family="wavelet", strength=4.0)
        img = SUR.embed(clean, cfg).watermarked
        u = UnifiedSignalDecomposition()
        sep = u.separate(img, "Method 35", surrogate=cfg, clean=clean)
        assert sep.decomposition.content_estimate is not None and sep.decomposition.signal_estimate is not None
        try:
            u.separate(img, "Method 13")
            raise AssertionError("detector allowed to separate")
        except CapabilityError:
            pass
        known = luminance(img) - luminance(clean)
        comp = run_pipeline(img, preset("residual_wavelet_pca"), known)
        assert comp.status == "COMPLETE" and comp.stages
        adv = ResearchAssistant().advise("Find Fingerprint", {"format": "PNG"}, has_ground_truth=True)
        assert adv.recommendations
        assert len(LANG_CODES) == 30 and Translator("ar").rtl and Translator("id").t("nav.Settings") == "Pengaturan"
        return (f"64 methods, unified decomposition + capability guard OK, composer {len(comp.stages)} stages, "
                f"{len(GOALS)} goals, 30 languages (id/ar verified)")
    check("v4_integration", v4_integration)

    passed = all(c["passed"] for c in checks)
    result = {"passed": passed, "version": app.__version__, "python": sys.version.split()[0],
              "platform": platform.platform(), "frozen": bool(getattr(sys, "frozen", False)),
              "duration_s": round(time.perf_counter() - t0, 2), "checks": checks}
    text = json.dumps(result, indent=2)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text, encoding="utf-8")
    try:
        print(text)
    except Exception:  # noqa: BLE001 - windowed builds may have no usable stdout
        pass
    return 0 if passed else 1
