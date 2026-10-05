"""Metadata engine: one entry point that turns untrusted bytes into a full,
evidence-only analysis record.

Nothing here is inferred or fabricated. Every field shown by the Forensic
Inspector is traceable to a byte range, a decoder field, or an explicitly
labelled external tool output.
"""
from __future__ import annotations

import json
import struct
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from app.analyzers.c2pa_analyzer import analyze_c2pa
from app.analyzers.compression_analyzer import analyze_compression
from app.analyzers.exif_analyzer import analyze_exif, orientation_of
from app.analyzers.iptc_analyzer import PS_HEADER, analyze_iptc, parse_iim
from app.analyzers.jpeg_analyzer import analyze_jpeg_markers
from app.analyzers.png_analyzer import analyze_png
from app.analyzers.xmp_analyzer import analyze_xmp
from app.core.containers import XMP_SIG, ContainerError, Structure, parse_container, png_text_chunk
from app.core.hashing import file_hashes
from app.core.image_loader import (
    MIME,
    ImageLoadError,
    aspect_ratio,
    bit_depth_of,
    compute_pixel_hash,
    frame_count,
    open_image_bytes,
)
from app.models.image_info import GROUP_ORDER, ImageInfo, ItemState, MetadataField, MetadataGroup
from app.models.provenance import AISignal, C2PAReport
from app.utils.serialization import jsonable
from app.utils.validation import sniff_format

MAX_RAW_PROFILE = 16 * 1024 * 1024

ORIENTATION_TEXT = {
    1: "1 (normal)", 2: "2 (mirrored horizontal)", 3: "3 (rotated 180)", 4: "4 (mirrored vertical)",
    5: "5 (mirrored horizontal, rotated 270 CW)", 6: "6 (rotated 90 CW)", 7: "7 (mirrored horizontal, rotated 90 CW)",
    8: "8 (rotated 270 CW)",
}


@dataclass
class Analysis:
    info: ImageInfo
    hashes: dict
    groups: dict[str, MetadataGroup]
    structure: Structure
    compression: dict
    c2pa: C2PAReport
    c2pa_raw: dict = field(default_factory=dict)
    png_texts: list[tuple[str, str, str]] = field(default_factory=list)
    signal: AISignal | None = None
    external: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    icc_info: dict = field(default_factory=dict)
    raw_blocks: dict = field(default_factory=dict)
    duration_ms: float = 0.0
    image: Image.Image | None = None
    data: bytes = b""

    @property
    def format(self) -> str:
        return self.info.format

    def to_dict(self) -> dict:
        return {
            "image": self.info.to_dict(),
            "hashes": dict(self.hashes),
            "groups": {name: _group_dict(g) for name, g in self.groups.items()},
            "structure": self.structure.to_dict(),
            "compression": jsonable(self.compression),
            "c2pa": self.c2pa.to_dict(),
            "signal": self.signal.to_dict() if self.signal else None,
            "external": jsonable(self.external),
            "errors": list(self.errors),
            "icc": jsonable(self.icc_info),
            "xmp_history": xmp_history(self.groups.get("XMP")),
            "duration_ms": self.duration_ms,
        }


def _group_dict(g: MetadataGroup) -> dict:
    return {
        "name": g.name,
        "state": g.state.value,
        "byte_size": g.byte_size,
        "location": g.location,
        "notes": list(g.notes),
        "fields": [
            {"group": f.group, "key": f.key, "value": f.value, "namespace": f.namespace, "category": f.category,
             "state": f.state.value}
            for f in g.fields
        ],
    }


# ----------------------------------------------------------------------- ICC

_ICC_CLASS = {"scnr": "input", "mntr": "display", "prtr": "output", "link": "device link", "spac": "color space",
              "abst": "abstract", "nmcl": "named color"}
_ICC_INTENT = {0: "perceptual", 1: "relative colorimetric", 2: "saturation", 3: "absolute colorimetric"}


