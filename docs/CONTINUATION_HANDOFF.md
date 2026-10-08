# PAM continuation handoff for Claude or another coding agent

Snapshot updated: 2026-10-07, after the coordinator's scoped design decision. This is an operational handoff, not a claim that full v5 or the product is finished. **The first functional software milestone's DESIGN gate is closed; three builders and the test lead are active.** No completed production change or post-CP0 test verdict has yet been relayed to this record.

Authority chain: existing v4 broad principles, latest explicit user scope, then [BUILD_CONTRACT.md](BUILD_CONTRACT.md) for the first milestone's exact interfaces and scoped decisions. It supersedes conflicting agent proposals; do not rewrite its APIs from this handoff. Research/model/device/pilot approval does not follow from the software design decision. Earlier “not started/open gate” statements in dated review history are historical, not current instructions.

## 1. Latest user instructions: these override older conversational typos

1. Build an assistive object-memory product using a coordinated team: one architecture lead, two research agents, commercialization/technology-permission review, cost verification, three builders after the design gate, an independent tester and a documentation lead. Use substantial cross-review, not isolated essays. Run simulations/checkpoints, hand failures to builders, and finish with an overall integrity report.
2. Be conscious of token usage. Prefer deltas and specific questions over repeating full reports or rereading everything.
3. **The browser app SHOULD have a stored-items/memories browser.** The earlier message saying it should NOT have this was explicitly corrected by the user. Do not remove the Memories/catalogue feature on that obsolete instruction. Provide an authenticated view of the user's stored items and evidence, not a public SQL/database administration console. Do not delete stored memories.
4. **Use a standard TEXT CHAT interface now. Deepgram is not necessary and is not to be integrated for this build.** Defer speech recognition, TTS, Voice Agent and microphone flows. Retire the legacy Deepgram integration during the approved server/browser trim, with explicit replacement/retirement tests. A text chatbot does not imply permission for a paid LLM: model/provider choice and budget remain an explicit decision. Local memory retrieval and evidence-grounded templates are a viable baseline.
5. Cost analysis should assume a **small per-user subscription**, not a selected $25 or $30 plan. Model price as a variable, including $5/$10/$15 sensitivity. The user did not choose family versus agency as the launch market.
6. Actual iPhone testing can happen **later**. Do software simulations now; do not claim iPhone speed, battery, camera recall, thermal behavior or real-world accuracy from them.
7. Maintain a thorough durable handoff before any usage cutoff, including planning, research, agent findings, decisions, tests and remaining work. The assistant cannot query the user's remaining Devin account allowance or predict its cutoff. Keep this record current instead of promising automatic quota monitoring.
8. Do not push. No deletion of existing files, real databases, secrets, branches or history rewriting without specific user authorization. No paid provider calls, real household recording, legal filings or purchases have been authorized here.

The latest UI/text-chat changes are REQUIREMENTS, not completed code changes. Existing `phone/agent.html` still has a Memories tab, item/timeline browsing and recent-memory rendering, and remains voice-centric. The corrected requirement needs reconciliation with the new browser build; there is no UI removal to undo from this session.

### Mandatory separation: memory runs without chatbot credentials

Latest user requirement: as the camera observes daily activity, meaningful events must be locally processed, indexed and persisted even when no chatbot provider/API key is configured. Starting the server, enabling capture, uploading episodes, updating item locations and browsing/searching stored items must not initialize or require a cloud-chat client. Existing authentication/profile isolation still applies; a chatbot provider key is not the local service's access credential.

Cloud-powered text chat is optional and explicitly user-initiated. Resolve/configure its provider only at that boundary. Missing credentials should produce a clear chat-only setup state; invalid keys, provider outages or exhausted chat budgets must not stop recording, ingestion, indexing or database browsing. Chat availability is not a prerequisite for the memory worker, and camera events must not invoke a paid VLM to write memory. Local models still require valid, provisioned artifacts: fail visibly when a required capability is unavailable rather than silently fabricating successful processing.

Required integration gate `T-NO-CHAT-KEY`: unset all chatbot/provider credentials; start the real application with synthetic capture/local-model fixtures; ingest a placement and relocation; verify durable item state and authenticated catalogue updates, including after restart. Assert no provider client construction or nonlocal provider egress. Then simulate optional chat missing-key, invalid-key, outage and budget-exhaustion paths while continuing ingestion; memory progress must be unaffected. A fixture pass establishes software independence, not real vision accuracy. This gate is required but has NOT been implemented or run yet.

Browser scope limitation: automatic collection works while the camera page is actively capturing and connected or safely queued. Safari backgrounding/screen lock may suspend capture. Report interruptions and queue/coverage loss honestly; do not promise continuous all-day background recording before the appropriate native/device validation.

## 2. Exact project and repository state

- Active project: `C:/Users/anees/My Programs/PAM`.
- Origin: `https://github.com/AneeshD04/Physical_Assistive_Memory_PAM.git`.
- Branch: `main`.
- Last production-code commit: `d94cc5da1928384ed08bcca4e38811aade16d43a` (Devin). The user then committed the whole milestone-1 working tree as `1fd24c8` ("Milestone 1 builder work") on 2026-10-07 22:15 and pushed; `main` and `origin/main` were equal at that point.
- **CP2 (architect with a six-role agent team, 2026-10-08, after `fbf6719`):** automatic capture path built on synthetic inputs and proven end to end with a scripted worker; cross-language controller/motion/hand-busy equivalence; clock-only staleness; manifest-gated model assets with a structured licence register; `docs/BUILD_PLAN.md` (CP2 to CP5), `docs/LICENSES.md`, `docs/OVERSIGHT_CP2.md`, `docs/FINANCE.md` added. 215/215 tests. The real hand model remains blocked on a human licence check (OVERSIGHT_CP2 §0). See section 5.
- **CP1 (architect, 2026-10-07, after `1fd24c8`, committed by the user as `fbf6719`):** the three bootstrap contract mismatches are decided and applied (`docs/BUILD_CONTRACT.md`, "Contract decisions after CP0"), the legacy pipeline API tests are retired in place with a method-by-method map, the certificate tests run the real `openssl`, and the browser outlines the target region on the evidence photo. Changed files: `perception/episode_store.py`, `server/memory_app.py`, `server/test_memory_bootstrap.py`, `server/test_personal_pipeline.py`, `phone/assets/memory.js`, `phone/assets/memory.css`, `docs/BUILD_CONTRACT.md`, this file. See section 5 for the reproduced counts.
- Archive project: `C:/Users/anees/hackmit`. Do NOT edit it or add its application modules to PYTHONPATH to make PAM tests pass.
- Existing archive virtual environment is used ONLY as an interpreter/dependency runtime: `C:/Users/anees/hackmit/perception/.venv/Scripts/python.exe`.
- Before documentation work, the tree was clean at `d94cc5d`. There are now uncommitted research documents and a CLAUDE appendix. This handoff and preserved input archives are also uncommitted unless a later checkpoint explicitly says otherwise. Do not reset/clean the working tree: that would lose the handoff.
- `docs/MEMORY_SYSTEM_V4.md` remains revision 4 with an additive milestone pointer, not a full v5 rewrite. Its broad principles and historical Part 2 remain. Latest user scope and `docs/BUILD_CONTRACT.md` govern this first milestone's conflicting contracts; the coordinator closed only that DESIGN gate. Full model/device/pilot gates remain open.
- Read `CLAUDE.md` before changes in perception/phone. It contains extensive historical HackMIT material; its newer PAM notes and the canonical spec distinguish what is current.

