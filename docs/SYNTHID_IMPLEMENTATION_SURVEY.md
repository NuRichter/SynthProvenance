# SynthID Implementation Survey

Survey of public implementations of AI-generated-image fingerprinting, detection, attribution and watermarking
methods, assessed for SynthProvenance. SynthProvenance is a local-first Windows desktop app whose shipped build uses
only PySide6, numpy and Pillow, with no PyTorch.

- **Accessed:** 2026-10-05. This is the first version of this document; no earlier
  `docs/SYNTHID_IMPLEMENTATION_SURVEY.md` existed.
- **Companion data:** the same entries in machine-readable form, `implementations.json`. It was written to the
  survey scratchpad (`research/implementations.json`), not to the repository.
- **Related documents:** `docs/SYNTHID_RESEARCH_SOURCES.md` covers SynthID itself: no local SynthID image detector
  exists, and verification runs only through Google-hosted pathways.

## 1. Purpose and method

**Purpose.** To record, for each method, whether an official implementation exists, under what licence, what it
needs to run, and whether its core idea can be reproduced inside SynthProvenance without a deep-learning runtime.
This tells the app which methods can honestly be offered as local **ADAPTED** re-implementations and which must be
shown as **UNAVAILABLE**.

**Sources.** Only pages that were actually fetched on 2026-10-05:

- GitHub repository pages and raw `LICENSE` / `README` / `requirements` files
- GitHub REST API metadata (licence SPDX id, `pushed_at`)
- arXiv abstract and HTML pages, CVF / PMLR / AAAI / NeurIPS / OpenReview pages
- Hugging Face model and dataset cards, Zenodo, and PyPI

Every entry in `implementations.json` lists its source URLs. Pages that failed to load are not cited.

**Validation rule: a README is not proof.** A README, abstract or results table shows what the authors *claim*.
Accuracy figures below are recorded as claims ("claims ..."). Independent follow-up results are attributed to the
paper that reported them. Nothing in this survey was executed (see Section 6).

**Conventions.**

- `UNKNOWN` means the information was not found on any fetched page.
- `no license file` means the repository has no LICENSE file. GitHub returns `license: null` for such repos, and
  under copyright law all rights are reserved.
- `NOASSERTION` means GitHub could not match the licence file to an SPDX id. In that case the licence text was read
  directly.
- Weight sizes are given only where a page states them. Most Google Drive, Baidu and Dropbox links do not.

**Verdicts.**

| Verdict | Meaning |
|---|---|
| NUMPY-REIMPLEMENTABLE | The core idea can be faithfully reproduced with numpy/Pillow without pretrained neural weights. A shallow decision layer (ridge, logistic regression, threshold) may still need locally supplied labelled images; such entries are marked † and are ADAPTED, not identical. |
| REQUIRES-DL-RUNTIME | Needs torch, TensorFlow or ONNX plus pretrained network weights. |
| REQUIRES-TRAINING-DATA | The learned model is not released, or training on large labelled sets is needed before anything can run. |
| NOT-APPLICABLE | Cannot be applied to an arbitrary third-party image because it needs the owner's secret key, the generating model, or a watermark planted at training time. Also used for work that is not a detector. |

**Survey limitations.**

- The GitHub API rate-limited part-way through. Remaining licence and activity checks used repository pages and raw
  files instead.
- ModelScope and Kaggle pages did not render, so DRCT-2M, WildFake and ArtiFact details on those hosts are partly
  UNKNOWN.
- Closed-access papers (Liu et al. 2024) could only be assessed from their abstracts.

## 2. Summary table

† = numpy-reimplementable features, but the decision layer must be fit on local labelled data (ADAPTED).

