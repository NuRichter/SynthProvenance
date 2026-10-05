# Fingerprint Evidence Model

SynthProvenance maps every observed feature to the fingerprint ontology of
`data/source/AI_Generative_Image_Fingerprints_Taxonomy_APA.txt`. The taxonomy warns that
**fingerprint, artifact, trace, signature, cue, watermark, provenance and detector representation
are not the same category**, and the evidence model preserves that distinction. The seven families
are kept separate and never merged:

| Family | What it is | Example local method |
|---|---|---|
| `INTRINSIC` | traces that arise naturally from a generator (architecture, upsampling, decoder) | Method 03 Residual Fingerprint |
| `CAUSAL` | fingerprints formulated through a provenance -> trace causal relation | (models UNAVAILABLE; studied conceptually) |
| `SPECTRAL` | frequency-domain cues (FFT / DCT / DWT, periodic peaks, spectral tail) | Method 13 FFT, Method 15 DWT, Method 18 Benford-DCT |
| `PROACTIVE WATERMARK` | deliberately embedded signals (incl. the local keyed surrogate; SynthID) | controlled surrogate study; local SynthID engine |
| `DETECTOR REPRESENTATION` | features/embeddings used by a detector (CLIP / ViT / DINO) | UNAVAILABLE (no bundled model) |
| `RECONSTRUCTION` | reconstruction-error cues | Method 55 Reconstruction Forensics (training-free prior; NOT DIRE/AEROBLADE) |
| `PROVENANCE` | signed provenance metadata (Content Credentials) | Method 02 C2PA + metadata |

## Evidence records

The **Evidence Mapper** turns each observed feature into a record:

```
Evidence ID         EVIDENCE-001, EVIDENCE-002, ...
Fingerprint Family  one of the seven families above
Representation      FFT / DWT / residual / C2PA / image prior / ...
Method              the SynthProvenance method that produced it
Observation         the measured readout (descriptive)
Source Reference    the literature / taxonomy reference
Confidence          qualitative (weak / moderate / strong) -- never a probability
Ground Truth        the ground-truth level of the study
Validation Status   OBSERVED / DESCRIPTIVE / VALIDATED (surrogate) / NOT IMPLEMENTED
```

## Direction vs conclusion

Each evidence **dimension** carries a *direction*:

- `LEANS SYNTHETIC` / `LEANS AUTHENTIC` — a cue in that direction (for example a camera C2PA
  manifest with a matching hard binding leans authentic; a metadata AI-tool declaration leans
  synthetic). A lean is **never** a conclusion.
- `DESCRIPTIVE` — measured, but it does not by itself favour an origin (most spectral/residual
  cues on a single image).
- `NOT EVALUATED` — the method is unavailable in this build (learned detectors) or needs data not
  present (reference images, a controlled surrogate).

The only decisive dimension is a **controlled surrogate** with known ground truth, and it concerns
the keyed laboratory signal, not the real image's origin. This is why a single image almost always
yields `INSUFFICIENT EVIDENCE` against an external label: the honest scientific position is that
descriptive pixel cues do not, on their own, establish origin.

## Honesty rules (enforced in code and tests)

- A method that needs trained weights is `UNAVAILABLE`, never faked.
- Detector-evasion optimisation is `NOT_IMPLEMENTED` by design.
- `SynthID` is only reported from a real local verification engine; it is never inferred from
  metadata and a surrogate is never presented as SynthID.
- The independent-evidence scorecard is never collapsed into one score.
