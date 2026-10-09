# PAM build plan: checkpoints CP2 to CP5

Architect, 2026-10-07, after CP1 (`fbf6719`, 151/151 tests). This is the concrete,
current plan. It reconciles three sources and names where each item came from:

- the canonical spec `MEMORY_SYSTEM_V4.md` Part 1, order of operations items 3 to 7;
- Devin's `CONTINUATION_HANDOFF.md` section 8 (open decisions 1 to 12), section 9
  (next steps 5 to 7) and `RESEARCH_LOG.md` blockers B-01 to B-17 and experiment
  queue P-101 to P-107;
- `BUILD_CONTRACT.md`, including the CP1 contract decisions.

Where the handoff and the spec disagree, the handoff's **user instructions** win
(text chat, no Deepgram, stored-items browser, iPhone later, small subscription,
no purge/push/deletion without authorization), then `BUILD_CONTRACT.md`, then
Part 1. Nothing below authorizes a paid provider call, a model download without a
recorded licence, real household footage, or any deletion.

## 0. Team and protocol

Six roles, one coordinator (the architect, who is also the only one who commits).
Agents cannot message each other; the coordinator relays. Every agent's final
report ends with an **Interface notes** section (what others must know) and an
**Open questions** section; the coordinator forwards those verbatim.

| Role | Owns (writes) | Must not write | Reports to the coordinator |
| --- | --- | --- | --- |
| Builder A: perception | `perception/*.py` (controller, motion, hand heuristics, store, identity, retention) | server/, phone/, tests, docs | module APIs with exact signatures |
| Builder B: server | `server/memory_app.py`, `server/*.py` non-test, `phone/serve.py`, `scripts/` | perception/, browser JS, tests, docs | routes, env vars, allowlists |
| Builder C: browser | `phone/memory.html`, `phone/assets/*` | serve.py, server/, perception/, tests, docs | module exports, worker protocol, UI states |
| Tester | `server/test_*.py`, `perception/test_*.py`, `server/fixtures/**`, `phone/test/**` | production code | red tests first, then verdicts with exact counts |
| Oversight | `docs/OVERSIGHT_*.md`, `docs/LICENSES.md` | code | plan adherence, licence/commercial findings, blockers |
| Finance | `docs/FINANCE.md` | code | unit economics, cost caps the builders must respect |

Checkpoint cadence, every checkpoint:

1. Coordinator publishes the checkpoint scope (below) and the interfaces.
2. Tester writes the acceptance tests and fixtures **first** (red). Oversight reviews
   the scope against the spec and the licence register. Finance states the cost
   constraints the checkpoint must respect.
3. Builders build in disjoint files. Each builder runs the existing suites before
   reporting; a builder never edits a test to make it pass.
4. Tester runs the checkpoint suite in a clean process and reports pass/fail/error
   per test with tracebacks. Coordinator relays failures to the owning builder.
5. Oversight reviews the diff: plan adherence, new dependencies, licences, any
   fabricated capability. Finance updates the cost model if the checkpoint changed
   a cost driver.
6. Coordinator records the result in `CONTINUATION_HANDOFF.md` section 5 and
   `RESEARCH_EXPERIMENTS.md`, commits, and transfers to the user's folder.

Hard rules carried from the handoff: no new runtime dependency without the
oversight agent's licence note; no model weights in git; no fake inference in
ordinary mode (a missing model is a visible `manual` capability, never a
simulated result); no `.env`, keys, real photos or private database contents read
for inspection; synthetic data only.

## 1. Checkpoint map

| CP | Theme | Spec item | Handoff / blockers closed | Gate advanced |
| --- | --- | --- | --- | --- |
| CP2 | Automatic capture path, cross-language controller equivalence, clock-only staleness | 4 (rig frame accounting, software half) | next step 6; open decisions 3, 10; B-01, B-02 (already), B-06, B-11; P-103 traces (synthetic) | G-TEST, G-PROV (hand model) |
| CP3 | Identity stage: embeddings, banks, conformal sets, calibration gate; group/clarify answers | 5 (memory logic half), 7 | open decisions 7, 8; B-03, B-05, B-14; D-008; P-104 protocol (code ready, data later) | G-PROV (DINOv2), G-TEST |
| CP4 | Idle keyframes, re-observation, containment, retention and SQL erasure, v1 migration | 3 (remaining retention tiers) | open decisions 4, 5, 6; B-07, B-08, B-09, B-10; P-107 | G-PRIV |
| CP5 | Resolver end to end, rubric harness on scripted synthetic episodes, UI smoke, frame counters | 5 (scripted cases), 7 | open decisions 8, 9; B-15; P-106 (synthetic half), P-105 (software counters) | G-TEST complete; G-RIG ready for the user's iPhone |

