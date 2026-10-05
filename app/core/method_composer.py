"""Method Composer (v4 Section 16).

Compose a reproducible pipeline of research stages that transform a plane or produce a
map, e.g. ``residual -> wavelet -> pca -> reconstruct`` or ``fft -> patch_consensus ->
embedding -> reconstruct``. A pipeline is plain data (a list of nodes) so it can be
saved, exported to JSON and reproduced deterministically.

Each node is ``{"op": <name>, "enabled": bool, "params": {...}}``. Stage operators are
pure plane→plane or plane→(plane, info) functions drawn from the research engine; the
composer records each stage's output statistics and, when a controlled surrogate is
supplied, the correlation of the running candidate with the known signal, so a chain can
be judged against ground truth. The composer never performs detector-evasion; it only
analyses, estimates and reconstructs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from app import __version__
from app.research import dct as D
from app.research import rpca as RPCA
from app.research import separation as SEP
from app.research import spectral as S
from app.research import wavelet as W
from app.research.imaging import EPS, gaussian_blur, luminance
from app.research.metrics import pearson
from app.research.residuals import residual

# op -> (label, kind). kind "plane" transforms the working plane; "map" produces a candidate without replacing content.
STAGE_OPS: dict[str, dict] = {
    "luminance": {"label": "Luminance", "help": "Reduce to the luminance plane"},
    "residual_highpass": {"label": "High-pass residual", "help": "X - Gaussian(X)"},
    "residual_laplacian": {"label": "Laplacian residual", "help": "Laplacian response"},
    "residual_denoise": {"label": "Denoising residual", "help": "X - wavelet-denoise(X) (PRNU-style)"},
    "wavelet_detail": {"label": "Wavelet detail", "help": "Reconstruct from detail sub-bands only"},
    "fft_crossdiff": {"label": "FFT cross-difference", "help": "Synthbuster-style residual"},
    "dct_highpass": {"label": "Block-DCT high-pass", "help": "Zero low-frequency DCT coefficients"},
    "pca_sparse": {"label": "Robust-PCA sparse", "help": "Sparse layer S of I = L + S + E"},
    "normalize": {"label": "Normalise", "help": "Zero-mean, unit-std"},
    "patch_consensus": {"label": "Patch consensus", "help": "Replace by tile-wise energy consistency map"},
    "reconstruct": {"label": "Reconstruct content", "help": "Content = observed - current candidate"},
}


def _apply(op: str, plane: np.ndarray, params: dict, observed: np.ndarray) -> np.ndarray:
    if op == "luminance":
        return plane
    if op == "residual_highpass":
        return residual(plane, "highpass")
    if op == "residual_laplacian":
        return residual(plane, "laplacian")
    if op == "residual_denoise":
        return residual(plane, "denoise")
    if op == "wavelet_detail":
        return W.detail_residual(plane, int(params.get("levels", 2)))
    if op == "fft_crossdiff":
        return S.cross_difference(plane)
    if op == "dct_highpass":
        return residual(plane, "dct")
    if op == "pca_sparse":
        res = RPCA.decompose(plane, mode="image", max_iter=int(params.get("max_iter", 40)))
        return res["S"]
    if op == "normalize":
        p = plane.astype(np.float64) - plane.mean()
        return (p / (p.std() + EPS)).astype(np.float32)
    if op == "patch_consensus":
        from app.research.imaging import box_mean
        e = box_mean(np.abs(plane), int(params.get("radius", 8)))
        return e.astype(np.float32)
    if op == "reconstruct":
        return (observed - plane).astype(np.float32)
    raise ValueError(f"Unknown stage op {op!r}")


@dataclass
class Pipeline:
    name: str = "pipeline"
    nodes: list = field(default_factory=list)

    def enabled(self) -> list:
        return [n for n in self.nodes if n.get("enabled", True)]

    def to_dict(self) -> dict:
        return {"name": self.name, "software": f"SynthProvenance {__version__}", "nodes": self.nodes}

    @classmethod
    def from_dict(cls, d: dict) -> "Pipeline":
        return cls(name=d.get("name", "pipeline"), nodes=list(d.get("nodes", [])))

    @staticmethod
    def node(op: str, enabled: bool = True, **params) -> dict:
        if op not in STAGE_OPS:
            raise ValueError(f"Unknown op {op!r}; available: {', '.join(STAGE_OPS)}")
        return {"op": op, "enabled": enabled, "params": params}


@dataclass
class ComposeResult:
    pipeline: dict
    status: str
    stages: list = field(default_factory=list)
    final_candidate: np.ndarray | None = None
    maps: dict = field(repr=False, default_factory=dict)
    ground_truth: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"pipeline": self.pipeline, "status": self.status, "stages": self.stages,
                "ground_truth": self.ground_truth}


def run_pipeline(image: np.ndarray, pipeline: Pipeline, known_signal: np.ndarray | None = None) -> ComposeResult:
    observed = luminance(image).astype(np.float32)
    plane = observed.copy()
    stages = []
    maps = {"observed": observed}
    for i, n in enumerate(pipeline.enabled(), 1):
        op = n["op"]
        plane = _apply(op, plane, n.get("params", {}), observed)
        corr = abs(pearson(plane, known_signal)) if known_signal is not None else None
        st = {"index": i, "op": op, "label": STAGE_OPS[op]["label"], "params": n.get("params", {}),
              "energy": float((plane.astype(np.float64) ** 2).mean()), "std": float(plane.std()),
              "candidate_vs_known_corr": corr}
        stages.append(st)
        maps[f"stage{i}_{op}"] = plane.copy()
    gt = {}
    if known_signal is not None and stages:
        gt = {"final_candidate_vs_known_corr": stages[-1]["candidate_vs_known_corr"],
              "best_stage": max(stages, key=lambda s: s["candidate_vs_known_corr"] or -1)["index"]}
    return ComposeResult(pipeline.to_dict(), "COMPLETE", stages, plane, maps, gt)


PRESETS = {
    "residual_wavelet_pca": ["residual_highpass", "wavelet_detail", "pca_sparse", "reconstruct"],
    "fft_patch_embed": ["fft_crossdiff", "patch_consensus", "normalize"],
    "denoise_consensus": ["residual_denoise", "normalize", "patch_consensus"],
}


def preset(name: str) -> Pipeline:
    ops = PRESETS[name]
    return Pipeline(name=name, nodes=[Pipeline.node(op) for op in ops])
