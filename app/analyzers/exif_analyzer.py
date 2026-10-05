"""EXIF (TIFF IFD) inspection and category-selective editing via Pillow."""
from __future__ import annotations

import struct

from PIL import ExifTags, Image, TiffImagePlugin

from app.models.image_info import ItemState, MetadataField, MetadataGroup

EXIF_IFD = 0x8769
GPS_IFD = 0x8825
INTEROP_IFD = 0xA005

_CATEGORY = {
    # camera
    "Make": "camera", "Model": "camera", "LensMake": "camera", "LensModel": "camera",
    "LensSpecification": "camera", "MakerNote": "camera", "FocalLength": "camera", "FNumber": "camera",
    "ExposureTime": "camera", "ISOSpeedRatings": "camera", "Flash": "camera", "FocalLengthIn35mmFilm": "camera",
    "ExposureProgram": "camera", "MeteringMode": "camera", "WhiteBalance": "camera", "ExposureBiasValue": "camera",
    "ShutterSpeedValue": "camera", "ApertureValue": "camera", "MaxApertureValue": "camera", "SceneCaptureType": "camera",
    "ExposureMode": "camera", "DigitalZoomRatio": "camera", "SensingMethod": "camera", "BrightnessValue": "camera",
    # device identity
    "BodySerialNumber": "device", "CameraSerialNumber": "device", "LensSerialNumber": "device",
    "HostComputer": "device", "ImageUniqueID": "device", "UniqueCameraModel": "device",
    # author
    "Artist": "author", "XPAuthor": "author", "CameraOwnerName": "author",
    # rights (always preserved by the sanitizer)
    "Copyright": "rights",
    # timestamps
    "DateTime": "timestamp", "DateTimeOriginal": "timestamp", "DateTimeDigitized": "timestamp",
    "SubsecTime": "timestamp", "SubsecTimeOriginal": "timestamp", "SubsecTimeDigitized": "timestamp",
    "OffsetTime": "timestamp", "OffsetTimeOriginal": "timestamp", "OffsetTimeDigitized": "timestamp",
    # software
    "Software": "software", "ProcessingSoftware": "software",
    # private free text
    "UserComment": "private", "ImageDescription": "private", "XPComment": "private", "XPSubject": "private",
    "XPKeywords": "private", "XPTitle": "private",
    # structure (always preserved)
    "Orientation": "structure", "XResolution": "structure", "YResolution": "structure",
    "ResolutionUnit": "structure", "YCbCrPositioning": "structure", "ColorSpace": "structure",
    "ExifImageWidth": "structure", "ExifImageHeight": "structure", "ExifVersion": "structure",
    "ComponentsConfiguration": "structure", "FlashPixVersion": "structure", "ExifOffset": "structure",
    "GPSInfo": "gps", "Gamma": "structure", "InteroperabilityIndex": "structure",
}
_XP_TAGS = {0x9C9B: "XPTitle", 0x9C9C: "XPComment", 0x9C9D: "XPAuthor", 0x9C9E: "XPKeywords", 0x9C9F: "XPSubject"}


def tag_name(tag: int, ifd: str) -> str:
    if ifd == "GPS":
        return ExifTags.GPSTAGS.get(tag, f"GPSTag_0x{tag:04X}")
    return _XP_TAGS.get(tag) or ExifTags.TAGS.get(tag, f"Tag_0x{tag:04X}")


def category_of(name: str, ifd: str) -> str:
    if ifd == "GPS":
        return "gps"
    return _CATEGORY.get(name, "other")


def format_value(value, name: str = "") -> str:
    if name == "MakerNote" and isinstance(value, (bytes, bytearray)):
        return f"<MakerNote, {len(value)} bytes, vendor-specific>"
    if name.startswith("XP") and isinstance(value, (bytes, bytearray, tuple)):
        try:
            raw = bytes(value) if not isinstance(value, bytes) else value
            return raw.decode("utf-16-le", "replace").rstrip("\x00")
        except (TypeError, ValueError):
            pass
    if isinstance(value, TiffImagePlugin.IFDRational):
        try:
            return f"{float(value):g}"
        except ZeroDivisionError:
            return "undefined (x/0)"
    if isinstance(value, (bytes, bytearray)):
        stripped = bytes(value).rstrip(b"\x00")
        if stripped and all(32 <= c < 127 for c in stripped[:256]):
            return stripped[:512].decode("ascii")
        return f"<{len(value)} bytes> {bytes(value)[:16].hex()}"
    if isinstance(value, tuple):
        return "(" + ", ".join(format_value(v) for v in value[:16]) + (", ..." if len(value) > 16 else "") + ")"
    text = str(value).replace("\x00", "")
    return text[:512] + ("..." if len(text) > 512 else "")


def _normalise(raw: bytes) -> bytes:
    """Accept either an APP1 payload ("Exif\\0\\0" + TIFF) or a bare TIFF block."""
    if raw.startswith(b"Exif\x00\x00") or raw.startswith(b"Exif\x00\xff"):
        return raw[6:]
    return raw


