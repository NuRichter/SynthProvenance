"""Research report assembly and rendering (JSON / CSV / HTML / PDF / PNG).

The report is built once as a list of typed sections (kv, table, text, list)
and rendered by format-specific writers, so every format carries the same
content. Conclusions are deliberately cautious: the report never states that
an image is or is not AI-generated and never predicts platform behaviour.
"""
from __future__ import annotations

import csv
import html
import io
import json
from pathlib import Path
from string import Template

from app import __app_name__, __classification__, __environment__, __motto__, __org__, __subtitle__, __version__
from app.core.provenance_engine import PIXEL_WATERMARK_NOTE
from app.models.experiment import Experiment, utc_now
from app.models.synthid import DEFAULT_LIMITATION
from app.utils.paths import resource_path
from app.utils.serialization import write_json

GLOBAL_STATEMENT = ("This report does not establish whether the image is AI-generated or human-created, and it makes no "
                    "prediction about how any external platform will classify the image or its experimental outputs.")
LIMITATIONS = [
    "C2PA signatures and certificate trust are not cryptographically validated by the native parser; they are reported "
    "as NOT VALIDATED / UNKNOWN unless a local engine (c2patool or c2pa-python) was available.",
    "SynthID is an embedded pixel-domain signal. It is measured only when a compatible local verification engine is "
    "configured; otherwise its state is UNAVAILABLE and nothing is inferred. " + DEFAULT_LIMITATION,
    PIXEL_WATERMARK_NOTE,
    "Absence of observable C2PA or of any metadata declaration does not establish that an image is not AI-generated.",
    "Pixel comparison uses the canonical decode of frame 0 without applying EXIF orientation.",
    "Forensic statistics (entropy, FFT, noise, blockiness) are descriptive only and are not origin verdicts.",
    "External platform classifications are user-recorded and unverified; SynthProvenance does not contact platforms.",
    "Results are specific to the tested conditions, codec builds and library versions listed under reproducibility.",
]
PDF_SAFE = {"\u2713": "YES", "\u2715": "NO", "\u2192": "->", "\u2014": "-", "\u2013": "-", "\u2026": "...",
            "\u00b7": "-", "\u2265": ">=", "\u2264": "<=", "\u2019": "'", "\u201c": '"', "\u201d": '"'}


def _f(v, nd: int = 4) -> str:
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def _psnr(pm: dict) -> str:
    if pm.get("psnr_infinite"):
        return "inf (identical)"
    return _f(pm.get("psnr_db"), 2)


def conclusion_for(t) -> str:
    pm, prov = t.pixel_metrics or {}, t.provenance_differences or {}
    first = prov.get("statement", "").split(" No observable")[0] or "Observable provenance state not evaluated."
    if pm.get("verdict") == "PIXEL-EXACT":
        second = "Pixel-level analysis indicates no measurable change in the underlying image array."
    elif pm.get("comparable"):
        second = (f"Pixel-level analysis measured changes in {_f(pm.get('changed_pixel_pct'))}% of pixels "
                  f"(MAE {_f(pm.get('mae'))}, PSNR {_psnr(pm)} dB).")
    else:
        second = "Pixel arrays are not directly comparable because the resolution changed."
    sid = next((x for x in t.layers if x.get("layer") == "SynthID"), {})
    third = ("The SynthID embedded-signal layer was not measured (no compatible local verification engine)."
             if sid.get("state") == "UNAVAILABLE" else f"SynthID layer: {sid.get('state')} ({sid.get('observation')})")
    return f"{t.transformation_id} ({t.label}): {first} {second} {third}"


