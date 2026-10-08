# PAM evidence and artifact register

Intake date: **2026-10-07**. Parent index: [RESEARCH_LOG.md](RESEARCH_LOG.md).
This is a provenance register, not an artifact-use authorization or license opinion.

## Source identity and verification scope

`PAM/` means this repository. `Downloads/` means the user's supplied download
location, not a tracked directory. `Review/` means
`%TEMP%/pam-final-review.tLYg9X63/review/` from the coordinator's extraction.
Personal absolute paths are deliberately not repeated here.

Sources are cited by ID plus section or original line range. Repo line ranges
below refer to the intake at `d94cc5d`; external ranges refer to the registered
bytes. Resolve changing line numbers against their recorded version, not by guess.

| ID | Source / version | What was checked here; authority and rights scope |
| --- | --- | --- |
| A-000 | User/coordinator documentation assignment and checkpoint handoff, 2026-10-07 | Source for role restrictions, reported test results and reported absent legacy artifacts. No standalone hashed transcript supplied. Not independent measurement. |
| A-001 | `PAM/docs/MEMORY_SYSTEM_V4.md`, revision 4, exported 2026-10-05; **pre-overlay snapshot** at `d94cc5d` | Read in full; hash below identifies the original bytes, not the later additive milestone pointer. Broad v4 principles and Part 2 history remain; A-025 plus latest user scope govern the first milestone. Textual license/performance assertions are not clearance or results. |
| A-002 | `PAM/docs/ROUND4_RESPONSE.md`; cites spec commit `f7ca543`; working bytes at `d94cc5d` | Read in full; local SHA-256 checked. Historical steps 1–2 go-ahead. Its stated line count/references are for its cited export, not necessarily the current file. |
| A-003 | `PAM/CLAUDE.md`, lines 1–909 before this intake's append, at `d94cc5d` | Read in full; pre-append SHA-256 checked. Checkpoint notes and historical measurements are reported evidence; not rerun here. The hash below intentionally does not describe later appends. |
| A-010 | `Downloads/FINAL_ARCHITECTURE_REVIEW.md`, dated 2026-10-06; reviews revision 4 / `f7ca543` | Read in full; digest matches the coordinator's supplied digest. External recommendations only, including its imperative §10. Authorship/redistribution rights not independently verified; do not assume an open-content license. |
| A-011 | `Downloads/pam-final-review.zip`, original supplied archive | Local file digest checked. Coordinator reports six Markdown files plus a directory, about 375 KB, with primary MD matching A-010. Archive contents/member digests were **not** independently rechecked here; no extraction or executable was run. No redistribution license supplied. |
| A-012 | `Review/README.md`, final review dated 2026-10-06 | Read and hashed. Describes the four domain reports and their internal revision history; its `docs/review/` paths describe the review package, not files installed in PAM. External input; rights unspecified. |
| A-013 | `Review/ARCH.md`, “final, round 2, revised after cross-review” | Hashed; intake inspected revision summary and relevant blocker/contract passages. Source/claim verification is selective, not a reproduction of the whole review. External input; rights unspecified. |
| A-014 | `Review/PERCEPTION.md`, “final, round 2” | Hashed; intake inspected summary, hand/coordinate/license/localization passages and targeted claims. Model, dataset and speed claims were not independently reproduced. External input; rights unspecified. |
| A-015 | `Review/MEMORY.md`, “final, round 2, revised after cross-review” | Hashed; intake inspected summary, proposed schema, retention/withdrawal and conformal-identity passages. No proposed SQL executed, model run or statistical calibration performed. External input; rights unspecified. |
| A-016 | `Review/COMMERCIAL.md`, “final, round 2” | Hashed; intake inspected revision summary, register and targeted provenance claims. The report itself disclaims legal advice and records unreachable primaries. No project legal clearance; external input, rights unspecified. |
| A-022 | Coordinator's Round B relay, 2026-10-07 | Source for the seven-agent roster, completed initial reviews, open cross-review, builders not started, user subscription/device-timing/archival instructions and tester CP0 environment/results. Reported observations and instructions, not architecture approval. No standalone transcript/hash supplied. |
| A-023 | Tester CP0 pipeline log: `%TEMP%/devin.exe-overflows/shell-744325-02a44c05da7db25e/content.txt` | Read relevant lines and independently hashed/count-checked in Round B. 59 methods, 36 `ok`, 23 `ERROR`; all 23 tracebacks report missing `doses`. Log evidence is not a DOC rerun. Other four suite results/environment are relayed through A-022; their raw logs were not supplied. Contains absolute local paths, so no unredacted copy is placed in research Markdown. |
| A-024 | Conditional subscription arithmetic, supplied assumptions in A-022; PowerShell decimal evaluation, 2026-10-07 | Computation independently confirms $18.22 and 72.88% for the stated hypothetical $25/$1.03/$5/$0.75 inputs. No observed spending, margin or adopted price. Reproducible expression below; no standalone output file/hash. |
| A-025 | `docs/BUILD_CONTRACT.md`, coordinator decision dated 2026-10-07 | Read in full and hashed; authoritative scoped software-milestone contract, not full v5/model/pilot approval. No edits by DOC. Exact APIs remain there rather than being redefined in the research log. |
| A-026 | `docs/CONTINUATION_HANDOFF.md`, living handoff, updated after scoped gate closure | Read and updated by DOC within documentation ownership. Source for parent-corrected cost table, `fail()` reservation correction, archived-response member mapping and earlier review dispositions. Historical and current statuses distinguished; no claim every transcript is archived. |
| A-027 | `docs/agent-round-b-raw.tar.gz` | Coordinator-preserved raw responses; local SHA-256 independently rechecked by DOC. Four-member/agent mapping is coordinator-reported in A-026; DOC did not extract/execute archive content. Raw proposals and incorrect arithmetic are not accepted contracts. |
| A-029 | Coordinator's later scoped-gate/build-start relay, 2026-10-07 | Reports first software DESIGN gate closed and builders A/B/C plus tester started; supplies current product scope and selected decisions. No completed builder changes or new test verdict reported. Supersedes A-022's work-state snapshot, not its historical facts. |