### Commits created by Devin

| Commit | What changed |
| --- | --- |
| `f545c5b` | Restricted static serving; temporal-frame validation; explicit TLS generation configuration; regression tests and notes. |
| `011baa4` | Exact intended-error assertions; actual-folder GET/HEAD denials with content-open guards; mutation-test evidence and honest blocked-coverage reporting. |
| `d94cc5d` | Standalone `private_append_fd` utility plus relevant tests; ObjectStore no longer imports the scheduling application. |

The Devin co-author trailer was intentional. The user's conditional suggestion to remove it if unintended does not require amending history. No amend/rebase/filter-repo has been performed.

## 3. Read order and durable research sources

1. This handoff: latest user scope and work state, separating historical checkpoints.
2. `docs/BUILD_CONTRACT.md`: authoritative exact interfaces/ownership for this software milestone; do not substitute a peer's schema or API list.
3. `docs/RESEARCH_LOG.md`: decision register, claim caveats and gate history; latest scope supersedes the no-browser typo and speech plans.
4. `docs/RESEARCH_EXPERIMENTS.md`: CP0, failure history, environment and protocols; no post-build verdict yet.
5. `docs/RESEARCH_EVIDENCE.md`: versions, hashes, authority, preservation and licensing limits.
6. `docs/MEMORY_SYSTEM_V4.md`, Part 1 broad principles and additive milestone pointer; `docs/ROUND4_RESPONSE.md` for history.
7. `docs/review-inputs-20261006/FINAL_ARCHITECTURE_REVIEW.md` and `review/{ARCH,PERCEPTION,MEMORY,COMMERCIAL,README}.md`: external inputs, not new approval.
8. `docs/agent-round-b-raw.tar.gz`: available verbatim current-agent Round-B responses; see member map and correction warnings below.

### Input preservation and authority

The original external package was supplied at `C:/Users/anees/Downloads/pam-final-review.zip`; standalone decision document at `C:/Users/anees/Downloads/FINAL_ARCHITECTURE_REVIEW.md`. The supplied Markdown and the archived repository copy have matching SHA-256:

`3adefa8747e1fd5c6467dc1a28cf50770127f0b114b5ac17faf9a546e5014892`

The reports' words "approved", "resolved", "Build", "purge" and "rewrite history" are proposals from those reviewers, NOT authorization to execute destructive commands or proof of commercial/legal clearance. Their [V] means that reviewer reports opening a source, not that the claim has been independently validated by this project.

Available verbatim current-agent Round-B outputs in the tar archive:

| Archive member | Agent |
| --- | --- |
| `90c93209/content.txt` | Architecture lead, Round B |
| `bf7fad1d/content.txt` | Perception research, Round B |
| `4b0e58c1/content.txt` | Memory/retrieval research, Round B |
| `45a3f1e1/content.txt` | Cost verifier, Round B |

Archive SHA-256: `d6e3260cb4f6af475633254014bb43433f380661eac6c46bf6c5cfb5c20a192e`. All six preserved supplied Markdown hashes match the earlier source register, not only the decision document.

These outputs include mistakes and conflicting recommendations. They are preserved as evidence of deliberation, not an implementation spec. The per-agent summaries below cover every current agent and both review rounds where available. This is not a byte-for-byte export of every Devin chat/tool transcript. Additional verbatim initial/commercial/test responses remain in Devin conversation history; the essential results, questions and status are recorded here and in the research logs. Agent IDs are audit/resume aids for Devin, not APIs available to Claude.

## 4. Verified code baseline at CP0 — before the active builders

The following describes `d94cc5d`, not the current contents of concurrently edited
builder files. Preserve it as baseline evidence; do not mark any new production
capability completed until a builder report and independent checkpoint arrive.

### Static files and TLS

`phone/serve.py` now uses `PublicFiles`. Public HTML pages and approved assets are permitted; private files, hidden paths, directory listings, traversal and Windows alternate-stream syntax are rejected for GET and HEAD. Canonical path containment is checked. Actual-folder denial tests cover `/key.pem`, `/cert.pem` and `/../server/app.py` without reading their contents.

TLS generation uses an explicit minimal OpenSSL config on stdin, SHA-256, SANs, `CA:FALSE`, key usage and server authentication. This fixes a discovered duplicate Basic Constraints problem caused by combining host OpenSSL defaults with an added leaf constraint. Existing complete pairs are reused; incomplete pairs are refused rather than overwritten.

Fresh ignored local TLS files were created previously, not copied from hackmit. At creation, the certificate covered `192.168.50.52`, `127.0.0.1`, `localhost`, and was valid from 2026-10-06 to 2027-10-06. OpenSSL and Python SSL verified the certificate/key pair. The private key's protected Windows DACL was set manually to the current user's SID and verified.

