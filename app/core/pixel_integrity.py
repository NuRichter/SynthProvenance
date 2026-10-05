"""Pixel Integrity Engine.

A result is labelled PIXEL-EXACT only when the canonical decoded pixel
arrays have identical shape, identical dtype and zero differing samples.
Everything is measured; nothing is assumed from file names, formats or
encoder settings.
"""
from __future__ import annotations

import time

import numpy as np
from PIL import Image

from app.core.hashing import pixel_hash
from app.core.image_loader import canonical_image, data_range_for, to_array
from app.models.metrics import VERDICT_CHANGED, VERDICT_EXACT, VERDICT_NOT_COMPARABLE, PixelIntegrityResult

STRIP_ROWS = 512
SSIM_WIN = 7
_K1, _K2 = 0.01, 0.03


def _align(img_a: Image.Image, img_b: Image.Image) -> tuple[np.ndarray, np.ndarray, str, list[str]]:
    ca, cb = canonical_image(img_a), canonical_image(img_b)
    notes: list[str] = []
    if ca.mode == cb.mode:
        return to_array(ca), to_array(cb), ca.mode, notes
    alpha = any(m in ("RGBA", "LA") for m in (ca.mode, cb.mode))
    gray = all(m in ("L", "LA", "I;16", "I;16B", "I;16L", "I", "F") for m in (ca.mode, cb.mode))
    target = ("LA" if alpha else "L") if gray else ("RGBA" if alpha else "RGB")
    notes.append(f"Modes differ ({ca.mode} vs {cb.mode}); both converted to {target} for measurement.")
    if any(m in ("I;16", "I;16B", "I;16L", "I", "F") for m in (ca.mode, cb.mode)):
        notes.append("High-bit-depth data was reduced to 8-bit for alignment; comparison is approximate.")
    return to_array(ca.convert(target)), to_array(cb.convert(target)), target, notes


def _diff_stats(a: np.ndarray, b: np.ndarray) -> dict:
    h = a.shape[0]
    wide = np.float64 if (np.issubdtype(a.dtype, np.floating) or np.issubdtype(b.dtype, np.floating)) else np.int64
    sum_abs = 0.0
    sum_sq = 0.0
    max_abs = 0.0
    changed = 0
    for r0 in range(0, h, STRIP_ROWS):
        sa = a[r0 : r0 + STRIP_ROWS].astype(wide)
        sb = b[r0 : r0 + STRIP_ROWS].astype(wide)
        d = sa - sb
        ad = np.abs(d)
        sum_abs += float(ad.sum())
        sum_sq += float((d * d).sum()) if wide is np.float64 else float(np.square(d, dtype=np.int64).sum())
        m = float(ad.max()) if ad.size else 0.0
        max_abs = max(max_abs, m)
        changed += int(np.any(d != 0, axis=2).sum())
    n = a.size
    return {"sum_abs": sum_abs, "sum_sq": sum_sq, "max_abs": max_abs, "changed": changed, "samples": n}


def _box_mean(x: np.ndarray, k: int) -> np.ndarray:
    """Valid-mode k x k mean filter via integral image (vectorised)."""
    c = np.cumsum(np.cumsum(x, axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0)))
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return s / float(k * k)


def ssim(a: np.ndarray, b: np.ndarray, data_range: float) -> float | None:
    """Mean SSIM (Wang et al. 2004), 7x7 uniform window, sample covariance, per-channel mean."""
    h, w = a.shape[:2]
    k = SSIM_WIN
    if h < k or w < k:
        return None
    c1 = (_K1 * data_range) ** 2
    c2 = (_K2 * data_range) ** 2
    ncov = k * k / (k * k - 1.0)
    total = 0.0
    count = 0
    for ch in range(a.shape[2]):
        for r0 in range(0, h - k + 1, STRIP_ROWS):
            r1 = min(h, r0 + STRIP_ROWS + k - 1)
            x = a[r0:r1, :, ch].astype(np.float64)
            y = b[r0:r1, :, ch].astype(np.float64)
            ux, uy = _box_mean(x, k), _box_mean(y, k)
            uxx, uyy, uxy = _box_mean(x * x, k), _box_mean(y * y, k), _box_mean(x * y, k)
            vx = ncov * (uxx - ux * ux)
            vy = ncov * (uyy - uy * uy)
            vxy = ncov * (uxy - ux * uy)
            s = ((2 * ux * uy + c1) * (2 * vxy + c2)) / ((ux * ux + uy * uy + c1) * (vx + vy + c2))
            total += float(s.sum())
            count += s.size
    return total / count if count else None


def histogram_difference(img_a: Image.Image, img_b: Image.Image) -> float:
    """Mean per-channel total-variation distance of normalised 256-bin histograms (0 = identical)."""
    def hists(img: Image.Image) -> list[np.ndarray]:
        c = canonical_image(img)
        if c.mode not in ("L", "LA", "RGB", "RGBA", "CMYK"):
            c = c.convert("RGB")
        raw = np.asarray(c.histogram(), dtype=np.float64).reshape(-1, 256)
        return [h / max(h.sum(), 1.0) for h in raw]

    ha, hb = hists(img_a), hists(img_b)
    n = min(len(ha), len(hb))
    if n == 0:
        return 0.0
    return float(np.mean([0.5 * np.abs(ha[i] - hb[i]).sum() for i in range(n)]))