def _icc_text(icc: bytes, off: int, size: int) -> str:
    if off < 0 or size < 8 or off + size > len(icc):
        return ""
    t = icc[off : off + 4]
    body = icc[off : off + size]
    try:
        if t == b"desc" and size >= 12:
            n = struct.unpack(">I", body[8:12])[0]
            return body[12 : 12 + max(0, n)].split(b"\x00")[0].decode("latin-1", "replace").strip()
        if t == b"text":
            return body[8:].split(b"\x00")[0].decode("latin-1", "replace").strip()
        if t == b"mluc" and size >= 16:
            count, rec = struct.unpack(">II", body[8:16])
            if count and rec >= 12 and 16 + rec <= size:
                ln, so = struct.unpack(">II", body[20:28])
                return body[so : so + ln].decode("utf-16-be", "replace").strip("\x00 ").strip()
    except (struct.error, UnicodeDecodeError):
        return ""
    return ""


def parse_icc(icc: bytes) -> dict:
    """Parse an ICC profile header and descriptive tags (bounds-checked)."""
    if len(icc) < 132:
        raise ValueError(f"ICC profile too short ({len(icc)} bytes)")
    declared = struct.unpack(">I", icc[:4])[0]
    info: dict = {
        "declared_size": declared,
        "actual_size": len(icc),
        "cmm": icc[4:8].decode("latin-1").strip("\x00 "),
        "version": f"{icc[8]}.{icc[9] >> 4}.{icc[9] & 0x0F}",
        "device_class": _ICC_CLASS.get(icc[12:16].decode("latin-1"), icc[12:16].decode("latin-1")),
        "color_space": icc[16:20].decode("latin-1").strip(),
        "pcs": icc[20:24].decode("latin-1").strip(),
        "signature_ok": icc[36:40] == b"acsp",
        "platform": icc[40:44].decode("latin-1").strip("\x00 "),
        "manufacturer": icc[48:52].decode("latin-1").strip("\x00 "),
        "model": icc[52:56].decode("latin-1").strip("\x00 ") if icc[52:56] != b"\x00\x00\x00\x00" else "",
        "rendering_intent": _ICC_INTENT.get(struct.unpack(">I", icc[64:68])[0], "unknown"),
        "creator": icc[80:84].decode("latin-1").strip("\x00 "),
        "profile_id": icc[84:100].hex() if any(icc[84:100]) else "",
    }
    y, mo, d, h, mi, s = struct.unpack(">6H", icc[24:36])
    info["created"] = f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}" if y else ""
    count = struct.unpack(">I", icc[128:132])[0]
    tags = {}
    for k in range(min(count, 200)):
        base = 132 + 12 * k
        if base + 12 > len(icc):
            break
        sig, off, size = struct.unpack(">4sII", icc[base : base + 12])
        tags[sig.decode("latin-1")] = (off, size)
    info["tag_count"] = count
    for sig, key in (("desc", "description"), ("cprt", "copyright"), ("dmnd", "device_manufacturer_text"),
                     ("dmdd", "device_model_text")):
        if sig in tags:
            text = _icc_text(icc, *tags[sig])
            if text:
                info[key] = text
    return info


def analyze_icc(icc: bytes | None, location: str) -> tuple[MetadataGroup, dict]:
    if not icc:
        return MetadataGroup("ICC", ItemState.ABSENT), {}
    group = MetadataGroup("ICC", ItemState.PRESENT, byte_size=len(icc), location=location)
    try:
        info = parse_icc(icc)
    except (ValueError, struct.error) as exc:
        group.state = ItemState.INVALID
        group.notes.append(f"ICC profile could not be parsed: {exc}")
        return group, {}
    order = ["description", "version", "device_class", "color_space", "pcs", "rendering_intent", "created", "cmm",
             "platform", "manufacturer", "model", "creator", "copyright", "profile_id", "declared_size"]
    for key in order:
        val = info.get(key)
        if val not in (None, ""):
            group.fields.append(MetadataField("ICC", key, str(val), "header" if key != "description" else "tag",
                                              "structure"))
    if not info["signature_ok"]:
        group.state = ItemState.INVALID
        group.notes.append("Missing 'acsp' profile signature.")
    if info["declared_size"] != info["actual_size"]:
        group.notes.append(f"Declared size {info['declared_size']} differs from actual {info['actual_size']} bytes.")
    group.notes.append("ICC profiles are colour-rendering data; the sanitizer always preserves them.")
    return group, info