**Still missing:** `ensure_cert` does not call the private-file utility; regeneration does not automatically enforce that ACL. Existing-pair reuse does not check changed LAN IP or expiry. Do not read, print, commit, automatically replace or delete the actual key. The next TLS work must enforce permissions in code, validate reuse, fail closed with deliberate rotation instructions, and test using temporary pairs. No trust store was changed and no live server was started.

### Temporal evidence

`perception/personal_memory.py:EventVerifier.prepare` now rejects reused resolved paths, missing/misaligned/nonfinite/nonpositive/non-increasing frame timestamps, and invalid list shapes. Identical pixels in separately captured frames remain valid. This is still the legacy optional cloud verifier, not the new v5 write path.

`server/test_personal_pipeline.py` media-negative fixtures were made timestamp-consistent, then strengthened to assert the exact intended messages: `Unapproved event image`, `Invalid event image`, `Event image too large`. A temporal-validation failure cannot silently satisfy those checks.

### SQLite cleanup regression

The production `ObjectStore._connection` already closes `db` in `finally`. The new isolated regression was mutation-checked by the coordinator: replace only `db.close()` with `pass`, run the single test, observe failure at `connections[0].closed`, restore the production line, rerun and observe success. The mutation was completely restored and not committed. Call this a **regression test**, not a newly implemented SQLite fix. It mocks only the private-file-writer boundary; full API assertions remain separately gated.

### Private storage utility

`perception/private_files.py` contains `private_append_fd` and the necessary Windows ctypes API support ported from archived `server/schedule.py`, without the scheduling application. It checks ownership, creates/re-secures private files, uses a protected current-user-only DACL on Windows, mode0600/owner checks on POSIX, and non-inheritable descriptors. Protection failures refuse writes.

`perception/test_private_files.py` has six focused tests: new file privacy, existing file protection without loss, append preservation, injected protection failure, wrong-owner refusal, non-inheritance. Windows ACLs were inspected with Get-Acl on temporary files; Unix mode bits were not substituted for Windows protection. POSIX code was not executed in this Windows session.

`ObjectStore` now imports that utility directly. **Its schema and v4 semantics have not been migrated.** Current SQL user_version is1; Candidate JSON schema_version is2. Those are different version numbers, neither denotes v5 implementation.

### Existing baseline versus intended product

The current perception entry point still uses YOLOE/BoT-SORT and the old motion/InteractionTrack pipeline. Personal memory is opt-in; optional cloud VLM code and older actor/admission rules remain. There is no integrated DINOv2/SigLIP/OCR/localizer/hand-worker pipeline, no new packet producer, no versioned-hypothesis schema, no new resolver, no idle patch index, and no native build.

`server/app.py` still imports absent legacy modules, beginning with `doses`; `server/object_api.py` imports absent `caregiver`. The app cannot import as currently checked out. There is no standalone auth shim yet. Old Deepgram/face/dose/calendar/etc routes still exist in source; their modules and behavior are not part of the desired memory-only product. Current user now explicitly requires text chat and NO Deepgram/speech integration.

## 5. Most recent independently reproduced baseline

### CP2, 2026-10-08 (coordinator re-run; Linux sandbox, Python 3.13.16, Node 22, Playwright 1.56 / chromium-1194)

**215 methods attempted, 215 passed, 0 errors, 0 skips.** New suites: `server/test_cp2_controller.py` 24 (golden traces and 100 seeded random traces byte-identical across the Python and Node CLIs; motion and hand-busy goldens bit-identical), `server/test_cp2_staleness.py` 13 (24 h hedge, 7 d abstain, `as_of` replay, stored projection clock-independent), `server/test_cp2_models.py` 18 (manifest gating, structured licence register, `fetch_models.py` refusals), `phone/test/test_ui_smoke.py` 9 (real app in Chromium; no request leaves the origin; manual/automatic/unavailable states; one `capture_mode: automatic` packet from a scripted worker; repeated-release case). The six CP1 suites are unchanged at 151. Blocked, not skipped: the real `hand_landmarker.task` (licence UNVERIFIED, hash unrecorded; sandbox cannot reach its host). Not covered in the browser: the carry burst in automatic mode (static fake camera) and the worker-hung path.

### CP1, 2026-10-07 (architect; Linux sandbox, Python 3.10.12, same package majors)

**151 methods attempted, 151 passed, 0 errors, 0 skips** (capture 8, interaction 7, private_files 6, lifecycle 61, memory_bootstrap 21, personal_pipeline 48). Mutation check: reverting the `outcome_hint` superset rule and the `placed` vocabulary each fails exactly its bootstrap test. Still not an integration result for real vision: every observation in these suites is a fixture or a synthetic rectangle.

| Suite | CP0 | CP1 | What changed |
| --- | ---: | ---: | --- |
| `server/test_memory_bootstrap.py` | 17 / 20 | 21 / 21 | three contract decisions (BUILD_CONTRACT "after CP0" 1-4), the `wait_items` oracle (5), and a new module-graph test that caught B's asset allowlist missing two of C's modules (6) |
| `server/test_personal_pipeline.py` | 34 pass, 25 broken of 59 | 48 / 48 | 23 legacy API methods replaced by 12 ported + the retirement map; certificate tests updated for `validate_pair` |
| other four suites | 82 / 82 | 82 / 82 | untouched |

The legacy file ran 59 methods at CP0 because the tester had already pointed `ApiFixture` at the new server without finishing the port; the "36 pass / 23 setup errors" figure below predates that.

### CP0 (testing lead)

Testing lead CP0, code `d94cc5da1928384ed08bcca4e38811aade16d43a`:

**141 methods attempted, 118 passed, 23 setup errors, 0 assertion failures, 0 skips. Not an all-green integration result.**

| Suite | Passed | Setup errors |
| --- | ---: | ---: |
| `perception/test_capture.py` | 8 | 0 |
| `perception/test_interaction.py` | 7 | 0 |
| `perception/test_private_files.py` | 6 | 0 |
| `server/test_memory_lifecycle.py` | 61 | 0 |
| `server/test_personal_pipeline.py` | 36 | 23 |

