# SynthID Research Sources

Last revised: 2026-10-05. Previous revision: 2026-10-02 (see section 11 for what changed).

SynthProvenance never fetches these URLs at runtime. The researcher consulted them while writing this document.
Anything that could not be confirmed from a fetched primary source is marked UNVERIFIED.

Note: the bundled catalogue `config/synthid_sources.json` was not modified in this revision and still reflects the
2026-10-02 research. Section 10 lists the entries that should be updated there.

---

## 1. Scope and method

| Item | Value |
|------|-------|
| Search date | 2026-10-05 |
| Questions | (1) Current state of Google DeepMind SynthID for images: paper, Detector portal, Gemini app verification, public APIs/SDKs, partnerships, local/offline detection. (2) C2PA specification version, hard and soft binding, durable Content Credentials, tooling versions and licences, AI-labelling changes in 2025-2026. (3) Official Google user-facing verification routes that a desktop app may open in the browser. |
| Tools | Web search (standard and extended modes), page fetch with summarisation, and direct HTTP requests (`curl`) against public pages. Package versions came from the crates.io API, the PyPI JSON API and GitHub "latest release" redirects. The GitHub REST API hit its anonymous rate limit, so GitHub pages and raw README files were read directly. |
| Sites consulted | deepmind.google, blog.google, support.google.com, docs.cloud.google.com, ai.google.dev, docs.google.com (forms), arxiv.org, huggingface.co, spec.c2pa.org, raw.githubusercontent.com (c2pa-org), cawg.io, github.com, crates.io, pypi.org, developers.openai.com, help.openai.com. Pages on openai.com returned HTTP 403 to automated requests; they are recorded only as seen in search results or as referenced by fetched OpenAI pages. |
| Evidence rule | Facts come from primary sources (the publisher of the product, standard or paper). Press and blog articles were used only to find primary sources and are not cited as evidence. |

---

## 2. SynthID official sources

All rows accessed 2026-10-05 unless marked otherwise.

