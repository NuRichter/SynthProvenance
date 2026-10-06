"""Generate the README figures in docs/readme/ from the lab's own data and measurements.

Nothing in these figures is typed in by hand. The 8x8 method block is read from
data/fingerprint_execution_matrix.json. The hero readout and the anatomy plates are the lab's own analysis of its
demo fixture (app.core.synthetic.make_jpeg), measured when this script runs. The signal plate shows the lab's keyed
surrogate pattern (app.research.surrogate), not SynthID. Every figure is written twice, for light and dark GitHub
themes, and animates only when the viewer has not asked for reduced motion.

    python scripts/build_readme_assets.py                 SVG figures
    python scripts/build_readme_assets.py --screenshots   also re-capture the GUI screenshots from source
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "readme"
TEST_IMAGE = ROOT / "test image" / "Playful Bunny Mascot in a Neon Toy Store.png"

from app import __version__  # noqa: E402

# colour tokens from app/ui/themes.py: "Dark Laboratory", and "Light Laboratory" accents on "Paper" stock
THEMES = {
    "dark": {"bg": "#0E1318", "panel": "#141B22", "raised": "#1A232C", "side": "#0A0F13", "line": "#243140",
             "text": "#D5DEE7", "muted": "#7D8C9B", "faint": "#3A4855", "accent": "#4CC3D9", "ok": "#46B37B",
             "warn": "#D9A441", "bad": "#E0605A", "tex": (213, 222, 231), "tex_alpha": 0.11},
    "light": {"bg": "#F6F5F2", "panel": "#FFFFFF", "raised": "#FBFAF8", "side": "#E4E0D6", "line": "#D9D5CC",
              "text": "#1A1A18", "muted": "#55534C", "faint": "#BDB7AA", "accent": "#0B6E80", "ok": "#1D7A4C",
              "warn": "#8A5A00", "bad": "#B42318", "tex": (26, 26, 24), "tex_alpha": 0.075},
}
FONTS = (".serif{font-family:Georgia,'Times New Roman','DejaVu Serif',serif}"
         ".mono{font-family:'Cascadia Mono','SF Mono',SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono',"
         "'Liberation Mono',monospace}"
         ".sans{font-family:'Segoe UI',-apple-system,'Helvetica Neue',Helvetica,Arial,sans-serif}")
MOTION = "@media (prefers-reduced-motion:no-preference){%s}"
MONO_ADVANCE = 0.6  # em; the widest common monospace fallback, used to lay out monospace runs


def esc(s) -> str:
    return escape(str(s), quote=True)


def mono_width(s: str, size: float, spacing: float = 0.0) -> float:
    return len(s) * (size * MONO_ADVANCE + spacing)


def document(w: int, h: int, t: dict, title: str, desc: str, body: str, css: str = "") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
            f'aria-labelledby="t d">\n<title id="t">{esc(title)}</title>\n<desc id="d">{esc(desc)}</desc>\n'
            f"<style>{FONTS}{css}</style>\n"
            f'<rect width="{w}" height="{h}" fill="{t["bg"]}"/>\n'
            f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" fill="none" stroke="{t["line"]}"/>\n'
            f"{body}\n</svg>\n")


def crop_marks(w: int, h: int, t: dict, inset: int = 18, arm: int = 14) -> str:
    out = []
    for x, y, dx, dy in ((inset, inset, 1, 1), (w - inset, inset, -1, 1), (inset, h - inset, 1, -1),
                         (w - inset, h - inset, -1, -1)):
        out.append(f'<path d="M{x} {y + dy * arm}V{y}H{x + dx * arm}" fill="none" stroke="{t["muted"]}"/>')
    return "".join(out)


def png_uri(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def jpeg_uri(img: Image.Image, quality: int) -> str:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, subsampling="4:2:0", optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# --------------------------------------------------------------------------------------------- measurement
def measure_fixture() -> dict:
    """Analyse the lab's demo fixture with the lab's own engines and keep what the figures show."""
    from app.core.metadata_engine import analyze_file
    from app.core.synthetic import make_jpeg
    from app.core.synthid_engine import SynthIDEngine
    from app.research.surrogate import SurrogateConfig, pattern

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "SYNTHETIC_TEST_FIXTURE_ai_c2pa.jpg"
        path.write_bytes(make_jpeg(size=(640, 427)))
        a = analyze_file(path).to_dict()
        synthid = SynthIDEngine.discover().analyze(path).state
        with Image.open(path) as im:
            pixels = im.convert("RGB")
    image, c2pa = a["image"], a["c2pa"]
    q = re.search(r"Q~(\d+)", image.get("compression", ""))
    declarations = [e for e in a["signal"]["evidence"] if e.get("counted")]
    surrogate = SurrogateConfig()
    return {
        "name": path.name, "format": image["format"], "width": image["width"], "height": image["height"],
        "kib": a["compression"]["file_bytes"] / 1024, "quality": q.group(1) if q else "?",
        "process": a["compression"].get("process", ""), "subsampling": "4:2:0" if "4:2:0" in image["compression"] else "",
        "pixel_sha256": a["hashes"]["pixel_sha256"],
        "c2pa": c2pa["state"], "binding": c2pa.get("hard_binding", "UNKNOWN"),
        "validity": c2pa.get("validity", "UNKNOWN"), "trust": c2pa.get("trust", "UNKNOWN"),
        "declarations": len(declarations),
        "declaration_sources": sorted({e["source"].split()[0] for e in declarations}),
        "metadata": [g for g in ("EXIF", "XMP", "IPTC", "ICC") if a["groups"].get(g, {}).get("state") == "PRESENT"],
        "exif": [(f["key"], f["value"]) for f in a["groups"].get("EXIF", {}).get("fields", [])][:5],
        "container": a["structure"]["container"],
        "segments": [(s["name"], s.get("ident", "")) for s in a["structure"]["segments"]],
        "synthid": synthid,
        "pixels": pixels,
        "surrogate_key": surrogate.key,
        "surrogate": pattern((17, 30), surrogate),
    }


# --------------------------------------------------------------------------------------------- Fig. 0: hero
def hero(t: dict, m: dict) -> str:
    w, h = 1000, 560
    b = [crop_marks(w, h, t)]
    b.append(f'<text x="56" y="52" class="mono" font-size="11" letter-spacing="2.2" fill="{t["muted"]}">'
             f"EXHIBIT 0 · SYNTHPROVENANCE {esc(__version__)}</text>")
    b.append(f'<text x="944" y="52" class="mono" font-size="11" letter-spacing="2.2" fill="{t["muted"]}" '
             f'text-anchor="end">LOCAL-ONLY · NO UPLOAD · NO TELEMETRY</text>')
    b.append(f'<path d="M56 68H944" stroke="{t["line"]}"/>')
    b.append(f'<text x="52" y="150" class="serif" font-size="70" letter-spacing="-1" fill="{t["text"]}">'
             f"SynthProvenance</text>")
    b.append(f'<text x="56" y="186" class="mono" font-size="12" letter-spacing="2.6" fill="{t["muted"]}">'
             f"SCIENTIFIC AI CONTENT SIGNAL &amp; IMAGE PROVENANCE LABORATORY</text>")
    b.append(f'<text x="944" y="122" class="serif" font-size="24" font-style="italic" fill="{t["muted"]}" '
             f'text-anchor="end">We do not guess.</text>')
    b.append(f'<text x="944" y="154" class="serif" font-size="24" font-style="italic" fill="{t["accent"]}" '
             f'text-anchor="end">We measure.</text>')
    b.append(f'<path d="M56 216H944" stroke="{t["line"]}"/>')

    # specimen on an ABFO-style L-scale: 4 px per millimetre, labelled every centimetre
    ix, iy, iw, ih = 104, 248, 330, 220
    spec = m["pixels"].resize((495, 330), Image.LANCZOS)
    b.append(f'<image x="{ix}" y="{iy}" width="{iw}" height="{ih}" href="{jpeg_uri(spec, 80)}" '
             f'preserveAspectRatio="none"/>')
    b.append(f'<rect x="{ix}" y="{iy}" width="{iw}" height="{ih}" fill="none" stroke="{t["line"]}"/>')
    b.append(f'<g class="scan"><rect x="{ix}" y="{iy}" width="{iw}" height="1.5" fill="{t["accent"]}"/>'
             f'<rect x="{ix}" y="{iy - 14}" width="{iw}" height="14" fill="{t["accent"]}" opacity=".12"/></g>')
    rx, ry = ix - 30, iy + ih + 10  # ruler inner corner
    b.append(f'<rect x="{rx}" y="{iy}" width="22" height="{ih + 32}" fill="{t["panel"]}" stroke="{t["line"]}"/>')
    b.append(f'<rect x="{rx}" y="{ry}" width="{iw + 30}" height="22" fill="{t["panel"]}" stroke="{t["line"]}"/>')
    for k in range(0, iw // 4 + 1):
        x = ix + k * 4
        ln = 9 if k % 10 == 0 else 6 if k % 5 == 0 else 3.5
        b.append(f'<path d="M{x} {ry}v{ln}" stroke="{t["muted"]}" stroke-width=".8"/>')
        if k % 10 == 0 and k:
            b.append(f'<text x="{x}" y="{ry + 19}" class="mono" font-size="8" fill="{t["muted"]}" '
                     f'text-anchor="middle">{k // 10}</text>')
    for k in range(0, ih // 4 + 1):
        y = iy + ih - k * 4
        ln = 9 if k % 10 == 0 else 6 if k % 5 == 0 else 3.5
        b.append(f'<path d="M{rx + 22} {y}h{-ln}" stroke="{t["muted"]}" stroke-width=".8"/>')
        if k % 10 == 0 and k:
            b.append(f'<text x="{rx + 7}" y="{y + 3}" class="mono" font-size="8" fill="{t["muted"]}" '
                     f'text-anchor="middle">{k // 10}</text>')
    b.append(f'<circle cx="{rx + 11}" cy="{ry + 11}" r="6" fill="none" stroke="{t["muted"]}"/>')
    b.append(f'<circle cx="{rx + 11}" cy="{ry + 11}" r="1.3" fill="{t["muted"]}"/>')
    b.append(f'<text x="{ix + iw + 4}" y="{ry + 15}" class="mono" font-size="8" fill="{t["muted"]}">cm</text>')

    # readout: what the lab measured on that specimen
    sha = m["pixel_sha256"]
    groups = [" ".join(sha[i:i + 8] for i in range(0, 32, 8)), " ".join(sha[i:i + 8] for i in range(32, 64, 8))]
    rows = [
        ("SPECIMEN", f'{m["format"]} · {m["width"]} × {m["height"]} · {m["kib"]:.1f} KiB', "text"),
        ("PIXEL SHA-256", groups[0], "text"),
        ("", groups[1], "text"),
        ("C2PA", f'{m["c2pa"]} · hard binding {m["binding"]}', "ok" if m["binding"] == "MATCH" else "text"),
        ("SIGNATURE", f'{m["validity"]} · trust {m["trust"]}', "warn"),
        ("AI DECLARATION", f'{m["declarations"]} ({", ".join(m["declaration_sources"])}) · declared, not determined',
         "text"),
        ("SYNTHID", f'{m["synthid"]} · no local engine' if m["synthid"] == "UNAVAILABLE" else m["synthid"],
         "muted"),
        ("METADATA", " · ".join(m["metadata"]) + " present", "text"),
    ]
    lx, vx, y0, step = 478, 616, 262, 25
    css_rows = []
    for i, (label, value, tone) in enumerate(rows):
        y = y0 + i * step
        b.append(f'<g class="r" style="animation-delay:{0.35 + i * 0.16:.2f}s">')
        if label:
            b.append(f'<text x="{lx}" y="{y}" class="mono" font-size="10.5" letter-spacing="1.4" '
                     f'fill="{t["muted"]}">{label}</text>')
            end = lx + mono_width(label, 10.5, 1.4) + 6
            b.append(f'<path d="M{end:.0f} {y - 3}H{vx - 8}" stroke="{t["faint"]}" stroke-dasharray="1 3"/>')
        b.append(f'<text x="{vx}" y="{y}" class="mono" font-size="13" fill="{t[tone]}">{esc(value)}</text></g>')
    y = y0 + len(rows) * step + 10
    b.append(f'<path d="M{lx} {y - 16}H944" stroke="{t["line"]}"/>')
    b.append(f'<g class="r" style="animation-delay:{0.35 + len(rows) * 0.16 + 0.2:.2f}s">'
             f'<text x="{lx}" y="{y + 8}" class="mono" font-size="10.5" letter-spacing="1.4" '
             f'fill="{t["muted"]}">VERDICT</text>'
             f'<path d="M{lx + mono_width("VERDICT", 10.5, 1.4) + 6:.0f} {y + 5}H{vx - 8}" stroke="{t["faint"]}" '
             f'stroke-dasharray="1 3"/>'
             f'<text x="{vx}" y="{y + 9}" class="serif" font-size="21" font-style="italic" fill="{t["accent"]}">'
             f"none issued.</text></g>")
    css_rows.append(".r{animation:in .5s ease-out both}")
    b.append(f'<text x="56" y="532" class="mono" font-size="9.5" letter-spacing="1.2" fill="{t["muted"]}">'
             f"FIG. 0 · THE LAB&#8217;S OWN DEMO FIXTURE, SHOWN REDUCED · EVERY READING ABOVE WAS "
             f"COMPUTED BY SYNTHPROVENANCE WHEN THIS FIGURE WAS BUILT</text>")
    # the scan line only exists while it moves; with reduced motion the figure is fully static
    css = ".scan{opacity:0}" + MOTION % (
        "@keyframes in{from{opacity:0;transform:translateX(-6px)}}"
        "@keyframes scan{0%{transform:translateY(0);opacity:0}6%{opacity:1}"
        f"40%{{transform:translateY({ih}px);opacity:1}}46%,100%{{transform:translateY({ih}px);opacity:0}}}}"
        ".scan{animation:scan 7s cubic-bezier(.4,0,.2,1) .2s infinite}" + "".join(css_rows))
    return document(w, h, t, "SynthProvenance",
                    "SynthProvenance, Scientific AI Content Signal and Image Provenance Laboratory. The lab's demo "
                    "fixture on a forensic scale, with the readings the lab computed for it: pixel SHA-256, C2PA "
                    "present with hard binding match, signature not validated, SynthID unavailable, and no verdict "
                    "issued.", "\n".join(b), css)


# --------------------------------------------------------------------------------------------- Fig. 1: anatomy
PW, PH = 300, 170          # plate, in flat units
IA, IB = 0.82, 0.26        # flat -> screen projection
PLATE_X, PLATE_Y0, PLATE_STEP = 200, 88, 80


def _iso(e: float, f: float) -> str:
    return f"matrix({IA} {IB} {-IA} {IB} {e} {f})"


def _plate_content(kind: str, t: dict, m: dict) -> str:
    out = []
    if kind == "external":
        for i, s in enumerate(("platform label", "detector result")):
            out.append(f'<rect x="{24 + i * 140}" y="56" width="124" height="44" rx="22" fill="none" '
                       f'stroke="{t["muted"]}" stroke-dasharray="5 4"/>'
                       f'<text x="{86 + i * 140}" y="84" class="mono" font-size="14" text-anchor="middle" '
                       f'fill="{t["muted"]}">{s}</text>')
        out.append(f'<text x="150" y="140" class="mono" font-size="13" text-anchor="middle" fill="{t["muted"]}">'
                   f"recorded by you · never fetched</text>")
    elif kind == "c2pa":
        for i, s in enumerate(("manifest", "claim", "signature")):
            x = 18 + i * 94
            out.append(f'<rect x="{x}" y="40" width="80" height="42" fill="{t["raised"]}" stroke="{t["accent"]}"/>'
                       f'<text x="{x + 40}" y="66" class="mono" font-size="13" text-anchor="middle" '
                       f'fill="{t["text"]}">{s}</text>')
            if i:
                out.append(f'<path d="M{x - 14} 61h14" stroke="{t["accent"]}"/>')
        out.append(f'<path d="M58 82v40h184v-40" fill="none" stroke="{t["accent"]}" stroke-dasharray="4 3"/>'
                   f'<text x="150" y="146" class="mono" font-size="13" text-anchor="middle" fill="{t["muted"]}">'
                   f"c2pa.hash.data → file bytes</text>")
    elif kind == "metadata":
        for i, (k, v) in enumerate(m["exif"]):
            y = 34 + i * 27
            out.append(f'<text x="20" y="{y}" class="mono" font-size="14" fill="{t["muted"]}">{esc(k)}</text>'
                       f'<text x="132" y="{y}" class="mono" font-size="14" fill="{t["text"]}">'
                       f"{esc(str(v)[:18])}</text>")
    elif kind == "structure":
        x, y = 14, 16
        for name, ident in [("SOI", "")] + m["segments"] + [("EOI", "")]:
            label = name if ident in ("", name) or name.startswith(("DQT", "DHT", "SOF")) else f"{name}·{ident}"
            bw = 12 + len(label) * 8.2
            if x + bw > PW - 10:
                x, y = 14, y + 30
            hot = ident == "JUMBF"
            out.append(f'<rect x="{x:.1f}" y="{y}" width="{bw:.1f}" height="22" fill="{t["raised"]}" '
                       f'stroke="{t["accent"] if hot else t["line"]}"/>'
                       f'<text x="{x + bw / 2:.1f}" y="{y + 15.5}" class="mono" font-size="12.5" text-anchor="middle" '
                       f'fill="{t["accent"] if hot else t["text"]}">{esc(label)}</text>')
            x += bw + 6
    elif kind == "encoding":
        for gx in range(0, PW + 1, 20):
            out.append(f'<path d="M{gx} 0V{PH}" stroke="{t["line"]}"/>')
        for gy in range(0, PH + 1, 20):
            out.append(f'<path d="M0 {gy}H{PW}" stroke="{t["line"]}"/>')
        out.append(f'<rect x="120" y="60" width="40" height="40" fill="{t["accent"]}" fill-opacity=".18" '
                   f'stroke="{t["accent"]}"/>')
        for k in range(1, 8):
            out.append(f'<path d="M{120 + k * 5} 60v40M120 {60 + k * 5}h40" stroke="{t["accent"]}" '
                       f'stroke-width=".4"/>')
    elif kind == "pixels":
        small = np.asarray(m["pixels"].resize((30, 17), Image.BOX))
        for r in range(17):
            for c in range(30):
                red, green, blue = (int(v) for v in small[r, c])
                out.append(f'<rect x="{c * 10}" y="{r * 10}" width="10" height="10" '
                           f'fill="#{red:02x}{green:02x}{blue:02x}"/>')
    elif kind == "signal":
        p = m["surrogate"]
        p = p / (np.abs(p).max() or 1.0)
        for r in range(17):
            for c in range(30):
                v = float(p[r, c])
                s = 2 + 6 * abs(v)
                out.append(f'<rect x="{c * 10 + 5 - s / 2:.1f}" y="{r * 10 + 5 - s / 2:.1f}" width="{s:.1f}" '
                           f'height="{s:.1f}" fill="{t["accent"] if v > 0 else t["muted"]}" '
                           f'fill-opacity="{0.25 + 0.6 * abs(v):.2f}"/>')
    return "".join(out)


def anatomy(t: dict, m: dict) -> str:
    w, h = 1000, 770
    plates = [
        ("external", "External platforms", "labels shown by third parties", "user-recorded only · never contacted",
         "OUTSIDE THE FILE"),
        ("c2pa", "C2PA manifest", "JUMBF / CBOR · hard-binding digest",
         f'{m["c2pa"]} · binding {m["binding"]} · {m["validity"]}', "IN THE CONTAINER"),
        ("metadata", "Ordinary metadata", "EXIF · XMP · IPTC · ICC · PNG text",
         " ".join(m["metadata"]) + " present", None),
        ("structure", "File structure", "segments and chunks, walked byte by byte",
         f'{len(m["segments"]) + 2} {m["container"]} markers walked', None),
        ("encoding", "Encoding", "codec and parameters",
         f'{m["format"]} {m["process"]} · {m["subsampling"]} · Q≈{m["quality"]} (est.)', "IN THE CODEC"),
        ("pixels", "Pixels", "the decoded sample array",
         f'pixel sha256 {m["pixel_sha256"][:16]}…', "IN THE PIXEL VALUES"),
        ("signal", "Embedded signal", "SynthID lives here — never in metadata",
         f'SynthID {m["synthid"]} · plate: lab surrogate, key {m["surrogate_key"]}', None),
    ]
    b = [crop_marks(w, h, t)]
    b.append(f'<text x="40" y="46" class="mono" font-size="11" letter-spacing="2.2" fill="{t["muted"]}">'
             f"FIG. 1 · ANATOMY OF A SPECIMEN</text>")
    b.append(f'<text x="960" y="46" class="mono" font-size="11" letter-spacing="2.2" fill="{t["muted"]}" '
             f'text-anchor="end">SEVEN LAYERS · MEASURED SEPARATELY</text>')
    rvx, rvy = PW * IA, PW * IB                     # right vertex, relative to the plate origin
    bvx, bvy = PW * IA - PH * IA, (PW + PH) * IB    # bottom vertex
    lvx, lvy = -PH * IA, PH * IB                    # left vertex
    css = ["@keyframes lab{from{opacity:0}}", ".lab{animation:lab .6s ease-out both}"]
    for i in reversed(range(len(plates))):
        kind = plates[i][0]
        e, f = PLATE_X, PLATE_Y0 + i * PLATE_STEP
        dy = (3 - i) * PLATE_STEP
        css.append(f"@keyframes p{i}{{from{{transform:translateY({dy}px)}}}}"
                   f".p{i}{{animation:p{i} 1.1s cubic-bezier(.2,.7,.2,1) .25s both}}")
        dashed = kind == "external"
        outline = f'stroke="{t["muted"]}" stroke-dasharray="6 5"' if dashed else f'stroke="{t["line"]}"'
        side = (f'<path d="M{e + lvx:.1f} {f + lvy:.1f}L{e + bvx:.1f} {f + bvy:.1f}L{e + rvx:.1f} {f + rvy:.1f}'
                f'v6L{e + bvx:.1f} {f + bvy + 6:.1f}L{e + lvx:.1f} {f + lvy + 6:.1f}Z" fill="{t["side"]}"/>')
        face = (f'<g transform="{_iso(e, f)}"><rect width="{PW}" height="{PH}" '
                f'fill="{"none" if dashed else t["panel"]}" fill-opacity=".94" {outline} '
                f'vector-effect="non-scaling-stroke"/>'
                f"{_plate_content(kind, t, m)}</g>")
        b.append(f'<g class="p{i}">{"" if dashed else side}{face}</g>')
    for i, (kind, name, what, reading, group) in enumerate(plates):
        f = PLATE_Y0 + i * PLATE_STEP
        y = f + rvy
        x0 = PLATE_X + rvx
        delay = 1.15 + i * 0.07
        b.append(f'<g class="lab" style="animation-delay:{delay:.2f}s">')
        b.append(f'<path d="M{x0 + 6:.1f} {y:.1f}H604" stroke="{t["faint"]}"/>'
                 f'<circle cx="{x0 + 6:.1f}" cy="{y:.1f}" r="2" fill="{t["muted"]}"/>')
        if group:
            b.append(f'<text x="616" y="{y - 33:.1f}" class="mono" font-size="9" letter-spacing="2" '
                     f'fill="{t["accent"]}">{group}</text>')
        b.append(f'<text x="616" y="{y - 6:.1f}" class="serif" font-size="19" fill="{t["text"]}">{esc(name)}</text>'
                 f'<text x="616" y="{y + 12:.1f}" class="mono" font-size="11" fill="{t["muted"]}">{esc(what)}</text>'
                 f'<text x="616" y="{y + 28:.1f}" class="mono" font-size="11" fill="{t["text"]}">{esc(reading)}</text>')
        b.append("</g>")
    b.append(f'<text x="40" y="{h - 26}" class="mono" font-size="9.5" letter-spacing="1.2" fill="{t["muted"]}">'
             f"READINGS: THE SAME FIXTURE AS FIG. 0 · THE SIGNAL PLATE SHOWS THE LAB&#8217;S KEYED SURROGATE, "
             f"NOT SYNTHID</text>")
    return document(w, h, t, "Anatomy of a specimen",
                    "Exploded view of the seven layers SynthProvenance measures separately: external platform labels, "
                    "C2PA manifest, ordinary metadata, file structure, encoding, pixels and the embedded signal, each "
                    "with the reading taken from the lab's demo fixture.",
                    "\n".join(b), MOTION % "".join(css))


# --------------------------------------------------------------------------------------------- Fig. 2: registry
CELL, GAP, GX, GY = 104, 6, 63, 96
CAPS = (("A", "CAN_ANALYZE"), ("E", "CAN_ESTIMATE"), ("S", "CAN_SEPARATE"), ("R", "CAN_RECONSTRUCT"),
        ("V", "CAN_VALIDATE"))


def zigzag(n: int = 8) -> list[tuple[int, int]]:
    """JPEG zig-zag scan order as (row, col), starting at the DC coefficient."""
    order = []
    for s in range(2 * n - 1):
        diag = [(r, s - r) for r in range(n) if 0 <= s - r < n]
        order += diag if s % 2 else diag[::-1]
    return order


def dct_atlas(t: dict) -> Image.Image:
    """The 64 DCT-II basis functions, one per cell, laid out on the grid geometry (13 px per basis sample)."""
    side = 8 * CELL + 7 * GAP
    rgba = np.zeros((side, side, 4), np.uint8)
    rgba[..., :3] = t["tex"]
    k = np.arange(8)
    for u in range(8):
        for v in range(8):
            basis = np.outer(np.cos((2 * k + 1) * u * np.pi / 16), np.cos((2 * k + 1) * v * np.pi / 16))
            alpha = ((basis + 1) / 2 * 255 * t["tex_alpha"]).astype(np.uint8)
            tile = np.kron(alpha, np.ones((CELL // 8, CELL // 8), np.uint8))
            y, x = u * (CELL + GAP), v * (CELL + GAP)
            rgba[y:y + tile.shape[0], x:x + tile.shape[1], 3] = tile
    return Image.fromarray(rgba, "RGBA")


def wrap(name: str, limit: int = 15, lines: int = 4) -> list[str]:
    words = []
    for word in name.split():
        while len(word) > limit and "-" in word[:limit]:
            cut = word[:limit].rindex("-") + 1
            words.append(word[:cut])
            word = word[cut:]
        words.append(word)
    out: list[str] = []
    for word in words:
        if out and len(out[-1]) + 1 + len(word) <= limit and not out[-1].endswith("-"):
            out[-1] += " " + word
        elif out and out[-1].endswith("-") and len(out[-1]) + len(word) <= limit:
            out[-1] += word
        else:
            out.append(word)
    return out[:lines]


def registry(t: dict, matrix: dict) -> str:
    methods = matrix["methods"]
    assert len(methods) == 64, "the 8x8 figure needs exactly 64 methods"
    order = zigzag()
    counts = {s: sum(1 for x in methods if x["availability"] == s) for s in ("READY", "UNAVAILABLE", "NOT_IMPLEMENTED")}
    separators = {x["category"] for x in methods if x["capabilities"]["CAN_SEPARATE"]}
    w, h = 1000, 1150
    b = [crop_marks(w, h, t)]
    b.append(f'<defs><pattern id="hatch" width="7" height="7" patternUnits="userSpaceOnUse" '
             f'patternTransform="rotate(45)"><path d="M0 0V7" stroke="{t["faint"]}" stroke-width="1"/></pattern></defs>')
    b.append(f'<text x="{GX}" y="48" class="mono" font-size="11" letter-spacing="2.2" fill="{t["muted"]}">'
             f'FIG. 2 · METHOD REGISTRY {esc(matrix["software_version"])} · {len(methods)} METHODS</text>')
    b.append(f'<text x="{w - GX}" y="48" class="mono" font-size="11" letter-spacing="2.2" fill="{t["muted"]}" '
             f'text-anchor="end">LAID OUT IN JPEG ZIG-ZAG ORDER</text>')
    b.append(f'<text x="{GX}" y="76" class="serif" font-size="17" font-style="italic" fill="{t["text"]}">'
             f"Each cell carries the DCT basis function of its coefficient. Method 00, the untouched control, "
             f"sits on DC.</text>")
    cells, marks = [], []
    css = ["@keyframes c{from{opacity:0}}", ".c{animation:c .45s ease-out both}"]
    for idx, x in enumerate(methods):
        r, c = order[idx]
        cx, cy = GX + c * (CELL + GAP), GY + r * (CELL + GAP)
        status = x["availability"]
        delay = f'style="animation-delay:{0.2 + idx * 0.028:.3f}s"'
        if status == "READY":
            fill = f'<rect x="{cx}" y="{cy}" width="{CELL}" height="{CELL}" fill="{t["panel"]}"/>'
            border = f'<rect x="{cx + .5}" y="{cy + .5}" width="{CELL - 1}" height="{CELL - 1}" fill="none" stroke="{t["line"]}"/>'
            border += f'<path d="M{cx} {cy + 1}H{cx + CELL}" stroke="{t["accent"]}" stroke-width="2"/>'
            ink, name_ink = t["text"], t["text"]
        elif status == "UNAVAILABLE":
            fill = f'<rect x="{cx}" y="{cy}" width="{CELL}" height="{CELL}" fill="url(#hatch)"/>'
            border = (f'<rect x="{cx + .5}" y="{cy + .5}" width="{CELL - 1}" height="{CELL - 1}" fill="none" '
                      f'stroke="{t["muted"]}" stroke-dasharray="3 3"/>')
            ink, name_ink = t["muted"], t["muted"]
        else:
            fill = (f'<rect x="{cx}" y="{cy}" width="{CELL}" height="{CELL}" fill="{t["bad"]}" fill-opacity=".10"/>')
            border = (f'<rect x="{cx + .5}" y="{cy + .5}" width="{CELL - 1}" height="{CELL - 1}" fill="none" '
                      f'stroke="{t["bad"]}"/><path d="M{cx + CELL} {cy}L{cx} {cy + CELL}" stroke="{t["bad"]}" '
                      f'stroke-opacity=".55"/>')
            ink, name_ink = t["bad"], t["bad"]
        cells.append(f'<g class="c" {delay}>{fill}</g>')
        g = [f'<g class="c" {delay}>{border}',
             f'<text x="{cx + 9}" y="{cy + 22}" class="mono" font-size="15" font-weight="700" fill="{ink}">'
             f'{x["code"].split("-")[1]}</text>']
        if status == "NOT_IMPLEMENTED":
            g.append(f'<text x="{cx + CELL - 8}" y="{cy + 20}" class="mono" font-size="7.5" letter-spacing=".8" '
                     f'text-anchor="end" fill="{t["bad"]}">REFUSED</text>')
        for j, line in enumerate(wrap(x["name"])):
            g.append(f'<text x="{cx + 9}" y="{cy + 41 + j * 12.5}" class="sans" font-size="10.5" fill="{name_ink}">'
                     f"{esc(line)}</text>")
        for j, (letter, flag) in enumerate(CAPS):
            on = x["capabilities"][flag]
            g.append(f'<text x="{cx + 9 + j * 13}" y="{cy + CELL - 9}" class="mono" font-size="9" '
                     f'font-weight="{700 if on else 400}" fill="{t["accent"] if on else t["faint"]}">{letter}</text>')
        g.append("</g>")
        marks.append("".join(g))
    b += cells
    b.append(f'<image x="{GX}" y="{GY}" width="{8 * CELL + 7 * GAP}" height="{8 * CELL + 7 * GAP}" '
             f'href="{png_uri(dct_atlas(t))}"/>')
    b += marks

    # legend: reading order, statuses, capability letters
    ly = GY + 8 * CELL + 7 * GAP + 40
    mini, ms = 11, GX
    b.append(f'<text x="{ms}" y="{ly}" class="mono" font-size="9" letter-spacing="1.6" fill="{t["muted"]}">'
             f"READING ORDER</text>")
    for r in range(8):
        for c in range(8):
            b.append(f'<rect x="{ms + c * mini}" y="{ly + 10 + r * mini}" width="{mini - 1}" height="{mini - 1}" '
                     f'fill="{t["panel"]}" stroke="{t["line"]}" stroke-width=".5"/>')
    pts = " ".join(f"{ms + c * mini + (mini - 1) / 2:.1f},{ly + 10 + r * mini + (mini - 1) / 2:.1f}" for r, c in order)
    b.append(f'<polyline points="{pts}" fill="none" stroke="{t["accent"]}" stroke-width="1.2" stroke-linejoin="round"/>')
    b.append(f'<circle cx="{ms + (mini - 1) / 2}" cy="{ly + 10 + (mini - 1) / 2}" r="2.6" fill="{t["accent"]}"/>')

    kx = ms + 8 * mini + 44
    keys = [
        ("READY", counts["READY"], "runs locally, now", "ready"),
        ("UNAVAILABLE", counts["UNAVAILABLE"], "needs a trained model that is not bundled — never faked",
         "unavailable"),
        ("NOT IMPLEMENTED", counts["NOT_IMPLEMENTED"], "detector evasion — refused by design", "refused"),
    ]
    for i, (label, n, why, kind) in enumerate(keys):
        y = ly + 4 + i * 26
        if kind == "ready":
            sw = (f'<rect x="{kx}" y="{y - 11}" width="16" height="16" fill="{t["panel"]}" stroke="{t["line"]}"/>'
                  f'<path d="M{kx} {y - 10}h16" stroke="{t["accent"]}" stroke-width="2"/>')
            ink = t["text"]
        elif kind == "unavailable":
            sw = (f'<rect x="{kx}" y="{y - 11}" width="16" height="16" fill="url(#hatch)" stroke="{t["muted"]}" '
                  f'stroke-dasharray="3 3"/>')
            ink = t["muted"]
        else:
            sw = (f'<rect x="{kx}" y="{y - 11}" width="16" height="16" fill="{t["bad"]}" fill-opacity=".10" '
                  f'stroke="{t["bad"]}"/><path d="M{kx + 16} {y - 11}l-16 16" stroke="{t["bad"]}" stroke-opacity=".55"/>')
            ink = t["bad"]
        b.append(sw + f'<text x="{kx + 28}" y="{y + 1}" class="mono" font-size="11.5" font-weight="700" '
                      f'fill="{ink}">{label} {n:>2}</text>'
                      f'<text x="{kx + 28 + mono_width(label + " 00", 11.5) + 12:.0f}" y="{y + 1}" class="sans" '
                      f'font-size="12" fill="{t["muted"]}">{esc(why)}</text>')
    cy = ly + 4 + 3 * 26 + 6
    caps = " · ".join(f"{letter} {flag[4:].lower()}" for letter, flag in CAPS)
    b.append(f'<text x="{kx}" y="{cy}" class="mono" font-size="11" fill="{t["accent"]}">{esc(caps)}</text>')
    if separators == {"CONTROLLED SURROGATE STUDY"}:
        b.append(f'<text x="{kx}" y="{cy + 18}" class="sans" font-size="12" fill="{t["muted"]}">'
                 f"S appears only on controlled-surrogate studies, where the embedded signal is known in advance."
                 f"</text>")
    return document(w, h, t, f"Method registry: {len(methods)} methods",
                    f"The {len(methods)} research methods of SynthProvenance {matrix['software_version']} laid out as an "
                    f"8 by 8 DCT block in JPEG zig-zag order: {counts['READY']} ready, {counts['UNAVAILABLE']} "
                    f"unavailable because their trained models are not bundled, {counts['NOT_IMPLEMENTED']} not implemented "
                    f"by design (detector evasion). Each cell shows the DCT basis function of its coefficient.",
                    "\n".join(b), MOTION % "".join(css))


# --------------------------------------------------------------------------------------------- screenshots
def _expert_shots(out: Path, image: str | None) -> None:
    """Runs inside a child process: drive the real Expert window, capture views, exit."""
    import os

    os.environ["SYNTHPROVENANCE_HOME"] = tempfile.mkdtemp(prefix="sp_readme_shots_")
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from app.ui import theme
    from app.ui.controller import AppController
    from app.ui.main_window import MainWindow
    from app.utils.config import Settings

    app = QApplication(sys.argv[:1])
    settings = Settings()
    settings.data["workspace"] = str(Path(os.environ["SYNTHPROVENANCE_HOME"]) / "workspace")
    theme.apply(app, "Dark Laboratory")
    ctl = AppController(settings)
    win = MainWindow(ctl, quiet=True)
    win.resize(1480, 940)
    win.show()
    state = {"phase": "open"}

    def view(name):
        win.go(name)
        app.processEvents()
        win.views[name]._do_refresh()
        app.processEvents()
        return win.views[name]

    def capture():
        lab = view("Fingerprint Research Lab")
        if image:
            lab.tabs.setCurrentIndex(1)  # Separation & Reconstruction
            app.processEvents()
            page = lab.tabs.currentWidget()
            kv = lab.sep_kv
            last = kv.rowCount() - 1
            bottom = kv.mapTo(page, kv.viewport().pos()).y() + kv.rowViewportPosition(last) + kv.rowHeight(last) + 6
            page.grab().copy(0, 0, page.width(), bottom).save(str(out / "expert-separation.png"))
        else:
            win.grab().save(str(out / "expert-fingerprint-lab.png"))
            view("C2PA Provenance")
            win.grab().save(str(out / "expert-c2pa.png"))
        QTimer.singleShot(200, app.quit)

    def on_source():
        if state["phase"] == "open":
            state["phase"] = "start"
            ctl.start_experiment()

    def on_experiment():
        if state["phase"] == "start" and ctl.experiment is not None:
            state["phase"] = "run"
            lab = view("Fingerprint Research Lab")
            # exactly what RUN SEPARATION STUDY does, so the form on screen matches the numbers beneath it
            ctl.run_fingerprint_method(lab.sep_method.currentData(), surrogate=lab._surrogate_cfg())

    def on_fingerprint():
        if state["phase"] == "run" and ctl.last_fp_run is not None:
            state["phase"] = "capture"
            QTimer.singleShot(300, capture)

    ctl.sourceChanged.connect(on_source)
    ctl.experimentChanged.connect(on_experiment)
    ctl.fingerprintChanged.connect(on_fingerprint)
    QTimer.singleShot(300, (lambda: ctl.open_image(image)) if image else ctl.open_demo_fixture)
    QTimer.singleShot(120_000, app.quit)
    app.exec()
    ctl.pool.waitForDone(10000)


def screenshots() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        easy = Path(tmp) / "easy"
        subprocess.run([sys.executable, str(ROOT / "app" / "main.py"), "--smoke-easy", "--smoke-shots", str(easy),
                        "--smoke-output", str(Path(tmp) / "easy.json")], cwd=ROOT, check=True, timeout=600)
        for src, dst in (("01_pilih.png", "easy-pilih.png"), ("03_output.png", "easy-output.png")):
            shutil.copyfile(easy / src, OUT / dst)
    for image in (None, str(TEST_IMAGE)):
        args = [sys.executable, str(Path(__file__).resolve()), "--expert-shots", str(OUT)]
        subprocess.run(args + (["--image", image] if image else []), cwd=ROOT, check=True, timeout=600)
    for png in OUT.glob("*.png"):
        with Image.open(png) as im:
            im.load()
            im.convert("RGB").save(png, "PNG", optimize=True)


# --------------------------------------------------------------------------------------------- main
def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--screenshots", action="store_true", help="also re-capture the GUI screenshots from source")
    p.add_argument("--expert-shots", help=argparse.SUPPRESS)
    p.add_argument("--image", help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.expert_shots:
        _expert_shots(Path(args.expert_shots), args.image)
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    m = measure_fixture()
    matrix = json.loads((ROOT / "data" / "fingerprint_execution_matrix.json").read_text(encoding="utf-8"))
    written = []
    for name, t in THEMES.items():
        for fig, render in (("hero", lambda: hero(t, m)), ("anatomy", lambda: anatomy(t, m)),
                            ("registry", lambda: registry(t, matrix))):
            path = OUT / f"{fig}-{name}.svg"
            path.write_text(render(), encoding="utf-8")
            written.append(path)
    if args.screenshots:
        screenshots()
    print("Wrote " + ", ".join(f"{p.name} ({p.stat().st_size // 1024} KiB)" for p in written))
    return 0


if __name__ == "__main__":
    sys.exit(main())