Blocked pipeline classes: `ObjectApiSecurityTests`12, `CameraRelaySecurityTests`7, `TokenSecurityTests`4. They fail in fixture setup at `app.py:32 import doses`; their assertions have NOT run. SyntheticFrameTests10 and WorkerBoundaryTests5 now run and pass after the private-file port.

The test fixture also refers to obsolete google_calendar/setup/doses/es components. Its port needs an approved semantic/route-retirement map, not dummy legacy modules or skipped tests. Old tests asserting JSONL/ES fallback or unauthenticated raw-camera behavior must be explicitly replaced if the approved product retires that behavior. Latest user instruction retires Deepgram: preserve denial/no-secret/no-provider-call coverage for retired endpoints and replacement chat/auth paths; do not require successful Deepgram grants as a product feature.

### Runtime and exact reproduction

- Python3.11.0,64-bit; Windows build26200.
- SQLite3.38.4 (STRICT availability established, not migration correctness).
- pydantic2.13.5; numpy2.4.6; opencv-python5.0.0.93; fastapi0.141.1; starlette1.6.0; httpx0.28.1.
- Python SSL OpenSSL1.1.1q; CLI OpenSSL1.1.1s. These old TLS runtimes need a controlled upgrade before production deployment.
- No local PAM venv was created. The archive venv supplies dependencies only; PAM code is imported.

From PAM root, Git Bash:

```bash
export PYTHONPATH="" PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
P="C:/Users/anees/hackmit/perception/.venv/Scripts/python.exe"
"$P" -B perception/test_capture.py -v
"$P" -B perception/test_interaction.py -v
"$P" -B perception/test_private_files.py -v
"$P" -B server/test_memory_lifecycle.py -v
"$P" -B server/test_personal_pipeline.py -v
```

Do not broadly discover server tests: legacy tests elsewhere may start services/use real credentials. Current tests use synthetic rectangles, temporary databases/JPEGs, fake providers and guarded in-memory/ASGI requests. No cameras, real household footage, paid APIs or model downloads were used. Pipeline time/UUID fixtures are not all seeded; do not claim byte-for-byte reproducibility until deterministic goldens are added.

Reported CP0 durations: capture0.002s, interaction0.001s, private-files8.923s, lifecycle141.303s, pipeline41.348s. These are test durations, not vision/model/phone performance.

## 6. Current team and communication record

Seven initial reviewers completed their first round; Round B circulated targeted contradictions via the coordinator, not direct peer messaging. At the earlier handoff the three builders had not started. **The coordinator has now closed the first software milestone's DESIGN gate in BUILD_CONTRACT and started builders A/B/C plus the test lead.** This changes work state, not CP0's results or model/pilot approval. Do not mistake earlier agent consensus or “freeze-ready” language for that scoped coordinator decision.

| Role | Devin ID | Latest state |
| --- | --- | --- |
| Architecture lead | `2da46caf` | A/B complete; coordinator BUILD_CONTRACT supersedes conflicting milestone proposals. |
| Perception research | `7537ab41` | A/B complete; contract selects causal capture-resolution evidence; model/device validation pending. |
| Memory/retrieval research | `f88ef336` | A/B complete; selected PERSIST/logical-erasure scope is in BUILD_CONTRACT, not wholesale approval of its draft. |
| Commercialization verifier | `f5fb648a` | A/B complete; exact weight rights and human legal gates remain. |
| Cost verifier | `11282b95` | A/B complete; parent corrections below govern reporting; hypothetical margins are not measurements. |
| Independent testing lead | `10410cae` | Active; owns tests/fixtures/oracles and next verdicts. CP0 remains latest completed checkpoint. |
| Documentation lead | `5fdacab5` | Resumed after the earlier interruption; updating gate/workstate/provenance. Parent resolved archival blockage. |
| Builder A: perception/data | ID not supplied in current relay | Started; production perception/ObjectStore/contracts only; no tests/docs. |
| Builder B: server/security | ID not supplied in current relay | Started; production server/ and phone/serve.py; no perception/browser/tests/docs. |
| Builder C: browser/UX | ID not supplied in current relay | Started; phone/memory.html and browser assets; no serve.py/server/perception/tests/docs. |

### Architecture lead report: substance and corrections

Round A proposed phone hand-only controller, per-episode ingestion, localizer/index jobs, three-layer SQLite, materialized current state, conformal sets, groups/clarify, retention and gated cloud use. It initially overclaimed readiness, required bootstrap tests green before builders (circular), used future-midpoint burst pinning, treated media deletion as SQL erasure, called projection rebuild a migration, and suggested automatic cert replacement. Coordinator rejected these formulations.

Round B accepts causal first-valid bursts, preserved cannot-links, digest/profile-bound acknowledgements with real errors for malformed/auth/over-limit requests, explicit migration separate from replay, injected clocks, protected reads/writes/WS regardless of DB existence, manual deliberate cert rotation, five answer shapes and disabled unverified model adapters. It separates design gate from post-build bootstrap.

Still unresolved: its SQL redaction uses an unspecified session-flag/trigger exception and WAL/vacuum claims, while MEMORY proposes payload separation. Exact executable DDL, erasure scope and independent tests are not frozen. IDs/timestamps alone are not automatically non-personal data. A shared PIN cannot justify the named attribution examples. No builder should copy its matrix as approved code.

### Perception research report: substance and corrections

Recommended aged Tasks Vision1.0.1 instead of fresh1.1.0; DINOv2-S masked mean-patch plus CLS secondary; SigLIP2; PaddleOCR detection plus line recognition; structural difference and sparse flow with a measured segmentation fallback. SAM3/3.1 was researched under custom terms but NOT adopted. BoT-SORT upstream code is MIT; the Ultralytics integration/licensing choice must not be confused with the algorithm's license. HaMeR depends on gated MANO and was not approved.

Corrected: internal model resizing does not make input resolution irrelevant; normalized image x/y, signed wrist-relative z and world XYZ metres are distinct; sparse LK points are not a dense mask; rec-only OCR timing is not whole curved-label timing; SAM3 was not proven strictly better for this CPU product; ONNX conversion is not a license cure.

