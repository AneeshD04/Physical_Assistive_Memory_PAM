# MEMORY review of MEMORY_SYSTEM_V4 (final, round 2, revised after cross-review)

Reviewer: MEMORY (memory, retrieval, system methods). Materials read: `spec/MEMORY_SYSTEM_V4.md` Part 1 (rules 1 to 13 at L63-L75; section 6 L77-L91; section 7 indexing L119-L120 and storage/re-observation L130; stage contracts L169-L189; pilot criteria L208-L232), `spec/ROUND4_RESPONSE.md`, `code/perception/object_memory.py`, `code/perception/personal_memory.py`, `code/server/object_api.py`, `code/perception/voice.py`; round 1: `drafts/ARCH.md`, `final/ARCH.md`, `drafts/PERCEPTION.md`, `final/PERCEPTION.md`; round 2: `final/ARCH.md` (revised; "Round 2 changes", BL-5/6/8/9/11, 2.4-2.7, section 7, "Reactions to peers"), `final/PERCEPTION.md` (revised; "Round 2 changes", section C, "Answers to MEMORY", "Positions"), `final/COMMERCIAL.md` (sections 1, 2, 4.4-4.6, 6, "Answers to MEMORY", "Reactions to peers: To MEMORY") in full.

Marking: `[V: url]` is a page I opened in this session; `[V-peer: url]` is a page a named peer opened and cited that I did not re-open; `[B]` is a belief or my own arithmetic. Every license below is `[V]` or `[V-peer]` from the LICENSE file, model card or terms page unless it says `[B]`. Line numbers `L…` are `spec/MEMORY_SYSTEM_V4.md` as exported.

Network note: this session reached `arxiv.org` (html and pdf), `raw.githubusercontent.com`, `huggingface.co` model pages (via the fetch tool; the HF API was blocked), `developers.deepgram.com`, `developer.apple.com`, `developer.android.com`, `docs.stripe.com`, `sqlite.org`, `martinfowler.com`, `pmc.ncbi.nlm.nih.gov`, `par.nsf.gov`, `about.fb.com`, `axios.com`, and `dspace.mit.edu`. It could not open `deepgram.com/pricing` (COMMERCIAL did; now `[V-peer]`), `deepgram.com/legal/terms` (COMMERCIAL did), the openWakeWord README (I opened only its LICENSE; COMMERCIAL opened the README) or the MemPal PDF itself.

---

## Round 2 changes

What changed from the round-1 final, and which peer answer drove it. Status per item: resolves (my recommendation stands, with the fact recorded), changes (a recommendation is different), disputed (none in this round).

