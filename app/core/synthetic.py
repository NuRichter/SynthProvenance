"""Deterministic synthetic test fixtures.

All fixtures are generated from fixed seeds and are byte-reproducible for a
given Pillow / libjpeg / libwebp build. The embedded C2PA manifest is an
UNSIGNED structural fixture (its COSE signature is 64 zero bytes and carries
no certificate). It exists only to exercise the parser, hard-binding check
and sanitizer; it would fail any real C2PA validation, by design.
"""
from __future__ import annotations

import io
import struct

import numpy as np
from PIL import Image, ImageCms, PngImagePlugin

from app.core import cbor
from app.core.containers import make_png_chunk, parse_jpeg, parse_png
from app.core.jumbf import (
    C2PA_ASSERTIONS_UUID,
    C2PA_CLAIM_UUID,
    C2PA_MANIFEST_UUID,
    C2PA_SIGNATURE_UUID,
    C2PA_STORE_UUID,
    CBOR_UUID,
    box,
    superbox,
)
from app.analyzers.iptc_analyzer import PS_HEADER, build_iim, build_irb

AI_SOURCE = "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"
FIXTURE_TAG = "SYNTHETIC TEST FIXTURE"


def pattern(width: int = 96, height: int = 64, seed: int = 20260927, mode: str = "RGB") -> Image.Image:
    """Deterministic gradients + geometric structure + seeded texture."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:height, 0:width].astype(np.float64)
    r = (x / max(width - 1, 1)) * 255
    g = (y / max(height - 1, 1)) * 255
    cx, cy = width * 0.6, height * 0.45
    rad = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    b = 127.5 + 127.5 * np.cos(rad / 4.0)
    tex = rng.integers(-12, 13, size=(height, width, 3))
    arr = np.stack([r, g, b], axis=2) + tex
    arr[(x % 16 < 2)] = arr[(x % 16 < 2)] * 0.4
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr, "RGB")
    if mode == "RGBA":
        alpha = np.clip(255 - rad * 3, 40, 255).astype(np.uint8)
        img = Image.fromarray(np.dstack([arr, alpha]), "RGBA")
    elif mode != "RGB":
        img = img.convert(mode)
    return img


def srgb_icc() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def fixture_exif(include_gps: bool = True, user_comment: str | None = None) -> Image.Exif:
    ex = Image.Exif()
    ex[0x010F] = "SynthCam"  # Make
    ex[0x0110] = "Model S-1"  # Model
    ex[0x0112] = 1  # Orientation
    ex[0x0131] = "SynthProvenance Fixture Writer 1.0"  # Software
    ex[0x0132] = "2026:09:27 10:00:00"  # DateTime
    ex[0x013B] = "Fixture Author"  # Artist
    ex[0x8298] = "(c) 2026 Fixture Rights Holder"  # Copyright
    sub = ex.get_ifd(0x8769)
    sub[0x9003] = "2026:09:27 09:59:58"  # DateTimeOriginal
    sub[0xA431] = "SN-0042-FIXTURE"  # BodySerialNumber
    sub[0x829A] = (1, 250)  # ExposureTime
    sub[0xA001] = 1  # ColorSpace sRGB
    if user_comment is not None:
        sub[0x9286] = b"ASCII\x00\x00\x00" + user_comment.encode("ascii", "replace")
    if include_gps:
        gps = ex.get_ifd(0x8825)
        gps[1] = "S"
        gps[2] = (7.0, 27.0, 36.0)
        gps[3] = "E"
        gps[4] = (112.0, 43.0, 12.0)
    return ex


def fixture_xmp(ai: bool = True) -> bytes:
    dst = f'<Iptc4xmpExt:DigitalSourceType>{AI_SOURCE}</Iptc4xmpExt:DigitalSourceType>' if ai else ""
    return (
        '<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/" xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/" '
        'xmlns:xmpRights="http://ns.adobe.com/xap/1.0/rights/" xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/" '
        'xmp:CreatorTool="SynthProvenance Fixture Writer 1.0" xmp:CreateDate="2026-09-27T09:59:58Z" '
        'photoshop:City="Fixture City" xmpMM:DocumentID="xmp.did:fixture-0001" xmpRights:Marked="True">'
        '<dc:creator><rdf:Seq><rdf:li>Fixture Author</rdf:li></rdf:Seq></dc:creator>'
        '<dc:rights><rdf:Alt><rdf:li xml:lang="x-default">(c) 2026 Fixture Rights Holder</rdf:li></rdf:Alt></dc:rights>'
        f'{dst}'
        '</rdf:Description></rdf:RDF></x:xmpmeta>\n<?xpacket end="w"?>'
    ).encode("utf-8")


def fixture_irb() -> bytes:
    iim = build_iim([(1, 90, b"\x1b%G"), (2, 0, b"\x00\x04"), (2, 80, b"Fixture Author"), (2, 90, b"Fixture City"),
                     (2, 116, b"(c) 2026 Fixture Rights Holder"), (2, 25, b"synthetic"), (2, 25, b"fixture")])
    return build_irb([(0x0404, b"", iim)])


# ------------------------------------------------------------------ C2PA

def _c2pa_store(exclusion_start: int, exclusion_length: int, digest: bytes, fmt_mime: str, ai: bool = True) -> bytes:
    actions = {"actions": [{"action": "c2pa.created", "softwareAgent": "SynthProvenance fixture generator",
                            **({"digitalSourceType": AI_SOURCE} if ai else {})}]}
    hash_data = {"exclusions": [{"start": exclusion_start, "length": exclusion_length}], "name": "jumbf manifest",
                 "alg": "sha256", "hash": digest, "pad": b""}
    assertions = superbox(C2PA_ASSERTIONS_UUID, "c2pa.assertions", [
        superbox(CBOR_UUID, "c2pa.actions", [box("cbor", cbor.dumps(actions))]),
        superbox(CBOR_UUID, "c2pa.hash.data", [box("cbor", cbor.dumps(hash_data))]),
    ])
    claim = {"claim_generator": "SynthProvenance-fixture/1.0 (unsigned test fixture)", "dc:title": FIXTURE_TAG,
             "dc:format": fmt_mime, "instanceID": "xmp:iid:00000000-0000-4000-8000-000000000001",
             "signature": "self#jumbf=c2pa.signature", "alg": "sha256",
             "assertions": [{"url": "self#jumbf=c2pa.assertions/c2pa.actions", "hash": b"\x00" * 32},
                            {"url": "self#jumbf=c2pa.assertions/c2pa.hash.data", "hash": b"\x00" * 32}]}
    protected = cbor.dumps({1: -7})
    cose = cbor.CBORTag(18, [protected, {}, None, b"\x00" * 64])
    manifest = superbox(C2PA_MANIFEST_UUID, "urn:uuid:00000000-0000-4000-8000-5f1c7e000001", [
        assertions,
        superbox(C2PA_CLAIM_UUID, "c2pa.claim", [box("cbor", cbor.dumps(claim))]),
        superbox(C2PA_SIGNATURE_UUID, "c2pa.signature", [box("cbor", cbor.dumps(cose))]),
    ])
    return superbox(C2PA_STORE_UUID, "c2pa", [manifest])


def _hash_excluding(data: bytes, start: int, length: int) -> bytes:
    import hashlib

    h = hashlib.sha256()
    h.update(data[:start])
    h.update(data[start + length :])
    return h.digest()


def _app11(store: bytes) -> bytes:
    payload = b"JP" + struct.pack(">HI", 1, 1) + store
    if len(payload) > 65533:
        raise ValueError("fixture store too large for a single APP11 segment")
    return b"\xff\xeb" + struct.pack(">H", len(payload) + 2) + payload


def embed_c2pa_jpeg(data: bytes, ai: bool = True) -> bytes:
    """Insert an unsigned synthetic C2PA store (APP11) with a valid c2pa.hash.data binding."""
    st = parse_jpeg(data)
    insert_at = next(s.offset for s in st.segments if not s.name.startswith("APP"))
    length = len(_app11(_c2pa_store(insert_at, 0, b"\x00" * 32, "image/jpeg", ai)))
    for _ in range(4):
        seg = _app11(_c2pa_store(insert_at, length, b"\x00" * 32, "image/jpeg", ai))
        if len(seg) == length:
            break
        length = len(seg)
    assembled = data[:insert_at] + seg + data[insert_at:]
    digest = _hash_excluding(assembled, insert_at, length)
    final = _app11(_c2pa_store(insert_at, length, digest, "image/jpeg", ai))
    assert len(final) == length
    return data[:insert_at] + final + data[insert_at:]


def embed_c2pa_png(data: bytes, ai: bool = True) -> bytes:
    st = parse_png(data)
    ihdr = st.segments[0]
    insert_at = ihdr.offset + ihdr.length
    length = len(make_png_chunk("caBX", _c2pa_store(insert_at, 0, b"\x00" * 32, "image/png", ai)))
    for _ in range(4):
        chunk = make_png_chunk("caBX", _c2pa_store(insert_at, length, b"\x00" * 32, "image/png", ai))
        if len(chunk) == length:
            break
        length = len(chunk)
    assembled = data[:insert_at] + chunk + data[insert_at:]
    digest = _hash_excluding(assembled, insert_at, length)
    final = make_png_chunk("caBX", _c2pa_store(insert_at, length, digest, "image/png", ai))
    assert len(final) == length
    return data[:insert_at] + final + data[insert_at:]


def _insert_jpeg_segments(data: bytes, segments: list[tuple[int, bytes]]) -> bytes:
    st = parse_jpeg(data)
    insert_at = next(s.offset for s in st.segments if not s.name.startswith("APP"))
    extra = b"".join(bytes([0xFF, m]) + struct.pack(">H", len(p) + 2) + p for m, p in segments)
    return data[:insert_at] + extra + data[insert_at:]


# ----------------------------------------------------------------- fixtures

def make_jpeg(with_metadata: bool = True, with_c2pa: bool = True, ai: bool = True, size=(96, 64), quality: int = 92) -> bytes:
    img = pattern(*size)
    buf = io.BytesIO()
    kw: dict = {}
    if with_metadata:
        kw = {"exif": fixture_exif().tobytes(), "icc_profile": srgb_icc(), "xmp": fixture_xmp(ai)}
    img.save(buf, "JPEG", quality=quality, subsampling="4:2:0", **kw)
    data = buf.getvalue()
    if with_metadata:
        data = _insert_jpeg_segments(data, [(0xED, PS_HEADER + fixture_irb()), (0xFE, b"fixture comment")])
    if with_c2pa:
        data = embed_c2pa_jpeg(data, ai)
    return data


A1111_PARAMETERS = ("a synthetic test pattern\nNegative prompt: none\nSteps: 20, Sampler: Euler a, CFG scale: 7, "
                    "Seed: 1234, Size: 96x64, Model: fixture")


def make_png(with_metadata: bool = True, with_c2pa: bool = True, ai: bool = True, size=(96, 64), mode: str = "RGB") -> bytes:
    img = pattern(*size, mode=mode)
    buf = io.BytesIO()
    kw: dict = {}
    if with_metadata:
        info = PngImagePlugin.PngInfo()
        info.add_text("Software", "SynthProvenance Fixture Writer 1.0")
        info.add_text("Author", "Fixture Author")
        info.add_text("Copyright", "(c) 2026 Fixture Rights Holder")
        info.add_text("Comment", "private note: fixture")
        if ai:
            info.add_text("parameters", A1111_PARAMETERS)
        info.add_itxt("XML:com.adobe.xmp", fixture_xmp(ai).decode("utf-8"))
        kw = {"pnginfo": info, "exif": fixture_exif(), "icc_profile": srgb_icc()}
    img.save(buf, "PNG", **kw)
    data = buf.getvalue()
    if with_metadata:
        st = parse_png(data)
        iend = st.segments[-1].offset
        data = data[:iend] + make_png_chunk("tIME", struct.pack(">HBBBBB", 2026, 9, 27, 10, 0, 0)) + \
            make_png_chunk("prVt", b"private vendor chunk") + data[iend:]
    if with_c2pa:
        data = embed_c2pa_png(data, ai)
    return data


def make_webp(with_metadata: bool = True, lossless: bool = True, size=(96, 64)) -> bytes:
    img = pattern(*size)
    buf = io.BytesIO()
    kw: dict = {}
    if with_metadata:
        kw = {"exif": fixture_exif().tobytes(), "xmp": fixture_xmp(True), "icc_profile": srgb_icc()}
    img.save(buf, "WEBP", lossless=lossless, quality=90, exact=True, **kw)
    return buf.getvalue()


def make_plain_png(size=(64, 48), mode: str = "RGB") -> bytes:
    buf = io.BytesIO()
    pattern(*size, mode=mode).save(buf, "PNG")
    return buf.getvalue()


def make_palette_png(size=(48, 32)) -> bytes:
    img = pattern(*size).convert("P", palette=Image.Palette.ADAPTIVE, colors=32)
    buf = io.BytesIO()
    img.save(buf, "PNG", transparency=0)
    return buf.getvalue()


def make_16bit_png(size=(40, 30)) -> bytes:
    y, x = np.mgrid[0 : size[1], 0 : size[0]]
    arr = ((x * 1500 + y * 700) % 65536).astype(np.uint16)
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, "PNG")
    return buf.getvalue()


def all_fixtures() -> dict[str, bytes]:
    return {
        "fixture_ai_c2pa.jpg": make_jpeg(),
        "fixture_ai_c2pa.png": make_png(),
        "fixture_meta.webp": make_webp(),
        "fixture_plain.png": make_plain_png(),
        "fixture_plain.jpg": make_jpeg(with_metadata=False, with_c2pa=False),
        "fixture_palette.png": make_palette_png(),
        "fixture_16bit.png": make_16bit_png(),
        "fixture_rgba.png": make_png(with_metadata=False, with_c2pa=False, mode="RGBA"),
    }
