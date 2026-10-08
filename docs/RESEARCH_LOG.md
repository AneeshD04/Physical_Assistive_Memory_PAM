# PAM research record: index, decisions and limitations

## Latest continuation update — 2026-10-07

Read [CONTINUATION_HANDOFF.md](CONTINUATION_HANDOFF.md) first for the current
operational state and per-agent round summaries. Latest user instructions:
**include** the stored-items/memories browser (the earlier negative was a typo),
and use **text chat with no Deepgram or speech integration in this build**.
Capture, local processing/indexing, database writes and authenticated browsing
must work without chatbot credentials; only optional user-initiated cloud chat
may require an API key. Provider errors must not stop memory collection.
`T-NO-CHAT-KEY` in the handoff is a required, unexecuted integration gate.
These are requirements, not completed implementation. Earlier voice plans below
are historical/deferred. The coordinator has now closed the **design gate for the
first functional software milestone** in [BUILD_CONTRACT.md](BUILD_CONTRACT.md)
and started three builders plus the test lead. No builder completion or post-CP0
verdict has been supplied to this record; model/device/pilot gates have not passed.
Authority: existing v4 broad principles + latest user scope + BUILD_CONTRACT for
this milestone. Agent “freeze-ready” claims are not authority.

The coordinator resolved the archival execution blocker: supplied reports are
now preserved under `review-inputs-20261006/`, and four available verbatim current
Round-B responses are in `agent-round-b-raw.tar.gz`. The handoff maps the members
and explains remaining transcript limitations. Earlier D-012/X-DOC-002 blocked
entries describe their checkpoint, not the latest archival state.

The cost agent's Round-B scenario table still had arithmetic errors. The handoff
contains independently recomputed hypothetical margins and corrects the agent's
misreading of `ObjectStore.fail`: only never-sent calls are zeroed; sent/unknown
outcomes retain their reservation. Do not treat peer signoff as verified profit.

Historical initial/Round-B checkpoint, **2026-10-07**, code `d94cc5d`: seven initial
reviews were complete and the coordinator had relayed cross-review, but builders
had **not yet started** and gate decisions were pending. Preserve that chronology.
The later scoped decision **D-015 / A-025** changes the current work state above;
X-006 / CP0 remains the latest completed test checkpoint in this record.

## Authority and navigation

This is the index for research provenance, not a replacement implementation spec.

| Record | Purpose and authority |
| --- | --- |
| [MEMORY_SYSTEM_V4.md](MEMORY_SYSTEM_V4.md), **Part 1** | Broad v4 principles and historical revision-4 go-ahead. Original text retained, with an additive scoped-milestone pointer; not a full v5 rewrite or performance result. |
| [BUILD_CONTRACT.md](BUILD_CONTRACT.md) | Coordinator-approved exact contract for the first functional software milestone, read-only to DOC. Governs conflicting peer proposals within that scope, together with latest user requirements. |
| [CONTINUATION_HANDOFF.md](CONTINUATION_HANDOFF.md) | Current work state, tester-owned retirement mapping and corrected hypothetical cost table; research/model/pilot gates are separate. |
| [ROUND4_RESPONSE.md](ROUND4_RESPONSE.md) | Historical review disposition and the steps 1–2 go-ahead. Its line references belong to the commit it cites, not necessarily today's file. |
| [../CLAUDE.md](../CLAUDE.md) | Existing historical methods, measurements, failures and implementation notes. Preserve their dates, devices, prompts and checkpoint scope; the HackMIT sections are not the current design authority. |
| This file | Decision states, review-claim caveats, approval workflow, limitations and update format. |
| [RESEARCH_EVIDENCE.md](RESEARCH_EVIDENCE.md) | Stable source IDs, versions, hashes, rights/provenance gaps and independently checked metadata. |
| [RESEARCH_EXPERIMENTS.md](RESEARCH_EXPERIMENTS.md) | Checkpoint history, expected versus actual results, failures, fixes, reruns and unexecuted protocols. |

