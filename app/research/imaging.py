"""Array utilities for the research engine: normalisation, colour spaces, filters,
resampling and overlap-aware tiling.

All functions are pure: they never modify their input and never touch files. The
source image is never resampled in place; analysis copies are derived explicitly and
their resolution is recorded separately (SOURCE / ANALYSIS / DISPLAY).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image

from app.core.image_loader import to_array

EPS = 1e-12


# ------------------------------------------------------------------ normalisation
def as_float(src) -> np.ndarray:
    """PIL image or array -> float32 HxWxC in [0, 1]. Alpha is dropped; grey stays 1 channel."""
    arr = to_array(src) if isinstance(src, Image.Image) else np.asarray(src)
    if arr.ndim == 2:
        arr = arr[:, :, None]
    if arr.shape[2] in (2, 4):  # LA / RGBA -> drop alpha
        arr = arr[:, :, :-1]
    if arr.dtype == np.uint8:
        out = arr.astype(np.float32) / 255.0
    elif arr.dtype == np.uint16:
        out = arr.astype(np.float32) / 65535.0
    elif np.issubdtype(arr.dtype, np.integer):
        a = arr.astype(np.float64)
        lo, hi = float(a.min()), float(a.max())
        out = ((a - lo) / max(hi - lo, 1.0)).astype(np.float32)
    else:
        out = np.clip(arr.astype(np.float32), 0.0, 1.0) if float(np.nanmax(arr)) <= 1.0 else \
            (arr / max(float(np.nanmax(arr)), EPS)).astype(np.float32)
    if out.shape[2] == 3 or out.shape[2] == 1:
        return np.ascontiguousarray(out)
    return np.ascontiguousarray(out[:, :, :3])  # CMYK -> first three planes (documented approximation)


def to_rgb3(x: np.ndarray) -> np.ndarray:
    return np.repeat(x, 3, axis=2) if x.shape[2] == 1 else x[:, :, :3]


def to_uint8(x: np.ndarray) -> np.ndarray:
    return np.clip(np.rint(np.asarray(x) * 255.0), 0, 255).astype(np.uint8)


def from_float(x: np.ndarray) -> Image.Image:
    a = to_uint8(x)
    return Image.fromarray(a[:, :, 0] if a.ndim == 3 and a.shape[2] == 1 else a)


# ------------------------------------------------------------------ colour spaces
def luminance(x: np.ndarray) -> np.ndarray:
    """ITU-R BT.601 luma of a float image (HxWxC) -> HxW."""
    if x.ndim == 2:
        return x.astype(np.float32)
    if x.shape[2] == 1:
        return x[:, :, 0].astype(np.float32)
    return (0.299 * x[:, :, 0] + 0.587 * x[:, :, 1] + 0.114 * x[:, :, 2]).astype(np.float32)


def rgb_to_ycbcr(x: np.ndarray) -> np.ndarray:
    """Full-range BT.601 (JPEG) YCbCr, all planes in [0, 1] (chroma centred at 0.5)."""
    r, g, b = x[:, :, 0], x[:, :, 1], x[:, :, 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    cb = 0.5 - 0.168736 * r - 0.331264 * g + 0.5 * b
    cr = 0.5 + 0.5 * r - 0.418688 * g - 0.081312 * b
    return np.stack([y, cb, cr], axis=2).astype(np.float32)


def ycbcr_to_rgb(x: np.ndarray) -> np.ndarray:
    y, cb, cr = x[:, :, 0], x[:, :, 1] - 0.5, x[:, :, 2] - 0.5
    r = y + 1.402 * cr
    g = y - 0.344136 * cb - 0.714136 * cr
    b = y + 1.772 * cb
    return np.stack([r, g, b], axis=2).astype(np.float32)


def rgb_to_lab(x: np.ndarray) -> np.ndarray:
    """sRGB (D65) -> CIE L*a*b*. L* in [0, 100], a*/b* roughly [-128, 127]."""
    c = np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]], dtype=np.float32)
    xyz = c @ m.T
    xyz = xyz / np.array([0.95047, 1.0, 1.08883], dtype=np.float32)
    d = 6.0 / 29.0
    f = np.where(xyz > d ** 3, np.cbrt(np.maximum(xyz, 0)), xyz / (3 * d * d) + 4.0 / 29.0)
    lab = np.stack([116 * f[:, :, 1] - 16, 500 * (f[:, :, 0] - f[:, :, 1]), 200 * (f[:, :, 1] - f[:, :, 2])], axis=2)
    return lab.astype(np.float32)


COLOR_BRANCHES = ("RGB", "YCbCr", "Lab", "LumaChroma")


def color_branches(x: np.ndarray, spaces: tuple = COLOR_BRANCHES) -> dict[str, np.ndarray]:
    """Analysis planes per colour space (copies; the input is untouched). Grey input yields luminance only."""
    out: dict[str, np.ndarray] = {}
    if x.shape[2] == 1:
        out["Y (grey)"] = x[:, :, 0].astype(np.float32)
        return out
    rgb = x[:, :, :3]
    if "RGB" in spaces:
        for i, n in enumerate("RGB"):
            out[f"RGB:{n}"] = rgb[:, :, i].astype(np.float32)
    if "YCbCr" in spaces or "LumaChroma" in spaces:
        ycc = rgb_to_ycbcr(rgb)
        if "YCbCr" in spaces:
            for i, n in enumerate(("Y", "Cb", "Cr")):
                out[f"YCbCr:{n}"] = ycc[:, :, i]
        if "LumaChroma" in spaces:
            out["Luma"] = ycc[:, :, 0]
            out["Chroma"] = np.hypot(ycc[:, :, 1] - 0.5, ycc[:, :, 2] - 0.5).astype(np.float32)
    if "Lab" in spaces:
        lab = rgb_to_lab(rgb)
        out["Lab:L*"] = lab[:, :, 0] / 100.0
        out["Lab:a*"] = (lab[:, :, 1] + 128.0) / 255.0
        out["Lab:b*"] = (lab[:, :, 2] + 128.0) / 255.0
    return out


# ------------------------------------------------------------------ filters
def _pad(x: np.ndarray, p: int, mode: str = "reflect") -> np.ndarray:
    if p <= 0:
        return x
    if mode == "reflect" and (x.shape[0] <= p or x.shape[1] <= p):
        mode = "edge"
    return np.pad(x, ((p, p), (p, p)) + ((0, 0),) * (x.ndim - 2), mode=mode)


def conv1d_axis(x: np.ndarray, k: np.ndarray, axis: int) -> np.ndarray:
    """'same' correlation of a 2D array with a short 1D kernel along one axis (reflect padding)."""
    k = np.asarray(k, dtype=np.float32)
    r = len(k) // 2
    pad = [(0, 0)] * x.ndim
    pad[axis] = (r, len(k) - 1 - r)
    mode = "reflect" if x.shape[axis] > len(k) else "edge"
    xp = np.pad(x.astype(np.float32, copy=False), pad, mode=mode)
    out = np.zeros_like(x, dtype=np.float32)
    n = x.shape[axis]
    for j, w in enumerate(k):
        if w == 0:
            continue
        sl = [slice(None)] * x.ndim
        sl[axis] = slice(j, j + n)
        out += w * xp[tuple(sl)]
    return out


def gaussian_kernel(sigma: float) -> np.ndarray:
    r = max(1, int(math.ceil(3.0 * sigma)))
    t = np.arange(-r, r + 1, dtype=np.float32)
    k = np.exp(-0.5 * (t / max(sigma, 1e-6)) ** 2)
    return k / k.sum()


def gaussian_blur(x: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return x.astype(np.float32, copy=True)
    k = gaussian_kernel(sigma)
    if x.ndim == 3:
        return np.stack([gaussian_blur(x[:, :, c], sigma) for c in range(x.shape[2])], axis=2)
    return conv1d_axis(conv1d_axis(x, k, 0), k, 1)


def conv2d(x: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """'same' 2D correlation with a small kernel (reflect padding)."""
    kernel = np.asarray(kernel, dtype=np.float32)
    kh, kw = kernel.shape
    ph, pw = kh // 2, kw // 2
    mode = "reflect" if min(x.shape[:2]) > max(kh, kw) else "edge"
    xp = np.pad(x.astype(np.float32, copy=False), ((ph, kh - 1 - ph), (pw, kw - 1 - pw)), mode=mode)
    out = np.zeros(x.shape[:2], dtype=np.float32)
    h, w = x.shape[:2]
    for i in range(kh):
        for j in range(kw):
            v = kernel[i, j]
            if v != 0:
                out += v * xp[i:i + h, j:j + w]
    return out


def box_mean(x: np.ndarray, r: int) -> np.ndarray:
    """(2r+1)^2 mean filter with edge padding, via integral image."""
    if r <= 0:
        return x.astype(np.float32, copy=True)
    xp = np.pad(x.astype(np.float64), r + 1, mode="edge")
    c = xp.cumsum(0).cumsum(1)
    k = 2 * r + 1
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    h, w = x.shape
    return (s[:h, :w] / (k * k)).astype(np.float32)


def median3(x: np.ndarray) -> np.ndarray:
    xp = _pad(x.astype(np.float32, copy=False), 1, "edge")
    h, w = x.shape
    stack = np.stack([xp[i:i + h, j:j + w] for i in range(3) for j in range(3)], axis=0)
    return np.median(stack, axis=0).astype(np.float32)


LAPLACIAN = np.array([[0, 1, 0], [1, -4, 1], [0, 1, 0]], dtype=np.float32)
SRM_KV = np.array([[-1, 2, -2, 2, -1], [2, -6, 8, -6, 2], [-2, 8, -12, 8, -2], [2, -6, 8, -6, 2],
                   [-1, 2, -2, 2, -1]], dtype=np.float32) / 12.0  # SRM "KV" kernel (Fridrich & Kodovsky 2012)


# ------------------------------------------------------------------ resampling
def resize_plane(x: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Resize a float plane to (width, height) with Pillow (mode F). Area for shrinking, bilinear for growing."""
    w, h = int(size[0]), int(size[1])
    if (x.shape[1], x.shape[0]) == (w, h):
        return x.astype(np.float32, copy=True)
    img = Image.fromarray(np.ascontiguousarray(x.astype(np.float32)), mode="F")
    shrink = w < x.shape[1] or h < x.shape[0]
    res = Image.Resampling.BOX if shrink else Image.Resampling.BILINEAR
    return np.asarray(img.resize((max(1, w), max(1, h)), res), dtype=np.float32)


