"""Transformation orchestration: execute, persist, measure, compare, audit."""
from __future__ import annotations

import json
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from app.analyzers.synthid_analyzer import analyze_synthid
from app.core import audit_engine as A
from app.core.image_loader import ImageLoadError, open_image_bytes, read_file_bytes
from app.core.image_writer import EXTENSIONS, FORMAT_CAPS, atomic_write_bytes, encode_as
from app.core.metadata_engine import Analysis, analyze_bytes, diff_groups
from app.core.pixel_integrity import compare_images
from app.core.transform_engine import (
    EXTRA_ROWS,
    MATRIX_BATTERY,
    MATRIX_ROWS,
    OPERATIONS,
    TransformError,
    TransformOutput,
    parse_chain,
    run_pixel_operation,
    source_metadata,
    validate_params,
)
from app.models.experiment import Experiment, TransformationRecord, utc_now
from app.services.c2pa_experiment import C2PA_WARNING, separate_provenance
from app.services.metadata_sanitizer import PROFILES, SanitizeOptions, SanitizeRefused, sanitize
from app.services.provenance_service import compare_layers, provenance_diff
from app.utils.logging import get_logger
from app.utils.validation import InputValidationError

_log = get_logger("transform")
DIMENSION_FLAG = "DIMENSION CHANGE DETECTED"
LOSSY_OPS = {"jpeg_reencode", "webp_reencode", "controlled_recompression", "format_conversion", "format_chain"}
GEOMETRY_OPS = {"resize", "crop"}
Progress = Callable[[int, str], None]


@dataclass
class SourceContext:
    path: Path
    analysis: Analysis
    analysis_dict: dict
    synthid: dict = field(default_factory=dict)

    @property
    def image(self):
        return self.analysis.image

    @property
    def data(self) -> bytes:
        return self.analysis.data

    @property
    def fmt(self) -> str:
        return self.analysis.info.format


def compact_metrics(pm) -> dict:
    d = pm.to_dict() if hasattr(pm, "to_dict") else pm
    return {k: d.get(k) for k in ("verdict", "comparable", "changed_pixels", "changed_pixel_pct", "mae", "max_abs_error",
                                  "psnr_db", "psnr_infinite", "ssim")}