def has_ifd1(raw: bytes) -> bool:
    tiff = _normalise(raw)
    try:
        endian = "<" if tiff[:2] == b"II" else ">"
        off = struct.unpack(endian + "I", tiff[4:8])[0]
        count = struct.unpack(endian + "H", tiff[off : off + 2])[0]
        nxt = struct.unpack(endian + "I", tiff[off + 2 + 12 * count : off + 6 + 12 * count])[0]
        return nxt != 0
    except (struct.error, IndexError):
        return False


def load_exif(raw: bytes) -> Image.Exif:
    exif = Image.Exif()
    exif.load(b"Exif\x00\x00" + _normalise(raw))
    return exif


def analyze_exif(raw: bytes | None, location: str = "") -> MetadataGroup:
    if not raw:
        return MetadataGroup("EXIF", ItemState.ABSENT)
    group = MetadataGroup("EXIF", ItemState.PRESENT, byte_size=len(raw), location=location)
    try:
        exif = load_exif(raw)
    except Exception as exc:  # noqa: BLE001 - malformed EXIF must never crash analysis
        group.state = ItemState.INVALID
        group.notes.append(f"EXIF block could not be parsed: {type(exc).__name__}: {exc}")
        return group
    try:
        for tag, value in exif.items():
            if tag in (EXIF_IFD, GPS_IFD, INTEROP_IFD):
                continue
            name = tag_name(tag, "IFD0")
            group.fields.append(MetadataField("EXIF", name, format_value(value, name), "IFD0", category_of(name, "IFD0")))
        for ifd_tag, ifd_name in ((EXIF_IFD, "ExifIFD"), (GPS_IFD, "GPS"), (INTEROP_IFD, "Interop")):
            try:
                sub = exif.get_ifd(ifd_tag)
            except Exception as exc:  # noqa: BLE001
                group.notes.append(f"{ifd_name} could not be read: {exc}")
                continue
            for tag, value in sub.items():
                if ifd_tag == EXIF_IFD and tag == INTEROP_IFD:
                    continue
                name = tag_name(tag, ifd_name)
                group.fields.append(MetadataField("EXIF", name, format_value(value, name), ifd_name, category_of(name, ifd_name)))
        if has_ifd1(raw):
            group.notes.append("IFD1 (embedded thumbnail directory) present.")
    except Exception as exc:  # noqa: BLE001
        group.state = ItemState.INVALID
        group.notes.append(f"EXIF traversal failed: {exc}")
    if not group.fields and group.state == ItemState.PRESENT:
        group.notes.append("EXIF block present but contains no readable tags.")
    return group


def orientation_of(raw: bytes | None) -> int | None:
    if not raw:
        return None
    try:
        return load_exif(raw).get(0x0112)
    except Exception:  # noqa: BLE001
        return None


def edit_exif(raw: bytes, remove: set[str]) -> tuple[bytes | None, list[str], list[str]]:
    """Remove tags whose category is in ``remove``.

    Returns (new TIFF block without the "Exif\\0\\0" prefix or None if the
    result would be empty, removed tag names, notes). Structure and rights
    categories are never removed.
    """
    remove = set(remove) - {"structure", "rights"}
    exif = load_exif(raw)
    removed: list[str] = []
    notes: list[str] = []
    for tag in list(exif.keys()):
        if tag in (EXIF_IFD, INTEROP_IFD):
            continue
        if tag == GPS_IFD:
            if "gps" in remove:
                try:
                    removed.extend(f"GPS:{tag_name(t, 'GPS')}" for t in exif.get_ifd(GPS_IFD))
                except Exception:  # noqa: BLE001
                    removed.append("GPS IFD")
                del exif[tag]
            continue
        name = tag_name(tag, "IFD0")
        if category_of(name, "IFD0") in remove:
            removed.append(f"IFD0:{name}")
            del exif[tag]
    if EXIF_IFD in exif:
        sub = exif.get_ifd(EXIF_IFD)
        for tag in list(sub.keys()):
            name = tag_name(tag, "ExifIFD")
            if category_of(name, "ExifIFD") in remove:
                removed.append(f"ExifIFD:{name}")
                del sub[tag]
    if not removed:
        return _normalise(raw), [], notes
    if has_ifd1(raw):
        notes.append("EXIF IFD1 thumbnail directory is not carried over by the selective rewrite.")
    try:
        new = exif.tobytes()
    except Exception as exc:  # noqa: BLE001
        notes.append(f"Selective EXIF rewrite failed ({exc}); falling back to an orientation-only EXIF block.")
        minimal = Image.Exif()
        orient = exif.get(0x0112)
        if orient is None:
            return None, removed + ["EXIF block"], notes
        minimal[0x0112] = orient
        new = minimal.tobytes()
    tiff = _normalise(new)
    probe = load_exif(tiff)
    if len(probe) == 0:
        return None, removed, notes
    return tiff, removed, notes
