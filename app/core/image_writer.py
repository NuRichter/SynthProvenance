"""Atomic, bounded writing of transformation outputs."""
from __future__ import annotations

import io
import os
from pathlib import Path

from PIL import Image


def atomic_write_bytes(path: Path, data: bytes) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".partial")
    with tmp.open("wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(path)
    return path


def encode_image(img: Image.Image, fmt: str, **params) -> bytes:
    """Encode with Pillow into memory. Only explicitly passed metadata is written."""
    buf = io.BytesIO()
    img.save(buf, format=fmt, **params)
    return buf.getvalue()


EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "TIFF": ".tif", "BMP": ".bmp", "GIF": ".gif"}


# ------------------------------------------------------------ multi-format export

PNG_MODES = ("1", "L", "LA", "I", "I;16", "P", "RGB", "RGBA")
FORMAT_ALIASES = {"JPG": "JPEG", "TIF": "TIFF"}

FORMAT_CAPS: dict[str, dict] = {
    "PNG": {"label": "PNG (*.png)", "ext": ".png", "filter": "PNG (*.png)", "modes": ("LOSSLESS",), "quality": False,
            "compression": "Deflate (zlib), lossless", "alpha": "YES (RGBA, LA, palette transparency)",
            "icc": "Embedded as iCCP when 'Keep ICC' is on", "bit_depth": "1/8/16-bit preserved",
            "metadata": "Stripped by default. EXIF (eXIf) and XMP (iTXt) copied only with 'Carry EXIF/XMP'. C2PA never copied.",
            "warning": ""},
    "JPEG": {"label": "JPEG (*.jpg / *.jpeg)", "ext": ".jpg", "filter": "JPEG (*.jpg *.jpeg)", "modes": ("LOSSY",),
             "quality": True, "compression": "Baseline DCT, lossy", "alpha": "NO (alpha channel discarded)",
             "icc": "Embedded as APP2 ICC_PROFILE when 'Keep ICC' is on", "bit_depth": "8-bit only (16-bit reduced)",
             "metadata": "Stripped by default. EXIF (APP1) and XMP (APP1) copied only with 'Carry EXIF/XMP'. C2PA never copied.",
             "warning": "JPEG encoding may alter pixel values."},
    "WEBP": {"label": "WEBP (*.webp)", "ext": ".webp", "filter": "WEBP (*.webp)", "modes": ("LOSSLESS", "LOSSY"),
             "quality": True, "compression": "VP8L (lossless) or VP8 (lossy)", "alpha": "YES",
             "icc": "Embedded as ICCP chunk when 'Keep ICC' is on", "bit_depth": "8-bit only (16-bit reduced)",
             "metadata": "Stripped by default. EXIF and XMP chunks copied only with 'Carry EXIF/XMP'. C2PA never copied.",
             "warning": "Lossy WebP encoding may alter pixel values."},
    "TIFF": {"label": "TIFF (*.tif / *.tiff)", "ext": ".tif", "filter": "TIFF (*.tif *.tiff)", "modes": ("LOSSLESS", "LOSSY"),
             "quality": True, "compression": "Adobe Deflate (lossless) or JPEG-in-TIFF (lossy)", "alpha": "YES (lossless mode)",
             "icc": "Embedded as tag 34675 when 'Keep ICC' is on", "bit_depth": "1/8/16/32-bit preserved (lossless mode)",
             "metadata": "Stripped by default. EXIF and XMP (tag 700) copied only with 'Carry EXIF/XMP'. C2PA never copied.",
             "warning": "JPEG-in-TIFF (lossy) encoding may alter pixel values."},
    "BMP": {"label": "BMP (*.bmp)", "ext": ".bmp", "filter": "BMP (*.bmp)", "modes": ("LOSSLESS",), "quality": False,
            "compression": "Uncompressed", "alpha": "NO (Pillow's BMP writer stores 24-bit; alpha discarded)",
            "icc": "NOT SUPPORTED (profile dropped)", "bit_depth": "1/8-bit palette or 24-bit",
            "metadata": "NOT SUPPORTED (no EXIF/XMP/C2PA container)", "warning": ""},
}


def normalise_format(fmt: str) -> str:
    f = str(fmt).upper().strip().lstrip(".")
    return FORMAT_ALIASES.get(f, f)


def reduce_to_8bit(img: Image.Image, actions: list[str]) -> Image.Image:
    import numpy as np

    if img.mode in ("I;16", "I;16B", "I;16L", "I;16N", "I"):
        arr = np.array(img, dtype=np.uint32)
        shift = 8 if img.mode.startswith("I;16") else max(0, int(arr.max()).bit_length() - 8)
        actions.append(f"{img.mode} reduced to 8-bit (right shift {shift}): NOT lossless")
        return Image.fromarray((arr >> shift).clip(0, 255).astype(np.uint8))
    if img.mode == "F":
        arr = np.asarray(img, dtype=np.float64)
        actions.append("32-bit float scaled [0,1] -> 8-bit: NOT lossless")
        return Image.fromarray((arr.clip(0, 1) * 255 + 0.5).astype(np.uint8))
    return img


