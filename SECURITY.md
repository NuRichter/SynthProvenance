# Security Policy

SynthProvenance is private scientific research software for a local research environment. It is designed to treat
every input image as untrusted and to operate offline.

## Security model

- **Untrusted inputs.** Images, metadata and C2PA manifests are parsed, never executed. Metadata is never evaluated
  as code. Decompression-bomb protection and a configurable pixel/memory budget bound decoding.
- **Local-only by default.** A CPython audit hook (`app/utils/netguard.py`) blocks outbound socket connections and
  name resolution to non-loopback hosts from the application. The self-test proves outbound access is blocked. The
  only intentional network use is the build (pip from PyPI, and an optional, consented Python download).
- **No silent model downloads.** The fingerprint research engine is numpy/Pillow only. Methods that would need a
  deep-learning runtime and trained weights are reported UNAVAILABLE; nothing is fetched during analysis.
- **Path safety.** All user-controlled names that reach disk pass through `safe_filename`/`safe_join`/`safe_arcname`
  (path-traversal and ZIP-slip guards). Subprocesses (optional ExifTool / c2patool / SynthID engine) are invoked with
  argument lists, never a shell string built from untrusted paths.
- **Originals are never modified.** Experiments and research runs operate on copies; originals are hashed before and
  after and reported as `original_unchanged`.
- **External detectors** (TruthScan) are studied by importing a user-supplied result; SynthProvenance never
  uploads an image or calls an external API. The optional browser hand-off is OFF by default, consent-gated per
  session and per open, restricted to allow-listed `https` hosts, and records `uploaded_by_synthprovenance: false`.
  SynthProvenance never automates repeated external submissions and never searches for transformations that defeat
  an external detector.
- **Online verification** (SynthID) is OFF by default and is an explicit, per-session, consent-gated hand-off to an
  official Google page in the browser. SynthProvenance itself uploads nothing.

## Scope and non-goals

SynthProvenance does not generate, forge or re-sign provenance, does not estimate, reconstruct, remove or attack
real pixel-domain watermarks (SynthID included), and contains no search for transformations that defeat detectors.
Red-team-style methods exist only against the local, keyed surrogate watermark with known ground truth, and are
limited to robustness measurement and ground-truth separation studies.

## Reporting a vulnerability

This is internal research software. Report suspected vulnerabilities privately to the maintainers of the NuRichter
Workspace research group, with a description of the problem class and reproduction steps. Please do not include a
working exploit or a step-by-step extraction path in the initial report.
