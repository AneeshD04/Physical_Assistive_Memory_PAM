<!-- PAM MEMORY LAYER, v4 spec, revision 4 (after the fourth review). Exported 2026-10-05.
     Part 1 (the spec) is authoritative. Part 2 is the review log; where they differ, Part 1 wins.
     Frozen for build: section 10 steps 1 and 2 are cleared to start. -->

> **Scoped milestone overlay — 2026-10-07:** The v4 text below retains the broad
> principles and review history; it has not been rewritten as a full v5 spec.
> For the first functional software milestone, follow the latest user scope and
> [BUILD_CONTRACT.md](BUILD_CONTRACT.md), which governs conflicting interface and
> implementation proposals. The coordinator closed that **design** gate and started
> builders/testing; this is not completed implementation or model/device/pilot
> validation. See [CONTINUATION_HANDOFF.md](CONTINUATION_HANDOFF.md) for work state.

# pam Memory Layer: Response to Review and v4 Direction

Oct 3, 2026 · @aneesh

## Bottom line

We accept the review's direction: the evidence ledger becomes the center of the system, three design rules in the September brief flip, and "seven proven components" becomes "a modular pipeline with explicit, testable uncertainty." The core bet survives intact: capture on hand interaction rather than on sight, write memory without language, keep instance identity separate from detector classes, and keep the paid cloud off the write path.

The review's single most important finding is one it under-sold. Wearer-only admission would make pam fail on the scenario we prioritize above all others: a caregiver moves the medication. That is not an edge case to handle later; observed non-wearer moves of tracked items are the product.

The second most important finding is ours, not the review's: actual v1 end-to-end performance is unknown, and 70% success is the initial experimental target (corrected in Round 2: the earlier framing of this as evidence-backed was wrong). The product has to be designed for that number, which means a photo-first answer and a first-class "I'm not sure" response, not a confident sentence that sends someone with memory impairment to the wrong room.

Everything below describes two systems and keeps them apart: the native wearable target, where the whole pipeline runs on-device, and the browser rig (iOS Safari streaming to a laptop) that we test on now. Section 7 says which stage runs where in each, and which rig results carry over. No performance, privacy or cost claim crosses between the two without saying so. Specific pushbacks on the review are in section 4; they are small and do not change the verdict.

## Assumptions for this revision

Two systems, kept apart. The research rig uses iOS Safari for capture and an authenticated laptop service for inference and storage, except for the stages explicitly assigned to the browser: the gate, hand landmarks, grasp, the episode state machine and the ring buffer. It validates episode detection, object localization, identity, retrieval, the data contracts and the UX. It does not establish native-phone inference latency, NPU use, offline operation or production battery life; those need separate on-device validation. The native target is a phone or wearable running the whole pipeline on its own silicon, with the same stage boundaries and the same episode packet, so the contract the rig validates is the one the wearable keeps internally.

The September brief's budget was "5 fps on a CPU laptop with a 45 ms hand detector." That target is retired. Native-target stages are sized for a mid-range phone, with the NPU where the platform exposes one. On the rig, phone-side stages are measured as they run in JavaScript (a measurement of the rig implementation, not a bound on the target) and server-side stages as the work a wearable would inherit; neither is a native number and neither is presented as one.

The form-factor question (pendant vs. glasses vs. phone-tethered) is parked by decision, not forgotten. The review's point that it must be answered before a production build stands; it does not block the next eight weeks. Updated October 4: the test rig is an iOS browser web app streaming to the laptop server; the Round 2 tab, under Platform decision, records what runs where and which efficiency numbers carry over to the wearable.

## What we accept from the review

Twelve of the review's findings change the design. Ranked by how much each one changes what pam does for a user.

| # | Finding (review §) | What changes | Why it ranks here |
| --- | --- | --- | --- |
| 1 | Relevance-based admission; actor-independent updates (§2A) | Relevance, actor and location become three independent fields. Creating a durable item needs a relevance signal; updating one accepts any actor. | A caregiver moving the medication is the scenario we prioritize. The brief's rule fails it by design. |
| 2 | Episodes must be object-centric (§2D) | Episode outcomes become picked\_up / placed\_on\_surface / placed\_in\_container / handed\_to\_someone / returned\_to\_origin / lost\_from\_view / uncertain. A location can be another object. | Purse, pocket, drawer and bag are where things actually go. "Hearing aids in the purse" is a verbatim MemPal interview quote. |
| 3 | Appearance banks drift (§2E, §8) | Observations are immutable; identity assignments are versioned; banks have trusted and provisional tiers; no update from an ambiguous match. | One wrong match poisons every later answer about that item. Event-sourcing the ledger also makes user corrections cheap. |
| 4 | MemPal's 97% is a filtered number (§1) | The comparison table is rewritten: 72% correct descriptions is their system accuracy; occlusion-at-carry is our hypothesis, tested by ablation. | We checked the paper: it sends 3x3 tiled batches of nine frames to GPT-4V, not one still. The brief's causal story was wrong. |
| 5 | The 45 ms detector is not the compute budget (§4) | Every stage is benchmarked where it runs: rig stages on the iPhone in JavaScript and on the laptop now, native stages on-device later, each with p50/p95, bursts, thermal and power. See section 7. | The event path (DINOv2, SigLIP 2, place, open-vocab) was never measured as a whole. |
| 6 | Voice cost was wrong (§6) | Deepgram Voice Agent at $0.075 per connected minute is $67.50 per user per month at 30 min/day. Replaced with push-to-talk STT and platform TTS. See section 8. | The brief's $6 assumed an implementation it did not name. |
| 7 | Self-taught hand bank is circular (§2C) | Geometry and temporal continuity first; appearance bank as supporting evidence only; optional 10-second wearer calibration; unknown\_actor is a valid output. | A false positive trains the next false positive. "No item enrollment" never meant "no wearer calibration." |
| 8 | Home/store policy contradicts the product (§3) | Encounter evidence, candidate items and durable items become three retention tiers. Geofence sets retention and processing policy, never ownership. | A phone left at checkout and a prescription first seen at the pharmacy are both things pam must remember. |
| 9 | Pilot criteria measure components, not reliability (§7) | End-to-end success across all asked questions; abstention scored separately from accuracy; confident-wrong on medication reported on its own. See section 9. | 0.80 x 0.95 x 0.95 x 0.95 is 69%. Component targets cannot substitute for the chain. |
| 10 | Labeling is under-specified (§4) | Annotation ontology written and a one-hour teacher batch audited before any labeling is bought. | "50 to 100 hours of footage" is 180k to 1.8M frames depending on rate; the budget has to say which. |
| 11 | Timers need a maximum gap (§2G) | Wall-clock and observed-evidence durations both kept; past the max unobserved gap the episode becomes uncertain. | A paused timer cannot establish that the bottle that reappears is the bottle that disappeared. |
| 12 | VPR is not a surface atlas (§2F) | EigenPlaces-on-DINOv2 was a spec error (its checkpoints are ResNet/VGG). The atlas moves to v2; v1 answers with a photo. | Different counters look alike; the same counter looks different with the kettle moved. |

The IRB point (§7) is accepted without a row: the determination happens before recruitment, not after the pilot.

## Where the review overreaches

Four points are correct in the letter and do not change the conclusion. They are listed so nobody re-litigates them.

