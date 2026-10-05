"""AI-content provenance signal and provenance-graph construction.

Evidence tiers (see docs/METHODOLOGY.md):

* OBSERVABLE EVIDENCE - a machine-readable provenance declaration found in the
  file: a C2PA action whose ``digitalSourceType`` is an IPTC generative-AI term,
  an XMP ``Iptc4xmpExt:DigitalSourceType`` generative-AI term, an
  ``Iptc4xmpExt:AISystemUsed`` declaration, or a structured generator-parameter
  record. Only this tier makes the signal OBSERVED.
* EXPERIMENTAL INTERPRETATION - weaker hints (software names, unstructured
  text chunks, non-generative synthetic source types). Reported, never counted.
* EXTERNAL PLATFORM CLASSIFICATION - labels recorded by the user from third
  party platforms. Unverified; never counted.
* UNKNOWN INFORMATION - what could not be observed (invalid containers,
  unsupported formats, pixel-domain watermarks which are not assessed).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.analyzers.png_analyzer import detect_generator_record
from app.analyzers.xmp_analyzer import AI_SOURCE_TYPES, SYNTHETIC_SOURCE_TYPES
from app.models.image_info import ItemState
from app.models.provenance import (
    NOT_OBSERVED_MEANING,
    SIGNAL_NOT_OBSERVED,
    SIGNAL_OBSERVED,
    SIGNAL_UNKNOWN,
    TIER_EVIDENCE,
    TIER_INTERPRETATION,
    TIER_UNKNOWN,
    AISignal,
    SignalEvidence,
)

if TYPE_CHECKING:  # pragma: no cover
    from app.core.metadata_engine import Analysis

GENERATOR_NAME_PATTERN = re.compile(
    r"midjourney|dall[\s\-·.]?e|stable[\s\-_]?diffusion|sdxl|comfyui|automatic1111|invokeai|novelai|firefly|imagen|"
    r"gemini|openai|chatgpt|gpt-4o|\bsora\b|leonardo\.?ai|ideogram|\bflux\b|runway|craiyon|nightcafe|dreamstudio|fooocus",
    re.IGNORECASE,
)
PIXEL_WATERMARK_NOTE = (
    "Pixel-domain / invisible watermarks: NOT ASSESSED. SynthProvenance inspects metadata and provenance "
    "containers only; it does not detect or evaluate watermarks embedded in pixel values."
)


def source_type_term(value: str) -> str:
    """Last path segment of an IPTC digital-source-type URI."""
    return (value or "").rstrip("/").rsplit("/", 1)[-1].strip()


def compute_signal(analysis: "Analysis", condition: str = "baseline") -> AISignal:
    evidence: list[SignalEvidence] = []
    interp: list[SignalEvidence] = []
    unknowns: list[str] = []
    groups = analysis.groups
    rep = analysis.c2pa

    # 1. C2PA actions (all manifests in the store)
    for m in rep.manifests:
        for a in m.actions:
            term = source_type_term(a.digital_source_type)
            if not term:
                continue
            where = f"C2PA {m.label} / {a.action}"
            if term in AI_SOURCE_TYPES:
                note = f"Hard binding: {rep.hard_binding}. Signature validity: {rep.validity}."
                if rep.hard_binding == "MISMATCH":
                    note += " The manifest does not bind to the current bytes."
                evidence.append(SignalEvidence(TIER_EVIDENCE, where, "digitalSourceType", a.digital_source_type, True, note))
            elif term in SYNTHETIC_SOURCE_TYPES:
                interp.append(SignalEvidence(TIER_INTERPRETATION, where, "digitalSourceType", a.digital_source_type, False,
                                             "Synthetic but not a generative-AI source type; recorded, not counted."))
            else:
                interp.append(SignalEvidence(TIER_INTERPRETATION, where, "digitalSourceType", a.digital_source_type, False,
                                             "Non-AI source type declared."))
        if m.claim_generator and GENERATOR_NAME_PATTERN.search(m.claim_generator):
            interp.append(SignalEvidence(TIER_INTERPRETATION, f"C2PA {m.label}", "claim_generator", m.claim_generator,
                                         False, "Generator-associated name in claim generator (heuristic)."))
    if rep.state == ItemState.INVALID.value:
        unknowns.append(f"C2PA data present but not decodable: {rep.summary}")
    elif rep.state == ItemState.UNKNOWN.value:
        unknowns.append(rep.summary)

    # 2. XMP declarations
    xmp = groups.get("XMP")
    if xmp is not None:
        for f in xmp.fields:
            base = f.key.split("/")[0].split("[")[0]
            if base == "Iptc4xmpExt:DigitalSourceType" or f.key.endswith("Iptc4xmpExt:DigitalSourceType"):
                term = source_type_term(f.value)
                if term in AI_SOURCE_TYPES:
                    evidence.append(SignalEvidence(TIER_EVIDENCE, "XMP", f.key, f.value, True,
                                                   "IPTC Digital Source Type declares generative-AI media."))
                elif term in SYNTHETIC_SOURCE_TYPES:
                    interp.append(SignalEvidence(TIER_INTERPRETATION, "XMP", f.key, f.value, False,
                                                 "Synthetic but not generative-AI; recorded, not counted."))
                elif term:
                    interp.append(SignalEvidence(TIER_INTERPRETATION, "XMP", f.key, f.value, False,
                                                 "Non-AI digital source type declared."))
            elif base == "Iptc4xmpExt:AISystemUsed":
                evidence.append(SignalEvidence(TIER_EVIDENCE, "XMP", f.key, f.value, True,
                                               "IPTC 'AI System Used' property declared."))
            elif f.category == "software" and GENERATOR_NAME_PATTERN.search(f.value or ""):
                interp.append(SignalEvidence(TIER_INTERPRETATION, "XMP", f.key, f.value, False,
                                             "Generator-associated software name (heuristic)."))
        if xmp.state == ItemState.INVALID:
            unknowns.append("XMP packet present but invalid; declarations inside it are not observable.")

    # 3. Generator-parameter records (PNG text chunks, EXIF free text)
    for keyword, text, chunk in analysis.png_texts:
        hit = detect_generator_record(keyword, text)
        if hit is None:
            continue
        structured, desc = hit
        (evidence if structured else interp).append(SignalEvidence(
            TIER_EVIDENCE if structured else TIER_INTERPRETATION, f"PNG {chunk}", keyword,
            (text[:160] + "...") if len(text) > 160 else text, structured, desc))
    exif = groups.get("EXIF")
    if exif is not None:
        for f in exif.fields:
            if f.key in ("UserComment", "ImageDescription"):
                hit = detect_generator_record("parameters", f.value)
                if hit and hit[0]:
                    evidence.append(SignalEvidence(TIER_EVIDENCE, "EXIF", f.key, f.value[:160], True, hit[1]))
            if f.category == "software" and GENERATOR_NAME_PATTERN.search(f.value or ""):
                interp.append(SignalEvidence(TIER_INTERPRETATION, "EXIF", f.key, f.value, False,
                                             "Generator-associated software name (heuristic)."))
        if exif.state == ItemState.INVALID:
            unknowns.append("EXIF block present but invalid.")
    for gname in ("IPTC", "PNG CHUNKS", "JPEG APP MARKERS"):
        g = groups.get(gname)
        if g is None:
            continue
        for f in g.fields:
            if f.category in ("software", "generator") and GENERATOR_NAME_PATTERN.search(f.value or ""):
                if not any(e.value == f.value for e in interp):
                    interp.append(SignalEvidence(TIER_INTERPRETATION, gname, f.key, f.value[:160], False,
                                                 "Generator-associated name (heuristic)."))
        if g.state == ItemState.INVALID:
            unknowns.append(f"{gname} present but invalid.")

    if analysis.info.format not in ("JPEG", "PNG", "WEBP"):
        unknowns.append(f"{analysis.info.format}: byte-level provenance containers are not inspected for this format.")
    unknowns.append(PIXEL_WATERMARK_NOTE)

    if evidence:
        state = SIGNAL_OBSERVED
        statement = (f"{len(evidence)} observable AI-content provenance declaration(s) found under the "
                     f"'{condition}' condition. This reflects declared provenance, not a pixel-level determination.")
    elif any(not u.startswith("Pixel-domain") for u in unknowns if "invalid" in u.lower() or "not decodable" in u.lower()):
        state = SIGNAL_UNKNOWN
        statement = ("No counted evidence was found, but at least one provenance-bearing container is invalid, "
                     "so the absence of a signal cannot be established.")
    else:
        state = SIGNAL_NOT_OBSERVED
        statement = NOT_OBSERVED_MEANING
    return AISignal(state=state, statement=statement, condition=condition, evidence=evidence, interpretations=interp,
                    unknowns=unknowns)


# ------------------------------------------------------------ provenance graph

GRAPH_STAGES = ["SOURCE", "GENERATED", "EDITED", "ENCODED", "SANITIZED", "EXPERIMENTAL OUTPUT"]
CREATION_ACTIONS = {"c2pa.created"}
NON_EDIT_ACTIONS = {"c2pa.created", "c2pa.opened", "c2pa.placed", "c2pa.published", "c2pa.managed"}


def _node(stage: str, state: str, basis: str, **kw) -> dict:
    node = {"stage": stage, "state": state, "basis": basis, "timestamp": "", "hash": "", "operation": "", "tool": "",
            "parameters": {}, "metadata_state": "", "provenance_state": "", "details": []}
    node.update(kw)
    return node


def build_provenance_graph(baseline: dict, transformations: list | None = None) -> list[dict]:
    """Build SOURCE -> ... -> EXPERIMENTAL OUTPUT nodes from persisted dicts.

    Nodes without evidence are marked NOT OBSERVED rather than filled in.
    """
    transformations = transformations or []
    c2pa = baseline.get("c2pa") or {}
    manifests = c2pa.get("manifests") or []
    signal = baseline.get("signal") or {}
    groups = baseline.get("groups") or {}
    image = baseline.get("image") or {}
    hashes = baseline.get("hashes") or {}
    history = baseline.get("xmp_history") or []
    nodes: list[dict] = []

    # SOURCE
    ingredients = [ing for m in manifests for ing in (m.get("ingredients") or [])]
    if ingredients:
        nodes.append(_node("SOURCE", "OBSERVED", TIER_EVIDENCE, operation="ingredient(s) declared in C2PA manifest",
                           tool="C2PA", provenance_state=f"{len(ingredients)} ingredient(s)",
                           details=[f"{i.get('title') or '(untitled)'} [{i.get('relationship') or 'unspecified'}] "
                                    f"{'with manifest' if i.get('has_manifest') else ''}".strip() for i in ingredients]))
    else:
        nodes.append(_node("SOURCE", "NOT OBSERVED", TIER_UNKNOWN,
                           details=["No ingredient or source record is present in the file."]))

    # GENERATED
    gen_details, gen_ts, gen_tool = [], "", ""
    for m in manifests:
        for a in m.get("actions") or []:
            if a.get("action") in CREATION_ACTIONS:
                gen_details.append(f"C2PA {a.get('action')} digitalSourceType={source_type_term(a.get('digital_source_type', '')) or 'unspecified'}")
                gen_ts = gen_ts or a.get("when", "")
                gen_tool = gen_tool or a.get("software_agent", "") or m.get("claim_generator", "")
    for e in signal.get("evidence") or []:
        if e.get("source", "").startswith(("XMP", "PNG", "EXIF")):
            gen_details.append(f"{e.get('source')} {e.get('field')}: {str(e.get('value'))[:80]}")
    if gen_details:
        nodes.append(_node("GENERATED", "OBSERVED", TIER_EVIDENCE, timestamp=gen_ts, tool=gen_tool,
                           operation="creation declared", provenance_state=signal.get("state", ""), details=gen_details))
    else:
        nodes.append(_node("GENERATED", "NOT OBSERVED", TIER_UNKNOWN,
                           details=["No creation / generation record observed. This does not establish how the "
                                    "image was produced."]))

    # EDITED
    edit_details, edit_ts = [], ""
    for m in manifests:
        for a in m.get("actions") or []:
            if a.get("action") not in NON_EDIT_ACTIONS:
                edit_details.append(f"C2PA {a.get('action')}" + (f" by {a.get('software_agent')}" if a.get("software_agent") else ""))
                edit_ts = a.get("when", "") or edit_ts
    for ev in history:
        if ev.get("action"):
            edit_details.append(f"XMP history: {ev.get('action')}" + (f" ({ev.get('softwareAgent')})" if ev.get("softwareAgent") else ""))
            edit_ts = ev.get("when", "") or edit_ts
    if edit_details:
        nodes.append(_node("EDITED", "OBSERVED", TIER_EVIDENCE, timestamp=edit_ts, operation="edit actions declared",
                           details=edit_details[:40]))
    else:
        nodes.append(_node("EDITED", "NOT OBSERVED", TIER_UNKNOWN, details=["No edit history observed."]))

    # ENCODED (the file as loaded)
    group_summary = ", ".join(f"{k}:{v.get('state')}" for k, v in groups.items() if k != "SOFTWARE")
    software = [f.get("value") for f in (groups.get("SOFTWARE") or {}).get("fields", [])][:3]
    nodes.append(_node("ENCODED", "OBSERVED", TIER_EVIDENCE, hash=hashes.get("sha256", ""),
                       operation=f"input file: {image.get('format', '')} {image.get('width')}x{image.get('height')}",
                       tool="; ".join(software) or "not declared",
                       parameters={"compression": (baseline.get("compression") or {}).get("summary", "")},
                       metadata_state=group_summary, provenance_state=f"C2PA {c2pa.get('state', 'UNKNOWN')}; signal "
                       f"{signal.get('state', 'UNKNOWN')}", details=[image.get("filename", "")]))

    # SANITIZED / EXPERIMENTAL OUTPUT (from this experiment)
    def as_dict(t):
        return t.to_dict() if hasattr(t, "to_dict") else t

    recs = [as_dict(t) for t in transformations if as_dict(t).get("status") == "COMPLETE"]
    san = [t for t in recs if t.get("operation") == "metadata_sanitize"]
    other = [t for t in recs if t.get("operation") != "metadata_sanitize"]
    for stage, items in (("SANITIZED", san), ("EXPERIMENTAL OUTPUT", other)):
        if not items:
            nodes.append(_node(stage, "NOT RUN", TIER_UNKNOWN, details=["No transformation of this kind recorded yet."]))
            continue
        last = items[-1]
        pm = last.get("pixel_metrics") or {}
        nodes.append(_node(
            stage, "RECORDED", "EXPERIMENT RECORD", timestamp=last.get("timestamp", ""), hash=last.get("output_sha256", ""),
            operation=f"{last.get('transformation_id')} {last.get('label')}", tool="SynthProvenance",
            parameters=last.get("parameters", {}),
            metadata_state=", ".join(f"{k}:{v.get('state')}" for k, v in (last.get("metadata_group_states") or {}).items()
                                     if k != "SOFTWARE"),
            provenance_state=f"signal {last.get('signal_before')} -> {last.get('signal_after')}; "
                             f"C2PA {(last.get('provenance_differences') or {}).get('c2pa_after', '?')}",
            details=[f"{t.get('transformation_id')} {t.get('label')}: {(t.get('pixel_metrics') or {}).get('verdict', '')}"
                     for t in items] + ([f"pixels: {pm.get('verdict')}"] if pm else [])))
    return nodes