The supplied final architecture review and four domain reports are **external inputs**.
Their words “approved,” “resolved,” “Build,” and their instructions to purge,
rewrite history or publish a new spec are the reviewers' positions, not project
approval or legal advice. Their `[V]` means that reviewer says they opened a page;
`[V-peer]` is indirect evidence; neither means this project independently verified
the claim. Do not silently import these verdicts into Part 1.

## Evidence vocabulary

Use both a verification label and a claim type; checking a source exists is not
checking its conclusions.

- **Verified here / observed:** directly inspected source bytes, command output
  or public metadata, with the scope and date recorded.
- **Reported / observed elsewhere:** coordinator or existing log reports a run;
  not rerun by the documentation lead. Missing raw logs remain missing.
- **External claim / unverified here:** a review or citation asserts it. Record
  primary versus secondary source and the unresolved question.
- **Proposal / predicted / target:** a method, estimate, threshold or planned
  experiment. Never put it in an “actual result” cell.
- **Unknown / not run:** absent evidence, blocked setup, uncollected footage or
  an unanswered license question. “Not run” is not a pass or a zero error rate.

Decision states are `proposal`, `accepted`, `rejected`, `deferred`. Every change
of state needs the decision-maker, date, scope, rationale and evidence IDs.
`Accepted` is not synonymous with implemented, tested, commercially cleared or
approved for a pilot. Preserve superseded decisions and failed runs by ID.

## Baseline at intake

Read-only Git checks found HEAD `d94cc5da1928384ed08bcca4e38811aade16d43a`,
`main` clean and three commits ahead of the local `origin/main` reference on
2026-10-07. No fetch was done; this does not establish the remote's live state.
The tree was clean **before these documentation additions**.

| Commit | Scope reported by the coordinator and recorded in existing notes |
| --- | --- |
| `f545c5b217d65f239fc801457ffbd84f94821bc6` | Static public-file allowlist; valid temporal evidence; explicit TLS certificate generation configuration. |
| `011baa43b2a259ffa36045e0279afddd81ac83de` | Exact rejection-message assertions; actual-phone-folder deny checks; SQLite close regression sensitivity evidence. |
| `d94cc5da1928384ed08bcca4e38811aade16d43a` | Standalone private-file utility removes the scheduling dependency from the retained memory store. |

Initial **reported** handoff: capture **8 pass**, interaction **7 pass**, lifecycle
**61 pass**, private-file **6 pass**; pipeline **36 pass / 23 setup errors** (X-005).
The fresh tester run **X-006 / CP0** confirms the same counts: **141 methods,
118 pass, 23 setup errors, 0 assertion failures, 0 skips**. Documentation inspected
the supplied pipeline log, not the other four raw logs, and reran no tests.
The `doses` import blocks ObjectApi 12, CameraRelay 7 and Token 4 bodies; their
assertions remain unverified. Neither checkpoint is “all tests green.”

TLS key ACL protection was a **manual Windows action**, not an `ensure_cert`
guarantee. The app/auth split and v4 data model remain pending. Removing and
restoring `db.close()` demonstrated a regression test's sensitivity, **not a new
SQLite fix**. No current model, camera, native-device or pilot accuracy is validated.

## Roles and gate workflow

- **Coordinator:** supplies explicit gate dispositions and reconciles independent
  reviews. Only a relayed decision with scope and evidence can advance a gate.
- **Architect:** proposes contract/schema changes and their dependencies; identifies
  contradictions and the exact canonical edits required if approved.
- **Tester:** records commands, environment, fixture provenance, counts, failure
  phase, logs and reruns; distinguishes isolated tests from device/model evaluation.
- **Provenance/security reviewer:** separates code, weights, data, conversion,
  vendor and consent terms; names primary-source gaps and counsel questions.
