"""Cross-Detector Research Lab store and the consent-gated external hand-off.

A reproducible run store (``SPX-XD-YYYYMMDD-NNNNNN``) that records a cross-detector study:
the imported external result (user-supplied), SynthProvenance's local evidence, the
comparison, the independent-evidence scorecard, an optional heatmap comparison, and the
benchmark matrix. The original image is hashed before and after; nothing is modified.

``ExternalDetectorGate`` is the only path to an external service. Like the SynthID online
gate it NEVER uploads from this process: it opens the detector's site in the browser after
explicit consent and the researcher uploads manually, under the service's own terms, then
imports the result back. Off by default.
"""
from __future__ import annotations

import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit


from app import __version__
from app.core.hashing import sha256_file
from app.core.synthid_research_engine import environment, file_fingerprint
from app.research import cross_detector as XD
from app.research import heatmap_compare as HM
from app.models.experiment import utc_now
from app.utils.paths import ensure_dir, safe_join
from app.utils.serialization import jsonable, read_json, write_json

RUN_ID_RE = re.compile(r"^SPX-XD-\d{8}-\d{6}$")
RUN_SUBDIRS = ("inputs", "external", "maps", "report", "logs")

# allow-listed external-detector destinations for the browser hand-off (https, no undocumented machine endpoints)
TRUTHSCAN_HOST = "truthscan.com"
ALLOWED_HOSTS = frozenset({"truthscan.com", "www.truthscan.com", "app.truthscan.com"})
NO_UPLOAD = ("SynthProvenance will NOT upload this image or call any API. It opens the detector's website in your "
             "browser and shows the file in Explorer. Any upload is your own manual action, under the service's "
             "sign-in, terms and access controls. Then import the result back with IMPORT TRUTHSCAN RESULT.")


class LabError(RuntimeError):
    pass