# ------------------------------------------------------------- raw profiles

def decode_raw_profile(text: str) -> bytes | None:
    """Decode an ImageMagick 'Raw profile type X' PNG text payload (hex)."""
    lines = text.strip().splitlines()
    if len(lines) < 3:
        return None
    try:
        length = int(lines[1].strip())
    except ValueError:
        return None
    if length <= 0 or length > MAX_RAW_PROFILE:
        return None
    hexdata = "".join(line.strip() for line in lines[2:])
    try:
        raw = bytes.fromhex(hexdata[: length * 2])
    except ValueError:
        return None
    return raw if len(raw) == length else None


def encode_raw_profile(kind: str, raw: bytes) -> str:
    hexdata = raw.hex()
    body = "\n".join(hexdata[i : i + 72] for i in range(0, len(hexdata), 72))
    return f"\n{kind}\n{len(raw):8d}\n{body}\n"


# ------------------------------------------------------------ extraction

def _strip_exif_prefix(raw: bytes) -> bytes:
    return raw[6:] if raw.startswith(b"Exif\x00\x00") else raw


def _jpeg_blocks(data: bytes, st: Structure) -> dict:
    out: dict = {"exif": None, "exif_loc": "", "xmp": None, "xmp_loc": "", "irb": None, "irb_loc": "", "icc": None,
                 "icc_loc": "", "notes": []}
    exif = st.find("EXIF")
    if exif:
        out["exif"] = exif[0].payload(data)[6:]
        out["exif_loc"] = f"JPEG APP1 @ {exif[0].offset}"
        if len(exif) > 1:
            out["notes"].append(f"{len(exif)} EXIF APP1 segments; the first is authoritative.")
    xmp = st.find("XMP")
    if xmp:
        out["xmp"] = xmp[0].payload(data)[len(XMP_SIG):]
        out["xmp_loc"] = f"JPEG APP1 @ {xmp[0].offset}"
    ext = st.find("XMP_EXT")
    if ext:
        out["notes"].append(f"Extended XMP present in {len(ext)} APP1 segment(s) (not merged into the main packet view).")
    irb = st.find("PHOTOSHOP_IRB")
    if irb:
        out["irb"] = b"".join(s.payload(data)[len(PS_HEADER):] for s in irb)
        out["irb_loc"] = f"JPEG APP13 x{len(irb)} @ {irb[0].offset}"
    icc = st.find("ICC")
    if icc:
        parts = []
        for s in icc:
            p = s.payload(data)
            if len(p) >= 14:
                parts.append((p[12], p[14:]))
        parts.sort(key=lambda t: t[0])
        out["icc"] = b"".join(p for _n, p in parts)
        out["icc_loc"] = f"JPEG APP2 ICC_PROFILE x{len(icc)}"
    return out


def _png_blocks(data: bytes, st: Structure) -> dict:
    out: dict = {"exif": None, "exif_loc": "", "xmp": None, "xmp_loc": "", "irb": None, "irb_loc": "", "icc": None,
                 "icc_loc": "", "notes": [], "iim": None}
    for seg in st.segments:
        if seg.name == "eXIf" and out["exif"] is None:
            out["exif"] = _strip_exif_prefix(seg.payload(data))
            out["exif_loc"] = f"PNG eXIf @ {seg.offset}"
        elif seg.ident == "XMP" and out["xmp"] is None:
            _k, text, _n = png_text_chunk(data, seg)
            out["xmp"] = text.encode("utf-8")
            out["xmp_loc"] = f"PNG iTXt XML:com.adobe.xmp @ {seg.offset}"
        elif seg.ident == "EXIF_TEXT" and out["exif"] is None:
            _k, text, _n = png_text_chunk(data, seg)
            raw = decode_raw_profile(text)
            if raw is not None:
                out["exif"] = _strip_exif_prefix(raw)
                out["exif_loc"] = f"PNG {seg.name} 'Raw profile type exif' @ {seg.offset} (legacy)"
        elif seg.ident == "IPTC_TEXT":
            _k, text, _n = png_text_chunk(data, seg)
            raw = decode_raw_profile(text)
            if raw is not None:
                if raw.startswith(b"8BIM"):
                    out["irb"] = raw
                else:
                    out["iim"] = raw
                out["irb_loc"] = f"PNG {seg.name} 'Raw profile type iptc' @ {seg.offset} (legacy)"
        elif seg.name == "iCCP" and out["icc"] is None:
            p = seg.payload(data)
            name, _, rest = p.partition(b"\x00")
            try:
                d = zlib.decompressobj()
                icc = d.decompress(rest[1:], MAX_RAW_PROFILE)
                if d.unconsumed_tail:
                    raise ValueError("ICC profile exceeds safety limit")
                out["icc"] = icc
                out["icc_loc"] = f"PNG iCCP '{name.decode('latin-1', 'replace')}' @ {seg.offset}"
            except (zlib.error, ValueError) as exc:
                out["notes"].append(f"iCCP chunk could not be inflated: {exc}")
                out["icc"] = b"\x00"  # forces INVALID state downstream
    return out


