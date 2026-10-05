"""Speculative research hypotheses (Section 20 of the research brief).

Every function here is an explicit RESEARCH HYPOTHESIS, evaluated only on controlled
data with ground truth (the local surrogate, or procedural images with a known
embedded signal). None is presented as an established method; each returns an
``evidence`` block with metrics, a ``verdict`` that is never "proven", and known
failure modes. A single positive run is reported as "SUPPORTED ON THIS CONTROLLED
CASE", never as proof.

Implemented hypotheses (learning-free, numpy):

    A provenance_orthogonal_subspace   PCA of per-patch descriptors on signed/unsigned
                                        controlled pairs; is there a stable direction that
                                        separates them? (proxy for a separable subspace)
    B information_bottleneck_decoupling quantise a representation to k levels and measure
                                        content preservation vs signal information retained
    C frequency_semantic_cross_domain   combine FFT + DWT + handcrafted descriptors into one
                                        candidate score and compare to each domain alone
    D topological_residual              persistence-style summary of residual super-level sets
                                        (Betti-0 / Euler characteristic vs threshold)
    E cross_representation_consensus     estimate the candidate independently in several domains
                                        and measure agreement (reuses consensus engines)
    F automated_hypothesis_discovery    grid search over (residual op, scale, colour plane) for
                                        the configuration whose candidate best matches ground truth

Automated discovery NEVER searches for a transformation that defeats a detector; it
searches for the analysis configuration that best *recovers* a known signal.
"""
from __future__ import annotations

import itertools
import time

import numpy as np

from app.research import consensus as C
from app.research import features as F
from app.research import spectral as S
from app.research import wavelet as W
from app.research.imaging import EPS, color_branches, luminance, scale_by
from app.research.metrics import pearson
from app.research.residuals import residual

HYPOTHESES = ("provenance_orthogonal_subspace", "information_bottleneck_decoupling", "frequency_semantic_cross_domain",
              "topological_residual", "cross_representation_consensus", "automated_hypothesis_discovery")
NEVER_PROVEN = "Hypothesis test on controlled data. A single positive result is never proof; replicate across cases."


def _verdict(effect: float, threshold: float, n: int) -> str:
    if n < 2:
        return "INSUFFICIENT DATA"
    if effect >= threshold:
        return "SUPPORTED ON THIS CONTROLLED CASE"
    if effect <= threshold * 0.3:
        return "NOT SUPPORTED ON THIS CONTROLLED CASE"
    return "INCONCLUSIVE"


def provenance_orthogonal_subspace(signed: list[np.ndarray], unsigned: list[np.ndarray], patch: int = 16) -> dict:
    """Is there a low-dimensional direction in patch-descriptor space separating signed vs unsigned?"""
    def desc(imgs):
        return np.array([F._patch_descriptors(im, patch, patch).mean(0) for im in imgs])
    if len(signed) < 2 or len(unsigned) < 2:
        return {"verdict": "INSUFFICIENT DATA"}
    A, B = desc(signed), desc(unsigned)
    X = np.vstack([A, B])
    X = X - X.mean(0)
    u, s, vt = np.linalg.svd(X, full_matrices=False)
    proj = X @ vt[0]
    ya, yb = proj[: len(A)], proj[len(A):]
    sep = abs(ya.mean() - yb.mean()) / (ya.std() + yb.std() + EPS)
    var = float(s[0] ** 2 / (s ** 2).sum())
    return {"hypothesis": "A provenance-orthogonal subspace", "evidence": {"top_direction_variance": var,
            "separation_cohens_d_like": float(sep), "n_signed": len(A), "n_unsigned": len(B)},
            "verdict": _verdict(sep, 1.0, min(len(A), len(B))),
            "failure_modes": ["content differences between the two sets can create spurious separation",
                              "a single PCA direction need not generalise to other generators"], "note": NEVER_PROVEN}


def information_bottleneck_decoupling(clean: np.ndarray, watermarked: np.ndarray, levels=(2, 4, 8, 16, 32)) -> dict:
    """Quantise luminance to k levels; measure content preservation (PSNR vs clean) and residual signal retained."""
    yc, yw = luminance(clean), luminance(watermarked)
    sig0 = yw - yc
    e0 = float((sig0 ** 2).sum()) or EPS
    rows = []
    for k in levels:
        q = np.round(yw * (k - 1)) / (k - 1)
        retained = float(((q - yc) * sig0).sum()) / e0
        mse = float(((q - yc) ** 2).mean())
        rows.append({"levels": k, "signal_retained": retained,
                     "content_psnr_db": 10 * np.log10(1.0 / mse) if mse > 0 else 99.0})
    best = min(rows, key=lambda r: abs(r["signal_retained"]) + max(0, 30 - r["content_psnr_db"]) * 0.01)
    return {"hypothesis": "B information-bottleneck signal decoupling", "evidence": {"rows": rows, "best": best},
            "verdict": "SUPPORTED ON THIS CONTROLLED CASE" if best["signal_retained"] < 0.5 and best["content_psnr_db"] > 30
            else "INCONCLUSIVE",
            "failure_modes": ["coarse quantisation destroys content too", "only a crude bottleneck proxy"], "note": NEVER_PROVEN}