Out of scope until the user says otherwise: Deepgram or any speech; the surface
atlas and landmark phrases (spec item 9); the Hand Sentinel decision (item 6, needs
real footage); any household recording (item 8, needs IRB); native build.

## 2. CP2 in detail (this round)

### Why this is next

The milestone-1 rig records episodes only when the user taps "mark"
(`capture_mode: manual`); `createAutomaticAdapter()` is a deliberately disabled
seam. The product is automatic. CP2 builds the automatic path end to end on
synthetic inputs, proves the browser and Python controllers are the same machine,
and settles the one licence question (the hand model) that decides whether the
automatic path can ship.

### Interfaces (fixed by the architect; builders implement, tester tests)

**Controller sample** (unchanged): `{t_ms:int, busy:bool|null, motion:bool|null, frame_valid:bool, gap?:bool}`;
actions as in `perception/episode_controller.py`. Both languages gain a replay entry point:

- Python: `perception/episode_controller.py` gets `replay(samples: list[dict]) -> list[dict]`
  returning `[{"t_ms":..., "actions":[...], "phase":...}]`, and a CLI
  `python -m perception.episode_controller trace.json` that prints the JSON list.
- JS: `phone/assets/controller.js` exports `replay(samples)` with the same output, and
  `phone/assets/controller-replay.mjs` is a Node entry: `node phone/assets/controller-replay.mjs trace.json`.
  No npm dependency; plain ESM.

**Motion energy** (new, non-neural, frame difference on the analysis-resolution grayscale):
pure function in both languages, `motionEnergy(prev: Uint8Array, next: Uint8Array, width, height) -> {energy: float 0..1, moving: bool}`
with hysteresis state passed explicitly: `motionStep(state, energy) -> [state, moving]`.
Thresholds live in one place per language and are mirrored: `MOTION_ON = 0.035`,
`MOTION_OFF = 0.015`, energy = mean absolute difference / 255 over pixels after a
3x3 box blur. These numbers are initial values to be measured on the rig (P-105); the
tester's golden arrays pin the arithmetic, not the product threshold.

**Hand busy heuristic** (new): pure function over landmark samples in the packet
format (`hands[].landmarks` 21 image-normalised points, `hand_bbox`), in both languages:
`handBusy(hands) -> {present: bool, busy: bool, basis: string}`. Busy means a hand is
present AND (mean fingertip-to-palm-centre distance below `CURL_RATIO = 0.55` of the
wrist-to-middle-MCP length, i.e. curled) OR the hand bbox centre is in the lower 60% of
the frame with bbox area at least 2% of the frame. `busy` is a heuristic for "the hand is
doing something", not contact; the basis string says which rule fired. `present=false`
yields `busy=null` for the controller (missing measurement never settles).

**Hand landmarker worker** (browser): `phone/assets/hand-worker.js` hosts MediaPipe
Tasks Vision HandLandmarker loaded **only** from same-origin `/assets/models/` (WASM,
JS, `.task`); the main thread posts `{type:'frame', t_ms, bitmap}` (transferable) and
receives `{type:'hands', t_ms, hands:[...], infer_ms}` or `{type:'unavailable', reason}`.
If any model asset is missing, the worker reports `unavailable` and the adapter stays
disabled with the reason shown in the camera status. The worker never fetches from a
CDN. `createAutomaticAdapter({worker})` returns `{enabled, reason, analyze(frame) ->
Promise<{busy, motion, frame_valid, hands}>}`.

