"""SynthID method registry: every verification pathway with its honest status.

A method is listed with the status it actually has on this machine. Nothing is
promoted to a detector without a validated engine behind it. Methods named in
the research brief that SynthProvenance deliberately does not implement are
listed as UNAVAILABLE / NOT IMPLEMENTED with the reason, so the scope is
visible in the UI and in exported papers.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from app.utils.serialization import jsonable

SCIENTIFIC_STATUSES = ("AUTHORITATIVE", "RESEARCH", "EXPERIMENTAL", "UNVERIFIED", "FAILED", "UNAVAILABLE")
OUT_OF_SCOPE = ("Not implemented. Out of scope by design: SynthProvenance does not estimate, reconstruct or attack "
                "embedded watermark signals (see docs/SYNTHID_RESEARCH_LAB.md).")
NOT_A_SYNTHID_METHOD = ("Not a SynthID method. Descriptive frequency/noise statistics remain available in the Forensic "
                        "Inspector, labelled as descriptive only.")
IMAGE_FORMATS = ("JPEG", "PNG", "WEBP", "TIFF", "BMP", "GIF")


@dataclass(frozen=True)
class MethodSpec:
    method_id: str
    method_name: str
    description: str
    source: str
    version: str
    license: str
    local_only: bool
    requires_gpu: bool
    requires_training: bool
    requires_reference_images: bool
    input_formats: tuple[str, ...]
    output: str
    scientific_status: str
    validation_status: str
    research_maturity: str
    dataset_requirement: str = "none"
    implemented: bool = True
    online: bool = False
    note: str = ""
    links: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return jsonable(self)

    @property
    def location(self) -> str:
        return "ONLINE (user-operated)" if self.online else "LOCAL"


def _excluded(mid: str, name: str, reason: str = OUT_OF_SCOPE) -> MethodSpec:
    return MethodSpec(mid, name, reason, "-", "-", "-", True, False, False, False, (), "none", "UNAVAILABLE",
                      "NOT IMPLEMENTED", "none", implemented=False, note=reason)


BASE_METHODS: tuple[MethodSpec, ...] = (
    MethodSpec("SID-M0", "BASELINE",
               "Original image, unmodified: metadata, C2PA, pixel integrity and hashing. Characterises the provenance "
               "layers. It does not measure SynthID.",
               "SynthProvenance (native)", "built-in", "see LICENSE", True, False, False, False, IMAGE_FORMATS,
               "layer states, hashes", "RESEARCH", "VALIDATED BY TEST SUITE", "PRODUCTION"),
    MethodSpec("SID-M1", "SUPPORTED DETECTION",
               "Local SynthID verification engine plugged in through the tools/synthid contract. Reports DETECTED, "
               "NOT DETECTED, POSSIBLY DETECTED, UNKNOWN or UNAVAILABLE exactly as the engine states.",
               "researcher-provided engine (tools/README.md)", "engine-reported", "engine-specific", True, False, False,
               False, IMAGE_FORMATS, "verification state + confidence", "UNAVAILABLE", "NO ENGINE", "DEPENDS ON ENGINE",
               note="No compatible local SynthID image verifier is publicly available. Status changes only when an "
                    "engine is configured, and becomes validated only through a recorded benchmark."),
    MethodSpec("SID-ON1", "OFFICIAL ONLINE VERIFICATION",
               "Google's own verification pathways (see Online Verification). Opened in the default browser only after "
               "explicit confirmation. SynthProvenance never uploads the image; the researcher does so manually and "
               "records the reported result.",
               "Google (official)", "service-defined", "service terms", False, False, False, False, IMAGE_FORMATS,
               "user-recorded result", "AUTHORITATIVE", "EXTERNAL (not verified by SynthProvenance)", "PRODUCTION SERVICE",
               online=True),
    _excluded("SID-X2", "EXPERIMENTAL FINGERPRINT"),
    _excluded("SID-X3", "MULTI-SCALE RESIDUAL"),
    _excluded("SID-X4", "WAVELET", NOT_A_SYNTHID_METHOD),
    _excluded("SID-X5", "FFT", NOT_A_SYNTHID_METHOD),
    _excluded("SID-X6", "DCT", NOT_A_SYNTHID_METHOD),
    _excluded("SID-X7", "ROBUST PCA"),
    _excluded("SID-X8", "PATCH CONSENSUS"),
    _excluded("SID-X9", "CROSS-IMAGE"),
    _excluded("SID-X10", "ENSEMBLE"),
    _excluded("SID-X11", "SURROGATE RED-TEAM"),
    _excluded("SID-X12", "RECONSTRUCTION"),
)
REQUIRED_FIELDS = ("method_id", "method_name", "source", "version", "license", "local_only", "requires_gpu",
                   "requires_training", "requires_reference_images", "input_formats", "output", "scientific_status",
                   "validation_status")


class MethodRegistry:
    def __init__(self, engine_status: dict | None = None, benchmark: dict | None = None) -> None:
        self._methods = {m.method_id: m for m in BASE_METHODS}
        self.update_engine(engine_status, benchmark)

    def update_engine(self, engine_status: dict | None, benchmark: dict | None = None) -> None:
        """Reflect the configured local engine (and its latest benchmark) in SID-M1."""
        st = engine_status or {}
        m = self._methods["SID-M1"]
        if not st.get("available"):
            self._methods["SID-M1"] = replace(m, scientific_status="UNAVAILABLE", validation_status="NO ENGINE",
                                              source=m.source, version="-")
            return
        validation, status = "NOT BENCHMARKED", "UNVERIFIED"
        if benchmark and benchmark.get("status") == "COMPLETE":
            validation = (f"BENCHMARKED {benchmark.get('run_id', '')}: AUC {benchmark.get('auc_text', '-')}, "
                          f"n={benchmark.get('n_scored', 0)}")
            status = "RESEARCH"
        self._methods["SID-M1"] = replace(m, scientific_status=status, validation_status=validation,
                                          source=f"{st.get('origin') or 'configured'}: {st.get('command', '')}"[:200],
                                          version="engine-reported")

    def all(self) -> list[MethodSpec]:
        return list(self._methods.values())

    def implemented(self) -> list[MethodSpec]:
        return [m for m in self._methods.values() if m.implemented]

    def get(self, method_id: str) -> MethodSpec:
        if method_id not in self._methods:
            raise KeyError(f"Unknown SynthID method {method_id!r}")
        return self._methods[method_id]

    def by_name(self, name: str) -> MethodSpec:
        for m in self._methods.values():
            if m.method_name == name:
                return m
        raise KeyError(f"Unknown SynthID method {name!r}")

    def to_rows(self) -> list[list]:
        return [[m.method_id, m.method_name, m.scientific_status, m.validation_status, m.location,
                 "yes" if m.requires_gpu else "no", m.dataset_requirement, m.research_maturity, m.license, m.source]
                for m in self._methods.values()]


def validate_spec(m: MethodSpec) -> list[str]:
    problems = [f"{m.method_id}: missing {f}" for f in REQUIRED_FIELDS if getattr(m, f, None) in (None, "")]
    if m.scientific_status not in SCIENTIFIC_STATUSES:
        problems.append(f"{m.method_id}: unknown scientific status {m.scientific_status!r}")
    if not m.implemented and m.scientific_status != "UNAVAILABLE":
        problems.append(f"{m.method_id}: unimplemented methods must be UNAVAILABLE")
    if m.scientific_status == "AUTHORITATIVE" and not m.online:
        problems.append(f"{m.method_id}: only official external pathways may be AUTHORITATIVE")
    return problems