- **Documentation lead:** consolidates these records under `docs/` and appends
  factual pointers to PAM's `CLAUDE.md`; does not approve architecture or edit code.
  This task does not authorize credentials/media changes, Git mutation, paid APIs,
  model downloads or real household capture. Tool configuration is not research
  documentation; any future new tool configuration belongs only in `.devin/`.

| Gate | Current disposition | Evidence needed before the coordinator can decide |
| --- | --- | --- |
| G-ARCH: first functional software DESIGN | Accepted by coordinator, 2026-10-07, A-025/A-029 | BUILD_CONTRACT governs this milestone; builders started. Full v5/model/pilot approval is not implied. |
| G-TEST: software integration/independent integrity | Pending; CP0 still has 23 setup errors | Tester owns the approved retirement/replacement map, keyless ingest/process/restart/catalogue gate and independent verdicts. No completed builder report or post-CP0 result supplied. |
| G-PROV: artifacts and permitted use | Pending | Actual scoped inventory; pinned code/weight/data identities; primary terms and intended-use assessment. No blanket legal clearance. |
| G-PRIV: retention and deletion | Pending | Data-class map covering SQL and derived copies, not just files; an approved deletion/replay policy and synthetic deletion tests. |
| G-RIG: model/device experiments | Not run; actual iPhone testing later per user | Agreed protocol, permitted fixtures, exact package/model/device pins, delivered-frame accounting and recorded failures. |
| G-COST: subscription feasibility | Pending; assumptions only | Small per-user subscription sensitivity at $5/$10/$15, without selecting a price or market; bounded token/image/audio spend and measured workload before margin claims. |
| G-PILOT: household recruitment/recording | Not authorized by this record | Institutional/IRB determination, consent and bystander plan, safety/retention/data-flow review and explicit authorization. |

A gate record must name who decided, when, affected revision, evidence and remaining
exceptions. A peer's agreement inside an external report does not satisfy a gate.

## Decision register

All intake rows were recorded on 2026-10-07; historical acceptance dates stay separate.

| ID | State | Decision or proposal; rationale and evidence | Authority / next action |
| --- | --- | --- | --- |
| D-001 | accepted (historical) | Part 1 remains authoritative; existing steps 1–2 go-ahead is in A-001/A-002. Preserve that history without treating subsequent external changes as approved. | Existing revision-4 decision, exported 2026-10-05; coordinator resolves new gates. |
| D-002 | accepted (workflow only) | Keep a linked, compact research record; preserve methods, negative results and provenance without copying large reports into new summaries or exposing personal data. | User's documentation assignment; this intake implements that scope only. |
| D-003 | proposal | External BL-1 through BL-11, new components, `group`/`clarify`, conformal identity, re-observation index and build-order changes (A-010/A-013–A-016). Review agreement is not evidence of an implementable or validated contract. | Architect and coordinator; G-ARCH. No Part 1 edits yet. |
| D-004 | deferred | App/auth trim and v4 data-model work remain outside this documentation pass; missing imports explain blocked coverage, not passing integration. | Coordinator assigns implementation scope; tester reruns X-005 after the change. |
| D-005 | rejected (instruction authority only) | Execute the supplied “purge/history rewrite” as an automatic instruction. The review is evidence to assess, not authorization; legal breach and current-artifact claims need checking (C-01/C-02). | User expressly forbids deletion/Git mutation in this task. No removal or history rewrite performed. |
| D-006 | proposal | A retention/deletion design must handle personal SQL text and derived data as well as media; blanket row immutability cannot be assumed to satisfy deletion (C-04). | Architect, privacy reviewer and coordinator; G-PRIV. No retention constants approved. |
| D-007 | proposal | Separate world-space hand geometry from image-space localization coordinates; explicitly preserve carry-burst evidence for long episodes (C-06/C-07). | Architect/perception reviewer; freeze units, lifetime and testable invariants before implementation. |
| D-008 | proposal | Treat conformal identity as a conditional statistical method with empirical evaluation, not an end-to-end medication safety guarantee (C-05). | Memory reviewer/tester specify calibration, open-set and bank-update protocols. |
| D-009 | deferred at initial intake; permission superseded by D-012 | At initial intake no stable archive was created; only hashes and source locators were registered. The original ZIP remains outside the repository. | Round B authorizes preservation (D-012), but tooling blocks execution; see X-DOC-002. No source has been copied or overwritten. |

