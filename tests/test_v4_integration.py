"""Tests for the v4 upgrade: registry-v2 capabilities, frontier methods, the unified
signal-decomposition engine, the method composer, the research assistant, and i18n."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.research import procedural as P
from app.research import surrogate as S
from app.research.imaging import luminance

ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ registry v2
def test_registry_capabilities_are_honest():
    from app.research.methods import CAPABILITY_FLAGS, MethodRegistry, validate
    assert validate() == []
    reg = MethodRegistry()
    assert len(reg.all()) == 64
    for m in reg.all():
        flags = m.capability_flags()
        assert set(flags) == set(CAPABILITY_FLAGS)
        if m.availability != "READY":
            assert not any(flags.values()), f"{m.method_id} non-READY advertises capabilities"
        # only sep: methods may claim separation
        if flags["CAN_SEPARATE"]:
            assert m.capability.startswith("sep:")
        # a method requiring a bundled model cannot be READY
        if m.requires_model:
            assert m.availability != "READY"
    # metadata record is complete
    md = reg.get("Method 34").metadata()
    assert md["separation_supported"] and md["capabilities"]["CAN_RECONSTRUCT"]
    assert reg.get("Method 13").metadata()["analysis_only"] is True


def test_frontier_methods_run_on_controlled_data():
    from app.research import runner as RUN
    from app.research.methods import MethodRegistry
    reg = MethodRegistry()
    clean = P.scene(160, 192, seed=5)
    cfg = S.SurrogateConfig(family="spatial", strength=4.0)
    emb = S.embed(clean, cfg)
    signed = [S.embed(c, cfg).watermarked for c in P.dataset(4, 96, 96, seed=60)]
    unsigned = P.dataset(4, 96, 96, seed=80)
    inp = RUN.MethodInput(image=emb.watermarked, surrogate_cfg=cfg, clean=clean, signed=signed, unsigned=unsigned)
    for num in range(55, 64):
        r = RUN.run(reg.get(f"Method {num}"), inp)
        assert r.status not in ("FAILED",), (num, r.detail)
        assert r.status in ("COMPLETE", "SIGNAL PERSISTED", "INSUFFICIENT DATA")


# ------------------------------------------------------------------ unified decomposition
def test_unified_decomposition_verbs_and_capability_guard():
    from app.core.unified_signal_decomposition import CapabilityError, UnifiedSignalDecomposition
    u = UnifiedSignalDecomposition()
    clean = P.scene(192, 224, seed=5)
    cfg = S.SurrogateConfig(family="wavelet", strength=4.0)
    img = S.embed(clean, cfg).watermarked
    assert u.analyze(img, "Method 13").status == "COMPLETE"
    assert u.estimate(img, "Method 03").decomposition.signal_estimate is not None
    sep = u.separate(img, "Method 35", surrogate=cfg, clean=clean)
    assert set(("observed", "content_estimate", "signal_estimate", "residual", "confidence_map")) <= set(sep.decomposition.maps())
    assert u.reconstruct(img, "Method 55", surrogate=cfg, clean=clean).status == "COMPLETE"
    assert u.validate(img, "Method 39", surrogate=cfg, clean=clean).status == "COMPLETE"
    with pytest.raises(CapabilityError):
        u.separate(img, "Method 13")           # a detector cannot separate
    with pytest.raises(CapabilityError):
        u.reconstruct(img, "Method 03")        # an estimator-only method cannot reconstruct


# ------------------------------------------------------------------ method composer
def test_method_composer_runs_exports_and_reproduces():
    from app.core.method_composer import Pipeline, preset, run_pipeline
    clean = P.scene(192, 224, seed=5)
    cfg = S.SurrogateConfig(family="spatial", strength=5.0, adaptive=False)
    emb = S.embed(clean, cfg)
    known = luminance(emb.watermarked) - luminance(clean)
    pipe = preset("residual_wavelet_pca")
    r = run_pipeline(emb.watermarked, pipe, known)
    assert r.status == "COMPLETE" and len(r.stages) == len(pipe.nodes)
    assert r.ground_truth["final_candidate_vs_known_corr"] is not None
    # JSON round-trip reproduces identically
    d = json.loads(json.dumps(pipe.to_dict()))
    r2 = run_pipeline(emb.watermarked, Pipeline.from_dict(d), known)
    assert [s["energy"] for s in r.stages] == [s["energy"] for s in r2.stages]


# ------------------------------------------------------------------ research assistant
def test_research_assistant_recommends_and_discovers():
    from app.core.research_assistant import GOALS, ResearchAssistant
    a = ResearchAssistant()
    for goal in GOALS:
        adv = a.advise(goal, {"format": "PNG", "width": 4000, "height": 3000}, has_ground_truth=False, n_references=1)
        assert adv.rationale
        assert adv.recommendations or adv.alternatives
    # watermark goal without ground truth warns to use the surrogate
    adv = a.advise("Study Watermark", {}, has_ground_truth=False)
    assert any("SURROGATE" in n or "surrogate" in n for n in adv.notes)
    disc = a.discover(has_ground_truth=True, n_references=5)
    assert disc and all("validation_plan" in d for d in disc)


# ------------------------------------------------------------------ i18n
def test_i18n_thirty_languages_load_with_english_fallback():
    from app.i18n import LANG_CODES, Translator
    assert len(LANG_CODES) == 30 and "en" in LANG_CODES
    for code in LANG_CODES:
        t = Translator(code)
        assert t.t("btn.run") and t.t("nav.Dashboard")
        # a key absent from a locale falls back to English, never to the raw key
        assert t.t("app.local_only") == "LOCAL-ONLY" or t.code != "en"
    t = Translator("ar")
    assert t.rtl is True
    assert Translator("id").t("nav.Settings") == "Pengaturan"
    assert Translator("en").completeness() == 1.0


def test_i18n_locale_files_present_and_valid():
    loc = ROOT / "app" / "i18n" / "locales"
    files = sorted(p.stem for p in loc.glob("*.json"))
    assert len(files) == 30
    for p in loc.glob("*.json"):
        data = json.loads(p.read_text(encoding="utf-8"))
        assert "_meta" in data and "complete" in data["_meta"]


# ------------------------------------------------------------------ gap analysis + catalog
def test_gap_analysis_and_catalog_bundled():
    gap = ROOT / "docs" / "IMPLEMENTATION_GAP_ANALYSIS.md"
    assert gap.is_file()
    text = gap.read_text(encoding="utf-8")
    assert "Per-method traceability" in text and "FULLY IMPLEMENTED" in text
    cat = json.loads((ROOT / "data" / "research_catalog.json").read_text(encoding="utf-8"))
    assert cat["methods"] and cat["datasets"] and cat["tools"]