def dhash(img: Image.Image) -> int:
    g = canonical_image(img).convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    px = np.asarray(g, dtype=np.int16)
    bits = (px[:, 1:] > px[:, :-1]).flatten()
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


def compare_images(img_a: Image.Image, img_b: Image.Image, region: tuple[int, int, int, int] | None = None) -> PixelIntegrityResult:
    """Compare original ``img_a`` against output ``img_b``.

    If ``region`` is given (crop box on ``img_a``), an additional region-aligned
    comparison is recorded, but the full-frame verdict stays authoritative.
    """
    t0 = time.perf_counter()
    ca, cb = canonical_image(img_a), canonical_image(img_b)
    res = PixelIntegrityResult(
        verdict=VERDICT_NOT_COMPARABLE,
        comparable=False,
        basis="full-frame, canonical decode (frame 0, orientation not applied)",
        resolution_a=ca.size,
        resolution_b=cb.size,
        pixel_count_a=ca.size[0] * ca.size[1],
        pixel_count_b=cb.size[0] * cb.size[1],
        channels_a=len(ca.getbands()),
        channels_b=len(cb.getbands()),
        mode_a=img_a.mode,
        mode_b=img_b.mode,
    )
    arr_a_native, arr_b_native = to_array(ca), to_array(cb)
    res.pixel_sha256_a = pixel_hash(arr_a_native)
    res.pixel_sha256_b = pixel_hash(arr_b_native)
    del arr_a_native, arr_b_native
    res.histogram_difference = histogram_difference(ca, cb)
    try:
        ha, hb = dhash(ca), dhash(cb)
        res.perceptual_hash_distance = bin(ha ^ hb).count("1")
        res.perceptual_difference = res.perceptual_hash_distance / 64.0
    except Exception as exc:  # noqa: BLE001
        res.notes.append(f"Perceptual hash unavailable: {exc}")

    if ca.size == cb.size:
        a, b, mode, notes = _align(ca, cb)
        res.notes.extend(notes)
        res.compared_mode = mode
        _fill_metrics(res, a, b)
        res.comparable = True
        identical = (
            res.changed_pixels == 0
            and res.max_abs_error == 0
            and ca.mode == cb.mode
            and a.shape == b.shape
            and res.pixel_sha256_a == res.pixel_sha256_b
        )
        res.verdict = VERDICT_EXACT if identical else VERDICT_CHANGED
        if res.changed_pixels == 0 and not identical:
            res.notes.append("Sample values match after alignment, but the pixel representation (mode/channels) changed.")
    else:
        res.verdict = VERDICT_CHANGED
        res.notes.append(
            f"Resolution changed ({ca.size[0]}x{ca.size[1]} -> {cb.size[0]}x{cb.size[1]}); per-pixel metrics are not defined."
        )
        if region is not None:
            l, t, r, bt = region
            if (r - l, bt - t) == cb.size:
                a, b, mode, notes = _align(ca.crop(region), cb)
                res.region = tuple(region)
                res.compared_mode = mode
                res.notes.extend(notes)
                _fill_metrics(res, a, b)
                res.comparable = True
                res.basis = f"region-aligned against crop box {tuple(region)} of the original"
                res.region_exact = bool(res.changed_pixels == 0 and res.max_abs_error == 0)
    res.duration_ms = (time.perf_counter() - t0) * 1000.0
    return res


def _fill_metrics(res: PixelIntegrityResult, a: np.ndarray, b: np.ndarray) -> None:
    st = _diff_stats(a, b)
    n = max(st["samples"], 1)
    res.mae = st["sum_abs"] / n
    res.mse = st["sum_sq"] / n
    res.max_abs_error = st["max_abs"]
    res.changed_pixels = st["changed"]
    pixels = a.shape[0] * a.shape[1]
    res.changed_pixel_pct = 100.0 * st["changed"] / max(pixels, 1)
    rng = data_range_for(a)
    if res.mse == 0:
        res.psnr_db = None
        res.psnr_infinite = True
    else:
        res.psnr_db = 10.0 * np.log10((rng * rng) / res.mse)
    try:
        res.ssim = ssim(a, b, rng)
        if res.ssim is None:
            res.notes.append("SSIM undefined: image smaller than the 7x7 window.")
    except MemoryError:
        res.ssim = None
        res.notes.append("SSIM skipped: insufficient memory.")


def difference_map(img_a: Image.Image, img_b: Image.Image) -> np.ndarray | None:
    """Per-pixel maximum absolute channel difference (uint8-scaled), or None if sizes differ."""
    ca, cb = canonical_image(img_a), canonical_image(img_b)
    if ca.size != cb.size:
        return None
    a, b, _mode, _ = _align(ca, cb)
    d = np.abs(a.astype(np.int32) - b.astype(np.int32)).max(axis=2)
    rng = data_range_for(a)
    if rng != 255.0:
        d = (d.astype(np.float64) * 255.0 / rng).astype(np.int32)
    return np.clip(d, 0, 255).astype(np.uint8)
