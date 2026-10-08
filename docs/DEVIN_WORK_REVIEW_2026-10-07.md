# Review of Devin's work in the PAM repo, 2026-10-07

Scope: everything in `C:\Users\anees\My Programs\PAM` as of the evening of October 7: three unpushed commits (`f545c5b`, `011baa4`, `d94cc5d`), the uncommitted working tree (26 new or changed files), and the five new documents in `docs/`. I re-ran every test suite in an independent Linux sandbox (Python 3.10, the same package versions Devin recorded) rather than trusting the reported counts. Line counts and test numbers below are mine.

## 1. Bottom line

Devin did a lot, and most of it is good. In two days it: hardened the phone server (private files, TLS generation, no key exposure), wrote the new episode packet, ledger extension, localizer and controller in Python, built a new browser app with a camera controller, a persisted upload queue, a text chat and a stored-items browser, wrote a 20-test bootstrap suite against the new server, and produced a detailed, honest handoff that distinguishes what is implemented from what is only designed. It ran an internal team (a coordinator, seven reviewers, three builders, a tester and a documentation lead) and recorded their disagreements instead of papering over them.

Three things need your attention:

1. **The working tree is uncommitted and the three commits are unpushed.** About 4,000 lines of new code and docs exist only on your laptop. Commit and push today, before anything else.
2. **The build is mid-flight, not done.** The new bootstrap suite is 17 of 20 passing; the three failures are real builder-versus-tester mismatches. The legacy pipeline suite went from 36 pass / 23 blocked to 34 pass / 41 fail, because the tester pointed it at the new server without finishing the retirement map for the old routes. Devin's handoff says exactly this ("no post-CP0 test verdict has yet been relayed"); nothing here is a surprise.
3. **Devin did not do the day-1 purge, and it was right not to.** You told it no deletions or history rewriting without your specific authorization, so it recorded the purge as a proposal and stopped. It also found that the review's purge list was partly aimed at the wrong repo: the weights, the MobileCLIP file and the EPIC video were never copied into PAM, so PAM's history is already clean and needs no rewrite. What remains is small and is listed in section 6; it needs one sentence from you.

Devin also recorded a set of scope decisions you gave it directly, which I did not have when the architecture review was written (section 7). They are sensible and they simplify the product; the review's voice and speech sections are now deferred material.

## 2. The three commits (pushed to nowhere yet)

| Commit | What it did | My check |
| --- | --- | --- |
| `f545c5b` Protect TLS material and require valid temporal evidence | `phone/serve.py` gained a `PublicFiles` handler: only named HTML pages and approved assets are served; `key.pem`, `cert.pem`, hidden paths, traversal, directory listings and Windows alternate-stream syntax are refused for GET and HEAD. TLS generation uses an explicit minimal OpenSSL config (SHA-256, SANs for the LAN IP, 127.0.0.1 and localhost, `CA:FALSE`), which fixed a duplicate Basic Constraints bug from inheriting host defaults. An incomplete cert/key pair is refused, never overwritten. `EventVerifier.prepare` rejects reused paths and non-increasing or non-finite frame timestamps. | Closes the key-exposure item from section 10 of the spec. The pair on disk is fresh (generated October 6, not copied from hackmit), gitignored and untracked. `git ls-files` shows no `.pem`, `.env`, weights or media. |
| `011baa4` Prove regression sensitivity and expose blocked coverage | Strengthened `test_personal_pipeline.py` to assert the exact intended error messages, added real-folder denial tests for `/key.pem` and `/../server/app.py` that never read the key's contents, and ran a mutation check on the SQLite-close regression (remove `db.close()`, watch the test fail, restore). | A regression test for a fix that already existed, and Devin says so. Good discipline. |
| `d94cc5d` Decouple private memory storage from the scheduling application | New `perception/private_files.py` (108 lines): `private_append_fd` with owner checks, a current-user-only Windows DACL via ctypes, mode 0600 on POSIX, non-inheritable descriptors, refusing to write if protection fails. Six tests. `ObjectStore` imports it instead of the archived `server/schedule.py`. | 6/6 pass in my sandbox. This is what let 15 previously blocked pipeline tests run. |

## 3. The uncommitted builder work

Devin's "builders A, B and C" each produced their part of the first milestone. None of it is committed. What exists:

