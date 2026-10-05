"""ONLINE OFFICIAL VERIFICATION fallback (user-controlled, OFF by default).

No public machine-readable SynthID image-verification API was found (see
docs/SYNTHID_RESEARCH_SOURCES.md), so SynthProvenance never sends an image
anywhere. This module only:

1. lists Google's official user-facing verification pathways (allow-listed
   https hosts, no undocumented endpoints);
2. builds an explicit plan showing the exact destination, the file and its
   SHA-256 before anything happens;
3. after the researcher confirms, asks the operating system to open the
   destination in the default browser and reveals the file in Explorer.

The researcher uploads manually, under the service's own sign-in, terms and
access controls, and records the reported result as an unverified external
entry. The LOCAL-ONLY network guard stays active for SynthProvenance itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

from app.core.hashing import sha256_file
from app.models.experiment import utc_now
from app.utils.serialization import jsonable

ALLOWED_HOSTS = frozenset({"gemini.google.com", "support.google.com", "deepmind.google"})
NO_UPLOAD = ("SynthProvenance will NOT upload this image. It asks Windows to open the destination in your default browser "
             "and shows the file in Explorer. Any upload is your own manual action, under the service's sign-in, terms "
             "and access controls.")


class OnlinePolicyError(PermissionError):
    pass


@dataclass(frozen=True)
class Destination:
    dest_id: str
    name: str
    operator: str
    url: str
    access: str
    upload_method: str = "Manual upload by the researcher in the browser"
    machine_api: bool = False
    notes: str = ""
    source_ids: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return jsonable(self)


DESTINATIONS: tuple[Destination, ...] = (
    Destination("GEMINI-APP", "Gemini app: verify Google AI content", "Google", "https://gemini.google.com/",
                "Personal or qualified Workspace Google account. Add the file, then ask whether it was created or edited "
                "by Google AI. About 10 image checks per rolling 24 h, one file per check, 100 MB maximum (as of "
                "2026-10-02).",
                notes="Recognises only content created or edited with Google AI tools. A 'not detected' answer does not "
                      "mean human-made; other AI systems are not covered.",
                source_ids=("GOOGLE-GEMINI-HELP", "GOOGLE-GEMINI-IMAGE-VERIFY")),
    Destination("GEMINI-HELP", "Gemini help: how verification works (instructions only)", "Google",
                "https://support.google.com/gemini/answer/16722517",
                "Public help page: steps, limits and the meaning of results. Opening it involves no image.",
                source_ids=("GOOGLE-GEMINI-HELP",)),
    Destination("SYNTHID-INFO", "SynthID (DeepMind): Detector portal information and access", "Google DeepMind",
                "https://deepmind.google/models/synthid/",
                "The SynthID Detector portal is limited to approved journalists and verification professionals "
                "(onboarding form). Its URL is not public; this page links to current access options.",
                source_ids=("DEEPMIND-SYNTHID", "GOOGLE-SYNTHID-DETECTOR", "SYNTHID-DETECTOR-ONBOARDING")),
)
NOT_INTEGRATED = [
    ("Google AI Content Detection API (Gemini Enterprise Agent Platform)",
     "Private Preview for trusted partners (application form). Not integrated: it would require uploading images to a "
     "cloud service, and whether it reads SynthID specifically is unverified."),
    ("Vertex AI 'Verify an image watermark' (Imagen)", "Documentation now returns HTTP 404; treated as retired."),
]


def destination(dest_id: str) -> Destination:
    for d in DESTINATIONS:
        if d.dest_id == dest_id:
            return d
    raise OnlinePolicyError(f"Unknown verification destination {dest_id!r}")


def check_destination(d: Destination) -> None:
    parts = urlsplit(d.url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS or parts.username or parts.password:
        raise OnlinePolicyError(f"Destination {d.dest_id} is not an allow-listed official https URL: {d.url}")
    if d.machine_api:
        raise OnlinePolicyError("Machine-to-machine upload is not supported; verification is browser-based only.")


@dataclass
class OpenPlan:
    dest_id: str
    name: str
    url: str
    image_path: str
    image_name: str
    image_sha256: str
    statement: str = NO_UPLOAD
    created: str = ""

    def to_dict(self) -> dict:
        return jsonable(self)

    def confirmation_text(self) -> str:
        return (f"DESTINATION: {self.name}\nURL: {self.url}\n\nFILE: {self.image_path}\nSHA-256: {self.image_sha256}\n\n"
                f"{self.statement}\n\nOpen the destination now?")


class OnlineGate:
    """Session-scoped switch. Starts OFF; enabling and every open need explicit confirmation."""

    def __init__(self, opener: Callable[[str], bool] | None = None, reveal: Callable[[Path], None] | None = None) -> None:
        self.enabled = False
        self._opener, self._reveal = opener, reveal
        self.history: list[dict] = []

    def enable(self, confirmed: bool) -> None:
        if confirmed is not True:
            raise OnlinePolicyError("Online verification mode requires explicit confirmation.")
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False

    def plan(self, dest_id: str, image_path: Path) -> OpenPlan:
        if not self.enabled:
            raise OnlinePolicyError("Online verification is OFF (LOCAL MODE). Enable it explicitly first.")
        d = destination(dest_id)
        check_destination(d)
        p = Path(image_path)
        if not p.is_file():
            raise OnlinePolicyError(f"Image not found: {p}")
        return OpenPlan(d.dest_id, d.name, d.url, str(p), p.name, sha256_file(p), created=utc_now())

    def execute(self, plan: OpenPlan, consent: bool) -> dict:
        if not self.enabled:
            raise OnlinePolicyError("Online verification is OFF (LOCAL MODE).")
        if consent is not True:
            raise OnlinePolicyError("No explicit consent given; nothing was opened.")
        check_destination(destination(plan.dest_id))
        if self._opener is None:
            raise OnlinePolicyError("No browser opener is available in this context.")
        opened = bool(self._opener(plan.url))
        if self._reveal is not None:
            self._reveal(Path(plan.image_path))
        entry = {**plan.to_dict(), "opened_utc": utc_now(), "browser_opened": opened, "uploaded_by_synthprovenance": False}
        self.history.append(entry)
        return entry
