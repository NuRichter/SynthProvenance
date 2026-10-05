"""Image and metadata records."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.utils.serialization import jsonable


class ItemState(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"
    INVALID = "INVALID"
    REMOVED = "REMOVED"
    PRESERVED = "PRESERVED"


# Canonical metadata groups shown by the Forensic Inspector.
GROUP_ORDER = ["EXIF", "XMP", "IPTC", "PNG CHUNKS", "JPEG APP MARKERS", "WEBP CHUNKS", "TIFF TAGS", "ICC", "SOFTWARE", "C2PA / JUMBF"]


@dataclass
class MetadataField:
    group: str
    key: str
    value: str
    namespace: str = ""
    category: str = "other"  # gps/camera/device/author/timestamp/software/private/ai/structure/other
    raw_type: str = ""
    state: ItemState = ItemState.PRESENT

    @property
    def ident(self) -> str:
        return f"{self.group}|{self.namespace}|{self.key}"


@dataclass
class MetadataGroup:
    name: str
    state: ItemState
    fields: list[MetadataField] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    byte_size: int = 0
    location: str = ""


@dataclass
class ImageInfo:
    path: str
    filename: str
    file_size: int
    format: str
    mime: str
    width: int
    height: int
    pixel_count: int
    aspect_ratio: str
    mode: str
    channels: int
    bit_depth: str
    color_space: str
    icc_profile: str
    compression: str
    frames: int = 1
    animated: bool = False
    orientation: str = "UNKNOWN"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return jsonable(self)
