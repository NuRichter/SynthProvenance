# TruthScan Research (external detector integration)

TruthScan is an external, commercial AI-image / deepfake detector. SynthProvenance treats it as an
**external detector** to study, not as ground truth, and integrates with it **only** in ways that
keep SynthProvenance local-first and respect the service's terms.

## What SynthProvenance does NOT do

- It does **not** upload images to TruthScan or call its API from the application process.
- It does **not** bypass authentication, circumvent rate limits, reverse-engineer private APIs, or
  exploit vulnerabilities.
- It does **not** automate repeated submissions, and it does **not** search for transformations whose
  goal is to lower a TruthScan score. Detector-evasion optimisation is out of scope by design (the
  surrogate-evasion methods remain `NOT_IMPLEMENTED`; see [`RESEARCH_SCOPE.md`](RESEARCH_SCOPE.md)).
- It never claims that a controlled-surrogate result transfers to TruthScan.

## Two supported paths

**1. Import (default, fully local).** The researcher obtains a TruthScan result themselves and
imports it into the Cross-Detector Lab: paste the JSON, load a saved `.json`, or type the final
label / confidence / detection step. The result is stored as `SOURCE = EXTERNAL / USER-SUPPLIED`
with its submission id, timestamp and file hash when present. This is the path to use for
reproducible research.

**2. Optional browser hand-off (OFF by default, consent-gated).** Like the SynthID online hand-off,
SynthProvenance can open `https://truthscan.com/ai-image-detector` in the browser and reveal the
file in Explorer, after explicit per-session confirmation and an explicit per-open consent. The
researcher uploads the file manually, under TruthScan's sign-in and terms, and imports the result
back. SynthProvenance itself never uploads (`uploaded_by_synthprovenance: false`). The destination
host is allow-listed and must be `https`. Enable it under Settings (`truthscan_integration`, OFF by
default) or on the External Result tab.

## Imported result fields

The importer parses the documented shape tolerantly, under several common key spellings, and keeps
the whole blob verbatim under `raw`:

| Field | Meaning |
|---|---|
| `final_result` / label | the detector's final label (mapped to a direction: leans synthetic / authentic / descriptive) |
| `confidence` | normalised to `[0, 1]` (accepts `0.97`, `97`, `"97%"`, `"high"`) |
| `detection_step` | `1` = metadata only, `2` = metadata + OCR/watermark, `3` = metadata + OCR/watermark + ML model |
| metadata / OCR-watermark / ML state | per-stage states |
| `warnings` | detector warnings |
| heatmap reference | optional heatmap image (compared spatially with local maps; overlap is not correctness) |
| submission id / timestamp / file hash | provenance of the external result |

> The exact TruthScan API response schema is not published in a machine-readable form that we could
> verify at build time, so these field names **must be re-verified against TruthScan's current
> official documentation** before relying on an automated import. The documented detection flow
> (obtain a presigned upload URL, upload, submit for detection) and the `detection_step` values
> (1/2/3) are stated by TruthScan's documentation and used here for the import mapping only.

**Sources (accessed October 2026):** TruthScan official documentation;
[composio.dev/toolkits/truthscan](https://composio.dev/toolkits/truthscan),
[docs.composio.dev/toolkits/truthscan](https://docs.composio.dev/toolkits/truthscan).

## Bundled research archive

A researcher-supplied Markdown archive (`TruthScan Archives/…`) documents TruthScan's pipeline and is imported as
**methodological context only** (reference-only; `direction = UNKNOWN`), never as a per-image score (v6 Section 36).
Documented facts it confirms about the response shape — `final_result`, `detection_step` (1/2/3; a watermark hit at
step 2 short-circuits and returns a generator name), `ocr`, hidden `synthid`, `ml_model`, `warnings`, a JET heatmap,
and an **asynchronous LLM** that writes the explanation — match this importer's fields. The archive marks model
architecture, weights, training data and thresholds as undisclosed and notes the 99%+ claim is not independently
validated. See `docs/RESEARCH_SOURCES_V6.md` for the full FACT / INFERENCE / UNKNOWN breakdown.

