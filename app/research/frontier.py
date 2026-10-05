"""Frontier / hypothetical research methods (v4 Section 23) and a training-free
reconstruction-forensics capability (Section 13).

Every function here is explicitly HYPOTHETICAL: evaluated only on controlled data with
ground truth (the local surrogate, or procedural images with a known embedded signal),
reported with a cautious verdict and known failure modes, and never called proven. None
searches for a transformation that defeats a detector; they recover or characterise a
known signal, or measure method agreement/stability.

Implemented (learning-free, numpy):

    A multi_representation_residual_consensus  residual agreement across RGB/FFT/DWT/DCT domains
    C fingerprint_null_space                   PCA null-space of per-patch descriptors; residual energy there
    D cross_scale_topological_residual         component/Euler curve of residual super-level sets across scales
    E spectral_semantic_fusion                 fuse spectral + handcrafted-descriptor candidate maps
    G iterative_reconstruction_consensus        repeat estimate(content)/estimate(signal); track convergence & drift
    H method_disagreement                        disagreement between independent candidate estimators as uncertainty
    I fingerprint_stability_field               per-tile stability of a candidate under small perturbations
    J provenance_energy_landscape               signal energy over a grid of standard transformations
    reconstruction                              self-supervised image-prior reconstruction + error map (Section 13)

B (counterfactual probe) and F (information-bottleneck decoupling) are covered by the
Hypothesis Lab (Methods 42/48); they are not duplicated here.
"""
from __future__ import annotations

import numpy as np

from app.research import consensus as C
from app.research import features as F
from app.research import hypotheses as HY
from app.research import robustness as ROB
from app.research import separation as SEP
from app.research import spectral as S
from app.research import wavelet as W
from app.research.imaging import EPS, color_branches, gaussian_blur, luminance, resize_plane
from app.research.metrics import pearson
from app.research.residuals import residual

NEVER_PROVEN = HY.NEVER_PROVEN


def _z(a: np.ndarray) -> np.ndarray:
    a = a.astype(np.float64)
    a = a - a.mean()
    return a / (a.std() + EPS)


def _verdict(effect: float, threshold: float) -> str:
    if effect >= threshold:
        return "SUPPORTED ON THIS CONTROLLED CASE"
    if effect <= threshold * 0.3:
        return "NOT SUPPORTED ON THIS CONTROLLED CASE"
    return "INCONCLUSIVE"


def _candidates(y: np.ndarray) -> dict:
    return {"rgb_highpass": residual(y, "highpass"), "fft_cross": S.cross_difference(y),
            "dwt_detail": W.detail_residual(y, 2), "dct_highpass": residual(y, "dct")}


def multi_representation_residual_consensus(watermarked: np.ndarray, clean: np.ndarray | None = None) -> dict:
    y = luminance(watermarked)
    cands = _candidates(y)
    names = list(cands)
    zs = {k: _z(v) for k, v in cands.items()}
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            pairs.append({"domains": [names[i], names[j]], "correlation": pearson(zs[names[i]], zs[names[j]])})
    fused = np.mean(list(zs.values()), axis=0)
    agree = float(np.mean([p["correlation"] for p in pairs]))
    out = {"hypothesis": "A multi-representation residual consensus", "method": "mean pairwise residual correlation + fused map",
           "evidence": {"pairs": pairs, "mean_agreement": agree}, "verdict": _verdict(agree, 0.3),
           "failure_modes": ["edges/content correlate across domains too"], "note": NEVER_PROVEN}
    maps = {"fused_candidate": fused.astype(np.float32)}
    if clean is not None:
        known = luminance(watermarked) - luminance(clean)
        out["evidence"]["fused_vs_known_corr"] = abs(pearson(fused, known))
        out["metrics"] = {"fused_recovery_corr": out["evidence"]["fused_vs_known_corr"]}
    return out, maps


def fingerprint_null_space(signed: list, unsigned: list, patch: int = 16) -> dict:
    def desc(imgs):
        return np.array([F._patch_descriptors(im, patch, patch).mean(0) for im in imgs])
    if len(signed) < 2 or len(unsigned) < 2:
        return ({"verdict": "INSUFFICIENT DATA", "hypothesis": "C fingerprint null-space projection"}, {})
    A, B = desc(signed), desc(unsigned)
    X = np.vstack([A, B])
    mu = X.mean(0)
    Xc = X - mu
    u, s, vt = np.linalg.svd(Xc, full_matrices=False)
    # top-k identity subspace vs its complement (null space): is signed/unsigned separation concentrated in few dims?
    energy = s ** 2 / (s ** 2).sum()
    k = int(np.searchsorted(np.cumsum(energy), 0.9)) + 1
    proj_full = Xc @ vt[:k].T
    ya, yb = proj_full[: len(A)], proj_full[len(A):]
    sep = float(np.linalg.norm(ya.mean(0) - yb.mean(0)) / (ya.std() + yb.std() + EPS))
    null_var = float(energy[k:].sum())
    return ({"hypothesis": "C fingerprint null-space projection",
             "method": "PCA identity subspace vs null space of patch descriptors",
             "evidence": {"identity_dims": k, "subspace_separation": sep, "null_space_variance_fraction": null_var},
             "metrics": {"subspace_separation": sep}, "verdict": _verdict(sep, 1.0),
             "failure_modes": ["content variance can dominate the subspace", "needs many controlled images"],
             "note": NEVER_PROVEN}, {})