@dataclass
class CrossDetectorRun:
    run_id: str
    created: str
    status: str = "COMPLETE"
    detector: str = "TruthScan"
    ground_truth_level: int = 0
    ground_truth_direction: str = XD.UNKNOWN
    outcome: str = XD.INSUFFICIENT
    software_version: str = __version__
    environment: dict = field(default_factory=dict)
    input: dict = field(default_factory=dict)
    external: dict = field(default_factory=dict)
    local_evidence: dict = field(default_factory=dict)
    comparison: dict = field(default_factory=dict)
    scorecard: dict = field(default_factory=dict)
    heatmap: dict = field(default_factory=dict)
    benchmark_row: dict = field(default_factory=dict)
    original_unchanged: bool | None = None
    detail: str = ""

    def to_dict(self) -> dict:
        return jsonable(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CrossDetectorRun":
        from dataclasses import fields
        return cls(**{f.name: d[f.name] for f in fields(cls) if f.name in d})


class CrossDetectorLab:
    def __init__(self, root: Path) -> None:
        self.root = ensure_dir(Path(root))

    # -- ids / io -----------------------------------------------------------
    def run_dir(self, run_id: str) -> Path:
        if not RUN_ID_RE.match(run_id or ""):
            raise LabError(f"Invalid run id: {run_id!r}")
        return safe_join(self.root, run_id)

    def _allocate(self) -> str:
        now = datetime.now(timezone.utc)
        prefix = f"SPX-XD-{now:%Y%m%d}-"
        existing = [int(p.name[len(prefix):]) for p in self.root.glob(prefix + "*") if p.name[len(prefix):].isdigit()]
        seq = 1 + max(existing or [0])
        while True:
            rid = f"{prefix}{seq:06d}"
            try:
                (self.root / rid).mkdir(exist_ok=False)
                for s in RUN_SUBDIRS:
                    ensure_dir(self.root / rid / s)
                return rid
            except FileExistsError:
                seq += 1

    def log(self, run: CrossDetectorRun, text: str) -> None:
        with (self.run_dir(run.run_id) / "logs" / "run.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{utc_now()}  {run.run_id}  {text}\n")

    def save(self, run: CrossDetectorRun) -> Path:
        return write_json(self.run_dir(run.run_id) / "run.json", run.to_dict())

    def load(self, run_id: str) -> CrossDetectorRun:
        p = self.run_dir(run_id) / "run.json"
        if not p.is_file():
            raise LabError(f"Run {run_id} not found")
        return CrossDetectorRun.from_dict(read_json(p))

    def list_runs(self, limit: int = 300) -> list[dict]:
        out = []
        for d in sorted(self.root.iterdir(), reverse=True) if self.root.is_dir() else []:
            if not (d.is_dir() and RUN_ID_RE.match(d.name) and (d / "run.json").is_file()):
                continue
            try:
                r = read_json(d / "run.json", max_bytes=64 * 1024 * 1024)
            except (OSError, ValueError):
                continue
            out.append({"run_id": d.name, "detector": r.get("detector", ""), "outcome": r.get("outcome", ""),
                        "ground_truth_level": r.get("ground_truth_level", 0), "created": r.get("created", ""),
                        "input": (r.get("input") or {}).get("name", "")})
            if len(out) >= limit:
                break
        return out

    # -- recording a study --------------------------------------------------
    def record_study(self, image_path: Path, easy_result: dict, external: XD.ExternalResult | None,
                     ground_truth_level: int = 0, ground_truth_direction: str = XD.UNKNOWN,
                     heatmap_path: Path | None = None, local_maps: dict | None = None) -> CrossDetectorRun:
        """Build and persist a cross-detector study from a local EasyModeResult dict and an imported external result."""
        image_path = Path(image_path)
        before = sha256_file(image_path) if image_path.is_file() else ""
        rid = self._allocate()
        run = CrossDetectorRun(run_id=rid, created=utc_now(), environment=environment(),
                               ground_truth_level=int(ground_truth_level), ground_truth_direction=ground_truth_direction)
        t0 = time.perf_counter()
        self.log(run, "RUN CREATED")
        if image_path.is_file():
            run.input = file_fingerprint(image_path)
            dest = self.run_dir(rid) / "inputs" / image_path.name
            try:
                shutil.copyfile(image_path, dest)
                run.input["copy"] = f"inputs/{dest.name}"
            except OSError:
                pass

        local = XD.local_evidence_from_easy(easy_result, int(ground_truth_level))
        run.local_evidence = local.to_dict()
        run.detector = external.detector if external else "TruthScan"
        if external is not None:
            run.external = external.to_dict()
            write_json(self.run_dir(rid) / "external" / "external_result.json", external.to_dict())
            cmp = XD.compare(local, external, int(ground_truth_level), ground_truth_direction)
            run.comparison = cmp.to_dict()
            run.outcome = cmp.outcome
            run.scorecard = XD.scorecard(local, external, int(ground_truth_level))
            # optional heatmap comparison against the local maps
            if heatmap_path is not None and Path(heatmap_path).is_file() and local_maps:
                try:
                    from app.research.imaging import as_float
                    from app.core.image_loader import open_image_bytes
                    ext_heat = as_float(open_image_bytes(Path(heatmap_path).read_bytes()))
                    run.heatmap = HM.compare_against_local_maps(ext_heat, local_maps)
                    shutil.copyfile(heatmap_path, self.run_dir(rid) / "external" / "external_heatmap.png")
                except Exception as exc:  # noqa: BLE001
                    run.heatmap = {"error": f"{type(exc).__name__}: {exc}"}
            run.detail = cmp.statement
        else:
            run.outcome = XD.INSUFFICIENT
            run.scorecard = XD.scorecard(local, XD.ExternalResult(final_result=""), int(ground_truth_level))
            run.detail = "Local analysis only; no external result imported yet."
        run.benchmark_row = benchmark_row(run)

        if image_path.is_file():
            after = sha256_file(image_path)
            run.original_unchanged = after == before
            if run.original_unchanged is False:
                run.status = "FAILED"
                run.detail = "INTEGRITY FAILURE: the input changed during the study. " + run.detail
        self.log(run, f"RUN {run.status} in {time.perf_counter() - t0:.2f}s; outcome {run.outcome}")
        self.save(run)
        return run


# ------------------------------------------------------------------ benchmark matrix (Section 23)
BENCHMARK_COLUMNS = ["IMAGE", "GROUND TRUTH", "TRUTHSCAN", "SYNTHPROVENANCE", "C2PA", "METADATA", "SPECTRAL",
                     "RECONSTRUCTION", "FINGERPRINT", "FINAL RESEARCH STATUS"]


def _dim_dir(local: dict, name: str) -> str:
    for d in (local.get("dimensions") or []):
        if str(d.get("name", "")).lower().startswith(name.lower()):
            return d.get("direction", "-")
    return "NOT EVALUATED"


def benchmark_row(run: CrossDetectorRun) -> dict:
    local = run.local_evidence or {}
    ext = run.external or {}
    prov = ""
    for d in (local.get("dimensions") or []):
        if d.get("family") == XD.FAMILY_PROVENANCE:
            prov = d.get("observation", "")[:60]
            break
    truth = f"LEVEL {run.ground_truth_level} {XD.GROUND_TRUTH_LEVELS.get(run.ground_truth_level, '')}"
    ts = ext.get("final_result", "not imported") if ext else "not imported"
    if ext and ext.get("confidence") is not None:
        ts += f" ({float(ext['confidence']):.0%})"
    return {
        "IMAGE": run.input.get("name", run.run_id), "GROUND TRUTH": truth, "TRUTHSCAN": ts,
        "SYNTHPROVENANCE": _overall(local), "C2PA": _dim_dir(local, "Provenance"), "METADATA": prov or "-",
        "SPECTRAL": _dim_dir(local, "Spectral"), "RECONSTRUCTION": _dim_dir(local, "Reconstruction"),
        "FINGERPRINT": _dim_dir(local, "Residual"), "FINAL RESEARCH STATUS": run.outcome,
    }


def _overall(local: dict) -> str:
    dirs = [d.get("direction") for d in (local.get("dimensions") or [])]
    if XD.LEANS_SYNTHETIC in dirs and XD.LEANS_AUTHENTIC not in dirs:
        return XD.LEANS_SYNTHETIC
    if XD.LEANS_AUTHENTIC in dirs and XD.LEANS_SYNTHETIC not in dirs:
        return XD.LEANS_AUTHENTIC
    return XD.DESCRIPTIVE


def write_benchmark_csv(rows: list[dict], path: Path) -> Path:
    import csv
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(BENCHMARK_COLUMNS)
        for r in rows:
            w.writerow([r.get(c, "") for c in BENCHMARK_COLUMNS])
    return path


# ------------------------------------------------------------------ external hand-off (no upload)
@dataclass
class HandoffPlan:
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
        return (f"EXTERNAL DETECTOR: {self.name}\nURL: {self.url}\n\nFILE: {self.image_path}\n"
                f"SHA-256: {self.image_sha256}\n\n{self.statement}\n\nOpen the detector website now?")


def _check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS or parts.username or parts.password:
        raise XD_PolicyError(f"Not an allow-listed external-detector https URL: {url}")


class XD_PolicyError(PermissionError):
    pass


class ExternalDetectorGate:
    """Session switch for the TruthScan browser hand-off. OFF by default; enabling and every open need consent.

    This gate never uploads an image and never calls an API. It opens the detector's website; the researcher uploads
    manually and imports the result back. Automated repeated submission / optimisation against the service is refused.
    """

    URL = "https://truthscan.com/ai-image-detector"

    def __init__(self, opener: Callable[[str], bool] | None = None, reveal: Callable[[Path], None] | None = None) -> None:
        self.enabled = False
        self._opener, self._reveal = opener, reveal
        self.history: list[dict] = []

    def enable(self, confirmed: bool) -> None:
        if confirmed is not True:
            raise XD_PolicyError("External detector integration requires explicit confirmation.")
        self.enabled = True

    def disable(self) -> None:
        self.enabled = False

    def plan(self, image_path: Path) -> HandoffPlan:
        if not self.enabled:
            raise XD_PolicyError("External detector integration is OFF. Enable it explicitly first.")
        _check_url(self.URL)
        p = Path(image_path)
        if not p.is_file():
            raise XD_PolicyError(f"Image not found: {p}")
        return HandoffPlan("TruthScan AI Image Detector", self.URL, str(p), p.name, sha256_file(p), created=utc_now())

    def execute(self, plan: HandoffPlan, consent: bool) -> dict:
        if not self.enabled:
            raise XD_PolicyError("External detector integration is OFF.")
        if consent is not True:
            raise XD_PolicyError("No explicit consent given; nothing was opened.")
        _check_url(plan.url)
        if self._opener is None:
            raise XD_PolicyError("No browser opener is available in this context.")
        opened = bool(self._opener(plan.url))
        if self._reveal is not None:
            self._reveal(Path(plan.image_path))
        entry = {**plan.to_dict(), "opened_utc": utc_now(), "browser_opened": opened,
                 "uploaded_by_synthprovenance": False, "external_submission_id": "", "response": "pending import"}
        self.history.append(entry)
        return entry