class TransformationService:
    def __init__(self, workspace, audit, synthid_engine=None, exiftool_path: str | None = None) -> None:
        self.ws = workspace
        self.audit = audit
        self.engine = synthid_engine
        self.exiftool_path = exiftool_path

    # ------------------------------------------------------------------ run
    def run(self, exp: Experiment, src: SourceContext, op: str, params: dict | None = None,
            progress: Progress | None = None) -> TransformationRecord:
        prog = progress or (lambda _p, _t: None)
        spec = OPERATIONS.get(op)
        if spec is None:
            raise TransformError(f"Unknown operation {op!r}")
        t0 = time.perf_counter()
        tid = exp.next_transformation_id()
        info = src.analysis.info
        rec = TransformationRecord(tid, exp.experiment_id, op, spec.label, utc_now(), {}, input_path=exp.original_path,
                                   input_sha256=src.analysis.hashes["sha256"], input_dimensions=(info.width, info.height))
        self.audit.log(A.TRANSFORMATION_STARTED, detail=f"{tid} {spec.label}")
        prog(5, f"{tid} {spec.label}: transforming")
        try:
            out = self._execute(exp, src, op, params or {}, rec, prog)
        except SanitizeRefused as exc:
            return self._finish_failed(exp, rec, "REFUSED", str(exc), A.TRANSFORMATION_REFUSED, "WARNING", t0)
        except (TransformError, ImageLoadError, InputValidationError, ValueError, OSError, MemoryError) as exc:
            return self._finish_failed(exp, rec, "FAILED", f"{type(exc).__name__}: {exc}", A.TRANSFORMATION_FAILED, "ERROR", t0)
        except Exception as exc:  # noqa: BLE001 - unexpected defects are recorded, never crash the GUI
            _log.error("Transformation %s crashed:\n%s", tid, traceback.format_exc())
            return self._finish_failed(exp, rec, "FAILED", f"Internal error {type(exc).__name__}: {exc}",
                                       A.TRANSFORMATION_FAILED, "ERROR", t0)

        out_path = self.ws.output_path(exp, tid, op, out.ext)
        atomic_write_bytes(out_path, out.data)
        rec.output_path = f"output/{out_path.name}"
        prog(35, f"{tid}: analysing output")
        out_an = analyze_bytes(out.data, out_path, out_path.name, exiftool_path=self.exiftool_path)
        out_dict = out_an.to_dict()
        prog(55, f"{tid}: verifying pixels")
        pm = compare_images(src.image, out_an.image, region=out.region)
        pmd = pm.to_dict()
        self.audit.log(A.PIXEL_VERIFICATION_COMPLETE, detail=f"{tid}: {pm.verdict}; changed pixels "
                       f"{pm.changed_pixels if pm.changed_pixels is not None else 'n/a'}")
        diffs, gstates = diff_groups(src.analysis_dict["groups"], out_dict["groups"])
        prov = provenance_diff(src.analysis_dict, out_dict)
        prog(75, f"{tid}: SynthID layer")
        sid_after = analyze_synthid(self.engine, out_path, tid, out_dict).to_dict()
        rec.layers = compare_layers(src.analysis_dict, out_dict, pmd, src.synthid, sid_after,
                                    exp.external_classifications, tid, gstates)
        flags = []
        dims_in, dims_out = (info.width, info.height), (out_an.info.width, out_an.info.height)
        if dims_in != dims_out and op not in GEOMETRY_OPS:
            flags.append(DIMENSION_FLAG)
        elif dims_in != dims_out:
            flags.append(f"{DIMENSION_FLAG} (expected for {op})")
        if out.expect_lossless and not pm.pixel_exact:
            flags.append("LOSSLESS EXPECTATION NOT MET (see pixel metrics)")
        if not spec.pixel_operation and op not in ("format_chain", "external_comparison") and not pm.pixel_exact:
            flags.append("METADATA-ONLY CONTRACT VIOLATED")
        if op in LOSSY_OPS and not out.expect_lossless:
            flags.append("LOSSY ENCODING: pixel preservation not claimed")
        rec.status = "COMPLETE"
        rec.output_sha256 = out_an.hashes["sha256"]
        rec.output_dimensions = dims_out
        rec.output_format = out_an.info.format
        rec.pixel_metrics = pmd
        rec.metadata_differences = diffs
        rec.metadata_group_states = gstates
        rec.provenance_differences = prov
        rec.signal_before = (src.analysis.signal.state if src.analysis.signal else "UNKNOWN")
        rec.signal_after = out_an.signal.state if out_an.signal else "UNKNOWN"
        rec.actions = list(out.actions)
        rec.notes = list(out.notes)
        rec.output_analysis = out_dict
        rec.synthid_before = dict(src.synthid)
        rec.synthid_after = sid_after
        rec.flags = flags
        rec.duration_ms = (time.perf_counter() - t0) * 1000.0
        exp.transformations.append(rec)
        self.ws.save(exp)
        self.audit.log(A.TRANSFORMATION_COMPLETE, detail=(
            f"{tid} {spec.label}: {pm.verdict}; C2PA {prov['c2pa_before']}->{prov['c2pa_after']}; signal "
            f"{prov['signal_before']}->{prov['signal_after']}; SynthID {sid_after.get('state')}"))
        for f in flags:
            if f.startswith(DIMENSION_FLAG) and "expected" not in f or "VIOLATED" in f or "NOT MET" in f:
                self.audit.log(f, "WARNING", tid)
        prog(100, f"{tid}: complete")
        return rec

    def _finish_failed(self, exp, rec, status, error, event, severity, t0) -> TransformationRecord:
        rec.status, rec.error = status, error
        rec.duration_ms = (time.perf_counter() - t0) * 1000.0
        exp.transformations.append(rec)
        self.ws.save(exp)
        self.audit.log(event, severity, f"{rec.transformation_id} {rec.label}: {error}")
        return rec

    # -------------------------------------------------------------- execute
    def _execute(self, exp, src: SourceContext, op: str, params: dict, rec: TransformationRecord, prog) -> TransformOutput:
        meta = source_metadata(src.image, src.analysis.raw_blocks)
        if op == "metadata_sanitize":
            mode = str(params.get("mode", "METADATA-ONLY")).upper()
            profile = str(params.get("profile", "BALANCED")).upper()
            opts = SanitizeOptions.from_dict(params["options"]) if isinstance(params.get("options"), dict) \
                else PROFILES.get(profile, PROFILES["BALANCED"])
            rec.parameters = {"mode": mode, "profile": profile if not isinstance(params.get("options"), dict) else
                              params.get("profile", "CUSTOM"), "options": opts.to_dict()}
            if mode == "LOSSLESS RE-ENCODE":
                out = run_pixel_operation("png_reencode", src.image, {"keep_icc": True, "carry_metadata": False}, meta)
                out.actions.insert(0, "LOSSLESS RE-ENCODE sanitization: pixels decoded and re-encoded as PNG; only ICC kept")
                return out
            res = sanitize(src.data, src.fmt, opts)
            if res.provenance_removed:
                res.notes.append("Provenance-bearing metadata was removed: " + C2PA_WARNING)
            return TransformOutput(res.data, res.format, EXTENSIONS[res.format],
                                   res.actions + [f"removed: {r}" for r in res.removed], res.notes, expect_lossless=True)
        if op == "c2pa_separation":
            p = validate_params(op, params)
            rec.parameters = p
            res = separate_provenance(src.data, src.fmt, p["include_xmp_declarations"])
            return TransformOutput(res.data, res.format, EXTENSIONS[res.format],
                                   res.actions + [f"removed: {r}" for r in res.removed], res.notes, expect_lossless=True)
        if op == "external_comparison":
            path = Path(str(params.get("path", "")))
            p, data = read_file_bytes(path)
            img = open_image_bytes(data)
            from app.utils.validation import sniff_format

            fmt = sniff_format(data[:16]) or "PNG"
            rec.parameters = {"file_name": p.name, "file_size": len(data)}
            del img
            return TransformOutput(data, fmt, EXTENSIONS.get(fmt, ".bin"),
                                   [f"external file '{p.name}' imported unchanged for comparison"],
                                   ["Processed outside SynthProvenance; the processing conditions are not controlled."])
        if op == "format_chain":
            return self._format_chain(exp, src, validate_params(op, params), rec, meta, prog)
        p = validate_params(op, params)
        rec.parameters = p
        image = src.image
        if op == "format_conversion" and str(p.get("source", "ORIGINAL")).upper() != "ORIGINAL":
            sid = str(p["source"]).upper()
            prior = next((t for t in exp.transformations if t.transformation_id == sid and t.status == "COMPLETE"), None)
            if prior is None:
                raise TransformError(f"Source condition {sid} does not exist or did not complete.")
            image = open_image_bytes(self.ws.resolve(exp, prior.output_path).read_bytes())
            rec.source_condition = sid
        out = run_pixel_operation(op, image, p, meta)
        if rec.source_condition != "ORIGINAL":
            out.notes.append(f"Encoded from {rec.source_condition}; all metrics are measured against ORIGINAL.")
        return out

    def _format_chain(self, exp, src, p: dict, rec, meta, prog) -> TransformOutput:
        steps = parse_chain(p["steps"])
        rec.parameters = {**p, "parsed_steps": steps}
        prev_img, prev_dict = src.image, src.analysis_dict
        records, data, fmt = [], b"", "PNG"
        for i, step in enumerate(steps, 1):
            prog(5 + int(25 * i / len(steps)), f"{rec.transformation_id}: chain step {i}/{len(steps)} -> {step['format']}")
            work = prev_img.copy()
            work.info = {}
            fmt = step["format"]
            data, acts = encode_as(work, fmt, step["compression"], step["quality"],
                                   icc=meta["icc"] if p["keep_icc"] else None,
                                   exif=meta["exif"] if p["carry_metadata"] else None,
                                   xmp=meta["xmp"] if p["carry_metadata"] else None,
                                   transparency=meta["transparency"] if i == 1 else None)
            path_i = self.ws.output_path(exp, rec.transformation_id, f"step{i}_{fmt}", FORMAT_CAPS[fmt]["ext"])
            atomic_write_bytes(path_i, data)
            an = analyze_bytes(data, path_i, path_i.name)
            ad = an.to_dict()
            _d, gst = diff_groups(prev_dict["groups"], ad["groups"])
            records.append({
                "step": i, "input_format": (prev_dict.get("image") or {}).get("format"), "output_format": fmt,
                "compression": step["compression"], "quality": step["quality"] if step["compression"] == "LOSSY" else None,
                "input_sha256": (prev_dict.get("hashes") or {}).get("sha256"), "output_sha256": an.hashes["sha256"],
                "resolution": f"{an.info.width}x{an.info.height}", "file": f"output/{path_i.name}", "bytes": len(data),
                "vs_original": compact_metrics(compare_images(src.image, an.image)),
                "vs_previous": compact_metrics(compare_images(prev_img, an.image)),
                "metadata_changes": {k: v["state"] for k, v in gst.items() if v["state"] not in ("PRESERVED", "ABSENT")},
                "provenance": {"c2pa": (ad.get("c2pa") or {}).get("state"), "signal": (ad.get("signal") or {}).get("state")},
                "actions": acts,
            })
            prev_img, prev_dict = an.image, ad
        rec.steps = records
        lossless = all(s["compression"] == "LOSSLESS" for s in steps)
        chain = " > ".join(f"{s['format']}:{s['compression']}" for s in steps)
        return TransformOutput(data, fmt, FORMAT_CAPS[fmt]["ext"], [f"format chain {chain}; {len(steps)} step file(s) saved"],
                               [], expect_lossless=lossless)

    # ---------------------------------------------------------------- battery
    def run_battery(self, exp, src, sanitize_params: dict | None = None, progress: Progress | None = None) -> list:
        out = []
        for n, op in enumerate(MATRIX_BATTERY):
            def sub(pct, text, n=n):
                if progress:
                    progress(int((n + pct / 100.0) * 100 / len(MATRIX_BATTERY)), text)
            params = sanitize_params if op == "metadata_sanitize" else {}
            out.append(self.run(exp, src, op, params or {}, sub))
        return out


