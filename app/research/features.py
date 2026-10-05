"""Handcrafted forensic feature vectors and geometric statistics (numpy only).

These are ADAPTED, learning-free versions of ideas named in the taxonomy. They do NOT
load CLIP / ViT / DINO weights (which need a deep-learning runtime) and are therefore
labelled as handcrafted descriptors, never as the published learned detectors:

    spectral_vector     radial log-power profile + high-frequency tail + band energies
                        (Durall 2020 / Dzanic 2020 style descriptor)
    dct_benford_vector  Benford JS-divergence feature vector over re-quantisation qualities
    residual_vector     statistics of several residual operators (energy, kurtosis, autocorr)
    wavelet_vector      sub-band energy / kurtosis / sparsity across levels
    lid / multiLID      Local Intrinsic Dimensionality of patch descriptors (Houle MLE;
                        Lorenz 2023 multiLID keeps per-neighbour growth, here over a patch set)

Attribution without training: a nearest-prototype score compares an image's descriptor
to per-group prototypes the researcher has built from labelled images (feature-space
attribution / prototype signature). No classifier is fitted; distances are reported
with the caveat that this is a descriptive similarity, not a trained detector.
"""
from __future__ import annotations

import numpy as np

from app.research import dct as D
from app.research import spectral as S
from app.research import wavelet as W
from app.research.imaging import EPS, luminance
from app.research.residuals import residual


