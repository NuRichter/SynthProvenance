"""Experiment workspace management.

Layout of one experiment (mirrors the exported bundle)::

    <workspace>/experiments/<EXPERIMENT_ID>/
        experiment.json
        original/<input file>
        output/<T001_operation.ext> ...
        report/  metadata/  provenance/  metrics/  logs/audit.jsonl
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from app import __version__
from app.core.image_writer import atomic_write_bytes
from app.models.experiment import Experiment, new_experiment_id, utc_now
from app.utils.paths import ensure_dir, safe_filename, safe_join, user_data_dir
from app.utils.serialization import read_json, write_json
from app.utils.system import system_info

SUBDIRS = ("original", "output", "report", "metadata", "provenance", "synthid", "metrics", "logs")
WORKSPACE_DIRS = ("experiments", "reports", "cache", "logs", "exports")
EXPERIMENT_ID_RE = re.compile(r"^(SPX-\d{4}-\d{4}-\d{6}|SP-\d{8}-\d{6}-[0-9A-F]{4})$")


class ExperimentError(RuntimeError):
    pass


class Workspace:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else user_data_dir() / "workspace"
        for name in WORKSPACE_DIRS:
            ensure_dir(self.root / name)
        self.experiments_dir = self.root / "experiments"
        self.exports_dir = self.root / "exports"
        self.reports_dir = self.root / "reports"
        self.cache_dir = self.root / "cache"
        self.logs_dir = self.root / "logs"

    # -- paths -----------------------------------------------------------
    def experiment_dir(self, experiment_id: str) -> Path:
        if not EXPERIMENT_ID_RE.match(experiment_id or ""):
            raise ExperimentError(f"Invalid experiment id: {experiment_id!r}")
        return safe_join(self.experiments_dir, experiment_id)

    def subdir(self, experiment: Experiment, name: str) -> Path:
        if name not in SUBDIRS:
            raise ExperimentError(f"Unknown experiment sub-directory {name!r}")
        return ensure_dir(self.experiment_dir(experiment.experiment_id) / name)

    def audit_path(self, experiment: Experiment) -> Path:
        return self.subdir(experiment, "logs") / "audit.jsonl"

    def output_path(self, experiment: Experiment, transformation_id: str, operation: str, ext: str) -> Path:
        name = safe_filename(f"{transformation_id}_{operation}{ext}")
        return safe_join(self.subdir(experiment, "output"), name)

    # -- lifecycle -------------------------------------------------------
    def create(self, input_name: str, data: bytes, baseline: dict | None = None) -> Experiment:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        prefix = f"SPX-{now:%Y}-{now:%m%d}-"
        seq = 1 + max([int(p.name[len(prefix):]) for p in self.experiments_dir.glob(prefix + "*")
                       if p.name[len(prefix):].isdigit()] or [0])
        while True:
            exp_id = new_experiment_id(seq, now)
            try:
                (self.experiments_dir / exp_id).mkdir(parents=False, exist_ok=False)
                break
            except FileExistsError:
                seq += 1
        exp = Experiment(experiment_id=exp_id, created=utc_now(), app_version=__version__, input_name=input_name)
        d = self.experiment_dir(exp_id)
        for sub in SUBDIRS:
            ensure_dir(d / sub)
        original = safe_join(d / "original", safe_filename(input_name, default="input"))
        atomic_write_bytes(original, data)
        exp.original_path = str(original.relative_to(d)).replace("\\", "/")
        exp.workspace = str(d)
        exp.baseline = baseline or {}
        try:
            exp.environment = system_info()
        except Exception:  # noqa: BLE001
            exp.environment = {}
        self.save(exp)
        return exp

    def save(self, exp: Experiment) -> Path:
        d = self.experiment_dir(exp.experiment_id)
        return write_json(d / "experiment.json", exp.to_dict())

    def load(self, experiment_id: str) -> Experiment:
        d = self.experiment_dir(experiment_id)
        path = d / "experiment.json"
        if not path.is_file():
            raise ExperimentError(f"Experiment {experiment_id} not found in {self.experiments_dir}")
        try:
            exp = Experiment.from_dict(read_json(path))
        except (ValueError, TypeError, KeyError) as exc:
            raise ExperimentError(f"experiment.json is unreadable: {exc}") from exc
        exp.workspace = str(d)
        return exp

    def resolve(self, exp: Experiment, relative: str) -> Path:
        """Resolve a path stored in experiment.json safely inside its directory."""
        return safe_join(self.experiment_dir(exp.experiment_id), *str(relative).replace("\\", "/").split("/"))

    def original_file(self, exp: Experiment) -> Path:
        return self.resolve(exp, exp.original_path)

    def recent(self, limit: int = 20) -> list[dict]:
        items = []
        for d in self.experiments_dir.iterdir() if self.experiments_dir.is_dir() else []:
            if not (d.is_dir() and EXPERIMENT_ID_RE.match(d.name)):
                continue
            path = d / "experiment.json"
            if not path.is_file():
                continue
            try:
                data = read_json(path, max_bytes=32 * 1024 * 1024)
            except (OSError, ValueError):
                continue
            base = data.get("baseline") or {}
            items.append({
                "experiment_id": d.name,
                "created": data.get("created", ""),
                "input_name": data.get("input_name", ""),
                "transformations": len(data.get("transformations") or []),
                "signal": (base.get("signal") or {}).get("state", ""),
                "status": data.get("status", ""),
                "mtime": path.stat().st_mtime,
            })
        items.sort(key=lambda x: x["mtime"], reverse=True)
        return items[:limit]

    def delete(self, experiment_id: str) -> None:
        d = self.experiment_dir(experiment_id)
        if d.is_dir():
            shutil.rmtree(d)
