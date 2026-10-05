# Research Method

## Principle

WE DO NOT GUESS. WE MEASURE. Every statement in the UI or report is traceable to bytes, decoded samples, an engine
output, or an explicit user record. Absence of evidence is reported as absence of evidence.

## Evidence tiers

| Tier | Examples | Counted toward OBSERVED |
|------|----------|-------------------------|
| OBSERVABLE EVIDENCE | C2PA action `digitalSourceType` = trainedAlgorithmicMedia / compositeWithTrainedAlgorithmicMedia, XMP `Iptc4xmpExt:DigitalSourceType` with those terms, `Iptc4xmpExt:AISystemUsed`, structured generator-parameter records | Yes |
| EXPERIMENTAL INTERPRETATION | Generator-associated software names, unstructured text chunks, synthetic but non-generative source types | No |
| EXTERNAL PLATFORM CLASSIFICATION | Labels copied by the researcher from a platform | No |
| UNKNOWN INFORMATION | Invalid containers, uninspected formats, pixel-domain watermarks | No |

NOT OBSERVED always carries the statement: "No observable AI-content provenance signal was detected under the selected
experimental condition. This does not establish that the image is human-created."

## Layer separation

Each transformation produces seven layer records (C2PA, SynthID, ordinary metadata, pixels, encoding, file structure,
external classification) with BEFORE, AFTER, STATE, OBSERVATION, METHOD, CONDITION and LIMITATION. States: DETECTED,
NOT DETECTED, REMOVED, PERSISTED, ALTERED, INVALID, UNKNOWN, UNAVAILABLE, NOT TESTABLE.

Rules enforced in code:

* Removing metadata is never assumed to remove an embedded signal.
* Absence of observable C2PA never implies the image is not AI-generated.
* A SynthID NOT DETECTED result never becomes REMOVED. REMOVED is used only where removal is directly measurable
  (a C2PA store whose bytes are gone).
* Containers that are not inspected yield UNKNOWN, not REMOVED.

## Pixel integrity

Canonical decode: frame 0, EXIF orientation not applied, palette expanded (RGBA when a transparency entry exists), native
bit depth kept. PIXEL-EXACT requires identical dimensions, identical canonical mode, zero changed samples and identical
pixel SHA-256. PSNR = 10 log10(L^2 / MSE) with L the dtype range. SSIM uses a 7x7 uniform window with sample covariance,
C1 = (0.01 L)^2 and C2 = (0.03 L)^2, averaged over channels. Crops also get a region-aligned comparison.

## Ethics and scope

The tool studies how provenance behaves. It contains no pixel-watermark removal, no adversarial perturbation, no
regeneration attack and no search for detector-defeating settings. Separation experiments always operate on copies,
preserve the original and are fully audited. Rights notices (copyright, credit, source) are never removed by the
sanitizer, since removing rights-management information can be unlawful in many jurisdictions.