### Builder A: perception (Python)

| File | Lines | What it is |
| --- | --- | --- |
| `perception/episode.py` | 227 | Strict pydantic `EpisodePacket` (extra fields forbidden) and `parse_packet(raw: bytes)`: 4 MiB cap, 1 to 8 unique keyframes with roles `pre_contact / hand_busy / carry / release / rest`, base64 JPEG decoded and dimension-checked against the declared capture size, strictly increasing keyframe times, a clock anchor, up to 10 carry-burst frames, bounded landmark samples (21 points per hand, image-normalised x/y, signed z, optional world coordinates, max 2 hands), gaps, `outcome_hint`, `capture_mode manual / automatic`. |
| `perception/episode_store.py` | 460 | `EpisodeStoreMixin` on `ObjectStore`, with a new additive schema (`user_version` 1 to 2, legacy tables untouched): `episode_revisions` keyed by profile, device, episode and revision with transport and semantic digests; `episode_jobs` with lease tokens and fencing; `local_observations`; a materialized `current_items` projection; `item_names`; episode and item tombstones; `local_audit`; `local_cannot_links`. `ingest_episode` stores durably before acking; same semantic digest is a no-op duplicate, a superset is a revision (max 8), otherwise conflict. `process_pending` claims jobs under `BEGIN IMMEDIATE`, runs the localizer, forces any observation without approved calibration down to `provisional / sighted / actor unknown`, never collapses two co-visible outputs into one item, inserts cannot-links between them, rebuilds the projection, and never persists exception text. `list_items`, `get_item`, `item_history`, `item_image`, `rename_item`, `answer_text`, `rebuild_all`, `migration_plan`, `redact_item`, `capabilities`. |
| `perception/localizer.py` | 93 | `localize(packet)`: registers first and last keyframe with sparse LK features plus RANSAC partial-affine, refuses scale or translation outside bounds, differences the registered grayscale frames, opens the mask, requires the changed area to be between 0.2% and 20% of the frame, and returns up to 4 regions as `LocalObservation`s with `confidence_basis = "registered OpenCV difference; not object or identity recognition"`. Flat frames, sparse features, camera cuts and broad motion return nothing. |
| `perception/episode_controller.py` | 65 | Pure `step(state, sample)` reference controller: idle, busy, settling; `BUSY_MIN_MS 200`, `REST_MIN_MS 600`, `MAX_EPISODE_MS 10000`; carry selection is the first valid frame after busy and motion, never a future midpoint; a missing measurement cannot settle an episode. |

### Builder B: server

