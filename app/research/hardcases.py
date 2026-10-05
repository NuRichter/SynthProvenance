"""Local 'hard case' benchmark generator with known ground truth (Section 22).

Produces a labelled benchmark of controlled images so cross-detector studies can be run
against a known origin. Everything is generated locally and reproducibly from a seed.

Honesty: this module CANNOT create a genuine camera photograph. The 'natural-like control'
is a procedurally generated image with camera-style noise and a mild optical blur, clearly
labelled as a CONTROL, not a real photo. Every record states its ground-truth level and the
exact transformation applied, so no case is ever presented as something it is not. The
generator makes a benchmark; it is not an attack tool and never targets an external service.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from app.research import procedural as PROC
from app.research import surrogate as SUR
from app.research.cross_detector import GROUND_TRUTH_LEVELS
from app.research.imaging import from_float, gaussian_blur, scale_by
from app.utils.paths import ensure_dir, safe_filename

# label -> (ground_truth_level, short description)
LABELS = {
    "SYNTHETIC": (5, "Procedural synthetic image (reproducible benchmark)"),
    "NATURAL-LIKE CONTROL": (3, "Procedural control with camera-style noise + optical blur (NOT a real photograph)"),
    "SYNTHETIC + SURROGATE WATERMARK": (4, "Synthetic image carrying a known keyed surrogate watermark"),
    "SYNTHETIC EDITED": (3, "Synthetic image with a local content edit"),
    "SYNTHETIC UPSCALED": (3, "Synthetic image downscaled then upscaled (resampling trace)"),
}


@dataclass
class HardCase:
    case_id: str
    label: str
    ground_truth_level: int
    ground_truth: str
    generator: str
    transform: str
    file: str = ""
    format: str = ""
    width: int = 0
    height: int = 0
    notes: str = ""
    surrogate: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        from app.utils.serialization import jsonable
        return jsonable(self)


def _camera_like(img: np.ndarray, seed: int) -> np.ndarray:
    """A synthetic control that imitates camera capture: mild optical blur + shot/read noise. Still not a real photo."""
    rng = np.random.default_rng(seed + 101)
    blurred = np.stack([gaussian_blur(img[:, :, c], 0.7) for c in range(img.shape[2])], axis=2)
    noise = rng.normal(0, 2.5 / 255.0, img.shape).astype(np.float32)
    shot = rng.normal(0, 1.0, img.shape).astype(np.float32) * np.sqrt(np.clip(blurred, 0, 1)) / 255.0 * 3.0
    return np.clip(blurred + noise + shot, 0, 1).astype(np.float32)


def _edit(img: np.ndarray, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed + 202)
    out = img.copy()
    h, w = img.shape[:2]
    bh, bw = h // 4, w // 4
    y0, x0 = int(rng.integers(0, h - bh)), int(rng.integers(0, w - bw))
    patch = scale_by(img[y0:y0 + bh, x0:x0 + bw], 1.0)
    out[y0:y0 + bh, x0:x0 + bw] = 0.5 * patch + 0.5 * rng.uniform(0.2, 0.8, 3)[None, None, :]
    return np.clip(out, 0, 1).astype(np.float32)


def _encode(img: np.ndarray, fmt: str, quality: int, strip: bool) -> tuple[bytes, str]:
    pil = from_float(img)
    buf = io.BytesIO()
    if fmt == "JPEG":
        pil.convert("RGB").save(buf, "JPEG", quality=quality)
        return buf.getvalue(), ".jpg"
    if fmt == "WEBP":
        pil.save(buf, "WEBP", quality=quality, lossless=(quality >= 100))
        return buf.getvalue(), ".webp"
    pil.save(buf, "PNG")
    return buf.getvalue(), ".png"


def generate(out_dir: str | Path, n_each: int = 2, seed: int = 20261005, size: tuple[int, int] = (384, 512),
             key: int = 20261005) -> list[HardCase]:
    """Write a labelled benchmark set to ``out_dir`` and return the records. Reproducible for a given seed."""
    out = ensure_dir(Path(out_dir))
    h, w = size
    cases: list[HardCase] = []
    idx = 0

    def save(img: np.ndarray, label: str, generator: str, transform: str, fmt: str, quality: int, strip: bool,
             notes: str = "", surrogate: dict | None = None) -> None:
        nonlocal idx
        idx += 1
        gt_level, gt_desc = LABELS[label]
        data, ext = _encode(img, fmt, quality, strip)
        name = safe_filename(f"HC-{idx:03d}_{label.replace(' ', '_')}{ext}")
        (out / name).write_bytes(data)
        with Image.open(io.BytesIO(data)) as im:
            iw, ih = im.size
        cases.append(HardCase(f"HC-{idx:03d}", label, gt_level, GROUND_TRUTH_LEVELS[gt_level], generator, transform,
                              f"{name}", fmt, iw, ih, notes or gt_desc, surrogate or {}))

    for i in range(int(n_each)):
        base = PROC.scene(h, w, seed=seed + i)
        save(base, "SYNTHETIC", "procedural 1/f + shapes", "none (PNG lossless)", "PNG", 100, True)
        save(base, "SYNTHETIC", "procedural 1/f + shapes", "JPEG q85", "JPEG", 85, True,
             notes="Synthetic, JPEG-compressed (studies compression confounds).")
        save(_camera_like(base, seed + i), "NATURAL-LIKE CONTROL", "procedural + camera-noise model",
             "optical blur + shot/read noise, JPEG q92", "JPEG", 92, True,
             notes="Control that imitates camera capture. NOT a real photograph; do not treat as a real-origin sample.")
        emb = SUR.embed(base, SUR.SurrogateConfig(family="spatial", strength=4.0, key=key))
        save(emb.watermarked, "SYNTHETIC + SURROGATE WATERMARK", "procedural + keyed surrogate",
             "keyed surrogate embed (PNG)", "PNG", 100, True, surrogate={"family": "spatial", "strength": 4.0, "key": key},
             notes="Carries a known keyed surrogate watermark (LEVEL 4 ground truth).")
        save(_edit(base, seed + i), "SYNTHETIC EDITED", "procedural + local edit", "local patch edit (PNG)", "PNG", 100,
             True)
        up = scale_by(scale_by(base, 0.5), 2.0)
        save(up[:h, :w] if up.shape[:2] != (h, w) else up, "SYNTHETIC UPSCALED", "procedural + resample",
             "downscale x0.5 then upscale x2 (PNG)", "PNG", 100, True)
    return cases
