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

### CP4 in detail: re-observation, retention and erasure (architect, 2026-10-09)

**Why this is next.** After CP3 the system knows what it saw and when, but only when a
hand moved something. It cannot notice that an item is no longer where it was placed,
it keeps every keyframe forever, it still stores raw hand landmarks, and its erasure is
a logical tombstone over rows that still contain personal text. CP4 closes Part 1 rule
13 (re-observation), the retention tiers, and gates G-PRIV: blockers B-07, B-08, B-09,
B-10, plus the CP3 deferrals (hand hull, crop geometry in the embedder tag).

**Interfaces (fixed by the architect; builders implement, tester tests).**

*Idle keyframes* (C → B → A). In automatic mode, with the camera running, the
controller idle, motion off and no hand present for at least 2 s, the browser captures
one capture-resolution JPEG every `IDLE_KEYFRAME_MS = 30000` and posts it to
`POST /api/idle` as `{"schema_version": 1, "device_id", "session_id", "frame_id",
"t_ms", "clock_anchor": {mono_ms, wall_ms}, "capture": {width, height}, "jpeg_b64",
"motion_energy": float}`; body cap `MAX_IDLE_BYTES = 256 KiB`, target ≤ 64 KiB (JPEG
quality 0.5). No IndexedDB mirror: a failed post increments the browser's
`idle_dropped` counter and is coverage, not evidence. Server: protected, origin-checked,
413/400 as for episodes; store `ingest_idle(raw) -> {"frame_id", "retained": true,
"expires_at_ms"}`. Store table `idle_frames(profile_id, device_id, frame_id, t_wall_ms,
received_ms, width, height, jpeg BLOB, motion_energy, expires_at_ms, promoted INTEGER)`;
`expires_at_ms = received_ms + IDLE_TTL_MS (24 h)`; `expire_idle(now_ms)` hard-deletes
expired unpromoted rows (a rolling cache, not evidence); caps `IDLE_MAX_PER_DAY = 2880`,
`IDLE_CACHE_BYTES = 200 MiB` (oldest unpromoted evicted first). Idle frames are never
listed or served to the browser except when promoted (then as ordinary observation
images).

*Re-observation (rule 13; A)*. `reobserve(now_ms, *, limit=16) -> counts` runs in the
worker after `process_pending`: for every item whose location is `placed` or
`inferred` with a reference image, and every unprocessed idle frame from the same
device newer than that placement: register the idle frame to the item's reference
keyframe with the localizer's registration (same LK + partial-affine, same bounds);
registration fails → no decision (`result: "unknown"`); succeeds → `region_diff` =
mean absolute difference / 255 over the item's bbox after a 3×3 box blur (reuse
`perception/motion.py`): `≤ REOBS_SAME_MAX = 0.06` → `present`, `≥ REOBS_GONE_MIN =
0.18` → `gone`, between → `unknown`. With an embedder present, `present` additionally
requires the registered region's embedding to match the item's bank under the active
calibration (set contains the item); without one it is diff-only and the observation's
identity stays `provisional`. Table `reobservations(profile_id, item_id, frame_id,
t_wall_ms, result, region_diff, registered INTEGER, embedded INTEGER)`. Effects:
`present` → the idle frame is promoted (`promoted=1`, never expires) and a new
observation row is written with `outcome: "sighted"`, `source: "reobservation"`,
`location_text` and `location_status` inherited from the placement, `identity_state`
= the item's state if embedder-confirmed else `provisional`; the projection's
`observed_at_ms` advances (ageing resets without a hand event). `gone` → the item's
projection gets `location_status: "stale"`, `stale_reason: "negative_reobservation"`,
`stale_since_ms`; a later `present` reverses it. `unknown` → nothing. Thresholds are
initial values pending P-105; the tester pins the arithmetic with synthetic frames.

