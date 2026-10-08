# PAM licence register

Owner: Oversight agent (`docs/OVERSIGHT_*.md`, this file). First version 2026-10-08
(CP2). This register is machine-read, row by row. `server/memory_app.py:176-184`
(`licence_verified`) reports `licence_recorded` for a manifest asset only when one
line of this file names the asset's **base file name** together with the literal
`VERIFIED-COMMERCIAL` token and carries neither `UNVERIFIED` nor `REJECTED`;
`scripts/fetch_models.py:129-136` (`check_pin`) applies the same rule and also
requires the pin's licence identifier (e.g. `Apache-2.0`) on that same line. So every
asset row below carries exactly one `status:` token on the same line as the file
name, and the words UNVERIFIED and REJECTED are never written on a verified row.

This is a provenance and permission register, not legal advice. "Verified" means
the Oversight agent fetched the named primary source on the stated date and read
the licence text or statement there. It does not mean counsel has reviewed it.

## How to read the columns

| Column | Meaning |
| --- | --- |
| Kind | runtime dep (imported by the served app), dev dep (tests/tools only), legacy dep (declared, not imported by `server/memory_app.py`), model weights, dataset, browser asset |
| Version pinned | exact version the register clears; "recommend" where the pin file still has `null` |
| Licence (SPDX) | the identifier as found at the primary source |
| Primary source URL | what was actually fetched (or the exact URL a human must open) |
| Commercial use / Redistribution | can we use it in a paid product; can we ship the bytes to customers |
| Verified | `oversight agent, fetched <date>` or `UNVERIFIED` with the reason |
| Notes/obligations | notices, attribution, upstream-data caveats |

Fetch method on 2026-10-08: `raw.githubusercontent.com`, `registry.npmjs.org` and
`pypi.org` were reachable directly from the sandbox (bytes downloaded and hashed);
`developers.google.com`, `purl.stanford.edu`, `data.bris.ac.uk`,
`express-licences.bristol.ac.uk` and `ultralytics.com` were read through the
WebFetch tool (text extracted, not hashed); `storage.googleapis.com`,
`huggingface.co`, `tfhub.dev`, `kaggle.com`, `arxiv.org`, `cdla.dev`,
`ai.meta.com` and `epic-kitchens.github.io` were **not reachable** (egress policy
HTTP 403 on CONNECT). Rows that depend on an unreachable host say UNVERIFIED.

## Rules: before any dependency or model is added

1. **Register first, code second.** A new runtime dependency, npm package, model
   weight, dataset or browser asset gets a row here (with a primary-source URL and a
   `status:` token) *before* it is imported, pinned or fetched. `scripts/fetch_models.py`
   refuses an asset whose base file name has no `VERIFIED-COMMERCIAL` row
   (`scripts/fetch_models.py:129-134`) or whose licence identifier is missing from
   that row (`:135-136`); a `null` `url` or `sha256` in `scripts/model_pins.json` is
   also a refusal (`:123-128`). Nothing is ever downloaded at app start or by a test.
2. **Status tokens.** Every asset row carries exactly one `status:` token:
   VERIFIED-COMMERCIAL (Oversight fetched the primary source and it permits
   commercial use and redistribution of what we ship), or UNVERIFIED (primary not
   read), or REJECTED. The server (`licence_verified`) and the fetch script
   (`check_pin`) treat a row as a grant only when it carries the first token and
   neither of the other two; the second and third words therefore never appear on
   a verified row, not even in a note. An unverified asset additionally keeps
   `sha256: null` in `scripts/model_pins.json` (second, independent refusal).
3. **Separate the grants.** Code licence, weight/model grant, training-data terms
   and required notices are recorded separately (`docs/RESEARCH_EVIDENCE.md`,
   "Register fields"). A repository `LICENSE` does not cover weights hosted
   outside the repository (the MediaPipe `.task` is the live example).
4. **Primary sources only.** A mirror, a model zoo, a package badge or a peer
   report is not verification. Registry metadata (`license` in npm/PyPI JSON) is
   the publisher's declaration and is recorded as such, with the licence text
   fetched from the publisher's repository.
5. **Never**: AGPL/GPL/NC/research-only code or weights on the product path
   (table 6); `ultralytics` or its `CLIP` fork as an import; checkpoints from a
   repository section with a different licence than the main model (DINOv2's
   XRay-DINO and Cell-DINO); "latest" URLs as pins; converted copies as a licence
   cure (RESEARCH_LOG C-03).
6. **Notices.** Every shipped third-party component listed as `VERIFIED-COMMERCIAL`
   needs its licence text and copyright line in a third-party-notices page of the
   served app (none exists yet; see `docs/OVERSIGHT_CP2.md` §2). Apache-2.0
   components also need any upstream `NOTICE` file reproduced; the tasks-vision npm
   tarball ships no `LICENSE`/`NOTICE` file, so the MediaPipe repository `LICENSE`
   is the text to ship.

## 1. Python runtime dependencies actually imported by the served app

Import graph of `server/memory_app.py` on 2026-10-08: `fastapi`, `starlette`
(`server/memory_app.py:16-18`), `perception.object_memory` -> `pydantic`
(`perception/object_memory.py:15`, `perception/episode.py:10`,
`perception/localizer.py:5`), `cv2` and `numpy` lazily inside `perception/episode.py:112-113`
and `perception/localizer.py:46-47`, `numpy` in `perception/motion.py:33`; `uvicorn`
only under `__main__` (`server/memory_app.py:638`). **Not imported by the served app:**
`httpx` (only legacy `server/app.py:41`), `anthropic` (only legacy `perception/vlm.py:11`),
`elasticsearch`, `icalendar`, `python-dateutil`, `google-auth-oauthlib` (declared in
`server/requirements.txt`, unused by `memory_app`), everything in
`perception/requirements.txt` except `opencv-python`, `pydantic`, `numpy`.

