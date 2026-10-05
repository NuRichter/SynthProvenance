"""Curated SynthID research-source catalogue (offline).

Source discovery reads the bundled catalogue ``config/synthid_sources.json``
and, when present, a researcher catalogue ``<workspace>/synthid_sources.json``.
SynthProvenance never fetches these URLs: they were consulted by the
researcher and are recorded with their access date and verification status.
Every entry is validated before it is shown or exported.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, fields
from pathlib import Path
from urllib.parse import urlsplit

from app.utils.paths import resource_path
from app.utils.serialization import jsonable

KINDS = ("OFFICIAL", "PAPER", "STANDARD", "DATASET", "OPEN SOURCE", "THIRD-PARTY")
STATUSES = ("VERIFIED", "UNVERIFIED", "NOT EVALUATED", "OUTDATED")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ID = re.compile(r"^[A-Z0-9][A-Z0-9_.-]{1,40}$")
MAX_SOURCES = 500


@dataclass
class ResearchSource:
    source_id: str
    title: str
    url: str
    kind: str
    publisher: str
    accessed: str
    status: str
    relevance: str
    license: str = ""
    notes: str = ""
    origin: str = "bundled"

    def to_dict(self) -> dict:
        return jsonable(self)

    @classmethod
    def from_dict(cls, d: dict, origin: str = "bundled") -> "ResearchSource":
        known = {f.name: str(d.get(f.name, "") or "") for f in fields(cls) if f.name != "origin"}
        return cls(**known, origin=origin)


def validate_source(s: ResearchSource) -> list[str]:
    p: list[str] = []
    if not _ID.match(s.source_id or ""):
        p.append(f"invalid source_id {s.source_id!r}")
    if not s.title.strip():
        p.append("empty title")
    parts = urlsplit(s.url or "")
    if parts.scheme != "https":
        p.append("URL must use https")
    if not parts.hostname:
        p.append("URL has no host")
    if parts.username or parts.password:
        p.append("URL must not contain credentials")
    if s.kind not in KINDS:
        p.append(f"unknown kind {s.kind!r}")
    if s.status not in STATUSES:
        p.append(f"unknown status {s.status!r}")
    if not _DATE.match(s.accessed or ""):
        p.append(f"accessed date must be YYYY-MM-DD, got {s.accessed!r}")
    if not s.relevance.strip():
        p.append("empty relevance note")
    return [f"{s.source_id or '?'}: {x}" for x in p]


def _read(path: Path, origin: str) -> tuple[list[ResearchSource], list[str]]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [], [f"{path.name}: unreadable catalogue ({exc})"]
    items = raw.get("sources") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return [], [f"{path.name}: 'sources' must be a list"]
    return [ResearchSource.from_dict(d, origin) for d in items[:MAX_SOURCES] if isinstance(d, dict)], []


def bundled_catalogue_path() -> Path:
    return resource_path("config", "synthid_sources.json")


def discover(workspace_root: Path | None = None, catalogue: Path | None = None) -> tuple[list[ResearchSource], list[str]]:
    """Load and validate every catalogue. Returns (valid sources, problems); invalid entries are excluded."""
    found, problems = _read(catalogue or bundled_catalogue_path(), "bundled")
    if workspace_root is not None and (Path(workspace_root) / "synthid_sources.json").is_file():
        extra, pr = _read(Path(workspace_root) / "synthid_sources.json", "workspace")
        found += extra
        problems += pr
    out, seen = [], set()
    for s in found:
        errs = validate_source(s)
        if s.source_id in seen:
            errs.append(f"{s.source_id}: duplicate source_id")
        if errs:
            problems += errs
            continue
        seen.add(s.source_id)
        out.append(s)
    return out, problems


def to_rows(sources: list[ResearchSource]) -> list[list]:
    return [[s.source_id, s.kind, s.status, s.title, s.publisher, s.accessed, s.url, s.relevance] for s in sources]


def to_markdown(sources: list[ResearchSource]) -> str:
    lines = ["| ID | Kind | Status | Title | Accessed | URL | Relevance |", "|---|---|---|---|---|---|---|"]
    for s in sources:
        cells = [s.source_id, s.kind, s.status, s.title, s.accessed, s.url, s.relevance]
        lines.append("| " + " | ".join(c.replace("|", "/") for c in cells) + " |")
    return "\n".join(lines) + "\n"