### SHA-256 of the local source files

Computed with `sha256sum` in the PAM working directory on 2026-10-07.
Hashes establish byte identity only. They do not prove an original author's
identity, archive safety, claim correctness or a license grant.

| Source ID | SHA-256 |
| --- | --- |
| A-001 | `c1ef99da292b959759b279acbe399283b6819aca5fad0512b633f8e7350c639c` |
| A-002 | `3faafe92974c005cf1079b9388cd528f9d229e069c48890949730558efff7883` |
| A-003, **pre-append** | `e8450454a0d11a73625278649600aceb7cd3a76f28d7d6bdf14453d2af3e007d` |
| A-010 | `3adefa8747e1fd5c6467dc1a28cf50770127f0b114b5ac17faf9a546e5014892` |
| A-011 | `448266b5ee0d4b5eeb05f2cf38341591b18ccb7b3834e94f8ffa4b38c9b3caf3` |
| A-012 | `92562febd65285ebcab5c2a4d9db8f47baec016d1ddb0f4dc67c39eb19fb3479` |
| A-013 | `7c4773d36cde305d3bd59aba2343fb7f58018b34a94d721e6676d224e2aae8ea` |
| A-014 | `e812ae0cc3dfea5f4862dca4095fb9234a9c282a40b89772854e614fc14bddac` |
| A-015 | `f9489f14fac0faf79b3a5f811edb2fc566164f714c085ac875d01da59250e9e5` |
| A-016 | `96dbcdb02e54922f78d15b752465942bb4e173dec392bcee69151ca8dca84ae7` |
| A-023, CP0 pipeline log | `c483470cff75a8871b1644fb9d06d6904e2cefc232eafd0b12e290299040be59` |
| A-025, BUILD_CONTRACT read-only snapshot | `6e5ca8634964f15acd906c76f2ef5beb3c02cada4d6afe00336cb49b0f990e1d` |
| A-027, raw Round-B archive | `d6e3260cb4f6af475633254014bb43433f380661eac6c46bf6c5cfb5c20a192e` |

