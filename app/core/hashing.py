"""Cryptographic hashing of files and decoded pixel buffers."""
from __future__ import annotations

import hashlib
from pathlib import Path

try:  # BLAKE3 is optional; absence is reported, never faked.
    import blake3 as _blake3  # type: ignore

    BLAKE3_AVAILABLE = True
except Exception:  # noqa: BLE001
    _blake3 = None
    BLAKE3_AVAILABLE = False

CHUNK = 1 << 20


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def blake3_bytes(data: bytes) -> str | None:
    if not BLAKE3_AVAILABLE:
        return None
    return _blake3.blake3(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def blake3_file(path: Path) -> str | None:
    if not BLAKE3_AVAILABLE:
        return None
    h = _blake3.blake3()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def file_hashes(data: bytes) -> dict:
    b3 = blake3_bytes(data)
    return {
        "sha256": sha256_bytes(data),
        "blake3": b3 or "",
        "blake3_state": "COMPUTED" if b3 else "UNAVAILABLE (blake3 module not installed)",
    }


def pixel_hash(array) -> str:
    """SHA-256 over a canonical decoded pixel buffer, including shape and dtype."""
    import numpy as np

    arr = np.ascontiguousarray(array)
    header = f"{arr.dtype.str}|{'x'.join(map(str, arr.shape))}|".encode("ascii")
    h = hashlib.sha256(header)
    h.update(memoryview(arr).cast("B"))
    return h.hexdigest()
