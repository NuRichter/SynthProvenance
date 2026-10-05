from pathlib import Path

import pytest

from app.core.containers import parse_jpeg
from app.core.metadata_engine import analyze_bytes, diff_groups
from app.analyzers.xmp_analyzer import analyze_xmp
from app.core import synthetic


def fields(a, group):
    return {f.key: f.value for f in a.groups[group].fields}


def test_jpeg_metadata_groups(fx):
    a = analyze_bytes(fx["fixture_ai_c2pa.jpg"], "", "x.jpg")
    ex = fields(a, "EXIF")
    assert ex["Make"] == "SynthCam" and "GPSLatitude" in ex and ex["Copyright"].startswith("(c)")
    assert "Iptc4xmpExt:DigitalSourceType" in fields(a, "XMP")
    assert fields(a, "IPTC")["By-line"] == "Fixture Author"
    assert "sRGB" in fields(a, "ICC")["description"]
    assert a.groups["SOFTWARE"].state.value == "PRESENT"
    assert a.signal.state == "OBSERVED"


def test_png_generator_record_is_counted_evidence(fx):
    a = analyze_bytes(fx["fixture_ai_c2pa.png"], "", "x.png")
    srcs = [e.source for e in a.signal.evidence]
    assert any(s.startswith("PNG") for s in srcs)
    assert any(s.startswith("C2PA") for s in srcs)


def test_plain_image_not_observed_statement(fx):
    a = analyze_bytes(fx["fixture_plain.png"], "", "x.png")
    assert a.signal.state == "NOT OBSERVED"
    assert "does not establish that the image is human-created" in a.signal.statement
    assert a.c2pa.summary == "No observable C2PA Content Credential detected."
    assert any("NOT ASSESSED" in u for u in a.signal.unknowns)


def test_software_names_are_interpretation_not_evidence():
    from PIL import Image
    import io

    ex = Image.Exif()
    ex[0x0131] = "Midjourney v6"
    buf = io.BytesIO()
    synthetic.pattern(32, 32).save(buf, "JPEG", exif=ex.tobytes())
    a = analyze_bytes(buf.getvalue(), "", "x.jpg")
    assert a.signal.state == "NOT OBSERVED"
    assert any("Midjourney" in i.value for i in a.signal.interpretations)


def test_xmp_entity_declarations_rejected():
    g = analyze_xmp(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><x:xmpmeta xmlns:x="adobe:ns:meta/"/>')
    assert g.state.value == "INVALID"


def test_diff_states(fx):
    a = analyze_bytes(fx["fixture_ai_c2pa.jpg"], "", "a").to_dict()
    b = analyze_bytes(fx["fixture_plain.jpg"], "", "b").to_dict()
    same_diffs, same = diff_groups(a["groups"], a["groups"])
    assert all(v["state"] in ("PRESERVED", "ABSENT") for v in same.values())
    _d, g = diff_groups(a["groups"], b["groups"])
    assert g["EXIF"]["state"] == "REMOVED" and g["XMP"]["state"] == "REMOVED"


@pytest.mark.parametrize("name", ["fixture_ai_c2pa.jpg", "fixture_ai_c2pa.png"])
def test_synthetic_c2pa_hard_binding(fx, name):
    a = analyze_bytes(fx[name], "", name)
    assert a.c2pa.present and a.c2pa.hard_binding == "MATCH"
    assert a.c2pa.validity == "NOT VALIDATED" and a.c2pa.trust == "UNKNOWN"
    assert a.c2pa.store_sha256 and len(a.c2pa.manifests) == 1
    act = a.c2pa.manifests[0].actions[0]
    assert act.action == "c2pa.created" and act.digital_source_type.endswith("trainedAlgorithmicMedia")


def test_tampered_bytes_break_binding(fx):
    data = bytearray(fx["fixture_ai_c2pa.jpg"])
    st = parse_jpeg(bytes(data))
    pos = st.scan_offset + 40
    data[pos] ^= 0x01
    a = analyze_bytes(bytes(data), "", "t.jpg") if True else None
    assert a.c2pa.hard_binding == "MISMATCH"


SAMPLES = Path("/home/claude/samples")


@pytest.mark.skipif(not SAMPLES.is_dir(), reason="real C2PA reference samples not available on this machine")
def test_real_c2pa_samples():
    for p in sorted(SAMPLES.iterdir()):
        a = analyze_bytes(p.read_bytes(), p, p.name)
        if a.c2pa.present:
            assert a.c2pa.hard_binding == "MATCH", p.name
            assert a.c2pa.manifests and a.c2pa.manifests[-1].signature_algorithm.startswith(("PS", "ES", "Ed"))