def _webp_blocks(data: bytes, st: Structure) -> dict:
    out: dict = {"exif": None, "exif_loc": "", "xmp": None, "xmp_loc": "", "irb": None, "irb_loc": "", "icc": None,
                 "icc_loc": "", "notes": []}
    for seg in st.segments:
        if seg.ident == "EXIF" and out["exif"] is None:
            out["exif"] = _strip_exif_prefix(seg.payload(data))
            out["exif_loc"] = f"WebP EXIF chunk @ {seg.offset}"
        elif seg.ident == "XMP" and out["xmp"] is None:
            out["xmp"] = seg.payload(data)
            out["xmp_loc"] = f"WebP 'XMP ' chunk @ {seg.offset}"
        elif seg.ident == "ICC" and out["icc"] is None:
            out["icc"] = seg.payload(data)
            out["icc_loc"] = f"WebP ICCP chunk @ {seg.offset}"
    return out


def _pillow_blocks(img: Image.Image, fmt: str) -> dict:
    out: dict = {"exif": None, "exif_loc": "", "xmp": None, "xmp_loc": "", "irb": None, "irb_loc": "", "icc": None,
                 "icc_loc": "", "notes": [], "iim": None}
    raw_exif = img.info.get("exif")
    if isinstance(raw_exif, bytes) and raw_exif:
        out["exif"] = _strip_exif_prefix(raw_exif)
        out["exif_loc"] = f"{fmt} (decoder-reported)"
    elif fmt == "TIFF":
        out["notes"].append("TIFF IFD0 tags are image-structure tags; EXIF sub-IFDs read via decoder only.")
    xmp = img.info.get("xmp") or (img.tag_v2.get(700) if hasattr(img, "tag_v2") else None)
    if isinstance(xmp, (bytes, str)) and xmp:
        out["xmp"] = xmp.encode("utf-8") if isinstance(xmp, str) else bytes(xmp)
        out["xmp_loc"] = f"{fmt} (decoder-reported)"
    if hasattr(img, "tag_v2"):
        iptc = img.tag_v2.get(33723)
        if isinstance(iptc, (bytes, tuple)) and iptc:
            out["iim"] = bytes(iptc) if isinstance(iptc, bytes) else b"".join(bytes([v]) if isinstance(v, int) else bytes(v) for v in iptc)
            out["irb_loc"] = "TIFF tag 33723 (IPTC-NAA)"
    icc = img.info.get("icc_profile")
    if isinstance(icc, bytes) and icc:
        out["icc"] = icc
        out["icc_loc"] = f"{fmt} (decoder-reported)"
    return out


def _iim_group(iim: bytes, location: str) -> MetadataGroup:
    """Analyse a bare IIM stream by wrapping it in a synthetic IRB envelope."""
    from app.analyzers.iptc_analyzer import build_irb

    try:
        parse_iim(iim)
    except ValueError as exc:
        return MetadataGroup("IPTC", ItemState.INVALID, notes=[f"IPTC-IIM stream invalid: {exc}"], location=location)
    return analyze_iptc(build_irb([(0x0404, b"", iim)]), location)