It retracted dropping existing hard negatives on failed homography, and accepted causal first-valid carry pinning. However its Round-B text still says an analysis-resolution ring is the source of pre-roll keyframes, conflicting with the required capture-resolution evidence. It also oscillates between burst320/384/512px, mask-generation thresholds and unregistered-diff behavior. These are unresolved choices/experiments, not frozen measurements. A true future carry midpoint cannot be known online; choose an explicit causal retained window.

Actual hand detection, mount recall, localizer IoU, Safari worker speed, OCR performance and DINO/SigLIP quality were NOT measured. No models were downloaded.

### Memory/retrieval research report: substance and corrections

Identified AMEGO/ESOM prior art; do not claim PAM invented interaction/DINO or online object memory. Proposed lexical/category/OCR-first query sets, SigLIP attribute assistance, explicit groups/clarification, versioned identity/actor/relevance/location, re-observation, migration/replay and erasure.

It corrected its initial false AGPL-breach statement, computation estimates and projection-rebuild/migration conflation. It accepts preserving cannot-links, explicit clocks/as_of, no E2E guarantee from conformal alpha and PERSIST until WAL privacy is proven. Extra Qwen/online-conformal/nightly-maintenance work is deferred unless needed.

Its Round-B erasure alternative moves personal payloads into deletable files behind immutable envelopes, but is NOT approved as written: globally hash-keyed payloads need household/retention scoping; IDs/timestamps/hashes can remain personal; deleting files is not a forensic erasure guarantee; old tables cannot be dropped without authorized migration; replay/backup restore must respect deletion. Its mutation matrix still has blanket-immutability exceptions to reconcile.

Other defects to fix: canonical JSON `repr`/Python round does not establish JS-equivalent serialization; acknowledgement hashing episode/status/revision without payload digest is insufficient; 'first canonical localization forever' conflicts with accepted superset revisions. Shared PIN reports must not assert a named person as authenticated. The original formula still needs a defined open-set policy and bank-sensitive calibration, not singleton-as-proof.

### Commercialization report: substance and corrections

Correctly distinguishes AGPL from non-commercial licenses; absent artifacts were not deleted by us. The eval script is not the dataset and is not automatically NC. No purge or history rewrite is approved. Parent verified the named MobileCLIP/YOLOE weight/EPIC-video paths absent from PAM checkout and matching reachable history; dependency references and obsolete routes remain.

Commercial path candidates include permissive-code/weight releases of DINOv2, SigLIP2, PaddleOCR, SAM2.1 and Whisper, with exact artifact/terms verification still needed before runtime adoption. MediaPipe JS package license is verified; the exact `.task` weight grant remains unresolved in this team's record. ONNX/OpenCV Zoo repackaging is not a bypass. Custom SAM3/DINOv3, restricted hand datasets/checkpoints and vendor data terms need distinct status labels, not blanket 'approved'.

Reports were corrected to treat PTT/indicators, biometric/FDA/HIPAA/trademark conclusions as risk flags requiring fact-specific human review. Config does not determine legal status. Shared PIN is role/session access only; use generic/claimed reporter provenance until individual authentication exists. Deletion must address SQL and derived data, not merely a source version bump. No legal clearance, provider account, BAA, consent filing or mark decision was completed.

Speech/vendor choices in this report are now historical/deferred because the user explicitly chose text chat with no Deepgram integration.

### Cost-verification report: substance and required corrections

Useful proposal: default paid egress off; operator-set per-household budgets; integer micro-USD, calendar UTC accounting, atomic reserve/send/settle with fencing, payload bounds, conservative unknown-spend handling and no unbudgeted client path. Five calls/day alone is NOT a dollar ceiling. Support, onboarding, hardware, distribution channel and retention growth remain unmeasured.

Round A incorrectly said API costs never threaten margin and overstated a $25 margin. Round B corrected some claims but its scenario-margin table still contains errors. Do not publish it as verified. Coordinator independently recomputed the table in section10 below.

Its claim that current `fail()` refunds all failures is incorrect: current code sets cost to zero only when `sent_to_provider` is false. Sent/unknown outcomes retain reservations. A processing lease TTL must NOT itself release a possibly billed reservation. Recheck actual code before changing this behavior.

The cost agent correctly distinguishes current1MiB caps from proposed4MiB episodes, and legacy opt-in cloud verification from the desired paid-cloud-free write path. Its newly named low-cost models and model IDs require primary/account verification; do not adopt guessed model IDs or a new low price blindly. All speech cost assumptions are superseded for the current text-only scope. 'Small subscription' is not a selected launch price or proven margin.

### Testing lead report and checkpoint responsibilities

Independently reproduced CP0:141 attempted/118pass/23setup errors. It explicitly did not rerun the parent's mutation check, and did not certify API/token bodies, model accuracy or physical phone behavior. It requires an approved old-test-to-new-test mapping before semantic changes; builders must not weaken assertions to achieve green.

Proposed checkpoints: CP0 baseline; CP1 strict contracts/serialization/tamper/profile binding; CP2 migration/rebuild/retention/erasure; CP3 TLS/auth/origin/secret boundaries; CP4 ingestion/leases/backpressure/revisions/budgets/chaos; CP5 actual JS/Python controller equivalence and browser interruption simulations; CP6 resolver/unknown/lookalike/stale/caregiver/containment semantics; CP7 independent seeded adversarial replay plus full regression. These tests mostly DO NOT EXIST yet.

Each failure handback needs test/checkpoint ID, commit, exact command, fixture/seed, expected/actual, first traceback, owner and rerun. A missing harness or setup failure is blocked, not skipped-green. The test lead should own tests/fixtures/oracles; builders own production code. It must revise token/voice checkpoints to text-only retirement and chat/auth protections after the latest user change.

### Documentation lead report

Created RESEARCH_LOG/EVIDENCE/EXPERIMENTS and appended CLAUDE pointers. It registered external inputs, hashes, initial agent IDs, CP0 environment and unresolved claims; it did not approve a new architecture. It flagged that the 333ms moving-chair optical-flow failure was a code-derived risk in CLAUDE, not a supplied measured chair experiment. Preserve that distinction.

Its archival step was blocked/canceled. Parent has now preserved the supplied six Markdown files under `docs/review-inputs-20261006/` and available raw current Round-B reports in `docs/agent-round-b-raw.tar.gz`. Older documentation lines saying sources were not copied describe the earlier checkpoint. Its latest partial Round-B records are useful but do not mean all cross-review objections were resolved.