## Unresolved external-review claims

These are review flags, not substitute architecture decisions or legal opinions.

| ID | Claim needing correction or a gate | Evidence and required treatment |
| --- | --- | --- |
| C-01 | AGPL treated as non-commercial or mere presence treated as a proven breach | A-016 component register and A-010 §4 overstate this. AGPL is a copyleft license, **not an NC license**; its text permits charging and running unmodified programs (A-021). Particular obligations depend on covered work, modification, distribution and network use. Check exact artifacts and facts; no project legal/commercial clearance is implied. |
| C-02 | Named old models/video are in today's PAM tree/history | A-010 §4 names `mobileclip2_b.ts`, `mobileclip_blt.ts`, YOLOE weights and `perception/data/epic/P02_102.MP4`. Coordinator reports the named old model/video artifacts absent from the current checkout/history. This intake did not repeat that inventory. Keep archive/HackMIT observations separate from PAM; obtain audited commands, refs, ignored-file scope and date before concluding absence or planning any removal. Absence does not settle dependency or license obligations. |
| C-03 | Switching to ONNX/OpenCV Zoo cures an unclear hand-weight license | A-014 §A and A-016 round-2 item 2 rely on secondary attribution while the primary model card was unreachable. A conversion or permissive wrapper does not cure unresolved upstream weight/data rights. Require the original weight grant, conversion provenance, exact checkpoint/hash and applicable notices before use. Package metadata alone is insufficient. |
| C-04 | Delete media but retain immutable SQL rows forever; withdrawal only changes the head source | A-015 §B includes `reports.raw_text`, `hypotheses.payload/source`, OCR fields, embeddings and old versions. Those can retain personal information after file deletion or source hashing. Design deletion/redaction for SQL, derived views, indexes/banks, revisions, browser caches, exports, backups and WAL/journals; distinguish minimal audit metadata from identifying content. Test deletion without resurrecting data on replay. No PII belongs in this documentation. |
| C-05 | Conformal alpha controls end-to-end confident-wrong medication answers | A-015 §C conditions coverage on an in-bank true label and exchangeability. It does not cover missed capture, wrong localization, novel/out-of-bank items, stale location, evolving banks, domain shift, post-selection/conditional singleton risk or the whole answer chain. Pin calibration and bank versions; score all queries and medication separately. No calibrated model or guarantee exists at this checkpoint. |
| C-06 | Normalized landmarks can stand in for world-space geometry | A-010 BL-4 normalizes packet landmarks; §2 and A-014 §B propose curl from `worldLandmarks`. Define both representations and units, frame IDs/times, crop/resize/mirror transforms and missing/interpolated values. Image x/y normalization is not a metric 3-D hand representation; do not assume normalized z has x/y units. |
| C-07 | A rolling 2-second buffer always contains a carry-midpoint burst at episode close | A-013 BL-2/BL-3 and A-014 §C propose up to 10 frames at 10 fps and a 150 ms gap guard. A long carry can overwrite the midpoint before close. Specify a pinned burst or equivalent bounded snapshot policy, ownership, memory limit, timestamps, release and failure behavior. These rates/thresholds are proposals, not measured guarantees. |
| C-08 | MediaPipe Tasks Vision 1.1.0 is unavailable, or its recency establishes performance | A-020 independently confirms publication **2026-10-06T17:55:06.100Z**. It is a recent release. Pin JS/WASM/model assets together and benchmark the actual combination; older TF.js/browser figures do not validate it. Runtime/API/delegate compatibility and `.task` rights are not verified by the registry. |
| C-09 | The 333 ms optical-flow failure was measured on a moving chair | A-013 BL-2 and A-014 §C describe it as observed. A-003 lines 175–190 explicitly separate a code-derived chair risk from measured ego-motion timings; no corresponding chair trial is supplied. Preserve it as predicted risk, not a fabricated experiment. |
| C-10 | “76 tests green,” novelty, market costs or regulatory assertions are current evidence | A-010 §§1, 6–9 are external assertions/targets. X-005 preserves the initial handoff and X-006 / CP0 is the fresh tester run; literature metrics are task-specific, not directly comparable PAM outcomes. Pricing is date/payload-dependent; FDA, HIPAA/FTC, recording, biometric, mark and export/withdrawal claims need fact-specific expert review. No novelty, clearance or gross-margin claim is established. |

