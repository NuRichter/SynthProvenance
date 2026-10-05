"""C2PA / Content Credentials analysis.

Native path: locate the JUMBF manifest store (JPEG APP11, PNG caBX, WebP
C2PA chunk), decode claims / assertions / COSE signature headers with the
bounded CBOR decoder, and recompute the ``c2pa.hash.data`` hard-binding
digest over the file bytes. The native path does NOT verify signatures or
certificate trust; those states are reported as NOT VALIDATED / UNKNOWN
unless an external engine (c2patool or c2pa-python) is available.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from app.core import cbor
from app.core.containers import Structure, reassemble_jpeg_jumbf
from app.core.jumbf import Box, JumbfError, parse_boxes
from app.models.image_info import ItemState
from app.models.provenance import NO_C2PA_TEXT, C2PAAction, C2PAIngredient, C2PAManifest, C2PAReport
from app.utils.system import ToolError, run_tool

COSE_ALGS = {-7: "ES256", -35: "ES384", -36: "ES512", -37: "PS256", -38: "PS384", -39: "PS512", -8: "EdDSA"}
HASH_ALGS = {"sha256": hashlib.sha256, "sha384": hashlib.sha384, "sha512": hashlib.sha512}
OID_NAMES = {b"\x55\x04\x03": "CN", b"\x55\x04\x0a": "O", b"\x55\x04\x0b": "OU", b"\x55\x04\x06": "C"}


def locate_store(data: bytes, fmt: str, st: Structure) -> tuple[bytes | None, str, list[str]]:
    if fmt == "JPEG":
        store, errs = reassemble_jpeg_jumbf(data, st)
        segs = st.find("JUMBF")
        loc = f"JPEG APP11 x{len(segs)} (first @ {segs[0].offset})" if segs else ""
        return store, loc, errs
    if fmt == "PNG":
        segs = st.find("JUMBF")
        if segs:
            return segs[0].payload(data), f"PNG caBX chunk @ {segs[0].offset}", []
    if fmt == "WEBP":
        segs = st.find("JUMBF")
        if segs:
            return segs[0].payload(data), f"WebP C2PA chunk @ {segs[0].offset}", []
    return None, "", []


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bytes):
        return v[:32].hex()
    if isinstance(v, dict):
        name = v.get("name") or v.get("label") or ""
        ver = v.get("version") or ""
        return f"{name} {ver}".strip() or json.dumps({str(k): str(x) for k, x in list(v.items())[:6]})
    return str(v)


def _decode_content(box: Box) -> object:
    c = box.content()
    if c is None:
        return None
    if c.type == "cbor":
        return cbor.untag(cbor.loads(c.payload))
    if c.type == "json":
        return json.loads(c.payload.decode("utf-8", "replace"))
    return {"__box__": c.type, "bytes": len(c.payload)}


def _der(data: bytes, i: int) -> tuple[int, int, int]:
    tag = data[i]
    ln = data[i + 1]
    i += 2
    if ln & 0x80:
        n = ln & 0x7F
        ln = int.from_bytes(data[i : i + n], "big")
        i += n
    return tag, i, ln


def _der_children(data: bytes, start: int, length: int) -> list[tuple[int, int, int]]:
    out = []
    i = start
    end = start + length
    while i < end:
        tag, vi, ln = _der(data, i)
        out.append((tag, vi, ln))
        i = vi + ln
    return out


def _der_name(data: bytes, start: int, length: int) -> str:
    parts = []
    for _t, si, sl in _der_children(data, start, length):  # SET
        for _t2, qi, ql in _der_children(data, si, sl):  # SEQUENCE
            kids = _der_children(data, qi, ql)
            if len(kids) >= 2:
                oid = data[kids[0][1] : kids[0][1] + kids[0][2]]
                val = data[kids[1][1] : kids[1][1] + kids[1][2]].decode("utf-8", "replace")
                if oid in OID_NAMES:
                    parts.append(f"{OID_NAMES[oid]}={val}")
    return ", ".join(parts)


def parse_certificate(der: bytes) -> dict:
    """Extract issuer/subject/validity for display only. Not a validation."""
    try:
        _t, ci, cl = _der(der, 0)
        tbs = _der_children(der, ci, cl)[0]
        kids = _der_children(der, tbs[1], tbs[2])
        idx = 1 if kids[0][0] == 0xA0 else 0
        issuer = kids[idx + 2]
        validity = kids[idx + 3]
        subject = kids[idx + 4]
        vals = _der_children(der, validity[1], validity[2])
        nb = der[vals[0][1] : vals[0][1] + vals[0][2]].decode("ascii", "replace")
        na = der[vals[1][1] : vals[1][1] + vals[1][2]].decode("ascii", "replace")
        return {"issuer": _der_name(der, issuer[1], issuer[2]), "subject": _der_name(der, subject[1], subject[2]),
                "not_before": nb, "not_after": na}
    except (IndexError, ValueError):
        return {}


def _signature_info(sig_box: Box, m: C2PAManifest) -> None:
    content = sig_box.content()
    if content is None or content.type != "cbor":
        m.errors.append("Signature box has no CBOR content")
        return
    m.signature_present = True
    try:
        cose = cbor.untag(cbor.loads(content.payload))
    except cbor.CBORError as exc:
        m.errors.append(f"COSE_Sign1 undecodable: {exc}")
        return
    if not isinstance(cose, list) or len(cose) != 4:
        m.errors.append("Signature is not a COSE_Sign1 structure")
        return
    protected, unprotected = cose[0], cose[1] if isinstance(cose[1], dict) else {}
    headers: dict = {}
    if isinstance(protected, bytes) and protected:
        try:
            ph = cbor.loads(protected)
            if isinstance(ph, dict):
                headers.update(ph)
        except cbor.CBORError:
            m.errors.append("Protected header undecodable")
    alg = headers.get(1)
    m.signature_algorithm = COSE_ALGS.get(alg, str(alg) if alg is not None else "UNKNOWN")
    chain = headers.get(33) or unprotected.get(33) or unprotected.get("x5chain")
    certs = chain if isinstance(chain, list) else [chain] if isinstance(chain, bytes) else []
    if certs and isinstance(certs[0], bytes):
        info = parse_certificate(certs[0])
        m.subject = info.get("subject", "")
        m.issuer = info.get("issuer", "")
        m.cert_not_before = info.get("not_before", "")
        m.cert_not_after = info.get("not_after", "")
    m.timestamp_token = any(k in unprotected for k in ("sigTst", "sigTst2"))


def _parse_manifest(mbox: Box) -> tuple[C2PAManifest, dict]:
    m = C2PAManifest(label=mbox.label or "(unlabelled)")
    raw: dict = {"assertions": {}}
    claim_box = mbox.child("c2pa.claim.v2") or mbox.child("c2pa.claim")
    if claim_box is not None:
        m.claim_version = "v2" if claim_box.label == "c2pa.claim.v2" else "v1"
        try:
            claim = _decode_content(claim_box)
            if isinstance(claim, dict):
                raw["claim"] = claim
                gen = claim.get("claim_generator")
                info = claim.get("claim_generator_info")
                if isinstance(info, list) and info:
                    info = info[0]
                m.claim_generator = _text(gen) if gen else _text(info)
                m.title = _text(claim.get("dc:title"))
                m.format = _text(claim.get("dc:format"))
                m.instance_id = _text(claim.get("instanceID"))
        except (cbor.CBORError, ValueError) as exc:
            m.errors.append(f"Claim undecodable: {exc}")
    else:
        m.errors.append("No claim box found")
    store = mbox.child("c2pa.assertions")
    if store is not None:
        for abox in store.superboxes():
            label = abox.label or "(unlabelled)"
            content = abox.content()
            entry = {"label": label, "content_type": content.type if content else "none",
                     "bytes": len(content.payload) if content else 0}
            m.assertions.append(entry)
            base = label.split("__")[0]
            if base.startswith("c2pa.thumbnail") or (content and content.type not in ("cbor", "json")):
                continue
            try:
                value = _decode_content(abox)
            except (cbor.CBORError, ValueError) as exc:
                m.errors.append(f"Assertion {label} undecodable: {exc}")
                continue
            raw["assertions"][label] = value
            if base in ("c2pa.actions", "c2pa.actions.v2") and isinstance(value, dict):
                for a in value.get("actions", []) or []:
                    if not isinstance(a, dict):
                        continue
                    params = a.get("parameters") if isinstance(a.get("parameters"), dict) else {}
                    m.actions.append(C2PAAction(
                        action=_text(a.get("action")), software_agent=_text(a.get("softwareAgent")),
                        digital_source_type=_text(a.get("digitalSourceType")), when=_text(a.get("when")),
                        description=_text(a.get("description") or params.get("description")), manifest=m.label))
            if base.startswith("c2pa.ingredient") and isinstance(value, dict):
                m.ingredients.append(C2PAIngredient(
                    title=_text(value.get("dc:title")), format=_text(value.get("dc:format")),
                    relationship=_text(value.get("relationship")), instance_id=_text(value.get("instanceID")),
                    has_manifest=bool(value.get("c2pa_manifest") or value.get("activeManifest")), manifest=m.label))
    sig = mbox.child("c2pa.signature")
    if sig is not None:
        _signature_info(sig, m)
    return m, raw


def _hard_binding(data: bytes, raw_active: dict, rep: C2PAReport) -> None:
    hd = None
    for label, value in raw_active.get("assertions", {}).items():
        if label.split("__")[0] == "c2pa.hash.data" and isinstance(value, dict):
            hd = value
            break
    if hd is None:
        if any(lbl.split("__")[0].startswith("c2pa.hash") for lbl in raw_active.get("assertions", {})):
            rep.hard_binding = "NOT SUPPORTED"
            rep.hard_binding_detail = "Hard binding uses a scheme other than c2pa.hash.data."
        else:
            rep.hard_binding = "NOT PRESENT"
        return
    alg_name = str(hd.get("alg") or raw_active.get("claim", {}).get("alg") or "sha256").lower()
    fn = HASH_ALGS.get(alg_name)
    expected = hd.get("hash")
    if fn is None or not isinstance(expected, bytes):
        rep.hard_binding = "UNKNOWN"
        rep.hard_binding_detail = f"Unsupported hash algorithm or missing digest ({alg_name})."
        return
    exclusions = []
    for ex in hd.get("exclusions", []) or []:
        if isinstance(ex, dict) and isinstance(ex.get("start"), int) and isinstance(ex.get("length"), int):
            exclusions.append((ex["start"], ex["length"]))
    exclusions.sort()
    h = fn()
    pos = 0
    for start, length in exclusions:
        if start < pos or start + length > len(data) or length < 0:
            rep.hard_binding = "MISMATCH"
            rep.hard_binding_detail = "Exclusion ranges do not fit the current file bytes (file was restructured)."
            return
        h.update(data[pos:start])
        pos = start + length
    h.update(data[pos:])
    if h.digest() == expected:
        rep.hard_binding = "MATCH"
        rep.hard_binding_detail = f"{alg_name} over file bytes minus {len(exclusions)} exclusion range(s) matches the c2pa.hash.data digest."
    else:
        rep.hard_binding = "MISMATCH"
        rep.hard_binding_detail = "Recomputed digest differs: bytes covered by the manifest changed after signing."


def analyze_c2pa(data: bytes, fmt: str, st: Structure) -> tuple[C2PAReport, dict]:
    """Returns (report, raw decoded structures of the active manifest)."""
    store, loc, errs = locate_store(data, fmt, st)
    if store is None:
        state = ItemState.ABSENT if fmt in ("JPEG", "PNG", "WEBP") else ItemState.UNKNOWN
        summary = NO_C2PA_TEXT if state == ItemState.ABSENT else f"C2PA embedding is not inspected for {fmt} containers."
        return C2PAReport(False, state.value, summary, errors=errs), {}
    rep = C2PAReport(True, ItemState.PRESENT.value, "C2PA manifest store detected.", location=loc, store_bytes=len(store),
                     errors=list(errs))
    rep.store_sha256 = hashlib.sha256(store).hexdigest()
    try:
        boxes = parse_boxes(store)
    except JumbfError as exc:
        rep.state = ItemState.INVALID.value
        rep.summary = f"C2PA/JUMBF data present but malformed: {exc}"
        rep.errors.append(str(exc))
        return rep, {}
    root = next((b for b in boxes if b.type == "jumb" and b.label == "c2pa"), None)
    if root is None:
        rep.state = ItemState.INVALID.value
        rep.summary = "JUMBF present but no 'c2pa' manifest store superbox found."
        return rep, {}
    raws: dict[str, dict] = {}
    for mbox in root.superboxes():
        try:
            m, raw = _parse_manifest(mbox)
        except (cbor.CBORError, JumbfError, ValueError, RecursionError) as exc:
            rep.errors.append(f"Manifest {mbox.label}: {exc}")
            continue
        rep.manifests.append(m)
        raws[m.label] = raw
    if not rep.manifests:
        rep.state = ItemState.INVALID.value
        rep.summary = "C2PA manifest store contains no decodable manifests."
        return rep, {}
    rep.active_manifest = rep.manifests[-1].label
    active_raw = raws.get(rep.active_manifest, {})
    _hard_binding(data, active_raw, rep)
    rep.validity = "NOT VALIDATED"
    rep.validity_detail = "Signature not cryptographically verified by the native parser (no C2PA validation engine used)."
    rep.trust = "UNKNOWN"
    rep.summary = f"C2PA manifest store with {len(rep.manifests)} manifest(s); active: {rep.active_manifest}."
    return rep, active_raw


# ------------------------------------------------------------ external engines

def _apply_engine_json(rep: C2PAReport, report: dict, engine: str) -> None:
    rep.engine = engine
    rep.engine_output = report
    statuses = report.get("validation_status") or []
    state = report.get("validation_state")
    codes = [s.get("code", "") for s in statuses if isinstance(s, dict)]
    if state:
        rep.validity = str(state).upper()
    elif codes:
        rep.validity = "INVALID"
    else:
        rep.validity = "NO VALIDATION FAILURES REPORTED"
    rep.validity_detail = "; ".join(codes) if codes else f"{engine} reported no failure codes."
    if state and str(state).lower() == "trusted":
        rep.trust = "TRUSTED"
    elif any("untrusted" in c for c in codes):
        rep.trust = "UNTRUSTED (signing credential not on the configured trust list)"
    else:
        rep.trust = "UNKNOWN (no trust list configured)"
    active = report.get("active_manifest")
    manifests = report.get("manifests") or {}
    if isinstance(manifests, dict) and active in manifests:
        si = manifests[active].get("signature_info") or {}
        for m in rep.manifests:
            if m.label == active:
                m.issuer = si.get("issuer") or m.issuer
                if si.get("alg"):
                    m.signature_algorithm = str(si.get("alg"))


def validate_with_c2patool(path: Path, rep: C2PAReport, tool_path: str) -> None:
    try:
        res = run_tool([tool_path, str(path)], timeout=60)
    except ToolError as exc:
        rep.errors.append(f"c2patool failed: {exc}")
        return
    text = res.stdout.decode("utf-8", "replace").strip()
    try:
        _apply_engine_json(rep, json.loads(text), "c2patool")
    except ValueError:
        rep.errors.append(f"c2patool output was not JSON (exit {res.returncode}).")


def validate_with_c2pa_python(data: bytes, fmt: str, rep: C2PAReport) -> None:
    try:
        import c2pa  # type: ignore
    except Exception:  # noqa: BLE001
        return
    suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}.get(fmt, ".bin")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / f"probe{suffix}"
        p.write_bytes(data)
        try:
            if hasattr(c2pa, "Reader"):
                reader = c2pa.Reader(str(p))
                try:
                    report = json.loads(reader.json())
                finally:
                    close = getattr(reader, "close", None)
                    if callable(close):
                        close()
            else:
                report = json.loads(c2pa.read_file(str(p), None))  # legacy API
        except Exception as exc:  # noqa: BLE001 - engine errors must not break analysis
            rep.errors.append(f"c2pa-python failed: {type(exc).__name__}: {exc}")
            return
    _apply_engine_json(rep, report, "c2pa-python")
