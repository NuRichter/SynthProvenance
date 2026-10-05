"""JPEG APP-marker inventory and quantisation-table extraction."""
from __future__ import annotations

import struct

from app.core.containers import Structure
from app.models.image_info import ItemState, MetadataField, MetadataGroup

ZIGZAG = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14,
          21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53, 60,
          61, 54, 47, 55, 62, 63]
STD_LUMA = [16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29,
            51, 87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92, 49, 64, 78, 87, 103, 121,
            120, 101, 72, 92, 95, 98, 112, 100, 103, 99]
STD_CHROMA = [17, 18, 24, 47] + [99] * 4 + [18, 21, 26, 66] + [99] * 4 + [24, 26, 56] + [99] * 5 + [47, 66] + [99] * 6 + [99] * 32

SEGMENT_CATEGORY = {
    "EXIF": "container", "XMP": "container", "XMP_EXT": "application", "ICC": "structure", "JFIF": "structure",
    "ADOBE": "structure", "PHOTOSHOP_IRB": "container", "JUMBF": "provenance", "MPF": "application",
    "COM": "software", "DUCKY": "application", "FPXR": "application",
}


def analyze_jpeg_markers(data: bytes, st: Structure) -> MetadataGroup:
    group = MetadataGroup("JPEG APP MARKERS", ItemState.ABSENT, location="JPEG header segments")
    seen: dict[str, int] = {}
    for seg in st.segments:
        if st.scan_offset is not None and seg.offset >= st.scan_offset:
            break
        if not (seg.name.startswith("APP") or seg.name == "COM"):
            continue
        group.state = ItemState.PRESENT
        base = f"{seg.name} {seg.ident}"
        seen[base] = seen.get(base, 0) + 1
        key = base if seen[base] == 1 else f"{base} #{seen[base]}"
        value = f"{seg.payload_length:,} bytes"
        if seg.ident == "COM":
            txt = seg.payload(data)[:200].decode("latin-1", "replace").strip("\x00")
            value = f"comment: {txt}"
        group.fields.append(MetadataField("JPEG APP MARKERS", key, value, seg.name,
                                          SEGMENT_CATEGORY.get(seg.ident, "application")))
    if st.trailing_bytes:
        group.notes.append(f"{st.trailing_bytes:,} bytes after EOI (e.g. MPF secondary images or appended data).")
    if st.errors:
        group.notes.extend(st.errors)
    return group


def quant_tables(data: bytes, st: Structure) -> list[dict]:
    tables = []
    for seg in st.segments:
        if seg.ident != "DQT":
            continue
        p = seg.payload(data)
        i = 0
        while i < len(p):
            pq, tq = p[i] >> 4, p[i] & 0x0F
            i += 1
            n = 128 if pq else 64
            if i + n > len(p):
                break
            vals = list(struct.unpack(">64H", p[i : i + 128])) if pq else list(p[i : i + 64])
            i += n
            natural = [0] * 64
            for zz, nat in enumerate(ZIGZAG):
                natural[nat] = vals[zz]
            tables.append({"id": tq, "precision_bits": 16 if pq else 8, "natural_order": natural})
    return tables


def estimate_quality(natural: list[int], chroma: bool) -> dict:
    std = STD_CHROMA if chroma else STD_LUMA
    best_q, best_err = None, None
    for q in range(1, 101):
        s = 5000 / q if q < 50 else 200 - 2 * q
        scaled = [min(255, max(1, int((v * s + 50) // 100))) for v in std]
        err = sum(abs(a - b) for a, b in zip(scaled, natural))
        if best_err is None or err < best_err:
            best_q, best_err = q, err
    exact = best_err == 0
    return {
        "ijg_equivalent_quality": best_q,
        "table_match_error": best_err,
        "basis": "exact IJG table match" if exact else ("approximate IJG match" if best_err < 64 else "non-IJG table; estimate unreliable"),
    }
