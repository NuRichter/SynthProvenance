# Software Quality

SynthProvenance organises its quality goals against **ISO/IEC 25010:2023** (Systems and software Quality Requirements
and Evaluation — product quality model) as a *reference model*. This is a mapping, not a certification; SynthProvenance
does not claim ISO certification.

## Product-quality characteristics

| Characteristic | How SynthProvenance addresses it | Evidence |
|----------------|----------------------------------|----------|
| **Functional suitability** | 39 of 55 fingerprint methods run and are validated by the test suite; the remaining methods carry an honest UNAVAILABLE (needs a DL runtime/weights) or NOT_IMPLEMENTED (detector-evasion, out of scope) status with a reason | `tests/test_research_engine.py::test_runner_runs_all_ready_methods_without_error`; method registry validation |
| **Performance efficiency** | Overlap-aware tiling, Welch-averaged spectra, strip-wise pixel metrics and a memory budget bound the working set; any practical resolution is supported without downscaling the source | `app/research/imaging.py` (`tiled_apply`, `auto_tile`), `bench_pixel_integrity.py` |
| **Compatibility** | PNG/JPEG/WEBP/TIFF/BMP/GIF decode; a portable one-folder Windows build; optional ExifTool/c2patool interop | `tests/test_pixels_formats.py`, build verification |
| **Usability** | Guided Research Wizard (7 steps), method cards with purpose/limitations, tooltips, a splash screen with a real init sequence, restrained scientific UI | `app/ui/wizard.py`, `app/ui/views/fingerprint_view.py` |
| **Reliability** | Originals are hashed before/after and reported `original_unchanged`; pixel integrity is measured (PIXEL-EXACT only on identical samples); failed/weak runs are recorded with failure analysis, not hidden | `tests/test_pixels_formats.py`, `app/research/failure.py` |
| **Security** | Untrusted images; no code execution from metadata; decompression-bomb and memory guards; path-traversal and ZIP-slip guards; safe subprocess invocation; LOCAL-ONLY network guard | `tests/test_security_ui.py`, `app/utils/netguard.py`, `app/utils/paths.py`, `SECURITY.md` |
| **Maintainability** | Pure numpy research engine (`app/research/*`) separated from Qt; a plugin-style method registry; full automated test suite; pinned dependencies | this repository, `tests/` |
| **Portability** | Local-only; numpy/Pillow/PySide6 only; no GPU or model required; GPU used only for an environment record | `requirements.txt`, `app/research/*` |

## Interaction-quality notes (ISO/IEC 25010 quality-in-use)

- **Trust / freedom from risk:** the application states what is and is not measured, never claims an AI/human verdict,
  and marks controlled-surrogate results as not transferable to real generators or real watermarks.
- **Effectiveness:** every run produces a reproducible record (SPX-… / SPX-FP-…) and a paper-ready export.

## Test mapping

The pytest suite covers: image loading/hashing, five export formats and lossless preservation, metadata parsing and
sanitisation (`changed_pixels == 0`), C2PA parsing/tampering/separation, SynthID Research Lab state and safeguards,
the fingerprint research engine (wavelet/DCT perfect reconstruction, surrogate ground-truth detection and null
calibration, separation recovery, cross-image consensus, robustness, the 55-method registry and runner, and the lab
run store with paper export), the taxonomy and library databases, high-resolution loading, the memory budget,
security guards, the offscreen GUI across all views, and build-file validation.

Run: `python -m pytest`. Build verification additionally launches the built EXE and runs `--self-test` and
`--smoke-gui` (which exercises a controlled-surrogate fingerprint run and a SynthID paper export in LOCAL MODE).
