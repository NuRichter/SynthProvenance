"""Consensus engines: patch, multi-scale, cross-region and cross-image agreement.

A candidate fingerprint estimator produces a map F(x) (default: the ``denoise``
residual R = X - Denoise(X), the PRNU-inspired residual named in the taxonomy). The
consensus engines ask whether independent estimates agree:

    patch           stability of the residual's local statistics across tiles
    multi_scale     agreement of residual maps computed at full, 1/2, 1/4, 1/8 scale
    cross_region    agreement of residual spectra between disjoint image quadrants
    cross_image     shared residual of several images from a suspected common source,
                    with a held-out split so a template is never evaluated on the
                    images used to build it (as the brief requires)

Agreement is measured by Pearson correlation of mean-removed maps resampled to a
common grid. These are descriptive consistency measures, not proof of a generator
fingerprint; shared content (edges) also correlates, so controls matter.
"""
from __future__ import annotations

import numpy as np

from app.research import spectral as S
from app.research.imaging import EPS, luminance, resize_plane, tile_grid
from app.research.metrics import pearson
from app.research.residuals import residual


def candidate_map(x: np.ndarray, op: str = "denoise") -> np.ndarray:
    return residual(luminance(x) if x.ndim == 3 else x, op)


def _norm(a: np.ndarray) -> np.ndarray:
    a = a.astype(np.float64)
    a = a - a.mean()
    s = a.std()
    return a / s if s > EPS else a


def patch_consensus(x: np.ndarray, op: str = "denoise", tile: int = 64, overlap: int = 0) -> dict:
    r = candidate_map(x, op)
    h, w = r.shape
    feats = []
    for y0, y1, x0, x1 in tile_grid(h, w, tile, overlap):
        p = r[y0:y1, x0:x1]
        feats.append([float(p.std()), float((p * p).mean()), float(np.abs(p).mean())])
    f = np.array(feats)
    cv = (f.std(0) / (np.abs(f.mean(0)) + EPS)) if len(f) else np.zeros(3)
    return {"n_patches": len(feats), "energy_cv": float(cv[1]),
            "consistency": float(1.0 / (1.0 + cv[1])) if len(f) else 0.0,
            "note": "High energy CV = the residual is localised (texture/edges); low CV = spread evenly."}


def multiscale_consensus(x: np.ndarray, op: str = "denoise", scales=(1.0, 0.5, 0.25, 0.125)) -> dict:
    base = candidate_map(x, op)
    h, w = base.shape
    maps = {}
    for s in scales:
        if s == 1.0:
            maps[s] = base
        else:
            from app.research.imaging import scale_by
            small = candidate_map(scale_by(x, s) if x.ndim == 3 else resize_plane(x, (max(2, int(w * s)), max(2, int(h * s)))), op)
            maps[s] = resize_plane(small.astype(np.float32), (w, h))
    pairs = []
    ss = list(scales)
    for i in range(len(ss)):
        for j in range(i + 1, len(ss)):
            pairs.append({"scales": [ss[i], ss[j]], "correlation": pearson(maps[ss[i]], maps[ss[j]])})
    agree = float(np.mean([p["correlation"] for p in pairs])) if pairs else 0.0
    return {"pairs": pairs, "agreement": agree, "scales": list(scales)}


def cross_region_consensus(x: np.ndarray, op: str = "denoise") -> dict:
    r = candidate_map(x, op)
    h, w = r.shape
    quads = {"TL": r[: h // 2, : w // 2], "TR": r[: h // 2, w // 2:], "BL": r[h // 2:, : w // 2], "BR": r[h // 2:, w // 2:]}
    names = list(quads)
    th = min(q.shape[0] for q in quads.values())
    tw = min(q.shape[1] for q in quads.values())
    specs = {n: np.log1p(np.sqrt(S.welch_power(q[:th, :tw], tile=min(64, th, tw), overlap=0))) for n, q in quads.items()}
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            pairs.append({"regions": [names[i], names[j]], "spectral_correlation": pearson(specs[names[i]], specs[names[j]])})
    return {"pairs": pairs, "agreement": float(np.mean([p["spectral_correlation"] for p in pairs])) if pairs else 0.0}


def cross_image_consensus(images: list[np.ndarray], op: str = "denoise", seed: int = 0) -> dict:
    """Estimate a shared residual template from a build split and evaluate it on a held-out split.

    Correlation of each image's residual with the mean template is reported per split; the held-out
    mean is the honest figure (never evaluate a template on the images used to build it).
    """
    if len(images) < 4:
        return {"status": "INSUFFICIENT DATA", "detail": "need at least 4 images for a build/held-out split"}
    hh = min(im.shape[0] for im in images)
    ww = min(im.shape[1] for im in images)
    res = [_norm(resize_plane(candidate_map(im, op).astype(np.float32), (ww, hh))) for im in images]
    idx = np.arange(len(res))
    np.random.default_rng(seed).shuffle(idx)
    half = len(idx) // 2
    build, held = idx[:half], idx[half:]
    template = np.mean([res[i] for i in build], axis=0)
    tnorm = _norm(template)

    def corr(group):
        return [pearson(res[i], tnorm) for i in group]

    cb, ch = corr(build), corr(held)
    # control: correlation to a template built from independent random noise of the same shape
    rng = np.random.default_rng(seed + 1)
    ctrl_template = _norm(np.mean([rng.standard_normal((hh, ww)) for _ in build], axis=0))
    ctrl = [pearson(res[i], ctrl_template) for i in held]
    return {"status": "COMPLETE", "n_images": len(images), "build_n": len(build), "held_out_n": len(held),
            "template_energy": float((template ** 2).mean()),
            "build_mean_corr": float(np.mean(cb)), "held_out_mean_corr": float(np.mean(ch)),
            "control_mean_corr": float(np.mean(ctrl)), "held_out_minus_control": float(np.mean(ch) - np.mean(ctrl)),
            "note": "A shared source fingerprint would give held-out correlation clearly above the noise-template "
                    "control. Shared content/processing can also raise it; use images with different scenes."}
