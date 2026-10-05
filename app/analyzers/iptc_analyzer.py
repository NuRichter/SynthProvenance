"""IPTC-IIM inspection and editing (Photoshop Image Resource Blocks)."""
from __future__ import annotations

import struct

from app.models.image_info import ItemState, MetadataField, MetadataGroup

PS_HEADER = b"Photoshop 3.0\x00"
IRB_IPTC = 0x0404
IRB_IPTC_DIGEST = 0x0425
IRB_KEEP_ALWAYS = {IRB_IPTC, 0x03ED}  # IPTC, ResolutionInfo

DATASETS = {
    (1, 90): ("CodedCharacterSet", "structure"), (2, 0): ("RecordVersion", "structure"),
    (2, 5): ("ObjectName", "other"), (2, 7): ("EditStatus", "other"), (2, 10): ("Urgency", "other"),
    (2, 15): ("Category", "other"), (2, 20): ("SupplementalCategories", "other"), (2, 25): ("Keywords", "other"),
    (2, 40): ("SpecialInstructions", "private"), (2, 55): ("DateCreated", "timestamp"),
    (2, 60): ("TimeCreated", "timestamp"), (2, 62): ("DigitalCreationDate", "timestamp"),
    (2, 63): ("DigitalCreationTime", "timestamp"), (2, 65): ("OriginatingProgram", "software"),
    (2, 70): ("ProgramVersion", "software"), (2, 80): ("By-line", "author"), (2, 85): ("By-lineTitle", "author"),
    (2, 90): ("City", "private"), (2, 92): ("Sub-location", "private"), (2, 95): ("Province-State", "private"),
    (2, 100): ("CountryCode", "private"), (2, 101): ("CountryName", "private"),
    (2, 103): ("OriginalTransmissionReference", "private"), (2, 105): ("Headline", "other"),
    (2, 110): ("Credit", "rights"), (2, 115): ("Source", "rights"), (2, 116): ("CopyrightNotice", "rights"),
    (2, 118): ("Contact", "private"), (2, 120): ("Caption-Abstract", "other"), (2, 122): ("Writer-Editor", "author"),
}


class IPTCError(ValueError):
    pass


def parse_irb(payload: bytes) -> list[tuple[int, bytes, bytes]]:
    """Parse Photoshop IRB payload (after header). Returns (id, name, data)."""
    if payload.startswith(PS_HEADER):
        payload = payload[len(PS_HEADER):]
    out = []
    i = 0
    n = len(payload)
    while i + 12 <= n:
        sig = payload[i : i + 4]
        if sig not in (b"8BIM", b"PHUT", b"AgHg", b"DCSR", b"MeSa"):
            raise IPTCError(f"Bad IRB signature {sig!r} at {i}")
        rid = struct.unpack(">H", payload[i + 4 : i + 6])[0]
        name_len = payload[i + 6]
        name_total = 1 + name_len
        name_total += name_total & 1
        name = payload[i + 7 : i + 7 + name_len]
        j = i + 6 + name_total
        if j + 4 > n:
            raise IPTCError("Truncated IRB size")
        size = struct.unpack(">I", payload[j : j + 4])[0]
        if j + 4 + size > n:
            raise IPTCError("IRB resource exceeds payload")
        out.append((rid, name, payload[j + 4 : j + 4 + size]))
        i = j + 4 + size + (size & 1)
    return out


def build_irb(resources: list[tuple[int, bytes, bytes]]) -> bytes:
    out = bytearray(PS_HEADER)
    for rid, name, data in resources:
        out += b"8BIM" + struct.pack(">H", rid)
        pname = bytes([len(name)]) + name
        if len(pname) & 1:
            pname += b"\x00"
        out += pname + struct.pack(">I", len(data)) + data
        if len(data) & 1:
            out += b"\x00"
    return bytes(out)


