"""Descriptive image statistics for the Advanced Forensic Lab.

Every value here is a descriptive statistic of the decoded pixels. None of
them is an authenticity test or an AI detector, and the UI and reports say so.
"""
from __future__ import annotations

import time

import numpy as np
from PIL import Image

from app.core.image_loader import canonical_image

DISCLAIMER = "Descriptive statistics only. Not an authenticity verdict or AI-detection result."
MAX_ANALYSIS_PIXELS = 4_000_000


def _working_image(img: Image.Image) -> tuple[Image.Image, int]:
    c = canonical_image(img)
    if c.mode not in ("L", "RGB", "RGBA", "LA"):
        c = c.convert("RGB")
    factor = 1
    w, h = c.size
    while (w // factor) * (h // factor) > MAX_ANALYSIS_PIXELS:
        factor += 1
    if factor > 1:
        c = c.reduce(factor)
    return c, factor


def luminance(arr: np.ndarray) -> np.ndarray:
    if arr.ndim == 2:
        return arr.astype(np.float64)
    if arr.shape[2] >= 3:
        return 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
    return arr[..., 0].astype(np.float64)


def entropy_bits(hist: np.ndarray) -> float:
    p = hist.astype(np.float64)
    p = p[p > 0] / max(p.sum(), 1.0)
    return float(-(p * np.log2(p)).sum())


def edge_density(lum: np.ndarray, threshold: float = 40.0) -> float:
    if lum.shape[0] < 3 or lum.shape[1] < 3:
        return 0.0
    gx = (lum[1:-1, 2:] - lum[1:-1, :-2]) * 2 + (lum[:-2, 2:] - lum[:-2, :-2]) + (lum[2:, 2:] - lum[2:, :-2])
    gy = (lum[2:, 1:-1] - lum[:-2, 1:-1]) * 2 + (lum[2:, :-2] - lum[:-2, :-2]) + (lum[2:, 2:] - lum[:-2, 2:])
    mag = np.hypot(gx, gy)
    return float((mag > threshold).mean())


def noise_sigma(lum: np.ndarray) -> float:
    """Immerkaer (1996) fast noise-variance estimate (Laplacian-difference kernel)."""
    h, w = lum.shape
    if h < 3 or w < 3:
        return 0.0
    L = (
        lum[:-2, :-2] - 2 * lum[:-2, 1:-1] + lum[:-2, 2:]
        - 2 * lum[1:-1, :-2] + 4 * lum[1:-1, 1:-1] - 2 * lum[1:-1, 2:]
        + lum[2:, :-2] - 2 * lum[2:, 1:-1] + lum[2:, 2:]
    )
    return float(np.sqrt(np.pi / 2.0) * np.abs(L).sum() / (6.0 * (w - 2) * (h - 2)))


def fft_analysis(lum: np.ndarray, size: int = 256) -> dict:
    h, w = lum.shape
    s = min(h, w, 1024)
    y0, x0 = (h - s) // 2, (w - s) // 2
    tile = lum[y0 : y0 + s, x0 : x0 + s]
    tile = tile - tile.mean()
    win = np.outer(np.hanning(s), np.hanning(s))
    spec = np.fft.fftshift(np.abs(np.fft.fft2(tile * win)))
    logmag = np.log1p(spec)
    # radial profile
    yy, xx = np.indices(spec.shape)
    r = np.hypot(yy - s / 2, xx - s / 2).astype(np.int32)
    power = spec**2
    radial = np.bincount(r.ravel(), power.ravel()) / np.maximum(np.bincount(r.ravel()), 1)
    nyq = s // 2
    radial = radial[1:nyq]
    freqs = np.arange(1, nyq)
    total = float(power.sum()) or 1.0
    hf_mask = r > (nyq // 2)
    hf_ratio = float(power[hf_mask].sum() / total)
    valid = radial > 0
    slope = float(np.polyfit(np.log(freqs[valid]), np.log(radial[valid]), 1)[0]) if valid.sum() > 4 else None
    img = Image.fromarray(
        np.clip(255.0 * (logmag - logmag.min()) / max(np.ptp(logmag), 1e-9), 0, 255).astype(np.uint8)
    ).resize((size, size), Image.Resampling.BILINEAR)
    step = max(1, len(radial) // 64)
    return {
        "tile_size": s,
        "high_frequency_energy_ratio": hf_ratio,
        "spectral_slope": slope,
        "radial_profile": [float(v) for v in np.log10(radial[::step] + 1e-12)],
        "spectrum_png_array": np.asarray(img),
    }


def blockiness(lum: np.ndarray) -> float | None:
    """Ratio of mean absolute luminance step on 8-px grid boundaries vs elsewhere (1.0 = no grid)."""
    h, w = lum.shape
    if w < 32 or h < 32:
        return None
    dx = np.abs(np.diff(lum, axis=1))
    cols = np.arange(dx.shape[1])
    on = dx[:, (cols % 8) == 7].mean()
    off = dx[:, (cols % 8) != 7].mean()
    return float(on / off) if off > 0 else None


def compute_statistics(img: Image.Image, jpeg_quant: dict | None = None) -> dict:
    t0 = time.perf_counter()
    work, factor = _working_image(img)
    arr = np.asarray(work)
    if arr.ndim == 2:
        arr = arr[:, :, None]
    bands = work.getbands()
    hist = np.asarray(canonical_image(img).convert("RGB" if len(bands) >= 3 else "L").histogram()).reshape(-1, 256)
    lum = luminance(arr[..., :3] if arr.shape[2] >= 3 else arr[..., 0])
    lum_hist = np.bincount(np.clip(lum, 0, 255).astype(np.uint8).ravel(), minlength=256)
    color_bands = arr[..., :3] if arr.shape[2] >= 3 else arr[..., :1]
    stats: dict = {
        "disclaimer": DISCLAIMER,
        "analysis_size": list(work.size),
        "reduction_factor": factor,
        "histograms": {("RGB"[i] if len(hist) == 3 else "L"): hist[i].tolist() for i in range(len(hist))},
        "luminance_histogram": lum_hist.tolist(),
        "entropy_bits": entropy_bits(lum_hist),
        "channel_entropy_bits": {("RGB"[i] if len(hist) == 3 else "L"): entropy_bits(hist[i]) for i in range(len(hist))},
        "edge_density": edge_density(lum),
        "noise_sigma_estimate": noise_sigma(lum),
        "color_distribution": {
            "mean": [float(color_bands[..., i].mean()) for i in range(color_bands.shape[2])],
            "std": [float(color_bands[..., i].std()) for i in range(color_bands.shape[2])],
        },
        "blockiness_8px": blockiness(lum),
    }
    if color_bands.shape[2] == 3:
        mx = color_bands.max(axis=2).astype(np.float64)
        mn = color_bands.min(axis=2).astype(np.float64)
        sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
        stats["color_distribution"]["saturation_mean"] = float(sat.mean())
        packed = (color_bands[..., 0].astype(np.uint32) << 16) | (color_bands[..., 1].astype(np.uint32) << 8) | color_bands[..., 2]
        stats["color_distribution"]["unique_colors"] = int(np.unique(packed).size)
        stats["color_distribution"]["unique_colors_basis"] = "exact" if factor == 1 else f"on {factor}x reduced image"
    try:
        stats["fft"] = fft_analysis(lum)
    except (ValueError, MemoryError, np.linalg.LinAlgError) as exc:
        stats["fft"] = {"error": str(exc)}
    if jpeg_quant:
        stats["jpeg_quantization"] = jpeg_quant
    stats["duration_ms"] = (time.perf_counter() - t0) * 1000.0
    return stats


def strip_arrays(stats: dict) -> dict:
    """Remove non-serialisable preview arrays before persisting."""
    out = dict(stats)
    if isinstance(out.get("fft"), dict):
        fft = dict(out["fft"])
        fft.pop("spectrum_png_array", None)
        out["fft"] = fft
    return out
