"""Research metrics and the definitions of custom SynthProvenance metrics.

Standard metrics reuse the audited implementations already in the code base
(``app.core.pixel_integrity.ssim`` for SSIM, ``app.core.synthid_benchmark`` for ROC /
AUC / confusion statistics with Wilson and bootstrap intervals). LPIPS needs a learned
network and is reported as NOT AVAILABLE, never estimated.
"""
from __future__ import annotations

import math

import numpy as np

from app.core.pixel_integrity import ssim as _ssim
from app.core.synthid_benchmark import auc_mann_whitney, bootstrap_auc_ci, confusion, roc_curve, wilson

LPIPS_STATUS = "NOT AVAILABLE (requires a learned perceptual network; not bundled, never estimated)"

DEFINITIONS = {
    "signal_energy": {
        "formula": "E_s = mean(s^2) * 255^2  (s = known or candidate signal on luminance, 0..1 scale)",
        "rationale": "Strength of a signal in 8-bit level units, comparable across image sizes.",
        "normalization": "Per-pixel mean, expressed in squared 8-bit levels.",
        "limitations": "Says nothing about detectability; masked or structured signals can be strong yet invisible."},
    "signal_reduction": {
        "formula": "SR = 1 - <r_att, r_0> / <r_0, r_0>,  r_0 = Y_wm - Y_clean,  r_att = Y_attacked - Y_clean",
        "rationale": "Fraction of the known embedded residual removed, measured by projection onto the ground truth.",
        "normalization": "1 = residual fully removed along its own direction, 0 = untouched, < 0 = amplified.",
        "limitations": "Needs pixel-aligned ground truth (undefined after crops/resizes). Content damage that happens "
                       "to be orthogonal to r_0 is not penalised; read it together with PSNR/SSIM."},
    "fingerprint_persistence": {
        "formula": "FP(t) = z_detector(T_t(x_wm)) / z_detector(x_wm)  (surrogate)  or  "
                   "corr(F(T_t(x)), F(x))  (candidate fingerprint map F, no ground truth)",
        "rationale": "How much of a signal (or of a candidate fingerprint) survives a transformation of severity t.",
        "normalization": "1 = fully persistent, 0 = gone; plotted against severity.",
        "limitations": "Without ground truth the map correlation measures stability of a statistic, not of a "
                       "verified generator fingerprint."},
    "cross_generator_generalization": {
        "formula": "CGG = mean over held-out groups g of AUC_g, with the method calibrated/trained on other groups only",
        "rationale": "Detectors that only work on the generators they were tuned on do not generalise.",
        "normalization": "AUC scale; 0.5 = chance.",
        "limitations": "Only as good as the researcher-supplied labels and group annotations; small groups give wide CIs."},
    "query_count": {
        "formula": "number of detector evaluations used by a red-team method",
        "rationale": "Black-box attack cost.",
        "normalization": "absolute count",
        "limitations": "White-box methods use gradients and report their (small) query count separately."},
    "consensus_agreement": {
        "formula": "mean pairwise Pearson correlation between candidate maps from different scales / regions / "
                   "representations, after resampling to a common grid",
        "rationale": "A real structured signal should be found consistently by independent estimators.",
        "normalization": "[-1, 1]",
        "limitations": "Shared content leakage (edges) also produces agreement; compare against control images."},
    "periodic_artifact_score": {
        "formula": "mean robust z-score (capped at 50) of isolated peaks in the residual log-magnitude spectrum",
        "rationale": "Up-sampling and tiling leave periodic peaks (checkerboard / grid artifacts).",
        "normalization": "z units above the local spectral background",
        "limitations": "JPEG 8x8 grids, halftoning and textiles also produce peaks."},
}


def fidelity(ref: np.ndarray, test: np.ndarray) -> dict:
    """MAE / MSE / PSNR / SSIM / changed pixels between two float images (0..1) of equal shape, in 8-bit units."""
    if ref.shape != test.shape:
        return {"comparable": False, "detail": f"shape {ref.shape} vs {test.shape}", "lpips": LPIPS_STATUS}
    a = np.rint(np.clip(ref, 0, 1) * 255).astype(np.int32)
    b = np.rint(np.clip(test, 0, 1) * 255).astype(np.int32)
    d = (a - b).astype(np.float64)
    mse = float((d * d).mean())
    changed = int(np.any(d != 0, axis=2).sum()) if d.ndim == 3 else int((d != 0).sum())
    npx = a.shape[0] * a.shape[1]
    s = _ssim(a.astype(np.float64) if a.ndim == 3 else a[:, :, None].astype(np.float64),
              b.astype(np.float64) if b.ndim == 3 else b[:, :, None].astype(np.float64), 255.0)
    return {"comparable": True, "width": int(a.shape[1]), "height": int(a.shape[0]), "pixel_count": npx,
            "channels": int(a.shape[2]) if a.ndim == 3 else 1, "bit_depth": "8-bit/channel (analysis quantisation)",
            "mae": float(np.abs(d).mean()), "mse": mse, "psnr_db": (10 * math.log10(255.0 ** 2 / mse)) if mse > 0 else None,
            "psnr_infinite": mse == 0, "ssim": s, "lpips": LPIPS_STATUS, "changed_pixels": changed,
            "changed_percent": 100.0 * changed / max(npx, 1), "max_abs": float(np.abs(d).max()) if d.size else 0.0}


def psnr(ref: np.ndarray, test: np.ndarray) -> float:
    d = (np.clip(ref, 0, 1) - np.clip(test, 0, 1)).astype(np.float64)
    mse = float((d * d).mean())
    return 99.0 if mse <= 1e-12 else 10 * math.log10(1.0 / mse)


def signal_energy(s: np.ndarray) -> float:
    return float((s.astype(np.float64) ** 2).mean() * 255.0 ** 2)


def detection_metrics(labels, scores, threshold: float, seed: int = 0) -> dict:
    labels = list(map(int, labels))
    scores = list(map(float, scores))
    auc = auc_mann_whitney(labels, scores)
    c = confusion(labels, scores, threshold)
    return {"auc": auc, "auc_ci95": bootstrap_auc_ci(labels, scores, 500, seed), "roc": roc_curve(labels, scores),
            "threshold": threshold, **c,
            "tpr_ci95": wilson(c.get("tp", 0), c.get("tp", 0) + c.get("fn", 0)),
            "fpr_ci95": wilson(c.get("fp", 0), c.get("fp", 0) + c.get("tn", 0))}


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float64).ravel() - float(a.mean())
    b = b.astype(np.float64).ravel() - float(b.mean())
    den = math.sqrt(float((a * a).sum()) * float((b * b).sum()))
    return float((a * b).sum() / den) if den > 1e-12 else 0.0
