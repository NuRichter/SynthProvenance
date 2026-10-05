"""Tests for the fingerprint research engine (numpy core): transforms, surrogate ground
truth, separation recovery, consensus, methods registry and the lab run store."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from app.research import consensus as C
from app.research import dct as D
from app.research import procedural as P
from app.research import spectral as S
from app.research import surrogate as SUR
from app.research import wavelet as W
from app.research.imaging import as_float, luminance


# ------------------------------------------------------------------ transforms
def test_wavelet_perfect_reconstruction():
    rng = np.random.default_rng(0)
    for shape in [(64, 64), (63, 77), (128, 96)]:
        x = rng.random(shape)
        for wv in ("haar", "db2"):
            dec = W.wavedec2(x, 3, wv)
            assert np.abs(x - W.waverec2(dec)).max() < 1e-9


def test_dct_perfect_reconstruction_and_jpeg_quality():
    import io
    from PIL import Image
    rng = np.random.default_rng(1)
    x = rng.random((64, 48)) * 255
    c = D.block_dct(x)
    assert np.abs(x - D.block_idct(c)).max() < 1e-8
    img = Image.fromarray((rng.random((64, 64, 3)) * 255).astype("uint8"))
    b = io.BytesIO()
    img.save(b, "JPEG", quality=83)
    b.seek(0)
    j = Image.open(b)
    j.load()
    q = D.estimate_quality(D.jpeg_tables(j)[0])
    assert q["quality"] == 83 and q["standard_ijg_tables"]


def test_fft_detects_periodic_peak():
    rng = np.random.default_rng(2)
    yy, xx = np.mgrid[0:256, 0:256]
    p = 0.5 + 0.1 * np.cos(np.pi * xx / 2) + 0.01 * rng.standard_normal((256, 256))
    a = S.analyse(p.astype(np.float32))
    assert a["peaks"]["n_peaks"] >= 1
    assert any(abs(pk["fx"]) > 0.4 for pk in a["peaks"]["peaks"])


# ------------------------------------------------------------------ surrogate ground truth
@pytest.mark.parametrize("family", SUR.AVAILABLE_FAMILIES)
def test_surrogate_detects_own_signal_and_rejects_clean_and_wrong_key(family):
    img = P.scene(192, 224, seed=11)
    cfg = SUR.SurrogateConfig(family=family, strength=4.0)
    emb = SUR.embed(img, cfg)
    rms = float(np.sqrt(((emb.watermarked - img) ** 2).mean())) * 255.0
    assert rms < 6.0                                          # RMS near the 4.0 target, low-amplitude
    assert np.abs(emb.watermarked - img).max() < 0.3          # no gross change at any pixel
    d_wm = SUR.detect(emb.watermarked, cfg)
    d_clean = SUR.detect(img, cfg)
    d_wrong = SUR.detect(emb.watermarked, SUR.SurrogateConfig(family=family, key=999, strength=4.0))
    assert d_wm.detected, (family, d_wm.score)
    assert not d_clean.detected, (family, d_clean.score)
    assert not d_wrong.detected, (family, d_wrong.score)
    if family == "multi_bit":
        assert d_wm.bit_accuracy == 1.0


def test_surrogate_neural_is_unavailable_not_faked():
    with pytest.raises(SUR.SurrogateUnavailable):
        SUR.embed(P.scene(64, 64), SUR.SurrogateConfig(family="neural"))


def test_surrogate_null_distribution_is_calibrated():
    img = P.scene(192, 192, seed=3)
    scores = [SUR.detect(img, SUR.SurrogateConfig(family="spatial", key=k)).score for k in range(200)]
    assert abs(np.mean(scores)) < 0.4 and 0.7 < np.std(scores) < 1.4
    assert np.max(scores) < SUR.DEFAULT_THRESHOLD_Z  # no false positive over 200 random keys


# ------------------------------------------------------------------ separation recovers the known signal
def test_separation_recovers_known_signal():
    from app.research import separation as SEP
    clean = P.scene(256, 320, seed=5)
    cfg = SUR.SurrogateConfig(family="spatial", strength=5.0, adaptive=False)
    emb = SUR.embed(clean, cfg)
    r = SEP.separate(emb.watermarked, "highpass", surrogate_cfg=cfg, clean=clean)
    assert r.ground_truth["candidate_vs_known_corr"] > 0.4
    assert r.reconstruction["psnr_db"] > 28


# ------------------------------------------------------------------ cross-image consensus with ground truth
def test_cross_image_consensus_separates_shared_signal_from_unrelated():
    imgs = P.dataset(8, 160, 160, seed=20)
    unrelated = C.cross_image_consensus(imgs)
    cfg = SUR.SurrogateConfig(family="spatial", strength=5.0, adaptive=False)
    shared = C.cross_image_consensus([SUR.embed(x, cfg).watermarked for x in imgs])
    assert unrelated["held_out_minus_control"] < 0.1
    assert shared["held_out_minus_control"] > 0.3


# ------------------------------------------------------------------ robustness measurement
def test_robustness_persistence_decreases_with_severity():
    from app.research import robustness as R
    img = P.scene(192, 192, seed=7)
    cfg = SUR.SurrogateConfig(family="spatial", strength=4.0)
    emb = SUR.embed(img, cfg)
    res = R.sweep(emb.watermarked, cfg, kinds=("jpeg",))
    jpeg = [r for r in res["rows"] if r["kind"] == "jpeg"]
    persistences = [r["persistence"] for r in jpeg]
    assert persistences[0] >= persistences[-1]  # higher quality keeps more signal than lower quality


# ------------------------------------------------------------------ methods registry
def test_methods_registry_is_valid_and_honest():
    from app.research import methods as M
    assert M.validate() == []
    reg = M.MethodRegistry()
    assert len(reg.all()) == 64
    for m in reg.all():
        if m.availability == "READY":
            assert m.capability
        else:
            assert m.reason, m.method_id
        if m.requires_model:
            assert m.availability != "READY"
    # detector-evasion methods are deliberately not implemented
    for num in (43, 44, 45, 46):
        assert reg.get(f"Method {num:02d}").availability == "NOT_IMPLEMENTED"


def test_runner_runs_all_ready_methods_without_error():
    from app.research import runner as RUN
    from app.research.methods import MethodRegistry
    reg = MethodRegistry()
    clean = P.scene(160, 192, seed=9)
    cfg = SUR.SurrogateConfig(family="spatial", strength=4.0)
    emb = SUR.embed(clean, cfg)
    refs = P.dataset(5, 160, 192, seed=40)
    signed = [SUR.embed(c, cfg).watermarked for c in P.dataset(4, 96, 96, seed=60)]
    unsigned = P.dataset(4, 96, 96, seed=80)
    inp = RUN.MethodInput(image=emb.watermarked, references=refs, surrogate_cfg=cfg, clean=clean, signed=signed,
                          unsigned=unsigned)
    ready_statuses = set()
    for m in reg.all():
        r = RUN.run(m, inp)
        assert r.status != "FAILED", (m.method_id, r.detail)
        if m.availability == "READY":
            ready_statuses.add(r.status)
        elif m.availability == "UNAVAILABLE":
            assert r.status == "UNAVAILABLE"
        else:
            assert r.status == "NOT IMPLEMENTED"
    assert "COMPLETE" in ready_statuses


# ------------------------------------------------------------------ lab run store
def test_fingerprint_lab_preserves_original_and_exports(tmp_path):
    from app.core.fingerprint_lab import FingerprintLab
    from app.research.imaging import from_float
    from app.services.fingerprint_paper_export import export_fingerprint_zip
    img = tmp_path / "scene.png"
    from_float(P.scene(192, 224, seed=2)).save(img)
    before = hashlib.sha256(img.read_bytes()).hexdigest()
    lab = FingerprintLab(tmp_path / "fp")
    run = lab.run_method("Method 34", [img], surrogate_cfg=SUR.SurrogateConfig(family="spatial", strength=4.0))
    assert run.status in ("COMPLETE", "SIGNAL PERSISTED")
    assert run.original_unchanged is True
    assert hashlib.sha256(img.read_bytes()).hexdigest() == before
    assert run.maps and (lab.run_dir(run.run_id) / run.maps[0]["file"]).is_file()
    z = tmp_path / "paper.zip"
    export_fingerprint_zip(lab, lab.load(run.run_id), z)
    import zipfile
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
    assert any(n.endswith(".pdf") for n in names) and any("hashes_sha256" in n for n in names)
    assert len(lab.list_runs()) == 1
