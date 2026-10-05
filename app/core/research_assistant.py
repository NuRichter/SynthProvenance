"""Research Assistant and Experiment Discovery (v4 Sections 17 & 24).

Rule-based, explainable recommendations. The assistant inspects image properties,
provenance, format, resolution, a chosen research goal and the locally available engines,
then recommends methods and controls with an explicit reason, the required data and a
rough compute cost. It never executes anything and never recommends an irreversible or
detector-evasion action.

Experiment discovery ranks candidate (method / pipeline) options by expected scientific
value subject to fidelity, runtime, memory, hardware and ground-truth availability, and
returns each with a reason, required dataset, expected cost and a validation plan.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.research.methods import MethodRegistry

# research goal -> (preferred method ids, needs_ground_truth, needs_references, one-line rationale)
GOALS: dict[str, dict] = {
    "Understand Provenance": {"methods": ["Method 02", "Method 01", "Method 00"], "gt": False, "refs": False,
                              "why": "Provenance lives in C2PA and metadata, not in pixels; characterise those layers first."},
    "Find Fingerprint": {"methods": ["Method 03", "Method 13", "Method 15", "Method 18", "Method 25"], "gt": False,
                         "refs": True, "why": "Residual, spectral and Benford cues plus cross-image consensus are the "
                         "learning-free fingerprint descriptors; cross-image needs several images from one source."},
    "Study Diffusion Trace": {"methods": ["Method 11", "Method 55", "Method 13", "Method 16"], "gt": False, "refs": False,
                              "why": "Without a diffusion model (DIRE/AEROBLADE UNAVAILABLE), use Synthbuster-style "
                              "spectral lattice features, a training-free reconstruction error map and the spectral tail."},
    "Study Spectral Trace": {"methods": ["Method 13", "Method 14", "Method 15", "Method 16", "Method 17"], "gt": False,
                             "refs": False, "why": "FFT/DCT/DWT, the spectral tail and the high-frequency residual cover "
                             "the spectral family across representations."},
    "Study Watermark": {"methods": ["Method 39", "Method 34", "Method 63"], "gt": True, "refs": False,
                        "why": "Watermark questions are answered on a controlled surrogate with known ground truth: "
                        "robustness persistence, separation recovery and the provenance-energy landscape."},
    "Compare Images": {"methods": ["Method 25", "Method 30", "Method 04"], "gt": False, "refs": True,
                      "why": "Cross-image consensus and feature-space attribution compare images; both need references."},
    "Run Controlled Experiment": {"methods": ["Method 34", "Method 35", "Method 37", "Method 39", "Method 52"], "gt": True,
                                   "refs": False, "why": "Embed a keyed surrogate signal, then run separation, robustness "
                                   "and automated discovery scored against ground truth."},
}


@dataclass
class Recommendation:
    method_id: str
    name: str
    availability: str
    reason: str
    required_data: str
    compute_cost: str
    controls: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Advice:
    goal: str
    rationale: str
    recommendations: list = field(default_factory=list)
    alternatives: list = field(default_factory=list)
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"goal": self.goal, "rationale": self.rationale,
                "recommendations": [r.to_dict() for r in self.recommendations],
                "alternatives": [r.to_dict() for r in self.alternatives], "notes": self.notes}


class ResearchAssistant:
    def __init__(self, registry: MethodRegistry | None = None) -> None:
        self.registry = registry or MethodRegistry()

    def advise(self, goal: str, image_info: dict | None = None, has_ground_truth: bool = False,
               n_references: int = 0, engines: dict | None = None) -> Advice:
        info = image_info or {}
        spec = GOALS.get(goal)
        if spec is None:
            return Advice(goal, "Unknown goal.", notes=[f"Known goals: {', '.join(GOALS)}"])
        recs, alts, notes = [], [], []
        if spec["gt"] and not has_ground_truth:
            notes.append("This goal is answered on a CONTROLLED SURROGATE. Embed a keyed signal (Surrogate Ground Truth "
                         "tab) so results can be scored against ground truth.")
        if spec["refs"] and n_references < 3:
            notes.append("Cross-image / attribution methods need several images from the same suspected source "
                         "(add reference images).")
        fmt = str(info.get("format", "")).upper()
        if fmt and fmt != "JPEG":
            notes.append(f"Input is {fmt}: JPEG-specific cues (quantisation tables, Benford on quantised coefficients) "
                         "are analytical only, not read from a JPEG bitstream.")
        w, h = info.get("width", 0), info.get("height", 0)
        if w and h and w * h > 24_000_000:
            notes.append(f"{w}x{h} is large: analysis tiles automatically; expect higher runtime and memory.")
        for mid in spec["methods"]:
            try:
                m = self.registry.get(mid)
            except KeyError:
                continue
            rec = Recommendation(m.method_id, m.name, m.availability, m.scientific_basis,
                                 self._required_data(m), m.compute_cost,
                                 "real-image and other-generator controls" if spec["gt"] else "a control image")
            (recs if m.runnable else alts).append(rec)
        rationale = spec["why"]
        if not recs:
            rationale += " (All preferred methods are UNAVAILABLE on this machine; see alternatives.)"
        return Advice(goal, rationale, recs, alts, notes)

    def _required_data(self, m) -> str:
        bits = []
        if m.requires_reference_images:
            bits.append("reference images")
        if m.requires_ground_truth:
            bits.append("a controlled surrogate (ground truth)")
        if m.requires_model:
            bits.append("a deep-learning runtime + weights (not bundled)")
        return ", ".join(bits) or "a single image"

    def discover(self, image_info: dict | None = None, has_ground_truth: bool = False, n_references: int = 0,
                 max_results: int = 6) -> list[dict]:
        """Rank candidate experiments by a simple expected-value heuristic given what is available."""
        out = []
        for m in self.registry.ready():
            if m.requires_ground_truth and not has_ground_truth:
                continue
            if m.requires_reference_images and n_references < 3:
                continue
            value = {"FOUNDATIONAL": 2, "ESTABLISHED": 3, "ADAPTED": 3, "EXPERIMENTAL": 2, "HYPOTHETICAL": 1}[m.maturity]
            cost = {"negligible": 0, "low": 1, "medium": 2, "high": 3}.get(m.compute_cost, 1)
            if m.can("CAN_VALIDATE"):
                value += 1  # a method with ground-truth scoring is worth more
            score = value - 0.3 * cost
            out.append({"method_id": m.method_id, "name": m.name, "score": round(score, 2),
                        "reason": f"{m.maturity} {m.category}; " + ("validates against ground truth" if
                                  m.can("CAN_VALIDATE") else "descriptive"),
                        "required_dataset": self._required_data(m), "expected_cost": m.compute_cost,
                        "validation_plan": ("score the recovered candidate against the known surrogate signal; replicate "
                                            "across seeds" if m.can("CAN_VALIDATE") else
                                            "compare against a real-image control; report descriptive statistics only")})
        out.sort(key=lambda r: -r["score"])
        return out[:max_results]