def parse_iim(data: bytes) -> list[tuple[int, int, bytes]]:
    out = []
    i = 0
    n = len(data)
    while i + 5 <= n:
        if data[i] != 0x1C:
            break
        rec, ds = data[i + 1], data[i + 2]
        size = struct.unpack(">H", data[i + 3 : i + 5])[0]
        hdr = 5
        if size & 0x8000:
            ext_len = size & 0x7FFF
            if ext_len > 4 or i + 5 + ext_len > n:
                raise IPTCError("Bad extended IIM length")
            size = int.from_bytes(data[i + 5 : i + 5 + ext_len], "big")
            hdr += ext_len
        if i + hdr + size > n:
            raise IPTCError("IIM dataset exceeds resource")
        out.append((rec, ds, data[i + hdr : i + hdr + size]))
        i += hdr + size
    return out


def build_iim(datasets: list[tuple[int, int, bytes]]) -> bytes:
    out = bytearray()
    for rec, ds, value in datasets:
        if len(value) > 0x7FFF:
            out += bytes([0x1C, rec, ds]) + struct.pack(">HI", 0x8004, len(value)) + value
        else:
            out += bytes([0x1C, rec, ds]) + struct.pack(">H", len(value)) + value
    return bytes(out)


def _decode(value: bytes, utf8: bool) -> str:
    try:
        text = value.decode("utf-8" if utf8 else "latin-1")
    except UnicodeDecodeError:
        text = value.decode("latin-1", "replace")
    return text[:512]


def analyze_iptc(irb_payload: bytes | None, location: str = "") -> MetadataGroup:
    if not irb_payload:
        return MetadataGroup("IPTC", ItemState.ABSENT)
    group = MetadataGroup("IPTC", ItemState.ABSENT, location=location)
    try:
        resources = parse_irb(irb_payload)
    except IPTCError as exc:
        return MetadataGroup("IPTC", ItemState.INVALID, notes=[f"Photoshop IRB could not be parsed: {exc}"], location=location)
    others = [f"0x{rid:04X}" for rid, _n, _d in resources if rid != IRB_IPTC]
    for rid, _name, data in resources:
        if rid != IRB_IPTC:
            continue
        group.state = ItemState.PRESENT
        group.byte_size = len(data)
        try:
            datasets = parse_iim(data)
        except IPTCError as exc:
            group.state = ItemState.INVALID
            group.notes.append(str(exc))
            continue
        utf8 = any(rec == 1 and ds == 90 and b"%G" in v for rec, ds, v in datasets)
        for rec, ds, value in datasets:
            name, cat = DATASETS.get((rec, ds), (f"{rec}:{ds:03d}", "other"))
            group.fields.append(MetadataField("IPTC", name, _decode(value, utf8), f"IIM {rec}:{ds}", cat))
    if others:
        group.notes.append(f"Other Photoshop image resources present: {', '.join(others[:20])}")
    if group.state == ItemState.ABSENT:
        group.notes.append("Photoshop IRB present without an IPTC-NAA (0x0404) resource.")
    return group


def edit_iptc(irb_payload: bytes, remove: set[str], drop_other_resources: bool) -> tuple[bytes | None, list[str]]:
    remove = set(remove) - {"rights", "structure"}
    resources = parse_irb(irb_payload)
    removed: list[str] = []
    new_res = []
    iptc_changed = False
    for rid, name, data in resources:
        if rid == IRB_IPTC:
            datasets = parse_iim(data)
            kept = []
            for rec, ds, value in datasets:
                label, cat = DATASETS.get((rec, ds), (f"{rec}:{ds:03d}", "other"))
                if cat in remove:
                    removed.append(f"IPTC:{label}")
                    iptc_changed = True
                else:
                    kept.append((rec, ds, value))
            content = [d for d in kept if not (d[0] == 1 or (d[0] == 2 and d[1] == 0))]
            if content:
                new_res.append((rid, name, build_iim(kept)))
            elif datasets:
                removed.append("IPTC:record (empty after removal)")
            continue
        if drop_other_resources and rid not in IRB_KEEP_ALWAYS:
            removed.append(f"IRB:0x{rid:04X}")
            continue
        new_res.append((rid, name, data))
    if iptc_changed:
        before = len(new_res)
        new_res = [r for r in new_res if r[0] != IRB_IPTC_DIGEST]
        if len(new_res) != before:
            removed.append("IRB:0x0425 (IPTC digest, invalidated by edit)")
    if not removed:
        return irb_payload, []
    if not new_res:
        return None, removed
    return build_irb(new_res), removed
