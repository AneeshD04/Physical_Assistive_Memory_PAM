# ARCH review of MEMORY_SYSTEM_V4 (final, round 2, revised after cross-review)

Reviewer: ARCH (systems architecture). Materials: `spec/MEMORY_SYSTEM_V4.md` (Part 1 authoritative, L1–L250; Part 2 L252–L429 cited for context only), `spec/ROUND4_RESPONSE.md`, `code/perception/{object_memory,interaction,capture,personal_memory,memory_pipeline}.py`, `code/server/{app,object_api}.py`, `code/phone/{serve.py,index.html}`, `code/CLAUDE.md`, and in round 2 `final/PERCEPTION.md`, `final/MEMORY.md`, `final/COMMERCIAL.md` in full.

Line numbers `L…` are from `spec/MEMORY_SYSTEM_V4.md` as exported. File line numbers are from the reviewed code.

Marking: **[V: url]** = a page I opened during this review; **[V-peer: url]** = a page a named peer opened and cited, which I did not re-open; **[B]** = belief. Numbers the spec asserts without a source (Pixel 6 timings at L113, "20 to 40 ms" at Part 2 L345) are marked [B].

---

## Round 2 changes

What changed between the round-1 final and this document, and why. Each item names the peer whose answer drove it.

1. **BL-2 resolved (PERCEPTION A1).** `carry_flow` stays in v1 on an optional `carry_burst[]` in the packet: up to 10 consecutive analysis-resolution grayscale JPEGs at 10 fps centred on the carry, present only for carries ≥ 0.5 s; the localizer returns `none` for `carry_flow` when actual spacing exceeds 150 ms. The phone remains hand-only.
2. **BL-5 resolved (MEMORY A1).** A fourth shape `group`, and the Answer is restructured around `members[]` (0 for abstain, 1 for confident/hedged, 2..N for group). The round-1 answer-contract field list in 2.5 is replaced.
3. **BL-6 resolved (MEMORY A5).** The localizer contract gains `container_region {frame_id, bbox, item_id | null, confidence} | null`, frozen now as optional-null; automatic containment is reported, not gated, and case 5 is scored on ledger logic with hand-labelled containment events in v1.
4. **BL-7 resolved (PERCEPTION A4).** There is no cheaper hand model inside MediaPipe; a no-hand frame already costs one palm-detector pass, the heavier of the two models. The tier-1 gate is non-neural (frame-difference energy) with a 1 Hz heartbeat, and `numHands = 1` outside Active.
5. **BL-8 resolved (MEMORY A6).** `stale` has four recorded reasons: `coverage_loss`, `negative_reobservation`, `age` (initial 12 h), `other_person_handling`; any reason yields `hedged`, never `abstain`.
6. **BL-9.4 resolved (MEMORY A2).** Re-observation is now a defined stage: idle keyframes stored at capture resolution, indexed at arrival with DINOv2-S at 518 px, scored at query over the 24 h cache, refined on at most 3 frames with RepViT-SAM, accepted only as a conformal singleton; 2 s hard timeout.
7. **BL-9.5 resolved (MEMORY A4), replacing my 2.1 idempotency rule.** Phone-minted deterministic `episode_id`; byte-identical replays; same id + same digest = no-op; same id + different digest = `episode_revisions` (superset or conflict), never an error back to the phone. I accept the departure (section 7, item e).
8. **BL-1 confirmed and tightened (PERCEPTION A5).** The hand-only controller stands; the phone's Escalating→Active signal is renamed "hand busy" (a recall-tuned capture trigger), and the contact decision that reaches the ledger is the laptop's pre/rest difference.
9. **New BL-10 (PERCEPTION A4).** Realistic Safari landmarker cost is 60–150 ms per frame, so 10 fps landmarks is at risk; L134's "A lower active rate is not acceptable" must be split into a hard 10 fps capture rate into the ring buffer and a measured landmark rate; L180's "3 consecutive 10 fps frames" becomes "3 consecutive analysed frames within 500 ms".
10. **New BL-11 (COMMERCIAL 4.4).** Persisted 21-point landmarks for every hand, and a stored per-person hand template, are a biometric-law surface. The packet keeps landmarks; the server reduces them after localization under a retention rule; the wearer calibration is a per-session scalar plus a wearer-only bank with a written release; no template for anyone else. Spec rule 8 and the schema change; the packet contract does not.
11. **Reliable sighting redefined (MEMORY C, PERCEPTION D).** A split-conformal prediction set over the exemplar bank replaces the 0.15 margin; the margin survives only as the logged interim (`calibration_id = margin_0.15_initial`) until the CUTE and rig calibration sets exist. Mean-patch foreground-masked DINOv2 is the matching vector; the localizer must emit a mask per identity crop.
12. **Risk order changed (PERCEPTION reactions 2).** Hand presence and landmark rate from the mount is now R1; localization R2; escalation latency R3; identity calibration R4; Safari sustain R5.
13. **Section 4 numbers updated.** Planning number 60–150 ms per analysed frame on a 2021-era iPhone, 30–60 ms on a 2024-era one with the WebGL delegate working in the Worker (PERCEPTION A, [V-peer] for the 2021 TF.js figures).
14. **Gap map additions.** whisper offline as primary STT with Deepgram Nova-3 as the opted-out fallback (MEMORY F, COMMERCIAL A5); PaddleOCR PP-OCRv5 mobile as rig OCR (PERCEPTION E); RepViT-SAM as proposer (PERCEPTION A2); SigLIP 2 zero-shot category and `is_container` at indexing (MEMORY D); `episode_revisions`, `reports`, `lookalike_links`, `item_current` (MEMORY B); `retention_until`, `consent_version`, caregiver withdrawal by version bump (COMMERCIAL 4.6); repo purge and CI licence gate (COMMERCIAL 7); third-party notices page and checkpoint pins by hash (COMMERCIAL A1, A2); `deployment_profile` (family | agency) gating all non-BAA egress (COMMERCIAL 4.2).
15. **Build order changes.** Day 1 adds the repo purge; week 1 adds the CUTE identity calibration (needs no footage), the hypothesis layer against synthetic packets through the replay harness (MEMORY reactions 4), the microphone invariant, the caregiver consent and the mark decision; the local-LLM residue and the caregiver report UI move to weeks 5–6.
16. **Cost line note.** L197's Flux line is the wrong line for push-to-talk clips; Nova-3 pre-recorded is $0.0043/min [V-peer COMMERCIAL: https://www.deepgram.com/pricing], and with whisper offline the rig's STT cloud line is $0. Not my section; recorded because 2.6 depends on it.
17. **Correction to a peer.** COMMERCIAL 7.1 places `ultralytics` and `clip @ ultralytics/CLIP` in `server/requirements.txt`; in the reviewed tree they are in `perception/requirements.txt` (L1, L7). The purge is the same.

Verdict unchanged in direction, firmer in detail: the architecture holds; after this round all nine round-1 blockers have an agreed fix, two new ones (BL-10, BL-11) are spec-text changes, and nothing requires a redesign. The day-1 freeze (packet, localizer, controller, answer) can now be written from sections 1 and 2 without guessing.

---

## 1. Build blockers

Status after cross-review is given per item. "Resolved" means the fix below is agreed by the peer whose domain it is and goes into the day-1 spec freeze.

### BL-1. The Settled predicate needs an object region on the phone; tier 3 says the phone has none — RESOLVED (hand-only controller; PERCEPTION A5)

- L182: "Active to Settled: the tracked object region stationary (centroid moving under 2% of frame width) for 1.0 s with no hand within 1.5 hand-widths of it, outcome `placed`; or the hand leaves the frame with no object region tracked, outcome `lost_from_view`".
- L114 (tier 3): "Localization does not run here; it consumes the packet in tier 4".
- L66 (rule 4): "The object region comes from an explicit localization component (section 7)".

Fix: the phone controller is hand-only. Active→Settled when (a) "hand busy" has been negative for 1.0 s and the hand centroid has moved more than 1.5 hand-widths from the point where it went negative; or (b) no hand for 1.0 s; or (c) the 3 s gap. `outcome_hint ∈ released | hand_gone | gap`; the laptop localizer assigns `placed_on_surface | placed_in_container | lost_from_view | uncertain`. PERCEPTION A5: no landmark-only grasp classifier has published precision/recall; the phone's signal is a recall-tuned "hand busy" trigger (closed or pinching for 3 analysed frames) and must not be called contact anywhere in the contract; the contact decision that reaches the ledger is the pre/rest difference.

### BL-2. `carry_flow` cannot run on a 6-to-8-keyframe packet — RESOLVED (`carry_burst[]`; PERCEPTION A1)

- L115: "co-motion minus the hand hull during the carry"; L173: "6 to 8 entries ... The server never needs a frame that is not in the packet."

