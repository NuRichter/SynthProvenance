"""Experiment and transformation records (persisted as JSON)."""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.utils.serialization import jsonable


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_experiment_id(sequence: int = 1, when: datetime | None = None) -> str:
    """Experiment identifier, e.g. SPX-2026-0927-000001 (per-day sequence)."""
    when = when or datetime.now(timezone.utc)
    return f"SPX-{when:%Y}-{when:%m%d}-{int(sequence):06d}"


def random_suffix() -> str:
    return secrets.token_hex(2).upper()


@dataclass
class TransformationRecord:
    transformation_id: str
    experiment_id: str
    operation: str
    label: str
    timestamp: str
    parameters: dict
    status: str = "PENDING"  # PENDING / COMPLETE / FAILED / REFUSED
    error: str = ""
    input_path: str = ""
    output_path: str = ""
    input_sha256: str = ""
    output_sha256: str = ""
    input_dimensions: tuple[int, int] | None = None
    output_dimensions: tuple[int, int] | None = None
    output_format: str = ""
    pixel_metrics: dict = field(default_factory=dict)
    metadata_differences: list[dict] = field(default_factory=list)
    metadata_group_states: dict = field(default_factory=dict)
    provenance_differences: dict = field(default_factory=dict)
    signal_before: str = ""
    signal_after: str = ""
    actions: list[str] = field(default_factory=list)
    output_analysis: dict = field(default_factory=dict)
    layers: list[dict] = field(default_factory=list)
    synthid_before: dict = field(default_factory=dict)
    synthid_after: dict = field(default_factory=dict)
    steps: list[dict] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    source_condition: str = "ORIGINAL"
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return jsonable(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TransformationRecord":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        for key in ("input_dimensions", "output_dimensions"):
            if isinstance(known.get(key), list):
                known[key] = tuple(known[key])
        return cls(**known)


@dataclass
class ExternalClassification:
    platform: str
    label: str
    observed_on: str
    note: str = ""
    layer: str = "PLATFORM"  # PLATFORM or SYNTHID
    condition: str = "ORIGINAL"  # ORIGINAL or a transformation id
    tier: str = "EXTERNAL PLATFORM CLASSIFICATION (user-recorded, unverified)"


@dataclass
class Experiment:
    experiment_id: str
    created: str
    app_version: str
    objective: str = (
        "Characterise the observable C2PA provenance layer, the SynthID embedded-signal layer (where a local "
        "verification engine exists), ordinary metadata, file encoding and pixel integrity of the input image "
        "under controlled, documented transformations."
    )
    notes: str = ""
    input_name: str = ""
    original_path: str = ""
    workspace: str = ""
    baseline: dict = field(default_factory=dict)
    statistics: dict = field(default_factory=dict)
    transformations: list[TransformationRecord] = field(default_factory=list)
    external_classifications: list[ExternalClassification] = field(default_factory=list)
    environment: dict = field(default_factory=dict)
    synthid_baseline: dict = field(default_factory=dict)
    research_environment: str = "Faculty of Computer Science / Insyide Innovations Lab / NuRichter Workspace"
    status: str = "OPEN"

    def next_transformation_id(self) -> str:
        return f"T{len(self.transformations) + 1:03d}"

    def to_dict(self) -> dict:
        return jsonable(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Experiment":
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        known["transformations"] = [TransformationRecord.from_dict(t) for t in d.get("transformations", [])]
        known["external_classifications"] = [
            ExternalClassification(**{k: v for k, v in e.items() if k in ExternalClassification.__dataclass_fields__})
            for e in d.get("external_classifications", [])
        ]
        return cls(**known)
