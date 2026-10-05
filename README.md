# SynthProvenance

**Scientific AI Content Signal & Image Provenance Laboratory**

*Separate the Signal. Preserve the Pixel. Study the Provenance.*  WE DO NOT GUESS. WE MEASURE.

Faculty of Computer Science · Insyide Innovations Lab · NuRichter Workspace
PRIVATE SCIENTIFIC RESEARCH SOFTWARE · LOCAL RESEARCH ENVIRONMENT

## WINDOWS QUICK START

1. Extract `SynthProvenance.zip` to a writable folder with a short path, for example `C:\Research\SynthProvenance`.
2. Double-click `build.bat`.
3. Wait for `BUILD SUCCESSFUL`. The first build downloads the pinned Python packages from PyPI and takes several minutes.
4. Run `dist\SynthProvenance\SynthProvenance.exe`.

Requirements: 64-bit Windows 10 or 11, about 3 GB free disk space, internet access for the first build only, and a 64-bit
Python 3.11 to 3.14 (3.12 recommended). If no suitable Python is found, `build.bat` offers to download the official Python
Software Foundation package from nuget.org into `runtime\python`. It asks first and verifies the Authenticode signature
before use. Declining is always possible. You can install Python 3.12 from python.org instead.

## Project

SynthProvenance is a desktop research workstation that separates, measures and documents the layers through which an
image may carry information about its origin:

| Layer | What it is | How it is measured here |
|-------|-----------|-------------------------|
| C2PA | PROVENANCE / CONTENT CREDENTIAL LAYER | Native JUMBF/CBOR parse, hard-binding digest recomputation, optional c2patool / c2pa-python validation |
| SynthID | EMBEDDED SIGNAL LAYER (pixel values) | SynthID Research Lab: compatible local engine, or user-operated official online verification. Otherwise UNAVAILABLE |
| Ordinary metadata | EXIF, XMP, IPTC, ICC, PNG text, TIFF tags | Field-level parsing and diffing |
| Pixels | Decoded pixel array | Sample-exact comparison, MAE/MSE/PSNR/SSIM/histogram/dHash |
| Encoding | Codec and parameters | Container and codec parameter parsing |
| File structure | Segments and chunks | Byte-level container walk |
| External platforms | Labels shown by third parties | User-recorded only, never contacted |

## Scientific Motivation

Provenance signals behave differently under ordinary processing. Metadata is trivially lost, C2PA manifests break when
bytes change, and pixel-domain signals are designed to survive some transformations. Conclusions about any of these
layers need controlled, reproducible measurements rather than assumptions. SynthProvenance records every condition,
parameter, hash and metric so that an experiment can be repeated and audited.

## Research Scope

In scope: observation of C2PA manifests and hard bindings, AI-content provenance declarations (IPTC Digital Source Type,
AI System Used, structured generator records), SynthID state when a local engine exists, metadata behaviour, file
encoding, pixel integrity and controlled transformations.

Out of scope by design: detecting AI generation from pixels, removing or attacking pixel-domain watermarks, searching for
transformations that defeat detectors, and predicting how any platform will classify an image. See `docs/RESEARCH_METHOD.md`.

## Architecture

`app/core` (loading, hashing, containers, metadata, provenance, SynthID adapter, transformations, experiments, audit,
fingerprint lab run store), `app/analyzers` (EXIF, XMP, IPTC, PNG, JPEG, WebP, TIFF, C2PA, SynthID, compression,
statistics), `app/research` (the pure-numpy fingerprint research engine: taxonomy, library, imaging, spectral, wavelet,
dct, residuals, rpca, consensus, features, surrogate, procedural, robustness, separation, hypotheses, metrics, failure,
methods, runner), `app/services` (sanitizer, C2PA separation, SynthID and fingerprint paper export, provenance
comparison, transformation orchestration, reports, export), SynthID Research Lab engines in `app/core/synthid_*`,
`app/models`, `app/ui` (PySide6 views and widgets, splash, wizard), `app/utils`. Details: `docs/ARCHITECTURE.md`.

