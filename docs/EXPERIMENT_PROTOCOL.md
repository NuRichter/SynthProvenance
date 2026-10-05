# Experiment Protocol

1. **Load.** Open or drop the image. It is validated by magic bytes, admitted by the memory budget and analysed. Nothing is
   written yet.
2. **Start.** Press START EXPERIMENT. An ID such as `SPX-2026-0927-000001` is allocated and the original is copied into
   `original/`. The baseline (metadata, C2PA, AI-content signal, SynthID state, forensic statistics) is recorded and audited.
3. **Objective.** Write the research objective and hypotheses in Research Report and press Save.
4. **Transform.** Choose operations in Transformation Lab, Format Conversion or C2PA Provenance. Use one variable per
   condition (for example lossless PNG containers for colour, resize and crop, so only that variable changes). Every run
   gets an ID (T001, T002 and so on) with its full parameters.
5. **External round-trips (optional).** Upload a copy to a platform yourself, download it, then use COMPARE to import it
   as an EXTERNAL FILE condition. Record what the platform displayed in External Records. SynthProvenance never contacts
   the platform.
6. **Measure.** Review Signal Separation (seven layers), Pixel Integrity, Comparison (side-by-side, overlay, blink,
   difference, heatmap with pixel inspector) and the Experiment Matrix.
7. **Report.** Export PDF/JSON/CSV/HTML/PNG and `experiment.zip`. Verify the bundle with `hashes.txt`.
8. **Replicate.** Repeat on independent images. Record library versions from Reproducibility Information, because codec
   builds influence lossy results.

## Workspace layout

```
<workspace>/experiments/<ID>/{experiment.json, original/, output/, report/, metadata/, provenance/, synthid/, metrics/, logs/audit.jsonl}
<workspace>/{reports/, exports/, cache/, logs/}
```
