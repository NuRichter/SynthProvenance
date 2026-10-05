"""Tests for the taxonomy database, the research library and their bundled JSON."""
from __future__ import annotations

import json
from pathlib import Path

from app.research import library as L
from app.research import taxonomy as T

ROOT = Path(__file__).resolve().parents[1]


def test_taxonomy_json_is_bundled_and_consistent():
    p = ROOT / "data" / "fingerprint_taxonomy.json"
    assert p.is_file()
    db = json.loads(p.read_text(encoding="utf-8"))
    assert db["schema_version"]
    assert len(db["entries"]) >= 100               # the UI must show 100+ entries when supported
    assert len(db["references"]) == 21              # the 21 APA references in the source file
    cats = {c["key"] for c in db["categories"]}
    assert {"INTRINSIC_PASSIVE", "CAUSAL", "SPECTRAL", "PROACTIVE_WATERMARK", "DETECTOR_REPRESENTATION",
            "C2PA_PROVENANCE"} <= cats
    # the separation rules are present and the families are kept distinct
    assert any("C2PA" in r for r in db["separation_rules"])
    for e in db["entries"][:50]:
        assert e["term"] and e["category"] in cats and e["source_line"] > 0


def test_taxonomy_rebuilds_from_source_deterministically():
    src = ROOT / "data" / "source" / T.SOURCE_NAME
    assert src.is_file()
    a = T.build_database(src)
    b = T.build_database(src)
    assert len(a["entries"]) == len(b["entries"]) >= 100
    assert a["source"]["sha256"] == b["source"]["sha256"]


def test_taxonomy_search_filters_by_category():
    db = T.load()
    spectral = T.search(db, "", "SPECTRAL")
    assert spectral and all(e["category"] == "SPECTRAL" for e in spectral)
    fft = T.search(db, "fourier")
    assert fft


def test_library_is_bundled_and_verified():
    items = L.all_items()
    assert len(items) >= 60
    assert all(it.get("verification_status") in ("VERIFIED", "VERIFIED_WITH_CORRECTIONS") for it in items)
    assert all(it.get("apa7") and it.get("bibtex") for it in items)
    tax = [it for it in items if it.get("origin") == "TAXONOMY_FILE"]
    assert len(tax) == 21


def test_library_exports_apa_bibtex_cff():
    res = L.search("frank")
    assert "Frank" in L.to_apa7(res)
    assert "@" in L.to_bibtex(res)
    cff = L.citation_cff()
    assert cff.startswith("cff-version:") and "SynthProvenance" in cff


def test_no_fabricated_doi_placeholders():
    for it in L.all_items():
        doi = it.get("doi")
        if doi:
            assert not doi.lower().startswith(("10.0000", "xx", "todo"))
            assert "example" not in doi.lower()