| ID | Source | URL | Type | Accessed | Key facts |
|----|--------|-----|------|----------|-----------|
| DEEPMIND-SYNTHID | SynthID - Google DeepMind | https://deepmind.google/models/synthid/ | Official product page | 2026-10-05 | Covers image, video, audio and text. Verification routes it names: the Gemini app (upload and ask) and the SynthID Detector portal, described as "in early testing with journalists". Its Detector link is the onboarding form (SYNTHID-DETECTOR-ONBOARDING). No API, SDK, local or offline image detection is mentioned. |
| GOOGLE-SYNTHID-DETECTOR | SynthID Detector announcement | https://blog.google/innovation-and-ai/products/google-synthid-ai-content-detector/ | Official blog | 2026-10-05 | Published 2025-05-20. The portal highlights the parts of a file most likely to carry the watermark. Partnerships: NVIDIA (SynthID on videos from NVIDIA Cosmos on build.nvidia.com) and GetReal Security (third-party detection of SynthID content). Says SynthID Text is open source. No API mentioned. |
| SYNTHID-DETECTOR-ONBOARDING | SynthID Detector & Backstory onboarding form | https://docs.google.com/forms/d/1KAkSpRixcGi7pKaPyw5FyahaQqpawmNq65gHgBWgFjg/viewform | Official form | 2026-10-05 | Accepting responses. Only for active journalists and verification professionals, who must use a corporate email address linked to a Google Account. Points everyone else to SynthID in the Gemini app. |
| SYNTHID-DETECTOR-WAITLIST | Original Detector waitlist | https://docs.google.com/forms/d/e/1FAIpQLSfAYrauHmY-PpUNxL4Fs6coa185CtKWp7TnEXL0tKbAezo4MQ/viewform | Official form | 2026-10-05 | "This form is no longer accepting responses." Says verification is available through the Gemini app. |
| GOOGLE-GEMINI-IMAGE-VERIFY | AI image verification in the Gemini app | https://blog.google/innovation-and-ai/products/ai-image-verification-gemini-app/ | Official blog | 2026-10-05 | Published 2025-11-20. Upload an image and ask whether it was made with Google AI; Gemini checks for SynthID. C2PA Content Credentials were added to Nano Banana Pro images in Gemini, Vertex AI and Google Ads. More than 20 billion items watermarked at that date. |
| GOOGLE-GEMINI-VIDEO-VERIFY | Verify Google AI videos in the Gemini app | https://blog.google/technology/ai/verify-google-ai-videos-gemini-app/ | Official blog | 2026-10-05 | Published 2025-12-18. Videos up to 100 MB and 90 s. Reports audio and visual segments separately. Image and video verification are available "across all languages and countries where the Gemini app operates". |
| GOOGLE-GEMINI-HELP | Verify AI-generated images, videos, and audio | https://support.google.com/gemini/answer/16722517 | Official help | 2026-10-05 | Procedure, limits and result meanings (see section 4). Gemini "can currently only recognize content created by Google AI tools", even though other companies have adopted SynthID. |
| GOOGLE-GEMINI-APP | Gemini | https://gemini.google.com/ | Official app | 2026-10-05 | The user-facing route: browser, signed-in Google account, manual upload. |
| NANO-BANANA-2 | Nano Banana 2 | https://blog.google/innovation-and-ai/technology/ai/nano-banana-2/ | Official blog | 2026-10-05 | Published 2026-02-26. Pairs SynthID with C2PA Content Credentials. Gemini verification had been used "over 20 million times". C2PA verification in the Gemini app announced as coming. |
| GOOGLE-IO26-PROVENANCE | Understanding how content was created and edited | https://blog.google/innovation-and-ai/products/identifying-ai-generated-media-online/ | Official blog | 2026-10-05 | Published 2026-05-19. More than 100 billion images and videos and 60,000 years of audio watermarked. Gemini verification used 50 million times. SynthID verification expands to Search "today" and Chrome "over the coming weeks". C2PA verification in Gemini "starting today", Search and Chrome "in the coming months". Adopters: OpenAI, Kakao, ElevenLabs; NVIDIA (Cosmos video). Announces the AI Content Detection API for trusted partners. |
| GOOGLE-IO26-100 | 100 things we announced at Google I/O 2026 | https://blog.google/innovation-and-ai/technology/ai/google-io-2026-all-our-announcements/ | Official blog | 2026-10-05 | Items 97-100 repeat the above. Verification through Lens, AI Mode, Circle to Search and Gemini in Chrome by asking "Is this made with AI?". |
| GOOGLE-SEARCH-IMAGE-DETAILS | Find Google Image details (Search Help) | https://support.google.com/websearch/answer/9789430 | Official help | 2026-10-05 | Lists SynthID ("a digital watermark embedded on some AI-generated images") and C2PA among the data that "Learn more about an image" can show when it exists. Does not describe access steps, regions or account requirements. |
| GCLOUD-AI-CONTENT-DETECTION | Detect AI-generated images (Gemini Enterprise Agent Platform) | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/ai-content-detection | Official cloud docs | 2026-10-05 | Page body now read in full. Pre-GA; Private Preview by application. REST upload of JPEG, PNG or WebP. Uses "machine learning models that analyze pixel-level artifacts, noise patterns, and spectral anomalies" for Google and third-party models. "Support for C2PA metadata detection is not included." Does not mention SynthID. Output is probabilistic and advisory. Images are not retained. |
| GCLOUD-CONTENT-CREDENTIALS | Content Credentials (Gemini Enterprise Agent Platform) | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/content-credentials | Official cloud docs | 2026-10-05 | Output of the listed models (for example gemini-3-pro-image, gemini-3.1-flash-image, gemini-2.5-flash-image, Veo 2/3/3.1, Lyria 3 previews) is signed by Google LLC with "Google Media Processing Services" as app/device. Verification is pointed to the Content Credentials website. |
| VERTEX-VERIFY-WATERMARK | Verify an image watermark (Vertex AI, Imagen) | https://docs.cloud.google.com/vertex-ai/generative-ai/docs/image/verify-watermark | Official cloud docs | 2026-10-05 | Still HTTP 404. Treated as retired. |
| GEMINI-API-IMAGE-GEN | Gemini API image generation | https://ai.google.dev/gemini-api/docs/image-generation | Official developer docs | 2026-10-05 | "All generated images include a SynthID watermark." No verification method documented. |
| WORKSPACE-AI-LABELS | AI labels & content credentials (Docs Help) | https://support.google.com/docs/answer/17560328 | Official help | 2026-10-02 (not re-checked) | Gemini output in Workspace carries Content Credentials signed as Google Media Processing Services. |
| SYNTHID-BIO | Introducing SynthID Bio | https://blog.google/innovation-and-ai/models-and-research/google-deepmind/synthid-bio/ | Official blog | 2026-10-05 | Published 2026-09-30. Watermarks AI-designed protein sequences and structures. Not related to images. No mention of open-source release, local detection or APIs. |
| ARXIV-2510.09263 | SynthID-Image paper | https://arxiv.org/abs/2510.09263 | Preprint (arXiv) | 2026-10-05 | See section 3. |

### Partner sources (not Google)

| ID | Source | URL | Type | Accessed | Key facts |
|----|--------|-----|------|----------|-----------|
| OPENAI-PROVENANCE-HELP | Provenance signals (Content Credentials, SynthID) in OpenAI-generated content | https://help.openai.com/en/articles/8912793 | Partner help | 2026-10-05 | Images from ChatGPT, Codex and the OpenAI API carry C2PA metadata and a SynthID watermark; OpenAI audio carries SynthID. OpenAI Verify (openai.com/verify) checks for OpenAI signals only and "is not designed to detect content generated by other AI services". A verification API exists. |
| OPENAI-CONTENT-PROVENANCE-API | Content provenance guide (OpenAI API) | https://developers.openai.com/api/docs/guides/content-provenance | Partner developer docs | 2026-10-05 | `POST /v1/content_provenance_checks`. Returns separate `c2pa` and `synthid` results (`detected` / `not_detected`). Checks "supported OpenAI signals" only; "isn't a general-purpose AI detector". PNG, JPEG, WebP; 50 MiB per file; strict rate limits; not eligible for Zero Data Retention; organisations without access get HTTP 404. |
| OPENAI-ADVANCING-PROVENANCE | Advancing content provenance | https://openai.com/index/advancing-content-provenance/ | Partner blog | 2026-10-05 (seen in search results only; HTTP 403 when fetched) | Search snippet: OpenAI adds SynthID watermarking to images through a partnership with Google, and previews a public verification tool. Publication date UNVERIFIED from the page itself. |

---

## 3. SynthID-Image paper summary

