"""Robustness Lab: apply fixed, standard transformations at graded severities and
measure how a signal persists, together with the fidelity cost of each transformation.

This is a characterisation protocol in the spirit of the WAVES benchmark (An et al.,
ICML 2024): a predetermined battery of common image operations is applied and the
outcome is *measured*. It is NOT a search for a transformation that defeats a
detector, and it operates on whatever image it is given; for a controlled surrogate
case it additionally reports signal persistence against the known ground truth.

Transformations (each with a severity sweep): PNG re-encode, JPEG, WebP, resize
(down+up round trip), centre crop, rotation, brightness, contrast, gamma, Gaussian
blur, unsharp sharpen, additive Gaussian noise, and colour (saturation) change.
"""
from __future__ import annotations

import io
import time
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from app.research import metrics as M
from app.research import surrogate as S
from app.research.imaging import (EPS, from_float, gaussian_blur, luminance, resize, rgb_to_ycbcr, scale_by, to_rgb3,
                                   to_uint8, ycbcr_to_rgb)

# name -> (list of severities, human label)
BATTERY = {
    "png_reencode": ([1], "PNG re-encode (lossless container)"),
    "jpeg": ([95, 90, 80, 70, 50, 30], "JPEG quality"),
    "webp": ([95, 90, 80, 70, 50], "WebP quality"),
    "resize": ([0.9, 0.75, 0.5, 0.25], "Resize factor (down then back)"),
    "crop": ([0.95, 0.9, 0.8, 0.7], "Centre crop keep-fraction"),
    "rotate": ([1, 2, 5, 10], "Rotation degrees"),
    "brightness": ([0.9, 0.95, 1.05, 1.1], "Brightness factor"),
    "contrast": ([0.9, 0.95, 1.05, 1.1], "Contrast factor"),
    "gamma": ([0.8, 0.9, 1.1, 1.25], "Gamma"),
    "blur": ([0.5, 1.0, 1.5, 2.0], "Gaussian blur sigma"),
    "sharpen": ([0.5, 1.0, 2.0], "Unsharp amount"),
    "noise": ([1, 2, 4, 8], "Additive noise sigma (8-bit)"),
    "color": ([0.8, 0.9, 1.1, 1.2], "Saturation factor"),
}


def _roundtrip(img: np.ndarray, fmt: str, **kw) -> np.ndarray:
    pil = Image.fromarray(to_uint8(to_rgb3(img)) if img.shape[2] == 3 else to_uint8(img)[:, :, 0])
    b = io.BytesIO()
    pil.save(b, fmt, **kw)
    b.seek(0)
    out = np.asarray(Image.open(b).convert("RGB" if img.shape[2] == 3 else "L"), dtype=np.float32) / 255.0
    return out if img.shape[2] == 3 else out[:, :, None]


