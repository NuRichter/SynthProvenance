# Implementation Gap Analysis

Generated from the live method registry of SynthProvenance 2.0.0 (`python scripts/build_gap_analysis.py`). Status is derived from each method's declared capability flags, not from the mere presence of a name in the registry.

## Taxonomy → engine → experiment bridge

| Taxonomy family | Engine modules | Methods / status |
|---|---|---|
| A INTRINSIC / PASSIVE | residuals, consensus, features (LID), rpca | Methods 03-05, 12, 17, 19-25 (residual estimation, PRNU-style cross-image consensus, handcrafted descriptors) |
| B CAUSAL | hypotheses, frontier (null-space) | Methods 31-33 UNAVAILABLE (need trained models); 47, 57 study causal directions on controlled data |
| C SPECTRAL | spectral, dct, wavelet, residuals | Methods 11, 13-18 (FFT/DCT/DWT, spectral tail, high-frequency residual, Benford-DCT) |
| D PROACTIVE / WATERMARK | surrogate, robustness, separation | Methods 34-42, 63 (controlled surrogate ground truth: detection, separation, robustness, energy landscape) |
| E DETECTOR REPRESENTATION | features | Methods 26-29 UNAVAILABLE (CLIP/ViT/DINO need weights); Method 30 handcrafted feature-space attribution |
| F RECONSTRUCTION | frontier (reconstruction), separation | Methods 09-10 UNAVAILABLE (diffusion/AE); Method 55 training-free self-supervised reconstruction error |
| G C2PA PROVENANCE | app/core provenance + analyzers (native) | Methods 01-02 (metadata and C2PA manifest analysis) |

## Per-method traceability

Columns: Analysis / Estimate / Separate / Reconstruct / Validate (capability flags), GT = needs ground truth.