def build_report(exp: Experiment, audit_events: list | None = None, engine_status: dict | None = None) -> dict:
    from app.services.synthid_experiment import synthid_summary
    from app.services.transformation_service import experiment_matrix, params_text

    base = exp.baseline or {}
    img, hashes, c2 = base.get("image") or {}, base.get("hashes") or {}, base.get("c2pa") or {}
    sig, groups = base.get("signal") or {}, base.get("groups") or {}
    done = [t for t in exp.transformations if t.status == "COMPLETE"]
    sections: list[dict] = []

    def sec(title, **kw):
        sections.append({"title": title, **kw})

    sec("1. Experiment Identification", kv=[
        ["Experiment ID", exp.experiment_id], ["Created (UTC)", exp.created], ["Report generated (UTC)", utc_now()],
        ["Application", f"{__app_name__} {__version__}"], ["Research environment", __environment__],
        ["Classification", __classification__], ["Status", exp.status],
        ["Transformations", f"{len(exp.transformations)} recorded, {len(done)} complete"]])
    sec("2. Research Objective", text=[exp.objective] + ([exp.notes] if exp.notes else []))
    sec("3. Input Image", kv=[
        ["File name", img.get("filename")], ["Format / MIME", f"{img.get('format')} / {img.get('mime')}"],
        ["File size", f"{_f(img.get('file_size'))} bytes"], ["Resolution", f"{img.get('width')} x {img.get('height')}"],
        ["Pixel count", _f(img.get("pixel_count"))], ["Aspect ratio", img.get("aspect_ratio")],
        ["Mode / channels / bit depth", f"{img.get('mode')} / {img.get('channels')} / {img.get('bit_depth')}"],
        ["Color space", img.get("color_space")], ["ICC profile", img.get("icc_profile")],
        ["Compression", img.get("compression")], ["Frames", img.get("frames")], ["EXIF orientation", img.get("orientation")],
        ["Warnings", "; ".join(img.get("warnings") or []) or "none"]])
    sec("4. Baseline State", kv=[[f"Metadata: {n}", g.get("state")] for n, g in groups.items()] + [
        ["C2PA", c2.get("summary", "")], ["C2PA hard binding", f"{c2.get('hard_binding')} {c2.get('hard_binding_detail', '')}"],
        ["AI-content provenance signal", f"{sig.get('state')}: {sig.get('statement')}"],
        ["SynthID (embedded signal layer)", f"{(exp.synthid_baseline or {}).get('state', 'UNAVAILABLE')}: "
                                            f"{(exp.synthid_baseline or {}).get('detail', '')}"]])
    sec("5. Metadata Findings", table={"columns": ["Group", "State", "Fields", "Location", "Notes"], "rows": [
        [n, g.get("state"), len(g.get("fields") or []), g.get("location", ""), "; ".join((g.get("notes") or [])[:2])]
        for n, g in groups.items()]})
    man_rows = [[m.get("label"), m.get("claim_generator"), m.get("signature_algorithm"), m.get("issuer") or "-",
                 len(m.get("actions") or []), len(m.get("ingredients") or [])] for m in c2.get("manifests") or []]
    act_rows = [[a.get("manifest", "")[-24:], a.get("action"), a.get("digital_source_type") or "-", a.get("software_agent") or "-",
                 a.get("when") or "-"] for m in c2.get("manifests") or [] for a in m.get("actions") or []]
    sec("6. C2PA Findings", kv=[
        ["Layer", "PROVENANCE / CONTENT CREDENTIAL LAYER"], ["Presence", c2.get("state")], ["Summary", c2.get("summary")],
        ["Location", c2.get("location") or "-"], ["Store size / SHA-256", f"{_f(c2.get('store_bytes'))} bytes / {c2.get('store_sha256') or '-'}"],
        ["Active manifest", c2.get("active_manifest") or "-"], ["Hard binding", c2.get("hard_binding")],
        ["Signature validity", f"{c2.get('validity')} ({c2.get('validity_detail', '')})"], ["Trust", c2.get("trust")],
        ["Engine", c2.get("engine")]],
        table={"columns": ["Manifest", "Claim generator", "Signature alg.", "Issuer", "Actions", "Ingredients"], "rows": man_rows},
        table2={"columns": ["Manifest", "Action", "digitalSourceType", "softwareAgent", "When"], "rows": act_rows})
    ss = synthid_summary(exp, engine_status)
    sb = exp.synthid_baseline or {}
    sec("7. SynthID Findings", kv=[
        ["Layer", "SynthID / EMBEDDED SIGNAL LAYER (not metadata)"],
        ["Engine", "available" if (ss["engine"] or {}).get("available") else f"UNAVAILABLE: {(ss['engine'] or {}).get('detail', '')}"],
        ["Baseline state", sb.get("state", "UNAVAILABLE")], ["Method", sb.get("method", "-")], ["Detail", sb.get("detail", "-")]],
        list=list(sb.get("context") or []) + [ss["policy"]],
        table={"columns": ["Condition", "Label", "Before", "After", "State", "Experiment type"], "rows": [
            [r["transformation_id"], r["label"], r["before"], r["after"], r["state"], r["experiment_type"]] for r in ss["conditions"]]})
    sec("8. Transformation Conditions", table={"columns": ["ID", "Operation", "Parameters", "Source", "Timestamp", "Status"], "rows": [
        [t.transformation_id, t.label, params_text(t.parameters), t.source_condition, t.timestamp,
         t.status + (f": {t.error}" if t.error else "")] for t in exp.transformations]})
    sec("9. Experimental Output", table={"columns": ["ID", "Format", "Resolution", "Output SHA-256", "File"], "rows": [
        [t.transformation_id, t.output_format, f"{t.output_dimensions[0]}x{t.output_dimensions[1]}" if t.output_dimensions else "-",
         t.output_sha256, t.output_path] for t in done]})
    sec("10. Pixel Integrity Results", table={"columns": ["ID", "Verdict", "Changed pixels", "Changed %", "Max error", "Flags"], "rows": [
        [t.transformation_id, (t.pixel_metrics or {}).get("verdict"), _f((t.pixel_metrics or {}).get("changed_pixels")),
         _f((t.pixel_metrics or {}).get("changed_pixel_pct")), _f((t.pixel_metrics or {}).get("max_abs_error")),
         "; ".join(t.flags) or "-"] for t in done]})
    sec("11. Image Quality Metrics", table={"columns": ["ID", "MAE", "MSE", "PSNR dB", "SSIM", "Histogram diff", "dHash dist."], "rows": [
        [t.transformation_id, _f(pm.get("mae")), _f(pm.get("mse")), _psnr(pm), _f(pm.get("ssim"), 6),
         _f(pm.get("histogram_difference"), 6), _f(pm.get("perceptual_hash_distance"))] for t in done for pm in [t.pixel_metrics or {}]]})
    fmt_rows = []
    for t in done:
        if t.steps:
            for s in t.steps:
                vo = s.get("vs_original") or {}
                fmt_rows.append([f"{t.transformation_id}.{s['step']}", s.get("input_format"), s.get("output_format"),
                                 s.get("compression"), _f(s.get("quality")), (s.get("output_sha256") or "")[:16],
                                 s.get("resolution"), vo.get("verdict"), _psnr(vo)])
        elif t.operation in ("format_conversion", "png_reencode", "jpeg_reencode", "webp_reencode", "lossless_export",
                             "controlled_recompression"):
            pm = t.pixel_metrics or {}
            fmt_rows.append([t.transformation_id, img.get("format"), t.output_format,
                             (t.parameters or {}).get("compression", "LOSSY" if "LOSSY ENCODING" in " ".join(t.flags) else "LOSSLESS"),
                             _f((t.parameters or {}).get("quality")), (t.output_sha256 or "")[:16],
                             f"{t.output_dimensions[0]}x{t.output_dimensions[1]}", pm.get("verdict"), _psnr(pm)])
    sec("12. Format Conversion Results", table={"columns": ["ID/step", "In", "Out", "Mode", "Quality", "Out SHA-256 (prefix)",
                                                            "Resolution", "Pixels vs ORIGINAL", "PSNR dB"], "rows": fmt_rows})
    layer_names = ["C2PA", "SynthID", "Ordinary metadata", "Image pixels", "File encoding", "File structure"]
    matrix = experiment_matrix(exp)
    sec("13. Observable Signal Changes",
        table={"columns": ["ID"] + layer_names, "rows": [
            [t.transformation_id] + [next((x["state"] for x in t.layers if x["layer"] == n), "-") for n in layer_names] for t in done]},
        table2={"columns": ["Condition", "Metadata", "C2PA", "SynthID", "Pixels", "Resolution"], "rows": [
            [r["row"] + (f" ({r['tid']})" if r["tid"] and r["tid"] != "BASELINE" else "")] +
            [r["cells"][c][0] for c in ("Metadata", "C2PA", "SynthID", "Pixels", "Resolution")] for r in matrix]},
        text=[conclusion_for(t) for t in done] + [GLOBAL_STATEMENT])
    sec("14. Limitations", list=LIMITATIONS)
    env = exp.environment or {}
    sec("15. Reproducibility Information", kv=[
        ["Application version", exp.app_version], ["Python", env.get("python")], ["Operating system", env.get("os")],
        ["Machine", env.get("machine")], ["Qt", env.get("qt")],
        ["Packages", ", ".join(f"{k} {v}" for k, v in (env.get("packages") or {}).items())],
        ["Canonical decode", "frame 0; EXIF orientation not applied; palette expanded; native bit depth kept"],
        ["SSIM", "7x7 uniform window, per-channel mean, sample covariance, C1=(0.01L)^2, C2=(0.03L)^2"],
        ["PSNR", "10*log10(L^2/MSE), L = data range of the source dtype"],
        ["Parameters", "Every transformation's full parameter set is stored in experiment.json"]])
    rows = [["ORIGINAL", hashes.get("sha256"), hashes.get("blake3") or hashes.get("blake3_state"), hashes.get("pixel_sha256")]]
    for t in done:
        oh = (t.output_analysis or {}).get("hashes") or {}
        rows.append([t.transformation_id, oh.get("sha256"), oh.get("blake3") or oh.get("blake3_state"), oh.get("pixel_sha256")])
    sec("16. Cryptographic Hashes", table={"columns": ["Item", "SHA-256 (file)", "BLAKE3 (file)", "SHA-256 (pixels)"], "rows": rows})
    sec("17. Audit Log", table={"columns": ["Timestamp (UTC)", "Severity", "Event", "Detail"], "rows": [
        [e.timestamp, e.severity, e.event, e.detail[:300]] for e in (audit_events or [])]})
    return {"title": f"{__app_name__} Research Report", "subtitle": f"{__subtitle__} | {exp.experiment_id}",
            "organisation": __org__, "motto": __motto__, "experiment_id": exp.experiment_id, "generated": utc_now(),
            "sections": sections}


