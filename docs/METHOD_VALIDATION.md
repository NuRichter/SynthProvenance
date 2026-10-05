# Method Validation

How a method's status and capabilities are established, and what "validated" means here.

## Capability flags

Each method in `app/research/methods.py` declares, through a single source of truth (`_CAP_FLAGS`), which of the five
verbs it provides: `CAN_ANALYZE`, `CAN_ESTIMATE`, `CAN_SEPARATE`, `CAN_RECONSTRUCT`, `CAN_VALIDATE`. The UI and the
Unified Signal Decomposition Engine use these flags, so a detector can never be presented or used as a separator.
`validate()` enforces that `CAN_SEPARATE` is granted only to `sep:` capabilities and that no non-READY method
advertises a capability.

## Availability

- **READY** — runs locally now with numpy/Pillow; validated by the test suite.
- **UNAVAILABLE** — needs a deep-learning runtime and trained weights that are not bundled (e.g. DIRE, AEROBLADE,
  CLIP/ViT/DINO, DNA-Det). The reason is shown in the method card. Nothing is downloaded or faked.
- **NOT_IMPLEMENTED** — out of scope by design (detector-evasion, Methods 43–46). The reason is shown.

## Maturity

`FOUNDATIONAL` / `ESTABLISHED` / `ADAPTED` / `EXPERIMENTAL` / `HYPOTHETICAL`. A numpy re-implementation of a published
idea is labelled `ADAPTED` and never presented as the authors' validated detector. Frontier methods start
`HYPOTHETICAL` and only move to a stronger claim after reproducible controlled experiments.

## Evidence of correctness (test suite)

- Wavelet and block-DCT transforms are checked for **perfect reconstruction** (round-trip error < 1e-8/1e-9).
- The FFT engine is checked to **detect a known periodic peak**.
- The surrogate detector is checked to **detect its own signal, reject the clean image and reject a wrong key**, and
  its **null distribution is calibrated** (mean ≈ 0, sd ≈ 1, no false positive over 200 random keys at the threshold).
- Separation methods are checked to **recover the known signal** (candidate-vs-known correlation) with reconstruction
  fidelity above a floor.
- Cross-image consensus is checked to **separate a shared embedded signal from unrelated images** (held-out minus
  control).
- The 64-method registry is validated for honesty; the runner is checked to run **every READY method without error**
  and to return UNAVAILABLE / NOT IMPLEMENTED otherwise.
- The lab run store is checked to **preserve the original** (re-hash) and to **export a paper ZIP** with verified
  hashes.

## What "validated" does not mean

A READY/validated status means the method runs correctly and, where it has ground truth, recovers a *known* surrogate
signal. It does **not** claim the method detects real AI generation, attributes a real generator, or generalises to
unseen generators. Cross-generator generalisation requires researcher-supplied labelled data and is reported with
confidence intervals, never as "works everywhere".

See `docs/IMPLEMENTATION_GAP_ANALYSIS.md` for the per-method status table (regenerated from the live registry).
