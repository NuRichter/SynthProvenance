# Research Sources (v6)

This upgrade adds a cross-detector research instrument and an operational taxonomy mapping. The
sources below are the ones consulted or bundled; nothing was fabricated, and a method is integrated
only after the validation steps in [`METHOD_VALIDATION.md`](METHOD_VALIDATION.md).

## Primary ontology

- `data/source/AI_Generative_Image_Fingerprints_Taxonomy_APA.txt` — the fingerprint taxonomy that
  keeps intrinsic / causal / spectral / proactive-watermark / detector-representation / reconstruction
  / C2PA-provenance as **distinct** families. It is parsed into `data/fingerprint_taxonomy.json` and
  mapped to executable stages in `data/fingerprint_execution_matrix.json`
  (`scripts/build_execution_matrix.py`).

## External-detector reference (TruthScan)

- `TruthScan Archives/TruthScan Deteksi Gambar AI (Riset 5 Oktober 2026).md` — a researcher-supplied
  study of TruthScan's detection pipeline. It is treated as **methodological context, not ground
  truth**, and it preserves a FACT vs `[INFERENSI]` (inference) vs unknown distinction. It can be
  imported into the Cross-Detector Lab as a reference (never as a per-image score).
  - **Documented (FACT):** a layered pipeline — file/quality validation, metadata (ExifTool + Pillow),
    a generator-watermark detector (`ocr` field), a hidden `synthid` field in the OpenAPI schema, an
    ML image classifier (`ml_model`), a JET activation heatmap, and an **asynchronous LLM narrative**
    that writes the human-readable explanation. Response fields include `final_result`,
    `detection_step` (a watermark hit at `detection_step = 2` can short-circuit and return a generator
    name as `final_result` with the ML score 0), `confidence`, `warnings`, and a heatmap reference.
  - **Inference `[INFERENSI]`:** model architecture (likely a quantised/compressed CNN or transformer),
    exact thresholds, and the decision-fusion logic are reconstructed, not official.
  - **Unknown / undisclosed:** weights, training data, decision thresholds; there is no public paper,
    patent or technical whitepaper. The referenced SDK repository returns 404.
  - **Caveat used in the app:** the 99%+ accuracy claim is **not independently validated**; third-party
    tests on specific domains report far lower numbers (e.g. ~71% detection, ~57% false positive on
    genuine ID photos), and some favourable tests are from affiliated/paid parties. Online
    cross-referencing of these composio/undetectable facts is consistent with the archive, but TruthScan's
    internal model remains undisclosed.
  - **Sources named in the archive and cross-checked:** TruthScan OpenAPI (`detect-image.truthscan.com/openapi.json`),
    the server `/help` document, official API/SDK docs; IDScan.net (Apr 2026), NewsGuard (May 2026),
    arXiv 2602.07814 (Feb 2026); plus [composio.dev/toolkits/truthscan](https://composio.dev/toolkits/truthscan).

## Method literature

Per-method literature is recorded on each method card (`app/research/methods.py`, column
`source_reference`) and in the Research Foundations view (`data/research_library.json`,
`data/research_catalog.json`): Marra 2019 (GAN/PRNU residuals), Durall 2020 / Frank 2020 (spectral),
Bammey 2023 (Synthbuster), Bonettini 2021 (Benford-DCT), Lorenz 2023 (LID/multiLID), Wang 2023 (DIRE),
Ricker 2024 (AEROBLADE), Ojha 2023 (CLIP/UniversalFakeDetect), Candès 2011 (Robust PCA),
He 2013 (guided filter), An 2024 (WAVES robustness). Methods that need trained weights (DIRE,
AEROBLADE, CLIP/ViT/DINO, DNA-Det, causal) stay `UNAVAILABLE`; detector-evasion methods stay
`NOT_IMPLEMENTED` by design.