| Method | Name | Family | A | E | S | R | V | GT | Status | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|
| Method 00 | Original / Control | BASELINE | Y | - | - | - | - | - | ANALYSIS ONLY | native |
| Method 01 | Metadata Isolation | METADATA / PROVENANCE | Y | - | - | - | - | - | ANALYSIS ONLY | native |
| Method 02 | C2PA Manifest Analysis | METADATA / PROVENANCE | Y | - | - | - | - | - | ANALYSIS ONLY | C2PA 2.4 spec [EXT]; taxonomy 4K |
| Method 03 | Residual Fingerprint | INTRINSIC FINGERPRINT RESEARCH | Y | Y | - | - | - | - | DETECTOR ONLY | Marra 2019 [EXT]; taxonomy 1B/3F |
| Method 04 | PRNU-Inspired Model Fingerprint | INTRINSIC FINGERPRINT RESEARCH | Y | Y | - | - | Y | - | DETECTOR ONLY | Marra 2019 [EXT]; Lukas 2006 [EXT]; taxonomy 1B |
| Method 05 | GAN Fingerprint (handcrafted) | INTRINSIC FINGERPRINT RESEARCH | Y | - | - | - | - | - | ANALYSIS ONLY | Yu 2019 [TAX-REF-03]; Marra 2019 [EXT] |
| Method 06 | Architecture-Level Fingerprint | INTRINSIC FINGERPRINT RESEARCH | - | - | - | - | - | - | UNAVAILABLE | Yang 2022 DNA-Det [TAX-REF-05] |
| Method 07 | Instance-Level Fingerprint | INTRINSIC FINGERPRINT RESEARCH | - | - | - | - | - | - | UNAVAILABLE | Liu 2024 [TAX-REF-07] |
| Method 08 | Fingerprint Disentanglement | INTRINSIC FINGERPRINT RESEARCH | - | - | - | - | - | - | UNAVAILABLE | Yang 2021 GFD-Net [TAX-REF-06] |
| Method 09 | DIRE | DIFFUSION FORENSICS | - | - | - | - | - | - | UNAVAILABLE | Wang 2023 DIRE [TAX-REF-08] |
| Method 10 | AEROBLADE Reconstruction Error | DIFFUSION FORENSICS | - | - | - | - | - | - | UNAVAILABLE | Ricker 2024 AEROBLADE [TAX-REF-09] |
| Method 11 | Synthbuster-style Spectral | DIFFUSION FORENSICS | Y | - | - | - | - | - | ANALYSIS ONLY | Bammey 2023 Synthbuster [EXT]; taxonomy 6C |
| Method 12 | Diffusion Residual Analysis | DIFFUSION FORENSICS | Y | Y | - | - | - | - | DETECTOR ONLY | taxonomy 1G/6 |
| Method 13 | FFT Analysis | SPECTRAL | Y | - | - | - | - | - | ANALYSIS ONLY | Durall 2020 [TAX-REF-02]; Frank 2020 [TAX-REF-01]; taxonomy 3A |
| Method 14 | DCT Analysis | SPECTRAL | Y | - | - | - | - | - | ANALYSIS ONLY | Frank 2020 [TAX-REF-01]; taxonomy 3D |
| Method 15 | DWT / Wavelet Analysis | SPECTRAL | Y | - | - | - | - | - | ANALYSIS ONLY | taxonomy 3E |
| Method 16 | Spectral Tail Analysis | SPECTRAL | Y | - | - | - | - | - | ANALYSIS ONLY | Durall 2020 [TAX-REF-02]; Dzanic 2020 [EXT]; taxonomy 3C |
| Method 17 | High-Frequency Residual | SPECTRAL | Y | Y | - | - | - | - | DETECTOR ONLY | taxonomy 3F |
| Method 18 | Benford-DCT Statistics | SPECTRAL | Y | - | - | - | - | - | ANALYSIS ONLY | Bonettini 2021 [EXT]; taxonomy 3G |
| Method 19 | LID | GEOMETRIC / STATISTICAL | Y | - | - | - | - | - | ANALYSIS ONLY | Lorenz 2023 [TAX-REF-10] (arXiv withdrawn by authors); taxonomy 5D |
| Method 20 | MultiLID | GEOMETRIC / STATISTICAL | Y | - | - | - | - | - | ANALYSIS ONLY | Lorenz 2023 [TAX-REF-10]; taxonomy 5D |
| Method 21 | Entropy / Noise Statistics | GEOMETRIC / STATISTICAL | Y | Y | - | - | - | - | DETECTOR ONLY | taxonomy 3; image-statistics engine |
| Method 22 | Patch Fingerprint Analysis | SPATIAL / MULTI-SCALE | Y | - | - | - | - | - | ANALYSIS ONLY | taxonomy 1/3 |
| Method 23 | Multi-Scale Consensus | SPATIAL / MULTI-SCALE | Y | - | - | - | - | - | ANALYSIS ONLY | taxonomy 1F/3H |
| Method 24 | Cross-Region Consensus | SPATIAL / MULTI-SCALE | Y | - | - | - | - | - | ANALYSIS ONLY | taxonomy 1/3 |
| Method 25 | Cross-Image Fingerprint Consensus | SPATIAL / MULTI-SCALE | Y | Y | - | - | Y | - | DETECTOR ONLY | Marra 2019 [EXT]; taxonomy 1B |
| Method 26 | CLIP | REPRESENTATION | - | - | - | - | - | - | UNAVAILABLE | Ojha 2023 UnivFD [TAX-REF-17] |
| Method 27 | ViT | REPRESENTATION | - | - | - | - | - | - | UNAVAILABLE | Dosovitskiy 2021 [EXT] |
| Method 28 | DINO | REPRESENTATION | - | - | - | - | - | - | UNAVAILABLE | Caron 2021 [EXT] |
| Method 29 | Contrastive Representation | REPRESENTATION | - | - | - | - | - | - | UNAVAILABLE | Wu 2025 LASTED [TAX-REF-19] |
| Method 30 | Feature-Space Attribution | REPRESENTATION | Y | - | - | - | - | - | ANALYSIS ONLY | taxonomy 5G |
| Method 31 | Causal Fingerprint | CAUSAL | - | - | - | - | - | - | UNAVAILABLE | Xu 2025 [TAX-REF-12] |
| Method 32 | Semantic-Invariant Representation | CAUSAL | - | - | - | - | - | - | UNAVAILABLE | Xu 2025 [TAX-REF-12] |
| Method 33 | Counterfactual Fingerprint Analysis | CAUSAL | - | - | - | - | - | - | UNAVAILABLE | Xu 2025 [TAX-REF-12] |
| Method 34 | Surrogate High-Pass Separation | CONTROLLED SURROGATE STUDY | Y | Y | Y | Y | Y | Y | FULLY IMPLEMENTED | taxonomy 3F |
| Method 35 | Surrogate Wavelet Separation | CONTROLLED SURROGATE STUDY | Y | Y | Y | Y | Y | Y | FULLY IMPLEMENTED | taxonomy 3E |
| Method 36 | Surrogate FFT Separation | CONTROLLED SURROGATE STUDY | Y | Y | Y | Y | Y | Y | FULLY IMPLEMENTED | taxonomy 3A |
| Method 37 | Surrogate Robust-PCA Separation | CONTROLLED SURROGATE STUDY | Y | Y | Y | Y | Y | Y | FULLY IMPLEMENTED | Candes 2011 RPCA [EXT]; taxonomy formulation |
| Method 38 | Surrogate Constrained Separation | CONTROLLED SURROGATE STUDY | Y | Y | Y | Y | Y | Y | FULLY IMPLEMENTED | He 2013 guided filter [EXT] |
| Method 39 | Surrogate Robustness Sweep | CONTROLLED SURROGATE STUDY | Y | - | - | - | Y | Y | ANALYSIS ONLY | An 2024 WAVES [EXT]; taxonomy robustness list |
| Method 40 | Surrogate Signal Persistence Map | CONTROLLED SURROGATE STUDY | Y | Y | - | - | Y | Y | DETECTOR ONLY | taxonomy robustness |
| Method 41 | Surrogate Reconstruction Fidelity | CONTROLLED SURROGATE STUDY | Y | Y | Y | Y | Y | Y | FULLY IMPLEMENTED | taxonomy |
| Method 42 | Surrogate Counterfactual Separation | CONTROLLED SURROGATE STUDY | Y | Y | Y | Y | Y | Y | FULLY IMPLEMENTED | taxonomy 2C (adapted, learning-free) |
| Method 43 | Surrogate Adversarial Optimisation | CONTROLLED SURROGATE STUDY | - | - | - | - | - | - | NOT IMPLEMENTED | taxonomy 2D |
| Method 44 | Surrogate Black-Box Detector Attack | CONTROLLED SURROGATE STUDY | - | - | - | - | - | - | NOT IMPLEMENTED | taxonomy 2D |
| Method 45 | Surrogate Evolutionary Search | CONTROLLED SURROGATE STUDY | - | - | - | - | - | - | NOT IMPLEMENTED | taxonomy 2D |
| Method 46 | Surrogate Differentiable Attack | CONTROLLED SURROGATE STUDY | - | - | - | - | - | - | NOT IMPLEMENTED | taxonomy 2D |
| Method 47 | Provenance-Orthogonal Subspace | ADVANCED HYPOTHESIS | Y | - | - | - | Y | Y | RESEARCH ONLY | taxonomy 2/2A |
| Method 48 | Information-Bottleneck Decoupling | ADVANCED HYPOTHESIS | Y | Y | - | - | Y | Y | RESEARCH ONLY | taxonomy |
| Method 49 | Frequency-Semantic Cross-Domain | ADVANCED HYPOTHESIS | Y | Y | - | - | Y | Y | RESEARCH ONLY | taxonomy 2B/3H |
| Method 50 | Topological Residual | ADVANCED HYPOTHESIS | Y | - | - | - | Y | Y | RESEARCH ONLY | taxonomy |
| Method 51 | Cross-Representation Consensus | ADVANCED HYPOTHESIS | Y | - | - | - | Y | - | RESEARCH ONLY | taxonomy 2B |
| Method 52 | Automated Hypothesis Discovery | ADVANCED HYPOTHESIS | Y | Y | - | - | Y | Y | RESEARCH ONLY | taxonomy |
| Method 53 | Ensemble Research | ENSEMBLE | Y | - | - | - | - | - | ANALYSIS ONLY | taxonomy |
| Method 54 | Meta-Analysis | ENSEMBLE | Y | - | - | - | - | - | ANALYSIS ONLY | taxonomy |
| Method 55 | Reconstruction Forensics (self-supervised) | RECONSTRUCTION FORENSICS | Y | Y | - | Y | Y | - | PARTIALLY IMPLEMENTED | He 2013 guided filter [EXT]; cf. DIRE/AEROBLADE (UNAVAILABLE) |
| Method 56 | Multi-Representation Residual Consensus | FRONTIER | Y | Y | - | - | Y | - | RESEARCH ONLY | taxonomy 1F/2B |
| Method 57 | Fingerprint Null-Space Projection | FRONTIER | Y | - | - | - | Y | Y | RESEARCH ONLY | taxonomy 2 (causal) |
| Method 58 | Cross-Scale Topological Residual | FRONTIER | Y | - | - | - | Y | - | RESEARCH ONLY | taxonomy 3 |
| Method 59 | Spectral-Semantic Fusion | FRONTIER | Y | Y | - | - | Y | Y | RESEARCH ONLY | taxonomy 2B/3H |
| Method 60 | Iterative Reconstruction Consensus | FRONTIER | Y | Y | - | Y | Y | - | PARTIALLY IMPLEMENTED | taxonomy |
| Method 61 | Method Disagreement Analysis | FRONTIER | Y | - | - | - | Y | - | RESEARCH ONLY | taxonomy |
| Method 62 | Fingerprint Stability Field | FRONTIER | Y | Y | - | - | Y | - | RESEARCH ONLY | taxonomy |
| Method 63 | Provenance Energy Landscape | FRONTIER | Y | - | - | - | Y | Y | RESEARCH ONLY | taxonomy robustness |

## Summary

- FULLY IMPLEMENTED: 7
- PARTIALLY IMPLEMENTED: 2
- DETECTOR ONLY: 7
- ANALYSIS ONLY: 19
- RESEARCH ONLY: 13
- UNAVAILABLE: 12
- NOT IMPLEMENTED: 4

Total methods: 64.

Notes: FULLY IMPLEMENTED methods are the controlled-surrogate separation studies, where separation and reconstruction are scored against known ground truth. Descriptive spectral/residual/statistical methods are ANALYSIS ONLY by design (they characterise, they do not separate). UNAVAILABLE methods need a deep-learning runtime and trained weights that are not bundled. NOT IMPLEMENTED methods (detector evasion) are out of scope by design. No method is marked implemented merely because it is registered.
