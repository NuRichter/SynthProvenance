"""EXPORT FOR PAPER: a Fingerprint Research Lab run as CSV / JSON / PDF / PNG / ZIP.

ZIP layout (``experiment/`` root)::

    run.json  inputs/  maps/  config/  logs/  report/
    hashes_sha256.txt  hashes_blake3.txt

Statements are cautious: descriptive forensic measurements, controlled-surrogate results
with ground truth, or explicit hypothesis tests - never an AI/human verdict.
"""
from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from pathlib import Path

from app import __version__
from app.core.fingerprint_lab import FingerprintLab, FingerprintRun
from app.core.hashing import BLAKE3_AVAILABLE, blake3_bytes
from app.services.report_service import _f, _pdf_text
from app.utils.paths import safe_arcname
from app.utils.serialization import dumps, write_json

STATEMENT = ("SynthProvenance measures. This record reports descriptive forensic statistics, controlled-surrogate "
             "results scored against known ground truth, or explicit hypothesis tests. It never states that an image is "
             "AI-generated or human-made, and a controlled result is never presented as proof about real generators or "
             "real watermarks.")


def _cell(v) -> str:
    if isinstance(v, bool):
        return "yes" if v else "no"
    return _f(v, 4) if isinstance(v, (int, float)) else ("-" if v in (None, "") else str(v))


def _flatten(d: dict, prefix: str = "") -> list[tuple[str, str]]:
    out = []
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out += _flatten(v, key + ".")
        elif isinstance(v, (list, tuple)):
            out.append((key, dumps(v, indent=None)[:300]))
        else:
            out.append((key, _cell(v)))
    return out


def summary_rows(run: FingerprintRun) -> list[list[str]]:
    env = run.environment or {}
    r = run.result or {}
    rows = [["Run", run.run_id], ["Created (UTC)", run.created], ["Method", f"{run.method_id} {run.method_name}"],
            ["Category", run.category], ["Maturity", run.maturity], ["Status", run.status],
            ["Parameters", dumps(run.parameters, indent=None)[:400]],
            ["Surrogate", dumps(run.surrogate, indent=None)[:400] if run.surrogate else "-"],
            ["Software", env.get("software", f"SynthProvenance {__version__}")], ["OS", env.get("os", "")],
            ["Python", env.get("python", "")], ["GPU / CUDA", f"{env.get('gpu', '')} / {env.get('cuda_version', '')}"],
            ["Runtime", f"{run.runtime_s:.3f} s"], ["Original unchanged", str(run.original_unchanged)],
            ["Detail", run.detail]]
    for k, v in (r.get("readouts") or {}).items():
        rows.append([f"readout: {k}", _cell(v)])
    return rows


def write_csv(run: FingerprintRun, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["run_id", "key", "value"])
        for k, v in summary_rows(run):
            w.writerow([run.run_id, k, v])
        for section in ("readouts", "metrics", "reconstruction", "ground_truth", "candidate_stats", "solver"):
            block = (run.result or {}).get(section) or {}
            for k, v in _flatten(block):
                w.writerow([run.run_id, f"{section}.{k}", v])
    return path


def write_pdf(run: FingerprintRun, path: Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=8.5, leading=11)
    cell = ParagraphStyle("c", parent=body, fontSize=7, leading=9, splitLongWords=1)
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=16, leading=20, alignment=0)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11, textColor=colors.HexColor("#1F7F95"), spaceBefore=8)
    width = A4[0] - 24 * mm
    grid = TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B8C4CE")), ("VALIGN", (0, 0), (-1, -1), "TOP")])
    story = [Paragraph("SynthProvenance - Fingerprint Research Lab - Insyide Innovations x NuRichter Workspace", body),
             Paragraph(_pdf_text(f"Fingerprint Research Record {run.run_id}"), h1), Paragraph(_pdf_text(STATEMENT), body),
             Paragraph("Run", h2)]
    kv = Table([[Paragraph(_pdf_text(k), cell), Paragraph(_pdf_text(v), cell)] for k, v in summary_rows(run)],
               colWidths=[width * 0.28, width * 0.72])
    kv.setStyle(grid)
    story.append(kv)
    for section in ("metrics", "reconstruction", "ground_truth", "solver"):
        block = (run.result or {}).get(section) or {}
        flat = _flatten(block)
        if flat:
            story.append(Paragraph(section.replace("_", " ").title(), h2))
            t = Table([[Paragraph(_pdf_text(k), cell), Paragraph(_pdf_text(v), cell)] for k, v in flat],
                      colWidths=[width * 0.4, width * 0.6])
            t.setStyle(grid)
            story.append(t)
    if run.failure_analysis:
        story.append(Paragraph("Failure analysis", h2))
        cols = ["failure_mode", "symptom", "likely_cause", "affected_metric", "possible_improvement"]
        data = [[Paragraph(c.replace("_", " "), cell) for c in cols]]
        data += [[Paragraph(_pdf_text(str(f.get(c, ""))), cell) for c in cols] for f in run.failure_analysis]
        t = Table(data, colWidths=[width / 5] * 5, repeatRows=1)
        t.setStyle(grid)
        story.append(t)
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm,
                            bottomMargin=12 * mm, title=f"Fingerprint Research Record {run.run_id}", author="SynthProvenance")
    doc.build(story)
    return path


