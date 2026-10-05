"""Compare an imported external heatmap with a local evidence map (pure numpy).

An external detector's heatmap (e.g. TruthScan's "which regions triggered analysis") is
imported from a user-supplied result and treated as evidence to study, never as truth.
It is resampled onto the local map's grid and compared with mathematically appropriate
measures only:

    pearson         linear correlation of the two intensity fields
    iou             intersection-over-union of the two top-quantile active regions
    dice            Dice overlap of the same regions
    region_consistency   fraction of the external active region covered by the local one

Nothing here concludes that either map is correct; it quantifies spatial overlap.
"""
from __future__ import annotations

import numpy as np

from app.research.imaging import as_float, luminance, resize_plane

EPS = 1e-9


def _to_plane(arr) -> np.ndarray:
    a = np.asarray(arr, dtype=np.float32)
    if a.ndim == 3:
        a = luminance(as_float(a)) if a.shape[2] == 3 else a[:, :, 0]
    return a.astype(np.float32)


def _norm01(a: np.ndarray) -> np.ndarray:
    lo, hi = float(np.nanmin(a)), float(np.nanmax(a))
    return (a - lo) / (hi - lo) if hi - lo > EPS else np.zeros_like(a)


def _pearson(a: np.ndarray, b: np.ndarray) -> float:
    x = a.ravel().astype(np.float64) - a.mean()
    y = b.ravel().astype(np.float64) - b.mean()
    den = float(np.sqrt((x * x).sum() * (y * y).sum()))
    return float((x * y).sum() / den) if den > EPS else 0.0


def compare_maps(external_heatmap, local_map, quantile: float = 0.80) -> dict:
    """Compare an external heatmap against one local map. Both are 2-D or HxWx{1,3}; the external is resampled."""
    ext = _norm01(_to_plane(external_heatmap))
    loc = _norm01(_to_plane(local_map))
    if ext.shape != loc.shape:
        ext = _norm01(resize_plane(ext, (loc.shape[1], loc.shape[0])))
    q = float(min(max(quantile, 0.5), 0.99))

    def active(x: np.ndarray) -> np.ndarray:
        # top (1-q) fraction by value; strictly above the q-quantile so a mostly-flat map does not select everything
        thr = float(np.quantile(x, q))
        mask = x > thr
        if not mask.any():                 # degenerate (e.g. a near-constant map): fall back to the maximum level
            mask = x >= float(x.max())
        return mask

    a = active(ext)
    b = active(loc)
    inter = float(np.logical_and(a, b).sum())
    union = float(np.logical_or(a, b).sum())
    area_a = float(a.sum())
    return {
        "shape": [int(loc.shape[0]), int(loc.shape[1])],
        "resampled_external": list(external_heatmap.shape[:2]) != [loc.shape[0], loc.shape[1]]
        if hasattr(external_heatmap, "shape") else True,
        "pearson": round(_pearson(ext, loc), 4),
        "iou": round(inter / union, 4) if union > EPS else 0.0,
        "dice": round(2.0 * inter / (area_a + float(b.sum())), 4) if (area_a + b.sum()) > EPS else 0.0,
        "region_consistency": round(inter / area_a, 4) if area_a > EPS else 0.0,
        "active_quantile": q,
        "note": "Spatial overlap of the two top-quantile active regions. Overlap is not correctness; it measures where "
                "the external heatmap and the local map agree on location.",
    }


def agreement_label(metrics: dict) -> str:
    iou, corr = metrics.get("iou", 0.0), abs(metrics.get("pearson", 0.0))
    if iou >= 0.4 and corr >= 0.4:
        return "STRONG SPATIAL AGREEMENT"
    if iou >= 0.2 or corr >= 0.25:
        return "PARTIAL SPATIAL AGREEMENT"
    return "LITTLE SPATIAL AGREEMENT"


def compare_against_local_maps(external_heatmap, local_maps: dict, quantile: float = 0.80) -> dict:
    """Compare the external heatmap against several named local maps (residual / fft / wavelet / reconstruction / ...)."""
    rows = {}
    for name, m in (local_maps or {}).items():
        if m is None:
            continue
        try:
            rows[name] = {**compare_maps(external_heatmap, m, quantile), "agreement": agreement_label(
                compare_maps(external_heatmap, m, quantile))}
        except Exception as exc:  # noqa: BLE001 - a bad map is skipped, recorded
            rows[name] = {"error": f"{type(exc).__name__}: {exc}"}
    best = max((k for k in rows if "iou" in rows[k]), key=lambda k: rows[k]["iou"], default="")
    return {"by_map": rows, "best_match": best,
            "best_agreement": rows.get(best, {}).get("agreement", "LITTLE SPATIAL AGREEMENT") if best else "N/A"}
