"""EXPORT FOR PAPER: SynthID Research Lab runs as CSV / JSON / PDF / PNG / ZIP.

ZIP layout (``experiment/`` root)::

    run.json  source/  output/  metrics/  config/  logs/  report/
    hashes_sha256.txt  hashes_blake3.txt     (sha256sum / b3sum format, relative to experiment/)

Statements are cautious: no report says an image is or is not AI-generated, and
a NOT DETECTED result is never described as removal.
"""
from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from pathlib import Path

from app import __version__
from app.core.hashing import BLAKE3_AVAILABLE, blake3_bytes
from app.core.synthid_research_engine import MATRIX_COLUMNS, ResearchRun, ResearchStore
from app.services.report_service import _f, _pdf_text
from app.utils.paths import safe_arcname
from app.utils.serialization import dumps

STATEMENT = ("This record does not establish whether any image is AI-generated or human-created. SynthID states are "
             "reported exactly as measured by the named engine or as recorded by the researcher; a NOT DETECTED result "
             "never verifies removal.")


def _cell(v) -> str:
    return _f(v, 4) if isinstance(v, (int, float)) and not isinstance(v, bool) else ("-" if v in (None, "") else str(v))


def write_csv(run: ResearchRun, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["run_id", *MATRIX_COLUMNS])
        for r in run.matrix:
            w.writerow([run.run_id, *[_cell(r.get(c)) for c in MATRIX_COLUMNS]])
    return path


def write_metrics_csv(run: ResearchRun, path: Path) -> Path | None:
    m = (run.benchmark or {}).get("metrics") or {}
    if not m:
        return None
    path = Path(path)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["run_id", "metric", "value"])
        for k, v in m.items():
            w.writerow([run.run_id, k, v if not isinstance(v, (list, tuple)) else ";".join(_cell(x) for x in v)])
        w.writerow([])
        w.writerow(["run_id", "fpr", "tpr", "threshold"])
        for fpr, tpr, thr in (run.benchmark or {}).get("roc") or []:
            w.writerow([run.run_id, fpr, tpr, thr])
    return path


def summary_rows(run: ResearchRun) -> list[list[str]]:
    env = run.environment or {}
    rows = [["Run", run.run_id], ["Kind", run.kind], ["Created (UTC)", run.created], ["Status", run.status],
            ["Method", f"{run.method_id} {run.method_name}"], ["Pipeline", " > ".join(run.pipeline)],
            ["Parameters", dumps(run.parameters, indent=None)[:600]], ["Seed", str(run.seed)], ["Device", run.device],
            ["Source / version / license", f"{run.source_repository} / {run.source_version} / {run.license}"],
            ["Model version / hash", f"{run.model_version or '-'} / {run.model_hash}"],
            ["Software", env.get("software", "")], ["OS", env.get("os", "")], ["Python", env.get("python", "")],
            ["GPU / CUDA", f"{env.get('gpu', '')} / {env.get('cuda_version', '')}"],
            ["Runtime", f"{run.runtime_s:.3f} s"], ["Original unchanged", str(run.original_unchanged)],
            ["Detail", run.detail]]
    m = (run.benchmark or {}).get("metrics") or {}
    if m:
        ci = m.get("auc_ci95")
        rows += [["AUC (95% CI)", f"{_cell(m.get('auc'))} ({_cell(ci[0])}-{_cell(ci[1])})" if ci else _cell(m.get("auc"))],
                 ["TPR / FPR @ threshold", f"{_cell(m.get('tpr'))} / {_cell(m.get('fpr'))} @ {_cell(m.get('threshold'))}"],
                 ["Precision / Recall / F1", f"{_cell(m.get('precision'))} / {_cell(m.get('recall'))} / {_cell(m.get('f1'))}"],
                 ["Scored / abstained", f"{run.benchmark.get('n_scored')} / {run.benchmark.get('n_abstained')}"]]
    return rows


def write_pdf(run: ResearchRun, path: Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=8.5, leading=11)
    cell = ParagraphStyle("c", parent=body, fontSize=6.5, leading=8, splitLongWords=1)
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=17, leading=21, alignment=0)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11, textColor=colors.HexColor("#1F7F95"), spaceBefore=8)
    page = landscape(A4)
    width = page[0] - 24 * mm
    grid = TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B8C4CE")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                       ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6EEF3"))])
    story = [Paragraph("SynthProvenance - SynthID Research Lab - Insyide Innovations x NuRichter Workspace", body),
             Paragraph(_pdf_text(f"SynthID Research Record {run.run_id}"), h1), Paragraph(_pdf_text(STATEMENT), body),
             Paragraph("Run", h2)]
    kv = Table([[Paragraph(_pdf_text(k), cell), Paragraph(_pdf_text(v), cell)] for k, v in summary_rows(run)],
               colWidths=[width * 0.22, width * 0.78])
    kv.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B8C4CE")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [kv, Paragraph("SynthID Research Matrix", h2)]
    if run.matrix:
        data = [[Paragraph(c, cell) for c in MATRIX_COLUMNS]]
        data += [[Paragraph(_pdf_text(_cell(r.get(c))), cell) for c in MATRIX_COLUMNS] for r in run.matrix[:400]]
        t = Table(data, colWidths=[width / len(MATRIX_COLUMNS)] * len(MATRIX_COLUMNS), repeatRows=1)
        t.setStyle(grid)
        story.append(t)
    else:
        story.append(Paragraph("No entries.", body))
    groups = (run.benchmark or {}).get("groups") or []
    if groups:
        story.append(Paragraph("Per-group rates", h2))
        cols = ["group", "kind", "n", "tpr", "fpr"]
        t = Table([[Paragraph(c, cell) for c in cols]] + [[Paragraph(_pdf_text(_cell(g.get(c))), cell) for c in cols]
                                                          for g in groups], colWidths=[width / 5] * 5, repeatRows=1)
        t.setStyle(grid)
        story.append(t)
    story.append(Paragraph("Limitations", h2))
    story += [Paragraph("- " + _pdf_text(x), body) for x in run.limitations]
    story.append(Spacer(1, 4))
    doc = SimpleDocTemplate(str(path), pagesize=page, leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm,
                            bottomMargin=12 * mm, title=f"SynthID Research Record {run.run_id}", author="SynthProvenance")
    doc.build(story)
    return path


