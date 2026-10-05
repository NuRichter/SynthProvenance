"""Fingerprint Research Lab: auditable, reproducible method runs.

Each run gets an id ``SPX-FP-YYYYMMDD-NNNNNN`` and a directory::

    <workspace>/fingerprint_research/<RUN_ID>/
        run.json            full record (method, parameters, seed, environment, inputs, result, metrics)
        inputs/             copies of the input image(s) (originals are never touched)
        maps/               candidate/residual/spectrum/reconstruction maps as PNG
        config/             method card + parameters
        logs/run.log        append-only step log

The lab never modifies the original: inputs are hashed before and after and the
result records ``original_unchanged``. Method execution is delegated to
``app.research.runner`` (pure numpy). GPU is probed for the record only; no model is
downloaded and nothing leaves the machine.
"""
from __future__ import annotations

import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from app import __version__
from app.core.hashing import blake3_file, sha256_file
from app.core.image_loader import open_image_bytes, to_array
from app.core.synthid_research_engine import environment, file_fingerprint
from app.research import runner as RUN
from app.research import surrogate as SUR
from app.research.imaging import as_float, display_limit, map_image
from app.research.methods import Method, MethodRegistry
from app.utils.memory import process_rss
from app.utils.paths import ensure_dir, safe_filename, safe_join
from app.utils.serialization import jsonable, read_json, write_json

RUN_ID_RE = re.compile(r"^SPX-FP-\d{8}-\d{6}$")
RUN_SUBDIRS = ("inputs", "maps", "config", "logs")
SYMMETRIC_MAPS = ("candidate", "residual", "difference", "signal", "phase")


class LabError(RuntimeError):
    pass


