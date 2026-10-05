# Architecture

## Layers

```
app/main.py            entry point (GUI, --self-test, --smoke-gui, --version), stdio guard, network guard
app/ui/                PySide6 main window, 12 views, widgets, controller (QThreadPool workers)
app/services/          orchestration: sanitizer, C2PA separation, SynthID lab, provenance comparison,
                       transformation service, report service, export service
app/core/              engines: image_loader, image_memory, image_writer, hashing, containers, cbor, jumbf,
                       metadata_engine, provenance_engine, synthid_engine, transform_engine, pixel_integrity,
                       image_metrics, experiment_engine, audit_engine, synthetic (fixtures),
                       SynthID Research Lab: synthid_detector_registry, synthid_source_manager,
                       synthid_local_verifier, synthid_benchmark, synthid_online, synthid_research_engine
app/analyzers/         format analyzers: exif, xmp, iptc, png, jpeg, webp, tiff, c2pa, synthid, compression, statistics
app/models/            dataclasses: image_info, metrics, provenance, synthid, experiment, audit
app/utils/             paths, validation, serialization, logging, system (safe subprocess), memory, config, netguard
```

Dependencies point downward only: ui to services to core/analyzers to models/utils.

## Data flow

1. `metadata_engine.analyze_bytes` sniffs magic bytes, decodes pixels under the memory budget, walks the container,
   extracts EXIF/XMP/IPTC/ICC, parses C2PA, aggregates software identifiers, computes hashes and the AI-content
   signal (`provenance_engine.compute_signal`). Result: `Analysis` plus a JSON-safe dict.
2. `experiment_engine.Workspace.create` allocates `SPX-YYYY-MMDD-NNNNNN`, copies the original byte-for-byte and stores
   the baseline.
3. `TransformationService.run` executes one operation, writes the output atomically, re-analyses it, compares pixels,
   diffs metadata, compares provenance, runs the SynthID adapter and builds the seven-layer separation record.
4. `report_service` renders one section model to JSON, CSV, HTML, PDF and PNG. `export_service` writes the bundle with a
   SHA-256 manifest.
5. SynthID Research Lab: `synthid_research_engine.ResearchStore` allocates `SPX-SID-YYYYMMDD-NNNNNN` runs under
   `<workspace>/synthid_research/`.
   - `synthid_local_verifier` wraps the engine contract and checks input integrity.
   - `synthid_benchmark` computes ROC, AUC and confidence intervals on researcher-labelled data.
   - `synthid_online.OnlineGate` enforces the off-by-default, consent-gated browser hand-off.
   - `services/synthid_paper_export` writes CSV, JSON, PDF, PNG and a ZIP with SHA-256 and BLAKE3 manifests.

   See `docs/SYNTHID_RESEARCH_LAB.md`.

6. Fingerprint Research Lab: the pure-numpy engine lives in `app/research/` and has no Qt or filesystem dependency.
   - `taxonomy` parses the supplied source file into `data/fingerprint_taxonomy.json`; `library` loads the verified
     `data/research_library.json` and exports APA 7 / BibTeX / CITATION.cff.
   - `imaging`, `spectral`, `wavelet`, `dct`, `residuals`, `rpca`, `consensus`, `features` are the measurement engines.
   - `surrogate` is the controlled keyed watermark + blind detector with known ground truth; `procedural` makes
     deterministic synthetic test images; `robustness`, `separation` and `hypotheses` are ground-truth studies.
   - `methods` is the plugin registry (Method 00–54) with honest READY / UNAVAILABLE / NOT_IMPLEMENTED status;
     `runner` dispatches a method to a standard `MethodResult`; `failure` adds rule-based failure analysis.
   - `core/fingerprint_lab.FingerprintLab` allocates `SPX-FP-YYYYMMDD-NNNNNN` runs under `<workspace>/fingerprint_research/`,
     copies inputs (originals hashed before/after), writes maps as PNG, and records a reproducible run.
   - `services/fingerprint_paper_export` writes CSV, JSON, PDF, PNG and a ZIP with SHA-256 and BLAKE3 manifests.

   See `docs/FINGERPRINT_TAXONOMY.md` and `docs/SOFTWARE_QUALITY.md`.

## Threading

All heavy work runs in `QRunnable` workers on the global `QThreadPool`. One experimental operation runs at a time so the
transformation sequence stays strictly ordered. Audit events from worker threads reach the GUI through queued Qt signals.

## Extending

New output format: add an entry to `FORMAT_CAPS` and a branch in `encode_as` (`app/core/image_writer.py`). New
transformation: add an `OpSpec` in `transform_engine.OPERATIONS` (parameters render automatically in the UI). New
SynthID engine: follow the contract in `tools/README.md`, no code change needed. New fingerprint method: add a `Method`
record in `app/research/methods.py` and a dispatch branch in `app/research/runner.py` (the registry and card render
automatically); `validate()` enforces the honesty rules.

## Easy Mode / Expert Mode

Two application shells share one `AppController` and every engine. `app/main.py` reads `Settings.ui_mode()` and
builds either `app/ui/easy/window.EasyWindow` (light theme, three steps) or `app/ui/main_window.MainWindow` (dark
research console). Switching is a restart (`app/ui/app_mode.save_and_restart`: persist, start a detached instance,
quit). The Easy shell calls `AppController.run_easy`, which runs `app/core/easy_mode_orchestrator.EasyModeOrchestrator`
in the worker pool: a deterministic 12-stage pipeline with a per-method suitability plan, shared execution of identical
method implementations, graceful per-method / per-stage fallback, a ground-truth candidate evaluator for the controlled
surrogate arm, the `format_conversion` transformation for the result image, and `app/services/easy_report.py` for the
report (rendered by `report_service`). Nothing in the orchestrator re-implements a scientific method.

## Cross-Detector Research Lab

`app/research/cross_detector.py` is the pure comparison engine: it parses a user-supplied external result
(`ExternalResult`), distils local evidence from an `EasyModeResult` (`local_evidence_from_easy`, descriptive dimensions
mapped to the seven fingerprint families), and compares them (`compare`) without ever declaring a system correct unless
the ground-truth level is decisive. `app/research/heatmap_compare.py` quantifies spatial overlap of an imported heatmap
with local maps (IoU / Dice / correlation). `app/research/hardcases.py` generates a labelled local benchmark with known
ground truth. `app/core/cross_detector_lab.py` is the `SPX-XD` run store, the benchmark-matrix CSV, and the
consent-gated `ExternalDetectorGate` browser hand-off (never uploads). `app/services/cross_detector_report.py` renders
the 14-section report through `report_service`. The Expert view `app/ui/views/cross_detector_view.py` wires it together;
`AppController.run_cross_detector` reuses the Easy orchestrator for the local pass. Nothing in this subsystem contacts a
network.

