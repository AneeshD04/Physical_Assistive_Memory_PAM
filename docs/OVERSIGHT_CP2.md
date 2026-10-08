# Oversight review: CP2 (automatic capture path)

Oversight agent, 2026-10-08, on the uncommitted CP2 working tree over `fbf6719`
(`git status`: 9 modified files, 9 new files under `perception/`, `phone/assets/`,
`scripts/`, plus `docs/BUILD_PLAN.md`). Read-only review; no git state changed. The
companion register is `docs/LICENSES.md`. The tester's CP2 suites appeared during this
review (`server/test_cp2_*.py`, `server/fixtures/cp2/`, `phone/test/test_ui_smoke.py`)
and are the tester's verdict, not mine; where I ran something I say so.

Verdict in one line: **the diff implements the CP2 interfaces in
`docs/BUILD_PLAN.md` §2 with no fabricated capability and no new dependency, but the
automatic path cannot be enabled yet**: the hand-model licence is still unverified at
its primary source (B-05/C-03 stays open), and the MediaPipe bundle carries a
telemetry POST that only the CSP stops. The CSP/WASM, register-gating and
cross-language findings of the first pass were fixed by the builders and re-verified
in the follow-up pass (§1.8).

## 0. Human actions required (the sandbox cannot do these)

All on the user's laptop, in the PAM checkout. Nothing below is optional for a go.

1. **Read the hand-model licence at its primary source.** Open
   `https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Hand%20Tracking%20(Lite_Full)%20with%20Fairness%20Oct%202021.pdf`
   (the "Model Card" link on
   `https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker`).
   Copy the licence line verbatim into `docs/LICENSES.md` §2b. Only if it names a
   licence permitting commercial use and redistribution (Apache-2.0 would) change that
   row's token from `status: UNVERIFIED` to `status: VERIFIED-COMMERCIAL` and remove
   every occurrence of the word UNVERIFIED from that line. If the PDF names no
   licence, leave the row as is and raise it with counsel; do not fetch.
2. **Download and hash the pinned artifact** (never `/latest/`):
   ```
   curl -L -o hand_landmarker.task "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
   sha256sum hand_landmarker.task          # Linux/macOS
   Get-FileHash .\hand_landmarker.task -Algorithm SHA256   # PowerShell
   ```
   Paste the 64-hex value into `scripts/model_pins.json` (`sha256` of the
   `hand_landmarker.task` entry; its `url` is already filled) and into the
   `docs/LICENSES.md` §2b row with the date and file size.
3. **Fetch under the gates and provision:**
   ```
   python scripts/fetch_models.py --dry-run       # after steps 1-2: every entry "would fetch" or "present", exit 0
                                                  # before them: the five tasks-vision entries "would fetch", hand_landmarker.task "refused", exit 2 (expected)
   python scripts/fetch_models.py                 # writes phone/assets/models/MANIFEST.json (6 assets)
   git status --short phone/assets/models         # expect nothing listed once .gitignore carries *.task, *.wasm, phone/assets/models/
   ```
4. **Run the controller equivalence suite on the laptop's Python 3.11** (the sandbox
   runs 3.13; the `sum()` fix removed the known 3.11/3.13 difference, this run proves
   it):
   ```
   python -B -m unittest server/test_cp2_controller.py -v
   ```
5. **Enable and verify on a real device:** start the app with
   `PAM_ENABLE_HAND_MODEL=1`, open the camera page on the iPhone (Safari) and on
   container Chromium, confirm `GET /api/health` shows the hand model
   `provisioned: true, licence_recorded: true` and the capability enabled with
   "accuracy unmeasured", confirm the worker reaches `ready` (toggle becomes enabled,
   status "Camera on · automatic capture (hand model float16/1)"), and run
   `phone/test/test_ui_smoke.py` with the assets present so the no-egress assertion
   covers the live worker (the only foreign request the runtime attempts is the
   `odml.pa.googleapis.com` POST, which must appear blocked or absent).
6. **Record the result** in `docs/RESEARCH_EXPERIMENTS.md` (blocked until 1-2 are done;
   not skipped) and in `CONTINUATION_HANDOFF.md` §5.

## 1. Plan adherence (BUILD_PLAN §2 interfaces and deliverables)

### 1.1 Deliverable status

