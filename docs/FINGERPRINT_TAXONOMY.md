# Fingerprint Taxonomy

SynthProvenance builds a structured taxonomy database from the user-supplied research file
`data/source/AI_Generative_Image_Fingerprints_Taxonomy_APA.txt` (Indonesian text with English terminology). The parser
is `app/research/taxonomy.py`; the generated database is `data/fingerprint_taxonomy.json`, rebuilt with
`python scripts/build_taxonomy.py`. The Fingerprint Taxonomy view browses it.

- **Source digest (SHA-256):** `41a7654e59b446b03a7dc66c6133608d15df779b210ad4f03cf823002f94ce4a`
- **Entries parsed:** 572 (terms, aliases, method names and section-8 search vocabulary)
- **APA references in the source:** 21 (also verified and enriched in the Research Library)
- **Anchor papers:** 23

Definitions are **quoted** from the source file; nothing is rewritten. `domain` and `representation` are **derived**
from the sub-section an entry belongs to and are listed in each entry's `derived_fields`, so the derivation stays
visible. Every entry records the `source_line` it came from.

## Families (kept separate by design)

The source file warns against collapsing "fingerprint", "artifact", "watermark", "provenance" and "detector feature"
into one class. SynthProvenance keeps seven families distinct and never merges them into a single "AI fingerprint"
label.

| Code | Family | Entries | What it is |
|------|--------|--------:|-----------|
| A | Intrinsic / passive fingerprint | 149 | Traces arising naturally from a generator (architecture, weights, training, upsampling, decoder, sampling) without an embedded watermark |
| B | Causal fingerprint | 55 | Model fingerprints formulated through a causal provenance → trace relation, separated from content and style |
| C | Spectral / frequency fingerprint | 156 | Cues in energy distribution, transform coefficients, periodic patterns or spectral statistics |
| D | Proactive / artificial watermark | 103 | Signals deliberately embedded for provenance, attribution, ownership or detection (ProMark, Stable Signature, Tree-Ring, Gaussian Shading, SynthID) |
| E | Detector-specific representation | 102 | Features/embeddings used by a detector or foundation model (CLIP, ViT, DINO, multiLID, contrastive) |
| F | C2PA provenance | 7 | Signed provenance metadata — related to, but not, an intrinsic image fingerprint |
| G | External platform classification | 0 | Labels shown by third parties — recorded by the researcher only, never inferred |

## Separation rules (surfaced in the UI)

- C2PA ≠ intrinsic fingerprint
- Metadata ≠ SynthID
- SynthID ≠ generic AI detector
- Detector feature ≠ intrinsic generator fingerprint
- No detected signal ≠ human-created

## Record schema

Each entry carries: `term`, `alias`, `category`, `subcategory`, `definition` (quoted), `paper`, `method`, `domain`,
`representation`, `source_type`, `research_status`, `source_line`. References carry authors, year, venue, DOI/URL and
the full APA 7 string, matched back to the sub-sections that cite them.

## Mapping to methods and literature

Taxonomy sub-sections map to the Fingerprint Research Lab methods (`app/research/methods.py`) and to the verified
Research Library (`data/research_library.json`). For example, family C (spectral) backs Methods 13–18 (FFT, DCT,
wavelet, spectral tail, high-frequency residual, Benford-DCT); family A backs Methods 03–05 and the cross-image
consensus (Method 25); family D is studied only through the controlled surrogate laboratory (Methods 34–42), never by
attacking a real watermark.
