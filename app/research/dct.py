"""Block DCT, JPEG forensics and Benford first-digit statistics.

For JPEG inputs the quantisation tables are read from the decoder (Pillow returns
them in natural row-major order) and the quality is estimated by matching the IJG
scaling of the standard tables. Coefficients are *analytical*: they are recomputed
from decoded pixels (8x8 orthonormal DCT-II on level-shifted samples), not read
from the entropy-coded bitstream; for JPEG they are additionally divided by the
quantisation table and rounded to estimate the quantised integers.

Benford analysis follows the idea in Bonettini et al. (2021): first-digit statistics
of quantised DCT AC coefficients, here reported as divergence from Benford's law
and as a generalised-Benford fit, optionally after re-quantisation at several JPEG
qualities (a "Benford feature vector"). Descriptive only.
"""
from __future__ import annotations

import math

import numpy as np

from app.research.imaging import EPS

N = 8
STD_LUMA = np.array([
    16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56,
    14, 17, 22, 29, 51, 87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101, 72, 92, 95, 98, 112, 100, 103, 99], dtype=np.float64).reshape(8, 8)
STD_CHROMA = np.array([
    17, 18, 24, 47, 99, 99, 99, 99, 18, 21, 26, 66, 99, 99, 99, 99, 24, 26, 56, 99, 99, 99, 99, 99,
    47, 66, 99, 99, 99, 99, 99, 99] + [99] * 32, dtype=np.float64).reshape(8, 8)
BENFORD = np.log10(1.0 + 1.0 / np.arange(1, 10))
ZIGZAG = sorted(((u, v) for u in range(8) for v in range(8)), key=lambda p: (p[0] + p[1], p[1] if (p[0] + p[1]) % 2 else p[0]))


def dct_matrix(n: int = N) -> np.ndarray:
    k = np.arange(n)
    m = np.cos(np.pi * (2 * k[None, :] + 1) * k[:, None] / (2 * n)) * math.sqrt(2.0 / n)
    m[0] /= math.sqrt(2.0)
    return m


_C = dct_matrix()