def cross_scale_topological_residual(watermarked: np.ndarray, clean: np.ndarray | None = None,
                                     scales=(1.0, 0.5, 0.25)) -> dict:
    curves = {}
    peak_by_scale = {}
    for sc in scales:
        y = luminance(watermarked)
        if sc != 1.0:
            y = resize_plane(y, (max(8, int(y.shape[1] * sc)), max(8, int(y.shape[0] * sc))))
        r = _z(residual(y, "highpass"))
        th = np.linspace(0.5, 4.0, 10)
        curve = [{"threshold": float(t), "components": HY._count_components(r > t)} for t in th]
        curves[str(sc)] = curve
        peak_by_scale[str(sc)] = max(c["components"] for c in curve)
    # cross-scale persistence: a structured signal keeps a similar component peak across scales
    peaks = list(peak_by_scale.values())
    stability = float(1.0 - (np.std(peaks) / (np.mean(peaks) + EPS)))
    out = {"hypothesis": "D cross-scale topological residual", "method": "component-count curve of residual super-level sets per scale",
           "evidence": {"curves": curves, "peak_by_scale": peak_by_scale, "cross_scale_stability": stability},
           "metrics": {"cross_scale_stability": stability}, "verdict": _verdict(stability, 0.5),
           "failure_modes": ["texture produces components at every scale", "coarse 4-connectivity proxy"], "note": NEVER_PROVEN}
    return out, {}


def spectral_semantic_fusion(watermarked: np.ndarray, clean: np.ndarray | None = None) -> dict:
    y = luminance(watermarked)
    spectral = _z(S.cross_difference(y))
    # "semantic" proxy without a neural net: multi-scale structure (guided-smoothing detail bands)
    semantic = _z(y - gaussian_blur(y, 3.0))
    fused = 0.5 * spectral + 0.5 * semantic
    out = {"hypothesis": "E spectral-semantic fusion", "method": "fuse spectral residual with a structure (semantic proxy) map",
           "evidence": {"spectral_vs_semantic_corr": pearson(spectral, semantic)}, "note": NEVER_PROVEN,
           "failure_modes": ["no learned semantics; structure proxy is coarse"]}
    maps = {"fused_candidate": fused.astype(np.float32)}
    if clean is not None:
        known = luminance(watermarked) - luminance(clean)
        single = max(abs(pearson(spectral, known)), abs(pearson(semantic, known)))
        fused_c = abs(pearson(fused, known))
        out["evidence"].update({"best_single_corr": single, "fused_corr": fused_c})
        out["metrics"] = {"fused_recovery_corr": fused_c}
        out["verdict"] = _verdict(fused_c - single, 0.02) if fused_c > single else "NOT SUPPORTED ON THIS CONTROLLED CASE"
    else:
        out["verdict"] = "DESCRIPTIVE (no control supplied)"
    return out, maps


def iterative_reconstruction_consensus(watermarked: np.ndarray, clean: np.ndarray | None = None, iters: int = 5) -> dict:
    y = luminance(watermarked).astype(np.float32)
    content = y.copy()
    drift, residual_energy = [], []
    prev = None
    for _ in range(int(iters)):
        content = SEP._guided_smooth(content, iters=3, r=2)
        sig = y - content
        residual_energy.append(float((sig * sig).mean()))
        if prev is not None:
            drift.append(float(np.sqrt(((content - prev) ** 2).mean())))
        prev = content.copy()
    converged = bool(drift and drift[-1] < 1e-3)
    out = {"hypothesis": "G iterative reconstruction consensus", "method": "repeated guided-smoothing content/signal estimation",
           "evidence": {"residual_energy": residual_energy, "drift": drift, "converged": converged},
           "metrics": {"final_drift": drift[-1] if drift else None, "final_residual_energy": residual_energy[-1]},
           "verdict": "CONVERGED" if converged else "DID NOT CONVERGE", "failure_modes": ["smoothing erodes content"],
           "note": NEVER_PROVEN}
    maps = {"estimated_content": content, "candidate_signal": (y - content).astype(np.float32)}
    if clean is not None:
        known = y - luminance(clean)
        out["evidence"]["candidate_vs_known_corr"] = abs(pearson(y - content, known))
    return out, maps