PERCEPTION's finding: the pyramidal LK search bound is not what breaks (15× the window at three levels, [V-peer: https://www.cs.ucf.edu/courses/cap4453/bouguetopticalflow.pdf]); the appearance change of a hand-held object over 300 ms and the hand hull moving are, and `CLAUDE.md` L185–L190 already records the failure at 333 ms. Usable spacing is about 100 ms. Fix: optional `carry_burst[]` of up to 10 consecutive analysis-resolution grayscale JPEGs at 10 fps (quality 80, ~8–12 KB each [B]), centred on the carry midpoint, present only when the controller saw a carry ≥ 0.5 s; the localizer sets `region_source = none` for `carry_flow` whenever the burst's actual spacing exceeds 150 ms and never runs LK across larger gaps. Burst at 320 px if the Worker budget allows (PERCEPTION C). The burst is cut from the ring buffer's 720p bitmaps at encode time, so it costs ten small encodes and no change to the analysis path.

### BL-3. The pre-roll's rate and cost are unspecified — OPEN, fix proposed (no peer objection)

- L112: "a bounded pre-roll of the last 2 s kept at capture resolution ... Under 5 ms plus the hand check"; L118: "On the rig that is 720p"; Part 2 L346: "last 2 s of 720p JPEG in memory, about 1 MB".

