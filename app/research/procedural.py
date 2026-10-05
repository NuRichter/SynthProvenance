"""Deterministic procedural test images (clearly labelled SYNTHETIC TEST CONTENT).

Natural photographs have an approximately 1/f amplitude spectrum. These generators
produce 1/f^beta colour noise mixed with smooth gradients, discs and edges, so that
residual, spectral and surrogate-watermark experiments can run without any external
data. They are never presented as real or AI-generated photographs.
"""
from __future__ import annotations

import numpy as np

from app.research.imaging import EPS


def pink_noise(h: int, w: int, beta: float = 2.0, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    f = np.hypot(fy, fx)
    f[0, 0] = 1.0
    amp = 1.0 / f ** (beta / 2.0)
    amp[0, 0] = 0.0
    spec = amp * np.exp(1j * rng.uniform(0, 2 * np.pi, (h, w)))
    x = np.fft.ifft2(spec).real
    x = (x - x.min()) / (x.max() - x.min() + EPS)
    return x.astype(np.float32)


def scene(h: int = 384, w: int = 512, seed: int = 0, beta: float = 2.0) -> np.ndarray:
    """RGB float image in [0,1]: 1/f texture + gradient + random discs and bars."""
    rng = np.random.default_rng(seed + 7919)
    base = np.stack([pink_noise(h, w, beta, seed * 3 + c) for c in range(3)], axis=2)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    grad = (0.6 * xx / max(w - 1, 1) + 0.4 * yy / max(h - 1, 1))[:, :, None]
    tint = rng.uniform(0.2, 0.9, 3)[None, None, :]
    img = 0.45 * base + 0.35 * grad * tint + 0.1
    for _ in range(int(rng.integers(3, 8))):
        cy, cx = rng.uniform(0, h), rng.uniform(0, w)
        r = rng.uniform(0.05, 0.2) * min(h, w)
        m = ((yy - cy) ** 2 + (xx - cx) ** 2) < r * r
        img[m] = 0.6 * img[m] + 0.4 * rng.uniform(0, 1, 3)
    for _ in range(int(rng.integers(1, 4))):
        x0 = int(rng.uniform(0, w * 0.8))
        bw = int(rng.uniform(4, w * 0.1))
        img[:, x0:x0 + bw] = 0.7 * img[:, x0:x0 + bw] + 0.3 * rng.uniform(0, 1, 3)
    return np.clip(np.rint(np.clip(img, 0, 1) * 255) / 255, 0, 1).astype(np.float32)


def dataset(n: int, h: int = 256, w: int = 256, seed: int = 0) -> list[np.ndarray]:
    return [scene(h, w, seed=seed + i) for i in range(n)]