## Round B — coordinator relay, 2026-10-07

Source **A-022** is the coordinator's relay, not direct peer messaging or newly
approved contracts. All seven agents completed their initial reports; cross-review
has been relayed and **builders have not started**. These agent IDs identify the
current review team, not necessarily the authors of the supplied October 6 package.

| Role | Agent ID | State at relay |
| --- | --- | --- |
| ARCH | `2da46caf` | Initial report complete; cross-review open. |
| PERCEPTION | `7537ab41` | Initial report complete; cross-review open. |
| MEMORY | `f88ef336` | Initial report complete; cross-review open. |
| COMMERCIAL | `f5fb648a` | Initial report complete; cross-review open. |
| COST | `11282b95` | Initial report complete; cross-review open. |
| TEST | `10410cae` | Initial report complete; fresh CP0 recorded as X-006. |
| DOC | This documentation agent; no ID supplied in the relay | Initial record complete; consolidating Round B. |

### Round B decision-register additions

The accepted rows below are **user constraints, reporting corrections or archival
permission**, not architecture approval. All implementation gates remain pending.

| ID | State | Scope, rationale and authority |
| --- | --- | --- |
| D-010 | accepted (user constraint) | Cost analysis assumes a **small per-user subscription**, with no fixed price or market selected. $5/$10/$15 are sensitivity scenarios, not offered prices. Source: A-022. |
| D-011 | deferred (user timing) | Actual iPhone testing happens later. No present claim of Safari/model/device latency, stability or accuracy. Source: A-022; G-RIG remains not run. |
| D-012 | accepted (archival permission); execution blocked | User authorizes byte-preserving snapshots of the provided ZIP/Markdown under a new non-conflicting `docs/review-inputs/` location, labeled external/unapproved. Supersedes D-009's permission question only. Does not authorize purge, execution, history rewrite or source overwrites. No suitable copy/archive tool is available; X-DOC-002 records the blocker. |
| D-013 | accepted (arithmetic correction only) | With the hypothetical $25 receipts, $1.03 fee, $5 API and $0.75 hosting inputs, residual is **$18.22 / $25 = 72.88%**, not at least 75%. A-024 verifies arithmetic only; inputs and cloud margins remain assumptions, and $25 is not a selected subscription price. |
| D-014 | proposal | Prefer Tasks Vision **1.0.1** over the just-published 1.1.0 for initial stability assessment. A-020's observed 1.1.0 release date remains true. Neither version's runtime, complete asset pins or weight rights are validated here; no package change/download authorized. Source: A-022. |

### Cross-review blocker register — all OPEN

These are coordinator-relayed corrections and unresolved requirements, not measured
failures of a new implementation. Keep the original reports intact as provenance,
but do not carry their factual mistakes forward as accepted decisions.

