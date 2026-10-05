"""Provenance comparison and the seven-layer separation analysis."""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from app.analyzers.c2pa_analyzer import validate_with_c2pa_python, validate_with_c2patool
from app.analyzers.synthid_analyzer import compare_synthid
from app.models.provenance import (
    LAYER_C2PA,
    LAYER_ENCODING,
    LAYER_EXTERNAL,
    LAYER_KIND,
    LAYER_METADATA,
    LAYER_PIXELS,
    LAYER_STRUCTURE,
    NO_C2PA_TEXT,
    NOT_OBSERVED_MEANING,
)

METADATA_GROUPS = ("EXIF", "XMP", "IPTC", "ICC", "PNG CHUNKS", "TIFF TAGS")


def _layer(layer, before, after, state, observation, method, condition, limitation) -> dict:
    return {"layer": layer, "kind": LAYER_KIND[layer], "before": before, "after": after, "state": state,
            "observation": observation, "method": method, "condition": condition, "limitation": limitation}


def c2pa_label(c: dict) -> str:
    if not c or not c.get("present"):
        return "ABSENT" if (c or {}).get("state", "ABSENT") == "ABSENT" else (c or {}).get("state", "UNKNOWN")
    return f"PRESENT ({len(c.get('manifests') or [])} manifest, binding {c.get('hard_binding')})"


def provenance_diff(before: dict, after: dict) -> dict:
    cb, ca = before.get("c2pa") or {}, after.get("c2pa") or {}
    sb, sa = before.get("signal") or {}, after.get("signal") or {}
    key = lambda e: (e.get("source"), e.get("field"), str(e.get("value"))[:200])  # noqa: E731
    eb, ea = sb.get("evidence") or [], sa.get("evidence") or []
    after_keys = {key(e) for e in ea}
    changed = cb.get("state") != ca.get("state") or cb.get("store_sha256") != ca.get("store_sha256") \
        or cb.get("hard_binding") != ca.get("hard_binding") or sb.get("state") != sa.get("state")
    statement = ("The selected experimental transformation altered the observable provenance state under the tested "
                 "condition." if changed else "The observable provenance state was unchanged under the tested condition.")
    if sa.get("state") == "NOT OBSERVED":
        statement += " " + NOT_OBSERVED_MEANING
    return {
        "c2pa_before": cb.get("state", "UNKNOWN"), "c2pa_after": ca.get("state", "UNKNOWN"),
        "manifests_before": len(cb.get("manifests") or []), "manifests_after": len(ca.get("manifests") or []),
        "store_sha256_before": cb.get("store_sha256", ""), "store_sha256_after": ca.get("store_sha256", ""),
        "hard_binding_before": cb.get("hard_binding", ""), "hard_binding_after": ca.get("hard_binding", ""),
        "active_manifest_before": cb.get("active_manifest", ""), "active_manifest_after": ca.get("active_manifest", ""),
        "signal_before": sb.get("state", "UNKNOWN"), "signal_after": sa.get("state", "UNKNOWN"),
        "evidence_before": len(eb), "evidence_after": len(ea),
        "evidence_not_observed_after": [f"{e.get('source')} {e.get('field')}" for e in eb if key(e) not in after_keys],
        "changed": changed, "statement": statement,
    }


