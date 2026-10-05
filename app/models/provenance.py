"""Provenance and AI-content-signal records."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.utils.serialization import jsonable

SIGNAL_OBSERVED = "OBSERVED"
SIGNAL_NOT_OBSERVED = "NOT OBSERVED"
SIGNAL_UNKNOWN = "UNKNOWN"

TIER_EVIDENCE = "OBSERVABLE EVIDENCE"
TIER_INTERPRETATION = "EXPERIMENTAL INTERPRETATION"
TIER_EXTERNAL = "EXTERNAL PLATFORM CLASSIFICATION"
TIER_UNKNOWN = "UNKNOWN INFORMATION"

NOT_OBSERVED_MEANING = (
    "No observable AI-content provenance signal was detected under the selected experimental condition. "
    "This does not establish that the image is human-created."
)
NO_C2PA_TEXT = "No observable C2PA Content Credential detected."

# Layer states used by the Provenance Separation Experiment.
LS_DETECTED = "DETECTED"
LS_NOT_DETECTED = "NOT DETECTED"
LS_REMOVED = "REMOVED"
LS_PERSISTED = "PERSISTED"
LS_ALTERED = "ALTERED"
LS_INVALID = "INVALID"
LS_UNKNOWN = "UNKNOWN"
LS_UNAVAILABLE = "UNAVAILABLE"
LS_NOT_TESTABLE = "NOT TESTABLE"
LAYER_STATES = (LS_DETECTED, LS_NOT_DETECTED, LS_REMOVED, LS_PERSISTED, LS_ALTERED, LS_INVALID, LS_UNKNOWN,
                LS_UNAVAILABLE, LS_NOT_TESTABLE)
LAYER_C2PA = "C2PA"
LAYER_SYNTHID = "SynthID"
LAYER_METADATA = "Ordinary metadata"
LAYER_PIXELS = "Image pixels"
LAYER_ENCODING = "File encoding"
LAYER_STRUCTURE = "File structure"
LAYER_EXTERNAL = "External platform classification"
LAYER_KIND = {
    LAYER_C2PA: "PROVENANCE / CONTENT CREDENTIAL LAYER",
    LAYER_SYNTHID: "EMBEDDED SIGNAL LAYER",
    LAYER_METADATA: "DESCRIPTIVE METADATA LAYER",
    LAYER_PIXELS: "PIXEL ARRAY",
    LAYER_ENCODING: "CODEC / COMPRESSION",
    LAYER_STRUCTURE: "CONTAINER STRUCTURE",
    LAYER_EXTERNAL: "EXTERNAL (USER-RECORDED, UNVERIFIED)",
}


@dataclass
class SignalEvidence:
    tier: str
    source: str
    field: str
    value: str
    counted: bool
    note: str = ""


@dataclass
class AISignal:
    state: str
    statement: str
    condition: str = "baseline"
    evidence: list[SignalEvidence] = field(default_factory=list)
    interpretations: list[SignalEvidence] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return jsonable(self)


@dataclass
class C2PAAction:
    action: str
    software_agent: str = ""
    digital_source_type: str = ""
    when: str = ""
    description: str = ""
    manifest: str = ""


@dataclass
class C2PAIngredient:
    title: str
    format: str = ""
    relationship: str = ""
    instance_id: str = ""
    has_manifest: bool = False
    manifest: str = ""


@dataclass
class C2PAManifest:
    label: str
    claim_version: str = ""
    claim_generator: str = ""
    title: str = ""
    format: str = ""
    instance_id: str = ""
    signature_algorithm: str = ""
    signature_present: bool = False
    issuer: str = ""
    subject: str = ""
    cert_not_before: str = ""
    cert_not_after: str = ""
    timestamp_token: bool = False
    assertions: list[dict] = field(default_factory=list)
    actions: list[C2PAAction] = field(default_factory=list)
    ingredients: list[C2PAIngredient] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class C2PAReport:
    present: bool
    state: str  # ItemState value
    summary: str
    location: str = ""
    store_bytes: int = 0
    store_sha256: str = ""
    manifests: list[C2PAManifest] = field(default_factory=list)
    active_manifest: str = ""
    hard_binding: str = "NOT APPLICABLE"
    hard_binding_detail: str = ""
    validity: str = "NOT VALIDATED"
    validity_detail: str = ""
    trust: str = "UNKNOWN"
    engine: str = "native JUMBF/CBOR parser"
    engine_output: dict | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def active(self) -> C2PAManifest | None:
        for m in self.manifests:
            if m.label == self.active_manifest:
                return m
        return self.manifests[-1] if self.manifests else None

    def to_dict(self) -> dict:
        return jsonable(self)
