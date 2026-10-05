import pytest

from app.core.metadata_engine import analyze_bytes
from app.core.pixel_integrity import compare_images
from app.services.c2pa_experiment import C2PA_WARNING, separate_provenance
from app.services.metadata_sanitizer import PROFILES, SanitizeOptions, SanitizeRefused, sanitize


def keys(a, g):
    return {f.key for f in a.groups[g].fields}


@pytest.mark.parametrize("name", ["fixture_ai_c2pa.jpg", "fixture_ai_c2pa.png", "fixture_meta.webp"])
@pytest.mark.parametrize("profile", list(PROFILES))
def test_metadata_only_is_pixel_exact(fx, name, profile):
    src = analyze_bytes(fx[name], "", name)
    res = sanitize(fx[name], src.info.format, PROFILES[profile])
    out = analyze_bytes(res.data, "", "out")
    r = compare_images(src.image, out.image)
    assert r.changed_pixels == 0 and r.verdict == "PIXEL-EXACT"
    assert "GPSLatitude" not in keys(out, "EXIF")
    assert any("Copyright" in k for k in keys(out, "EXIF"))  # rights always preserved
    assert out.groups["ICC"].state.value == "PRESENT"  # structure always preserved


def test_balanced_keeps_provenance_maximum_removes_it(fx):
    data = fx["fixture_ai_c2pa.jpg"]
    bal = analyze_bytes(sanitize(data, "JPEG", PROFILES["BALANCED"]).data, "", "b")
    assert bal.c2pa.present and bal.signal.state == "OBSERVED"
    mx = sanitize(data, "JPEG", PROFILES["MAXIMUM PRIVACY"])
    assert mx.provenance_removed
    out = analyze_bytes(mx.data, "", "m")
    assert not out.c2pa.present and out.signal.state == "NOT OBSERVED"


def test_conservative_keeps_camera(fx):
    out = analyze_bytes(sanitize(fx["fixture_ai_c2pa.jpg"], "JPEG", PROFILES["CONSERVATIVE"]).data, "", "c")
    assert "Make" in keys(out, "EXIF") and "BodySerialNumber" not in keys(out, "EXIF")


def test_sanitize_refuses_unsupported_container():
    with pytest.raises(SanitizeRefused):
        sanitize(b"BM" + b"\x00" * 60, "BMP", SanitizeOptions())


def test_no_options_keeps_content(fx):
    res = sanitize(fx["fixture_ai_c2pa.png"], "PNG", SanitizeOptions(gps=False, device=False))
    assert res.data == fx["fixture_ai_c2pa.png"]


@pytest.mark.parametrize("name", ["fixture_ai_c2pa.jpg", "fixture_ai_c2pa.png"])
def test_c2pa_separation_only_removes_store(fx, name):
    src = analyze_bytes(fx[name], "", name)
    res = separate_provenance(fx[name], src.info.format)
    out = analyze_bytes(res.data, "", "o")
    assert not out.c2pa.present and C2PA_WARNING in res.notes
    assert compare_images(src.image, out.image).verdict == "PIXEL-EXACT"
    assert keys(out, "EXIF") == keys(src, "EXIF") and keys(out, "XMP") == keys(src, "XMP")
    # XMP declaration remains unless explicitly requested -> signal still observable
    assert out.signal.state == "OBSERVED"
    res2 = separate_provenance(fx[name], src.info.format, include_xmp_declarations=True)
    out2 = analyze_bytes(res2.data, "", "o2")
    assert "Iptc4xmpExt:DigitalSourceType" not in keys(out2, "XMP")
