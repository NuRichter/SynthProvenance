"""Fingerprint research engine (numpy only, no Qt).

Modules
-------
taxonomy      structured database parsed from the supplied taxonomy file
library       research literature library (taxonomy anchors + validated external additions)
imaging       colour spaces, filters, resampling, overlap-aware tiling
spectral      FFT engine (magnitude, phase, radial / angular spectra, band energy, spectral tail)
wavelet       multi-level 2D DWT (Haar, Daubechies-2) with sub-band statistics
dct           block DCT / JPEG forensics and Benford first-digit statistics
residuals     residual operators and residual statistics
rpca          Robust PCA (I = L + S + E) by inexact augmented Lagrangian
consensus     patch, multi-scale, cross-region and cross-image consensus
features      handcrafted forensic feature vectors, LID / multiLID, attribution, contrastive projection
surrogate     controlled surrogate watermark embedder and detector with known ground truth
redteam       red-team methods that target ONLY the local surrogate watermark / detector
hypotheses    explicitly hypothetical research methods, evaluated on controlled data
robustness    transformation battery with severity sweeps
metrics       research metrics and definitions of custom SynthProvenance metrics
failure       rule-based failure analysis
methods       the method registry (Method 00 - Method 54) and method cards
runner        executes a method and returns a standard MethodResult
"""
