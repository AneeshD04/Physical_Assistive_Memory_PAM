# PAM experiment and checkpoint ledger

Intake date: **2026-10-07**. Parent index: [RESEARCH_LOG.md](RESEARCH_LOG.md).
Source IDs resolve in [RESEARCH_EVIDENCE.md](RESEARCH_EVIDENCE.md).

**The documentation lead ran no application tests, models or camera experiments.**
X-001 through X-005 preserve the initial reported checkpoints. **X-006 / CP0** is a
fresh tester execution relayed in Round B, with its pipeline log inspected here;
it is not a DOC rerun. X-DOC entries are documentation/provenance checks. P-IDs
remain proposals, not results. Preserve failed and blocked runs when adding reruns.

## Initial-checkpoint environment and fixture scope (X-001–X-005)

A-003 lines 798–909 and A-000 identify a Windows laptop, PAM as working directory,
`PYTHONPATH` cleared, using the existing archive virtual environment **only as a
Python/dependency runtime**, not as permission to import omitted application code.
Reported versions: Python **3.11.0**, Python SSL OpenSSL **1.1.1q**, CLI OpenSSL
**1.1.1s**. At that checkpoint there was no PAM-local venv and no package/model
installation. These are historical environment statements, not a new runtime probe.

At initial intake, exact OS build, CPU/RAM, dependency lock/hash, run timestamps,
stdout/stderr hashes and complete original command lines were not supplied for
these older runs. CP0 below supplies its own environment and pipeline-log hash;
do not retroactively assign them to X-001–X-005. Commit associations do not replace
a contemporaneous run manifest. Phone/browser/delegate fields remain unknown for
later device/model experiments.

Fixture source is the test code at the associated commit, not household footage:

- `perception/test_capture.py`: constructed packets, timestamps and location cases.
- `perception/test_interaction.py`: synthetic interaction-state sequences.
- `server/test_memory_lifecycle.py`: temporary stores, injected clock, synthetic
  evidence and network guards (header and `MemoryFixture`, lines 1–49 at intake).
- `server/test_personal_pipeline.py`: synthetic frames/configuration, mocked
  provider boundaries and guarded external I/O; its actual-phone-folder test is
  an in-memory handler test with content opens forbidden, not a live TLS session.
- `perception/test_private_files.py`: synthetic temporary-file bytes, owner/DACL
  checks and injected permission/owner faults (lines 15–98 at intake).

This pass read/inspected test sources only. Passing current tests is not validation
of the new v4 architecture, of model semantics or of all security/deployment cases.
The standalone storage utility's Windows ACL tests do not prove TLS-key generation
uses that utility; the TLS ACL step was manual.

## Checkpoint history

### X-000 — earlier review baseline (historical pointer)

A-001 Part 2 line 426 and A-002 line 55 retain **42 of 49 integration tests passing
before the SQLite cleanup fix, not rerun at the time**. Exact run manifest and raw
logs are not supplied here. Do not combine that denominator with today's 59-method
pipeline suite. Later tests changed; old failures remain part of the history.

### X-001 — TLS generation failure and manual verification

- **Associated change:** `f545c5b`; source A-003 lines 804–822.
- **Protocol / expected:** public-file allowlisting; generate a fresh local TLS
  pair without overwriting an existing complete pair or accepting a partial pair;
  verify server certificate, matching key and SSL loading. No private material is
  included in this record. Exact original OpenSSL/ACL command lines are not supplied.
- **Actual, reported:** inherited OpenSSL configuration plus an added `CA:FALSE`
  emitted duplicate Basic Constraints (`CA:TRUE` and `CA:FALSE`); verification failed.
- **Fix / rerun, reported:** supply an explicit OpenSSL configuration on stdin,
  SHA-256, SANs and server-authentication usage. A fresh ignored pair then passed
  OpenSSL certificate verification, key consistency and Python SSL matching-pair load.
  Existing complete pairs are reused; partial pairs are refused.
- **Manual action:** protected Windows DACL on the key, owner-only with inheritance
  disabled. This is **not code-level `ensure_cert` ACL enforcement**.
- **Limit:** no trust-store change, live server or phone session. Safari trust and
  actual browser handshake remain unverified. Actual pair contents/addresses stay
  outside this log; no key hash is recorded.

### X-002 — first isolated suite run after the split

- **Checkpoint association:** `f545c5b`; source A-003 lines 823–856.
- **Protocol / expected:** direct file-based isolated unit/integration suites;
  expectation was execution of the requested test bodies, not merely discovery.