def _webp_group(data: bytes, st: Structure) -> MetadataGroup:
    g = MetadataGroup("WEBP CHUNKS", ItemState.PRESENT, location="RIFF chunk stream")
    seen: dict[str, int] = {}
    for seg in st.segments:
        name = seg.name.strip()
        seen[name] = seen.get(name, 0) + 1
        key = name if seen[name] == 1 else f"{name} #{seen[name]}"
        cat = {"VP8": "structure", "VP8L": "structure", "VP8X": "structure", "ALPH": "structure", "ANIM": "structure",
               "ANMF": "structure", "ICCP": "structure", "EXIF": "container", "XMP": "container",
               "C2PA": "provenance"}.get(name, "application")
        g.fields.append(MetadataField("WEBP CHUNKS", key, f"{seg.payload_length:,} bytes", "chunk", cat))
    if st.errors:
        g.notes.extend(st.errors)
    return g


def _c2pa_group(rep: C2PAReport) -> MetadataGroup:
    state = ItemState(rep.state) if rep.state in ItemState._value2member_map_ else ItemState.UNKNOWN
    g = MetadataGroup("C2PA / JUMBF", state, byte_size=rep.store_bytes, location=rep.location)
    if not rep.present:
        g.notes.append(rep.summary)
        return g
    g.fields.append(MetadataField("C2PA / JUMBF", "manifest_store", f"{rep.store_bytes:,} bytes, {len(rep.manifests)} manifest(s)",
                                  "store", "provenance"))
    act = rep.active
    if act is not None:
        g.fields.append(MetadataField("C2PA / JUMBF", "active_manifest", act.label, "store", "provenance"))
        if act.claim_generator:
            g.fields.append(MetadataField("C2PA / JUMBF", "claim_generator", act.claim_generator, "claim", "software"))
    g.fields.append(MetadataField("C2PA / JUMBF", "hard_binding", rep.hard_binding, "binding", "provenance"))
    g.fields.append(MetadataField("C2PA / JUMBF", "validity", rep.validity, "validation", "provenance"))
    g.notes.append(rep.summary)
    g.notes.extend(rep.errors[:10])
    return g


SOFTWARE_KEYS = {
    ("EXIF", "Software"), ("EXIF", "ProcessingSoftware"), ("EXIF", "HostComputer"), ("XMP", "xmp:CreatorTool"),
    ("XMP", "tiff:Software"), ("IPTC", "OriginatingProgram"), ("IPTC", "ProgramVersion"),
}


def _software_group(groups: dict[str, MetadataGroup], rep: C2PAReport) -> MetadataGroup:
    g = MetadataGroup("SOFTWARE", ItemState.ABSENT, location="aggregated from other groups")
    for name in ("EXIF", "XMP", "IPTC", "PNG CHUNKS", "JPEG APP MARKERS"):
        src = groups.get(name)
        if src is None:
            continue
        for f in src.fields:
            is_sw = (name, f.key) in SOFTWARE_KEYS or (f.category == "software" and name in ("PNG CHUNKS", "JPEG APP MARKERS"))
            if name == "XMP" and f.key.endswith("stEvt:softwareAgent"):
                is_sw = True
            if is_sw:
                g.fields.append(MetadataField("SOFTWARE", f"{name}: {f.key}", f.value, name, "software"))
    for m in rep.manifests:
        if m.claim_generator:
            g.fields.append(MetadataField("SOFTWARE", f"C2PA claim_generator [{m.label[-12:]}]", m.claim_generator,
                                          "C2PA / JUMBF", "software"))
        for a in m.actions:
            if a.software_agent:
                g.fields.append(MetadataField("SOFTWARE", f"C2PA {a.action} softwareAgent", a.software_agent,
                                              "C2PA / JUMBF", "software"))
    if g.fields:
        g.state = ItemState.PRESENT
    g.notes.append("Derived view: software/tool identifiers reported by the groups above. Not an independent container.")
    return g