### Easy Mode and Expert Mode

SynthProvenance has two application shells over the same research engines. **Easy Mode** (default) is three steps:
**01 PILIH** (drop or choose an image, pick PNG / JPG / WEBP / TIFF / BMP, optional report location) ->
**02 RUN** (one RUN TRANSFORMATION button; `app/core/easy_mode_orchestrator.py` runs a fixed 12-stage pipeline:
safety, baseline hash, metadata, C2PA, local SynthID status, fingerprint analysis, signal estimation, controlled
surrogate separation, consensus, validation, output, report) -> **03 OUTPUT** (result image, pixel status, SAVE RESULT,
OPEN REPORT, RUN ANOTHER). The result image is a pixel-preserving re-encoding of the original; separation and
reconstruction run only on a locally embedded keyed surrogate with known ground truth and are reported, never applied
to the real image. **Expert Mode** is the full research console. Switch in Settings > APPLICATION MODE >
SAVE & RESTART (the application persists the mode, closes and relaunches). `--ui-mode easy|expert` overrides the mode
for one session.

### TruthScan Cross-Detector Research Lab

Expert Mode includes a comparative research instrument. SynthProvenance is an **independent forensic system**; an
external detector such as TruthScan is an **external detector** whose result is imported (user-supplied) and studied,
never trusted as ground truth and never fetched by the app. The lab compares the imported result with SynthProvenance's
own local, descriptive evidence across fingerprint families, reports `AGREEMENT` / `PARTIAL AGREEMENT` / `DISAGREEMENT`
/ `INSUFFICIENT EVIDENCE`, records the ground-truth level (0-5), shows an independent-evidence scorecard that is never
collapsed into a single "truth score", compares an imported heatmap with local maps, generates a labelled local
hard-case benchmark, and exports a Cross-Detector Research Report and benchmark CSV. It never declares either system
correct unless ground truth supports it, and TruthScan integration is OFF by default and never uploads an image (an
optional, consent-gated browser hand-off opens the site; the researcher uploads manually). See
`docs/CROSS_DETECTOR_RESEARCH.md`, `docs/TRUTHSCAN_RESEARCH.md`, `docs/FINGERPRINT_EVIDENCE_MODEL.md`.

## Fingerprint Research Lab

The **Fingerprint Research Lab** is a local, numpy-only forensic laboratory for generative-image fingerprint research
on decoded pixels. It exposes a plugin **method registry of 55 methods** (Method 00 – Method 54) across baseline,
metadata/provenance, intrinsic fingerprint, diffusion forensics, spectral, geometric/statistical, spatial/multi-scale,
representation, causal, controlled-surrogate, advanced-hypothesis and ensemble categories. Each method has a card
(purpose, how it works, inputs, ground-truth and compute needs, limitations, literature sources, validation status) and
an honest status: **READY** (runs now), **UNAVAILABLE** (needs a deep-learning runtime and trained weights that are not
bundled — nothing is faked or downloaded), or **NOT_IMPLEMENTED** (detector-evasion methods, out of scope by design).

Real engines included: an FFT engine (radial/angular spectra, band energy, spectral-tail power-law fit, periodic-peak
detection), a multi-level Haar/Daubechies wavelet engine with perfect reconstruction and sub-band statistics, block-DCT
and JPEG forensics with Benford first-digit statistics, a residual engine (Gaussian/Laplacian/high-pass/wavelet/DCT/
median/denoise), Robust PCA (`I = L + S + E`), patch/multi-scale/cross-region/cross-image consensus (with a held-out
split and a noise-template control), handcrafted descriptors and LID/multiLID.