# ------------------------------------------------------------------ writers

def write_json_report(report: dict, path: Path) -> Path:
    return write_json(path, report)


CSV_COLUMNS = ["transformation_id", "operation", "label", "status", "source", "output_format", "output_width",
               "output_height", "output_sha256", "verdict", "changed_pixels", "changed_pixel_pct", "mae", "mse",
               "max_abs_error", "psnr_db", "ssim", "histogram_difference", "dhash_distance", "c2pa_before", "c2pa_after",
               "signal_before", "signal_after", "synthid_before", "synthid_after", "flags", "parameters"]


def write_csv(exp: Experiment, path: Path) -> Path:
    from app.services.transformation_service import params_text

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_COLUMNS)
        for t in exp.transformations:
            pm, pv = t.pixel_metrics or {}, t.provenance_differences or {}
            dims = t.output_dimensions or (None, None)
            w.writerow([t.transformation_id, t.operation, t.label, t.status, t.source_condition, t.output_format, dims[0], dims[1],
                        t.output_sha256, pm.get("verdict"), pm.get("changed_pixels"), pm.get("changed_pixel_pct"), pm.get("mae"),
                        pm.get("mse"), pm.get("max_abs_error"), "inf" if pm.get("psnr_infinite") else pm.get("psnr_db"),
                        pm.get("ssim"), pm.get("histogram_difference"), pm.get("perceptual_hash_distance"),
                        pv.get("c2pa_before"), pv.get("c2pa_after"), t.signal_before, t.signal_after,
                        (t.synthid_before or {}).get("state"), (t.synthid_after or {}).get("state"), "; ".join(t.flags),
                        params_text(t.parameters)])
    return path


