"""Fingerprint taxonomy database parsed from the supplied research taxonomy file.

Source: ``data/source/AI_Generative_Image_Fingerprints_Taxonomy_APA.txt`` (Indonesian
text with English terminology). The parser is a plain line-based state machine. It
never evaluates content, and it keeps the original wording: definitions are quoted
from the file, and every entry records the line it came from (``source_line``).

Each entry has the fields requested by the research brief::

    term, alias, category, subcategory, definition, paper, method, domain,
    representation, source_type, research_status

``domain`` and ``representation`` are not stated per term in the file. They are
derived from the sub-section the term belongs to and are listed in
``derived_fields`` so the derivation stays visible.

The seven top-level categories are kept separate on purpose (the file warns against
merging "fingerprint", "artifact", "watermark", "provenance" and "detector feature"):

    A INTRINSIC_PASSIVE        intrinsic / passive generator fingerprints
    B CAUSAL                   causal fingerprints
    C SPECTRAL                 frequency-domain / spectral fingerprints
    D PROACTIVE_WATERMARK      proactive / artificial fingerprints and watermarks
    E DETECTOR_REPRESENTATION  detector-specific representations
    F C2PA_PROVENANCE          signed provenance metadata (not a fingerprint)
    G EXTERNAL_PLATFORM        labels shown by external platforms (user-recorded only)
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.utils.paths import resource_path
from app.utils.serialization import jsonable, read_json, write_json

SOURCE_NAME = "AI_Generative_Image_Fingerprints_Taxonomy_APA.txt"
SCHEMA_VERSION = "1.0"
MAX_SOURCE_BYTES = 4 * 1024 * 1024

CATEGORIES = {
    "INTRINSIC_PASSIVE": ("A", "Intrinsic / passive fingerprint",
                          "Traces that arise naturally from a generator (architecture, weights, training, upsampling, "
                          "decoder, sampling) without an explicitly embedded watermark."),
    "CAUSAL": ("B", "Causal fingerprint",
               "Model fingerprints formulated through a causal relation provenance -> trace, separated from content and "
               "style; evaluated with interventions and counterfactuals."),
    "SPECTRAL": ("C", "Spectral / frequency fingerprint",
                 "Cues in energy distribution, transform coefficients, periodic patterns or spectral statistics. Can be an "
                 "intrinsic cue or a detector feature."),
    "PROACTIVE_WATERMARK": ("D", "Proactive / artificial watermark",
                            "Signals deliberately embedded for provenance, attribution, ownership or detection."),
    "DETECTOR_REPRESENTATION": ("E", "Detector-specific representation",
                                "Features or embeddings used by a detector or foundation model. Not automatically an "
                                "intrinsic or causal generator fingerprint."),
    "C2PA_PROVENANCE": ("F", "C2PA provenance",
                        "Signed provenance metadata (Content Credentials). Related to, but not, an intrinsic image "
                        "fingerprint."),
    "EXTERNAL_PLATFORM": ("G", "External platform classification",
                          "Labels displayed by third-party platforms. Recorded by the researcher only; never inferred."),
}
SEPARATION_RULES = [
    "C2PA != intrinsic fingerprint",
    "Metadata != SynthID",
    "SynthID != generic AI detector",
    "Detector feature != intrinsic generator fingerprint",
    "No detected signal != human-created",
]

# section / sub-section code -> (category, domain, representation)
_SECTION_MAP = {
    "1": ("INTRINSIC_PASSIVE", "Spatial", "noise residual / generator trace"),
    "1A": ("INTRINSIC_PASSIVE", "Spatial", "GAN pattern-noise residual"),
    "1B": ("INTRINSIC_PASSIVE", "Spatial", "averaged noise residual (PRNU-inspired)"),
    "1C": ("INTRINSIC_PASSIVE", "Latent", "learned image / model fingerprint"),
    "1D": ("INTRINSIC_PASSIVE", "Mixed", "architecture- vs instance-level trace"),
    "1E": ("INTRINSIC_PASSIVE", "Latent", "content-irrelevant disentangled fingerprint"),
    "1F": ("INTRINSIC_PASSIVE", "Mixed", "multi-level (spatial + frequency) fingerprint"),
    "1G": ("INTRINSIC_PASSIVE", "Latent", "diffusion / autoencoder reconstruction residual"),
    "2": ("CAUSAL", "Causal", "causally decoupled fingerprint representation"),
    "2A": ("CAUSAL", "Causal", "semantic-invariant latent space"),
    "2B": ("CAUSAL", "Mixed", "multi-space feature fusion (RGB, DCT, Fourier, ViT, DINO, ResNet)"),
    "2C": ("CAUSAL", "Causal", "counterfactual fingerprint intervention"),
    "2D": ("CAUSAL", "Latent", "constrained optimisation in fingerprint space"),
    "3": ("SPECTRAL", "Frequency", "transform-domain statistics"),
    "3A": ("SPECTRAL", "Frequency", "Fourier magnitude / power spectrum"),
    "3B": ("SPECTRAL", "Frequency", "periodic peaks from up-sampling"),
    "3C": ("SPECTRAL", "Frequency", "radial log-power spectrum and tail"),
    "3D": ("SPECTRAL", "Frequency", "block DCT coefficients"),
    "3E": ("SPECTRAL", "Frequency", "wavelet sub-bands (LL, LH, HL, HH)"),
    "3F": ("SPECTRAL", "Spatial", "high-pass / Laplacian residual"),
    "3G": ("SPECTRAL", "Frequency", "first-digit distribution of quantised DCT coefficients"),
    "3H": ("SPECTRAL", "Frequency", "learned spectral representation"),
    "3I": ("SPECTRAL", "Frequency", "Fourier artifacts of diffusion images"),
    "4": ("PROACTIVE_WATERMARK", "Mixed", "embedded signal"),
    "4A": ("PROACTIVE_WATERMARK", "Spatial", "training-data embedded fingerprint"),
    "4B": ("PROACTIVE_WATERMARK", "Spatial", "encoder-decoder steganographic signal"),
    "4C": ("PROACTIVE_WATERMARK", "Spatial", "watermark propagated through training"),
    "4D": ("PROACTIVE_WATERMARK", "Spatial", "proactive concept watermark"),
    "4E": ("PROACTIVE_WATERMARK", "Latent", "watermark in model weights / activations / behaviour"),
    "4F": ("PROACTIVE_WATERMARK", "Latent", "latent-decoder binary signature"),
    "4G": ("PROACTIVE_WATERMARK", "Frequency", "Fourier-structured initial-noise pattern"),
    "4H": ("PROACTIVE_WATERMARK", "Latent", "distribution-preserving latent watermark"),
    "4I": ("PROACTIVE_WATERMARK", "Frequency", "multi-key Fourier-space noise watermark"),
    "4J": ("PROACTIVE_WATERMARK", "Spatial", "deep-learning pixel-domain watermark"),
    "4K": ("C2PA_PROVENANCE", "Metadata", "signed provenance manifest"),
    "5": ("DETECTOR_REPRESENTATION", "Semantic", "detector feature embedding"),
    "5A": ("DETECTOR_REPRESENTATION", "Semantic", "CLIP / ViT image embedding"),
    "5B": ("DETECTOR_REPRESENTATION", "Semantic", "adapted CLIP features"),
    "5C": ("DETECTOR_REPRESENTATION", "Semantic", "image-text contrastive representation"),
    "5D": ("DETECTOR_REPRESENTATION", "Latent", "local intrinsic dimensionality of feature manifold"),
    "5E": ("DETECTOR_REPRESENTATION", "Semantic", "self-supervised ViT (DINO) features"),
    "5F": ("DETECTOR_REPRESENTATION", "Latent", "contrastive / metric-learning embedding"),
    "5G": ("DETECTOR_REPRESENTATION", "Latent", "feature-space similarity / prototypes"),
    "6": ("INTRINSIC_PASSIVE", "Spatial", "reconstruction error"),
    "6A": ("INTRINSIC_PASSIVE", "Spatial", "diffusion reconstruction error"),
    "6B": ("INTRINSIC_PASSIVE", "Latent", "autoencoder reconstruction error"),
    "6C": ("SPECTRAL", "Frequency", "Fourier artifacts of diffusion images"),
}
_KEYWORD_GROUPS = {
    "FINGERPRINT": "INTRINSIC_PASSIVE", "ARTIFACT / TRACE": "INTRINSIC_PASSIVE", "ATTRIBUTION": "INTRINSIC_PASSIVE",
    "INTRINSIC / PASSIVE": "INTRINSIC_PASSIVE", "CAUSAL": "CAUSAL", "FREQUENCY": "SPECTRAL",
    "PROACTIVE": "PROACTIVE_WATERMARK", "DETECTOR-SPECIFIC": "DETECTOR_REPRESENTATION",
}
_DOMAIN_OF = {"INTRINSIC_PASSIVE": "Spatial", "CAUSAL": "Causal", "SPECTRAL": "Frequency", "PROACTIVE_WATERMARK": "Mixed",
              "DETECTOR_REPRESENTATION": "Semantic", "C2PA_PROVENANCE": "Metadata", "EXTERNAL_PLATFORM": "N/A"}

# label line (lower-case, without trailing colon) -> group kind
_TERM_LABELS = ("alias", "istilah", "nomenklatur", "nama", "sub-band", "representasi", "komponen", "terkait", "spai",
                "mfdl", "lasted", "deeclip", "ppm-clip")
_METHOD_LABELS = ("metode", "nomenklatur/metode")
_PAPER_LABELS = ("paper", "paper kunci", "paper utama", "paper fundamental", "paper anchor", "paper penting")
_NOTE_LABELS = ("definisi", "ide", "konsep", "catatan", "tujuan", "gagasan", "interpretasi", "poin penting", "pipeline",
                "perbedaan", "ciri", "kegunaan", "fokus", "bentuk konseptual", "konsep utama", "catatan konseptual",
                "penting")
_CONCEPT_LABELS = ("sumber umum", "modern direction")

_SEC_RE = re.compile(r"^(\d{1,2})\.\s+([A-Z0-9][^a-z]*)$")
_SUB_RE = re.compile(r"^(\d{1,2}[A-Z])\.\s+(.+)$")
_REF_NUM_RE = re.compile(r"^\[(\d{1,3})\]\s*$")
_YEAR_RE = re.compile(r"\((\d{4})\)\.\s")
_DOI_RE = re.compile(r"https?://doi\.org/(10\.\S+?)\.?$")
_URL_RE = re.compile(r"(https?://\S+)")
_DASHES = re.compile(r"^[-=]{6,}$")


@dataclass
class TaxonomyEntry:
    id: str
    term: str
    alias: str
    category: str
    category_code: str
    subcategory: str
    definition: str
    paper: list = field(default_factory=list)
    method: list = field(default_factory=list)
    domain: str = ""
    representation: str = ""
    source_type: str = "TAXONOMY_FILE"
    research_status: str = ""
    source_line: int = 0
    language: str = "id/en"
    derived_fields: list = field(default_factory=lambda: ["domain", "representation"])


@dataclass
class Reference:
    ref_id: str
    number: int
    authors: list
    year: int | None
    title: str
    venue: str
    doi: str | None
    url: str | None
    apa7: str
    source_line: int
    origin: str = "TAXONOMY_FILE"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _label_kind(text: str) -> str | None:
    t = text.strip().rstrip(":").strip().lower()
    if not t or len(t) > 80:
        return None
    for group, labels in (("METHOD", _METHOD_LABELS), ("PAPER", _PAPER_LABELS), ("NOTE", _NOTE_LABELS),
                          ("CONCEPT", _CONCEPT_LABELS), ("TERM", _TERM_LABELS)):
        for lab in labels:
            if t == lab or t.startswith(lab + " ") or t.startswith(lab + "/") or t.startswith(lab + ":"):
                return group
    if t.startswith("representasi yang dapat"):
        return "TERM"
    return None


def parse_reference(lines: list[str], number: int, line_no: int) -> Reference:
    text = " ".join(x.strip() for x in lines if x.strip())
    ym = _YEAR_RE.search(text)
    authors_part, rest, year = (text[:ym.start()].strip(), text[ym.end():], int(ym.group(1))) if ym else ("", text, None)
    title, venue = (rest.split(". ", 1) + [""])[:2] if rest else ("", "")
    authors = []
    if authors_part:
        for a in authors_part.replace(", & ", ", ").replace(" & ", ", ").split("., "):
            a = a.strip().rstrip(",").strip()
            if a:
                authors.append(a if a.endswith(".") else a + ".")
    urls = _URL_RE.findall(text)
    url = urls[-1].rstrip(".") if urls else None
    dm = _DOI_RE.search(url or "")
    venue = _URL_RE.sub("", venue).strip().rstrip(".").strip()
    return Reference(ref_id=f"TAX-REF-{number:02d}", number=number, authors=authors, year=year, title=title.strip(),
                     venue=venue, doi=dm.group(1) if dm else None, url=url, apa7=text, source_line=line_no)


def parse_text(text: str) -> dict:
    """Parse the taxonomy file text into entries, references, keywords, anchors and the record schema."""
    lines = text.splitlines()
    entries: list[TaxonomyEntry] = []
    refs: list[Reference] = []
    anchors: list[dict] = []
    schema_fields: list[str] = []
    terminology_notes: list[str] = []
    sec_code, sec_title, sub_code, sub_title = "0", "", "", ""
    group, group_line = None, 0
    notes: dict[str, list[str]] = {}
    papers: dict[str, list[str]] = {}
    methods: dict[str, list[str]] = {}
    section_def: dict[str, list[str]] = {}
    mode = "body"
    ref_buf: list[str] = []
    ref_num, ref_line = 0, 0
    kw_group = ""
    i = 0

    def key() -> str:
        return sub_code or sec_code

    def add_entry(term: str, status: str, line_no: int) -> None:
        term = term.strip().strip('"').strip()
        if not term or len(term) > 200:
            return
        code = key()
        cat, dom, rep = _SECTION_MAP.get(code, _SECTION_MAP.get(sec_code, ("INTRINSIC_PASSIVE", "Spatial", "")))
        canonical = (sub_title or sec_title).strip().title() if (sub_title or sec_title) else term
        entries.append(TaxonomyEntry(id="", term=term, alias=canonical, category=cat, category_code=CATEGORIES[cat][0],
                                     subcategory=f"{code}. {(sub_title or sec_title).strip()}".strip(), definition="",
                                     domain=dom, representation=rep, research_status=status, source_line=line_no))

    while i < len(lines):
        raw = lines[i]
        s = raw.strip()
        nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
        line_no = i + 1
        i += 1
        if not s or _DASHES.match(s):
            continue
        if s.startswith("APA STYLE SOURCES"):
            mode = "refs"
            continue
        if s.startswith("SUMBER UTAMA UNTUK VERIFIKASI") or s.startswith("CATATAN AKHIR"):
            if ref_buf:
                refs.append(parse_reference(ref_buf, ref_num, ref_line))
                ref_buf = []
            mode = "tail"
            continue
        if mode == "refs":
            m = _REF_NUM_RE.match(s)
            if m:
                if ref_buf:
                    refs.append(parse_reference(ref_buf, ref_num, ref_line))
                ref_buf, ref_num, ref_line = [], int(m.group(1)), line_no + 1
            else:
                ref_buf.append(s)
            continue
        if mode == "tail":
            continue
        if s == "CATATAN TERMINOLOGI":
            mode = "terminology"
            continue
        m = _SEC_RE.match(s)
        if m and (_DASHES.match(nxt) or (lines[i - 2].strip() if i >= 2 else "").startswith("---")):
            sec_code, sec_title, sub_code, sub_title, group = m.group(1), m.group(2).strip(), "", "", None
            mode = {"7": "cross", "8": "keywords", "9": "anchors", "10": "schema", "11": "summary"}.get(sec_code, "body")
            continue
        if mode == "terminology":
            if s.startswith("- "):
                terminology_notes.append(s[2:].strip())
            continue
        if mode == "keywords":
            if s.endswith(":") and not s.startswith("-"):
                kw_group = s.rstrip(":").strip()
            elif s.startswith("- ") and kw_group:
                cat = _KEYWORD_GROUPS.get(kw_group, "INTRINSIC_PASSIVE")
                entries.append(TaxonomyEntry(id="", term=s[2:].strip().strip('"'), alias=f"search vocabulary: {kw_group}",
                                             category=cat, category_code=CATEGORIES[cat][0],
                                             subcategory=f"8. Search vocabulary / {kw_group}",
                                             definition="Literature search keyword listed in section 8 of the taxonomy file.",
                                             domain=_DOMAIN_OF[cat], representation="search vocabulary",
                                             source_type="TAXONOMY_FILE (search vocabulary)",
                                             research_status="SEARCH KEYWORD", source_line=line_no))
            continue
        if mode == "anchors":
            am = re.match(r"^(\d{1,2})\.\s+(.+)$", s)
            if am:
                anchors.append({"rank": int(am.group(1)), "title": am.group(2).strip(), "note": "", "source_line": line_no})
            elif s.startswith("->") and anchors:
                anchors[-1]["note"] = s[2:].strip()
            continue
        if mode == "schema":
            if s.startswith("- "):
                schema_fields.append(s[2:].strip())
            continue
        if mode in ("cross", "summary"):
            continue
        # ---- body sections 1-6
        sm = _SUB_RE.match(s)
        if sm and (_DASHES.match(nxt)):
            sub_code, sub_title, group = sm.group(1), sm.group(2).strip(), None
            continue
        if _DASHES.match(nxt) and s.isupper() and not s.startswith("-"):
            kind = _label_kind(s)
            group, group_line = (kind or "NOTE"), line_no
            if s.startswith("DEFINISI"):
                group = "DEF"
            continue
        if not s.startswith("-") and not s.startswith('"') and s.endswith(":"):
            kind = _label_kind(s)
            if kind:
                group, group_line = kind, line_no
                continue
        if s.startswith("- ") or s.startswith('"'):
            item = s[2:].strip() if s.startswith("- ") else s
            if group in ("TERM", "CONCEPT", None):
                if item.startswith('"'):
                    papers.setdefault(key(), []).append(item.strip('"'))
                else:
                    add_entry(item, "MODERN DIRECTION" if group == "CONCEPT" and "modern" in
                              lines[group_line - 1].lower() else ("CONCEPT" if group == "CONCEPT" else "TERM / ALIAS"),
                              line_no)
            elif group == "METHOD":
                methods.setdefault(key(), []).append(item)
                add_entry(item.split("=")[0].strip(), "METHOD NAME", line_no)
            elif group == "PAPER":
                papers.setdefault(key(), []).append(item.strip('"'))
            elif group in ("NOTE", "DEF"):
                notes.setdefault(key(), []).append(item)
            elif item.startswith('"'):
                papers.setdefault(key(), []).append(item.strip('"'))
            continue
        # free paragraph text
        if group == "DEF":
            section_def.setdefault(key(), []).append(s)
        elif group in ("NOTE", "TERM", "CONCEPT", None):
            notes.setdefault(key(), []).append(s)
        elif group == "PAPER":
            papers.setdefault(key(), []).append(s.strip('"'))
        elif group == "METHOD":
            methods.setdefault(key(), []).append(s)
    if ref_buf:
        refs.append(parse_reference(ref_buf, ref_num, ref_line))

    # ---- attach definitions / papers / methods, de-duplicate, assign ids
    ref_by_title = {_norm(r.title): r for r in refs if r.title}

    def match_paper(title: str) -> str:
        n = _norm(title)
        for t, r in ref_by_title.items():
            if n and (n in t or t in n):
                return f"{title} [{r.ref_id}]"
        return f"{title} [NOT IN SOURCE REFERENCE LIST]"

    generic = {"watermarking", "watermarks", "fingerprints", "fingerprint", "features", "representations", "metode", "modern",
               "dan", "turunan", "related", "but", "different", "the"}
    sub_titles: dict[str, str] = {}
    for e in entries:
        c = e.subcategory.split(".")[0]
        sub_titles.setdefault(c, e.subcategory.split(".", 1)[1] if "." in e.subcategory else "")

    def name_matches(code: str) -> list[str]:
        """References whose title contains the sub-section name (used only when no paper is listed)."""
        out_refs = []
        for part in re.split(r"/|\(", sub_titles.get(code, "")):
            words = [w for w in _norm(part).split() if w not in generic]
            if not words:
                continue
            needle = " ".join(words)
            for t, r in ref_by_title.items():
                if len(needle) >= 4 and re.search(r"\b" + re.escape(needle) + r"\b", t):
                    out_refs.append(f"{r.title} [{r.ref_id}, matched by sub-section name]")
        return list(dict.fromkeys(out_refs))

    seen: set[tuple[str, str]] = set()
    out: list[TaxonomyEntry] = []
    for e in entries:
        code = e.subcategory.split(".")[0]
        sec = code.rstrip("ABCDEFGHIJK") or code
        k = (e.term.lower(), code)
        if k in seen:
            continue
        seen.add(k)
        if not e.definition:
            text_parts = section_def.get(code) or notes.get(code) or section_def.get(sec) or notes.get(sec) or []
            e.definition = " ".join(text_parts)[:900] or CATEGORIES[e.category][2]
        e.paper = [match_paper(p) for p in dict.fromkeys(papers.get(code, []) or papers.get(sec, []))] or name_matches(code)
        e.method = list(dict.fromkeys(methods.get(code, [])))
        e.id = f"TAX-{len(out) + 1:04d}"
        out.append(e)
    return {"entries": out, "references": refs, "anchors": anchors, "record_schema": schema_fields,
            "terminology_notes": terminology_notes}


def build_database(source: Path) -> dict:
    source = Path(source)
    if source.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Taxonomy source file is unexpectedly large; refusing to parse.")
    raw = source.read_bytes()
    parsed = parse_text(raw.decode("utf-8", "replace"))
    counts: dict[str, int] = {}
    for e in parsed["entries"]:
        counts[e.category] = counts.get(e.category, 0) + 1
    return jsonable({
        "schema_version": SCHEMA_VERSION,
        "source": {"file": source.name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                   "language": "Indonesian with English terminology",
                   "note": "Definitions are quoted from the source file; nothing was rewritten. domain/representation are "
                           "derived from the sub-section and listed in derived_fields."},
        "categories": [{"key": k, "code": v[0], "name": v[1], "description": v[2], "entries": counts.get(k, 0)}
                       for k, v in CATEGORIES.items()],
        "separation_rules": SEPARATION_RULES,
        "terminology_notes": parsed["terminology_notes"],
        "record_schema": parsed["record_schema"],
        "anchors": parsed["anchors"],
        "references": parsed["references"],
        "entries": parsed["entries"],
    })


def default_source() -> Path:
    return resource_path("data", "source", SOURCE_NAME)


def default_json() -> Path:
    return resource_path("data", "fingerprint_taxonomy.json")


_CACHE: dict | None = None


def load(force: bool = False) -> dict:
    """Load the taxonomy database (bundled JSON, else parse the bundled source file)."""
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE
    p = default_json()
    if p.is_file():
        db = read_json(p, max_bytes=16 * 1024 * 1024)
    else:
        db = build_database(default_source())
    if not isinstance(db, dict) or not isinstance(db.get("entries"), list):
        raise ValueError("Taxonomy database is malformed")
    _CACHE = db
    return db


def search(db: dict, text: str = "", category: str = "", status: str = "") -> list[dict]:
    t = text.strip().lower()
    out = []
    for e in db.get("entries", []):
        if category and e.get("category") != category:
            continue
        if status and e.get("research_status") != status:
            continue
        if t and t not in " ".join(str(e.get(k, "")) for k in ("term", "alias", "subcategory", "definition", "method",
                                                                    "paper")).lower():
            continue
        out.append(e)
    return out


def write_database(source: Path, dest: Path) -> dict:
    db = build_database(source)
    write_json(dest, db)
    return db
