"""Detection benchmark for a SynthID verifier on a researcher-labelled dataset.

Dataset layout (labels are the researcher's ground truth, never inferred)::

    <dataset>/positive/...   images expected to carry the signal
    <dataset>/negative/...   controls (real photographs, other generators, ...)
    <dataset>/manifest.csv   optional: path,label,group,split  (label 1/0)

Without a manifest, the group is the first sub-folder below positive/ or
negative/ (e.g. negative/real_controls/, negative/other_generator/) and the
split is "held-out": a fixed detector is not trained here, so every item is an
evaluation item. Items whose verifier state is not scorable (UNKNOWN, INVALID,
UNAVAILABLE) are excluded from ROC/AUC and reported as abstentions.

Metrics: ROC, AUC (Mann-Whitney U with tie correction), TPR, FPR, precision,
recall, F1 and accuracy at a threshold, Wilson 95% intervals for proportions,
stratified bootstrap 95% interval for AUC, and per-group rates.
"""
from __future__ import annotations

import csv
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from app.utils.paths import is_within
from app.utils.serialization import jsonable

IMAGE_EXT = {".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif"}
MAX_ITEMS = 20_000
Z95 = 1.959963984540054


@dataclass
class DatasetItem:
    path: str
    label: int
    group: str = ""
    split: str = "held-out"


@dataclass
class BenchmarkResult:
    status: str
    detail: str = ""
    method_id: str = "SID-M1"
    threshold: float = 0.5
    seed: int = 0
    n_items: int = 0
    n_positive: int = 0
    n_negative: int = 0
    n_scored: int = 0
    n_abstained: int = 0
    metrics: dict = field(default_factory=dict)
    roc: list = field(default_factory=list)
    groups: list = field(default_factory=list)
    score_basis: list = field(default_factory=list)
    items: list = field(default_factory=list)
    runtime_s: float = 0.0

    def to_dict(self) -> dict:
        return jsonable(self)


# ------------------------------------------------------------------ dataset
def load_dataset(root: Path) -> list[DatasetItem]:
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"Dataset folder not found: {root}")
    manifest = root / "manifest.csv"
    items: list[DatasetItem] = []
    if manifest.is_file():
        with manifest.open(newline="", encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                rel = (row.get("path") or "").strip()
                p = (root / rel).resolve()
                if not rel or not is_within(root, p) or not p.is_file():
                    raise ValueError(f"manifest.csv: invalid or missing path {rel!r}")
                lab = str(row.get("label", "")).strip()
                if lab not in ("0", "1"):
                    raise ValueError(f"manifest.csv: label must be 0 or 1 for {rel!r}")
                items.append(DatasetItem(str(p), int(lab), (row.get("group") or "").strip(),
                                         (row.get("split") or "held-out").strip() or "held-out"))
    else:
        for name, label in (("positive", 1), ("negative", 0)):
            d = root / name
            if not d.is_dir():
                continue
            for p in sorted(d.rglob("*")):
                if p.is_file() and p.suffix.lower() in IMAGE_EXT and is_within(root, p):
                    rel = p.relative_to(d).parts
                    group = rel[0] if len(rel) > 1 else name
                    items.append(DatasetItem(str(p), label, group))
    if len(items) > MAX_ITEMS:
        raise ValueError(f"Dataset has {len(items)} items; the limit is {MAX_ITEMS}.")
    if not items:
        raise ValueError("No images found. Expected positive/ and negative/ sub-folders or a manifest.csv.")
    return items


# ------------------------------------------------------------------ metrics (pure)
def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float] | None:
    if n <= 0:
        return None
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def auc_mann_whitney(labels, scores) -> float | None:
    y = np.asarray(labels, dtype=int)
    s = np.asarray(scores, dtype=float)
    n1, n0 = int((y == 1).sum()), int((y == 0).sum())
    if n1 == 0 or n0 == 0:
        return None
    order = np.argsort(s, kind="mergesort")
    ranks = np.empty(len(s), dtype=float)
    sorted_s = s[order]
    i = 0
    while i < len(s):  # average ranks over ties
        j = i
        while j + 1 < len(s) and sorted_s[j + 1] == sorted_s[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    u = ranks[y == 1].sum() - n1 * (n1 + 1) / 2.0
    return float(u / (n1 * n0))


def roc_curve(labels, scores) -> list[list[float]]:
    """[[fpr, tpr, threshold], ...] from the strictest threshold (+inf) to the most lenient."""
    y = np.asarray(labels, dtype=int)
    s = np.asarray(scores, dtype=float)
    n1, n0 = max(int((y == 1).sum()), 1), max(int((y == 0).sum()), 1)
    pts = [[0.0, 0.0, float("inf")]]
    for t in sorted(set(s.tolist()), reverse=True):
        pred = s >= t
        pts.append([float((pred & (y == 0)).sum() / n0), float((pred & (y == 1)).sum() / n1), float(t)])
    return pts


def confusion(labels, scores, threshold: float) -> dict:
    y = np.asarray(labels, dtype=int)
    pred = np.asarray(scores, dtype=float) >= threshold
    tp, fp = int((pred & (y == 1)).sum()), int((pred & (y == 0)).sum())
    fn, tn = int((~pred & (y == 1)).sum()), int((~pred & (y == 0)).sum())
    tpr = tp / (tp + fn) if tp + fn else None
    fpr = fp / (fp + tn) if fp + tn else None
    prec = tp / (tp + fp) if tp + fp else None
    f1 = 2 * prec * tpr / (prec + tpr) if prec is not None and tpr is not None and (prec + tpr) > 0 else None
    n = tp + fp + tn + fn
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "tpr": tpr, "fpr": fpr, "precision": prec, "recall": tpr, "f1": f1,
            "accuracy": (tp + tn) / n if n else None, "tpr_ci95": wilson(tp, tp + fn), "fpr_ci95": wilson(fp, fp + tn),
            "precision_ci95": wilson(tp, tp + fp)}