def write_png(run: FingerprintRun, lab: FingerprintLab, path: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    def font(size):
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()

    W, H = 1600, 900
    im = Image.new("RGB", (W, H), "#0E1318")
    d = ImageDraw.Draw(im)
    cyan, text, muted, line = "#4CC3D9", "#D5DEE7", "#7D8C9B", "#243140"
    d.text((40, 28), "INSiYDE INNOVATIONS  |  NuRichter Workspace  |  Fingerprint Research Lab", fill=muted, font=font(16))
    d.text((40, 56), f"{run.method_id}: {run.method_name}", fill=text, font=font(30))
    d.text((40, 96), f"{run.run_id}   {run.maturity}   {run.status}", fill=cyan, font=font(18))
    d.line((40, 126, W - 40, 126), fill=cyan, width=2)
    for i, (k, v) in enumerate(summary_rows(run)[:16]):
        d.text((40, 146 + i * 30), f"{k}:", fill=muted, font=font(15))
        d.text((320, 146 + i * 30), str(v)[:60], fill=text, font=font(15))
    # first map thumbnail
    maps = run.maps or []
    if maps:
        try:
            mp = Image.open(lab.run_dir(run.run_id) / maps[0]["file"]).convert("RGB")
            mp.thumbnail((520, 520))
            im.paste(mp, (1040, 150))
            d.text((1040, 120), maps[0]["name"], fill=muted, font=font(15))
        except Exception:  # noqa: BLE001
            pass
    d.text((40, H - 54), "Descriptive / controlled-surrogate measurement. WE DO NOT GUESS. WE MEASURE.", fill=muted,
           font=font(15))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    path.write_bytes(buf.getvalue())
    return path


def export_fingerprint_zip(lab: FingerprintLab, run: FingerprintRun, dest: Path) -> Path:
    d = lab.run_dir(run.run_id) / "report"
    d.mkdir(parents=True, exist_ok=True)
    stem = f"{run.run_id}_paper"
    write_csv(run, d / f"{stem}.csv")
    write_json(d / f"{stem}.json", run.to_dict())
    write_pdf(run, d / f"{stem}.pdf")
    write_png(run, lab, d / f"{stem}.png")
    lab.log(run, "PAPER EXPORT csv, json, pdf, png")
    root = lab.run_dir(run.run_id)
    members: list[tuple[str, bytes]] = []
    for f in sorted(root.rglob("*")):
        if f.is_file() and not f.name.endswith((".tmp", ".partial")):
            rel = f.relative_to(root).as_posix()
            members.append((safe_arcname("experiment", rel), f.read_bytes()))
    sha = [f"{hashlib.sha256(data).hexdigest()}  {name.split('/', 1)[1]}" for name, data in members]
    b3 = [f"{blake3_bytes(data)}  {name.split('/', 1)[1]}" for name, data in members] if BLAKE3_AVAILABLE else []
    members.append(("experiment/hashes_sha256.txt",
                    ("# SHA-256, sha256sum format, relative to experiment/\n" + "\n".join(sha) + "\n").encode("utf-8")))
    members.append(("experiment/hashes_blake3.txt",
                    (("# BLAKE3, b3sum format\n" + "\n".join(b3)) if b3 else "# BLAKE3 UNAVAILABLE").encode("utf-8") + b"\n"))
    members.append(("experiment/README.txt",
                    (f"SynthProvenance {__version__} Fingerprint Research Lab export {run.run_id}\n{STATEMENT}\n").encode("utf-8")))
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".partial")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for name, data in members:
            zf.writestr(name, data)
    tmp.replace(dest)
    return dest