def compare_layers(before: dict, after: dict, pixel: dict, synthid_before: dict, synthid_after: dict,
                   externals: list, condition: str, group_states: dict) -> list[dict]:
    layers: list[dict] = []
    # --- C2PA
    cb, ca = before.get("c2pa") or {}, after.get("c2pa") or {}
    pb, pa = bool(cb.get("present")), bool(ca.get("present"))
    method = "Native JUMBF/CBOR manifest parse; c2pa.hash.data digest recomputed over the file bytes"
    lim = ("Signature and certificate trust are not cryptographically validated by the native parser. Absence of an "
           "observable C2PA manifest does not establish that an image is not AI-generated.")
    if ca.get("state") == "INVALID":
        st, obs = "INVALID", f"Output manifest data is present but invalid: {ca.get('summary')}"
    elif ca.get("state") == "UNKNOWN" or (not pb and cb.get("state") == "UNKNOWN"):
        st = "UNKNOWN"
        obs = (f"{ca.get('summary') or cb.get('summary')} Presence is not measured for this container, so no removal or "
               "persistence is claimed.")
    elif pb and not pa:
        st = "REMOVED"
        obs = (f"Manifest store present before ({cb.get('store_bytes', 0):,} bytes, SHA-256 "
               f"{str(cb.get('store_sha256', ''))[:16]}...) is absent from the output.")
    elif pb and pa:
        same = cb.get("store_sha256") == ca.get("store_sha256")
        if same and ca.get("hard_binding") == "MATCH":
            st, obs = "PERSISTED", "Identical manifest store; hard binding still MATCHES the output bytes."
        else:
            st = "ALTERED"
            obs = (f"Manifest store {'identical' if same else 'changed'}; hard binding "
                   f"{cb.get('hard_binding')} -> {ca.get('hard_binding')}.")
    elif pa and not pb:
        st, obs = "DETECTED", "A manifest store appears in the output that was not in the input."
    else:
        st, obs = "NOT DETECTED", f"{NO_C2PA_TEXT} (before and after)"
    layers.append(_layer(LAYER_C2PA, c2pa_label(cb), c2pa_label(ca), st, obs, method, condition, lim))
    # --- SynthID
    layers.append(compare_synthid(synthid_before, synthid_after, condition))
    # --- ordinary metadata
    rel = {k: v for k, v in group_states.items() if k in METADATA_GROUPS}
    present_before = [k for k, v in rel.items() if v["before"] != "ABSENT"]
    present_after = [k for k, v in rel.items() if v["after"] != "ABSENT"]
    if not present_before and not present_after:
        st = "NOT DETECTED"
    elif any(v["state"] == "INVALID" for v in rel.values()):
        st = "INVALID"
    elif all(v["state"] in ("PRESERVED", "ABSENT") for v in rel.values()):
        st = "PERSISTED"
    elif present_before and all(rel[k]["state"] == "REMOVED" for k in present_before) and not any(
            v["PRESENT"] for v in rel.values()):
        st = "REMOVED"
    else:
        st = "ALTERED"
    obs = "; ".join(f"{k}: {v['state']} ({v['detail']})" for k, v in rel.items() if v["state"] != "ABSENT") or \
        "No ordinary metadata before or after."
    layers.append(_layer(LAYER_METADATA, ", ".join(present_before) or "none", ", ".join(present_after) or "none", st,
                         obs, "Field-level comparison of decoded EXIF, XMP, IPTC, ICC, PNG text and TIFF tags",
                         condition, "Opaque vendor blocks (e.g. maker notes) are compared as whole values."))
    # --- pixels
    verdict = pixel.get("verdict")
    if verdict == "PIXEL-EXACT":
        st, obs = "PERSISTED", "PIXEL-EXACT: every sample identical, identical pixel SHA-256."
    elif pixel.get("comparable"):
        st = "ALTERED"
        psnr = "infinite" if pixel.get("psnr_infinite") else f"{pixel.get('psnr_db') or 0:.2f} dB"
        obs = (f"TRANSFORMATION DETECTED: {pixel.get('changed_pixels', 0):,} pixels changed "
               f"({pixel.get('changed_pixel_pct') or 0:.4f}%), max error {pixel.get('max_abs_error')}, PSNR {psnr}.")
    else:
        st, obs = ("ALTERED" if verdict == "TRANSFORMATION DETECTED" else "NOT TESTABLE"), \
            "; ".join(pixel.get("notes") or []) or "Not directly comparable."
    rb, ra = pixel.get("resolution_a") or [0, 0], pixel.get("resolution_b") or [0, 0]
    layers.append(_layer(LAYER_PIXELS, f"{rb[0]}x{rb[1]} {pixel.get('mode_a', '')}", f"{ra[0]}x{ra[1]} {pixel.get('mode_b', '')}",
                         st, obs, "Canonical decode (frame 0, orientation not applied); all samples compared; "
                         "MAE/MSE/PSNR/SSIM(7x7)/histogram/dHash", condition,
                         "Pixel identity does not predict how third-party detectors or platforms behave."))
    # --- encoding
    eb, ea = before.get("compression") or {}, after.get("compression") or {}
    same_enc = eb.get("summary") == ea.get("summary")
    layers.append(_layer(LAYER_ENCODING, eb.get("summary", "?"), ea.get("summary", "?"),
                         "PERSISTED" if same_enc else "ALTERED",
                         "Codec and parameters unchanged." if same_enc else "Codec or parameters changed.",
                         "Magic-byte sniffing, SOF/IHDR/VP8X parsing, quantisation-table estimation", condition,
                         "Quality estimates for JPEG are IJG-table matches, not encoder settings."))
    # --- structure
    sb_ = [(s.get("name"), s.get("ident")) for s in (before.get("structure") or {}).get("segments", [])]
    sa_ = [(s.get("name"), s.get("ident")) for s in (after.get("structure") or {}).get("segments", [])]
    hb, ha = (before.get("hashes") or {}).get("sha256"), (after.get("hashes") or {}).get("sha256")
    if hb == ha:
        st, obs = "PERSISTED", "Byte-identical file."
    elif sb_ == sa_ and sb_:
        st, obs = "PERSISTED", "Same segment/chunk layout; byte content differs inside segments."
    else:
        lost = Counter(n for n, _ in sb_) - Counter(n for n, _ in sa_)
        new = Counter(n for n, _ in sa_) - Counter(n for n, _ in sb_)
        st = "ALTERED"
        obs = (f"{len(sb_)} -> {len(sa_)} segments/chunks. Not in output: {dict(lost) or '-'}; new: {dict(new) or '-'}.")
    def layout(d, segs):
        cont = (d.get("structure") or {}).get("container", "?")
        return f"{cont} {len(segs)} segments" if segs else f"{cont} (layout not walked)"
    layers.append(_layer(LAYER_STRUCTURE, layout(before, sb_), layout(after, sa_), st, obs,
                         "Byte-level container walk (JPEG markers, PNG chunks with CRC, RIFF chunks)", condition,
                         "TIFF/BMP/GIF layouts are not walked at byte level."))
    # --- external platform (user-recorded)
    def ext(cond):
        return [e for e in externals if getattr(e, "layer", "PLATFORM") == "PLATFORM" and getattr(e, "condition", "") == cond]
    xb, xa = ext("ORIGINAL"), ext(condition.split(" ")[0])
    if not xb and not xa:
        layers.append(_layer(LAYER_EXTERNAL, "not recorded", "not recorded", "NOT TESTABLE",
                             "SynthProvenance never contacts external platforms (LOCAL-ONLY). No user record exists.",
                             "User-recorded entry only", condition, "Unverified by design."))
    else:
        fmt = lambda xs: "; ".join(f"{e.platform}: {e.label}" for e in xs) or "not recorded"  # noqa: E731
        layers.append(_layer(LAYER_EXTERNAL, fmt(xb), fmt(xa), "UNKNOWN",
                             "User-recorded external labels are shown as reported; they are not measurements.",
                             "User-recorded entry (EXTERNAL PLATFORM CLASSIFICATION tier)", condition,
                             "Unverified. Platform classifiers change without notice and are not reproducible here."))
    return layers


def c2pa_manifest_export(analysis_dict: dict) -> dict:
    c = dict(analysis_dict.get("c2pa") or {})
    c["exported_by"] = "SynthProvenance native JUMBF/CBOR parser"
    c["file_sha256"] = (analysis_dict.get("hashes") or {}).get("sha256", "")
    return c


def run_external_c2pa_validation(analysis, path: Path, c2patool_path: str | None, use_c2pa_python: bool) -> str:
    """Optional local validation engines. Returns the engine used or ''."""
    rep = analysis.c2pa
    if not rep.present:
        return ""
    if c2patool_path:
        validate_with_c2patool(Path(path), rep, c2patool_path)
        return "c2patool"
    if use_c2pa_python:
        before = rep.engine
        validate_with_c2pa_python(analysis.data, analysis.info.format, rep)
        return rep.engine if rep.engine != before else ""
    return ""