def bootstrap_auc_ci(labels, scores, n_boot: int = 1000, seed: int = 0) -> tuple[float, float] | None:
    y = np.asarray(labels, dtype=int)
    s = np.asarray(scores, dtype=float)
    pos, neg = np.flatnonzero(y == 1), np.flatnonzero(y == 0)
    if len(pos) < 2 or len(neg) < 2:
        return None
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        idx = np.concatenate([rng.choice(pos, len(pos)), rng.choice(neg, len(neg))])
        a = auc_mann_whitney(y[idx], s[idx])
        if a is not None:
            vals.append(a)
    if not vals:
        return None
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def evaluate(labels, scores, groups=None, threshold: float = 0.5, seed: int = 0, n_boot: int = 1000) -> dict:
    labels, scores = list(labels), list(scores)
    m = confusion(labels, scores, threshold)
    m["auc"] = auc_mann_whitney(labels, scores)
    m["auc_ci95"] = bootstrap_auc_ci(labels, scores, n_boot, seed) if m["auc"] is not None else None
    m["threshold"] = threshold
    out_groups = []
    if groups is not None:
        for g in sorted(set(groups)):
            idx = [i for i, x in enumerate(groups) if x == g]
            gl = [labels[i] for i in idx]
            gs = [scores[i] for i in idx]
            c = confusion(gl, gs, threshold)
            label = "positive" if all(v == 1 for v in gl) else "negative" if all(v == 0 for v in gl) else "mixed"
            out_groups.append({"group": g, "kind": label, "n": len(idx), "tpr": c["tpr"], "fpr": c["fpr"],
                               "tpr_ci95": c["tpr_ci95"], "fpr_ci95": c["fpr_ci95"]})
    return {"metrics": m, "roc": roc_curve(labels, scores), "groups": out_groups}


# ------------------------------------------------------------------ run
def run_benchmark(items: list[DatasetItem], verifier, threshold: float = 0.5, seed: int = 20261002,
                  progress=None) -> BenchmarkResult:
    t0 = time.perf_counter()
    res = BenchmarkResult(status="UNAVAILABLE", threshold=threshold, seed=seed, n_items=len(items),
                          n_positive=sum(1 for i in items if i.label == 1), n_negative=sum(1 for i in items if i.label == 0))
    if not verifier.available:
        res.detail = "No local SynthID engine is configured. A benchmark needs a detector; nothing was measured."
        return res
    labels, scores, groups, bases = [], [], [], set()
    for n, it in enumerate(items, 1):
        if progress:
            progress(int(5 + 85 * n / max(len(items), 1)), f"Benchmark {n}/{len(items)}: {Path(it.path).name}")
        rec = verifier.verify(Path(it.path))
        row = {"path": it.path, "label": it.label, "group": it.group, "split": it.split, **rec.to_dict()}
        res.items.append(row)
        if rec.score is None:
            res.n_abstained += 1
            continue
        labels.append(it.label)
        scores.append(rec.score)
        groups.append(it.group or ("positive" if it.label else "negative"))
        bases.add(rec.score_basis)
    res.n_scored = len(scores)
    res.score_basis = sorted(bases)
    res.runtime_s = time.perf_counter() - t0
    if len(set(labels)) < 2:
        res.status = "INSUFFICIENT DATA"
        res.detail = "Scored items must include both positives and negatives to compute ROC/AUC."
        return res
    ev = evaluate(labels, scores, groups, threshold, seed)
    res.metrics, res.roc, res.groups = ev["metrics"], ev["roc"], ev["groups"]
    res.status = "COMPLETE"
    res.detail = (f"{res.n_scored} scored, {res.n_abstained} abstained. Labels are researcher-supplied ground truth. "
                  "Metrics describe this dataset and engine build only.")
    return res
