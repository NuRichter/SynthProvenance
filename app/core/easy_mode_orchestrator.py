"""Easy Mode orchestrator: one RUN button over the complete local research engine.

Easy Mode is an operational facade. It contains no scientific implementation of its own:
every stage calls the engines Expert Mode uses (the metadata / C2PA engine, the SynthID
analyzer, the fingerprint method runner, the separation engine, the format-conversion
transformation with pixel-integrity verification, and the report renderers). This module
adds only orchestration:

* a fixed, deterministic 12-stage pipeline (:data:`STAGES`);
* a method suitability engine (:meth:`EasyModeOrchestrator.plan`) that decides for every
  registry method whether it applies to the current input, and records why not
  (model not installed, data not present, incompatible format, Expert-only study, ...);
* graceful fallback: a failing method is recorded and the run continues. Only an
  undecodable source, a failed output, or a failed integrity check stops the run;
* a candidate evaluator that ranks reconstruction candidates and never promotes one that
  fails the validation criteria (``NO VALIDATED RECONSTRUCTION`` is a valid outcome);
* the Easy research report (``app.services.easy_report``).

Two arms are kept strictly apart and labelled in every record:

REAL IMAGE OBSERVATION
    The user's image. Observation only: metadata, C2PA, SynthID status from a local engine,
    descriptive fingerprint statistics. Nothing is estimated out of, or removed from, the
    real image's pixels. The result image is a pixel-preserving re-encoding of the decoded
    original in the chosen format, verified against it.

CONTROLLED SURROGATE RESEARCH
    A keyed local surrogate signal is embedded into a bounded copy of the image (the clean
    host), so the ground truth is known. Separation / reconstruction methods are scored
    against it. These are measurements in the report; they never become the result image.

Nothing here touches the network. The source file is hashed before and after the run.
"""
from __future__ import annotations

import os
import re
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from app import __version__
from app.analyzers.synthid_analyzer import analyze_synthid
from app.core import audit_engine as A
from app.core.hashing import file_hashes, pixel_hash, sha256_file
from app.core.image_loader import open_image_bytes, read_file_bytes, to_array
from app.core.metadata_engine import analyze_bytes
from app.models.experiment import utc_now
from app.research import metrics as M
from app.research import runner as RUN
from app.research import surrogate as SUR
from app.research.imaging import as_float, display_limit, luminance, map_image
from app.research.methods import Method, MethodRegistry
from app.utils.serialization import jsonable, write_json
from app.utils.validation import sniff_format

Progress = Callable[[int, str], None]

ARM_REAL = "REAL IMAGE OBSERVATION"
ARM_CONTROLLED = "CONTROLLED SURROGATE RESEARCH"
PHASES = ("Preparing", "Analyzing", "Reconstructing", "Validating", "Finalizing")


@dataclass(frozen=True)
class EasyModePipelineStage:
    number: int
    key: str
    label: str
    phase: str      # one of PHASES: the only progress word the Easy UI shows
    weight: int     # share of the progress bar


STAGES: tuple[EasyModePipelineStage, ...] = (
    EasyModePipelineStage(1, "safety", "File safety check", "Preparing", 2),
    EasyModePipelineStage(2, "baseline", "Baseline hash & image decode", "Preparing", 4),
    EasyModePipelineStage(3, "metadata", "Metadata analysis", "Preparing", 5),
    EasyModePipelineStage(4, "c2pa", "C2PA analysis / provenance separation", "Analyzing", 3),
    EasyModePipelineStage(5, "synthid", "SynthID status (local verification only)", "Analyzing", 2),
    EasyModePipelineStage(6, "fingerprint", "Fingerprint taxonomy matching & analysis", "Analyzing", 36),
    EasyModePipelineStage(7, "signal", "Signal estimation", "Analyzing", 10),
    EasyModePipelineStage(8, "separation", "Controlled separation / reconstruction", "Reconstructing", 22),
    EasyModePipelineStage(9, "consensus", "Multi-method consensus", "Validating", 2),
    EasyModePipelineStage(10, "validation", "Candidate & integrity validation", "Validating", 2),
    EasyModePipelineStage(11, "output", "Output generation", "Finalizing", 8),
    EasyModePipelineStage(12, "report", "Report generation", "Finalizing", 4),
)
STAGE_BY_KEY = {s.key: s for s in STAGES}

# Easy output format -> format_conversion parameters. No compression controls are exposed in Easy Mode: lossless
# containers are written losslessly and JPEG (lossy by definition) at a fixed high quality. ICC is kept and EXIF/XMP
# are carried verbatim, so AI-content declarations in ordinary metadata survive; a C2PA manifest cannot stay valid for
# re-encoded bytes and is never copied (the transform engine records this).
OUTPUT_FORMATS = ("PNG", "JPG", "WEBP", "TIFF", "BMP")
OUTPUT_ENCODING = {
    "PNG": {"format": "PNG", "compression": "LOSSLESS"},
    "JPG": {"format": "JPEG", "compression": "LOSSY", "quality": 95},
    "WEBP": {"format": "WEBP", "compression": "LOSSLESS"},
    "TIFF": {"format": "TIFF", "compression": "LOSSLESS"},
    "BMP": {"format": "BMP", "compression": "LOSSLESS"},
}

# The fixed Easy Mode plan: method -> (stage, arm). Everything else in the registry is skipped with a stated reason.
REAL_FINGERPRINT = ("Method 00", "Method 03", "Method 05", "Method 11", "Method 12", "Method 13", "Method 14",
                    "Method 15", "Method 16", "Method 17", "Method 18", "Method 19", "Method 20", "Method 21",
                    "Method 22", "Method 23", "Method 24")
REAL_SIGNAL = ("Method 56", "Method 58", "Method 61", "Method 62")
CONTROLLED_SEPARATION = ("Method 34", "Method 35", "Method 36", "Method 37", "Method 38", "Method 41", "Method 42",
                         "Method 55", "Method 60", "Method 59")
EASY_PLAN: dict[str, tuple[str, str]] = {"Method 01": ("metadata", ARM_REAL), "Method 02": ("c2pa", ARM_REAL),
                                         **{m: ("fingerprint", ARM_REAL) for m in REAL_FINGERPRINT},
                                         **{m: ("signal", ARM_REAL) for m in REAL_SIGNAL},
                                         **{m: ("separation", ARM_CONTROLLED) for m in CONTROLLED_SEPARATION},
                                         "Method 54": ("consensus", ARM_REAL)}
NATIVE_ENGINE_METHODS = {"Method 01": "native metadata engine (EXIF / XMP / IPTC / ICC)",
                         "Method 02": "native JUMBF / CBOR C2PA parser (+ optional local validator)"}
