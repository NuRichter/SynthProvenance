"""Encoding / compression characteristics."""
from __future__ import annotations

from PIL import Image

from app.analyzers.jpeg_analyzer import estimate_quality, quant_tables
from app.core.containers import VP8X_ALPHA, VP8X_ANIM, Structure

PNG_COLOR = {0: "grayscale", 2: "truecolor RGB", 3: "indexed (palette)", 4: "grayscale + alpha", 6: "truecolor RGBA"}


def analyze_compression(fmt: str, data: bytes, st: Structure, img: Image.Image) -> dict:
    w, h = img.size
    bands = len(img.getbands())
    out: dict = {"format": fmt, "file_bytes": len(data)}
    bpp_file = len(data) * 8 / max(w * h, 1)
    out["bits_per_pixel_file"] = round(bpp_file, 4)
    raw_bytes = w * h * bands * (2 if img.mode.startswith("I;16") else 1)
    out["raw_bytes_estimate"] = raw_bytes
    out["compression_ratio"] = round(raw_bytes / max(len(data), 1), 3)
    summary = fmt
    if fmt == "JPEG":
        sof = st.info.get("sof", {})
        out.update({
            "process": sof.get("process", "UNKNOWN"), "precision": sof.get("precision"),
            "chroma_subsampling": sof.get("subsampling", "UNKNOWN"), "components": len(sof.get("components", [])),
            "scans": st.info.get("scans"), "restart_interval": st.info.get("restart_interval", 0),
            "arithmetic_coding": sof.get("marker") in ("SOF9", "SOF10", "SOF11", "SOF13", "SOF14", "SOF15"),
        })
        tables = quant_tables(data, st)
        for t in tables:
            t["quality_estimate"] = estimate_quality(t["natural_order"], chroma=t["id"] > 0)
        out["quantization_tables"] = tables
        q = tables[0]["quality_estimate"]["ijg_equivalent_quality"] if tables else None
        summary = f"JPEG {out['process']}, {out['chroma_subsampling']}" + (f", IJG-equivalent Q~{q} (estimate)" if q else "")
    elif fmt == "PNG":
        ih = st.info.get("ihdr", {})
        out.update({
            "color_type": PNG_COLOR.get(ih.get("color_type"), "UNKNOWN"), "bit_depth": ih.get("bit_depth"),
            "interlace": "Adam7" if ih.get("interlace") == 1 else "none", "method": "deflate (zlib)",
            "idat_chunks": st.info.get("idat_chunks"), "idat_bytes": st.info.get("idat_bytes"),
        })
        summary = f"PNG deflate (lossless), {out['color_type']}, {out['bit_depth']}-bit, interlace {out['interlace']}"
    elif fmt == "WEBP":
        flags = st.info.get("vp8x", {}).get("flags", 0)
        out.update({
            "bitstream": st.info.get("bitstream", "UNKNOWN"), "alpha": bool(flags & VP8X_ALPHA) or img.mode == "RGBA",
            "animation": bool(flags & VP8X_ANIM), "extended_format": "vp8x" in st.info,
        })
        summary = f"WebP {out['bitstream']}"
    else:
        comp = img.info.get("compression")
        out["codec"] = str(comp) if comp else "UNKNOWN"
        summary = f"{fmt} ({out['codec']})"
    out["summary"] = summary
    return out