def block_dct(x: np.ndarray, offset: tuple[int, int] = (0, 0)) -> np.ndarray:
    """8x8 orthonormal DCT-II of every complete block. Returns (by, bx, 8, 8)."""
    oy, ox = offset
    x = x[oy:, ox:]
    h, w = (x.shape[0] // N) * N, (x.shape[1] // N) * N
    b = x[:h, :w].astype(np.float64).reshape(h // N, N, w // N, N).transpose(0, 2, 1, 3)
    return np.einsum("ij,abjk,lk->abil", _C, b, _C)


def block_idct(c: np.ndarray) -> np.ndarray:
    b = np.einsum("ji,abjk,kl->abil", _C, c, _C)
    by, bx = b.shape[:2]
    return b.transpose(0, 2, 1, 3).reshape(by * N, bx * N)


def scaled_table(base: np.ndarray, quality: int) -> np.ndarray:
    q = max(1, min(100, int(quality)))
    s = 5000 / q if q < 50 else 200 - 2 * q
    return np.clip(np.floor((base * s + 50) / 100), 1, 255)


def estimate_quality(table: np.ndarray, chroma: bool = False) -> dict:
    base = STD_CHROMA if chroma else STD_LUMA
    best = min(range(1, 101), key=lambda q: float(np.abs(scaled_table(base, q) - table).sum()))
    err = float(np.abs(scaled_table(base, best) - table).mean())
    return {"quality": best, "mean_abs_error": err, "standard_ijg_tables": err < 0.5}


def jpeg_tables(img) -> dict:
    q = getattr(img, "quantization", None) or {}
    out = {}
    for k, v in q.items():
        t = np.asarray(list(v), dtype=np.float64)
        if t.size == 64:
            out[int(k)] = t.reshape(8, 8)
    return out


def blockiness(x: np.ndarray) -> dict:
    """Mean absolute horizontal/vertical gradient on 8-pixel block boundaries vs inside blocks, for each grid offset."""
    if min(x.shape) < 16:
        return {"status": "INSUFFICIENT DATA"}
    dh = np.abs(np.diff(x.astype(np.float64), axis=1)).mean(axis=0)
    dv = np.abs(np.diff(x.astype(np.float64), axis=0)).mean(axis=1)
    ph = np.array([dh[o::8].mean() for o in range(8)])
    pv = np.array([dv[o::8].mean() for o in range(8)])
    oh, ov = int(ph.argmax()), int(pv.argmax())
    ratio_h = float(ph.max() / max(np.median(ph), EPS))
    ratio_v = float(pv.max() / max(np.median(pv), EPS))
    return {"status": "COMPLETE", "grid_offset": [(ov + 1) % 8, (oh + 1) % 8], "boundary_ratio_h": ratio_h,
            "boundary_ratio_v": ratio_v, "blockiness": 0.5 * (ratio_h + ratio_v),
            "note": "Ratio of mean gradient at the strongest 8-periodic column/row to the median over the 8 phases; "
                    "~1.0 means no visible 8x8 grid."}


def first_digits(c: np.ndarray) -> np.ndarray:
    a = np.abs(c[np.isfinite(c)])
    a = a[a >= 1.0]
    if a.size == 0:
        return np.zeros(9)
    d = np.floor(a / 10.0 ** np.floor(np.log10(a))).astype(int)
    d = np.clip(d, 1, 9)
    return np.bincount(d, minlength=10)[1:].astype(np.float64)


def benford_divergence(counts: np.ndarray) -> dict:
    n = float(counts.sum())
    if n < 50:
        return {"status": "INSUFFICIENT DATA", "n": int(n)}
    p = counts / n
    m = 0.5 * (p + BENFORD)

    def kl(a, b):
        s = a > 0
        return float((a[s] * np.log2(a[s] / b[s])).sum())

    chi2 = float(n * (((p - BENFORD) ** 2) / BENFORD).sum())
    # generalised Benford p(d) = N log10(1 + 1/(s + d^q)); coarse grid fit
    best = (1e9, 1.0, 0.0)
    d = np.arange(1, 10, dtype=np.float64)
    for q in np.linspace(0.5, 2.5, 41):
        for s in np.linspace(-0.9, 1.0, 39):
            g = np.log10(1 + 1 / np.maximum(s + d ** q, 1e-9))
            g = g / g.sum()
            e = float(((p - g) ** 2).sum())
            if e < best[0]:
                best = (e, float(q), float(s))
    return {"status": "COMPLETE", "n": int(n), "distribution": p.tolist(), "benford": BENFORD.tolist(),
            "chi2": chi2, "js_divergence": 0.5 * kl(p, m) + 0.5 * kl(BENFORD, m),
            "mad": float(np.abs(p - BENFORD).mean()),
            "generalised_fit": {"q": best[1], "s": best[2], "sse": best[0]}}


def analyse(lum255: np.ndarray, img=None, requant_qualities=(100, 90, 80, 70, 60)) -> dict:
    """DCT / JPEG forensics on a luminance plane in 0..255 scale. ``img`` (PIL) gives JPEG tables when present."""
    x = lum255.astype(np.float64) - 128.0
    if min(x.shape) < 8:
        return {"status": "INSUFFICIENT DATA"}
    c = block_dct(x)
    tables = jpeg_tables(img) if img is not None else {}
    is_jpeg = bool(tables) and getattr(img, "format", "") == "JPEG"
    q_est = estimate_quality(tables[0]) if 0 in tables else None
    if is_jpeg and 0 in tables:
        qc = np.rint(c / tables[0][None, None])
        coeff_basis = "estimated quantised coefficients (analytical DCT of decoded pixels / luma table, rounded)"
    else:
        qc = np.rint(c)
        coeff_basis = "analytical DCT of decoded pixels, rounded (no JPEG quantisation available)"
    dc = c[:, :, 0, 0]
    ac_std = np.array([[float(c[:, :, u, v].std()) for v in range(8)] for u in range(8)])
    hist_pos = {}
    for (u, v) in ((0, 1), (1, 0), (1, 1), (2, 2)):
        vals = qc[:, :, u, v].ravel()
        lim = int(min(50, max(5, np.percentile(np.abs(vals), 99))))
        hv, _ = np.histogram(vals, bins=2 * lim + 1, range=(-lim - 0.5, lim + 0.5))
        hist_pos[f"({u},{v})"] = {"range": lim, "counts": hv.tolist()}
    ac = qc.copy()
    ac[:, :, 0, 0] = 0
    benford = benford_divergence(first_digits(ac))
    vector = []
    for q in requant_qualities:
        t = scaled_table(STD_LUMA, q)
        rq = np.rint(c / t[None, None])
        rq[:, :, 0, 0] = 0
        bd = benford_divergence(first_digits(rq))
        vector.append({"quality": q, "js_divergence": bd.get("js_divergence"), "n": bd.get("n")})
    zz = [float(ac_std[u, v]) for (u, v) in ZIGZAG[1:16]]
    return {"status": "COMPLETE", "jpeg": is_jpeg,
            "quantization_tables": {str(k): v.astype(int).tolist() for k, v in tables.items()},
            "quality_estimate": q_est, "coefficient_basis": coeff_basis,
            "blocks": list(c.shape[:2]), "dc": {"mean": float(dc.mean()), "std": float(dc.std())},
            "ac_std_8x8": ac_std.tolist(), "ac_std_zigzag_1_15": zz, "histograms": hist_pos,
            "zero_fraction_ac": float((ac == 0).mean()), "benford": benford, "benford_feature_vector": vector,
            "blockiness": blockiness(lum255), "maps": {"dct_log_ac_energy": np.log1p((c[:, :, 1:, 1:] ** 2).sum(axis=(2, 3))
                                                                                       ).astype(np.float32)}}


def dct_residual(x: np.ndarray, keep_low: int = 2) -> np.ndarray:
    """Block-DCT high-pass: zero coefficients with u + v < keep_low, inverse transform. Output cropped to blocks."""
    c = block_dct(x.astype(np.float64))
    for u in range(8):
        for v in range(8):
            if u + v < keep_low:
                c[:, :, u, v] = 0
    r = block_idct(c)
    out = np.zeros(x.shape, dtype=np.float32)
    out[: r.shape[0], : r.shape[1]] = r
    return out