- **Actual, reported:** capture 8 pass; interaction 7 pass; lifecycle 0 pass / 61
  setup errors; pipeline 20 pass / 38 setup errors. No assertion failures or skips
  reported. All **99 setup errors** were missing `server.schedule`.
- **Failure cause:** `ObjectStore._private_file()` still depended on a utility in
  the omitted scheduling application. API/app import boundaries also needed work.
- **Fix disposition:** retain the SQLite store and port only its private-file
  utility, not the old medication/scheduling application. X-005 is the later rerun.
  Passing verifier/static/certificate tests did not establish storage or API coverage.

### X-003 — exact-error and actual-folder regression strengthening

- **Checkpoint:** `011baa4`; source A-003 lines 864–880.
- **Protocol:** align media fixtures' capture timestamps, then assert intended
  errors exactly: `Unapproved event image`, `Invalid event image`, `Event image too
  large`. Exercise GET and HEAD denials against the actual `phone/` directory,
  guarding Python content opens and asserting none occurred; no socket is opened.
- **Expected:** tests cannot pass on an unrelated temporal error; private/traversal
  requests return 403/404 without reading private content. Separate captures with
  identical pixels are valid when resolved paths and capture times are distinct.
- **Actual, reported:** assertions satisfied. Requested verbose pipeline run grew
  to **59 methods: 21 pass / 38 setup errors**, all missing `server.schedule`.
  Blocked classes: SyntheticFrame 10, WorkerBoundary 5, ObjectApi 12, CameraRelay 7,
  Token 4. This was a coverage improvement, not a green integration suite.
- **Follow-up:** X-005 removes the storage import blocker; remaining app imports
  are separately reported. No real key contents were read by these denial tests.

### X-004 — SQLite close regression sensitivity, not a new fix

- **Checkpoint:** `011baa4`; source A-003 lines 850–863.
- **Protocol:** temporarily replace `ObjectStore._connection`'s existing
  `db.close()` with `pass`, run the isolated regression, restore the original line
  and rerun. The test mocks the private-file-writer boundary only.
- **Expected:** mutant fails at the connection-closed assertion; restored source passes.
- **Actual, reported:** mutant failed at `connections[0].closed`; restored version
  passed. The temporary production mutation was fully restored by its author.
- **Interpretation:** sensitivity evidence for this regression test. It is **not a
  new SQLite fix**, not proof of the missing dependency, and not full API coverage.
  This documentation pass did not repeat or perform any mutation.

### X-005 — initial handoff baseline: standalone private storage

**Checkpoint:** `d94cc5d`; A-003 lines 894–909 and A-000.
Change: `perception/private_files.py` ports only the private-append primitive and
Windows support; the retained store uses it without scheduling imports.

| Suite | Expected test methods | Passed | Assertion failures reported | Setup errors | Scope of actual result |
| --- | ---: | ---: | ---: | ---: | --- |
| `perception/test_capture.py` | 8 | 8 | 0 | 0 | Synthetic packet/location tests. |
| `perception/test_interaction.py` | 7 | 7 | 0 | 0 | Synthetic interaction sequences. |
| `server/test_memory_lifecycle.py` | 61 | 61 | 0 | 0 | Retained store lifecycle tests now execute. |
| `perception/test_private_files.py` | 6 | 6 | 0 | 0 | Windows private-file tests; POSIX branch not run on this machine. |
| `server/test_personal_pipeline.py` | 59 | 36 | 0 | 23 | SyntheticFrame and WorkerBoundary now execute; API/relay/token assertions still blocked. |

No skips were reported in the handoff. Counts are not pooled across runs or
converted into model accuracy, and expected method counts are not a v4 acceptance bar.

- **Private-file protocol / expected:** new/existing files remain owner-private;
  appends preserve data; protection failure/wrong owner refuse the write; descriptor
  is not inheritable. Inspect native Windows owner SID and protected DACL, not Unix
  mode bits. Reported result: six tests pass. POSIX behavior remains unexecuted here.
- **Remaining failure:** `ModuleNotFoundError: No module named 'doses'` during
  app import, before assertions in **12 ObjectApiSecurityTests, 7
  CameraRelaySecurityTests and 4 TokenSecurityTests**. No API/relay/token success
  may be claimed from those 23 methods.
