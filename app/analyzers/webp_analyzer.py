"""WebP RIFF chunk inventory."""
from __future__ import annotations

from app.core.containers import Structure
from app.models.image_info import ItemState, MetadataField, MetadataGroup

CHUNK_CATEGORY = {"VP8": "structure", "VP8L": "structure", "VP8X": "structure", "ALPH": "structure",
                  "ANIM": "structure", "ANMF": "structure", "ICCP": "structure", "EXIF": "container",
                  "XMP": "container", "C2PA": "provenance"}


def analyze_webp_chunks(data: bytes, st: Structure) -> MetadataGroup:
    g = MetadataGroup("WEBP CHUNKS", ItemState.PRESENT, location="RIFF chunk stream")
    seen: dict[str, int] = {}
    for seg in st.segments:
        name = seg.name.strip()
        seen[name] = seen.get(name, 0) + 1
        key = name if seen[name] == 1 else f"{name} #{seen[name]}"
        g.fields.append(MetadataField("WEBP CHUNKS", key, f"{seg.payload_length:,} bytes", "chunk",
                                      CHUNK_CATEGORY.get(name, "application")))
    flags = st.info.get("vp8x", {}).get("flags")
    if flags is not None:
        g.notes.append(f"VP8X flags 0x{flags:02X} (ICC {bool(flags & 0x20)}, alpha {bool(flags & 0x10)}, "
                       f"EXIF {bool(flags & 0x08)}, XMP {bool(flags & 0x04)}, animation {bool(flags & 0x02)}).")
    g.notes.extend(st.errors)
    return g
