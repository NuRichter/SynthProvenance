"""Residual engine: residual operators R = X - estimate(X) and residual statistics.

Operators
---------
gaussian     X - G_sigma * X
laplacian    3x3 Laplacian response
highpass     SRM "KV" 5x5 high-pass (Fridrich & Kodovsky 2012)
median       X - median3(X)
wavelet      reconstruction from detail sub-bands only (LL removed)
dct          block-DCT high-pass (low-frequency coefficients removed)
multiscale   mean of normalised difference-of-Gaussian residuals at sigma 1, 2, 4
cross_diff   Synthbuster-style cross-difference filter
denoise      X - BayesShrink(X)  (wavelet-denoiser residual, PRNU-style R = X - Denoise(X))

Statistics: residual histogram, entropy (bits, 256-bin quantisation over +/-4 sigma),
energy (mean square), kurtosis, normalised spatial autocorrelation (lags 1..8 and
the 2D autocorrelation map) and frequency response (radial spectrum of the residual).
"""
from __future__ import annotations

import numpy as np

from app.research import dct as D
from app.research import spectral as S
from app.research import wavelet as W
from app.research.imaging import EPS, LAPLACIAN, SRM_KV, conv2d, gaussian_blur, median3

OPERATORS = ("gaussian", "laplacian", "highpass", "median", "wavelet", "dct", "multiscale", "cross_diff", "denoise")


def residual(x: np.ndarray, op: str = "gaussian", sigma: float = 1.0, levels: int = 2) -> np.ndarray:
    x = x.astype(np.float32)
    if op == "gaussian":
        return x - gaussian_blur(x, sigma)
    if op == "laplacian":
        return conv2d(x, LAPLACIAN)
    if op == "highpass":
        return conv2d(x, SRM_KV)
    if op == "median":
        return x - median3(x)
    if op == "wavelet":
        return W.detail_residual(x, levels=levels)
    if op == "dct":
        return D.dct_residual(x)
    if op == "multiscale":
        acc = np.zeros_like(x)
        for s in (1.0, 2.0, 4.0):
            r = gaussian_blur(x, s / 2.0) - gaussian_blur(x, s)
            acc += r / (float(r.std()) + EPS)
        return acc / 3.0
    if op == "cross_diff":
        return S.cross_difference(x)
    if op == "denoise":
        est, _ = W.bayes_shrink(x, levels=3, wavelet="db2")
        return x - est
    raise ValueError(f"Unknown residual operator {op!r}; available: {', '.join(OPERATORS)}")


def autocorrelation(r: np.ndarray, max_lag: int = 8, map_radius: int = 16) -> dict:
    r = r.astype(np.float64) - r.mean()
    h, w = r.shape
    f = np.fft.fft2(r, s=(2 * h, 2 * w))
    ac = np.fft.ifft2(f * np.conj(f)).real
    ac = ac / (ac[0, 0] + EPS)
    lags_h = [float(ac[0, k]) for k in range(1, max_lag + 1)]
    lags_v = [float(ac[k, 0]) for k in range(1, max_lag + 1)]
    lags_d = [float(ac[k, k]) for k in range(1, max_lag + 1)]
    sh = np.fft.fftshift(ac)
    cy, cx = sh.shape[0] // 2, sh.shape[1] // 2
    m = sh[cy - map_radius:cy + map_radius + 1, cx - map_radius:cx + map_radius + 1].astype(np.float32)
    off = m.copy()
    off[map_radius, map_radius] = 0
    return {"lag_h": lags_h, "lag_v": lags_v, "lag_d": lags_d, "map": m,
            "max_offcentre": float(np.abs(off).max()), "periodic_lag8_h": lags_h[7] if max_lag >= 8 else None,
            "periodic_lag8_v": lags_v[7] if max_lag >= 8 else None}


def stats(r: np.ndarray, with_spectrum: bool = True) -> dict:
    v = r.astype(np.float64).ravel()
    sd = float(v.std())
    lim = 4.0 * sd if sd > EPS else 1.0
    hist, edges = np.histogram(np.clip(v, -lim, lim), bins=256, range=(-lim, lim))
    p = hist / max(hist.sum(), 1)
    nz = p[p > 0]
    kurt = float(((v - v.mean()) ** 4).mean() / sd ** 4 - 3.0) if sd > EPS else 0.0
    ac = autocorrelation(r if r.size <= 4_000_000 else r[: 2000, : 2000])
    out = {"mean": float(v.mean()), "std": sd, "energy": float((v * v).mean()), "kurtosis": kurt,
           "entropy_bits": float(-(nz * np.log2(nz)).sum()), "histogram": {"edges": [float(edges[0]), float(edges[-1])],
                                                                          "counts": hist.tolist()},
           "autocorrelation": {k: ac[k] for k in ("lag_h", "lag_v", "lag_d", "max_offcentre", "periodic_lag8_h",
                                                  "periodic_lag8_v")}}
    maps = {"autocorrelation": ac["map"]}
    if with_spectrum and min(r.shape) >= 16:
        pw = S.welch_power(r, tile=min(256, *r.shape), overlap=min(256, *r.shape) // 2)
        f, prof = S.radial_profile(pw, 32)
        out["frequency_response"] = {"freq": f.tolist(), "power": prof.tolist()}
    return {"stats": out, "maps": maps}


def analyse(x: np.ndarray, ops: tuple = ("gaussian", "laplacian", "highpass", "wavelet", "dct", "multiscale")) -> dict:
    res, maps = {}, {}
    for op in ops:
        r = residual(x, op)
        s = stats(r)
        res[op] = s["stats"]
        maps[f"residual_{op}"] = r
        maps[f"autocorr_{op}"] = s["maps"]["autocorrelation"]
    return {"operators": res, "maps": maps}