**Model assets**: never committed. `scripts/fetch_models.py` (Builder B) downloads
pinned URLs with recorded SHA-256 into `phone/assets/models/`, writes
`phone/assets/models/MANIFEST.json` (url, sha256, version, licence, fetched_at), and
refuses to run unless `docs/LICENSES.md` (Oversight) has an entry for that asset.
`.gitignore` already excludes `*.task`; add `phone/assets/models/` except the manifest.

**Server**: `GET /api/health` adds `"models": [{name, provisioned: bool, licence_recorded: bool, version}]`
and `capabilities` reflects it (`automatic_hand_recognition` enabled only when the
hand model is provisioned, licence recorded, and `PAM_ENABLE_HAND_MODEL=1`). The asset
allowlist serves `/assets/models/<file>` only for files named in the manifest.
`GET /api/items?as_of=<ms>` and `POST /api/chat {text, as_of}` evaluate at a given
time (deterministic replay, B-11).

**Clock-only staleness** (Builder A, B-11): `answer_text` and `_projection` take the
evaluation time. A `placed` location whose observation is older than `AGE_STALE_MS =
24h` at evaluation time is answered `hedged` with `stale_reason` "age"; after 7 days it
is `abstain` unless re-observed (CP4 provides re-observation). The catalogue shows the
same ageing. No write is needed for an answer to age.

**Packets**: `capture_mode: "automatic"` packets carry `landmarks` samples and `gaps`
exactly as the contract already allows; nothing new in the schema.

### Deliverables by owner

Builder A: `episode_controller.replay` + CLI; `perception/motion.py`; `perception/hand_busy.py`;
age-based staleness in `episode_store.py` (`AGE_STALE_MS`, `AGE_ABSTAIN_MS`, evaluation
time threaded through `answer_text`/`list_items`/`get_item`); all existing suites still green.

Builder B: `as_of` on items and chat; health `models`; manifest-gated `/assets/models/`
serving; `scripts/fetch_models.py`; `PAM_ENABLE_HAND_MODEL` gate; existing suites green.

Builder C: `controller.replay` + `controller-replay.mjs`; `phone/assets/motion.js`;
`phone/assets/hand-busy.js`; `phone/assets/hand-worker.js`; `createAutomaticAdapter`
wired into `memory-camera.js` (automatic episodes use the controller actions to pin
keyframes and the burst, record gaps, and submit `capture_mode: "automatic"` packets);
camera status strings for `manual` vs `automatic` vs `unavailable`; the Stored-items
and Chat views unchanged except the age `stale_reason` rendering.

Tester: `server/fixtures/cp2/*.json` golden traces (fast put-down; long carry over
2 s; mid-episode gap; busy that ends before `BUSY_MIN_MS`; missing measurements never
settle; `MAX_EPISODE_MS` timeout; two back-to-back episodes; the landmark sets for
`handBusy`; two-frame arrays for `motionEnergy`); `server/test_cp2_controller.py`
running every trace through Python and Node and asserting identical action logs and
identical `handBusy`/`motionEnergy` outputs; `server/test_cp2_staleness.py` for B-11;
`server/test_cp2_models.py` (health `models`, allowlist gating, no serving without a
manifest entry, capability stays disabled without the env flag); `phone/test/test_ui_smoke.py`
with Playwright (container Chromium): sign in, Stored items empty state, Chat
abstains, Camera shows the manual state when the model is absent, and **no request
leaves the origin** (request interception).

Oversight: `docs/LICENSES.md` register (every runtime dependency and model asset with
licence, source URL, version, and whether commercial use is permitted); primary-source
verdict on the MediaPipe hand landmarker `.task` licence (B-05, C-03) and the
tasks-vision pin (B-06, D-014); confirmation that CP2 adds no AGPL/NC/research-only
component; `docs/OVERSIGHT_CP2.md` with plan-adherence findings on the final diff.

Finance: `docs/FINANCE.md` v1: cost per user-month for the rig (laptop server, zero
cloud) and for a hosted variant; per-line inputs with sources and dates; $5/$10/$15
sensitivity using the handoff's margin formula; the cost drivers CP2 to CP5 could move
(cloud chat tokens, storage of ~20 MB/day keyframes, egress, support) and the per-user
caps builders must respect; what must be measured before any margin claim.

### CP2 acceptance