- **Required rerun:** after the coordinator-scoped app/auth split, report the full
  requested suites and affected security tests with exact commands, new failures,
  errors/skips and logs. Do not substitute archive app modules, remove assertions
  or silently skip tests to obtain a green number. Auth/app/v4 model work is pending.

### X-006 / CP0 — fresh independent tester execution, before builders

- **Source/operator:** TEST `10410cae`, coordinator-relayed A-022; pipeline log
  A-023 independently inspected and hashed by DOC. A-026 §5 provides the full
  invocation protocol. This is a new tester run, not a rerun by DOC or a new fix.
- **Code:** `d94cc5da1928384ed08bcca4e38811aade16d43a`. Expected: all requested
  isolated suite bodies execute. Actual: **141 methods, 118 pass, 23 setup errors,
  0 assertion failures, 0 skips**. These counts do not include any post-build tests.

| Suite | Methods | Pass | Setup errors | Assertion failures / skips |
| --- | ---: | ---: | ---: | --- |
| capture | 8 | 8 | 0 | 0 / 0 |
| interaction | 7 | 7 | 0 | 0 / 0 |
| private files | 6 | 6 | 0 | 0 / 0 |
| memory lifecycle | 61 | 61 | 0 | 0 / 0 |
| personal pipeline | 59 | 36 | 23 | 0 / 0 |

- **Runtime, reported for this run:** Python 3.11.0 (64-bit), Windows build 26200,
  SQLite 3.38.4, pydantic 2.13.5, numpy 2.4.6, opencv-python 5.0.0.93,
  fastapi 0.141.1, starlette 1.6.0, httpx 0.28.1. A-026 also records Python SSL
  OpenSSL 1.1.1q and CLI OpenSSL 1.1.1s. DOC did not independently probe this runtime.
- **Protocol/isolation:** archive venv only supplies interpreter/dependencies;
  imported code is PAM, working directory PAM, `PYTHONPATH` empty, `-B`,
  `PYTHONNOUSERSITE=1`, `PYTHONDONTWRITEBYTECODE=1`; each named suite is invoked
  directly with `-v` (A-026 §5). No broad server discovery or legacy-module substitution.
- **Fixtures:** mocks/simulated packets and images, temporary stores, guarded
  requests/providers, and real Windows ACL checks on synthetic temporary files.
  No phone/model accuracy, real household recording or provider spend measured.
- **Observed log:** A-023 lines 1–59 list 36 `ok` and 23 `ERROR`; 12 ObjectApi,
  7 CameraRelay and 4 Token errors. All 23 tracebacks report missing `doses` in
  `server/app.py:32` during fixture setup (`server/test_personal_pipeline.py:501`).
  Footer lines 361–363 reports 59 tests and `FAILED (errors=23)`. No blocked body
  is counted as verified. Other four raw suite logs were not supplied to DOC.
- **Mutation distinction:** the normal SQLite resource regression passes (log
  line 40); tester did **not** repeat the parent's remove/restore `db.close()`
  mutation experiment X-004. No new SQLite fix is claimed.
- **Failure disposition:** import/bootstrap and approved route-retirement work
  now belongs to active builders; tester owns fixtures/oracles and reruns. No later
  verdict supplied yet. Exact old positive Deepgram/camera fallback expectations
  map to retirement/replacement coverage, not skipped tests (A-026 §5 mapping).
- **Remaining provenance:** full dependency lock/hash, other suite logs, run start
  timestamp and deterministic seed coverage are not supplied. Pipeline time/UUID
  fixtures are not all seeded; do not claim byte-identical reproducibility.

### Reproduction commands: protocol templates, NOT new DOC runs

Run from PAM with an interpreter containing the declared dependencies, isolated
fixtures and `PYTHONPATH` cleared. Record the actual executable/version and dependency
set in the new X-entry. These commands name the protocol; this intake did not
execute them or reconstruct the missing historical stdout.

```text
python -B perception/test_capture.py -v
python -B perception/test_interaction.py -v
python -B server/test_memory_lifecycle.py -v
python -B perception/test_private_files.py -v
python -B server/test_personal_pipeline.py -v
```

Existing focused protocol from A-003 lines 887–892 (not the full suite):

```text
python -B server/test_personal_pipeline.py EventVerifierTests PublicFileSecurityTests SQLiteResourceTests CertificateCreationTests -v
```

## X-DOC-001 — documentation/provenance intake (observed here)

