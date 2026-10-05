# Research Scope

SynthProvenance is a local research instrument for the question:

> What observable fingerprints, traces, signatures, artifacts or watermark-like signals exist in generative images,
> where do they live across representations, how persistent are they, and can they be experimentally separated from
> visual content in a controlled ground-truth environment while quantitatively preserving fidelity?

## Categories kept distinct

The taxonomy (`data/source/AI_Generative_Image_Fingerprints_Taxonomy_APA.txt`) warns that *fingerprint, artifact,
trace, signature, cue, watermark* and *detector representation* are not interchangeable. SynthProvenance keeps them
separate everywhere:

- **Intrinsic / passive fingerprint** — natural generator traces (residual, PRNU-style, architecture/instance).
- **Causal fingerprint** — provenance → trace formulations with content/style decoupling.
- **Spectral fingerprint** — FFT/DCT/DWT energy, tails, periodic peaks.
- **Proactive / artificial watermark** — deliberately embedded signals (studied only via the controlled surrogate).
- **Detector representation** — CLIP/ViT/DINO/contrastive features; *not* an intrinsic fingerprint.
- **Reconstruction cue** — reconstruction-error signals (diffusion/AE need models → UNAVAILABLE; a training-free
  prior is provided).
- **C2PA provenance** — signed authenticity metadata; *not* an intrinsic image fingerprint.

## In scope

Descriptive forensic analysis on decoded pixels; C2PA/metadata observation; controlled-surrogate watermark studies
with known ground truth (detection, separation, reconstruction, robustness, hypothesis tests); pixel-integrity and
reproducibility; literature traceability.

## Out of scope by design

- Claiming an image is AI-generated or human-made from pixels.
- Attacking, removing or defeating real pixel-domain watermarks (SynthID included).
- Searching for transformations that reduce a watermark detector's score (Methods 43–46 are NOT IMPLEMENTED).
- Impersonating the official SynthID decoder or any proprietary system.
- Silent model downloads, telemetry, uploads or cloud inference.

## Real SynthID

There is no validated local SynthID image detector (see `docs/SYNTHID_RESEARCH_SOURCES.md`). SynthProvenance therefore
shows `LOCAL SYNTHID VERIFICATION: UNAVAILABLE` and offers an explicit, consent-gated hand-off to Google's official
online pathways. It never fabricates a SynthID result and never represents a generic residual/detector as the official
decoder.

## Controlled surrogate track

All watermark separation/robustness research runs against a transparent, keyed surrogate signal with known ground
truth (`app/research/surrogate.py`). This is clearly labelled SURROGATE RESEARCH and is not a proprietary
implementation.
