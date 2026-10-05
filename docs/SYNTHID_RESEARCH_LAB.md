# SynthID Research Lab

Navigation: **SynthID Research Lab**. The header reads *SynthID Research Lab · Local / Online Verification*.

## Scope

The lab measures and documents the SynthID embedded-signal layer, and only through legitimate verifiers:

| Method | ID | Status on a default install |
|--------|----|------------------------------|
| BASELINE: metadata, C2PA, pixel integrity, hashing (no SynthID measurement) | SID-M0 | RESEARCH, validated by the test suite |
| SUPPORTED DETECTION: local engine through the `tools/synthid` contract | SID-M1 | UNAVAILABLE (no engine) |
| OFFICIAL ONLINE VERIFICATION: Google pathways, user-operated | SID-ON1 | AUTHORITATIVE external service, result user-recorded |

The research brief also lists experimental fingerprint, multi-scale residual, robust PCA, patch consensus,
cross-image, ensemble, surrogate red-team and reconstruction methods. These are **not implemented**, by design: they
estimate, reconstruct or attack embedded watermark signals. That is outside the project's research ethics
(`docs/RESEARCH_METHOD.md`): no pixel-watermark removal, no adversarial perturbation, no search for detector-defeating
settings. Wavelet, FFT and DCT are not SynthID methods. Descriptive frequency statistics stay in the Forensic
Inspector, labelled descriptive only. All of these methods appear in the registry as `UNAVAILABLE / NOT IMPLEMENTED`,
so the scope is visible in the UI and in exported records.

## Tabs

- **Detection**: runs SID-M1 on the current image (the experiment's preserved original) or on chosen files. Each input
  is copied into the run's `source/` folder, the engine runs on the copy, and the original is hashed before and after.
  The result is `original_unchanged` and is shown in the UI.
- **Local Methods**: the method registry with method id, name, source, version, license, local/online, GPU, training,
  reference-image and dataset requirements, input formats, output, scientific status and validation status.
- **Research Sources**: the validated offline catalogue (`config/synthid_sources.json`, plus an optional
  `<workspace>/synthid_sources.json`). See `docs/SYNTHID_RESEARCH_SOURCES.md`.
- **Benchmark**: evaluates SID-M1 on a dataset you label yourself (see below).
- **Comparison**: SynthID before and after for each transformation of the current experiment. These are TRANSFORMATION
  EXPERIMENT observations, never removal claims.
- **Online Verification**: the user-controlled hand-off to official verifiers (see below).
- **Experiments**: SPX-SID runs, the SYNTHID RESEARCH MATRIX, and EXPORT FOR PAPER.

## Verification states

DETECTED, NOT DETECTED, POSSIBLY DETECTED, UNKNOWN and UNAVAILABLE. INVALID means the engine returned an error or
unreadable output, or modified its input. A verification record stores the detector and its version, the model
version, the state, the source, the UTC timestamp, the image SHA-256 and BLAKE3, the confidence, the score and its
basis, and the runtime.

Engine contract additions (see `tools/README.md`): `"state": "POSSIBLY_DETECTED"`, plus optional `"model_version"` and
`"score"` (watermark likelihood 0-1, used for ROC/AUC). Without `score`, ROC uses the ordinal state (DETECTED 1,
POSSIBLY 0.5, NOT 0). The basis is recorded.

## Benchmark protocol

```
<dataset>/positive/...                 images expected to carry the signal (your ground truth)
<dataset>/negative/real_controls/...   real photographs
<dataset>/negative/other_generator/... images from other generators
<dataset>/manifest.csv                 optional: path,label,group,split (label 1/0; paths must stay inside <dataset>)
```

A fixed detector is not trained here, so every item counts as a held-out evaluation item. Items the engine cannot
score (UNKNOWN, INVALID, UNAVAILABLE) are excluded from ROC and reported as abstentions. The reported metrics are:

- **AUC**: Mann-Whitney U with average ranks for ties, plus a stratified bootstrap 95% CI (seeded, 1000 resamples).
- **At a threshold**: TPR, FPR, precision, recall, F1 and accuracy, each proportion with a Wilson 95% CI.
- **ROC points** and **per-group TPR/FPR**, so real-image controls and other-generator controls are separated.

Public datasets (GenImage, Synthbuster, CNNDetection) contain no SynthID images. They work only as controls.

## Online verification (OFF by default)

1. LOCAL MODE is the default. There are no network calls, telemetry, uploads or background requests, and the
   LOCAL-ONLY guard stays installed.
2. Choosing **ONLINE OFFICIAL VERIFICATION** asks for confirmation and lasts for the session only.
3. **OPEN IMAGE IN OFFICIAL VERIFIER** first shows the exact destination URL, the file path and its SHA-256, then asks
   again.
4. After confirmation, Windows opens the allow-listed https destination in the default browser and shows the file's
   folder. SynthProvenance does not upload anything. Any upload is the researcher's manual action under the service's
   own sign-in, terms, quotas and access controls. No undocumented endpoints are used, and CAPTCHA, authentication,
   waitlists and rate limits are never bypassed.
5. The researcher records the reported result. It is stored as an ONLINE run (`SPX-SID-...`) and as an EXTERNAL SYNTHID
   VERIFICATION entry (user-recorded, unverified) in the experiment.

Allow-listed destinations are `https://gemini.google.com/`, `https://support.google.com/gemini/answer/16722517` and
`https://deepmind.google/models/synthid/`. In scripted (`--smoke-gui`) runs, confirmations are always refused.

## Runs and reproducibility

Run id: `SPX-SID-YYYYMMDD-NNNNNN` (per-day sequence). Each run is stored in
`<workspace>/synthid_research/<RUN_ID>/` with this layout:

- `run.json`
- `source/`
- `output/`
- `metrics/`
- `config/parameters.json`
- `logs/run.log`

`run.json` records:

- method, pipeline, parameters, seed and device
- source repository, source version and license
- model version and model hash
- input hashes (SHA-256 and BLAKE3), output hashes, resolution
- software version, OS, CPU, GPU and CUDA version (local `nvidia-smi` probe, if present), library versions
- timestamp, runtime, process memory before and after
- metrics, status, `original_unchanged` and limitations

## Export for paper

EXPORT FOR PAPER writes CSV (the matrix, plus metrics and ROC for benchmarks), JSON, PDF and PNG (summary, with ROC
when available). It then builds a ZIP with this layout:

```
experiment/run.json  source/  output/  metrics/  config/  logs/  report/
experiment/hashes_sha256.txt   experiment/hashes_blake3.txt   experiment/README.txt
```

The brief's `signal/`, `residual/` and `maps/` folders are not produced, because no signal estimation is performed.
LPIPS is reported as `NOT COMPUTED`, because no learned perceptual model is bundled.

## Result language

- For a real provenance change: "Observable provenance state changed under the tested transformation."
- SynthProvenance never writes that an image "is now non-AI", that detection "was defeated", or that SynthID "was
  removed". A NOT DETECTED result does not establish that an image is human-created.