Versions below are the ones installed in the CP2 review sandbox (where the suites
ran green) and the latest on PyPI on 2026-10-08; `server/requirements.txt` carries no
pins at all, which is itself a finding.

| Component | Kind | Version pinned | Licence (SPDX) | Primary source URL (fetched) | Commercial use | Redistribution of what we ship | Verified | Notes/obligations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fastapi | runtime dep | 0.142.4 (sandbox; PyPI latest 0.142.4, 2026-10-07) | MIT | https://raw.githubusercontent.com/fastapi/fastapi/master/LICENSE ; PyPI JSON `license_expression: MIT` | Yes | Yes (server side; not shipped to the phone) | oversight agent, fetched 2026-10-08 | MIT notice. `status: VERIFIED-COMMERCIAL` |
| starlette | runtime dep | 1.6.0 (sandbox; PyPI latest 1.7.0, 2026-09-23) | BSD-3-Clause | https://raw.githubusercontent.com/Kludex/starlette/main/LICENSE.md ; PyPI `BSD-3-Clause` | Yes | Yes | oversight agent, fetched 2026-10-08 | BSD notice (Encode OSS Ltd). `status: VERIFIED-COMMERCIAL` |
| uvicorn | runtime dep (process host) | 0.53.0 (sandbox; PyPI latest 0.54.0, 2026-09-25) | BSD-3-Clause | https://raw.githubusercontent.com/Kludex/uvicorn/master/LICENSE.md ; PyPI `BSD-3-Clause` | Yes | Yes | oversight agent, fetched 2026-10-08 | `uvicorn[standard]` pulls `httptools` (MIT), `uvloop` (MIT/Apache-2.0), `watchfiles` (MIT), `websockets` (BSD-3-Clause), `python-dotenv` (BSD-3-Clause), `pyyaml` (MIT): declared-by-publisher only, not fetched; the sandbox ran without `httptools`/`uvloop`/`watchfiles`/`websockets` installed. Plain `uvicorn` is enough for the rig. `status: VERIFIED-COMMERCIAL` |
| pydantic | runtime dep | 2.13.5 (sandbox = PyPI latest, 2026-08-28) | MIT | https://raw.githubusercontent.com/pydantic/pydantic/main/LICENSE ; PyPI `MIT` | Yes | Yes | oversight agent, fetched 2026-10-08 | MIT notice. `status: VERIFIED-COMMERCIAL` |
| pydantic-core | runtime dep (transitive) | 2.46.5 (sandbox; PyPI latest 2.49.0) | MIT | same repository as pydantic; PyPI `license_expression: MIT` | Yes | Yes | PyPI metadata only, 2026-10-08 (repo text not separately fetched) | `status: VERIFIED-COMMERCIAL` (publisher declaration + pydantic repo LICENSE) |
| numpy | runtime dep | 2.5.3 (sandbox = PyPI latest, 2026-09-06) | BSD-3-Clause (wheel bundles 0BSD, MIT, Zlib, CC0-1.0 components per PyPI `license_expression`) | https://raw.githubusercontent.com/numpy/numpy/main/LICENSE.txt ; PyPI JSON | Yes | Yes | oversight agent, fetched 2026-10-08 | BSD notice; bundled OpenBLAS/other notices travel in the wheel's `LICENSE` files. `status: VERIFIED-COMMERCIAL` |
| opencv-python-headless | runtime dep (**recommended** replacement for `opencv-python`) | 5.0.0.93 (sandbox = PyPI latest, 2026-07-02) | MIT (packaging scripts) + Apache-2.0 (OpenCV) + LGPL-2.1 (bundled FFmpeg) | https://raw.githubusercontent.com/opencv/opencv-python/4.x/README.md L195-207 ; https://raw.githubusercontent.com/opencv/opencv-python/4.x/LICENSE.txt ; https://raw.githubusercontent.com/opencv/opencv/4.x/LICENSE | Yes | Yes, with LGPL-2.1 compliance for the FFmpeg shared libraries in the wheel (notice + licence text + the user's ability to replace the library; the wheel links FFmpeg dynamically) | oversight agent, fetched 2026-10-08 | README L203: "All wheels ship with FFmpeg licensed under the LGPLv2.1." README L205: "Non-headless Linux wheels ship with Qt 5 licensed under the LGPLv3." Use the **headless** wheel on the server to avoid Qt/LGPL-3.0 and X11. Third-party list: https://github.com/opencv/opencv-python/blob/master/LICENSE-3RD-PARTY.txt (not fetched). `status: VERIFIED-COMMERCIAL` |
| opencv-python (currently declared, `perception/requirements.txt`) | legacy dep (what `cv2` resolves to today) | 5.0.0.93 | as above plus LGPL-3.0 Qt 5 on Linux wheels | as above | Yes | Yes but adds LGPL-3.0 Qt obligations on Linux | oversight agent, fetched 2026-10-08 | Replace with `opencv-python-headless` in the served requirements (coordinator decision; purge list in handoff §9 step 0). `status: VERIFIED-COMMERCIAL` |
| httpx | legacy dep (declared in `server/requirements.txt`; imported only by `server/app.py:41`) | 0.28.1 (sandbox = PyPI latest, 2024-12-06) | BSD-3-Clause | https://raw.githubusercontent.com/encode/httpx/master/LICENSE.md | Yes | Yes | oversight agent, fetched 2026-10-08 | Not imported by `memory_app`; keep only if a cloud-chat provider adapter later needs it. `status: VERIFIED-COMMERCIAL` |
| anthropic (Python SDK) | legacy dep (declared in `perception/requirements.txt`; imported only by `perception/vlm.py:11`) | 1.12.0 (sandbox; PyPI latest 1.12.1, 2026-10-08) | MIT | https://raw.githubusercontent.com/anthropics/anthropic-sdk-python/main/LICENSE | Yes (SDK) | Yes (SDK code); API use is governed by Anthropic's commercial terms, not this licence | oversight agent, fetched 2026-10-08 | **Not imported by `server/memory_app.py`** (checked 2026-10-08). The licence covers the SDK only; any paid provider call remains a separate bounded-cost checkpoint (BUILD_CONTRACT). `status: VERIFIED-COMMERCIAL` |
| anyio, h11, click, typing-extensions, annotated-types, idna, sniffio | runtime deps (transitive of fastapi/starlette/uvicorn/pydantic) | 4.15.1, 0.16.0, 8.5.0, 4.16.0, 0.8.0, 3.20, 1.3.1 (sandbox) | MIT, MIT, BSD-3-Clause, PSF-2.0, MIT, BSD-3-Clause, MIT OR Apache-2.0 | PyPI JSON `license_expression` for each, 2026-10-08 | Yes | Yes | PyPI metadata only (publisher declaration), 2026-10-08 | All permissive; licence texts to be collected into the notices page when it is built. `status: VERIFIED-COMMERCIAL` (declaration-level) |

