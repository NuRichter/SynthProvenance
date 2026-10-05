"""Fingerprint research method registry: Method 00 - Method 54.

Each method is a :class:`Method` record with the plugin fields from the research brief
plus the method-card fields. ``maturity`` is one of FOUNDATIONAL, ESTABLISHED, ADAPTED,
EXPERIMENTAL, HYPOTHETICAL. ``availability`` is READY (runs locally now), UNAVAILABLE
(needs a deep-learning runtime / trained weights not bundled), or NOT_IMPLEMENTED
(deliberately out of scope). ``capability`` names the runner entry point.

Honesty rules (validated by the test-suite via ``validate``):
* a method that needs learned weights is UNAVAILABLE with a reason, never faked;
* detector-evasion optimisation (Methods 43-46) is NOT_IMPLEMENTED by design, matching
  the project's ethics; the reason is shown in the card;
* numpy re-implementations of published ideas are labelled ADAPTED, never presented as
  the original authors' validated detector.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from app.research import hypotheses as HY
from app.research import separation as SEP
from app.research import surrogate as SUR

MATURITIES = ("FOUNDATIONAL", "ESTABLISHED", "ADAPTED", "EXPERIMENTAL", "HYPOTHETICAL")
AVAILABILITY = ("READY", "UNAVAILABLE", "NOT_IMPLEMENTED")
CAPABILITY_FLAGS = ("CAN_ANALYZE", "CAN_ESTIMATE", "CAN_SEPARATE", "CAN_RECONSTRUCT", "CAN_VALIDATE")

# capability dispatch key -> set of CAN_* flags the method actually provides. Single source of truth so the UI can
# never advertise a detector as a separator.
_CAP_FLAGS: dict[str, tuple] = {
    "baseline": ("CAN_ANALYZE",), "metadata": ("CAN_ANALYZE",), "c2pa": ("CAN_ANALYZE",),
    "residual": ("CAN_ANALYZE", "CAN_ESTIMATE"), "residual_vector": ("CAN_ANALYZE",),
    "cross_image": ("CAN_ANALYZE", "CAN_ESTIMATE", "CAN_VALIDATE"), "synthbuster": ("CAN_ANALYZE",),
    "fft": ("CAN_ANALYZE",), "dct": ("CAN_ANALYZE",), "wavelet": ("CAN_ANALYZE",), "benford": ("CAN_ANALYZE",),
    "lid": ("CAN_ANALYZE",), "patch_consensus": ("CAN_ANALYZE",), "multiscale_consensus": ("CAN_ANALYZE",),
    "cross_region_consensus": ("CAN_ANALYZE",), "attribution": ("CAN_ANALYZE",),
    "robustness": ("CAN_ANALYZE", "CAN_VALIDATE"),
    "persistence_map": ("CAN_ANALYZE", "CAN_ESTIMATE", "CAN_VALIDATE"),
    "ensemble": ("CAN_ANALYZE",), "meta": ("CAN_ANALYZE",),
    # separation studies estimate, separate, reconstruct and validate against ground truth
    "sep:highpass": ("CAN_ANALYZE", "CAN_ESTIMATE", "CAN_SEPARATE", "CAN_RECONSTRUCT", "CAN_VALIDATE"),
    "sep:wavelet": ("CAN_ANALYZE", "CAN_ESTIMATE", "CAN_SEPARATE", "CAN_RECONSTRUCT", "CAN_VALIDATE"),
    "sep:fft": ("CAN_ANALYZE", "CAN_ESTIMATE", "CAN_SEPARATE", "CAN_RECONSTRUCT", "CAN_VALIDATE"),
    "sep:dct": ("CAN_ANALYZE", "CAN_ESTIMATE", "CAN_SEPARATE", "CAN_RECONSTRUCT", "CAN_VALIDATE"),
    "sep:robust_pca": ("CAN_ANALYZE", "CAN_ESTIMATE", "CAN_SEPARATE", "CAN_RECONSTRUCT", "CAN_VALIDATE"),
    "sep:self_prior": ("CAN_ANALYZE", "CAN_ESTIMATE", "CAN_SEPARATE", "CAN_RECONSTRUCT", "CAN_VALIDATE"),
    # hypotheses analyse and validate (some reconstruct)
    "hyp:provenance_orthogonal_subspace": ("CAN_ANALYZE", "CAN_VALIDATE"),
    "hyp:information_bottleneck_decoupling": ("CAN_ANALYZE", "CAN_ESTIMATE", "CAN_VALIDATE"),
    "hyp:frequency_semantic_cross_domain": ("CAN_ANALYZE", "CAN_ESTIMATE", "CAN_VALIDATE"),
    "hyp:topological_residual": ("CAN_ANALYZE", "CAN_VALIDATE"),
    "hyp:cross_representation_consensus": ("CAN_ANALYZE", "CAN_VALIDATE"),
    "hyp:automated_hypothesis_discovery": ("CAN_ANALYZE", "CAN_ESTIMATE", "CAN_VALIDATE"),
    # frontier methods (added in v4)
    "frontier:multi_representation_residual_consensus": ("CAN_ANALYZE", "CAN_ESTIMATE", "CAN_VALIDATE"),
    "frontier:fingerprint_null_space": ("CAN_ANALYZE", "CAN_VALIDATE"),
    "frontier:cross_scale_topological_residual": ("CAN_ANALYZE", "CAN_VALIDATE"),
    "frontier:spectral_semantic_fusion": ("CAN_ANALYZE", "CAN_ESTIMATE", "CAN_VALIDATE"),
    "frontier:iterative_reconstruction_consensus": ("CAN_ANALYZE", "CAN_ESTIMATE", "CAN_RECONSTRUCT", "CAN_VALIDATE"),
    "frontier:method_disagreement": ("CAN_ANALYZE", "CAN_VALIDATE"),
    "frontier:fingerprint_stability_field": ("CAN_ANALYZE", "CAN_ESTIMATE", "CAN_VALIDATE"),
    "frontier:provenance_energy_landscape": ("CAN_ANALYZE", "CAN_VALIDATE"),
    "reconstruction": ("CAN_ANALYZE", "CAN_ESTIMATE", "CAN_RECONSTRUCT", "CAN_VALIDATE"),
}
CATEGORIES = ("BASELINE", "METADATA / PROVENANCE", "INTRINSIC FINGERPRINT RESEARCH", "DIFFUSION FORENSICS", "SPECTRAL",
              "GEOMETRIC / STATISTICAL", "SPATIAL / MULTI-SCALE", "REPRESENTATION", "CAUSAL",
              "CONTROLLED SURROGATE STUDY", "ADVANCED HYPOTHESIS", "ENSEMBLE", "RECONSTRUCTION FORENSICS",
              "FRONTIER")
IMAGE_FORMATS = ("PNG", "JPEG", "WEBP", "TIFF", "BMP", "GIF")

DL_REASON = ("Requires a deep-learning runtime (PyTorch/ONNX) and trained weights that are not bundled. "
             "SynthProvenance ships numpy/Pillow only and never downloads models during analysis. "
             "Status would change only if a validated local model were added through the model manager.")
TRAIN_REASON = ("Requires a trained classifier/model fitted on labelled data. The handcrafted descriptor is available "
                "(see the matching feature method); the trained detector is not bundled.")
EVASION_REASON = ("Not implemented by design. SynthProvenance does not search for transformations that reduce a "
                  "watermark detector's score. The controlled Robustness and Separation studies measure a known "
                  "surrogate signal's persistence and recoverability against ground truth instead "
                  "(docs/RESEARCH_METHOD.md).")


@dataclass(frozen=True)
class Method:
    method_id: str              # "Method 00"
    code: str                   # "FP-00"
    name: str
    category: str
    maturity: str
    availability: str
    capability: str             # runner dispatch key ("" if not runnable)
    scientific_basis: str
    how_it_works: str
    source_reference: str       # taxonomy ref ids / literature slugs
    source_repository: str
    license: str
    local_or_online: str
    requires_gpu: bool
    requires_model: bool
    requires_reference_images: bool
    requires_ground_truth: bool
    supported_formats: tuple = IMAGE_FORMATS
    supported_resolution: str = "any (tiled)"
    compute_cost: str = "low"
    input_requirements: str = "a single decoded image"
    known_limitations: str = ""
    validation_status: str = "VALIDATED BY TEST SUITE"
    reason: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["supported_formats"] = list(self.supported_formats)
        d["implemented"] = self.availability == "READY"
        d["capabilities"] = self.capability_flags()
        return d

    @property
    def runnable(self) -> bool:
        return self.availability == "READY" and bool(self.capability)

    def capability_flags(self) -> dict[str, bool]:
        """Explicit CAN_ANALYZE / CAN_ESTIMATE / CAN_SEPARATE / CAN_RECONSTRUCT / CAN_VALIDATE flags.

        A non-READY method advertises no capabilities: the UI must never present it as able to do anything.
        """
        active = set(_CAP_FLAGS.get(self.capability, ())) if self.runnable else set()
        return {flag: (flag in active) for flag in CAPABILITY_FLAGS}

    def can(self, flag: str) -> bool:
        return self.capability_flags().get(flag, False)

    @property
    def subfamily(self) -> str:
        return self.capability.split(":", 1)[1] if ":" in self.capability else self.capability

    def metadata(self) -> dict:
        """The metadata-rich Registry-V2 record for a method."""
        flags = self.capability_flags()
        return {"method_id": self.method_id, "code": self.code, "name": self.name, "family": self.category,
                "subfamily": self.subfamily, "maturity": self.maturity, "availability": self.availability,
                "paper_ids": self.source_reference, "source_url": self.source_repository, "license": self.license,
                "local_or_online": self.local_or_online, "representation": self.subfamily,
                "requires_reference_images": self.requires_reference_images,
                "requires_ground_truth": self.requires_ground_truth, "requires_model": self.requires_model,
                "training_required": self.requires_model, "training_free": not self.requires_model,
                "cpu_supported": not self.requires_gpu, "cuda_supported": self.requires_gpu,
                "max_practical_resolution": self.supported_resolution, "compute_cost": self.compute_cost,
                "analysis_only": flags["CAN_ANALYZE"] and not (flags["CAN_SEPARATE"] or flags["CAN_RECONSTRUCT"]),
                "separation_supported": flags["CAN_SEPARATE"], "reconstruction_supported": flags["CAN_RECONSTRUCT"],
                "validation_status": self.validation_status, "limitations": self.known_limitations,
                "capabilities": flags, "reason": self.reason}

    def card(self) -> list[tuple[str, str]]:
        return [("Method", f"{self.method_id} - {self.name}"), ("Category", self.category),
                ("Research maturity", self.maturity), ("Availability", self.availability),
                ("Scientific purpose", self.scientific_basis), ("How it works", self.how_it_works),
                ("Input requirements", self.input_requirements),
                ("Ground truth requirement", "required (controlled surrogate / labels)" if self.requires_ground_truth
                 else "not required"),
                ("Compute requirement", f"{self.compute_cost}; GPU {'required' if self.requires_gpu else 'not used'}; "
                 f"model {'required' if self.requires_model else 'none'}"),
                ("Reference images", "required" if self.requires_reference_images else "not required"),
                ("Known limitations", self.known_limitations or "see the method notes"),
                ("Literature sources", self.source_reference),
                ("Implementation source", f"{self.source_repository} / {self.license}"),
                ("Local / online", self.local_or_online), ("Supported formats", ", ".join(self.supported_formats)),
                ("Supported resolution", self.supported_resolution), ("Validation status", self.validation_status),
                ("Reason (if unavailable)", self.reason or "-")]


def _m(num, name, category, maturity, availability, capability, basis, how, refs, **kw) -> Method:
    code = f"FP-{num:02d}"
    defaults = dict(source_repository="SynthProvenance (native, numpy)", license="see LICENSE", local_or_online="LOCAL",
                    requires_gpu=False, requires_model=False, requires_reference_images=False, requires_ground_truth=False)
    defaults.update(kw)
    return Method(f"Method {num:02d}", code, name, category, maturity, availability, capability, basis, how, refs,
                  **defaults)


_ADAPTED_LIC = "idea from the cited paper; numpy re-implementation under this project's LICENSE"

METHODS: tuple[Method, ...] = (
    # ---- BASELINE
    _m(0, "Original / Control", "BASELINE", "FOUNDATIONAL", "READY", "baseline",
       "Characterise the unmodified image: resolution, hashes, and the forensic baseline used as the control for every "
       "other method.", "Decode frame 0 canonically, hash pixels and bytes, record format and basic statistics.",
       "native", known_limitations="Descriptive only; not a detector.", compute_cost="negligible"),
    # ---- METADATA / PROVENANCE
    _m(1, "Metadata Isolation", "METADATA / PROVENANCE", "ESTABLISHED", "READY", "metadata",
       "List the ordinary metadata layers (EXIF/XMP/IPTC/ICC) that may carry origin hints, kept separate from pixels.",
       "Reuse the native metadata engine; report presence and AI-content declarations per block.", "native",
       known_limitations="Metadata is trivially edited or stripped; absence proves nothing."),
    _m(2, "C2PA Manifest Analysis", "METADATA / PROVENANCE", "ESTABLISHED", "READY", "c2pa",
       "Parse the C2PA/Content Credentials manifest and recompute the hard binding (the provenance layer).",
       "Reuse the native JUMBF/CBOR parser; recompute the hard-binding digest; signatures validated only if c2patool / "
       "c2pa-python is present.", "C2PA 2.4 spec [EXT]; taxonomy 4K", known_limitations="C2PA is signed metadata, NOT an "
       "intrinsic fingerprint; validity UNKNOWN without a validator.", source_repository="native + optional c2patool",
       license="tool: MIT OR Apache-2.0"),
    # ---- INTRINSIC FINGERPRINT RESEARCH
    _m(3, "Residual Fingerprint", "INTRINSIC FINGERPRINT RESEARCH", "FOUNDATIONAL", "READY", "residual",
       "Extract high-frequency residual operators where generator traces are reported to live.",
       "Compute Gaussian/Laplacian/high-pass/wavelet/DCT/median residuals and their statistics (energy, kurtosis, "
       "entropy, autocorrelation, spectrum).", "Marra 2019 [EXT]; taxonomy 1B/3F", license=_ADAPTED_LIC,
       known_limitations="Residual statistics are content-dependent; descriptive, not attribution."),
    _m(4, "PRNU-Inspired Model Fingerprint", "INTRINSIC FINGERPRINT RESEARCH", "FOUNDATIONAL", "READY", "cross_image",
       "Estimate a source template by averaging denoising residuals over many images (PRNU analogy).",
       "R_i = X_i - Denoise(X_i); average over a build split; correlate held-out residuals with the template against a "
       "noise-template control.", "Marra 2019 [EXT]; Lukas 2006 [EXT]; taxonomy 1B", license=_ADAPTED_LIC,
       requires_reference_images=True, input_requirements="4+ images from a suspected common source",
       known_limitations="Shared scene/processing also correlates; a GAN residual is not camera PRNU.",
       compute_cost="medium"),
    _m(5, "GAN Fingerprint (handcrafted)", "INTRINSIC FINGERPRINT RESEARCH", "ADAPTED", "READY", "residual_vector",
       "Handcrafted descriptor in the spirit of learned GAN fingerprints, for attribution studies.",
       "Concatenate residual/spectral/wavelet statistics into a descriptor; compare to researcher-built prototypes.",
       "Yu 2019 [TAX-REF-03]; Marra 2019 [EXT]", license=_ADAPTED_LIC,
       known_limitations="The published method learns the fingerprint; this is a learning-free proxy."),
    _m(6, "Architecture-Level Fingerprint", "INTRINSIC FINGERPRINT RESEARCH", "EXPERIMENTAL", "UNAVAILABLE", "",
       "Attribute an image to a generator architecture (DNA-Det).", "Needs a trained attribution network.",
       "Yang 2022 DNA-Det [TAX-REF-05]", requires_model=True, requires_gpu=True,
       reason=TRAIN_REASON, validation_status="NOT IMPLEMENTED", license="paper: non-commercial"),
    _m(7, "Instance-Level Fingerprint", "INTRINSIC FINGERPRINT RESEARCH", "EXPERIMENTAL", "UNAVAILABLE", "",
       "Distinguish checkpoints/instances of one architecture.", "Needs trained instance-level features.",
       "Liu 2024 [TAX-REF-07]", requires_model=True, requires_gpu=True, reason=TRAIN_REASON,
       validation_status="NOT IMPLEMENTED", license="paper"),
    _m(8, "Fingerprint Disentanglement", "INTRINSIC FINGERPRINT RESEARCH", "EXPERIMENTAL", "UNAVAILABLE", "",
       "Separate content-irrelevant fingerprint from semantics (GFD-Net).", "Needs a trained disentangling network.",
       "Yang 2021 GFD-Net [TAX-REF-06]", requires_model=True, requires_gpu=True, reason=TRAIN_REASON,
       validation_status="NOT IMPLEMENTED", license="paper"),
    # ---- DIFFUSION FORENSICS
    _m(9, "DIRE", "DIFFUSION FORENSICS", "ESTABLISHED", "UNAVAILABLE", "",
       "Diffusion reconstruction error between an image and its diffusion reconstruction.",
       "Needs a pretrained diffusion model to reconstruct the image.", "Wang 2023 DIRE [TAX-REF-08]", requires_model=True,
       requires_gpu=True, reason=DL_REASON, validation_status="NOT IMPLEMENTED", license="repo: no license file"),
    _m(10, "AEROBLADE Reconstruction Error", "DIFFUSION FORENSICS", "ESTABLISHED", "UNAVAILABLE", "",
       "Autoencoder reconstruction error of latent-diffusion images (training-free, but needs the LDM autoencoder).",
       "Needs a pretrained LDM autoencoder.", "Ricker 2024 AEROBLADE [TAX-REF-09]", requires_model=True, requires_gpu=True,
       reason=DL_REASON, validation_status="NOT IMPLEMENTED", license="repo: no license file"),
    _m(11, "Synthbuster-style Spectral", "DIFFUSION FORENSICS", "ADAPTED", "READY", "synthbuster",
       "Residual-spectrum peaks on the (k/8, l/8) frequency lattice reported for diffusion images.",
       "Cross-difference high-pass, averaged windowed periodogram, measure the mean lattice-peak-to-median ratio.",
       "Bammey 2023 Synthbuster [EXT]; taxonomy 6C", license=_ADAPTED_LIC,
       known_limitations="The published detector trains a classifier on these features; here only the descriptive "
       "features and a lattice-peak ratio are produced."),
    _m(12, "Diffusion Residual Analysis", "DIFFUSION FORENSICS", "EXPERIMENTAL", "READY", "residual",
       "Descriptive residual/spectral analysis of denoising/sampling traces (no reconstruction model).",
       "Run the residual engine and report spectral tail and periodic-peak statistics.", "taxonomy 1G/6",
       license=_ADAPTED_LIC, known_limitations="Without a diffusion model this cannot compute a reconstruction error; "
       "it is a descriptive proxy."),
    # ---- SPECTRAL
    _m(13, "FFT Analysis", "SPECTRAL", "FOUNDATIONAL", "READY", "fft",
       "Fourier magnitude/phase, radial & angular spectra, band energy, spectral tail and periodic peaks.",
       "Welch-averaged windowed periodogram; radial log-power fit; robust peak detection.",
       "Durall 2020 [TAX-REF-02]; Frank 2020 [TAX-REF-01]; taxonomy 3A", license=_ADAPTED_LIC,
       known_limitations="Spectral cues vary by generator and post-processing; descriptive."),
    _m(14, "DCT Analysis", "SPECTRAL", "FOUNDATIONAL", "READY", "dct",
       "Block-DCT coefficient statistics and (for JPEG) quantisation-table / quality analysis.",
       "8x8 orthonormal DCT of decoded pixels; coefficient histograms; JPEG table match.",
       "Frank 2020 [TAX-REF-01]; taxonomy 3D", license=_ADAPTED_LIC, known_limitations="Coefficients are analytical "
       "(recomputed from pixels), not read from the JPEG bitstream."),
    _m(15, "DWT / Wavelet Analysis", "SPECTRAL", "FOUNDATIONAL", "READY", "wavelet",
       "Multi-level LL/LH/HL/HH sub-band energy, variance, kurtosis, sparsity and cross-scale persistence.",
       "Orthogonal Haar/db2 DWT with perfect reconstruction; per-band statistics.", "taxonomy 3E", license=_ADAPTED_LIC,
       known_limitations="Sub-band conventions vary; descriptive statistics only."),
    _m(16, "Spectral Tail Analysis", "SPECTRAL", "ESTABLISHED", "READY", "fft",
       "Fit the radial log-power spectrum and measure excess high-frequency (tail) energy.",
       "Power-law fit on mid frequencies; deviation of the 0.75-1.0 tail from the extrapolation (dB).",
       "Durall 2020 [TAX-REF-02]; Dzanic 2020 [EXT]; taxonomy 3C", license=_ADAPTED_LIC,
       known_limitations="Resampling and sharpening also change the tail."),
    _m(17, "High-Frequency Residual", "SPECTRAL", "FOUNDATIONAL", "READY", "residual",
       "Isolate and characterise the high-frequency residual band.", "SRM/high-pass residual and its spectrum.",
       "taxonomy 3F", license=_ADAPTED_LIC, known_limitations="Content edges dominate; descriptive."),
    _m(18, "Benford-DCT Statistics", "SPECTRAL", "ESTABLISHED", "READY", "benford",
       "First-digit distribution of quantised DCT AC coefficients vs Benford's law.",
       "First-digit histogram, chi-square / JS divergence, generalised-Benford fit and a re-quantisation feature vector.",
       "Bonettini 2021 [EXT]; taxonomy 3G", license=_ADAPTED_LIC,
       known_limitations="A statistical cue, not a watermark; JPEG history affects it."),
    # ---- GEOMETRIC / STATISTICAL
    _m(19, "LID", "GEOMETRIC / STATISTICAL", "ADAPTED", "READY", "lid",
       "Local Intrinsic Dimensionality of patch descriptors (manifold geometry).",
       "Houle MLE estimator over k nearest neighbours of high-pass patch descriptors.",
       "Lorenz 2023 [TAX-REF-10] (arXiv withdrawn by authors); taxonomy 5D", license=_ADAPTED_LIC,
       known_limitations="Paper uses deep features; this uses handcrafted patches. The source arXiv was withdrawn for a "
       "reported bug - treat as exploratory.", compute_cost="medium"),
    _m(20, "MultiLID", "GEOMETRIC / STATISTICAL", "ADAPTED", "READY", "lid",
       "Multi-neighbour LID profile (keeps per-neighbour growth, not one scalar).",
       "Per-neighbour log-distance ratios averaged over patches.", "Lorenz 2023 [TAX-REF-10]; taxonomy 5D",
       license=_ADAPTED_LIC, known_limitations="Same caveats as LID.", compute_cost="medium"),
    _m(21, "Entropy / Noise Statistics", "GEOMETRIC / STATISTICAL", "ESTABLISHED", "READY", "residual",
       "Entropy and noise-floor statistics of the image and its residuals.", "Histogram entropy, residual sigma, "
       "block noise.", "taxonomy 3; image-statistics engine", license=_ADAPTED_LIC,
       known_limitations="Descriptive; strongly content-dependent."),
    # ---- SPATIAL / MULTI-SCALE
    _m(22, "Patch Fingerprint Analysis", "SPATIAL / MULTI-SCALE", "EXPERIMENTAL", "READY", "patch_consensus",
       "Stability of the candidate residual's statistics across image patches.",
       "Tile the residual; report the coefficient of variation of patch energy (consistency).", "taxonomy 1/3",
       license=_ADAPTED_LIC, known_limitations="Localised texture lowers consistency; needs controls."),
    _m(23, "Multi-Scale Consensus", "SPATIAL / MULTI-SCALE", "EXPERIMENTAL", "READY", "multiscale_consensus",
       "Agreement of candidate residual maps across full, 1/2, 1/4, 1/8 scale.",
       "Compute the residual at each scale, resample to a common grid, average pairwise correlation.", "taxonomy 1F/3H",
       license=_ADAPTED_LIC, known_limitations="Edges correlate across scales too.", compute_cost="medium"),
    _m(24, "Cross-Region Consensus", "SPATIAL / MULTI-SCALE", "EXPERIMENTAL", "READY", "cross_region_consensus",
       "Agreement of residual spectra between disjoint image quadrants.",
       "Welch spectra of four quadrants; average pairwise correlation.", "taxonomy 1/3", license=_ADAPTED_LIC,
       known_limitations="Global texture raises agreement; descriptive."),
    _m(25, "Cross-Image Fingerprint Consensus", "SPATIAL / MULTI-SCALE", "ESTABLISHED", "READY", "cross_image",
       "Shared residual template across images from a suspected common source, with a held-out split.",
       "Build a residual template on half the images; evaluate held-out correlation against a noise-template control.",
       "Marra 2019 [EXT]; taxonomy 1B", license=_ADAPTED_LIC, requires_reference_images=True,
       input_requirements="4+ images from a suspected common source", compute_cost="medium",
       known_limitations="Shared scene/processing can mimic a shared fingerprint."),
    # ---- REPRESENTATION
    _m(26, "CLIP", "REPRESENTATION", "ESTABLISHED", "UNAVAILABLE", "",
       "CLIP feature-space detection (UniversalFakeDetect).", "Needs CLIP ViT weights and a probe.",
       "Ojha 2023 UnivFD [TAX-REF-17]", requires_model=True, requires_gpu=True, reason=DL_REASON,
       validation_status="NOT IMPLEMENTED", license="CLIP: MIT; method non-commercial"),
    _m(27, "ViT", "REPRESENTATION", "ESTABLISHED", "UNAVAILABLE", "", "Vision-Transformer forensic features.",
       "Needs ViT weights.", "Dosovitskiy 2021 [EXT]", requires_model=True, requires_gpu=True, reason=DL_REASON,
       validation_status="NOT IMPLEMENTED", license="model-specific"),
    _m(28, "DINO", "REPRESENTATION", "ESTABLISHED", "UNAVAILABLE", "", "Self-supervised DINO features.",
       "Needs DINO/DINOv2 weights.", "Caron 2021 [EXT]", requires_model=True, requires_gpu=True, reason=DL_REASON,
       validation_status="NOT IMPLEMENTED", license="model-specific"),
    _m(29, "Contrastive Representation", "REPRESENTATION", "EXPERIMENTAL", "UNAVAILABLE", "",
       "Contrastive/metric-learning forensic embedding (LASTED/DeeCLIP).", "Needs trained contrastive weights.",
       "Wu 2025 LASTED [TAX-REF-19]", requires_model=True, requires_gpu=True, reason=DL_REASON,
       validation_status="NOT IMPLEMENTED", license="paper"),
    _m(30, "Feature-Space Attribution", "REPRESENTATION", "ADAPTED", "READY", "attribution",
       "Nearest-prototype attribution in handcrafted descriptor space (no training).",
       "Standardise descriptors; compare an image to researcher-built per-group prototypes (cosine / Euclidean).",
       "taxonomy 5G", license=_ADAPTED_LIC, requires_reference_images=True,
       input_requirements="prototypes built from labelled images, then a query image",
       known_limitations="Descriptive similarity in a handcrafted space, not a learned detector."),
    # ---- CAUSAL
    _m(31, "Causal Fingerprint", "CAUSAL", "EXPERIMENTAL", "UNAVAILABLE", "",
       "Causally-decoupled fingerprint in a semantic-invariant latent space.",
       "Needs trained multi-space causal representation.", "Xu 2025 [TAX-REF-12]", requires_model=True, requires_gpu=True,
       reason=DL_REASON, validation_status="NOT IMPLEMENTED", license="paper"),
    _m(32, "Semantic-Invariant Representation", "CAUSAL", "EXPERIMENTAL", "UNAVAILABLE", "",
       "Representation preserving content while isolating source identity.", "Needs trained SILS encoder.",
       "Xu 2025 [TAX-REF-12]", requires_model=True, requires_gpu=True, reason=DL_REASON,
       validation_status="NOT IMPLEMENTED", license="paper"),
    _m(33, "Counterfactual Fingerprint Analysis", "CAUSAL", "HYPOTHETICAL", "UNAVAILABLE", "",
       "Intervene on fingerprint while preserving content, to test causal attribution.",
       "Needs a generative model to produce counterfactuals.", "Xu 2025 [TAX-REF-12]", requires_model=True,
       requires_gpu=True, reason=DL_REASON, validation_status="NOT IMPLEMENTED", license="paper"),
    # ---- CONTROLLED SURROGATE STUDY (ground truth; no detector-evasion search)
    _m(34, "Surrogate High-Pass Separation", "CONTROLLED SURROGATE STUDY", "EXPERIMENTAL", "READY", "sep:highpass",
       "On a controlled surrogate, separate the known signal with a high-pass split and score recovery/fidelity.",
       "content = Gaussian low-pass, candidate = high-pass residual; measure recovery correlation and reconstruction "
       "PSNR/SSIM against ground truth.", "taxonomy 3F", license=_ADAPTED_LIC, requires_ground_truth=True,
       input_requirements="a controlled surrogate case (clean + embedded)",
       known_limitations="Characterisation only; not a removal tool and not run on real watermarks."),
    _m(35, "Surrogate Wavelet Separation", "CONTROLLED SURROGATE STUDY", "EXPERIMENTAL", "READY", "sep:wavelet",
       "Wavelet BayesShrink separation of the known surrogate signal, scored against ground truth.",
       "content = BayesShrink estimate; candidate = removed detail; measure recovery and fidelity.", "taxonomy 3E",
       license=_ADAPTED_LIC, requires_ground_truth=True, input_requirements="a controlled surrogate case",
       known_limitations="Ground-truth study only."),
    _m(36, "Surrogate FFT Separation", "CONTROLLED SURROGATE STUDY", "EXPERIMENTAL", "READY", "sep:fft",
       "Attenuate blindly-detected anomalous spectral bins and measure recovery/fidelity on the surrogate.",
       "Per-radius robust z-score selects anomalous bins; attenuate; score against ground truth.", "taxonomy 3A",
       license=_ADAPTED_LIC, requires_ground_truth=True, input_requirements="a controlled surrogate case",
       known_limitations="Crude; can damage content (reported as a failure mode)."),
    _m(37, "Surrogate Robust-PCA Separation", "CONTROLLED SURROGATE STUDY", "EXPERIMENTAL", "READY", "sep:robust_pca",
       "Decompose the surrogate image as I = L + S + E and treat S as the candidate signal.",
       "Principal Component Pursuit (inexact ALM); score S against the known signal.", "Candes 2011 RPCA [EXT]; taxonomy "
       "formulation", license=_ADAPTED_LIC, requires_ground_truth=True, input_requirements="a controlled surrogate case",
       compute_cost="high", known_limitations="Convergence and lambda sensitive; ground-truth study only."),
    _m(38, "Surrogate Constrained Separation", "CONTROLLED SURROGATE STUDY", "EXPERIMENTAL", "READY", "sep:self_prior",
       "Self-supervised guided-filter image prior as the content estimate; candidate = residual.",
       "Repeated self-guided edge-aware smoothing; score against ground truth.", "He 2013 guided filter [EXT]",
       license=_ADAPTED_LIC, requires_ground_truth=True, input_requirements="a controlled surrogate case",
       known_limitations="Ground-truth study only."),
    _m(39, "Surrogate Robustness Sweep", "CONTROLLED SURROGATE STUDY", "ESTABLISHED", "READY", "robustness",
       "Measure how the known surrogate signal persists under a fixed battery of standard transformations.",
       "Apply JPEG/WebP/resize/crop/rotate/blur/noise/... at graded severities; report persistence and fidelity "
       "(WAVES-style characterisation).", "An 2024 WAVES [EXT]; taxonomy robustness list", license=_ADAPTED_LIC,
       requires_ground_truth=True, input_requirements="a controlled surrogate case", compute_cost="medium",
       known_limitations="Fixed transformations only; this is robustness measurement, not a detector-evasion search."),
    _m(40, "Surrogate Signal Persistence Map", "CONTROLLED SURROGATE STUDY", "EXPERIMENTAL", "READY", "persistence_map",
       "Localise where the known signal survives after a standard transformation.",
       "Project the post-transformation residual onto the known signal per tile; map the retained fraction.",
       "taxonomy robustness", license=_ADAPTED_LIC, requires_ground_truth=True,
       input_requirements="a controlled surrogate case", known_limitations="Needs pixel-aligned geometry."),
    _m(41, "Surrogate Reconstruction Fidelity", "CONTROLLED SURROGATE STUDY", "EXPERIMENTAL", "READY", "sep:wavelet",
       "Measure content fidelity of a separation (reconstruction panels + MAE/MSE/PSNR/SSIM).",
       "Reuse wavelet separation and report the full fidelity block and reconstruction panels.", "taxonomy",
       license=_ADAPTED_LIC, requires_ground_truth=True, input_requirements="a controlled surrogate case",
       known_limitations="LPIPS not computed (no learned model)."),
    _m(42, "Surrogate Counterfactual Separation", "CONTROLLED SURROGATE STUDY", "HYPOTHETICAL", "READY", "sep:self_prior",
       "Produce a content-preserving counterfactual (signal-free estimate) and compare candidate maps.",
       "Use the image-prior estimate as a learning-free counterfactual; compare its residual to ground truth.",
       "taxonomy 2C (adapted, learning-free)", license=_ADAPTED_LIC, requires_ground_truth=True,
       input_requirements="a controlled surrogate case", known_limitations="Not a diffusion counterfactual; a proxy."),
    _m(43, "Surrogate Adversarial Optimisation", "CONTROLLED SURROGATE STUDY", "HYPOTHETICAL", "NOT_IMPLEMENTED", "",
       "Optimise a perturbation to reduce the surrogate detector score.", "Deliberately not implemented.",
       "taxonomy 2D", reason=EVASION_REASON, validation_status="NOT IMPLEMENTED",
       known_limitations=EVASION_REASON),
    _m(44, "Surrogate Black-Box Detector Attack", "CONTROLLED SURROGATE STUDY", "HYPOTHETICAL", "NOT_IMPLEMENTED", "",
       "Query-based search to evade the surrogate detector.", "Deliberately not implemented.", "taxonomy 2D",
       reason=EVASION_REASON, validation_status="NOT IMPLEMENTED", known_limitations=EVASION_REASON),
    _m(45, "Surrogate Evolutionary Search", "CONTROLLED SURROGATE STUDY", "HYPOTHETICAL", "NOT_IMPLEMENTED", "",
       "Evolutionary search for a detector-evading transformation.", "Deliberately not implemented.", "taxonomy 2D",
       reason=EVASION_REASON, validation_status="NOT IMPLEMENTED", known_limitations=EVASION_REASON),
    _m(46, "Surrogate Differentiable Attack", "CONTROLLED SURROGATE STUDY", "HYPOTHETICAL", "NOT_IMPLEMENTED", "",
       "Gradient-based perturbation to minimise the detector score.", "Deliberately not implemented.", "taxonomy 2D",
       reason=EVASION_REASON, validation_status="NOT IMPLEMENTED", known_limitations=EVASION_REASON),
    # ---- ADVANCED HYPOTHESIS
    _m(47, "Provenance-Orthogonal Subspace", "ADVANCED HYPOTHESIS", "HYPOTHETICAL", "READY", "hyp:provenance_orthogonal_subspace",
       "Test whether a separable direction distinguishes signed vs unsigned controlled images.",
       "PCA of patch descriptors on signed/unsigned sets; separation along the top direction.", "taxonomy 2/2A",
       license=_ADAPTED_LIC, requires_ground_truth=True, input_requirements="signed and unsigned controlled image sets",
       known_limitations="Never proven from one case; content can confound.", validation_status="HYPOTHESIS TEST"),
    _m(48, "Information-Bottleneck Decoupling", "ADVANCED HYPOTHESIS", "HYPOTHETICAL", "READY", "hyp:information_bottleneck_decoupling",
       "Test whether a quantisation bottleneck keeps content while dropping signal information.",
       "Quantise luminance to k levels; measure content PSNR vs retained known-signal energy.", "taxonomy",
       license=_ADAPTED_LIC, requires_ground_truth=True, input_requirements="a controlled surrogate case",
       known_limitations="Crude bottleneck proxy.", validation_status="HYPOTHESIS TEST"),
    _m(49, "Frequency-Semantic Cross-Domain", "ADVANCED HYPOTHESIS", "HYPOTHETICAL", "READY", "hyp:frequency_semantic_cross_domain",
       "Test whether fusing FFT+DWT+residual descriptors recovers the known signal better than any one domain.",
       "Z-score and average candidate maps from several domains; compare recovery correlation.", "taxonomy 2B/3H",
       license=_ADAPTED_LIC, requires_ground_truth=True, input_requirements="a controlled surrogate case",
       known_limitations="Equal-weight fusion, no learned semantics.", validation_status="HYPOTHESIS TEST"),
    _m(50, "Topological Residual", "ADVANCED HYPOTHESIS", "HYPOTHETICAL", "READY", "hyp:topological_residual",
       "Test whether a structured signal leaves stable residual topology (0-dim persistence proxy).",
       "Component / Euler-characteristic curve of residual super-level sets vs a control.", "taxonomy",
       license=_ADAPTED_LIC, requires_ground_truth=True, input_requirements="watermarked image (+ clean control)",
       known_limitations="Texture also produces components.", validation_status="HYPOTHESIS TEST"),
    _m(51, "Cross-Representation Consensus", "ADVANCED HYPOTHESIS", "HYPOTHETICAL", "READY", "hyp:cross_representation_consensus",
       "Test whether independent representations agree on a candidate signal.",
       "Combine multi-scale and cross-region agreement into one score.", "taxonomy 2B", license=_ADAPTED_LIC,
       input_requirements="an image (controlled case for interpretation)",
       known_limitations="Content correlates across representations too.", validation_status="HYPOTHESIS TEST"),
    _m(52, "Automated Hypothesis Discovery", "ADVANCED HYPOTHESIS", "HYPOTHETICAL", "READY", "hyp:automated_hypothesis_discovery",
       "Search analysis configurations for the one that best RECOVERS a known signal (not evasion).",
       "Grid over residual op x scale x colour plane; rank by recovery correlation to ground truth.", "taxonomy",
       license=_ADAPTED_LIC, requires_ground_truth=True, input_requirements="a controlled surrogate case",
       compute_cost="medium", known_limitations="May overfit to one image; replicate.", validation_status="HYPOTHESIS TEST"),
    # ---- ENSEMBLE
    _m(53, "Ensemble Research", "ENSEMBLE", "EXPERIMENTAL", "READY", "ensemble",
       "Combine several READY descriptive methods into one report for cross-checking.",
       "Run FFT, DCT, wavelet, residual and Benford methods; collect their key statistics side by side.", "taxonomy",
       license=_ADAPTED_LIC, compute_cost="medium", known_limitations="Aggregation of descriptive cues, not a verdict."),
    _m(54, "Meta-Analysis", "ENSEMBLE", "EXPERIMENTAL", "READY", "meta",
       "Summarise the methods run in the current experiment and their agreement.",
       "Aggregate recorded method results; report which cues co-occur and any failure findings.", "taxonomy",
       license=_ADAPTED_LIC, known_limitations="Only as reliable as the methods it summarises."),
    # ---- RECONSTRUCTION FORENSICS (Section 13)
    _m(55, "Reconstruction Forensics (self-supervised)", "RECONSTRUCTION FORENSICS", "EXPERIMENTAL", "READY",
       "reconstruction",
       "Reconstruct the image with a training-free self-supervised prior and study the error map.",
       "Guided-filter image prior produces a reconstruction and an error map (candidate signal); on a controlled "
       "surrogate the error map is scored against the known signal. NOT a diffusion/autoencoder reconstruction.",
       "He 2013 guided filter [EXT]; cf. DIRE/AEROBLADE (UNAVAILABLE)", license=_ADAPTED_LIC,
       input_requirements="a single image; a controlled surrogate case to score recovery",
       known_limitations="A learning-free prior is weaker than a diffusion/AE reconstruction; descriptive error map."),
    # ---- FRONTIER (Section 23) - all HYPOTHETICAL, controlled data only
    _m(56, "Multi-Representation Residual Consensus", "FRONTIER", "HYPOTHETICAL", "READY",
       "frontier:multi_representation_residual_consensus",
       "Fuse residual agreement across RGB / FFT / DWT / DCT representations.",
       "Z-score residual maps per domain, measure pairwise agreement and a fused candidate; recovery scored on a "
       "controlled case.", "taxonomy 1F/2B", license=_ADAPTED_LIC,
       input_requirements="an image; a controlled surrogate case for recovery scoring",
       known_limitations="Content/edges correlate across domains.", validation_status="HYPOTHESIS TEST"),
    _m(57, "Fingerprint Null-Space Projection", "FRONTIER", "HYPOTHETICAL", "READY", "frontier:fingerprint_null_space",
       "Research feature directions weakly tied to source identity while preserving semantics.",
       "PCA identity subspace vs its null space over patch descriptors of signed/unsigned controlled sets.",
       "taxonomy 2 (causal)", license=_ADAPTED_LIC, requires_ground_truth=True, requires_reference_images=True,
       input_requirements="signed and unsigned controlled image sets",
       known_limitations="Content variance can dominate.", validation_status="HYPOTHESIS TEST"),
    _m(58, "Cross-Scale Topological Residual", "FRONTIER", "HYPOTHETICAL", "READY",
       "frontier:cross_scale_topological_residual",
       "Measure the topology (component curve) of the candidate residual across scales.",
       "Component-count curve of residual super-level sets at several scales; cross-scale stability.", "taxonomy 3",
       license=_ADAPTED_LIC, input_requirements="an image (controlled case for interpretation)",
       known_limitations="Texture produces components at every scale.", validation_status="HYPOTHESIS TEST"),
    _m(59, "Spectral-Semantic Fusion", "FRONTIER", "HYPOTHETICAL", "READY", "frontier:spectral_semantic_fusion",
       "Combine spectral features with a structure (semantic proxy) map.",
       "Fuse a spectral residual with a multi-scale structure map; compare fused recovery to each alone.", "taxonomy 2B/3H",
       license=_ADAPTED_LIC, requires_ground_truth=True, input_requirements="a controlled surrogate case",
       known_limitations="No learned semantics; coarse structure proxy.", validation_status="HYPOTHESIS TEST"),
    _m(60, "Iterative Reconstruction Consensus", "FRONTIER", "HYPOTHETICAL", "READY",
       "frontier:iterative_reconstruction_consensus",
       "Repeated content/signal estimation with convergence and drift measurement.",
       "Iterate guided-smoothing content estimation; track residual energy and drift to convergence.", "taxonomy",
       license=_ADAPTED_LIC, input_requirements="an image (controlled case for recovery)",
       known_limitations="Smoothing erodes content.", validation_status="HYPOTHESIS TEST"),
    _m(61, "Method Disagreement Analysis", "FRONTIER", "HYPOTHETICAL", "READY", "frontier:method_disagreement",
       "Use disagreement between independent estimators as a model-uncertainty signal.",
       "1 - mean pairwise correlation of independent candidate maps.", "taxonomy", license=_ADAPTED_LIC,
       input_requirements="an image", known_limitations="Shared-content agreement is not fingerprint agreement.",
       validation_status="HYPOTHESIS TEST"),
    _m(62, "Fingerprint Stability Field", "FRONTIER", "HYPOTHETICAL", "READY", "frontier:fingerprint_stability_field",
       "Build a spatial field of candidate-fingerprint consistency under a small perturbation.",
       "Per-tile correlation of the candidate residual before/after a small noise perturbation.", "taxonomy",
       license=_ADAPTED_LIC, input_requirements="an image", known_limitations="Noise-dominated tiles are unstable.",
       validation_status="HYPOTHESIS TEST"),
    _m(63, "Provenance Energy Landscape", "FRONTIER", "HYPOTHETICAL", "READY", "frontier:provenance_energy_landscape",
       "Represent experimental transformations as a provenance-energy landscape.",
       "Known-signal energy retained across a grid of standard transformations.", "taxonomy robustness",
       license=_ADAPTED_LIC, requires_ground_truth=True, input_requirements="a controlled surrogate case",
       known_limitations="Geometry-changing transforms are undefined for projection.", validation_status="HYPOTHESIS TEST"),
)


class MethodRegistry:
    def __init__(self) -> None:
        self._by_id = {m.method_id: m for m in METHODS}
        self._by_code = {m.code: m for m in METHODS}

    def all(self) -> list[Method]:
        return list(METHODS)

    def ready(self) -> list[Method]:
        return [m for m in METHODS if m.runnable]

    def get(self, key: str) -> Method:
        if key in self._by_id:
            return self._by_id[key]
        if key in self._by_code:
            return self._by_code[key]
        raise KeyError(f"Unknown method {key!r}")

    def categories(self) -> list[str]:
        return list(CATEGORIES)

    def to_rows(self) -> list[list]:
        return [[m.method_id, m.name, m.category, m.maturity, m.availability, m.local_or_online,
                 "yes" if m.requires_gpu else "no", "yes" if m.requires_model else "no",
                 "yes" if m.requires_ground_truth else "no", m.license, m.source_reference] for m in METHODS]


REGISTRY_COLUMNS = ["Method", "Name", "Category", "Maturity", "Availability", "Local/Online", "GPU", "Model",
                    "Ground truth", "License", "Sources"]


def validate() -> list[str]:
    problems = []
    nums = [int(m.method_id.split()[1]) for m in METHODS]
    if nums != list(range(0, len(METHODS))):
        problems.append(f"methods must be 00..{len(METHODS) - 1} contiguous; got {nums}")
    for m in METHODS:
        if m.maturity not in MATURITIES:
            problems.append(f"{m.method_id}: bad maturity {m.maturity}")
        if m.availability not in AVAILABILITY:
            problems.append(f"{m.method_id}: bad availability {m.availability}")
        if m.availability == "READY" and not m.capability:
            problems.append(f"{m.method_id}: READY but no capability")
        if m.runnable and m.capability not in _CAP_FLAGS:
            problems.append(f"{m.method_id}: READY capability {m.capability!r} has no CAN_* flag mapping")
        if m.availability != "READY" and not m.reason:
            problems.append(f"{m.method_id}: non-READY must state a reason")
        if m.category not in CATEGORIES:
            problems.append(f"{m.method_id}: bad category {m.category}")
        if m.requires_model and m.availability == "READY":
            problems.append(f"{m.method_id}: a READY method must not require a bundled model")
        # a method must not advertise separation/reconstruction unless its capability provides it
        flags = m.capability_flags()
        if flags["CAN_SEPARATE"] and not m.capability.startswith("sep:"):
            problems.append(f"{m.method_id}: CAN_SEPARATE only for sep: capabilities")
    return problems
