"""PNG chunk inventory, text-chunk inspection and generator-record detection."""
from __future__ import annotations

import json

from app.core.containers import PNG_CRITICAL, PNG_RENDERING, Structure, png_text_chunk
from app.models.image_info import ItemState, MetadataField, MetadataGroup

GENERATOR_KEYS = {"parameters", "prompt", "workflow", "invokeai_metadata", "sd-metadata", "dream", "generation_data",
                  "negative_prompt", "aigc"}
TEXT_CATEGORY = {
    "author": "author", "artist": "author", "copyright": "rights", "creation time": "timestamp",
    "software": "software", "source": "device", "comment": "private", "description": "private",
    "title": "other", "disclaimer": "rights", "warning": "other",
}


def text_category(keyword: str) -> str:
    k = keyword.lower()
    if k in GENERATOR_KEYS:
        return "generator"
    return TEXT_CATEGORY.get(k, "application")


def chunk_category(seg_name: str, ident: str) -> str:
    if seg_name in PNG_CRITICAL or seg_name in PNG_RENDERING:
        return "structure"
    if ident == "JUMBF":
        return "provenance"
    if seg_name == "tIME":
        return "timestamp"
    if seg_name == "eXIf":
        return "container"
    if len(seg_name) == 4 and seg_name[1].islower():
        return "application"  # private chunk (ancillary + private bits)
    return "application"


def detect_generator_record(keyword: str, text: str) -> tuple[bool, str] | None:
    """Return (structured, description) for a likely generator-parameter record, else None."""
    k = keyword.lower()
    t = text or ""
    if k == "parameters":
        if "Steps:" in t and ("Sampler:" in t or "Seed:" in t):
            return True, "Structured diffusion-generation parameter record (Steps/Sampler/Seed fields)"
        return False, "Text chunk named 'parameters' (unstructured)"
    if k in ("prompt", "workflow"):
        try:
            obj = json.loads(t[:2_000_000])
            if isinstance(obj, dict) and any(isinstance(v, dict) and "class_type" in v for v in obj.values()):
                return True, "Structured node-graph generation record (class_type nodes)"
            if isinstance(obj, dict) and isinstance(obj.get("nodes"), list):
                return True, "Structured node-graph workflow record"
        except (ValueError, TypeError, RecursionError):
            pass
        return False, f"Text chunk named '{keyword}' (unstructured)"
    if k in ("invokeai_metadata", "sd-metadata", "dream", "generation_data"):
        return True, f"Generator metadata record '{keyword}'"
    if k == "comment" and '"steps"' in t and ('"sampler"' in t or '"prompt"' in t):
        return True, "JSON comment containing generation parameters (steps/sampler/prompt)"
    return None


def analyze_png(data: bytes, st: Structure) -> tuple[MetadataGroup, list[tuple[str, str, str]]]:
    group = MetadataGroup("PNG CHUNKS", ItemState.PRESENT, location="PNG chunk stream")
    texts: list[tuple[str, str, str]] = []
    for seg in st.segments:
        if seg.name in ("IDAT",):
            continue
        cat = chunk_category(seg.name, seg.ident)
        if seg.name in ("tEXt", "zTXt", "iTXt"):
            keyword, text, note = png_text_chunk(data, seg)
            if seg.ident == "XMP":
                group.fields.append(MetadataField("PNG CHUNKS", f"{seg.name}:{keyword}", f"XMP packet, {len(text)} chars",
                                                  seg.name, "container"))
                continue
            cat = text_category(keyword)
            texts.append((keyword, text, seg.name))
            shown = text if len(text) <= 400 else text[:400] + f"... ({len(text)} chars)"
            group.fields.append(MetadataField("PNG CHUNKS", f"{seg.name}:{keyword}", shown + (f" [{note}]" if note else ""),
                                              seg.name, cat, raw_type=seg.name))
        else:
            desc = f"{seg.payload_length} bytes" + ("" if seg.crc_ok else " (CRC MISMATCH)")
            if seg.name == "IHDR" and "ihdr" in st.info:
                ih = st.info["ihdr"]
                desc = f"{ih['width']}x{ih['height']}, depth {ih['bit_depth']}, color type {ih['color_type']}, interlace {ih['interlace']}"
            elif seg.name == "caBX":
                desc = f"C2PA JUMBF manifest store, {seg.payload_length} bytes"
            group.fields.append(MetadataField("PNG CHUNKS", seg.name, desc, "chunk", cat))
    idat = st.info.get("idat_chunks", 0)
    group.notes.append(f"{idat} IDAT chunk(s), {st.info.get('idat_bytes', 0):,} bytes of compressed image data (not shown).")
    if st.trailing_bytes:
        group.notes.append(f"{st.trailing_bytes:,} bytes of data after IEND.")
    if any(s.crc_ok is False for s in st.segments):
        group.state = ItemState.INVALID
        group.notes.append("One or more chunks failed CRC verification.")
    return group, texts