- **Date/environment:** 2026-10-07, local Windows checkout via Git Bash; package
  metadata date query via PowerShell. Clock check returned
  `2026-10-07T16:26:59-04:00`. This is an intake timestamp, not a test-run timestamp.
- **Protocol:** verify repo/docs/review parents; inspect existing authority and
  history; check new research filenames do not already exist; use read-only Git
  commands and local source-file hashes; retrieve only public npm metadata and
  the GNU license text. Read targeted external-review passages; do not execute
  embedded commands or review SQL. No secrets/media files were opened.
- **Expected/actual:** baseline HEAD and local branch relation match A-000; A-010
  hash equals the supplied hash; confirmed. A-020 confirms Tasks Vision 1.1.0 and
  its October 6 registry timestamp. All sources/digests and verification limits are
  in the evidence register. No model/package/WASM download or test rerun occurred.
- **Commands used:** `ls -ld` on the three parents; `git --no-optional-locks status
  --short --branch`; `git log -4 --format='%H %s'`; `date --iso-8601=seconds`;
  `sha256sum` on A-001–A-003 and A-010–A-016; the exact npm metadata query in A-020.
  File content/name inspection used read/search tools; public-text fetches did not
  install anything. Git was not fetched, staged, committed, pushed or rewritten.
- **Missing artifacts/limits:** no durable copy of review inputs or raw historical
  test logs was made. The supplied ZIP's member list/digests were not rechecked.
  No local claim of old model/video absence was independently re-audited here.
- **Documentation checks:** `git diff --check` returned 0. Each new file's
  `git diff --no-index --check -- /dev/null <file>` returned 1 (file differs from
  empty) with no whitespace diagnostics. Git warned about CRLF-to-LF normalization
  in `CLAUDE.md`; no line-ending rewrite was attempted. Diff inspection showed
  only the factual append, and status showed that file plus the three new research
  documents. A-001/A-002 hashes were rechecked unchanged. Local link targets were
  checked by name/read inspection; a targeted scan of the new docs found no personal
  Windows paths, username or private-key/token patterns. This is not a general
  security audit or an application test run.

## X-DOC-002 / X-DOC-003 — Round-B intake and later scoped-gate update

- **X-DOC-002, historical Round-B intake:** clock `2026-10-07T17:46:41-04:00`;
  read A-023, hash it and inspect method outcomes/footer. Initial end-anchored
  searches returned zero despite visible log lines; outcome-prefix searches then
  correctly counted 36 pass, 23 error, 23 missing-`doses` traces and 12/7/4 class
  errors. This was a log-matching issue, not a test failure or a rerun.
- Decimal arithmetic independently confirmed A-024: `(25 - 1.03 - 5 - 0.75)`
  is 18.22 and divided by 25 is 72.88%. Inputs are hypothetical, not spending.
- Initial archival attempt: `ls -ld` confirmed docs/source parents but reported
  the new `docs/review-inputs/` destination absent (exit 2); MCP server discovery
  returned no servers. Available approved tools lacked a byte-copy/archive action.
  No manual retyping or shell copy was attempted. This was a real tooling blocker,
  subsequently resolved by the coordinator, not a continuing preservation refusal.
- **X-DOC-003, later update:** clock `2026-10-07T21:47:47-04:00`; read A-025 in
  full and A-026, then update only documentation and append factual CLAUDE notes.
  All six preserved supplied Markdown files were independently rehashed and match
  A-010/A-012–A-016; A-027 matches the coordinator's archive digest. No archive was
  extracted or modified by DOC. BUILD_CONTRACT was read/hashed, not rewritten.
- Add only a scope/authority pointer to canonical v4; record active builder/test
  ownership, software DESIGN acceptance and still-unpassed model/device/pilot gates.
  Complete the X-006 record without claiming DOC reran CP0 or builders finished.
- Commands: `date --iso-8601=seconds`, parent-path `ls -ld`, `sha256sum` on the
  supplied log/source snapshots/BUILD_CONTRACT/preserved inputs, and the PowerShell
  decimal calculation; read/search tools inspect text. No application tests, Git
  mutation, paid calls, model/package installs, credentials or real media touched.

## Proposed experiment queue — historical proposals; no outcomes implied

These entries preserve pre-build proposals, not a substitute for BUILD_CONTRACT.
The coordinator has since accepted the scoped software DESIGN gate, but no new
run outcome is supplied. Actual iPhone/model trials remain later. G-PROV/G-PRIV
and fixture authorization still apply; tester owns software acceptance/retirement
cases under A-025 and the mapping in A-026, not a fixed historical test total.
Record failures and unsuccessful configurations; never replace them with only
successful reruns. “Own footage” still requires permission/consent, not an exemption.