A **controlled surrogate ground-truth laboratory** embeds a transparent, keyed watermark (spatial, pseudo-random, FFT,
DCT, wavelet, multi-scale, learned, multi-bit, hybrid; a neural family is marked UNAVAILABLE). Against this known signal
the lab runs **separation and reconstruction studies** (six panels: Original · Candidate Signal · Estimated Content ·
Residual · Reconstructed · Difference), a **robustness sweep** (WAVES-style persistence vs. severity under a fixed
battery of standard transformations), and explicit **research hypotheses** — each scored against ground truth and
reported as SUPPORTED / INCONCLUSIVE / NOT SUPPORTED *on this controlled case*, never as proof. This is not SynthID, does
not imitate SynthID internals, and SynthProvenance never searches for transformations that defeat a detector and never
attacks a real watermark. Every run gets an id `SPX-FP-YYYYMMDD-NNNNNN`, preserves the original (hashed before/after),
and **EXPORT FOR PAPER** writes CSV/JSON/PDF/PNG and a ZIP with SHA-256 and BLAKE3 manifests.

## Fingerprint Taxonomy and Research Library

The **Fingerprint Taxonomy** view browses a structured database (`data/fingerprint_taxonomy.json`, 572 entries, 21 APA
references) parsed from the supplied research file, keeping seven families distinct and quoting definitions with source
line numbers (`docs/FINGERPRINT_TAXONOMY.md`). The **Research Library** is a searchable, web-verified literature database
(`data/research_library.json`, 66 references: 21 from the taxonomy file plus validated external additions, each VERIFIED
or VERIFIED_WITH_CORRECTIONS) with APA 7, BibTeX and CITATION.cff export. The **About This Program** view carries the
**HERE OUR HERO** → Research Foundations panel, an ISO-5807-style research workflow, and an ISO/IEC 25010:2023 software
quality mapping (`docs/SOFTWARE_QUALITY.md`). A premium splash screen runs a real initialisation sequence and a Research
Wizard (7 steps) guides the workflow. No citation, DOI or result is fabricated.

## Installation

No installation is needed on the target machine after building. The `dist\SynthProvenance` folder is portable and can be
copied elsewhere. To run from source instead: create a virtual environment with Python 3.12, `pip install -r
requirements.txt`, then `python app/main.py`.

## Build

`build.bat` runs eight stages: [1/8] environment checks, [2/8] Python runtime and `.venv`, [3/8] pinned dependency
installation, [4/8] source validation (compile, import every module, tool detection, resources), [5/8] the full pytest
suite, [6/8] PyInstaller one-folder windowed build via `SynthProvenance.spec`, [7/8] executable verification, [8/8]
distribution preparation (assets, config, licenses, tools, workspace, BUILD_INFO.json, SHA256SUMS.txt).

Logs: `build\build.log`, `build\test.log`, `build\verification.log`. On failure the console shows the failed stage, the
reason, the log location and a remediation. `build.ps1` is an equivalent PowerShell entry point (`-SkipTests` available
for development only).

## Execution

`SynthProvenance.exe [image]` starts the GUI. `--self-test [--self-test-output file.json]` runs the headless pipeline
verification, including the SynthID Research Lab. `--smoke-gui` runs a scripted GUI experiment and exits. That
experiment includes a SynthID Research run and a paper export in LOCAL MODE, with checks that the original is untouched
and that no network attempt was made. `--version` prints the version.

Typical workflow: open or drop an image, press START EXPERIMENT (the original is copied into the experiment and never
modified), inspect the baseline, run transformations, review Signal Separation, Pixel Integrity, Comparison and the
Experiment Matrix, then export the report and `experiment.zip`.

## C2PA Research

The C2PA Provenance view shows manifests, claims, assertions, actions, ingredients, claim generator, signature algorithm,
certificate issuer and subject, timestamp token, hard binding and validity. Manifest data can be exported as JSON. The
C2PA / PROVENANCE DATA SEPARATION EXPERIMENT removes only the manifest store container, with the warning: "This
operation may invalidate provenance authenticity information. This mode is intended for controlled laboratory research."
Before and after are compared for presence, store hash, manifests, binding and the AI-content signal. The native parser
does not validate signatures. Validity is NOT VALIDATED and trust is UNKNOWN unless c2patool or c2pa-python is present.

## SynthID Research Lab