def frequency_semantic_cross_domain(clean: np.ndarray, watermarked: np.ndarray) -> dict:
    """Does fusing FFT + DWT + residual descriptors recover the known signal better than any single domain?"""
    y = luminance(watermarked)
    known = luminance(watermarked) - luminance(clean)
    cands = {"fft_residual": S.cross_difference(y), "wavelet_detail": W.detail_residual(y, 2),
             "highpass_residual": residual(y, "highpass")}
    singles = {k: abs(pearson(v, known)) for k, v in cands.items()}
    stack = np.stack([(_z(v)) for v in cands.values()], 0)
    fused = stack.mean(0)
    fused_corr = abs(pearson(fused, known))
    return {"hypothesis": "C frequency-semantic cross-domain decomposition",
            "evidence": {"single_domain_corr": singles, "fused_corr": fused_corr, "best_single": max(singles.values())},
            "verdict": _verdict(fused_corr - max(singles.values()), 0.02, 2) if fused_corr > max(singles.values())
            else "NOT SUPPORTED ON THIS CONTROLLED CASE",
            "failure_modes": ["domains may be redundant", "equal-weight fusion is not optimal"], "note": NEVER_PROVEN}


def _z(a):
    a = a.astype(np.float64)
    a = a - a.mean()
    return a / (a.std() + EPS)


def topological_residual(watermarked: np.ndarray, clean: np.ndarray | None = None, thresholds=None) -> dict:
    """Euler-characteristic / component curve of residual super-level sets vs threshold (0-dim persistence proxy)."""
    r = residual(luminance(watermarked), "highpass")
    r = (r - r.mean()) / (r.std() + EPS)
    thresholds = thresholds if thresholds is not None else list(np.linspace(0.5, 4.0, 12))
    curve = []
    for t in thresholds:
        comps = _count_components(r > t)
        curve.append({"threshold": float(t), "components": comps, "area": float((r > t).mean())})
    peak = max(curve, key=lambda c: c["components"])
    out = {"hypothesis": "D topological residual analysis", "evidence": {"curve": curve, "peak": peak}}
    if clean is not None:
        rc = residual(luminance(clean), "highpass")
        rc = (rc - rc.mean()) / (rc.std() + EPS)
        ctrl = max(_count_components(rc > t) for t in thresholds)
        out["evidence"]["control_peak_components"] = ctrl
        out["verdict"] = _verdict((peak["components"] - ctrl) / max(ctrl, 1), 0.3, 2)
    else:
        out["verdict"] = "DESCRIPTIVE (no control supplied)"
    out["failure_modes"] = ["texture produces many components too", "4-connectivity component count is a coarse proxy"]
    out["note"] = NEVER_PROVEN
    return out


def _count_components(mask: np.ndarray) -> int:
    """Number of 4-connected True components via iterative label propagation (no SciPy)."""
    m = mask.astype(bool)
    labels = np.zeros(m.shape, dtype=np.int32)
    labels[m] = np.arange(1, m.sum() + 1)
    if labels.max() == 0:
        return 0
    for _ in range(64):
        prev = labels.copy()
        lab = labels.copy()
        lab[:-1] = np.maximum(lab[:-1], labels[1:] * m[:-1])
        lab[1:] = np.maximum(lab[1:], labels[:-1] * m[1:])
        lab[:, :-1] = np.maximum(lab[:, :-1], labels[:, 1:] * m[:, :-1])
        lab[:, 1:] = np.maximum(lab[:, 1:], labels[:, :-1] * m[:, 1:])
        labels = lab * m
        if np.array_equal(labels, prev):
            break
    return int(len(np.unique(labels)) - 1)


def cross_representation_consensus(watermarked: np.ndarray, clean: np.ndarray | None = None) -> dict:
    ms = C.multiscale_consensus(watermarked)
    cr = C.cross_region_consensus(watermarked)
    agree = 0.5 * (ms["agreement"] + cr["agreement"])
    return {"hypothesis": "E cross-representation consensus",
            "evidence": {"multiscale_agreement": ms["agreement"], "cross_region_agreement": cr["agreement"],
                         "combined": agree}, "verdict": _verdict(agree, 0.3, 2),
            "failure_modes": ["edges/content correlate across representations too"], "note": NEVER_PROVEN}


def automated_hypothesis_discovery(clean: np.ndarray, watermarked: np.ndarray, max_configs: int = 60) -> dict:
    """Search (residual op, scale, colour plane) for the configuration that best RECOVERS the known signal.

    Objective = |corr(candidate, known signal)|. This recovers a signal (analysis), it does not evade a detector.
    """
    known = luminance(watermarked) - luminance(clean)
    ops = ("highpass", "laplacian", "wavelet", "dct", "denoise", "multiscale")
    scales = (1.0, 0.5)
    planes = ("Luma", "RGB:G", "Lab:a*")
    t0 = time.perf_counter()
    results = []
    branches = color_branches(watermarked)
    for op, sc, pl in itertools.islice(itertools.product(ops, scales, planes), max_configs):
        plane = branches.get(pl)
        if plane is None:
            continue
        img = plane if sc == 1.0 else scale_by(plane[:, :, None], sc)[:, :, 0]
        cand = residual(img, op)
        k = known if sc == 1.0 else scale_by(known[:, :, None], sc)[:, :, 0]
        results.append({"config": {"op": op, "scale": sc, "plane": pl}, "recovery_corr": abs(pearson(cand, k))})
    results.sort(key=lambda r: -r["recovery_corr"])
    best = results[0] if results else None
    return {"hypothesis": "F automated hypothesis discovery",
            "evidence": {"n_configs": len(results), "best": best, "top5": results[:5]},
            "candidate_configuration": best["config"] if best else None,
            "metrics": {"best_recovery_corr": best["recovery_corr"] if best else None},
            "verdict": _verdict(best["recovery_corr"] if best else 0.0, 0.3, len(results)),
            "failure_modes": ["the best config on one controlled case may not transfer", "search overfits to this image"],
            "runtime_s": time.perf_counter() - t0, "note": NEVER_PROVEN}