| File | Lines | What it is |
| --- | --- | --- |
| `server/memory_app.py` | 346 | `create_app(database_path, profile_id, processor, clock, auth_pin, chat_provider)`. PIN login with an opaque server-side session, HttpOnly SameSite=Strict cookie, Secure on HTTPS, rate limits (5 per client, 60 global), explicit logout revocation. State-changing requests require an exact same-origin `Origin`; `sec-fetch-site: cross-site` is rejected before effects. No default PIN: missing PIN fails closed. `GET /api/auth/session`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/health` (protected), `POST /api/episodes` (4 MiB actual-byte cap, content-encoding identity only), `GET /api/items`, `/api/items/{id}`, `/history`, `/image` (no-store), `POST /api/items/{id}/name`, `POST /api/chat` (local mode needs no key; cloud mode returns 503 `chat_not_configured` unless a provider and a policy are configured), `GET /` serves `memory.html`, `/agent.html` redirects, assets from an allowlist. Every retired Deepgram, face, dose and calendar route returns 410 without importing anything. |
| `server/app.py` | 17 live lines | Now a shim that re-exports `memory_app`. The entire old 68 KB source is kept inside an inert raw string `_RETIRED_SOURCE` and then deleted, so the old handlers can never run. This satisfies the contract's "preserve old source and comments" rule literally; see section 6 for why I would not keep it that way. |

### Builder C: browser

| File | Lines | What it is |
| --- | --- | --- |
| `phone/memory.html` | 82 | One page: sign-in, text chat, stored items, camera. Loads only `/assets/memory.css` and `/assets/memory.js`; no CDN, no telemetry. |
| `phone/assets/memory.js` | 268 | App shell; all data rendered through `textContent`; same-origin `fetch` with `cache: 'no-store'`. |
| `phone/assets/memory-camera.js` | 183 | `getUserMedia({audio: false, video: {environment, 1280x720, 10 fps ideal, 15 max}})`; a 2-second ring of capture-resolution bitmaps capped at 20, up to 8 pinned keyframes and 10 downscaled grayscale burst frames; the burst starts causally at the first motion after busy; every bitmap is closed on eviction, abort, pause and stop; track `ended`, a frame-delivery gap over 1 s, and visibility changes are recorded as coverage gaps. |
| `phone/assets/memory-queue.js` | 137 | Serialized packets persisted in IndexedDB with their UUID and SHA-256 transport digest; retries resend the exact bytes; a record is deleted only when an ack matches episode, device, digest and `retained: true`. Storage denial is reported as coverage loss. |
| `phone/assets/controller.js` | 47 | A port of `episode_controller.py` with the same three constants and the same transitions. |
| `phone/assets/grayscale-jpeg.js`, `memory.css` | 62, 83 | A tiny grayscale JPEG encoder for burst frames; the white-and-blue accessible stylesheet. |

### Tester

`server/test_memory_bootstrap.py` (619 lines, 20 tests): the `T-NO-CHAT-KEY` gate (start the real app with every chat credential unset, ingest a placement and a relocation through a fixture processor, restart, check the catalogue), auth independent of a missing database, cookie and logout revocation, origin rejection, PIN-missing fail-closed, 400 for malformed packets without processing, 413 for over-cap bytes without an ack, semantic duplicates echoing this submission's transport digest, the revision cap returning 409, conflicts retained but not reinterpreted, catalogue image and history, cross-profile isolation, abstention without an image when there is no evidence, uncalibrated evidence never claiming confidence, a chat-provider error not stopping memory, retired routes never executing, and an egress guard that fails the test if any `anthropic` or HTTP client is constructed.

### Documentation lead

`docs/BUILD_CONTRACT.md` (115 lines): the milestone's exact interfaces and ownership, the packet JSON, the auth API, the store methods, the catalogue and chat API, and the browser rules. This is the document the builders worked from, and the code matches it closely.

`docs/CONTINUATION_HANDOFF.md` (397 lines, 50 KB): the operational handoff. Authority chain, your latest instructions, repo state, read order, the CP0 test baseline with exact reproduction commands, a per-agent summary with each agent's corrected mistakes, the intended architecture, twelve open decisions builders must not guess, the planned work order, the recomputed subscription sensitivity table, legal and evidence boundaries, and a resume prompt. This is the "in-depth reporting doc" you were looking for.

`docs/RESEARCH_LOG.md` (290 lines): decision register (D-001 to D-013), the cross-review blocker register (B-01 to B-17, all open), and limits on any public claim. `docs/RESEARCH_EVIDENCE.md` (167 lines): SHA-256 of every supplied input, the primary-source checks it made (MediaPipe package metadata, the AGPL text), and the register fields every future artifact must carry. `docs/RESEARCH_EXPERIMENTS.md` (305 lines): checkpoints X-001 through X-006 with environment, commands and durations.

`docs/review-inputs-20261006/`: the architecture review and the four agent reports, filed under a dated folder with matching hashes. `docs/agent-round-b-raw.tar.gz`: the verbatim round-B outputs of its four internal agents (plain text, 20 KB).

## 4. Test results, independently reproduced

Sandbox: Linux, Python 3.10.12, pydantic 2.13.5, numpy 2.2.6, opencv 5.0.0, fastapi 0.142.4, httpx 0.28.1, run from the PAM root with `PYTHONPATH=""` as Devin documents. One sandbox difference: `TestCase.enterContext` is a Python 3.11 API, so I ran the suites through a 10-line shim that adds it; nothing in the repo was changed.

| Suite | Devin's CP0 (at `d94cc5d`) | Mine (uncommitted tree) | Reading |
| --- | --- | --- | --- |
| `perception/test_capture.py` | 8 pass | 8 pass | |
| `perception/test_interaction.py` | 7 pass | 7 pass | |
| `perception/test_private_files.py` | 6 pass | 6 pass | POSIX path exercised here for the first time; Devin had only run the Windows path |
| `server/test_memory_lifecycle.py` | 61 pass, 141 s | 61 pass, 1.2 s | Green. The Windows run is slow because of the DACL work, not the tests |
| `server/test_memory_bootstrap.py` | did not exist | 17 pass, 3 fail | New suite against the new server; the failures are below |
| `server/test_personal_pipeline.py` | 36 pass, 23 setup errors | 34 pass, 16 fail, 25 errors | The tester removed the legacy `ApiFixture` and pointed the old security tests at the new app without finishing the retirement map |

The three bootstrap failures, which are the current state of the build:

1. `test_T_NO_CHAT_KEY_real_app_store_process_restart_catalogue`: after a fixture placement, the catalogue reports `location_status = unknown`, the test expects `placed`. Cause: `process_pending` forces any observation whose `calibration.approved` is not `True` down to `sighted / unknown`; the tester's fixture processor either does not set that flag or the two sides disagree on what a trusted fixture may assert. A contract question, not a bug in either half.
2. `test_conflict_is_retained_but_not_reinterpreted`: a packet the tester built as a conflict is accepted as `revised`. `_superset` compares the eight header fields and checks every old keyframe, burst frame, landmark and gap is present in the new packet; the tester's conflict case passes that test. One of them has the wrong definition of superset.
3. `test_catalogue_image_and_history`: `item_image` serves a different JPEG from the one the test expects (a different frame or crop of the same episode). A provenance rule to pin: which frame is the item's reference image.

The legacy pipeline failures fall into three groups: 12 assertions of `410 != 401` (the old tests expect unauthenticated requests to retired routes to get 401; the new server returns 410 before auth); 19 attribute errors (`relay_open`, `tracked`, `review`, `legacy_search`, `app`) from the removed fixture; and 2 certificate-creation errors. Devin's handoff already states the rule for this: old positive expectations are replaced only with an explicit retirement map and replacement tests, never skips. That map is the next tester task.

## 5. What Devin got right that the architecture review got wrong

Devin's internal cross-review (B-01 to B-17 in `RESEARCH_LOG.md`) found several errors in the review I gave it. These are legitimate and should be carried forward:

- **B-01, the carry burst.** The review said the burst is "centred on the carry midpoint." A live controller cannot know where the midpoint will be. The build uses a causal first-valid rule: the burst starts at the first valid frame after busy and motion. Correct.
- **B-04, "breach today."** The review called the AGPL dependencies a breach. AGPL is not a non-commercial license; presence of a dependency in a requirements file, in a repo that has not distributed anything, is a diligence flag, not an infringement. The direction (remove them) stands; the word was wrong.
- **B-08, SQLite roles.** The memory reviewer's schema relied on a session-flag or role exception to immutability triggers that SQLite does not have. The build uses explicit tombstone tables and an audited `redact_item` instead.
- **B-13, certificate rotation.** The review's "generate a fresh cert and key" became, correctly, "never overwrite an existing pair automatically; refuse and print rotation instructions."
- **B-16, acks bind to digests.** The review's "never an error to the phone" would have acknowledged dropped bytes. The build acks only after durable storage, binds the ack to the transport digest of this submission, and returns real 400/401/409/413 errors.
- **The purge list.** The review told Devin to purge weights, the MobileCLIP file and the EPIC video and rewrite history. Those artifacts were never copied into PAM (I excluded them when I split the repo), so there is nothing to rewrite. Devin checked and said so.

## 6. What needs a decision from you

**The purge, correctly scoped.** No history rewrite is needed. What is left in PAM, and the one-line authorization each needs:

| Item | Where | Risk if left | Action |
| --- | --- | --- | --- |
| `ultralytics==8.4.155` and `clip @ git+https://github.com/ultralytics/CLIP.git` | `perception/requirements.txt` lines 1 and 7 | Both AGPL-3.0; nothing in the new code imports them, but any future `pip install -r` pulls them in and a diligence reviewer reads the file | Delete the two lines; add `pip-licenses` to CI failing on AGPL/GPL/unknown |
| `perception/blockers/eval_epic.py` | `perception/blockers/` | References an EPIC-KITCHENS clip that is not in the repo; the script itself is not the dataset | Delete it, or keep it only if you intend to buy Bristol's license |
| `elasticsearch`, `icalendar`, `python-dateutil`, `google-auth-oauthlib` | `server/requirements.txt` | Dead dependencies of retired routes | Delete the lines |
| The 68 KB retired source inside `_RETIRED_SOURCE` in `server/app.py` | `server/app.py` | Inert, but a `'''` anywhere in a future edit of that string breaks the module, and it carries the old face and Deepgram code forward in every clone | Cut it; the history has it. Keep the 17-line shim |
| `memory_pipeline.py`, `vlm.py`, `glasses_rx.py`, `fake_glasses.py`, `interaction.py` and the YOLOE-keyed paths | `perception/` | Still the old entry point; not imported by the new server | Leave until the new path passes the gates, then delete in one commit |