SynthID is treated as an EMBEDDED SIGNAL LAYER in pixel values, never as metadata. The **SynthID Research Lab** (header:
*SynthID Research Lab / Local / Online Verification*) offers two paths.

- **[LOCAL RESEARCH]**, the default. A compatible local engine (SID-M1, contract in `tools/README.md`) runs on a
  preserved copy, and the original is hashed before and after. Research as of 2026-10-02 found no validated local SynthID
  image detector and no public machine-readable verification API (`docs/SYNTHID_RESEARCH_SOURCES.md`). The default
  state is therefore `LOCAL SYNTHID ENGINE: UNAVAILABLE`, and nothing is inferred.
- **[ONLINE OFFICIAL VERIFICATION]**, OFF by default. It hands the image off to Google's official pathways (Gemini app;
  information on the SynthID Detector portal) in the browser, only after explicit confirmation that shows the exact
  destination. SynthProvenance never uploads anything. The researcher uploads manually and records the reported result
  as an unverified external entry.

The lab has seven tabs: Detection, Local Methods (the method registry with honest status), Research Sources (a validated
offline catalogue), Benchmark (AUC with bootstrap CI, ROC, TPR/FPR/precision/recall/F1 with Wilson CI, per-group control
rates on data you label yourself), Comparison, Online Verification and Experiments.

Every run gets an id `SPX-SID-YYYYMMDD-NNNNNN` with full reproducibility records, and appears in the SYNTHID RESEARCH
MATRIX. **EXPORT FOR PAPER** writes CSV, JSON, PDF, PNG and a ZIP with SHA-256 and BLAKE3 manifests. Results are never
fabricated, never inferred from metadata or C2PA, and removal is never claimed. Signal estimation, reconstruction and
watermark-attack methods are deliberately not implemented. See `docs/SYNTHID_RESEARCH_LAB.md`.

## Metadata Sanitization

Nine options (GPS, camera, device, author, timestamps, private XMP, private IPTC, software, nonessential application
metadata) and three profiles (CONSERVATIVE, BALANCED, MAXIMUM PRIVACY). The default METADATA-ONLY mode rewrites JPEG, PNG
and WebP containers at byte level and copies compressed image data verbatim, then verifies `changed_pixels == 0`.
Structure (orientation, ICC, JFIF, PNG rendering chunks) and rights notices are always preserved. The nonessential option
also removes C2PA stores and XMP provenance declarations and is labelled as such in the UI.

## Pixel Integrity

Canonical decode of frame 0 without orientation. Reported: resolution, pixel count, channels, MAE, MSE, maximum error,
changed pixel count and percentage, PSNR, SSIM (7x7), histogram difference and dHash distance. `PIXEL-EXACT ✓` appears
only when every sample is identical, the pixel representation is identical and the pixel SHA-256 digests match.
Dimension-preserving operations are checked automatically and flagged `DIMENSION CHANGE DETECTED` otherwise.

## Format Conversion

SAVE AS exports PNG, JPEG, WEBP, TIFF and BMP with explicit LOSSLESS or LOSSY mode, quality, ICC and metadata handling.
Each export is a recorded transformation measured against ORIGINAL. JPEG always shows "WARNING: JPEG encoding may alter
pixel values." The Format Conversion Lab runs chains such as `JPEG:LOSSY:90 > WEBP:LOSSY:90 > PNG:LOSSLESS` and records
format, mode, quality, hashes, resolution, pixel metrics, metadata and provenance changes for every step. The writer is a
capability table (`app/core/image_writer.py`) so new formats can be added. See `docs/FORMAT_HANDLING.md`.

## High-Resolution Support

There is no hard-coded resolution cap. A decode is admitted when its estimated working set fits into available RAM
(configurable fixed limit in Settings, 0 by default). Sources are never downscaled. Very large images are shown through a
reduced display pixmap, and the view states `SOURCE WxH | DISPLAY n% | preview 1/k (display only)`. Pixel coordinates
always refer to the source. Comparisons run in row strips to bound memory. The status bar shows process RAM, available
RAM, progress, elapsed time and the current operation.