Dev/test-only: Playwright (Apache-2.0, not yet declared anywhere; the tester's
`phone/test/test_ui_smoke.py` needs it) and Node 22 (MIT) for `controller-replay.mjs`.
Neither ships. Add a row when the tester records the exact version.

## 2. Browser assets served from our origin (CP2)

The hand worker (`phone/assets/hand-worker.js:105-156`) loads exactly these files
from `/assets/models/` and nothing else; the server serves them only when
`MANIFEST.json` lists them and `PAM_ENABLE_HAND_MODEL=1` (`server/memory_app.py:599-620`).

### 2a. `@mediapipe/tasks-vision` (JS + WASM runtime)

Both versions below were downloaded from `registry.npmjs.org` on 2026-10-08 and
verified against the registry's `dist.integrity`/`shasum`; every file inside was
hashed. Package `license` field: `Apache-2.0` (both). The tarball contains **no
LICENSE or NOTICE file**: `README.md`, `package.json`, `vision.d.ts`, the three
bundles with source maps and the `wasm/` directory only. The licence text to ship is
the MediaPipe repository `LICENSE` (Apache-2.0, 218 lines, fetched from
https://raw.githubusercontent.com/google-ai-edge/mediapipe/master/LICENSE, SHA-256
`8707eef0533987efc5b155d64761eeb6e20793f50b9bd1a68dad1cf4719d0ed8`).

**Telemetry (obligation).** `vision_bundle.mjs` (both versions) contains a metrics
logger that POSTs protobuf to `https://odml.pa.googleapis.com/v1/log` every 60 s
(`setInterval(... 6e4)`, header `x-goog-api-key`), with no public opt-out in
`vision.d.ts`. The package README, "Privacy Notice" (last modified 2026-06-05):
"MediaPipe Tasks APIs send metrics about the performance and utilization of the APIs
in your app to Google ... **You are responsible for obtaining informed consent from
your app users about Google's processing of MediaPipe metrics data as required by
applicable law.**" Input frames stay on device per the same notice. PAM's CSP
`connect-src 'self'` (`server/memory_app.py:385`) blocks that POST in the worker; the
tester's no-egress assertion must cover the worker path once assets exist
(`docs/OVERSIGHT_CP2.md` §1). The notice obligation is recorded here regardless.

**Pin recommendation (B-06 / D-014): 1.0.1.** Published 2026-07-31 (A-020), older
than the handoff's 7-day rule by two months; identical README/licence to 1.1.0; the
1.1.0 release (2026-10-06) is two days old at review time. Switching later is a pin
change in `scripts/model_pins.json` plus a re-fetch; both file sets are recorded below
so no new verification is needed for the switch.