**Commit and push.** Three commits are unpushed and the builder tree is uncommitted. Devin's instructions from you forbid it from pushing; that was right, but it means you are the only copy. In PowerShell:

```powershell
cd "C:\Users\anees\My Programs\PAM"
git add -A
git commit -m "First milestone build: episode packet, ledger extension, localizer, controller, memory server, browser app, bootstrap tests, research record"
git push
```

(`.gitattributes` normalises Devin's CRLF files on commit; the warnings are expected.)

**The tarball.** `docs/agent-round-b-raw.tar.gz` holds four plain-text agent outputs. Extract them to `docs/review-inputs-20261006/round-b/*.md` so they are readable and diffable; binary blobs in `docs/` are a habit worth stopping early.

## 7. Scope changes Devin recorded from you

The handoff records these as your instructions. They were not in the architecture review and they change parts of it:

| Your instruction (per the handoff) | Effect |
| --- | --- |
| Text chat, not voice; no Deepgram, STT, TTS or microphone in this build | The review's speech stack (whisper, Deepgram Nova-3, push-to-talk) is deferred. This also removes the entire audio-consent surface from the pilot, which simplifies the recording-law position. The browser requests `audio: false` and loads no voice library. |
| The browser app must have an authenticated stored-items browser; do not delete stored memories | Built: `/api/items`, `/api/items/{id}`, `/history`, `/image`, `/name`, and the Stored items tab. It is a catalogue of the user's own evidence, not a database console. |
| Small per-user subscription; model price as a variable with $5 / $10 / $15 sensitivity; no family-vs-agency launch decision yet | Devin recomputed the margin table itself (section 10 of the handoff) after finding errors in its cost agent's table. At $5 a month the product loses money under every support assumption; at $10 it is positive only with low support cost. That is the honest number. |
| iPhone testing later; software simulations now, with no claims about speed, battery or accuracy from them | The build uses a fixture processor and manual episode marking; the handoff is explicit that no real vision accuracy has been measured. |
| No push, no deletion, no history rewrite, no paid calls, no household recording without specific authorization | Followed to the letter, which is why the purge and the push are waiting on you. |

One consequence to be aware of: with no hand model yet cleared (the MediaPipe `.task` weight license is still unverified by a primary source), the camera page runs in a labeled manual-mark mode. Automatic daily capture is a required later checkpoint, not something this build delivers.

## 8. What I would do next, in order

1. Commit and push (section 6).
2. Authorize the scoped purge in section 6 with one sentence to Devin; no history rewrite.
3. Have the tester resolve the three bootstrap failures as contract decisions, not test edits: (a) what a trusted fixture processor may assert, (b) the definition of superset versus conflict, (c) which frame is an item's reference image. Then finish the retirement map so `test_personal_pipeline.py` either passes or is explicitly replaced, test by test.
4. Extract the tarball; delete `_RETIRED_SOURCE`.
5. Then the next checkpoint in Devin's own list: CP1 (strict contracts, serialization, tamper and profile binding) and CP3 (TLS, auth, origin, secret boundaries), both of which the bootstrap suite already half-covers.
6. The model-enable gate stays closed until someone opens the MediaPipe model-card PDF and records the weight license. Five minutes for a human; Devin cannot reach the file.

Devin's process is heavier than the code so far: five documents and a 17-item blocker register for roughly 1,900 lines of new production code. That is the right ratio at a design gate and the wrong one two weeks from now. The signal to watch is whether the next handoff reports test counts going up and blocker counts going down.