| Field | Value (from https://arxiv.org/abs/2510.09263, accessed 2026-10-05) |
|-------|------|
| Title | SynthID-Image: Image watermarking at internet scale |
| Authors | Sven Gowal, Rudy Bunel, Florian Stimberg, David Stutz, Guillermo Ortiz-Jimenez, Christina Kouridi, Mel Vecerik, Jamie Hayes, Sylvestre-Alvise Rebuffi, Paul Bernard, Chris Gamble, Miklós Z. Horváth, Fabian Kaczmarczyck, Alex Kaskasoli, Aleksandar Petrov, Ilia Shumailov, Meghana Thotakuri, Olivia Wiles, Jessica Yung, Zahra Ahmed, Victor Martin, Simon Rosen, Christopher Savčak, Armin Senoner, Nidhi Vyas, Pushmeet Kohli |
| Year / version | 2025; v1 submitted 2025-10-10 (only version listed) |
| Categories | cs.CR (Cryptography and Security), cs.AI |

What the abstract says:

- SynthID-Image is a deep-learning system that invisibly watermarks AI-generated images.
- The paper documents requirements (effectiveness, fidelity, robustness, security), threat models and deployment problems
  at internet scale.
- It has watermarked more than ten billion images and video frames across Google services. Its verification service
  is "available to trusted testers".
- An external variant, SynthID-O, is "available through partnerships" and is benchmarked against post-hoc
  watermarking methods from the literature.
- The authors say the deployment and threat-model conclusions generalise to other modalities, including audio.

What it does not provide: no code, model weights or detector are released according to the arXiv page. The paper
does not create a way for third parties to verify SynthID locally.

---

## 4. Online verification routes

SynthProvenance policy: a route is opened in the system browser only after the researcher confirms. SynthProvenance
never uploads files. The researcher uploads by hand and records the result.

| Route | URL to open | What the user does | Requirements and limits | What it covers | Use in SynthProvenance |
|-------|-------------|--------------------|-------------------------|----------------|------------------------|
| Gemini app (Google) | https://gemini.google.com/ (instructions: https://support.google.com/gemini/answer/16722517) | Sign in. Click "Add files", choose the file (device, Google Photos or Drive), then ask, for example, "Was this image created or edited by Google AI?" | Personal account or qualified Workspace account. Signed in. One file per check, no collages. Up to 100 MB. About 10 image checks, 10 video checks (5 min total) and 10 audio checks (3 h total) per rolling 24 h. Video under 90 s, audio under 1 h. Mobile needs the latest app version. Available in all languages and countries where the Gemini app operates (GOOGLE-GEMINI-VIDEO-VERIFY). | SynthID from Google AI tools only. Results: detected (all or part made or edited by Google AI), not detected (not made by Google AI, but could be from other AI), or unclear. Also shows C2PA Content Credentials when present. | PRIMARY route. Open after confirmation. |
| SynthID Detector portal (Google) | Access request: https://docs.google.com/forms/d/1KAkSpRixcGi7pKaPyw5FyahaQqpawmNq65gHgBWgFjg/viewform. Information: https://deepmind.google/models/synthid/ | Apply through the form. After approval, upload image, audio or video in the portal. | Active journalists and verification professionals only. Corporate email linked to a Google Account. Portal URL is not public. | SynthID; highlights the watermarked regions. | Offer the information page and the form. Never present it as a general route. |
| Google Search: Lens, AI Mode, Circle to Search | Not linked (announcement: https://blog.google/innovation-and-ai/products/identifying-ai-generated-media-online/) | Ask "Is this made with AI?" about an image. | Announced 2026-05-19 as live "today". The Search Help page (https://support.google.com/websearch/answer/9789430) confirms SynthID can appear in image details. Desktop web steps, regions and account requirements: UNVERIFIED. | SynthID (and C2PA later, per the announcement). | Do not link until an official help page with steps is found. |
| Gemini in Chrome | Not linked | Ask Gemini in Chrome "Is this made with AI?" about an image. | Announced 2026-05-19 for "the coming weeks". Completed rollout, requirements and regions: UNVERIFIED. No Chrome help page found. | SynthID. | Do not link. |
| OpenAI Verify (partner, not Google) | https://openai.com/verify | Upload an image or audio file in the browser. | Account and region requirements UNVERIFIED (page returned HTTP 403 to automated fetch). | Only OpenAI signals: a trusted C2PA manifest issued to OpenAI, and SynthID in OpenAI-generated images and audio. Does not detect Google or other companies' content. | Optional secondary route for images suspected to come from OpenAI. Must be labelled "OpenAI content only". |

Programmatic services (not user routes; not integrated because they need automated upload to a cloud service):

| Service | URL | Status | Why not used |
|---------|-----|--------|--------------|
| Google Cloud AI Content Detection API | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/ai-content-detection | Pre-GA, Private Preview by application | Cloud upload. It is a statistical classifier; its documentation does not say it reads SynthID, and C2PA is excluded. |
| OpenAI Content Provenance API | https://developers.openai.com/api/docs/guides/content-provenance | Available to organisations with access; strict rate limits | Cloud upload; not eligible for Zero Data Retention; OpenAI signals only. |
| Vertex AI Imagen watermark verification | https://docs.cloud.google.com/vertex-ai/generative-ai/docs/image/verify-watermark | HTTP 404 | Retired. |

---

## 5. Local verification status

**LOCAL SYNTHID VERIFICATION: UNAVAILABLE**

No legitimate local or offline SynthID image detector was found. The evidence:

- Every official Google image-verification route is hosted: the Gemini app, the restricted Detector portal, Search and
  Chrome, and the cloud API (DEEPMIND-SYNTHID, GOOGLE-GEMINI-HELP, GOOGLE-IO26-PROVENANCE).
- The SynthID-Image paper releases no code, weights or detector. Verification is "available to trusted testers" and
  SynthID-O is available "through partnerships" (ARXIV-2510.09263).
- The only open-source SynthID code is SynthID Text, which is text only (section 6).
- The partner verifier (OpenAI) is also hosted: a web tool and a cloud API (OPENAI-CONTENT-PROVENANCE-API).
- The Gemini API documents that images are watermarked but offers no verification method (GEMINI-API-IMAGE-GEN).
- SynthID is not registered in the C2PA soft-binding algorithm list (53 entries on 2026-10-05, none from Google or
  SynthID; see section 8). So there is no C2PA-registered SynthID soft binding that a local C2PA tool could decode.
- No official Google statement about local or offline SynthID image detection was found, in either direction. The
  absence of such an offering is the finding; no Google statement that it will never exist was found.

Consequence for SynthProvenance: method SID-M1 (local engine) stays `UNAVAILABLE` unless a researcher configures an
engine, and the interface shows `LOCAL SYNTHID ENGINE: UNAVAILABLE`.

---

## 6. SynthID Text (text only, not applicable to images)

| Item | Value | Source (accessed 2026-10-05) |
|------|-------|--------|
| Reference implementation | google-deepmind/synthid-text | https://github.com/google-deepmind/synthid-text |
| PyPI package | `synthid-text` 0.2.1, uploaded 2024-11-14, Apache-2.0 | https://pypi.org/project/synthid-text/ |
| Hugging Face Transformers | Built in from v4.46.0 (`SynthIDTextWatermarkingConfig`, `SynthIDTextWatermarkLogitsProcessor`) | https://huggingface.co/blog/synthid-text and https://huggingface.co/docs/transformers/main/en/internal/generation_utils |
| Responsible GenAI Toolkit page | Describes SynthID Text, its limits, the HF Space and the Nature paper | https://ai.google.dev/responsible/docs/safeguards/synthid |
| Paper | Nature (2024) | https://www.nature.com/articles/s41586-024-08025-4 (linked from the page above; not fetched) |
| Licence | Code Apache-2.0; other materials CC-BY-4.0 (repository README, recorded 2026-10-02) | https://github.com/google-deepmind/synthid-text |

How it works: a logits processor changes token probabilities during generation. Detection needs a Bayesian detector
trained per watermarking configuration (the HF blog gives a minimum of 10,000 examples). The keys must be kept
private. It is a toolkit for watermarking your own model's output with your own keys. No source consulted says it
can detect watermarks in Gemini output, and it has nothing to do with images. Limits stated by Google: weaker on factual responses, and confidence drops after thorough rewriting or
translation.

---

## 7. Unofficial third-party claims

Every entry is **UNOFFICIAL / NOT VALIDATED**. None was inspected, executed or integrated. Claims are quoted or
paraphrased from each repository's own description (github.com, accessed 2026-10-05). Listing is not endorsement.
Removal and reverse-engineering tools are out of scope for SynthProvenance (see `docs/SYNTHID_RESEARCH_LAB.md`). They
matter only as a caveat: a "SynthID not detected" result can follow deliberate removal.

| Repository | Claim (repository's own wording, abridged) | Status |
|------------|-------------------------------------------|--------|
| https://github.com/Rinne414/SynthID-detector | Detect invisible watermarks in AI-generated images (SynthID, GPT-Image2, Nano Banana); runs in browser | UNOFFICIAL / NOT VALIDATED |
| https://github.com/newideas99/gpt-image-synthid-detector | CNN ensemble said to detect SynthID in ChatGPT / GPT-Image-2 images, "validated against the official verifier" | UNOFFICIAL / NOT VALIDATED |
| https://github.com/aloshdenny/reverse-SynthID | "Reverse engineering Gemini's SynthID detection"; spectral detector and bypass | UNOFFICIAL / NOT VALIDATED |
| https://github.com/MSanwiru411/Reverse-SynthID | "Reverse Engineering Gemini's SynthID Detection" | UNOFFICIAL / NOT VALIDATED |
| https://github.com/zDarkHaze/reverse-synthid | "reverse engineering Gemini's SynthID detection" | UNOFFICIAL / NOT VALIDATED |
| https://github.com/wiltodelta/remove-ai-watermarks | Remove visible and invisible AI watermarks and provenance metadata, including SynthID and C2PA | UNOFFICIAL / NOT VALIDATED |
| https://github.com/wiltodelta/ComfyUI-remove-ai-watermarks | ComfyUI nodes for detecting provenance marks and removing invisible AI watermarks | UNOFFICIAL / NOT VALIDATED |
| https://github.com/mertizci/noai-watermark | Remove invisible AI watermarks (SynthID, StableSignature, TreeRing) | UNOFFICIAL / NOT VALIDATED |
| https://github.com/froggeric/gemini-watermark-and-synthid-remover | Remove watermarks from Gemini, Veo and NotebookLM images and videos | UNOFFICIAL / NOT VALIDATED |
| https://github.com/0xROOTPLS/DeSynth | Remove SynthID from OpenAI and Google images ("SynthID Bypass") | UNOFFICIAL / NOT VALIDATED |
| https://github.com/obaskly/NeuralBleach | Remove invisible AI watermarks such as Google SynthID | UNOFFICIAL / NOT VALIDATED |
| https://github.com/BovineOverlord/Loyal-Bear---The-SynthID-Scrambler | "Automatically remove SynthID from any image" | UNOFFICIAL / NOT VALIDATED |
| https://github.com/satiricalguru/Synthid-remover | Remove AI watermarks, C2PA and "SynthID frequency signals" locally | UNOFFICIAL / NOT VALIDATED |
| https://github.com/denuwanpro/removebanana | Remove invisible AI watermarks from Gemini images (npm package) | UNOFFICIAL / NOT VALIDATED |
| https://github.com/doofzoff/pagedMark | "SynthID-class pixel regeneration" watermark removal for Apple Silicon | UNOFFICIAL / NOT VALIDATED |

Also tagged `synthid` on GitHub (https://github.com/topics/synthid) but without an explicit SynthID image claim in
the description: guillaumemeyer/watermarks-remover, PyModel/watermark-remover, lhfer/image-fingerprint-remover,
vctor03/noai-watermark, gconsigli/ai-watermarking (an own watermarker "that replicates SynthID's functionality"), and
the text-only projects ruvnet/ai-text-watermark and swaylq/humanize-chinese. Same status: UNOFFICIAL / NOT VALIDATED.

---

## 8. C2PA specification and binding concepts

### Current version

| Item | Value | Source (accessed 2026-10-05) |
|------|-------|--------|
| Current technical specification | **2.4**. Version history: "2.4 - April 2026". PDF creation date 2026-04-23. | https://spec.c2pa.org/specifications/specifications/2.4/specs/C2PA_Specification.html (the index https://spec.c2pa.org/specifications/ redirects to 2.4) |
| Previous | 2.3 (version history: "December 2025"; PDF title in search results dated 2026-01-05). 2.2 and earlier remain online. | https://spec.c2pa.org/specifications/specifications/2.3/specs/C2PA_Specification.html |
| Newer than 2.4 | None found (2.5 URLs return 404) | — |
| Companion documents in 2.4 | Content Credentials JSON (crJSON), Attestations, Soft Binding API, Explainer, Guidance for Implementers, UX Guidance, Security Considerations, Harms Modelling, AI/ML Guidance, Human and Organizational Identity Recommendation | https://spec.c2pa.org/specifications/specifications/2.4/index.html |

### Binding definitions (C2PA 2.4, section 2 and section 9)

- **Hard binding**: "One or more cryptographic hashes that uniquely identifies either the entire asset or a portion
  thereof." It lets a validator confirm that the manifest belongs to this asset and that the asset has not been
  modified. A manifest may contain at most one hard-binding assertion (data hash, general box hash for JPEG/PNG/GIF,
  BMFF hash, and similar).
- **Soft binding**: "A content identifier that is either (a) not statistically unique, such as a fingerprint, or
  (b) embedded as an invisible watermark in the identified digital content." It is computed from the content, not the
  raw bits, so it can match renditions. A manifest may contain zero or more. "A soft binding shall not be used as a
  hard binding."
- **Durable Content Credential**: "a Content Credential for which there exists one or more soft bindings that enable
  its discovery in a manifest repository."
- **Manifest repository**: a repository of C2PA manifests and manifest stores "which can be searched using a content
  binding."
- **Watermark actions**: `c2pa.watermarked.bound` (and the deprecated `c2pa.watermarked`) require a
  `c2pa.soft-binding` assertion in the same manifest, otherwise validation fails with
  `assertion.action.softBindingMissing`.

### Soft Binding API

- Document: https://spec.c2pa.org/specifications/specifications/2.4/softbinding/Decoupled.html
- Purpose: recover a C2PA manifest that has been stripped from, or replaced in, an asset, by decoding a watermark or
  computing a fingerprint and querying a manifest repository through the **Soft Binding Resolution API**. Also
  defines federated (decentralised) lookup.
- Algorithm list: https://github.com/c2pa-org/softbinding-algorithm-list (raw JSON read on 2026-10-05). It has 53
  entries, for example Digimarc Validate, Adobe TrustMark (Q, C, P), ISCC, Microsoft InvisMark and WavMark, Imatag,
  Steg.AI, and vendor deployments of Meta's PixelSeal and VideoSeal. **No SynthID or Google entry.**

### 2025-2026 changes relevant to labelling AI-generated images

- **digitalSourceType**: a gen-AI asset's `c2pa.created` action carries
  `http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia`. AI edits of existing content use
  `compositeWithTrainedAlgorithmicMedia`. C2PA adds `http://c2pa.org/digitalsourcetype/trainedAlgorithmicData` for
  non-media data output.
- **New in 2.4**:
  - `c2pa.ai-disclosure` assertion for machine-readable AI transparency. It adds model provenance, scientific routing
    metadata, and a `humanOversightLevel` (for example `fully_autonomous`, `prompt_guided`, `human_validated`). It
    complements `digitalSourceType` and does not replace it.
  - `c2pa.repository-receipt` assertion: proof that a manifest was ingested by a manifest repository.
  - `digitalSourceType` allowed in ingredient assertions for ingredients without their own manifest.
  - `c2pa.watermarked.bound` actions should reference their soft-binding assertions.
  - Soft-binding `alg` matching the algorithm list relaxed from "shall" to "should".
  - Manifests can be embedded in HTML and structured text.
  - `specVersion` moved into `claim_generator_info`.
- **New in 2.3**: live video streaming, fine-grained watermarking actions, the External Reference assertion.
- **CAWG (Creator Assertions Working Group, hosted by DIF)** (https://cawg.io/): Identity Assertion 1.3, Training and
  Data Mining Assertion 1.1 (DIF Ratified, 2025-05-16), Metadata Assertion 1.1.
  - The training-and-data-mining assertion has label `cawg.training-mining`, with entries such as
    `cawg.ai_generative_training`, `cawg.ai_training`, `cawg.ai_inference` and `cawg.data_mining`. It replaces the
    C2PA 1.x `c2pa.training-mining` definition (https://cawg.io/training-and-data-mining/1.1/).
  - It records whether an asset **may be used** for AI training. It does **not** label an asset as AI-generated.
- **Google signing**: Google model output is signed by Google LLC with "Google Media Processing Services" as the
  app/device (GCLOUD-CONTENT-CREDENTIALS).

---

## 9. C2PA tooling

| Tool | Latest version | Released | Licence | Notes | Source (accessed 2026-10-05) |
|------|----------------|----------|---------|-------|--------|
| c2patool (CLI) | 0.28.1 | 2026-09-28 | MIT OR Apache-2.0 | Now in its own repository. v0.27.15 and earlier were released from the c2pa-rs monorepo. Prebuilt Windows binary `c2patool-vX.Y.Z-x86_64-pc-windows-msvc.zip`. | https://github.com/contentauth/c2patool (latest release tag v0.28.1), https://crates.io/crates/c2patool |
| c2pa (c2pa-rs, Rust SDK) | 0.91.1 | 2026-09-27 | MIT OR Apache-2.0 | Beta (0.x). Implements "a subset" of C2PA spec 2.4 and the CAWG identity assertion. Requires Rust 1.96.0+. | https://github.com/contentauth/c2pa-rs, https://crates.io/crates/c2pa |
| c2pa-python | 0.38.0 | 2026-09-29 | MIT OR Apache-2.0 | Wheels for win_amd64 and win_arm64, macOS and manylinux. | https://github.com/contentauth/c2pa-python (latest release tag v0.38.0), https://pypi.org/project/c2pa-python/ |

---

## 10. Implications for SynthProvenance

- Keep `LOCAL SYNTHID ENGINE: UNAVAILABLE` as the default state. No legitimate local detector exists.
- Keep the Gemini app as the primary user-facing route. Open https://gemini.google.com/ (and the help page
  https://support.google.com/gemini/answer/16722517) only after explicit confirmation. Never upload automatically.
  Show the quota (about 10 image checks per 24 h), the 100 MB limit and the one-file rule before opening.
- Record Gemini results with the three official outcomes: detected / not detected / unclear. A "not detected" result
  means only "not made or edited by Google AI as far as Gemini can tell". It does not mean "not AI".
- Since May 2026, SynthID is no longer Google-only: OpenAI images (ChatGPT, Codex, API) carry SynthID and C2PA. But
  Gemini says it can recognise only content from Google AI tools. A SynthID-bearing OpenAI image may therefore read as
  "not detected" in Gemini. The record should allow a second, separately labelled check through OpenAI Verify
  (https://openai.com/verify), which covers OpenAI content only.
- Do not link Search, Lens or Chrome until an official help page with steps exists. Their status is announced but
  UNVERIFIED for desktop.
- Do not integrate the Google Cloud AI Content Detection API as a SynthID method. Its documentation describes a
  statistical classifier (pixel artifacts, noise, spectra) and does not mention SynthID. If ever used, it must be a
  separate "AI classifier" method, and it would need cloud upload, which conflicts with the local-first design.
- Keep C2PA and SynthID strictly separate. A C2PA soft binding is not SynthID, and SynthID is not in the C2PA
  soft-binding algorithm list. A Google or OpenAI C2PA manifest is a Content Credential statement, not a SynthID
  detection. Absence of C2PA never implies absence of SynthID.
- For C2PA labelling, read `digitalSourceType` (trainedAlgorithmicMedia, compositeWithTrainedAlgorithmicMedia) and the
  new `c2pa.ai-disclosure` assertion. Do not treat `cawg.training-mining` as an AI-generated label.
- Tooling targets: c2pa-python 0.38.0 / c2pa-rs 0.91.1 (spec 2.4 subset), c2patool 0.28.1. All are MIT OR Apache-2.0
  and have Windows builds.
- Third-party SynthID detectors and removers stay out of scope and listed as UNOFFICIAL / NOT VALIDATED. Removal tools
  exist, so "SynthID not detected" can also follow deliberate removal. Interpretation text should say so.
- Suggested updates to `config/synthid_sources.json` (not made in this revision):
  - change GCLOUD-AI-CONTENT-DETECTION from UNVERIFIED to VERIFIED, with relevance "classifier; SynthID not
    mentioned; Private Preview";
  - add GOOGLE-IO26-100, GOOGLE-SEARCH-IMAGE-DETAILS, GCLOUD-CONTENT-CREDENTIALS, SYNTHID-BIO,
    OPENAI-PROVENANCE-HELP, OPENAI-CONTENT-PROVENANCE-API, C2PA-SPEC-2.4, C2PA-SOFTBINDING-API,
    C2PA-SOFTBINDING-ALG-LIST, C2PATOOL and CAWG;
  - update the RINNE414 entry's relevance with its stated claim.

---

## 11. Change log vs 2026-10-02

| Area | Change |
|------|--------|
| AI Content Detection API | CHANGED: the page body was read in full. Pre-GA Private Preview; ML classifier for JPEG/PNG/WebP covering Google and third-party models; C2PA excluded; SynthID not mentioned. Previously "page body did not load; SynthID UNVERIFIED". |
| SynthID adopters | NEW: OpenAI (images from ChatGPT, Codex and the API carry SynthID and C2PA; audio carries SynthID), Kakao and ElevenLabs announced 2026-05-19. NVIDIA Cosmos (2025-05-20) and GetReal Security partnerships recorded. |
| Partner verification | NEW: OpenAI Verify (web) and the OpenAI Content Provenance API, both limited to OpenAI signals. |
| Gemini coverage | NEW: availability "across all languages and countries where the Gemini app operates" (2025-12-18 post). Gemini still recognises only content from Google AI tools. |
| Search / Chrome | UPDATED: the Search Help page now confirms SynthID can appear in image details. Desktop steps and the Chrome rollout remain UNVERIFIED. |
| SynthID Bio | NEW: announced 2026-09-30 (proteins). Not relevant to images. |
| SynthID-Image paper | UNCHANGED: still only v1 (2025-10-10). Full author list added (26 authors). |
| Local verification | UNCHANGED: UNAVAILABLE. NEW evidence: SynthID is absent from the C2PA soft-binding algorithm list. |
| SynthID Text | ADDED detail: PyPI `synthid-text` 0.2.1 (Apache-2.0); Bayesian detector must be trained per configuration. |
| C2PA specification | NEW: current version 2.4 (April 2026). Binding definitions, durable Content Credentials, Soft Binding API, `c2pa.ai-disclosure`, and CAWG `cawg.training-mining` documented. |
| C2PA tooling | NEW: c2patool 0.28.1 (separate repository). UNCHANGED: c2pa-rs 0.91.1 and c2pa-python 0.38.0. Licences confirmed as MIT OR Apache-2.0. |
| Third-party repositories | EXPANDED: one entry (Rinne414, "NOT EVALUATED") became 15 listed repositories plus 7 tagged ones, all UNOFFICIAL / NOT VALIDATED. |
| Vertex verify-watermark page | UNCHANGED: HTTP 404. |
| Datasets | UNCHANGED, not re-checked (section 12). |

---

## 12. Datasets (controls only; carried over from 2026-10-02, not re-checked)

None of these datasets contains SynthID-marked images. All are non-commercial (CC BY-NC-SA 4.0). In a benchmark they
can serve only as negative and other-generator controls.

- GenImage: https://github.com/GenImage-Dataset/GenImage
- Synthbuster: https://zenodo.org/records/10066460
- CNNDetection / ForenSynths: https://github.com/peterwang512/CNNDetection

---

## 13. Source index

| ID | Kind | Status | Accessed | URL |
|----|------|--------|----------|-----|
| DEEPMIND-SYNTHID | OFFICIAL | VERIFIED | 2026-10-05 | https://deepmind.google/models/synthid/ |
| GOOGLE-SYNTHID-DETECTOR | OFFICIAL | VERIFIED | 2026-10-05 | https://blog.google/innovation-and-ai/products/google-synthid-ai-content-detector/ |
| SYNTHID-DETECTOR-ONBOARDING | OFFICIAL | VERIFIED | 2026-10-05 | https://docs.google.com/forms/d/1KAkSpRixcGi7pKaPyw5FyahaQqpawmNq65gHgBWgFjg/viewform |
| SYNTHID-DETECTOR-WAITLIST | OFFICIAL | VERIFIED (closed) | 2026-10-05 | https://docs.google.com/forms/d/e/1FAIpQLSfAYrauHmY-PpUNxL4Fs6coa185CtKWp7TnEXL0tKbAezo4MQ/viewform |
| GOOGLE-GEMINI-IMAGE-VERIFY | OFFICIAL | VERIFIED | 2026-10-05 | https://blog.google/innovation-and-ai/products/ai-image-verification-gemini-app/ |
| GOOGLE-GEMINI-VIDEO-VERIFY | OFFICIAL | VERIFIED | 2026-10-05 | https://blog.google/technology/ai/verify-google-ai-videos-gemini-app/ |
| GOOGLE-GEMINI-HELP | OFFICIAL | VERIFIED | 2026-10-05 | https://support.google.com/gemini/answer/16722517 |
| GOOGLE-GEMINI-APP | OFFICIAL | VERIFIED | 2026-10-05 | https://gemini.google.com/ |
| NANO-BANANA-2 | OFFICIAL | VERIFIED | 2026-10-05 | https://blog.google/innovation-and-ai/technology/ai/nano-banana-2/ |
| GOOGLE-IO26-PROVENANCE | OFFICIAL | VERIFIED | 2026-10-05 | https://blog.google/innovation-and-ai/products/identifying-ai-generated-media-online/ |
| GOOGLE-IO26-100 | OFFICIAL | VERIFIED | 2026-10-05 | https://blog.google/innovation-and-ai/technology/ai/google-io-2026-all-our-announcements/ |
| GOOGLE-SEARCH-IMAGE-DETAILS | OFFICIAL | VERIFIED | 2026-10-05 | https://support.google.com/websearch/answer/9789430 |
| GCLOUD-AI-CONTENT-DETECTION | OFFICIAL | VERIFIED | 2026-10-05 | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/ai-content-detection |
| GCLOUD-CONTENT-CREDENTIALS | OFFICIAL | VERIFIED | 2026-10-05 | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/content-credentials |
| VERTEX-VERIFY-WATERMARK | OFFICIAL | OUTDATED (404) | 2026-10-05 | https://docs.cloud.google.com/vertex-ai/generative-ai/docs/image/verify-watermark |
| GEMINI-API-IMAGE-GEN | OFFICIAL | VERIFIED | 2026-10-05 | https://ai.google.dev/gemini-api/docs/image-generation |
| WORKSPACE-AI-LABELS | OFFICIAL | VERIFIED | 2026-10-02 | https://support.google.com/docs/answer/17560328 |
| SYNTHID-BIO | OFFICIAL | VERIFIED | 2026-10-05 | https://blog.google/innovation-and-ai/models-and-research/google-deepmind/synthid-bio/ |
| ARXIV-2510.09263 | PAPER | VERIFIED | 2026-10-05 | https://arxiv.org/abs/2510.09263 |
| SYNTHID-TEXT | OPEN SOURCE | VERIFIED | 2026-10-05 | https://github.com/google-deepmind/synthid-text |
| SYNTHID-TEXT-PYPI | OPEN SOURCE | VERIFIED | 2026-10-05 | https://pypi.org/project/synthid-text/ |
| SYNTHID-TEXT-DOCS | OFFICIAL | VERIFIED | 2026-10-05 | https://ai.google.dev/responsible/docs/safeguards/synthid |
| HF-SYNTHID-TEXT-BLOG | OFFICIAL | VERIFIED | 2026-10-05 | https://huggingface.co/blog/synthid-text |
| HF-TRANSFORMERS-GENERATION-UTILS | OFFICIAL | VERIFIED | 2026-10-05 | https://huggingface.co/docs/transformers/main/en/internal/generation_utils |
| OPENAI-PROVENANCE-HELP | PARTNER | VERIFIED | 2026-10-05 | https://help.openai.com/en/articles/8912793 |
| OPENAI-CONTENT-PROVENANCE-API | PARTNER | VERIFIED | 2026-10-05 | https://developers.openai.com/api/docs/guides/content-provenance |
| OPENAI-ADVANCING-PROVENANCE | PARTNER | SEEN IN SEARCH ONLY (HTTP 403) | 2026-10-05 | https://openai.com/index/advancing-content-provenance/ |
| OPENAI-VERIFY | PARTNER | REFERENCED BY FETCHED OPENAI PAGES (HTTP 403) | 2026-10-05 | https://openai.com/verify |
| C2PA-SPEC-2.4 | STANDARD | VERIFIED | 2026-10-05 | https://spec.c2pa.org/specifications/specifications/2.4/specs/C2PA_Specification.html |
| C2PA-SPEC-INDEX-2.4 | STANDARD | VERIFIED | 2026-10-05 | https://spec.c2pa.org/specifications/specifications/2.4/index.html |
| C2PA-SOFTBINDING-API | STANDARD | VERIFIED | 2026-10-05 | https://spec.c2pa.org/specifications/specifications/2.4/softbinding/Decoupled.html |
| C2PA-SOFTBINDING-ALG-LIST | STANDARD | VERIFIED | 2026-10-05 | https://github.com/c2pa-org/softbinding-algorithm-list |
| CAWG | STANDARD | VERIFIED | 2026-10-05 | https://cawg.io/ |
| CAWG-TDM-1.1 | STANDARD | VERIFIED | 2026-10-05 | https://cawg.io/training-and-data-mining/1.1/ |
| C2PATOOL | STANDARD TOOL | VERIFIED | 2026-10-05 | https://github.com/contentauth/c2patool |
| C2PA-RS | STANDARD TOOL | VERIFIED | 2026-10-05 | https://github.com/contentauth/c2pa-rs |
| C2PA-PYTHON | STANDARD TOOL | VERIFIED | 2026-10-05 | https://github.com/contentauth/c2pa-python |
| GENIMAGE | DATASET | VERIFIED | 2026-10-02 | https://github.com/GenImage-Dataset/GenImage |
| SYNTHBUSTER | DATASET | VERIFIED | 2026-10-02 | https://zenodo.org/records/10066460 |
| CNNDETECTION | DATASET | VERIFIED | 2026-10-02 | https://github.com/peterwang512/CNNDetection |
| GITHUB-TOPIC-SYNTHID | THIRD-PARTY INDEX | UNOFFICIAL / NOT VALIDATED | 2026-10-05 | https://github.com/topics/synthid |
| RINNE414-SYNTHID-DETECTOR | THIRD-PARTY | UNOFFICIAL / NOT VALIDATED | 2026-10-05 | https://github.com/Rinne414/SynthID-detector |

Researchers can add entries in `<workspace>/synthid_sources.json` using the same schema as
`config/synthid_sources.json`. Invalid entries are excluded and listed with the reason.
