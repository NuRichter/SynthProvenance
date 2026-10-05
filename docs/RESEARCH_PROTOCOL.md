# Research Protocol

Every experiment follows the same pipeline so results are measurable and reproducible.

## Pipeline

```
SOURCE IMAGE
  -> FORENSIC BASELINE          decode, hashes, format, statistics (original preserved)
  -> TAXONOMY CLASSIFICATION    choose the fingerprint family/representation to study
  -> REPRESENTATION SELECTION   RGB / YCbCr / Lab; FFT / DCT / DWT / residual / feature
  -> FINGERPRINT CANDIDATE EXTRACTION
  -> SIGNAL ESTIMATION          estimate a candidate signal / map
  -> CONTENT / SIGNAL DECOMPOSITION   (controlled surrogate only; unified decomposition engine)
  -> EXPERIMENTAL RECONSTRUCTION
  -> PIXEL / PERCEPTUAL VALIDATION    MAE/MSE/PSNR/SSIM (LPIPS UNAVAILABLE)
  -> PROVENANCE COMPARISON
  -> RESEARCH CONCLUSION        cautious; never an AI/human verdict
```

Each stage produces machine-readable artifacts. The Unified Signal Decomposition Engine
(`app/core/unified_signal_decomposition.py`) exposes `analyze / estimate / separate / reconstruct / validate`, and
refuses to separate or reconstruct with a method whose capability flags do not advertise it.

## Ground truth

Separation, reconstruction and robustness claims are made only against a controlled surrogate signal with known ground
truth (`app/research/surrogate.py`): a clean image, a keyed embedded signal, a blind local detector and the known
residual. Recovery is scored by correlation of the recovered candidate with the known signal, and fidelity by
MAE/MSE/PSNR/SSIM against the watermarked image.

## Reproducibility record

Every Fingerprint Research Lab run gets `SPX-FP-YYYYMMDD-NNNNNN` and stores: method and capability flags, parameters,
seed, surrogate config, environment (OS, CPU, GPU, CUDA, library versions), input/output hashes (SHA-256), runtime,
peak memory, and `original_unchanged` (inputs re-hashed after the run). Maps are written as PNG. EXPORT FOR PAPER
writes CSV/JSON/PDF/PNG and a ZIP with SHA-256 and BLAKE3 manifests.

## Determinism

All synthetic data, surrogate keys and stochastic steps use fixed seeds. Re-running a method or reproducing an
exported pipeline (`app/core/method_composer.py`) gives the same result.

## Failure reporting

Weak or negative results are reported, not hidden. Each run carries a rule-based failure analysis
(`app/research/failure.py`): failure mode, observed symptom, likely cause, affected metric, possible improvement.
Hypotheses are reported as SUPPORTED / INCONCLUSIVE / NOT SUPPORTED *on this controlled case* — never as proof.
