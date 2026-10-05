"""Safe image loading and canonical pixel decoding.

Canonical decode rules (documented in docs/METHODOLOGY.md):
* only frame 0 of multi-frame files is decoded;
* EXIF orientation is NOT applied (stored pixel order is compared);
* palette images are expanded to RGB, or RGBA when a transparency entry exists;
* bilevel images are expanded to 8-bit L (0/255);
* 16-bit, 32-bit integer and float modes keep their native precision.
"""
from __future__ import annotations

import io
import math
import struct
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFile, UnidentifiedImageError

from app.core.hashing import file_hashes, pixel_hash
from app.utils.validation import DEFAULT_MAX_FILE_BYTES, DEFAULT_MAX_MEGAPIXELS, InputValidationError, sniff_format, validate_input_file

ImageFile.LOAD_TRUNCATED_IMAGES = False

MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "TIFF": "image/tiff", "BMP": "image/bmp", "GIF": "image/gif"}


class ImageLoadError(RuntimeError):
    pass


_max_megapixels = DEFAULT_MAX_MEGAPIXELS


def set_max_megapixels(mp: float) -> None:
    global _max_megapixels
    _max_megapixels = float(mp)


def _limit_pixels() -> int:
    return int(_max_megapixels * 1_000_000) if _max_megapixels and _max_megapixels > 0 else 0


@dataclass
class LoadedImage:
    path: Path
    data: bytes
    format: str
    image: Image.Image
    hashes: dict

    @property
    def size(self) -> tuple[int, int]:
        return self.image.size


def read_file_bytes(path: str | Path, max_bytes: int = DEFAULT_MAX_FILE_BYTES) -> tuple[Path, bytes]:
    p = validate_input_file(path, max_bytes)
    from app.utils.memory import system_memory

    avail = system_memory().get("available")
    size = p.stat().st_size
    if avail and size > avail * 0.5:
        raise InputValidationError(
            f"File is {size / 2**20:.0f} MiB but only {avail / 2**20:.0f} MiB of RAM is available; "
            "reading it safely is not possible on this machine right now.")
    return p, p.read_bytes()


def open_image_bytes(data: bytes) -> Image.Image:
    """Decode bytes with Pillow under a pixel budget. Raises ImageLoadError."""
    fmt = sniff_format(data[:16])
    if fmt is None:
        raise ImageLoadError("Unrecognised image container (magic bytes do not match a supported format).")
    previous = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = _limit_pixels() or None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            probe = Image.open(io.BytesIO(data))
            w, h = probe.size
            if w <= 0 or h <= 0:
                raise ImageLoadError("Image declares zero width or height.")
            limit = _limit_pixels()
            if limit and w * h > limit:
                raise ImageLoadError(
                    f"Image is {w}x{h} ({w * h / 1e6:.1f} MP), above the configured {_max_megapixels:.0f} MP limit "
                    "(Settings > Maximum megapixels; 0 = memory-based)."
                )
            from app.core.image_memory import MemoryBudgetError, check_decode_budget

            try:
                check_decode_budget(w, h, probe.mode)
            except MemoryBudgetError as exc:
                raise ImageLoadError(str(exc)) from exc
            probe.verify()
            img = Image.open(io.BytesIO(data))
            img.seek(0)
            img.load()
            return img
    except ImageLoadError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageLoadError(f"Decompression-bomb protection triggered: {exc}") from exc
    except UnidentifiedImageError as exc:
        raise ImageLoadError("Pillow could not identify the image data.") from exc
    except MemoryError as exc:
        raise ImageLoadError("Not enough memory to decode this image.") from exc
    except (OSError, SyntaxError, ValueError, EOFError, struct.error) as exc:
        raise ImageLoadError(f"Image data is corrupted or truncated: {exc}") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = previous


def load_image(path: str | Path, max_bytes: int = DEFAULT_MAX_FILE_BYTES) -> LoadedImage:
    try:
        p, data = read_file_bytes(path, max_bytes)
    except InputValidationError as exc:
        raise ImageLoadError(str(exc)) from exc
    img = open_image_bytes(data)
    return LoadedImage(p, data, sniff_format(data[:16]) or "UNKNOWN", img, file_hashes(data))


def canonical_image(img: Image.Image) -> Image.Image:
    """Return frame 0 in a canonical mode for comparison (see module docstring)."""
    try:
        img.seek(0)
    except EOFError:
        pass
    mode = img.mode
    if mode == "P" or mode == "PA":
        has_alpha = mode == "PA" or "transparency" in img.info
        return img.convert("RGBA" if has_alpha else "RGB")
    if mode == "1":
        return img.convert("L")
    if mode in ("L", "LA", "RGB", "RGBA", "CMYK", "I;16", "I;16B", "I;16L", "I", "F"):
        return img
    if mode in ("I;16N",):
        return img.convert("I")
    if mode in ("RGBX", "RGBa", "La"):
        return img.convert("RGBA")
    return img.convert("RGB")


def to_array(img: Image.Image) -> np.ndarray:
    """Canonical image -> HxWxC numpy array (native dtype)."""
    canon = canonical_image(img)
    if canon.mode in ("I;16", "I;16B", "I;16L"):
        arr = np.array(canon, dtype=np.uint16)
    else:
        arr = np.asarray(canon)
    if arr.ndim == 2:
        arr = arr[:, :, None]
    return arr


def bit_depth_of(mode: str) -> str:
    return {
        "1": "1-bit", "L": "8-bit", "P": "8-bit palette", "RGB": "8-bit/channel", "RGBA": "8-bit/channel",
        "LA": "8-bit/channel", "CMYK": "8-bit/channel", "YCbCr": "8-bit/channel", "I;16": "16-bit",
        "I;16B": "16-bit", "I;16L": "16-bit", "I": "32-bit integer", "F": "32-bit float",
    }.get(mode, "UNKNOWN")


def data_range_for(arr: np.ndarray) -> float:
    if arr.dtype == np.uint8:
        return 255.0
    if arr.dtype == np.uint16:
        return 65535.0
    if np.issubdtype(arr.dtype, np.floating):
        return 1.0
    return float(max(1, int(arr.max()) - int(arr.min())))


def aspect_ratio(w: int, h: int) -> str:
    if w <= 0 or h <= 0:
        return "UNKNOWN"
    g = math.gcd(w, h)
    return f"{w // g}:{h // g} ({w / h:.4f})"


def compute_pixel_hash(img: Image.Image) -> str:
    return pixel_hash(to_array(img))


def frame_count(img: Image.Image) -> int:
    try:
        return int(getattr(img, "n_frames", 1) or 1)
    except Exception:  # noqa: BLE001
        return 1