def _html_table(columns, rows) -> str:
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in columns)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(_f(v))}</td>" for v in r) + "</tr>" for r in rows)
    return f"<table><tr>{head}</tr>{body}</table>" if rows else '<p class="muted">No entries.</p>'


def render_html(report: dict) -> str:
    parts = []
    for s in report["sections"]:
        parts.append(f"<h2>{html.escape(s['title'])}</h2>")
        if s.get("kv"):
            parts.append("<table>" + "".join(f'<tr><td class="k">{html.escape(str(k))}</td><td class="mono">{html.escape(_f(v))}</td></tr>'
                                             for k, v in s["kv"]) + "</table>")
        for key in ("table", "table2"):
            if s.get(key):
                parts.append(_html_table(s[key]["columns"], s[key]["rows"]))
        for p in s.get("text") or []:
            parts.append(f"<p>{html.escape(str(p))}</p>")
        if s.get("list"):
            parts.append("<ul>" + "".join(f"<li>{html.escape(str(x))}</li>" for x in s["list"]) + "</ul>")
        for im in s.get("images") or []:
            parts.append(f'<figure><img src="{html.escape(str(im["file"]))}" alt="{html.escape(str(im.get("caption", "")))}" '
                         f'style="max-width:100%;border:1px solid var(--line)"><figcaption class="muted">'
                         f'{html.escape(str(im.get("caption", "")))}</figcaption></figure>')
    try:
        tpl = Template(resource_path("assets", "templates", "report.html").read_text(encoding="utf-8"))
    except OSError:
        tpl = Template("<html><head><meta charset='utf-8'><title>$title</title></head><body><h1>$title</h1><p>$subtitle</p>$content</body></html>")
    return tpl.safe_substitute(title=html.escape(report["title"]), subtitle=html.escape(report["subtitle"]), content="\n".join(parts))


