"""Privacy sanitizer.

METADATA-ONLY mode rewrites the container at byte level. The compressed image
stream (JPEG scan data, PNG IDAT, WebP VP8/VP8L/ALPH/ANMF) is copied verbatim,
so decoded pixels cannot change. The transformation service still *verifies*
this by decoding both files and comparing every sample.

Always preserved regardless of options:
* image structure (EXIF Orientation / resolution / colour space tags, JFIF,
  Adobe APP14, ICC profiles, PNG rendering chunks such as gAMA/sRGB/pHYs),
* rights notices (EXIF Copyright, XMP dc:rights / xmpRights, IPTC
  CopyrightNotice / Credit / Source, PNG Copyright/Disclaimer text).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.analyzers.exif_analyzer import edit_exif
from app.analyzers.iptc_analyzer import PS_HEADER, IPTCError, edit_iptc
from app.analyzers.png_analyzer import chunk_category, text_category
from app.analyzers.xmp_analyzer import XMPError, edit_xmp
from app.core.containers import (
    PNG_RENDERING,
    XMP_SIG,
    ContainerError,
    Segment,
    Structure,
    parse_container,
    png_text_chunk,
    rebuild_jpeg,
    rebuild_png,
    rebuild_webp,
)
from app.core.metadata_engine import decode_raw_profile, encode_raw_profile


class SanitizeRefused(RuntimeError):
    """The requested mode cannot guarantee its contract for this input."""


OPTION_LABELS = {
    "gps": "Remove GPS",
    "camera": "Remove camera information",
    "device": "Remove device information",
    "author": "Remove author",
    "timestamps": "Remove timestamps",
    "private_xmp": "Remove private XMP fields",
    "private_iptc": "Remove private IPTC fields",
    "software": "Remove unnecessary software metadata",
    "nonessential": "Remove nonessential application metadata",
}
OPTION_HELP = {
    "gps": "EXIF GPS IFD and XMP exif:GPS* properties.",
    "camera": "Make, model, lens, exposure settings and maker notes.",
    "device": "Body / lens serial numbers, host computer, image unique IDs.",
    "author": "Artist, creator, by-line, caption writer, owner names.",
    "timestamps": "Capture / digitisation / modification dates, PNG tIME.",
    "private_xmp": "XMP location text, instructions, document IDs and edit history (xmpMM), prompt information, "
                   "and equivalent EXIF free-text fields (UserComment, ImageDescription, XP*).",
    "private_iptc": "IPTC city / region / country, contact, special instructions, transmission reference.",
    "software": "Software / creator-tool identifiers and JPEG comments.",
    "nonessential": "Vendor and application data: private PNG chunks and text, generator-parameter records, MPF, "
                    "extended XMP, other Photoshop resources, trailing data, AND provenance containers "
                    "(C2PA/JUMBF manifest stores, XMP provenance declarations). Removing these removes the "
                    "file's Content Credentials.",
}


@dataclass
class SanitizeOptions:
    gps: bool = True
    camera: bool = False
    device: bool = True
    author: bool = False
    timestamps: bool = False
    private_xmp: bool = False
    private_iptc: bool = False
    software: bool = False
    nonessential: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "SanitizeOptions":
        d = d or {}
        return cls(**{k: bool(d[k]) for k in cls.__dataclass_fields__ if k in d})

    def exif_categories(self) -> set[str]:
        cats = set()
        for opt, cat in (("gps", "gps"), ("camera", "camera"), ("device", "device"), ("author", "author"),
                         ("timestamps", "timestamp"), ("software", "software"), ("private_xmp", "private")):
            if getattr(self, opt):
                cats.add(cat)
        if self.nonessential:
            cats.add("application")
        return cats

    def xmp_categories(self) -> set[str]:
        cats = self.exif_categories()
        if self.nonessential:
            cats |= {"application", "provenance"}
        return cats

    def iptc_categories(self) -> set[str]:
        cats = {c for c in self.exif_categories() if c != "private"}
        if self.private_iptc:
            cats.add("private")
        return cats

    def any(self) -> bool:
        return any(asdict(self).values())


PROFILES: dict[str, SanitizeOptions] = {
    "CONSERVATIVE": SanitizeOptions(gps=True, device=True),
    "BALANCED": SanitizeOptions(gps=True, camera=True, device=True, author=True, timestamps=False,
                                private_xmp=True, private_iptc=True, software=False, nonessential=False),
    "MAXIMUM PRIVACY": SanitizeOptions(gps=True, camera=True, device=True, author=True, timestamps=True,
                                       private_xmp=True, private_iptc=True, software=True, nonessential=True),
}
PROFILE_HELP = {
    "CONSERVATIVE": "Location and device identifiers only.",
    "BALANCED": "Personal data (location, device, camera, author, private fields). Keeps timestamps, software and "
                "provenance containers.",
    "MAXIMUM PRIVACY": "Every option, including provenance containers (C2PA / Content Credentials).",
}
SUPPORTED = ("JPEG", "PNG", "WEBP")


@dataclass
class SanitizeResult:
    data: bytes
    format: str
    removed: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    provenance_removed: bool = False


def sanitize(data: bytes, fmt: str, options: SanitizeOptions) -> SanitizeResult:
    if fmt not in SUPPORTED:
        raise SanitizeRefused(
            f"Metadata-only sanitization supports JPEG, PNG and WebP containers. {fmt} would require re-encoding, "
            "which cannot be guaranteed pixel-exact in METADATA-ONLY mode.")
    try:
        st = parse_container(data, fmt)
    except ContainerError as exc:
        raise SanitizeRefused(f"Container cannot be parsed safely: {exc}") from exc
    fatal = [e for e in st.errors if "exceeds" in e or "Invalid" in e or "Truncated" in e or "No SOS" in e]
    if fatal:
        raise SanitizeRefused("Container structure is damaged; a byte-level rewrite could corrupt it: " + "; ".join(fatal[:3]))
    res = SanitizeResult(data=data, format=fmt)
    if fmt == "JPEG":
        res.data = _sanitize_jpeg(data, st, options, res)
    elif fmt == "PNG":
        res.data = _sanitize_png(data, st, options, res)
    else:
        res.data = _sanitize_webp(data, st, options, res)
    if not res.removed:
        res.notes.append("No metadata matched the selected options; output is byte-identical in content.")
    res.actions.insert(0, "METADATA-ONLY container rewrite; compressed image data copied verbatim")
    return res


# ------------------------------------------------------------------- shared

def _edit_exif_block(tiff: bytes, opts: SanitizeOptions, res: SanitizeResult, where: str) -> bytes | None | bool:
    """Returns True (unchanged), None (drop) or new TIFF bytes."""
    cats = opts.exif_categories()
    if not cats:
        return True
    try:
        new, removed, notes = edit_exif(tiff, cats)
    except Exception as exc:  # noqa: BLE001 - malformed EXIF
        if opts.nonessential:
            res.removed.append(f"{where}: EXIF block (unparseable)")
            res.notes.append(f"EXIF could not be parsed ({exc}); removed entirely under nonessential.")
            return None
        res.notes.append(f"EXIF could not be parsed ({exc}); left untouched.")
        return True
    res.notes.extend(notes)
    if not removed:
        return True
    res.removed.extend(f"{where}: {r}" for r in removed)
    return new


def _edit_xmp_block(packet: bytes, opts: SanitizeOptions, res: SanitizeResult, where: str) -> bytes | None | bool:
    cats = opts.xmp_categories()
    if not cats:
        return True
    try:
        new, removed = edit_xmp(packet, cats)
    except XMPError as exc:
        if opts.nonessential:
            res.removed.append(f"{where}: XMP packet (invalid)")
            return None
        res.notes.append(f"XMP invalid ({exc}); left untouched.")
        return True
    if not removed:
        return True
    res.removed.extend(f"{where}: {r}" for r in removed)
    if any(k.startswith(("Iptc4xmpExt:DigitalSourceType", "Iptc4xmpExt:AISystem", "c2pa:")) for k in removed):
        res.provenance_removed = True
    return new


# --------------------------------------------------------------------- JPEG

def _sanitize_jpeg(data: bytes, st: Structure, opts: SanitizeOptions, res: SanitizeResult) -> bytes:
    def decide(seg: Segment):
        ident = seg.ident
        if ident in ("JFIF", "ADOBE", "ICC", "DQT", "DHT", "DRI", "SOF") or not (seg.name.startswith("APP") or seg.name == "COM"):
            return True
        payload = seg.payload(data)
        if ident == "EXIF":
            out = _edit_exif_block(payload[6:], opts, res, "APP1 EXIF")
            if out is True:
                return True
            return False if out is None else b"Exif\x00\x00" + out
        if ident == "XMP":
            out = _edit_xmp_block(payload[len(XMP_SIG):], opts, res, "APP1 XMP")
            if out is True:
                return True
            if out is not None and len(out) + len(XMP_SIG) > 65533:
                res.notes.append("Edited XMP exceeds one APP1 segment; original packet kept.")
                return True
            return False if out is None else XMP_SIG + out
        if ident == "PHOTOSHOP_IRB":
            cats = opts.iptc_categories()
            if not cats and not opts.nonessential:
                return True
            try:
                new, removed = edit_iptc(payload[len(PS_HEADER):], cats, drop_other_resources=opts.nonessential)
            except IPTCError as exc:
                res.notes.append(f"Photoshop IRB invalid ({exc}); " + ("removed." if opts.nonessential else "left untouched."))
                if opts.nonessential:
                    res.removed.append("APP13: Photoshop IRB (invalid)")
                    return False
                return True
            if not removed:
                return True
            res.removed.extend(f"APP13 {r}" for r in removed)
            if new is None:
                return False
            if len(new) + len(PS_HEADER) > 65533:
                res.notes.append("Edited Photoshop IRB exceeds one APP13 segment; original kept.")
                return True
            return PS_HEADER + new
        if ident == "COM":
            if opts.software or opts.nonessential:
                res.removed.append(f"COM comment ({seg.payload_length} bytes)")
                return False
            return True
        if ident == "JUMBF":
            if opts.nonessential:
                res.removed.append(f"APP11 JUMBF/C2PA segment ({seg.payload_length:,} bytes)")
                res.provenance_removed = True
                return False
            return True
        if ident in ("XMP_EXT", "MPF", "DUCKY", "FPXR") or ident.endswith("_OTHER"):
            if opts.nonessential:
                res.removed.append(f"{seg.name} {ident} ({seg.payload_length:,} bytes)")
                return False
            return True
        return True

    drop_trailing = bool(opts.nonessential and st.trailing_bytes)
    if drop_trailing:
        res.removed.append(f"{st.trailing_bytes:,} bytes after EOI (MPF secondary images / appended data)")
    out = rebuild_jpeg(data, st, decide, drop_trailing=drop_trailing)
    res.actions.append(f"JPEG header segments rewritten; scan data copied verbatim ({len(data) - (st.scan_offset or 0):,} bytes)")
    return out


# ---------------------------------------------------------------------- PNG

def _sanitize_png(data: bytes, st: Structure, opts: SanitizeOptions, res: SanitizeResult) -> bytes:
    text_opts = {"author": opts.author, "timestamp": opts.timestamps, "software": opts.software, "device": opts.device,
                 "private": opts.private_xmp, "generator": opts.nonessential, "application": opts.nonessential}

    def decide(seg: Segment):
        name = seg.name
        if name in PNG_RENDERING:
            return True
        if name == "eXIf":
            payload = seg.payload(data)
            prefix = b"Exif\x00\x00" if payload.startswith(b"Exif\x00\x00") else b""
            out = _edit_exif_block(payload[len(prefix):], opts, res, "eXIf")
            if out is True:
                return True
            return False if out is None else prefix + out
        if name in ("tEXt", "zTXt", "iTXt"):
            keyword, text, _note = png_text_chunk(data, seg)
            if seg.ident == "XMP":
                out = _edit_xmp_block(text.encode("utf-8"), opts, res, "iTXt XMP")
                if out is True:
                    return True
                if out is None:
                    return False
                return b"XML:com.adobe.xmp\x00\x00\x00\x00\x00" + out
            if seg.ident == "EXIF_TEXT":
                raw = decode_raw_profile(text)
                if raw is None:
                    if opts.nonessential:
                        res.removed.append(f"{name} '{keyword}' (undecodable legacy EXIF profile)")
                        return False
                    return True
                prefix = b"Exif\x00\x00" if raw.startswith(b"Exif\x00\x00") else b""
                out = _edit_exif_block(raw[len(prefix):], opts, res, f"{name} raw EXIF profile")
                if out is True:
                    return True
                if out is None:
                    return False
                return keyword.encode("latin-1") + b"\x00" + encode_raw_profile("exif", prefix + out).encode("ascii")
            cat = text_category(keyword)
            if seg.ident == "IPTC_TEXT":
                cat = "private" if opts.private_iptc else "rights"
            if cat == "rights":
                return True
            if text_opts.get(cat):
                res.removed.append(f"{name} '{keyword}' ({cat})")
                if cat == "generator":
                    res.provenance_removed = True
                return False
            return True
        if name == "tIME":
            if opts.timestamps:
                res.removed.append("tIME (last-modification time)")
                return False
            return True
        cat = chunk_category(name, seg.ident)
        if cat == "provenance":
            if opts.nonessential:
                res.removed.append(f"{name} C2PA/JUMBF manifest store ({seg.payload_length:,} bytes)")
                res.provenance_removed = True
                return False
            return True
        if cat == "application" and opts.nonessential:
            res.removed.append(f"{name} ancillary chunk ({seg.payload_length:,} bytes)")
            return False
        return True

    drop_trailing = bool(opts.nonessential and st.trailing_bytes)
    if drop_trailing:
        res.removed.append(f"{st.trailing_bytes:,} bytes after IEND")
    out = rebuild_png(data, st, decide, drop_trailing=drop_trailing)
    res.actions.append(f"PNG ancillary chunks rewritten; {st.info.get('idat_chunks', 0)} IDAT chunk(s) copied verbatim")
    return out


# --------------------------------------------------------------------- WebP

def _sanitize_webp(data: bytes, st: Structure, opts: SanitizeOptions, res: SanitizeResult) -> bytes:
    def decide(seg: Segment):
        name = seg.name
        if name == "ICCP":
            return True
        if name == "EXIF":
            payload = seg.payload(data)
            prefix = b"Exif\x00\x00" if payload.startswith(b"Exif\x00\x00") else b""
            out = _edit_exif_block(payload[len(prefix):], opts, res, "EXIF chunk")
            if out is True:
                return True
            return False if out is None else prefix + out
        if name == "XMP ":
            out = _edit_xmp_block(seg.payload(data), opts, res, "XMP chunk")
            if out is True:
                return True
            return False if out is None else out
        if seg.ident == "JUMBF":
            if opts.nonessential:
                res.removed.append(f"C2PA chunk ({seg.payload_length:,} bytes)")
                res.provenance_removed = True
                return False
            return True
        if opts.nonessential:
            res.removed.append(f"unknown chunk {name!r} ({seg.payload_length:,} bytes)")
            return False
        return True

    if st.trailing_bytes and opts.nonessential:
        res.removed.append(f"{st.trailing_bytes:,} bytes after the RIFF container")
    out = rebuild_webp(data, st, decide)
    res.actions.append("WebP RIFF chunks rewritten; VP8/VP8L/ALPH/ANIM/ANMF chunks copied verbatim; VP8X flags updated")
    return out