JPEG_DOMAIN = {"Method 18"}
EXPERT_ONLY_REASON = {
    "ROBUSTNESS": "Robustness characterisation (fixed transformation battery) is not part of the fixed Easy Mode "
                  "pipeline; run it from Expert Mode > Fingerprint Research Lab > Robustness.",
    "HYPOTHESIS": "Speculative hypothesis test; not part of the fixed Easy Mode pipeline. Run it from Expert Mode > "
                  "Hypothesis Lab.",
}
REDUNDANT_REASON = {"Method 53": "Its member methods (13, 14, 15, 17, 18) run individually in this pipeline."}

# Controlled surrogate case (fixed, documented, deterministic). The key is the lab's published default key.
SURROGATE_CONFIG = {"family": "spatial", "strength": 3.0, "key": 20261005}
ANALYSIS_MAX_SIDE = 1024      # native-resolution centre tile for the fingerprint analysis arm
CONTROLLED_MAX_SIDE = 512     # native-resolution centre tile used as the clean host of the controlled case
MIN_ANALYSIS_SIDE = 64
MIN_CONTROLLED_SIDE = 128
TILE_ALIGN = 16               # keep the JPEG 8x8 / 16x16 MCU grid aligned in the analysis tile

# Candidate validation criteria (gates) and ranking weights. Ranking never uses the surrogate detector's score:
# candidates are ranked by how accurately they recover the KNOWN signal and how well they preserve content.
CANDIDATE_GATES = {"min_candidate_vs_known_corr": 0.30, "min_recon_ssim": 0.90, "min_recon_psnr_db": 32.0}
CANDIDATE_WEIGHTS = {"signal_consistency": 0.30, "perceptual_fidelity": 0.20, "pixel_integrity": 0.15,
                     "method_agreement": 0.15, "research_validity": 0.10, "resolution_preservation": 0.05,
                     "runtime": 0.05}
MATURITY_VALIDITY = {"ESTABLISHED": 1.0, "FOUNDATIONAL": 0.9, "ADAPTED": 0.85, "EXPERIMENTAL": 0.7,
                     "HYPOTHETICAL": 0.5}
OK_STATUSES = ("COMPLETE", "SIGNAL PERSISTED")

FRIENDLY = {
    "safety": "The selected file could not be read as an image.",
    "baseline": "The image could not be decoded.",
    "metadata": "The image could not be prepared for the experiment.",
    "validation": "The original image changed during the run, so the experiment was stopped.",
    "output": "No valid result image could be generated.",
}


class _CriticalStop(RuntimeError):
    def __init__(self, stage: str, detail: str) -> None:
        super().__init__(detail)
        self.stage, self.detail = stage, detail
        self.friendly = FRIENDLY.get(stage, "The experiment could not be completed.")


# ------------------------------------------------------------------ records
@dataclass
class EasyModeRequest:
    source_path: str
    output_format: str = "PNG"
    save_report: bool = True
    report_dir: str = ""        # "" = the experiment folder

    @property
    def fmt(self) -> str:
        f = str(self.output_format).upper().strip().lstrip(".")
        return {"JPEG": "JPG", "TIF": "TIFF"}.get(f, f)

    def to_dict(self) -> dict:
        return {"source_path": str(self.source_path), "output_format": self.fmt, "save_report": bool(self.save_report),
                "report_dir": str(self.report_dir or "")}


@dataclass
class EasyModeStageResult:
    number: int
    key: str
    label: str
    phase: str
    status: str = "PENDING"     # COMPLETE / PARTIAL / SKIPPED / FAILED
    detail: str = ""
    runtime_s: float = 0.0


@dataclass
class MethodExecution:
    method_id: str
    name: str
    category: str
    maturity: str
    stage: str = "-"
    arm: str = "-"
    decision: str = "SKIP"      # RUN / SKIP
    status: str = "NOT RUN"     # runner status, or the skip status
    reason: str = ""
    suitability: dict = field(default_factory=dict)
    readouts: dict = field(default_factory=dict)
    detail: str = ""
    runtime_s: float = 0.0
    shared_with: str = ""       # id of the method whose (identical) execution this record shares
    failure_findings: int = 0
    taxonomy: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.decision == "RUN" and self.status in OK_STATUSES


@dataclass
class ReconstructionCandidate:
    method_id: str
    name: str
    maturity: str
    status: str
    metrics: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)
    total: float = 0.0
    passed: bool = False
    gate_failures: list = field(default_factory=list)
    rank: int = 0
    duplicates: list = field(default_factory=list)


@dataclass
class EasyModeResult:
    status: str = "PENDING"     # COMPLETE / COMPLETE WITH WARNINGS / FAILED
    request: dict = field(default_factory=dict)
    experiment_id: str = ""
    experiment_dir: str = ""
    created: str = ""
    finished: str = ""
    software_version: str = __version__
    input: dict = field(default_factory=dict)
    output: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    analysis_region: dict = field(default_factory=dict)
    controlled_case: dict = field(default_factory=dict)
    stages: list = field(default_factory=list)
    methods: list = field(default_factory=list)
    families: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    best_candidate: str = ""
    reconstruction_status: str = "NOT RUN"   # VALIDATED / NO VALIDATED RECONSTRUCTION / NOT RUN
    consensus: dict = field(default_factory=dict)
    figures: list = field(default_factory=list)
    report_paths: dict = field(default_factory=dict)
    original_unchanged: bool | None = None
    warnings: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    environment: dict = field(default_factory=dict)
    error: str = ""             # user-facing sentence
    error_detail: str = ""      # optional technical detail (shown only behind DETAILS)
    runtime_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.status in ("COMPLETE", "COMPLETE WITH WARNINGS")

    def counts(self) -> dict:
        run = [m for m in self.methods if m.decision == "RUN"]
        skipped = [m for m in self.methods if m.decision == "SKIP"]
        not_applicable = [m for m in skipped if m.status in ("EXPERT ONLY", "REDUNDANT")]
        return {"total": len(self.methods), "executed": sum(1 for m in run if m.status in OK_STATUSES),
                "insufficient": sum(1 for m in run if m.status not in OK_STATUSES + ("FAILED", "NOT RUN")),
                "failed": sum(1 for m in run if m.status in ("FAILED", "NOT RUN")), "skipped": len(skipped),
                "unavailable": len(skipped) - len(not_applicable)
                + sum(1 for m in run if m.status not in OK_STATUSES),
                "not_in_easy_pipeline": len(not_applicable)}

    def method(self, method_id: str) -> MethodExecution | None:
        return next((m for m in self.methods if m.method_id == method_id), None)

    def to_dict(self) -> dict:
        d = jsonable(self)
        d["counts"] = self.counts()
        return d


@dataclass
class _RunState:
    request: EasyModeRequest
    path: Path | None = None
    data: bytes = b""
    fmt: str = ""
    sha_before: str = ""
    pil: object = None
    analysis: object = None
    exp: object = None
    src: object = None
    x: np.ndarray | None = None
    records: dict = field(default_factory=dict)        # method id -> MethodExecution
    plan: list = field(default_factory=list)           # MethodExecution (decision + suitability)
    cand_maps: dict = field(default_factory=dict)      # method id -> (candidate_signal, content_luma)
    known: np.ndarray | None = None
    observed_y: np.ndarray | None = None
    figures_dir: Path | None = None


