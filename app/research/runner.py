"""Execute a fingerprint research method and return a standard :class:`MethodResult`.

The runner is pure (numpy/Pillow, no Qt, no files, no network). It takes a
:class:`MethodInput` describing what is available (the image, optional PIL image for
JPEG tables, optional reference images, and an optional controlled surrogate case with
ground truth) and dispatches on ``Method.capability``. Methods that are not READY return
a result with ``status = "UNAVAILABLE"`` or ``"NOT IMPLEMENTED"`` and the reason, never a
fabricated measurement.

A MethodResult carries: scalar ``readouts`` (for the UI), the full ``data`` block, the
``maps`` (named float planes for display), a ``fidelity`` / ``ground_truth`` block where
applicable, the ``failure_analysis`` findings, and the record fields needed for the audit
trail and paper export.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from app.research import consensus as C
from app.research import dct as D
from app.research import failure as FA
from app.research import features as F
from app.research import hypotheses as HY
from app.research import metrics as MET
from app.research import procedural as PROC
from app.research import residuals as RES
from app.research import robustness as ROB
from app.research import separation as SEP
from app.research import spectral as SP
from app.research import surrogate as SUR
from app.research import wavelet as WV
from app.research.imaging import as_float, luminance
from app.research.methods import Method, MethodRegistry


@dataclass
class MethodInput:
    image: np.ndarray                      # float HxWxC in [0,1] (the analysis copy)
    pil: object = None                     # optional PIL image (for JPEG tables)
    references: list = field(default_factory=list)   # extra float images (cross-image / attribution)
    surrogate_cfg: SUR.SurrogateConfig | None = None
    clean: np.ndarray | None = None        # clean image of a controlled surrogate case
    signed: list = field(default_factory=list)       # hypothesis A: signed controlled images
    unsigned: list = field(default_factory=list)      # hypothesis A: unsigned controlled images
    prototypes: dict = field(default_factory=dict)    # attribution prototypes {group: vector}
    params: dict = field(default_factory=dict)
    prior_results: list = field(default_factory=list)  # for meta-analysis


@dataclass
class MethodResult:
    method_id: str
    code: str
    name: str
    category: str
    maturity: str
    status: str                 # COMPLETE / UNAVAILABLE / NOT IMPLEMENTED / INSUFFICIENT DATA / FAILED
    readouts: dict = field(default_factory=dict)
    data: dict = field(default_factory=dict)
    candidate_stats: dict = field(default_factory=dict)
    reconstruction: dict = field(default_factory=dict)
    ground_truth: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    solver: dict = field(default_factory=dict)
    failure_analysis: list = field(default_factory=list)
    maps: dict = field(repr=False, default_factory=dict)   # name -> float plane/image (not serialised to JSON)
    detail: str = ""
    runtime_s: float = 0.0
    note: str = ""

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in ("method_id", "code", "name", "category", "maturity", "status", "readouts",
                                              "data", "candidate_stats", "reconstruction", "ground_truth", "metrics",
                                              "solver", "failure_analysis", "detail", "runtime_s", "note")}


def _case(inp: MethodInput) -> tuple:
    if inp.surrogate_cfg is None or inp.clean is None:
        return None, None
    emb = SUR.embed(inp.clean, inp.surrogate_cfg)
    return emb, inp.clean


def run(method: Method, inp: MethodInput, progress=None) -> MethodResult:
    t0 = time.perf_counter()
    base = dict(method_id=method.method_id, code=method.code, name=method.name, category=method.category,
                maturity=method.maturity)
    if method.availability == "NOT_IMPLEMENTED":
        return MethodResult(**base, status="NOT IMPLEMENTED", detail=method.reason, note=method.reason)
    if method.availability == "UNAVAILABLE":
        return MethodResult(**base, status="UNAVAILABLE", detail=method.reason, note=method.reason)
    try:
        res = _dispatch(method, inp, progress)
    except Exception as exc:  # noqa: BLE001 - surfaced as a FAILED result, never hidden
        return MethodResult(**base, status="FAILED", detail=f"{type(exc).__name__}: {exc}",
                            runtime_s=time.perf_counter() - t0)
    res.runtime_s = time.perf_counter() - t0
    if not res.failure_analysis and res.status in ("COMPLETE", "SIGNAL PERSISTED"):
        res.failure_analysis = FA.analyse(res.to_dict())
    return res


def _mk(method, **kw) -> MethodResult:
    return MethodResult(method_id=method.method_id, code=method.code, name=method.name, category=method.category,
                        maturity=method.maturity, status=kw.pop("status", "COMPLETE"), **kw)


def _dispatch(method: Method, inp: MethodInput, progress) -> MethodResult:  # noqa: C901 - explicit dispatch table
    cap = method.capability
    x = inp.image
    y = luminance(x)
    p = inp.params

    if cap.startswith("sep:"):
        return _separation(method, inp, cap.split(":", 1)[1])
    if cap.startswith("hyp:"):
        return _hypothesis(method, inp, cap.split(":", 1)[1])
    if cap.startswith("frontier:") or cap == "reconstruction":
        return _frontier(method, inp, cap)

    if cap == "baseline":
        from app.research.residuals import stats
        s = stats(RES.residual(y, "gaussian"), with_spectrum=False)["stats"]
        return _mk(method, readouts={"Resolution": f"{x.shape[1]}x{x.shape[0]}", "Channels": x.shape[2],
                                     "Residual energy": round(s["energy"], 6), "Entropy (bits)": round(s["entropy_bits"], 3)},
                   data={"shape": list(x.shape), "residual_baseline": s},
                   detail="Baseline control characterised.")
    if cap in ("metadata", "c2pa"):
        return _mk(method, status="COMPLETE", detail="Handled by the native metadata / C2PA engines in the main "
                   "experiment; this method documents the layer in the Fingerprint Lab.",
                   data={"note": "See the C2PA Provenance and Forensic Inspector views for the full parse."},
                   readouts={"Layer": "provenance (see C2PA view)"})

    if cap == "fft":
        a = SP.analyse(y)
        return _mk(method, readouts={"Tail slope": round(a["tail"].get("slope", 0), 3) if a["tail"].get("slope") is not None else "-",
                                     "Tail excess (dB)": round(a["tail"].get("tail_deviation_db", 0), 2),
                                     "Periodic peaks": a["peaks"]["n_peaks"],
                                     "Grid-aligned peaks": a["peaks"]["grid_aligned_peaks"]},
                   data={"radial": a["radial"], "angular": a["angular"], "bands": a["bands"], "tail": a["tail"],
                         "peaks": a["peaks"]}, maps=a["maps"], detail=a["note"])
    if cap == "dct":
        a = D.analyse(y * 255.0, inp.pil)
        if a.get("status") != "COMPLETE":
            return _mk(method, status="INSUFFICIENT DATA", detail="image too small for 8x8 DCT")
        q = a.get("quality_estimate") or {}
        return _mk(method, readouts={"JPEG": a["jpeg"], "Est. quality": q.get("quality", "-"),
                                     "AC zero fraction": round(a["zero_fraction_ac"], 3),
                                     "Blockiness": round(a["blockiness"].get("blockiness", 0), 3)},
                   data=a, maps=a["maps"], detail=a["coefficient_basis"])
    if cap == "wavelet":
        a = WV.analyse(y, levels=int(p.get("levels", 3)), wavelet=str(p.get("wavelet", "db2")))
        hh = next((r for r in a["subbands"] if r["band"] == "HH" and r["level"] == 1), {})
        return _mk(method, readouts={"Levels": a["levels"], "HH1 energy": round(hh.get("energy", 0), 6),
                                     "HH1 kurtosis": round(hh.get("kurtosis", 0), 2),
                                     "HH1 sparsity": round(hh.get("sparsity", 0), 3)},
                   data={"subbands": a["subbands"], "persistence": a["persistence"]}, maps=a["maps"],
                   detail=f"{a['wavelet']} DWT, {a['levels']} levels")
    if cap == "benford":
        a = F.dct_benford_vector(x, inp.pil)
        b = a.get("benford", {})
        return _mk(method, readouts={"Benford status": b.get("status", "-"), "JS divergence": round(b.get("js_divergence", 0), 4)
                                     if b.get("js_divergence") is not None else "-", "chi2": round(b.get("chi2", 0), 1)
                                     if b.get("chi2") is not None else "-"},
                   data=a, detail="First-digit statistics of quantised DCT AC coefficients.")
    if cap == "residual":
        a = RES.analyse(y)
        g = a["operators"].get("highpass", {})
        return _mk(method, readouts={"High-pass energy": round(g.get("energy", 0), 6),
                                     "Kurtosis": round(g.get("kurtosis", 0), 2),
                                     "Autocorr off-centre": round(g.get("autocorrelation", {}).get("max_offcentre", 0), 3)},
                   data={"operators": a["operators"]}, maps=a["maps"], candidate_stats=g, detail="Residual operators and statistics.")
    if cap == "synthbuster":
        a = SP.synthbuster_features(y)
        return _mk(method, readouts={"Lattice peak ratio": round(a["lattice_peak_ratio"], 3), "Features": len(a["features"])},
                   data={"features": a["features"], "names": a["names"], "lattice_peak_ratio": a["lattice_peak_ratio"]},
                   maps={"synthbuster_residual_spectrum": a["log_magnitude"]},
                   detail="Residual-spectrum lattice features (ADAPTED; no trained classifier).")
    if cap == "lid":
        a = F.lid_features(x, k=int(p.get("k", 20)))
        if a.get("status") != "COMPLETE":
            return _mk(method, status="INSUFFICIENT DATA", detail=f"{a.get('n_patches', 0)} patches")
        return _mk(method, readouts={"LID mean": round(a["lid_mean"], 2), "LID std": round(a["lid_std"], 2),
                                     "Patches": a["n_patches"]}, data=a, detail=a["note"])
    if cap == "residual_vector":
        a = F.residual_vector(x)
        return _mk(method, readouts={"Descriptor length": len(a["vector"])}, data=a,
                   detail="Handcrafted GAN-fingerprint-style descriptor (ADAPTED).")
    if cap == "patch_consensus":
        a = C.patch_consensus(x)
        return _mk(method, readouts={"Patches": a["n_patches"], "Consistency": round(a["consistency"], 3),
                                     "Energy CV": round(a["energy_cv"], 3)}, data=a, detail=a["note"])
    if cap == "multiscale_consensus":
        a = C.multiscale_consensus(x)
        return _mk(method, readouts={"Agreement": round(a["agreement"], 3)}, data=a, detail="Multi-scale map agreement.")
    if cap == "cross_region_consensus":
        a = C.cross_region_consensus(x)
        return _mk(method, readouts={"Agreement": round(a["agreement"], 3)}, data=a, detail="Cross-region spectral agreement.")
    if cap == "cross_image":
        imgs = [x] + list(inp.references)
        a = C.cross_image_consensus(imgs)
        if a.get("status") != "COMPLETE":
            return _mk(method, status="INSUFFICIENT DATA", detail=a.get("detail", "need 4+ images"))
        return _mk(method, readouts={"Held-out corr": round(a["held_out_mean_corr"], 3),
                                     "Control corr": round(a["control_mean_corr"], 3),
                                     "Held-out - control": round(a["held_out_minus_control"], 3)}, data=a, detail=a["note"])
    if cap == "attribution":
        if not inp.prototypes:
            return _mk(method, status="INSUFFICIENT DATA", detail="No prototypes supplied. Build prototypes from "
                       "labelled images first (requires reference images).")
        d = F.descriptor(x, inp.pil)
        a = F.nearest_prototype(d["vector"], inp.prototypes)
        return _mk(method, readouts={"Nearest prototype": a["nearest"] or "-"}, data=a, detail=a["note"])
    if cap == "robustness":
        emb, clean = _case(inp)
        if emb is None:
            return _mk(method, status="INSUFFICIENT DATA", detail="Robustness sweep needs a controlled surrogate case.")
        a = ROB.sweep(emb.watermarked, inp.surrogate_cfg, kinds=tuple(p.get("kinds", ())), progress=progress)
        bad = sum(1 for g in a["by_kind"].values() if g.get("still_detected"))
        return _mk(method, readouts={"Transforms": len(a["by_kind"]), "Baseline z": round(a["baseline_score"], 1)},
                   data=a, ground_truth={"surrogate": emb.config}, detail=a["note"])
    if cap == "persistence_map":
        return _persistence_map(method, inp, p)
    if cap == "ensemble":
        return _ensemble(method, inp)
    if cap == "meta":
        return _meta(method, inp)
    return _mk(method, status="FAILED", detail=f"no runner for capability {cap!r}")


def _separation(method, inp, sub) -> MethodResult:
    emb, clean = _case(inp)
    if emb is None:
        return _mk(method, status="INSUFFICIENT DATA",
                   detail="This separation study runs on a controlled surrogate case (clean + embedded) so that the "
                          "recovered candidate can be scored against ground truth.")
    r = SEP.separate(emb.watermarked, sub, inp.params, surrogate_cfg=inp.surrogate_cfg, clean=clean)
    gt = r.ground_truth
    return _mk(method, readouts={"Recon PSNR (dB)": round(r.reconstruction.get("psnr_db") or 99, 1),
                                 "Recon SSIM": round(r.reconstruction.get("ssim") or 0, 3),
                                 "Candidate vs known": round(gt.get("candidate_vs_known_corr", 0), 3),
                                 "Signal reduction": round(gt.get("signal_reduction") or 0, 3),
                                 "Still detected": gt.get("still_detected_after")},
               data={"params": r.params, "label": r.label}, candidate_stats=r.candidate_stats,
               reconstruction=r.reconstruction, ground_truth=gt, solver=r.solver, maps=r.panels,
               status="SIGNAL PERSISTED" if gt.get("still_detected_after") else "COMPLETE",
               detail=r.label)


def _hypothesis(method, inp, name) -> MethodResult:
    emb, clean = _case(inp)
    wm = emb.watermarked if emb is not None else inp.image
    if name == "provenance_orthogonal_subspace":
        if not inp.signed or not inp.unsigned:
            return _mk(method, status="INSUFFICIENT DATA", detail="Needs signed and unsigned controlled image sets.")
        a = HY.provenance_orthogonal_subspace(inp.signed, inp.unsigned)
    elif name == "information_bottleneck_decoupling":
        if emb is None:
            return _mk(method, status="INSUFFICIENT DATA", detail="Needs a controlled surrogate case.")
        a = HY.information_bottleneck_decoupling(clean, wm)
    elif name == "frequency_semantic_cross_domain":
        if emb is None:
            return _mk(method, status="INSUFFICIENT DATA", detail="Needs a controlled surrogate case.")
        a = HY.frequency_semantic_cross_domain(clean, wm)
    elif name == "topological_residual":
        a = HY.topological_residual(wm, clean)
    elif name == "cross_representation_consensus":
        a = HY.cross_representation_consensus(wm, clean)
    elif name == "automated_hypothesis_discovery":
        if emb is None:
            return _mk(method, status="INSUFFICIENT DATA", detail="Needs a controlled surrogate case.")
        a = HY.automated_hypothesis_discovery(clean, wm)
    else:
        return _mk(method, status="FAILED", detail=f"unknown hypothesis {name}")
    return _mk(method, readouts={"Verdict": a.get("verdict", "-")}, data=a, metrics=a.get("metrics", {}),
               detail=a.get("verdict", ""), note=a.get("note", ""))


def _frontier(method, inp, cap) -> MethodResult:
    from app.research import frontier as FR
    emb, clean = _case(inp)
    wm = emb.watermarked if emb is not None else inp.image
    name = cap.split(":", 1)[1] if ":" in cap else cap
    if name == "fingerprint_null_space":
        if not inp.signed or not inp.unsigned:
            return _mk(method, status="INSUFFICIENT DATA", detail="Needs signed and unsigned controlled image sets.")
        a, maps = FR.fingerprint_null_space(inp.signed, inp.unsigned)
    elif name in ("spectral_semantic_fusion", "provenance_energy_landscape"):
        if emb is None:
            return _mk(method, status="INSUFFICIENT DATA", detail="Needs a controlled surrogate case.")
        a, maps = getattr(FR, name)(wm, clean)
    elif name == "reconstruction":
        a, maps = FR.reconstruction_forensics(wm, clean)
    else:
        a, maps = getattr(FR, name)(wm, clean)
    if a.get("verdict") == "INSUFFICIENT DATA":
        return _mk(method, status="INSUFFICIENT DATA", detail=a.get("note", ""))
    readouts = {"Verdict": a.get("verdict", "-")}
    for k, v in (a.get("metrics") or {}).items():
        readouts[k] = v
    gt = a.get("ground_truth") or {}
    return _mk(method, readouts=readouts, data=a, metrics=a.get("metrics", {}), ground_truth=gt, maps=maps,
               reconstruction=a.get("reconstruction", {}), detail=a.get("verdict", a.get("note", "")),
               note=a.get("note", ""))


def _persistence_map(method, inp, p) -> MethodResult:
    emb, clean = _case(inp)
    if emb is None:
        return _mk(method, status="INSUFFICIENT DATA", detail="Needs a controlled surrogate case.")
    kind = str(p.get("transform", "jpeg"))
    sev = p.get("severity", 80)
    att = ROB.apply(emb.watermarked, kind, sev)
    if att.shape != emb.watermarked.shape:
        return _mk(method, status="NOT COMPARABLE", detail="transform changed geometry; per-tile projection undefined")
    known = luminance(emb.watermarked) - luminance(clean)
    r1 = luminance(att) - luminance(clean)
    tile = 16
    h, w = known.shape
    retain = np.zeros((h // tile, w // tile), dtype=np.float32)
    for i in range(h // tile):
        for j in range(w // tile):
            a = known[i * tile:(i + 1) * tile, j * tile:(j + 1) * tile]
            b = r1[i * tile:(i + 1) * tile, j * tile:(j + 1) * tile]
            e = float((a * a).sum())
            retain[i, j] = float((a * b).sum()) / e if e > 1e-9 else 0.0
    sr = SUR.signal_reduction(clean, emb.watermarked, att)
    return _mk(method, readouts={"Transform": f"{kind}={sev}", "Mean retained": round(float(retain.mean()), 3),
                                 "Signal reduction": round(sr.get("signal_reduction", 0), 3)},
               data={"transform": kind, "severity": sev, "signal_reduction": sr},
               maps={"signal_persistence": retain, "attacked": att}, ground_truth=sr,
               detail="Per-tile retained fraction of the known signal after a standard transformation.")


def _ensemble(method, inp) -> MethodResult:
    reg = MethodRegistry()
    out = {}
    readouts = {}
    for code in ("Method 13", "Method 14", "Method 15", "Method 17", "Method 18"):
        r = run(reg.get(code), inp)
        out[code] = {"name": r.name, "status": r.status, "readouts": r.readouts}
        if r.readouts:
            k = next(iter(r.readouts))
            readouts[r.name] = r.readouts[k]
    return _mk(method, readouts=readouts, data={"members": out},
               detail="Descriptive cross-check across FFT / DCT / wavelet / residual / Benford methods.")


def _meta(method, inp) -> MethodResult:
    runs = inp.prior_results or []
    done = [r for r in runs if r.get("status") == "COMPLETE"]
    findings = [f for r in runs for f in (r.get("failure_analysis") or []) if f.get("failure_mode") != "none"]
    return _mk(method, readouts={"Methods summarised": len(runs), "Completed": len(done), "Findings": len(findings)},
               data={"summary": [{"method": r.get("method_id"), "name": r.get("name"), "status": r.get("status")}
                                 for r in runs], "findings": findings},
               detail="Meta-analysis of the methods run in this experiment.")


def quick_surrogate_case(family: str = "spatial", strength: float = 3.0, seed: int = 0, size=(256, 256)) -> MethodInput:
    """A ready-made controlled surrogate MethodInput for demos / self-test (clearly synthetic content)."""
    clean = PROC.scene(size[1], size[0], seed=seed)
    cfg = SUR.SurrogateConfig(family=family, strength=strength)
    emb = SUR.embed(clean, cfg)
    return MethodInput(image=emb.watermarked, surrogate_cfg=cfg, clean=clean)