## 7. Consolidated intended architecture (proposal awaiting gate)

The broad direction remains:

```text
Phone camera/sensors/consent controls
  -> cheap non-neural motion gate + optional cleared hand model
  -> hand-only capture controller + bounded evidence retention
  -> authenticated, bounded episode packets + idle keyframes
  -> laptop per-episode localization
  -> image features / OCR / semantic index (cleared adapters only)
  -> private evidence store + versioned hypotheses
  -> current-state projection
  -> TEXT CHAT + authenticated STORED-ITEMS BROWSER
  -> query-specific photo/evidence, group, clarification or abstention
```

Rig: Safari and laptop; future native target moves compute/storage on-device but requires separate hardware evidence. No paid cloud on the normal write path. No speech or Deepgram for this build. No real model or synthetic fixture may be misrepresented as working production inference.

### Data and correctness invariants to retain

- Capture time and arrival/completion time are different; ordered histories use observation time plus explicit tie-breaking/session anchors.
- Episode/revision acknowledgements bind authorized household/device, episode, digest and revision; never acknowledge dropped bytes as durably retained.
- Malformed, unauthorized, cross-profile and over-limit traffic is rejected. 'Never error to the phone' cannot override validation/security.
- Same exact evidence is idempotent. Changed evidence is a controlled, bounded revision/conflict decision, not an overwrite. Privacy tombstones prevent resurrection after resend/replay.
- Relevance, actor and location are independent. Being handled does not itself prove ownership. Known items can be updated by observed non-wearer moves.
- New candidates should be searchable without multi-day enrollment. Background sightings do not catalogue all objects; bounded re-observation is for known items.
- Persistent item identity is not a detector category or raw tracker ID. Empty prediction sets are unmatched-candidate evidence, not proven novelty.
- Ambiguous matches do not update trusted banks. Failed geometry does not delete known cannot-links.
- Containment is inferred and preserves separate child/parent timestamps. Automatic containment is not validated by hand-labelled ledger tests.
- Unknown/out-of-bank/expired/unreliable evidence must not produce a confident current-location claim or an unrelated nearest photo.
- No fabricated frame padding, capture timestamps, consent, successful experiments, room names, medical contents or model accuracy.
- Retention applies to raw media AND personal SQL/derived content, caches, revisions and export/backup scope. 'Immutable' does not authorize indefinite personal-data retention.
- Cost/lease/accounting state survives restarts; stale workers cannot commit after reclamation; unknown spending is not released just because a timer elapsed.

### Likely components, not approvals or installations

- Browser hand library: Tasks Vision1.0.1 proposed instead of brand-new1.1.0; weight grant still needs primary evidence. Until cleared, use explicit fixture/manual mode for development, not fake live inference.
- Localization: gradient/structure difference with registration; sparse-flow support converted into an explicitly defined mask; measured optional segmenter. Failure yields context-only/uncertain evidence.
- DINOv2-S masked appearance features; SigLIP2 semantic/category assistance; PaddleOCR detection plus line recognition. Exact model, preprocessing, license, hash and runtime must be pinned.
- Identity/calibration: versioned banks/calibrations, unknown/group handling and empirical evaluation. Marginal in-bank conformal guarantees are not medication-subpopulation or E2E guarantees.
- Backend: Python/FastAPI, SQLite. Keep PERSIST until a secure WAL-directory/sidecar recreation lifecycle is demonstrated. STRICT support exists in the tested runtime.
- Frontend: existing vanilla HTML/CSS/JS and white/blue accessible styling unless an explicit decision changes it. No framework rewrite by default. Maintain large targets, keyboard/focus, readable text, low motion, truthful empty/error/pending states.
- Deferred: native app, real iPhone/model benchmarks, autonomous containment, surface atlas, Hand Sentinel training, local-LLM residue unless needed, speech, named caregiver accounts and real household pilot.

## 8. Open decisions: builders must not guess these

1. Packet schema and cross-language canonical bytes/IDs: distinguish normalized XY/signedZ from world XYZ; define exact timestamp units, bounds, rounding and transforms. Ack must include/bind content digest and authorization context. Do not expose/store auth cookies inside evidence packets.
2. Retained frame geometry: capture-resolution source for keyframes, analysis-resolution burst separately; causal first-valid burst; explicit pin counts/memory/lifetime; short episodes emit available unique evidence. No future midpoint logic. Current perception RoundB contradicts this with an analysis-only ring.
3. Controller exact thresholds/fallback behavior: world-landmark availability and low-fps handling, no hand/busy vs observed contact distinction, blur/head-turn gaps, refractory emission versus analysis. Measure, do not assert10fps inference.
4. Executable ledger/mutation design: reconcile immutable events, mutable jobs, versioned interpretations, erasure and promoted retention. Do not implement imaginary SQLite SET/role privileges. Cross-household relationships need enforced validation/constraints, not only a later join assertion.
5. Migration: explicit conversion from v1, dry-run/temporary-copy tests, IDs/order/budgets/unknown-spend/lease fencing preserved. Projection rebuild replays stored stage outputs, not new model inference. No real database/table drop without authorization.
6. Privacy deletion: choose tested logical/cryptographic redaction scope, address retained hashes/pseudonymous IDs and physical-copy limitations. VACUUM INTO creates another copy; it does not by itself erase old originals, backups or SSD history. Do not promise forensic erasure from a byte search.
7. Calibration: bank/model/recipe/tier/quality scope, invalidation, held-out chronology, open-set behavior and class/subgroup limitations. Don't auto-promote wrong singleton evidence or erase preserved negatives.
8. Answer precedence: five shapes proposed (confident, hedged, abstain, group, clarify); clarify transaction semantics and per-member image provenance/null rules. A stale reason only hedges when usable historical evidence exists; otherwise abstain. Current user wants text chat plus catalogue, not voice-oriented member limits chosen only for speech.
9. Authentication/provenance: all protected reads/writes/WS must fail closed even with missing DB; sharedPIN is not person identity. Reports may be generically attributed/claimed, not falsely authenticated named relatives.
10. Model permission/version gates: exact hand-weight grant unverified; converted copies are not a loophole. All newer/custom licenses and data/teacher lineage need records. No history scrub or declarations of breach from library presence alone.
11. Budgets: fixed-point monetary ledger, calendar windows, payload/model limits, conservative reservations and retry rules. No refund of possibly billed calls via TTL. Text-only scope excludes speech expenses and routes; external text LLM choice remains unapproved.
12. Test ownership and retirement: tester owns oracles/tests; preserve blocked security coverage under replacement routes. Remove unsupported feature claims in UI and add retirement tests for Deepgram/non-memory endpoints rather than merely deleting tests.