| Component | Kind | Version pinned | Licence (SPDX) | Primary source URL (fetched) | Commercial use | Redistribution of what we ship | Verified | Notes/obligations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `@mediapipe/tasks-vision` package | browser asset (runtime) | **1.0.1** (recommend; pins file has `null`) | Apache-2.0 | https://registry.npmjs.org/@mediapipe/tasks-vision/1.0.1 (tarball https://registry.npmjs.org/@mediapipe/tasks-vision/-/tasks-vision-1.0.1.tgz, shasum `7ab992e2415d48e526934abd6390ffc208699fb1`, integrity `sha512-rvRE2FmAZ6ZxKSw7wq+e+jQDpN3t1B/tD2mJz9SmAzb1msoDkd4dMoE4wAh8Z30Um0PQwLiHr9QtomhmXk3aUQ==`, tarball SHA-256 `ee318eaa3d42230aa10910d114faf2a488c577c4e4d33c7cb04126924aca505f`); licence text https://raw.githubusercontent.com/google-ai-edge/mediapipe/master/LICENSE | Yes | Yes, from our origin, with the Apache-2.0 text and Google copyright in the notices page | oversight agent, fetched 2026-10-08 (package bytes verified against registry integrity) | Telemetry obligation above. `status: VERIFIED-COMMERCIAL` |
| `vision_bundle.mjs` | browser asset | 1.0.1 | Apache-2.0 | in the 1.0.1 tarball, path `package/vision_bundle.mjs` (155,439 bytes) | Yes | Yes | oversight agent, fetched 2026-10-08 | SHA-256 `d885630c297c0b20b1fe86096cb06291c4c8080876f27852e724f24ac603713f`. Contains the odml logger (blocked by CSP). `status: VERIFIED-COMMERCIAL` |
| `vision_wasm_internal.js` | browser asset | 1.0.1 | Apache-2.0 | tarball path `package/wasm/vision_wasm_internal.js` (323,377 bytes) | Yes | Yes | oversight agent, fetched 2026-10-08 | SHA-256 `e170ee67dd4e16c1a6fcd8840a206687e5a59b22c20e4a902bc445b095454d73`. Emscripten glue; no network URLs other than documentation links. `status: VERIFIED-COMMERCIAL` |
| `vision_wasm_internal.wasm` | browser asset | 1.0.1 | Apache-2.0 | tarball path `package/wasm/vision_wasm_internal.wasm` (11,756,954 bytes) | Yes | Yes | oversight agent, fetched 2026-10-08 | SHA-256 `8da277a733926eacd0474b8704b36742d6ec3231c57a860c5b889dff8f1df886`. `status: VERIFIED-COMMERCIAL` |
| `vision_wasm_nosimd_internal.js` | browser asset (optional fallback) | 1.0.1 | Apache-2.0 | tarball path `package/wasm/vision_wasm_nosimd_internal.js` (323,180 bytes) | Yes | Yes | oversight agent, fetched 2026-10-08 | SHA-256 `e81d715a3d42cc3373602eb2f7aff795d164934db680e32496b65dab537f9658`. `status: VERIFIED-COMMERCIAL` |
| `vision_wasm_nosimd_internal.wasm` | browser asset (optional fallback) | 1.0.1 | Apache-2.0 | tarball path `package/wasm/vision_wasm_nosimd_internal.wasm` (10,960,242 bytes) | Yes | Yes | oversight agent, fetched 2026-10-08 | SHA-256 `a28483cd42e74e855bf5ebdb6b40d9b66a5b49e35e95020bc97669e6822a3192`. `status: VERIFIED-COMMERCIAL` |
| `@mediapipe/tasks-vision` 1.1.0 (recorded, **not** the recommended pin) | browser asset | 1.1.0 | Apache-2.0 | https://registry.npmjs.org/@mediapipe/tasks-vision/1.1.0 (shasum `282102e87c53034254974ced8f772c626a6c3496`, integrity `sha512-ZJqh0wMKOINorfSffvDAxzyO1//c+FiG3IkzOdNDnLqvBB3DbMfj0bB/tys2SNf9S914sgoIbIpF4HTOi336cg==`, tarball SHA-256 `46fc3d3d13fa5de631915929d045be2f74bb32e909d7a5b3a322b28976f54165`) | Yes | Yes | oversight agent, fetched 2026-10-08 | File SHA-256: `vision_bundle.mjs` `9d5fc9ef74b22329cf9aa88dc543956d192b8c254210b187271614713eb5b10c` (156,135 B); `wasm/vision_wasm_internal.js` `7c652617b5bef832f42878ce8c5f752b0724bca6054e4bc1013a37d4b1949723` (335,393 B); `wasm/vision_wasm_internal.wasm` `782eda3ec1f414fdb4f1d66a8b59093eb4d5ab437e06117796abf05962d68eef` (12,997,248 B); `wasm/vision_wasm_nosimd_internal.js` `510fc70a170eb8b46767a7abab2af89a7a8341fa5b3ebfb8a5de41a79b7fa9df` (335,196 B); `wasm/vision_wasm_nosimd_internal.wasm` `b802041d105876865d6a0806f2ff7c4419a7f1b80bc01340fe36e759c2030011` (12,168,316 B). Same README, same telemetry endpoint. `status: VERIFIED-COMMERCIAL` (licence); not benchmarked (C-08) |

The tarballs also contain `vision_bundle.cjs`, `vision_bundle.js`, the two `.map`
files and `wasm/vision_wasm_module_internal.{js,wasm}`; PAM does not serve them and
they are not pinned.

### 2b. MediaPipe Hand Landmarker model bundle