- **Licensing wording (§5).** BSD-3-Clause is as permissive as Apache for our purposes, so "everything is Apache/MIT/CC BY" is wrong by one word. Fix the sentence to "all permissive, pinned by checkpoint." The Places365 split (CC BY model, non-commercial images) is a real catch and stays. Whether AGPL "inherits" into trained weights is legally contested; the business decision to avoid Ultralytics is unchanged either way, so we will not seek a quote.
- **Aria Gen 2 wearer-hand tracking (§2C).** True, and not something we can ship. The brief's practical claim stands for any camera we can actually buy.
- **The examine test (§2B).** Correct, and small. A returned\_to\_origin event is a timestamp refresh, which is itself useful ("you last touched your keys at 3 pm, on the counter"). It becomes a state update that suppresses a notification, not a discard.
- **"Choose hardware now" (§4).** Parked by decision. The browser rig on an iPhone is the research platform and the native target stays unchosen; the pipeline accepts a glasses stream later, and nothing in the next eight weeks depends on the answer.

One thing the review under-sells: it treats the caregiver-moves-the-medication case as an architectural weakness. It is the product. We expect Pam's value to be highest when someone other than the wearer moved the thing and the camera saw it, because that is when the wearer's own memory has nothing to offer; the pilot measures whether that holds.

## Revised design rules

These replace the corresponding rules in the September brief and in MEMORY\_SYSTEM\_V3.md. Each is written so it can be checked against the schema and the tests.

