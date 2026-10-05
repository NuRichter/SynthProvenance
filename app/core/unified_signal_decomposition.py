"""Unified Signal Decomposition Engine (v4 Section 15).

A single interface over the research engine so every compatible method exposes the same
five verbs. The common data object is :class:`Decomposition`:

    observed_image     the input (float HxWxC in [0, 1])
    content_estimate   estimated visual content (signal removed)
    signal_estimate    estimated candidate signal / fingerprint (observed - content)
    residual           what the decomposition could not explain (observed - content - signal)
    confidence_map     per-pixel confidence in [0, 1] (relative candidate energy, smoothed)

Operators (each returns a :class:`DecompResult`):

    analyze(image, method)        descriptive statistics for a method (no modification)
    estimate(image, method)       a candidate signal estimate
    separate(image, method)       content + signal + residual decomposition
    reconstruct(image, method)    the content estimate (image with the candidate removed)
    validate(image, method, gt)   score against ground truth when a controlled surrogate is provided

The engine refuses to separate/reconstruct with a method whose registry capability does
not advertise it: a detector is never silently used as a separator.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.research import runner as RUN
from app.research import separation as SEP
from app.research import surrogate as SUR
from app.research.imaging import EPS, box_mean, gaussian_blur, luminance
from app.research.methods import MethodRegistry

# method capability -> separation sub-method used when the UI asks a non-separation method to separate
_DEFAULT_SEP = "wavelet"


class CapabilityError(RuntimeError):
    pass


@dataclass
class Decomposition:
    observed_image: np.ndarray
    content_estimate: np.ndarray | None = None
    signal_estimate: np.ndarray | None = None
    residual: np.ndarray | None = None
    confidence_map: np.ndarray | None = None

    def maps(self) -> dict:
        out = {"observed": self.observed_image}
        for name in ("content_estimate", "signal_estimate", "residual", "confidence_map"):
            v = getattr(self, name)
            if v is not None:
                out[name] = v
        return out


@dataclass
class DecompResult:
    operator: str
    method_id: str
    status: str
    decomposition: Decomposition | None = None
    readouts: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    ground_truth: dict = field(default_factory=dict)
    detail: str = ""

    def to_dict(self) -> dict:
        return {"operator": self.operator, "method_id": self.method_id, "status": self.status,
                "readouts": self.readouts, "metrics": self.metrics, "ground_truth": self.ground_truth,
                "detail": self.detail}


def _first_map(maps: dict, *names: str):
    for n in names:
        if n in maps and maps[n] is not None:
            return maps[n]
    return None


def _confidence(signal_plane: np.ndarray) -> np.ndarray:
    e = np.abs(signal_plane.astype(np.float32))
    e = box_mean(e, 3)
    hi = float(np.percentile(e, 99)) or 1.0
    return np.clip(e / hi, 0, 1).astype(np.float32)


class UnifiedSignalDecomposition:
    def __init__(self, registry: MethodRegistry | None = None) -> None:
        self.registry = registry or MethodRegistry()

    def _method(self, method):
        return method if hasattr(method, "capability") else self.registry.get(method)

    def _input(self, image: np.ndarray, surrogate: SUR.SurrogateConfig | None, clean: np.ndarray | None,
               references, params) -> RUN.MethodInput:
        return RUN.MethodInput(image=image, references=list(references or []), surrogate_cfg=surrogate, clean=clean,
                               params=dict(params or {}))

    # -- verbs ---------------------------------------------------------------
    def analyze(self, image, method, references=None, params=None) -> DecompResult:
        m = self._method(method)
        if not m.can("CAN_ANALYZE"):
            raise CapabilityError(f"{m.method_id} cannot analyze")
        res = RUN.run(m, self._input(image, None, None, references, params))
        return DecompResult("analyze", m.method_id, res.status, Decomposition(image), res.readouts, res.metrics,
                            detail=res.detail)

    def estimate(self, image, method, surrogate=None, clean=None, params=None) -> DecompResult:
        m = self._method(method)
        if not m.can("CAN_ESTIMATE"):
            raise CapabilityError(f"{m.method_id} cannot estimate a signal")
        res = RUN.run(m, self._input(image, surrogate, clean, None, params))
        sig = _first_map(res.maps, "candidate_signal", "signal_estimate", "error_map")
        sig = sig if sig is not None else (luminance(image) - gaussian_blur(luminance(image), 1.2))
        dec = Decomposition(image, signal_estimate=np.asarray(sig, np.float32), confidence_map=_confidence(np.asarray(sig)))
        return DecompResult("estimate", m.method_id, res.status, dec, res.readouts, res.metrics,
                            res.ground_truth, res.detail)

    def separate(self, image, method, surrogate=None, clean=None, params=None) -> DecompResult:
        m = self._method(method)
        sub = m.capability.split(":", 1)[1] if m.capability.startswith("sep:") else None
        if not m.can("CAN_SEPARATE"):
            raise CapabilityError(f"{m.method_id} is not a separation method; it cannot separate content from signal")
        r = SEP.separate(image, sub or _DEFAULT_SEP, params, surrogate_cfg=surrogate, clean=clean)
        y = luminance(image)
        content_y = luminance(r.panels["estimated_content"])
        dec = Decomposition(image, content_estimate=r.panels["estimated_content"],
                            signal_estimate=np.asarray(r.panels["candidate_signal"], np.float32),
                            residual=np.asarray(r.panels["residual"], np.float32),
                            confidence_map=_confidence(np.asarray(r.panels["candidate_signal"])))
        return DecompResult("separate", m.method_id, "COMPLETE", dec,
                            {"Recon PSNR": r.reconstruction.get("psnr_db"), "Recon SSIM": r.reconstruction.get("ssim")},
                            r.reconstruction, r.ground_truth, r.label)

    def reconstruct(self, image, method, surrogate=None, clean=None, params=None) -> DecompResult:
        m = self._method(method)
        if not m.can("CAN_RECONSTRUCT"):
            raise CapabilityError(f"{m.method_id} cannot reconstruct")
        if m.capability == "reconstruction" or m.capability.startswith("frontier:"):
            res = RUN.run(m, self._input(image, surrogate, clean, None, params))
            recon = _first_map(res.maps, "reconstruction", "estimated_content")
            sig = _first_map(res.maps, "error_map", "candidate_signal")
            dec = Decomposition(image, content_estimate=np.asarray(recon, np.float32) if recon is not None else None,
                                signal_estimate=np.asarray(sig, np.float32) if sig is not None else None)
            return DecompResult("reconstruct", m.method_id, res.status, dec, res.readouts, res.metrics,
                                res.ground_truth, res.detail)
        r = self.separate(image, m, surrogate, clean, params)
        r.operator = "reconstruct"
        return r

    def validate(self, image, method, surrogate: SUR.SurrogateConfig, clean: np.ndarray, params=None) -> DecompResult:
        m = self._method(method)
        if not m.can("CAN_VALIDATE"):
            raise CapabilityError(f"{m.method_id} has no ground-truth validation")
        if surrogate is None or clean is None:
            raise CapabilityError("validation needs a controlled surrogate case (surrogate config + clean image)")
        if m.can("CAN_SEPARATE"):
            r = self.separate(image, m, surrogate=surrogate, clean=clean, params=params)
        else:
            res = RUN.run(m, self._input(image, surrogate, clean, None, params))
            dec = Decomposition(image)
            sig = _first_map(res.maps, "candidate_signal", "signal_estimate", "error_map")
            if sig is not None:
                dec.signal_estimate = np.asarray(sig, np.float32)
                dec.confidence_map = _confidence(dec.signal_estimate)
            r = DecompResult("validate", m.method_id, res.status, dec, res.readouts, res.metrics, res.ground_truth,
                             res.detail)
        r.operator = "validate"
        return r

    def available(self, verb: str) -> list:
        flag = {"analyze": "CAN_ANALYZE", "estimate": "CAN_ESTIMATE", "separate": "CAN_SEPARATE",
                "reconstruct": "CAN_RECONSTRUCT", "validate": "CAN_VALIDATE"}[verb]
        return [m for m in self.registry.ready() if m.can(flag)]