# -------------------------------------------------------------------- matrix
CHECK, CROSS = "\u2713", "\u2715"
MATRIX_COLUMNS = ["Metadata", "C2PA", "SynthID", "Pixels", "Resolution"]


def _layer_cell(rec: TransformationRecord, name: str) -> tuple[str, str]:
    lay = next((x for x in rec.layers if x.get("layer") == name), None)
    if lay is None:
        return "?", "no layer record"
    st, tip = lay["state"], f"{lay['state']}: {lay['observation']}"
    if name == "SynthID":
        return {"UNAVAILABLE": "UNAVAILABLE", "PERSISTED": CHECK}.get(st, "N/A" if st == "NOT DETECTED" and lay["before"] == "NOT DETECTED" else "?"), tip
    return {"PERSISTED": CHECK, "REMOVED": CROSS, "ALTERED": "ALTERED", "NOT DETECTED": "N/A"}.get(st, "?"), tip


def experiment_matrix(exp: Experiment) -> list[dict]:
    base = exp.baseline or {}
    groups = base.get("groups") or {}
    img = base.get("image") or {}
    has_meta = any(g.get("state") != "ABSENT" for n, g in groups.items() if n in ("EXIF", "XMP", "IPTC", "ICC"))
    c2 = base.get("c2pa") or {}
    sid = (exp.synthid_baseline or {}).get("state", "UNAVAILABLE")
    rows = [{"row": "ORIGINAL", "tid": "BASELINE", "cells": {
        "Metadata": (CHECK if has_meta else "N/A", "baseline metadata " + ("present" if has_meta else "absent")),
        "C2PA": (CHECK if c2.get("present") else "N/A", c2.get("summary", "")),
        "SynthID": ({"UNAVAILABLE": "UNAVAILABLE", "DETECTED": CHECK, "NOT DETECTED": "N/A"}.get(sid, "?"), f"baseline {sid}"),
        "Pixels": (CHECK, "baseline pixel array"),
        "Resolution": (CHECK, f"{img.get('width')}x{img.get('height')}")}}]
    latest: dict[str, TransformationRecord] = {}
    for t in exp.transformations:
        if t.status == "COMPLETE":
            latest[OPERATIONS[t.operation].matrix_row if t.operation in OPERATIONS else t.operation] = t
    for row in MATRIX_ROWS[1:] + [r for r in EXTRA_ROWS if r in latest]:
        t = latest.get(row)
        if t is None:
            rows.append({"row": row, "tid": "", "cells": {c: ("\u2014", "not run") for c in MATRIX_COLUMNS}})
            continue
        pm = t.pixel_metrics or {}
        pix = (CHECK if pm.get("verdict") == "PIXEL-EXACT" else "ALTERED" if pm.get("verdict") == "TRANSFORMATION DETECTED"
               else "?", f"{pm.get('verdict')}; changed {pm.get('changed_pixel_pct')}%")
        same = tuple(t.input_dimensions or ()) == tuple(t.output_dimensions or ())
        res = (CHECK if same else CROSS, f"{t.input_dimensions} -> {t.output_dimensions}" + ("" if same else f" ({DIMENSION_FLAG})"))
        rows.append({"row": row, "tid": t.transformation_id, "cells": {
            "Metadata": _layer_cell(t, "Ordinary metadata"), "C2PA": _layer_cell(t, "C2PA"),
            "SynthID": _layer_cell(t, "SynthID"), "Pixels": pix, "Resolution": res}})
    return rows


def params_text(p: dict) -> str:
    return json.dumps({k: v for k, v in (p or {}).items() if k != "parsed_steps"}, ensure_ascii=False, sort_keys=True)[:400]