| ID | Open issue / relation to initial flags | Evidence or contract still needed |
| --- | --- | --- |
| B-01 | ARCH's future-midpoint pin is non-causal (C-07). | A live controller cannot know the eventual carry midpoint before the carry ends. Specify a causal, bounded retention/selection rule that still works on long carries; “pin the future midpoint” is not an implementable fix. |
| B-02 | Raw ring-buffer versus analysis-resolution frames are ambiguous (C-06/C-07). | Name actual stored resolutions/representations, source-frame ownership, transforms, burst extraction, memory bounds and release/failure behavior. Do not infer capture-resolution evidence from analysis-only buffers. |
| B-03 | PERCEPTION drops hard negatives when homography fails. | Separate unavailable registration evidence from already established co-visibility/identity exclusions. A failed homography must not erase valid hard-negative constraints. Define and test unknown behavior without inventing a positive match. |
| B-04 | MEMORY still describes AGPL presence as a breach (C-01). | Correct the assertion: AGPL is not NC and presence alone establishes no breach. Review exact covered artifacts and use/distribution/network facts; do not promote wording from a peer report to a legal finding. |
| B-05 | Primary model-weight license gap persists; ONNX is not a cure (C-03). | Obtain the applicable original weight grant and conversion/data provenance; distinguish package/code notices from model rights. No commercial clearance from a conversion. |
| B-06 | MediaPipe pin choice remains open (C-08/D-014). | Record version-specific JS/WASM/model identities and terms; evaluate 1.0.1 preference without calling the verified 1.1.0 release nonexistent or either version benchmarked. Device testing is later. |
| B-07 | True SQL personal-data erasure is missing (C-04). | Explicit deletion/redaction of personal text and all identifying versions/derived copies, including replay and backup/export policies. Media deletion or changing only the latest source is insufficient. |
| B-08 | Proposed SQLite role-bypass mechanism is not real. | SQLite has no ordinary built-in `SET`/`PRAGMA` role bypass for immutable-row triggers. Define an actual, scoped administrative erasure mechanism and its authorization/tests; a generic SQL role-switch placeholder is not an implementation. |
| B-09 | WAL sidecar recreation privacy is unverified. | Test owner/privacy guarantees for creation and recreation of `-wal`/`-shm` and applicable journals, not just the main database. The six existing private-file tests do not by themselves settle this surface. |
| B-10 | Actual v1 migration is not a projection rebuild. | Define source schema/version, transformations and preservation/deletion rules for real v1-format fixtures, transactional failure/recovery and validation. Recomputing a new derived view is not legacy-data migration. |
| B-11 | Clock-only staleness and replay `as_of` are unspecified. | Answers must age without waiting for another write. Define observation time, evaluation/as-of time and deterministic replay semantics; do not reuse a previously fresh projection indefinitely. |
| B-12 | Read/write/WebSocket authorization must not depend on database presence. | State fail-closed behavior for absent/corrupt/unconfigured databases, before reads, writes or relay connection. Previously blocked security tests are not evidence this is implemented. |
| B-13 | No automatic overwrite of real certificate material. | Preserve non-overwrite/partial-pair behavior; any real rotation requires an explicit separate authorization. Certificate tests use temporary/synthetic fixtures, not replacement of the user's pair. |
| B-14 | Per-member answer precedence is unresolved. | A deterministic contract and fixtures for conflicting, stale, inferred, reported, matched and unknown evidence per member; group presentation cannot silently upgrade any member's certainty or identity. |
| B-15 | Caregiver PIN is not named-person identity. | Distinguish role/session authorization from attribution to a particular caregiver. Do not narrate a named reporter as authenticated solely by a shared PIN. Define provenance and consent separately. |
| B-16 | Revision ACKs must bind to digests and actual durability. | Bind episode/revision/disposition to submitted and stored content digests. Duplicate/conflict/revision handling must not acknowledge dropped bytes as durable; specify cap/truncation/retry behavior and test it. |
| B-17 | Subscription economics and spend bounds remain assumptions. | Use D-013's corrected arithmetic; provide $5/$10/$15 sensitivity with a stated fee model and cost inclusions. “Five calls” cannot bound dollars without token/image/audio limits, retries/concurrency and provider-price assumptions. No measured cloud margin exists. |

