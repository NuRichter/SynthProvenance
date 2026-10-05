"""Research literature library.

Loads ``data/research_library.json`` (verified references: 21 from the taxonomy file,
marked ``TAXONOMY_FILE``, plus validated EXTERNAL RESEARCH ADDITION entries). Every
entry was checked against DOI/arXiv/CVF/PMLR and carries a ``verification_status``
(VERIFIED or VERIFIED_WITH_CORRECTIONS, with the original text and the correction kept
in ``verification_note``). Nothing is fabricated: entries that could not be verified are
not included, and the loader does not invent fields.

The library backs the Research Foundations ("HERE OUR HERO") panel and the searchable
library view, and exports APA 7, BibTeX and CITATION.cff.
"""
from __future__ import annotations

from app.utils.paths import resource_path
from app.utils.serialization import read_json

FILTERS = ("fingerprint_category", "generator_family", "domain", "code_availability", "local_reproducibility", "origin",
           "year", "verification_status")
DISPLAY_COLUMNS = ["ID", "Year", "Title", "Venue", "Category", "Generator", "Code", "Local", "Origin", "Verified"]


def default_json():
    return resource_path("data", "research_library.json")


_CACHE: dict | None = None


def load(force: bool = False) -> dict:
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE
    db = read_json(default_json(), max_bytes=16 * 1024 * 1024)
    items = db.get("items", [])
    for it in items:
        it.setdefault("origin", "EXTERNAL RESEARCH ADDITION")
    _CACHE = {"accessed": db.get("accessed", ""), "items": items}
    return _CACHE


def all_items() -> list[dict]:
    return load()["items"]


def options(field: str) -> list:
    vals = {it.get(field) for it in all_items() if it.get(field) not in (None, "")}
    return sorted(vals, key=lambda v: (str(type(v)), v))


def search(text: str = "", filters: dict | None = None) -> list[dict]:
    t = text.strip().lower()
    filters = {k: v for k, v in (filters or {}).items() if v not in (None, "", "All")}
    out = []
    for it in all_items():
        if any(str(it.get(k)) != str(v) for k, v in filters.items()):
            continue
        if t and t not in " ".join(str(it.get(k, "")) for k in ("title", "authors", "venue", "key_idea",
                                                                 "research_question", "method_category", "doi",
                                                                 "arxiv")).lower():
            continue
        out.append(it)
    return sorted(out, key=lambda i: (-(i.get("year") or 0), str(i.get("title"))))


def rows(items: list[dict]) -> list[list]:
    return [[it.get("id"), it.get("year"), it.get("title"), it.get("venue", "")[:60],
             it.get("fingerprint_category"), it.get("generator_family"), it.get("code_availability"),
             it.get("local_reproducibility"), it.get("origin", "").split()[0], it.get("verification_status")]
            for it in items]


def to_apa7(items: list[dict]) -> str:
    return "\n\n".join(it.get("apa7", "").strip() for it in items if it.get("apa7"))


def to_bibtex(items: list[dict]) -> str:
    return "\n\n".join(it.get("bibtex", "").strip() for it in items if it.get("bibtex"))


def citation_cff() -> str:
    """A CITATION.cff referencing the software and its most important research foundations."""
    from app import __version__
    items = [it for it in all_items() if it.get("origin") == "TAXONOMY_FILE"]
    lines = ["cff-version: 1.2.0",
             "message: \"If you use SynthProvenance in research, please cite the software and the relevant foundational works.\"",
             "title: SynthProvenance", f"version: {__version__}",
             "abstract: \"Scientific AI Content Signal & Image Provenance Laboratory: a local-first research workstation "
             "for measuring C2PA provenance, metadata, pixel integrity and candidate generative-image fingerprints, with "
             "a controlled surrogate watermark ground-truth laboratory.\"",
             "authors:", "  - name: \"NuRichter Workspace / Insyide Innovations\"",
             "license: see LICENSE", "references:"]
    for it in items:
        au = it.get("authors") or []
        lines.append("  - type: article")
        lines.append(f"    title: \"{_q(it.get('title',''))}\"")
        if it.get("year"):
            lines.append(f"    year: {it['year']}")
        if au:
            lines.append("    authors:")
            for a in au:
                fam = a.split(",")[0].strip()
                giv = a.split(",", 1)[1].strip() if "," in a else ""
                lines.append(f"      - family-names: \"{_q(fam)}\"" + (f"\n        given-names: \"{_q(giv)}\"" if giv else ""))
        if it.get("doi"):
            lines.append(f"    doi: {it['doi']}")
    return "\n".join(lines) + "\n"


def _q(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace("\"", "\\\"")


def catalog() -> dict:
    """Methods / datasets / tools catalogue from the implementation survey (bundled, offline)."""
    try:
        return read_json(resource_path("data", "research_catalog.json"), max_bytes=8 * 1024 * 1024)
    except Exception:  # noqa: BLE001
        return {"methods": [], "datasets": [], "tools": []}


def foundations() -> list[dict]:
    """The anchor works for the Research Foundations panel: taxonomy items first, newest external next."""
    items = all_items()
    tax = [i for i in items if i.get("origin") == "TAXONOMY_FILE"]
    ext = sorted((i for i in items if i.get("origin") != "TAXONOMY_FILE"), key=lambda i: -(i.get("year") or 0))
    return tax + ext
