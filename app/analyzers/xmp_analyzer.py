"""XMP packet inspection and category-selective editing.

XML from untrusted files is parsed only after rejecting DOCTYPE / ENTITY
declarations, so entity-expansion and external-entity attacks are blocked.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from app.models.image_info import ItemState, MetadataField, MetadataGroup

MAX_XMP_BYTES = 4 * 1024 * 1024
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

PREFIX = {
    "adobe:ns:meta/": "x", RDF: "rdf",
    "http://purl.org/dc/elements/1.1/": "dc",
    "http://ns.adobe.com/xap/1.0/": "xmp",
    "http://ns.adobe.com/xap/1.0/mm/": "xmpMM",
    "http://ns.adobe.com/xap/1.0/rights/": "xmpRights",
    "http://ns.adobe.com/photoshop/1.0/": "photoshop",
    "http://ns.adobe.com/exif/1.0/": "exif",
    "http://cipa.jp/exif/1.0/": "exifEX",
    "http://ns.adobe.com/tiff/1.0/": "tiff",
    "http://ns.adobe.com/exif/1.0/aux/": "aux",
    "http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/": "Iptc4xmpCore",
    "http://iptc.org/std/Iptc4xmpExt/2008-02-29/": "Iptc4xmpExt",
    "http://ns.useplus.org/ldf/xmp/1.0/": "plus",
    "http://ns.adobe.com/camera-raw-settings/1.0/": "crs",
    "http://ns.adobe.com/lightroom/1.0/": "lr",
    "http://ns.adobe.com/xap/1.0/sType/ResourceEvent#": "stEvt",
    "http://ns.adobe.com/xap/1.0/sType/ResourceRef#": "stRef",
    "http://ns.adobe.com/xmp/note/": "xmpNote",
    "http://ns.adobe.com/pdf/1.3/": "pdf",
    "http://ns.google.com/photos/1.0/camera/": "GCamera",
    "http://ns.google.com/photos/1.0/panorama/": "GPano",
    "http://c2pa.org/": "c2pa",
}

AI_SOURCE_TYPES = {"trainedAlgorithmicMedia", "compositeWithTrainedAlgorithmicMedia"}
SYNTHETIC_SOURCE_TYPES = {"algorithmicMedia", "compositeSynthetic", "algorithmicallyEnhanced", "virtualRecording"}

_CAT_EXACT = {
    "tiff:Make": "camera", "tiff:Model": "camera", "aux:Lens": "camera", "aux:LensInfo": "camera",
    "aux:LensID": "camera", "exifEX:LensMake": "camera", "exifEX:LensModel": "camera",
    "exifEX:LensSpecification": "camera",
    "aux:SerialNumber": "device", "exifEX:BodySerialNumber": "device", "exifEX:LensSerialNumber": "device",
    "aux:LensSerialNumber": "device", "exif:ImageUniqueID": "device", "exifEX:ImageUniqueID": "device",
    "dc:creator": "author", "photoshop:AuthorsPosition": "author", "photoshop:CaptionWriter": "author",
    "exifEX:CameraOwnerName": "author", "aux:OwnerName": "author", "tiff:Artist": "author",
    "Iptc4xmpExt:AIPromptWriterName": "author",
    "xmp:CreateDate": "timestamp", "xmp:ModifyDate": "timestamp", "xmp:MetadataDate": "timestamp",
    "photoshop:DateCreated": "timestamp", "exif:DateTimeOriginal": "timestamp",
    "exif:DateTimeDigitized": "timestamp", "tiff:DateTime": "timestamp",
    "xmp:CreatorTool": "software", "tiff:Software": "software",
    "photoshop:City": "private", "photoshop:State": "private", "photoshop:Country": "private",
    "photoshop:Instructions": "private", "photoshop:TransmissionReference": "private",
    "photoshop:DocumentAncestors": "private", "Iptc4xmpCore:Location": "private",
    "Iptc4xmpCore:CreatorContactInfo": "private", "Iptc4xmpExt:LocationCreated": "private",
    "Iptc4xmpExt:LocationShown": "private", "Iptc4xmpExt:AIPromptInformation": "private",
    "Iptc4xmpExt:DigitalSourceType": "provenance", "Iptc4xmpExt:AISystemUsed": "provenance",
    "Iptc4xmpExt:AISystemVersionUsed": "provenance",
    "xmpNote:HasExtendedXMP": "application",
}
_CAT_PREFIX = {
    "xmpMM": "private", "crs": "application", "lr": "application", "GCamera": "application",
    "xmpRights": "rights", "c2pa": "provenance",
}
_SUBPATH_CAT = {"stEvt:when": "timestamp", "stEvt:softwareAgent": "software"}
_PRESERVE = {"structure", "rights"}


class XMPError(ValueError):
    pass


XML_NS = "http://www.w3.org/XML/1998/namespace"


def _unknown_prefix(uri: str) -> str:
    tail = re.sub(r"[^A-Za-z0-9]", "", uri.rstrip("/#").split("/")[-1]) or "ns"
    return "x-" + tail[:16]


def _qname(tag: str) -> tuple[str, str, str]:
    if tag.startswith("{"):
        uri, local = tag[1:].split("}", 1)
        if uri == XML_NS:
            return uri, "xml", local
        return uri, PREFIX.get(uri) or _unknown_prefix(uri), local
    return "", "", tag


def category_of(key: str) -> str:
    base = key.split("/")[0].split("[")[0]
    if base in _CAT_EXACT:
        return _CAT_EXACT[base]
    leaf = key.split("/")[-1].split("[")[0]
    if leaf in _SUBPATH_CAT and base.startswith("xmpMM"):
        return "private"
    if base.startswith("exif:GPS"):
        return "gps"
    if base in ("dc:rights", "photoshop:Copyright", "photoshop:Credit", "photoshop:Source", "Iptc4xmpCore:CopyrightNotice"):
        return "rights"
    prefix = base.split(":", 1)[0]
    if prefix in _CAT_PREFIX:
        return _CAT_PREFIX[prefix]
    if prefix.startswith("x-"):
        return "application"
    return "other"


def _check_safe(packet: bytes) -> None:
    if len(packet) > MAX_XMP_BYTES:
        raise XMPError(f"XMP packet exceeds {MAX_XMP_BYTES} bytes")
    head = packet.lower()
    if b"<!doctype" in head or b"<!entity" in head:
        raise XMPError("XMP contains DOCTYPE/ENTITY declarations and was rejected for safety")


def parse_packet(packet: bytes) -> ET.Element:
    _check_safe(packet)
    text = packet
    if text.startswith(b"\xef\xbb\xbf"):
        text = text[3:]
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        # Some writers pad with NULs or trailing garbage after </x:xmpmeta>.
        m = re.search(rb"<x:xmpmeta.*?</x:xmpmeta>", text, re.S)
        if m:
            try:
                return ET.fromstring(m.group(0))
            except ET.ParseError:
                pass
        raise XMPError(f"XMP is not well-formed XML: {exc}") from exc


def _flatten(elem: ET.Element, path: str, out: list[tuple[str, str]]) -> None:
    kids = list(elem)
    if not kids:
        text = (elem.text or "").strip()
        resource = elem.get(f"{{{RDF}}}resource")
        out.append((path, resource if resource is not None else text))
        for ak, av in elem.attrib.items():
            _u, p, l = _qname(ak)
            if p in ("rdf", "xml"):
                continue
            out.append((f"{path}/{p}:{l}", av))
        return
    for child in kids:
        _u, p, l = _qname(child.tag)
        if p == "rdf" and l in ("Seq", "Bag", "Alt"):
            for idx, li in enumerate(child, 1):
                _flatten(li, f"{path}[{idx}]", out)
        elif p == "rdf" and l == "Description":
            for ak, av in child.attrib.items():
                _u2, p2, l2 = _qname(ak)
                if p2 not in ("rdf", "xml"):
                    out.append((f"{path}/{p2}:{l2}", av))
            _flatten_children(child, path, out)
        elif p == "rdf" and l == "li":
            _flatten(child, path, out)
        else:
            _flatten(child, f"{path}/{p}:{l}", out)
    for ak, av in elem.attrib.items():
        _u, p, l = _qname(ak)
        if p not in ("rdf", "xml"):
            out.append((f"{path}/{p}:{l}", av))


def _flatten_children(desc: ET.Element, path: str, out: list[tuple[str, str]]) -> None:
    for child in desc:
        _u, p, l = _qname(child.tag)
        _flatten(child, f"{path}/{p}:{l}" if path else f"{p}:{l}", out)


def extract_fields(root: ET.Element) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for desc in root.iter(f"{{{RDF}}}Description"):
        for ak, av in desc.attrib.items():
            _u, p, l = _qname(ak)
            if p in ("rdf", "xml"):
                continue
            out.append((f"{p}:{l}", av))
        for child in desc:
            _u, p, l = _qname(child.tag)
            if p in ("rdf", "xml"):
                continue
            _flatten(child, f"{p}:{l}", out)
    return out


def analyze_xmp(packet: bytes | None, location: str = "") -> MetadataGroup:
    if not packet:
        return MetadataGroup("XMP", ItemState.ABSENT)
    group = MetadataGroup("XMP", ItemState.PRESENT, byte_size=len(packet), location=location)
    try:
        root = parse_packet(packet)
        for key, value in extract_fields(root):
            ns = key.split(":", 1)[0]
            v = value if len(value) <= 512 else value[:512] + "..."
            group.fields.append(MetadataField("XMP", key, v, ns, category_of(key)))
    except XMPError as exc:
        group.state = ItemState.INVALID
        group.notes.append(str(exc))
    if group.state == ItemState.PRESENT and not group.fields:
        group.notes.append("XMP packet present but contains no properties.")
    return group


def digital_source_types(fields: list[MetadataField]) -> list[tuple[str, str]]:
    out = []
    for f in fields:
        if f.key.split("[")[0].endswith("DigitalSourceType") or f.key.startswith("Iptc4xmpExt:DigitalSourceType"):
            out.append((f.key, f.value))
    return out


# ------------------------------------------------------------------ editing

def edit_xmp(packet: bytes, remove: set[str]) -> tuple[bytes | None, list[str]]:
    """Remove top-level properties whose category is in ``remove``.

    Returns (new packet or None if no properties remain, removed keys).
    Raises XMPError if the packet cannot be parsed safely.
    """
    remove = set(remove) - _PRESERVE
    root = parse_packet(packet)
    removed: list[str] = []
    for uri, prefix in PREFIX.items():
        ET.register_namespace(prefix, uri)
    for desc in list(root.iter(f"{{{RDF}}}Description")):
        for ak in list(desc.attrib.keys()):
            _u, p, l = _qname(ak)
            if p in ("rdf", "xml"):
                continue
            key = f"{p}:{l}"
            if category_of(key) in remove:
                removed.append(key)
                del desc.attrib[ak]
        for child in list(desc):
            _u, p, l = _qname(child.tag)
            key = f"{p}:{l}"
            if p != "rdf" and category_of(key) in remove:
                removed.append(key)
                desc.remove(child)
    if not removed:
        return packet, []
    remaining = extract_fields(root)
    if not remaining:
        return None, removed
    body = ET.tostring(root, encoding="unicode")
    new = '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n' + body + '\n<?xpacket end="w"?>'
    return new.encode("utf-8"), removed