At ~20 KB per 720p JPEG (`CLAUDE.md` L433), 1 MB over 2 s is ~50 frames, i.e. continuous 25–30 fps JPEG encoding, which alone breaks the tier-1 budget. Fix: Part 1 states the pre-roll rate (initial: the idle analysis rate, 5 fps, rising to 10 fps in Escalating/Active), its representation, and that its cost is inside tier 1. Keep the last ≤10 `ImageBitmap`s in Idle (transferable, closable; **[V: https://developer.mozilla.org/en-US/docs/Web/API/ImageBitmap]**) and ≤20 in Active; encode to JPEG only on promotion, in the worker via `OffscreenCanvas.convertToBlob` (**[V: https://developer.mozilla.org/en-US/docs/Web/API/OffscreenCanvas/convertToBlob]**). With BL-10, the ring buffer is fed at the capture decimation rate (10 fps in Active) independent of the landmark rate.

### BL-4. Landmark coordinates are defined in frames the server never receives — OPEN, fix proposed (consistent with MediaPipe output)

- L173: "each hand is 21 points in the pixel coordinates of that frame"; L175: `association_to_hand {frame_id, hand_index, overlap}`.

MediaPipe returns landmarks normalised to [0, 1] of the input image (**[V: https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/web_js]**). Fix: landmarks and `hand_bbox` normalised to the capture frame; the packet carries `capture{width,height}` and `analysis{width,height}` once. PERCEPTION adds that the task resizes internally to 192/224 px, so "256 px downscale" (L112) buys nothing over 224 and the analysis size is chosen by the R1 experiment (256 vs 384), not fixed.

### BL-5. `identity_status = group` can never be answered, so case 4 cannot pass — RESOLVED (`group` shape; MEMORY A1)

- L189 reliable-sighting rule; L73 rule 11; Part 2 L374 case 4.

Fix: the Answer becomes `{shape ∈ confident | hedged | abstain | group, members[], index_pending, clarify {question, options[]} | null}` with each member `{item_id, reference_image {frame_id, bbox} | null, target_indicated, capture_time, identity_status, location_status, stale_reason, room, relevance}`. A group is the connected component of `lookalike_links` containing the queried item (a view, never a row; rule 11). Speech: "I have two that look the same: one here at 2 pm, one here at 4 pm." My condition: for voice, more than three members becomes `clarify` ("which one?") or `abstain`; members are ordered by recency. Members keep separate crops, masks and OCR fields so a later Rx read splits the group retroactively (MEMORY answers to PERCEPTION 4).

### BL-6. `placed_in_container` is an outcome, but no stage produces a container — RESOLVED (MEMORY A5)

Fix: the localizer gains `container_region {frame_id, bbox, item_id | null, confidence} | null`, frozen now as optional-null. Minimum evidence for a link, all required: (a) the rest frame has no accepted target region (object left its pre-contact position, no arrival blob); (b) the hand's release point lies inside the box of a second region that is itself a tracked item with `is_container` (set by user naming or SigLIP 2 zero-shot over a container vocabulary at indexing); (c) that region is present in the rest frame. Then `outcome = placed_in_container` and a `containment_links` row with `confidence = region_confidence × container_match`; removal when a later episode on the inner item has an accepted rest region outside the outer item. Automatic containment is beyond v1 (the best published tracker through containers reaches 16.0 % target IoU on invisible frames, [V-peer: https://ar5iv.labs.arxiv.org/html/2305.03052]); case 5 is scored on ledger logic with hand-labelled containment events, and the spec must say so.

### BL-7. The tier-1 "cheap hand check" is an unnamed component — RESOLVED (non-neural gate; PERCEPTION A4)

- L112: "cheap hand check | Under 5 ms plus the hand check".

PERCEPTION's finding (I accept it; section 7 item a): in a no-hand frame the task runs only the palm detector and skips the landmark model ([V-peer: https://raw.githubusercontent.com/google-ai-edge/mediapipe/master/docs/solutions/hands.md]); the palm detector is the heavier model (5.35 ms vs 2.40 ms on a 12700K; 97 vs 42.6 ms on a Pi 4, [V-peer: https://raw.githubusercontent.com/opencv/opencv_zoo/main/benchmark/README.md]); the JS API exposes no palm score [B]. Fix: tier 1 = frame-difference energy on the downscaled canvas gating the landmarker, a 1 Hz heartbeat call regardless, `numHands = 1` outside Active, raised to 2 in Active. Conditions: the energy test's region (PERCEPTION proposes the lower two-thirds) is initial and must be checked against hands entering from the side on a wheelchair mount; the runtime `setOptions` switch of `numHands` is [B] and is tested in week 1 (a re-init costs 1–3 s [B]); the skip rate is a week-1 counter.

### BL-8. `stale` has no transition rule — RESOLVED (MEMORY A6)

Fix: `stale_reason ∈ coverage_loss | negative_reobservation | age | other_person_handling`, recorded on `item_current`: `coverage_loss` = a `gaps[]`, screen-lock or Wi-Fi interval after the last reliable sighting longer than the max unobserved gap; `negative_reobservation` = a later idle frame whose global descriptor matches the item's last rest frame above the place threshold scores the item below the frame threshold at the registered location; `age` = initial 12 h; `other_person_handling` = a later episode on a durable item with `actor = other_person` and no accepted rest region. Any reason makes the shape `hedged` through the L189 rule; none makes it `abstain`; the speech names the reason.

### BL-9. Contract gaps that force guessing — statuses

1. **Keyframe selection rule** — OPEN, fix proposed: `pre_contact` = newest pre-roll frame with no hand detected; 3 `rest` frames at 0.33 s; shorter episodes send what exists, never padded.
2. **Pause semantics** — OPEN, fix proposed: blur and `head_turn` pause the Settled counter; the paused interval is appended to `gaps[]` with `reason`.
3. **The "qualified" answer** — RESOLVED: `relevance` is a field of every `members[]` entry; the "something I saw once this afternoon" sentence is a template keyed on `relevance = candidate` (MEMORY reactions 5).
4. **Re-observation stage** — RESOLVED (MEMORY A2, E): idle keyframes at capture resolution (720p, ~40–60 KB [B]); at arrival DINOv2-S/14 at 518 px long side, `global_vec` (384 × fp16) and a 2×2-pooled, PCA-64 `patch_index` (~27 KB per frame, ~77 MB per 24 h [B]); at query, exemplar-token vs index scoring over the cache most-recent-first (< 1 s [B]), then refinement on ≤ 3 frames (2.5× crop at full resolution, DINOv2 at 518 px, PerSAM-style confidence map, RepViT-SAM point-prompted, conformal check), accept only a singleton; hard timeout 2 s, after which the answer proceeds and says nothing about having looked. Floor: objects ≥ 28 px at index scale, ~12 cm within ~1.2 m [B]; the pilot reports the distance distribution of visible relocations so the index resolution can be raised where the data says so. Change L130 and Part 2 L347 from "low-resolution" to "capture resolution, indexed at 518 px".
5. **Clock and session** — RESOLVED (MEMORY B): `session_id` = a V4 UUID minted per page load, kept in `sessionStorage`; `episode_id = base32(sha256(device_id | session_id | round(t_start_mono × 1000)))[:26]`; `clock_anchor {t_mono, t_wall}` per packet; `decode_frame`'s 30 s window (`capture.py` L76) is deleted. My acceptance of the per-load session id: yes, the anchor must change with it anyway; `device_id` persists in `localStorage` so reinstalls do not collide [B on Safari persistence].
6. **Packet size** — OPEN, fix proposed: 4 MiB cap (`capture.py` L10, `app.py` L1085/L1131 are 1 MiB); the burst adds ~100 KB; idle keyframes are a separate message.
7. **Step 1 is stale** — unchanged: L238's line reference is to code already fixed (`serve.py` L45–L70; `CLAUDE.md` L804–L822); move the residual (key-file permission enforcement in `ensure_cert`) into step 2.
8. **Refractory vs. two items at once** — OPEN, fix proposed: the 0.5 s refractory (L183) applies to packet emission, not to hand analysis; a hand present during refractory re-enters Escalating.
9. **Two difference regions (new, PERCEPTION C / MEMORY answers to PERCEPTION 1).** `pre_rest_diff` is expected to yield two regions (where the object left, where it arrived) and sometimes a brushed second item. The localizer emits both as rival `region` hypotheses with their own `region_confidence` and `rival_of`; identity runs on both crops; two singleton matches to different items split the episode into two object events (L225's "two items at once"); both matching one item keeps the region nearest the release point; an ambiguous crop writes nothing to the bank. L175's one `target_region` becomes `target_regions[]` with at most two entries.

### BL-10 (new). L134's "A lower active rate is not acceptable" cannot hold for landmarks in Safari

- L134: "A lower active rate is not acceptable."; L180: "the grasp classifier positive in 3 consecutive 10 fps frames"; Part 2 L345: "Expect 20 to 40 ms per frame in JS" [B, no source].

PERCEPTION A4: the only published browser measurement is Google's 2021 TF.js blog for the previous solution, iPhone 11 at 8/5 fps (MediaPipe runtime, lite/full) and 15/12 fps (TF.js WebGL) [V-peer: https://blog.tensorflow.org/2021/11/3D-handpose.html], against 1.1/5.3 ms native on the same phone [V-peer: https://arxiv.org/pdf/2006.10214]. Planning number: 60–150 ms per analysed frame on a 2021-era iPhone, 30–60 ms on a 2024-era one with the WebGL delegate in the Worker [B]. Fix: split the two rates. Capture decimation into the ring buffer is 10 fps in Escalating/Active and is the hard floor L134 means; the landmark rate is measured (one frame in flight, drops counted in `landmarks[]` gaps); L180 reads "hand busy in 3 consecutive analysed frames within 500 ms"; the Settled "no hand for 1.0 s" counts wall time, not frames.

### BL-11 (new). Persisted hand geometry is a biometric-law surface (COMMERCIAL 4.4)

- L173: `landmarks[]` for every analysed frame; L70 (rule 8): "Hand size ... the appearance bank is supporting evidence; an optional 10-second wearer calibration seeds it".

COMMERCIAL: Illinois BIPA defines a biometric identifier to include a "scan of hand ... geometry" [V-peer: https://ilga.gov/legislation/publicacts/103/103-0769.htm]; Washington's definition turns on a stored template used to identify a specific individual [V-peer: RCW 19.375.010]. Fix (a retention and scope rule; the packet contract is unchanged): the packet keeps full landmarks because the localizer and the replay harness need them; after localization and hypothesis writing, the server reduces the stored landmark record to `hand_bbox`, `handedness`, per-frame `hand_present` and the wearer hand-size scalar, with the raw landmark file under its own `retention_until`; the wearer calibration is a per-session scalar plus a wearer-only appearance bank with a written release; `other_person` and `unknown` are the only non-wearer outputs, with no template for anyone else. My condition (section 7 item h): during weeks 1–4 on the team's own consented footage, raw landmarks are retained for the controller equivalence tests and the week-4 decision; the reduction rule applies to pilot households from the first recording.

---

## 2. Spec-vs-code gap map

For each stage contract (L169–L189): what exists today, what must be written, what must be deleted. Round-2 additions are marked (R2).

### 2.1 Episode packet (L173)

**Exists:**
- `perception/capture.py:encode_frame/decode_frame` (L49–L82): per-frame `CMP2` envelope (≤ 8 KiB header, ≤ 1 MiB, `captured_at, session_id, frame_id, location`), wall-clock skew check (L76), `location_at()` validation (L24–L46). Good validation discipline; wrong granularity.
- `phone/index.html`: `setInterval` at 10 fps (L160), `canvas.toBlob` JPEG q0.7 at 720p (L115–L123), `bufferedAmount` backpressure (L113), wake lock (L170), `visibilitychange` warning (L189–L191), `audio: false` (L141). Sends bare JPEGs; `decode_frame` returns `time_source="received"` (L61) and `personal_memory.process_frame` L192 returns early, so this page cannot drive personal memory today.
- `server/app.py:camera_stream` (L1092–L1187): monotone `frame_id` per `session_id` (L1145–L1152), per-frame relay to `wss://127.0.0.1:8765` (`open_camera_relay` L1079–L1086).

**Write new:**
- `perception/episode.py`: pydantic `EpisodePacket{episode_id, device_id, session_id, clock_anchor{t_mono,t_wall}, t_start, t_end, capture{width,height,fps_negotiated}, analysis{width,height}, keyframes[], carry_burst[]? (R2), landmarks[] (normalised), imu[], location, gaps[], quality, outcome_hint ∈ released|hand_gone|gap, counters}` with `extra="forbid", strict=True` as `object_memory.Candidate` (L40–L57). Reuse `capture.finite_number`, `location_at`.
- `phone/` JS: packet builder with the deterministic `episode_id` (BL-9.5); episode queue in memory with the IndexedDB mirror storing serialized bytes and deleting only on server ack (R2, MEMORY B); idle-keyframe message every 30 s at capture resolution (R2); seven frame counters and `getSettings()` record (L134).
- `server/episodes.py`: `/api/episodes` WebSocket, one packet per message; `packet_digest` over canonical JSON with JPEGs replaced by their sha256; same id + same digest → ack `duplicate`; same id + different digest → `episode_revisions` with `relation ∈ superset | conflict` computed server-side (superset = same `t_start/t_end/session_id/anchor`, keyframe set ⊇, landmark list a prefix-extension), ack `revised` or `conflict`, never an error (R2); keyframes written under `object_evidence/<episode_id>/` with `personal_memory._write_image`'s private-file discipline (L241–L247); arrival time stored separately from observation time (L148).

**Delete:** the per-frame relay chain (`camera_stream` forwarding, `open_camera_relay`, `glasses_rx.py`, `fake_glasses.py`), `_last_frame`/`_frame_now` (L553–L563), `capture.py` L76 skew rejection, `app.py:MemoryTail` (L284–L322), the memory.jsonl branch of `/api/push` (L352–L360), `/frames/` (L409–L419), `/api/es/*`.

### 2.2 Object-region localizer (L175)

**Exists:** nothing that takes a packet. Reusable: `memory_pipeline.py:ego_homography` (L74–L87; measured 7.6 ms on the Mac, 13–39 ms on the Windows laptop, `CLAUDE.md` L182, L427), `personal_memory.PersonalMemory._overlap` (L186–L189). The current object region is a YOLOE box (`memory_pipeline.py` L451–L458); the crop is cut in `personal_memory._submit` (L261–L269).

**Write new:**
- `perception/localizer.py:localize(packet) -> Localization` with `target_regions[]` (≤ 2, rival), `region_source`, `region_confidence`, `association_to_hand`, `association_to_pre_contact_object`, `association_to_resting_object`, `container_region | null` (R2), `crops[]` each `{frame_id, bbox, mask_path, purpose ∈ identity_224 | ocr_full}` (R2: mask required for foreground-pooled identity, MEMORY question to PERCEPTION 1; a GrabCut-style mask inside the diff region is acceptable when RepViT-SAM is too slow per episode [B]). `pre_rest_diff`: register with `ego_homography` when `imu ≠ still`; difference a structure map (gradient orientation or local SSIM) rather than raw intensity so auto-exposure and white-balance shifts do not become blobs (R2, PERCEPTION C); per-region 0.5–30 % area window; prefer the region nearest the release point, keep the other as rival. `carry_flow` on `carry_burst[]` with the 150 ms spacing guard (R2). `proposer`: RepViT-SAM (Apache-2.0 [V-peer: https://raw.githubusercontent.com/THU-MIG/RepViT/main/LICENSE]), point/box-prompted from the hand's last position and the diff blob, encoding a 2.5× hand-box crop; a few hundred ms on CPU [B], inside the tier-4 0.3–1 s budget because it runs only when differencing fails (R2, PERCEPTION A2; COMMERCIAL: record SA-1B provenance, prefer SAM 2 where latency allows). Identity crops cut from the 720p keyframe at native resolution and padded, never upsampled from the 256 px frame (PERCEPTION D).
- OCR (R2, PERCEPTION E): PaddleOCR PP-OCRv5 mobile (Apache-2.0 [V-peer: https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/LICENSE]) on the rig; Apple Vision when the server is a Mac (an OS API, not under Apple's research model licence, COMMERCIAL A3); per-field confidence stored, sub-threshold fields treated as absent. L101 ("Tesseract or the Vision framework") becomes "PaddleOCR, Vision on a Mac, Tesseract last resort".
- `perception/test_localizer.py`: IoU against hand-labelled boxes on recorded packets.

**Delete:** `ultralytics`/YOLOE/BoT-SORT (`memory_pipeline.py` L33, L299, L451; `perception/requirements.txt` L1 `ultralytics`, L7 `clip @ git+https://github.com/ultralytics/CLIP.git`, both AGPL-3.0 [V-peer COMMERCIAL]), `Track` (L124–L132), arm-box heuristics (L471–L474), everything keyed by class (L319, L515–L517, L561–L565), the YOLOE `.pt` weights, `mobileclip2_b.ts` (Apple research-only licence [V-peer: https://raw.githubusercontent.com/apple/ml-mobileclip/main/LICENSE_MODELS]), `data/epic/P02_102.MP4` and `blockers/eval_epic.py` (CC BY-NC; `memory_pipeline.py` L3, `CLAUDE.md` L536, L554) (R2, COMMERCIAL 7).

### 2.3 Capture-mode controller (L177–L185)

**Exists:** `perception/interaction.py:InteractionTrack` (contact 0.3 s, rest 0.6 s, gap 0.8 s; contact = person-box overlap, L64); `memory_pipeline.py` gate constants (L44–L71); `phone/index.html` has no state machine.

**Write new (phone-side JavaScript; feasibility in section 4):**
- `capture.js`: `getUserMedia` 720p, `requestVideoFrameCallback` loop, decimation to 5 fps idle / 10 fps active into the ring buffer (BL-10), downscale canvas at the size chosen by R1 (256 vs 384), Laplacian sharpness, frame-difference energy gate (BL-7), `getSettings()` record, the seven counters plus the landmarker skip and drop counters.
- `hands.worker.js`: MediaPipe Tasks Vision `HandLandmarker` 1.1.0 (Apache-2.0 [V-peer: https://registry.npmjs.org/@mediapipe/tasks-vision/latest]) in a Worker (Google: "each detection blocks the main thread. You can prevent this by implementing web workers", **[V: https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/web_js]**), VIDEO mode, `numHands` 1 outside Active, one frame in flight, loaded at page start; served with the Apache-2.0 licence text and "Copyright Google LLC" on a third-party-notices page and the header kept in the bundle (R2, COMMERCIAL A1).
- `handbusy.js` (renamed from `grasp.js`, R2): finger-curl from `worldLandmarks` (metres, scale-free), 3 consecutive analysed frames within 500 ms; recall-tuned.
- `controller.js`: four states, the L179–L183 predicates with BL-1, BL-9.2, BL-9.8 and BL-10 amendments, transition log with cause and timestamp (L185).
- `ring.js`: BL-3 pre-roll; keyframe selection (BL-9.1); `carry_burst[]` extraction (BL-2).
- `motion.js`: `DeviceMotionEvent.requestPermission` from a tap in a secure context (**[V: https://developer.mozilla.org/en-US/docs/Web/API/DeviceMotionEvent/requestPermission_static]**), 60 Hz, `still | walking | head_turn | unknown`, denied/unavailable/interrupted (L142).
- `perception/controller.py`: Python reference implementation as a pure function of (landmark result, sharpness, IMU, t); replay harness over recorded landmark logs; equivalence tests with `controller.js`; port `test_interaction.py` cases.
- Product invariants built into the page (R2, COMMERCIAL 4.3): no `audio` track ever (`getUserMedia({audio:false})`, as L141 today); microphone only inside a push-to-talk `MediaRecorder` session; visible recording indicator; one-touch pause reachable by an aide (L91).

**Delete:** `InteractionTrack` and `test_interaction.py` after porting, the `memory_pipeline.py` gate, `index.html`'s `setInterval` loop.

### 2.4 Immediate indexing (L187)

**Exists:** `object_memory.py:ObjectStore.claim_next` (L282–L304): lease queue (`queued | processing | budget_wait | capacity_wait`, 300 s lease L290, 2-attempt limit L291, budget L296–L301), oldest-first (L292); `PersonalMemory._run/run_once` (L147–L183) worker. Keep the mechanics (L240). No image embedding model exists (`CLAUDE.md` L104–L108).

**Write new:**
- `index_jobs` table and `claim_next_index()` most-recent-first (L187), same lease pattern.
- `perception/embed.py`: DINOv2 ViT-S/14 pinned as `dinov2_vits14` by name and hash (Apache-2.0 [V-peer: https://raw.githubusercontent.com/facebookresearch/dinov2/main/LICENSE]; the same repo now hosts XRay-DINO and Cell-DINO under a noncommercial licence, so a wrong `torch.hub` entry point is a licence breach, COMMERCIAL A2); foreground-masked mean-patch as the identity vector with CLS kept as a tie-break vector (PERCEPTION D); SigLIP 2 `google/siglip2-base-patch16-256` (Apache-2.0 [V-peer: https://huggingface.co/google/siglip2-base-patch16-256]) image + text encoders.
- The index job per new candidate (R2, MEMORY D): DINOv2 exemplar (provisional tier), SigLIP 2 image embedding of the best crop, SigLIP 2 zero-shot `category` over a fixed household vocabulary and `is_container` over a container vocabulary, OCR fields if `ocr_full` exists. Exemplar bank tables with `tier ∈ trusted | provisional`, capacities 4/8, promotion rules (3 singleton episodes over 2 days with held-out singleton; user naming; OCR identifier on this and a trusted exemplar) (MEMORY C).
- Conformal calibration store: `calibrations{calibration_id, embedding_model, crop_bucket, alpha, q_hat, n, source}`; the interim entry `margin_0.15_initial` (R2).
- Query-time rule: `index_pending` if any candidate < 24 h is unindexed; synchronous embed past 15 min (L187); resolver re-run through the existing `notify` callback (`personal_memory.py` L136).

**Delete:** `personal_memory.EventVerifier`, `VERIFY_SYSTEM` (L26–L118), `ObjectStore.gallery` (L259–L280; rewrites `candidates.payload` at L278, violating rule 7), `apply_result`'s VLM semantics (L312–L359), `Verification` (field ideas go to `hypotheses` payloads), `vlm.py:describe_event/ask`, `memory.jsonl`; `api_calls` stays only for the L201 cloud tie-break budget, gated by `deployment_profile` (R2).

### 2.5 Answer / resolver (L189)

**Exists:** `server/object_api.py:find_objects` (L66–L101): word-match search (`ObjectStore.search` L487–L490, `_category` aliases L184–L190), four templated sentences, stale footnote at > 3600 s (`get_object` L480), card image (L96), maps link. `app.py:/api/find` (L444–L493) legacy path; `SYSTEM_PROMPT` L191, L199–L201.

**Write new:**
- `perception/resolver.py:answer(query) -> Answer` reading `item_current` only, never deriving at read time (R2, MEMORY question to ARCH 2: accepted). Fields per BL-5: `shape`, `members[]`, `index_pending`, `clarify`. `location_status ∈ placed | sighted | inferred | reported | stale | unknown` (R2: `reported` for caregiver reports, MEMORY G). Reliable sighting (R2, replaces the L189 sentence): identity head has conformal `set_size = 1` at the item's α (0.05; 0.01 for medication, where `confident` additionally requires an OCR identifier or user naming on the matched exemplar), `location.status ∈ {placed, sighted}`, crop passed the quality gate, no co-visibility contradiction, most recent `location` hypothesis by `t_observed`. `stale_reason` per BL-8. `room = "room unknown"` until a source exists (L74).
- Query rule (R2, MEMORY D, accepted with the condition in section 7 item c): lexical match on names, aliases, categories and OCR text → set S; SigLIP 2 text-to-crop only when S is empty or to rerank by an attribute phrase; `group` when members share a `group_key`; one clarifying question at |S| ∈ {2, 3} built from the best-separating ledger field; ask for a name at |S| > 3; time/room slot parser first for time/place phrasings. The local-LLM residue (Qwen2.5-1.5B) and the cloud LLM are weeks 5–6 and `deployment_profile`-gated, not on the scripted-case path.
- Speech templates per shape; abstain never says "the last time I saw it" (L74); `reference_image.bbox` only when `target_indicated`; `relevance = candidate` template.
- `/api/answer`; the phone page renders photo + box, speaks with `speechSynthesis`, and supports a second push-to-talk round for `clarify` (R2). `/api/corrections` with source, meaning, timestamp, linked hypothesis (L87), parsed into `assert_hypothesis | merge | split | name` (MEMORY B).
- Re-observation on demand per BL-9.4 (R2): an arrival-time job on idle keyframes and a bounded query-time matcher with the 2 s timeout.

**Delete:** `find_objects`'s `placed` sentence as default (L79), `/api/find`'s jsonl branch, `es.py`, `places.py` Google resolution (`allow_google`, L537). Keep `_when()` (L51–L63) and the alias table.

### 2.6 Voice path

**Exists:** `app.py` is built around the Deepgram Voice Agent: `/api/dg-token` (L135–L151), `agent_config()` (L158–L170), `SYSTEM_PROMPT`/`FUNCTIONS` (L173–L256). The spec removes the Voice Agent (L204). `perception/voice.py` already runs `mlx-whisper` on a Mac (`CLAUDE.md` L493–L498).

**Write new (R2, MEMORY F; COMMERCIAL A5):** `/api/stt` accepting a push-to-talk `MediaRecorder` clip (Safari `audio/mp4` [B]; Deepgram accepts MP4/AAC/M4A without transcoding [V-peer: https://developers.deepgram.com/docs/supported-audio-formats]); primary STT faster-whisper or whisper.cpp `large-v3-turbo` (MIT [V-peer: https://huggingface.co/openai/whisper-large-v3-turbo]) offline on the laptop with `initial_prompt` seeded from the ledger's item names; fallback Deepgram Nova-3 pre-recorded with `mip_opt_out=true` on every request and no PHI without a BAA (COMMERCIAL A5, [V-peer: https://deepgram.com/legal/terms]); STT confidence logged per query, with "did you say your glasses?" when low (MEMORY F). `speechSynthesis` on the phone from the push-to-talk tap (iOS needs a user gesture for the first utterance [B]). My condition: whisper `large-v3-turbo` int8 latency on the Windows laptop CPU for a 5 s clip is a week-2 measurement; if over 2 s, fall to `small.en` with the vocabulary prompt.

**Delete:** `/api/dg-token`, `/api/agent-config`, `SYSTEM_PROMPT`, `FUNCTIONS`, `/api/fake-dg` (L1190–L1213), `AGENT_ROUTES` (L97–L104), and every non-memory function (calendar, reminders, flights, rides, doses) plus the face routes and modules (`/api/face/save|who|sync|restore`, `face_tools`, `es_faces`, L566–L619; "The ONLY call here that stores biometric", L568) (R2, COMMERCIAL 4.4). The caregiver PIN gate (`caregiver.require_caregiver`, L113–L119, L1098) survives behind the `auth.py` shim as the rig's "authenticated laptop service" (L21).

### 2.7 Data model (step 3, L240), cross-cutting

**Exists:** `ObjectStore` schema (L111–L138). Keep: the `observations` immutability guard (`_observe` L380–L384), `bindings` as the continuity idea (becomes `hypotheses(kind = identity, source = continuity)`), `decisions` as the audit log, `_private_file` discipline (L97–L99), `PRAGMA user_version` gate (L151; bump to 2 with `rebuild_all()` as the migration path, never a silent overwrite).

**New (R2, MEMORY B adopted; COMMERCIAL 4.6 conditions folded in):** three layers in SQLite ≥ 3.37 with `STRICT` tables and `journal_mode=WAL` (today `PERSIST`, L147; WAL is same-host, which the laptop is [V-peer: https://sqlite.org/wal.html]; check `sqlite3.sqlite_version` at startup, since the Windows laptop runs Python 3.11.0 [B that its bundled SQLite is ≥ 3.37]). Layer 1 immutable: `episodes` (with `anchor_mono/anchor_wall`, `packet_digest`, `packet_path`, `received_at`), `episode_revisions`, `keyframes`, `idle_keyframes` (with `global_vec`, `patch_index`, `expires_at`, `promoted_item_id`), `reports` (wearer corrections and caregiver reports as observations). Layer 2 append-only: `items` (with `merged_into`), `hypotheses` (`kind ∈ identity | actor | relevance | location | containment | region | name`, `version`, `supersedes`, `t_observed`, `payload`, `confidence`, `source`), `exemplars` (tier, crop, mask, embedding, `siglip_embedding`, `ocr_fields`, `retired_at`), `lookalike_links`, `containment_links` (cycle walk to depth 8 in Python inside `BEGIN IMMEDIATE`), `index_jobs`, `calibrations`. Layer 3 derived: `item_current` recomputed per item inside the writing transaction by one `recompute(item)`; `rebuild_all()` is the proof that it is a pure function of layers 1 and 2. Operations: `ingest`, `assert_hypothesis`, `merge`, `split`, `correct`, `recompute`. Immutability by `RAISE(ABORT)` triggers on layers 1 and 2.

Retention (R2, COMMERCIAL 4.6, as a condition on MEMORY's triggers): `retention_until` on `episodes`, `keyframes`, `idle_keyframes`, `reports` and the raw landmark file; a `media_retention{frame_id | episode_id, deleted_at, reason}` side table so retention deletes media files while the immutable rows and digests stay; `consent_version` on anything exported for training; caregiver withdrawal as a `source` version bump (`caregiver:<id>` → `caregiver:withdrawn`). `deployment_profile ∈ family | agency` in config, gating the cloud LLM, the Deepgram fallback and any labeling upload (COMMERCIAL 4.2).

Widen the state guard: `enqueue` L222–L227 and `get_object` L470 become the seven rule-4 outcomes plus `sighted` and `reported`.

**Blocking today:** `CLAUDE.md` L904–L909: 23 test methods error on `import doses` through `app.py`; `object_api.py` L13 imports `caregiver`. The `auth.py` shim and `app.py` trim (ROUND4_RESPONSE L64) are day-1 work.

---

## 3. Risk ranking: the five things most likely to make the six scripted cases fail

Reordered in round 2 (PERCEPTION reactions 2). Case numbers are Part 2 L369–L376.

### R1. Hands are not detected reliably, or landmarks run far below 10 fps, from the mount (fails everything: nothing escalates, or every episode is full of gaps)

Why: every tier above idle is gated on "a hand present" (L179). The task resizes internally to 192/224 px ([V-peer: OpenCV Zoo benchmark README; Tasks page]), so the spec's 256 px analysis is already the floor; a hand 0.7 m from a chest or wheelchair mount is tens of pixels at that size, seen from above and behind, often clipped at the bottom edge; default thresholds (0.5) were tuned for selfie-distance hands (**[V: web_js page]**). And the only published browser frame rates for this model family are 5–15 fps on an iPhone 11 ([V-peer: TF.js blog 2021]), against the spec's unsourced 20–40 ms. If detection is 60 % and landmarks run at 7 fps, the "2 consecutive analysis frames" rule opens an episode late or not at all, and `gaps[]` fills.

Experiment (week 1, two hours plus the benchmark page): on the mount, hands at 0.3, 0.6, 1.0 m, three grips, 20 s each, at 256 and 384 px input, GPU and CPU delegates; report landmark presence rate per condition and the Worker's delivered rate (p50/p95 ms per call, drops). The analysis size and the BL-10 landmark-rate expectation go into the spec from this table.

### R2. `pre_rest_diff` picks the wrong region on real surfaces (fails cases 1, 2, 4, 5 together)

Why: the hand's shadow, the sleeve, auto-exposure and white-balance shifts, the chair rolling (`CLAUDE.md` L175–L180), a brushed second item; on a cluttered counter several blobs fit the 0.5–30 % window. A confidently wrong crop is not an "ambiguous match" and would write to the bank. Round-2 mitigations: structure-map differencing, two rival regions, the conformal co-visibility check (section 2.2, 2.5).

Experiment (week 1): 30 handling clips on the mount in two rooms; hand-label the object box in pre-contact and rest keyframes; run `pre_rest_diff` alone; report IoU ≥ 0.5 rate, `none` rate and wrong-blob rate, split by `imu = still` vs. moving. First input to the week-4 decision (L243).

### R3. Escalation latency misses the fast put-down (case 3), compounded by BL-10

Why: idle at 2–5 fps + 2 consecutive hand frames + 60–150 ms per landmark call + 3 analysed "hand busy" frames is 1–2 s from first hand pixel to Active; a quick put-down is over in ~1.5 s. The pre-roll (BL-3) must hold the grasp phase at 10 fps from the moment of Escalating.

Experiment (week 1, one afternoon): 20 scripted fast put-downs with a second camera as ground truth; log every transition; report time-to-Active p50/p95 and the fraction of packets containing both a hand-busy-phase and a rest-phase keyframe, at idle 2 and 5 fps.

### R4. Identity calibration does not separate distinct items at α = 0.05 (coverage collapses) or the bank fragments on day one

Why: CUTE shows even DINOv2 ViT-B/14 at 336 px reaches only 61.8 % top-1 on paired lookalikes in the wild ([V-peer: https://arxiv.org/pdf/2311.00750]); PERCEPTION expects runner-up margins of 0.05–0.25 on distinct items [B]. Lookalikes go to `group` by rule; the risk is distinct items of one category (two different pill bottles) landing in empty or ≥ 2 sets, which either creates duplicate items (the fragmentation L120 warns about) or blocks `confident`. MEMORY's acceptance bar: conformal singleton rate ≥ 0.80 on distinct-instance queries; 5th-percentile intra-instance similarity above the 95th-percentile nearest-other similarity by ≥ 0.05; EER ≤ 10 %.

Experiment (week 1, no footage needed; then week 2 on the rig set): calibrate on CUTE (CC BY 4.0), then 10 household items × 10 crops on the rig camera at 0.5–2 m; foreground-masked mean-patch vs CLS; report EER, singleton rate at α = 0.05, empty-set rate on in-bank queries (fragmentation), per object class. If the bar fails, DINOv3 ViT-S/16 under its custom licence (COMMERCIAL: fallback only, licence snapshot, counsel initial) before anything larger.

### R5. The Safari pipeline degrades over 20 minutes (thermal, memory, drops), turning every answer `hedged`

Why: sustained landmarker + 10 fps ring buffer + keyframe encoding + WebSocket on a phone in a mount; every gap past 3 s is `uncertain` (L182) and every coverage loss after a sighting is `stale` (BL-8).

Experiment (week 1, the spec's step 4): the benchmark page, 20 minutes on the mount, per-stage p50/p95, dropped frames from `requestVideoFrameCallback` metadata (**[V: https://developer.mozilla.org/en-US/docs/Web/API/HTMLVideoElement/requestVideoFrameCallback]**), fps trend, bitmaps in flight, memory high-water mark.

Next two: (R6) retrieval for elderly phrasing (case 1): no defensible top-1 exists (MEMORY A3); the experiment is 50 crops × 20 phrasings on the lexical path vs SigLIP text-to-crop, plus a one-clarifying-question arm, because success after one question is the number the product runs on. (R7) the re-observation 2 s timeout and the arrival-time 518 px index cost on the laptop CPU (100–250 ms per idle frame [B]), measured in week 2.

---

## 4. Feasibility of the phone-side JavaScript stages in Safari

### 4.1 Capture at 720p

- Realistic. `index.html` L139–L142 already requests `{facingMode: environment, 1280×720}`; `getSettings()` reports the negotiated mode. `getUserMedia` works in home-screen (standalone) web apps since iOS 13.4 (**[V: https://bugs.webkit.org/show_bug.cgi?id=185448]**). In iOS 26 Safari treats every site added to the home screen as a web app by default (**[V, secondary: https://gigazine.net/gsc_news/en/20250623-safari-26-webkit-beta]**).
- `requestVideoFrameCallback` gives `presentedFrames` for missed-frame accounting (**[V]**); use it instead of `setInterval` (L160). First Safari version [B] 15.4.
- Will bite: camera stops on backgrounding and screen lock (L140); auto-exposure drift between pre-contact and rest (R2, mitigated by structure-map differencing); `MediaStreamTrackProcessor` is not Baseline and worker-only where it exists (**[V: https://developer.mozilla.org/en-US/docs/Web/API/MediaStreamTrackProcessor]**), treat as unavailable in Safari [B], so frames are pulled on the main thread with `createImageBitmap(video)` or `new VideoFrame(video)` (Baseline since September 2024, transferable, **[V: https://developer.mozilla.org/en-US/docs/Web/API/VideoFrame]**), 1–3 ms per analysed frame [B]; `applyConstraints` mid-stream is a policy no-go (L128).

### 4.2 MediaPipe Hand Landmarker in a Web Worker

- Realistic, slower than the spec assumes. Google recommends workers (**[V]**); `OffscreenCanvas` is Baseline since March 2023 (Safari 16.4) and worker-usable (**[V: https://developer.mozilla.org/en-US/docs/Web/API/OffscreenCanvas]**); WebGL contexts in workers on Safari [B] 17.0. GPU delegate needs WebGL2 on an `OffscreenCanvas` in the worker; failing that, the WASM CPU path, 2–3× slower [B].
- Planning numbers (R2): 60–150 ms per analysed frame on a 2021-era iPhone, 30–60 ms on a 2024-era one with the GPU delegate [B, from PERCEPTION's [V-peer] 2021 iPhone 11 figures of 5–15 fps and the 1.1/5.3 ms native figures]. The Pixel 6 17/12 ms at L113 is native and not a browser number. Design consequence: BL-10.
- Will bite: model and WASM load 1–3 s [B], do it at page start; one worker serialises inference, keep one frame in flight and count drops; `close()` every transferred `ImageBitmap`/`VideoFrame` (**[V]**) or the page leaks to a jetsam kill in minutes [B]; `numHands = 2` makes the legacy graph re-run palm detection every frame while one hand is tracked [B, PERCEPTION], hence `numHands = 1` outside Active; the runtime `setOptions` switch is [B] and is measured in week 1; landmarks are normalised [0, 1] (**[V]**), the BL-4 convention.

### 4.3 "Hand busy" heuristic (was "grasp")

- Realistic as a recall-tuned capture trigger only (PERCEPTION A5): finger curl from `worldLandmarks` (metres, **[V]**), 3 consecutive analysed frames within 500 ms. False positives cost a packet; false negatives cost an episode, so tune for recall. It does not see the object; the laptop's pre/rest difference is the contact decision.
- Will bite: self-occlusion from a chest/wheelchair view; landmark jitter at the analysis size for a hand 1 m away (R1).

### 4.4 Episode state machine

- Realistic and cheap. Design problems are BL-1, BL-9.2, BL-9.8, BL-10, all resolved or proposed above. Pure function of (landmark result, sharpness, IMU, t) so the Python reference replays logs identically; MEMORY's replay harness consumes the same logs.

### 4.5 Ring buffer and `carry_burst[]`

- Realistic with BL-3: ≤ 10 `ImageBitmap`s in Idle, ≤ 20 in Active at 10 fps (~75 MB at 720p [B]); encode on promotion via `convertToBlob` in the worker (**[V]**); the burst is ten 320 px grayscale encodes from the same bitmaps (R2).
- Will bite: unpublished per-page memory ceilings on iOS Safari [B]; cap bitmaps in flight hard and count them.

### 4.6 WebSocket packets, idle keyframes and the IndexedDB mirror

- Realistic. Packets of a few hundred KB (plus ~100 KB burst) over LAN; the `bufferedAmount` pattern (L113) becomes "queue, never drop" for episodes. Idle keyframes are now capture-resolution (R2, BL-9.4): ~50 KB every 30 s ≈ 6 MB/h ≈ 100 MB per 16 h day on the rig, plus ~15 MB of episodes; the rig's bytes-per-hour is transport work the native target keeps internal (L132), so the number must be reported as rig transport, not radio.
- Mirror: Safari evicts an origin's script-written data after seven days of browser use with no interaction, and LRU under pressure (**[V: https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria]**); the rig page is tapped daily, so LRU pressure is the real risk and the mirror stays best-effort (L148). The mirror stores serialized packet bytes and deletes only on server ack (R2).
- Screen Wake Lock is Baseline since March 2025 and released whenever the document is hidden (**[V: https://developer.mozilla.org/en-US/docs/Web/API/Screen_Wake_Lock_API]**); re-request on `visibilitychange`, which `index.html` L170 does not do.
- Self-signed cert trust on the phone remains the setup friction (`serve.py` L23–L29).

### 4.7 Voice pieces

- `MediaRecorder` is Baseline since April 2021 (**[V: https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder]**); Safari emits `audio/mp4` [B], accepted by whisper (via ffmpeg) and Deepgram ([V-peer]). `speechSynthesis` needs a user gesture for the first utterance on iOS [B]; the push-to-talk tap provides it. No audio track in `getUserMedia`, ever (product invariant, COMMERCIAL 4.3).
- WebGPU shipped in Safari 26 (**[V, secondary: gigazine WWDC25 report]**), consistent with L144; not needed for the rig.

### 4.8 What to measure in week 1 (adds to the seven counters at L134)

1. Per stage, p50/p95 ms on the phone: frame grab + bitmap/VideoFrame, downscale, sharpness/diff, landmarker (CPU vs GPU delegate; 256 vs 384 px), hand-busy, 720p JPEG encode, 320 px burst encode, packet build; worker vs main thread.
2. Delivered camera fps vs `presentedFrames` over 20 minutes; the fps trend (thermal).
3. Landmark presence rate vs distance and grip; the Worker's delivered landmark rate (R1).
4. Time from first hand frame to Active, p50/p95, at idle 2 and 5 fps (R3).
5. Memory high-water mark; bitmaps in flight.
6. Bytes per hour at rest (with capture-resolution idle keyframes) and in a 10-handlings-in-2-minutes burst (L132).
7. `DeviceMotion` permission and delivered sample rate; `getUserMedia`, wake lock and `DeviceMotion` in standalone mode on the test iOS version (L140).
8. IndexedDB write/read-back of a 1 MB packet and survival across a reload; ack-then-delete.
9. Tier-1 landmarker skip rate from the energy gate; misses by hand entry edge (BL-7 condition).
10. `setOptions({numHands})` switch cost (BL-7 condition).

---

## 5. Build-order sanity

Section 10 (L234–L246) in one line: key route → rerun suite → data model → week-1 benchmark → weeks 2–3 whole chain → week-4 Sentinel decision → weeks 4–6 resolver and corrections → IRB → week 7+ atlas/native.

Problems (round-1 points 1–7 stand; round-2 additions marked):

1. Steps 1–2 are done except the `doses`/`caregiver` import failures (`CLAUDE.md` L904–L909); the `auth.py` shim and `app.py` trim are day-1 work.
2. The localizer (R2) has no step; it must be a week-1 experiment on recorded packets.
3. (Softened, MEMORY reactions 4.) The hypothesis/derivation layer and `recompute()` do not depend on packet fields and can start in week 1 against synthetic packets through the replay harness; only `episodes/keyframes` columns wait for packet v0, which is frozen on day 1–2 anyway.
4. Step 5 scores answers before step 7's resolver exists; a minimal resolver belongs in step 5.
5. Immediate indexing (case 1) and OCR (case 4) are in no step; SigLIP 2, DINOv2 and PaddleOCR setup precede weeks 2–3.
6. The IRB determination has lead time; file in week 1. Indicator, pause and the microphone invariant are phone-page features built with it.
7. The voice path is in no step; whisper offline and push-to-talk precede the UX work.
8. (R2, COMMERCIAL 7.) The repo purge (AGPL `ultralytics` and `ultralytics/CLIP`, YOLOE weights, `mobileclip2_b.ts`, the EPIC fixture and `eval_epic.py`, the face modules) with a history rewrite and a CI licence gate must happen on day 1, before the build branch exists, because rewriting history under parallel branches two weeks in is the expensive version of the same job.
9. (R2, PERCEPTION D / MEMORY C.) The identity calibration on CUTE needs no footage and belongs in week 1.
10. (R2, COMMERCIAL 5.) The mark decision precedes any pilot material; user-facing strings take the product name from config.

Proposed order:

- Day 1–2: repo purge and history rewrite; `pip-licenses` CI gate; `auth.py` shim, `app.py` trim, suite green; freeze packet v0, localizer, controller and answer contracts with BL-1 to BL-11 resolved in one page of spec text (including `members[]`, `group`, `reported`, `clarify`, `stale_reason`, `container_region`, `carry_burst[]`, normalised landmarks, `session_id`/anchor, the two-rate rule, the retention rule).
- Week 1, five parallel tracks: (a) phone recorder page: capture, landmarker in a worker, energy gate, counters, manual episode marks, packet upload, server sink; the 4.8 benchmark; indicator, pause, no-audio invariant. (b) Record 30 scripted episodes (fast put-down, caregiver move, purse, two bottles, clutter) in two rooms with a second camera; hand-label boxes and containment events. (c) Localizer experiment R2; hand-presence and landmark-rate study R1; CUTE calibration R4. (d) Hypothesis layer, `recompute()`, `rebuild_all()`, replay harness against synthetic packets; `controller.py` reference. (e) File the IRB determination; bystander plan with the microphone invariant; caregiver consent; store-trip connectivity (L146); choose and clear a mark; vendor data-flow table (`mip_opt_out`, Roboflow opt-out).
- Week 2: `controller.js` replaces manual marks; equivalence tests; escalation measurement R3; `episodes/keyframes` columns and ingestion with the idempotency rule; DINOv2/SigLIP/PaddleOCR services and the index job; rig-set calibration (R4) with `calibration_id`; whisper STT latency on the laptop; arrival-time idle index and the re-observation timeout (R7).
- Week 3: minimal resolver with the four shapes and `clarify`; immediate indexing; OCR; re-observation on demand; cases 1–5 end to end, twice (hand-verified vs automatic crops, L242); score with MEMORY's section-H sheet (five outcomes, conformal set size, clarify rate, empirical coverage).
- Week 4: Hand Sentinel decision from where the chain failed (L243; training data HoloAssist plus own footage, COMMERCIAL A4); correction capture (`correct()`); `stale` validated on case 2.
- Weeks 5–6: audited corrections, UX (photo + speech, image-alone test, L81), caregiver report path (`reports`, `reported`, attribution speech; MEMORY G) with its own consent, local-LLM residue if the clarify arm shows a need, the store trip, two deployment profiles documented with data-flow diagrams.
- Week 7+: as the spec (L246).

---

## 6. Peer answers to my questions, and what each changes

Seventeen questions were sent (5 PERCEPTION, 6 MEMORY, 6 COMMERCIAL; the sixth MEMORY question on `stale` was added in the round-1 final). Each row: resolved?; effect on blockers, gap map, risks.

### PERCEPTION

| # | Question | Answer (short) | Resolves? | Changes |
| --- | --- | --- | --- | --- |
| P1 | `carry_flow` spacing; burst or drop? | ~100 ms; keep with `carry_burst[]` (10 frames, 10 fps, carries ≥ 0.5 s; `none` above 150 ms) | Yes | BL-2 resolved; packet (2.1) and localizer (2.2) gain the burst and the spacing guard |
| P2 | Fallback proposer | RepViT-SAM, point/box-prompted on a 2.5× hand-box crop; a few hundred ms CPU; inside the tier-4 budget because it runs only on differencing failure; not EdgeSAM/FastSAM/YOLO-World/`ultralytics` | Yes | 2.2 names the proposer; COMMERCIAL adds SA-1B provenance note and SAM 2 preference; no blocker change |
| P3 | DINOv2 margins; is 0.15 sane? | Mean-patch foreground-masked over CLS; lookalikes unseparable at any margin (→ `group`); distinct items margins 0.05–0.25 [B]; 0.15 fail-safe but costs coverage; add an absolute top-1 floor; calibrate on CUTE | Yes, superseded by MEMORY's conformal set | Reliable-sighting definition (2.5) replaced; localizer must emit masks (2.2); R4 reframed as calibration with a named bar; CUTE in week 1 |
| P4 | Cheap "hand present"? Safari ms? | No cheaper model; palm detector is the heavier one and already runs alone on no-hand frames; gate must be non-neural; 60–150 ms planning number | Yes | BL-7 resolved; new BL-10; section 4.2 numbers; R1 reordered to the top |
| P5 | Landmark-only grasp P/R? | None published; keep as recall-tuned "hand busy"; contact = laptop pre/rest diff; image contact model only at tier 4 after week 4, trained on commercially clean data | Yes | BL-1 confirmed; 2.3 renames `grasp.js`; step 6 names the data |

### MEMORY

| # | Question | Answer (short) | Resolves? | Changes |
| --- | --- | --- | --- | --- |
| M1 | `group` shape or `hedged`? | Fourth shape `group`; Answer restructured as `members[]` + `clarify` | Yes | BL-5 resolved; 2.5 field list replaced; rubric counts groups |
| M2 | Re-observation matcher and resolution | Two-stage: 518 px arrival index, query scoring, ≤ 3 RepViT-SAM refinements, conformal singleton, 2 s timeout; idle frames at capture resolution | Yes | BL-9.4 resolved; L130/L347 wording; bytes/hour (4.6); R7 added |
| M3 | Case-1 query rule | Lexical/category/OCR → set; SigLIP only to narrow; one clarifying question at 2–3; no defensible top-1 for elderly phrasing | Yes | 2.4 index job gains zero-shot category and `is_container`; 2.5 query rule; R6 gains the one-question arm; phone page needs a second push-to-talk round |
| M4 | Event-sourced ledger; idempotency on reload | Yes; `episodes/episode_revisions`, append-only `hypotheses`, `item_current` via `recompute()`; deterministic `episode_id`; same id + different digest = revision, never an error | Yes | BL-9.5 resolved; 2.1 rule replaced (accepted, section 7 e); 2.7 schema replaced |
| M5 | Containment evidence; v1 scoring | Three required conditions; localizer gains `container_region`; v1 scores case 5 on hand labels; automatic path reported | Yes | BL-6 resolved; 2.2 output; step 5 scoring |
| M6 | `stale` rule | Four reasons; any → `hedged` | Yes | BL-8 resolved; 2.5 |

### COMMERCIAL

| # | Question | Answer (short) | Resolves? | Changes |
| --- | --- | --- | --- | --- |
| C1 | MediaPipe notice obligations | JS Apache-2.0 at primary; weights Apache-2.0 by secondary (model-card PDF unreachable); §4 obligations: licence text + "Copyright Google LLC" on a notices page, keep the header in the served bundle, NOTICE if any; read the MediaPipe privacy notice for telemetry | Yes (primary pending) | 2.3 adds the notices page and a build-step rule |
| C2 | DINOv2 / SigLIP 2 terms | Apache-2.0 confirmed at primary; pin `dinov2_vits14` by name and hash (noncommercial siblings in the same repo); no dataset terms flow | Yes | 2.4 pins by hash; my round-1 Reaction 3 does not trigger |
| C3 | Apple terms vs Vision framework | Research-only language is in the Apple ML Research Model License on released checkpoints; Vision is an OS API with no such restriction | Yes | 2.2 OCR line stands; `mobileclip2_b.ts` must leave the repo |
| C4 | Hand Sentinel training data | HoloAssist (CDLA-Permissive-2.0) yes; EPIC-KITCHENS only with the £7k licence; Ego4D hold until the PDF is read and the company signs; 100DOH ontology only; NC datasets not even for evaluation inside product development | Yes | Step 6 names the data; repo purge includes the EPIC fixture |
| C5 | Deepgram line; bystander audio | Flux is the wrong line; Nova-3 pre-recorded $0.0043/min; `audio/mp4` accepted; `mip_opt_out=true` every request; BAA before agency PHI; push-to-talk is lawful in all-party states with indicator and disclosure; "no ambient audio" invariant | Yes | 2.6 (whisper primary, opted-out fallback); page invariant (2.3); L197 note |
| C6 | "Pam" mark | Not clear (Insignia Health Reg. 3755291 in health-behavior software; pending Dream Lab AI AI-assistant application) | Yes | Build order: mark decision in week 1; product name from config in all user-facing strings |

---

## 7. Positions on the contested items

"Accept" = goes into the day-1 freeze as the peer wrote it; "condition" = accepted with the stated change; "reject" = not built as written.

a) **PERCEPTION: no palm-only cheap signal; tier-1 gate must be non-neural frame-difference energy.** Accept. The evidence is specific (palm detector runs alone on no-hand frames and is the heavier model; no palm score in the JS API). Conditions: the energy region (lower two-thirds) is initial and is checked against side entries on the wheelchair mount in week 1; the 1 Hz heartbeat is mandatory; the skip rate and the `numHands` switch cost are week-1 counters (4.8 items 9–10).

b) **PERCEPTION: Safari MediaPipe is likely 60–150 ms, not 20–40.** Accept as the planning number; it is the only sourced browser figure and the spec's number has no source. Consequence: BL-10 (two rates), L180 rewritten, R1 to the top. I do not accept lowering the capture rate: the ring buffer and the burst are fed at 10 fps regardless of the landmark rate, so the evidence the localizer needs is still captured even when landmarks lag.

c) **MEMORY: `group` answer shape.** Accept; the `members[]` restructure is better than my round-1 condition (multi-image `hedged`). Conditions: more than three members for voice becomes `clarify` or `abstain`; members ordered by recency; the shape, `clarify`, `reported` and `stale_reason` go into the day-1 freeze so the resolver and the page are built against one field list (MEMORY question to ARCH 3: yes).

d) **MEMORY: conformal prediction set instead of the 0.15 margin.** Accept with conditions. Reasons: the margin was a guess the spec itself calls initial; the conformal set uses the same cosine scores, gives a stated coverage, and its set size is exactly the signal `group` and `clarify` need; the α = 0.01 medication rule plus the OCR/naming requirement for `confident` is a mechanism for L219, not a hope. Conditions: (i) the guarantee is marginal, in-bank only, and over the calibration distribution; CUTE is not the rig's distribution, so the margin stays as the logged interim until the week-2 rig set, and every pilot answer records its `calibration_id`; (ii) empty sets on a tiny day-one bank will create duplicate items (the L120 fragmentation); report the empty-set rate on in-bank queries and make `merge` by correction cheap; (iii) the co-visibility check needs a homography at query time; budget it inside the 2 s; (iv) calibration per `embedding_model` and crop-quality bucket means `exemplars` stores crop size.

e) **MEMORY: event-sourced SQLite schema with an idempotency rule that departs from my 2.1.** Accept the departure. My "same id + different digest is an error" copied `ObjectStore.enqueue`'s semantics (L229–L234), which are right for an API client that can read an error and wrong for a lossy producer that replays from a mirror and cannot repair a conflict; record-and-flag is correct. Conditions: the superset/conflict classification is computed by the server from the stored bytes, never from a phone claim; the phone deletes the mirror only on ack and acks are idempotent; immutability triggers must coexist with retention (COMMERCIAL's condition), which I resolve with the `media_retention` side table rather than nullable media paths; WAL replaces `PERSIST` and the SQLite version is checked at startup; `/api/answer` reads `item_current` only (MEMORY question to ARCH 2: yes), and `rebuild_all()` is the `user_version` migration path.

f) **MEMORY: re-observation via a 518 px DINOv2 patch index with no proposer at arrival, RepViT-SAM on ≤ 3 frames at query.** Accept with conditions: the 2 s timeout and the 100–250 ms arrival cost are week-2 measurements on the laptop CPU; idle keyframes at capture resolution raise rig bytes/hour to ~6 MB/h, recorded as transport; storage ~150 MB + 77 MB per 24 h is fine on the laptop and is a phone-storage line on the native target; the ~1.2 m floor is a stated limit the pilot reports against.

g) **MEMORY: whisper offline as primary STT.** Accept. $0, offline, no third-party data terms, MIT at all primaries ([V-peer COMMERCIAL]), and `voice.py` already does it on a Mac. Conditions: latency on the Windows laptop CPU measured in week 2 (fall to `small.en` with the vocabulary prompt if a 5 s clip takes over 2 s); the Deepgram fallback only with `mip_opt_out=true` and only under the `family` profile unless a BAA exists.

h) **COMMERCIAL: `landmarks[]` for every hand is a BIPA surface; reduce after localization.** Accept as a retention and scope rule (BL-11), with one condition: the reduction applies to pilot households from the first recording, while weeks 1–4 on the team's own consented footage retain raw landmarks, because the controller equivalence tests, the escalation measurement and the week-4 decision replay them. The packet contract does not change. The wearer-only bank with a written release and "no template for anyone else" are accepted as written.

i) **COMMERCIAL: face routes in `app.py` must go.** Accept without condition; already in 2.6's delete list, now with the modules named.

j) **COMMERCIAL: purge AGPL `ultralytics`/YOLOE/`mobileclip` artifacts from repo history.** Accept, with the engineering condition that it is the first task of day 1, before the build branch exists; the EPIC fixture and `eval_epic.py` go with them (or the £7k licence is bought and filed); `CLAUDE.md`'s YOLOE measurements stay as text. Correction: the two AGPL lines are in `perception/requirements.txt` (L1, L7), not `server/requirements.txt`.

k) **COMMERCIAL: "PAM" is not a clear mark.** Accept. Architectural consequence only: no product name in code strings; the spoken name and page title come from config.

Smaller items I accept without discussion: PERCEPTION's analysis size chosen by R1 (256 vs 384), structure-map differencing, two rival regions, native-resolution identity crops, PaddleOCR; MEMORY's `location_status = reported`, caregiver report path (scheduled weeks 5–6, its consent in week 1), the section-H scoring sheet for step 5, the hypothesis layer starting in week 1; COMMERCIAL's `retention_until`/`consent_version`, `deployment_profile`, the notices page, pins by hash, the microphone invariant.

One item I defer rather than accept: MEMORY's local Qwen2.5-1.5B residue. Nothing in the six scripted cases needs it, the lexical + SigLIP + clarify path covers them, and it adds a model to the laptop; it is built only if the week-3 clarify arm shows a residue worth it.

---

## Exchanges

- Round 1: `ListAgents` listed only this process's own subagent id; `SendMessage` to `PERCEPTION` returned "No agent named 'PERCEPTION' is reachable". All questions went to `main` for relay. No peer message was received; no peer draft was present in `drafts/` at the time of the round-1 final (three checks).
- Round 2: the coordinator reported all three finals in `final/`; I read `PERCEPTION.md`, `MEMORY.md` and `COMMERCIAL.md` in full. Their "Answers to ARCH" sections are reconciled in section 6; MEMORY's four questions to ARCH are answered in "Reactions to peers" below; no direct peer message was exchanged.

## Reactions to peers

### Answers to MEMORY's questions to ARCH

1. Per-load `session_id` in `sessionStorage`: accepted. The clock anchor must change with the page anyway; `device_id` persists in `localStorage` so a reinstall does not collide [B on Safari persistence of `localStorage` for home-screen apps].
2. `/api/answer` reads `item_current` only; `rebuild_all()` is the migration path for `user_version` bumps: accepted. `get_object()`'s read-time derivation (L461–L480) is deleted.
3. Fold `members[]`, `shape = group`, `location_status = reported`, `clarify` and `stale_reason` into the day-1 freeze: yes (section 5, day 1–2).
4. `container_region`: in the week-1 packet/localizer freeze as optional-null (cheap now, expensive later); implementation deferred; case 5 scored on hand labels in v1.

### To PERCEPTION

1. Reactions 2 (move R2 up): done; R1 is now hand presence and landmark rate, with the Worker's delivered rate in the same table.
2. A1 burst: accepted with "only on carries ≥ 0.5 s" and the 150 ms guard; I add that the burst is cut from the ring buffer's bitmaps, so it costs ten small encodes and nothing in the analysis path.
3. C "run the burst at 320 px if the Worker budget allows": accepted as a week-1 measurement; the acceptance threshold of 400 px² (L175) is close to the object size at 256 px, as you note.
4. A "the energy test on the lower two-thirds": conditioned (section 7 a); hands on a wheelchair mount enter from the sides.
5. D "identity crops never upsampled from the analysis frame": accepted and written into 2.2; L118's rule extends to all crops.
6. Your "contact detection with numbers is image-based and every checkpoint is NC-trained": this is what keeps BL-1's hand-only phone correct and makes the week-4 decision a tier-4 question; agreed.

### To MEMORY

1. Idempotency: accepted over my 2.1 (section 7 e), with the conditions there.
2. Conformal set: accepted with conditions (section 7 d). One disagreement: the "two regions visible in one frame" refusal requires registering X's last rest frame to the query frame; on a wheelchair that homography will fail often (`CLAUDE.md` L185–L190), so the check must degrade to "no refusal" with a logged reason, not to "refuse on failure", or coverage collapses.
3. Re-observation: accepted with the measurement conditions (section 7 f).
4. Schema: accepted; the retention side table resolves COMMERCIAL's trigger condition without nullable paths on immutable rows.
5. Section G caregiver reports: good, scheduled weeks 5–6; the consent in week 1 (COMMERCIAL 4.5); the proactive push that sends a rest-frame photo to the caregiver is a disclosure that must be in both consents, as COMMERCIAL says.
6. Local-LLM residue: deferred, not rejected (section 7, last paragraph).
7. Reactions 4 ("schema before packets" softened): accepted; build order point 3 revised.

### To COMMERCIAL

1. BL-11 adopted as a spec rule; the development-phase exemption is my one condition (section 7 h).
2. Repo purge on day 1: accepted; `requirements.txt` attribution corrected (perception, not server).
3. `deployment_profile`: adopted in 2.7; the agency profile forbids all non-BAA egress, which with whisper offline and no write-path VLM leaves only the cloud tie-break to gate.
4. Your reading that `doses.py` must stay out of the memory layer and that any future adherence feature is user-entered, never camera-inferred: consistent with 2.6; recorded.
5. Your "evaluation inside product development is commercial use" changes one week-1 item: the identity calibration runs on CUTE (CC BY 4.0) and the rig set only; no EPIC footage in any experiment unless the licence is bought and filed.
6. Mark: accepted; config-driven product name.

### Disagreements that remain

- None that block the freeze. The three open spec-text items (BL-3 pre-roll, BL-4 coordinates, BL-9.1/9.2/9.6/9.8) had no peer objection and are mine to write into the day-1 page.