def _color_space(img: Image.Image, icc_info: dict, groups: dict, st: Structure) -> str:
    if icc_info.get("description"):
        return f"{icc_info['description']} (ICC {icc_info.get('color_space', '')})"
    if icc_info:
        return f"ICC {icc_info.get('color_space', 'profile')}"
    if st.container == "PNG" and st.find("sRGB"):
        return "sRGB (PNG sRGB chunk)"
    exif = groups.get("EXIF")
    if exif:
        for f in exif.fields:
            if f.key == "ColorSpace":
                return {"1": "sRGB (EXIF ColorSpace=1)", "65535": "Uncalibrated (EXIF ColorSpace=65535)"}.get(
                    f.value.split()[0], f"EXIF ColorSpace={f.value}")
    model = {"L": "Grayscale", "LA": "Grayscale + alpha", "RGB": "RGB", "RGBA": "RGB + alpha", "P": "Indexed RGB",
             "CMYK": "CMYK", "YCbCr": "YCbCr", "1": "Bilevel", "I;16": "Grayscale 16-bit", "I": "Grayscale 32-bit"}.get(
        img.mode, img.mode)
    return f"{model}, unspecified profile (no ICC or colour-space tag)"


def xmp_history(group: MetadataGroup | None) -> list[dict]:
    if group is None:
        return []
    events: dict[str, dict] = {}
    for f in group.fields:
        if not f.key.startswith("xmpMM:History["):
            continue
        idx = f.key.split("[", 1)[1].split("]", 1)[0]
        leaf = f.key.rsplit("/", 1)[-1].split(":")[-1]
        events.setdefault(idx, {})[leaf] = f.value
    return [events[k] for k in sorted(events, key=lambda x: int(x) if x.isdigit() else 0)]


# ---------------------------------------------------------------- entry point