def spectral_vector(x: np.ndarray, nbins: int = 32) -> dict:
    y = luminance(x) if x.ndim == 3 else x
    pw = S.welch_power(y, tile=min(256, *y.shape), overlap=min(256, *y.shape) // 2)
    f, prof = S.radial_profile(pw, nbins)
    logp = np.log10(prof + EPS)
    tail = S.spectral_tail(f, prof)
    bands = S.band_energy(pw)
    vec = logp.tolist() + [tail.get("slope", 0.0), tail.get("tail_deviation_db", 0.0)] + [b["fraction"] for b in bands]
    return {"vector": vec, "names": [f"logP[{i}]" for i in range(nbins)] + ["slope", "tail_db"] +
            [f"band:{b['band']}" for b in bands], "radial": {"freq": f.tolist(), "logpower": logp.tolist()},
            "tail": tail}


def dct_benford_vector(x: np.ndarray, img=None) -> dict:
    a = D.analyse((luminance(x) if x.ndim == 3 else x) * 255.0, img)
    if a.get("status") == "INSUFFICIENT DATA":
        return a
    vec = [v.get("js_divergence") or 0.0 for v in a["benford_feature_vector"]]
    return {"vector": vec, "names": [f"benfordJS@q{v['quality']}" for v in a["benford_feature_vector"]],
            "benford": a["benford"], "blockiness": a["blockiness"]}


def residual_vector(x: np.ndarray, ops=("gaussian", "laplacian", "highpass", "wavelet", "denoise")) -> dict:
    from app.research.residuals import stats
    y = luminance(x) if x.ndim == 3 else x
    vec, names = [], []
    for op in ops:
        s = stats(residual(y, op), with_spectrum=False)["stats"]
        for key in ("energy", "kurtosis", "entropy_bits"):
            vec.append(float(s[key]))
            names.append(f"{op}:{key}")
        vec.append(float(s["autocorrelation"]["max_offcentre"]))
        names.append(f"{op}:autocorr_offcentre")
    return {"vector": vec, "names": names}


def wavelet_vector(x: np.ndarray, levels: int = 3) -> dict:
    y = luminance(x) if x.ndim == 3 else x
    rows = W.subband_stats(W.wavedec2(y, levels, "db2"))
    vec, names = [], []
    for r in rows:
        for key in ("energy", "kurtosis", "sparsity"):
            vec.append(float(r[key]))
            names.append(f"L{r['level']}{r['band']}:{key}")
    return {"vector": vec, "names": names}


def descriptor(x: np.ndarray, img=None) -> dict:
    """Concatenated handcrafted descriptor used for cross-image attribution prototypes."""
    sv = spectral_vector(x)
    dv = dct_benford_vector(x, img)
    rv = residual_vector(x)
    wv = wavelet_vector(x)
    vec = sv["vector"] + (dv.get("vector", [])) + rv["vector"] + wv["vector"]
    names = sv["names"] + dv.get("names", []) + rv["names"] + wv["names"]
    return {"vector": vec, "names": names}


# ------------------------------------------------------------------ LID / multiLID
def _patch_descriptors(x: np.ndarray, patch: int = 16, stride: int = 16, op: str = "highpass") -> np.ndarray:
    r = residual(luminance(x) if x.ndim == 3 else x, op)
    h, w = r.shape
    out = []
    for y0 in range(0, h - patch + 1, stride):
        for x0 in range(0, w - patch + 1, stride):
            out.append(r[y0:y0 + patch, x0:x0 + patch].ravel())
    return np.asarray(out, dtype=np.float64)


def lid_mle(dists: np.ndarray) -> float:
    """Houle & Hein MLE estimator of local intrinsic dimensionality from sorted neighbour distances."""
    d = np.sort(dists)
    d = d[d > 0]
    if len(d) < 2:
        return 0.0
    w = d[-1]
    r = np.log(d[:-1] / w)
    s = r.sum()
    return float(-(len(d) - 1) / s) if s < 0 else 0.0


def lid_features(x: np.ndarray, k: int = 20, patch: int = 16, stride: int = 16, max_patches: int = 2000,
                 seed: int = 0) -> dict:
    """LID and multiLID (Lorenz et al. 2023 style) over high-pass patch descriptors."""
    P = _patch_descriptors(x, patch, stride)
    if len(P) < k + 2:
        return {"status": "INSUFFICIENT DATA", "n_patches": int(len(P))}
    rng = np.random.default_rng(seed)
    if len(P) > max_patches:
        P = P[rng.choice(len(P), max_patches, replace=False)]
    P = P - P.mean(1, keepdims=True)
    norms = (P * P).sum(1)
    lids, multi = [], []
    step = max(1, len(P) // 400)
    for i in range(0, len(P), step):
        d2 = norms + norms[i] - 2 * (P @ P[i])
        d = np.sqrt(np.maximum(d2, 0))
        d[i] = np.inf
        nn = np.sort(d)[:k]
        lids.append(lid_mle(nn))
        w = nn[-1] if nn[-1] > 0 else 1.0
        multi.append((-np.log(np.maximum(nn[:-1] / w, 1e-12))).tolist())
    multi = np.asarray(multi)
    return {"status": "COMPLETE", "n_patches": int(len(P)), "k": k, "lid_mean": float(np.mean(lids)),
            "lid_std": float(np.std(lids)), "multilid_mean": multi.mean(0).tolist(),
            "vector": [float(np.mean(lids)), float(np.std(lids)), float(np.percentile(lids, 10)),
                       float(np.percentile(lids, 90))] + multi.mean(0).tolist(),
            "note": "LID over handcrafted high-pass patch descriptors; not the paper's deep-feature LID."}


# ------------------------------------------------------------------ attribution
def cosine(a, b) -> float:
    a, b = np.asarray(a, float), np.asarray(b, float)
    da, db = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / (da * db)) if da > EPS and db > EPS else 0.0


def standardize(vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    v = np.asarray(vectors, float)
    mu, sd = v.mean(0), v.std(0) + EPS
    return (v - mu) / sd, mu, sd


def nearest_prototype(vec, prototypes: dict, mu=None, sd=None) -> dict:
    """Distance of a descriptor to per-group prototype means (feature-space attribution, no training)."""
    v = np.asarray(vec, float)
    if mu is not None:
        v = (v - np.asarray(mu)) / np.asarray(sd)
    scores = {}
    for g, proto in prototypes.items():
        p = np.asarray(proto, float)
        scores[g] = {"cosine": cosine(v, p), "euclidean": float(np.linalg.norm(v - p))}
    best = max(scores, key=lambda g: scores[g]["cosine"]) if scores else None
    return {"scores": scores, "nearest": best,
            "note": "Descriptive similarity to researcher-built prototypes; not a trained classifier verdict."}