def pixel_expectation(fmt: str, compression: str, src_mode: str) -> str:
    fmt, compression = normalise_format(fmt), compression.upper()
    if compression == "LOSSY":
        return "LOSSY: pixel preservation is NOT claimed. Measured metrics are recorded after export."
    caveats = []
    if src_mode.startswith("I;16") or src_mode in ("I", "F"):
        if fmt in ("WEBP", "BMP", "JPEG"):
            caveats.append("source is >8-bit and will be reduced")
    if ("A" in src_mode or src_mode == "P") and fmt == "BMP":
        caveats.append("alpha / transparency will be discarded")
    if src_mode == "CMYK" and fmt in ("PNG", "WEBP", "BMP"):
        caveats.append("CMYK will be converted to RGB")
    base = "LOSSLESS: preservation expected, then VERIFIED mathematically after export"
    return base + (f" (caveat: {'; '.join(caveats)})" if caveats else "")


def encode_as(img: Image.Image, fmt: str, compression: str = "LOSSLESS", quality: int = 90, icc: bytes | None = None,
              exif: bytes | None = None, xmp: bytes | None = None, transparency=None) -> tuple[bytes, list[str]]:
    """Encode ``img`` into one of FORMAT_CAPS. Returns (bytes, factual action list)."""
    from PIL import PngImagePlugin

    fmt = normalise_format(fmt)
    caps = FORMAT_CAPS.get(fmt)
    if caps is None:
        raise ValueError(f"Unsupported output format {fmt!r}. Supported: {', '.join(FORMAT_CAPS)}")
    compression = compression.upper()
    if compression not in caps["modes"]:
        raise ValueError(f"{fmt} supports {' / '.join(caps['modes'])} only")
    quality = int(max(1, min(100, int(quality))))
    actions: list[str] = []
    work = img
    kw: dict = {}
    if fmt == "PNG":
        if work.mode not in PNG_MODES:
            target = "RGBA" if "A" in work.mode else "RGB"
            actions.append(f"mode {work.mode} converted to {target} (not representable in PNG)")
            work = work.convert(target)
        if icc:
            kw["icc_profile"] = icc
        if exif:
            kw["exif"] = exif
        if xmp:
            info = PngImagePlugin.PngInfo()
            info.add_itxt("XML:com.adobe.xmp", xmp.decode("utf-8", "replace"))
            kw["pnginfo"] = info
        if transparency is not None and work.mode in ("P", "L", "RGB"):
            kw["transparency"] = transparency
            actions.append("transparency entry preserved")
        data = encode_image(work, "PNG", compress_level=6, **kw)
        actions.append("PNG deflate level 6 (lossless container)")
    elif fmt == "JPEG":
        work = reduce_to_8bit(work, actions)
        if work.mode not in ("RGB", "L", "CMYK"):
            actions.append(f"mode {work.mode} converted to RGB (JPEG has no alpha/palette): alpha discarded")
            work = work.convert("RGB")
        if icc:
            kw["icc_profile"] = icc
        if exif:
            kw["exif"] = b"Exif\x00\x00" + exif
        if xmp:
            kw["xmp"] = xmp
        data = encode_image(work, "JPEG", quality=quality, **kw)
        actions.append(f"JPEG baseline, quality {quality}, Pillow default chroma subsampling (LOSSY)")
    elif fmt == "WEBP":
        work = reduce_to_8bit(work, actions)
        if work.mode not in ("RGB", "RGBA"):
            target = "RGBA" if ("A" in work.mode or (work.mode == "P" and transparency is not None)) else "RGB"
            actions.append(f"mode {work.mode} converted to {target} (WebP is RGB/RGBA)")
            work = work.convert(target)
        if icc:
            kw["icc_profile"] = icc
        if exif:
            kw["exif"] = exif
        if xmp:
            kw["xmp"] = xmp
        if compression == "LOSSLESS":
            data = encode_image(work, "WEBP", lossless=True, quality=100, method=6, exact=True, **kw)
            actions.append("WebP VP8L lossless, effort 100, method 6, exact=True")
        else:
            data = encode_image(work, "WEBP", quality=quality, method=4, **kw)
            actions.append(f"WebP VP8 lossy, quality {quality}, method 4 (LOSSY)")
    elif fmt == "TIFF":
        if icc:
            kw["icc_profile"] = icc
        if exif:
            kw["exif"] = exif
        if xmp:
            kw["tiffinfo"] = {700: xmp}
        if compression == "LOSSLESS":
            if work.mode not in ("1", "L", "LA", "RGB", "RGBA", "CMYK", "I;16", "I", "F", "P"):
                actions.append(f"mode {work.mode} converted to RGB")
                work = work.convert("RGB")
            data = encode_image(work, "TIFF", compression="tiff_adobe_deflate", **kw)
            actions.append("TIFF Adobe Deflate (lossless)")
        else:
            work = reduce_to_8bit(work, actions)
            if work.mode not in ("RGB", "L"):
                actions.append(f"mode {work.mode} converted to RGB for JPEG-in-TIFF: alpha discarded")
                work = work.convert("RGB")
            data = encode_image(work, "TIFF", compression="jpeg", quality=quality, **kw)
            actions.append(f"TIFF with JPEG compression, quality {quality} (LOSSY)")
    else:  # BMP
        work = reduce_to_8bit(work, actions)
        if work.mode not in ("1", "L", "P", "RGB"):
            actions.append(f"mode {work.mode} converted to RGB (BMP writer is 24-bit): alpha discarded")
            work = work.convert("RGB")
        if work.mode == "P" and transparency is not None:
            actions.append("palette transparency discarded (BMP has no transparency)")
        if icc or exif or xmp:
            actions.append("ICC / EXIF / XMP dropped (not supported by BMP)")
        data = encode_image(work, "BMP")
        actions.append("BMP uncompressed")
    return data, actions