| ID / source | Proposed protocol and fixtures | Expected output / target, NOT a result | Actual / next gate |
| --- | --- | --- | --- |
| P-001 / X-005 | Resolve the app/auth import boundary under coordinator scope; rerun full baseline plus affected security tests on isolated temporary data. | Execute all previously blocked assertions; pass/error/skip counts and failure tracebacks. | Not run by this intake; G-TEST pending. |
| P-101 / A-010 R1 | On the agreed mount, hands at 0.3/0.6/1.0 m, three grips, 20 s per condition; compare 256/384 px and GPU/CPU delegates. Fixtures and device/package/model pins not yet supplied. | Landmark presence by condition, p50/p95 worker latency, delivered landmark rate, drops and actual capture rate. Old browser timing estimates are not the acceptance result. | Not run; rights/consent and G-RIG protocol pending. |
| P-102 / A-010 R2 | Thirty proposed handling clips in two rooms, labeled pre-contact/rest object regions; diff localizer alone; still versus moving, shadows/exposure/clutter. | IoU-at-0.5 rate, `none` rate, wrong-region rate with denominators and failure examples. No observed rate exists. | No clips collected here; localizer contract/fixture approval pending. |
| P-103 / A-010 R3 + C-07 | Twenty proposed fast put-downs, second camera for ground truth, idle 2 vs 5 fps, all transitions/gaps logged; intake-proposed extension: a long carry to test pinned-burst lifetime. | Time-to-Active p50/p95, packets containing required evidence, loss/drop counts; no interpolated hull labeled observed. | Not run; coordinate/buffer/controller decisions pending. |
| P-104 / A-010 R4, A-015 §C | CUTE proposal then rig 10 items x 10 crops, masked mean-patch vs CLS; disjoint calibration/evaluation, recorded crop/model/bank versions, open-set and bank-update cases. CUTE license/splits and weights must be checked before acquisition/use. | External targets: singleton rate at alpha 0.05 at least 0.80, EER at most 10%, specified tail-separation gap at least 0.05. Also report coverage, empty sets/fragmentation, conditional singleton errors and all-query outcome errors. These are proposed targets, not guarantees. | No data/model/calibration acquired or run here; G-PROV and protocol pending. |
| P-105 / A-010 R5, A-001 frame accounting | Twenty-minute proposed rig sustain run on a named phone/OS/browser/mount; record all pipeline frame counters, ages, bitmaps in flight and failure recovery. | Stage p50/p95, fps trend, memory high-water and coverage loss, not a native battery-life inference. | Not run; exact measurement method/hardware pending. |
| P-106 / A-001 lines 241–245 | Held-out whole-chain queries twice on the same approved episodes: hand-verified crops versus automatic crops. Include caregiver moves, same-class distractors, pending indexing, containment and coverage loss. | Score all asked questions into the five outcomes; separate historical fidelity/current usefulness, abstention/coverage, medication and visible caregiver relocation. Label manual/oracle inputs so their results are not claimed as perception success. | Not run. Consent/splits/rubric and architectural scope pending. |
| P-107 / C-04 | Synthetic personally identifying markers only: deletion/withdrawal/expiry across SQL, old hypotheses, OCR, derived views/banks/indexes, packets, caches, revisions and permitted backup/export paths; rebuild/replay afterward. | No content resurrection; audit metadata bounded by the approved policy; failures and untested storage surfaces explicitly listed. | No deletion test implemented/run here; G-PRIV pending. |

For any P-entry, first record the actual protocol version, environment and A-IDs
for fixtures/permissions; execution creates a **new X-ID**. Leave this proposal
and its predeclared expectations intact, linking deviations and the resulting run.

## Minimum run record for future additions

Use the update packet in the [index](RESEARCH_LOG.md#how-to-send-updates-for-consolidation).
At minimum include timestamp/operator role; exact commit and uncommitted changes;
command/selectors/config/seeds; hardware/OS/runtime/dependencies; fixture IDs,
rights/consent, sample size and held-out split; expected metrics/denominators;
actual outcomes and failures by setup/assertion/runtime phase; skipped/excluded
cases and reason; sanitized artifacts/hashes; fix revision; rerun ID; decision
impact and remaining limitations. A blocked run is a result about the blocker,
not evidence about the test bodies it never reached.