| Component | Kind | Version pinned | Licence (SPDX) | Primary source URL | Commercial use | Redistribution of what we ship | Verified | Notes/obligations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hand_landmarker.task` (MediaPipe Hand Landmarker, "HandLandmarker (full)", float16) | model weights (browser asset) | `float16/1` (pins file; the developers page links `float16/latest`, which is not a pin) | **UNVERIFIED** (pins file says `Apache-2.0`; not confirmed at any primary source) | Canonical artifact URL: https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task . Primary model card (the licence statement lives here): https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Hand%20Tracking%20(Lite_Full)%20with%20Fairness%20Oct%202021.pdf (linked as "Model Card: info" from https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker, read 2026-10-08) | **Not yet established.** The developers page states only that page content is CC BY 4.0 and code samples are Apache 2.0; it "says nothing about the licensing of the hand_landmarker.task model bundle itself" (WebFetch extraction, 2026-10-08). The weights are **not** in the Apache-2.0 repository: `mediapipe/modules/hand_landmark/*.tflite` return 404 on `raw.githubusercontent.com`; `docs/solutions/models.md` links them on `storage.googleapis.com` and the model card via `https://mediapipe.page.link/handmc` | Not until verified | **UNVERIFIED**: `storage.googleapis.com` denied at the sandbox egress (HTTP 403 on CONNECT, curl and WebFetch, 2026-10-08); `tfhub.dev/mediapipe/handskeleton/1` and `kaggle.com/models/mediapipe/hand-landmark-detection` also unreachable. SHA-256 of the `.task` **not obtained** (same denial); nothing is invented | Training data per the developers page (verbatim): "The model was trained on approximately 30K real-world images" "as well as several rendered synthetic hand models imposed over various backgrounds." Human action: open the model card PDF above, transcribe its licence line verbatim into this row, then download the `/float16/1/` artifact on the laptop and record its SHA-256 (`docs/OVERSIGHT_CP2.md` §2 gives the commands). Until then `scripts/model_pins.json` keeps `url: null, sha256: null` for this entry, which makes `scripts/fetch_models.py` refuse it (`:117`, `:120`). `status: UNVERIFIED` |

## 3. Planned CP3+ components (not in CP2; verified now so CP3 does not stall)

| Component | Kind | Version pinned | Licence (SPDX) | Primary source URL (fetched) | Commercial use | Redistribution of what we ship | Verified | Notes/obligations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DINOv2 ViT-S/14 (`dinov2_vits14`, weights `dinov2_vits14_pretrain.pth`; optional `dinov2_vits14_reg4_pretrain.pth`) | model weights + code | not pinned (CP3; pin the `dl.fbaipublicfiles.com/dinov2/dinov2_vits14/...` file by SHA-256 at fetch) | Apache-2.0 (code and weights) | https://raw.githubusercontent.com/facebookresearch/dinov2/main/LICENSE (Apache-2.0 text); README L658-660: "DINOv2 code and model weights are released under the Apache License 2.0."; MODEL_CARD.md L32: "**License:** Apache License 2.0" | Yes | Yes | oversight agent, fetched 2026-10-08 | **History:** the April-2023 release was CC-BY-NC-4.0 and was relicensed to Apache-2.0 later in 2023; the current primary texts (above) are Apache-2.0 and that is what this row relies on. The relicensing commit itself was not fetched (GitHub API is blocked here); anyone pinning must pin from the current `main`. **Trap in the same repository:** README L159-160 (XRay-DINO) "Model weights are released under the FAIR Noncommercial Research License" and L754-757 (Cell-DINO) "Code is released under the CC BY NC License ... Model weights are released under the FAIR Noncommercial Research License". Never pull those checkpoints. Training data LVD-142M is not redistributed and no terms flow to weight users (MODEL_CARD). `status: VERIFIED-COMMERCIAL` |
| SigLIP 2 release terms (Google Research `big_vision`, covers code and the released SigLIP 2 materials) | model weights + code | not pinned (CP3) | Apache-2.0 (software); CC-BY-4.0 (other materials) | https://raw.githubusercontent.com/google-research/big_vision/main/LICENSE (Apache-2.0) ; https://raw.githubusercontent.com/google-research/big_vision/main/big_vision/configs/proj/image_text/README_siglip2.md L51-55: "All software is licensed under the Apache License, Version 2.0 ... All other materials are licensed under the Creative Commons Attribution 4.0 International License (CC-BY)." | Yes | Yes, with Apache-2.0 notice and CC-BY attribution for the checkpoint if it is treated as "other materials" | oversight agent, fetched 2026-10-08 | Training data WebLI (Google-internal, not released). `status: VERIFIED-COMMERCIAL` |
| SigLIP 2 Hugging Face checkpoint card (`google/siglip2-base-patch16-256`, the exact files CP3 would pin) | model weights (distribution point) | not pinned (CP3; record the HF revision hash at pin time) | expected `apache-2.0` tag, not read | https://huggingface.co/google/siglip2-base-patch16-256 (`huggingface.co` unreachable from the sandbox, 2026-10-08) | Not until the card is read | Not until the card is read | A human must open the card and confirm the licence tag and that no gating/terms acceptance applies to the checkpoint | Row exists so the CP3 pin cannot proceed on the release README alone. `status: UNVERIFIED` |
| SAM 2.1 (`sam2.1_hiera_tiny.pt`, `sam2.1_hiera_small.pt`) | model weights + code | not pinned (CP3 candidate proposer; teacher tier) | Apache-2.0 | https://raw.githubusercontent.com/facebookresearch/sam2/main/LICENSE ; README L198: "The SAM 2 model checkpoints, SAM 2 demo code (front-end and back-end), and SAM 2 training code are licensed under Apache 2.0"; README L23-26 and L68 list the SAM 2.1 checkpoints (e.g. https://dl.fbaipublicfiles.com/segment_anything_2/092824/sam2.1_hiera_tiny.pt) from the same repository | Yes | Yes | oversight agent, fetched 2026-10-08 | Weights trained by the dataset licensor (Meta, SA-V) and released by it: no third-party dataset term upstream. Demo fonts (OFL) and `cc_torch` (own licence) are not used. Preferred over RepViT-SAM on provenance. `status: VERIFIED-COMMERCIAL` |
| RepViT-SAM (`repvit_sam.pt` from the THU-MIG/RepViT v1.0 GitHub release) | model weights + code | not pinned (CP3 fallback proposer) | Apache-2.0 (repository; the release asset carries no separate licence) | https://raw.githubusercontent.com/THU-MIG/RepViT/main/LICENSE (Apache-2.0 text) ; https://raw.githubusercontent.com/THU-MIG/RepViT/main/sam/README.md L28 (download from the repo release) | Yes under the authors' grant | Yes | oversight agent, fetched 2026-10-08 | Provenance caveat: distilled from SAM, trained on SA-1B, which Meta licenses for research only per the COMMERCIAL review (https://ai.meta.com/datasets/segment-anything/ was not reachable from the sandbox, so that dataset page is peer-reported, not re-read). Whether a dataset licence reaches third-party distilled weights is contested; prefer SAM 2.1 where latency allows (COMMERCIAL review, accepted). `status: VERIFIED-COMMERCIAL` |
| PaddleOCR PP-OCRv5 mobile (det + rec) | model weights + code | not pinned (CP3/CP5 OCR; PyPI `paddleocr` 3.7.0, 2026-06-11, `Apache License 2.0`; `paddlepaddle` 3.3.1 `Apache Software License`) | Apache-2.0 | https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/LICENSE (Apache-2.0 text) ; README L280-281: "This project is released under the Apache 2.0 license" | Yes | Yes | oversight agent, fetched 2026-10-08 | Weights are "released with the project"; the exact model files (`PP-OCRv5_mobile_det`, `en_PP-OCRv5_mobile_rec`) have no separate licence file; record their download URL and SHA-256 at pin time. The PaddlePaddle runtime is a heavy dependency; ONNX export via ONNX Runtime is the lighter path. `status: VERIFIED-COMMERCIAL` |
| ONNX Runtime (`onnxruntime`, and `onnxruntime-web` if a browser experiment happens) | runtime dep (CP3+) | not pinned (PyPI `onnxruntime` 1.30.0, 2026-09-10, `MIT License`) | MIT | https://raw.githubusercontent.com/microsoft/onnxruntime/main/LICENSE (MIT, Microsoft Corporation) | Yes | Yes | oversight agent, fetched 2026-10-08 | MIT notice; execution-provider binaries (CoreML, CUDA) carry their own vendor terms if ever used. `status: VERIFIED-COMMERCIAL` |

## 4. Datasets (evaluation/calibration only; none are in the repository)

| Component | Kind | Version pinned | Licence (SPDX) | Primary source URL (fetched) | Commercial use | Redistribution of what we ship | Verified | Notes/obligations |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CUTE ("Dataset Accompanying 'Are These the Same Apple? Comparing Images Based on Object Intrinsics'", Kotar, Tian, Yu, Yamins, Wu, 2023) | dataset (identity evaluation, conformal calibration) | DOI 10.25740/gj714cj0414 (2023-06-14) | CC-BY-4.0 | https://purl.stanford.edu/gj714cj0414 : "This work is licensed under a Creative Commons Attribution 4.0 International license (CC BY)." Use statement: "User agrees that, where applicable, content will not be used to identify or to otherwise infringe the privacy or confidentiality rights of individuals." | Yes (evaluation during product development is permitted; attribution required) | Not shipped; if any image is ever shipped, attribution per CC BY 4.0 | oversight agent, read via WebFetch 2026-10-08 (page text; download link needs JavaScript, not exercised) | Attribution in any report that uses it. `status: VERIFIED-COMMERCIAL` |
| HoloAssist | dataset (future Hand Sentinel training; not in CP2-CP5) | release per https://holoassist.github.io/ (unreachable here) | CDLA-Permissive-2.0 | https://raw.githubusercontent.com/Ember-HoloAssist/holoassist-release/main/README.md L10: "We release the dataset under the [CDLAv2] license, a permissive license." Licence text (SPDX copy) https://raw.githubusercontent.com/spdx/license-list-data/main/text/CDLA-Permissive-2.0.txt §3.1: "This agreement does not impose any restriction or obligations with respect to the use, modification, or sharing of Results." §5.4: "'Results' means any outcome obtained by computational analysis of Data, including for example machine learning models" | Yes, including training a commercial model | Models trained on it carry no obligation; the Data itself may only be shared with the agreement text (§2.1) | oversight agent, fetched 2026-10-08 (README + SPDX text; `cdla.dev` itself unreachable) | `status: VERIFIED-COMMERCIAL` |

## 5. Required notices for what CP2 ships

| Shipped component | Notice to include in the served app's third-party notices page (does not exist yet) |
| --- | --- |
| PAM code (`perception/`, `server/`, `phone/`) | Repository `LICENSE` is MIT, "Copyright (c) 2026 Praneeth Samineni". Our own code; a commercial product can keep it MIT or relicense: that is a business decision, not a blocker. The copyright holder named in the file must match the entity that will sign commercial agreements (open question in `docs/OVERSIGHT_CP2.md`). |
| `@mediapipe/tasks-vision` 1.0.1 files | Apache-2.0 text (MediaPipe repository `LICENSE`), "Copyright Google LLC" line as in the repository headers, plus the package README Privacy Notice disclosure (metrics are blocked by CSP in PAM; say so in the privacy notice rather than pretending the code does not try). |
| `hand_landmarker.task` | Whatever the model card states, verbatim, once read. Until then it does not ship. |
| Python server deps | MIT/BSD texts for fastapi, starlette, uvicorn, pydantic, numpy, and the OpenCV Apache-2.0 + FFmpeg LGPL-2.1 texts if the server is ever distributed (a hosted service does not distribute them; a laptop installer would). |
| Tabler icons (legacy pages) | MIT (noted in `CLAUDE.md`); not loaded by `memory.html` (checked: `PUBLIC_ASSETS` lists no icon set). |

## 6. REJECTED components (do not reintroduce)

Every row was verified at the primary source on 2026-10-08 unless marked. These
are rejected for the product path; a published, non-product academic comparison is
a different question for counsel.

| Component | Why rejected | Primary source (fetched) | Status |
| --- | --- | --- | --- |
| EdgeSAM | S-Lab License 1.0: "Redistribution and use for non-commercial purpose in source and binary forms ... are permitted" (first clause of the licence) | https://raw.githubusercontent.com/chongzhou96/EdgeSAM/master/LICENSE (SHA-256 `cfd654022bdc44fdd809670d50239bcb1ebf2f4a661dca7e328f93c269538246`) | `status: REJECTED` (non-commercial) |
| FastSAM | AGPL-3.0 (full text in the repository) | https://raw.githubusercontent.com/CASIA-IVA-Lab/FastSAM/main/LICENSE (SHA-256 `0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0`, identical bytes to the Ultralytics AGPL file) | `status: REJECTED` (AGPL on a proprietary product path; AGPL is not NC, RESEARCH_LOG C-01) |
| YOLO-World | GPL-3.0 (full text in the repository) | https://raw.githubusercontent.com/AILab-CVC/YOLO-World/master/LICENSE (SHA-256 `e1d283b7a07b0964e38ddd080e69f95b52ecb40f594254168994f1816c7d7829`) | `status: REJECTED` (GPL) |
| Ultralytics (`ultralytics` package, YOLOE/YOLO weights, `ultralytics/CLIP` fork) | AGPL-3.0 for code; ultralytics.com/license FAQ: "All Ultralytics YOLO trained models fall under the AGPL-3.0 License by default." and "If you do not want to open-source the full project, you need an Enterprise License." PyPI `ultralytics` 8.4.174 `AGPL-3.0`. The `ultralytics/CLIP` fork is AGPL-3.0, unlike upstream OpenAI CLIP (MIT) | https://raw.githubusercontent.com/ultralytics/ultralytics/main/LICENSE ; https://raw.githubusercontent.com/ultralytics/CLIP/main/LICENSE ; https://ultralytics.com/license (WebFetch) | `status: REJECTED` (business decision: no Enterprise quote, spec §5). Still declared in `perception/requirements.txt` (`ultralytics==8.4.155`, `clip @ git+https://github.com/ultralytics/CLIP.git`), not imported by the served app; purge awaits user authorization (handoff §9 step 0) |
| RF-DETR PML tier: Atto, Femto, Pico, XL, 2XL, `rfdetr_plus` | README L21: "Plus components (`rfdetr_plus`, including RF-DETR-Atto/Femto/Pico/XL/2XL detection models) are licensed under PML 1.0." PyPI `rfdetr-plus` 1.1.0 `LicenseRef-PML-1.0`. Account-bound weights are a lock-in and termination risk in a shipped device | https://raw.githubusercontent.com/roboflow/rf-detr/develop/README.md ; https://pypi.org/pypi/rfdetr-plus/json | `status: REJECTED`. The Apache tier (RF-DETR-N/S/M/L, README L66-69 "Apache 2.0"; `rfdetr` 1.11.2 Apache; repo LICENSE Apache-2.0 text) remains an allowed future fine-tune target, not pinned |
| MobileCLIP / MobileCLIP2 weights (`mobileclip*.ts`, `.pt`) | Apple Machine Learning Research Model License, `LICENSE_MODELS` L22-28: "exclusively for Research Purposes ... 'Research Purposes' does not include any commercial exploitation, product development or use in any commercial product or service." (code is MIT, `LICENSE`) | https://raw.githubusercontent.com/apple/ml-mobileclip/main/LICENSE_MODELS ; https://raw.githubusercontent.com/apple/ml-mobileclip/main/LICENSE | `status: REJECTED` (research-only weights). Not present in this checkout (handoff §11) |
| EPIC-KITCHENS-100 (video, annotations) | Free release is non-commercial: data.bris.ac.uk record "EPIC-KITCHENS-100 Automatic Annotations" lists Licence "Non-Commercial Government Licence for public sector information"; the University of Bristol sells perpetual commercial licences at "From £7,000.00 excl. VAT" (micro, <=5 staff), "From £19,000.00" (SME), "From £49,000.00" (large). Evaluation inside product development is a commercial purpose | https://data.bris.ac.uk/data/dataset/3l8eci2oqgst92n14w2yqi5ytu ; https://express-licences.bristol.ac.uk/product/epic-kitchens-100---dataset (both WebFetch, 2026-10-08); the CC BY-NC 4.0 statement on https://epic-kitchens.github.io/ was not reachable from the sandbox (wording not re-read; consistent with the two records that were) | `status: REJECTED` without a purchased licence. `perception/blockers/eval_epic.py` is a script, not the dataset; its removal is on the purge list |
| DINOv2 repository siblings: XRay-DINO, Cell-DINO checkpoints | FAIR Noncommercial Research License / CC BY NC (README L159-160, L754-757) | https://raw.githubusercontent.com/facebookresearch/dinov2/main/README.md | `status: REJECTED`; only `dinov2_vits14*` from the Apache-2.0 section is cleared |
| DINOv3, SAM 3 | Custom Meta licences (modifiable at will, delete-on-termination, indemnity) per the COMMERCIAL review; not fetched here | https://raw.githubusercontent.com/facebookresearch/dinov3/main/LICENSE.md ; https://github.com/facebookresearch/sam3 (UNVERIFIED here) | Not adopted; re-verify at the primary source before any use. `status: UNVERIFIED` |
| Places365 scene classifier | CC BY model trained on non-commercial images (spec Round-2 note L60); conditional, only on a measured need | not fetched | `status: UNVERIFIED`; not planned |
| EgoLife (S-Lab), ReMEmbR (NVIDIA non-commercial), PerSAM (no LICENSE file), HaMeR (gated MANO), Deepgram/Whisper/Piper/openWakeWord (speech, out of scope) | Non-commercial or unlicensed, or deferred features | COMMERCIAL review A-016 (peer-verified, not re-fetched) | `status: REJECTED` or out of scope |

## 7. Evidence hashes (what was fetched on 2026-10-08)

SHA-256 of the licence/README texts fetched by curl from `raw.githubusercontent.com`
(kept in the review scratchpad; not committed):

| File | SHA-256 |
| --- | --- |
| google-ai-edge/mediapipe `LICENSE` | `8707eef0533987efc5b155d64761eeb6e20793f50b9bd1a68dad1cf4719d0ed8` |
| google-ai-edge/mediapipe `docs/solutions/models.md` | `36f2b0956f6b2743ecb81720daf54408b89542679a071d2e2d0d0aacc2a7aba4` |
| facebookresearch/dinov2 `LICENSE` / `README.md` / `MODEL_CARD.md` | `600cc67cc4cb2f5ea317dcfc687ad1c74dc4bec8782bbe9db0afd83513b935b7` / `d1bc2e9686522bbd66ed6123dc81eb36b3a98e8ea9a2ca97778f54a1c641c9e1` / `70ca59606bee0a5fbb1baec80e7e29a93cd7cfbe26ca1910c52a852c4aab09d0` |
| facebookresearch/sam2 `LICENSE` / `README.md` | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` / `eea69ee1042fb30933c5ca5019fbf0f6f9366cec5e792109281b5023a4f1589c` |
| THU-MIG/RepViT `LICENSE` / `sam/README.md` | `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4` / `cb82e32b2da53e71c80a34dedfe207de6682c9587a6c55c13817864703f4656a` |
| PaddlePaddle/PaddleOCR `LICENSE` / `README.md` | `3840c5c0c61c294264d2dd77b8777be6ddd90121ef4e0e64abcd22edea581d6e` / `63d76041f1dcb84e1dd141d45dc8dec5d86a3e357fe98bf8432ad2721c0ced90` |
| microsoft/onnxruntime `LICENSE` | `2f07c72751aed99790b8a4869cf2311df85a860b22ded05fa22803587a48922c` |
| google-research/big_vision `LICENSE` / `README_siglip2.md` | `43070e2d4e532684de521b885f385d0841030efa2b1a20bafb76133a5e1379c1` / `3c1862c16c6c75a97278fe9556482618db1d0419997eaefd4006ec9149994eef` |
| Ember-HoloAssist `README.md` / SPDX `CDLA-Permissive-2.0.txt` | `83a34eccdb570da45b9453e52c81470d090afd08630a1d9a5b3ce7c5dae9df8c` / `4531a67d443284d93ffed0803df5b10634aff21c3d77e381f2d48af01d875868` |
| chongzhou96/EdgeSAM `LICENSE` | `cfd654022bdc44fdd809670d50239bcb1ebf2f4a661dca7e328f93c269538246` |
| CASIA-IVA-Lab/FastSAM `LICENSE` = ultralytics `LICENSE` = ultralytics/CLIP `LICENSE` (AGPL-3.0) | `0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0` |
| AILab-CVC/YOLO-World `LICENSE` (GPL-3.0) | `e1d283b7a07b0964e38ddd080e69f95b52ecb40f594254168994f1816c7d7829` |
| roboflow/rf-detr `LICENSE` / `README.md` | `8cabf52c61130fc97a7e5da5e3685ccf44841c0c53d6f881189369b136603cca` / `c926dfdd1d5b325f291b302c90cf7c25ba4bb742beb0907093272b64e8aa0178` |
| apple/ml-mobileclip `LICENSE` / `LICENSE_MODELS` | `e7b09f708a137b12d14656d05dce036353b426f53eebd215106738a00a0a9357` / `30c59d255d2b4075ba11b81ce5aa0109c28d28138d66d52f7f5d8cbba814df8b` |
| fastapi / starlette / uvicorn / pydantic / numpy / httpx / anthropic licence files | `4ec89ffc81485b97fec584b2d4a961032eeffe834453894fd9c1274906cc744e` / `dcb95677a02240243187e964f941847d19b17821cf99e5afae684fab328c19bf` / `efe1acf3e62fb99c288b0ec73e5a773b7268ef4320fe757ea994214e4b63c371` / `a9e186f3ca16b5eef84318e7a701721351a00cb7b8ae3a4394b67b49e3529ef3` / `1be1df33863f97a7bc1c4d67980bd6c69c9a6fef0a5ee76e6ad6cb91e56e8491` / `4ec59d544f12b5f539a3a716fd321ac58ccd8030b465221f2c880200cdf28d8d` / `8bf96984ff8bcfae7e48cae76a529e8a25317ba9e02abf7fd3cc64fdf95657a6` |
| opencv/opencv-python `LICENSE.txt` / `README.md`; opencv/opencv `LICENSE` | `09d719058e782ac7bc71ba21c944e1136cde2bb957c0e888121f0218d6b5f02c` / `96d6b5b49d1b94240d6e68caac705af90f9874bd36658227ddc7e2eca5a34c26`; `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` |
| `@mediapipe/tasks-vision` tarballs 1.0.1 / 1.1.0 | `ee318eaa3d42230aa10910d114faf2a488c577c4e4d33c7cb04126924aca505f` / `46fc3d3d13fa5de631915929d045be2f74bb32e909d7a5b3a322b28976f54165` (registry integrity matched for both) |