def resize(x: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    if x.ndim == 2:
        return resize_plane(x, size)
    return np.stack([resize_plane(x[:, :, c], size) for c in range(x.shape[2])], axis=2)


def scale_by(x: np.ndarray, factor: float) -> np.ndarray:
    h, w = x.shape[:2]
    return resize(x, (max(1, int(round(w * factor))), max(1, int(round(h * factor)))))


@dataclass
class Resolution:
    source: tuple[int, int]
    analysis: tuple[int, int]
    factor: float
    display: tuple[int, int] | None = None

    def text(self) -> str:
        s = f"SOURCE {self.source[0]}x{self.source[1]} | ANALYSIS {self.analysis[0]}x{self.analysis[1]}"
        if self.factor != 1.0:
            s += f" (x{self.factor:.4g}, analysis copy only)"
        if self.display:
            s += f" | DISPLAY {self.display[0]}x{self.display[1]}"
        return s

    def to_dict(self) -> dict:
        return {"source": list(self.source), "analysis": list(self.analysis), "factor": self.factor,
                "display": list(self.display) if self.display else None, "text": self.text()}


def analysis_copy(x: np.ndarray, max_pixels: int = 0) -> tuple[np.ndarray, Resolution]:
    """Return an analysis copy (downscaled only if ``max_pixels`` > 0 and exceeded) plus its resolution record."""
    h, w = x.shape[:2]
    if max_pixels and h * w > max_pixels:
        f = math.sqrt(max_pixels / float(h * w))
        y = scale_by(x, f)
        return y, Resolution((w, h), (y.shape[1], y.shape[0]), y.shape[1] / w)
    return x, Resolution((w, h), (w, h), 1.0)


# ------------------------------------------------------------------ tiling
def tile_grid(h: int, w: int, tile: int, overlap: int) -> list[tuple[int, int, int, int]]:
    """Tiles (y0, y1, x0, x1) that cover the image with the requested overlap; last tiles are flush with the edge."""
    tile = max(8, int(tile))
    overlap = max(0, min(int(overlap), tile // 2))
    step = tile - overlap

    def starts(n: int) -> list[int]:
        if n <= tile:
            return [0]
        s = list(range(0, n - tile + 1, step))
        if s[-1] + tile < n:
            s.append(n - tile)
        return s

    return [(y, min(h, y + tile), x, min(w, x + tile)) for y in starts(h) for x in starts(w)]


def _ramp(n: int, overlap: int) -> np.ndarray:
    r = np.ones(n, dtype=np.float32)
    if overlap > 0 and n > 2 * overlap:
        t = (np.arange(overlap, dtype=np.float32) + 0.5) / overlap
        r[:overlap] = t
        r[-overlap:] = t[::-1]
    return r


def tiled_apply(x: np.ndarray, fn, tile: int = 512, overlap: int = 32) -> np.ndarray:
    """Apply ``fn`` (plane -> plane of the same shape) per tile and blend overlaps with linear ramps."""
    h, w = x.shape[:2]
    if h <= tile and w <= tile:
        return fn(x).astype(np.float32)
    out = np.zeros((h, w), dtype=np.float64)
    acc = np.zeros((h, w), dtype=np.float64)
    for y0, y1, x0, x1 in tile_grid(h, w, tile, overlap):
        t = fn(x[y0:y1, x0:x1]).astype(np.float64)
        wgt = np.outer(_ramp(y1 - y0, overlap if h > tile else 0), _ramp(x1 - x0, overlap if w > tile else 0))
        out[y0:y1, x0:x1] += t * wgt
        acc[y0:y1, x0:x1] += wgt
    return (out / np.maximum(acc, EPS)).astype(np.float32)


def auto_tile(available_bytes: int | None, planes: int = 12, default: int = 1024) -> int:
    """Largest power-of-two tile whose float32 working set (``planes`` copies) fits in a quarter of free RAM."""
    if not available_bytes:
        return default
    budget = available_bytes / 4.0
    t = 4096
    while t > 256 and t * t * 4 * planes > budget:
        t //= 2
    return t


# ------------------------------------------------------------------ display helpers
_VIRIDIS = np.array([[68, 1, 84], [72, 40, 120], [62, 74, 137], [49, 104, 142], [38, 130, 142], [31, 158, 137],
                     [53, 183, 121], [109, 205, 89], [180, 222, 44], [253, 231, 37]], dtype=np.float32) / 255.0


def normalize(x: np.ndarray, lo: float = 1.0, hi: float = 99.0, symmetric: bool = False) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    finite = x[np.isfinite(x)]
    if finite.size == 0:
        return np.zeros_like(x)
    if symmetric:
        m = float(np.percentile(np.abs(finite), hi)) or 1.0
        return np.clip(0.5 + 0.5 * x / m, 0, 1)
    a, b = float(np.percentile(finite, lo)), float(np.percentile(finite, hi))
    if b - a < EPS:
        return np.zeros_like(x)
    return np.clip((x - a) / (b - a), 0, 1)


def colormap(x01: np.ndarray) -> np.ndarray:
    """Perceptually uniform (viridis-like) colour map of a [0,1] plane -> HxWx3 float."""
    t = np.clip(np.nan_to_num(x01), 0, 1) * (len(_VIRIDIS) - 1)
    i = np.floor(t).astype(int)
    i1 = np.minimum(i + 1, len(_VIRIDIS) - 1)
    f = (t - i)[..., None]
    return _VIRIDIS[i] * (1 - f) + _VIRIDIS[i1] * f


def map_image(x: np.ndarray, symmetric: bool = False, color: bool = True) -> Image.Image:
    n = normalize(x, symmetric=symmetric)
    return from_float(colormap(n) if color else n[:, :, None])


def display_limit(x: np.ndarray, max_side: int = 1600) -> np.ndarray:
    h, w = x.shape[:2]
    s = max(h, w)
    if s <= max_side:
        return x
    return scale_by(x, max_side / s)
