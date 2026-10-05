"""Multi-level 2D discrete wavelet transform (orthogonal Haar and Daubechies-2) with
periodic extension and perfect reconstruction, plus sub-band statistics.

Sub-band convention used throughout SynthProvenance (conventions vary in the
literature, as the taxonomy file notes):

    LL  low-pass horizontally and vertically (approximation)
    LH  low-pass horizontally, high-pass vertically  (responds to horizontal edges)
    HL  high-pass horizontally, low-pass vertically  (responds to vertical edges)
    HH  high-pass in both directions                 (diagonal detail)

Odd dimensions are edge-padded to even before each level and cropped on
reconstruction, so ``waverec2(wavedec2(x)) == x`` up to float rounding.
"""
from __future__ import annotations

import math

import numpy as np

from app.research.imaging import EPS, resize_plane

_S3 = math.sqrt(3.0)
FILTERS = {
    "haar": np.array([1.0, 1.0]) / math.sqrt(2.0),
    "db2": np.array([1 + _S3, 3 + _S3, 3 - _S3, 1 - _S3]) / (4 * math.sqrt(2.0)),
}
ORIENTATIONS = ("LH", "HL", "HH")


def _hg(wavelet: str) -> tuple[np.ndarray, np.ndarray]:
    if wavelet not in FILTERS:
        raise ValueError(f"Unknown wavelet {wavelet!r}; available: {', '.join(FILTERS)}")
    h = FILTERS[wavelet]
    g = np.array([(-1) ** k * h[len(h) - 1 - k] for k in range(len(h))])
    return h, g


def _analysis(x: np.ndarray, f: np.ndarray, axis: int) -> np.ndarray:
    out = None
    for k, c in enumerate(f):
        t = c * np.roll(x, -k, axis=axis)
        out = t if out is None else out + t
    sl = [slice(None)] * x.ndim
    sl[axis] = slice(0, None, 2)
    return out[tuple(sl)]


def _synthesis(a: np.ndarray, d: np.ndarray, h: np.ndarray, g: np.ndarray, axis: int) -> np.ndarray:
    shape = list(a.shape)
    shape[axis] *= 2
    ua, ud = np.zeros(shape, dtype=np.float64), np.zeros(shape, dtype=np.float64)
    sl = [slice(None)] * a.ndim
    sl[axis] = slice(0, None, 2)
    ua[tuple(sl)], ud[tuple(sl)] = a, d
    out = np.zeros(shape, dtype=np.float64)
    for k in range(len(h)):
        out += h[k] * np.roll(ua, k, axis=axis) + g[k] * np.roll(ud, k, axis=axis)
    return out


def dwt2(x: np.ndarray, wavelet: str = "haar") -> tuple[np.ndarray, dict, tuple[int, int]]:
    """One level. Returns (LL, {LH, HL, HH}, original_shape)."""
    h, g = _hg(wavelet)
    shape = x.shape
    xp = np.pad(x.astype(np.float64), ((0, shape[0] % 2), (0, shape[1] % 2)), mode="edge")
    lo = _analysis(xp, h, 1)
    hi = _analysis(xp, g, 1)
    ll, lh = _analysis(lo, h, 0), _analysis(lo, g, 0)
    hl, hh = _analysis(hi, h, 0), _analysis(hi, g, 0)
    return ll, {"LH": lh, "HL": hl, "HH": hh}, shape


def idwt2(ll: np.ndarray, det: dict, shape: tuple[int, int], wavelet: str = "haar") -> np.ndarray:
    h, g = _hg(wavelet)
    lo = _synthesis(ll, det["LH"], h, g, 0)
    hi = _synthesis(det["HL"], det["HH"], h, g, 0)
    x = _synthesis(lo, hi, h, g, 1)
    return x[: shape[0], : shape[1]]


def max_levels(shape: tuple[int, int], minimum: int = 8) -> int:
    n = min(shape)
    lev = 0
    while n >= 2 * minimum:
        n //= 2
        lev += 1
    return lev


def wavedec2(x: np.ndarray, levels: int = 3, wavelet: str = "haar") -> dict:
    levels = max(1, min(int(levels), max_levels(x.shape) or 1))
    cur = x.astype(np.float64)
    details, shapes = [], []
    for _ in range(levels):
        cur, det, shp = dwt2(cur, wavelet)
        details.append(det)
        shapes.append(shp)
    return {"wavelet": wavelet, "levels": levels, "LL": cur, "details": details, "shapes": shapes}


def waverec2(dec: dict) -> np.ndarray:
    cur = dec["LL"]
    for det, shp in zip(reversed(dec["details"]), reversed(dec["shapes"])):
        cur = idwt2(cur, det, shp, dec["wavelet"])
    return cur


def _kurtosis(v: np.ndarray) -> float:
    v = v.ravel().astype(np.float64)
    s = v.std()
    if s < EPS:
        return 0.0
    return float(((v - v.mean()) ** 4).mean() / s ** 4 - 3.0)


