"""Cross-detector research engine (pure: numpy/stdlib, no Qt, no network).

SynthProvenance is an INDEPENDENT FORENSIC SYSTEM. An external commercial detector
(e.g. TruthScan) is an EXTERNAL DETECTOR whose result is *evidence to study*, never
ground truth. This module compares an imported, user-supplied external result against
SynthProvenance's own local, descriptive evidence and reports where they agree, where
they disagree, and what remains unknown.

Scientific rules enforced here (see docs/CROSS_DETECTOR_RESEARCH.md):

* SynthProvenance never emits an "AI vs human" verdict from pixels. Its local evidence is
  descriptive; a dimension only *leans* a direction, and most stay DESCRIPTIVE.
* The comparison never calls the external detector "wrong" or SynthProvenance "correct"
  unless the ground-truth level is high enough to support that (LEVEL >= 3), and then it is
  phrased as "matches / does not match the known ground truth", not as a judgement of a system.
* Fingerprint families (INTRINSIC / CAUSAL / SPECTRAL / PROACTIVE / DETECTOR_REPRESENTATION /
  RECONSTRUCTION / PROVENANCE) are kept distinct, as the taxonomy file insists.

Nothing here contacts a network or uploads an image.
"""
from __future__ import annotations


from dataclasses import dataclass, field

from app.models.experiment import utc_now
from app.utils.serialization import jsonable

# ------------------------------------------------------------------ ground-truth hierarchy (Section 8)
GROUND_TRUTH_LEVELS: dict[int, str] = {
    0: "Unknown origin",
    1: "Observer-reported origin (unverified)",
    2: "Known generator + known source dataset",
    3: "Locally generated controlled sample",
    4: "Known watermark / fingerprint ground truth",
    5: "Reproducible synthetic benchmark",
}
# at or above this level the known truth is strong enough to say an external label matches it or not
GROUND_TRUTH_DECISIVE = 3

# direction a piece of evidence or a label points, toward synthetic or toward authentic/natural
LEANS_SYNTHETIC = "LEANS SYNTHETIC"
LEANS_AUTHENTIC = "LEANS AUTHENTIC"
DESCRIPTIVE = "DESCRIPTIVE"           # measured, but does not by itself favour either origin
NOT_EVALUATED = "NOT EVALUATED"
UNKNOWN = "UNKNOWN"

# comparison outcomes (Section 7)
AGREEMENT = "AGREEMENT"
PARTIAL = "PARTIAL AGREEMENT"
DISAGREEMENT = "DISAGREEMENT"
INSUFFICIENT = "INSUFFICIENT EVIDENCE"

# evidence-mapper fingerprint families (Section 16), kept distinct from one another
FAMILY_INTRINSIC = "INTRINSIC"
FAMILY_CAUSAL = "CAUSAL"
FAMILY_SPECTRAL = "SPECTRAL"
FAMILY_PROACTIVE = "PROACTIVE WATERMARK"
FAMILY_DETECTOR_REP = "DETECTOR REPRESENTATION"
FAMILY_RECONSTRUCTION = "RECONSTRUCTION"
FAMILY_PROVENANCE = "PROVENANCE"
FAMILIES = (FAMILY_INTRINSIC, FAMILY_CAUSAL, FAMILY_SPECTRAL, FAMILY_PROACTIVE, FAMILY_DETECTOR_REP,
            FAMILY_RECONSTRUCTION, FAMILY_PROVENANCE)

SOURCE_EXTERNAL = "EXTERNAL / USER-SUPPLIED"

# words that map a free-text external label to a direction (lower-cased substring match)
_SYNTHETIC_WORDS = ("ai generated", "ai-generated", "aigenerated", "synthetic", "fake", "generated", "deepfake",
                    "artificial", "machine generated", "gan", "diffusion", "likely ai", "ai image")
_AUTHENTIC_WORDS = ("human", "real", "authentic", "genuine", "camera", "photograph", "natural", "not ai", "no ai",
                    "not generated", "likely real", "likely human")
_UNCERTAIN_WORDS = ("uncertain", "inconclusive", "unknown", "unsure", "possibly", "maybe", "ambiguous")