- `server/test_cp2_*.py` and `phone/test/test_ui_smoke.py` pass; all six existing suites still pass.
- Both controllers produce identical action logs on every golden trace.
- With no model assets present, the app reports `automatic_hand_recognition: false` with
  a reason, the camera page says so, and automatic capture does not start.
- With the model present and licence recorded (only if Oversight clears it), the
  automatic adapter can produce a `capture_mode: automatic` packet from synthetic frames
  in the Playwright test; otherwise this case is recorded as blocked, not skipped silently.
- No request to a non-origin host from the page. No new npm or pip dependency at runtime.

### CP2 result (2026-10-08)

**Passed: 215/215 methods across the four CP2 suites and the six existing suites, 0 skips**
(controller 24, staleness 13, models 18, UI smoke 9, bootstrap 21, lifecycle 61, pipeline 48,
capture 8, interaction 7, private_files 6), reproduced independently by the coordinator.
One acceptance case is **blocked, not skipped**: the real hand model. Its licence line is
`UNVERIFIED` in `docs/LICENSES.md` because the model card PDF sits on a host the sandbox
cannot reach; the exact human steps are in `docs/OVERSIGHT_CP2.md` §0. The automatic
packet path is proven with a scripted worker (fake landmark results through the real
adapter, controller, camera, server and store).

Decisions made during CP2 (binding; each has a test):

1. Integral-float `t_ms` (JSON text `100.0`) is accepted as `100` at the trace boundary in
   both CLIs; `step()` itself still requires an int.
2. `hand_busy` accumulates with explicit loops in index order; no builtin `sum()` (CPython
   3.12+ compensated summation differs from 3.11 in the last bit).
3. Repeated `select_release` in one automatic episode replaces the previous release pin;
   `finish` never ships a packet without a rest keyframe (abort with gap reason
   "rest frame unavailable").
4. CSP: `script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; connect-src 'self'`
   (no `'unsafe-eval'`). `connect-src 'self'` is what blocks the MediaPipe bundle's
   telemetry POST; the user-facing disclosure obligation is recorded in `LICENSES.md`.
5. The licence register is structured: `licence_recorded` requires the asset's base file
   name and the token `VERIFIED-COMMERCIAL` on one line with neither `UNVERIFIED` nor
   `REJECTED`; `scripts/fetch_models.py` applies the same rule plus the licence id.
6. `@mediapipe/tasks-vision` pinned at **1.0.1** (D-014 resolved) with per-file SHA-256
   from the registry tarball; `hand_landmarker.task` pinned to `/float16/1/`, hash to be
   recorded by a human, never `/latest/`.
7. `/assets/models/*` is public (no session): non-personal upstream artifacts, served only
   when the manifest lists the file and `PAM_ENABLE_HAND_MODEL=1`.
8. Server policy wins over worker state for `automatic_hand_recognition`; the UI shows the
   server's reason.
9. Finance caps adopted as the builders' constraints (see `docs/FINANCE.md` §5): cloud chat
   hard cap $1.50 per household per UTC month with at most 10 calls/day by default on a
   tier at or below $1/$5 per MTok, bounded 2,000 input / 200 output tokens, one retry,
   no images to the provider; episodes soft 100/day, hard 200; packet median target
   ≤ 500 KB; one object per episode packet; retention default 90 days pending G-PRIV.

Human actions outstanding (from `OVERSIGHT_CP2.md` §0): open the hand-model model card and
transcribe its licence line; download `/float16/1/hand_landmarker.task` on the laptop and
record its SHA-256 in `docs/LICENSES.md` and `scripts/model_pins.json`; run
`python scripts/fetch_models.py`; run `server/test_cp2_controller.py` on the laptop's
Python 3.11; then the real-device check with `PAM_ENABLE_HAND_MODEL=1`.

### Not in CP2

Real hand-model accuracy, iPhone timing, battery, any claim about recall. Those are
P-101/P-103/P-105 on the user's device later.

## 3. CP3 to CP5 (scoped now, detailed at their start)

### CP3 in detail: identity (architect, 2026-10-09)