*Containment as `inferred` (A)*. When a placed item A's rest bbox lies at least 80 %
inside the rest bbox of another item B placed in the same frame, record
`containment(profile_id, inner_item, outer_item, since_ms, frame_id)` (most recent
wins; a pickup of A clears it). When B's location later changes (a new placement of
B, or B becomes stale), A's projection becomes `location_status: "inferred"`,
`location_text` = B's current location text, `inference: {"container": B,
"since_ms"}`; A's own last-observed location is kept in history. The answer shape for
an inferred location is `hedged` with text "I think {A} is with {B}, which I last saw
at {location}." A negative re-observation of A at its old place does not contradict an
inferred location (A is expected to be gone).

*Retention and consent (A, B)*. Table `retention(profile_id PRIMARY KEY,
consent_version TEXT, episodes_days INTEGER, idle_hours INTEGER, landmarks_hours
INTEGER, updated_ms)`; defaults 30, 24, 72 (changed from 90 on Finance's cost analysis; `consent_version` is the build constant `perception.consent.CONSENT_VERSION = "rig-2026-10"`);
`set_retention(**fields, actor)` audited; `apply_retention(now_ms) -> counts` runs in
the worker: (a) revisions older than `episodes_days` have their packet bytes replaced
by NULL and `redacted_reason = "retention"` (metadata, digests, observations and
embeddings stay; `reference_image`/`image_url` become null and the item shows
"evidence image expired"); (b) idle expiry as above; (c) *landmark reduction*: packets
older than `landmarks_hours` are rewritten with `landmarks: []` and a new server-only
optional field `landmark_summary: [{frame_id, t_ms, hands: [{hand_bbox, busy, basis}]}]`
(bounded as `landmarks` is); `parse_packet` accepts it, `ingest_episode` rejects a
client packet that carries it (400); `episode_revisions.reduced_ms` records when; the
stored transport/semantic digest columns are unchanged (duplicate detection uses the
columns, never re-hashing bytes). Reduction must leave the packet parseable and
`item_image` working.

*Erasure (B-07, B-08, P-107; A)*. `erase_item(item_id, actor) -> report` replaces the
CP1 `redact_item`: within one transaction it (1) tombstones the item and every item
reached by the CP1 co-visibility closure; (2) deletes `embeddings`, `reobservations`,
`containment` and promoted idle frames of those items and blanks their `corrections` rows (`erased=1`); (3)
rewrites `local_observations.record` to a minimal non-identifying stub `{"erased": true,
"observed_at_ms"}` (no label, bbox, location text, candidates or match); (4) blanks
`item_names.name`, `local_audit.detail` and `corrections.payload` text for those items
(row kept with `erased=1`); (5) NULLs the packet bytes of the affected revisions and
marks `redacted_reason = "erasure"`; (6) writes one audit row `erased` carrying only
counts. `erase_profile(actor, confirm)` does the same for everything in the profile and
also deletes unpromoted idle frames, calibrations stay (they are not personal), then
runs `VACUUM INTO` a fresh file and swaps it in under the private-file rules (documented
as reducing, not guaranteeing, residue — no forensic claim). `rebuild_all`, `as_of`
views, `/history`, `/evidence` and chat must never resurrect erased content; a resent
packet for an erased episode is refused by the existing tombstone. The old
`redact_item` name is kept as an alias. No SQL roles, no triggers that pretend to be
permissions (B-08): erasure is an explicit audited method behind the same actor rule.

*WAL and journal privacy (B-09; A)*. The store already opens with
`journal_mode=PERSIST`. Before the first `connect`, the database file and the
`-journal` sidecar are created through `private_append_fd` so SQLite inherits private
modes; after any write the store asserts (debug method `sidecar_report()`) that every
sidecar present (`-journal`, `-wal`, `-shm`) is owner-only on POSIX (mode 0600) and
carries the protected DACL on Windows, and the tester checks both paths it can.

*v1 migration (B-10; A)*. `migrate_v1(*, dry_run=True, actor) -> report`: reads the
legacy v1 tables (`objects`, `candidates`, `observations`, `decisions`, `api_calls`) and
converts each confirmed legacy observation into a new `local_observations` row with
`source: "legacy_v1"`, `identity_state: "provisional"` (never trusted), `outcome` from
the legacy event type, `location_text` from the legacy scene surface and room fields only (never the VLM description, geolocation, file paths or actor), `observed_at_ms`
from its timestamp, and no image (legacy frames are paths on disk, not stored bytes:
`reference_image` null); legacy budgets, unknown spend and leases are untouched;
`dry_run` returns counts and up to 5 sample rows without writing; a real run is one
transaction with a `migrations` row `{migration_id, from_version, counts, at_ms,
actor}` and is idempotent (a second run reports `already_migrated`). Any exception
rolls back everything. The tester builds the v1 fixture with the v1 `ObjectStore` API
(as `test_memory_lifecycle.py` does).

*Hand hull and crop geometry (CP3 deferrals; A)*. `perception/hand_hull.py:
hand_hull_mask(hands, width, height) -> np.ndarray[bool]` (convex hull of the 21
image-normalised points per hand, dilated by 3 % of the frame width); in
`process_pending` the identity crop's mask excludes the hull of any hand in the
landmark sample nearest in time (≤ 150 ms) to the keyframe; crop padding `CROP_PAD =
0.10` of the bbox on each side (clamped). Both rules are part of the embedder recipe:
`RECIPE = "r2"`, so any existing calibration for `r1` is not active for `r2` (the
server reports it).

*Server (B)*: `POST /api/idle`; `GET /api/retention` → the retention row plus live
counts (`idle_cached`, `idle_promoted`, `revisions_expired`, `landmarks_reduced`);
`PUT /api/retention {episodes_days (7..365), idle_hours (1..72), landmarks_hours (1..168)}`
→ the row (audited, actor literal; `consent_version` is a build constant, not a field); `POST /api/items/{id}/erase
{"confirm": "<item_id>"}` → report (409 on mismatch); `POST /api/erase-all {"confirm":
"ERASE EVERYTHING"}` → report; `POST /api/migrate {"dry_run": true|false}` — a real run
also requires env `PAM_ALLOW_MIGRATION=1` (503 otherwise); the worker loop calls
`expire_idle`, `apply_retention` and `reobserve` after each processing batch and at
least every 5 minutes; health adds `retention` counts; items carry `inference` and
`stale_since_ms`; `present_item` whitelists them. `redact_item` route, if any, maps to
`erase_item`.

*Browser (C)*: idle keyframe capture and post with the conditions above and the
counter in the camera summary; a "Privacy" view: retention settings (read, edit with
confirmation), the idle-cache and expiry counts, "Erase this item" in the item view and
"Erase everything" (typed confirmation), with the server's reports; rendering of
`inferred` ("probably with {B}, last seen at {location}"), `negative_reobservation`
("it was no longer there when Pam looked at {time}"), and "evidence image expired".

*Tester*: `server/test_cp4_idle.py` (caps, expiry, eviction, promotion, re-observation
present / gone / unknown on synthetic registered frames, ageing reset, stale reason,
embedder-confirmed vs diff-only identity), `server/test_cp4_containment.py`,
`server/test_cp4_retention.py` (windows, landmark reduction keeps packets parseable and
images servable, digests stable, `landmark_summary` rejected from clients),
`server/test_cp4_erasure.py` (P-107: synthetic PII markers planted in every text field
and every table vanish from every table, from `rebuild_all`, from `as_of` views, from
`/history`, `/evidence`, `/api/items`, chat, and from a byte scan of the main database
file after `erase_profile`; sidecar modes, B-09), `server/test_cp4_migration.py`
(v1 fixture → dry-run counts → real run → provisional-only rows, idempotence,
rollback on an injected failure, budgets untouched), `server/test_cp4_api.py` (routes,
auth, confirmations, env gate), `phone/test/test_ui_smoke.py` extended (idle post with
the fake camera, Privacy view, erase flow, inferred and negative-reobservation
rendering). No skipped-green tests.

*Oversight*: the G-PRIV data-class map (every table and column: personal or not,
retention window, which operation removes it, what survives as audit), consent-version
semantics and what a version bump must trigger, the biometric reduction (landmarks →
bbox + scalars at 72 h) against the spec rule, confirmation that erasure covers derived
data and that no claim of forensic erasure appears in code or UI; `docs/OVERSIGHT_CP4.md`.

*Finance*: storage per user-day measured from the tester's synthetic runs (durable
revisions, embeddings, idle cache) against the FINANCE caps; retention 30 vs 90 days;
update `docs/FINANCE.md` §5 if a cap moves.

**CP4 acceptance.** `server/test_cp4_*.py` and the extended smoke test pass; all earlier
suites still pass; a placed item becomes `stale/negative_reobservation` from an idle
frame alone and fresh again from a positive one; erased content is absent from every
read path and from the database bytes after `erase_profile`; a v1 fixture migrates to
provisional-only evidence and never to trusted; packets older than 72 h hold no raw
landmarks; no new runtime dependency; no request leaves the origin.

**Not in CP4.** Room names, OCR, the notices page (CP5), real-device thresholds.

### CP4 result (2026-10-10)

**Passed: 341/341 methods, 0 skips**, reproduced by the coordinator in a clean process: eight
new `server/test_cp4_*.py` suites (api 10, containment 9, erasure 7, fixtures 9, hull 4, idle 20,
migration 6, retention 10), `phone/test/test_ui_smoke.py` grown to 19 (Privacy view, consent
gate, erase flows, idle keyframe posting under a fake clock), every earlier suite unchanged.
Oversight's pass 2 (`docs/OVERSIGHT_CP4.md`) closes **G-PRIV from the software side**: every
reader filters erased rows; `secure_delete=ON`; private `VACUUM INTO` swap; no forensic claim in
any UI copy; the landmark summary schema is closed; migration copies no prose, geolocation or
paths; the disclosure text covers each data class. What remains for G-PRIV is human (below).

Decisions made during CP4 (binding; each has a test):

1. **Consent gate.** `perception/consent.py` holds `CONSENT_VERSION` and `DISCLOSURE_TEXT`; the
   profile acknowledges a version (`acknowledged_version`, audited); `/api/episodes` and
   `/api/idle` refuse with 409 `consent_required` until it matches; rows are stamped with the
   version at ingest; a version bump stops capture until re-acknowledged and never lengthens
   retention or erases by itself.
2. **Retention default** `episodes_days = 30` (Finance: 30 vs 90 is $0.18/user-month hosted and
   shorter is better for privacy); idle 24 h; landmarks 72 h; ranges 7..365 / 1..72 / 1..168.
3. **Rule 13 is continuous but bounded:** hourly refresh per item, an unchanged-frame gate that
   compares the previous decision's bbox window (a whole-frame gate hid removals of small
   objects — the tester caught it), and a per-day compute budget `REOBS_CPU_BUDGET_S = 300`
   with `reobs_deferred` (embeds skipped, decisions diff-only). `reobservations` rows expire with
   `episodes_days`; promoted idle stills follow `episodes_days` and are labelled "seen while idle".
4. **Erasure** stubs observations (`erased=1`, filtered by every reader), blanks names, audit
   detail and corrections, NULLs packet bytes, deletes embeddings/reobservations/containment and
   `own-footage` calibrations, and (profile) swaps in a `VACUUM INTO` copy created privately;
   `secure_delete=ON` on every connection; erase-all requires the typed phrase and the PIN again;
   captures dated before an erasure are refused (`erased_before`, 5-minute phone-clock tolerance).
5. **Superseded revisions** lose their packet bytes after 72 h (`redacted_reason 'superseded'`);
   the item image is served from the newest accepted revision; digest columns never change.
6. **Hand hull:** identity crops exclude the dilated hull of any hand within 150 ms; a crop whose
   surviving mask is under 25 % is not embedded at all (`embedding_skipped_hand`, reason
   "hand covers the region"); landmark reduction skips revisions still waiting to be processed.
   Recipe tag `r2`; crop padding 10 %.
7. **Migration** converts confirmed legacy objects to provisional-only evidence with
   `location_text = "{surface}, {room}"`, counts legacy media files and never touches them,
   is idempotent and rolls back whole.
8. **Hosted variant rule:** one SQLite file per household (the erasure swap rewrites the file).

Human actions outstanding (`docs/OVERSIGHT_CP4.md` §P2.6): the signed landmark release for
anyone whose hands are in frame on the rig; confirm the BIPA §15 wording at the primary source
before any consent packet is used with a household; the Windows laptop run of `sidecar_report()`,
the PRAGMAs and the erase-all swap path; the Playwright no-egress smoke test with real assets.

**CP5 resolver and harness.** Five shapes end to end with photo; `perception/rubric.py`
scoring every scripted query into the five outcomes with coverage reported separately;
the week-2-to-3 scripted cases as synthetic episode scripts; browser frame counters
posted to the server and stored; coverage-loss reporting; the Playwright smoke test
extended to a full placement-to-answer flow. After CP5 the user runs the rig on an
iPhone (P-101, P-103, P-105) and the numbers replace every "initial value" above.