def analyze_bytes(data: bytes, path: str | Path = "", filename: str = "", exiftool_path: str | None = None,
                  image: Image.Image | None = None) -> Analysis:
    """Analyse untrusted image bytes. Raises ImageLoadError if pixels cannot be decoded."""
    t0 = time.perf_counter()
    fmt = sniff_format(data[:16])
    if fmt is None:
        raise ImageLoadError("Unrecognised image container.")
    img = image if image is not None else open_image_bytes(data)
    errors: list[str] = []
    try:
        st = parse_container(data, fmt)
    except ContainerError as exc:
        st = Structure(fmt, errors=[str(exc)])
        errors.append(f"Container parse failed: {exc}")
    errors.extend(st.errors)

    if fmt == "JPEG" and st.segments:
        blocks = _jpeg_blocks(data, st)
    elif fmt == "PNG" and st.segments:
        blocks = _png_blocks(data, st)
    elif fmt == "WEBP" and st.segments:
        blocks = _webp_blocks(data, st)
    else:
        blocks = _pillow_blocks(img, fmt)

    groups: dict[str, MetadataGroup] = {}
    groups["EXIF"] = analyze_exif(blocks["exif"], blocks["exif_loc"])
    groups["XMP"] = analyze_xmp(blocks["xmp"], blocks["xmp_loc"])
    if blocks.get("irb"):
        groups["IPTC"] = analyze_iptc(blocks["irb"], blocks["irb_loc"])
    elif blocks.get("iim"):
        groups["IPTC"] = _iim_group(blocks["iim"], blocks["irb_loc"])
    else:
        groups["IPTC"] = MetadataGroup("IPTC", ItemState.ABSENT)
    png_texts: list = []
    if fmt == "PNG" and st.segments:
        groups["PNG CHUNKS"], png_texts = analyze_png(data, st)
    if fmt == "JPEG" and st.segments:
        groups["JPEG APP MARKERS"] = analyze_jpeg_markers(data, st)
    if fmt == "WEBP" and st.segments:
        from app.analyzers.webp_analyzer import analyze_webp_chunks

        groups["WEBP CHUNKS"] = analyze_webp_chunks(data, st)
    if fmt == "TIFF":
        from app.analyzers.tiff_analyzer import analyze_tiff_tags

        groups["TIFF TAGS"] = analyze_tiff_tags(img)
    icc_group, icc_info = analyze_icc(blocks["icc"], blocks["icc_loc"])
    groups["ICC"] = icc_group
    for note in blocks["notes"]:
        target = "XMP" if "XMP" in note else ("ICC" if "iCCP" in note else "EXIF")
        groups[target].notes.append(note)

    try:
        c2pa, c2pa_raw = analyze_c2pa(data, fmt, st)
    except Exception as exc:  # noqa: BLE001 - hostile manifests must never break analysis
        c2pa, c2pa_raw = C2PAReport(True, ItemState.INVALID.value, f"C2PA analysis failed: {type(exc).__name__}: {exc}"), {}
        errors.append(c2pa.summary)
    groups["SOFTWARE"] = _software_group(groups, c2pa)
    groups["C2PA / JUMBF"] = _c2pa_group(c2pa)
    groups = {k: groups[k] for k in GROUP_ORDER if k in groups}

    try:
        compression = analyze_compression(fmt, data, st, img)
    except Exception as exc:  # noqa: BLE001
        compression = {"format": fmt, "summary": "UNKNOWN", "error": str(exc)}

    w, h = img.size
    orient = orientation_of(blocks["exif"])
    hashes = file_hashes(data)
    try:
        hashes["pixel_sha256"] = compute_pixel_hash(img)
    except MemoryError:
        hashes["pixel_sha256"] = ""
        errors.append("Pixel hash skipped: insufficient memory.")
    frames = frame_count(img)
    p = Path(path) if path else None
    info = ImageInfo(
        path=str(p) if p else "",
        filename=filename or (p.name if p else "(memory)"),
        file_size=len(data),
        format=fmt,
        mime=MIME.get(fmt, "application/octet-stream"),
        width=w,
        height=h,
        pixel_count=w * h,
        aspect_ratio=aspect_ratio(w, h),
        mode=img.mode,
        channels=len(img.getbands()),
        bit_depth=bit_depth_of(img.mode),
        color_space=_color_space(img, icc_info, groups, st),
        icc_profile=(icc_info.get("description") or f"present, {len(blocks['icc'])} bytes") if blocks["icc"] and icc_info
        else ("INVALID" if blocks["icc"] else "ABSENT"),
        compression=compression.get("summary", "UNKNOWN"),
        frames=frames,
        animated=frames > 1,
        orientation=ORIENTATION_TEXT.get(orient, "ABSENT (no EXIF orientation tag)" if orient is None else str(orient)),
    )
    if frames > 1:
        info.warnings.append(f"Multi-frame image ({frames} frames): only frame 0 is analysed and compared.")
    if st.trailing_bytes:
        info.warnings.append(f"{st.trailing_bytes:,} bytes follow the end-of-image marker.")

    external: dict = {}
    if exiftool_path and p is not None and p.is_file():
        external["exiftool"] = run_exiftool(exiftool_path, p)

    analysis = Analysis(info=info, hashes=hashes, groups=groups, structure=st, compression=compression, c2pa=c2pa,
                        c2pa_raw=c2pa_raw, png_texts=png_texts, external=external, errors=errors,
                        icc_info=icc_info, image=img, data=data,
                        raw_blocks={"exif": blocks["exif"], "xmp": blocks["xmp"],
                                    "icc": blocks["icc"] if icc_info else None, "has_c2pa": c2pa.present})
    from app.core.provenance_engine import compute_signal  # local import avoids a cycle

    analysis.signal = compute_signal(analysis)
    analysis.duration_ms = (time.perf_counter() - t0) * 1000.0
    return analysis


def analyze_file(path: str | Path, exiftool_path: str | None = None) -> Analysis:
    from app.core.image_loader import read_file_bytes
    from app.utils.validation import InputValidationError

    try:
        p, data = read_file_bytes(path)
    except InputValidationError as exc:
        raise ImageLoadError(str(exc)) from exc
    return analyze_bytes(data, p, p.name, exiftool_path=exiftool_path)


def run_exiftool(exiftool_path: str, path: Path) -> dict:
    """Read-only ExifTool extraction (argument list, no shell). Output is external, labelled data."""
    from app.utils.system import ToolError, run_tool

    try:
        res = run_tool([exiftool_path, "-j", "-G1", "-a", "-s", "-n", "-b0", "--", str(path)], timeout=60)
    except ToolError as exc:
        return {"status": "FAILED", "detail": str(exc)}
    try:
        parsed = json.loads(res.stdout.decode("utf-8", "replace") or "[]")
        record = parsed[0] if isinstance(parsed, list) and parsed else {}
    except ValueError:
        return {"status": "FAILED", "detail": f"non-JSON output (exit {res.returncode})"}
    record = {str(k): (str(v)[:512] if not isinstance(v, (int, float)) else v) for k, v in list(record.items())[:2000]}
    return {"status": "OK", "tier": "EXTERNAL TOOL OUTPUT (ExifTool, read-only)", "tags": record}