**Why this is next.** Today every observation is its own provisional candidate: the
system cannot say that this morning's sighting of the glasses and this afternoon's are
the same object, so it can never answer confidently about an item it has seen twice,
and lookalikes (two refills) are never distinguished. CP3 adds the identity stage
from Part 1 sections 3 and 5: an appearance embedding of the localized region, per-item
banks, conformal "same object" sets with an explicit calibration gate, cannot-link
enforcement, the `group` answer, and the two user corrections.

**Interfaces (fixed by the architect; builders implement, tester tests).**

*Embedder protocol* (`perception/identity.py`):
`class Embedder: name: str; version: str; dim: int; def embed(self, crop: np.ndarray[H,W,3] uint8, mask: np.ndarray[H,W] bool | None) -> np.ndarray[float32, dim]` returning an L2-normalised vector. Production: `DinoV2Embedder` over ONNX Runtime (`dinov2_vits14.onnx`, 224 px, mean of patch tokens whose patch overlaps the mask by at least 50 %, falling back to all patches when the mask is None or covers under 4 patches), loaded only through the model manifest gate (same `scripts/fetch_models.py` + `docs/LICENSES.md` rule as CP2; capability `physical_instance_recognition`). When the asset is absent the store runs with `embedder=None`: no embedding, identity stays `provisional`, nothing is simulated. Tests inject a deterministic `Embedder`.

*Bank and matcher*:
`ItemBank(item_id)` holds `[{observation_id, frame_id, embedder: "name@version", vector}]`, max 32 vectors (oldest evicted), `score(query) -> float` = max cosine over the bank. `ConformalMatcher(calibration)` with nonconformity `1 - cosine`; a calibration record is `{calibration_id, embedder: "name@version", alpha: 0.05, quantile: q, n: int, source: "synthetic"|"cute"|"own-footage", created_ms, approved: bool}` stored in a new `calibrations` table (approved only via `approve_calibration(calibration_id, actor)`, audited; the processor's `calibration` dict in `LocalObservation` must name a `calibration_id` that exists and is approved for identity to be `trusted`; CP2 fixture semantics are kept for the bootstrap suite by treating a `fixture_only: true` record as a code-only injection, as today). `match(query, banks, excluded) -> {"set": [item_id...], "scores": {item_id: cosine}, "state": "new"|"match"|"ambiguous"}`: set = items with nonconformity ≤ q, minus `excluded`; size 0 → `new`, size 1 → `match`, size > 1 → `ambiguous`. `calibrate(pairs: list[(cosine, same: bool)], alpha) -> quantile` is the split-conformal quantile over the *same*-pair nonconformities with the standard finite-sample correction; the tester checks coverage on held-out synthetic pairs.

*Cannot-links (B-03)*: observations co-visible in one frame can never be one item; the existing `local_cannot_links` table is consulted during matching: any item that holds an observation co-visible (same device, episode and frame) with the query observation is `excluded`. A failed registration or missing embedding never removes an existing cannot-link.

*Integration* (`process_pending`): after `localize`, for every observation with a region: crop at capture resolution, mask from the localizer's diff mask (new optional field `LocalObservation.mask_rle: str | None`, run-length over the bbox), `embed`, `match`. `match` → reuse `item_id` (identity `trusted` if the calibration is approved and the embedder matches the calibration's, else `provisional`); `new` → new item; `ambiguous` → new observation stored with `identity_state: "ambiguous"` and `candidates: [item_id...]` (new column on `local_observations`), and the projection marks every candidate item `identity_status: "ambiguous"` with `lookalikes: [item_id...]`. Embeddings live in a new `embeddings` table keyed by observation_id (vector as float32 bytes, embedder name@version); projection rebuild replays stored embeddings and decisions, never re-embeds (open decision 5).

*Answers* (`answer_text`): `group` when the matched members are mutual lookalikes (each is in the others' `lookalikes`) — text "I have N items that look alike; which one is yours?", `members` each with their own `reference_image`, `observed_at_ms`, `location_text` (only if that member's own location is placed/sighted) and `provenance: {"observation_id", "identity_status"}`; a group never upgrades any member's certainty (B-14). `clarify` stays for distinct items whose names match the words. `confident` requires a single matched member, trusted, placed, not aged.