Architecture/readiness gate is NOT passed. The lead called its RoundB 'not freeze-ready until adopted'; other agents still conflict. A design-ready gate must be independent of post-build green tests, otherwise it is circular. Hardware/model/pilot gates cannot pass via software-only simulation.

## 9. Planned work order and ownership after the gate

### Immediate next steps

0. (CP2 done 2026-10-08; see `docs/BUILD_PLAN.md` for CP3 to CP5.) (Done at CP1, 2026-10-07.) Steps 2 and 4 below are closed for this milestone: the contract decisions are recorded, the legacy API tests are ported or retired with a map, and all six suites pass. Remaining from the architect's review: the scoped purge (two `ultralytics`/CLIP lines in `perception/requirements.txt`, four dead deps in `server/requirements.txt`, `perception/blockers/eval_epic.py`, the inert `_RETIRED_SOURCE` string in `server/app.py`) is still awaiting the user's explicit authorization; `docs/agent-round-b-raw.tar.gz` is still a tarball; the MediaPipe `hand_landmarker.task` model-card licence still needs a human to open the PDF.
1. Read this snapshot; verify git status without discarding uncommitted docs. Keep latest text-chat + memory-browser requirements explicit.
2. Consolidate a short architecture decision matrix with remaining contradictions resolved and assumptions marked. Update existing canonical spec only under the approved scope; supplied reviews are not authority to purge.
3. Finish TLS key enforcement and deliberate regeneration instructions. Existing pair must not be automatically overwritten on DHCP/expiry mismatch.
4. Add auth shim and trim server/browser legacy dependencies. Retire Deepgram/speech for current scope. Get every surviving API/security test body executing.
5. Implement protocol, migrated ledger/projection/retention and text-chat/catalogue interfaces against synthetic fixtures, with explicit checkpoint gates.
6. Add cleared perception adapters and actual JS/Python controller equivalence; then independent overall integrity tests. No fake inference result in ordinary mode.
7. Later: actual iPhone and real-world evaluation with appropriate device access/consent/legal review. Record unmeasured gates as such.

### Disjoint builder boundaries

- Builder A: perception/data production modules, packet types, localizer/embedder interfaces, ledger/migration/projection/retention, queues/budgets, Python controller. Not server/browser files or tests/docs.
- Builder B: server routes/auth/ingestion/chat/catalogue APIs, server-only cost/egress adapters, `phone/serve.py` TLS. Not browser JS, shared packet schema, tests/docs.
- Builder C: browser HTML/CSS/JS, camera controller/ring/worker/packet sender, text chat, stored-items browser, uncertainty/pending/evidence rendering, frame accounting. NOT `phone/serve.py`, server routes, ledger internals, tests/docs. Do not build speech/Deepgram now.
- Tester: independent test files, fixtures/goldens, simulation/integrity harness and verdicts. Builders receive failures and change production; a changed legacy expectation needs documented semantic approval.
- Documentation: CLAUDE/research records/spec changes approved by coordinator, source/cost/license registers, experiment history and final research/testing report.
- Coordinator: cross-review, final interface decisions, integration, selective commits and communication. No concurrent writers to the same file. Do not let agents independently stage/commit over each other.

## 10. Cost model: current scope and corrected arithmetic

Current scope is TEXT ONLY. Historical Whisper/Deepgram/TTS analyses are research inputs for a deferred feature. They must not be included as implemented services or assumed current recurring costs. The user has not chosen a paid text LLM. Default provider egress should remain off until configured/approved; ordinary local lookup has no per-query provider bill but still consumes local compute.

Prior agents' round-B margin table is NOT reliable. Coordinator independently recomputed the following hypothetical sensitivity with Decimal arithmetic:

`margin = (P - (0.029*P + 0.30) - A - 0.75 - S) / P`

P = monthly subscription, A = hypothetical metered API+storage allocation, S = support/onboarding allocation; hardware subsidy is zero in this particular table ONLY. Prices, support and hosting allocations are assumptions, not selected commercial terms or measurements. No app-store fee included.

| P | A1.10/S3 | A1.10/S8 | A5/S3 | A5/S8 |
| --- | ---: | ---: | ---: | ---: |
| $5 | -5.90% | -105.90% | -83.90% | -183.90% |
| $10 | 45.60% | -4.40% | 6.60% | -43.40% |
| $15 | 62.77% | 29.43% | 36.77% | 3.43% |
| $20 | 71.35% | 46.35% | 51.85% | 26.85% |
| $25 | 76.50% | 56.50% | 60.90% | 40.90% |
| $30 | 79.93% | 63.27% | 66.93% | 50.27% |

These are examples to expose sensitivity, NOT a guarantee costs stay below revenue. A small subscription can lose money with modest support/API expense. Recompute for the actual text-only implementation and actual channel/hardware/support choices. Do not automatically cut off human support using an API-budget mechanism.

Required future cost controls: per-household and per-provider caps; integer monetary accounting; bounded tokens/images/decoded audio only if that feature later exists; reservations made before egress; stale-completion fencing; receipts/idempotency; unknown outcomes held conservatively; local typed answers continue safely when optional budgets are exhausted. Fail closed on undefined price/model/policy. Limit CPU/memory/cache/revision growth as engineering resources too.

## 11. Evidence and legal/commercial boundaries