## Local Processing

Default mode: LOCAL-ONLY. There are no cloud APIs, uploads, telemetry or remote storage. A runtime audit hook
blocks outbound network connections from Python code in the application and the self-test proves it. The SynthID Research
Lab's online verification is an explicit, per-session, consent-gated hand-off to the default browser. The application
itself sends nothing. The only network
use is the build itself (pip from PyPI, and the optional consented Python download). See `docs/LOCAL_PROCESSING.md`.

## Experiment Reproducibility

Experiment IDs look like `SPX-2026-0927-000001`. Each experiment stores timestamps, application version, OS, Python,
package versions, input and output hashes, full parameters, tool and engine versions, and an append-only audit log
(IMAGE LOADED, BASELINE FORENSIC ANALYSIS COMPLETE, C2PA ANALYSIS COMPLETE, SYNTHID ANALYSIS COMPLETE, METADATA ANALYSIS
COMPLETE, TRANSFORMATION STARTED / COMPLETE, PIXEL VERIFICATION COMPLETE, REPORT GENERATED and more).

## Reports

PDF, JSON, CSV, HTML and PNG summary, plus `experiment.zip` with `original/ output/ report/ metadata/ provenance/ synthid/
metrics/ logs/`, `experiment.json`, `metadata.json`, `provenance.json`, `synthid.json`, `metrics.json`, `hashes.txt`
(sha256sum format) and `audit.log`. Conclusions are cautious. The report never says an image is or is not AI-generated
and never predicts platform behaviour.

## Limitations

Signature and trust validation need c2patool or c2pa-python. SynthID is UNAVAILABLE without a local engine; official
online verification depends on Google's service access, quotas and scope (Google AI content only), and its results are
user-recorded. Pixel-domain
watermarks in general are not assessed. Byte-level inspection covers JPEG, PNG and WebP (TIFF, BMP and GIF use
decoder-level metadata and C2PA is reported UNKNOWN for them). Only frame 0 of animated images is compared. Forensic
statistics are descriptive only. The Windows build was designed for Windows 10/11 x64 but must be verified on the target
machine by running `build.bat`. Freshly built executables can be flagged by antivirus heuristics.

## Testing

`python -m pytest` runs the suite (image loading, writing and all five export formats, metadata parsing, sanitization with
`changed_pixels == 0`, C2PA parsing, tampering and separation, SynthID state handling with a fake local engine, hashing
vectors, pixel comparison, lossless preservation, 24 MP high-resolution loading, memory budget refusal, experiments,
audit logging, reports, bundle hashes, security, offscreen GUI and build-file validation). It also covers the SynthID
Research Lab: source discovery and validation, the method registry, local detector adapters with a contract-following
test engine, benchmark metrics with known values, held-out control groups, run serialization, paper-export hashes
(SHA-256 and BLAKE3), online-mode safeguards, absence of network requests in local mode, and the lab GUI.
`benchmarks/bench_pixel_integrity.py` measures throughput.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `No supported Python found` | Install 64-bit Python 3.12 from python.org, or accept the verified NuGet download |
| Stage 3 fails | pip needs https://pypi.org. Check proxy/firewall. Delete `.venv` and retry |
| Stage 5 fails | Open `build\test.log` for the failing test |
| Stage 6/7 fails with access errors | Close SynthProvenance.exe. Allow `dist\SynthProvenance` in antivirus and rebuild |
| Very long path errors | Extract nearer the drive root or enable Windows long paths |
| Image refused for memory | The message states needed vs available RAM. Close applications or use a larger machine |

## Ethical Research Notes

SynthProvenance measures and documents. It does not generate, forge or re-sign provenance, does not estimate,
reconstruct, remove or attack pixel-domain watermarks (SynthID included), and contains no search for transformations
that defeat detectors. Separation experiments exist to study how
provenance behaves, always on copies, with the original preserved and every step audited. Rights notices are never
removed. Do not use results to misrepresent the origin of media. See `docs/RESEARCH_METHOD.md`.