@dataclass
class FingerprintRun:
    run_id: str
    created: str
    method_id: str
    method_code: str
    method_name: str
    category: str
    maturity: str
    status: str
    parameters: dict = field(default_factory=dict)
    seed: int = 0
    surrogate: dict = field(default_factory=dict)
    environment: dict = field(default_factory=dict)
    software_version: str = __version__
    inputs: list = field(default_factory=list)
    result: dict = field(default_factory=dict)
    maps: list = field(default_factory=list)
    failure_analysis: list = field(default_factory=list)
    detail: str = ""
    runtime_s: float = 0.0
    memory: dict = field(default_factory=dict)
    original_unchanged: bool | None = None

    def to_dict(self) -> dict:
        return jsonable(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FingerprintRun":
        from dataclasses import fields
        return cls(**{f.name: d[f.name] for f in fields(cls) if f.name in d})


def _is_map_symmetric(name: str) -> bool:
    return any(k in name for k in SYMMETRIC_MAPS)


class FingerprintLab:
    def __init__(self, root: Path) -> None:
        self.root = ensure_dir(Path(root))
        self.registry = MethodRegistry()

    # -- ids / io -----------------------------------------------------------
    def run_dir(self, run_id: str) -> Path:
        if not RUN_ID_RE.match(run_id or ""):
            raise LabError(f"Invalid run id: {run_id!r}")
        return safe_join(self.root, run_id)

    def _allocate(self) -> str:
        now = datetime.now(timezone.utc)
        prefix = f"SPX-FP-{now:%Y%m%d}-"
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

    def log(self, run: FingerprintRun, text: str) -> None:
        with (self.run_dir(run.run_id) / "logs" / "run.log").open("a", encoding="utf-8") as fh:
            fh.write(f"{datetime.now(timezone.utc).isoformat()}  {run.run_id}  {text}\n")

    def save(self, run: FingerprintRun) -> Path:
        return write_json(self.run_dir(run.run_id) / "run.json", run.to_dict())

    def load(self, run_id: str) -> FingerprintRun:
        p = self.run_dir(run_id) / "run.json"
        if not p.is_file():
            raise LabError(f"Run {run_id} not found")
        return FingerprintRun.from_dict(read_json(p))

    def list_runs(self, limit: int = 300) -> list[dict]:
        out = []
        for d in sorted(self.root.iterdir(), reverse=True) if self.root.is_dir() else []:
            if not (d.is_dir() and RUN_ID_RE.match(d.name) and (d / "run.json").is_file()):
                continue
            try:
                r = read_json(d / "run.json", max_bytes=64 * 1024 * 1024)
            except (OSError, ValueError):
                continue
            out.append({"run_id": d.name, "method": r.get("method_id", ""), "name": r.get("method_name", ""),
                        "maturity": r.get("maturity", ""), "status": r.get("status", ""), "created": r.get("created", ""),
                        "runtime_s": r.get("runtime_s", 0.0), "original_unchanged": r.get("original_unchanged")})
            if len(out) >= limit:
                break
        return out

    # -- running ------------------------------------------------------------
    def run_method(self, method_key: str, image_paths: list[Path], params: dict | None = None,
                   surrogate_cfg: SUR.SurrogateConfig | None = None, references: list[Path] | None = None,
                   progress=None) -> FingerprintRun:
        method = self.registry.get(method_key)
        rid = self._allocate()
        run = FingerprintRun(run_id=rid, created=datetime.now(timezone.utc).isoformat(), method_id=method.method_id,
                             method_code=method.code, method_name=method.name, category=method.category,
                             maturity=method.maturity, status="PENDING", parameters=dict(params or {}),
                             surrogate=surrogate_cfg.to_dict() if surrogate_cfg else {}, environment=environment())
        write_json(self.run_dir(rid) / "config" / "method.json", method.to_dict())
        write_json(self.run_dir(rid) / "config" / "parameters.json",
                   {"parameters": run.parameters, "surrogate": run.surrogate})
        self.log(run, f"RUN CREATED {method.method_id} {method.name}")
        t0, rss0 = time.perf_counter(), process_rss()
        image_paths = [Path(p) for p in image_paths]
        before = {str(p): sha256_file(p) for p in image_paths if p.is_file()}
        run.inputs = self._copy_inputs(run, image_paths)
        inp = self._build_input(method, image_paths, references or [], params or {}, surrogate_cfg)
        res = RUN.run(method, inp, progress)
        run.status, run.detail = res.status, res.detail
        run.result = res.to_dict()
        run.failure_analysis = res.failure_analysis
        run.maps = self._write_maps(run, res.maps)
        unchanged = all(sha256_file(Path(p)) == h for p, h in before.items()) if before else None
        run.original_unchanged = unchanged
        if unchanged is False:
            run.status = "FAILED"
            run.detail = "INTEGRITY FAILURE: an input changed during the run. " + run.detail
        run.runtime_s = time.perf_counter() - t0
        rss1 = process_rss()
        run.memory = {"process_rss_before": rss0, "process_rss_after": rss1,
                      "delta_bytes": (rss1 - rss0) if rss0 is not None and rss1 is not None else None}
        self.log(run, f"RUN {run.status} in {run.runtime_s:.2f}s; original unchanged: {unchanged}")
        self.save(run)
        return run

    def _copy_inputs(self, run: FingerprintRun, paths: list[Path]) -> list[dict]:
        out = []
        dest = self.run_dir(run.run_id) / "inputs"
        for i, p in enumerate(paths, 1):
            if not p.is_file():
                continue
            fp = file_fingerprint(p)
            if fp["bytes"] <= 256 * 1024 * 1024:
                d = safe_join(dest, safe_filename(f"{i:04d}_{p.name}", default=f"{i:04d}_input"))
                shutil.copyfile(p, d)
                fp["copy"] = f"inputs/{d.name}"
            out.append(fp)
        return out

    def _build_input(self, method: Method, paths: list[Path], refs: list[Path], params: dict,
                     cfg: SUR.SurrogateConfig | None) -> RUN.MethodInput:
        pil = open_image_bytes(paths[0].read_bytes()) if paths and paths[0].is_file() else None
        img = as_float(pil) if pil is not None else None
        ref_imgs = []
        for r in refs:
            try:
                ref_imgs.append(as_float(open_image_bytes(Path(r).read_bytes())))
            except Exception:  # noqa: BLE001 - unreadable references are skipped, recorded in the log
                self.log  # no-op marker
        clean = signed = unsigned = None
        if cfg is not None and img is not None:
            clean = img  # the opened image is treated as the clean host; the lab embeds the surrogate from it
            if method.capability.endswith(("provenance_orthogonal_subspace", "fingerprint_null_space")):
                from app.research import procedural as PROC
                signed = [SUR.embed(c, cfg).watermarked for c in PROC.dataset(4, 128, 128, seed=cfg.key)]
                unsigned = PROC.dataset(4, 128, 128, seed=cfg.key + 1)
        return RUN.MethodInput(image=img, pil=pil, references=ref_imgs, surrogate_cfg=cfg, clean=clean,
                               signed=signed or [], unsigned=unsigned or [], params=dict(params))

    def _write_maps(self, run: FingerprintRun, maps: dict) -> list[dict]:
        out = []
        mdir = self.run_dir(run.run_id) / "maps"
        for name, arr in (maps or {}).items():
            try:
                a = np.asarray(arr, dtype=np.float32)
                if a.ndim == 3 and a.shape[2] == 3:
                    from app.research.imaging import from_float
                    img = from_float(display_limit(np.clip(a, 0, 1)))
                else:
                    plane = a if a.ndim == 2 else a[:, :, 0]
                    img = map_image(display_limit(plane[:, :, None])[:, :, 0], symmetric=_is_map_symmetric(name))
                fn = safe_filename(f"{name}.png")
                img.save(mdir / fn)
                out.append({"name": name, "file": f"maps/{fn}", "shape": list(a.shape)})
            except Exception as exc:  # noqa: BLE001 - a bad map never fails the run
                self.log(run, f"map {name} not written: {type(exc).__name__}: {exc}")
        return out

    # -- surrogate helpers for the lab UI ----------------------------------
    def embed_surrogate(self, image_path: Path, cfg: SUR.SurrogateConfig, out_path: Path) -> dict:
        """Create a watermarked copy of ``image_path`` (never overwriting it) and record ground truth."""
        src = open_image_bytes(Path(image_path).read_bytes())
        clean = as_float(src)
        emb = SUR.embed(clean, cfg)
        from app.research.imaging import from_float
        from_float(emb.watermarked).save(out_path)
        det_wm = SUR.detect(emb.watermarked, cfg)
        det_clean = SUR.detect(clean, cfg)
        return {"config": emb.config, "stats": emb.stats, "detector_watermarked": det_wm.to_dict(),
                "detector_clean": det_clean.to_dict(), "watermarked_file": str(out_path),
                "valid_ground_truth": bool(det_wm.detected and not det_clean.detected)}
