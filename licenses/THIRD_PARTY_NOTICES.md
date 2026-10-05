# Third-Party Notices

SynthProvenance bundles the following third-party components. Their license terms are preserved. At build time,
`scripts/collect_runtime.py` additionally writes `dist/SynthProvenance/licenses/THIRD_PARTY_NOTICES.txt` with the
exact license texts discovered in the installed distributions.

| Component | Role | License |
|-----------|------|---------|
| Qt for Python — PySide6-Essentials, shiboken6 | GUI toolkit | GNU LGPL v3 (dynamically linked; libraries in `_internal/PySide6` may be replaced) |
| Pillow | Image decoding/encoding | MIT-CMU / HPND |
| NumPy | Numerical engine | BSD-3-Clause |
| blake3 | BLAKE3 hashing | Apache-2.0 / CC0 (see package) |
| reportlab | PDF reports | BSD-3-Clause |
| charset-normalizer | Text encoding detection | MIT |
| PyInstaller (build only) | Windows packaging | GPL-2.0 with a bootloader exception permitting distribution of the produced executable |

## Optional external tools (not bundled; user-installed)

| Tool | Role | License |
|------|------|---------|
| ExifTool | Richer metadata parsing | Perl Artistic / GPL |
| c2patool | C2PA validation | MIT OR Apache-2.0 |
| c2pa-python / c2pa-rs | C2PA validation | MIT OR Apache-2.0 |

## Research sources

The fingerprint taxonomy database is derived from the user-supplied file
`data/source/AI_Generative_Image_Fingerprints_Taxonomy_APA.txt`. The research library
(`data/research_library.json`) records bibliographic metadata for publicly published works; it contains citations
and summaries only, not the copyrighted papers themselves. Each paper remains under its publisher's terms.

No model weights are bundled. SynthProvenance does not include or redistribute SynthID, any diffusion/GAN model, or
any trained detector.
