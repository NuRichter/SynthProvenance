"""SynthID Research Lab engine: auditable runs with reproducible records.

Every run gets an id ``SPX-SID-YYYYMMDD-NNNNNN`` and a directory::

    <workspace>/synthid_research/<RUN_ID>/
        run.json            full record (inputs, outputs, method, parameters, seed, environment, metrics)
        source/             copies of the inputs (the originals are never touched)
        output/             per-item verifier records
        metrics/            benchmark metrics and ROC points
        config/             method spec and parameters
        logs/run.log        append-only step log

Run kinds: DETECTION (method SID-M1 on one or more images), BENCHMARK (SID-M1
on a labelled dataset) and ONLINE (a user-confirmed hand-off to an official
verifier plus the user-recorded result). Each original input is hashed before
and after a run and the result is stored as ``original_unchanged``.
"""
from __future__ import annotations

import platform
import re
import shutil
import sys
import time
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from app import __version__
from app.core.hashing import blake3_file, sha256_file
from app.core.synthid_benchmark import DatasetItem, run_benchmark
from app.core.synthid_detector_registry import MethodRegistry
from app.core.synthid_local_verifier import LocalVerifier
from app.models.experiment import utc_now
from app.utils.memory import process_rss
from app.utils.paths import ensure_dir, safe_filename, safe_join
from app.utils.serialization import jsonable, read_json, write_json
from app.utils.system import ToolError, package_versions, run_tool

RUN_ID_RE = re.compile(r"^SPX-SID-\d{8}-\d{6}$")
RUN_SUBDIRS = ("source", "output", "metrics", "config", "logs")
MATRIX_COLUMNS = ["Image", "Source", "Method", "Detector", "Before", "After", "Signal Score", "Confidence", "MAE", "PSNR",
                  "SSIM", "LPIPS", "Resolution", "Runtime", "Memory", "Status"]
LPIPS_NOTE = "NOT COMPUTED"  # no learned perceptual model is bundled; never estimated
RESULT_LANGUAGE = "Observable provenance state changed under the tested transformation."
MAX_COPY_BYTES = 512 * 1024 * 1024


class ResearchError(RuntimeError):
    pass