*Corrections* (`perception/episode_store.py`): `link_items(keep_id, other_id, actor) -> dict` ("same object": refuses with `ValueError("cannot-link")` if any cannot-link exists between them; merges banks and observations under `keep_id`, tombstones `other_id`, audit row `user_linked`); `unlink_observation(observation_id, actor) -> dict` ("not this one": moves that observation to a new item, adds a cannot-link between the two items, audit row `user_unlinked`); both recorded in a new `corrections` table that `rebuild_all` replays in order. `actor` is the session role string ("caregiver_pin"), never a named person (B-15).

*Server* (Builder B): `POST /api/items/{id}/link {other_item_id}` → Item; `POST /api/items/{id}/observations/{obs}/unlink` → Item (the new one); `GET /api/items/{id}/evidence` → `{observations: [{observation_id, observed_at_ms, reference_image, image_url, identity_status, outcome, location_text}]}` with `GET /api/items/{id}/observations/{obs}/image` serving that observation's keyframe (same rules as the item image); 409 on cannot-link refusal with a safe message; `/api/chat` passes the `group` shape through with per-member fields; health `models` and capabilities include `physical_instance_recognition` from the same policy helper pattern as CP2 (`dinov2_vits14.onnx` provisioned + licence recorded + `PAM_ENABLE_IDENTITY_MODEL=1`).

*Browser* (Builder C): `group` answers render the members' photos side by side with "I can't tell these apart — which one is yours?" and tapping a member resubmits the chat as a clarify selection (existing mechanism); item detail gains an evidence list (each observation's photo, time, status) and two controls, "Same as another item…" (pick from the catalogue, confirm, calls link) and "Not this one" on an evidence row (confirm, calls unlink); 409 shows the safe reason; identity badge shows `ambiguous` with the lookalike count.

*Tester*: `server/test_cp3_identity.py` with a deterministic synthetic embedder (vectors from seeded per-instance prototypes plus bounded noise): new item on first sighting; re-match on a second sighting with the same calibration → one item, two observations; two lookalike prototypes inside the quantile → `ambiguous` with both candidates and a `group` chat answer with per-member provenance; cannot-link excludes a co-visible item from the set even when registration failed (B-03); `calibrate` coverage ≥ 1 − alpha on held-out synthetic pairs within tolerance; unapproved calibration never yields `trusted`; embedder absent → `provisional` only, capability false, no embedding rows; link/unlink corrections, 409 on cannot-link, replay after `rebuild_all` reproduces the same projection; `as_of` before a correction shows the pre-correction state. `server/test_cp3_api.py` for the routes (auth, origin, 404/409, evidence images profile-scoped). `phone/test/test_ui_smoke.py` extended: a seeded group answer renders N members and tapping one resolves; link and unlink from the detail view.

*Oversight*: DINOv2 ViT-S/14 ONNX provenance (the weights are released as PyTorch; the export needs torch at dev time — record the exact script, commit of `facebookresearch/dinov2`, and hash of the exported file in `LICENSES.md`; no export runs in the sandbox); CUTE licence (CC BY 4.0) and attribution text for the calibration source; confirm no embedding leaves the device in the rig; `docs/OVERSIGHT_CP3.md`.

*Finance*: DINOv2-S/14 CPU cost per crop on the laptop and in the hosted variant (2–4 crops per episode); storage of embeddings (384 floats × observations); update §2/§5 of `docs/FINANCE.md` if any cap changes.

**CP3 acceptance.** `server/test_cp3_*.py` and the extended smoke test pass; all CP1/CP2 suites still pass; with no identity model present the app reports `physical_instance_recognition: false` and identity never exceeds `provisional`; with the deterministic embedder the full chain new → match → ambiguous → group → correction → replay is proven; no new runtime dependency beyond `onnxruntime` (recorded in `LICENSES.md`); no request leaves the origin.

**Not in CP3.** Real DINOv2 accuracy on real objects (P-104 needs CUTE or own footage on the laptop), OCR, re-observation (CP4), room names.

### CP3 result (2026-10-09)

