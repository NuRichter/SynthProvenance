import io

import numpy as np
import pytest
from PIL import Image

from app.core.image_loader import open_image_bytes
from app.core.image_writer import FORMAT_CAPS, encode_as
from app.core.pixel_integrity import compare_images
from app.core.synthetic import pattern
from app.core.transform_engine import TransformError, parse_chain


def test_identical_is_exact():
    a = pattern(40, 30)
    r = compare_images(a, a.copy())
    assert r.verdict == "PIXEL-EXACT" and r.psnr_infinite and r.ssim == pytest.approx(1.0)


def test_single_pixel_change_measured():
    a = pattern(40, 30)
    arr = np.array(a)
    arr[5, 7, 1] = (int(arr[5, 7, 1]) + 3) % 256
    r = compare_images(a, Image.fromarray(arr))
    assert r.verdict == "TRANSFORMATION DETECTED" and r.changed_pixels == 1 and r.max_abs_error == 3


def test_mode_change_is_not_exact():
    a = pattern(20, 20)
    r = compare_images(a, a.convert("RGBA"))
    assert r.verdict != "PIXEL-EXACT"


def test_dimension_change_and_crop_region():
    a = pattern(50, 40)
    assert compare_images(a, a.resize((25, 20))).verdict == "TRANSFORMATION DETECTED"
    r = compare_images(a, a.crop((5, 4, 45, 36)), region=(5, 4, 45, 36))
    assert r.region_exact is True


@pytest.mark.parametrize("fmt,mode", [("PNG", "LOSSLESS"), ("WEBP", "LOSSLESS"), ("TIFF", "LOSSLESS"), ("BMP", "LOSSLESS")])
def test_lossless_exports_are_pixel_exact(fmt, mode):
    src = pattern(64, 48)
    data, actions = encode_as(src, fmt, mode)
    out = open_image_bytes(data)
    assert out.format == ("TIFF" if fmt == "TIFF" else fmt)
    assert compare_images(src, out).verdict == "PIXEL-EXACT"


@pytest.mark.parametrize("fmt", ["JPEG", "WEBP", "TIFF"])
def test_lossy_exports_measured_not_claimed(fmt):
    src = pattern(64, 48)
    data, actions = encode_as(src, fmt, "LOSSY", 60)
    assert any("LOSSY" in a for a in actions)
    assert compare_images(src, open_image_bytes(data)).verdict == "TRANSFORMATION DETECTED"


def test_capability_table_is_honest():
    assert FORMAT_CAPS["JPEG"]["modes"] == ("LOSSY",) and FORMAT_CAPS["JPEG"]["warning"]
    assert "NO" in FORMAT_CAPS["BMP"]["alpha"] and "NOT SUPPORTED" in FORMAT_CAPS["BMP"]["icc"]
    data, actions = encode_as(pattern(16, 16, mode="RGBA"), "BMP", "LOSSLESS")
    assert any("alpha discarded" in a for a in actions)


def test_16bit_preserved_in_png_and_tiff(fx):
    img = open_image_bytes(fx["fixture_16bit.png"])
    for fmt in ("PNG", "TIFF"):
        data, _ = encode_as(img, fmt, "LOSSLESS")
        assert compare_images(img, open_image_bytes(data)).verdict == "PIXEL-EXACT", fmt


def test_parse_chain():
    steps = parse_chain("jpg:lossy:80 > WEBP:LOSSLESS > png")
    assert [s["format"] for s in steps] == ["JPEG", "WEBP", "PNG"] and steps[0]["quality"] == 80
    with pytest.raises(TransformError):
        parse_chain("PNG:LOSSY")
    with pytest.raises(TransformError):
        parse_chain("GIF")
