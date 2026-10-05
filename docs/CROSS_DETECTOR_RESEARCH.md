# Cross-Detector Research

SynthProvenance is an **independent forensic system**. An external commercial AI-image detector
(for example TruthScan) is an **external detector** whose result is *evidence to study*, never
ground truth. The TruthScan Cross-Detector Lab (Expert Mode) compares an imported external result
with SynthProvenance's own local, descriptive evidence and reports where they agree, where they
disagree, and what remains unknown.

> One detector is an opinion. Multiple independent measurements create evidence.
> We do not guess. We measure. We challenge. We reproduce. We document.

## Workflow

```
IMAGE
 -> local baseline, C2PA, metadata, fingerprint taxonomy, SynthProvenance analysis   (local, automatic)
 -> OPTIONAL user-controlled TruthScan result                                         (imported, user-supplied)
 -> cross-detector comparison -> disagreement analysis -> research report
```

1. Open an image (Expert Mode).
2. On **External Result**, import the detector's JSON result, load a saved `.json`, or type the
   final label / confidence / detection step by hand. The result is tagged
   `SOURCE = EXTERNAL / USER-SUPPLIED`.
3. Choose the **ground-truth level** (see below) and, if known, the ground-truth direction.
4. Press **RUN CROSS-DETECTOR STUDY**. SynthProvenance runs its full local pipeline, distils
   independent evidence, and compares.
5. Read **Agreement** and **Disagreement**, optionally compare an imported heatmap, and **Export**
   the Cross-Detector Research Report (HTML / PDF / JSON / CSV).

## What SynthProvenance does and does not conclude

SynthProvenance never emits an "AI vs human" verdict from pixels. Its local evidence is
**descriptive**: a dimension may *lean* a direction (a verified camera C2PA manifest, or an
AI-tool declaration in metadata), but most dimensions stay `DESCRIPTIVE`. The comparison therefore
has four outcomes:

| Outcome | Meaning |
|---|---|
| `AGREEMENT` | the independent evidence leans the same direction as the external label |
| `PARTIAL AGREEMENT` | some dimensions are consistent, some are not |
| `DISAGREEMENT` | at least one independent dimension is inconsistent with the external label |
| `INSUFFICIENT EVIDENCE` | the local evidence is descriptive and does not confirm or refute the label |

The comparison **never** declares the external detector "wrong" or SynthProvenance "correct". The
only statements allowed to say "matches / does not match" require a ground-truth level of 3 or more,
and they describe the **external label versus the known ground truth**, never a judgement of a system.

## Ground-truth hierarchy

Every study records its ground-truth level. Only LEVEL 3 and above are decisive.

| Level | Meaning |
|---|---|
| 0 | Unknown origin |
| 1 | Observer-reported origin (unverified) |
| 2 | Known generator + known source dataset |
| 3 | Locally generated controlled sample |
| 4 | Known watermark / fingerprint ground truth |
| 5 | Reproducible synthetic benchmark |

## Evidence model and the ten research questions

Local evidence is mapped to the seven fingerprint families of the taxonomy (see
[`FINGERPRINT_EVIDENCE_MODEL.md`](FINGERPRINT_EVIDENCE_MODEL.md)), which are kept distinct:
`INTRINSIC`, `CAUSAL`, `SPECTRAL`, `PROACTIVE WATERMARK`, `DETECTOR REPRESENTATION`,
`RECONSTRUCTION`, `PROVENANCE`. The **Independent Evidence Scorecard** shows each dimension
separately and, by design, is **never** combined into a single "truth score". The lab is built to
investigate: where the systems agree and disagree; which evidence categories correlate with each
decision; whether metadata, OCR/watermark, spectral, reconstruction and learned cues are mutually
consistent; how stable classifications are under normal transformations; which signals are
persistent or representation-specific; which claims survive independent replication; which apparent
"fingerprints" are actually content artefacts; and whether a controlled surrogate reproduces the
behaviour.

## Hard-case benchmark and matrix

The lab can generate a local, reproducible **hard-case benchmark** with known ground truth
(`app/research/hardcases.py`): synthetic images, a synthetic image carrying a known keyed surrogate
watermark, edited and upscaled variants, and a *natural-like control* that imitates camera capture
and is clearly labelled as **not a real photograph**. Studies export to the **cross-detector
benchmark matrix** (CSV): `IMAGE, GROUND TRUTH, TRUTHSCAN, SYNTHPROVENANCE, C2PA, METADATA,
SPECTRAL, RECONSTRUCTION, FINGERPRINT, FINAL RESEARCH STATUS`.

## Reproducibility and run store

Each study is an auditable run `SPX-XD-YYYYMMDD-NNNNNN` under
`<workspace>/cross_detector/<ID>/` with `run.json` (external result, local evidence, comparison,
scorecard, heatmap, benchmark row, environment), copied inputs, and the report. The original image
is hashed before and after and reported as `original_unchanged`.

## Local-only

SynthProvenance does not upload the image and does not call any external API. See
[`TRUTHSCAN_RESEARCH.md`](TRUTHSCAN_RESEARCH.md) for the import and the optional, consent-gated
browser hand-off.