**Passed: 260/260 methods, 0 skips**, reproduced by the coordinator in a clean process:
new `server/test_cp3_identity.py` 28 and `server/test_cp3_api.py` 13; `phone/test/test_ui_smoke.py`
grown from 9 to 13 (group answer rendering and member choice, "Same as" and "Not this one"
from the detail view, 409 reason shown); every CP1/CP2 suite unchanged. Oversight's diff
review (`docs/OVERSIGHT_CP3.md`, pass 2) found the plan implemented with no fabricated
capability, no vector or score on any route, and `onnxruntime` as the only new runtime
dependency; its two medium findings (the cannot-link refusal wording, and `assign`
inferring cannot-links the user never asserted) were fixed before this result.

Decisions made during CP3 (binding; each has a test or a register row):

1. The identity model is a **local export**: DINOv2 ViT-S/14 weights (Apache-2.0,
   `facebookresearch/dinov2` at commit `7764ea0f`) are exported to ONNX on the laptop by
   `scripts/export_dinov2_onnx.py` (dev-only `torch`/`onnx` in `requirements-dev.txt`);
   the served app imports only `onnxruntime` (MIT, 1.30.0). The export records a
   provenance sidecar and the embedder tag is `dinov2_vits14@<hash16>-r1` (recipe tag).
2. Server-side models live in `server/models/` with their own manifest; the browser
   `/assets/models/` route refuses `.onnx` and the server manifest refuses `.task`, so a
   mislabelled file invalidates one inventory and never crosses to the other.
3. `physical_instance_recognition.enabled` requires a provisioned, licence-recorded model,
   `PAM_ENABLE_IDENTITY_MODEL=1` **and an approved calibration for the exact embedder tag**;
   an enabled model without one still runs and reports "no approved calibration: identity
   stays provisional", which is the correct state for the P-104 measurement.
4. Calibration sources are a closed set `synthetic | cute | holoassist | own-footage`;
   `synthetic` is never approved on the rig; CUTE calibrations carry the CC BY 4.0
   attribution text from `docs/LICENSES.md`.
5. `actor` on corrections and approvals is a closed server-chosen set
   (`caregiver_pin | operator | test`); request bodies never carry it (B-15).
6. A group answer carries `unresolved_observation_id`; tapping a member records only
   "this sighting is that item" (`assign_observation`); it adds no cannot-link between the
   candidates, so fragmented duplicates can still be merged later with "Same as".
7. No route returns embeddings, scores or banks; history records are scrubbed of
   numeric identity internals; embeddings never leave the device in the rig.
8. Deferred to CP4 with a note in `OVERSIGHT_CP3.md` §7: hand-hull exclusion from the
   identity crop, pinning the crop geometry into the embedder tag, the notices page,
   and re-pinning `onnxruntime`.

Human actions outstanding (`docs/OVERSIGHT_CP3.md` §0): create the export venv, clone
DINOv2 at the pinned commit, download the checkpoint and record its hash, run the
export, run `scripts/fetch_models.py`, then register and approve a real calibration
before enabling the capability. Until then identity stays provisional by design.

**CP4 retention.** Idle keyframe every 30 s in automatic mode to `POST /api/idle`; 24 h
idle cache; landmark reduction (decided at CP2 with Oversight): landmarks stay processing
inputs in the packet, and after `process_pending` completes the stored revision's landmark
samples are reduced to per-hand bbox plus the busy scalars, with raw landmarks retained at
most 72 h (spec rule; biometric-law exposure); rule-13 re-observation (negative re-observation sets `stale`, positive
promotes the idle frame into evidence); containment as `inferred`; retention windows
and `consent_version`; SQL erasure that redacts personal text in every revision, derived
view and index with replay that does not resurrect (B-07, P-107); WAL/journal privacy
test (B-09); the real v1 migration with dry-run (B-10). Oversight: data-class map for
G-PRIV. Finance: storage growth per user-day measured from the synthetic runs.

**CP5 resolver and harness.** Five shapes end to end with photo; `perception/rubric.py`
scoring every scripted query into the five outcomes with coverage reported separately;
the week-2-to-3 scripted cases as synthetic episode scripts; browser frame counters
posted to the server and stored; coverage-loss reporting; the Playwright smoke test
extended to a full placement-to-answer flow. After CP5 the user runs the rig on an
iPhone (P-101, P-103, P-105) and the numbers replace every "initial value" above.