1. **Section F, openWakeWord (COMMERCIAL A2; its reaction to MEMORY 1): changes.** My "Apache-2.0 [V]" covered the code only; "All of the included pre-trained models are licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International license" [V-peer: https://raw.githubusercontent.com/dscripka/openWakeWord/main/README.md L278]. The wake-word fallback is now "none in v1; if ever wanted, openWakeWord code with a model trained on our own synthetic data". The license cell is corrected.
2. **Section F, Piper (COMMERCIAL A2; reaction 2): changes.** Piper code is MIT [V], but the voice files carry their dataset's terms; the default `en_US-lessac-*` voice is Blizzard-licensed and research-only per the maintainer thread; LibriTTS-R (CC BY 4.0) and LJSpeech (public domain) voices are the safe ones [V-peer: https://huggingface.co/rhasspy/piper-voices/blob/856d185c267ad13c45e707792c8c6fbf5fac01d9/en/en_US/lessac/medium/MODEL_CARD; V-peer, secondary: https://github.com/rhasspy/piper/discussions/271]. The Piper fallback is now "`en_US-libritts_r-*` or `en_US-ljspeech-*` only, never `lessac`".
3. **Section F, Kokoro and Piper both reach espeak-ng, GPL-3.0 (COMMERCIAL A2): resolves with a scope condition.** Kokoro's G2P (`misaki`, Apache-2.0) falls back to espeak-ng, and `piper-phonemize` links it; espeak-ng is GPL-3.0 [V-peer: https://raw.githubusercontent.com/espeak-ng/espeak-ng/master/COPYING]. Both TTS fallbacks are laptop/server-only (no distribution, so no GPL obligation); the native target uses platform TTS as the spec says (L104), and if a laptop TTS is ever shipped on a device, espeak-ng is dropped or the bundle is treated as GPL-3. The cells are corrected.
4. **Section F, Deepgram (COMMERCIAL A1): resolves; recommendation conditioned.** Nova-3 pre-recorded confirmed at $0.0043/min on the live page [V-peer: https://www.deepgram.com/pricing]; ToS §3.2 grants Deepgram an "irrevocable, perpetual, transferable, sublicensable" training licence on Your Content unless opted out per request (§3.3) and §3.5(4) forbids PHI without a BAA [V-peer: https://deepgram.com/legal/terms]; the parameter is `mip_opt_out=true`, after which "Data from opted-out requests is retained only for the duration necessary to process the request" [V-peer: https://developers.deepgram.com/docs/the-deepgram-model-improvement-partnership-program]. The Deepgram fallback is now: `mip_opt_out=true` on every request, enabled only under `deployment_profile = family` unless a BAA exists, and never the correction loop's audio store (that stays on the laptop).
5. **Section G, caregiver as data subject (COMMERCIAL A3): resolves; design extended.** The caregiver is a participant, not a bystander: own IRB consent in the pilot and own terms and privacy notice in the product, covering identity, reports, voice notes, photos, repetition of their words to the wearer by name, retention, and withdrawal as a `source` version bump (`caregiver:<id>` → `caregiver:withdrawn`) [V-peer: final/COMMERCIAL.md §4.5]. The proactive push that sends a rest-frame photo to the caregiver is a disclosure of camera imagery to a third party and goes into both consents. Voice notes are one-party recordings and are handled like wearer push-to-talk clips (transcript kept, audio ≤ 30 days).
6. **Section A/E, EgoObjects and PerSAM (COMMERCIAL A4): resolves.** EgoObjects is treated as research-only until its licence PDF is read; CUTE covers the identity evaluation. Reimplementing PerSAM's method on RepViT-SAM from the paper carries no licence obligation from the unlicensed repo; cite the paper [V-peer: final/COMMERCIAL.md Answers to MEMORY 4].
7. **Section B, schema (ARCH 7(e), COMMERCIAL reaction 4, ARCH BL-11, PERCEPTION position on BL-11): changes.** Added: `retention_until` and `consent_version` on every observation table, a `media_retention` side table so retention deletes files while immutable rows and digests stay (ARCH's resolution of COMMERCIAL's trigger condition; accepted over nullable paths), a `retention_policy` table keyed by consent class and data class, `landmark_reduction` with the raw landmark file's `retention_until = max(localization done, revision window)` where the revision window is 72 h initial (PERCEPTION), `households(deployment_profile, consent_version)`, `calibrations`, `localizations` (the localizer's per-episode output, versioned per revision), `exports` with per-sample consent. Section B states the retention rule and what the correction loop may keep.
8. **Section B, idempotency (ARCH 7(e)): resolves.** ARCH accepted the departure from "error on mismatch" with conditions I already meet: the superset/conflict relation is computed by the server from stored bytes, the phone deletes its mirror only on an idempotent ack, WAL replaces PERSIST with a startup check of `sqlite3.sqlite_version`, `/api/answer` reads `item_current` only, `rebuild_all()` is the migration path. Written explicitly in section B.
9. **Section C, conformal set (ARCH 7(d)): resolves with four conditions accepted.** (i) the 0.15 margin stays as the logged interim `calibration_id = margin_0.15_initial` until the week-2 rig calibration; (ii) the empty-set rate on in-bank queries (fragmentation) is a reported number in section H and `merge` by correction is one tap; (iii) the co-visibility check degrades to "no refusal, logged" when the query-time homography fails (ARCH and PERCEPTION both asked), with one addition of mine: on homography failure a medication item's shape is capped at `hedged`; (iv) `exemplars` stores `crop_px` so calibration can be bucketed by crop size.
10. **Section C/E, localizer contract (PERCEPTION round-2 items 5 and 6; ARCH BL-9.9): changes.** The localizer emits `target_regions[]` (≤ 2, each `{frame_id, bbox, mask, region_confidence, rival_of}`), a mask per identity crop from the region's own source, `release_point`, and `container_region` geometry; the identity stage fills `container_region.item_id` and checks `is_container` [V-peer: final/PERCEPTION.md C, Positions]. Schema and operations updated: `localizations` rows carry the geometry; `region` hypotheses are written per item by the identity stage; containment links are created by the identity stage, not the localizer.
11. **Section E, shared masked-token recipe (PERCEPTION A2, Positions (a)): changes.** The exemplar bank, the re-observation index and the refinement step use one `token_recipe_id` (defined in section E); the pooled/PCA index format is frozen only after it keeps ≥ 95% of the unpooled recall@3 on CUTE in-the-wild (PERCEPTION's condition); PERCEPTION's cost estimate for the arrival pass (60 to 200 ms, [B]) is recorded alongside mine.
12. **Section F, STT (ARCH 7(g)): resolves.** whisper offline primary accepted; conditions accepted: `large-v3-turbo` int8 latency for a 5 s clip measured on the Windows laptop CPU in week 2, falling to `small.en` with the vocabulary prompt if over 2 s.
13. **Section D, local LLM residue (ARCH section 7, last paragraph): resolves.** Deferred to weeks 5-6, built only if the week-3 clarify arm shows a residue; the cloud LLM is `deployment_profile`-gated with BAA/HIPAA readiness before any agency use and no PHI in JSON schema definitions [V-peer: https://platform.claude.com/docs/en/manage-claude/api-and-data-retention].
14. **Answer shape (ARCH 7(c)): resolves.** More than three members for voice becomes `clarify` ("which one?") or `abstain`; members ordered by recency; `members[]`, `group`, `reported`, `clarify`, `stale_reason` go into the day-1 freeze.
15. **Section H: changes.** Aggregates gain the empty-set (fragmentation) rate, the duplicate-item count per day, and the `covis_unchecked` rate; the sheet gains `landmark_fps` and `hand_bbox_interpolated` pass-throughs from PERCEPTION's packet additions so pilot failures can be split by Worker rate.
16. **Section F tags corrected:** Deepgram prices from `[V, secondary]` to `[V-peer]` at the primary; the Deepgram data terms added as `[V-peer]`.

Nothing in round 2 changed a primary choice in the decisions table except the two license-driven fallbacks (openWakeWord models, Piper voice); what changed is conditions, contract fields, retention and consent.

---

## Decisions in one table

| Item | Primary | Fallback | Not this |
| --- | --- | --- | --- |
| A. Episodic memory architecture | Keep the spec's third way: structured evidence ledger written from embeddings at episode time, photo at read time. Borrow one piece from the training-free VQ2D line (RELOCATE): mask-pooled DINO features matched against an exemplar, used for re-observation only | Caption-at-write, text-at-read (EgoLife/ReMEmbR/MemPal style) as a charger-tier annotation layer, never on the v1 write path | Per-frame visual-query detectors over all video (VQ2D-style; 0.37 tAP25 and minutes of compute per query); any method whose code is non-commercial (EgoLife S-Lab, ReMEmbR NVIDIA non-commercial) |
| B. Ledger | Event-sourced SQLite (STRICT tables, WAL, version checked at startup): immutable `episodes/keyframes/idle_keyframes/reports/localizations`, append-only versioned `hypotheses`, a materialized `item_current` recomputed per item inside the writing transaction by one Python function that can also rebuild everything from scratch; retention by `retention_until` per row and a `media_retention` side table; `consent_version` on everything exportable | Same schema with the current view as a plain SQL `VIEW` while the write rate is tiny | Mutable rows (the current `candidates.payload` rewrite in `gallery()`), triggers carrying resolver logic, nullable media paths on immutable rows, a second database engine |
| C. Identity and groups | Trusted/provisional exemplar banks; identity decided by a split-conformal prediction set over the bank (α = 0.05 all items, 0.01 medication); singleton = match, empty = new, ≥ 2 = ambiguous (no bank write, lookalike link, `group`); merge/split/correct as explicit versioned operations; co-visibility check degrades to no-refusal-logged on homography failure | The spec's margin rule (initial 0.15) as the logged interim until the calibration set exists (CUTE in week 1, the rig set in week 2) | A tuned margin presented as a safety guarantee; merging lookalikes on OCR category alone |
| D. Query resolution | Lexical (aliases, user names, OCR text) to an item set; SigLIP 2 text-to-crop only to narrow a set that is already category-matched ("the blue one"); one clarifying question when the set has 2 or 3 members; `group` when they are lookalikes; name request or `abstain` above 3 | Local LLM (Qwen2.5-1.5B-Instruct, Apache-2.0) over a compact textual ledger for time/place phrasings, weeks 5-6 only if the clarify arm shows a residue; cloud LLM only for the residue of that, `deployment_profile`-gated, inside the 5 calls/day budget | SigLIP 2 text-to-crop as the primary instance picker; any cloud VLM on the write path |
| E. Re-observation | Two-stage, bounded, one shared masked-token recipe: (1) at arrival, one DINOv2-S/14 pass per idle keyframe at 518 px, cached as a pooled patch index; (2) at query, exemplar-token vs index scoring over the 24 h cache (sub-second), then refinement on at most 3 frames (DINOv2 on a 2.5× crop, RepViT-SAM point-prompted at the peak, conformal check in the bank's vector space); 2 s timeout | Frame-level global-vector shortlist only, no spatial refinement: reports "seen in a frame" without a box (`target_indicated = false`) | A proposer over every idle frame; patch matching on 256 px frames (a pill bottle at 1 m is one patch) |
| F. Speech | Rig: push-to-talk `MediaRecorder` to the laptop; STT whisper.cpp or faster-whisper with `large-v3-turbo` (MIT) offline, `initial_prompt` from the ledger's item names, latency measured in week 2 (fall to `small.en` if a 5 s clip takes over 2 s); TTS `speechSynthesis` on the phone. Native: Apple SpeechTranscriber (iOS 26, on-device) / Android `createOnDeviceSpeechRecognizer` (API 31) | Deepgram Nova-3 pre-recorded at $0.0043/min with `mip_opt_out=true` on every request, `family` profile only unless a BAA exists; Kokoro-82M (Apache-2.0) on the laptop only (espeak-ng GPL-3 fallback stays server-side); Piper (MIT) with `en_US-libritts_r-*` or `en_US-ljspeech-*` voices only; no wake word in v1, and if ever wanted openWakeWord code (Apache-2.0) with a model we train ourselves | Deepgram Flux for push-to-talk clips (a streaming turn-taking line); the Voice Agent API; openWakeWord's pretrained models (CC BY-NC-SA); Piper's `lessac` voice (research-only); any laptop TTS shipped on a device with espeak-ng inside |
| G. Caregiver platform | Append-only "reports": one tap on an item card plus an optional voice line or photo; stored as a `location` hypothesis with `source = caregiver_report:<id>`; answered as `hedged` with attribution ("your daughter says…"); camera evidence ordered by observation time supersedes or is superseded by it; caregiver has their own consent/terms; withdrawal is a `source` version bump | A proactive one-question push to the caregiver (with the rest-frame photo, disclosed in both consents) when the camera saw an `other_person` handling a durable item with an uncertain destination | Free-form forms; a caregiver-entered location shown as a confident photo answer; speaker identification on voice notes |
| H. Evaluation | MemPal's in-home protocol (20 objects, 40 min, 3 min per retrieval) extended with the spec's scripted cases, scored per query on two axes into the five outcomes; the scoring sheet in section H with the fragmentation, covis-unchecked and Worker-rate columns | Same sheet on the rig's recorded footage with hand-verified crops (the memory-logic arm) | Component metrics as the pass criterion; counting abstentions as neutral |

---

## A. Episodic object memory for egocentric video: what the frontier does and what transfers

### The three families

1. **Visual-query localization over raw video (Ego4D VQ2D/VQ3D).** The task is "spatio-temporally localize the last occurrence of a visual query object within a long-form egocentric video" given a query crop [V: https://arxiv.org/pdf/2509.00385]. The 2025 trained state of the art (HERO-VQL) reaches tAP25 0.37 / stAP25 0.28 on the test set versus VQLoC's 0.32 / 0.24, and it is a per-frame detector over 32-frame clips with no speed reported [V: same]. The training-free RELOCATE pipeline (SAM ViT-H masks, DINO ViT-B/8 features at 384×512 pooled inside each mask into "object tokens", cosine similarity to the query tokens, then crop-and-re-segment refinement) beats the trained methods: stAP25 0.35, tAP25 0.43, success 60.1% vs 55.9%, recovery 50.6% vs 45.1%; but video preparation costs 1,422 s per 1,000 frames and a query costs about 40 s unoptimized [V: https://arxiv.org/pdf/2412.01826]. Two RELOCATE ablations matter to us: removing refinement drops stAP25 from 0.333 to 0.246, and DINOv2 ViT-L/14 was better at frame-level retrieval but worse at spatial precision than DINO ViT-B/8 [V: same]. The language-query variant (NLQ) is worse still: the 2024 challenge winner is at R@1 IoU=0.3 of 28.05% [V: https://arxiv.org/html/2406.15778v2].

2. **Caption at write, text at read.** EgoLife (CVPR 2025): 300 h from 6 participants over a week; EgoGPT (7B) captions 30-second clips, EgoRAG keeps a hierarchical memory of clip features, descriptions and hourly/daily summaries, and retrieves top-k for an LLM; on EgoLifeQA the EntityLog category ("last use, location, price" of objects) scores 39.2% and Gemini-1.5-Pro averages 36.9% [V: https://arxiv.org/html/2503.03803v3]; the code is S-Lab License 1.0, non-commercial [V: https://raw.githubusercontent.com/EvolvingLMMs-Lab/EgoLife/main/LICENSE]. ReMEmbR (NVIDIA): VILA captions per segment, embedded with mxbai-embed-large-v1 into a vector DB with robot position and time; an LLM agent calls text/position/time retrieval functions; on NaVQA (210 questions, 34% "where is X" spatial) GPT-4o reaches 0.58 to 0.65 correctness and spatial error of 5 to 46 m [V: https://arxiv.org/html/2409.13682v1]; the code is under the NVIDIA License, "non-commercially … research or evaluation purposes only" [V: https://raw.githubusercontent.com/nvidia-ai-iot/remembr/main/LICENSE.md]. Vinci stores "detailed descriptions and corresponding timestamps" and reports no quantitative retrieval metric and no license [V: https://arxiv.org/html/2412.21080v1]. MM-Ego's EgoMemoria benchmark (629 videos, 7,026 multiple-choice questions, 30 s to 1 h) is answered at 61.27% mean debiased accuracy by MM-Ego and 60.48% by GPT-4o [V: https://arxiv.org/html/2410.07177v1]. MemPal is the same family on a person: GPT-4V over hand-detected image sequences, text-only activity logs in a vector DB, RAG for complex queries [V: https://www.alphaxiv.org/overview/2502.01801].

3. **Products.** Ray-Ban Meta's "reminders" are user-initiated ("your glasses can remember your spot in long-term parking"); nothing passive about object locations is described [V: https://about.fb.com/news/2024/09/ray-ban-meta-glasses-new-ai-features-and-partner-integrations/]. Project Astra's December 2024 build holds "10 minutes of video, as opposed to the 45 seconds" of the May 2024 demo [V: https://www.axios.com/2024/12/11/google-project-astra-hands-on]; the TED 2025 Android XR demo answered "where is my hotel key card" with "to the left of the music record", with "no specifics about recording duration or memory capacity" disclosed [V: https://hiverlab.com/android-xr-google-glasses-revealed-at-ted-2025]. These are rolling in-session video memories plus a VLM, not a ledger; none publishes an object-finding accuracy.

### Instance identity benchmarks

EgoObjects (ICCV 2023): 9,200+ videos, 114K frames, 14.4K instances, 368 categories; instance-level detection reaches 22.6 AP / 37.9 AP50 with a ResNet-101 TA-IDet; the authors "exclude objects from categories that have indistinguishable appearances between instances" [V: https://arxiv.org/pdf/2309.08816]; the repo code is MIT [V: https://raw.githubusercontent.com/facebookresearch/EgoObjects/main/LICENSE]; the dataset licence PDF was unreachable for COMMERCIAL as well, and the dataset page gives its intended use as workshop research, so it is treated as research-only and not downloaded (COMMERCIAL A4 [V-peer: https://ai.meta.com/datasets/egoobjects-dataset/]). CUTE (180 objects, 50 categories, 18,000 images, mostly two lookalike instances per category; CC BY 4.0): best DINOv2 configuration is patch-level foreground pooling, with top-1 of 89.0% under illumination change, 96.6% under pose change and 61.8% in the wild [V: https://arxiv.org/pdf/2311.00750]. PerMIR (3.1 same-class instances per frame on average): DINOv2 29.7 mAP, CLIP 20.9, OpenCLIP 26.7 [V: https://arxiv.org/pdf/2405.18025]; it has no licence of its own, so its numbers are cited and the data is not downloaded (COMMERCIAL §2).

### What transfers to PAM

- The spec's choice (embed at write, structured ledger, photo at read) is the right one and is not what the literature benchmarks. The two published families either pay a detector pass over all video at query time (family 1) or put a VLM on the write path (family 2, and the spec's L202 removes that). Numbers to keep in view: the best "where is X" systems over long video score 0.37 to 0.65 on their own benchmarks; MemPal's description accuracy in homes is 72% [V: https://www.alphaxiv.org/overview/2502.01801]. The spec's 70% initial target is in the range the field reaches, not above it.
- Take from RELOCATE the mask-pooled exemplar matching and the crop-and-refine step, for re-observation only (section E). Take from the conformal retrieval line the set-valued answer (section C). Take from MemPal the in-home protocol (section H). Take nothing executable from EgoLife, ReMEmbR or the PerSAM repository (non-commercial or unlicensed code); PerSAM's method is reimplemented from the paper, which carries no obligation (COMMERCIAL A4).
- The caption layer is not dead, it is deferred: a charger-tier caption of each rest keyframe (local VLM, nightly) would make time/place phrasings cheap to resolve (section D) at no write-path cost. Measure whether case 1 needs it before building it.

---

## B. The versioned evidence ledger

### Principles, with sources

Event sourcing: "capture all changes to an application state as a sequence of events"; "we can discard the application state completely and rebuild it by re-running the events from the event log on an empty application"; a wrong past event is fixed by "reversing it and later events and then replaying the new event and later events", not by editing; external side effects need gateways that know replay from real processing [V: https://martinfowler.com/eaaDev/EventSourcing.html]. Idempotency, the Stripe rule: the server saves "the resulting status code and body of the first request made for any given idempotency key", replays return it, "the idempotency layer compares incoming parameters to those of the original request and errors if they're not the same", keys are pruned after 24 h, V4 UUIDs are recommended [V: https://docs.stripe.com/api/idempotent_requests]. SQLite: STRICT tables since 3.37.0 (2021-11-27), types limited to INT/INTEGER/REAL/TEXT/BLOB/ANY, `SQLITE_CONSTRAINT_DATATYPE` on a failed coercion, combinable with WITHOUT ROWID [V: https://www2.sqlite.org/stricttables.html]; WAL: "readers do not block writers and a writer does not block readers", single writer, mode is persistent, same-host only [V: https://sqlite.org/wal.html]; SQLite is public domain [V: https://raw.githubusercontent.com/sqlite/sqlite/master/LICENSE.md]. ARCH's condition: the server checks `sqlite3.sqlite_version >= 3.37.0` at startup, because the Windows laptop's bundled SQLite is unverified [V-peer: final/ARCH.md 2.7, B].

What the current code already has right: `candidates.digest` plus "same id + different digest raises" (`object_memory.py` L229-L234); `_observe` refuses a silent rewrite (L380-L384); `decisions` is an audit log; `bindings` is continuity; `PRAGMA user_version` gate. What violates rule 7 today: `gallery()` rewrites `candidates.payload` (L278); `get_object()` derives state at read time with `stale = age > 3600` (L480); identity is a single column, not a version chain.

### Schema sketch (SQLite ≥ 3.37, `STRICT`, `journal_mode=WAL`, `foreign_keys=ON`)

Three layers. Layer 1 is observations and stage outputs and is immutable (triggers abort `UPDATE`/`DELETE`; retention deletes files, never rows). Layer 2 is hypotheses and is append-only (new version supersedes; nothing is rewritten). Layer 3 is derived and is rebuildable from 1 and 2 by one function. Retention and consent are columns on every row that can carry personal content.

```sql
-- Households, consent and retention policy
CREATE TABLE households (household_id TEXT PRIMARY KEY, deployment_profile TEXT NOT NULL CHECK (deployment_profile IN ('family','agency','dev_internal')),
  consent_version TEXT NOT NULL, created_at REAL NOT NULL) STRICT;
CREATE TABLE retention_policy (                -- what retention_until is computed from, per consent class and data class
  consent_version TEXT NOT NULL, data_class TEXT NOT NULL,   -- 'raw_landmarks' | 'keyframe_evidence' | 'keyframe_no_evidence' | 'idle_keyframe' | 'audio_clip' | 'caregiver_media' | 'packet'
  ttl_seconds INTEGER,                         -- NULL = until household offboarding (manual)
  PRIMARY KEY (consent_version, data_class)) STRICT;

-- Layer 1: observations and stage outputs (immutable rows)
CREATE TABLE episodes (
  episode_id TEXT PRIMARY KEY,                 -- minted on the phone, see idempotency
  household_id TEXT NOT NULL REFERENCES households,
  device_id TEXT NOT NULL, session_id TEXT NOT NULL,
  anchor_mono REAL NOT NULL, anchor_wall REAL NOT NULL,
  t_start REAL NOT NULL, t_end REAL NOT NULL,  -- observation clock
  outcome_hint TEXT NOT NULL, landmark_fps REAL,            -- PERCEPTION's per-episode Worker rate
  packet_digest TEXT NOT NULL,                 -- sha256 over canonical JSON, jpeg bytes replaced by their sha256
  packet_path TEXT NOT NULL,                   -- raw packet on disk: landmarks, imu, gaps, quality, location, burst
  received_at REAL NOT NULL,
  revision_window_until REAL NOT NULL,         -- received_at + 72 h initial; late revisions after this are 'conflict'
  consent_version TEXT NOT NULL,
  retention_until REAL,                        -- for the packet file as a whole (data_class 'packet')
  landmarks_retention_until REAL,              -- max(localization done, revision_window_until) per retention_policy 'raw_landmarks'
  landmarks_reduced_path TEXT) STRICT;         -- written by the reduction job: hand_bbox, handedness, hand_present, release_point, entry-edge flags, wearer size scalar
CREATE TABLE episode_revisions (               -- same id, different bytes: recorded, never merged silently
  episode_id TEXT NOT NULL REFERENCES episodes, revision INTEGER NOT NULL,
  packet_digest TEXT NOT NULL, packet_path TEXT NOT NULL, received_at REAL NOT NULL,
  relation TEXT NOT NULL CHECK (relation IN ('superset','conflict')),   -- computed by the server from stored bytes
  retention_until REAL, PRIMARY KEY (episode_id, revision)) STRICT;
CREATE TABLE keyframes (
  frame_id TEXT PRIMARY KEY, episode_id TEXT NOT NULL REFERENCES episodes,
  t REAL NOT NULL, role TEXT NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
  path TEXT NOT NULL, jpeg_sha256 TEXT NOT NULL, sharpness REAL,
  consent_version TEXT NOT NULL, retention_until REAL) STRICT;
CREATE TABLE idle_keyframes (                  -- 24 h rolling cache (L130)
  frame_id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households,
  t REAL NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
  path TEXT NOT NULL, global_vec BLOB, patch_index BLOB, token_recipe_id TEXT,   -- filled at arrival (section E)
  consent_version TEXT NOT NULL, retention_until REAL NOT NULL, promoted_item_id TEXT) STRICT;
CREATE TABLE localizations (                   -- the localizer's output per episode and revision (PERCEPTION C contract)
  episode_id TEXT NOT NULL REFERENCES episodes, revision INTEGER NOT NULL,
  payload TEXT NOT NULL,                       -- JSON: target_regions[] {frame_id,bbox,mask_path,region_source,region_confidence,rival_of}, release_point, container_region {frame_id,bbox,mask_path,confidence}|null, hand_bbox_interpolated flags, crops[]
  created_at REAL NOT NULL, PRIMARY KEY (episode_id, revision)) STRICT;
CREATE TABLE reports (                         -- wearer corrections and caregiver reports are observations too
  report_id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households,
  t_received REAL NOT NULL, t_claimed REAL,
  source TEXT NOT NULL,                        -- 'wearer_voice' | 'caregiver:<id>' | 'review_ui'
  raw_text TEXT, media_path TEXT, media_kind TEXT, item_id_hint TEXT,
  consent_version TEXT NOT NULL, retention_until REAL) STRICT;   -- audio ≤ 30 d; transcript stays in raw_text
CREATE TABLE media_retention (                 -- retention deletes files; rows and digests stay (ARCH's side table)
  ref_kind TEXT NOT NULL, ref_id TEXT NOT NULL, path TEXT NOT NULL, deleted_at REAL NOT NULL, reason TEXT NOT NULL,
  PRIMARY KEY (ref_kind, ref_id, path)) STRICT;

-- Layer 2: hypotheses (append-only, versioned per (item, kind))
CREATE TABLE items (item_id TEXT PRIMARY KEY, household_id TEXT NOT NULL REFERENCES households, created_at REAL NOT NULL,
  created_from TEXT NOT NULL REFERENCES episodes, merged_into TEXT REFERENCES items(item_id)) STRICT;   -- merge keeps the old row as an alias
CREATE TABLE hypotheses (
  hyp_id INTEGER PRIMARY KEY,
  item_id TEXT NOT NULL REFERENCES items,
  kind TEXT NOT NULL CHECK (kind IN ('identity','actor','relevance','location','containment','region','name','category')),
  version INTEGER NOT NULL,
  supersedes INTEGER REFERENCES hypotheses(hyp_id),
  episode_id TEXT REFERENCES episodes, report_id TEXT REFERENCES reports,   -- exactly one is set
  t_observed REAL NOT NULL,                    -- observation-clock time the claim is about (never arrival time)
  payload TEXT NOT NULL,                       -- JSON (shapes below)
  confidence REAL NOT NULL,
  source TEXT NOT NULL,                        -- 'localizer:pre_rest_diff' | 'identity' | 'resolver' | 'reobservation' | 'correction:<id>' | 'caregiver:<id>' | 'caregiver:withdrawn'
  created_at REAL NOT NULL,
  UNIQUE (item_id, kind, version)) STRICT;
CREATE TABLE exemplars (
  exemplar_id INTEGER PRIMARY KEY, item_id TEXT NOT NULL REFERENCES items,
  episode_id TEXT NOT NULL REFERENCES episodes, frame_id TEXT NOT NULL REFERENCES keyframes,
  bbox TEXT NOT NULL, crop_px INTEGER NOT NULL,                   -- crop size bucket for calibration (ARCH 7(d)(iv))
  mask_path TEXT NOT NULL, crop_path TEXT NOT NULL,
  embedding BLOB NOT NULL, token_set BLOB, token_recipe_id TEXT NOT NULL,   -- one recipe shared with the idle index (section E)
  siglip_embedding BLOB, category_scores TEXT, container_score REAL, ocr_text TEXT, ocr_fields TEXT,
  tier TEXT NOT NULL CHECK (tier IN ('trusted','provisional')),
  created_at REAL NOT NULL, retired_at REAL, retired_reason TEXT,
  consent_version TEXT NOT NULL) STRICT;
CREATE TABLE lookalike_links (item_a TEXT NOT NULL, item_b TEXT NOT NULL, similarity REAL NOT NULL,
  created_at REAL NOT NULL, dissolved_at REAL, reason TEXT, PRIMARY KEY (item_a, item_b)) STRICT;
CREATE TABLE containment_links (
  link_id INTEGER PRIMARY KEY, inner_item_id TEXT NOT NULL REFERENCES items, outer_item_id TEXT NOT NULL REFERENCES items,
  t_in REAL NOT NULL, t_out REAL, confidence REAL NOT NULL, source TEXT NOT NULL,
  hyp_id INTEGER NOT NULL REFERENCES hypotheses, CHECK (inner_item_id <> outer_item_id)) STRICT;
CREATE TABLE calibrations (calibration_id TEXT PRIMARY KEY, embedding_model TEXT NOT NULL, token_recipe_id TEXT NOT NULL,
  crop_bucket TEXT NOT NULL, alpha REAL NOT NULL, q_hat REAL NOT NULL, n INTEGER NOT NULL, source TEXT NOT NULL, created_at REAL NOT NULL) STRICT;
CREATE TABLE index_jobs (item_id TEXT PRIMARY KEY REFERENCES items, created_at REAL NOT NULL,
  started_at REAL, done_at REAL, attempts INTEGER NOT NULL DEFAULT 0, error TEXT) STRICT;
CREATE TABLE exports (export_id TEXT PRIMARY KEY, created_at REAL NOT NULL, purpose TEXT NOT NULL,
  sample_ref TEXT NOT NULL, consent_version TEXT NOT NULL, deidentified INTEGER NOT NULL CHECK (deidentified = 1),
  manifest_path TEXT NOT NULL) STRICT;

-- Layer 3: derived (rebuildable); recomputed for an item at the end of every transaction that touched it
CREATE TABLE item_current (
  item_id TEXT PRIMARY KEY REFERENCES items,
  relevance TEXT NOT NULL, retention_until REAL,
  identity_status TEXT NOT NULL, location_status TEXT NOT NULL, stale_reason TEXT, covis_unchecked INTEGER NOT NULL DEFAULT 0,
  last_reliable_episode TEXT, last_reliable_frame TEXT, last_reliable_bbox TEXT, last_reliable_t REAL,
  last_event_t REAL, last_event_kind TEXT, container_item_id TEXT, room TEXT,
  category TEXT, is_container INTEGER NOT NULL DEFAULT 0, is_medication INTEGER NOT NULL DEFAULT 0,
  group_key TEXT,                              -- connected component of lookalike_links, or null
  index_pending INTEGER NOT NULL, computed_at REAL NOT NULL, ledger_version INTEGER NOT NULL) STRICT;
```

Payload shapes (JSON, validated by pydantic with `extra="forbid"` as `Candidate` already is): `location {status: placed|sighted|inferred|reported, frame_id, bbox, room, container_item_id}`; `identity {status: matched_trusted|matched_provisional|new|ambiguous, set: [item_id...], top1_sim, set_size, calibration_id, covis_unchecked}`; `actor {actor, basis: geometry|appearance|calibration}`; `relevance {tier, signal: handled_days|label|named}`; `region {frame_id, bbox, mask_path, region_source, region_confidence, rival_of: hyp_id, localization_revision}`; `category {scores: {label: p}, container_score, source: siglip2_zeroshot|user_name}`.

Immutability is enforced in SQL, not by convention: `CREATE TRIGGER no_update_episodes BEFORE UPDATE ON episodes BEGIN SELECT RAISE(ABORT,'immutable'); END;` and the same for `keyframes`, `idle_keyframes`, `localizations`, `hypotheses`, `reports`; the only permitted mutations are `exemplars.retired_at` once, `idle_keyframes.promoted_item_id` once, and `episodes.landmarks_reduced_path` once (set by the reduction job). Retention never updates a row: the job deletes the file, inserts a `media_retention` row, and readers treat a path with a `media_retention` row as absent (ARCH 7(e); COMMERCIAL reaction 4 resolved without nullable paths). Cycle prevention for containment: inside the write transaction, walk `outer_item_id` through active links (`t_out IS NULL`) up to depth 8; if the walk reaches `inner_item_id` or exceeds the depth, abort with the reason recorded in `decisions`. Done in Python inside `BEGIN IMMEDIATE`, where it is testable; a recursive-CTE trigger can be added later as a second guard [B].

### Retention rule (ARCH BL-11, COMMERCIAL §4.4 and §4.6, PERCEPTION's 72 h)

`retention_until` is computed at insert from `retention_policy(consent_version, data_class)`; a nightly job deletes files past it and writes `media_retention`. Initial policy for pilot households (`consent_version = pilot-1`), all values `[B]` as proposals that counsel confirms:

| data_class | What | TTL |
| --- | --- | --- |
| `raw_landmarks` (in `packet_path`) | 21-point hands for every analysed frame, including aides' | `max(localization done for the latest revision, revision_window_until)` = 72 h initial (PERCEPTION); then the reduction job writes `landmarks_reduced_path` (`hand_bbox`, `handedness`, per-frame `hand_present`, `release_point`, entry-edge flags, the wearer hand-size scalar) and the raw file is deleted. No per-person template is ever derived; `other_person` and `unknown` are the only non-wearer outputs. |
| `packet` (the rest: imu, gaps, quality, burst) | Needed for replay and the week-4 decision | 30 days, then the burst is deleted and the scalar fields stay in the row |
| `keyframe_evidence` | Keyframes referenced by an exemplar or a reliable sighting | While the item is durable or until offboarding, whichever first (COMMERCIAL §4.6) |
| `keyframe_no_evidence` | Keyframes of context-only episodes and unreferenced roles | 30 days |
| `idle_keyframe` | The re-observation cache | 24 h (L130); promoted frames move to `keyframe_evidence` |
| `audio_clip` | Push-to-talk audio (wearer) | 30 days for STT-error audit; the transcript stays in `reports.raw_text` |
| `caregiver_media` | Caregiver voice note or photo | 30 days for audio; photos while the report is the head location hypothesis, then 30 days |

The team's own footage in weeks 1 to 4 carries `consent_version = dev-internal-1` with `raw_landmarks` TTL `NULL` (manual), which is ARCH's development-phase exemption written as policy rather than code, and those rows are never exportable (`exports` requires a pilot consent version with the global-training flag). A late `episode_revisions` row arriving after `revision_window_until` is stored as `conflict` and not re-localized, because the raw landmarks are gone; its keyframes are still stored.

What the correction loop may keep: the transcript, the parsed meaning, the linked hypothesis and the `report_id` (indefinitely, as the ledger); audio for 30 days; nothing with landmarks; caregiver identity until withdrawal, after which `source` bumps to `caregiver:withdrawn` on a new hypothesis version and the `reports.source` row is retained only as its hash. Training export: audited samples only, from households whose `consent_version` carries the separate global-training consent, de-identified (no caregiver identity, no audio, no landmarks), one `exports` row per sample with the consent version in the manifest (COMMERCIAL §4.6).

### Operations (each is one transaction, each appends, none rewrites)

- `ingest(packet)`: idempotency (below); insert `episodes`, `keyframes`; compute `retention_until` and `revision_window_until`; enqueue localization.
- `localize(episode, revision)`: the localizer's output row in `localizations` (geometry only: `target_regions[]`, masks, `release_point`, `container_region` geometry); then `identify(episode, revision)`.
- `identify(episode, revision)`: for each region, the section C conformal decision; writes `region`, `identity`, `location`, `actor`, `relevance` hypotheses per item; resolves rival regions (two singleton matches to different items split the episode into two object events; both matching one item keeps the region nearest `release_point`; an ambiguous crop writes nothing to the bank); fills `container_region.item_id` by matching the container geometry's crop against the bank and checks `is_container` on `item_current`; creates `containment_links` when the section "Answers to ARCH 5" conditions hold.
- `assert_hypothesis(item, kind, payload, source, t_observed)`: `version = max+1`, `supersedes = previous head`; then `recompute(item)`.
- `merge(a, b, source)`: sets `items.merged_into = a` on b, appends `identity` v+1 on a listing b's exemplars as adopted, moves b's exemplars to tier `provisional` under a (new rows; b's rows retired with reason `merged`); queries resolve aliases through `merged_into`. Reversible by `split`. One tap in the review UI, because the fragmentation rate on day one is a reported risk (ARCH 7(d)(ii)).
- `split(a, t_split, source)`: creates item c; every exemplar and hypothesis of a with `t_observed >= t_split` gets a new copy under c; a's copies are superseded by a `retracted` version. The originals stay.
- `correct(report)`: parses the meaning the spec lists (L87: identity constraint, current location, past location, usual home, mistaken recollection) into one of `assert_hypothesis` (location, source `correction`), `merge`, `split`, or `name`; the report row is the observation; the hypothesis links to it. Scoring stays chronological because `t_observed` is the claimed time and `created_at` is when we learned it (L212).
- `withdraw_caregiver(id)`: for every hypothesis whose head has `source = caregiver:<id>`, a new version with `source = caregiver:withdrawn` and the same payload; `reports` rows keep only a hash of `source`; media deleted via `media_retention`.
- `recompute(item)`: the single derivation function (reliable sighting, shape inputs, stale reasons, containment inference, group key, index_pending, `covis_unchecked`). `rebuild_all()` truncates `item_current` and replays; it is the test for "the derived view is a pure function of layers 1 and 2" and the migration path for `user_version` bumps (ARCH: accepted).

### Idempotency rule (the exact answer to ARCH question 4; accepted by ARCH 7(e))

1. The phone mints `episode_id = base32(sha256(device_id | session_id | round(t_start_mono * 1000)))[:26]`, where `session_id` is a V4 UUID minted per page load and kept in `sessionStorage` and `device_id` persists in `localStorage` (ARCH: accepted, [B] on Safari persistence for home-screen apps). The id is deterministic within a session, so an IndexedDB replay carries the same id; a reload changes `session_id`, so a new episode after reload can never collide with one before it.
2. The IndexedDB mirror stores the serialized packet bytes, not the inputs; a replay is therefore byte-identical by construction. The phone deletes a mirrored packet only on the server's ack `{episode_id, status, revision}`; acks are idempotent (re-sending the same packet after an ack returns the same ack).
3. The server computes `packet_digest` over canonical JSON with each JPEG replaced by its sha256 (so the digest does not depend on JSON key order or on how many keyframes were re-read from disk).
4. Same id, same digest: no-op; ack `status = duplicate` with the stored row. (Stripe's replay rule [V: https://docs.stripe.com/api/idempotent_requests].)
5. Same id, different digest: never an error back to the phone, which cannot repair it and would retry forever, and never a silent overwrite. Store the new bytes as `episode_revisions(revision = n+1)`. The relation is computed by the server from the stored bytes, never from a phone claim (ARCH's condition): if the new packet is a strict superset (same `t_start`, `t_end`, `session_id`, `anchor`; keyframe set ⊇ and landmark list is a prefix-extension) and arrives before `revision_window_until`, `relation = superset`, ack `status = revised`, and the localizer re-runs on the union into `localizations(revision = n+1)`, appending new hypothesis versions (nothing earlier is touched). Otherwise `relation = conflict`, ack `status = conflict`, the first revision stays canonical, and the conflict is surfaced in the review list. This departs from Stripe's "error on mismatch" [V: https://docs.stripe.com/api/idempotent_requests] and from ARCH's round-1 2.1 deliberately, and ARCH has accepted it: on a lossy link the correct behavior is record-and-flag.
6. Keys are never pruned: `episodes` is the ledger. (Stripe prunes after 24 h because keys are not its data [V]; ours are.) Files under the rows are pruned by retention; the rows and digests stay.
7. The same rule, one level down, applies to `reports` (`report_id` minted on the client) and to `idle_keyframes` (`frame_id = device | session | t`).

---

## C. Identity continuity and lookalike groups

### The two banks

- `provisional`: every exemplar starts here. Written only when the identity decision for its episode was unambiguous (set size 0 → new item; set size 1 → match). Capacity 4 per item, oldest retired first.
- `trusted`: promoted when any of: (a) the item was matched as a singleton on at least 3 episodes spanning at least 2 days and the candidate exemplar, held out, is itself a singleton match against the rest of the bank; (b) a user named or confirmed the item (`name` hypothesis from a report); (c) an OCR identifier (Rx number and fill date, L83) was read on this exemplar and on a trusted one. Capacity 8 per item, farthest-point selected in embedding space so the bank covers viewpoints; retired exemplars stay on disk with `retired_reason` until retention removes the file.
- Never written: any exemplar from an episode whose identity set had ≥ 2 members (rule 7), any exemplar whose crop fails the quality gate (sharpness, region ≥ 400 px² at analysis resolution per L175), any exemplar from a `region_source = none` episode, any exemplar whose `hand_bbox_interpolated` flag covered the release frame (PERCEPTION: an interpolated hull is never treated as observed).
- Two regions visible in one frame are never one item (rule 7): before accepting a match to item X at frame F, the resolver registers X's last rest frame to F (the existing `ego_homography`); if the fit succeeds and X's box is still occupied by a region matching X, the match is refused, a new provisional item is created, and a `lookalike_links` row is written. If the fit fails (expected often on a wheelchair, `CLAUDE.md` L185-L190, ARCH and PERCEPTION's condition), there is no refusal: the match proceeds with `covis_unchecked = true` logged on the identity hypothesis and on `item_current`, and for an item with `is_medication = 1` the shape is capped at `hedged` until a later episode passes the check. The homography is budgeted inside the 2 s query timeout (ARCH 7(d)(iii)).

Matching vector: foreground-masked mean-patch DINOv2 under the shared token recipe of section E, with the mask from the region's own source (PERCEPTION A1: the structure-difference component for `pre_rest_diff`, the co-moving set minus the hull for `carry_flow`, the SAM mask for `proposer`; GrabCut only for a bare bbox). CUTE: patch-level foreground pooling beats the class token; in the wild 61.8% top-1 on paired lookalikes even at ViT-B/336 [V: https://arxiv.org/pdf/2311.00750]. Score against an item = max over its trusted exemplars, else max over provisional ones with a flag.

### The decision rule: a conformal prediction set, not a margin

Split conformal in four steps: a score function with larger scores meaning worse agreement, q̂ = the ⌈(n+1)(1−α)⌉/n quantile of the n calibration scores, and the set C(x) = {y : s(x, y) ≤ q̂}; under exchangeability 1−α ≤ P(Y ∈ C) ≤ 1−α + 1/(n+1), with "n ≈ 500 fresh data points" sufficing in practice [V: https://arxiv.org/html/2107.07511v6]. Applied to retrieval, the nonconformity score is the negated similarity and the set is "every candidate above the quantile"; the known failure is oversized sets, which a rank-aware monotone rescaling shrinks (FEVER at α = 0.1: 4.81 → 1.18 documents at ~87% coverage) [V: https://arxiv.org/pdf/2410.02914]. The set size is exactly the signal we need: in composed image retrieval, "small sets are committed directly; large sets trigger an expected-information-gain clarification policy", and one clarifying question lifted success from 58.4% to 74.2% on CIRR [V: https://arxiv.org/pdf/2605.24634].

For PAM:

- `s(crop, item) = 1 − max_cos(crop, trusted exemplars of item)`; calibration pairs (crop, true item) from CUTE's same-instance views (CC BY 4.0 [V: https://arxiv.org/pdf/2311.00750]) in week 1 and then the rig's own 10-item set in week 2 and the pilot's audited corrections; a separate q̂ per `embedding_model`, `token_recipe_id` and crop-size bucket (`exemplars.crop_px`), stored in `calibrations` with a `calibration_id` that every identity hypothesis records.
- `C = {items : s ≤ q̂_α}`. |C| = 1: `matched_trusted` if the max was on a trusted exemplar, else `matched_provisional`. |C| = 0: new provisional item (and `unknown` is the answer if asked, rule 12). |C| ≥ 2: `ambiguous`; no bank write; `lookalike_links` among C; the episode's location hypothesis is attached to each member with `confidence /= |C|` and `payload.ambiguous_set = C` so the answer for any member is at best `hedged` ("something that looks like it was moved at 3 pm") or `group`.
- α = 0.05 for all items (the spec's confident-wrong bound, L217). For items with `is_medication = 1` (an OCR drug-name field, a category score for medication, or a user name containing pills/medication), α = 0.01, and a `confident` shape additionally requires an OCR identifier match or user naming on the matched exemplar; otherwise the medication answer is `hedged` or `group` by construction. This is a mechanism for L219 ("zero in the pilot"), not a hope.
- What the guarantee says and does not say: if the true item is in the bank, P(true ∉ C) ≤ α, so a wrong singleton (the confident-wrong event) has probability ≤ α on in-bank queries, marginally over the calibration distribution [B, follows from the theorem]. It says nothing about an item that was never indexed (out-of-bank), which is why `index_pending` (L187), the two-regions rule and the quality gates exist; and on a tiny day-one bank, empty sets create duplicate items, which is the L120 fragmentation: the empty-set rate on in-bank queries and the duplicate-item count per day are reported in section H and `merge` is one tap (ARCH 7(d)(ii)). Calibration on CUTE is not the rig's distribution: the number is re-estimated on rig crops in week 2 and checked per home; the report states the calibration set and the empirical coverage, not just α.

### "Reliable sighting", restated (replaces the L189 sentence)

An observation of item X is a reliable sighting when all hold: (1) its identity hypothesis head has `set_size = 1` at the item's α (trusted or provisional); (2) `location.status ∈ {placed, sighted}`; (3) the crop passed the quality gate; (4) no co-visibility contradiction (above; `covis_unchecked` is allowed except for medication at `confident`); (5) it is X's most recent `location` hypothesis by `t_observed`. The "margin ≥ 0.15" initial value survives only as the interim until the first calibration set exists; it is logged as `calibration_id = margin_0.15_initial` so that pilot answers made under it are identifiable (ARCH 7(d)(i)).

### Groups

A group is the connected component of `lookalike_links` containing the queried item, computed in `recompute()` and stored as `group_key`; it is a view over items (rule 11), never a row. A group answer lists each member's own latest reliable sighting (photo, time, status, room), members ordered by recency, at most three spoken (ARCH 7(c)); more than three becomes `clarify` ("which one?") or `abstain`. It dissolves when an identifier splits it (OCR Rx number read on both members; a user naming; a `split`/`merge` correction). Members keep separate exemplars, crops, masks and OCR fields so that a later OCR read can split retroactively (PERCEPTION question 4: yes).

The literature precedent for "one of N identical instances" is the set-valued answer itself: conformal prediction sets [V: https://arxiv.org/html/2107.07511v6], and the retrieval practice of committing small sets and clarifying large ones [V: https://arxiv.org/pdf/2605.24634]. Re-identification benchmarks avoid the case (EgoObjects excluded indistinguishable categories [V: https://arxiv.org/pdf/2309.08816]) or treat identical SKUs as one class, which is exactly what rule 11 forbids. So there is no off-the-shelf "group" answer to copy; the shape in "Answers to ARCH 1" is ours.

---

## D. Query resolution

### Paths and evidence

- Text-to-crop (SigLIP 2): the model card lists "zero-shot image classification and image-text retrieval" as intended uses, Apache-2.0 [V: https://huggingface.co/google/siglip2-base-patch16-256]. There is no published number for a phrase like "my pills" against 224 px crops of same-category distractors. The nearest evidence is that CLIP-class features are the weakest at instance level even with a visual exemplar (PerMIR: CLIP 20.9 mAP, DINOv2 29.7 [V: https://arxiv.org/pdf/2405.18025]), and in the language-query video benchmark the best system is at R@1 28% [V: https://arxiv.org/html/2406.15778v2]. So text cannot be the instance picker; it can pick the category and sometimes an attribute.
- Text-to-category then continuity: the ledger carries, per item, `category_scores` and `container_score` from SigLIP 2 zero-shot at indexing (PERCEPTION A3: text embeddings of the household and container vocabularies computed once at startup; one image forward per new candidate, which L120 already schedules; stored as soft scores, treated as a prior, user naming overrides), user-given names, and OCR text; the existing `_category` alias table (`object_memory.py` L184-L190) is the seed. The instance is then whatever the ledger says it is; DINOv2 continuity has already been resolved at write time, so the "continuity" step at query time is a lookup, not a model call.
- LLM over a textual ledger: this is what ReMEmbR and EgoLife do, and their numbers (0.58 to 0.65 with GPT-4o; 39.2% EntityLog with a 7B model [V: https://arxiv.org/html/2409.13682v1; https://arxiv.org/html/2503.03803v3]) are for free-form questions over captions. Our ledger is a few dozen rows with names, categories, OCR fields, times and rooms; a 1.5B local model can pick a row or say "ask" from that. Qwen2.5-1.5B-Instruct is Apache-2.0, 32k context [V: https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct]; COMMERCIAL: pin the 1.5B (its 3B and 72B siblings carry different licences) [V-peer: final/COMMERCIAL.md §1]. Cloud LLM: Anthropic's retention page states retained data is never used for training without permission, ZDR on request, and PHI only with a signed BAA and a HIPAA-enabled organisation; no PHI in JSON schema definitions [V-peer: https://platform.claude.com/docs/en/manage-claude/api-and-data-retention].

### The rule (primary)

1. Normalize the STT text; strip "where is/are/did I leave my". Lexical match against item names, aliases, categories and OCR text (drug names count as categories, L83) → candidate set S.
2. If S is empty: SigLIP 2 text embedding of the phrase vs the `siglip_embedding` of each item's best crop; keep items inside a conformal set at α = 0.1 calibrated on the rig's own (phrase, item) pairs; if still empty, `abstain` with "I don't have anything I'd call that; if you show it to me once I'll remember it" (rule 2 permits a candidate seen once).
3. If |S| ≥ 2 and the phrase carries an attribute ("blue", "little", "silver"): rerank S by SigLIP 2 text-to-crop on the attribute phrase; keep members within the conformal set.
4. If |S| ≥ 2 and the members share a `group_key`: `group` shape (section C).
5. If |S| ∈ {2, 3}, not a group: one clarifying question built from the ledger field that best separates the members, in this order: user name ("the Lipitor or the Metformin?"), OCR identifier ("the one filled in March?"), last-seen room/time ("the one you had in the kitchen this morning, or the one from the bathroom?"), colour from a crop histogram ("the blue one or the white one?"). One question, then answer or `hedged` for the best member. (The CIR evidence: one question is where most of the gain is, 58.4 → 74.2% [V: https://arxiv.org/pdf/2605.24634].) The phone page supports a second push-to-talk round for the answer (ARCH 2.5).
6. If |S| > 3: ask for a name ("I know a few of those; which one?"), else `abstain`.
7. Time/place phrasings ("the thing I had in the kitchen"): a slot parser for time words (this morning / yesterday / before lunch) and room words (only when `room` has a source, L74) filters S first; if the parser finds no item word at all ("the thing"), S = items with a `location` hypothesis inside the time window, ranked by recency, and step 5 applies.
8. Local LLM fallback (Qwen2.5-1.5B-Instruct on the laptop, CPU), weeks 5-6 and only if the week-3 clarify arm shows a residue (ARCH: deferred, not rejected): input is the compact textual ledger (≤ 50 rows: id, name, category, OCR fields, last_t, room, relevance) and the phrase; output is an item id or `ask`. Cloud LLM (L201 budget, 5 calls/day; `deployment_profile`-gated; BAA before any agency use) only when the local model says `ask` and the user has already answered one question.

Expected top-1 for elderly phrasings: no defensible number exists for this vocabulary. What can be said: on the lexical path, top-1 is bounded by category multiplicity in the home, which is why steps 4 and 5 exist; the end-to-end success target (0.70, L216) is reached by clarifying and grouping, not by raw top-1. ARCH's R6 experiment (50 crops, 20 phrasings each, text→crop vs text→category→ledger) is the measurement, with the clarifying-question arm added (success after one question) because that is the number the product runs on.

### Cost

Everything in steps 1 to 7 is a lookup or one SigLIP 2 text forward pass (tens of milliseconds on a laptop CPU [B]). Step 8 is a 1.5B-parameter generation of ~20 tokens, a few seconds on CPU [B], run only on the residue. Cloud stays at the L201 line ($0.68 per user-month at 5 calls/day by COMMERCIAL's arithmetic [V-peer: final/COMMERCIAL.md §6]).

---

## E. Re-observation of tracked items against idle keyframes (rule 13)

### Why patch matching on whole 256 px frames is not enough

Geometry [B, arithmetic]: a 26 mm-equivalent rear camera has about 69° horizontal field of view; at 518 px frame width the focal length is ≈ 377 px; a 5 cm wide, 12 cm tall pill bottle at 2 m projects to ≈ 9 × 23 px, at 1 m to ≈ 19 × 45 px. DINOv2/14 patches are 14 px, so at 518 px the bottle is one patch wide at 2 m and 1.3 patches at 1 m; at 256 px it is sub-patch at any realistic distance. Patch matching needs at least a 2 × 2 patch footprint to be a vote rather than noise [B], i.e. ≥ 28 px of object at the index resolution, which at 518 px is a 12 cm object within about 1.2 m. RELOCATE's evidence points the same way: frame-level retrieval is where DINOv2 is strong, spatial precision is where mask pooling and a crop-and-refine step are needed (refinement ablation 0.333 → 0.246 stAP25) [V: https://arxiv.org/pdf/2412.01826]; PerSAM shows that a location-confidence map from "foreground features from the reference mask, cosine similarity with test image features" plus the highest/lowest-confidence points as positive/negative prompts to a SAM-class decoder segments the same object in a new image (PerSeg 89.3 mIoU training-free; DAVIS 2017 76.1 J&F) [V: https://ar5iv.labs.arxiv.org/html/2305.03048]. The PerSAM repository has no LICENSE file [V: https://raw.githubusercontent.com/ZrrSkywalker/Personalize-SAM/main/LICENSE returns 404; README has no license line], so the method is reimplemented from the paper on top of RepViT-SAM (Apache-2.0 [V: https://raw.githubusercontent.com/THU-MIG/RepViT/main/LICENSE]; COMMERCIAL A4: no obligation from the unlicensed repo, cite the paper). DINOv2 itself: "DINOv2 code and model weights are released under the Apache License 2.0" [V: https://raw.githubusercontent.com/facebookresearch/dinov2/main/README.md L660; LICENSE file Apache-2.0 at https://raw.githubusercontent.com/facebookresearch/dinov2/main/LICENSE]; the same README's "FAIR Noncommercial Research License" line (L159-L160) applies only to the separately downloaded XRay-DINO checkpoint, which we do not use [V: same README L142-L160]; pin `dinov2_vits14` by name and hash (COMMERCIAL A2 to ARCH).

### The shared masked-token recipe (PERCEPTION's condition; one `token_recipe_id` for the bank, the index and the refiner)

- Backbone: `dinov2_vits14` pinned by hash; last-layer patch tokens, no CLS, L2-normalized.
- Exemplar vector (bank): the identity crop cut at native resolution from the 720p keyframe, padded square, resized to 224 px (336 px is the first escalation if the week-1 CUTE bar fails, PERCEPTION D); the region mask (from the region's own source) downsampled to the 16 × 16 patch grid by area ≥ 0.5; `embedding` = mean of masked tokens, L2-normalized; `token_set` = k-means of the masked tokens to ≤ 64 centroids. This is CUTE's "patch-level foreground pooling" [V: https://arxiv.org/pdf/2311.00750].
- Idle index: the whole frame at 518 px long side (37 × 21 patches on 16:9, 777 tokens); `global_vec` = mean token (384 × fp16); `patch_index` = 2 × 2 average-pooled grid (19 × 11 = 209 tokens), projected by a PCA-64 fitted on CUTE plus rig tokens and stored with the recipe, fp16: ≈ 27 KB per frame, ≈ 77 MB per 24 h [B].
- Frame score: exemplar `token_set` projected through the same PCA; score = mean over exemplar tokens of the max cosine over the frame's 209 tokens (the RELOCATE/PerSAM form).
- Refinement vector: unpooled, un-projected tokens on the 2.5× crop, pooled inside the SAM mask with the exemplar recipe (resize the masked crop to 224/336), so the conformal test runs in the bank's own vector space with the bank's own `calibration_id`.
- Known mismatch: the bank sees the object at crop scale (many patches), the index at frame scale (few patches); that is why the index is only a shortlist and the refinement re-crops. Freeze the index format only after it keeps ≥ 95% of the unpooled recall@3 on CUTE in-the-wild retrieval; if it does not, keep 2 × 2 pooling and raise PCA to 128 (PERCEPTION A2).
- A recipe change invalidates the bank, the index and the calibrations together: one rebuild job keyed by `token_recipe_id`.

### Design (bounded, two-stage)

Storage: keep the idle keyframe at capture resolution (720p JPEG, roughly 40 to 60 KB [B]); one per 30 s is 2,880 frames and ≈ 150 MB per 24 h, dropped on expiry unless promoted (L130); ARCH records ≈ 6 MB/h added rig transport [V-peer: final/ARCH.md 7(f)].

At arrival (once per idle frame, off the query path): one DINOv2 ViT-S/14 pass at 518 px long side, storing `global_vec` and `patch_index`. Cost: my estimate 100 to 250 ms on a laptop CPU [B]; PERCEPTION's arithmetic (777 vs 256 tokens, 20 to 28 GFLOPs) gives 60 to 200 ms [V-peer: final/PERCEPTION.md Answers to MEMORY 2, B]; once per 30 s either way, negligible; a week-2 measurement (ARCH R7).

At query for item X (rule 13, "most recent first, stop at the first confident hit"):

1. Score every frame in the cache with the frame score above. 2,880 × 64 × 209 × 64 MACs ≈ 2.5 GMAC, under a second in NumPy [B]. Walk most recent first; stop when a frame scores above the frame-level conformal threshold and 3 refinements have been spent, or when the 24 h cache is exhausted.
2. Refine at most 3 frames: cut a 2.5× crop around the peak at capture resolution, run DINOv2 at 518 px on the crop (so the object now spans several patches), build the PerSAM-style confidence map, prompt RepViT-SAM at the positive/negative points, pool the mask's tokens with the exemplar recipe, and run the section C conformal test against X's bank. Accept only a singleton. Expect ≤ 3 × (≈ 150 ms + ≈ 300 ms) ≈ 1.5 s worst case on the laptop [B]; hard timeout 2 s (shared with the co-visibility homography of section C), after which the answer proceeds without a re-observation and says nothing about having looked. RepViT-SAM's CPU cost is the same week-1 measurement as the event-path proposer (PERCEPTION).
3. On acceptance: append `location` hypothesis `{status: sighted, frame_id, bbox}` with `source = reobservation`, promote the idle frame (`promoted_item_id`, which moves it to the `keyframe_evidence` retention class), and record the frame's capture time as `last_observed`. Never `placed` (rule 13).

Negative re-observation (feeds BL-8 `stale`): if a later idle frame's `global_vec` matches X's last rest frame's global descriptor above the place threshold (same view of the same surface) and step 1 scores X below the frame threshold at the registered location, append `stale_reason = negative_reobservation` on the next `recompute()`. This is a hedge input, never a confident "it is gone"; PERCEPTION notes a kettle moved on the same counter can defeat the global match [B], which is fine for a hedge input.

What this cannot do, said plainly: small items beyond about 1.2 m from the camera are not re-observable at 518 px; the pilot reports the distance distribution of visible relocations (L220) so the index resolution can be raised (1036 px roughly quadruples the arrival cost) where the data says it matters.

---

## F. Speech stack for the rig and the target

### Costs and terms

- Deepgram, pay as you go, on the live pricing page: Nova-3 pre-recorded monolingual $0.0043/min ($0.0036 Growth); Nova-3 streaming $0.0048/min; Flux English $0.0065/min; Voice Agent $0.075/min; Aura-2 TTS $0.030 per 1,000 characters [V-peer: https://www.deepgram.com/pricing]; the same figures and the $200 free credit on a secondary page dated 24 August 2026 [V, secondary: https://diyai.io/ai-tools/speech-to-text/deepgram-pricing-2026/]. Flux is "conversational speech recognition purpose-built for interactive voice agents" with model-integrated turn detection (`StartOfTurn`, `EagerEndOfTurn`, `TurnResumed`, `EndOfTurn`) and ~260 ms end-of-turn latency; the migration guide describes streaming WebSocket use only [V: https://developers.deepgram.com/docs/flux/nova-3-migration]. A push-to-talk clip has no turn to detect: the right Deepgram line is Nova-3 pre-recorded, $0.0043 × 30 min × 30 days = $3.87 per user-month at the spec's minute count [B, arithmetic], and ≈ $0.39 at a realistic 3 min/day of push-to-talk (COMMERCIAL §6), not the $5.85 at L197. Safari's `audio/mp4` (AAC) is an accepted format, no transcode needed [V-peer: https://developers.deepgram.com/docs/supported-audio-formats]. Data terms: ToS §3.2 grants Deepgram an "irrevocable, perpetual, transferable, sublicensable" licence to use Your Content "including training and testing our Models" unless opted out; §3.3 opt out per request; §3.5(4) no PHI without a BAA [V-peer: https://deepgram.com/legal/terms]; the parameter is `mip_opt_out=true`, after which "Data from opted-out requests is retained only for the duration necessary to process the request" [V-peer: https://developers.deepgram.com/docs/the-deepgram-model-improvement-partnership-program].
- Whisper: code and weights MIT [V: https://raw.githubusercontent.com/openai/whisper/main/LICENSE]; `whisper-large-v3-turbo` model card: MIT, 809M parameters, decoder reduced from 32 to 4 layers "at the expense of a minor quality degradation", mean WER 7.83 on its benchmark set [V: https://huggingface.co/openai/whisper-large-v3-turbo]; the card's advisory cautions (against transcribing individuals recorded without consent; against high-risk decision contexts) are respected by push-to-talk and the abstain-first contract (COMMERCIAL §1). whisper.cpp MIT [V: https://raw.githubusercontent.com/ggml-org/whisper.cpp/master/LICENSE]; faster-whisper MIT [V: https://raw.githubusercontent.com/SYSTRAN/faster-whisper/master/LICENSE]; mlx-whisper MIT [V-peer: https://raw.githubusercontent.com/ml-explore/mlx-examples/main/LICENSE]. The current `voice.py` already runs `mlx-whisper` base.en on a Mac at "0.05 s per question once loaded" [V: code/perception/voice.py L15].
- Platform on-device STT: Apple's SpeechTranscriber (iOS 26 family) is "entirely on device but the models need to be fetched" through AssetInventory, "faster and more flexible than the one previously available through SFSpeechRecognizer", available on all platforms but watchOS [V: https://developer.apple.com/videos/play/wwdc2025/277/]. Android added `createOnDeviceSpeechRecognizer(Context)` and `isOnDeviceRecognitionAvailable(Context)` in API level 31 [V: https://developer.android.com/sdk/api_diff/31/changes/android.speech.SpeechRecognizer]. Both are $0 and offline; neither is reachable from Safari (L143), so they are native-target lines only.
- TTS: `speechSynthesis` on the phone, $0 (L104). Kokoro-82M: Apache-2.0 code and weights, 82M parameters, "trained exclusively on permissive/non-copyrighted audio data", and the card says it "has been deployed in numerous projects and commercial APIs" [V: https://huggingface.co/hexgrad/Kokoro-82M; https://raw.githubusercontent.com/hexgrad/kokoro/main/LICENSE]; its G2P `misaki` is Apache-2.0 but falls back to espeak-ng, GPL-3.0 [V-peer: https://raw.githubusercontent.com/hexgrad/misaki/main/LICENSE; https://raw.githubusercontent.com/espeak-ng/espeak-ng/master/COPYING]. Piper: MIT code [V: https://raw.githubusercontent.com/rhasspy/piper/master/LICENSE.md]; voice files carry their dataset's terms: `en_US-lessac-*` is Blizzard-licensed and research-only per the maintainer thread, LibriTTS-R (CC BY 4.0) and LJSpeech (public domain) voices are commercially safe [V-peer: https://huggingface.co/rhasspy/piper-voices/blob/856d185c267ad13c45e707792c8c6fbf5fac01d9/en/en_US/lessac/medium/MODEL_CARD; V-peer, secondary: https://github.com/rhasspy/piper/discussions/271]; `piper-phonemize` links espeak-ng (GPL-3.0) [V-peer: COPYING above]. Consequence for both: laptop/server use only (no distribution, no GPL obligation); the native target uses platform TTS; a laptop TTS is never shipped on a device with espeak-ng inside.
- Wake word: openWakeWord code Apache-2.0 [V: https://raw.githubusercontent.com/dscripka/openWakeWord/main/LICENSE], but "All of the included pre-trained models are licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International license due to the inclusion of datasets with unknown or restrictive licensing" [V-peer: https://raw.githubusercontent.com/dscripka/openWakeWord/main/README.md L278]. Not in v1: push-to-talk is the spec (L104), and a wake word on a wearer with memory impairment is a recall demand; if ever wanted, the code with a model we train on our own synthetic data.

### Accuracy on older voices

Evidence is thin and mostly not English. Whisper large-v2 zero-shot on JASMIN-CGN native elderly (65+, Dutch) is 28.73% WER, falling to 10.05% after fine-tuning on elderly speech [V: https://arxiv.org/html/2502.17284v1]. A 2025 Berkeley MIDS capstone (Common Voice 50+ and DementiaBank) reports Whisper at 21.5% WER for speakers 60+ and 31.3% under 59 on its test split, improving to 9.9% / 12.3% after fine-tuning [V: https://www.ischool.berkeley.edu/projects/2025/agevoice-evaluating-voice-ai-aging-place]; treat it as indicative only. Two consequences for the design: (1) the query vocabulary is tiny (object names, "where", "my", rooms), so bias the decoder: whisper `initial_prompt` with the ledger's item names and aliases, Deepgram keyterm prompting, Apple custom vocabulary [B as to each API's exact feature]; (2) log STT confidence and the recognized string with every query, and when confidence is low ask "did you say your glasses?" before resolving, because a mis-heard item name produces a confident-wrong answer about the wrong item, which the rubric counts against us. No speaker identification or voiceprint is ever computed from a clip or a voice note (COMMERCIAL §4.4): the push-to-talk tap and the authenticated caregiver session are the attribution.

### Decision

Rig: push-to-talk `MediaRecorder` (audio/mp4 from Safari per ARCH 4.7 [B]) to `/api/stt`; faster-whisper `large-v3-turbo` (int8, CPU) or whisper.cpp with CoreML on a Mac server, offline, $0; latency for a 5 s clip measured on the Windows laptop CPU in week 2, falling to `small.en` with the vocabulary prompt if over 2 s (ARCH 7(g)); Nova-3 pre-recorded as the cloud fallback at $0.0043/min with `mip_opt_out=true` on every request, enabled only under `deployment_profile = family` unless a BAA exists; `speechSynthesis` for replies; Kokoro on the laptop only if the pilot's image-alone test (L81) shows the phone voice is unintelligible to the users. Native: SpeechTranscriber / `createOnDeviceSpeechRecognizer`, with whisper.cpp as the cross-platform offline fallback. Update L197 to the Nova-3 pre-recorded line plus `mip_opt_out=true`, state the minutes-per-day as push-to-talk minutes, and mark Flux as "not applicable to push-to-talk".

---

## G. Caregiver platform patterns

### What exists

Care-management software exposes each log entry with "Carer name and avatar who recorded the log", "Date and time logged", an "Edited status if the log was changed after creation", witness details and up to three images or one video [V: https://support.logmycare.co.uk/en/articles/12044295-carer-app-log-view-explained]. That is the attribution convention: who, when, edited-or-not, evidence attached. Consumer trackers (Find My, Tile) have no "a person reported moving it" state; the closest consumer analogue is a shared note [B].

### Burden evidence

Speech input cut personal-data-capture time from 175.9 s to 115.9 s per entry in one diary and from 86.7 s to 65.5 s in another, with a significant regression effect (b = −.38, p = .004) [V: https://par.nsf.gov/servlets/purl/10394083]. Among 317 elderly mHealth resisters, information overload and feature overload drove fatigue (β = 0.475, 0.462) and technostress (β = 0.517, 0.642), which drove resistance (β = 0.419, 0.673) [V: https://pmc.ncbi.nlm.nih.gov/articles/PMC7560067]. The 2018 systematic review of ICT for dementia caregivers found individual-level, person-delivered interventions most effective and did not study data-entry burden at all [V: https://pmc.ncbi.nlm.nih.gov/articles/PMC6315277/]. So: no form, one tap, speech optional, and the system fills who/when.

### Design

- The caregiver page lists the wearer's durable items as cards (photo, name). A report is: tap the card, then either say one line ("I put them in the kitchen drawer") or take a photo, or tap a room chip. The server stores a `reports` row (who = authenticated caregiver id, `t_received`, `t_claimed` = now unless the line says "this morning", `consent_version`, `retention_until` for the media), then `assert_hypothesis(item, location, {status: reported, room, media_path}, source = caregiver:<id>, confidence = 0.8 policy)`.
- `location_status` gains the value `reported` (L189 enum; ARCH 2.5 adopted). Shape: a reported head is `hedged` by rule, spoken with attribution: "Your daughter says she moved your pills to the kitchen drawer at 3 pm. I haven't seen them there myself." If a photo was attached it is shown labeled as hers (`reference_image.source = caregiver`), never as a camera sighting (rule 12 forbids a photo without a reliable sighting; a labeled caregiver photo is not a sighting claim). This is also what keeps the feature inside the general-wellness position: no inference about the wearer's condition (COMMERCIAL reaction 5).
- Conflict rule, by observation time (never arrival, L148): a camera reliable sighting with `t_observed` after the report's `t_claimed` supersedes it (`confident` if reliable); a report after a camera sighting supersedes the sighting as the head and makes the shape `hedged` with both facts ("I saw it on the counter at 2 pm; your daughter says she moved it to the drawer at 3 pm"); a later idle frame that shows the reported place empty (negative re-observation) does not retract the report, it adds `stale_reason` and the speech says "I haven't seen it there since".
- Attribution stays in the answer because corrections are evidence with a source (L87); the report row is the observation, the hypothesis links to it, and the review UI shows the Log-my-Care fields: who, when, edited (never: a report is superseded by a new report, not edited), media.
- Consent (COMMERCIAL A3, §4.5): the caregiver is a participant, not a bystander. Pilot: an IRB-approved secondary-participant consent covering their identity, reports, voice notes and photos, storage on the laptop, any transmission to Deepgram or the LLM, retention, the fact that their words are repeated to the wearer by name, and withdrawal. Product: terms of use and a privacy notice for the caregiver account with the same elements. Withdrawal is `withdraw_caregiver(id)` (section B): a `source` version bump to `caregiver:withdrawn`, media deleted, no rewrite. The wearer's consent says caregiver reports are repeated to them by name, so a caregiver who reports a hidden item (medication locked away) understands the wearer will be told.
- Voice notes are one-party recordings consented by pressing the button and are treated exactly like wearer push-to-talk clips: transcribed, audio kept ≤ 30 days (`caregiver_media` class), never ambient; the bystander plan covers whoever is audible behind the note.
- Proactive prompt (fallback, opt-in, weeks 5-6 per ARCH): when an episode has `actor = other_person` on a durable item and the location head is `uncertain` or `ambiguous`, push one question to the caregiver with the rest-frame photo: "Did you move Mom's pills? Tap where." One tap closes it. Sending the rest-frame photo to the caregiver's phone is a disclosure of camera imagery to a third party and is in both consents (COMMERCIAL). This converts the product's central case (L57) from "unknown" to "reported" at the cost of one tap, and the pilot can measure response rate.

---

## H. Evaluation

### How MemPal ran its protocol

N = 15 older adults aged 62 to 96 (normal cognition, SCD and MCI), in their own homes, neck-worn iPhone and bone-conduction headset; within-subjects with three conditions (baseline, MemPal audio, visual on a laptop); participants "placed 20 common household objects around their homes, waited 40 minutes, then attempted retrieval under each condition with a 3-minute limit per object". Results: audio description accuracy 72%, visual 53%; retrieval success 97% vs 81% baseline when the assistance was accurate (p = .015); rooms searched 1.1 vs 1.9; mean response time 2.17 s; SUS 69.4; errors were object misidentification 24% and incorrect location 22% [V: https://www.alphaxiv.org/overview/2502.01801]. Venue IUI '25; the record is CC BY-NC-SA [V: https://dspace.mit.edu/handle/1721.1/159037]; copying the study design is not copying the paper (COMMERCIAL reaction 8). The thing to copy is the design (own homes, scripted placements, timed retrieval, within-subjects); the thing not to copy is reporting success conditioned on accurate assistance as the headline, which L36 already notes.

### PAM protocol (per household, one session)

20 placements as MemPal, of which: 5 are caregiver relocations in camera view (L221), 3 are relocations out of view (L222), 2 are an identical pair (case 4), 2 go into a container that later moves (case 5), 2 are new items first handled that day (case 1), 3 are fast put-downs (case 3); the rest ordinary. Wait 40 min. Ask every item in two phrasings (a category phrase and an attribute/time phrase), 3-minute retrieval limit, experimenter logs the item's true current location at the moment of each query. Run the whole chain twice on the recording (hand-verified crops, automatic crops; L242). The household's `consent_version` and `deployment_profile` are recorded on the session.

### Scoring sheet (one row per query; CSV header)

```
home_id, session_id, participant_id, consent_version, query_id, t_query, item_id_true, item_class, is_medication,
phrasing_type (category|attribute|time_place|name), stt_text, stt_confidence, stt_engine,
case_tag (plain|caregiver_in_view|caregiver_out_of_view|lookalike_pair|container|new_item|fast_putdown),
move_visible_to_camera (y|n|na), coverage_loss_during_move (y|n), index_pending_at_query (y|n),
landmark_fps_at_move, hand_bbox_interpolated_at_move (y|n),
shape (confident|hedged|abstain|group), n_members, clarify_asked (y|n), clarify_answered (y|n),
resolved_item_id, identity_status, location_status, stale_reason, conformal_set_size, calibration_id, covis_unchecked (y|n),
reobservation_attempted (y|n), reobservation_hit (y|n), reobservation_ms,
answer_place (room/surface string or photo id), answer_time,
hist_fidelity (1 if the photo/time shows the true item at that time, else 0),
current_useful (1 if following the answer finds the item now, else 0),
outcome (correct|hedged_correct|hedged_wrong|confident_wrong|abstain),
retrieval_time_s, rooms_searched, correction_given (y|n), correction_meaning, notes
```

Outcome assignment, deterministic from the row: `abstain` if shape = abstain; else if shape = confident: `correct` if current_useful = 1 else `confident_wrong`; else (hedged or group): `hedged_correct` if current_useful = 1 (for group: if the member the user went to was right) else `hedged_wrong`. `hist_fidelity` is recorded on every answered row but never changes the outcome: a true old photo of the counter when the item is in the drawer scores `confident_wrong` or `hedged_wrong` (L212). A clarifying question counts as part of the same query; `clarify_answered = n` with no answer is `abstain`.

Aggregates: accuracy among answered = (correct + hedged_correct) / (answered); coverage = answered / all; confident-wrong rate = confident_wrong / all, with the one-sided 95% Clopper–Pearson upper bound (0 of 150 gives ≈ 2.0%, the spec's L230 figure) [B, standard binomial math]; medication confident-wrong on `is_medication = 1` rows only; caregiver-relocation success on `case_tag = caregiver_in_view` rows (pass at ≥ 0.70, L221); out-of-view rows report the share with `stale_reason` set and no confident shape; per-home figures reported separately because rows in one home are correlated (L230); corrections scored chronologically: a row's outcome is fixed at `t_query` and a later correction only affects later rows (L212). Also report: mean conformal set size, clarify rate, the conformal empirical coverage on rows where the true item was in the bank (the check that α means what section C says), the empty-set rate on in-bank identity decisions and the duplicate-item count per day (fragmentation, ARCH 7(d)(ii)), the `covis_unchecked` rate, and outcomes split by `landmark_fps_at_move` buckets so a slow Worker is distinguishable from a memory-logic failure (BL-10).

---

## Answers to ARCH

1. **Group shape.** Add a fourth shape, `group`; do not map to `hedged`. Answer fields become `members[]` (0 for abstain, 1 for confident/hedged, 2 to N for group), each `{item_id, reference_image {frame_id, bbox} | null, target_indicated, capture_time, identity_status, location_status, stale_reason, room, relevance}`, plus top-level `shape`, `index_pending`, `clarify {question, options[]} | null`. Members ordered by recency; at most three spoken, more becomes `clarify` or `abstain` (ARCH's condition, accepted). Speech: "I have two that look the same. One was here at 2 pm (photo 1). One was here at 4 pm (photo 2)." Rule 7 still forbids merging rows; the group is the connected component of `lookalike_links`. Precedent is the set-valued answer of conformal prediction and the commit-small-sets/clarify-large-sets practice [V: https://arxiv.org/html/2107.07511v6; https://arxiv.org/pdf/2605.24634], not any object-retrieval benchmark, which avoid the case [V: https://arxiv.org/pdf/2309.08816]. Status after round 2: resolved (ARCH BL-5).
2. **Re-observation matcher.** Not patch matching on a 256 to 512 px frame alone. Section E: index every idle frame at arrival with DINOv2-S at 518 px (pooled patch index, ≈ 27 KB per frame), score the 24 h cache in under a second at query time, refine at most 3 frames with a 2.5× crop plus RepViT-SAM point-prompted at the peak, accept only a conformal singleton in the bank's vector space under one shared token recipe. Idle keyframe stored at capture resolution (720p); the index resolution is 518 px, which bounds re-observation to objects ≥ 28 px at that scale (≈ 12 cm within ≈ 1.2 m) [B]. Change L130 and Part 2 L347 from "low-resolution" to "capture resolution, indexed at 518 px". Status: resolved (ARCH BL-9.4), measurements in week 2 (ARCH R7).
3. **Case 1 query rule.** Text → item set by lexical/category/OCR, instance from the ledger (continuity already resolved at write time), SigLIP 2 text-to-crop only to narrow a set by attribute, one clarifying question at 2 or 3 members, `group` for lookalikes (section D). No published top-1 exists for elderly phrasings on small crops; the instance-level evidence for CLIP-class text features is weak (PerMIR CLIP 20.9 mAP [V: https://arxiv.org/pdf/2405.18025]), so the design must not depend on text picking the instance. R6 gains the one-question arm. The local-LLM residue is deferred to weeks 5-6 (ARCH; accepted). Status: resolved.
4. **Ledger.** Yes: immutable observation and stage-output tables, append-only versioned hypotheses, a materialized `item_current` recomputed per item inside the writing transaction by one Python function that can also rebuild from scratch (section B), with retention by `retention_until` and a `media_retention` side table, `consent_version` on every exportable row, and `rebuild_all()` as the `user_version` migration path. Idempotency: phone-minted deterministic `episode_id` from (device, per-load session, t_start_mono); byte-identical replays from the IndexedDB mirror; digest over canonical JSON with JPEGs replaced by their sha256; same id + same digest = no-op ack; same id + different digest = stored as `episode_revisions` with the superset/conflict relation computed by the server from stored bytes (superset within the 72 h window → localizer re-run and new hypothesis versions; otherwise conflict, first revision canonical, surfaced for review), never an error to the phone, never an overwrite; ack-then-delete on the phone with idempotent acks. Status: resolved (ARCH 7(e), BL-9.5), all five of ARCH's conditions accepted.
5. **Containment.** Automatic containment is beyond v1: the best published tracker through containers reaches 16.0% target IoU on invisible frames and 78.2% container IoU on synthetic data, with a full-video transformer [V: https://ar5iv.labs.arxiv.org/html/2305.03052]. Minimum evidence for a link in v1, all required: (a) the episode's rest frame has no accepted target region (`pre_rest_diff` finds the object left its pre-contact position and no arrival blob), (b) `release_point` lies inside a second region that persists from pre-contact to rest (the localizer's `container_region` geometry, PERCEPTION's restructuring: the localizer fills `{frame_id, bbox, mask, confidence}`, the identity stage fills `item_id` by matching that region against the bank and checks `is_container` from the item's category score or user naming), and (c) that region is present in the rest frame. Then `outcome = placed_in_container`, `containment_links(inner, outer, t_in, confidence = region_confidence × container_match)`. Removal: any later episode on the inner item with an accepted rest region outside the outer item sets `t_out`. `container_region` is in the day-1 freeze as optional-null (ARCH: accepted); v1 scoring of case 5 is on ledger logic with hand-labelled containment events, and the spec should say so; the automatic path is reported, not gated. Status: resolved (ARCH BL-6).
6. **Stale.** All four, each recorded as `stale_reason`: `coverage_loss` (a `gaps[]`, screen-lock or Wi-Fi interval after the last reliable sighting longer than the max unobserved gap), `negative_reobservation` (section E), `age` (initial 12 h), and `other_person_handling` (a later episode on a durable item with `actor = other_person` and no accepted rest region). Any reason makes the shape `hedged` through the L189 rule; none makes it `abstain`, because a reliable sighting still exists; the speech names the reason ("I lost sight of things for twenty minutes after that"). Status: resolved (ARCH BL-8).

### ARCH's round-2 conditions on my items, one line each

| Condition | Position |
| --- | --- |
| 7(c): > 3 members → `clarify`/`abstain`; members by recency; fields into the day-1 freeze | Accept; in sections C and "Answers to ARCH 1" |
| 7(d)(i): margin stays as logged interim `margin_0.15_initial` until the week-2 rig set; `calibration_id` on every pilot answer | Accept; sections C and H |
| 7(d)(ii): report the empty-set (fragmentation) rate; make `merge` by correction cheap | Accept; section H aggregates; one-tap `merge` in section B |
| 7(d)(iii): co-visibility needs a query-time homography inside the 2 s; degrade to no-refusal-logged on failure (also PERCEPTION) | Accept, with one addition: on failure a medication item is capped at `hedged` (`covis_unchecked`); section C |
| 7(d)(iv): calibration per model and crop-quality bucket, so `exemplars` stores crop size | Accept; `exemplars.crop_px`, `calibrations.crop_bucket` |
| 7(e): superset/conflict computed server-side from stored bytes; mirror deleted only on idempotent ack; `media_retention` side table instead of nullable paths; WAL with a startup version check; `/api/answer` reads `item_current` only; `rebuild_all()` as migration | Accept all six; section B |
| 7(f): 2 s timeout and arrival cost measured in week 2; ≈ 6 MB/h added transport recorded; the 1.2 m floor reported against | Accept; section E |
| 7(g): whisper `large-v3-turbo` int8 latency on the Windows CPU in week 2, fall to `small.en` if > 2 s; Deepgram fallback opted-out and `family`-profile-gated | Accept; section F |
| Section 7 last paragraph: local Qwen residue deferred to weeks 5-6 | Accept; section D step 8 |
| 7(h) / BL-11: landmarks reduced after localization under a retention rule; dev-phase exemption weeks 1-4 | Accept; the retention table in section B expresses the exemption as `consent_version = dev-internal-1` with manual TTL, never exportable |

## Answers to PERCEPTION

1. **Two candidate regions.** Both, as rival `region` hypotheses on the same episode, each with its own `region_confidence` and `rival_of` pointing at the other; the identity stage runs on both crops; if both yield singleton matches to different items the episode is split into two object events (two items at once, L225); if both match the same item, the one nearest `release_point` wins and the other is superseded; if either is ambiguous, no bank write for that crop. One region plus `none` throws away the evidence the versioned design exists to keep. Status: resolved; PERCEPTION's `target_regions[]` contract (≤ 2, masks, `rival_of`, `release_point`) is what section B's `localizations` row stores.
2. **Proposer on idle frames.** Not on the whole frame. Frame-level scoring is DINOv2 only (the index); the proposer (RepViT-SAM, point-prompted from the DINOv2 peak, PerSAM-style) runs on at most 3 shortlisted frames per query, on a 2.5× crop. So RepViT-SAM is on the query path but bounded to ≤ 3 calls and a 2 s total timeout. The idle keyframe must be stored at capture resolution and indexed at 518 px; the re-observable object floor is ≈ 28 px at index scale. Status: resolved; PERCEPTION's conditions (shared masked-token recipe; ≥ 95% of unpooled recall@3 on CUTE before freezing the index; RepViT-SAM's CPU cost from the same week-1 measurement; negative re-observation as hedge input only) are all adopted in section E.
3. **Separation needed.** Stated in the terms the ledger uses: at α = 0.05 the conformal singleton rate on distinct-instance queries (same category, not deliberate lookalikes) must be ≥ 0.80 for the coverage line to be meaningful. In raw cosine terms on 224 px foreground-masked mean-patch crops: the 5th percentile of intra-instance similarity must exceed the 95th percentile of nearest-other-instance similarity by ≥ 0.05, and the EER between the two distributions must be ≤ 10%. In CUTE terms: ≥ 0.85 top-1 on the in-the-wild non-lookalike subset at our crop size. For medication (α = 0.01) the same gap must hold at the 1st/99th percentiles or the item falls to `hedged` by rule, which is acceptable: I do not need the backbone to separate refills, the group path and OCR do that. PERCEPTION's escalation order if ViT-S misses it (336 px crops, then DINOv3 ViT-S/16 under COMMERCIAL's conditions, then ViT-B/14 on the laptop) is accepted; each step is a new `token_recipe_id` and a rebuild.
4. **Per-member crops for retroactive split.** Yes: every exemplar keeps its own crop, mask and OCR fields (`exemplars` table), so an Rx read on a later episode splits the group by `split()` without touching earlier rows. The localizer stores the OCR source crop per episode, not per item (PERCEPTION: done).

### Answers to COMMERCIAL's four answers to me (resolves / changes / disputed)

1. **Deepgram price and data terms.** Resolves on price (my `[V, secondary]` is now `[V-peer]` at the primary) and changes the recommendation's conditions: `mip_opt_out=true` on every request, `family` profile only without a BAA, audit audio stays on the laptop. Not disputed.
2. **Speech stack terms.** Changes two license cells (openWakeWord pretrained models CC BY-NC-SA; Piper `lessac` research-only) and adds the espeak-ng GPL-3 scope condition to both TTS fallbacks; whisper family and Qwen2.5-1.5B confirmed. Not disputed; my round-1 `[V]` on openWakeWord was correct for the code and incomplete for the models, which is the thing that matters, and the final now says so.
3. **Caregiver as data subject.** Resolves; the design gains the consent elements, the withdrawal operation, the photo-disclosure line in both consents, and the voice-note handling. Not disputed.
4. **EgoObjects and PerSAM.** Resolves; EgoObjects is not downloaded, CUTE covers the need; PerSAM is reimplemented from the paper. Not disputed.

---

## Questions for peers

### For ARCH

1. `revision_window_until = received_at + 72 h` bounds both superset revisions and raw-landmark retention; do you want the phone's IndexedDB mirror to expire unsent packets at the same 72 h (logged as coverage loss) so that no packet older than the window can ever arrive as a superset?
2. `localizations` is a layer-1 table keyed by `(episode_id, revision)`; is the localizer deterministic enough (given the same packet bytes and pinned weights) that `rebuild_all()` can re-run it, or should `rebuild_all()` replay from stored `localizations` rows only?
3. The `households` table carries `deployment_profile`; should the resolver refuse the cloud LLM and the Deepgram fallback at the code level under `agency` (a hard gate) or only by config?

### For PERCEPTION

1. The shared token recipe resizes the identity crop to 224 px and the idle frame to 518 px long side; if the week-1 CUTE bar forces 336 px crops, do you want the idle index raised to 777 px in step (so the patch scale ratio between crop and frame stays constant), or kept at 518 px with the refinement doing the scale bridging?
2. For `container_region` geometry you fill `{frame_id, bbox, mask, confidence}` of the region enclosing `release_point` that persists from pre-contact to rest; when two such regions nest (a bag on a chair), do you emit the innermost only, or both so the identity stage can build the chain?

### For COMMERCIAL

1. The retention table (section B) proposes 72 h raw landmarks, 30 days audio, 30 days non-evidence keyframes, evidence keyframes until offboarding; which of these needs a counsel-set number before the IRB packet, and does BIPA's retention-schedule requirement apply to the reduced record (`hand_bbox`, hand-size scalar) or only to the 21-point file?
2. `exports` rows require `deidentified = 1` and a pilot `consent_version` with the global-training flag; is a per-sample manifest enough, or does the consent need to name the data classes (crops, masks, transcripts) that may be exported?

---

## Reactions to peers

All three round-2 finals were read in full before this section was written.

### To ARCH

1. **BL-5 / 7(c), BL-6, BL-8, BL-9.4, BL-9.5, 7(d), 7(e), 7(f), 7(g), the Qwen deferral:** accepted with every condition, each placed in the section it affects (the table in "Answers to ARCH" is the index).
2. **Round-1 2.1 idempotency ("same id + different digest is an error") → replaced by record-and-flag:** ARCH accepted; the conditions (server-computed relation, ack-then-delete) were already in my rule and are now stated explicitly.
3. **BL-11 and 7(h):** accepted; the retention rule is in section B as a policy table so the dev-phase exemption is a consent class, not a code path, and so that `exports` cannot pick up dev footage by accident.
4. **2.7 `media_retention` side table instead of nullable paths:** accepted; it is the cleaner resolution of COMMERCIAL's trigger condition and it keeps every digest verifiable after deletion.
5. **Build order:** the hypothesis layer, `recompute()`, `rebuild_all()` and the replay harness in week 1 against synthetic packets (ARCH track d) is what I asked for; the caregiver report UI in weeks 5-6 with its consent in week 1 is right.
6. **R4 and R7:** the CUTE calibration in week 1 and the re-observation measurements in week 2 are the two experiments my sections depend on; nothing else in my design needs footage before week 2.

### To PERCEPTION

1. **`target_regions[]` with masks, `rival_of`, `release_point`; `container_region` geometry by the localizer, `item_id`/`is_container` by the identity stage:** accepted and written into `localizations`, `identify()` and "Answers to ARCH 5". The restructuring is correct: the localizer cannot know identity.
2. **Shared masked-token recipe:** accepted and specified in section E with one id across bank, index, refiner and calibrations; your ≥ 95% recall@3 condition is the freeze gate.
3. **Arrival cost 60 to 200 ms [B]:** recorded beside my 100 to 250 ms; both are week-2 measurements.
4. **BL-10 (`landmark_fps`, `hand_bbox_interpolated`):** both pass through to the ledger (`episodes.landmark_fps`, the `localizations` payload) and to the scoring sheet so pilot failures can be split by Worker rate; an interpolated hull on the release frame also blocks a bank write (section C).
5. **BL-11 72 h window:** adopted as `revision_window_until` and as the raw-landmark TTL; it also bounds superset revisions, which is the right coupling.
6. **Negative re-observation as hedge input only; co-visibility degrade-to-no-refusal:** both accepted; the medication cap on `covis_unchecked` is my one addition.
7. **SigLIP 2 zero-shot category and `is_container` as soft scores, user naming overrides:** accepted; `exemplars.category_scores`, `container_score`, `item_current.category/is_container`, a `category` hypothesis kind.

### To COMMERCIAL

1. **Answers to MEMORY 1 to 4:** each resolves or changes a recommendation as listed under "Answers to COMMERCIAL"; nothing disputed.
2. **Reaction 4 (immutability vs retention):** resolved by ARCH's `media_retention` side table rather than nullable paths; rows and digests stay, files go; `retention_until` and `consent_version` are on `episodes`, `episode_revisions`, `keyframes`, `idle_keyframes`, `localizations` (via the episode), `reports` and `exemplars`.
3. **Reaction 5 (caregiver consent; the proactive push photo):** adopted in section G; the push is weeks 5-6 and opt-in.
4. **Reaction 6 (cloud LLM BAA; no PHI in JSON schemas):** adopted in section D.
5. **§4.4 (no voiceprint; no non-wearer hand template):** adopted: no speaker ID anywhere in section F or G; the reduced landmark record never contains a per-person template, and `other_person`/`unknown` are the only non-wearer actor values in the `actor` payload.
6. **§6 cost lines:** my $3.87 was at the spec's 30 min/day; your $0.39 at 3 min/day of push-to-talk is the realistic line and is recorded in section F; the rig's STT cloud line is $0 with whisper primary.
7. **Reaction 8 (MemPal record licence):** agreed; the protocol is copied, not the text.
8. **Reaction 9 ("nothing depends on a non-permissive term" is true after items 1 and 2):** agreed, and now true in the text: the only non-permissive terms left in my sections are on things explicitly excluded (openWakeWord models, `lessac`, espeak-ng on a device).

### Disagreements that remain

- None. One addition of mine that peers have not yet seen: the medication cap at `hedged` when the co-visibility check could not run (`covis_unchecked`). It costs coverage only on medication items on a moving camera and is the cheapest way to keep L219's zero bound honest without refusing matches.

## Exchanges

- Round 1: `ListAgents` listed only this process's own subagent; no `ARCH`, `PERCEPTION` or `COMMERCIAL` agent was addressable; questions were left in `drafts/MEMORY.md` for the coordinator to relay.
- Round 2: the coordinator reported all three finals in `final/`; I read the revised `final/ARCH.md` and `final/PERCEPTION.md` ("Round 2 changes" first) and `final/COMMERCIAL.md` in full. Their answers to MEMORY are reconciled above; no direct peer message was exchanged.