def write_html(report: dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(report), encoding="utf-8")
    return path


def _pdf_text(v) -> str:
    s = _f(v)
    for a, b in PDF_SAFE.items():
        s = s.replace(a, b)
    s = s.encode("latin-1", "replace").decode("latin-1")
    return html.escape(s, quote=False)


def write_pdf(report: dict, path: Path) -> Path:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=8.5, leading=11)
    cell = ParagraphStyle("c", parent=body, fontSize=7, leading=8.6, splitLongWords=1)
    cellh = ParagraphStyle("ch", parent=cell, fontName="Helvetica-Bold", textColor=colors.HexColor("#1D3B4A"))
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=18, leading=22, alignment=0)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11.5, textColor=colors.HexColor("#1F7F95"), spaceBefore=10)
    small = ParagraphStyle("s", parent=body, fontSize=7.5, textColor=colors.HexColor("#5A6773"))
    width = A4[0] - 30 * mm
    grid = TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B8C4CE")),
                       ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E6EEF3")),
                       ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3),
                       ("RIGHTPADDING", (0, 0), (-1, -1), 3)])
    story = [Paragraph("INSiYDE INNOVATIONS - NuRichter Workspace - Faculty of Computer Science", small),
             Paragraph(_pdf_text(report["title"]), h1), Paragraph(_pdf_text(report["subtitle"]), small), Spacer(1, 6)]

    def table(columns, rows):
        if not rows:
            return Paragraph("No entries.", small)
        data = [[Paragraph(_pdf_text(c), cellh) for c in columns]] + [[Paragraph(_pdf_text(v), cell) for v in r] for r in rows]
        t = Table(data, colWidths=[width / len(columns)] * len(columns), repeatRows=1)
        t.setStyle(grid)
        return t

    for s in report["sections"]:
        story.append(Paragraph(_pdf_text(s["title"]), h2))
        if s.get("kv"):
            data = [[Paragraph(_pdf_text(k), cellh), Paragraph(_pdf_text(v), cell)] for k, v in s["kv"]]
            t = Table(data, colWidths=[width * 0.3, width * 0.7])
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B8C4CE")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story.append(t)
        for key in ("table", "table2"):
            if s.get(key):
                story.extend([Spacer(1, 3), table(s[key]["columns"], s[key]["rows"])])
        for p in s.get("text") or []:
            story.append(Paragraph(_pdf_text(p), body))
        for item in s.get("list") or []:
            story.append(Paragraph("- " + _pdf_text(item), body))
        for im in s.get("images") or []:
            src = Path(str(im.get("path") or ""))
            if src.is_file():
                from reportlab.platypus import Image as RLImage

                img = RLImage(str(src))
                scale = min(1.0, (width * 0.6) / float(img.drawWidth), (90 * mm) / float(img.drawHeight))
                img.drawWidth, img.drawHeight = img.drawWidth * scale, img.drawHeight * scale
                story.extend([Spacer(1, 3), img, Paragraph(_pdf_text(im.get("caption", "")), small)])

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#5A6773"))
        canvas.drawString(15 * mm, 10 * mm, "SynthProvenance - Insyide Innovations x NuRichter Workspace - LOCAL RESEARCH "
                                            f"ENVIRONMENT - {report['experiment_id']}")
        canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f"page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=14 * mm,
                            bottomMargin=16 * mm, title=report["title"], author="SynthProvenance",
                            subject=report["experiment_id"])
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path


