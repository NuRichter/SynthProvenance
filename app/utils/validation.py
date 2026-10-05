"""Input validation for untrusted files."""
from __future__ import annotations

import os
from pathlib import Path

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".jpe", ".jfif", ".png", ".webp", ".tif", ".tiff", ".bmp", ".gif"}
DEFAULT_MAX_FILE_BYTES = 4 * 1024 * 1024 * 1024  # configurable; memory budget is checked separately
DEFAULT_MAX_MEGAPIXELS = 0  # 0 = no fixed limit, decode admitted by available-memory budget


class InputValidationError(ValueError):
    """Raised when an input file is rejected before decoding."""


def sniff_format(header: bytes) -> str | None:
    """Identify a container by magic bytes. Extensions are never trusted."""
    if header.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "WEBP"
    if header[:4] in (b"II*\x00", b"MM\x00*"):
        return "TIFF"
    if header.startswith(b"BM"):
        return "BMP"
    if header[:6] in (b"GIF87a", b"GIF89a"):
        return "GIF"
    return None


def validate_input_file(path: str | os.PathLike, max_bytes: int = DEFAULT_MAX_FILE_BYTES) -> Path:
    p = Path(path)
    try:
        p = p.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise InputValidationError(f"File not found: {path}") from exc
    if not p.is_file():
        raise InputValidationError(f"Not a regular file: {p}")
    size = p.stat().st_size
    if size == 0:
        raise InputValidationError("File is empty (0 bytes).")
    if size > max_bytes:
        raise InputValidationError(
            f"File is {size / 1048576:.1f} MiB, above the configured limit of {max_bytes / 1048576:.0f} MiB."
        )
    try:
        with p.open("rb") as fh:
            header = fh.read(16)
    except OSError as exc:
        raise InputValidationError(f"File is not readable: {exc}") from exc
    if sniff_format(header) is None:
        raise InputValidationError(
            "Unsupported or unrecognised format. Supported containers: JPEG, PNG, WebP, TIFF, BMP, GIF."
        )
    return p


def clamp(value, lo, hi):
    return max(lo, min(hi, value))