- AGPL is not NC. An import/dependency alone does not prove infringement. Avoidance is the chosen direction, but cleanup is not a license judgment or permission to conceal history.
- Current PAM does not contain the named MobileCLIP/YOLOE weight/EPIC-video paths checked by the parent. Relevant dependency/source references remain. Do not confuse the archive's artifacts with this repo or an evaluation script with a dataset.
- Public package metadata confirmed Tasks Vision1.1.0 published2026-10-06T17:55:06.100Z;1.0.1 published2026-07-31T21:03:39.261Z. Prefer aged reviewed dependencies, no floating latest. This is code/package evidence, not model-weight permission or benchmark evidence.
- Exact weights, upstream data/conversion/teacher provenance, license texts, versions/hashes and notices need their own artifact register. Primary sources outrank mirrors and peers' assertions. Custom DINOv3/SAM3, non-commercial datasets and unclear hand weights are not automatically cleared for this product.
- Deepgram prerecorded price/opt-out was independently checked historically, but its integration is now explicitly deferred. No provider call was made during research.
- Conformal coverage is marginal/in-bank under its assumptions; it does not guarantee full medication answers or conditional singleton error under distribution shift. Calibration sets need honest independent/cluster-aware evaluation.
- The documented333ms chair-flow failure was described as a code-derived risk in CLAUDE, not a provided physical-chair measurement. Do not turn it into experimental evidence.
- PTT/visible indicators do not universally establish consent. Deployment profile flags do not decide HIPAA status. FDA, biometric, recording, trademark and withdrawal/export conclusions require fact-specific human review. No IRB filing, BAA, trademark clearance, recruitment or household recording was performed.
- Real-world accuracy, camera recall, localization quality, instance identity and iPhone battery/performance remain unmeasured. Do not combine unrelated papers' metrics into an expected PAM success rate.70% remains a target, not a forecast.

### Current-agent literature leads and primary-source locators

These are agent-reported reading leads, not parent-replicated results or code/weight-use clearance. Check the exact experiment/table and license before making a paper claim:

- AMEGO: https://arxiv.org/pdf/2409.10917 — structured egocentric hand-object/location memory; relevant prior art, not evidence that PAM's end-to-end target is achieved.
- ESOM: https://arxiv.org/html/2411.16934 — online egocentric object memory; research agent emphasized the gap between actual pipeline and oracle tracking/discovery results.
- Risk Controlled Image Retrieval: https://ojs.aaai.org/index.php/AAAI/article/view/34931 — set-valued retrieval precedent; not an open-world medication-answer guarantee.
- Conformal prediction assumptions: https://arxiv.org/html/2107.07511v6 — retain exchangeability, marginal coverage and calibration-size caveats.
- MediaPipe coordinate/API reference: https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/web_js — parent checked distinct normalized image and world coordinates; this page is not exact-weight clearance.
- SAM3 source/license: https://github.com/facebookresearch/sam3 — current research candidate under custom terms, not adopted merely because it is newer.
- SAM2.1 candidate card: https://huggingface.co/facebook/sam2.1-hiera-tiny — agent-checked Apache card; actual laptop performance not measured.
- Paddle text-line recognizer: https://huggingface.co/PaddlePaddle/en_PP-OCRv5_mobile_rec — line recognition does not replace text detection/dewarping for arbitrary label crops.
- Exact artifact licenses, CUTE/PerMIR/RELOCATE data, other related work and historical vendor links are in the preserved external reports. Reading a paper's methods or reported numbers does not authorize downloading restricted datasets or shipping its checkpoint.

## 12. Safety and working conventions for the successor

- Never read or print `.env`, actual TLS keys, personal photos/audio/logs or private database contents just to inspect the project. IDE-open `phone/key.pem` is not authorization to paste it into a model.
- Use explicit PAM working directories; do not accidentally operate in hackmit. Quote paths containing spaces. Read files before editing. Preserve unrelated user changes.
- No broad server test discovery, no real-camera/provider calls in synthetic suites, no dummy import shims that hide missing production dependencies, no skipped-green tests.
- No source-file/directory deletion, real DB truncation/drop, certificate rotation over existing material, branch deletion/history rewrite, push, payment or external communication without specific authorization. Temporary files created by a test are a different scope from real user data.
- No updates to Git configuration; no force push or hook bypass. Existing three implementation commits are local. Documentation currently uncommitted must be preserved before any cleanup.
- Do not add frameworks/libraries without checking the existing stack and declared dependencies; prefer releases at least7days old. New assistant-tool configuration belongs in `.devin/`, not `.claude/` or `.cursor/`. This handoff is ordinary project documentation, not tool configuration.
- Existing visual guidance preserves the white/blue accessible UI and Tabler assets. Marketing-design defaults are not appropriate here. Do not invent photos, patient metrics or successful memories in ordinary UI states. Simulations must be explicitly labeled.
- Keep research docs truthful and current: distinguish planned/implemented/tested, localOS/sim/device/pilot, primary/peer/unverified claims. Keep failed experiments and corrected statements, not only successful runs.

## 13. How to resume efficiently

Use this as a starting prompt for Claude:

> Continue PAM in `C:/Users/anees/My Programs/PAM`. Read `docs/CONTINUATION_HANDOFF.md`, then CLAUDE and the research index. Preserve uncommitted research documents and the three local implementation commits. Latest scope is a text chatbot plus an authenticated stored-items browser; do not integrate Deepgram or speech now. Architecture cross-review is not yet fully resolved and the three builders have not started. First reconcile the specific open contracts and review incorrect agent claims; do not blindly execute purge/history instructions. Complete TLS/auth/app bootstrap and then the approved data/recorder work in separate tested checkpoints. Use synthetic data and no paid calls, real private data or household recording. Keep exact test counts and provenance; do not claim phone/model accuracy from simulations. No push or destructive operations without my specific approval.

Devin usage visibility: this agent cannot inspect remaining account quota. Devin documents `/session-stats` (`/stats`) for session consumption and `/usage` in supported CLI sessions; those are not a guaranteed remaining-account-budget feed to the model. `/export` shows export information, while the CLI `--export [PATH]` option enables per-turn ATIF conversation export. If a complete verbatim session is required, preserve/export it from Devin as well; do not pretend this handoff is a lossless transcript.

Update this file after every material checkpoint with HEAD/tree state, latest user scope, what actually changed, tests that ran versus blocked, agent corrections, and remaining human gates. Keep updates concise but sufficient to continue without replaying the entire chat.