def write_png(report: dict, exp: Experiment, path: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    def font(size):
        try:
            return ImageFont.load_default(size=size)
        except TypeError:  # very old Pillow
            return ImageFont.load_default()

    done = [t for t in exp.transformations if t.status == "COMPLETE"]
    W, row_h = 1600, 30
    H = 330 + row_h * (len(done) + 1) + 120
    im = Image.new("RGB", (W, H), "#0E1318")
    d = ImageDraw.Draw(im)
    cyan, text, muted, line = "#4CC3D9", "#D5DEE7", "#7D8C9B", "#243140"
    d.text((40, 30), "INSiYDE INNOVATIONS  |  NuRichter Workspace", fill=muted, font=font(16))
    d.text((40, 58), "SynthProvenance Research Summary", fill=text, font=font(34))
    d.line((40, 108, W - 40, 108), fill=cyan, width=2)
    base = exp.baseline or {}
    img, c2, sig = base.get("image") or {}, base.get("c2pa") or {}, base.get("signal") or {}
    info = [f"Experiment  {exp.experiment_id}", f"Input  {img.get('filename')}  {img.get('format')}  {img.get('width')}x{img.get('height')}",
            f"SHA-256  {(base.get('hashes') or {}).get('sha256', '')}",
            f"C2PA  {c2.get('state')}   |   AI-content signal  {sig.get('state')}   |   SynthID  {(exp.synthid_baseline or {}).get('state', 'UNAVAILABLE')}"]
    for i, s in enumerate(info):
        d.text((40, 126 + i * 34), s, fill=text if i else cyan, font=font(19))
    y = 290
    cols = [(40, "ID"), (120, "Condition"), (560, "Pixels"), (860, "C2PA"), (1110, "SynthID"), (1330, "Signal")]
    for x, h in cols:
        d.text((x, y), h, fill=muted, font=font(16))
    d.line((40, y + 24, W - 40, y + 24), fill=line)
    for n, t in enumerate(done, 1):
        yy = y + n * row_h + 4
        c2l = next((x for x in t.layers if x["layer"] == "C2PA"), {}).get("state", "-")
        sil = next((x for x in t.layers if x["layer"] == "SynthID"), {}).get("state", "-")
        verdict = (t.pixel_metrics or {}).get("verdict", "-")
        vals = [t.transformation_id, t.label[:40], verdict, c2l, sil, f"{t.signal_before} -> {t.signal_after}"]
        for (x, _h), v in zip(cols, vals):
            color = "#46B37B" if v == "PIXEL-EXACT" else "#D9A441" if v == "TRANSFORMATION DETECTED" else text
            d.text((x, yy), str(v), fill=color, font=font(16))
    d.line((40, H - 90, W - 40, H - 90), fill=line)
    d.text((40, H - 76), "Experimental observation only. Not an AI/human verdict and no prediction of platform behaviour.",
           fill=muted, font=font(15))
    d.text((40, H - 50), "SynthProvenance  |  Insyide Innovations x NuRichter Workspace  |  LOCAL RESEARCH ENVIRONMENT  |  "
                         "WE DO NOT GUESS. WE MEASURE.", fill=muted, font=font(15))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    path.write_bytes(buf.getvalue())
    return path


def write_all(exp: Experiment, out_dir: Path, audit_events: list | None = None, engine_status: dict | None = None,
              formats=("pdf", "json", "csv", "html", "png")) -> dict[str, Path]:
    report = build_report(exp, audit_events, engine_status)
    out_dir = Path(out_dir)
    paths: dict[str, Path] = {}
    stem = f"{exp.experiment_id}_report"
    if "json" in formats:
        paths["json"] = write_json_report(report, out_dir / f"{stem}.json")
    if "csv" in formats:
        paths["csv"] = write_csv(exp, out_dir / f"{stem}.csv")
    if "html" in formats:
        paths["html"] = write_html(report, out_dir / f"{stem}.html")
    if "pdf" in formats:
        paths["pdf"] = write_pdf(report, out_dir / f"{stem}.pdf")
    if "png" in formats:
        paths["png"] = write_png(report, exp, out_dir / f"{stem}.png")
    return paths
