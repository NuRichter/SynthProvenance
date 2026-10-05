"""Controlled research transformations.

Each operation is a pure function of (decoded image, parameters) that returns
encoded bytes plus a factual list of actions taken. Nothing is assumed about
the outcome: pixel integrity is always *measured* afterwards by the
transformation service against the canonical decode of the original.

Metadata policy for pixel operations: outputs carry no metadata except the
ICC profile (``keep_icc``, default on) unless ``carry_metadata`` is enabled,
in which case the original EXIF and XMP blocks are copied verbatim. C2PA
manifests are never copied: a manifest cannot remain valid for re-encoded
bytes without re-signing, which this tool does not do.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageCms, PngImagePlugin

from app.core.image_loader import canonical_image, open_image_bytes
from app.core.image_writer import EXTENSIONS, FORMAT_CAPS, encode_as, encode_image, normalise_format


class TransformError(RuntimeError):
    pass


@dataclass
class ParamSpec:
    name: str
    label: str
    kind: str  # int / float / choice / bool
    default: object
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple = ()
    help: str = ""


@dataclass
class OpSpec:
    op: str
    label: str
    matrix_row: str
    description: str
    params: list[ParamSpec] = field(default_factory=list)
    pixel_operation: bool = True

    def defaults(self) -> dict:
        return {p.name: p.default for p in self.params}


_KEEP_ICC = ParamSpec("keep_icc", "Keep ICC profile", "bool", True, help="Embed the original ICC profile in the output.")
_CARRY = ParamSpec("carry_metadata", "Carry EXIF/XMP", "bool", False,
                   help="Copy the original EXIF and XMP blocks verbatim into the output. C2PA is never copied.")

OPERATIONS: dict[str, OpSpec] = {
    "metadata_sanitize": OpSpec(
        "metadata_sanitize", "Metadata-only sanitization", "METADATA SANITIZED",
        "Byte-level container rewrite. Selected metadata is removed; compressed image data is copied verbatim.",
        [], pixel_operation=False),
    "png_reencode": OpSpec(
        "png_reencode", "PNG re-encode", "PNG RE-ENCODE",
        "Decode and re-encode as PNG (lossless deflate) in the native pixel mode where PNG supports it.",
        [ParamSpec("compress_level", "Compression level", "int", 6, 0, 9), _KEEP_ICC, _CARRY]),
    "jpeg_reencode": OpSpec(
        "jpeg_reencode", "JPEG re-encode", "JPEG RE-ENCODE",
        "Decode and re-encode as baseline/progressive JPEG with the chosen quality and chroma subsampling.",
        [ParamSpec("quality", "Quality", "int", 90, 1, 100),
         ParamSpec("subsampling", "Chroma subsampling", "choice", "4:2:0", choices=("4:4:4", "4:2:2", "4:2:0")),
         ParamSpec("progressive", "Progressive", "bool", False), ParamSpec("optimize", "Optimize Huffman", "bool", False),
         _KEEP_ICC, _CARRY]),
    "webp_reencode": OpSpec(
        "webp_reencode", "WebP re-encode", "WEBP RE-ENCODE",
        "Decode and re-encode as WebP (lossy VP8 or lossless VP8L).",
        [ParamSpec("quality", "Quality", "int", 90, 0, 100), ParamSpec("lossless", "Lossless (VP8L)", "bool", False),
         ParamSpec("method", "Method (effort)", "int", 4, 0, 6), _KEEP_ICC, _CARRY]),
    "lossless_export": OpSpec(
        "lossless_export", "Lossless export", "LOSSLESS EXPORT",
        "Export through a lossless codec. Pixel preservation is verified afterwards, not assumed.",
        [ParamSpec("format", "Container", "choice", "PNG", choices=("PNG", "WEBP", "TIFF")), _KEEP_ICC, _CARRY]),
    "color_conversion": OpSpec(
        "color_conversion", "Color conversion", "COLOR CONVERSION",
        "Colour transform written to lossless PNG so that only the colour change is measured.",
        [ParamSpec("target", "Conversion", "choice", "grayscale",
                   choices=("grayscale", "srgb_from_icc", "cmyk_roundtrip", "drop_alpha"),
                   help="grayscale: ITU-R 601-2 luma. srgb_from_icc: ICC-managed conversion to sRGB. "
                        "cmyk_roundtrip: naive RGB->CMYK->RGB. drop_alpha: remove the alpha channel.")]),
    "resize": OpSpec(
        "resize", "Resize", "RESIZE", "Resample to a new resolution, written to lossless PNG.",
        [ParamSpec("scale", "Scale factor", "float", 0.5, 0.01, 4.0),
         ParamSpec("resample", "Resampling filter", "choice", "lanczos", choices=("lanczos", "bicubic", "bilinear", "box", "nearest")),
         _KEEP_ICC]),
    "crop": OpSpec(
        "crop", "Crop", "CROP", "Crop margins (percent of each dimension), written to lossless PNG.",
        [ParamSpec("left_pct", "Left %", "float", 10.0, 0, 49), ParamSpec("top_pct", "Top %", "float", 10.0, 0, 49),
         ParamSpec("right_pct", "Right %", "float", 10.0, 0, 49), ParamSpec("bottom_pct", "Bottom %", "float", 10.0, 0, 49),
         _KEEP_ICC]),
    "controlled_recompression": OpSpec(
        "controlled_recompression", "Controlled recompression", "RECOMPRESSION",
        "Repeated lossy encode/decode generations to study generation loss.",
        [ParamSpec("format", "Codec", "choice", "JPEG", choices=("JPEG", "WEBP")),
         ParamSpec("quality", "Quality", "int", 75, 1, 100), ParamSpec("generations", "Generations", "int", 3, 1, 50),
         _KEEP_ICC]),
    "c2pa_separation": OpSpec(
        "c2pa_separation", "C2PA / provenance data separation experiment", "C2PA EXPERIMENT",
        "Byte-level removal of the C2PA/JUMBF manifest store only (optionally also XMP provenance declarations). "
        "All other metadata and the compressed image data are copied verbatim.",
        [ParamSpec("include_xmp_declarations", "Also remove XMP provenance declarations", "bool", False,
                   help="Iptc4xmpExt:DigitalSourceType / AISystemUsed and c2pa: XMP properties.")],
        pixel_operation=False),
    "format_conversion": OpSpec(
        "format_conversion", "Format conversion (Save As)", "FORMAT CONVERSION",
        "Encode into PNG / JPEG / WEBP / TIFF / BMP with an explicit compression mode.",
        [ParamSpec("format", "Output format", "choice", "PNG", choices=("PNG", "JPEG", "WEBP", "TIFF", "BMP")),
         ParamSpec("compression", "Compression mode", "choice", "LOSSLESS", choices=("LOSSLESS", "LOSSY")),
         ParamSpec("quality", "Quality (lossy)", "int", 90, 1, 100), _KEEP_ICC, _CARRY,
         ParamSpec("source", "Source condition", "text", "ORIGINAL",
                   help="ORIGINAL or an earlier transformation id (e.g. T002). Metrics are always against ORIGINAL.")]),
    "format_chain": OpSpec(
        "format_chain", "Format conversion chain", "FORMAT CHAIN",
        "Sequential conversions, e.g. JPEG:LOSSY:90 > WEBP:LOSSY:90 > PNG:LOSSLESS. Every step is saved and measured.",
        [ParamSpec("steps", "Chain", "text", "JPEG:LOSSY:90 > WEBP:LOSSY:90 > PNG:LOSSLESS"), _KEEP_ICC, _CARRY],
        pixel_operation=False),
    "external_comparison": OpSpec(
        "external_comparison", "External file comparison", "EXTERNAL FILE",
        "Compare the original against a file processed outside SynthProvenance (e.g. a platform round-trip).",
        [], pixel_operation=False),
}

MATRIX_ROWS = ["ORIGINAL", "METADATA SANITIZED", "C2PA EXPERIMENT", "PNG RE-ENCODE", "JPEG RE-ENCODE", "WEBP RE-ENCODE",
               "COLOR CONVERSION", "RESIZE", "CROP", "LOSSLESS EXPORT"]
EXTRA_ROWS = ["RECOMPRESSION", "FORMAT CONVERSION", "FORMAT CHAIN", "EXTERNAL FILE"]
MATRIX_BATTERY = ["metadata_sanitize", "c2pa_separation", "png_reencode", "jpeg_reencode", "webp_reencode",
                  "color_conversion", "resize", "crop", "lossless_export"]
MAX_CHAIN_STEPS = 12


def parse_chain(text: str) -> list[dict]:
    """Parse 'JPEG:LOSSY:90 > WEBP:LOSSLESS > PNG' into validated steps."""
    parts = [p.strip() for p in str(text).replace("\u2192", ">").replace("->", ">").replace(",", ">").split(">") if p.strip()]
    if not parts:
        raise TransformError("Format chain is empty.")
    if len(parts) > MAX_CHAIN_STEPS:
        raise TransformError(f"Format chain is limited to {MAX_CHAIN_STEPS} steps.")
    steps = []
    for part in parts:
        bits = [b.strip() for b in part.split(":")]
        fmt = normalise_format(bits[0])
        caps = FORMAT_CAPS.get(fmt)
        if caps is None:
            raise TransformError(f"Unknown format {bits[0]!r} in chain (use PNG, JPEG, WEBP, TIFF, BMP).")
        mode = bits[1].upper() if len(bits) > 1 and bits[1] else caps["modes"][0]
        if mode not in caps["modes"]:
            raise TransformError(f"{fmt} does not support {mode} (supports {' / '.join(caps['modes'])}).")
        try:
            q = int(bits[2]) if len(bits) > 2 and bits[2] else 90
        except ValueError as exc:
            raise TransformError(f"Invalid quality in chain step {part!r}") from exc
        steps.append({"format": fmt, "compression": mode, "quality": max(1, min(100, q))})
    return steps

_RESAMPLE = {"lanczos": Image.Resampling.LANCZOS, "bicubic": Image.Resampling.BICUBIC,
             "bilinear": Image.Resampling.BILINEAR, "box": Image.Resampling.BOX, "nearest": Image.Resampling.NEAREST}


@dataclass
class TransformOutput:
    data: bytes
    format: str
    ext: str
    actions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    region: tuple[int, int, int, int] | None = None
    expect_lossless: bool = False


def validate_params(op: str, params: dict | None) -> dict:
    """Merge with defaults and clamp to the declared ranges. Unknown keys are dropped."""
    spec = OPERATIONS.get(op)
    if spec is None:
        raise TransformError(f"Unknown operation {op!r}")
    out = spec.defaults()
    for p in spec.params:
        if params is None or p.name not in params:
            continue
        v = params[p.name]
        try:
            if p.kind == "int":
                v = int(v)
            elif p.kind == "float":
                v = float(v)
            elif p.kind == "bool":
                v = bool(v)
            elif p.kind == "text":
                v = str(v)[:500]
            elif p.kind == "choice":
                v = str(v)
                if v not in p.choices:
                    raise TransformError(f"{p.label}: {v!r} is not one of {', '.join(p.choices)}")
        except (TypeError, ValueError) as exc:
            raise TransformError(f"{p.label}: invalid value {v!r}") from exc
        if p.minimum is not None and v < p.minimum:
            v = type(v)(p.minimum)
        if p.maximum is not None and v > p.maximum:
            v = type(v)(p.maximum)
        out[p.name] = v
    return out


# ------------------------------------------------------------------ helpers

def _clean(img: Image.Image) -> Image.Image:
    c = canonical_image(img).copy() if img.mode != "P" else img.copy()
    c.info = {}
    return c


def _to_8bit(img: Image.Image, actions: list[str]) -> Image.Image:
    if img.mode in ("I;16", "I;16B", "I;16L", "I"):
        arr = np.array(img, dtype=np.uint32)
        scale = 8 if img.mode.startswith("I;16") else max(0, int(arr.max()).bit_length() - 8)
        actions.append(f"{img.mode} reduced to 8-bit by right shift of {scale} bits")
        return Image.fromarray((arr >> scale).clip(0, 255).astype(np.uint8))
    if img.mode == "F":
        arr = np.asarray(img, dtype=np.float64)
        actions.append("32-bit float scaled from [0,1] to 8-bit")
        return Image.fromarray((arr.clip(0, 1) * 255 + 0.5).astype(np.uint8))
    return img


def _meta_kwargs(fmt: str, source_meta: dict, params: dict, actions: list[str]) -> dict:
    kw: dict = {}
    icc = source_meta.get("icc")
    if params.get("keep_icc", True) and icc:
        kw["icc_profile"] = icc
        actions.append(f"ICC profile embedded ({len(icc):,} bytes)")
    elif icc:
        actions.append("ICC profile NOT embedded (keep_icc disabled)")
    if params.get("carry_metadata"):
        exif, xmp = source_meta.get("exif"), source_meta.get("xmp")
        if exif:
            kw["exif"] = b"Exif\x00\x00" + exif if fmt in ("JPEG",) else exif
            actions.append(f"EXIF block copied verbatim ({len(exif):,} bytes)")
        if xmp:
            if fmt == "PNG":
                info = PngImagePlugin.PngInfo()
                info.add_itxt("XML:com.adobe.xmp", xmp.decode("utf-8", "replace"))
                kw["pnginfo"] = info
            elif fmt in ("JPEG", "WEBP"):
                kw["xmp"] = xmp
            elif fmt == "TIFF":
                kw["tiffinfo"] = {700: xmp}
            actions.append(f"XMP packet copied verbatim ({len(xmp):,} bytes)")
        if source_meta.get("has_c2pa"):
            actions.append("C2PA manifest NOT copied (cannot remain valid for re-encoded bytes without re-signing)")
    elif source_meta.get("exif") or source_meta.get("xmp"):
        actions.append("EXIF/XMP not carried (carry_metadata disabled)")
    return kw


def _png(img: Image.Image, source_meta: dict, params: dict, actions: list[str], notes: list[str],
         compress_level: int = 6) -> bytes:
    if img.mode not in ("1", "L", "LA", "I", "I;16", "P", "RGB", "RGBA"):
        actions.append(f"mode {img.mode} converted to RGB (not representable in PNG)")
        img = img.convert("RGB")
    kw = _meta_kwargs("PNG", source_meta, params, actions)
    tr = source_meta.get("transparency")
    if tr is not None and img.mode in ("P", "L", "RGB"):
        kw["transparency"] = tr
        actions.append("transparency entry preserved")
    return encode_image(img, "PNG", compress_level=compress_level, optimize=False, **kw)


def source_metadata(img: Image.Image, analysis_blocks: dict | None = None) -> dict:
    blocks = analysis_blocks or {}
    return {
        "icc": img.info.get("icc_profile") if isinstance(img.info.get("icc_profile"), bytes) else blocks.get("icc"),
        "exif": blocks.get("exif"),
        "xmp": blocks.get("xmp"),
        "transparency": img.info.get("transparency"),
        "has_c2pa": bool(blocks.get("has_c2pa")),
    }


# ---------------------------------------------------------------- operations

def run_pixel_operation(op: str, img: Image.Image, params: dict, source_meta: dict) -> TransformOutput:
    spec = OPERATIONS.get(op)
    if spec is None or not spec.pixel_operation:
        raise TransformError(f"{op!r} is not a pixel operation")
    params = validate_params(op, params)
    actions: list[str] = []
    notes: list[str] = []
    base = _clean(img)
    if canonical_image(img).mode != img.mode and img.mode != "P":
        actions.append(f"decoded {img.mode} expanded to canonical {base.mode}")

    if op == "format_conversion":
        fmt = normalise_format(params["format"])
        caps = FORMAT_CAPS[fmt]
        comp = params["compression"]
        if comp not in caps["modes"]:
            notes.append(f"{fmt} does not support {comp}; {caps['modes'][0]} used instead.")
            comp = caps["modes"][0]
        data, acts = encode_as(base, fmt, comp, params["quality"],
                               icc=source_meta.get("icc") if params["keep_icc"] else None,
                               exif=source_meta.get("exif") if params["carry_metadata"] else None,
                               xmp=source_meta.get("xmp") if params["carry_metadata"] else None,
                               transparency=source_meta.get("transparency"))
        actions.extend(acts)
        if params["carry_metadata"] and source_meta.get("has_c2pa"):
            actions.append("C2PA manifest NOT copied (cannot remain valid for re-encoded bytes without re-signing)")
        if caps["warning"] and comp == "LOSSY" or fmt == "JPEG":
            notes.append(f"WARNING: {caps['warning']}")
        return TransformOutput(data, fmt, caps["ext"], actions, notes, expect_lossless=(comp == "LOSSLESS"))

    if op == "png_reencode":
        data = _png(base, source_meta, params, actions, notes, params["compress_level"])
        return TransformOutput(data, "PNG", ".png", actions + [f"PNG deflate level {params['compress_level']}"], notes,
                               expect_lossless=True)

    if op == "jpeg_reencode":
        work = _to_8bit(base, actions)
        if work.mode not in ("RGB", "L", "CMYK"):
            actions.append(f"mode {work.mode} converted to RGB (JPEG has no alpha / palette); alpha discarded")
            work = work.convert("RGB")
        kw = _meta_kwargs("JPEG", source_meta, params, actions)
        sub = params["subsampling"] if work.mode == "RGB" else None
        extra = {"subsampling": sub} if sub else {}
        data = encode_image(work, "JPEG", quality=params["quality"], progressive=params["progressive"],
                            optimize=params["optimize"], **extra, **kw)
        actions.append(f"JPEG quality {params['quality']}, subsampling {sub or 'n/a'}, "
                       f"{'progressive' if params['progressive'] else 'baseline'}")
        return TransformOutput(data, "JPEG", ".jpg", actions, notes)

    if op == "webp_reencode":
        work = _to_8bit(base, actions)
        if work.mode not in ("RGB", "RGBA"):
            actions.append(f"mode {work.mode} converted to {'RGBA' if 'A' in work.mode else 'RGB'} (WebP is RGB/RGBA only)")
            work = work.convert("RGBA" if "A" in work.mode or work.mode == "P" else "RGB")
        kw = _meta_kwargs("WEBP", source_meta, params, actions)
        if params["lossless"]:
            data = encode_image(work, "WEBP", lossless=True, quality=params["quality"], method=params["method"], exact=True, **kw)
            actions.append(f"WebP lossless (VP8L), effort {params['quality']}, method {params['method']}, exact=True")
        else:
            data = encode_image(work, "WEBP", quality=params["quality"], method=params["method"], **kw)
            actions.append(f"WebP lossy (VP8), quality {params['quality']}, method {params['method']}")
        return TransformOutput(data, "WEBP", ".webp", actions, notes, expect_lossless=params["lossless"])

    if op == "lossless_export":
        fmt = params["format"]
        if fmt == "PNG":
            data = _png(base, source_meta, params, actions, notes, 9)
            actions.append("PNG deflate level 9")
            return TransformOutput(data, "PNG", ".png", actions, notes, expect_lossless=True)
        if fmt == "WEBP":
            work = _to_8bit(base, actions)
            if work.mode not in ("RGB", "RGBA"):
                actions.append(f"mode {work.mode} converted for WebP")
                work = work.convert("RGBA" if "A" in work.mode else "RGB")
            kw = _meta_kwargs("WEBP", source_meta, params, actions)
            data = encode_image(work, "WEBP", lossless=True, quality=100, method=6, exact=True, **kw)
            actions.append("WebP lossless (VP8L), effort 100, method 6, exact=True")
            return TransformOutput(data, "WEBP", ".webp", actions, notes, expect_lossless=True)
        kw = _meta_kwargs("TIFF", source_meta, params, actions)
        work = base if base.mode in ("1", "L", "LA", "RGB", "RGBA", "CMYK", "I;16", "I", "F", "P") else base.convert("RGB")
        data = encode_image(work, "TIFF", compression="tiff_lzw", **kw)
        actions.append("TIFF LZW")
        return TransformOutput(data, "TIFF", ".tif", actions, notes, expect_lossless=True)

    if op == "color_conversion":
        target = params["target"]
        work = base
        out_meta = dict(source_meta)
        if target == "grayscale":
            work = _to_8bit(base, actions)
            work = work.convert("L") if work.mode != "L" else work
            actions.append("converted to 8-bit grayscale, L = 0.299 R + 0.587 G + 0.114 B (ITU-R 601-2)")
            out_meta["icc"] = None
            actions.append("colour ICC profile dropped (incompatible with grayscale)")
        elif target == "srgb_from_icc":
            icc = source_meta.get("icc")
            work = _to_8bit(base, actions)
            if work.mode not in ("RGB", "RGBA", "CMYK", "L"):
                work = work.convert("RGB")
            srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
            if icc:
                try:
                    src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
                    out_mode = "RGBA" if work.mode == "RGBA" else "RGB"
                    work = ImageCms.profileToProfile(work, src, srgb, outputMode=out_mode,
                                                     renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC)
                    actions.append("ICC-managed conversion embedded profile -> sRGB (relative colorimetric)")
                except (ImageCms.PyCMSError, OSError, ValueError) as exc:
                    notes.append(f"ICC conversion failed ({exc}); pixels left unchanged")
            else:
                notes.append("No embedded ICC profile: source treated as sRGB, so the conversion is an identity.")
            out_meta["icc"] = srgb.tobytes()
            actions.append("sRGB profile embedded")
        elif target == "cmyk_roundtrip":
            work = _to_8bit(base, actions).convert("RGB").convert("CMYK").convert("RGB")
            actions.append("naive RGB -> CMYK -> RGB round trip (Pillow, no ICC)")
        elif target == "drop_alpha":
            if "A" in base.mode or base.mode == "P":
                work = base.convert("RGB" if base.mode != "LA" else "L")
                actions.append(f"alpha channel removed ({base.mode} -> {work.mode})")
            else:
                notes.append("Image has no alpha channel; drop_alpha is an identity operation.")
        data = _png(work, out_meta, {"keep_icc": True}, actions, notes, 6)
        return TransformOutput(data, "PNG", ".png", actions, notes)

    if op == "resize":
        w, h = base.size
        nw, nh = max(1, round(w * params["scale"])), max(1, round(h * params["scale"]))
        if nw * nh > 250_000_000:
            raise TransformError("Requested size exceeds the 250 MP safety limit.")
        work = base
        if work.mode == "P":
            work = canonical_image(work)
        work = work.resize((nw, nh), _RESAMPLE[params["resample"]])
        actions.append(f"resized {w}x{h} -> {nw}x{nh} ({params['resample']})")
        data = _png(work, source_meta, params, actions, notes, 6)
        return TransformOutput(data, "PNG", ".png", actions, notes)

    if op == "crop":
        w, h = base.size
        left = int(round(w * params["left_pct"] / 100.0))
        top = int(round(h * params["top_pct"] / 100.0))
        right = w - int(round(w * params["right_pct"] / 100.0))
        bottom = h - int(round(h * params["bottom_pct"] / 100.0))
        if right - left < 1 or bottom - top < 1:
            raise TransformError("Crop margins leave no pixels.")
        box = (left, top, right, bottom)
        work = base.crop(box)
        actions.append(f"cropped to box {box} ({right - left}x{bottom - top})")
        data = _png(work, source_meta, params, actions, notes, 6)
        return TransformOutput(data, "PNG", ".png", actions, notes, region=box)

    if op == "controlled_recompression":
        fmt = params["format"]
        work = _to_8bit(base, actions)
        work = work.convert("RGB") if work.mode not in ("RGB", "L") else work
        sizes = []
        data = b""
        for gen in range(params["generations"]):
            kw = _meta_kwargs(fmt, source_meta, {"keep_icc": params["keep_icc"]}, []) if gen == params["generations"] - 1 else {}
            data = encode_image(work, fmt, quality=params["quality"], **kw)
            sizes.append(len(data))
            work = open_image_bytes(data)
            work.load()
        actions.append(f"{params['generations']} generation(s) of {fmt} quality {params['quality']}; "
                       f"encoded sizes: {', '.join(f'{s:,}' for s in sizes)} bytes")
        if params["keep_icc"] and source_meta.get("icc"):
            actions.append("ICC profile embedded in the final generation")
        return TransformOutput(data, fmt, EXTENSIONS[fmt], actions, notes)

    raise TransformError(f"Operation {op!r} is not implemented")  # pragma: no cover