| # | Method (venue, year) | Official repo | Licence | Framework | Weights | Verdict |
|---|---|---|---|---|---|---|
| 1 | Marra et al., *Do GANs leave artificial fingerprints?* (MIPR 2019) | none found | n/a | none needed (denoising residual + correlation) | none; per-generator reference images | NUMPY-REIMPLEMENTABLE † |
| 2 | Yu, Davis, Fritz, GAN fingerprints / attribution (ICCV 2019) | [ningyu1991/GANFingerprints](https://github.com/ningyu1991/GANFingerprints) | CC-BY-NC-4.0 + custom non-commercial (GitHub: NOASSERTION) | TensorFlow 1.12 | Google Drive, size UNKNOWN, non-commercial | REQUIRES-DL-RUNTIME |
| 3 | Yu et al., Artificial Fingerprinting (ICCV 2021) | [ningyu1991/ArtificialGANFingerprints](https://github.com/ningyu1991/ArtificialGANFingerprints) | custom non-commercial (NOASSERTION) | PyTorch | Google Drive encoder/decoder + 12 GANs, size UNKNOWN | NOT-APPLICABLE |
| 4 | Frank et al., DCT frequency analysis (ICML 2020) | [RUB-SysSec/GANDCTAnalysis](https://github.com/RUB-SysSec/GANDCTAnalysis) | MIT | TensorFlow 2 + numpy | optional, Google Drive, size UNKNOWN | NUMPY-REIMPLEMENTABLE † |
| 5 | Durall et al., up-convolution spectra (CVPR 2020) | [cc-hpc-itwm/UpConv](https://github.com/cc-hpc-itwm/UpConv); detector in [cc-hpc-itwm/DeepFakeDetection](https://github.com/cc-hpc-itwm/DeepFakeDetection) | GPL-3.0 (UpConv); no license file (DeepFakeDetection) | PyTorch 1.1 (training); numpy + OpenCV (detector) | none | NUMPY-REIMPLEMENTABLE † |
| 6 | Schwarz et al., frequency bias (NeurIPS 2021) | [autonomousvision/frequency_bias](https://github.com/autonomousvision/frequency_bias) | MIT | PyTorch | none | NOT-APPLICABLE |
| 7 | Bonettini et al., Benford's law (ICPR 2020, publ. 2021) | none found | n/a | none needed (block DCT + Random Forest) | none | NUMPY-REIMPLEMENTABLE † |
| 8 | DNA-Det, Yang et al. (AAAI 2022) | [ICTMCG/DNA-Det](https://github.com/ICTMCG/DNA-Det) | no license file | PyTorch 1.9 | Baidu / Google Drive, size UNKNOWN | REQUIRES-TRAINING-DATA |
| 9 | GFD-Net, Yang et al. (arXiv 2106.08749, 2021) | none found | n/a | UNKNOWN | none released | REQUIRES-TRAINING-DATA |
| 10 | Liu et al., multi-level GAN fingerprints (Computer Standards & Interfaces 89, 2024) | none found | n/a | UNKNOWN | none released | REQUIRES-TRAINING-DATA |
| 11 | DIRE, Wang et al. (ICCV 2023) | [ZhendongWang6/DIRE](https://github.com/ZhendongWang6/DIRE) (archived) | no license file | PyTorch 2.0 | classifier + ADM diffusion model on BaiduDrive/RecDrive, size UNKNOWN | REQUIRES-DL-RUNTIME |
| 12 | AEROBLADE, Ricker et al. (CVPR 2024) | [jonasricker/aeroblade](https://github.com/jonasricker/aeroblade) | no license file | PyTorch 2.1 + diffusers + lpips | SD1 / SD2 / Kandinsky 2.1 autoencoders from Hugging Face + LPIPS | REQUIRES-DL-RUNTIME |
| 13 | multiLID, Lorenz et al. (ICCV-W 2023; arXiv withdrawn) | [juanmals/deepfake_multiLID](https://github.com/juanmals/deepfake_multiLID) | MIT | PyTorch (+ TF/JAX pins) | pretrained ResNet-18 features | REQUIRES-DL-RUNTIME |
| 14 | ManiFPT, Song et al. (CVPR 2024) | none (project-page repo only) | n/a | UNKNOWN | none released | REQUIRES-TRAINING-DATA |
| 15 | Causal Fingerprints, Xu et al. (ICASSP 2026; arXiv 2509.15406) | none found | n/a | UNKNOWN (DIRE + VAE + CLIP) | none released | REQUIRES-DL-RUNTIME |
| 16 | ProMark, Asnani et al. (CVPR 2024) | none found | n/a | UNKNOWN | none released | NOT-APPLICABLE |
| 17 | Stable Signature, Fernandez et al. (ICCV 2023) | [facebookresearch/stable_signature](https://github.com/facebookresearch/stable_signature) | CC-BY-NC-4.0 (src/ldm, src/taming MIT) | PyTorch 1.12 | 48-bit extractors on dl.fbaipublicfiles.com, size UNKNOWN, CC-BY-NC | REQUIRES-DL-RUNTIME |
| 18 | Tree-Ring, Wen et al. (NeurIPS 2023) | [YuxinWenRick/tree-ring-watermark](https://github.com/YuxinWenRick/tree-ring-watermark) | MIT (GitHub API; LICENSE file not fetched directly) | PyTorch + diffusers 0.11 | Stable Diffusion 2.1 base | NOT-APPLICABLE |
| 19 | Gaussian Shading, Yang et al. (CVPR 2024) | [bsmhmmlf/Gaussian-Shading](https://github.com/bsmhmmlf/Gaussian-Shading) | MIT (GitHub API) | PyTorch | Stable Diffusion v1.4 / v2.x | NOT-APPLICABLE |
| 20 | RingID, Ci et al. (ECCV 2024) | [showlab/RingID](https://github.com/showlab/RingID) | no license file | PyTorch + diffusers 0.11 | Stable Diffusion v2 | NOT-APPLICABLE |
| 21 | HiDDeN, Zhu et al. (ECCV 2018) | [jirenz/HiDDeN](https://github.com/jirenz/HiDDeN) | MIT | Lua Torch7 | none ("coming soon") | REQUIRES-TRAINING-DATA |
| 22 | StegaStamp, Tancik et al. (CVPR 2020) | [tancik/StegaStamp](https://github.com/tancik/StegaStamp) | MIT (GitHub API) | TensorFlow 1.13 | saved encoder/decoder + detector, host/size not stated | REQUIRES-DL-RUNTIME |
| 23 | WAVES benchmark, An et al. (ICML 2024) | [umd-huang-lab/WAVES](https://github.com/umd-huang-lab/WAVES) | no license file (README says MIT) | PyTorch + ONNX decoders | ONNX decoders in repo; diffusion/VAE for attacks | NUMPY-REIMPLEMENTABLE (8 distortion attacks only) |
| 24 | Regeneration attack, Zhao et al. (NeurIPS 2024) | [XuandongZhao/WatermarkAttacker](https://github.com/XuandongZhao/WatermarkAttacker) | MIT | PyTorch + diffusers + compressai | Stable Diffusion + compressai VAEs | REQUIRES-DL-RUNTIME |
| 25 | TrustMark, Bui et al. (Adobe; ICCV 2025) | [adobe/trustmark](https://github.com/adobe/trustmark) (PyPI `trustmark`) | MIT for code and model files (README; GitHub: NOASSERTION) | PyTorch; ONNX (JS/Rust) | 21–45 MB decoders from cai-watermark.adobe.net, MIT | REQUIRES-DL-RUNTIME |
| 26 | invisible-watermark / imwatermark (DwtDct, DwtDctSvd, RivaGAN) | [ShieldMnt/invisible-watermark](https://github.com/ShieldMnt/invisible-watermark) | MIT | numpy + OpenCV + PyWavelets; onnxruntime for RivaGAN | none for DwtDct; RivaGAN ONNX | NUMPY-REIMPLEMENTABLE (DwtDct/DwtDctSvd) |
| 27 | UnivFD, Ojha et al. (CVPR 2023) | [WisconsinAIVision/UniversalFakeDetect](https://github.com/WisconsinAIVision/UniversalFakeDetect) | MIT | PyTorch + CLIP ViT-L/14 | linear head in repo + CLIP backbone | REQUIRES-DL-RUNTIME |
| 28 | LASTED, Wu et al. (IEEE TAI 2025; arXiv 2023) | [HighwayWu/LASTED](https://github.com/HighwayWu/LASTED) | MIT (GitHub API) | PyTorch 1.9 + CLIP | Google Drive, size UNKNOWN | REQUIRES-DL-RUNTIME |
| 29 | SPAI, Karageorgiou et al. (CVPR 2025) | [mever-team/spai](https://github.com/mever-team/spai) | Apache-2.0 (code and weights) | PyTorch, CUDA 12.4 | Google Drive checkpoint, size UNKNOWN | REQUIRES-DL-RUNTIME |
| 30 | PPM-CLIP, Wang et al. (CVPR 2026) | [bandaidssssss/PPM_CLIP](https://github.com/bandaidssssss/PPM_CLIP) (self-described official; not linked from the CVPR page) | no license file | PyTorch 2.5.1 + CLIP/LoRA | ModelScope, size UNKNOWN | REQUIRES-DL-RUNTIME |
| 31 | DeeCLIP, Keita et al. (arXiv 2504.19876, 2025) | [Mamadou-Keita/DeeCLIP](https://github.com/Mamadou-Keita/DeeCLIP) | no license file | PyTorch 2.1.2 + CLIP-ViT + LoRA | Dropbox, size UNKNOWN | REQUIRES-DL-RUNTIME |
| 32 | Synthbuster, Bammey (IEEE OJSP, 2023/2024) | [qbammey/synthbuster](https://github.com/qbammey/synthbuster) | no license file | numpy / scipy / scikit-learn / numba | scikit-learn joblib models ~1.4 MB, unlicensed | NUMPY-REIMPLEMENTABLE † |
| 33 | CNNSpot, Wang et al. (CVPR 2020) | [PeterWang512/CNNDetection](https://github.com/PeterWang512/CNNDetection) | CC-BY-NC-SA-4.0 | PyTorch ResNet-50 | Dropbox, size UNKNOWN, CC-BY-NC-SA | REQUIRES-DL-RUNTIME |
| 34 | NPR, Tan et al. (CVPR 2024) | [chuangchuangtan/NPR-DeepfakeDetection](https://github.com/chuangchuangtan/NPR-DeepfakeDetection) | no license file | PyTorch | NPR.pth 17.4 MB in repo, unlicensed | REQUIRES-DL-RUNTIME |
| 35 | B-Free, Guillaro et al. (CVPR 2025): *2025–26 addition* | [grip-unina/B-Free](https://github.com/grip-unina/B-Free) | custom GRIP-UNINA non-commercial (NOASSERTION) | PyTorch, DINOv2-with-registers ViT | zip from grip.unina.it, size UNKNOWN | REQUIRES-DL-RUNTIME |
| 36 | CO-SPY, Cheng et al. (CVPR 2025): *addition* | [Megum1/Co-Spy](https://github.com/Megum1/Co-Spy) | MIT | PyTorch 2.4.1, CUDA 12.1 | Hugging Face `ruojiruoli/Co-Spy-Pretrained-Weights`, size and licence UNKNOWN | REQUIRES-DL-RUNTIME |
| 37 | AIDE, Yan et al. (ICLR 2025): *addition* | [shilinyan99/AIDE](https://github.com/shilinyan99/AIDE) | MIT (Chameleon data: academic use only) | PyTorch 2.0.1, OpenCLIP + ResNet-50/ConvNeXt | Google Drive, size UNKNOWN | REQUIRES-DL-RUNTIME |
| 38 | Community Forensics detector, Park & Owens (CVPR 2025): *addition* | [JeongsooP/Community-Forensics](https://github.com/JeongsooP/Community-Forensics) | MIT | PyTorch ViT | Hugging Face `OwensLab/commfor-model-384` / `-224`, 21.8M params, MIT | REQUIRES-DL-RUNTIME |
| 39 | WaRPAD, Choi et al. (NeurIPS 2025): *addition* | [sungikchoi/WaRPAD](https://github.com/sungikchoi/WaRPAD) | no license file | PyTorch 2.8 + DINOv2 ViT-L/14 | no detector weights; DINOv2 backbone via torch.hub | REQUIRES-DL-RUNTIME |
| 40 | Manifold Induced Biases, Brokman et al. (ICLR 2025): *addition* | [JonathanBrok/Manifold-Induced-Biases-…](https://github.com/JonathanBrok/Manifold-Induced-Biases-for-Zero-shot-and-Few-shot-Detection-of-Generated-Images) | no license file | PyTorch + diffusers | Stable Diffusion v1.4 | REQUIRES-DL-RUNTIME |
| 41 | Forensic Self-Descriptions, Nguyen et al. (CVPR 2025): *addition* | none found | n/a | no network needed in principle (linear predictive filters + GMM) | not released; must be fit on real images | REQUIRES-TRAINING-DATA |
| 42 | VINE watermark + W-Bench, Lu et al. (ICLR 2025): *addition* | [Shilin-LU/VINE](https://github.com/Shilin-LU/VINE) | NTU / NTUitive non-commercial dual licence | PyTorch, SDXL-Turbo based | Hugging Face VINE-B / VINE-R encoder and decoder, size UNKNOWN | REQUIRES-DL-RUNTIME |
| 43 | UnMarker, Kassis & Hengartner (IEEE S&P 2025): *addition* | [andrekassis/ai-watermark](https://github.com/andrekassis/ai-watermark) | custom non-commercial (NOASSERTION) | PyTorch, GPU with ≥ 32 GB | none for the attack itself | NOT-APPLICABLE |
| 44 | SynthID-Image, Gowal et al. (arXiv 2510.09263, 2025): *addition* | none (nothing released) | n/a | not released | not released | NOT-APPLICABLE |

**Verdict counts (44 methods):**

| Verdict | Count |
|---|---|
| NUMPY-REIMPLEMENTABLE | 7 (5 of them †) |
| REQUIRES-DL-RUNTIME | 23 |
| REQUIRES-TRAINING-DATA | 6 |
| NOT-APPLICABLE | 8 |

Five lower-priority entries from the 2025–2026 search are listed in Section 5.2 and are not counted.

## 3. Per-method notes

Each note gives the core mechanism, evaluation data, reported limitations and last visible activity. Figures are the
authors' claims unless attributed to a follow-up paper.

### 3.1 Classical fingerprints and spectral cues

**1. Marra et al. 2019.**
- **Method:** takes the noise residual `R = X − f(X)` from a denoiser (the paper does not name the filter), averages
  residuals into a per-GAN fingerprint, and attributes by correlation.
- **Evaluation:** CycleGAN, ProGAN and StarGAN images plus RAISE camera images, 256 px, 512 fingerprint / 488 test
  images per source. Claims near-perfect AUC, weaker for StarGAN.
- **Limitations:** closed set, needs reference images per candidate generator. Follow-up attacks remove such
  fingerprints: *Smudged Fingerprints* (IEEE SaTML 2026) reports >80% white-box and >50% black-box success across 14
  methods, and Lai et al. 2025 (arXiv 2508.03067) report 97% average attack success.
- **Code:** no official code.

**2. Yu et al. 2019.**
- **Method:** a learned CNN attributes images to one of ProGAN, SNGAN, CramerGAN or MMDGAN (CelebA / LSUN, 128 px).
- **Requirements:** Linux, CUDA 10.0, Python 3.6, tensorflow-gpu 1.12.
- **Limitations:** closed set at 128 px.
- **Activity:** last push 2023-04-16.

**3. Yu et al. 2021.**
- **Method:** proactive. A 100-bit fingerprint is embedded in the training data, and a decoder recovers it from the
  generated images. Claims 0.93–0.99 bitwise accuracy.
- **Applicability:** works only for generators trained on fingerprinted data, so it is useless on arbitrary images.
- **Activity:** last push 2023-04-16.

**4. Frank et al. 2020.**
- **Method:** log-scaled 2-D DCT spectra fed to ridge or logistic regression (plus CNN variants).
- **Evaluation:** FFHQ, CelebA and LSUN real images against StyleGAN, BigGAN, ProGAN and others. Claims 100% for
  ridge regression on StyleGAN vs FFHQ.
- **Limitations:**
  - The authors note evasion by crafted perturbations, and accuracy drops to about 84% with anti-aliased upsampling.
  - Ricker et al. (VISAPP 2024) report that diffusion models lack GAN grid artefacts, so GAN-trained detectors need
    retraining.
- **Activity:** last push 2023-02-15.

**5. Durall et al. 2020.**
- **Method:** DFT power spectrum, reduced to a 1-D profile by azimuthal averaging, then SVM / logistic regression /
  k-means.
- **Evaluation:** claims up to 100% on CelebA with 20 training samples and about 90% on FaceForensics++.
- **Limitations:** the README warns of sensitivity to resizing, compression and non-square inputs. The authors' own
  spectral loss removes the cue, so it can be evaded by design.
- **Code:** the official detector code (DeepFakeDetection) uses no deep learning. Last activity 2020-03-26.

**6. Schwarz et al. 2021.**
- **What it is:** an analysis of why GAN upsampling and discriminators cause spectral artefacts, using a "reduced
  spectrum" measurement. It is not a detector.
- **Activity:** last push 2021-11-30.

**7. Bonettini et al. 2021.**
- **Method:**
  1. 8×8 block DCT, re-quantised at JPEG quality 80–100.
  2. First-significant-digit histograms of the first 9 AC coefficients.
  3. Divergence from the generalised Benford law.
  4. Random Forest.
- **Evaluation:** claims 99.83% on uncompressed GAN images.
- **Limitations:** the authors report poor results after JPEG recompression without retraining, and weaker results on
  face GANs. Diffusion models were not tested.
- **Code:** no official code.

### 3.2 Learned attribution and reconstruction-based detection

**8. DNA-Det.**
- **Method:** architecture-level attribution with patchwise contrastive learning, tested on 10 GANs (cross-seed,
  cross-loss, cross-finetune, cross-dataset).
- **Requirements:** Linux, CUDA 11.1, Python 3.7, PyTorch 1.9.
- **Limitations:** GAN-only and closed set.
- **Activity:** last commit 2023-07-04.

**9. GFD-Net.**
- **Method:** U-Net disentangling network with adversarial and auxiliary-classifier losses.
- **Limitations:** the authors report that open-world performance "degrades across all methods".
- **Code / venue:** no code and no peer-reviewed venue found.

**10. Liu et al. 2024.**
- **What is known:** the paper is closed access. The abstract describes two levels of fingerprint in different signal
  domains, a decoupling framework and adversarial augmentation.
- **Unknown:** datasets, code and limitations.

**11. DIRE.**
- **Method:**
  1. Compute `|x − reconstruction(x)|` via DDIM inversion with a pretrained ADM diffusion model.
  2. Train a ResNet classifier on those maps.
- **Evaluation:** DiffusionForensics.
- **Limitations:**
  - Ricker et al. (AEROBLADE, Sec. 5.3) suspect a storage bias: real-image maps saved as JPEG and generated-image maps
    as PNG.
  - Grommelt et al. 2024 (*Fake or JPEG?*) report near-perfect results on DIRE data but a sharp drop on GenImage.
  - Reconstruction is computationally heavy.
- **Activity:** repo archived; last commit 2024-09-26.

**12. AEROBLADE.**
- **Method:** training-free. Score = minimum LPIPS distance between the image and its reconstruction by each latent
  diffusion model's autoencoder.
- **Evaluation:** SD 1.1, 1.5, 2.1, Kandinsky 2.1 and Midjourney v4/v5/v5.1 against LAION. Reports AP and
  TPR@5%FPR.
- **Limitations:**
  - Only covers latent diffusion models whose autoencoder is available.
  - Robustness depends on the dataset and the LPIPS layer.
  - Weaker on low-complexity images.
  - On 2026-10-05 the Hugging Face API returned 401 for `stabilityai/stable-diffusion-2-1-base`, so the SD2 weights
    may no longer be obtainable as the README describes.
- **Activity:** last commit 2024-12-09.

**13. multiLID.**
- **Method:** multi-scale local intrinsic dimensionality of ResNet-18 feature maps, fed to a classifier.
- **Status:** the authors **withdrew** the arXiv version: "We have a serious bug and the method is not that good as
  thought." The repository linked from the paper returns 404. A copy labelled "Official Implementation" (MIT) exists
  at juanmals/deepfake_multiLID. Treat its results as unreliable.
- **Activity:** last commit 2023-08-14.

**14. ManiFPT.**
- **Venue:** CVPR 2024, not ICLR.
- **Method:** artefact = generated sample minus its nearest real sample in RGB, FFT or embedding space; attribution by
  a ResNet-50.
- **Evaluation:** 18–24 generators per GM-dataset.
- **Code:** the code and dataset promised in March 2024 were not found on 2026-10-05.

**15. Causal Fingerprints (Xu et al.).**
- **Method:** DIRE reconstruction residuals mapped into a semantic-invariant latent space, with a VAE and a CLIP-based
  attribution network.
- **Evaluation:** 4 generators from GM-GenImage. Claims 98.04% accuracy.
- **Venue / code:** accepted at ICASSP 2026; no code. It inherits DIRE's dependencies and DIRE's reported bias.

### 3.3 Watermarking (attribution by design) and watermark robustness

**16. ProMark.**
- **Method:** concept watermarks embedded in training data so that generated images can be attributed to training
  concepts. Uses a RoSteALS encoder/decoder and an LDM.
- **Limitations:** authors report a quality / attribution trade-off and LDM-only results.
- **Code:** none found.

**17. Stable Signature.**
- **Method:** the LDM decoder is fine-tuned to embed a fixed 48-bit signature, and an extractor network reads it.
  Claims 90+% detection after a 10% crop at FPR < 1e-6.
- **Limitations:**
  - WAVES reports vulnerability to regeneration with different VAEs.
  - Zhao et al. report that regeneration removes 65–100% of signatures.
- **Requirements:** Python 3.8, PyTorch 1.12, CUDA 11.3.
- **Activity:** last push 2026-09-02.

**18. Tree-Ring.**
- **Method:** a key pattern is placed in the Fourier transform of the initial noise. Detection uses DDIM inversion.
- **Limitations:**
  - WAVES finds it vulnerable to grey-box adversarial embedding attacks.
  - Müller et al. (CVPR 2025) show forgery and removal using unrelated models.
  - RingID reports weak multi-key identification.
  - Zhao et al. find it robust to regeneration but visibly altering.
- **Activity:** last push 2024-03-21.

**19. Gaussian Shading.**
- **Method:** a ChaCha20-encrypted watermark is mapped into the initial latent by distribution-preserving sampling.
  Extraction is DDIM inversion followed by decryption.
- **Limitations:**
  - The authors note key management, the need for operator cooperation, and forgery if model parameters leak.
  - Müller et al. (CVPR 2025) attack it.
- **Activity:** last push 2024-05-15.

**20. RingID.**
- **Method:** multi-key extension of Tree-Ring.
- **Limitations:** the authors report vulnerability to crop/scale in identification.
- **Activity:** last push 2024-08-30.

**21. HiDDeN.**
- **Method:** jointly trained encoder/decoder with a noise layer.
- **Code status:** official Lua Torch code is marked WIP, and its weights were never released. The popular PyTorch
  re-implementation (ando-khachatryan/HiDDeN, MIT) says it does not fully reproduce the paper.

**22. StegaStamp.**
- **Method:** learned encoder/decoder robust to print-and-capture; 100-bit payload (56 bits after error correction).
  Claims 98.7% mean bit accuracy.
- **Robustness:** WAVES ranks it the most robust of the three watermarks it tested. Zhao et al. find it more
  resistant to regeneration than pixel-level watermarks.
- **Activity:** last push 2023-12-08.

**23. WAVES.**
- **What it is:** a benchmark with 26 attacks in three groups:
  - 8 distortions: rotation, crop, erase, brightness, contrast, blur, noise, JPEG
  - 6 regeneration attacks
  - 12 adversarial attacks

  It reports TPR@0.1%FPR plus a normalised quality-degradation score, on DiffusionDB, MS-COCO and DALL-E 3 (5,000
  images each). It evaluates Stable Signature, Tree-Ring and StegaStamp.
- **Licence:** the README says MIT, but the repository has no LICENSE file.
- **Activity:** last push 2024-09-15.

**24. Zhao et al. regeneration attack.**
- **Method:** add noise in latent or pixel space, then reconstruct with a diffusion model or VAE.
- **Results (claims):** removes 93–99% of RivaGAN, 91–99% of DwtDctSvd, 85–97% of SSL and 65–100% of Stable
  Signature watermarks. StegaStamp is more resistant, and Tree-Ring kept over 99% detection.
- **Activity:** last push 2025-01-24.

**25. TrustMark.**
- **Method:** 100-bit payload with BCH error-correction options. The residual is computed at 256 px and scaled to any
  resolution. Tested against 18 perturbations.
- **Removal model:** TrustMark-RM is a public model that removes the watermark.
- **Weights:** downloaded on first use from `cai-watermark.adobe.net`. The README says the host moved from Netlify to
  S3 in April 2026.
- **Applicability:** it is the only decoder in this list that is public and keyless, so it can be applied to anyone's
  image. It still needs PyTorch or ONNX.
- **Activity:** last push 2026-09-29; PyPI 0.9.2 released 2026-09-08.

**26. invisible-watermark (imwatermark).**
- **dwtDct decoding:**
  1. Convert BGR to YUV.
  2. Haar DWT, take the LL band.
  3. 4×4 block DCT; take the largest-magnitude non-DC coefficient.
  4. Bit = `(value mod 36) > 18`; average over the channels used.
- **Known payloads:** CompVis SD scripts embed `StableDiffusionV1`; diffusers SDXL embeds a fixed 48-bit message and
  skips images smaller than 256 px.
- **Limitations:**
  - The README says decoding is not guaranteed even without attacks.
  - It fails on resize and rotation, and on crop for the DCT variants.
  - Zhao et al. remove 91–99% of DwtDctSvd marks.
  - Absence of the payload is weak evidence, because many pipelines never embed it.
- **Activity:** last push 2023-09-23.

### 3.4 Universal (generalisable) detectors

**27. UnivFD.**
- **Method:** frozen CLIP ViT-L/14 features with a linear probe trained on ProGAN only.
- **Evaluation:** the released diffusion test set has 1k images per domain, versus the 10k used in the paper.
- **Follow-up results:** Yan et al. (arXiv 2406.19435) report 60.42% accuracy on Chameleon. De Rosa et al. (arXiv
  2407.19553) show white-box adversarial vulnerability.
- **Activity:** last push 2026-08-19.

**28. LASTED.**
- **Method:** language-guided contrastive training (CLIP ResNet-50x64) over four text labels (real/synthetic ×
  photo/painting).
- **Limitations:** a 2025 review (arXiv 2502.15176) notes that four labels may not transfer to distant domains such as
  medical or satellite imagery.
- **Venue / activity:** IEEE TAI 2025; last push 2026-03-12.

**29. SPAI.**
- **Method:** masked spectral learning on real images. Synthetic images are treated as out-of-distribution by spectral
  reconstruction similarity, at any resolution.
- **Evaluation:** 13 generators, including Flux, SD3, DALL-E 3, Midjourney v6.1 and Firefly. Claims +5.5% AUC.
- **Limitations (authors):** compression corrupts the spectral cue, and the method fails on screenshots, memes and
  printed material.
- **Requirements:** Python 3.11, CUDA 12.4; inference uses < 8 GB VRAM.

**30. PPM-CLIP.**
- **Status:** the paper exists (CVPR 2026 poster). The CVPR page says code "will be released" and gives no link. A
  repository describing itself as official exists, created 2025-11-10, with 4 commits.
- **Method:** CLIP with probabilistic prompts and LoRA.
- **Limitations:** UNKNOWN.

**31. DeeCLIP.**
- **Method:** LoRA-fine-tuned CLIP-ViT with a fusion module, trained on ProGAN.
- **Claims:** the abstract claims 89.00% average accuracy on 19 subsets, but the README reports about 79%. The figures
  disagree.
- **Venue:** acceptance at ACIVS 2025 appears only in a search snippet (UNVERIFIED).

**32. Synthbuster.**
- **Method:**
  1. Cross-difference residual `|I(x,y)+I(x+1,y+1)−I(x+1,y)−I(x,y+1)|`.
  2. FFT magnitude peaks at periods 0, 2, 4 and 8.
  3. Histogram gradient-boosting classifier.
- **Robustness (claim):** the abstract claims robustness only to "mild" JPEG.
- **Follow-up:** Mandelli et al. (arXiv 2510.05633, *Beyond Spectral Peaks*) test peak removal and argue detectors are
  not fundamentally dependent on peaks.
- **Activity:** last push 2025-09-14.

**33. CNNSpot.**
- **Method:** ResNet-50 trained on ProGAN with blur and JPEG augmentation, tested on 13 CNN generators.
- **Follow-up results:** Yan et al. report 56.94% on Chameleon. Ojha et al. argue it overfits to GAN artefacts.
- **Activity:** last push 2024-07-26.

**34. NPR.**
- **Method:** residual `x − up₂(down₂(x))` with nearest-neighbour resampling (confirmed in `networks/resnet.py`), fed
  to a CNN. Claims +11.6% across 28 generators.
- **Follow-up results:** Yan et al. report 57.81% on Chameleon. Grommelt et al. show that GenImage's JPEG and
  image-size biases inflate GenImage scores.
- **Activity:** last push 2025-05-01.

## 4. Benchmark datasets

Licences are copied from the dataset page or repository. Where two sources disagree, both are given. None of these
datasets was downloaded.

| Dataset (paper) | URL | Licence | Size (as stated) | Generators (as stated) |
|---|---|---|---|---|
| ForenSynths / CNNDetection (Wang et al., CVPR 2020) | https://github.com/PeterWang512/CNNDetection | CC-BY-NC-SA-4.0 (repo LICENSE.txt; no separate dataset licence) | UNKNOWN count/GB. Train: ProGAN + LSUN in 20 categories; test: 13 generators | Train: ProGAN. Test: ProGAN, StyleGAN, StyleGAN2, BigGAN, CycleGAN, StarGAN, GauGAN, CRN, IMLE, SITD, SAN, Deepfake, whichfaceisreal |
| GenImage (Zhu et al., NeurIPS 2023 D&B) | https://github.com/GenImage-Dataset/GenImage | custom non-commercial licence based on CC-BY-NC-SA-4.0 (GitHub: NOASSERTION) | > 1M fake/real image pairs; GB UNKNOWN | Midjourney, SD v1.4, SD v1.5, ADM, GLIDE, Wukong, VQDM, BigGAN (ImageNet classes) |
| Synthbuster (Bammey, IEEE OJSP) | https://zenodo.org/records/10066460 | CC-BY-NC-SA-4.0 (Zenodo); RAISE-1k reals under RAISE's own terms (UNKNOWN) | 9,000 synthetic images (1,000 per generator), 12.4 GB | DALL-E 2, DALL-E 3, Adobe Firefly, Midjourney v5, SD 1.3, 1.4, 2, XL, GLIDE |
| DiffusionForensics (DIRE, Wang et al., ICCV 2023) | https://github.com/ZhendongWang6/DIRE | UNKNOWN (no license file; repo archived 2025-07-08) | per paper: LSUN-Bedroom 42k/42k per ADM/DDPM/iDDPM/PNDM, 1k/1k for others; ImageNet ADM 50k/50k, SD-v1 10k/10k; GB UNKNOWN | LSUN-Bedroom: ADM, DDPM, iDDPM, PNDM, LDM, SD-v1, SD-v2, VQ-Diffusion; ImageNet: ADM, SD-v1; plus a CelebA-HQ subset (generators not listed) |
| WildFake (Hong et al., AAAI 2025) | https://github.com/hy-zpg/AIGC-Image-Detection-Dataset | UNKNOWN | 3,694,313 images (2,680,867 fake, 1,013,446 real) | hierarchical: GANs (StyleGAN, BigGAN, StarGAN, GigaGAN …), diffusion (SD, DDPM, DDIM, ADM, DALL-E, Imagen, Midjourney, VQDM), others (VQVAE, VQGAN, MaskGIT, Muse) |
| Chameleon (AIDE, Yan et al., ICLR 2025) | https://github.com/shilinyan99/AIDE | academic research only, commercial use prohibited; access by e-mail request | ~26,000 test images (11,170 AI, 14,863 real), 720p–4K | ArtStation / Civitai / Liblib images (Midjourney, DALL-E 3, SD + LoRA); reals from Unsplash |
| Community Forensics (Park & Owens, CVPR 2025) | https://huggingface.co/datasets/OwensLab/CommunityForensics | main card CC-BY-4.0 "for research purposes"; **eval card CC-BY-NC-SA-4.0**; images keep source-model licences (mostly CreativeML OpenRAIL-M) | 2,760,270 images, 1.08 TB (small version 278 GB; eval 206 GB) | 4,803 generator models (mostly community diffusion models); reals from LAION, ImageNet, COCO, FFHQ and others |
| DRCT-2M (Chen et al., ICML 2024) | https://modelscope.cn/datasets/BokingChen/DRCT-2M | UNKNOWN (code repo has no license file; ModelScope page did not load) | "million-scale"; exact count UNKNOWN | 16 diffusion models (abstract); the breakdown (10 SD variants, 3 ControlNet, 3 inpainting) comes only from a search snippet and is unverified |
| UniversalFakeDetect diffusion test set (Ojha et al., CVPR 2023) | https://github.com/WisconsinAIVision/UniversalFakeDetect | code MIT; dataset licence UNKNOWN | 1k fake + 1k real per domain (paper used 10k) | LDM, GLIDE, Guided/ADM, DALL-E mini |
| ArtiFact (Rahman et al., ICIP 2023) | https://github.com/awsaf49/artifact | mixed, inherited from sources (CC-BY-NC-SA, CC-BY-NC, MIT, Apache-2.0, BSD, non-commercial) | 2,496,738 images (964,989 real, 1,531,749 fake) | 25 methods: 13 GANs, 7 diffusion, 5 other (e.g. GLIDE, MAT, LaMa) |
| ImagiNet (Boychev & Cholakov, arXiv 2407.20020) | https://huggingface.co/datasets/delyanboychev/imaginet | mixed: source licences for reals; CC-BY-4.0 for SD/SDXL/Animagine/StyleGAN outputs; CC0 for a DALL-E 3 folder; JourneyDB licence for Midjourney | 200,000 images, 144 GB (gated) | SD v2.1, SDXL, Animagine XL, StyleGAN3, StyleGAN-XL, DALL-E 3, Midjourney |
| OpenFake (arXiv 2509.09495) | https://huggingface.co/datasets/ComplexDataLab/OpenFake | CC-BY-NC-4.0 (current card) | paper: ~3M real + ~1M synthetic; card: 2.45M images in the core subset | 75 models on the card, incl. SD 1.5/2.1/3.5, SDXL, Flux variants, Imagen 4.0; reals from LAION and Pexels |

**Known dataset biases.** Grommelt et al. (*Fake or JPEG?*, arXiv 2403.17608) show that GenImage has JPEG-format and
image-size biases that detectors learn. Ricker et al. suspect a similar storage bias in DIRE's DiffusionForensics
maps. Benchmarks used by SynthProvenance should therefore control for format, compression and size.

## 5. 2025–2026 additions

These were selected from a search of CVPR 2025/2026, ICLR 2025, ICML 2025, NeurIPS 2025, IEEE S&P 2025 and arXiv
2025–2026. Training-free and signal-processing methods were preferred. **No 2025–2026 method was found that is
NUMPY-REIMPLEMENTABLE as published.** "Training-free" methods (WaRPAD, Manifold Induced Biases, and the 2026
efficient zero-shot detector) still need a large pretrained foundation or diffusion model.

### 5.1 Selected (rows 35–44)

**35. B-Free.**
- **Method:** DINOv2-with-registers ViT trained on COCO reals plus content-aligned SD 2.1 fakes, to remove format and
  content bias.
- **Evaluation:** 27 generators, including FLUX, SD 3.5 and DALL-E 3, plus a set of "viral" web-laundered images. A
  new-generator set was released 2026-01-14.
- **Limitations:** the authors expect it to fail on generators with "a completely different synthesis process", and
  adversarial robustness is untested.
- **Licence:** the code licence is non-commercial.

**36. CO-SPY.**
- **Method:** fuses a CLIP-style semantic branch with a pixel-artefact branch.
- **Benchmark:** CO-SPY-Bench covers 22 generators including FLUX, 5 real sources, and ~50k in-the-wild images.
  Claims +11–34% average accuracy.
- **Activity:** last push 2026-05-04.

**37. AIDE + Chameleon.**
- **Method:** DCT patch selection with low-level CNN experts and CLIP semantics.
- **Finding:** the authors' own finding is that on Chameleon "almost all models classify AI-generated images as real
  ones".
- **Activity:** last push 2025-06-04.

**38. Community Forensics.**
- **Method:** a ViT trained on images from 4,803 generators. The released model has 21.8M parameters and is under
  MIT.
- **Limitations:** the dataset card warns of "far too high error rates to be used directly in the wild" and of the
  risk of "falsely accusing an author".
- **Plug-in note:** its small size and MIT licence make it the most licence-friendly detector for an optional ONNX
  plug-in.

**39. WaRPAD.**
- **Method:** training-free. The score is how sensitive a DINOv2 embedding is to Haar high-frequency perturbations,
  across rescaled patches.
- **Evaluation:** Synthbuster, GenImage and LSUN-Bedroom generators (23 in total).
- **Limitations (authors):** depends on the backbone, may not generalise to high-resolution images, and needs extra
  compute.

**40. Manifold Induced Biases.**
- **Method:** zero-shot score built from the curvature and gradient of a diffusion model's score function, using 64
  spherical perturbations per image through SD v1.4. Tested on 20 generators.
- **Limitations (authors):** cross-model generalisation is empirical, and compute is heavy.

**41. Forensic Self-Descriptions (FSD).**
- **Method:**
  - Eight 11×11 linear predictive filters are learned on real images only.
  - Each image is described by multi-scale linear residual-model parameters.
  - Gaussian mixture models then perform zero-shot detection, open-set attribution and clustering.
  - Tested on 24 generators.
- **Code:** none found.
- **Relevance:** the closest 2025 work to a numpy pipeline, since inference uses no deep network. A faithful version
  still needs filters and GMMs fit on a large, diverse real-image corpus. The authors name this dependence as their
  main limitation.

**42. VINE + W-Bench.**
- **Benchmark:** W-Bench tests 11 watermarks plus VINE against regeneration, global and local generative editing, and
  image-to-video. It has 10,000 samples, released on Hugging Face 2025-03-02.
- **Licence:** the LICENSE file is the NTU non-commercial agreement, contradicting an automated page summary that
  said MIT.

**43. UnMarker.**
- **Method:** a universal, detector-free watermark removal attack that disrupts spectral amplitudes.
- **Results (claims):** reports attacks on StegaStamp, Stable Signature, Tree-Ring, Gaussian Shading, VINE and
  Google SynthID.
- **README caveat:** Google has since restricted SDK access to the SynthID verifier, so automated reproduction may no
  longer work.
- **Implication:** "no watermark found" after editing is not evidence of origin.

**44. SynthID-Image.**
- **Paper:** describes deployment on more than 10 billion images and frames.
- **Status:** no code, weights or detector are released. Verification is for trusted testers, and SynthID-O is
  offered through partnerships. This confirms that local SynthID detection is UNAVAILABLE (see
  `docs/SYNTHID_RESEARCH_SOURCES.md`).

### 5.2 Also checked (lower priority; in `also_checked_2025_2026`, not counted)

| Method | Repo / licence | Verdict | Note |
|---|---|---|---|
| Effort (ICML 2025 Oral) | [YZY-stack/Effort-AIGI-Detection](https://github.com/YZY-stack/Effort-AIGI-Detection); no license file (README badge says CC-BY-NC-4.0) | REQUIRES-DL-RUNTIME | SVD-based adaptation of CLIP ViT-L/14 |
| Watermark Anything (ICLR 2025) | [facebookresearch/watermark-anything](https://github.com/facebookresearch/watermark-anything); MIT code, archived; `wam_mit.pth` weights MIT, `wam_coco.pth` CC-BY-NC | REQUIRES-DL-RUNTIME | localised 32-bit messages; most permissive modern neural watermark |
| Aligned Datasets / AlignedForensics (ICLR 2025) | [AniSundar18/AlignedForensics](https://github.com/AniSundar18/AlignedForensics); no license file | REQUIRES-DL-RUNTIME | ResNet-50 trained on reals and their LDM-autoencoder reconstructions |
| ZED (ECCV 2024) | [grip-unina/ZED](https://github.com/grip-unina/ZED); GRIP-UNINA non-commercial; code "Coming Soon" | REQUIRES-DL-RUNTIME | learned lossless-coder surprisal, trained on real images only |
| Efficient Zero-Shot AIGI Detection (arXiv 2603.21619, 2026) | no code found | REQUIRES-DL-RUNTIME (inferred from abstract only) | Fourier-perturbation sensitivity of an unnamed representation model; claims ~10% AUC gain on OpenFake |

## 6. Local-execution status

**None of the methods, repositories, weights or datasets in this survey were downloaded, installed or executed.** No
accuracy figure in this document was reproduced by SynthProvenance. Every entry in `implementations.json` carries
`"executed_in_survey": false`.

What SynthProvenance actually ran is recorded separately, by the app's own validation step: the method registry,
benchmark runs and audit logs. That record is authoritative for "was this run and what did it produce"; this survey
is not. An ADAPTED numpy method built from an idea below is a new implementation. It must be validated by the app's
own benchmark protocol before any result is reported, and it inherits none of the original paper's claimed accuracy.

## 7. Implications for SynthProvenance

**None of these methods detects SynthID.** SynthID-Image has no public detector (see
`docs/SYNTHID_RESEARCH_SOURCES.md`). A generic "AI-generated" or spectral signal on an image is not evidence of a
SynthID watermark, and the app must never phrase it that way.

### 7.1 Ideas suitable for local ADAPTED numpy re-implementation

These need only numpy/Pillow. Each must be labelled **ADAPTED**: it reproduces the published *feature*, not the
published *detector*, and is unvalidated until the app's benchmark has run it.

| Idea | Source method(s) | What can be faithful | What is adapted / missing |
|---|---|---|---|
| Residual fingerprint and correlation attribution | Marra 2019 | residual averaging, normalised correlation | denoiser choice (unnamed in the paper); needs researcher-supplied reference images per generator (closed set) |
| DCT log-spectrum features | Frank 2020 | 2-D DCT and log scaling; a closed-form ridge regression in numpy | decision layer fit on local labelled data; the CNN variants are dropped |
| Azimuthal (reduced) power spectrum | Durall 2020; Schwarz 2021 (measurement only) | FFT, azimuthal integration, DC normalisation | logistic regression or threshold fit locally |
| Benford statistics on block-DCT coefficients | Bonettini 2021 | block DCT, quantisation, first-digit histograms, JS/Rényi/Tsallis divergences | Random Forest replaced by a numpy classifier or threshold |
| Cross-difference residual FFT peaks | Synthbuster | residual filter, FFT peak features | gradient-boosting classifier replaced and refit; the shipped pickles have no licence |
| Up-sampling residual statistic | NPR | `x − up₂(down₂(x))` map and its statistics | the learned CNN decision is unavailable, so this is a descriptive statistic only |
| DwtDct / DwtDctSvd payload decoding | invisible-watermark | Haar DWT, block DCT/SVD and quantisation, with known SD v1 / SDXL payloads | YUV and Haar are hand-written; bit-exact agreement with cv2/pywt must be tested |
| Classical distortion stress tests | WAVES (8 distortions), Zhao (classical baselines) | rotation, crop, erase, brightness, contrast, blur, noise, JPEG; TPR at low FPR reporting | regeneration and adversarial attacks are excluded |
| Real-image-only predictive-residual self-description (candidate) | Forensic Self-Descriptions (verdict: REQUIRES-TRAINING-DATA) | linear predictive filters, least-squares residual models and a GMM are all numpy-feasible | no code; filters and GMM must be fit on a large, diverse local real-image corpus, so it is EXPERIMENTAL until such a corpus exists |
| Haar high-frequency perturbation (component only) | WaRPAD | the Haar perturbation step | the DINOv2 embedding that gives the score is unavailable; do not present as WaRPAD |

**Code licensing.** Durall's detector repository, Synthbuster and NPR have **no licence file**, so their code must
not be copied. Re-implement from the paper's description instead. Frank (MIT) and invisible-watermark (MIT) may be
consulted and adapted with attribution. UpConv is GPL-3.0, so do not copy it into a non-GPL build.

### 7.2 UNAVAILABLE without a deep-learning runtime

These should appear in the registry as **UNAVAILABLE**, with the reason "requires DL runtime and weights" or
"requires unreleased model or training data":

- **Needs a DL runtime + released weights:** Yu 2019, DIRE, AEROBLADE, multiLID (withdrawn), Causal Fingerprints (no
  code), Stable Signature, StegaStamp, Zhao regeneration, TrustMark, UnivFD, LASTED, SPAI, PPM-CLIP, DeeCLIP, CNNSpot,
  the NPR classifier, and the RivaGAN mode of invisible-watermark. From 2025–2026: B-Free, CO-SPY, AIDE, Community
  Forensics, WaRPAD, Manifold Induced Biases and VINE.
- **Needs unreleased models or training:** DNA-Det, GFD-Net, Liu 2024, ManiFPT, HiDDeN, Forensic Self-Descriptions.
- **Not applicable to third-party images:**
  - Need the owner's key or a training-time watermark: Yu 2021, ProMark, Tree-Ring, Gaussian Shading, RingID.
  - Not a detector: Schwarz 2021 (analysis), UnMarker (attack).
  - Nothing released: SynthID-Image.

If a DL runtime is ever added as an optional plug-in, these are the most relevant candidates:

- **TrustMark (watermark decoding):** keyless, MIT for code and weights, with an ONNX path.
- **Detection:** Community Forensics (MIT, 21.8M parameters) and SPAI (Apache-2.0 code and weights).

Licence restrictions remain:

- CC-BY-NC-SA: CNNSpot
- CC-BY-NC: Stable Signature
- Non-commercial: Yu 2019 and 2021, B-Free, VINE, UnMarker
- No licence file (not redistributable): DIRE, AEROBLADE, NPR, DeeCLIP, PPM-CLIP, WaRPAD, Manifold Induced Biases

### 7.3 Datasets

Most benchmark datasets are non-commercial (CC-BY-NC-SA or custom), on request only, or of unknown licence. The app
should not bundle any of them. It should accept researcher-supplied local folders and record each dataset's name,
version and licence in the experiment record.

### 7.4 Reporting language

- Detectors trained on GANs drop to about 57–60% accuracy on modern in-the-wild images. Yan et al. report this on
  Chameleon for CNNSpot, UnivFD and NPR.
- Spectral cues are removed by compression and by generators designed against them (Durall, Frank, SPAI
  limitations).
- Fingerprints can be removed by attack (Smudged Fingerprints, SaTML 2026).
- Watermarks, reportedly including SynthID, can be removed (UnMarker, S&P 2025; Zhao et al., NeurIPS 2024). Absence
  of a watermark or fingerprint is therefore never evidence that an image is authentic.
- Even the largest 2025 training effort (Community Forensics, 4,803 generators) warns its classifiers have "far too
  high error rates to be used directly in the wild".

ADAPTED signals should therefore be reported as research measurements with stated uncertainty, never as verdicts
about an image's origin.