# ----------------------------------------------------------------- diffing

def _index(fields: list[dict]) -> dict[tuple, list[dict]]:
    idx: dict[tuple, list[dict]] = {}
    for f in fields:
        idx.setdefault((f.get("namespace", ""), f.get("key", "")), []).append(f)
    return idx


def diff_groups(before: dict[str, dict], after: dict[str, dict]) -> tuple[list[dict], dict[str, dict]]:
    """Field- and group-level differences between two analyses (``groups`` dicts).

    Field states: PRESERVED (same value), REMOVED (only before), PRESENT (only after:
    new in output). A changed value is reported as the old value REMOVED plus
    the new value PRESENT.
    """
    diffs: list[dict] = []
    group_states: dict[str, dict] = {}
    names = [n for n in GROUP_ORDER if n in before or n in after]
    for name in names:
        gb, ga = before.get(name), after.get(name)
        sb = gb["state"] if gb else "ABSENT"
        sa = ga["state"] if ga else "ABSENT"
        fb = _index(gb["fields"]) if gb else {}
        fa = _index(ga["fields"]) if ga else {}
        counts = {"PRESERVED": 0, "REMOVED": 0, "PRESENT": 0}
        for key in list(fb) + [k for k in fa if k not in fb]:
            lb, la = fb.get(key, []), fa.get(key, [])
            for i in range(max(len(lb), len(la))):
                vb = lb[i] if i < len(lb) else None
                va = la[i] if i < len(la) else None
                ref = vb or va
                entry = {"group": name, "namespace": key[0], "key": key[1], "category": ref.get("category", "other")}
                if vb and va and vb["value"] == va["value"]:
                    diffs.append({**entry, "state": "PRESERVED", "before": vb["value"], "after": va["value"]})
                    counts["PRESERVED"] += 1
                    continue
                if vb:
                    diffs.append({**entry, "state": "REMOVED", "before": vb["value"], "after": ""})
                    counts["REMOVED"] += 1
                if va:
                    diffs.append({**entry, "state": "PRESENT", "before": "", "after": va["value"],
                                  "note": "value changed" if vb else "new in output"})
                    counts["PRESENT"] += 1
        if sa == "INVALID":
            state = "INVALID"
        elif sb in ("ABSENT",) and sa in ("ABSENT",):
            state = "ABSENT"
        elif sb == "UNKNOWN" or sa == "UNKNOWN":
            state = "UNKNOWN"
        elif sb != "ABSENT" and (sa == "ABSENT" or not ga or (not ga["fields"] and gb and gb["fields"])):
            state = "REMOVED"
        elif sb == "ABSENT" and sa != "ABSENT":
            state = "PRESENT"
        elif counts["REMOVED"] == 0 and counts["PRESENT"] == 0:
            state = "PRESERVED"
        else:
            state = "PRESENT"
        detail = f"{counts['PRESERVED']} preserved, {counts['REMOVED']} removed, {counts['PRESENT']} new/changed"
        if state == "PRESENT" and sb != "ABSENT":
            detail = "MODIFIED: " + detail
        group_states[name] = {"state": state, "before": sb, "after": sa, "detail": detail, **counts}
    return diffs, group_states


def metadata_retained(group_states: dict[str, dict]) -> str:
    """Summarise for the experiment matrix: 'yes' / 'no' / 'unknown' / 'na'."""
    relevant = {k: v for k, v in group_states.items() if k not in ("SOFTWARE",)}
    if not relevant or all(v["before"] == "ABSENT" for v in relevant.values()):
        return "na"
    if any(v["state"] in ("UNKNOWN", "INVALID") for v in relevant.values()):
        return "unknown"
    if all(v["state"] in ("PRESERVED", "ABSENT") for v in relevant.values()):
        return "yes"
    return "no"
