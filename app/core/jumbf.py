"""ISO/IEC 19566-5 JUMBF box parsing and construction."""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

MAX_BOXES = 50_000
MAX_DEPTH = 32

C2PA_STORE_UUID = bytes.fromhex("6332706100110010800000AA00389B71")  # 'c2pa'
C2PA_MANIFEST_UUID = bytes.fromhex("63326D6100110010800000AA00389B71")  # 'c2ma'
C2PA_ASSERTIONS_UUID = bytes.fromhex("6332617300110010800000AA00389B71")  # 'c2as'
C2PA_CLAIM_UUID = bytes.fromhex("6332636C00110010800000AA00389B71")  # 'c2cl'
C2PA_SIGNATURE_UUID = bytes.fromhex("6332637300110010800000AA00389B71")  # 'c2cs'
CBOR_UUID = bytes.fromhex("63626F7200110010800000AA00389B71")  # 'cbor'
JSON_UUID = bytes.fromhex("6A736F6E00110010800000AA00389B71")  # 'json'


class JumbfError(ValueError):
    pass


@dataclass
class Box:
    type: str
    offset: int
    size: int
    payload: bytes = b""
    label: str | None = None
    uuid: bytes | None = None
    children: list["Box"] = field(default_factory=list)

    def child(self, label: str) -> "Box | None":
        for c in self.children:
            if c.type == "jumb" and c.label == label:
                return c
        return None

    def content(self) -> "Box | None":
        for c in self.children:
            if c.type not in ("jumd",):
                return c
        return None

    def superboxes(self) -> list["Box"]:
        return [c for c in self.children if c.type == "jumb"]


class _Counter:
    n = 0


def parse_boxes(data: bytes, start: int = 0, end: int | None = None, depth: int = 0, counter: _Counter | None = None) -> list[Box]:
    counter = counter or _Counter()
    end = len(data) if end is None else end
    if depth > MAX_DEPTH:
        raise JumbfError("JUMBF nesting too deep")
    boxes: list[Box] = []
    i = start
    while i + 8 <= end:
        counter.n += 1
        if counter.n > MAX_BOXES:
            raise JumbfError("JUMBF box limit exceeded")
        lbox = struct.unpack(">I", data[i : i + 4])[0]
        tbox = data[i + 4 : i + 8].decode("latin-1")
        hdr = 8
        if lbox == 1:
            if i + 16 > end:
                raise JumbfError("Truncated XLBox")
            lbox = struct.unpack(">Q", data[i + 8 : i + 16])[0]
            hdr = 16
        elif lbox == 0:
            lbox = end - i
        if lbox < hdr or i + lbox > end:
            raise JumbfError(f"Box {tbox!r} at {i} has invalid length {lbox}")
        box = Box(tbox, i, lbox)
        p0, p1 = i + hdr, i + lbox
        if tbox == "jumb":
            box.children = parse_boxes(data, p0, p1, depth + 1, counter)
            if box.children and box.children[0].type == "jumd":
                box.uuid, box.label = _parse_jumd(box.children[0].payload)
        else:
            box.payload = data[p0:p1]
        boxes.append(box)
        i += lbox
    return boxes


def _parse_jumd(p: bytes) -> tuple[bytes | None, str | None]:
    if len(p) < 17:
        return None, None
    uuid = p[:16]
    toggles = p[16]
    label = None
    if toggles & 0x02:
        raw = p[17:]
        nul = raw.find(b"\x00")
        label = raw[: nul if nul >= 0 else len(raw)].decode("utf-8", "replace")
    return uuid, label


# ---------------------------------------------------------------- construction

def box(tbox: str, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + tbox.encode("latin-1") + payload


def superbox(uuid: bytes, label: str, children: list[bytes]) -> bytes:
    jumd = box("jumd", uuid + bytes([0x03]) + label.encode("utf-8") + b"\x00")
    return box("jumb", jumd + b"".join(children))