# ------------------------------------------------------------------ helpers
def centre_tile(w: int, h: int, max_side: int, align: int = TILE_ALIGN) -> tuple[int, int, int, int]:
    """Deterministic native-resolution centre tile (no resampling); origin aligned to the codec block grid."""
    tw, th = min(w, max_side), min(h, max_side)
    left = ((w - tw) // 2) // align * align
    top = ((h - th) // 2) // align * align
    return left, top, left + tw, top + th


_TAX_CODE = re.compile(r"taxonomy\s+((?:\d[A-Z]?)(?:/\d[A-Z]?)*)")


def taxonomy_codes(method: Method) -> list[str]:
    m = _TAX_CODE.search(method.source_reference or "")
    return m.group(1).split("/") if m else []


def taxonomy_families(method_ids: dict[str, list[str]]) -> list[dict]:
    """Match taxonomy codes cited by the executed methods to the bundled taxonomy database.

    ``method_ids`` maps a taxonomy code (e.g. "3A") to the methods that investigated it.
    """
    from app.research import taxonomy as T

    db = T.load()
    names: dict[str, dict] = {}
    for e in db.get("entries", []):
        sub = str(e.get("subcategory", ""))
        m = re.match(r"(\d[A-Z]?)\.\s", sub)
        if not m or sub.startswith("8."):
            continue
        rec = names.setdefault(m.group(1), {"subcategory": sub, "category": e.get("category", ""), "entries": 0})
        rec["entries"] += 1
    out = []
    for code in sorted(method_ids):
        info = names.get(code)
        if info is None:
            continue
        out.append({"code": code, "family": info["subcategory"], "category": info["category"],
                    "taxonomy_entries": info["entries"], "methods": sorted(set(method_ids[code]))})
    return out


def _safe_readouts(r) -> dict:
    out = {}
    for k, v in (r.readouts or {}).items():
        if isinstance(v, (int, float, str, bool)) or v is None:
            out[str(k)] = v
        else:
            out[str(k)] = str(v)[:120]
    return jsonable(out)


def _workers() -> int:
    from app.utils.memory import system_memory

    avail = system_memory().get("available") or 0
    if avail and avail < 2 * 1024 ** 3:
        return 1
    return max(1, min(4, (os.cpu_count() or 2) - 1))


# ------------------------------------------------------------------ orchestrator
class EasyModeOrchestrator:
    def __init__(self, workspace, audit, synthid_engine=None, service=None, exiftool_path: str | None = None,
                 c2patool_path: str | None = None, use_c2pa_python: bool = False, registry: MethodRegistry | None = None,
                 max_file_mb: float = 4096, analysis_max_side: int = ANALYSIS_MAX_SIDE,
                 controlled_max_side: int = CONTROLLED_MAX_SIDE, workers: int | None = None) -> None:
        from app.services.transformation_service import TransformationService

        self.ws = workspace
        self.audit = audit
        self.engine = synthid_engine
        self.service = service or TransformationService(workspace, audit, synthid_engine, exiftool_path)
        self.exiftool_path = exiftool_path
        self.c2patool_path = c2patool_path
        self.use_c2pa_python = use_c2pa_python
        self.registry = registry or MethodRegistry()
        self.max_file_mb = max_file_mb
        self.analysis_max_side = int(analysis_max_side)
        self.controlled_max_side = int(controlled_max_side)
        self.workers = workers if workers is not None else _workers()
        self._progress: Progress = lambda _p, _t: None
        self._done_weight = 0

    # -- suitability engine -------------------------------------------------
    def plan(self, fmt: str, width: int, height: int, has_gpu: bool = False) -> list[MethodExecution]:
        """Decide, for every registry method, whether the Easy pipeline runs it on this input and why (not)."""
        out = []
        for m in self.registry.all():
            rec = MethodExecution(m.method_id, m.name, m.category, m.maturity)
            stage, arm = EASY_PLAN.get(m.method_id, ("-", "-"))
            rec.stage, rec.arm = stage, arm
            controlled = arm == ARM_CONTROLLED
            fmt_ok = not (m.method_id in JPEG_DOMAIN and fmt != "JPEG")
            min_side = MIN_CONTROLLED_SIDE if controlled else MIN_ANALYSIS_SIDE
            res_ok = min(width, height) >= min_side
            rec.suitability = {
                "format_compatible": fmt_ok, "resolution_ok": res_ok, "model_available": not m.requires_model,
                "dependency_available": m.availability == "READY", "gpu_required": m.requires_gpu,
                "ground_truth": "controlled surrogate (local, keyed)" if controlled else
                ("required" if m.requires_ground_truth else "not required"),
                "compute_cost": m.compute_cost, "maturity": m.maturity,
                "analysis_capability": m.can("CAN_ANALYZE"),
                "reconstruction_capability": m.can("CAN_RECONSTRUCT"),
                "tiled": f"native centre tile <= {self.controlled_max_side if controlled else self.analysis_max_side} px",
            }
            if m.availability == "NOT_IMPLEMENTED":
                rec.status, rec.reason = "NOT IMPLEMENTED", m.reason
            elif m.availability == "UNAVAILABLE" or m.requires_model:
                rec.status = "UNAVAILABLE"
                rec.reason = "Requires a model / deep-learning runtime that is not installed. " + (m.reason or "")
            elif m.requires_gpu and not has_gpu:
                rec.status, rec.reason = "UNAVAILABLE", "Requires a GPU; none is available to the bundled engines."
            elif m.method_id in REDUNDANT_REASON:
                rec.status, rec.reason = "REDUNDANT", REDUNDANT_REASON[m.method_id]
            elif m.method_id not in EASY_PLAN:
                if m.requires_reference_images or m.capability == "attribution":
                    rec.status = "REQUIRES DATA"
                    rec.reason = ("Requires data that is not present in a single-image run: "
                                  + (m.input_requirements or "reference images") + ".")
                elif m.capability in ("robustness", "persistence_map") or \
                        m.capability.endswith("provenance_energy_landscape"):
                    rec.status, rec.reason = "EXPERT ONLY", EXPERT_ONLY_REASON["ROBUSTNESS"]
                elif m.category == "ADVANCED HYPOTHESIS":
                    rec.status, rec.reason = "EXPERT ONLY", EXPERT_ONLY_REASON["HYPOTHESIS"]
                else:
                    rec.status, rec.reason = "EXPERT ONLY", "Not part of the fixed Easy Mode pipeline."
            elif not fmt_ok:
                rec.status = "INCOMPATIBLE"
                rec.reason = (f"JPEG-domain statistic (quantised DCT coefficients of a JPEG bitstream); the input is "
                              f"{fmt}, which has no JPEG quantisation history.")
            elif not res_ok:
                rec.status = "INCOMPATIBLE"
                rec.reason = (f"Image is {width}x{height}; this stage needs at least {min_side}x{min_side} px "
                              f"({'controlled case' if controlled else 'analysis tile'}).")
            else:
                rec.decision, rec.status = "RUN", "PENDING"
                rec.reason = ("Applicable: " + ("scored against a locally embedded keyed surrogate signal (ground "
                                                "truth known)." if controlled else "descriptive observation of the "
                                                "real image; nothing is removed from it."))
            rec.taxonomy = taxonomy_codes(m)
            out.append(rec)
        return out

    # -- progress / stage plumbing -----------------------------------------
    def _emit(self, stage: EasyModePipelineStage, frac: float) -> None:
        pct = int(round(self._done_weight + stage.weight * max(0.0, min(1.0, frac))))
        try:
            self._progress(max(0, min(100, pct)), stage.phase)
        except Exception:  # noqa: BLE001 - a UI callback must never break the pipeline
            pass

    def _stage(self, res: EasyModeResult, key: str, fn, critical: bool = False) -> None:
        stage = STAGE_BY_KEY[key]
        sr = EasyModeStageResult(stage.number, stage.key, stage.label, stage.phase)
        self._emit(stage, 0.0)
        t0 = time.perf_counter()
        try:
            detail = fn(sr, lambda f: self._emit(stage, f))
            sr.status = sr.status if sr.status not in ("PENDING", "") else "COMPLETE"
            sr.detail = str(detail or sr.detail or "")[:600]
        except _CriticalStop as stop:
            sr.status, sr.detail = "FAILED", stop.detail[:600]
            sr.runtime_s = time.perf_counter() - t0
            res.stages.append(sr)
            raise
        except Exception as exc:  # noqa: BLE001 - graceful fallback: record and continue
            if critical:
                sr.status, sr.detail = "FAILED", f"{type(exc).__name__}: {exc}"[:600]
                sr.runtime_s = time.perf_counter() - t0
                res.stages.append(sr)
                raise _CriticalStop(key, f"{type(exc).__name__}: {exc}") from exc
            sr.status, sr.detail = "FAILED", f"{type(exc).__name__}: {exc}"[:600]
            res.warnings.append(f"Stage {stage.number:02d} {stage.label} failed: {type(exc).__name__}: {exc}")
        sr.runtime_s = time.perf_counter() - t0
        res.stages.append(sr)
        self._done_weight += stage.weight
        if self.audit is not None:
            self.audit.log(A.EASY_STAGE, "INFO" if sr.status in ("COMPLETE", "SKIPPED") else "WARNING",
                           f"{stage.number:02d} {stage.label}: {sr.status} ({sr.runtime_s:.2f}s) {sr.detail[:160]}")

    # -- the run -------------------------------------------------------------
    def run(self, request: EasyModeRequest, progress: Progress | None = None) -> EasyModeResult:
        self._progress = progress or (lambda _p, _t: None)
        self._done_weight = 0
        t0 = time.perf_counter()
        res = EasyModeResult(request=request.to_dict(), created=utc_now())
        st = _RunState(request=request)
        if request.fmt not in OUTPUT_FORMATS:
            res.status, res.error = "FAILED", "The selected output format is not supported."
            res.error_detail = f"output format {request.output_format!r}; supported: {', '.join(OUTPUT_FORMATS)}"
            return res
        try:
            self._stage(res, "safety", lambda sr, p: self._safety(st, res), critical=True)
            self._stage(res, "baseline", lambda sr, p: self._baseline(st, res), critical=True)
            self._stage(res, "metadata", lambda sr, p: self._metadata(st, res), critical=True)
            self._stage(res, "c2pa", lambda sr, p: self._c2pa(st, res))
            self._stage(res, "synthid", lambda sr, p: self._synthid(st, res))
            self._stage(res, "fingerprint", lambda sr, p: self._fingerprint(st, res, sr, p))
            self._stage(res, "signal", lambda sr, p: self._signal(st, res, sr, p))
            self._stage(res, "separation", lambda sr, p: self._separation(st, res, sr, p))
            self._stage(res, "consensus", lambda sr, p: self._consensus(st, res))
            self._stage(res, "validation", lambda sr, p: self._validation(st, res, sr))
            self._stage(res, "output", lambda sr, p: self._output(st, res, p), critical=True)
            self._finish_records(st, res)
            self._stage(res, "report", lambda sr, p: self._report(st, res, sr))
            failed = res.counts()["failed"] or any(s.status in ("FAILED", "PARTIAL") for s in res.stages)
            res.status = "COMPLETE WITH WARNINGS" if (failed or res.warnings) else "COMPLETE"
        except _CriticalStop as stop:
            res.status, res.error, res.error_detail = "FAILED", stop.friendly, stop.detail
            self._finish_records(st, res)
            if st.exp is not None and request.save_report:   # analysis done so far is still reported
                try:
                    self._report(st, res, EasyModeStageResult(12, "report", "Report generation", "Finalizing"))
                except Exception as exc:  # noqa: BLE001
                    res.warnings.append(f"Report after failure not written: {type(exc).__name__}: {exc}")
        finally:
            self._final_integrity(st, res)
            res.runtime_s = time.perf_counter() - t0
            res.finished = utc_now()
            self._persist(st, res)
            try:
                self._progress(100, "Finalizing")
            except Exception:  # noqa: BLE001
                pass
        return res

    # -- stages --------------------------------------------------------------
    def _safety(self, st: _RunState, res: EasyModeResult) -> str:
        p = Path(st.request.source_path)
        try:
            path, data = read_file_bytes(p, int(self.max_file_mb * 1024 * 1024))
        except Exception as exc:  # noqa: BLE001
            raise _CriticalStop("safety", f"{type(exc).__name__}: {exc}") from exc
        st.path, st.data, st.fmt = path, data, sniff_format(data[:16]) or ""
        res.input = {"name": path.name, "path": str(path), "bytes": len(data), "container": st.fmt}
        return f"{st.fmt} container identified by magic bytes; {len(data):,} bytes; size and memory budget checked"

    def _baseline(self, st: _RunState, res: EasyModeResult) -> str:
        h = file_hashes(st.data)
        st.sha_before = h["sha256"]
        try:
            st.pil = open_image_bytes(st.data)
        except Exception as exc:  # noqa: BLE001
            raise _CriticalStop("baseline", f"{type(exc).__name__}: {exc}") from exc
        w, hh = st.pil.size
        res.input.update({"sha256": h["sha256"], "blake3": h["blake3"] or h["blake3_state"], "width": w, "height": hh,
                          "mode": st.pil.mode, "pixel_sha256": pixel_hash(to_array(st.pil))})
        return f"SHA-256 {h['sha256'][:16]}...; decoded {w}x{hh} {st.pil.mode}"

    def _metadata(self, st: _RunState, res: EasyModeResult) -> str:
        an = analyze_bytes(st.data, st.path, st.path.name, exiftool_path=self.exiftool_path, image=st.pil)
        st.analysis = an
        res.input.update({"format": an.info.format, "mime": an.info.mime, "bit_depth": an.info.bit_depth,
                          "color_space": an.info.color_space})
        exp = self.ws.create(an.info.filename or st.path.name, st.data, baseline=an.to_dict())
        exp.objective = ("Easy Mode research pipeline (PILIH > RUN > OUTPUT): observe the real image's provenance and "
                         "fingerprint statistics, run the controlled surrogate separation study, and export a "
                         "pixel-preserving result image in the selected format.")
        st.exp = exp
        res.experiment_id, res.experiment_dir = exp.experiment_id, str(self.ws.experiment_dir(exp.experiment_id))
        if self.audit is not None:
            self.audit.bind(exp.experiment_id, self.ws.audit_path(exp), carry_unbound=False)
            self.audit.log(A.EASY_RUN_STARTED, detail=f"{exp.experiment_id} input {st.path.name} sha256 {st.sha_before} "
                                                      f"output {st.request.fmt}")
            self.audit.log(A.METADATA_COMPLETE, detail=", ".join(f"{k}:{g.state.value}" for k, g in an.groups.items()))
        st.plan = self.plan(an.info.format, an.info.width, an.info.height)
        st.records = {r.method_id: r for r in st.plan}
        rec = st.records["Method 01"]
        present = [k for k, g in an.groups.items() if g.state.value != "ABSENT"]
        self._native(rec, "COMPLETE", {"Groups present": ", ".join(present) or "none",
                                       "AI declaration": an.signal.state if an.signal else "UNKNOWN"},
                     f"{NATIVE_ENGINE_METHODS['Method 01']}: {len(present)} metadata group(s) present")
        return f"experiment {exp.experiment_id}; metadata groups present: {', '.join(present) or 'none'}"

    def _native(self, rec: MethodExecution, status: str, readouts: dict, detail: str) -> None:
        if rec.decision == "RUN":
            rec.status, rec.readouts, rec.detail = status, jsonable(readouts), detail

    def _c2pa(self, st: _RunState, res: EasyModeResult) -> str:
        from app.services.provenance_service import run_external_c2pa_validation

        an = st.analysis
        engine = ""
        try:
            engine = run_external_c2pa_validation(an, self.ws.original_file(st.exp), self.c2patool_path,
                                                  self.use_c2pa_python)
        except Exception as exc:  # noqa: BLE001 - optional validator; the native parse stands
            res.warnings.append(f"Optional C2PA validator failed: {type(exc).__name__}: {exc}")
        c2 = an.c2pa
        st.exp.baseline = an.to_dict()
        self.ws.save(st.exp)
        sig = an.signal
        res.provenance.update({
            "c2pa_present": c2.present, "c2pa_state": c2.state if c2.present else "NOT PRESENT", "c2pa_summary": c2.summary,
            "c2pa_hard_binding": c2.hard_binding, "c2pa_validity": c2.validity, "c2pa_trust": c2.trust,
            "c2pa_engine": engine or c2.engine, "c2pa_manifests": len(c2.manifests),
            "ai_declaration": sig.state if sig else "UNKNOWN", "ai_declaration_statement": sig.statement if sig else "",
            "separation": "C2PA is signed provenance metadata: it is analysed separately from the pixel layer and is "
                          "never treated as an intrinsic fingerprint."})
        if self.audit is not None:
            self.audit.log(A.C2PA_COMPLETE, detail=f"{c2.state}: {c2.summary} binding {c2.hard_binding}")
        self._native(st.records["Method 02"], "COMPLETE",
                     {"C2PA": res.provenance["c2pa_state"], "Hard binding": c2.hard_binding, "Validity": c2.validity},
                     f"{NATIVE_ENGINE_METHODS['Method 02']}: {c2.summary}")
        return f"C2PA {res.provenance['c2pa_state']}; hard binding {c2.hard_binding}; validity {c2.validity}"

    def _synthid(self, st: _RunState, res: EasyModeResult) -> str:
        sid = analyze_synthid(self.engine, self.ws.original_file(st.exp), "ORIGINAL", st.exp.baseline).to_dict()
        st.exp.synthid_baseline = sid
        self.ws.save(st.exp)
        res.provenance.update({"synthid_state": sid.get("state", "UNAVAILABLE"), "synthid_detail": sid.get("detail", ""),
                               "synthid_engine": sid.get("engine", "none"),
                               "synthid_policy": "Local verification engine only. Easy Mode never contacts an online "
                                                 "verifier and never attempts to bypass or attack a real watermark."})
        if self.audit is not None:
            self.audit.log(A.SYNTHID_COMPLETE, detail=f"{sid['state']}: {sid.get('detail', '')}")
        return f"SynthID {sid.get('state')}: {sid.get('detail', '')}"

    def _source_context(self, st: _RunState):
        from app.services.transformation_service import SourceContext

        if st.src is None:
            an = st.analysis
            st.src = SourceContext(self.ws.original_file(st.exp), an, an.to_dict(), dict(st.exp.synthid_baseline or {}))
        return st.src

    def _analysis_tile(self, st: _RunState, res: EasyModeResult) -> np.ndarray:
        if st.x is None:
            w, h = st.pil.size
            box = centre_tile(w, h, self.analysis_max_side)
            region = st.pil if box == (0, 0, w, h) else st.pil.crop(box)
            st.x = as_float(region)
            res.analysis_region = {"box": list(box), "width": box[2] - box[0], "height": box[3] - box[1],
                                   "full_image": box == (0, 0, w, h),
                                   "note": "native-resolution centre tile (no resampling), origin aligned to a "
                                           f"{TILE_ALIGN}-px grid" if box != (0, 0, w, h) else "full image"}
        return st.x

    def _runnable(self, st: _RunState, ids) -> list[MethodExecution]:
        return [st.records[i] for i in ids if i in st.records and st.records[i].decision == "RUN"]

    def _execute(self, st: _RunState, recs: list[MethodExecution], inp: RUN.MethodInput, report: Callable,
                 keep_maps: tuple = ()) -> dict:
        """Run methods; identical (capability, input) pairs execute once and the record says so. Order is fixed."""
        groups: OrderedDict[str, list[MethodExecution]] = OrderedDict()
        for r in recs:
            groups.setdefault(self.registry.get(r.method_id).capability, []).append(r)
        results: dict[str, object] = {}
        total = max(1, len(groups))

        def job(cap):
            return RUN.run(self.registry.get(groups[cap][0].method_id), inp)

        done = 0
        with ThreadPoolExecutor(max_workers=max(1, self.workers)) as ex:
            futs = {ex.submit(job, cap): cap for cap in groups}
            for fut in as_completed(futs):
                cap = futs[fut]
                try:
                    results[cap] = fut.result()
                except Exception as exc:  # noqa: BLE001 - e.g. MemoryError outside the runner's own guard
                    results[cap] = exc
                done += 1
                report(done / total)
        maps: dict[str, dict] = {}
        for cap, members in groups.items():
            r = results[cap]
            primary = members[0]
            for rec in members:
                if isinstance(r, Exception):
                    rec.status, rec.detail = "FAILED", f"{type(r).__name__}: {r}"[:500]
                    continue
                rec.status = r.status
                rec.readouts = _safe_readouts(r)
                rec.detail = (r.detail or r.note or "")[:500]
                rec.runtime_s = float(r.runtime_s or 0.0)
                rec.failure_findings = len(r.failure_analysis or [])
                if rec is not primary:
                    rec.shared_with = primary.method_id
            if not isinstance(r, Exception) and primary.method_id in keep_maps:
                maps[primary.method_id] = r.maps
            if not isinstance(r, Exception):
                r.maps = {}
        return maps

    def _fingerprint(self, st: _RunState, res: EasyModeResult, sr, report) -> str:
        x = self._analysis_tile(st, res)
        recs = self._runnable(st, REAL_FINGERPRINT)
        inp = RUN.MethodInput(image=x, pil=st.pil)
        maps = self._execute(st, recs, inp, report, keep_maps=("Method 03", "Method 13"))
        self._figures(st, res, maps.get("Method 13", {}), ("fft_log_magnitude",), "Real image: FFT log-magnitude")
        self._figures(st, res, maps.get("Method 03", {}), ("residual_highpass",), "Real image: high-pass residual")
        # taxonomy matching over every method this run executes (both arms) plus the provenance layers observed
        codes: dict[str, list[str]] = {}
        for r in st.plan:
            if r.decision == "RUN":
                for c in r.taxonomy:
                    codes.setdefault(c, []).append(r.method_id)
        codes.setdefault("4J", []).append("SynthID status (stage 05)")
        res.families = taxonomy_families(codes)
        ok = sum(1 for r in recs if r.ok)
        if ok < len(recs):
            sr.status = "PARTIAL"
        return (f"{ok}/{len(recs)} analysis methods complete on the {res.analysis_region.get('width')}x"
                f"{res.analysis_region.get('height')} analysis region; {len(res.families)} taxonomy families matched")

    def _signal(self, st: _RunState, res: EasyModeResult, sr, report) -> str:
        recs = self._runnable(st, REAL_SIGNAL)
        if not recs:
            sr.status = "SKIPPED"
            return "no applicable signal-estimation method"
        self._execute(st, recs, RUN.MethodInput(image=self._analysis_tile(st, res)), report)
        ok = sum(1 for r in recs if r.ok)
        if ok < len(recs):
            sr.status = "PARTIAL"
        return f"{ok}/{len(recs)} descriptive signal-estimation methods complete (real image; nothing removed)"

    def _separation(self, st: _RunState, res: EasyModeResult, sr, report) -> str:
        recs = self._runnable(st, CONTROLLED_SEPARATION)
        if not recs:
            sr.status = "SKIPPED"
            res.reconstruction_status = "NO VALIDATED RECONSTRUCTION"
            return "controlled case not applicable to this input (see method reasons)"
        w, h = st.pil.size
        box = centre_tile(w, h, self.controlled_max_side)
        host = as_float(st.pil if box == (0, 0, w, h) else st.pil.crop(box))
        cfg = SUR.SurrogateConfig(**SURROGATE_CONFIG)
        emb = SUR.embed(host, cfg)
        det_wm, det_clean = SUR.detect(emb.watermarked, cfg), SUR.detect(host, cfg)
        valid = bool(det_wm.detected and not det_clean.detected)
        res.controlled_case = {"region_box": list(box), "width": box[2] - box[0], "height": box[3] - box[1],
                               "surrogate": cfg.to_dict(), "detector_z_clean": det_clean.score,
                               "detector_z_embedded": det_wm.score, "valid_ground_truth": valid,
                               "embed_stats": jsonable(emb.stats),
                               "note": "The clean host is a native-resolution tile of the input. The keyed surrogate is a "
                                       "transparent laboratory signal, not SynthID; results are scored against it only."}
        if not valid:
            for r in recs:
                r.status = "INSUFFICIENT DATA"
                r.detail = "controlled case rejected: the surrogate ground truth did not validate on this host"
            sr.status = "PARTIAL"
            res.reconstruction_status = "NO VALIDATED RECONSTRUCTION"
            return "surrogate ground truth did not validate on this host; separation study not scored"
        st.known = luminance(emb.watermarked) - luminance(host)
        st.observed_y = luminance(emb.watermarked)
        inp = RUN.MethodInput(image=host, surrogate_cfg=cfg, clean=host)
        maps = self._execute(st, recs, inp, report, keep_maps=tuple(r.method_id for r in recs))
        for mid, mp in maps.items():
            cand = mp.get("candidate_signal")
            content = mp.get("estimated_content", mp.get("reconstruction"))
            if cand is None or content is None or not self.registry.get(mid).can("CAN_RECONSTRUCT"):
                continue
            content_y = luminance(content) if np.asarray(content).ndim == 3 else np.asarray(content, np.float32)
            st.cand_maps[mid] = (np.asarray(cand, np.float32), content_y)
        ok = sum(1 for r in recs if r.ok)
        if ok < len(recs):
            sr.status = "PARTIAL"
        return (f"controlled case {box[2] - box[0]}x{box[3] - box[1]} (ground truth valid); {ok}/{len(recs)} methods "
                f"complete; {len(st.cand_maps)} reconstruction candidates")

    def _consensus(self, st: _RunState, res: EasyModeResult) -> str:
        real = [r for r in st.plan if r.arm == ARM_REAL and r.decision == "RUN" and r.method_id != "Method 54"]
        fam = {}
        for r in real:
            f = fam.setdefault(r.category, {"methods": 0, "complete": 0})
            f["methods"] += 1
            f["complete"] += int(r.ok)
        res.consensus["real_image_families"] = fam
        dis = st.records.get("Method 61")
        if dis is not None and dis.ok:
            res.consensus["method_disagreement"] = dis.readouts.get("disagreement")
            res.consensus["method_disagreement_verdict"] = dis.readouts.get("Verdict")
        meta = st.records.get("Method 54")
        if meta is not None and meta.decision == "RUN":
            prior = [{"method_id": r.method_id, "name": r.name, "status": r.status, "failure_analysis": []} for r in real]
            r = RUN.run(self.registry.get("Method 54"), RUN.MethodInput(image=self._analysis_tile(st, res),
                                                                        prior_results=prior))
            meta.status, meta.readouts, meta.detail, meta.runtime_s = r.status, _safe_readouts(r), r.detail, r.runtime_s
        # agreement between controlled-case candidate signals (independent decompositions)
        ids = list(st.cand_maps)
        agree = {}
        pairs = []
        for i in ids:
            vals = [M.pearson(st.cand_maps[i][0], st.cand_maps[j][0]) for j in ids if j != i]
            agree[i] = float(np.mean(vals)) if vals else None
            pairs.extend(vals)
        res.consensus["candidate_agreement"] = agree
        res.consensus["candidate_agreement_mean"] = float(np.mean(pairs)) if pairs else None
        return (f"{sum(v['complete'] for v in fam.values())} real-image results across {len(fam)} method families; "
                f"{len(ids)} controlled candidates cross-checked")

    def _validation(self, st: _RunState, res: EasyModeResult, sr) -> str:
        if st.path is not None and sha256_file(st.path) != st.sha_before:
            res.original_unchanged = False
            raise _CriticalStop("validation", f"source file hash changed during the run: {st.path}")
        res.original_unchanged = True
        cands = self._evaluate(st, res)
        res.candidates = cands
        best = next((c for c in cands if c.passed), None)
        if best is not None:
            res.best_candidate, res.reconstruction_status = best.method_id, "VALIDATED"
            mp = st.cand_maps.get(best.method_id)
            if mp is not None:
                self._figures(st, res, {"candidate_signal": mp[0], "known_signal": st.known},
                              ("candidate_signal", "known_signal"),
                              f"Controlled case: {best.method_id} recovered candidate vs known surrogate signal")
        elif res.reconstruction_status == "NOT RUN" or cands:
            res.reconstruction_status = "NO VALIDATED RECONSTRUCTION"
        st.cand_maps.clear()
        return (f"original unchanged (SHA-256 re-verified); {len(cands)} candidate(s) evaluated; reconstruction "
                f"{res.reconstruction_status}" + (f" ({res.best_candidate})" if res.best_candidate else ""))

    def _evaluate(self, st: _RunState, res: EasyModeResult) -> list[ReconstructionCandidate]:
        """Gate and rank controlled-case reconstruction candidates. The first candidate is never assumed best."""
        out = []
        agree = res.consensus.get("candidate_agreement") or {}
        dups: dict[str, list[str]] = {}
        for r in st.plan:
            if r.shared_with:
                dups.setdefault(r.shared_with, []).append(r.method_id)
        for mid, (cand, content_y) in st.cand_maps.items():
            rec = st.records[mid]
            f = M.fidelity(st.observed_y, content_y)
            corr = M.pearson(cand, st.known)
            psnr = f.get("psnr_db")
            psnr = 99.0 if f.get("psnr_infinite") else psnr
            ssim = f.get("ssim")
            same_shape = cand.shape == st.known.shape and content_y.shape == st.observed_y.shape
            ro = rec.readouts or {}
            metrics = {"candidate_vs_known_corr": corr, "recon_psnr_db": psnr, "recon_ssim": ssim,
                       "method_agreement": agree.get(mid), "resolution_preserved": same_shape,
                       "runtime_s": rec.runtime_s, "signal_reduction_observed": ro.get("Signal reduction"),
                       "still_detected_after_observed": ro.get("Still detected")}
            fails = []
            if rec.status not in OK_STATUSES:
                fails.append(f"status {rec.status}")
            if not same_shape:
                fails.append("resolution not preserved")
            finite = all(v is not None and np.isfinite(v) for v in (corr, psnr, ssim))
            if not finite:
                fails.append("non-finite metric")
            else:
                if corr < CANDIDATE_GATES["min_candidate_vs_known_corr"]:
                    fails.append(f"recovery corr {corr:.3f} < {CANDIDATE_GATES['min_candidate_vs_known_corr']}")
                if ssim < CANDIDATE_GATES["min_recon_ssim"]:
                    fails.append(f"SSIM {ssim:.3f} < {CANDIDATE_GATES['min_recon_ssim']}")
                if psnr < CANDIDATE_GATES["min_recon_psnr_db"]:
                    fails.append(f"PSNR {psnr:.1f} dB < {CANDIDATE_GATES['min_recon_psnr_db']}")
            scores = {
                "signal_consistency": float(np.clip(corr, 0, 1)) if finite else 0.0,
                "perceptual_fidelity": float(np.clip((ssim - 0.8) / 0.2, 0, 1)) if finite else 0.0,
                "pixel_integrity": float(np.clip((psnr - 25.0) / 20.0, 0, 1)) if finite else 0.0,
                "method_agreement": float(np.clip(agree.get(mid) or 0.0, 0, 1)),
                "research_validity": MATURITY_VALIDITY.get(rec.maturity, 0.5),
                "resolution_preservation": 1.0 if same_shape else 0.0,
                "runtime": float(1.0 / (1.0 + max(rec.runtime_s, 0.0) / 10.0)),
            }
            total = float(sum(CANDIDATE_WEIGHTS[k] * v for k, v in scores.items()))
            out.append(ReconstructionCandidate(mid, rec.name, rec.maturity, rec.status, jsonable(metrics),
                                               {k: round(v, 4) for k, v in scores.items()}, round(total, 4),
                                               not fails, fails, duplicates=dups.get(mid, [])))
        out.sort(key=lambda c: (not c.passed, -c.total, c.method_id))
        for i, c in enumerate(out, 1):
            c.rank = i
        return out

    def _output(self, st: _RunState, res: EasyModeResult, report) -> str:
        from app.core.image_writer import FORMAT_CAPS

        src = self._source_context(st)
        params = dict(OUTPUT_ENCODING[st.request.fmt], keep_icc=True, carry_metadata=True, source="ORIGINAL")
        rec = self.service.run(st.exp, src, "format_conversion", params, lambda p, _t: report(p / 100.0))
        if rec.status != "COMPLETE":
            raise _CriticalStop("output", f"{rec.transformation_id} {rec.status}: {rec.error}")
        out_path = self.ws.resolve(st.exp, rec.output_path)
        try:
            open_image_bytes(out_path.read_bytes())        # the result must be a real, decodable image file
        except Exception as exc:  # noqa: BLE001
            raise _CriticalStop("output", f"result file does not decode: {type(exc).__name__}: {exc}") from exc
        pm = rec.pixel_metrics or {}
        verdict = pm.get("verdict", "")
        lossy = OUTPUT_ENCODING[st.request.fmt]["compression"] == "LOSSY"
        if verdict == "PIXEL-EXACT":
            pixel_status = "VERIFIED"
        elif verdict == "NOT COMPARABLE":
            pixel_status = "NOT COMPARABLE"
        else:
            pixel_status = "LOSSY (MEASURED)" if lossy else "CHANGED (MEASURED)"
        oa = rec.output_analysis or {}
        res.output = {"path": str(out_path), "file_name": out_path.name, "transformation_id": rec.transformation_id,
                      "format": rec.output_format, "easy_format": st.request.fmt,
                      "extension": FORMAT_CAPS.get(rec.output_format, {}).get("ext", out_path.suffix),
                      "width": rec.output_dimensions[0] if rec.output_dimensions else None,
                      "height": rec.output_dimensions[1] if rec.output_dimensions else None,
                      "bytes": out_path.stat().st_size, "sha256": rec.output_sha256,
                      "pixel_sha256": (oa.get("hashes") or {}).get("pixel_sha256"),
                      "pixel_verdict": verdict, "pixel_status": pixel_status,
                      "changed_pixels": pm.get("changed_pixels"), "changed_pixel_pct": pm.get("changed_pixel_pct"),
                      "mae": pm.get("mae"), "psnr_db": None if pm.get("psnr_infinite") else pm.get("psnr_db"),
                      "psnr_infinite": pm.get("psnr_infinite"), "ssim": pm.get("ssim"),
                      "encoding": params, "flags": list(rec.flags), "actions": list(rec.actions),
                      "notes": list(rec.notes), "c2pa_after": (rec.provenance_differences or {}).get("c2pa_after"),
                      "synthid_after": (rec.synthid_after or {}).get("state"),
                      "content": "pixel-preserving re-encoding of the decoded original (REAL IMAGE OBSERVATION arm); "
                                 "no signal was estimated out of or removed from the real image"}
        if self.audit is not None:
            self.audit.log(A.FILE_EXPORTED, detail=f"{rec.transformation_id} Easy result {out_path.name} {verdict}")
        return f"{rec.transformation_id} {rec.output_format} {res.output['width']}x{res.output['height']}: {verdict}"

    def _finish_records(self, st: _RunState, res: EasyModeResult) -> None:
        recs = st.plan or []
        for r in recs:
            if r.decision == "RUN" and r.status == "PENDING":
                r.status, r.detail = "NOT RUN", "not executed: its stage did not complete"
        res.methods = list(recs)

    def _report(self, st: _RunState, res: EasyModeResult, sr) -> str:
        if not st.request.save_report:
            sr.status = "SKIPPED"
            return "research report disabled by the user (the run record easy_mode_run.json is still kept)"
        from app.services.easy_report import write_easy_report

        res.report_paths = {k: str(v) for k, v in
                            write_easy_report(res, self.ws.subdir(st.exp, "report"), st.request.report_dir).items()}
        if self.audit is not None:
            self.audit.log(A.REPORT_GENERATED, detail=f"Easy research report {', '.join(sorted(res.report_paths))}")
        return "report written: " + ", ".join(sorted(res.report_paths))

    def _figures(self, st: _RunState, res: EasyModeResult, maps: dict, names: tuple, caption: str) -> None:
        if st.exp is None:
            return
        try:
            d = self.ws.subdir(st.exp, "report") / "figures"
            d.mkdir(parents=True, exist_ok=True)
            for name in names:
                arr = maps.get(name)
                if arr is None:
                    continue
                a = np.asarray(arr, dtype=np.float32)
                plane = a if a.ndim == 2 else a[:, :, 0]
                fn = f"{len(res.figures) + 1:02d}_{name}.png"
                map_image(display_limit(plane[:, :, None])[:, :, 0],
                          symmetric=any(k in name for k in ("signal", "residual"))).save(d / fn)
                res.figures.append({"file": f"figures/{fn}", "caption": f"{caption} ({name})", "path": str(d / fn)})
        except Exception as exc:  # noqa: BLE001 - a figure never fails the run
            res.warnings.append(f"figure not written: {type(exc).__name__}: {exc}")

    def _final_integrity(self, st: _RunState, res: EasyModeResult) -> None:
        if st.path is None or not st.sha_before:
            return
        try:
            same = sha256_file(st.path) == st.sha_before
        except OSError as exc:
            res.warnings.append(f"final integrity re-hash failed: {exc}")
            return
        res.input["sha256_after"] = st.sha_before if same else "CHANGED"
        if not same:
            res.original_unchanged = False
            if res.ok:
                res.status, res.error = "FAILED", FRIENDLY["validation"]
                res.error_detail = "source file hash changed after the run"
        elif res.original_unchanged is None:
            res.original_unchanged = True

    def _persist(self, st: _RunState, res: EasyModeResult) -> None:
        if st.exp is None:
            return
        try:
            from app.utils.system import system_info

            info = system_info()
            res.environment = {k: info.get(k) for k in ("os", "machine", "python", "qt", "frozen")}
            res.environment["cpu_threads"] = os.cpu_count()
            res.environment["network"] = "LOCAL-ONLY (no network access, no upload, no telemetry)"
            st.exp.status = "COMPLETE" if res.ok else "FAILED"
            st.exp.notes = (f"Easy Mode run {res.status}: {res.counts()['executed']} methods executed; reconstruction "
                            f"{res.reconstruction_status}; result {res.output.get('file_name', '-')}")
            self.ws.save(st.exp)
            write_json(self.ws.experiment_dir(st.exp.experiment_id) / "easy_mode_run.json", res.to_dict())
            if self.audit is not None:
                self.audit.log(A.EASY_RUN_COMPLETE, "INFO" if res.ok else "ERROR",
                               f"{res.experiment_id} {res.status} in {res.runtime_s:.1f}s; original unchanged "
                               f"{res.original_unchanged}")
        except Exception as exc:  # noqa: BLE001
            res.warnings.append(f"run record not written: {type(exc).__name__}: {exc}")


# ------------------------------------------------------------------ save result
FORMAT_SUFFIXES = {"PNG": (".png",), "JPG": (".jpg", ".jpeg"), "WEBP": (".webp",), "TIFF": (".tif", ".tiff"),
                   "BMP": (".bmp",)}


class SaveRefused(ValueError):
    pass


def save_result(res: EasyModeResult, dest: str | Path, audit=None) -> Path:
    """Copy the verified result image to ``dest``. The original image is never overwritten."""
    out = Path(str((res.output or {}).get("path") or ""))
    if not res.ok or not out.is_file():
        raise SaveRefused("There is no result image to save.")
    src = Path(str((res.input or {}).get("path") or ""))

    def is_original(p: Path) -> bool:
        if not src.name:
            return False
        try:
            if p.exists() and src.exists() and os.path.samefile(src, p):
                return True
        except OSError:
            pass
        return p.resolve() == src.resolve()

    dest = Path(dest)
    if is_original(dest):   # refuse the user's intent, even if the extension would be corrected below
        raise SaveRefused("The result cannot be saved over the original image. Choose a different name.")
    fmt = (res.output or {}).get("easy_format") or "PNG"
    if dest.suffix.lower() not in FORMAT_SUFFIXES.get(fmt, ()):
        dest = dest.with_name(dest.name + FORMAT_SUFFIXES.get(fmt, (out.suffix,))[0])
    if is_original(dest):
        raise SaveRefused("The result cannot be saved over the original image. Choose a different name.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".partial")
    import shutil

    shutil.copyfile(out, tmp)
    if sha256_file(tmp) != res.output.get("sha256"):
        tmp.unlink(missing_ok=True)
        raise SaveRefused("The copy did not match the verified result (hash mismatch); nothing was saved.")
    tmp.replace(dest)
    if audit is not None:
        audit.log(A.FILE_EXPORTED, detail=f"Easy result {out.name} -> {dest.name} (sha256 verified)")
    return dest


def default_result_name(res: EasyModeResult) -> str:
    stem = Path(str((res.input or {}).get("name") or "image")).stem
    fmt = (res.output or {}).get("easy_format") or "PNG"
    return f"{stem}_SynthProvenance{FORMAT_SUFFIXES.get(fmt, ('.png',))[0]}"