def hoyer_sparsity(v: np.ndarray) -> float:
    """Hoyer (2004) sparsity in [0, 1]: 0 = all equal magnitude, 1 = a single non-zero coefficient."""
    v = np.abs(v.ravel().astype(np.float64))
    n = v.size
    l2 = math.sqrt(float((v * v).sum()))
    if n < 2 or l2 < EPS:
        return 0.0
    return float((math.sqrt(n) - v.sum() / l2) / (math.sqrt(n) - 1))


def spatial_consistency(v: np.ndarray, block: int = 8) -> float:
    """1 / (1 + CV) of block-wise energy: 1 = energy spread uniformly over the image, -> 0 = concentrated."""
    h, w = v.shape
    b = max(2, min(block, h // 2 or 1, w // 2 or 1))
    hh, ww = (h // b) * b, (w // b) * b
    if hh == 0 or ww == 0:
        return 0.0
    e = (v[:hh, :ww] ** 2).reshape(hh // b, b, ww // b, b).mean(axis=(1, 3))
    m = float(e.mean())
    return float(1.0 / (1.0 + (e.std() / m))) if m > EPS else 0.0


def subband_stats(dec: dict) -> list[dict]:
    rows = []
    for lev, det in enumerate(dec["details"], 1):
        for o in ORIENTATIONS:
            c = det[o]
            rows.append({"level": lev, "band": o, "shape": list(c.shape), "energy": float((c * c).mean()),
                         "variance": float(c.var()), "kurtosis": _kurtosis(c), "sparsity": hoyer_sparsity(c),
                         "spatial_consistency": spatial_consistency(c)})
    ll = dec["LL"]
    rows.append({"level": dec["levels"], "band": "LL", "shape": list(ll.shape), "energy": float((ll * ll).mean()),
                 "variance": float(ll.var()), "kurtosis": _kurtosis(ll), "sparsity": hoyer_sparsity(ll),
                 "spatial_consistency": spatial_consistency(ll - ll.mean())})
    return rows


def cross_scale_persistence(dec: dict) -> list[dict]:
    """Correlation between |child| and up-sampled |parent| per orientation (Shapiro-style inter-scale dependency)."""
    out = []
    for lev in range(1, dec["levels"]):
        child, parent = dec["details"][lev - 1], dec["details"][lev]
        for o in ORIENTATIONS:
            c = np.abs(child[o])
            p = resize_plane(np.abs(parent[o]).astype(np.float32), (c.shape[1], c.shape[0]))
            cc, pp = c.ravel() - c.mean(), p.ravel() - p.mean()
            den = math.sqrt(float((cc * cc).sum()) * float((pp * pp).sum()))
            out.append({"levels": f"{lev}<-{lev + 1}", "band": o, "correlation": float((cc * pp).sum() / den) if den > EPS else 0.0})
    return out


def detail_residual(x: np.ndarray, levels: int = 2, wavelet: str = "haar") -> np.ndarray:
    """Image minus its level-``levels`` approximation: the reconstruction from detail bands only."""
    dec = wavedec2(x, levels, wavelet)
    dec["LL"] = np.zeros_like(dec["LL"])
    return waverec2(dec).astype(np.float32)


def bayes_shrink(x: np.ndarray, levels: int = 3, wavelet: str = "db2", strength: float = 1.0) -> tuple[np.ndarray, dict]:
    """BayesShrink soft-threshold denoising (Chang, Yu & Vetterli 2000). Returns (estimate, thresholds)."""
    dec = wavedec2(x, levels, wavelet)
    hh1 = dec["details"][0]["HH"]
    sigma_n = float(np.median(np.abs(hh1)) / 0.6745)
    thr = {}
    for lev, det in enumerate(dec["details"], 1):
        for o in ORIENTATIONS:
            c = det[o]
            sx = math.sqrt(max(float((c * c).mean()) - sigma_n ** 2, EPS))
            t = strength * sigma_n ** 2 / sx
            det[o] = np.sign(c) * np.maximum(np.abs(c) - t, 0.0)
            thr[f"L{lev}{o}"] = t
    return waverec2(dec).astype(np.float32), {"sigma_noise": sigma_n, "thresholds": thr}


def analyse(x: np.ndarray, levels: int = 3, wavelet: str = "haar") -> dict:
    dec = wavedec2(x, levels, wavelet)
    maps = {}
    for lev, det in enumerate(dec["details"], 1):
        for o in ORIENTATIONS:
            maps[f"dwt_L{lev}_{o}"] = np.abs(det[o]).astype(np.float32)
    maps["dwt_LL"] = dec["LL"].astype(np.float32)
    return {"wavelet": wavelet, "levels": dec["levels"], "subbands": subband_stats(dec),
            "persistence": cross_scale_persistence(dec), "maps": maps}
