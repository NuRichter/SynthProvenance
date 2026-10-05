"""Signal / content separation and reconstruction study.

A separation method decomposes an image into an estimated content layer and a
candidate-signal layer:

    X = content_estimate + candidate_signal   (+ residual)

The panels requested by the Reconstruction Lab are produced directly:

    Original · Candidate Signal · Estimated Content · Residual · Reconstructed · Difference

Reconstructed = content_estimate (the content with the candidate signal removed), and
Difference = Original - Reconstructed. For a CONTROLLED SURROGATE case the known signal
is available as ground truth, so the recovered candidate is scored against it
(correlation, recovered energy fraction) and the detector is re-run on the estimated
content to quantify how much of the known signal the separation removed. This is a
forensic separation/analysis study with ground truth, not a detector-evasion search:
the methods are fixed decompositions, and the figures of merit are recovery accuracy
and reconstruction fidelity.

Methods (all operate on the luminance plane; chroma is carried through unchanged):

    highpass    content = Gaussian-blurred image; candidate = high-pass residual
    wavelet     content = BayesShrink wavelet estimate; candidate = detail removed
    fft         content = spectrum with blindly-detected anomalous bins attenuated
    dct         content = image with block-DCT high band attenuated
    robust_pca  I = L + S + E; content = L (+E), candidate = S
    self_prior  content = iterative edge-aware (guided) smoothing; candidate = residual
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from app.research import metrics as M
from app.research import rpca
from app.research import spectral as S_
from app.research import surrogate as SUR
from app.research import wavelet as W
from app.research.imaging import (EPS, box_mean, gaussian_blur, luminance, rgb_to_ycbcr, to_rgb3, ycbcr_to_rgb)

METHODS = ("highpass", "wavelet", "fft", "dct", "robust_pca", "self_prior")
METHOD_LABELS = {
    "highpass": "High-pass separation (content = Gaussian low-pass)",
    "wavelet": "Wavelet separation (content = BayesShrink estimate)",
    "fft": "FFT separation (attenuate blindly-detected anomalous bins)",
    "dct": "Block-DCT separation (attenuate high band)",
    "robust_pca": "Robust PCA  I = L + S + E  (content = L+E, candidate = S)",
    "self_prior": "Self-supervised image prior (guided edge-aware smoothing)",
}


def _spectral_attenuate(y: np.ndarray, anomaly_z: float = 2.5, gain: float = 0.0) -> np.ndarray:
    """Content estimate that attenuates (by ``gain``) spectral bins standing out from the radial background.

    Bins are selected *blindly* from the image's own spectrum (no key), by a robust per-radius z-score, so this
    is an isolation of anomalous periodic structure, not keyed removal.
    """
    f = np.fft.fft2(y.astype(np.float64) - float(y.mean()))
    lm = np.log1p(np.abs(f))
    fy = np.fft.fftfreq(y.shape[0])[:, None] * 2
    fx = np.fft.fftfreq(y.shape[1])[None, :] * 2
    rb = np.minimum((np.hypot(fy, fx) * 64).astype(int), 90)
    med = np.zeros(rb.max() + 1)
    mad = np.ones(rb.max() + 1)
    for b in range(rb.max() + 1):
        v = lm[rb == b]
        if v.size:
            med[b] = np.median(v)
            mad[b] = np.median(np.abs(v - med[b])) * 1.4826 + 1e-6
    mask = (lm - med[rb]) / mad[rb] > anomaly_z
    f[mask] *= gain
    return np.fft.ifft2(f).real.astype(np.float32)


def _guided_smooth(y: np.ndarray, iters: int = 8, r: int = 2, eps: float = 1e-3) -> np.ndarray:
    """Self-guided edge-aware smoothing (He et al. guided filter, self-guided), repeated. A learning-free image prior."""
    out = y.astype(np.float32)
    for _ in range(int(iters)):
        mean = box_mean(out, r)
        corr = box_mean(out * out, r)
        var = corr - mean * mean
        a = var / (var + eps)
        b = mean - a * mean
        out = a * out + b
    return out


def _content_candidate(y: np.ndarray, method: str, params: dict):
    if method == "highpass":
        c = gaussian_blur(y, float(params.get("sigma", 1.2)))
    elif method == "wavelet":
        c, _ = W.bayes_shrink(y, int(params.get("levels", 3)), str(params.get("wavelet", "db2")),
                              float(params.get("strength", 1.0)))
    elif method == "fft":
        c = _spectral_attenuate(y, float(params.get("anomaly_z", 2.5)), float(params.get("gain", 0.0)))
    elif method == "dct":
        from app.research import dct as D
        hp = D.dct_residual(y, keep_low=int(params.get("keep_low", 3)))
        c = y - float(params.get("gain", 1.0)) * hp
    elif method == "robust_pca":
        res = rpca.decompose(y, mode=str(params.get("mode", "image")), max_iter=int(params.get("max_iter", 60)),
                             patch=int(params.get("patch", 16)))
        return (res["L"] + res["E"]).astype(np.float32), res["S"].astype(np.float32), res
    elif method == "self_prior":
        c = _guided_smooth(y, int(params.get("iters", 8)), int(params.get("radius", 2)))
    else:
        raise ValueError(f"Unknown separation method {method!r}")
    return c.astype(np.float32), (y - c).astype(np.float32), {}


def _merge_luma(content_y: np.ndarray, src: np.ndarray) -> np.ndarray:
    if src.shape[2] == 1:
        out = content_y[:, :, None]
    else:
        ycc = rgb_to_ycbcr(src)
        base = ycbcr_to_rgb(ycc)
        new = ycbcr_to_rgb(np.dstack([content_y, ycc[:, :, 1], ycc[:, :, 2]]))
        out = src + (new - base)
    return np.clip(out, 0, 1).astype(np.float32)


@dataclass
class SeparationResult:
    method: str
    label: str
    params: dict
    panels: dict = field(repr=False, default_factory=dict)   # float planes/images for display
    candidate_stats: dict = field(default_factory=dict)
    reconstruction: dict = field(default_factory=dict)
    ground_truth: dict = field(default_factory=dict)
    solver: dict = field(default_factory=dict)
    runtime_s: float = 0.0

    def to_dict(self) -> dict:
        d = {k: getattr(self, k) for k in ("method", "label", "params", "candidate_stats", "reconstruction",
                                           "ground_truth", "solver", "runtime_s")}
        return d


def separate(img: np.ndarray, method: str = "highpass", params: dict | None = None,
             surrogate_cfg: SUR.SurrogateConfig | None = None, clean: np.ndarray | None = None,
             progress=None) -> SeparationResult:
    """Decompose ``img``. With ``surrogate_cfg`` (and optionally the ``clean`` image), score against ground truth."""
    params = dict(params or {})
    t0 = time.perf_counter()
    y = luminance(img)
    if progress:
        progress(20, f"Separating ({method})")
    content_y, candidate_y, solver = _content_candidate(y, method, params)
    content_img = _merge_luma(content_y, img)
    cand = candidate_y
    from app.research.residuals import stats as rstats
    cs = rstats(cand, with_spectrum=False)["stats"]
    recon = M.fidelity(img, content_img)
    recon["difference_energy"] = float(((luminance(img) - content_y) ** 2).mean())
    panels = {"original": img, "candidate_signal": cand, "estimated_content": content_img,
              "residual": (y - content_y - 0).astype(np.float32), "reconstructed": content_img,
              "difference": (img - content_img).astype(np.float32)}
    gt = {}
    if surrogate_cfg is not None:
        if progress:
            progress(70, "Scoring against surrogate ground truth")
        d_after = SUR.detect(content_img, surrogate_cfg)
        d_before = SUR.detect(img, surrogate_cfg)
        gt = {"known_signal_available": True, "score_before": d_before.score, "score_after": d_after.score,
              "still_detected_after": d_after.detected,
              "signal_reduction": (1.0 - max(0.0, d_after.score) / d_before.score) if d_before.score > EPS else None}
        known = surrogate_cfg and clean is not None
        if known:
            known_sig = luminance(img) - luminance(clean)
            gt["candidate_vs_known_corr"] = M.pearson(cand, known_sig)
            e_known = float((known_sig ** 2).sum()) or EPS
            gt["recovered_energy_fraction"] = float((cand * known_sig).sum()) / e_known
            gt["candidate_noise_ratio"] = float((cand ** 2).mean()) / (float((known_sig ** 2).mean()) + EPS)
    return SeparationResult(method, METHOD_LABELS[method], params, panels, cs, recon, gt,
                            solver.get("summary", {}) if solver else {}, time.perf_counter() - t0)
