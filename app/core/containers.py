"""Byte-level container parsing and rewriting for JPEG, PNG and WebP.

Metadata-only operations rewrite container structure without ever decoding
or re-encoding the compressed image stream. The entropy-coded JPEG scan,
PNG IDAT chunks and WebP VP8/VP8L bitstreams are copied byte-for-byte,
which is what makes pixel-exact sanitisation possible.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from typing import Callable

MAX_SEGMENTS = 20000


class ContainerError(ValueError):
    pass


@dataclass
class Segment:
    name: str
    offset: int
    length: int  # total bytes including header / CRC / padding
    payload_offset: int
    payload_length: int
    ident: str = ""
    marker: int | None = None
    crc_ok: bool | None = None
    note: str = ""

    def payload(self, data: bytes) -> bytes:
        return data[self.payload_offset : self.payload_offset + self.payload_length]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "offset": self.offset,
            "length": self.length,
            "payload_length": self.payload_length,
            "ident": self.ident,
            "crc_ok": self.crc_ok,
            "note": self.note,
        }


@dataclass
class Structure:
    container: str
    segments: list[Segment] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    trailing_bytes: int = 0
    info: dict = field(default_factory=dict)
    # JPEG specific
    scan_offset: int | None = None
    eoi_end: int | None = None

    def find(self, ident: str) -> list[Segment]:
        return [s for s in self.segments if s.ident == ident]

    def to_dict(self) -> dict:
        return {
            "container": self.container,
            "segments": [s.to_dict() for s in self.segments],
            "errors": list(self.errors),
            "trailing_bytes": self.trailing_bytes,
            "info": dict(self.info),
        }


# --------------------------------------------------------------------------- JPEG

_JPEG_NAMES = {
    0xC0: "SOF0", 0xC1: "SOF1", 0xC2: "SOF2", 0xC3: "SOF3", 0xC5: "SOF5", 0xC6: "SOF6", 0xC7: "SOF7",
    0xC9: "SOF9", 0xCA: "SOF10", 0xCB: "SOF11", 0xCD: "SOF13", 0xCE: "SOF14", 0xCF: "SOF15",
    0xC4: "DHT", 0xCC: "DAC", 0xDA: "SOS", 0xDB: "DQT", 0xDC: "DNL", 0xDD: "DRI", 0xDE: "DHP",
    0xDF: "EXP", 0xFE: "COM", 0xD8: "SOI", 0xD9: "EOI",
}
for _i in range(16):
    _JPEG_NAMES[0xE0 + _i] = f"APP{_i}"
SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}

XMP_SIG = b"http://ns.adobe.com/xap/1.0/\x00"
XMP_EXT_SIG = b"http://ns.adobe.com/xmp/extension/\x00"


def jpeg_marker_name(marker: int) -> str:
    return _JPEG_NAMES.get(marker, f"0xFF{marker:02X}")


def identify_jpeg_segment(marker: int, payload: bytes) -> str:
    if marker == 0xE0 and payload[:5] in (b"JFIF\x00", b"JFXX\x00"):
        return "JFIF"
    if marker == 0xE1:
        if payload.startswith(b"Exif\x00\x00") or payload.startswith(b"Exif\x00\xff"):
            return "EXIF"
        if payload.startswith(XMP_SIG):
            return "XMP"
        if payload.startswith(XMP_EXT_SIG):
            return "XMP_EXT"
        return "APP1_OTHER"
    if marker == 0xE2:
        if payload.startswith(b"ICC_PROFILE\x00"):
            return "ICC"
        if payload.startswith(b"MPF\x00"):
            return "MPF"
        if payload.startswith(b"FPXR"):
            return "FPXR"
        return "APP2_OTHER"
    if marker == 0xEB and payload[:2] == b"JP":
        return "JUMBF"
    if marker == 0xED and payload.startswith(b"Photoshop 3.0\x00"):
        return "PHOTOSHOP_IRB"
    if marker == 0xEE and payload.startswith(b"Adobe"):
        return "ADOBE"
    if marker == 0xEC and payload.startswith(b"Ducky"):
        return "DUCKY"
    if marker == 0xFE:
        return "COM"
    if marker == 0xDB:
        return "DQT"
    if marker == 0xC4:
        return "DHT"
    if marker == 0xDD:
        return "DRI"
    if marker in SOF_MARKERS:
        return "SOF"
    if 0xE0 <= marker <= 0xEF:
        return f"APP{marker - 0xE0}_OTHER"
    return jpeg_marker_name(marker)


def parse_jpeg(data: bytes) -> Structure:
    st = Structure("JPEG")
    if not data.startswith(b"\xff\xd8"):
        raise ContainerError("Missing JPEG SOI marker")
    n = len(data)
    i = 2
    count = 0
    while i < n:
        count += 1
        if count > MAX_SEGMENTS:
            st.errors.append("Segment limit exceeded; structure truncated")
            break
        if data[i] != 0xFF:
            st.errors.append(f"Expected marker at offset {i}, found 0x{data[i]:02X}")
            break
        while i < n and data[i] == 0xFF:
            i += 1
        if i >= n:
            break
        marker = data[i]
        start = i - 1
        i += 1
        if marker == 0xD9:
            st.eoi_end = i
            break
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            continue
        if i + 2 > n:
            st.errors.append("Truncated segment length")
            break
        seg_len = struct.unpack(">H", data[i : i + 2])[0]
        if seg_len < 2 or i + seg_len > n:
            st.errors.append(f"Invalid length {seg_len} for {jpeg_marker_name(marker)} at {start}")
            break
        payload_off = i + 2
        payload = data[payload_off : i + seg_len]
        seg = Segment(jpeg_marker_name(marker), start, seg_len + 2, payload_off, seg_len - 2,
                      identify_jpeg_segment(marker, payload), marker)
        if marker == 0xDA:
            st.scan_offset = start
            st.segments.append(seg)
            i = _scan_entropy(data, i + seg_len, st)
            if st.eoi_end is not None:
                break
            continue
        if marker in SOF_MARKERS:
            _parse_sof(payload, marker, st)
        if marker == 0xDD and len(payload) >= 2:
            st.info["restart_interval"] = struct.unpack(">H", payload[:2])[0]
        st.segments.append(seg)
        i += seg_len
    if st.scan_offset is None:
        st.errors.append("No SOS (start of scan) marker found")
    if st.eoi_end is None:
        st.errors.append("No EOI marker found (file may be truncated)")
    else:
        st.trailing_bytes = n - st.eoi_end
    st.info["scans"] = sum(1 for s in st.segments if s.name == "SOS")
    return st


def _scan_entropy(data: bytes, i: int, st: Structure) -> int:
    """Walk entropy-coded data after an SOS header; return index of next marker."""
    n = len(data)
    while True:
        j = data.find(b"\xff", i)
        if j < 0 or j + 1 >= n:
            return n
        nxt = data[j + 1]
        if nxt == 0x00 or 0xD0 <= nxt <= 0xD7 or nxt == 0xFF:
            i = j + 1 if nxt == 0xFF else j + 2
            continue
        return j


def _parse_sof(payload: bytes, marker: int, st: Structure) -> None:
    if len(payload) < 6:
        st.errors.append("Truncated SOF segment")
        return
    precision, height, width, ncomp = struct.unpack(">BHHB", payload[:6])
    comps = []
    for k in range(ncomp):
        base = 6 + 3 * k
        if base + 3 > len(payload):
            break
        cid, sampling, tq = payload[base], payload[base + 1], payload[base + 2]
        comps.append({"id": cid, "h": sampling >> 4, "v": sampling & 0x0F, "tq": tq})
    process = {0xC0: "baseline", 0xC1: "extended sequential", 0xC2: "progressive", 0xC3: "lossless"}.get(
        marker, jpeg_marker_name(marker)
    )
    subsampling = "N/A"
    if len(comps) >= 3:
        h0, v0 = comps[0]["h"], comps[0]["v"]
        h1, v1 = comps[1]["h"], comps[1]["v"]
        ratio = (h0 // max(h1, 1), v0 // max(v1, 1))
        subsampling = {(1, 1): "4:4:4", (2, 1): "4:2:2", (2, 2): "4:2:0", (4, 1): "4:1:1", (1, 2): "4:4:0"}.get(
            ratio, f"{h0}x{v0}/{h1}x{v1}"
        )
    elif len(comps) == 1:
        subsampling = "grayscale"
    st.info["sof"] = {
        "marker": jpeg_marker_name(marker), "process": process, "precision": precision,
        "width": width, "height": height, "components": comps, "subsampling": subsampling,
    }


def rebuild_jpeg(
    data: bytes,
    st: Structure,
    decide: Callable[[Segment], bool | bytes],
    drop_trailing: bool = False,
    extra_after_soi: list[tuple[int, bytes]] | None = None,
) -> bytes:
    """Rebuild a JPEG. ``decide`` returns True (keep), False (drop) or new payload bytes.

    Only header segments before the first SOS are subject to ``decide``; the
    scan data from the first SOS through EOI is copied verbatim.
    """
    if st.scan_offset is None:
        raise ContainerError("Cannot rewrite JPEG without a scan (SOS) segment")
    out = bytearray(b"\xff\xd8")
    for marker, payload in extra_after_soi or []:
        out += _jpeg_segment(marker, payload)
    for seg in st.segments:
        if seg.offset >= st.scan_offset:
            break
        verdict = decide(seg)
        if verdict is True:
            out += data[seg.offset : seg.offset + seg.length]
        elif verdict is False:
            continue
        else:
            out += _jpeg_segment(seg.marker or 0, bytes(verdict))
    end = st.eoi_end if (drop_trailing and st.eoi_end is not None) else len(data)
    out += data[st.scan_offset : end]
    return bytes(out)


def _jpeg_segment(marker: int, payload: bytes) -> bytes:
    if len(payload) > 65533:
        raise ContainerError(f"Segment payload too large for a single JPEG marker ({len(payload)} bytes)")
    return bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload


# --------------------------------------------------------------------------- PNG

PNG_SIG = b"\x89PNG\r\n\x1a\n"
PNG_CRITICAL = {"IHDR", "PLTE", "IDAT", "IEND"}
PNG_RENDERING = {"tRNS", "gAMA", "cHRM", "sRGB", "iCCP", "sBIT", "pHYs", "bKGD", "cICP", "mDCV", "cLLI",
                 "acTL", "fcTL", "fdAT", "hIST", "sPLT"}
PNG_TEXT = {"tEXt", "zTXt", "iTXt"}
MAX_TEXT_INFLATE = 8 * 1024 * 1024


def parse_png(data: bytes) -> Structure:
    if not data.startswith(PNG_SIG):
        raise ContainerError("Missing PNG signature")
    st = Structure("PNG")
    n = len(data)
    i = 8
    count = 0
    while i < n:
        count += 1
        if count > MAX_SEGMENTS:
            st.errors.append("Chunk limit exceeded")
            break
        if i + 8 > n:
            st.errors.append("Truncated chunk header")
            break
        length = struct.unpack(">I", data[i : i + 4])[0]
        ctype_raw = data[i + 4 : i + 8]
        try:
            ctype = ctype_raw.decode("ascii")
        except UnicodeDecodeError:
            st.errors.append(f"Non-ASCII chunk type at offset {i}")
            break
        if not ctype.isalpha():
            st.errors.append(f"Invalid chunk type {ctype!r} at offset {i}")
            break
        if length > 0x7FFFFFFF or i + 12 + length > n:
            st.errors.append(f"Chunk {ctype} at offset {i} exceeds file bounds")
            break
        payload_off = i + 8
        crc_stored = struct.unpack(">I", data[payload_off + length : payload_off + length + 4])[0]
        crc_calc = zlib.crc32(data[i + 4 : payload_off + length]) & 0xFFFFFFFF
        seg = Segment(ctype, i, length + 12, payload_off, length, _png_ident(ctype, data[payload_off:payload_off + min(length, 80)]),
                      crc_ok=(crc_stored == crc_calc))
        if not seg.crc_ok:
            st.errors.append(f"CRC mismatch in {ctype} chunk at offset {i}")
        if ctype == "IHDR" and length >= 13:
            w, h, depth, ctyp, comp, filt, inter = struct.unpack(">IIBBBBB", data[payload_off : payload_off + 13])
            st.info["ihdr"] = {"width": w, "height": h, "bit_depth": depth, "color_type": ctyp,
                               "compression": comp, "filter": filt, "interlace": inter}
        st.segments.append(seg)
        i = payload_off + length + 4
        if ctype == "IEND":
            st.eoi_end = i
            break
    if st.eoi_end is None:
        st.errors.append("No IEND chunk (file may be truncated)")
    else:
        st.trailing_bytes = n - st.eoi_end
    idat = [s for s in st.segments if s.name == "IDAT"]
    st.info["idat_chunks"] = len(idat)
    st.info["idat_bytes"] = sum(s.payload_length for s in idat)
    return st


def _png_ident(ctype: str, head: bytes) -> str:
    if ctype in PNG_TEXT:
        key = head.split(b"\x00", 1)[0].decode("latin-1", "replace")
        if ctype == "iTXt" and key == "XML:com.adobe.xmp":
            return "XMP"
        if key.lower() in ("raw profile type exif", "raw profile type app1"):
            return "EXIF_TEXT"
        if key.lower() == "raw profile type iptc":
            return "IPTC_TEXT"
        return "TEXT"
    return {"eXIf": "EXIF", "iCCP": "ICC", "caBX": "JUMBF", "tIME": "TIME"}.get(ctype, ctype)


def png_text_chunk(data: bytes, seg: Segment) -> tuple[str, str, str]:
    """Decode a tEXt/zTXt/iTXt chunk into (keyword, text, note). Bounded inflate."""
    payload = seg.payload(data)
    key, _, rest = payload.partition(b"\x00")
    keyword = key.decode("latin-1", "replace")
    note = ""
    try:
        if seg.name == "tEXt":
            text = rest.decode("latin-1", "replace")
        elif seg.name == "zTXt":
            text = _bounded_inflate(rest[1:]).decode("latin-1", "replace")
        else:  # iTXt
            comp_flag = rest[0] if rest else 0
            rest2 = rest[2:]
            lang, _, rest3 = rest2.partition(b"\x00")
            _tk, _, body = rest3.partition(b"\x00")
            body = _bounded_inflate(body) if comp_flag == 1 else body
            text = body.decode("utf-8", "replace")
            if lang:
                note = f"lang={lang.decode('latin-1', 'replace')}"
    except (zlib.error, ValueError) as exc:
        return keyword, "", f"undecodable: {exc}"
    return keyword, text, note


def _bounded_inflate(buf: bytes) -> bytes:
    d = zlib.decompressobj()
    out = d.decompress(buf, MAX_TEXT_INFLATE)
    if d.unconsumed_tail:
        raise ValueError(f"compressed text exceeds {MAX_TEXT_INFLATE} byte safety limit")
    return out


def make_png_chunk(ctype: str, payload: bytes) -> bytes:
    t = ctype.encode("ascii")
    return struct.pack(">I", len(payload)) + t + payload + struct.pack(">I", zlib.crc32(t + payload) & 0xFFFFFFFF)


def rebuild_png(data: bytes, st: Structure, decide: Callable[[Segment], bool | bytes], drop_trailing: bool = False) -> bytes:
    out = bytearray(PNG_SIG)
    for seg in st.segments:
        if seg.name in PNG_CRITICAL:
            out += data[seg.offset : seg.offset + seg.length]
            continue
        verdict = decide(seg)
        if verdict is True:
            out += data[seg.offset : seg.offset + seg.length]
        elif verdict is False:
            continue
        else:
            out += make_png_chunk(seg.name, bytes(verdict))
    if not drop_trailing and st.eoi_end is not None:
        out += data[st.eoi_end :]
    return bytes(out)


# --------------------------------------------------------------------------- WebP

VP8X_ICC, VP8X_ALPHA, VP8X_EXIF, VP8X_XMP, VP8X_ANIM = 0x20, 0x10, 0x08, 0x04, 0x02


def parse_webp(data: bytes) -> Structure:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ContainerError("Missing RIFF/WEBP header")
    st = Structure("WEBP")
    riff_size = struct.unpack("<I", data[4:8])[0]
    end = min(len(data), 8 + riff_size)
    if 8 + riff_size != len(data):
        st.errors.append(f"RIFF size {riff_size} does not match file length {len(data)}")
    i = 12
    count = 0
    while i + 8 <= end:
        count += 1
        if count > MAX_SEGMENTS:
            st.errors.append("Chunk limit exceeded")
            break
        fourcc = data[i : i + 4].decode("latin-1")
        size = struct.unpack("<I", data[i + 4 : i + 8])[0]
        if i + 8 + size > end:
            st.errors.append(f"Chunk {fourcc!r} at {i} exceeds RIFF bounds")
            break
        padded = size + (size & 1)
        ident = {"EXIF": "EXIF", "XMP ": "XMP", "ICCP": "ICC", "C2PA": "JUMBF"}.get(fourcc, fourcc.strip())
        seg = Segment(fourcc, i, 8 + padded, i + 8, size, ident)
        if fourcc == "VP8X" and size >= 10:
            flags = data[i + 8]
            w = 1 + int.from_bytes(data[i + 12 : i + 15], "little")
            h = 1 + int.from_bytes(data[i + 15 : i + 18], "little")
            st.info["vp8x"] = {"flags": flags, "width": w, "height": h}
        if fourcc == "VP8 ":
            st.info["bitstream"] = "VP8 (lossy)"
        elif fourcc == "VP8L":
            st.info["bitstream"] = "VP8L (lossless)"
        elif fourcc == "ANMF":
            st.info["bitstream"] = st.info.get("bitstream", "animated")
        st.segments.append(seg)
        i += 8 + padded
    st.eoi_end = end
    st.trailing_bytes = len(data) - end
    return st


def rebuild_webp(data: bytes, st: Structure, decide: Callable[[Segment], bool | bytes]) -> bytes:
    body = bytearray()
    kept: list[str] = []
    vp8x_pos = None
    for seg in st.segments:
        if seg.name in ("VP8 ", "VP8L", "VP8X", "ALPH", "ANIM", "ANMF"):
            verdict: bool | bytes = True
        else:
            verdict = decide(seg)
        if verdict is False:
            continue
        if seg.name == "VP8X":
            vp8x_pos = len(body)
        if verdict is True:
            body += data[seg.offset : seg.offset + seg.length]
        else:
            payload = bytes(verdict)
            body += seg.name.encode("latin-1") + struct.pack("<I", len(payload)) + payload + (b"\x00" if len(payload) & 1 else b"")
        kept.append(seg.name)
    if vp8x_pos is not None:
        flags = body[vp8x_pos + 8]
        for fourcc, bit in (("ICCP", VP8X_ICC), ("EXIF", VP8X_EXIF), ("XMP ", VP8X_XMP)):
            flags = (flags | bit) if fourcc in kept else (flags & ~bit & 0xFF)
        body[vp8x_pos + 8] = flags
    return b"RIFF" + struct.pack("<I", len(body) + 4) + b"WEBP" + bytes(body)


# --------------------------------------------------------------------------- dispatch

def parse_container(data: bytes, fmt: str) -> Structure:
    if fmt == "JPEG":
        return parse_jpeg(data)
    if fmt == "PNG":
        return parse_png(data)
    if fmt == "WEBP":
        return parse_webp(data)
    st = Structure(fmt)
    st.info["note"] = f"Byte-level structure parsing is not implemented for {fmt}; decoder-level metadata only."
    return st


def reassemble_jpeg_jumbf(data: bytes, st: Structure) -> tuple[bytes | None, list[str]]:
    """Reassemble a JUMBF superbox split across JPEG APP11 segments (ISO 19566-5)."""
    errors: list[str] = []
    groups: dict[int, list[tuple[int, bytes]]] = {}
    for seg in st.find("JUMBF"):
        p = seg.payload(data)
        if len(p) < 16:
            errors.append(f"APP11 segment at {seg.offset} too short")
            continue
        en = struct.unpack(">H", p[2:4])[0]
        z = struct.unpack(">I", p[4:8])[0]
        groups.setdefault(en, []).append((z, p[8:]))
    if not groups:
        return None, errors
    stores = []
    for en, parts in sorted(groups.items()):
        parts.sort(key=lambda t: t[0])
        first = parts[0][1]
        lbox = struct.unpack(">I", first[:4])[0]
        hdr = 16 if lbox == 1 else 8
        buf = bytearray(first)
        for _z, chunk in parts[1:]:
            buf += chunk[hdr:]
        stores.append(bytes(buf))
    # Prefer the store whose description label is "c2pa".
    for s in stores:
        if b"c2pa" in s[:64]:
            return s, errors
    return stores[0], errors
