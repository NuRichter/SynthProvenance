# SynthProvenance — Bagaimana Proses Bekerja (Dokumen Brainstorming)

> Dokumen ini menjelaskan **seluruh alur** SynthProvenance v2.1.0 untuk tiap skenario, agar bisa dipakai
> brainstorming (mis. dengan ChatGPT) tanpa perlu membuka kode. Istilah teknis & nama metode sengaja
> dibiarkan dalam Bahasa Inggris (istilah kanonik), seperti di dalam aplikasi.
>
> Motto proyek: **WE DO NOT GUESS. WE MEASURE. — PRESERVE THE PIXEL. STUDY THE FINGERPRINT.**

---

## Daftar Isi

1. [Identitas & filosofi](#1-identitas--filosofi)
2. [Prinsip kunci (yang membentuk semua alur)](#2-prinsip-kunci-yang-membentuk-semua-alur)
3. [Peta arsitektur & aliran data](#3-peta-arsitektur--aliran-data)
4. [Taksonomi → representasi → eksperimen (jembatan)](#4-taksonomi--representasi--eksperimen-jembatan)
5. [Skenario A — Startup aplikasi (splash → dashboard)](#5-skenario-a--startup-aplikasi)
6. [Skenario B — Buka gambar & baseline forensik](#6-skenario-b--buka-gambar--baseline-forensik)
7. [Skenario C — Mulai eksperimen (experiment workspace)](#7-skenario-c--mulai-eksperimen)
8. [Skenario D — C2PA Provenance](#8-skenario-d--c2pa-provenance)
9. [Skenario E — SynthID Research Lab (lokal & online)](#9-skenario-e--synthid-research-lab)
10. [Skenario F — Fingerprint Research Lab (modul unggulan)](#10-skenario-f--fingerprint-research-lab)
11. [Skenario G — Surrogate ground truth (embed → detect → GT)](#11-skenario-g--surrogate-ground-truth)
12. [Skenario H — Separation & Reconstruction (6 panel)](#12-skenario-h--separation--reconstruction)
13. [Skenario I — Robustness sweep](#13-skenario-i--robustness-sweep)
14. [Skenario J — Hypothesis Lab & Frontier methods](#14-skenario-j--hypothesis-lab--frontier-methods)
15. [Skenario K — Unified Signal Decomposition Engine](#15-skenario-k--unified-signal-decomposition-engine)
16. [Skenario L — Method Composer (pipeline)](#16-skenario-l--method-composer)
17. [Skenario M — Research Assistant & Experiment Discovery](#17-skenario-m--research-assistant--experiment-discovery)
18. [Skenario N — Fingerprint Taxonomy browser](#18-skenario-n--fingerprint-taxonomy-browser)
19. [Skenario O — Research Library & HERE OUR HERO](#19-skenario-o--research-library--here-our-hero)
20. [Skenario P — About, ISO-5807 workflow, ISO 25010](#20-skenario-p--about-iso-5807-workflow-iso-25010)
21. [Skenario Q — Easy Mode (PILIH → RUN → OUTPUT) vs Expert Mode](#21-skenario-q--easy-mode-pilih--run--output-vs-expert-mode)
22. [Skenario R — Research Wizard (7 langkah)](#22-skenario-r--research-wizard-7-langkah)
23. [Skenario S — Transformation/Format/Sanitization & Pixel Integrity](#23-skenario-s--transformationformatsanitization--pixel-integrity)
24. [Skenario T — Paper Export & reprodusibilitas](#24-skenario-t--paper-export--reprodusibilitas)
25. [Skenario U — i18n (30 bahasa)](#25-skenario-u--i18n-30-bahasa)
26. [Skenario V — Keamanan & LOCAL-ONLY](#26-skenario-v--keamanan--local-only)
27. [Skenario W — Build → Test → EXE → Verify](#27-skenario-w--build--test--exe--verify)
28. [Format ID & artefak yang dihasilkan](#28-format-id--artefak-yang-dihasilkan)
29. [Status metode (apa yang benar-benar jalan)](#29-status-metode-apa-yang-benar-benar-jalan)
30. [Batasan & etika (apa yang TIDAK dilakukan)](#30-batasan--etika-apa-yang-tidak-dilakukan)
31. [Pertanyaan untuk brainstorming](#31-pertanyaan-untuk-brainstorming)

---

## 1. Identitas & filosofi

- **Nama:** SynthProvenance — *Scientific AI Content Signal & Image Provenance Laboratory*.
- **Jenis:** aplikasi desktop Windows, **local-first**, PySide6 + numpy + Pillow (TIDAK ada PyTorch di build rilis).
- **Lingkungan:** Insyide Innovations Lab · NuRichter Workspace. Versi saat ini **2.1.0**.
- **Pertanyaan riset utama:** *"Fingerprint/trace/signature/watermark apa yang teramati pada citra generatif, di
  representasi mana ia hidup, seberapa persisten, dan dapatkah ia dipisahkan dari konten visual di lingkungan
  ground-truth terkendali sambil menjaga fidelitas secara kuantitatif?"*
- **Pembedaan kategori (tidak boleh dicampur):** intrinsic fingerprint ≠ causal fingerprint ≠ spectral cue ≠
  proactive watermark ≠ detector representation ≠ reconstruction cue ≠ C2PA provenance.

---

## 2. Prinsip kunci (yang membentuk semua alur)

Setiap skenario di bawah tunduk pada aturan ini (inilah yang membuat alurnya seperti itu):

1. **Original tidak pernah diubah.** Semua operasi berjalan di atas salinan. File asli di-hash (SHA-256) sebelum &
   sesudah, dan dilaporkan `original_unchanged`.
2. **Measure, jangan tebak.** Setiap klaim = pengukuran. Tidak ada verdict "AI vs manusia".
3. **Ground truth untuk separation.** Klaim pemisahan/rekonstruksi/robustness hanya dibuat terhadap **surrogate
   terkendali berkunci** yang sinyalnya diketahui.
4. **Status jujur.** Metode berstatus `READY` / `UNAVAILABLE` (butuh runtime DL+bobot, tidak di-bundle) /
   `NOT_IMPLEMENTED` (sengaja di luar scope, mis. detector-evasion). Tidak ada tombol palsu.
5. **Kapabilitas eksplisit.** Tiap metode mendeklarasikan `CAN_ANALYZE / CAN_ESTIMATE / CAN_SEPARATE /
   CAN_RECONSTRUCT / CAN_VALIDATE`. Detektor tidak pernah dipakai diam-diam sebagai separator.
6. **LOCAL-ONLY.** Audit hook CPython memblokir koneksi keluar. Tidak ada telemetry/upload/cloud/unduh model diam-diam.
   Verifikasi online SynthID = hand-off eksplisit ke browser dengan konfirmasi.
7. **Reprodusibel.** Tiap run punya ID + catatan lengkap (parameter, seed, environment, hash, runtime, metrik).
8. **Kegagalan didokumentasikan, bukan disembunyikan.** Setiap run punya failure analysis berbasis aturan.

---

## 3. Peta arsitektur & aliran data

```
                         ┌─────────────────────────────────────────────┐
                         │                 app/ui (PySide6)             │
                         │  EXPERT: MainWindow · 16 views · wizard      │
                         │  EASY:   EasyWindow (01 PILIH·02 RUN·03 OUTPUT)│
                         │  splash · Settings (bahasa, APPLICATION MODE)│
                         └───────────────┬─────────────────────────────┘
                                         │ sinyal Qt (busy, progress, *Changed)
                         ┌───────────────▼─────────────────────────────┐
                         │          app/ui/controller.AppController     │
                         │  orkestrasi job di QThreadPool (1 op/eksperimen) │
                         └───┬───────────────┬───────────────┬──────────┘
                             │               │               │
             ┌───────────────▼──┐   ┌────────▼─────────┐  ┌──▼───────────────────┐
             │ app/core         │   │ app/core (lab)   │  │ app/research (numpy) │
             │ loading, hashing │   │ fingerprint_lab  │  │ taxonomy, library,   │
             │ metadata, C2PA,  │   │ unified_signal_  │  │ spectral, wavelet,   │
             │ experiment,      │   │ decomposition,   │  │ dct, residuals, rpca,│
             │ pixel_integrity, │   │ method_composer, │  │ consensus, features, │
             │ synthid_*        │   │ research_asst.   │  │ surrogate, frontier, │
             └──────────────────┘   └──────────────────┘  │ hypotheses, methods, │
                             │               │            │ runner, metrics,...  │
                             │               │            └──────────────────────┘
                             ▼               ▼
                    <workspace>/experiments/…   <workspace>/fingerprint_research/…
                    <workspace>/synthid_research/…   <workspace>/exports/…
```

- **app/research/** = mesin numerik murni (tanpa Qt, tanpa file, tanpa jaringan) — mudah diuji.
- **app/core/fingerprint_lab.py** = "run store" yang membungkus mesin menjadi run yang terjejak & reprodusibel.
- **Data bundel:** `data/fingerprint_taxonomy.json` (572 entri), `data/research_library.json` (66 referensi
  terverifikasi), `data/research_catalog.json` (metode/dataset/tools), `app/i18n/locales/*.json` (30 bahasa).

---

## 4. Taksonomi → representasi → eksperimen (jembatan)

Alur konseptual yang memetakan tiap keluarga taksonomi ke apa yang benar-benar bisa dilakukan software:

```
RESEARCH TAXONOMY → REPRESENTATION → OBSERVABLE SIGNAL → ANALYSIS → ESTIMATION → SEPARATION → RECONSTRUCTION → VALIDATION
```

| Keluarga taksonomi | Modul engine | Metode / status |
|---|---|---|
| A Intrinsic/passive | residuals, consensus, features, rpca | 03–05, 12, 17, 19–25 |
| B Causal | hypotheses, frontier(null-space) | 31–33 UNAVAILABLE; 47, 57 di data terkendali |
| C Spectral | spectral, dct, wavelet | 11, 13–18 |
| D Proactive watermark | surrogate, robustness, separation | 34–42, 63 (surrogate GT) |
| E Detector representation | features | 26–29 UNAVAILABLE; 30 handcrafted |
| F Reconstruction | frontier(reconstruction) | 09–10 UNAVAILABLE; 55 self-supervised |
| G C2PA provenance | app/core (native) | 01–02 |

Rinciannya dibangkitkan otomatis ke `docs/IMPLEMENTATION_GAP_ANALYSIS.md`.

---

## 5. Skenario A — Startup aplikasi

```
Jalankan EXE
  → netguard.install()            (pasang audit hook LOCAL-ONLY)
  → set bahasa dari Settings       (i18n.set_active)
  → Splash tampil (non-blocking) dan menjalankan urutan init NYATA:
        Loading image engine        → decode PNG mini
        Loading C2PA engine          → import parser JUMBF/CBOR
        Loading fingerprint taxonomy → hitung jumlah entri (572)
        Loading research library     → hitung referensi (66)
        Loading local research modules → 48/64 metode ready
        Checking GPU                 → nvidia-smi (hanya untuk catatan)
        Checking external tools      → ExifTool/c2patool/c2pa-python (opsional)
        Checking experiment workspace→ path workspace
  → baca Settings.ui_mode (EASY default; --ui-mode easy|expert hanya untuk sesi itu)
       EASY   → tema terang Easy + EasyWindow (shell aplikasi terpisah, 3 langkah)
       EXPERT → tema gelap konsol riset + MainWindow (16 view)
  → window.show() → splash.finish(win)
```
Catatan: progres **tidak dipalsukan** — tiap langkah cek beneran dan menampilkan hasil (✓/✕ + durasi ms).

---

## 6. Skenario B — Buka gambar & baseline forensik

```
File > Open Image  (atau drag-drop, atau Open Demo Fixture)
  → controller.open_image(path)  → job latar (QThreadPool)
       read_file_bytes()          (validasi, budget memori, anti decompression-bomb)
       analyze_file()             (EXIF/XMP/IPTC/ICC/PNG-text + C2PA + optional c2patool)
       hitung hash file + pixel hash
  → SourceContext tersimpan; audit: IMAGE LOADED
  → semua view me-refresh (lazy, saat terlihat)
```
Baseline forensik yang direkam: resolusi, channel, bit depth, format, statistik deskriptif (entropi, noise, dsb.),
state C2PA, state metadata per grup. **Semua deskriptif** — bukan deteksi AI.

---

## 7. Skenario C — Mulai eksperimen

```
Tombol START EXPERIMENT
  → workspace.create(nama, bytes, baseline)
       alokasi ID  SPX-YYYY-MMDD-NNNNNN
       salin original byte-for-byte ke experiments/<ID>/original/
  → analisis SynthID baseline (engine lokal → biasanya UNAVAILABLE)
  → hitung statistik; simpan experiment.json
  → audit: EXPERIMENT STARTED, BASELINE COMPLETE, C2PA COMPLETE, SYNTHID COMPLETE, METADATA COMPLETE, STATISTICS COMPLETE
```
Mulai titik ini, semua transformasi/run beroperasi pada salinan di dalam folder eksperimen.

---

## 8. Skenario D — C2PA Provenance

```
View "C2PA Provenance"
  → tampilkan manifest, claims, assertions, actions, ingredients,
     claim generator, algoritma tanda tangan, issuer/subject sertifikat, timestamp,
     HARD BINDING (digest dihitung ulang) dan VALIDITAS
  → Validitas = NOT VALIDATED / trust UNKNOWN  KECUALI c2patool / c2pa-python ada
  → Ekspor manifest sebagai JSON
  → "C2PA SEPARATION EXPERIMENT": hapus hanya kontainer manifest store
       (PIXEL-EXACT; metadata/pixel dibandingkan sebelum/sesudah)
```
Pesan kunci di UI: **C2PA = signed metadata, BUKAN intrinsic fingerprint.**

---

## 9. Skenario E — SynthID Research Lab

Dua jalur, dengan 7 tab (Detection, Local Methods, Research Sources, Benchmark, Comparison, Online Verification,
Experiments).

**Jalur LOKAL (default):**
```
RUN LOCAL DETECTION
  → research_image() = salinan original
  → hash sebelum → verifier.verify() (engine kontrak SID-M1) → hash sesudah
  → Tanpa engine valid: state = UNAVAILABLE  → tampil "LOCAL SYNTHID ENGINE: UNAVAILABLE"
  → run disimpan: SPX-SID-YYYYMMDD-NNNNNN, original_unchanged dicatat
```

**Jalur ONLINE (OFF default, consent-gated):**
```
Toggle ONLINE OFFICIAL VERIFICATION → dialog konfirmasi (mode quiet TIDAK pernah auto-confirm)
  → pilih destinasi resmi Google (mis. Gemini app) → tampil rencana (URL, nama file, SHA-256)
  → konfirmasi → OS membuka BROWSER (SynthProvenance TIDAK meng-upload apa pun)
  → peneliti upload manual di browser, lalu merekam hasil sebagai EXTERNAL (user-recorded, unverified)
```
Benchmark: AUC (bootstrap CI), ROC, TPR/FPR/precision/recall/F1 (Wilson CI) di atas data berlabel peneliti sendiri.

---

## 10. Skenario F — Fingerprint Research Lab (modul unggulan)

View dengan tab: **Analysis · Separation & Reconstruction · Surrogate Ground Truth · Robustness · Hypothesis Lab ·
Method Composer · Research Assistant · Methods · Experiments** (tab "expert" disembunyikan di Easy Mode).

Alur umum menjalankan 1 metode:
```
Pilih metode (dropdown, dengan Method Card "Why this method?")
  → RUN METHOD  → controller.run_fingerprint_method(method_id, surrogate?)
       lab.run_method():
          alokasi SPX-FP-YYYYMMDD-NNNNNN
          salin input ke inputs/ (hash sebelum)
          build MethodInput (image float, pil utk tabel JPEG, refs, surrogate cfg, clean)
          runner.run(method, input)  → MethodResult (readouts, data, maps, ground_truth, failure_analysis)
          tulis maps/*.png, config/, logs/run.log
          hash sesudah → original_unchanged
          save run.json
  → UI tampilkan: Result Card ("WHAT DID WE FIND?"), readouts, peta output, failure analysis
```
Tiap `MethodResult` berisi: status (COMPLETE/SIGNAL PERSISTED/UNAVAILABLE/NOT IMPLEMENTED/INSUFFICIENT DATA/FAILED),
`readouts` (skalar untuk UI), `maps` (plane float → PNG), `ground_truth`, `reconstruction`, `metrics`,
`failure_analysis`.

---

## 11. Skenario G — Surrogate ground truth

Inti dari semua riset watermark (bukan SynthID, tidak meniru internal SynthID).

```
CLEAN IMAGE
   → SURROGATE EMBEDDER (berkunci: family, strength[RMS 8-bit], key)
        family: spatial | pseudo_random | fft | dct | wavelet | multi_scale | learned | multi_bit | hybrid
        (family "neural" = UNAVAILABLE, tidak disimulasikan)
   → WATERMARKED IMAGE  (ditulis sebagai file BARU; original tak tersentuh)
   → LOCAL DETECTOR (blind, hanya butuh key) → z-score + p-value; multi_bit → bit accuracy
   → GROUND TRUTH: sinyal diketahui (luminance) + residu diketahui (8-bit) + skor detektor
```
Properti yang diuji (lihat tes): detektor **mengenali sinyalnya sendiri**, **menolak gambar clean**, **menolak key
salah**; distribusi null terkalibrasi (mean≈0, sd≈1, tak ada false positive di 200 key acak pada threshold).

---

## 12. Skenario H — Separation & Reconstruction

```
Surrogate case (clean + watermarked) → pilih metode separasi (Method 34–38, 41, 42)
   content_estimate + candidate_signal + residual  (I = content + signal + residual)
   6 PANEL: Original · Candidate Signal · Estimated Content · Residual · Reconstructed · Difference
   SKOR vs GROUND TRUTH:
       candidate_vs_known_corr   (korelasi sinyal terpulihkan vs sinyal diketahui)
       recovered_energy_fraction
       signal_reduction
       recon PSNR / SSIM  (LPIPS = UNAVAILABLE, tidak diestimasi)
```
Metode: highpass, wavelet (BayesShrink), fft (atenuasi bin anomali), robust_pca (`I=L+S+E`), self_prior (guided
filter). Status bisa `SIGNAL PERSISTED` (sinyal masih terdeteksi) — itu hasil ilmiah yang sah, bukan kegagalan.

---

## 13. Skenario I — Robustness sweep

```
Surrogate watermarked copy → battery transformasi standar (severity bertingkat):
   PNG, JPEG(q), WebP(q), resize, crop, rotate, brightness, contrast, gamma, blur, sharpen, noise, color
Untuk tiap transformasi:
   persistence = z_detektor(sesudah) / z_detektor(sebelum)
   + PSNR/SSIM (biaya fidelitas)
```
Ini **karakterisasi persistensi** (gaya WAVES), **BUKAN** pencarian transformasi yang mengalahkan detektor.

---

## 14. Skenario J — Hypothesis Lab & Frontier methods

```
Pilih hipotesis (Method 47–52) / frontier (Method 55–63) → jalankan di DATA TERKENDALI
   Verdict: SUPPORTED / INCONCLUSIVE / NOT SUPPORTED  "ON THIS CONTROLLED CASE"  (tak pernah "terbukti")
   + failure_modes + catatan "satu hasil positif bukan bukti; replikasi"
```
Frontier (Section 23): Multi-Representation Residual Consensus, Fingerprint Null-Space, Cross-Scale Topological
Residual, Spectral-Semantic Fusion, Iterative Reconstruction Consensus, Method Disagreement, Fingerprint Stability
Field, Provenance Energy Landscape, + Reconstruction Forensics self-supervised (bukan diffusion/AE).

---

## 15. Skenario K — Unified Signal Decomposition Engine

Antarmuka tunggal 5 kata kerja dengan **capability guard**:
```
analyze(image, method)                         → statistik deskriptif
estimate(image, method)                         → candidate signal + confidence_map
separate(image, method, surrogate, clean)       → content + signal + residual (+skor GT)
reconstruct(image, method, surrogate, clean)    → content estimate / error map
validate(image, method, surrogate, clean)       → skor terhadap ground truth
```
Guard: `separate()`/`reconstruct()` **menolak** metode yang flag kapabilitasnya tak mengizinkan (detektor tak bisa
jadi separator). Objek umum `Decomposition{observed, content_estimate, signal_estimate, residual, confidence_map}`.

---

## 16. Skenario L — Method Composer

```
Susun pipeline node: {op, enabled, params}   (preset atau tambah/stop node)
   op contoh: luminance, residual_highpass, wavelet_detail, fft_crossdiff, dct_highpass,
              pca_sparse, normalize, patch_consensus, reconstruct
RUN PIPELINE (opsional surrogate GT):
   jalankan tiap stage berurutan pada plane; rekam energy, std, candidate_vs_known_corr per stage
   ground_truth: final_candidate_vs_known_corr, best_stage
Export pipeline → JSON; reproduce dari JSON → hasil identik (deterministik)
```
Contoh rantai: `Residual → Wavelet → Robust-PCA → Reconstruct`.

---

## 17. Skenario M — Research Assistant & Experiment Discovery

```
Pilih Research Goal → assistant.advise(goal, image_info, has_gt, n_refs):
   rationale + rekomendasi metode (dengan alasan, data yang diperlukan, biaya, kontrol)
   + catatan (mis. "butuh surrogate untuk ground truth", "butuh ≥3 reference images",
              "input bukan JPEG → fitur JPEG analitik saja", "resolusi besar → tiling")
DISCOVER EXPERIMENTS → ranking kandidat pipeline berdasar nilai ilmiah vs biaya/GT/hardware,
   tiap kandidat: reason, required_dataset, expected_cost, validation_plan
```
Assistant **tidak pernah mengeksekusi** apa pun secara otomatis; hanya merekomendasikan + menjelaskan WHY.

Research goals: Understand Provenance · Find Fingerprint · Study Diffusion Trace · Study Spectral Trace ·
Study Watermark · Compare Images · Run Controlled Experiment.

---

## 18. Skenario N — Fingerprint Taxonomy browser

```
View "Fingerprint Taxonomy"  (dari data/fingerprint_taxonomy.json)
   Readout: 572 entri · 21 referensi APA · 7 keluarga
   Separation rules ditampilkan: C2PA≠intrinsic, Metadata≠SynthID, SynthID≠generic detector,
                                  Detector feature≠intrinsic, No signal≠human-created
   Filter: teks + keluarga → tabel (ID, Term, Category, Subcategory, Domain, Representation, Status, Line)
   Klik entri → definisi (DIKUTIP dari sumber), methods, papers, derived_fields, source_line
```
Definisi **dikutip** dari file sumber (tidak ditulis ulang). `domain`/`representation` diturunkan dari sub-bagian dan
ditandai di `derived_fields`.

---

## 19. Skenario O — Research Library & HERE OUR HERO

```
View "Research Library" (5 tab, kind dipisah):
   Terminology (572) · Methods (44 survei implementasi) · Papers (66 verified) · Tools (4) · Datasets (12)
Papers = dinding "RESEARCH FOUNDATIONS":
   filter kategori/generator/local/origin + search
   AKSI per paper: COPY APA · COPY BIBTEX · OPEN PAPER · OPEN SOURCE
   Export seleksi → APA 7 / BibTeX / CITATION.cff
```
Tiap paper membawa `verification_status` (VERIFIED / VERIFIED_WITH_CORRECTIONS) + catatan koreksi. Jumlah paper
**tidak** digelembungkan agar sama dengan jumlah istilah. Tidak ada sitasi/DOI fiktif.

---

## 20. Skenario P — About, ISO-5807 workflow, ISO 25010

```
View "About This Program" (4 panel):
   ABOUT                → apa itu, filosofi, scope, local processing, reprodusibilitas
   HERE OUR HERO        → RESEARCH FOUNDATIONS (tabel referensi) → buka Research Library
   ISO-5807 WORKFLOW    → flowchart notasi ISO 5807 (terminator/proses/keputusan/predefined)
   SOFTWARE QUALITY     → pemetaan ISO/IEC 25010:2023 (8 karakteristik)
```
Teks di UI: "Workflow notation follows ISO 5807 conventions" + "reference mapping, not certification".

---

## 21. Skenario Q — Easy Mode (PILIH → RUN → OUTPUT) vs Expert Mode

Dua **shell aplikasi yang berbeda** di atas **mesin riset yang sama** (tidak ada implementasi ilmiah ganda):

```
                    CORE ENGINES (metadata/C2PA, SynthID analyzer, method runner 64 metode,
                    separation, format conversion + pixel integrity, report renderers)
                                   │
                ┌──────────────────┴──────────────────┐
                │                                     │
   app/core/easy_mode_orchestrator.py       AppController (Expert actions)
                │                                     │
          EasyWindow (Easy)                   MainWindow (Expert)
```

### Ganti mode = ganti layout aplikasi (SAVE & RESTART)

```
Expert: Settings > User Interface Mode > APPLICATION MODE ( ) Easy Mode ( ) Expert Mode
        atau menu View > "Switch to Easy Mode (save & restart)..."
Easy:   tombol ⚙ Settings > APPLICATION MODE
  → muncul "Your interface mode will change after restart."   [SAVE & RESTART] [CANCEL]
  → SAVE & RESTART: simpan ui_mode ke settings.json → start instance baru (detached, EXE yang sama;
    --workspace sesi ikut) → tutup instance lama → instance baru membuka shell sesuai mode
  → ditolak bila ada operasi berjalan; bila relaunch gagal: mode tetap tersimpan + pesan jelas
```
Easy Mode **bukan** Expert yang tab-nya disembunyikan: Fingerprint Lab di Expert kini selalu menampilkan semua tab
(strip lama "RESEARCH GOAL → RUN" menjadi **QUICK RUN** khusus Expert).

### Easy Mode — tiga langkah saja

```
01 · PILIH   "Pilih gambar yang ingin diteliti."
    ├─ area besar DROP GENERATIVE IMAGE HERE (drag & drop / klik / Enter) + tombol CHOOSE IMAGE
    ├─ fakta file saja: Selected file · Resolution · Format (dari magic bytes) · File size
    │   (TIDAK ada metadata, C2PA, SynthID, hash, metode, istilah riset)
    ├─ OUTPUT FORMAT: PNG / JPG / WEBP / TIFF / BMP (default PNG) — "Pilih format hasil."
    ├─ RESEARCH REPORT: [✓] Save research report · lokasi opsional (default: folder eksperimen)
    └─ CONTINUE (selalu terlihat di action bar bawah)

02 · RUN     READY TO ANALYZE → [ RUN TRANSFORMATION ] → "RUNNING..." (disabled)
    ├─ ANALYZING YOUR IMAGE + progress bar + 5 kata saja:
    │     Preparing · Analyzing · Reconstructing · Validating · Finalizing
    ├─ LOCAL RESEARCH ENVIRONMENT: CPU threads · GPU (nama atau "not detected"; engine jalan di CPU)
    └─ Error: "Something went wrong." + DETAILS (opsional, tersembunyi) + TRY AGAIN / BACK
       (tidak pernah traceback Python mentah)

03 · OUTPUT  ✓ RESULT READY
    ├─ preview besar RESULT IMAGE · "PNG · 1536 × 2048" · PIXEL STATUS (✓ VERIFIED / ≈ LOSSY · PSNR / ...)
    ├─ SAVE RESULT (dialog simpan; menolak menimpa file asli) · OPEN RESULT · OPEN REPORT · RUN ANOTHER
    ├─ 3 kartu kecil: IMAGE (resolusi, format, pixel status) · PROVENANCE (C2PA, SynthID)
    │                 · RESEARCH (methods executed, methods unavailable, experiment ID)
    ├─ bila ada metode gagal: "Some research methods were unavailable. The experiment continued using
    │   the validated methods that were available."
    └─ VIEW RESEARCH DETAILS → viewer detail gaya Expert (Summary, Methods 64, Reconstruction candidates,
       Controlled case, Provenance, Fingerprint families, Pipeline) TANPA pindah ke Expert Mode
Step indicator selalu tepat 3: 01 aktif → 01 ✓ 02 aktif → 01 ✓ 02 ✓ 03 aktif (simbol + teks, bukan warna saja).
RUN ANOTHER → kembali ke 01 PILIH dengan state bersih, tanpa restart.
```

### Pipeline internal (EasyModeOrchestrator) — deterministik, 12 stage

```
01 Safety        read_file_bytes: magic bytes (ekstensi tak dipercaya), batas ukuran & memori   [KRITIS]
02 Baseline      SHA-256 + BLAKE3 file, decode (open_image_bytes), pixel SHA-256                [KRITIS]
03 Metadata      analyze_bytes (EXIF/XMP/IPTC/ICC/...), buat eksperimen SPX-YYYY-MMDD-NNNNNN,
                 original disalin ke experiments/<ID>/original/ ; Method 01 = engine native    [KRITIS]
04 C2PA          parse JUMBF/CBOR + hard binding; validator lokal opsional; dipisah dari piksel (Method 02)
05 SynthID       analyze_synthid → hanya engine LOKAL; tanpa engine = UNAVAILABLE; TIDAK PERNAH online
06 Fingerprint   taxonomy matching (kode "taxonomy 3A" dst. → 17 famili di DB taksonomi) +
                 17 metode analisis pada tile pusat resolusi native ≤1024 px (tanpa resampling,
                 origin sejajar grid 16 px untuk blok JPEG)
07 Signal        metode frontier deskriptif (56, 58, 61, 62) pada gambar nyata — tidak ada yang dihapus
08 Separation    CONTROLLED SURROGATE: tile ≤512 px = host bersih → sinyal surrogate berkunci
                 (spatial, strength 3, key 20261005) → detektor harus valid (clean tidak terdeteksi,
                 embedded terdeteksi) → 34–38, 41, 42, 55, 59, 60 diskor terhadap ground truth
09 Consensus     ringkasan per famili, Method 54 (meta) dengan hasil nyata, Method 61 (disagreement),
                 agreement antar kandidat (korelasi rata-rata peta kandidat)
10 Validation    re-hash original (berubah → STOP) + evaluator kandidat                          [KRITIS]
11 Output        format_conversion (engine Transformation yang sama): PNG/WEBP/TIFF/BMP LOSSLESS,
                 JPG LOSSY q95; ICC + EXIF/XMP dibawa; C2PA tidak bisa valid utk byte baru → tidak
                 disalin; verifikasi piksel vs original; output harus bisa di-decode            [KRITIS]
12 Report        HTML + PDF + JSON (renderer report_service) + figur; salin ke lokasi pilihan bila ada
Selalu: easy_mode_run.json (rekam lengkap) di folder eksperimen; audit log per stage.
```

**Dua arm yang tidak pernah dicampur** (tercatat di setiap metode & di laporan):

- **REAL IMAGE OBSERVATION** — gambar pengguna hanya **diamati** (metadata, C2PA, status SynthID lokal, statistik
  fingerprint deskriptif). Tidak ada sinyal yang diestimasi keluar atau dihapus dari gambar nyata. **Gambar hasil =
  re-encode piksel-preserving dari original** dalam format terpilih, terverifikasi (PIXEL-EXACT untuk format lossless).
- **CONTROLLED SURROGATE RESEARCH** — rekonstruksi/separasi hanya pada host + sinyal surrogate berkunci lokal yang
  ground truth-nya diketahui. Hasilnya **pengukuran di laporan**, tidak pernah menjadi gambar hasil, dan tidak
  digeneralisasi ke SynthID/watermark nyata.

**Method suitability engine** (`EasyModeOrchestrator.plan`) memutuskan untuk SETIAP metode (64): RUN atau SKIP +
alasan, dengan faktor format, resolusi, model, dependency, ground truth, GPU, maturity, kapabilitas analyze/reconstruct:

| Status skip | Contoh |
|---|---|
| UNAVAILABLE | DIRE, AEROBLADE, CLIP/ViT/DINO, DNA-Det, causal (model/runtime DL tidak terpasang) |
| NOT IMPLEMENTED | Method 43–46 (detector evasion — sengaja di luar scope) |
| REQUIRES DATA | 04, 25, 30, 57 (butuh gambar referensi / set terkendali) |
| INCOMPATIBLE | 18 Benford-DCT untuk input non-JPEG; arm terkendali bila gambar < 128 px |
| EXPERT ONLY | robustness (39, 40, 63) & Hypothesis Lab (47–52) — bukan bagian pipeline Easy |
| REDUNDANT | 53 Ensemble (anggotanya dijalankan satu per satu) |

Metode dengan implementasi & input identik (mis. 03/12/17/21 = residual, 13/16 = FFT, 35/41, 38/42) dieksekusi
**sekali**; recordnya menyatakan "shared execution with Method X". Eksekusi paralel (thread pool) tapi urutan
rekaman tetap deterministik.

**Evaluator kandidat** (tidak memilih yang pertama): gate validasi = recovery corr ≥ 0.30, SSIM ≥ 0.90,
PSNR ≥ 32 dB, resolusi sama, metrik finite. Skor = signal consistency 0.30 + perceptual fidelity 0.20 + pixel
integrity 0.15 + method agreement 0.15 + research validity (maturity) 0.10 + resolution 0.05 + runtime 0.05.
Skor detektor surrogate **dicatat tapi tidak dipakai untuk ranking** (bukan pencarian evasion). Kandidat lolos
selalu di atas yang gagal; bila tak ada yang lolos → **NO VALIDATED RECONSTRUCTION** (laporan tetap ditulis).

**Penanganan kegagalan:** metode yang gagal → FAILED + detail, run lanjut; stage non-kritis gagal → dicatat,
metode di stage itu "NOT RUN", run lanjut (status COMPLETE WITH WARNINGS). Berhenti hanya bila sumber tak bisa
dibaca/di-decode, output tidak valid, atau integritas original gagal — dengan kalimat ramah, detail teknis opsional.

**Laporan Easy** (`app/services/easy_report.py`): Experiment ID, input/output + hash, resolusi, format, pixel
integrity, C2PA, SynthID, famili fingerprint, metode executed/skipped/failed, kasus terkendali, kandidat + metrik,
konsensus, stage pipeline, limitations, research notes, source references, figur.

**Pengaturan Easy minimal:** Language · Mode · Default output format · Report on/off · Default report location.

**Aksesibilitas:** semua kontrol bisa di-Tab; Enter = aksi utama langkah (CONTINUE / RUN / SAVE), Escape = BACK;
Ctrl+O pilih gambar, Ctrl+S simpan hasil; ring fokus biru 3 px; target klik ≥ 44–68 px; teks kontras tinggi;
accessible name di setiap tombol/area; status tidak hanya warna (✓ ● ○ ≈ + teks); layout RTL untuk ar/fa/ur.

---

## 21b. Skenario Q2 — TruthScan Cross-Detector Lab (Expert)

SynthProvenance = **sistem forensik independen**; TruthScan = **detektor eksternal** yang hasilnya *diimpor*
(user-supplied), dipelajari, **bukan** dijadikan ground truth, dan **tidak pernah** diunggah oleh aplikasi.

```
GAMBAR
  → baseline lokal, C2PA, metadata, taksonomi, analisis SynthProvenance (lokal, otomatis)
  → OPSIONAL hasil TruthScan user-supplied (impor JSON / entri manual / hand-off browser consent-gated)
  → mesin perbandingan → analisis disagreement → laporan cross-detector
```

**Impor (default, lokal penuh):** tab External Result → tempel JSON / Load JSON / entri manual (final label,
confidence, detection_step 1/2/3). Hasil ditandai `SOURCE = EXTERNAL / USER-SUPPLIED` (+ submission id, timestamp,
file hash bila ada). Parser toleran terhadap beberapa ejaan field; seluruh blob disimpan di `raw`. *Field harus
diverifikasi ulang ke dokumentasi TruthScan terkini.*

**Hand-off browser (OFF default, consent-gated):** seperti SynthID online — buka `truthscan.com` di browser +
reveal file di Explorer setelah konfirmasi sesi + consent per-buka; peneliti mengunggah sendiri; aplikasi
TIDAK pernah mengunggah (`uploaded_by_synthprovenance: false`; host allow-listed https).

**Evidence lokal = deskriptif.** SynthProvenance tidak pernah memberi verdict "AI vs manusia" dari piksel. Tiap
dimensi bukti bisa *condong* (provenance C2PA kamera / deklarasi AI di metadata) tapi mayoritas `DESCRIPTIVE`.
Dipetakan ke 7 keluarga taksonomi (INTRINSIC / CAUSAL / SPECTRAL / PROACTIVE / DETECTOR REPRESENTATION /
RECONSTRUCTION / PROVENANCE) via **Evidence Mapper** (EVIDENCE-### + family + representasi + metode + referensi +
ground truth + status validasi).

**Outcome perbandingan:** `AGREEMENT` / `PARTIAL AGREEMENT` / `DISAGREEMENT` / `INSUFFICIENT EVIDENCE`. **Tidak
pernah** menyebut detektor eksternal "salah" atau SynthProvenance "benar". Pernyataan "matches / does not match"
hanya saat **ground-truth LEVEL ≥ 3**, dan itu tentang label eksternal vs ground truth — bukan vonis atas sistem.

**Hierarki ground truth (Section 8):** LEVEL 0 unknown · 1 observer-reported · 2 known generator+dataset ·
3 locally generated controlled · 4 known watermark/fingerprint GT · 5 reproducible synthetic benchmark.

**Scorecard independen (9 dimensi)** TIDAK pernah digabung jadi satu "truth score". **Heatmap**: impor heatmap
TruthScan → bandingkan IoU/Dice/korelasi dengan peta lokal (FFT/residual/rekonstruksi); overlap ≠ kebenaran.
**Hard-case generator**: benchmark lokal reproducible berlabel ground truth (sintetis, +surrogate watermark,
edited, upscaled, dan *natural-like control* yang JELAS ditandai BUKAN foto nyata). **Benchmark matrix** → CSV
(IMAGE/GROUND TRUTH/TRUTHSCAN/SYNTHPROVENANCE/C2PA/METADATA/SPECTRAL/RECONSTRUCTION/FINGERPRINT/FINAL STATUS).

**Store:** run `SPX-XD-YYYYMMDD-NNNNNN` di `<workspace>/cross_detector/<ID>/` (run.json, inputs/, external/,
report/, logs/); original di-hash sebelum & sesudah (`original_unchanged`). **Laporan** 14 bagian (HTML/PDF/JSON)
+ matrix CSV. **Batas (sama dengan [[synthprovenance-redteam-scope]]):** tidak ada optimizer detector-evasion
(Method 43–46 tetap NOT_IMPLEMENTED); tidak ada auto-upload/auto-submit; tidak klaim transfer surrogate→TruthScan.
Doc: `docs/CROSS_DETECTOR_RESEARCH.md`, `docs/TRUTHSCAN_RESEARCH.md`, `docs/FINGERPRINT_EVIDENCE_MODEL.md`.

Motto lab: **ONE DETECTOR IS AN OPINION. MULTIPLE INDEPENDENT MEASUREMENTS CREATE EVIDENCE. — WE DO NOT GUESS.
WE MEASURE. WE CHALLENGE. WE REPRODUCE. WE DOCUMENT.**

---

## 21c. Skenario Q3 — Upgrade v6 (execution matrix, import Markdown, tema)

- **Taksonomi → stage dapat dieksekusi.** `data/fingerprint_execution_matrix.json` + `docs/UPGRADE_V6_IMPLEMENTATION_AUDIT.md`
  (dibangkitkan `scripts/build_execution_matrix.py`) memetakan tiap metode (64) ke keluarga fingerprint, representasi,
  dan flag kapabilitas (CAN_ANALYZE/ESTIMATE/SEPARATE/RECONSTRUCT/VALIDATE). Kesiapan dari registry, bukan karena
  muncul di dropdown; `test_execution_matrix_is_bundled_and_consistent` memverifikasi cocok dengan registry live.
- **TruthScan archive (Markdown).** `ExternalResult.from_markdown` mengimpor arsip riset sebagai **konteks metodologis
  saja** (reference-only; direction UNKNOWN; mengekstrak documented stages/fields + distingsi FAKTA/INFERENSI + caveat
  "99%+ tidak tervalidasi independen"). TIDAK pernah menyimpulkan skor per-gambar dari teks riset umum (v6 §36).
  `from_csv` juga ditambahkan. Arsip bundel: `TruthScan Archives/…`; dok `docs/RESEARCH_SOURCES_V6.md`,
  `docs/TRUTHSCAN_RESEARCH.md`.
- **Tema (15).** Engine tema berbasis peran (`app/ui/themes.py` + `app/ui/theme.py`): Dark/Light Laboratory, Neon Blue,
  Neon Yellow, Arctic Cyan, Aurora, Graphite, Ivory, Ocean, Forest, Sunset, Violet, Rose, Solar, Paper. Dipilih di
  Expert Settings, diterapkan langsung (live) + persisten (`theme`); presentasi saja. Easy Mode tetap tampilan light
  khususnya.
- **Easy OUTPUT cards** di-relabel: **PROVENANCE · FINGERPRINT · PIXEL INTEGRITY** (v6 §24).
- **Verifikasi EXE** menambah `--smoke-cross` (studi cross-detector lengkap dalam EXE: import external + arsip Markdown,
  banding dengan evidence lokal, ekspor laporan, original unchanged, LOCAL-ONLY).

---

## 22. Skenario R — Research Wizard (7 langkah)

```
STEP 1 Input            → buka gambar / demo fixture
STEP 2 Baseline         → start experiment (hash, C2PA, metadata, statistik)
STEP 3 Research Target  → pilih goal (assistant menyarankan metode)
STEP 4 Method           → pilih metode + parameter surrogate (family/strength/key)
STEP 5 Experiment       → jalankan metode → SPX-FP id
STEP 6 Validation       → original re-hash (unchanged) + metrik fidelitas/GT
STEP 7 Report           → buka lab / Export for Paper (ZIP)
```
Selalu tampil "Step X of 7".

---

## 23. Skenario S — Transformation/Format/Sanitization & Pixel Integrity

```
Transformation Lab  → operasi terkendali (mis. jpeg_reencode) → diukur vs ORIGINAL
Format Conversion   → SAVE AS PNG/JPEG/WEBP/TIFF/BMP (LOSSLESS/LOSSY, quality, ICC, metadata) → tiap step diukur
Metadata Sanitizer  → mode METADATA-ONLY: tulis ulang kontainer, data piksel disalin verbatim
                       → VERIFIKASI changed_pixels == 0 ; jika tidak → "UNEXPECTED PIXEL MODIFICATION DETECTED" (STOP)
Pixel Integrity     → MAE/MSE/max err/changed px%/PSNR/SSIM(7x7)/hist diff/dHash
                       → "PIXEL-EXACT ✓" hanya jika semua sample identik + digest piksel sama
```

---

## 24. Skenario T — Paper Export & reprodusibilitas

```
EXPORT FOR PAPER (ZIP)  → CSV + JSON + PDF + PNG + struktur folder:
   experiment/
     run.json  inputs/  maps/  config/  logs/  report/
     hashes_sha256.txt   (format sha256sum)
     hashes_blake3.txt   (format b3sum)
     README.txt          (pernyataan hati-hati)
```
Tiap run menyimpan: method + capability flags, parameter, seed, surrogate cfg, environment (OS/CPU/GPU/CUDA/versi
library), hash input/output, runtime, memori puncak, `original_unchanged`. Reproduksi = jalankan ulang (seed tetap) /
muat pipeline JSON.

---

## 25. Skenario U — i18n (30 bahasa)

```
Settings > Language → set_active(code) → MainWindow.retranslate() (label navigasi ganti langsung)
   30 locale (en, id, zh, es, hi, ar, pt, bn, ru, ja, pa, de, jv, ko, fr, vi, ta, ur, tr, it, th, gu, fa, pl,
              uk, ms, ro, nl, el, cs)
   Kunci yang tak diterjemahkan → fallback ke English (tak pernah ke raw key)
   Istilah teknis/nama metode tetap English (istilah kanonik dipertahankan)
   RTL untuk ar/fa/ur; tiap locale punya _meta.complete (kelengkapan)
```
Translasi inti dibangkitkan `scripts/build_i18n.py`. Shell Easy Mode (85 string: PILIH/RUN/OUTPUT, tombol, fase,
pesan error, settings, mode) **lengkap di 30 bahasa** (`scripts/i18n_easy.py`, divalidasi placeholder & jumlahnya);
bahasa Indonesia memakai nama langkah proyek PILIH · RUN · OUTPUT. Ganti bahasa di Easy Settings berlaku langsung.

---

## 26. Skenario V — Keamanan & LOCAL-ONLY

```
netguard (audit hook)  → blokir socket.connect/getaddrinfo ke host non-loopback
                         → self-test membuktikan koneksi keluar diblokir
Input tak dipercaya     → metadata tak pernah dieksekusi; anti decompression-bomb; budget memori
Path safety             → safe_filename / safe_join / safe_arcname (anti traversal & zip-slip)
Subprocess aman         → argumen sebagai list (bukan shell string dari path tak dipercaya)
Tidak ada               → unduh model diam-diam, telemetry, upload, cloud inference
```

---

## 27. Skenario W — Build → Test → EXE → Verify

```
build.bat → scripts/build.py (8 stage):
  [1/8] cek environment        [2/8] siapkan Python+.venv     [3/8] install deps (pinned)
  [4/8] validasi sumber         [5/8] pytest penuh            [6/8] PyInstaller (one-folder, windowed)
  [7/8] verifikasi EXE          [8/8] siapkan distribusi (assets/config/data/i18n, BUILD_INFO, SHA256SUMS)
Verifikasi stage 7 MENJALANKAN EXE:
  SynthProvenance.exe --self-test   (10 cek, termasuk fingerprint lab, v4_integration, easy_mode_pipeline)
  SynthProvenance.exe --smoke-gui   (Expert: 16 view render, run fingerprint + SynthID, 0 network attempt)
  SynthProvenance.exe --smoke-easy --smoke-restart-to EXPERT --smoke-restart-ack <file>
                                    (Easy: PILIH → RUN TRANSFORMATION → OUTPUT lewat widget asli, SAVE RESULT,
                                     RUN ANOTHER, lalu SAVE & RESTART → EXE baru harus membuka MainWindow/EXPERT)
Output: dist\SynthProvenance\SynthProvenance.exe
```
Status terakhir: **suite lulus (exit 0)** (Easy Mode + Cross-Detector + tema + execution-matrix tests); self-test (11 cek, +easy_mode_pipeline +cross_detector_lab), smoke Expert (17 view termasuk TruthScan Cross-Detector Lab), smoke Easy, smoke Cross-Detector +
SAVE & RESTART exit 0; EXE v2.1.0 terverifikasi, plus uji GUI nyata via Windows UI Automation (Expert → Easy → PILIH →
RUN → OUTPUT → SAVE RESULT → Easy → Expert).

---

## 28. Format ID & artefak yang dihasilkan

| Hal | Format / lokasi |
|---|---|
| Experiment utama | `SPX-YYYY-MMDD-NNNNNN` → `<workspace>/experiments/<ID>/` |
| Run Easy Mode | eksperimen yang sama + `easy_mode_run.json`, `output/T001_format_conversion.<ext>`, `report/<ID>_easy_research_report.{html,pdf,json}` + `report/figures/` |
| SynthID research run | `SPX-SID-YYYYMMDD-NNNNNN` → `<workspace>/synthid_research/<ID>/` |
| Fingerprint lab run | `SPX-FP-YYYYMMDD-NNNNNN` → `<workspace>/fingerprint_research/<ID>/` |
| Peta/maps | PNG di `maps/` (viridis; simetris untuk candidate/residual/difference) |
| Bundel makalah | ZIP + CSV/JSON/PDF/PNG + manifest SHA-256 & BLAKE3 |
| Taksonomi/Library/Katalog | `data/*.json` (bundel, offline) |
| Locale | `app/i18n/locales/<code>.json` |

---

## 29. Status metode (apa yang benar-benar jalan)

Registry = **64 metode (Method 00–63)**. Ringkasan `docs/IMPLEMENTATION_GAP_ANALYSIS.md`:

- **FULLY IMPLEMENTED (7):** studi separasi surrogate (analyze+estimate+separate+reconstruct+validate).
- **PARTIALLY IMPLEMENTED (2):** separasi/rekonstruksi tanpa set lengkap.
- **DETECTOR ONLY (7):** mengestimasi kandidat, tak memisah.
- **ANALYSIS ONLY (19):** deskriptif (spectral/residual/statistik).
- **RESEARCH ONLY (13):** hipotesis/frontier (validasi hanya di GT terkendali).
- **UNAVAILABLE (12):** butuh runtime DL+bobot (DIRE, AEROBLADE, CLIP/ViT/DINO, DNA-Det, causal, dst.).
- **NOT IMPLEMENTED (4):** detector-evasion (Method 43–46) — di luar scope by design.

48 metode `READY` (jalan lokal sekarang).

---

## 30. Batasan & etika (apa yang TIDAK dilakukan)

- Tidak mengklaim gambar "AI" atau "manusia" dari piksel.
- Tidak menyerang/menghapus/mengalahkan watermark piksel nyata (termasuk SynthID).
- Tidak mencari transformasi yang menurunkan skor detektor watermark (Method 43–46 = NOT IMPLEMENTED).
- Tidak meniru decoder resmi SynthID; verifikasi SynthID lokal = UNAVAILABLE + hand-off resmi.
- Tidak unduh bobot/model diam-diam, tanpa telemetry/upload/cloud.
- Hasil surrogate = ground truth terkendali, **tidak** dapat digeneralisasi ke generator/watermark nyata.

---

## 31. Pertanyaan untuk brainstorming

Gunakan bagian ini sebagai pemantik diskusi (mis. dengan ChatGPT):

**Validitas ilmiah**
1. Apakah metrik `candidate_vs_known_corr` + `signal_reduction` cukup untuk menyimpulkan "separable"? Metrik tambahan apa?
2. Bagaimana membedakan korelasi karena konten/edge dari korelasi karena fingerprint sejati, tanpa model terlatih?
3. Kalibrasi null surrogate (mean≈0, sd≈1) — apakah cukup untuk klaim FPR rendah? Perlu uji permutasi?

**Jembatan ke dunia nyata (tanpa melanggar scope)**
4. Jalur etis apa untuk mengevaluasi metode pada generator nyata (dataset berlabel) tanpa menjadi alat penghapus watermark?
5. Jika runtime DL ditambahkan (opsional), kandidat mana yang paling bernilai (TrustMark? SPAI? Community Forensics?) dan bagaimana batas lisensinya?
6. Bagaimana merancang "cross-generator generalization" yang jujur (seen/unseen/cross-family) dengan CI?

**Desain metode baru**
7. Frontier mana yang layak naik dari HYPOTHETICAL ke tervalidasi, dan desain eksperimen replikasinya seperti apa?
8. Apakah Method Composer perlu optimasi pemilihan pipeline (search) — dan bagaimana menjaga agar bukan detector-evasion?
9. Metrik ketidakpastian (Method Disagreement) — bagaimana mengkalibrasinya menjadi confidence yang bermakna?

**Produk & UX**
10. Apakah pembedaan Easy/Expert sudah tepat? Fitur apa yang harus naik/turun level?
11. Research Assistant: aturan rekomendasi mana yang kurang, dan bagaimana menjelaskan "WHY" lebih baik?
12. i18n: strategi menambah kelengkapan 30 bahasa tanpa menerjemahkan istilah teknis secara keliru?

**Reprodusibilitas & tata kelola**
13. Apa lagi yang harus masuk ke paper bundle agar benar-benar "paper-ready" & dapat diaudit pihak ketiga?
14. Bagaimana memverifikasi klaim "LOCAL-ONLY" secara independen (mis. sandbox jaringan eksternal)?

---

*Dokumen ini deskriptif atas implementasi v2.1.0. Perubahan kode → perbarui dokumen ini. WE DO NOT GUESS. WE MEASURE.*
