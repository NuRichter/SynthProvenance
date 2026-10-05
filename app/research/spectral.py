"""FFT engine: magnitude, log magnitude, phase, radial and angular spectra, band energy,
spectral-tail analysis, periodic-peak detection and a Synthbuster-style residual spectrum.

Frequencies are normalised so that 1.0 is the Nyquist frequency along an axis
(0.5 cycles / pixel). Radial profiles stop at 1.0 (corners are excluded).

References (see Research Library): Durall et al. 2020 and Dzanic et al. 2020 for the
radial power spectrum and high-frequency tail, Frank et al. 2020 for frequency-domain
cues, Bammey 2023 (Synthbuster) for residual-spectrum peaks. Values are descriptive
measurements; no AI-generation verdict is derived from them.
"""
from __future__ import annotations

import numpy as np

from app.research.imaging import EPS, box_mean, conv2d, tile_grid

BANDS = ((0.0, 0.125, "very low"), (0.125, 0.25, "low"), (0.25, 0.5, "mid"), (0.5, 0.75, "high"), (0.75, 1.0, "very high"))


def hann2d(h: int, w: int) -> np.ndarray:
    return np.outer(np.hanning(h), np.hanning(w)).astype(np.float32)


def freq_grid(h: int, w: int) -> tuple[np.ndarray, np.ndarray]:
    """Shifted normalised frequency grid: radius (1.0 = Nyquist) and angle in degrees [0, 180)."""
    fy = np.fft.fftshift(np.fft.fftfreq(h)) * 2.0
    fx = np.fft.fftshift(np.fft.fftfreq(w)) * 2.0
    yy, xx = np.meshgrid(fy, fx, indexing="ij")
    r = np.hypot(yy, xx)
    ang = (np.degrees(np.arctan2(yy, xx)) + 180.0) % 180.0
    return r.astype(np.float32), ang.astype(np.float32)


def spectrum(x: np.ndarray, window: bool = True) -> dict:
    """Centred 2D FFT of a plane. Returns magnitude, log magnitude, phase and power."""
    x = x.astype(np.float64)
    x = x - x.mean()
    if window:
        x = x * hann2d(*x.shape)
    f = np.fft.fftshift(np.fft.fft2(x))
    mag = np.abs(f)
    return {"magnitude": mag.astype(np.float32), "log_magnitude": np.log1p(mag).astype(np.float32),
            "phase": np.angle(f).astype(np.float32), "power": (mag * mag).astype(np.float64)}


def welch_power(x: np.ndarray, tile: int = 256, overlap: int = 128, max_tiles: int = 400) -> np.ndarray:
    """Averaged windowed periodogram over overlapping tiles (any-resolution, bounded memory)."""
    h, w = x.shape
    tile = int(min(tile, h, w))
    tile -= tile % 2
    tiles = tile_grid(h, w, tile, overlap)
    if len(tiles) > max_tiles:  # deterministic sub-sampling of tiles for very large images
        idx = np.linspace(0, len(tiles) - 1, max_tiles).round().astype(int)
        tiles = [tiles[i] for i in idx]
    win = hann2d(tile, tile)
    acc = np.zeros((tile, tile), dtype=np.float64)
    n = 0
    for y0, y1, x0, x1 in tiles:
        t = x[y0:y1, x0:x1]
        if t.shape != (tile, tile):
            continue
        t = (t - t.mean()) * win
        f = np.fft.fftshift(np.fft.fft2(t))
        acc += (f.real ** 2 + f.imag ** 2)
        n += 1
    return acc / max(n, 1)