No supplied report was overwritten or copied into the canonical specification.
At initial intake this register was not a durable backup. The coordinator later
preserved all six supplied Markdown files under `review-inputs-20261006/` using
the original ZIP, after verifying the destination and its absence. The decision
document's extracted SHA-256 matches A-010. These remain external, unapproved
inputs; preservation grants no license or implementation clearance.

DOC independently rechecked all six preserved Markdown hashes after the scoped
gate announcement: they match A-010 and A-012 through A-016 byte-for-byte. Four
available verbatim current-agent Round-B responses are preserved in
`agent-round-b-raw.tar.gz` (SHA-256
`d6e3260cb4f6af475633254014bb43433f380661eac6c46bf6c5cfb5c20a192e`);
member-to-agent mapping and remaining transcript
limitations are in [CONTINUATION_HANDOFF.md](CONTINUATION_HANDOFF.md). They contain
rejected/conflicting proposals and incorrect cost arithmetic, not authoritative
contracts. The handoff includes every current agent's findings and corrected
current user scope: text chat plus a stored-items browser, no Deepgram now.
Keep any redacted derivative distinct and record both versions; never silently
change a source and retain its old hash.

## Public primary-source checks made during this intake

### A-020 — MediaPipe Tasks Vision package metadata

- Sources: [version-specific npm metadata](https://registry.npmjs.org/@mediapipe/tasks-vision/1.1.0)
  and [registry time map](https://registry.npmjs.org/@mediapipe/tasks-vision),
  accessed 2026-10-07. **Verified here / observed metadata.**
- Name/version: `@mediapipe/tasks-vision@1.1.0`.
- Registry `time["1.1.0"]`: **`2026-10-06T17:55:06.100Z`**. This is a recent
  release, not grounds to dismiss the version as nonexistent.
- Package metadata declares `Apache-2.0`. This check did not inspect an installed
  distribution, its notices or its runtime/API behavior, and does not establish
  the separate `hand_landmarker.task` weight/data terms.
- Distribution metadata lists SHA-1 `282102e87c53034254974ced8f772c626a6c3496`
  and the following integrity value. These are **registry-reported**, not locally
  verified bytes: no package, WASM or model archive was downloaded.

```text
sha512-ZJqh0wMKOINorfSffvDAxzyO1//c+FiG3IkzOdNDnLqvBB3DbMfj0bB/tys2SNf9S914sgoIbIpF4HTOi336cg==
```

A version-specific metadata fetch was followed by this read-only PowerShell API
query; it returned the timestamp and license declaration above without saving a
package or installing dependencies:

```powershell
Invoke-RestMethod -Uri 'https://registry.npmjs.org/@mediapipe/tasks-vision' |
  Select-Object @{Name='package';Expression={$_.name}},
    @{Name='version';Expression={'1.1.0'}},
    @{Name='published_utc';Expression={$_.time.'1.1.0'}},
    @{Name='license_declaration';Expression={$_.versions.'1.1.0'.license}} |
  ConvertTo-Json
```

Raw registry documents were not archived or hashed in this intake. Re-fetching
is a new dated check, not a guarantee of identical future metadata. The review's
`/latest` URL is not a reproducible version pin.

### A-021 — AGPL-3.0 text, not project compliance advice

Primary [GNU AGPL version 3](https://www.gnu.org/licenses/agpl-3.0.html),
19 November 2007, accessed 2026-10-07. The preamble describes a free copyleft
license; §2 affirms permission to run the unmodified program; §4 permits charging
for copies. **Verified here / textual observation:** AGPL is not an NC license.
Distribution and network provisions still matter for covered works. This is not
an assessment of a particular project's obligations or any trained weight's status.
The served license text was not archived/hashed; source version is the named v3 text.

## Claim-to-source map and missing evidence

| Subject | Existing source / location | Evidence classification and outstanding work |
| --- | --- | --- |
| Historical prompt, speed, trigger and cost experiments | A-003 lines 139–510, with open questions at 526–538 | Reported historical observations mixed with explicitly predicted risks. Retain original model/device/scene scope. Fixture hashes, full logs and some environment fields are not supplied in this intake; no rerun. |
| Legacy UI/voice, calendar/capability and schedule tests | A-003 lines 578–796 | Historical method and outcome notes retained at source, including mocked versus live boundaries and platform limits. Not rerun, not transferred to the PAM split's coverage, and not evidence of v4 accuracy. |
| Split security failures and reruns | A-003 lines 798–909; A-000; commits in the index | Reported observations. [Experiment ledger](RESEARCH_EXPERIMENTS.md) preserves setup errors and mutation history. Raw run logs not supplied here. |
| Pilot rubric, oracle/automatic crop comparison and rig/native separation | A-001 Part 1, especially lines 130–165 and 208–246 | Design/protocol requirements, not executed pilot results. Existing thresholds are initial values, not achieved performance. |
| Review R1–R5 and model choices | A-010 §§2–6; A-013–A-015 | External proposals. Runtime, fixture, checkpoint and calibration versions remain to be selected and authorized. |
| Hand-weight rights and conversion | A-014 lines 53–57; A-016 round-2 item 2 | Review reports the primary card unreachable; secondary claims do not resolve upstream weight provenance. No model card was fetched by this intake and no rights conclusion is added. C-03 remains open. |
| Legacy artifact absence | A-000 vs A-010 §4 | Coordinator-reported absence in current checkout/history, not independently inventoried here. Request scoped checkout/ignored-files/reachable-ref evidence; do not infer absence from Git-tracked files alone. |
| Deletion and retention | A-015 lines 83–222, especially 129–161 and 193–222 | Proposed schema stores personal-capable SQL text/versions; media-only deletion is insufficient as a design claim. No real personal data inspected; C-04 is a design gap, not a tested deletion failure. |
| CP and answer correctness | A-015 lines 248–261 | External statistical proposal; exchangeability, fixed scoring/bank, in-bank status and end-to-end errors require separate evaluation. No calibration dataset, hash or result supplied. |
| World/image landmarks and carry burst | A-010 BL-2/BL-4; A-013 lines 49–65; A-014 lines 86 and 116–124 | Contract review, not device evidence. Units and pinned-buffer lifetime still need G-ARCH decisions. |

## Register fields required for each future artifact

Use a new A-ID rather than overwriting a previous version. Record:

1. Source/owner role, primary URL or controlled locator, retrieval date, exact
   version/revision and cryptographic content hash (or explicitly `not available`).
2. Kind: code, package/WASM, weight, conversion, dataset, fixture, calibration,
   annotation, log, generated output or external report; synthetic versus real.
3. **Separate** code license, weight/model grant, training/evaluation dataset terms,
   conversion/teacher provenance and required notices. A repo license does not
   automatically cover its weights, datasets or pseudo-labels.
4. Intended use and environment: internal evaluation, product-development research,
   redistribution or deployment. Track rights/consent reviewed versus unresolved;
   identify the approver/date rather than inferring clearance from a filename.
5. For data/fixtures: acquisition method, pseudonymous source IDs, consent version,
   annotation protocol, train/calibration/test split and leakage controls, retention,
   controlled access, export permission and withdrawal/deletion handling.
6. For derived artifacts: all input A-IDs, producing code/commit and command/config,
   random seed, preprocessing/model/bank versions, output hash, and whether the
   output was observed, predicted or only reported by another party.

Do not store credentials, key bytes, household images/audio, identifying OCR or
participant records here. Use safe IDs; retain protected evidence outside the
research Markdown. Record failures to obtain a primary source, denied permissions
and unavailable artifacts rather than upgrading secondary citations to “verified.”