# ------------------------------------------------------------------ external result
def _to_confidence(value) -> float | None:
    """Normalise a confidence to [0, 1]. Accepts 0.97, 97, '97%', '0.97', 'high'."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        v = float(value)
    else:
        s = str(value).strip().lower().rstrip("%").strip()
        words = {"very high": 0.95, "high": 0.85, "medium": 0.6, "moderate": 0.6, "low": 0.3, "very low": 0.15}
        if s in words:
            return words[s]
        try:
            v = float(s)
        except ValueError:
            return None
    if v > 1.0:
        v = v / 100.0
    return max(0.0, min(1.0, v))


def label_direction(text: str) -> str:
    t = str(text or "").strip().lower()
    if not t:
        return UNKNOWN
    if any(w in t for w in _UNCERTAIN_WORDS):
        return DESCRIPTIVE
    syn = any(w in t for w in _SYNTHETIC_WORDS)
    auth = any(w in t for w in _AUTHENTIC_WORDS)
    if syn and not auth:
        return LEANS_SYNTHETIC
    if auth and not syn:
        return LEANS_AUTHENTIC
    return UNKNOWN


def _first(d: dict, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] not in (None, ""):
            return d[k]
    return default


def _stage_state(d: dict, *keys) -> str:
    v = _first(d, *keys)
    if v is None:
        return "NOT REPORTED"
    if isinstance(v, bool):
        return "DETECTED" if v else "NOT DETECTED"
    if isinstance(v, dict):
        inner = _first(v, "state", "status", "result", "label", "verdict")
        return str(inner) if inner is not None else "REPORTED"
    return str(v)[:200]


@dataclass
class ExternalResult:
    """A user-supplied result from an external detector. Imported, never fetched by this app."""
    detector: str = "TruthScan"
    source: str = SOURCE_EXTERNAL
    final_result: str = ""
    direction: str = UNKNOWN
    confidence: float | None = None
    detection_step: int | None = None
    metadata_state: str = "NOT REPORTED"
    ocr_watermark_state: str = "NOT REPORTED"
    ml_state: str = "NOT REPORTED"
    warnings: list = field(default_factory=list)
    heatmap_ref: str = ""
    external_submission_id: str = ""
    file_hash: str = ""
    timestamp: str = ""
    imported_utc: str = ""
    notes: str = ""
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return jsonable(self)

    @property
    def detection_step_text(self) -> str:
        return {1: "1 = metadata only", 2: "2 = metadata + OCR/watermark",
                3: "3 = metadata + OCR/watermark + ML model"}.get(self.detection_step, "not reported")

    @classmethod
    def from_markdown(cls, text: str, detector: str = "TruthScan") -> "ExternalResult":
        """Import a Markdown research archive.

        A research archive is methodological context, NOT a per-image result, so it is imported as a reference only:
        the documented pipeline stages and the FACT / INFERENCE distinction are extracted into ``raw`` and the
        direction stays UNKNOWN (it never drives a comparison as this image's label). A concrete per-image result must
        be imported through ``from_json`` / ``from_fields`` instead (v6 Section 36).
        """
        import re as _re
        body = str(text or "")
        documented_stages = [ln.strip("# ").strip() for ln in body.splitlines()
                             if _re.match(r"^#{2,3}\s*(Tahap|Stage|Step)\b", ln.strip(), _re.IGNORECASE)][:20]
        facts = [ln.strip() for ln in body.splitlines() if "[FAKTA]" in ln or "Terdokumentasi" in ln][:12]
        inferences = [ln.strip() for ln in body.splitlines() if "[INFERENSI]" in ln or "[INFERENCE]" in ln][:12]
        documented_fields = sorted({m for m in _re.findall(r"`(final_result|detection_step|confidence|ocr|synthid|"
                                                           r"ml_model|result|warnings|heatmap)`", body)})
        ref = {"archive_reference": True, "documented_stages": documented_stages, "documented_fields": documented_fields,
               "facts_sample": facts, "inferences_sample": inferences,
               "caveat": "Model architecture, weights, training data and decision thresholds are undisclosed, and the "
                         "99%+ accuracy claim is not independently validated. This import is methodological context, "
                         "not a per-image result."}
        return cls(detector=detector, direction=UNKNOWN,
                   final_result="(methodological reference — no per-image result)", imported_utc=utc_now(),
                   notes="Imported a research archive as methodological context. It carries no per-image result; import "
                         "a concrete JSON/CSV result or enter one manually to run a comparison.", raw=ref)

    @classmethod
    def from_csv(cls, text: str, detector: str = "TruthScan") -> "ExternalResult":
        """Import a one-row CSV result (header row + one data row)."""
        import csv as _csv
        import io as _io
        rows = list(_csv.DictReader(_io.StringIO(str(text or ""))))
        if not rows:
            raise ValueError("CSV has no data row")
        return cls.from_json({k.strip(): v for k, v in rows[0].items() if k}, detector)

    @classmethod
    def from_fields(cls, detector: str = "TruthScan", final_result: str = "", confidence=None, detection_step=None,
                    metadata_state: str = "NOT REPORTED", ocr_watermark_state: str = "NOT REPORTED",
                    ml_state: str = "NOT REPORTED", warnings: list | None = None, heatmap_ref: str = "",
                    external_submission_id: str = "", file_hash: str = "", timestamp: str = "",
                    notes: str = "") -> "ExternalResult":
        return cls(detector=detector or "TruthScan", final_result=final_result,
                   direction=label_direction(final_result), confidence=_to_confidence(confidence),
                   detection_step=int(detection_step) if str(detection_step).strip().isdigit() else None,
                   metadata_state=metadata_state or "NOT REPORTED", ocr_watermark_state=ocr_watermark_state or "NOT REPORTED",
                   ml_state=ml_state or "NOT REPORTED", warnings=list(warnings or []), heatmap_ref=heatmap_ref,
                   external_submission_id=external_submission_id, file_hash=file_hash, timestamp=timestamp,
                   imported_utc=utc_now(), notes=notes, raw={})

    @classmethod
    def from_json(cls, blob: dict, detector: str = "TruthScan") -> "ExternalResult":
        """Tolerant parse of a TruthScan-style result. Field names must be re-verified against current docs.

        Recognises the documented shape: a final label / result, a confidence, ``detection_step`` (1/2/3), and
        per-stage metadata / OCR-watermark / ML state, warnings and an optional heatmap reference, under several
        common key spellings. Unknown structures are still kept verbatim under ``raw``.
        """
        if not isinstance(blob, dict):
            raise ValueError("external result must be a JSON object")
        # the detection payload may be nested under result/data/detection/details
        d = blob
        for key in ("result", "results", "data", "detection", "details", "response"):
            inner = blob.get(key)
            if isinstance(inner, dict):
                d = {**blob, **inner}
                break
        final = _first(d, "final_result", "finalResult", "result", "label", "verdict", "classification", "prediction",
                       default="")
        if isinstance(final, dict):
            final = _first(final, "label", "result", "verdict", default=str(final))
        conf = _first(d, "confidence", "confidence_score", "confidenceScore", "score", "probability", "ai_probability",
                      "aiProbability", "likelihood")
        step = _first(d, "detection_step", "detectionStep", "step", "analysis_level", "level")
        warnings = _first(d, "warnings", "warning", "flags", default=[])
        if isinstance(warnings, (str, dict)):
            warnings = [warnings]
        heat = _first(d, "heatmap", "heatmap_url", "heatmapUrl", "heat_map", "heatmap_reference", "heatmapRef",
                      "visualization", default="")
        if isinstance(heat, dict):
            heat = _first(heat, "url", "path", "reference", default="")
        obj = cls(
            detector=detector or _first(d, "detector", "model", "engine", default="TruthScan"),
            final_result=str(final), direction=label_direction(str(final)), confidence=_to_confidence(conf),
            detection_step=int(step) if str(step).strip().isdigit() else None,
            metadata_state=_stage_state(d, "metadata", "metadata_result", "metadataResult", "metadata_state"),
            ocr_watermark_state=_stage_state(d, "ocr", "watermark", "ocr_result", "ocrResult", "ocr_watermark",
                                             "watermark_result"),
            ml_state=_stage_state(d, "ml", "ml_model", "mlModel", "model_result", "modelResult", "ml_result", "ai_model"),
            warnings=[str(w)[:300] for w in (warnings if isinstance(warnings, list) else [warnings]) if w],
            heatmap_ref=str(heat or ""),
            external_submission_id=str(_first(d, "id", "submission_id", "submissionId", "request_id", "scan_id",
                                              default="")),
            file_hash=str(_first(d, "file_hash", "fileHash", "sha256", "hash", default="")),
            timestamp=str(_first(d, "timestamp", "created_at", "createdAt", "date", "time", default="")),
            imported_utc=utc_now(), raw=dict(blob))
        return obj


# ------------------------------------------------------------------ local evidence
@dataclass
class EvidenceDimension:
    name: str
    family: str
    representation: str
    direction: str = DESCRIPTIVE
    observation: str = ""
    method: str = ""
    ground_truth_level: int = 0
    validation_status: str = "DESCRIPTIVE"
    strength: str = "weak"       # weak / moderate / strong (qualitative; never a probability)

    def to_dict(self) -> dict:
        return jsonable(self)


@dataclass
class EvidenceItem:
    """The Evidence Mapper record (Section 17): one observed feature -> fingerprint family + reference."""
    evidence_id: str
    family: str
    representation: str
    method: str
    observation: str
    source_reference: str
    confidence: str
    ground_truth: str
    validation_status: str

    def to_dict(self) -> dict:
        return jsonable(self)


@dataclass
class LocalEvidence:
    dimensions: list = field(default_factory=list)          # EvidenceDimension
    evidence_items: list = field(default_factory=list)       # EvidenceItem
    provenance_summary: str = ""
    ground_truth_level: int = 0
    note: str = ("SynthProvenance reports descriptive forensic evidence and does not produce an AI/human verdict from "
                 "pixels. Dimensions that 'lean' a direction are cues, not conclusions.")

    def to_dict(self) -> dict:
        return jsonable(self)

    def dimension(self, name: str) -> EvidenceDimension | None:
        return next((d for d in self.dimensions if d.name == name), None)

    def overall_direction(self) -> str:
        syn = sum(1 for d in self.dimensions if d.direction == LEANS_SYNTHETIC)
        auth = sum(1 for d in self.dimensions if d.direction == LEANS_AUTHENTIC)
        if syn and not auth:
            return LEANS_SYNTHETIC
        if auth and not syn:
            return LEANS_AUTHENTIC
        if syn and auth:
            return UNKNOWN
        return DESCRIPTIVE


def _num(readouts: dict, key, default=None):
    v = (readouts or {}).get(key)
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def local_evidence_from_easy(easy: dict, ground_truth_level: int = 0) -> LocalEvidence:
    """Distil the SynthProvenance local evidence from an EasyModeResult dict.

    Provenance leans a direction (a verified camera C2PA vs an AI-tool declaration); every pixel-domain dimension stays
    DESCRIPTIVE unless a controlled surrogate provides ground truth. This mirrors the app's 'measure, do not guess' stance.
    """
    prov = easy.get("provenance") or {}
    methods = {m.get("method_id"): m for m in (easy.get("methods") or [])}

    def readouts(mid) -> dict:
        return (methods.get(mid) or {}).get("readouts") or {}

    def ran(mid) -> bool:
        m = methods.get(mid) or {}
        return m.get("decision") == "RUN" and m.get("status") in ("COMPLETE", "SIGNAL PERSISTED")

    dims: list[EvidenceDimension] = []
    items: list[EvidenceItem] = []
    n = [0]

    def add_item(family, rep, method, observation, ref, conf, gt, status):
        n[0] += 1
        items.append(EvidenceItem(f"EVIDENCE-{n[0]:03d}", family, rep, method, observation, ref, conf, gt, status))

    # --- PROVENANCE (metadata-declared origin; distinct from an intrinsic fingerprint)
    c2 = str(prov.get("c2pa_state", "NOT PRESENT"))
    ai_decl = str(prov.get("ai_declaration", "UNKNOWN"))
    binding = str(prov.get("c2pa_hard_binding", ""))
    if ai_decl == "OBSERVED":
        pdir, pobs = LEANS_SYNTHETIC, f"Provenance metadata declares AI generation (C2PA {c2}; {prov.get('ai_declaration_statement','')[:120]})."
        pstr = "moderate"
    elif c2.startswith("PRESENT") and binding == "MATCH" and ai_decl in ("NOT OBSERVED", "UNKNOWN"):
        pdir, pobs = LEANS_AUTHENTIC, "A C2PA manifest with a matching hard binding is present and declares no AI generation (signatures not cryptographically validated)."
        pstr = "weak"
    else:
        pdir, pobs = DESCRIPTIVE, f"C2PA {c2}; AI-content declaration {ai_decl}. Absence of a declaration proves nothing."
        pstr = "weak"
    dims.append(EvidenceDimension("Provenance (C2PA / metadata)", FAMILY_PROVENANCE, "signed metadata", pdir, pobs,
                                  "Method 02 C2PA + Method 01 metadata", ground_truth_level, "OBSERVED", pstr))
    add_item(FAMILY_PROVENANCE, "C2PA/JUMBF", "Method 02 C2PA Manifest Analysis", pobs,
             "C2PA 2.4 spec; taxonomy 4K", pstr, GROUND_TRUTH_LEVELS[ground_truth_level], "OBSERVED")

    # --- SynthID embedded-signal layer (only from a local engine)
    sid = str(prov.get("synthid_state", "UNAVAILABLE"))
    sid_dir = DESCRIPTIVE if sid in ("DETECTED",) else NOT_EVALUATED if sid == "UNAVAILABLE" else DESCRIPTIVE
    dims.append(EvidenceDimension("SynthID (embedded signal)", FAMILY_PROACTIVE, "pixel watermark",
                                  sid_dir, f"SynthID {sid} (local verification engine only; never inferred from metadata).",
                                  "Local SynthID engine", ground_truth_level,
                                  "NOT MEASURED" if sid == "UNAVAILABLE" else "OBSERVED", "weak"))

    # --- SPECTRAL (FFT tail / periodic peaks; descriptive)
    if ran("Method 13") or ran("Method 16"):
        r = {**readouts("Method 13"), **readouts("Method 16")}
        tail = _num(r, "Tail excess (dB)")
        peaks = r.get("Grid-aligned peaks")
        obs = (f"Spectral tail excess {tail:+.2f} dB; " if tail is not None else "") + \
              (f"{peaks} grid-aligned periodic peak(s)." if peaks is not None else "radial/periodogram computed.")
        dims.append(EvidenceDimension("Spectral", FAMILY_SPECTRAL, "FFT", DESCRIPTIVE, obs,
                                      "Method 13 FFT / Method 16 Spectral Tail", ground_truth_level, "DESCRIPTIVE",
                                      "moderate" if (tail and abs(tail) > 1.0) else "weak"))
        add_item(FAMILY_SPECTRAL, "FFT", "Method 13 FFT Analysis", obs, "Durall 2020; Frank 2020; taxonomy 3A",
                 "descriptive", GROUND_TRUTH_LEVELS[ground_truth_level], "DESCRIPTIVE")
    # --- DCT (Benford / block statistics)
    if ran("Method 14") or ran("Method 18"):
        r = {**readouts("Method 14"), **readouts("Method 18")}
        obs = "; ".join(f"{k}: {v}" for k, v in list(r.items())[:3]) or "block-DCT statistics computed."
        dims.append(EvidenceDimension("DCT / Benford", FAMILY_SPECTRAL, "DCT", DESCRIPTIVE, obs,
                                      "Method 14 DCT / Method 18 Benford-DCT", ground_truth_level, "DESCRIPTIVE", "weak"))
    # --- RESIDUAL / INTRINSIC
    if ran("Method 03") or ran("Method 17"):
        r = {**readouts("Method 03"), **readouts("Method 17")}
        obs = "; ".join(f"{k}: {v}" for k, v in list(r.items())[:3]) or "high-frequency residual statistics computed."
        dims.append(EvidenceDimension("Residual (intrinsic)", FAMILY_INTRINSIC, "high-pass residual", DESCRIPTIVE, obs,
                                      "Method 03 Residual Fingerprint / Method 17 High-Frequency Residual",
                                      ground_truth_level, "DESCRIPTIVE", "weak"))
        add_item(FAMILY_INTRINSIC, "residual", "Method 03 Residual Fingerprint", obs, "Marra 2019; taxonomy 1B/3F",
                 "descriptive", GROUND_TRUTH_LEVELS[ground_truth_level], "DESCRIPTIVE")
    # --- WAVELET
    if ran("Method 15"):
        r = readouts("Method 15")
        obs = "; ".join(f"{k}: {v}" for k, v in list(r.items())[:3]) or "multi-level DWT sub-band statistics computed."
        dims.append(EvidenceDimension("Wavelet", FAMILY_SPECTRAL, "DWT", DESCRIPTIVE, obs,
                                      "Method 15 DWT / Wavelet Analysis", ground_truth_level, "DESCRIPTIVE", "weak"))
    # --- RECONSTRUCTION cue (training-free prior)
    if ran("Method 55"):
        r = readouts("Method 55")
        obs = "; ".join(f"{k}: {v}" for k, v in list(r.items())[:2]) or "training-free reconstruction error map computed."
        dims.append(EvidenceDimension("Reconstruction cue", FAMILY_RECONSTRUCTION, "self-supervised prior", DESCRIPTIVE,
                                      obs + " (NOT a diffusion/AE reconstruction; DIRE/AEROBLADE are UNAVAILABLE).",
                                      "Method 55 Reconstruction Forensics", ground_truth_level, "DESCRIPTIVE", "weak"))
        add_item(FAMILY_RECONSTRUCTION, "image prior", "Method 55 Reconstruction Forensics", obs,
                 "He 2013 guided filter; cf. DIRE/AEROBLADE", "descriptive", GROUND_TRUTH_LEVELS[ground_truth_level],
                 "DESCRIPTIVE")
    # --- DETECTOR REPRESENTATION (learned) — unavailable without a model, stated honestly
    dims.append(EvidenceDimension("Learned representation (CLIP/ViT/DINO)", FAMILY_DETECTOR_REP, "deep features",
                                  NOT_EVALUATED,
                                  "No deep-learning runtime or trained weights are bundled; learned-feature detectors are UNAVAILABLE.",
                                  "Methods 26-29 (UNAVAILABLE)", ground_truth_level, "NOT IMPLEMENTED", "weak"))

    # --- CONTROLLED SURROGATE (ground truth) — only decisive dimension, about the keyed lab signal, not real origin
    cc = easy.get("controlled_case") or {}
    if cc.get("valid_ground_truth"):
        recon = easy.get("reconstruction_status", "")
        best = easy.get("best_candidate", "")
        dims.append(EvidenceDimension("Controlled surrogate (ground truth)", FAMILY_PROACTIVE, "keyed surrogate",
                                      DESCRIPTIVE,
                                      f"On a keyed local surrogate (known ground truth), reconstruction {recon}"
                                      + (f" ({best})." if best else "."),
                                      "Methods 34-38/55 controlled separation", 4, "VALIDATED (surrogate)", "strong"))
        add_item(FAMILY_PROACTIVE, "surrogate", "Controlled separation study", f"reconstruction {recon} {best}".strip(),
                 "WAVES; RPCA; taxonomy robustness", "validated (surrogate only)", GROUND_TRUTH_LEVELS[4],
                 "VALIDATED (surrogate)")

    ev = LocalEvidence(dims, items, pobs, ground_truth_level)
    return ev


# ------------------------------------------------------------------ comparison (Section 7, 13)
@dataclass
class CrossDetectorComparison:
    detector: str
    external: dict
    outcome: str = INSUFFICIENT
    ground_truth_level: int = 0
    ground_truth_label: str = ""
    local_direction: str = DESCRIPTIVE
    external_direction: str = UNKNOWN
    agreements: list = field(default_factory=list)
    disagreements: list = field(default_factory=list)
    unknowns: list = field(default_factory=list)
    external_vs_truth: str = "not evaluable without ground truth"
    local_vs_truth: str = "not evaluable without ground truth"
    statement: str = ""
    dimension_rows: list = field(default_factory=list)   # [{dimension, family, local_direction, observation, vs_external}]

    def to_dict(self) -> dict:
        return jsonable(self)


def _vs_external(dim: EvidenceDimension, ext_dir: str) -> str:
    if dim.direction in (NOT_EVALUATED, UNKNOWN):
        return "no independent evidence"
    if dim.direction == DESCRIPTIVE:
        return "descriptive (neither confirms nor refutes the external label)"
    if ext_dir == UNKNOWN:
        return "external label unclear"
    return "consistent with external label" if dim.direction == ext_dir else "inconsistent with external label"


def compare(local: LocalEvidence, external: ExternalResult, ground_truth_level: int = 0,
            ground_truth_direction: str = UNKNOWN) -> CrossDetectorComparison:
    """Compare local evidence with an external result. Never declares a system right or wrong."""
    gt_level = int(ground_truth_level or local.ground_truth_level or 0)
    ext_dir = external.direction
    rows, agrees, disagrees, unknowns = [], [], [], []
    for d in local.dimensions:
        verdict = _vs_external(d, ext_dir)
        rows.append({"dimension": d.name, "family": d.family, "local_direction": d.direction,
                     "observation": d.observation, "vs_external": verdict, "strength": d.strength})
        if verdict == "consistent with external label":
            agrees.append(d.name)
        elif verdict == "inconsistent with external label":
            disagrees.append(d.name)
        elif d.direction in (NOT_EVALUATED, UNKNOWN):
            unknowns.append(d.name)

    local_dir = local.overall_direction()
    # overall outcome from the independent local evidence vs the external label
    if ext_dir == UNKNOWN:
        outcome = INSUFFICIENT
    elif disagrees and agrees:
        outcome = PARTIAL
    elif disagrees:
        outcome = DISAGREEMENT
    elif agrees:
        outcome = AGREEMENT if local_dir == ext_dir else PARTIAL
    else:
        outcome = INSUFFICIENT   # local evidence is purely descriptive

    # ground-truth comparison (only phrasing allowed to say "matches / does not match")
    ext_vs_truth = local_vs_truth = "not evaluable without ground truth (LEVEL < 3)"
    if gt_level >= GROUND_TRUTH_DECISIVE and ground_truth_direction in (LEANS_SYNTHETIC, LEANS_AUTHENTIC):
        ext_vs_truth = ("matches the known ground truth" if ext_dir == ground_truth_direction
                        else "does not match the known ground truth" if ext_dir in (LEANS_SYNTHETIC, LEANS_AUTHENTIC)
                        else "external label is unclear relative to ground truth")
        if local_dir in (LEANS_SYNTHETIC, LEANS_AUTHENTIC):
            local_vs_truth = ("the independent evidence leans the same way as the known ground truth"
                              if local_dir == ground_truth_direction else
                              "the independent evidence leans against the known ground truth")
        else:
            local_vs_truth = "the independent evidence is descriptive and does not lean either way"

    conf = f" (confidence {external.confidence:.0%})" if external.confidence is not None else ""
    if outcome == DISAGREEMENT:
        statement = (f"DETECTOR DISAGREEMENT. {external.detector} reports '{external.final_result}'{conf}; the "
                     "independent SynthProvenance evidence is inconsistent with that label on "
                     f"{len(disagrees)} dimension(s). Neither system is declared correct"
                     + ("." if gt_level < GROUND_TRUTH_DECISIVE else f"; against the known ground truth, {ext_vs_truth}."))
    elif outcome == INSUFFICIENT:
        statement = (f"INDEPENDENT EVIDENCE INCOMPLETE. {external.detector} reports '{external.final_result}'{conf}; "
                     "SynthProvenance's local evidence is descriptive and does not by itself confirm or refute that "
                     "label. No conclusion about either system is drawn.")
    elif outcome == AGREEMENT:
        statement = (f"CONSISTENT. {external.detector} reports '{external.final_result}'{conf}; the independent "
                     "evidence leans the same direction. This is consistency under the tested condition, not proof.")
    else:
        statement = (f"PARTIAL. {external.detector} reports '{external.final_result}'{conf}; the independent evidence "
                     "is mixed (some dimensions consistent, some not). No system is declared correct.")

    return CrossDetectorComparison(
        detector=external.detector, external=external.to_dict(), outcome=outcome, ground_truth_level=gt_level,
        ground_truth_label=GROUND_TRUTH_LEVELS.get(gt_level, "Unknown origin"), local_direction=local_dir,
        external_direction=ext_dir, agreements=agrees, disagreements=disagrees, unknowns=unknowns,
        external_vs_truth=ext_vs_truth, local_vs_truth=local_vs_truth, statement=statement, dimension_rows=rows)


# ------------------------------------------------------------------ scorecard (Section 24) — independent dimensions, no single score
SCORECARD_DIMENSIONS = ("Provenance Evidence", "Metadata Evidence", "Spectral Evidence", "Residual Evidence",
                        "Reconstruction Evidence", "Representation Evidence", "Cross-Image Evidence",
                        "External Detector Evidence", "Ground Truth Quality")


def scorecard(local: LocalEvidence, external: ExternalResult, ground_truth_level: int = 0) -> dict:
    """Independent evidence dimensions. Deliberately NOT combined into a single 'truth score'."""
    gt_level = int(ground_truth_level or local.ground_truth_level or 0)

    def dim(name, fam=None):
        d = next((x for x in local.dimensions if (fam and x.family == fam) or x.name.lower().startswith(name.lower())), None)
        if d is None:
            return {"direction": NOT_EVALUATED, "strength": "none", "observation": "not evaluated"}
        return {"direction": d.direction, "strength": d.strength, "observation": d.observation}

    rows = {
        "Provenance Evidence": dim("Provenance", FAMILY_PROVENANCE),
        "Metadata Evidence": dim("Provenance"),
        "Spectral Evidence": dim("Spectral", FAMILY_SPECTRAL),
        "Residual Evidence": dim("Residual", FAMILY_INTRINSIC),
        "Reconstruction Evidence": dim("Reconstruction", FAMILY_RECONSTRUCTION),
        "Representation Evidence": dim("Learned", FAMILY_DETECTOR_REP),
        "Cross-Image Evidence": {"direction": NOT_EVALUATED, "strength": "none",
                                 "observation": "needs reference images from a suspected common source (not supplied)"},
        "External Detector Evidence": {"direction": external.direction, "strength":
                                       "reported" if external.direction != UNKNOWN else "unclear",
                                       "observation": f"{external.detector}: '{external.final_result}'"
                                       + (f" (confidence {external.confidence:.0%})" if external.confidence is not None else "")},
        "Ground Truth Quality": {"direction": DESCRIPTIVE, "strength": f"LEVEL {gt_level}",
                                 "observation": GROUND_TRUTH_LEVELS.get(gt_level, "Unknown origin")},
    }
    return {"dimensions": rows, "combined_score": None,
            "note": "Independent evidence dimensions are shown separately on purpose. They are NOT combined into a "
                    "single truth score; a cross-detector study weighs them against the ground-truth level."}


# ------------------------------------------------------------------ the ten research questions (Section 3)
RESEARCH_QUESTIONS = (
    "Where do the external detector and SynthProvenance agree?",
    "Where do they disagree?",
    "Which observable evidence categories correlate with each decision?",
    "Are metadata, OCR/watermark, spectral, reconstruction and learned cues mutually consistent?",
    "How stable are classifications under normal transformations?",
    "Which signals are persistent?",
    "Which signals are representation-specific?",
    "Which claims survive independent replication?",
    "Which apparent 'fingerprints' are actually content artefacts?",
    "Can a controlled surrogate system reproduce the same behaviour?",
)