def new_run_id(sequence: int, when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    return f"SPX-SID-{when:%Y%m%d}-{int(sequence):06d}"


@lru_cache(maxsize=1)
def gpu_info() -> dict:
    """Local GPU/CUDA description via nvidia-smi when present (subprocess, no network). Never required."""
    exe = shutil.which("nvidia-smi")
    if not exe:
        return {"gpu": "none detected", "cuda": "n/a"}
    try:
        res = run_tool([exe, "--query-gpu=name,driver_version", "--format=csv,noheader"], timeout=8)
        head = run_tool([exe], timeout=8).stdout.decode("utf-8", "replace")
    except ToolError as exc:
        return {"gpu": f"probe failed: {exc}", "cuda": "unknown"}
    cuda = re.search(r"CUDA (?:UMD )?Version:\s*([0-9.]+)", head)
    return {"gpu": res.stdout.decode("utf-8", "replace").strip().splitlines()[0][:200] if res.returncode == 0 and res.stdout
            else "unknown", "cuda": cuda.group(1) if cuda else "unknown"}


def environment() -> dict:
    g = gpu_info()
    return {"software": f"SynthProvenance {__version__}", "os": f"{platform.system()} {platform.release()} ({platform.version()})",
            "machine": platform.machine(), "cpu": platform.processor() or platform.machine(), "python": sys.version.split()[0],
            "frozen": bool(getattr(sys, "frozen", False)), "gpu": g["gpu"], "cuda_version": g["cuda"],
            "libraries": package_versions()}


def file_fingerprint(path: Path) -> dict:
    p = Path(path)
    out = {"name": p.name, "path": str(p), "bytes": p.stat().st_size, "sha256": sha256_file(p), "blake3": blake3_file(p) or ""}
    try:
        from PIL import Image

        with Image.open(p) as im:
            out["resolution"] = f"{im.size[0]}x{im.size[1]}"
            out["mode"] = im.mode
    except Exception as exc:  # noqa: BLE001 - unreadable files are recorded, not fatal
        out["resolution"] = "unreadable"
        out["mode"] = f"{type(exc).__name__}"
    return out


@dataclass
class ResearchRun:
    run_id: str
    kind: str
    created: str
    method_id: str
    method_name: str
    pipeline: list = field(default_factory=list)
    parameters: dict = field(default_factory=dict)
    seed: int = 0
    device: str = "CPU (engine subprocess; device use is engine-defined)"
    method_spec: dict = field(default_factory=dict)
    source_repository: str = ""
    source_version: str = ""
    license: str = ""
    model_version: str = ""
    model_hash: str = "n/a (no model bundled)"
    environment: dict = field(default_factory=dict)
    inputs: list = field(default_factory=list)
    outputs: list = field(default_factory=list)
    records: list = field(default_factory=list)
    matrix: list = field(default_factory=list)
    benchmark: dict = field(default_factory=dict)
    online: dict = field(default_factory=dict)
    status: str = "PENDING"
    detail: str = ""
    runtime_s: float = 0.0
    memory: dict = field(default_factory=dict)
    original_unchanged: bool | None = None
    limitations: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return jsonable(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ResearchRun":
        return cls(**{f.name: d[f.name] for f in fields(cls) if f.name in d})


LIMITATIONS = [
    "SynthID is an embedded pixel-domain signal. It is measured only by a configured local engine (SID-M1) or by the "
    "researcher through Google's official verifier; otherwise its state is UNAVAILABLE.",
    "A NOT DETECTED result does not establish that an image is human-created, and never verifies removal.",
    "Metadata or C2PA absence says nothing about SynthID. Each layer is reported separately.",
    "Benchmark labels are researcher-supplied ground truth. Metrics describe the tested dataset and engine build only.",
    "LPIPS is not computed: no learned perceptual model is bundled.",
]


class ResearchStore:
    def __init__(self, root: Path) -> None:
        self.root = ensure_dir(Path(root))

    # -- ids / paths ------------------------------------------------------
    def run_dir(self, run_id: str) -> Path:
        if not RUN_ID_RE.match(run_id or ""):
            raise ResearchError(f"Invalid research run id: {run_id!r}")
        return safe_join(self.root, run_id)

    def _allocate(self) -> str:
        now = datetime.now(timezone.utc)
        prefix = f"SPX-SID-{now:%Y%m%d}-"
        seq = 1 + max([int(p.name[len(prefix):]) for p in self.root.glob(prefix + "*") if p.name[len(prefix):].isdigit()]
                      or [0])
        while True:
            rid = new_run_id(seq, now)
            try:
                (self.root / rid).mkdir(exist_ok=False)
                for sub in RUN_SUBDIRS:
                    ensure_dir(self.root / rid / sub)
                return rid
            except FileExistsError:
                seq += 1

    def _new(self, kind: str, method, parameters: dict, seed: int) -> ResearchRun:
        rid = self._allocate()
        run = ResearchRun(run_id=rid, kind=kind, created=utc_now(), method_id=method.method_id,
                          method_name=method.method_name, parameters=dict(parameters), seed=seed,
                          method_spec=method.to_dict(), source_repository=method.source, source_version=method.version,
                          license=method.license, environment=environment(), limitations=list(LIMITATIONS))
        write_json(self.run_dir(rid) / "config" / "parameters.json",
                   {"method": method.to_dict(), "parameters": parameters, "seed": seed})
        self.log(run, f"RUN CREATED {kind} {method.method_id} {method.method_name}")
        return run

    def log(self, run: ResearchRun, text: str) -> None:
        with (self.run_dir(run.run_id) / "logs" / "run.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{utc_now()}  {run.run_id}  {text}\n")

    def save(self, run: ResearchRun) -> Path:
        return write_json(self.run_dir(run.run_id) / "run.json", run.to_dict())

    def load(self, run_id: str) -> ResearchRun:
        p = self.run_dir(run_id) / "run.json"
        if not p.is_file():
            raise ResearchError(f"Research run {run_id} not found")
        return ResearchRun.from_dict(read_json(p))

    def list_runs(self, limit: int = 200) -> list[dict]:
        out = []
        for d in sorted(self.root.iterdir(), reverse=True) if self.root.is_dir() else []:
            if not (d.is_dir() and RUN_ID_RE.match(d.name) and (d / "run.json").is_file()):
                continue
            try:
                r = read_json(d / "run.json", max_bytes=64 * 1024 * 1024)
            except (OSError, ValueError):
                continue
            out.append({"run_id": d.name, "kind": r.get("kind", ""), "method": r.get("method_name", ""),
                        "status": r.get("status", ""), "created": r.get("created", ""), "inputs": len(r.get("inputs") or []),
                        "original_unchanged": r.get("original_unchanged")})
            if len(out) >= limit:
                break
        return out

    # -- helpers ------------------------------------------------------------
    def _copy_inputs(self, run: ResearchRun, paths: list[Path]) -> list[dict]:
        fps = []
        src_dir = self.run_dir(run.run_id) / "source"
        for i, p in enumerate(paths, 1):
            fp = file_fingerprint(p)
            if fp["bytes"] <= MAX_COPY_BYTES:
                dest = safe_join(src_dir, safe_filename(f"{i:04d}_{p.name}", default=f"{i:04d}_input"))
                shutil.copyfile(p, dest)
                fp["copy"] = f"source/{dest.name}"
            else:
                fp["copy"] = "not copied (larger than 512 MiB); hashes recorded"
            fps.append(fp)
        return fps

    def _finish(self, run: ResearchRun, originals: list[dict], t0: float, rss0) -> ResearchRun:
        unchanged = all(sha256_file(Path(fp["path"])) == fp["sha256"] for fp in originals)
        run.original_unchanged = unchanged
        if not unchanged:
            run.status = "FAILED"
            run.detail = "INTEGRITY FAILURE: an original input changed during the run. " + run.detail
        run.runtime_s = time.perf_counter() - t0
        rss1 = process_rss()
        run.memory = {"process_rss_before": rss0, "process_rss_after": rss1,
                      "delta_bytes": (rss1 - rss0) if rss0 is not None and rss1 is not None else None}
        self.log(run, f"RUN {run.status} in {run.runtime_s:.2f}s; original unchanged: {unchanged}")
        self.save(run)
        return run

    # -- run kinds ----------------------------------------------------------
    def run_detection(self, paths: list[Path], verifier: LocalVerifier, registry: MethodRegistry, progress=None,
                      seed: int = 0) -> ResearchRun:
        paths = [Path(p) for p in paths]
        if not paths:
            raise ResearchError("No input images.")
        t0, rss0 = time.perf_counter(), process_rss()
        run = self._new("DETECTION", registry.get("SID-M1"), {"engine": verifier.status()}, seed)
        run.pipeline = ["hash original", "copy to source/", "SID-M1 local engine on preserved copy", "re-hash original"]
        run.inputs = self._copy_inputs(run, paths)
        out_dir = self.run_dir(run.run_id) / "output"
        for n, fp in enumerate(run.inputs, 1):
            if progress:
                progress(int(10 + 80 * n / len(run.inputs)), f"SynthID verification {n}/{len(run.inputs)}")
            target = self.run_dir(run.run_id) / fp["copy"] if fp["copy"].startswith("source/") else Path(fp["path"])
            rec = verifier.verify(target).to_dict()
            rec["image"] = fp["name"]
            run.records.append(rec)
            name = safe_filename(f"{n:04d}_verification.json")
            write_json(out_dir / name, rec)
            run.outputs.append({"name": f"output/{name}", "sha256": sha256_file(out_dir / name)})
            run.model_version = run.model_version or rec.get("model_version", "")
            run.matrix.append(_matrix_row(fp, "SID-M1", rec.get("detector") or "none", rec["state"], "-",
                                          rec.get("score"), rec.get("confidence"), None, rec.get("runtime_ms", 0.0),
                                          rec["state"]))
            self.log(run, f"{fp['name']} sha256 {fp['sha256'][:16]}... -> {rec['state']} ({rec.get('detail', '')[:120]})")
        states = {r["state"] for r in run.records}
        run.status = "UNAVAILABLE" if states == {"UNAVAILABLE"} else "COMPLETE"
        run.detail = ("LOCAL SYNTHID ENGINE: UNAVAILABLE. No measurement was performed and nothing was inferred."
                      if run.status == "UNAVAILABLE" else f"{len(run.records)} image(s) verified by the local engine.")
        return self._finish(run, run.inputs, t0, rss0)

    def run_benchmark(self, items: list[DatasetItem], verifier: LocalVerifier, registry: MethodRegistry,
                      threshold: float = 0.5, seed: int = 20261002, progress=None) -> ResearchRun:
        t0, rss0 = time.perf_counter(), process_rss()
        run = self._new("BENCHMARK", registry.get("SID-M1"), {"threshold": threshold, "items": len(items),
                                                               "engine": verifier.status()}, seed)
        run.pipeline = ["load labelled dataset", "SID-M1 per item", "ROC / AUC / CI", "re-hash every input"]
        originals = [{"path": it.path, "sha256": sha256_file(Path(it.path))} for it in items]
        run.inputs = [{"name": Path(it.path).name, "path": it.path, "label": it.label, "group": it.group, "split": it.split,
                       "sha256": o["sha256"]} for it, o in zip(items, originals)]
        res = run_benchmark(items, verifier, threshold, seed, progress)
        run.benchmark = res.to_dict()
        run.records = res.items
        run.status, run.detail = res.status, res.detail
        for r in res.items:
            run.matrix.append(_matrix_row({"name": Path(r["path"]).name, "resolution": "-"}, "SID-M1",
                                          r.get("detector") or "none", r["state"], "-", r.get("score"), r.get("confidence"),
                                          None, r.get("runtime_ms", 0.0), f"label={r['label']} {r['group']}"))
        write_json(self.run_dir(run.run_id) / "metrics" / "benchmark.json", run.benchmark)
        return self._finish(run, originals, t0, rss0)

    def record_online(self, entry: dict, reported: str, service: str, note: str, registry: MethodRegistry) -> ResearchRun:
        t0, rss0 = time.perf_counter(), process_rss()
        run = self._new("ONLINE", registry.get("SID-ON1"), {"destination": entry.get("dest_id"), "url": entry.get("url")}, 0)
        run.pipeline = ["explicit enable", "plan shown (destination, file, SHA-256)", "explicit consent",
                        "browser opened by OS", "manual upload by researcher", "result recorded by researcher"]
        p = Path(entry.get("image_path", ""))
        run.inputs = [file_fingerprint(p)] if p.is_file() else []
        run.online = {**entry, "reported_result": reported[:300], "service": service[:120], "note": note[:1000],
                      "tier": "EXTERNAL SYNTHID VERIFICATION (user-recorded, unverified)"}
        run.records = [run.online]
        run.status, run.detail = "RECORDED", "User-recorded result from an official verifier. Not verified by SynthProvenance."
        if run.inputs:
            run.matrix.append(_matrix_row(run.inputs[0], "SID-ON1", service or entry.get("name", ""), reported or "-", "-",
                                          None, None, None, 0.0, "RECORDED (user)"))
        return self._finish(run, run.inputs, t0, rss0)

    def import_conditions(self, run: ResearchRun, experiment) -> ResearchRun:
        """Append the main experiment's per-condition SynthID before/after with measured pixel metrics."""
        for t in experiment.transformations:
            if t.status != "COMPLETE":
                continue
            pm = t.pixel_metrics or {}
            before = (t.synthid_before or {}).get("state", "UNAVAILABLE")
            after = (t.synthid_after or {}).get("state", "UNAVAILABLE")
            fp = {"name": f"{t.transformation_id} {t.label}",
                  "resolution": "x".join(map(str, t.output_dimensions)) if t.output_dimensions else "-"}
            psnr = "inf" if pm.get("psnr_infinite") else pm.get("psnr_db")
            run.matrix.append(_matrix_row(fp, "TRANSFORMATION", (t.synthid_after or {}).get("engine", "none"), before, after,
                                          (t.synthid_after or {}).get("score"), (t.synthid_after or {}).get("confidence"),
                                          (pm.get("mae"), psnr, pm.get("ssim")), t.duration_ms, pm.get("verdict", "-")))
        self.save(run)
        return run


def _matrix_row(fp: dict, method: str, detector: str, before, after, score, confidence, pix, runtime_ms, status) -> dict:
    mae, psnr, ssim = pix if pix else ("-", "-", "-")
    return {"Image": fp.get("name", "-"), "Source": fp.get("sha256", "")[:16] or "-", "Method": method,
            "Detector": detector, "Before": before, "After": after, "Signal Score": score, "Confidence": confidence,
            "MAE": mae, "PSNR": psnr, "SSIM": ssim, "LPIPS": LPIPS_NOTE, "Resolution": fp.get("resolution", "-"),
            "Runtime": f"{(runtime_ms or 0.0):.1f} ms", "Memory": "-", "Status": status}