All review runtime forecasts and cloud-margin figures are **assumptions until
measured** on the stated configuration/workload. Historical scoped measurements
remain historical; they do not validate a new stack. The corrected $25 arithmetic
is conditional on the supplied hypothetical inputs and omits any costs not named;
it is not a measured gross margin or a market decision.

## Limitations for any paper or public claim

- Existing synthetic tests exercise the implemented checkpoint, not the proposed v4
  vision pipeline or its real-world reliability. API/relay/token assertions are blocked.
- No new detector, localizer, identity, OCR, STT, camera, phone, thermal/battery or
  household pilot evaluation was run here. No training, paid call or capture occurred.
- The 70% end-to-end number in Part 1 is an **initial target**, not a prediction or
  result. Component rates, external papers and an illustrative 69% product of rates
  cannot validate it. Report all-query outcomes, abstention/coverage and confident-
  wrong medication separately; historical fidelity is not current usefulness.
- Historical figures in CLAUDE.md stay attached to their old setup. Rig results
  cannot establish native power, NPU speed, offline behavior or background capture.
- Missing raw logs, artifact permissions, exact environment fields and calibration
  data remain explicit gaps. A digest identifies bytes, not authorship, truth or rights.
- Local tests do not establish phone trust/handshake or automated TLS-key ACLs.
  Reported Python/OpenSSL versions are old; production readiness is not established.

## How to send updates for consolidation

Send a short packet to the coordinator, who relays it to the documentation lead.
Do not silently edit shared decision rows while reviews are still independent.

```text
Kind: decision / evidence / run / correction
ID: existing D-/C-/B-/A-/X-/P- ID, or proposed new ID; supersedes if applicable
Author role and timestamp:
Scope: commit + dirty diff/version; spec/contract revision; rig vs native
Sources: repo-relative file:lines or public URL/version/date; artifact IDs/hashes
Method: protocol, command/selectors, fixtures and rights/consent provenance, environment
Expected:
Actual: pass/fail/error/skip or metric + denominator; not run/blocked if appropriate
Failures and exclusions: phase, exact safe error, negative results, fixes and rerun IDs
Artifacts: sanitized log/result locations and hashes; inaccessible/missing items
Decision requested or relayed: state, rationale, gate, decision-maker/date/conditions
Remaining uncertainty:
```

Never send keys, tokens, participant names, addresses, OCR of real labels, raw
household media or caregiver transcripts into these docs. Use non-identifying
artifact IDs and controlled-access references; do not publish hashes of secrets.

**Questions awaiting the architect:** Supply coordinator-relayed dispositions for
B-01–B-16 and the earlier C-flags, with revised invariants and tests. In particular,
resolve causal burst retention/resolutions, hard negatives, full SQL erasure and
WAL privacy, actual v1 migration, clock/as-of behavior, unconditional authorization,
per-member answers, caregiver attribution and digest-bound durable ACK semantics.

**Questions awaiting the tester:** Supply exact CP0 invocations, run timestamps,
remaining four suite logs and an environment/dependency manifest; do not assign
CP0's environment retroactively to older runs. After approved app/auth work, do
all 23 blocked bodies run without legacy imports, skips or weakened assertions?
Name proposed synthetic migration/deletion/sidecar/clock/ACK/auth cases separately
from later iPhone/model tests. The parent mutation experiment was not repeated in CP0.

**Questions awaiting COST/provenance via the coordinator:** Provide $5/$10/$15
sensitivity, fee formula, cost inclusions, workload and enforceable token/image/audio
budgets; identify assumptions versus measured inputs. Supply missing primary weight
terms and version pins. Arrange an authorized byte-copy/archive capability for
D-012, then report destination manifests/hashes; the present tooling blocker is
not a refusal of the user's preservation instruction.