def radial_profile(power: np.ndarray, nbins: int = 64) -> tuple[np.ndarray, np.ndarray]:
    r, _ = freq_grid(*power.shape)
    edges = np.linspace(0.0, 1.0, nbins + 1)
    idx = np.digitize(r.ravel(), edges) - 1
    ok = (idx >= 0) & (idx < nbins)
    sums = np.bincount(idx[ok], weights=power.ravel()[ok], minlength=nbins)
    cnt = np.bincount(idx[ok], minlength=nbins)
    prof = sums / np.maximum(cnt, 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    return centers, prof


def angular_profile(power: np.ndarray, nbins: int = 36, rmin: float = 0.1, rmax: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    r, ang = freq_grid(*power.shape)
    sel = (r >= rmin) & (r <= rmax)
    edges = np.linspace(0.0, 180.0, nbins + 1)
    idx = np.clip(np.digitize(ang[sel], edges) - 1, 0, nbins - 1)
    sums = np.bincount(idx, weights=power[sel], minlength=nbins)
    cnt = np.bincount(idx, minlength=nbins)
    return 0.5 * (edges[:-1] + edges[1:]), sums / np.maximum(cnt, 1)


def band_energy(power: np.ndarray) -> list[dict]:
    r, _ = freq_grid(*power.shape)
    total = float(power[(r > 0) & (r <= 1.0)].sum()) or EPS
    out = []
    for lo, hi, name in BANDS:
        sel = (r > lo) & (r <= hi)
        out.append({"band": name, "range": [lo, hi], "fraction": float(power[sel].sum()) / total})
    return out


def spectral_tail(freqs: np.ndarray, prof: np.ndarray, fit=(0.1, 0.5), tail=(0.75, 1.0)) -> dict:
    """Fit log10 P = a + b log10 f on ``fit`` and measure the deviation of the tail (dB) from the extrapolation."""
    ok = (prof > 0) & np.isfinite(prof)
    sel = ok & (freqs >= fit[0]) & (freqs <= fit[1])
    tl = ok & (freqs >= tail[0]) & (freqs <= tail[1])
    if sel.sum() < 3 or tl.sum() < 2:
        return {"status": "INSUFFICIENT DATA"}
    lx, ly = np.log10(freqs[sel]), np.log10(prof[sel])
    b, a = np.polyfit(lx, ly, 1)
    pred = a + b * lx
    ss_res = float(((ly - pred) ** 2).sum())
    ss_tot = float(((ly - ly.mean()) ** 2).sum()) or EPS
    tail_pred = a + b * np.log10(freqs[tl])
    dev_db = 10.0 * (np.log10(prof[tl]) - tail_pred)
    return {"status": "COMPLETE", "slope": float(b), "intercept": float(a), "r2": 1.0 - ss_res / ss_tot,
            "tail_deviation_db": float(dev_db.mean()), "tail_deviation_max_db": float(dev_db.max()),
            "fit_range": list(fit), "tail_range": list(tail),
            "interpretation": "Positive tail deviation = more high-frequency energy than the power-law fit predicts; "
                              "negative = less. Descriptive only."}


def peak_analysis(log_mag: np.ndarray, k: float = 6.0, max_peaks: int = 24, exclude_r: float = 0.04) -> dict:
    """Isolated spectral peaks (periodic structure): log magnitude minus local background, robust z-score."""
    bg = box_mean(log_mag, 4)
    resid = log_mag - bg
    r, _ = freq_grid(*log_mag.shape)
    valid = r > exclude_r
    med = float(np.median(resid[valid]))
    mad = float(np.median(np.abs(resid[valid] - med))) * 1.4826 or EPS
    z = (resid - med) / mad
    z[~valid] = 0
    h, w = z.shape
    cand = np.argwhere(z > k)
    peaks = []
    for (yy, xx) in cand[np.argsort(-z[cand[:, 0], cand[:, 1]])] if len(cand) else []:
        if xx < w // 2 or (xx == w // 2 and yy < h // 2):  # keep one of each conjugate pair
            continue
        if any(abs(yy - p["y"]) <= 2 and abs(xx - p["x"]) <= 2 for p in peaks):
            continue
        fy, fx = (yy - h // 2) / (h / 2.0), (xx - w // 2) / (w / 2.0)
        peaks.append({"y": int(yy), "x": int(xx), "fy": float(fy), "fx": float(fx), "z": float(z[yy, xx])})
        if len(peaks) >= max_peaks:
            break
    grid_hits = 0
    for p in peaks:  # peaks on the up-sampling grid (multiples of 1/8 of the sampling rate)
        if all(abs(v * 4 - round(v * 4)) < 0.02 for v in (p["fy"], p["fx"])):
            grid_hits += 1
    return {"z_map": z.astype(np.float32), "peaks": peaks, "n_peaks": len(peaks), "grid_aligned_peaks": grid_hits,
            "threshold_z": k,
            "periodic_artifact_score": float(sum(min(p["z"], 50.0) for p in peaks) / max(1, len(peaks)) if peaks else 0.0)}


CROSS_DIFF = np.array([[1, -1], [-1, 1]], dtype=np.float32)


def cross_difference(x: np.ndarray) -> np.ndarray:
    """Cross-difference high-pass x(i,j) - x(i+1,j) - x(i,j+1) + x(i+1,j+1) (Synthbuster-style residual)."""
    return conv2d(x, CROSS_DIFF)


def synthbuster_features(x: np.ndarray, tile: int = 256) -> dict:
    """Mean residual-spectrum magnitude at the (k/8, l/8) frequency lattice (k, l = 0..4), normalised by the median.

    ADAPTED from Bammey (2023): the published detector feeds such features into a trained classifier; no
    classifier is bundled here, so the output is a feature vector plus a descriptive lattice-peak ratio.
    """
    res = cross_difference(x)
    p = welch_power(res, tile=tile, overlap=tile // 2)
    mag = np.sqrt(p)
    n = mag.shape[0]
    c = n // 2
    med = float(np.median(mag)) or EPS
    feats, names = [], []
    for ky in range(0, 5):
        for kx in range(0, 5):
            if ky == 0 and kx == 0:
                continue
            yy, xx = c + int(round(ky * n / 8.0)) - (1 if ky == 4 else 0), c + int(round(kx * n / 8.0)) - (1 if kx == 4 else 0)
            v = float(mag[max(0, yy - 1):yy + 2, max(0, xx - 1):xx + 2].max()) / med
            feats.append(v)
            names.append(f"({ky}/8,{kx}/8)")
    return {"features": feats, "names": names, "lattice_peak_ratio": float(np.mean(feats)),
            "log_magnitude": np.log1p(mag).astype(np.float32)}


def analyse(x: np.ndarray, tile: int = 512, nbins: int = 64) -> dict:
    """Full FFT analysis of a plane: global spectrum (for maps) + Welch spectrum (for statistics)."""
    h, w = x.shape
    big = h * w > 4096 * 4096
    sp = spectrum(x if not big else x[: min(h, 4096), : min(w, 4096)])
    pw = welch_power(x, tile=min(tile, h, w), overlap=min(tile, h, w) // 2)
    f, prof = radial_profile(pw, nbins)
    a, aprof = angular_profile(pw)
    tail = spectral_tail(f, prof)
    peaks = peak_analysis(np.log1p(np.sqrt(pw)))
    return {"maps": {"fft_log_magnitude": sp["log_magnitude"], "fft_phase": sp["phase"],
                     "fft_peak_z": peaks.pop("z_map")},
            "radial": {"freq": f.tolist(), "power": prof.tolist()},
            "angular": {"deg": a.tolist(), "power": aprof.tolist()},
            "bands": band_energy(pw), "tail": tail, "peaks": peaks,
            "note": "global spectrum computed on the full plane" if not big else
                    "global spectrum map computed on the top-left 4096x4096 region; statistics use all tiles"}
