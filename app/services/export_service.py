"""experiment.zip bundle export with SHA-256 manifest (hashes.txt)."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from app.core import audit_engine as A
from app.core.audit_engine import read_jsonl
from app.core.provenance_engine import build_provenance_graph
from app.models.experiment import Experiment
from app.services.provenance_service import c2pa_manifest_export
from app.services.report_service import write_all
from app.services.synthid_experiment import synthid_summary
from app.utils.paths import safe_arcname
from app.utils.serialization import dumps


def _events(ws, exp, audit):
    if audit is not None and audit.experiment_id == exp.experiment_id:
        return audit.events()
    p = ws.audit_path(exp)
    return read_jsonl(p) if p.is_file() else []


def export_bundle(exp: Experiment, ws, audit, dest: Path, engine_status: dict | None = None) -> Path:
    events = _events(ws, exp, audit)
    report_dir = ws.subdir(exp, "report")
    reports = write_all(exp, report_dir, events, engine_status)
    if audit is not None:
        audit.log(A.REPORT_GENERATED, detail=", ".join(sorted(reports)))
        events = _events(ws, exp, audit)
    members: list[tuple[str, bytes]] = []
    add = lambda name, data: members.append((safe_arcname("experiment", name), data))  # noqa: E731
    add("experiment.json", dumps(exp.to_dict()).encode("utf-8"))
    orig = ws.original_file(exp)
    add(f"original/{orig.name}", orig.read_bytes())
    out_dir = ws.subdir(exp, "output")
    for f in sorted(out_dir.iterdir()):
        if f.is_file() and not f.name.endswith(".partial"):
            add(f"output/{f.name}", f.read_bytes())
    for _fmt, p in sorted(reports.items()):
        add(f"report/{p.name}", p.read_bytes())
    done = [t for t in exp.transformations if t.status == "COMPLETE"]
    base = exp.baseline or {}
    add("metadata/metadata.json", dumps({
        "baseline": {"groups": base.get("groups"), "icc": base.get("icc"), "structure": base.get("structure"),
                     "compression": base.get("compression"), "external": base.get("external")},
        "transformations": {t.transformation_id: {"group_states": t.metadata_group_states,
                                                  "differences": t.metadata_differences} for t in done}}).encode("utf-8"))
    add("provenance/provenance.json", dumps({
        "baseline_c2pa": base.get("c2pa"), "baseline_signal": base.get("signal"),
        "provenance_graph": build_provenance_graph(base, exp.transformations),
        "external_classifications": [e.__dict__ for e in exp.external_classifications],
        "transformations": {t.transformation_id: {"provenance_differences": t.provenance_differences, "layers": t.layers}
                            for t in done}}).encode("utf-8"))
    add("provenance/c2pa_manifest.json", dumps(c2pa_manifest_export(base)).encode("utf-8"))
    add("synthid/synthid.json", dumps(synthid_summary(exp, engine_status)).encode("utf-8"))
    add("metrics/metrics.json", dumps({
        "baseline_statistics": exp.statistics,
        "transformations": {t.transformation_id: {"pixel_metrics": t.pixel_metrics, "steps": t.steps, "flags": t.flags}
                            for t in done}}).encode("utf-8"))
    add("logs/audit.log", ("\n".join(e.to_line() for e in events) + "\n").encode("utf-8"))
    add("logs/audit.jsonl", ("\n".join(json.dumps(e.to_dict(), ensure_ascii=False) for e in events) + "\n").encode("utf-8"))
    lines = [f"{hashlib.sha256(data).hexdigest()}  {name.split('/', 1)[1]}" for name, data in members]
    add("hashes.txt", ("# SHA-256 of every file in this bundle (sha256sum format), relative to experiment/\n"
                       + "\n".join(lines) + "\n").encode("utf-8"))
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".partial")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for name, data in members:
            zf.writestr(name, data)
    tmp.replace(dest)
    if audit is not None:
        audit.log(A.BUNDLE_EXPORTED, detail=f"{dest.name}: {len(members)} files")
    return dest