1. **Three fields, independent.** Every observation carries `relevance` (encounter / candidate / durable), `actor` (wearer / other\_person / unknown) and `location` (a hypothesis with confidence and a reference frame). None implies another automatically; their evidence may still inform each other.
2. **Admission is strict; update is open; retrieval is neither.** A durable item is created only on a relevance signal: handled by the wearer on two or more days, a printed label matched, or the user named it. A durable item's location is updated on any observed actor's handling. Durability governs retention and trust, not searchability: a candidate handled once today is answerable today, with the answer qualified ("something I saw once, this afternoon"). This includes items only ever handled by a caregiver.
3. **Uncertain invalidates, never invents.** When identity or destination is uncertain after a move, the prior location's confidence drops and the state becomes `uncertain` with the last reference frame. No new location is asserted.
4. **Episodes are object-centric.** An episode is a set of relationships among hands, objects, supports and containers. Outcomes: picked\_up, placed\_on\_surface, placed\_in\_container, handed\_to\_someone, returned\_to\_origin, lost\_from\_view, uncertain. An object vanishing behind a hand or into a pocket is lost\_from\_view, not placed. The object region comes from an explicit localization component (section 7); an episode with no localized object is kept as context-only and is given no identity.
5. **Containment is an inferred location.** "Keys in purse, purse on chair" resolves to the chair as an inference, not an observation. Moving the purse does not re-observe the keys; both facts keep their own timestamps ("I saw the keys go into the purse at 2 pm; I saw the purse on the chair at 3 pm"). Containment links carry a timestamp, a confidence, explicit removal and uncertainty handling, and cycle prevention.
6. **Returned-to-origin refreshes.** It restores the resting-state claim with a new timestamp and suppresses the notification. It is never discarded.
7. **Observations are immutable; every hypothesis is versioned.** Frames, capture times and sensor readings never change. Identity, actor, relevance and location interpretations are all hypotheses and all versioned. Exemplar banks have trusted and provisional tiers; an ambiguous match never writes to the bank; two objects visible in one frame are never one instance; merge, split and correct are explicit operations, and a user correction is a version bump.
8. **Wearer attribution is geometry first.** Hand size, entry from the bottom edge and temporal continuity decide; the appearance bank is supporting evidence; an optional 10-second wearer calibration seeds it; `unknown` is a valid output and is reported as such. Missing IMU data means unknown, never still.
9. **Timers pause, then expire.** Blur and head turns pause the episode clock. Past the maximum unobserved gap (to be measured; start at 3 s at full rate) the episode is closed as uncertain. Wall-clock and observed-evidence durations are both stored.
10. **Place is a prior, not a gate.** Geofence, scene class and time of day set how long encounter evidence is retained and how much processing it gets. They never decide ownership and never block creating a durable item.
11. **Lookalikes stay distinct when continuity says so.** A group of visually identical instances is one answer surface, not one database row. Two identical bottles tracked separately remain two rows.
12. **The answer contract.** Every answer carries: a reference image only when a reliable sighting exists; a target indication in the image only when supported; capture time; identity status; location-evidence status (observed placement, sighting, or inference); and room, or "room unknown" until room identification has a source. Three shapes: confident, hedged, abstain. An abstention does not say "the last time I saw it," because that asserts an identity match, and the nearest candidate is never shown as if it were a match. `unknown` is a valid answer even when the nearest embedding has a large margin.
13. **Tracked items can be re-observed.** A durable item sighted at rest with no hand present updates `last_observed` with status "sighted," never "placed." Re-observation runs bounded and on demand (when asked about item X, match X's trusted exemplars against recent idle keyframes, most recent first), not as a shelf catalog.

## Changes beyond the review

Six changes the review did not ask for. Three of them also cut compute.

**The photo is the answer.** v1 answers "where are my glasses" with the last rest-frame photo, the capture time and, when a source for it exists, the room. The text description ("counter, left of the sink, next to the kettle") becomes a derived annotation added later, not the primary output. A real photo avoids generated-layout errors, but it can still be the wrong bottle, the wrong episode, a pre-placement frame or stale, so it is shown only under the answer contract in rule 12 and never when no reliable sighting exists. Answers are image plus simple speech; image alone is tested against that, because a mounted phone or low vision can make the image inaccessible. This removes the open-vocabulary landmark pass and the surface atlas from the v1 write path. It does not remove the need to localize the right object.

**Printed labels are evidence, not identity.** Zero enrollment stays the default, and the system may still read text on its own. At first sighting of an object with text (pharmacy label, box, bottle), run OCR on a capture-resolution source crop kept separately from the 224 px embedding crop (ML Kit wants about 16 px per character). On the native target this is the platform OCR; on the rig it is Tesseract or the Vision framework on the server. The result is stored as recognized text, the source image and an uncertainty. It contributes candidate identifiers: drug name as category, patient name as relevance, Rx number and fill date as the strongest discriminator between refills. Two refills can share patient, drug and dose, so text alone never establishes physical-instance identity or ownership; continuous visual tracking is what establishes continuity. Extracted dose text is never an input to any medication-taking or dosing feature.

**Abstention is a first-class answer.** Three response shapes, chosen by the resolver under rule 12 and the answer contract in section 7: confident (a reliable sighting and no later uncertain event: photo, time, room when known); hedged (a reliable sighting followed by an unobserved gap or an unknown actor: "I saw it here at 3 pm, but someone may have moved it since," with the photo); abstain (no reliable sighting: "I'm not sure where it is," with no photo and no claimed sighting, and the offer to say when it is next seen). For a person with memory impairment, a confident wrong answer is worse than no answer: it sends them searching the wrong room and erodes trust in every later answer. The pilot scores confident-wrong as a worse outcome than abstain.

**Corrections are evidence first, labels second.** "No, the silver one." "It was in the drawer." Each is a correction on our own hardware in a real home. The voice loop is built to capture them: when two hypotheses are close, ask one clarifying question; log every correction with its source, meaning, timestamp and the hypothesis it links to. A correction may be an identity constraint, a current location, a past location, the item's usual home, or a mistaken recollection; the resolver asks which when it matters. A sample is human-audited before any export as training labels, and personalization of this user's ledger is kept separate from consent to global model training. The loop is expected to reduce labeling cost; by how much is measured, not assumed.

**Validate with existing checkpoints now.** We validate with existing checkpoints whose terms permit our intended experiments, obtaining permission where needed; some model terms restrict product-development research itself, so each checkpoint's weight, code and dataset terms are checked separately (corrected in Round 2). DINOv2, SigLIP 2, MediaPipe and the platform OCR are permitted; the hand-contact checkpoints are checked one by one before use. The decision to train the Hand Sentinel, and on what ontology, comes after that measurement, not before. This is a large schedule and cash saving.

**Bystander recording is a product requirement.** Aides, visitors and family get recorded. Audio consent law varies by state. Before any household pilot: a visible recording indicator, a one-touch pause, a disclosure for people in the home, and a retention policy for frames that include other people's faces. The review puts this under IRB; it also belongs in the product spec, because it applies after the pilot too.

## Compute efficiency: native target and browser rig

Two systems share one set of stage boundaries. The native target runs everything on the wearable's own silicon. The browser rig runs the cheap stages in iOS Safari and streams one small packet per episode to a laptop that runs the rest. The table says which is which; nothing below carries a performance, privacy or cost claim across the two without saying so.

| Concern | Browser/laptop rig (now) | Native target (later) |
| --- | --- | --- |
| Capture | iOS Safari, `getUserMedia`, 720p, standalone home-screen mode | Native camera API or glasses stream |
| Gate, hand landmarks, grasp, episode machine, ring buffer | Browser JavaScript; MediaPipe Tasks Vision JS in a Web Worker | On-device, NPU where exposed |
| Localization, DINOv2, SigLIP 2, OCR, ledger, resolver | Laptop, Python; OCR via Tesseract or the Vision framework on a Mac | On-device; platform OCR |
| Persistent store | Laptop SQLite | Phone-local store |
| Data leaving the phone | Episode keyframes and idle keyframes go to the laptop; the disclosure says so | A few tie-break crops and a nightly digest |
| Voice | Push-to-talk `MediaRecorder` to server STT; `speechSynthesis` on the phone | On-device recognizer only if it demonstrates offline operation; platform TTS |
| What it validates | Episode detection, localization, identity, retrieval, data contracts, UX, and the proxy numbers below | Latency, NPU use, offline operation, battery, background capture |

The design principle for both: the camera is believed to be the dominant power draw (a hypothesis, measured alongside screen, compute, location and radio), so the pipeline spends the day in a mode costing a few milliseconds per frame and escalates on evidence of a hand. Six tiers; each runs only when the one above it says so. Timings are targets to measure, not claims.

| Tier | Mode | Rate and resolution | What runs | Cost per frame (target) |
| --- | --- | --- | --- | --- |
| 0 Sensors | Always | Continuous | IMU motion state when permitted (missing means unknown, never still); coarse geofence; time of day | Near zero |
| 1 Idle | No hand in view | 2 to 5 fps analysis on a 256 px downscale of the stream; a bounded pre-roll of the last 2 s kept at capture resolution | Sharpness; near-duplicate drop, for storage and idle compute only; cheap hand check | Under 5 ms plus the hand check |
| 2 Escalating | The moment a hand appears or relevant motion starts, not after a confirmed grasp | 10 fps at 256 px for landmarks; the pre-roll is promoted into the episode | Hand landmarks (MediaPipe; about 17 ms CPU and 12 ms GPU on a Pixel 6 per Google's benchmark; JS numbers measured on the rig); hand size and entry edge | 10 to 40 ms |
| 3 Active episode | Grasp evidence accumulates | 10 fps evidence acquisition; duplicate suppression off, because near-duplicate rest frames are the evidence | On the phone: grasp classifier on landmarks; episode state machine; keyframe selection for the packet; quality gaps recorded explicitly. Localization does not run here; it consumes the packet in tier 4 | Under 30 ms on the phone |
| 4 Event write | Episode close; on the rig this is the laptop receiving the packet, on the target it is on-device | 2 to 4 crops at 224 px plus one capture-resolution OCR crop | Object-region localization on the packet (frame differencing pre-contact against rest; co-motion minus the hand hull during the carry; a tiny class-agnostic proposer as fallback), then DINOv2 ViT-S/14 on the pre-contact and rest crops; one global embedding of the rest frame; OCR if text is present; 6 to 8 keyframes stored; one SigLIP 2 embedding per genuinely new candidate scheduled at once | 0.3 to 1 s per event, localization included; per episode, never per frame |
| 5 Charger | Nightly or on the charger; not guaranteed to run | Batch | Additional-view embeddings, bank maintenance, cloud VLM for the day's unresolved ties | Off the critical path |

Tier 1 is a mode controller, not a filter: it decides which mode the camera and the analysis are in; it does not pass individual frames to tier 2. The pre-roll exists at whatever resolution idle capture runs at. On the rig that is 720p, because the stream is captured once and downscaled, so pre-contact crops are full resolution there. A native build that runs idle capture lower tells identity and OCR the pre-contact crop's resolution and does not upsample it.

**Indexing is immediate to schedule and asynchronous to complete.** Text-space (SigLIP 2) embeddings are only used at query time, but a text query cannot find an unindexed new item, because DINOv2 and SigLIP 2 are different spaces. So one SigLIP 2 embedding per genuinely new candidate is scheduled the moment the candidate is created and runs in the background; the contract in "Stage contracts" below gives the queue order, the readiness deadline and the query rule. Additional views, bank cleanup and maintenance wait for the charger. The new-candidate rate is expected to be low after the first days and high on day one; it is measured, not assumed, including the identity fragmentation that inflates it. Background jobs are not guaranteed to run every night on a phone; the nightly batch is a convenience, not a dependency.

**What v1 does not run on the phone.**

- OWLv2 or Grounding DINO per event. ViT-B at 960 px is seconds on a phone CPU. The photo-first answer removes the need; landmark phrases return in v2, at most once per new surface.
- AnyLoc. DINOv2 ViT-G plus VLAD is far beyond a phone budget. The DINOv2-S global embedding of the rest frame, plus geofence and time, is the v1 place descriptor; it does not name rooms, so room stays optional until something does.
- A scene classifier per frame. Geofence, IMU and time of day do the gate's job. Places365 at most once per minute, and only if a measured need appears.
- SAM 2, metric SLAM, any segmentation. Teacher-side, offline, on a rented GPU.
- Resolution switching on the hot path. Capture once at the mode the device actually delivers (recorded from `getSettings()`) and downscale for the cheap stages. This is a frozen policy choice, not a platform fact: `applyConstraints` behavior mid-stream has varied across Safari versions in our experience, and native format changes carry their own cost; neither is claimed to be universal.

**Storage and radio.** Two stores with different retention. Event keyframes (6 to 8 per episode plus crops) are durable; video is never kept. Idle keyframes (one every 30 s) are a rolling cache for re-observation under rule 13, retained for 24 hours and then dropped unless a re-observation match promoted one into an item's evidence. At roughly 50 handlings per day, durable storage is on the order of 20 MB per day (estimate; measure), against the 5.8 GB per day the review computed for streaming at 5 fps. On the native target nothing leaves the phone except tie-break crops and the nightly digest. On the rig, every episode packet and the idle keyframes go to the laptop; bytes per hour is recorded.

**Thermal and power.** The native bar is a full waking day on one charge with the pipeline on; a battery pack on the mount is acceptable for a pilot if the number is reported. The rig cannot measure this: a lit screen, video encoding and streaming dominate its battery and say nothing about local inference. What the rig measures instead: per-stage milliseconds in JavaScript on the iPhone (a measurement of the rig implementation, not a bound on the target); per-event milliseconds on the laptop (the work a wearable would inherit); escalation rate (the share of frames that reach the hand stage, and the share that open an episode); bytes per hour (rig transport, which the target keeps internal, so it measures work moved, not native radio use); and a burst of 10 handlings in 2 minutes to see whether the queue drains. These five replace the brief's single "45 ms" number. They are proxies that inform the design; native feasibility is established only by the native build.

**Frame accounting.** Requested frame rate is not delivered frame rate, and a JavaScript timer firing five times a second does not prove five fresh camera frames were processed. Record the negotiated stream settings from `getSettings()`; use `requestVideoFrameCallback` metadata to detect missed frames; and count separately: source frames, frames selected, frames transmitted, frames received, frames processed, capture-to-processing age, and dropped frames and observation gaps. Missed-transition rate at each active-tier rate is a week-2 measurement. A lower idle rate rests on the assumption that nothing happens between samples; the missed-transition test evaluates that assumption rather than granting it. A lower active rate is not acceptable.

## The browser rig

The rig is the current code's shape: Safari captures, the laptop infers, HTTPS between them, which is why `serve.py` carries a certificate and why the key route is closed first. What the browser imposes, and the answer to each:

- The camera stops on screen lock or backgrounding. Screen Wake Lock API, auto-lock off, brightness at minimum, standalone home-screen mode; every stop logged as coverage loss. Verify `getUserMedia`, the wake lock and `DeviceMotion` in standalone on the test iOS version before mounting anything.
- MediaPipe's JS detection blocks the calling thread. Inference runs in a Web Worker so that synchronous call does not block capture or the UI; shared compute, memory and transfer contention can still stall them, and the frame counters are what will show it.
- `DeviceMotion` needs HTTPS and a tap-initiated permission. Denied, unavailable and interrupted are handled explicitly; camera without motion is a valid state; missing IMU means unknown.
- Speech is not offline in Safari. Push-to-talk to server STT, `speechSynthesis` for replies; the "$0 platform recognizer" line in section 8 is native-target only.
- Native OCR and the NPU are not reachable from a page. OCR runs on the server. WebGPU (shipped by default in Safari 26) is GPU compute and an optional later experiment, not evidence for native NPU timings.

**Connectivity, decided before the store trip.** The laptop lives on a home LAN that the phone leaves at the front door. One of three is chosen and recorded before the scripted store trip: carry the laptop on a phone hotspot; an authenticated tunnel to the laptop, with bandwidth, exposure and availability accounted for; or record on the phone and replay later, acknowledging that this does not test live assistance. Without the choice, the store trip measures a disconnected camera, not the relevance gate.

**Failure modes with defined behavior.** Wi-Fi loss, laptop sleep, browser backgrounding or screen lock, server restart, delayed upload. This is a requirement on the rig, not a guarantee the browser gives: the phone holds its episode queue in memory for the page's lifetime and mirrors unsent packets to IndexedDB as a best-effort cache, uploading when the link returns; a page reload or storage eviction can still lose them, and every such loss is recorded as coverage loss. The server processes on observation time, never arrival time; a network stall is not an object coming to rest.

**Disclosure matches the rig.** Camera keyframes leave the phone for the laptop. "Only a few tie-break crops leave the phone" describes the native target and is not used in the rig's consent language.

**What carries over to the wearable.**

| Rig result | Transfers? |
| --- | --- |
| Ledger ordering, idempotency, corrections, containment logic | Yes: software behavior |
| API token cost for identical requests | Yes, at the same rates and payloads |
| Escalation rate and bytes per hour | Yes, as design proxies |
| Phone-side JS milliseconds per stage | As a rig measurement; not a bound on the target |
| Event frequency and storage per day | As workload-dependent estimates |
| Accuracy on the rig's recorded footage | For that camera, mount and input distribution only |
| Hand visibility, blur, exposure, viewpoint robustness | Revalidated on the new camera and mount |
| Laptop inference latency | No |
| Browser streaming battery consumption | No |
| Background operation and recovery | No: platform-specific |

Rig cost (laptop time, a hotspot plan, the phone) is kept separate from the subscription economics in section 8; laptop vision processing is not free because it makes no paid VLM calls.

## Stage contracts

Five interfaces a coding agent builds from without guessing: the packet, the localizer, the capture controller, indexing, and the answer. Every number marked *initial* is a starting value for the week-1 and week-2 measurements, not a tuned result; it is in the spec so that two implementers start from the same place.

**Episode packet (phone to server; on the target, phone to its own tier 4). One per episode.** `episode_id`; `device_id`; `t_start` and `t_end` on the observation clock (monotonic) with a wall-clock anchor; `keyframes[]`, 6 to 8 entries of `{frame_id, t, role, width, height, jpeg}` at capture resolution with `role` in `pre_contact | grasp | carry | release | rest | idle`; `landmarks[]`, one entry per analysed frame, `{t, frame_id, hands[]}` where each hand is 21 points in the pixel coordinates of that frame plus `handedness` and `hand_bbox`; `imu[]` as `{t, state}` with `state` in `still | walking | head_turn | unknown`; `location` as `{lat, lon, accuracy_m, t}` or null; `gaps[]` as `{t_from, t_to, reason}`; `quality` as sharpness per keyframe; `outcome_hint` from the phone's state machine. The server never needs a frame that is not in the packet.

**Object-region localizer. Runs on the laptop on the rig, on-device on the target; input is the packet.** Output per episode: `target_region` as `{frame_id, x, y, w, h}` in the pixel coordinates of that frame; `region_source` in `pre_rest_diff | carry_flow | proposer | none`; `region_confidence` in \[0, 1\]; `association_to_hand` as `{frame_id, hand_index, overlap}` or null; `association_to_pre_contact_object` as `{frame_id, bbox, confidence}` or null; `association_to_resting_object` as `{frame_id, bbox, confidence}` or null; `crops[]`, each `{frame_id, bbox, purpose}` with `purpose` in `identity_224 | ocr_full`. `region_source = none` with `region_confidence = 0` is a valid output: the episode is stored context-only and no identity is created (rule 4). Initial acceptance: a difference region is accepted when it covers between 0.5% and 30% of the frame and overlaps the last hand bbox; a carry region is accepted when the co-moving area minus the hand hull is at least 400 px² at analysis resolution; the proposer runs only when both fail.

**Capture-mode controller (phone). States: Idle, Escalating, Active, Settled. Transitions, initial values:**

- Idle to Escalating: a hand present in 2 consecutive analysis frames, or IMU or flow motion above the still threshold within 1 s of a hand being seen.
- Escalating to Active: the grasp classifier positive in 3 consecutive 10 fps frames. Capture is already at full rate, so the 300 ms of evidence costs nothing; it is a decision threshold, not a capture trigger.
- Escalating to Idle: no hand for 1.5 s.
- Active to Settled: the tracked object region stationary (centroid moving under 2% of frame width) for 1.0 s with no hand within 1.5 hand-widths of it, outcome `placed`; or the hand leaves the frame with no object region tracked, outcome `lost_from_view`; or the maximum unobserved gap of 3 s is exceeded, outcome `uncertain`.
- Settled to Idle: once the packet is enqueued, after a 0.5 s refractory period.

Every transition is logged with its cause and timestamp; the log is part of frame accounting.

**Immediate indexing (server on the rig).** Trigger: candidate creation. Queue order: most recent episode first. Readiness: target 5 minutes, maximum 15; past 15 minutes the next query embeds that candidate synchronously before answering. Query rule: answer from indexed items; if any candidate created in the last 24 hours is unindexed, attach `index_pending` and re-run the resolver when indexing completes; never answer "I haven't seen it" while a candidate is pending.

**Answer (resolver).** Fields: `reference_image` as `{frame_id, bbox}` or null; `target_indicated` (bool, false when `reference_image` is null); `capture_time` (null when `reference_image` is null); `identity_status` in `matched_trusted | matched_provisional | group | unknown`; `location_status` in `placed | sighted | inferred | stale | unknown`; `room` (string, or "room unknown"); `shape` in `confident | hedged | abstain`; `index_pending` (bool). A *reliable sighting* is an observation where `identity_status` is `matched_trusted` or `matched_provisional` with a margin over the runner-up at or above the trusted threshold (initial 0.15 cosine), `location_status` is `placed` or `sighted`, and it is the item's most recent observation. Shape: `confident` when there is a reliable sighting and no later `uncertain` episode or unknown-actor event on the item; `hedged` when there is a reliable sighting and a later gap, an unknown actor, or an `inferred` location; `abstain` otherwise, with `reference_image` null and no sighting claimed. `index_pending` may accompany any shape.

## Corrected cost model

Cloud cost per user per month is about $6 to $8 with cloud speech-to-text, and about $1 to $2 if speech-to-text runs on the phone. Each number below names the implementation it assumes, which the brief's did not. Rates are the ones the review cited; measure actual token counts before quoting a margin.

| Component | Implementation assumed | Per user per month |
| --- | --- | --- |
| Speech-to-text | Push-to-talk, Deepgram Flux, 30 min/day at $0.0065/min | $5.85 |
| Speech-to-text, alternative | Platform on-device recognizer, native target only (not reachable from the browser rig); offline behavior demonstrated, not assumed | $0, accuracy on older voices to be tested |
| Text-to-speech | Platform voice on the phone | $0 |
| Text-to-speech, alternative | Cloud voice (Aura-2 class), 30 replies/day | about $5 |
| Query reasoning | Local: embedding compare and templated sentence. Cloud LLM only for descriptive queries and ties, budget 5 calls/day at about 1.5k input and 150 output tokens at the review's $2/$10 per million | under $1 |
| Write-path VLM | None in v1 | $0 |
| Write-path VLM, September brief (not in v1) | Excluded from v1; shown only to compare with the brief's 10 calls/day | $1.80 to $5.10 depending on crop and context size |
| Deepgram Voice Agent | Not used: $0.075 per connected minute is $67.50 at 30 min/day, and push-to-talk does not change the rate | removed |

The pilot cash figures in the brief ($9 to 18k founders-only; $34 to 78k with a contract engineer) stay as hypotheses with two changes: add a 25% contingency line for hardware access, failed experiments, data handling, participant support and labeling QA, and move the IRB or institutional determination from "after the pilot" to before recruitment. The labeling line ($8 to 15k) is now conditional on the week-4 decision in section 10, and the correction loop in section 6 may reduce it by an amount that is measured, not assumed. Research-rig costs (laptop time, a hotspot plan, the phone) are tracked separately from the subscription estimate.

## Pilot criteria

The brief's weekly numbers (placed precision 0.95, recall 0.80, query correctness 0.85) stay as engineering milestones. They are no longer the pilot's pass criteria. The pilot passes or fails on the end-to-end chain, scored on every question asked.

Every answer is scored into one of five outcomes: correct, hedged-correct, hedged-wrong, confident-wrong, abstain. Accuracy is reported among answered queries and coverage separately, so a system cannot look good by abstaining. Two axes are kept apart: historical fidelity (was this truly the item at that time) and current usefulness (does the answer help find it now); a truthful old photo of the counter is not a successful answer if the item is now in the drawer. Corrections are scored chronologically and never improve a scored past answer.

| Measure | v1 target | Note |
| --- | --- | --- |
| End-to-end query success, all questions | 0.70 | Initial experimental target, not a forecast; actual performance is measured |
| Confident-wrong, all items | 0.05 or lower | Scored worse than abstain |
| Hedged-wrong, all items | Reported | A hedge that shows the wrong place is still a wrong answer |
| Confident-wrong, medication | Zero in the pilot | Bound computed on medication queries only; any occurrence is stop-and-fix |
| Relevant moves visible to the camera | Reported | Separates capture coverage from model failure |
| Success on visible caregiver relocations | 0.70 or better; its own pass criterion | The product's central case; it cannot pass on easy wearer placements alone |
| Behavior after an unobserved move | Reported | Prior location marked stale; never a confident stale answer |
| Wearer placements recalled away from home | Reported | Replaces "zero store writes" |
| Irrelevant durable items created | Zero | The retention tiers exist for this |
| Pockets, bags, drawers, two-handed transfers, two items at once | Reported per case | The object-centric episode exists for this |
| False instance merges and recovery after a correction | Reported | The versioned ledger exists for this |
| Capture downtime and out-of-view events | Reported as coverage loss | Includes budget\_wait and backpressure in the current code |
| Cost and power over complete sessions | Reported | Native only; the rig reports the section 7 proxies |

Test design: held-out homes, people, physical objects and recording days; a store trip, a bystander, an identical pair and a caregiver relocation scripted into every household. Zero failures in 150 trials still leaves a one-sided 95% upper bound near 2%, and trials in one home are correlated, so the report states the bound, not just the count.

The IRB or institutional determination, consent, bystander privacy, retention and non-reliance safeguards are settled before recruitment. The pilot can produce the MemPal-style paper the brief described, with their outcomes (retrieval success, path length) plus ours (confident-wrong rate, cost per day, abstention rate, placements away from home).

## Order of operations

The sequence is chosen so that nothing expensive is built before the thing it depends on is measured. Items 1 and 2 are independent of everything else and happen first.

1. **Today: close the key.pem route.** `phone/serve.py` lines 94 to 100 serve the private key through unrestricted static serving. Close the route, rotate the key and certificate if the server has run on a shared network, commit. The certificate is public; the private key is the sensitive material.
2. **Rerun the suite.** Rerun the integration tests after the SQLite cleanup patch (7 methods were failing; the fix was not rerun). Finish repeated-frame validation and the five PublicFiles tests. Commit the uncommitted changes.
3. **Rewrite the data model.** Three independent fields; object-centric episode outcomes; immutable observations with every hypothesis versioned; the three retention tiers; the re-observation path. This is a SQLite schema change and the `object_memory.py` state guard widened to the new outcomes. Keep the budget\_wait and lease-recovery paths; add coverage-loss reporting to the backpressure drop.
4. **Week 1: rig benchmark and frame accounting.** Phone-side stages in JavaScript on the iPhone, in a Web Worker; server stages on the laptop; `getSettings()` and the seven frame counters from section 7; escalation rate and bytes per hour over a normal afternoon. Decide the store-trip connectivity option. Nothing is trained yet.
5. **Weeks 2 to 3: run the whole chain on our own footage with checkpoints whose terms permit it.** Run the ledger and resolver twice, once on hand-verified crops and once on automatic crops, to separate memory logic from perception. Score every answer with the section 9 rubric. Scripted cases: a new unlabeled item queried before the nightly job; a fast put-down; an observed caregiver relocation; a later sighting after an unobserved relocation; two refills with matching patient, drug and dose; network loss and screen lock, logged as coverage loss on the rig.
6. **Week 4: decide on the Hand Sentinel.** From where the chain actually failed. If contact detection or localization is the bottleneck, write the annotation ontology, pseudo-label one hour with the teacher, audit it by hand, and only then size and buy labeling. If it is not the bottleneck, the $8 to 15k stays unspent.
7. **Weeks 4 to 6: photo-first Resolver under the answer contract, the three answer shapes, correction capture with audited labels.** When two hypotheses are close, ask one clarifying question; every correction logged with source, meaning, timestamp and linkage.
8. **Before any household recording: IRB determination and the bystander plan.** Consent, indicator, pause, disclosure that says keyframes go to the laptop, retention.
9. **Week 7 onward: the atlas and the landmark pass only if the data says text locations are worth their compute; then the native build, with the section 7 proxies re-measured on-device.**

What stays from the brief's "What Devin does next": keep `capture.py` and the CMP2 envelope, the `/api/camera` hardening, the SQLite ledger, the state guard, the `find_objects` wording and the test discipline. Replace YOLOE-first detection with the tiered pipeline, `InteractionTrack` with the object-centric episode, and the six-image VLM gallery with the versioned ledger. The review queue becomes the three retention tiers plus the correction loop.

---

<!-- PART 2: REVIEW LOG (rounds 2, 3 and 4). Not canonical; kept for traceability. -->

# Round 2: response to the review of v4

Oct 4, 2026 · @aneesh

The main tab is canonical. This tab is the response log: Round 2 (October 4) answered the review of v4; Round 3 (October 5, at the end of this tab) was a consistency pass that merged every Round 2 decision and the new Round 3 points into the main tab. Where this tab and the main tab differ, the main tab wins.

## Verdict and approvals

The second review is accepted in full, with one addition at the end of section 3. It found three real design holes in v4 (object crops, capture scheduling, immediate indexing) and two sentences v4 presented as evidence that were not. Nothing in it reopens the architecture, and its closing instruction stands: freeze the broad architecture after these fixes and build one native end-to-end path.

Approved without change:

- The verdict itself: v4 direction approved for a prototype; not yet an implementation spec.
- Section 1, both corrections. v4 called 70% an evidence-backed expectation. It was built from the review's own illustrative 69% (made-up component rates) and MemPal's 72% (a different measure of a different system). Neither is evidence. 70% is the initial experimental target; actual v1 performance is unknown.
- Section 2, the observability limit and the re-observation path. Pam remembers observed caregiver relocations. The hand-only trigger misses a tracked item seen at rest in a new place with no hand present.
- Section 3, object-region localization as an explicit component. This is the largest gap in v4: MediaPipe gives landmarks, and v4 drew an arrow from landmarks to DINOv2 crops with nothing in between.
- Section 4, all three scheduler problems: a 2 fps filter cannot feed a 5 fps detector; global SSIM suppresses the rest evidence; 1080p pre-roll cannot be created after the grasp is confirmed.
- Section 5, the circular lookup. DINOv2 and SigLIP 2 are different spaces; a text query cannot find an unindexed new item.
- Sections 6 through 8, the OCR, answer-contract and data-model tightenings.
- Section 9, choose the phone platform now. Not the glasses; the phone, OS, camera, mount and runtime.
- Section 10, the five-outcome rubric with hedged-wrong, a pass criterion for caregiver relocation, the medication bound on medication queries only, and chronological scoring of corrections.

The largest single correction is the licensing one. "Licensing is a ship-time constraint" is wrong where a license restricts the research use itself, which Apple's model terms do. The replacement is in section 2 of this tab. It narrows the "validate with existing checkpoints" plan to checkpoints whose terms permit the experiment; it does not remove the plan, because DINOv2, SigLIP 2, MediaPipe and the platform OCR are all permitted.

## Corrections to v4

Five sentences in the main tab are wrong or overstated. The two factual ones are corrected in place on the main tab; all five are listed here so the change is visible.

| v4 said | Problem | Replacement |
| --- | --- | --- |
| "The honest end-to-end expectation for v1 is about 7 in 10; MemPal's 72% and the review's 69% land in the same place." | Neither number is evidence about v4. 69% was an illustration with invented rates; 72% is description accuracy of a different system. | "Actual v1 performance is unknown. 70% end-to-end success is the initial experimental target." |
| "Licensing is a ship-time constraint, not a research-time one." | Some model terms restrict product-development research itself. Apple's exclude it explicitly. Running a checkpoint on our own footage does not lift its terms. | "We validate with existing checkpoints whose terms permit our intended experiments, obtaining permission where needed. Each checkpoint's weight, code and dataset terms are checked separately." |
| "A pharmacy label yields exact instance identity." | Two refills share patient, drug and dose. Retail barcodes identify a product type. | "A label yields text evidence and candidate identifiers. Rx number and fill date distinguish refills better than drug and dose; continuous visual tracking is what establishes physical continuity." |
| "A photo cannot be wrong about layout the way a sentence can." | True of layout, false of the answer: the photo can be the wrong bottle, the wrong episode, a pre-placement frame, or stale. | The answer contract in section 4 of this tab. |
| "The correction loop replaces most of the labeling budget over time." | A hypothesis stated as a plan. Corrections give identity and location constraints, not contact masks or boxes. | "The correction loop is expected to reduce labeling cost. By how much is measured, not assumed." |

Two more that are not wrong but were loose: "10 to 20 ms on NPU" in the tier table should read "about 17 ms CPU, 12 ms GPU on a Pixel 6 per Google's published benchmark; NPU unmeasured." And "the camera is the dominant power draw" is a hypothesis to measure alongside screen, compute, location and radio, not a premise.

## Components v4 left out

Four components are added. Each is a contract between stages that v4 drew as an arrow.

**1. Object-region localization.** Sits between the hand stage and every consumer of crops (DINOv2, OCR, the ledger). Output per episode: `target_region`, `region_source`, `region_confidence`, `association_to_hand`, `association_to_pre_contact_object`, `association_to_resting_object`. If localization fails, the episode is kept as context-only with no object identity; a fabricated identity is worse than none.

The cheapest mechanism to try first, before any proposal model: difference the pre-contact frame against the rest frame. With the IMU confirming the head was still, or a homography registering the two frames when it was not, the region that changed is where the object left (pre-contact crop) and where it arrived (rest crop). During the carry, the region moving with the hand under sparse optical flow, minus the hand's own convex hull from the landmarks, is the held-object proposal. Both are tens of milliseconds and need no training. A tiny class-agnostic proposal model is the fallback if differencing fails on cluttered surfaces.

The experiment that goes with it, taken from the review: run the ledger and resolver once on hand-verified crops and once on automatic crops. The gap between the two numbers is the perception problem; the first number alone is the memory-logic problem. Without this split, every failure looks like a model failure.

**2. Re-observation path for tracked items.** Interaction-triggered capture is right for discovery. It is wrong for a durable item that was moved out of view and is later seen at rest with no hand present. Three distinct evidence types, each with its own confidence ceiling:

- Discovery: a new candidate, requires a handling or a relevance signal.
- Handling update: a tracked item moved by any actor, witnessed.
- Re-observation: a tracked item sighted at rest, no handling seen. Updates `last_observed` with the status "sighted," never "placed."

Re-observation runs bounded and on demand, not as a shelf catalog: when the user asks about item X, match X's trusted DINOv2 exemplars against the day's idle keyframes, most recent first, stopping at the first confident hit. This keeps the original rule that pam does not log every bottle it sees; it only looks for bottles it already knows about, when asked. The pilot reports two numbers separately: how many relevant moves were visible to the camera at all, and how many visible moves the system understood.

**3. Capture state machine.** Tier 1 is a mode controller, not a filter. Capture, analysis and retained-image resolutions are three separate settings.

| State | Capture mode | Analysis | Duplicate suppression | Retained |
| --- | --- | --- | --- | --- |
| Idle | A mode the device supports, with a bounded pre-roll buffer | Hand check at low rate and resolution | On, for storage and idle compute only | Nothing, until an episode starts |
| Escalating | Full capture mode begins the moment a hand appears or relevant motion starts, not after a 300 ms grasp | Hand and contact at full rate | Off | Pre-roll is promoted into the episode |
| Active episode | Full | Localization, co-motion, contact, release, rest | Off: the near-duplicate rest frames are the evidence | Contact, release and rest frames; quality gaps recorded explicitly |
| Settled | Returns to idle mode | Keyframe selection | On | 6 to 8 keyframes, crops, a high-resolution OCR source crop |

The pre-roll is whatever resolution idle capture runs at. If that is lower than the identity crop wants, the pre-contact crop is lower resolution and the identity stage is told so; it is not upsampled and treated as equal.

**4. Immediate indexing of new items.** One SigLIP 2 embedding per genuinely new candidate, computed asynchronously within minutes of capture. New candidates are rare (a handful a day), so this is a handful of forward passes, not one per episode; the compute saving in v4 survives, the circular lookup does not. Additional views, bank cleanup and maintenance still wait for the charger. A query that arrives while a candidate is unindexed prioritizes it and the answer carries `index_pending` rather than "I haven't seen it." Background jobs are not guaranteed to run every night on Android; the nightly batch is a convenience, not a dependency.

## Rules tightened

These amend the twelve rules on the main tab. Rule numbers refer to that list.

- **Rule 2, admission.** Durability governs retention and trust, not searchability. A candidate handled once today is answerable today, with the answer qualified ("something I saw once, this afternoon"). Losing a new item on day one is a normal query, not a gap. This also covers items only ever handled by a caregiver.
- **Rule 5, containment.** "Keys in purse, purse on chair" is an inferred location. Moving the purse does not re-observe the keys. Both facts keep their own timestamps: "I saw the keys go into the purse at 2 pm; I saw the purse on the chair at 3 pm." Containment links carry a timestamp, a confidence, explicit removal and uncertainty handling, and cycle prevention.
- **Rule 7, versioning.** Not only identity. Actor classification, relevance and location interpretation are all hypotheses and all versioned. Raw frames, capture times and sensor readings are the only observations. "Three independent fields" means none implies another automatically; their evidence may still inform each other.
- **Rule 12 becomes the answer contract.** Every answer carries: reference image, only when a reliable sighting exists; target indication in the image, only when supported; capture time; identity status; location-evidence status; whether the location is observed, sighted or inferred; room, or "room unknown" until room identification has a source (a DINOv2 descriptor does not name rooms). An abstention does not say "the last time I saw it," because that asserts an identity match. Showing the nearest candidate when no reliable sighting exists is false assurance and is not done. Answers are image plus simple speech; image alone is tested against it, not assumed, because a mounted phone or low vision can make the image inaccessible.
- **OCR is evidence, not identity.** Stores the recognized text, the source image and an uncertainty. Contributes candidate identifiers (drug name as category, patient name as relevance, Rx number and fill date as the strongest refill discriminator). Never establishes ownership or verified contents on its own. Extracted dose text is never an input to any medication-taking or dosing feature. The OCR source crop is kept at capture resolution, separately from the 224 px embedding crop; ML Kit wants roughly 16 px per character.
- **Corrections are audited.** Each correction stores its source, meaning, timestamp and the hypothesis it links to. "It was in the drawer" can mean current location, past location, usual home or a mistaken recollection; the resolver asks which when it matters. A sample is human-audited before any export as training labels. Service personalization (this user's ledger learns from this user's correction) is separate from consent to global model training. Corrections are scored chronologically: a correction improves future answers and never retroactively improves a scored past answer.
- **The rubric has five outcomes.** Correct; hedged-correct; hedged-wrong; confident-wrong; abstain. A historically accurate photo of the counter is still a wrong answer if the item is now in the drawer, so the rubric scores current-location usefulness, not photo truthfulness. Caregiver relocation gets its own pass criterion. The medication error bound is computed on medication queries only.

## Platform decision and the frozen test list

**Decision, October 4: the test rig is a browser web app on an iPhone, streaming to the laptop server.** This is what the current code already does (`capture.py`, the CMP2 envelope, `serve.py` over HTTPS). The wearable comes later and must run the whole pipeline on-device, so the rig is built to the same shape: the stages that run in the phone's browser are exactly the stages a wearable would run on its own silicon, and the packet the phone ships to the server is the contract a wearable would keep internally. Nothing about the Android-vs-iOS background-capture question is decided by this; it is deferred to the native build.

**What runs where in the rig.**

| Stage | Where | How, in Safari | Note |
| --- | --- | --- | --- |
| Capture | Phone | `getUserMedia` rear camera at 720p; `requestVideoFrameCallback`; decimate to 5 fps idle, 10 fps active; downscale to 256 px on a canvas for the cheap stages | A secure context is required, which is why `serve.py` carries `cert.pem`. Keep HTTPS; close the key route. |
| Gate: sharpness, near-duplicate, motion | Phone | Laplacian variance on the 256 px canvas; frame difference against the last kept frame; `DeviceMotion` at about 60 Hz (needs `requestPermission` from a tap on iOS) | Geolocation for the geofence prior, foreground only |
| Hand presence and landmarks | Phone | MediaPipe Hand Landmarker, Tasks Vision JS, WebGL delegate, 256 px input | Expect 20 to 40 ms per frame in JS on a recent iPhone; measure. A JS number is an upper bound on native. |
| Grasp, episode state machine, ring buffer | Phone | Finger-curl heuristic on landmarks; frame-difference co-motion; last 2 s of 720p JPEG in memory, about 1 MB | Escalation starts when a hand appears, not after a confirmed grasp |
| Episode packet | Phone to server | WebSocket; 6 to 8 keyframes, landmarks, timestamps, IMU and location per episode; one low-resolution keyframe every 30 s while idle, for the re-observation path | Bytes per hour is the proxy for radio power |
| Object localization, DINOv2, SigLIP 2, OCR, ledger, resolver | Server | Python, as now. OCR via Tesseract, or the Vision framework if the server is a Mac. | Moves on-device for the wearable with the same inputs and outputs |
| Voice | Phone and server | Push-to-talk: `MediaRecorder` to server STT; reply spoken by `speechSynthesis` on the phone | Safari's own speech recognition is server-based, so the rig does not test offline speech |

**Constraints the browser imposes, and what to do about each.**

- The camera stops when the tab is backgrounded or the screen locks. Use the Screen Wake Lock API, turn auto-lock off, set brightness to minimum, and log every stop as coverage loss. Do not try to fix this in the browser; it is the native build's job.
- Add the app to the home screen (standalone mode) to lose the Safari chrome. Verify `getUserMedia`, the wake lock and `DeviceMotion` all work in standalone on the test iOS version before mounting anything.
- Switching resolution mid-stream with `applyConstraints` is unreliable in Safari. Capture at one resolution and downscale on a canvas for the cheap stages. This is cheaper than restarting the stream, and it makes the pre-roll full resolution, which removes the Round 2 pre-roll problem for the rig.
- The ledger stays on the server in SQLite, as now. IndexedDB on iOS is subject to eviction and is not a system of record.
- Safari ships WebGPU on iOS 18 and later. Running DINOv2-S in the browser through ONNX Runtime Web is an optional later experiment for the on-device question; the rig does not need it.

**What the rig validates, and what it cannot.** It validates the memory logic, the episode state machine, object localization, scripted cases 1 through 5, the answer contract and the correction loop. It cannot measure power, thermal behavior, all-day battery, background capture, on-device embedding latency or offline speech; those stay hypotheses until the native build, and case 6 is deferred with them.

**Efficiency is still measured, as proxies.** Four numbers are hardware-independent and predict wearable cost: escalation rate (the share of captured frames that reach the hand stage, and the share that open an episode); bytes shipped per hour; phone-side milliseconds per stage in JS, read as an upper bound; and server-side milliseconds per event, read as the on-device work a wearable would inherit. A design that keeps escalation under a few percent of frames and ships tens of megabytes a day, not gigabytes, is one that can move onto a wearable; one that does not will not be rescued by better silicon.

To record for the rig: iPhone model, iOS and Safari versions, standalone or tab, the capture mode Safari actually delivered, the mount, and the server machine. Glasses later reuse the episode packet, with field of view, motion, calibration and timestamp alignment revalidated.

**The architecture is frozen after the fixes above.** No further wholesale redesign. The work is one native end-to-end path: capture an interaction, localize the actual object, record evidence, make the new item searchable within minutes, answer with the correct reference image under the answer contract, accept a correction.

**Six scripted cases, run before any further investment decision.** Each one isolates a different stage, so the results say where the next engineering goes.

| Case | What it isolates | Pass looks like |
| --- | --- | --- |
| New unlabeled item, queried before the nightly job | Immediate indexing | Answer with `index_pending` resolved or an honest pending state; never "I haven't seen it" |
| Caregiver move in view vs. outside camera coverage | Admission-vs-update rule, and capture coverage vs. model failure | In-view move recalled; out-of-view move reported as unknown, with the prior location marked stale |
| Fast interaction between idle samples | Capture escalation latency | Episode captured with contact and release evidence, or an explicit quality gap recorded |
| Two refill bottles, same patient, drug and dose | OCR as evidence; lookalike groups; continuity | Distinguished by Rx number or fill date when readable; otherwise one group with both locations preserved, never one merged row |
| Keys inside a purse that later moves | Containment as inferred location | Two timestamps reported; keys' last-seen not changed by the purse moving |
| Screen lock, app switching, interruption, recovery | Platform operating mode | Native build only. In the browser rig this case is not scored; every stop is logged as coverage loss |

These replace the brief's week-by-week numbers as the gate. The cost figures on the main tab stand as an API-spend estimate (about $6.50 at the stated rates) and are not operating cost or gross margin until tie-break images, retries, digests, storage, sync, support, fees and any hardware subsidy are added.

## Round 3 (October 5): consistency pass

The third review saw only the main tab and found it describing two systems at once, with two headings saying the opposite of their bodies. That was a fault of putting fixes on this tab instead of in the canonical text, and the review's instruction, a consistency pass rather than another rewrite, is what was done. Every Round 2 decision is now in the main tab in place, and these Round 3 points are new and merged with them:

- The rig and the native target are separated explicitly (main tab sections 1, 2 and 7), with a rig-versus-target table and a table of which rig results transfer to the wearable.
- The section 3 table heading now reads "Relevance-based admission; actor-independent updates."
- The pilot table note on 70% now reads "initial experimental target, not a forecast."
- Store-trip connectivity: one of carry-the-laptop on a hotspot, an authenticated tunnel, or record-and-replay, chosen and recorded before the trip.
- Failure modes with defined behavior: Wi-Fi loss, laptop sleep, backgrounding, server restart, delayed upload; processing on observation time, never arrival time.
- Frame accounting: `getSettings()`, `requestVideoFrameCallback` metadata, and seven counters from source frames to observation gaps.
- MediaPipe JS inference runs in a Web Worker; `DeviceMotion` denied, unavailable and interrupted are handled; missing IMU means unknown.
- The "$0 platform recognizer" cost line is marked native-only; the rig uses push-to-talk to server STT.
- The rig's disclosure says keyframes go to the laptop.
- Rules 2, 5, 7 and 12 rewritten in place; rule 13 (re-observation) added.
- Section 6 paragraphs on photos, labels and corrections rewritten in place.
- Rubric: five outcomes; caregiver relocation has its own pass criterion; the medication bound is on medication queries; the visible-moves fraction is reported.
- Research-rig cost is separated from subscription economics.

Not changed, because the review's point was already answered on the main tab or is a hypothesis by design: the 69% chain in the section 3 table stays as the reason end-to-end testing matters, labeled as an illustration; the containment inference stays as a rule with its two timestamps; the "camera dominates power" sentence is labeled a hypothesis.

Still open after this pass: the exact hand-contact checkpoints and their terms, checked one by one before use; the store-trip connectivity choice itself; and the iPhone model, iOS version and standalone-mode verification, recorded when the rig is first mounted.

## Round 4 (October 5, evening): interface pass

The fourth review was against the exported file with both parts and found three contradictions, one timing ambiguity, four contracts not yet buildable without guessing, and eleven sentences that overstated. All are merged into the main tab; none changed the architecture.

| Finding | What changed on the main tab |
| --- | --- |
| C1: §6 abstention example asserted a sighting and a photo | §6 paragraph rewritten to the rule 12 shapes; abstain has no photo and no claimed sighting |
| C2: §3 promised phone benchmarks for every stage | Row 5 now says each stage is benchmarked where it runs: rig now, native later |
| C3: "event keyframes only" vs. idle keyframes | §7 storage now has two stores: durable event keyframes, and a 24-hour rolling idle cache for re-observation |
| S1: localization listed at 10 fps on the phone and on the laptop | Tier 3 is evidence acquisition on the phone; localization consumes the packet in tier 4, per episode, never per frame |
| S2: optional write-path VLM row read as allowed | Row relabeled "September brief (not in v1)" |
| Four contracts | New section "Stage contracts": the episode packet, the localizer's inputs and outputs, the capture controller's transition predicates with initial values, the indexing queue and readiness deadline, and the answer fields with the reliable-sighting definition |
| "Upper bound on native" (§2, §7 twice) | Now "a measurement of the rig implementation, not a bound on the target" |
| "Can move onto a wearable; not rescued by silicon" | Proxies inform the design; feasibility is established only by the native build |
| "A handful a day" | Expected low after the first days, high on day one; measured, including identity fragmentation |
| "Lower idle rate is acceptable because nothing is happening" | An assumption the missed-transition test evaluates |
| "Never stalled" by the Web Worker | The synchronous call does not block; contention still can, and the counters show it |
| WebGPU on iOS 18 | Shipped by default in Safari 26 |
| Resolution switching "unreliable" and "costs a restart" | A frozen policy choice; the justification qualified, not claimed universal |
| "Most common elder-care scenario" (§1, §3) | "The scenario we prioritize" |
| "Value is highest exactly when" (§4) | An expectation the pilot measures |
| "Single largest saving" (§6) | "A large saving" |
| Ring buffer "in every case" | A requirement with IndexedDB best-effort mirroring; losses logged as coverage loss |

Subagent results noted as historical: rates verified at the time; 42 of 49 integration tests passing before the SQLite fix, not rerun since.

After this pass the spec is frozen for build. Devin's go-ahead for section 10 steps 1 and 2 is given with the export of this revision.