| Deliverable (plan §2) | Owner | Status | Evidence |
| --- | --- | --- | --- |
| Python `replay(samples) -> [{t_ms, actions, phase}]` + CLI `python -m perception.episode_controller trace.json` | A | done | `perception/episode_controller.py:68-86` (replay), `:89-116` (`_main`, compact sorted JSON, exit 1 on ValueError, 2 on usage) |
| JS `replay(samples)` + `phone/assets/controller-replay.mjs`, no npm dependency | C | done | `phone/assets/controller.js:49-60`; `phone/assets/controller-replay.mjs:9-43` (only `node:fs`; sorted-key stringify). Oversight spot check 2026-10-08: a 30-sample synthetic trace through both CLIs gave byte-identical output |
| `motionEnergy(prev,next,w,h) -> {energy, moving}` and `motionStep(state, energy) -> [state, moving]`, `MOTION_ON=0.035`, `MOTION_OFF=0.015`, 3x3 box blur, MAD/255 | A + C | done, with one deliberate refinement | `perception/motion.py:36-37, 78-139`; `phone/assets/motion.js:18-19, 55-100`. Both round the energy to 6 decimals with integer arithmetic (BigInt in JS) so ties cannot diverge (`motion.py:14-19`, `motion.js:8-12`); that is stricter than the plan's prose, not a deviation. Spot check: identical `{energy, moving}` and blur bytes on a random 7x5 pair |
| `handBusy(hands) -> {present, busy, basis}`, `CURL_RATIO=0.55`, lower 60% of frame, area >= 2%, `present=false -> busy=null` | A + C | done (portability risk fixed in the follow-up) | `perception/hand_busy.py:39-41, 103-133`; `phone/assets/hand-busy.js:27-29`. First pass: `hand_busy.py` used builtin `sum()` (Neumaier on CPython >= 3.12, naive on the user's 3.11) and the JS port emulated 3.12. **Resolved:** Builder A now accumulates with an explicit loop (`hand_busy.py:90-99`) and Builder C dropped the emulation (`hand-busy.js:75-77`); re-verified identical outputs on random fixtures 2026-10-08. The laptop's 3.11 run (§0 step 4) is the remaining proof |
| Hand worker loads **only** same-origin `/assets/models/` (WASM, JS, `.task`); `{type:'frame'}` / `{type:'hands'|'unavailable'}` protocol; never a CDN | C | done | `phone/assets/hand-worker.js:60-64` (`sameOriginURL` rejects any other origin), `:105-156` (`init`: manifest, bundle, loader, binary, model all under `base`), `:111` (`redirect: 'error'`), `:183-203` (frames). No `http` literal in any new browser file except `hand-worker.js` comments; `grep` of `phone/assets/*.js` finds no CDN host |
| `createAutomaticAdapter({worker}) -> {enabled, reason, analyze}` | C | done, signature extended | `phone/assets/controller.js:95-182`. `analyze(t_ms, analysisGray, bitmap)` takes three arguments (plan says `analyze(frame)`), returns the plan's four fields plus `basis, present, energy, infer_ms`. Acceptable: the controller sample stays `{t_ms,busy,motion,frame_valid}`; the tester's fixtures should pin the actual signature |
| Model assets never committed; `scripts/fetch_models.py` with pinned URL + SHA-256, writes `MANIFEST.json`, refuses without a `docs/LICENSES.md` entry | B | done; `.gitignore` decided by the coordinator, not yet on disk at re-review | `scripts/fetch_models.py:111-137` (refusals: name, version, licence id, https url, 64-hex sha256, then the structured register check `:129-136`: a line naming the base file with `VERIFIED-COMMERCIAL`, without `UNVERIFIED`/`REJECTED`, and carrying the pin's licence id), `:148-180` (streamed, hashed, atomic, https-only redirects), never overwrites a differing file. Dry run 2026-10-08 after the follow-up: five tasks-vision entries "would fetch", `hand_landmarker.task` refused on `sha256: null` (and would also be refused by the register, whose row is UNVERIFIED). `.gitignore`: the plan assumed `*.task` was excluded; it is not (`*.ts`, `*.pt`, `*.onnx`, `*.safetensors` only). The coordinator has taken ownership and is adding `*.task`, `*.wasm`, `phone/assets/models/`; at re-review (2026-10-08 05:40 UTC) the file was unchanged, so §0 step 3 checks it before the first fetch |
| Health `models: [{name, provisioned, licence_recorded, version}]`; `automatic_hand_recognition` enabled only when provisioned + licence recorded + `PAM_ENABLE_HAND_MODEL=1`; allowlist serves `/assets/models/<file>` only for manifest names | B | done | `server/memory_app.py:100-144` (manifest validation, fail-closed on any bad entry), `:147-160` (`model_file`, no symlinks, resolves inside dir), `:176-184` (`licence_verified`, row-structured register check), `:188-206` (inventory), `:225-240` (policy: unprovisioned -> unlicensed -> disabled -> enabled with "accuracy unmeasured on this device"), `:530-540` (health), `:553-562` (items share the same policy via `with_hand_policy`), `:624-650` (route: 404 unless manifest valid and env flag set; manifest no-store; model files `private, max-age=86400`) (line numbers as of the follow-up re-read). `phone/serve.py:74-78` refuses `assets/models/` on the standalone server |
| `GET /api/items?as_of=<ms>`, `POST /api/chat {text, as_of}` evaluate at a time (B-11) | B | done, plus `GET /api/items/{id}?as_of` | `server/memory_app.py:442-458` (`as_of_query`, `as_of_body`; 16-digit bound, 400 on anything else), `:553-562`, `:569-573`, `:594-610` |
| Clock-only staleness: `AGE_STALE_MS=24h` hedged with `stale_reason "age"`, 7 days -> abstain; catalogue shows the same ageing; no write needed | A | done | `perception/episode_store.py:32-33`, `:261-280` (`_age_item`, pure), `:353-378` (`list_items` ages on read), `:382-398` (`get_item`), `:443-475` (`answer_text`: `confident` only when trusted + placed + not aged; `:467-470` hedged text with the UTC date; `:468` abstains past 7 days). `_rebuild_projection` stores un-aged items (`:343-350`) so the stored projection never depends on wall-clock time |
| `capture_mode: "automatic"` packets carry `landmarks` and `gaps`; nothing new in the schema | C | done | `phone/assets/memory-camera.js:279-280` (`landmarks` only when automatic, capped at `LANDMARK_SAMPLES_MAX=128`, two hands) |
| `createAutomaticAdapter` wired into `memory-camera.js`: controller actions pin keyframes and the burst, gaps recorded, status strings for manual / automatic / unavailable | C | done | `memory-camera.js:12` (`MANUAL_STATUS`), `:35-37` (`automaticAvailable` requires worker-ready AND server policy), `:179-194` (`automaticTick`), `:220-241` (`apply`: `select_pre_contact` pins the oldest retained frame before the busy frame, `select_carry` starts the burst causally, `finish` submits with hint `released`, `gap`/`abort` discard with a reason), `:46-51` (worker becoming unavailable mid-episode records a gap and discards, `:47`). Stored-items and Chat views unchanged except the age rendering (`phone/assets/memory.js:62-70`, `:71-80`) |
| Server/page agreement on the capability | B + C | done | `memory.js:218-225` reads the health capability and `memory-camera.js:53-58` applies it; the toggle is disabled unless both the worker reported `ready` and the server did not deny (`memory.js:159-171`) |
| Tester deliverables (goldens, three `test_cp2_*.py`, Playwright smoke) | Tester | present, in progress at review time | `server/fixtures/cp2/` holds the eight named traces, `hand_goldens.json`, `motion_goldens.json` and invalid-input cases; `server/test_cp2_controller.py` (38 KB), `test_cp2_models.py` (33 KB), `test_cp2_staleness.py` (14 KB); `phone/test/test_ui_smoke.py`. A read-only run of the three server suites at 05:00 UTC gave 55 tests, 1 failure: Python rejected a float literal `t_ms: 100.0` while Node's `JSON.parse` turns `100.0` into 100 and accepted it. **Resolved** by coordinator decision (integral floats accepted at the trace boundary in both CLIs; `perception/episode_controller.py:77-92` normalises them in a copied sample, `step()` still requires `int`, `100.5` still raises). Re-run after the follow-up: 55 tests, 0 failures |
| Oversight deliverables | Oversight | this file + `docs/LICENSES.md` | see §2 |
| Finance `docs/FINANCE.md` v1 | Finance | appeared in the tree while this review was being written; not reviewed here | `docs/FINANCE.md` (untracked) |

Existing suites: `perception/test_capture.py`, `test_interaction.py`, `test_private_files.py`
(21 tests, run from `perception/`) and `server/test_memory_lifecycle.py`,
`test_personal_pipeline.py`, `test_memory_bootstrap.py` (130 tests) all passed in a
read-only run on 2026-10-08 (151 total, same as CP1).

### 1.2 Fabricated capability: none found

- With no assets, the worker posts `unavailable` with a fixed sentence
  (`hand-worker.js:31-38`, `:112-125`), the adapter stays `enabled:false`
  (`controller.js:96-97`, `:112-118` `unavailable`, `:122-127` only a `ready` message enables), `automaticActive()` is false
  (`memory-camera.js:36`), the page says "Unavailable: ... Manual marking still works"
  (`memory.js:164-165`), and the server reports `automatic_hand_recognition: false`
  with one of three reasons (`memory_app.py:74-78`). No path produces `busy`/`motion`
  from anything but measured pixels and worker output; a missing measurement is
  `null` (`controller.js:171`), never a guess.
- The enabled reason is honest: "Hand model {version} provisioned; accuracy
  unmeasured on this device." (`memory_app.py:239`). The page's automatic-mode copy
  says "a busy-hand heuristic, not verified recognition" (`memory.js:170`,
  `memory.html:74`).
- `hand-worker.js:159-181` (`convertHand`) clamps and rounds model output; it does not
  synthesise hands. `MAX_HANDS=2` matches the packet contract.

### 1.3 New dependencies: none at runtime

No new import in Python (`numpy` was already a dependency; `motion.py:33` is the
only new import) and no npm package. `controller-replay.mjs` is Node-only and is
deliberately **not** served (`memory_app.py:34-36`, absent from `PUBLIC_ASSETS` at
`:37-41`). The tester's Playwright suite introduces a **dev** dependency that is not yet
declared or pinned; the coordinator will record it in a dev requirements file during
the purge round (`docs/LICENSES.md` §1, dev/test note).

### 1.4 Network fetches from browser code

- Asset loading: same-origin only, verified above.
- **The MediaPipe runtime itself phones home.** `vision_bundle.mjs` (1.0.1 and 1.1.0)
  contains a metrics logger that POSTs `application/x-protobuf` to
  `https://odml.pa.googleapis.com/v1/log` every 60 s with an `x-goog-api-key` header
  (`docs/LICENSES.md` §2a quotes the package README's Privacy Notice). There is no
  public opt-out in `vision.d.ts`. In PAM the worker script is served with
  `Content-Security-Policy: ... connect-src 'self'` (`server/memory_app.py:410`), and
  a dedicated worker is governed by the policy delivered with its own script, so the
  POST is refused by the browser and the logger disables itself after the first
  failure ("net-send-failed"). Three consequences: (a) the plan's acceptance "no
  request leaves the origin" must be asserted by the Playwright test **with assets
  present and the worker running**, not only on the empty-model page; (b)
  `phone/serve.py` sets no CSP at all, which is fine only because it never serves
  `assets/models/` (`serve.py:78`); if that ever changes, the CSP must come with it;
  (c) the user-facing privacy notice has to mention that the runtime attempts this
  and that PAM blocks it (README obligation: "You are responsible for obtaining
  informed consent from your app users about Google's processing of MediaPipe metrics
  data").

### 1.5 CSP and the WASM runtime (first pass: blocker; follow-up: resolved)

First pass: `script-src 'self'` without `'wasm-unsafe-eval'` would make
`WebAssembly.compile`/`instantiate` fail inside the worker under CSP Level 3
(Chromium and WebKit enforce it; the policy delivered with the worker script governs
the worker), so the automatic path could never reach `ready`. **Resolved:**
`server/memory_app.py:410` now sends `script-src 'self' 'wasm-unsafe-eval';
worker-src 'self'; ... connect-src 'self'` (no `'unsafe-eval'`), with a comment at
`:406-409` explaining that `connect-src 'self'` is what blocks the MediaPipe
telemetry POST. `frame-ancestors 'none'`, `object-src 'none'` and `base-uri 'none'`
are unchanged. Not executed in a browser here; §0 step 5 is the proof on a real device.

### 1.6 "Manual" vs "automatic" confusion points

- `memory-camera.js:37` and `memory.js:140` label the mode from `automaticActive()`,
  which requires the toggle, the worker and the server policy together; the badge
  (`memory.js:168`) and the summary line agree. Good.
- `memory-camera.js:260` (`rest()`) throws if an automatic episode is in progress,
  so a manual "Mark at rest" cannot close an automatic episode and mislabel it.
- The server's 404 for `/assets/models/MANIFEST.json` when `PAM_ENABLE_HAND_MODEL`
  is unset makes the worker say "Hand model assets are not provisioned" even when
  they are on disk but disabled; the page then shows the server's "disabled" reason
  because the policy reason wins (`memory-camera.js:40`). Acceptable, but the two
  sentences will coexist in logs; document it for support.
- `select_pre_contact` rewrites `episode.t_start_ms` to the pinned pre-contact
  frame's time (`memory-camera.js:230`), so an automatic packet's `t_start_ms`
  precedes the controller's `start` sample. Consistent with the contract (monotonic,
  start <= end), but the tester's packet fixture must not assume
  `t_start_ms == first busy sample`.

### 1.7 Paths, secrets, personal data

- No file-system path leaves the server: inventory carries only manifest names and
  versions (`memory_app.py:200-206`); errors are fixed strings.
- `PAM_ENABLE_HAND_MODEL` is read per request and never logged (`:220-222`).
- `hand-worker.js:53` `console.warn`s the caught error object on load failure; it
  contains same-origin URLs only. Fine.
- **Landmarks are persisted.** Automatic packets carry up to 128 samples x 2 hands x 21
  points (`memory-camera.js:279`), and `ingest_episode` stores the raw packet bytes
  in `episode_revisions.packet` (`perception/episode_store.py:149-150`). See §3 on
  biometric exposure; this is the single largest new data-class in CP2 and the
  retention design (CP4, G-PRIV) must name it.

### 1.8 Follow-up re-verification (2026-10-08, after the coordinator's decisions)

Re-read in the working tree: `server/memory_app.py` (CSP block `:406-410`,
`licence_verified` `:176-184`, inventory `:188-206`, reason text `:76`),
`scripts/fetch_models.py` (`:65-68`, `check_pin` `:111-137`), `scripts/model_pins.json`,
`perception/episode_controller.py:77-92`, `perception/hand_busy.py:90-99`,
`phone/assets/hand-busy.js:75-77`.

| First-pass finding | Status | Evidence |
| --- | --- | --- |
| 1. CSP would refuse WASM in the worker | **Resolved** | `script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'` at `memory_app.py:410`; comment `:406-409` names the telemetry endpoint and says to keep `connect-src 'self'`. `frame-ancestors`, `object-src`, `base-uri` unchanged |
| 2. MediaPipe telemetry POST | Unchanged by design | Blocked by `connect-src 'self'`; disclosure obligation stays in `docs/LICENSES.md` §2a; real-worker no-egress run is go/no-go item 3 |
| 3. `.gitignore` lacks `*.task`, `*.wasm`, `phone/assets/models/` | **Decided** (coordinator owns it); not yet on disk at re-review | §0 step 3 verifies before the first fetch |
| 4. Cross-language: integral-float `t_ms`; `sum()` portability | **Resolved** | Trace-boundary normalisation `episode_controller.py:77-92`; explicit loops `hand_busy.py:90-99` and `hand-busy.js:75-77`. Re-run: tester's three CP2 server suites 55/55 green; my replay and motion/hand-busy spot checks byte-identical again |
| 5. Raw landmarks persisted | **Scheduled** (CP4 deliverable: bbox + busy scalars after processing; raw landmarks at most 72 h) | §3.1 stands as the review note for that deliverable |
| 6. Substring register gating | **Resolved** | `licence_verified` and `check_pin` are row-structured (§3.8); dry run refuses `hand_landmarker.task`, admits the five tasks-vision files; register restructured to one token per row |
| Pins unfilled | **Resolved** | `scripts/model_pins.json`: 1.0.1, jsDelivr per-file URLs, the five SHA-256 values match `docs/LICENSES.md` §2a; hand model `url` filled, `sha256: null` |

## 2. Commercial path for what CP2 ships

| Component | Can we redistribute it in a commercial product? | Notices required | Verdict |
| --- | --- | --- | --- |
| Our code (`perception/`, `server/`, `phone/`, `scripts/`) | Yes; repository `LICENSE` is MIT, copyright "Praneeth Samineni" 2026 | Keep the MIT notice if the code stays MIT; relicensing is a business choice | Clear. Open question: the named copyright holder must be the contracting entity |
| `@mediapipe/tasks-vision` JS + WASM served from our origin | **Yes.** Package declares Apache-2.0 (registry JSON for 1.0.1 and 1.1.0; `package.json` inside the verified tarballs). The tarball ships no LICENSE/NOTICE file, so ship the MediaPipe repository `LICENSE` text (fetched, SHA-256 in `docs/LICENSES.md` §7) | Apache-2.0 text + Google copyright line in a third-party-notices page (does not exist yet); Privacy Notice disclosure about the blocked metrics POST | Clear with notices. **Pin 1.0.1** (B-06, D-014): published 2026-07-31 (A-020), two months aged; 1.1.0 is two days old at review and only differs in bundle/WASM bytes (same README, same licence, same telemetry). Both sets of hashes are recorded so switching is a pin edit |
| `hand_landmarker.task` (float16/1) | **Not established.** The licence is stated (if anywhere) in the model card PDF, which is on `storage.googleapis.com` and was unreachable from this sandbox (HTTP 403 at the egress proxy on every attempt, curl and WebFetch, 2026-10-08). The developers page was read and says nothing about the bundle's licence; the weights are not in the Apache-2.0 repository (`.tflite` paths 404 on raw GitHub; `docs/solutions/models.md` links them on GCS). A third-party model-zoo attribution (COMMERCIAL review) is not a grant | Whatever the card says, verbatim | **B-05 / C-03 remain open.** UNVERIFIED in the register; pins stay null; the capability stays disabled |

Exact values for Builder B's `scripts/model_pins.json` (Task 2; **applied by Builder B
in the follow-up and re-read 2026-10-08: all six entries match this table, the hand
model keeps `sha256: null`**):

| name | version | url (any mirror is acceptable only because the script verifies the SHA-256 below, which was computed from the registry tarball whose `dist.integrity` matched) | sha256 |
| --- | --- | --- | --- |
| `vision_bundle.mjs` | `1.0.1` | `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/vision_bundle.mjs` (jsDelivr/unpkg were unreachable from the sandbox; the file is `package/vision_bundle.mjs` inside `https://registry.npmjs.org/@mediapipe/tasks-vision/-/tasks-vision-1.0.1.tgz`, integrity `sha512-rvRE2FmAZ6ZxKSw7wq+e+jQDpN3t1B/tD2mJz9SmAzb1msoDkd4dMoE4wAh8Z30Um0PQwLiHr9QtomhmXk3aUQ==`, shasum `7ab992e2415d48e526934abd6390ffc208699fb1`) | `d885630c297c0b20b1fe86096cb06291c4c8080876f27852e724f24ac603713f` |
| `vision_wasm_internal.js` | `1.0.1` | `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm/vision_wasm_internal.js` | `e170ee67dd4e16c1a6fcd8840a206687e5a59b22c20e4a902bc445b095454d73` |
| `vision_wasm_internal.wasm` | `1.0.1` | `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm/vision_wasm_internal.wasm` | `8da277a733926eacd0474b8704b36742d6ec3231c57a860c5b889dff8f1df886` |
| `vision_wasm_nosimd_internal.js` | `1.0.1` | `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm/vision_wasm_nosimd_internal.js` | `e81d715a3d42cc3373602eb2f7aff795d164934db680e32496b65dab537f9658` |
| `vision_wasm_nosimd_internal.wasm` | `1.0.1` | `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1/wasm/vision_wasm_nosimd_internal.wasm` | `a28483cd42e74e855bf5ebdb6b40d9b66a5b49e35e95020bc97669e6822a3192` |
| `hand_landmarker.task` | `float16/1` | `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task` (do **not** pin `/latest/`) | **leave `null`** until the licence is read and the hash computed on the laptop |

The 1.1.0 file hashes are in `docs/LICENSES.md` §2a if the coordinator overrides D-014.
The tarball file list for both versions: `README.md`, `package.json`, `vision.d.ts`,
`vision_bundle.{cjs,js,mjs}` (+ `.map` for cjs/mjs), `wasm/vision_wasm_internal.{js,wasm}`,
`wasm/vision_wasm_nosimd_internal.{js,wasm}`, `wasm/vision_wasm_module_internal.{js,wasm}`.
The `wasm/` files are stored flat in `phone/assets/models/` because the worker looks
them up by bare name (`hand-worker.js:118-125`); the manifest `name` must be the flat
name as `model_pins.json` already has it.

Human steps on the laptop: see §0 (single copy; a conversion or an OpenCV-Zoo copy
of the model does not cure an unread licence, RESEARCH_LOG C-03).

## 3. Risks to commercialisation beyond licences

1. **Biometric statutes and hand landmarks.** Illinois BIPA (740 ILCS 14/10) lists
   "scan of hand or face geometry" among biometric identifiers; Texas CUBI and
   Washington's law are similar; the EU AI Act and GDPR Art. 9 turn on whether the
   data is used for unique identification. PAM stores 21-point hand geometry per
   frame in `episode_revisions.packet` (§1.7) although it only needs a busy flag. The
   contract already allows world landmarks "in development traces" only
   (BUILD_CONTRACT, landmarks bullet). Recommendation for CP4/G-PRIV: in production
   mode send and store only derived scalars (`busy`, `basis`, `hand_bbox`, `infer_ms`)
   and keep the 21 points behind an explicit development flag with a retention
   window and erasure path; get the fact-specific review the handoff already calls
   for before any pilot in a BIPA state. Whether landmarks that are never matched to
   an identity are "biometric identifiers" is exactly the kind of question counsel
   must answer; the cheap engineering answer is not to keep them.
2. **Consent and bystanders.** The camera page already says "Start only when everyone
   in view has agreed to be recorded" (`memory.html:72`, `#camera-status`). Automatic mode lowers the
   per-episode friction, so the recording-consent and two-party-consent analysis
   (handoff §11) applies with more force; the Playwright suite must never use real
   footage (BUILD_CONTRACT, browser section).
3. **MediaPipe telemetry and the privacy notice.** §1.4. Even blocked, the obligation
   to disclose exists in the package README; a reviewer or an app store will ask.
4. **Apple App Store, if this ever becomes native.** A browser rig has no store
   review; a native build would face App Review Guidelines on camera use disclosure,
   on-device vs. cloud processing statements, health-adjacent claims (a memory aid
   for cognitively impaired users is scrutinised as a health app), and the data
   collection "nutrition label". The plan's "native build" line item should carry a
   store-compliance review as a gate, not a task.
5. **Trademark.** The COMMERCIAL review (A-016 §5) found live registrations of "PAM"
   in Class 42 health-behaviour software (Reg. 3755291, Insignia Health) and a pending
   AI-assistant application (SN 99348754, Dream Lab AI); "not clear for
   health-adjacent software; pick a new mark before public pilot materials". Nothing
   in CP2 changed that; the served page still calls itself Pam. Keep the name out of
   any external pilot material until counsel clears or replaces it.
6. **Copyright holder.** `LICENSE` names an individual. Before any licence is
   granted to a customer or an acquirer, the contracting entity needs to own or be
   licensed the code; contributor agreements for the agents' output are a human
   question.
7. **Dependency hygiene.** `server/requirements.txt` has no version pins and still
   lists dead dependencies; `perception/requirements.txt` still declares
   `ultralytics` (AGPL-3.0) and the AGPL `CLIP` fork (`docs/LICENSES.md` §6). Not a
   licence breach (nothing imports them from the served app) but a diligence finding
   and an accidental-import hazard; the purge is still waiting for the user's
   authorization (handoff §9 step 0). Use `opencv-python-headless` rather than
   `opencv-python` on the server to avoid the LGPL-3.0 Qt wheel.
8. **Register gating (first pass: substring; follow-up: structured, resolved).**
   `server/memory_app.py:176-184` (`licence_verified`) now grants only when one
   register line names the base file with the literal `VERIFIED-COMMERCIAL` token and
   neither `UNVERIFIED` nor `REJECTED`; `scripts/fetch_models.py:129-136` applies the
   same rule and additionally requires the pin's licence id on that line, with
   per-entry refusals (exit 2 if any). Re-verified 2026-10-08: `licence_verified`
   is False for `hand_landmarker.task` (its row is UNVERIFIED) and True for the five
   tasks-vision files; the register was restructured so no asset row carries two
   tokens (`docs/LICENSES.md` rule 2). The `sha256: null` pin remains a second,
   independent refusal for the hand model.
9. **Secure context and Safari.** Unchanged from CP1: no background capture promise
   (handoff §1). CP2 adds nothing that runs while the page is hidden.

## 4. Go/no-go on enabling `automatic_hand_recognition` once assets are fetched

**No-go today.** Resolved since the first pass: CSP (`'wasm-unsafe-eval'`,
`worker-src 'self'`), structured register gating, the float `t_ms` boundary rule,
the `sum()` portability fix, tasks-vision pinned at 1.0.1 with verified hashes,
`.gitignore` ownership taken by the coordinator, landmark retention scheduled as a
CP4 deliverable (bbox + busy scalars after processing, raw landmarks at most 72 h).
What remains, all required (and all human actions, §0):

1. **Hand-model licence line + hash.** A human reads the model card PDF, quotes the
   licence verbatim in `docs/LICENSES.md` §2b, flips the row to
   `VERIFIED-COMMERCIAL` only if the terms permit commercial use and redistribution,
   downloads `/float16/1/hand_landmarker.task`, records its SHA-256 in the register
   and in `scripts/model_pins.json`, and runs `scripts/fetch_models.py` to exit 0
   (§0 steps 1-3). Until then B-05/C-03 stay open and the capability stays disabled.
2. **Worker reaching `ready` on a real device.** With assets provisioned and
   `PAM_ENABLE_HAND_MODEL=1`, the iPhone Safari page and container Chromium show the
   toggle enabled and the automatic status string (§0 step 5). The health reason
   must still say "accuracy unmeasured on this device".
3. **No-egress with the real worker.** `phone/test/test_ui_smoke.py`'s foreign-request
   assertion (`test_00_egress_controls_detect_and_block_a_foreign_request`) run with
   the model present and the worker active; the only attempt the runtime makes is the
   `odml.pa.googleapis.com` POST and it must be blocked or absent.
4. **Laptop Python 3.11 run of `server/test_cp2_controller.py`** green (§0 step 4),
   since the sandbox proves equivalence only on 3.13.

Meeting all four gives a **go for the rig on the user's own device** (CP2 acceptance,
"only if Oversight clears it"), with the enable remaining an explicit operator action
plus the in-page toggle, default off. Use beyond the rig additionally waits for the
CP4 landmark-reduction deliverable and the fact-specific biometric review (§3.1).

## 5. Open questions for the coordinator (with the decisions received 2026-10-08)

1. `.gitignore` ownership: **decided**, coordinator adds `*.task`, `*.wasm`,
   `phone/assets/models/`. Not on disk at re-review; §0 step 3 checks it.
2. Integral-float `t_ms`: **decided**, accepted at the trace boundary in both CLIs;
   implemented and green.
3. `sum()` in `hand_busy.py`: **decided**, explicit loop in both languages; done.
4. tasks-vision pin: **decided**, 1.0.1 with the per-file jsDelivr URLs and the
   registry-derived SHA-256 values; `scripts/model_pins.json` filled by Builder B
   (re-read: the six hashes match `docs/LICENSES.md` §2a byte for byte).
5. Hand-model licence/hash: **decided**, human action on the laptop, recorded as
   blocked, not skipped (§0 steps 1-3). Still the gating item.
6. `'wasm-unsafe-eval'`: **decided and done**, with `worker-src 'self'` and
   `connect-src 'self'` kept.
7. Landmark retention: **decided**, landmarks remain processing inputs in the packet;
   CP4 reduces stored samples to per-hand bbox + busy scalars after processing with
   raw landmarks retained at most 72 h (spec rule), recorded in `docs/BUILD_PLAN.md`.
   Oversight will check that deliverable against the biometric note in §3.1 at CP4.
8. Playwright pin: **decided**, dev requirements file during the purge round; the
   register row waits for that version.
9. `opencv-python-headless`: **decided**, part of the deferred purge.
10. Contracting entity for `LICENSE`: **open, user decision.**

New since the follow-up: none.

## Interface notes

- `docs/LICENSES.md` is the gate file. Every asset row carries exactly one `status:`
  token on the same line as the base file name, and the licence id (`Apache-2.0`)
  on the same line, which is what `check_pin` requires.
- Pins applied: tasks-vision `1.0.1` with the file SHA-256 values in §2;
  `hand_landmarker.task` `float16/1` with `url` filled and `sha256` null until a
  human reads the model card and hashes the artifact (§0).
- The MediaPipe runtime attempts a telemetry POST to `odml.pa.googleapis.com`; PAM
  relies on CSP `connect-src 'self'` to block it. Keep that directive; test it.
- CSP now carries `script-src 'self' 'wasm-unsafe-eval'; worker-src 'self';
  connect-src 'self'` (`server/memory_app.py:410`); keep all three.
- `licence_verified` (server) and `check_pin` (script) read the register row by row;
  a verified row must never contain the words UNVERIFIED or REJECTED, so notes on a
  verified row say "not reachable"/"not re-read" instead.
