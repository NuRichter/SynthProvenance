"""Robust PCA research formulation  I = L + S + E.

L  content estimate (low rank)
S  structured candidate signal (sparse)
E  residual (dense, small): what remains when the solver stops

Solved by Principal Component Pursuit with the inexact augmented Lagrange multiplier
method (Candes, Li, Ma & Wright 2011; Lin, Chen & Ma 2010):

    minimise ||L||_* + lambda ||S||_1   subject to  ||I - L - S||_F <= tol ||I||_F

Every parameter (lambda, mu, rho, max_iter, tol, mode) and the convergence history
(relative residual, rank(L), nnz(S) per iteration) are returned for the record.

Modes
-----
image   M is the analysis plane itself (H x W)
patch   M stacks non-overlapping p x p patches as columns (p^2 x n_patches); repeated
        structure across patches tends to fall into L, patch-unique content into S/E
"""
from __future__ import annotations

import math
import time

import numpy as np

from app.research.imaging import EPS


def _svt(x: np.ndarray, tau: float) -> tuple[np.ndarray, int]:
    u, s, vt = np.linalg.svd(x, full_matrices=False)
    s = np.maximum(s - tau, 0.0)
    r = int((s > 0).sum())
    return (u[:, :r] * s[:r]) @ vt[:r], r


def _shrink(x: np.ndarray, tau: float) -> np.ndarray:
    return np.sign(x) * np.maximum(np.abs(x) - tau, 0.0)


def pcp(m: np.ndarray, lam: float | None = None, max_iter: int = 100, tol: float = 1e-6, rho: float = 1.5,
        mu: float | None = None, progress=None) -> dict:
    m = m.astype(np.float64)
    n1, n2 = m.shape
    lam = float(lam) if lam else 1.0 / math.sqrt(max(n1, n2))
    norm2 = float(np.linalg.norm(m, 2))
    norm_inf = float(np.abs(m).max()) / lam
    dual = max(norm2, norm_inf, EPS)
    y = m / dual
    mu = float(mu) if mu else 1.25 / max(norm2, EPS)
    mu_max = mu * 1e7
    normf = float(np.linalg.norm(m)) or EPS
    s = np.zeros_like(m)
    l = np.zeros_like(m)
    hist = []
    t0 = time.perf_counter()
    status = "MAX ITERATIONS"
    for it in range(1, int(max_iter) + 1):
        l, rank = _svt(m - s + y / mu, 1.0 / mu)
        s = _shrink(m - l + y / mu, lam / mu)
        z = m - l - s
        y = y + mu * z
        mu = min(mu * rho, mu_max)
        err = float(np.linalg.norm(z)) / normf
        hist.append({"iteration": it, "rel_residual": err, "rank_L": rank, "nnz_S": int((s != 0).sum())})
        if progress and it % 5 == 0:
            progress(it, err)
        if err < tol:
            status = "CONVERGED"
            break
    e = m - l - s
    return {"L": l, "S": s, "E": e, "status": status, "iterations": len(hist), "history": hist,
            "parameters": {"lambda": lam, "mu0": float(1.25 / max(norm2, EPS)), "rho": rho, "max_iter": int(max_iter),
                           "tol": tol}, "runtime_s": time.perf_counter() - t0,
            "summary": {"rank_L": hist[-1]["rank_L"] if hist else 0, "sparsity_S": float((s != 0).mean()),
                        "energy_L": float((l * l).mean()), "energy_S": float((s * s).mean()), "energy_E": float((e * e).mean()),
                        "final_rel_residual": hist[-1]["rel_residual"] if hist else None}}


def to_patches(x: np.ndarray, p: int) -> tuple[np.ndarray, tuple]:
    h, w = (x.shape[0] // p) * p, (x.shape[1] // p) * p
    b = x[:h, :w].reshape(h // p, p, w // p, p).transpose(0, 2, 1, 3).reshape(-1, p * p)
    return b.T, (h, w)


def from_patches(m: np.ndarray, p: int, hw: tuple, full_shape: tuple) -> np.ndarray:
    h, w = hw
    b = m.T.reshape(h // p, w // p, p, p).transpose(0, 2, 1, 3).reshape(h, w)
    out = np.zeros(full_shape, dtype=np.float32)
    out[:h, :w] = b
    return out


def decompose(x: np.ndarray, mode: str = "image", lam: float | None = None, max_iter: int = 100, tol: float = 1e-6,
              patch: int = 16, rho: float = 1.5, progress=None) -> dict:
    """Decompose a float plane. Returns L, S, E planes (same shape as ``x``) and the solver record."""
    if mode == "patch":
        m, hw = to_patches(x, patch)
        res = pcp(m, lam, max_iter, tol, rho, progress=progress)
        for k in ("L", "S", "E"):
            res[k] = from_patches(res[k], patch, hw, x.shape)
        res["parameters"]["patch"] = patch
    elif mode == "image":
        res = pcp(x, lam, max_iter, tol, rho, progress=progress)
        for k in ("L", "S", "E"):
            res[k] = res[k].astype(np.float32)
    else:
        raise ValueError("mode must be 'image' or 'patch'")
    res["parameters"]["mode"] = mode
    return res
