"""Generate docs/IMPLEMENTATION_GAP_ANALYSIS.md from the live method registry and taxonomy.

The table is derived from what each method's capability flags actually provide (never from
the fact that a name appears in the registry), so the status is evidence-based:

    FULLY IMPLEMENTED   analysis + estimation + separation + reconstruction + validation
    PARTIALLY IMPLEMENTED  separation or reconstruction present, but not the full set
    ANALYSIS ONLY       analyzes, no estimation/separation/reconstruction
    DETECTOR ONLY       estimates a candidate but does not separate/reconstruct
    RESEARCH ONLY       runs but validates only on controlled ground truth (hypothesis/frontier)
    UNAVAILABLE         needs a DL runtime/weights not bundled
    NOT IMPLEMENTED     deliberately out of scope (detector-evasion)

Run: python scripts/build_gap_analysis.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import __version__  # noqa: E402
from app.research.methods import METHODS  # noqa: E402

# taxonomy family -> engine modules / methods that operationalise it (v4 Section 2 bridge)
FAMILY_MAP = [
    ("A INTRINSIC / PASSIVE", "residuals, consensus, features (LID), rpca",
     "Methods 03-05, 12, 17, 19-25 (residual estimation, PRNU-style cross-image consensus, handcrafted descriptors)"),
    ("B CAUSAL", "hypotheses, frontier (null-space)",
     "Methods 31-33 UNAVAILABLE (need trained models); 47, 57 study causal directions on controlled data"),
    ("C SPECTRAL", "spectral, dct, wavelet, residuals",
     "Methods 11, 13-18 (FFT/DCT/DWT, spectral tail, high-frequency residual, Benford-DCT)"),
    ("D PROACTIVE / WATERMARK", "surrogate, robustness, separation",
     "Methods 34-42, 63 (controlled surrogate ground truth: detection, separation, robustness, energy landscape)"),
    ("E DETECTOR REPRESENTATION", "features",
     "Methods 26-29 UNAVAILABLE (CLIP/ViT/DINO need weights); Method 30 handcrafted feature-space attribution"),
    ("F RECONSTRUCTION", "frontier (reconstruction), separation",
     "Methods 09-10 UNAVAILABLE (diffusion/AE); Method 55 training-free self-supervised reconstruction error"),
    ("G C2PA PROVENANCE", "app/core provenance + analyzers (native)",
     "Methods 01-02 (metadata and C2PA manifest analysis)"),
]


def status(m) -> str:
    if m.availability == "NOT_IMPLEMENTED":
        return "NOT IMPLEMENTED"
    if m.availability == "UNAVAILABLE":
        return "UNAVAILABLE"
    f = m.capability_flags()
    if f["CAN_SEPARATE"] and f["CAN_RECONSTRUCT"] and f["CAN_VALIDATE"] and f["CAN_ESTIMATE"]:
        return "FULLY IMPLEMENTED"
    if f["CAN_SEPARATE"] or f["CAN_RECONSTRUCT"]:
        return "PARTIALLY IMPLEMENTED"
    if m.maturity == "HYPOTHETICAL":
        return "RESEARCH ONLY"
    if f["CAN_ESTIMATE"]:
        return "DETECTOR ONLY"
    return "ANALYSIS ONLY"


def yn(b: bool) -> str:
    return "Y" if b else "-"


def main() -> int:
    lines = [f"# Implementation Gap Analysis", "",
             f"Generated from the live method registry of SynthProvenance {__version__} "
             f"(`python scripts/build_gap_analysis.py`). Status is derived from each method's declared capability flags, "
             f"not from the mere presence of a name in the registry.", "",
             "## Taxonomy → engine → experiment bridge", "",
             "| Taxonomy family | Engine modules | Methods / status |",
             "|---|---|---|"]
    for fam, mods, meth in FAMILY_MAP:
        lines.append(f"| {fam} | {mods} | {meth} |")
    counts: dict[str, int] = {}
    rows = []
    for m in METHODS:
        f = m.capability_flags()
        st = status(m)
        counts[st] = counts.get(st, 0) + 1
        rows.append(f"| {m.method_id} | {m.name} | {m.category} | {yn(f['CAN_ANALYZE'])} | {yn(f['CAN_ESTIMATE'])} | "
                    f"{yn(f['CAN_SEPARATE'])} | {yn(f['CAN_RECONSTRUCT'])} | {yn(f['CAN_VALIDATE'])} | "
                    f"{m.requires_ground_truth and 'Y' or '-'} | {st} | {m.source_reference} |")
    lines += ["", "## Per-method traceability", "",
              "Columns: Analysis / Estimate / Separate / Reconstruct / Validate (capability flags), GT = needs ground "
              "truth.", "",
              "| Method | Name | Family | A | E | S | R | V | GT | Status | Evidence |",
              "|---|---|---|---|---|---|---|---|---|---|---|"] + rows
    lines += ["", "## Summary", ""]
    for st in ("FULLY IMPLEMENTED", "PARTIALLY IMPLEMENTED", "DETECTOR ONLY", "ANALYSIS ONLY", "RESEARCH ONLY",
               "UNAVAILABLE", "NOT IMPLEMENTED"):
        lines.append(f"- {st}: {counts.get(st, 0)}")
    lines += ["", f"Total methods: {len(METHODS)}.", "",
              "Notes: FULLY IMPLEMENTED methods are the controlled-surrogate separation studies, where separation and "
              "reconstruction are scored against known ground truth. Descriptive spectral/residual/statistical methods "
              "are ANALYSIS ONLY by design (they characterise, they do not separate). UNAVAILABLE methods need a "
              "deep-learning runtime and trained weights that are not bundled. NOT IMPLEMENTED methods (detector "
              "evasion) are out of scope by design. No method is marked implemented merely because it is registered."]
    out = ROOT / "docs" / "IMPLEMENTATION_GAP_ANALYSIS.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({len(METHODS)} methods)")
    for st, n in sorted(counts.items()):
        print(f"  {st}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
