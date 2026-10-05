"""TIFF IFD0 tag inventory (decoder-level, via Pillow)."""
from __future__ import annotations

from PIL import Image, TiffTags

from app.analyzers.exif_analyzer import format_value
from app.models.image_info import ItemState, MetadataField, MetadataGroup

STRUCTURE_TAGS = {256, 257, 258, 259, 262, 273, 277, 278, 279, 282, 283, 284, 296, 317, 322, 323, 324, 325, 338, 339,
                  530, 531, 532}
CATEGORY = {305: "software", 306: "timestamp", 315: "author", 316: "device", 33432: "rights", 270: "private",
            271: "camera", 272: "camera", 700: "container", 33723: "container", 34665: "container", 34853: "gps",
            34675: "structure", 37724: "application"}


def analyze_tiff_tags(img: Image.Image) -> MetadataGroup:
    tags = getattr(img, "tag_v2", None)
    if tags is None:
        return MetadataGroup("TIFF TAGS", ItemState.UNKNOWN, notes=["Decoder exposes no TIFF tag directory."])
    g = MetadataGroup("TIFF TAGS", ItemState.PRESENT, location="TIFF IFD0")
    for tag in sorted(tags.keys()):
        name = TiffTags.lookup(tag).name or f"Tag_{tag}"
        try:
            value = tags[tag]
        except Exception as exc:  # noqa: BLE001
            value = f"<unreadable: {exc}>"
        if tag in (700, 33723, 34675, 37724) or isinstance(value, (bytes, bytearray)) and len(value) > 64:
            shown = f"{len(value) if hasattr(value, '__len__') else '?'} bytes"
        else:
            shown = format_value(value, name)
        cat = "structure" if tag in STRUCTURE_TAGS else CATEGORY.get(tag, "other")
        g.fields.append(MetadataField("TIFF TAGS", name, shown, f"tag {tag}", cat))
    return g