def method_disagreement(watermarked: np.ndarray, clean: np.ndarray | None = None) -> dict:
    y = luminance(watermarked)
    cands = {k: _z(v) for k, v in _candidates(y).items()}
    names = list(cands)
    corr = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            corr.append(pearson(cands[names[i]], cands[names[j]]))
    mean_agree = float(np.mean(corr))
    disagreement = float(1.0 - mean_agree)
    return ({"hypothesis": "H method disagreement analysis",
             "method": "1 - mean pairwise correlation of independent candidate estimators (uncertainty proxy)",
             "evidence": {"mean_agreement": mean_agree, "disagreement": disagreement, "n_methods": len(names)},
             "metrics": {"disagreement": disagreement},
             "verdict": "HIGH AGREEMENT (low uncertainty)" if mean_agree > 0.5 else "HIGH DISAGREEMENT (high uncertainty)",
             "failure_modes": ["agreement from shared content is not agreement about a fingerprint"],
             "note": NEVER_PROVEN}, {})


def fingerprint_stability_field(watermarked: np.ndarray, clean: np.ndarray | None = None, tile: int = 16,
                                sigma: float = 0.5) -> dict:
    y = luminance(watermarked).astype(np.float32)
    base = _z(residual(y, "highpass"))
    rng = np.random.default_rng(0)
    pert = _z(residual(np.clip(y + sigma / 255.0 * rng.standard_normal(y.shape).astype(np.float32), 0, 1), "highpass"))
    h, w = y.shape
    field = np.zeros((h // tile, w // tile), dtype=np.float32)
    for i in range(h // tile):
        for j in range(w // tile):
            a = base[i * tile:(i + 1) * tile, j * tile:(j + 1) * tile]
            b = pert[i * tile:(i + 1) * tile, j * tile:(j + 1) * tile]
            field[i, j] = pearson(a, b)
    out = {"hypothesis": "I fingerprint stability field",
           "method": "per-tile correlation of the candidate residual under a small perturbation",
           "evidence": {"mean_stability": float(field.mean()), "stable_fraction": float((field > 0.5).mean())},
           "metrics": {"mean_stability": float(field.mean())},
           "verdict": "STABLE FIELD" if field.mean() > 0.5 else "UNSTABLE FIELD",
           "failure_modes": ["noise-dominated tiles are unstable regardless of a fingerprint"], "note": NEVER_PROVEN}
    return out, {"stability_field": field}


def provenance_energy_landscape(watermarked: np.ndarray, clean: np.ndarray | None = None) -> dict:
    if clean is None:
        return ({"hypothesis": "J provenance energy landscape", "verdict": "INSUFFICIENT DATA",
                 "note": "needs a controlled surrogate case (clean + watermarked) to measure known-signal energy"}, {})
    known = luminance(watermarked) - luminance(clean)
    e0 = float((known * known).sum()) or EPS
    grid = []
    for kind, sev in (("jpeg", 90), ("jpeg", 70), ("blur", 1.0), ("noise", 2), ("resize", 0.5), ("color", 1.2)):
        att = ROB.apply(watermarked, kind, sev)
        if att.shape != watermarked.shape:
            retained = None
        else:
            r1 = luminance(att) - luminance(clean)
            retained = float((r1 * known).sum()) / e0
        grid.append({"transform": f"{kind}={sev}", "retained_energy_fraction": retained})
    vals = [g["retained_energy_fraction"] for g in grid if g["retained_energy_fraction"] is not None]
    return ({"hypothesis": "J provenance energy landscape",
             "method": "known-signal energy retained across a grid of standard transformations",
             "evidence": {"landscape": grid, "mean_retained": float(np.mean(vals)) if vals else None,
                          "min_retained": float(np.min(vals)) if vals else None},
             "metrics": {"mean_retained_energy": float(np.mean(vals)) if vals else None},
             "verdict": "DESCRIPTIVE", "failure_modes": ["geometry-changing transforms are undefined for projection"],
             "note": NEVER_PROVEN}, {})


def reconstruction_forensics(watermarked: np.ndarray, clean: np.ndarray | None = None, iters: int = 10) -> dict:
    """Self-supervised image-prior reconstruction + error map (Section 13). Training-free; NOT a diffusion/AE model."""
    y = luminance(watermarked).astype(np.float32)
    recon = SEP._guided_smooth(y, iters=int(iters), r=3)
    err = y - recon
    out = {"method": "self-supervised guided-filter image prior (training-free)",
           "evidence": {"error_energy": float((err * err).mean()), "error_max": float(np.abs(err).max())},
           "note": "This is a learning-free reconstruction prior. It is NOT a diffusion or autoencoder reconstruction "
                   "(DIRE/AEROBLADE need a pretrained model, reported UNAVAILABLE)."}
    maps = {"reconstruction": recon, "error_map": err.astype(np.float32), "candidate_signal": err.astype(np.float32)}
    if clean is not None:
        known = y - luminance(clean)
        corr = abs(pearson(err, known))
        out["evidence"]["error_vs_known_corr"] = corr
        out["metrics"] = {"reconstruction_error_recovery_corr": corr}
        out["ground_truth"] = {"candidate_vs_known_corr": corr}
    return out, maps