def write_png(run: ResearchRun, path: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    def font(size):
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            return ImageFont.load_default()

    roc = (run.benchmark or {}).get("roc") or []
    W, H = 1600, 900
    im = Image.new("RGB", (W, H), "#0E1318")
    d = ImageDraw.Draw(im)
    cyan, text, muted, line = "#4CC3D9", "#D5DEE7", "#7D8C9B", "#243140"
    d.text((40, 28), "INSiYDE INNOVATIONS  |  NuRichter Workspace  |  SynthID Research Lab", fill=muted, font=font(16))
    d.text((40, 56), f"SynthID Research Record {run.run_id}", fill=text, font=font(32))
    d.line((40, 104, W - 40, 104), fill=cyan, width=2)
    for i, (k, v) in enumerate(summary_rows(run)[:18]):
        d.text((40, 124 + i * 32), f"{k}:", fill=muted, font=font(16))
        d.text((300, 124 + i * 32), str(v)[:68], fill=text, font=font(16))
    x0, y0, size = 1040, 150, 480
    d.rectangle((x0, y0, x0 + size, y0 + size), outline=line)
    d.text((x0, y0 - 30), "ROC (FPR vs TPR)" if roc else "ROC: no benchmark in this run", fill=muted, font=font(16))
    d.line((x0, y0 + size, x0 + size, y0), fill=line)
    if roc:
        pts = [(x0 + fpr * size, y0 + size - tpr * size) for fpr, tpr, _t in roc] + [(x0 + size, y0)]
        d.line(pts, fill=cyan, width=3)
    d.text((40, H - 60), "Experimental observation only. Not an AI/human verdict. WE DO NOT GUESS. WE MEASURE.",
           fill=muted, font=font(15))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    path.write_bytes(buf.getvalue())
    return path


def write_reports(store: ResearchStore, run: ResearchRun) -> dict[str, Path]:
    d = store.run_dir(run.run_id) / "output" / "paper"
    stem = f"{run.run_id}_paper"
    from app.utils.serialization import write_json

    out = {"csv": write_csv(run, d / f"{stem}_matrix.csv"), "json": write_json(d / f"{stem}.json", run.to_dict()),
           "pdf": write_pdf(run, d / f"{stem}.pdf"), "png": write_png(run, d / f"{stem}.png")}
    m = write_metrics_csv(run, d / f"{stem}_metrics.csv")
    if m:
        out["metrics_csv"] = m
    return out


def export_paper_zip(store: ResearchStore, run: ResearchRun, dest: Path) -> Path:
    reports = write_reports(store, run)
    store.save(run)
    store.log(run, "PAPER EXPORT " + ", ".join(sorted(reports)))
    root = store.run_dir(run.run_id)
    members: list[tuple[str, bytes]] = []
    for f in sorted(root.rglob("*")):
        if f.is_file() and not f.name.endswith((".tmp", ".partial")):
            rel = f.relative_to(root).as_posix()
            if rel.startswith("output/paper/"):
                rel = "report/" + rel[len("output/paper/"):]
            members.append((safe_arcname("experiment", rel), f.read_bytes()))
    sha = [f"{hashlib.sha256(data).hexdigest()}  {name.split('/', 1)[1]}" for name, data in members]
    b3 = [f"{blake3_bytes(data)}  {name.split('/', 1)[1]}" for name, data in members] if BLAKE3_AVAILABLE else []
    members.append(("experiment/hashes_sha256.txt", ("# SHA-256, sha256sum format, relative to experiment/\n"
                                                     + "\n".join(sha) + "\n").encode("utf-8")))
    members.append(("experiment/hashes_blake3.txt", (("# BLAKE3, b3sum format, relative to experiment/\n" + "\n".join(b3))
                                                     if b3 else "# BLAKE3 UNAVAILABLE (blake3 module not installed)")
                                                    .encode("utf-8") + b"\n"))
    members.append(("experiment/README.txt", (f"SynthProvenance {__version__} SynthID Research Lab export {run.run_id}\n"
                                              f"{STATEMENT}\n").encode("utf-8")))
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".partial")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for name, data in members:
            zf.writestr(name, data)
    tmp.replace(dest)
    return dest