def apply(img: np.ndarray, kind: str, severity) -> np.ndarray:
    """Return a transformed copy (float 0..1). ``img`` is never modified."""
    x = img.astype(np.float32)
    if kind == "png_reencode":
        return _roundtrip(x, "PNG", compress_level=6)
    if kind == "jpeg":
        return _roundtrip(x, "JPEG", quality=int(severity))
    if kind == "webp":
        return _roundtrip(x, "WEBP", quality=int(severity))
    if kind == "resize":
        h, w = x.shape[:2]
        return resize(scale_by(x, float(severity)), (w, h))
    if kind == "crop":
        h, w = x.shape[:2]
        f = float(severity)
        ch, cw = int(h * f), int(w * f)
        y0, x0 = (h - ch) // 2, (w - cw) // 2
        return resize(x[y0:y0 + ch, x0:x0 + cw], (w, h))
    if kind == "rotate":
        pil = from_float(to_rgb3(x)).rotate(float(severity), resample=Image.Resampling.BILINEAR)
        return np.asarray(pil, dtype=np.float32)[:, :, : x.shape[2]] / 255.0
    if kind == "brightness":
        return np.clip(x * float(severity), 0, 1)
    if kind == "contrast":
        return np.clip((x - 0.5) * float(severity) + 0.5, 0, 1)
    if kind == "gamma":
        return np.clip(x, 0, 1) ** float(severity)
    if kind == "blur":
        return np.stack([gaussian_blur(x[:, :, c], float(severity)) for c in range(x.shape[2])], axis=2)
    if kind == "sharpen":
        a = float(severity)
        return np.clip(x + a * (x - np.stack([gaussian_blur(x[:, :, c], 1.0) for c in range(x.shape[2])], axis=2)), 0, 1)
    if kind == "noise":
        rng = np.random.default_rng(0)
        return np.clip(x + rng.standard_normal(x.shape).astype(np.float32) * (float(severity) / 255.0), 0, 1)
    if kind == "color":
        if x.shape[2] == 1:
            return x
        ycc = rgb_to_ycbcr(x)
        ycc[:, :, 1] = np.clip(0.5 + (ycc[:, :, 1] - 0.5) * float(severity), 0, 1)
        ycc[:, :, 2] = np.clip(0.5 + (ycc[:, :, 2] - 0.5) * float(severity), 0, 1)
        return np.clip(ycbcr_to_rgb(ycc), 0, 1)
    raise ValueError(f"Unknown transformation {kind!r}")


@dataclass
class RobustnessRow:
    kind: str
    label: str
    severity: float
    psnr_db: float
    ssim: float
    persistence: float | None   # surrogate: z_after / z_before (clamped to >= 0)
    score_after: float | None
    detected: bool | None

    def to_dict(self) -> dict:
        return {"kind": self.kind, "label": self.label, "severity": self.severity, "psnr_db": self.psnr_db,
                "ssim": self.ssim, "persistence": self.persistence, "score_after": self.score_after,
                "detected": self.detected}


def sweep(img: np.ndarray, cfg: S.SurrogateConfig | None = None, kinds: tuple = (), progress=None) -> dict:
    """Run the battery. With a surrogate ``cfg``, ``img`` must be the watermarked image and persistence is measured."""
    kinds = kinds or tuple(BATTERY)
    z0 = S.detect(img, cfg).score if cfg is not None else None
    rows: list[RobustnessRow] = []
    t0 = time.perf_counter()
    total = sum(len(BATTERY[k][0]) for k in kinds if k in BATTERY)
    done = 0
    for k in kinds:
        if k not in BATTERY:
            continue
        sevs, label = BATTERY[k]
        for sev in sevs:
            t = apply(img, k, sev)
            fid = M.fidelity(img, t) if t.shape == img.shape else {"comparable": False}
            persistence = score = det = None
            if cfg is not None:
                d = S.detect(t, cfg)
                score, det = d.score, d.detected
                persistence = max(0.0, d.score / z0) if z0 and z0 > EPS else None
            rows.append(RobustnessRow(k, label, float(sev),
                                      99.0 if fid.get("psnr_infinite") else float(fid.get("psnr_db") or 0.0),
                                      float(fid.get("ssim") or 0.0), persistence, score, det))
            done += 1
            if progress:
                progress(int(90 * done / max(total, 1)), f"{label} = {sev}")
    by_kind = {}
    for k in kinds:
        krows = [r for r in rows if r.kind == k]
        if krows and cfg is not None:
            surviving = [r.severity for r in krows if r.detected]
            by_kind[k] = {"severities_tested": len(krows), "still_detected": sum(1 for r in krows if r.detected),
                          "weakest_severity_detected": surviving[-1] if surviving else None,
                          "min_persistence": min((r.persistence for r in krows if r.persistence is not None), default=None)}
    return {"baseline_score": z0, "rows": [r.to_dict() for r in rows], "by_kind": by_kind,
            "runtime_s": time.perf_counter() - t0,
            "note": "Standard transformations applied at fixed severities; persistence = detector z after / z before. "
                    "This characterises robustness; it is not a detector-evasion search."}
