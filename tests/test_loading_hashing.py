import io
import struct
import zlib

import numpy as np
import pytest
from PIL import Image

from app.core import image_memory
from app.core.hashing import blake3_bytes, pixel_hash, sha256_bytes
from app.core.image_loader import ImageLoadError, load_image, open_image_bytes, to_array
from app.core.metadata_engine import analyze_bytes


def test_all_fixtures_load(fx):
    for name, data in fx.items():
        img = open_image_bytes(data)
        assert img.size[0] > 0 and img.size[1] > 0, name


def test_known_hash_vectors():
    assert sha256_bytes(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    b3 = blake3_bytes(b"abc")
    assert b3 is None or b3 == "6437b3ac38465133ffb63b75273a8db548c558465d79db03fd359c6cd5bd9d85"


def test_pixel_hash_depends_on_shape_and_dtype():
    a = np.zeros((2, 3, 1), np.uint8)
    assert pixel_hash(a) != pixel_hash(a.reshape(3, 2, 1))
    assert pixel_hash(a) != pixel_hash(a.astype(np.uint16))


def test_truncated_and_garbage_rejected(fx):
    with pytest.raises(ImageLoadError):
        open_image_bytes(fx["fixture_plain.png"][:120])
    with pytest.raises(ImageLoadError):
        open_image_bytes(b"not an image at all")


def test_empty_and_unsupported_files(tmp_path):
    (tmp_path / "empty.png").write_bytes(b"")
    (tmp_path / "x.txt").write_bytes(b"hello world, not an image")
    for n in ("empty.png", "x.txt", "missing.png"):
        with pytest.raises(ImageLoadError):
            load_image(tmp_path / n)


def test_extension_is_not_trusted(tmp_path, fx):
    p = tmp_path / "actually_png.jpg"
    p.write_bytes(fx["fixture_plain.png"])
    assert load_image(p).format == "PNG"


def _png_header_only(w, h):
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)  # noqa: E731
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00" * 10)) + chunk(b"IEND", b"")


def test_memory_budget_refuses_instead_of_downscaling():
    with pytest.raises(ImageLoadError) as e:
        open_image_bytes(_png_header_only(200_000, 200_000))
    assert "does not downscale" in str(e.value) or "limit" in str(e.value).lower() or "memory" in str(e.value).lower()


def test_budget_math(monkeypatch):
    monkeypatch.setattr(image_memory, "system_memory", lambda: {"total": 8 << 30, "available": 1 << 30})
    assert image_memory.check_decode_budget(4000, 3000, "RGB")["decision"] == "admitted"
    with pytest.raises(image_memory.MemoryBudgetError):
        image_memory.check_decode_budget(40000, 30000, "RGB")


def test_high_resolution_full_res_roundtrip():
    from app.core.synthetic import pattern
    from app.core.pixel_integrity import compare_images

    img = pattern(6000, 4000)
    buf = io.BytesIO()
    img.save(buf, "PNG", compress_level=1)
    a = analyze_bytes(buf.getvalue(), "", "big.png")
    assert (a.info.width, a.info.height, a.info.pixel_count) == (6000, 4000, 24_000_000)
    r = compare_images(a.image, img)
    assert r.verdict == "PIXEL-EXACT" and r.changed_pixels == 0
    assert to_array(a.image).shape == (4000, 6000, 3)


def test_16bit_and_palette_canonical(fx):
    a = analyze_bytes(fx["fixture_16bit.png"], "", "x")
    assert a.info.mode.startswith("I;16") and a.info.bit_depth == "16-bit"
    p = open_image_bytes(fx["fixture_palette.png"])
    assert to_array(p).shape[2] == 4  # palette with transparency -> RGBA canonical
