# Oversight, CP4: re-observation, retention, erasure, migration (G-PRIV)

Pass 1 (plan review, 2026-10-09), written while the builders worked; pass 2 (diff
review, 2026-10-10, after the coordinator's decisions) is the section "Diff review,
pass 2" below, with the ranked findings in P2.3 and the final G-PRIV verdict in P2.6.
Pass 1 is kept as written (it is the record the decisions answered); where pass 2
supersedes a pass-1 recommendation (the stub, E8(ii)), P2.1 says so.

Scope and authority: `docs/BUILD_PLAN.md` "CP4 in detail" (the plan under review, working
tree), `docs/MEMORY_SYSTEM_V4.md` Part 1 (design authority), `docs/BUILD_CONTRACT.md`
"Store and local processing boundary" (retention and erasure sentences),
`docs/OVERSIGHT_CP2.md` §3 and `docs/OVERSIGHT_CP3.md` §3/§7 (earlier verdicts),
`docs/RESEARCH_LOG.md` (C-04, B-07..B-10, G-PRIV). The external reviews under
`docs/review-inputs-20261006/review/` (COMMERCIAL §4, MEMORY retention rule) are inputs,
not authority. Code citations are `file:line` in the **committed** tree at `77b769e`
(what I read; `git show HEAD:` lengths match). The working tree already carries ~2,100
inserted lines of CP4 code and tests; that is pass 2's object, not this one's.

What is verified where (every legal quotation below is one of these):

| Source | How verified | Date |
| --- | --- | --- |
| 740 ILCS 14/10 (BIPA definitions, as amended by P.A. 103-769) | fetched, primary: https://lig.ilga.gov/legislation/ilcs/documents/074000140K10.htm | 2026-10-09 |
| 740 ILCS 14/20(b)-(c) (single-violation rule) | fetched, primary: https://ilga.gov/legislation/publicacts/103/103-0769.htm | 2026-10-09 |
| 740 ILCS 14/15(a), 15(b) (retention schedule; notice and release) | **UNVERIFIED in this pass**: the fetch needed a permission that was not granted. URL: https://lig.ilga.gov/legislation/ilcs/documents/074000140K15.htm. Wording below is from memory and from `COMMERCIAL.md` §4.4 ([B] there too); confirm before any consent text is drafted | - |
| 740 ILCS 14/20 damages amounts ($1,000 / $5,000) | per `COMMERCIAL.md` §4.4 [V at the P.A. page]; not re-fetched here | 2026-10-06 (theirs) |
| Tex. Bus. & Com. Code § 503.001 (CUBI) | fetched at a secondary reproduction of the statute: https://texas.public.law/statutes/tex._bus._&_com._code_section_503.001 ; primary (UNVERIFIED, permission): https://statutes.capitol.texas.gov/Docs/BC/htm/BC.503.htm | 2026-10-09 |
| RCW 19.375.010 and .020 (Washington, HB 1493) | fetched, primary archive: https://lawfilesext.leg.wa.gov/Law/RCWArchive/2023/htm/RCW%20%2019%20%20TITLE/RCW%20%2019%20.375%20%20CHAPTER/RCW%20%2019%20.375%20.010.htm and the mirror https://wa-law.org/rcw/19_business_regulations%E2%80%94miscellaneous/19.375_biometric_identifiers.html | 2026-10-09 |
| RCW 19.373 (My Health My Data Act) | **UNVERIFIED** (not fetched). URL: https://app.leg.wa.gov/rcw/default.aspx?cite=19.373 | - |
| SQLite `VACUUM INTO`, `journal_mode=PERSIST`, `secure_delete` | documentation fetch refused (permission); URLs: https://www.sqlite.org/lang_vacuum.html , https://www.sqlite.org/pragma.html . **Measured instead** on the sandbox runtime (SQLite 3.45.1, Python 3.12) with the store's own PRAGMAs; method and numbers in Appendix A | 2026-10-09 |

Verdict in one line: **the plan is the right shape for G-PRIV and closes B-07, B-08, B-09
and B-10 as designed, with nine corrections it needs before the diff can close the gate**:
(1) promoted idle frames and `embeddings` are left outside every retention window
(§1.3); (2) the erasure stub in `local_observations.record` breaks the `record IS NOT
NULL` sentinel every reader uses (§4.1 E3); (3) steps (2) and (4) of `erase_item` both
claim `corrections` rows, and a blanked payload crashes replay unless filtered (§4.1
E2); (4) the `VACUUM INTO` swap must pre-create the target privately, discard the
persistent `-journal` (which holds pre-images of the erased pages, measured) and set
`secure_delete=ON` (§4.3); (5) a packet captured before an erasure can still arrive
afterwards from the browser mirror (§4.2); (6) `consent_version` must not be a
user-typed field (§3); (7) migration must not copy VLM prose, geolocation or file paths
and must stamp a legacy consent class (§6); (8) `erase_profile` must also erase the v1
content tables (§6); (9) a late revision of an expired episode hits `bytes(None)` in
`ingest_episode`, and the superset check is vacuous after reduction (§4.1 E8). None of
these changes the architecture; all are one-transaction or one-column fixes.

## 1. G-PRIV data-class map

### 1.1 Classes

| Class | Meaning |
| --- | --- |
| **IMG** | an image of the home, possibly showing a person (the user, a bystander, a face). Photographs are excluded from the biometric definitions (§2.1) and governed by the recording/consent regime (`COMMERCIAL.md` §4.3). |
| **HAND** | hand geometry: 21 image-space points per hand, optional 21 world-space points, per analysed frame. The class the biometric statutes reach (§2.2). |
| **LOC** | location text: words describing where in the home something is (`location_text`, a user's name for a place). Personal: it describes the household. No geolocation exists in the CP1+ schema (`perception/episode.py:153-168` has no lat/lon; the v1 schema does, §6). |
| **NAME** | user-typed free text (`item_names.name`). Can contain a person's name ("Dad's pills"). |
| **VEC** | a derived vector (`embeddings.vector`, 384 float32): not biometric by definition (CP3 §3.1), personal data by linkage; may incidentally describe a hand if the crop contained one (mitigated by the CP4 hand hull). |
| **IDS** | identifiers, timestamps, counts, digests, enumerated status strings, role strings. Private, not anonymous (BUILD_CONTRACT: "Remaining metadata stays private and is not declared anonymous"). |
| **MONEY** | v1 budget/lease bookkeeping. |

Retention columns in the table use the brief's defaults: `episodes_days` 90, `idle_hours`
24, `landmarks_hours` 72. "forever" means no window in the brief; "item" means until
`erase_item` reaches it through the co-visibility closure; "profile" means
`erase_profile`.

### 1.2 The map

| Table / column(s) | Class | Written by | Retention per the brief | Removed or reduced by | Survives as audit |
| --- | --- | --- | --- | --- | --- |
| **v1 (`object_memory.py:127-151`)** | | | | | |
| `objects.name`, `.category` | NAME (VLM- or user-chosen label) | v1 pipeline | forever | nothing in the brief (§4.1 E7, §6: `erase_profile` must) | - |
| `objects.object_id/status/created_at/profile_id` | IDS | v1 | forever | - | yes |
| `candidates.payload` (`Candidate`, `:48-65`: `frames[]` and `crop` **file paths**, `box`, `location {lat, lon, accuracy_m}` or status, object label, track/session ids) | IMG-by-path, **geolocation**, LOC-adjacent | v1 | forever | nothing in the brief (§6) | - |
| `candidates.verification` (`Verification`, `:76-94`: `actor` wearer/bystander, `actor_evidence[]`, `appearance` ≤ 600 chars, `scene{room, surface, landmarks[], description ≤ 600}`, `identity_evidence`, `reason`) | **VLM prose about the scene and the people in it** | v1 | forever | nothing in the brief (§6) | - |
| `candidates.status/reason/digest/sequence/active_call_id` | IDS | v1 | forever | - | yes |
| `observations.record` (`_observe`, `:398-406`: everything above plus `frames` paths, `crop` path, `location`) | as `candidates.payload` + `verification` | v1 | forever | nothing in the brief (§6) | - |
| `bindings` | IDS | v1 | forever | - | yes |
| `api_calls` | MONEY + event ids | v1 | forever (contract: preserve) | never | yes |
| `decisions.detail` (`_audit`, `:219-221`: JSON incl. `{"name": ...}` on confirm/resolve) | NAME inside audit text | v1 | forever | nothing in the brief (§6) | - |
| **CP1-CP3 (`episode_store.py:71-128`)** | | | | | |
| `episode_revisions.packet` (keyframes 1-8 JPEG at capture resolution, roles incl. `hand_busy`/`carry`/`release`; `carry_burst` ≤ 10 grayscale analysis frames; `landmarks[]` ≤ 128 samples × 2 hands × (21 image points + optional 21 world points + bbox + handedness); gaps; ids) | **IMG + HAND** | `ingest_episode` | HAND: 72 h then reduced; IMG: 90 days then NULL | landmark reduction (c); expiry (a); `erase_item` (5); `erase_profile` | digests, ids, `reduced_ms`, `redacted_reason` |
| `episode_revisions` other columns (`semantic_digest`, `transport_digest`, device/episode/revision ids, `received_at_ms`, `accepted`, `clock_status`, `redacted`, CP4 `redacted_reason`, `reduced_ms`) | IDS (digests are hashes of personal bytes: a verification oracle, not reversible) | ingest | forever | never | yes |
| `episode_jobs` (`status`, `token`, `lease_until`, `attempts`, `result_count`, `error` = fixed literal `local_processing_failed` `:513`) | IDS | worker | forever | `redacted` status on erasure | yes |
| `local_observations.record` (`:431-435, :488-496`: `label`, `bbox`, `location_text`, `actor`, `outcome`, `identity_state`, `continuity_id`, `session_id`, `match{set, excluded, scores, calibration_id}`, `source`, ids) | **LOC + IDS** (+ bbox, a region of an image; scores are numbers about the user's items) | `process_pending` | **forever** (brief (a): "observations ... stay") | `erase_item` (3): stub (see §4.1 E3) | `observed_at_ms`, `decided_at_ms`, ids |
| `local_observations.candidates` | IDS | worker | forever | erased with the row | - |
| `current_items.record` (projection: `name`, `location_text`, `reference_image.bbox`, status fields, `lookalikes`, CP4 `inference`, `stale_since_ms`) | LOC + NAME + IDS | `_rebuild_projection` | rebuilt on every write | `DELETE` + rebuild on erasure (today `:1277`; **the brief does not list it**, §4.1 E6) | - |
| `item_names.name` | **NAME** | `rename_item` | forever | `erase_item` (4) NULL, row kept | `at_ms`, ids |
| `episode_tombstones`, `item_tombstones` | IDS | redaction/link | forever (they are the refusal mechanism) | never | yes |
| `local_audit.detail` (today: calibration ids/embedder/source/n `:265`; `{}` `:995`; `other_item_id/actor/correction_id` `:1036`; `from_item_id/observation_id` `:1072`; `other_candidates` `:1144`; counts `:1282`) | IDS and role strings; **no free text today** | every audited method | forever | `erase_item` (4) blanks `detail`, keeps row with `erased=1` | `action`, `item_id`, `at_ms` |
| `local_cannot_links` | IDS (pairs of item ids) | worker, corrections | forever | **not in the brief**; keep (ids only), say so | yes |
| `calibrations` (`embedder` tag, `alpha`, `quantile`, `n`, `source`, `approved_by` role) | IDS/numbers; an `own-footage` row is a statistic derived from the household's images (CP3 §3.3 c) | `register_calibration` | forever | "calibrations stay" (§8 Q6: delete `own-footage` rows on `erase_profile`) | yes |
| `embeddings.vector` (+ `embedder`, `dim`, `created_ms`) | **VEC** | worker | **forever** (brief (a): "embeddings stay" after the keyframe expires) | `erase_item` (2) | ids |
| `corrections.payload` (`keep_id/other_id`, `observation_id/from_item_id/new_item_id`, `item_id/other_candidates`), `actor` role | IDS | corrections | forever | `erase_item` (2) *or* (4): **the brief says both** (§4.1 E2) | `kind`, `at_ms`, `actor` |
| **CP4 additions (brief)** | | | | | |
| `idle_frames.jpeg` (+ `width`, `height`, `motion_energy`) | **IMG** (the home while nobody is handling anything; bystanders possible) | `ingest_idle` | 24 h unpromoted; **promoted: "never expires"** | `expire_idle`; cache eviction; `erase_item` (2) for promoted frames; `erase_profile` for all | `frame_id`, `t_wall_ms`, `received_ms`, `promoted`, counts |
| `idle_frames` ids/times | IDS | ingest | 24 h / forever if promoted | with the row | yes |
| `reobservations` (`result`, `region_diff`, `registered`, `embedded`, `t_wall_ms`, ids) | IDS/numbers; a behavioural trace of when each item was present or gone | `reobserve` | **forever** | `erase_item` (2) | counts |
| observation rows with `source: "reobservation"` (`outcome: sighted`, inherited `location_text`) | LOC + IDS | `reobserve` | forever | `erase_item` (3) | ids |
| `containment` (`inner_item`, `outer_item`, `since_ms`, `frame_id`) | IDS | worker | forever (most recent wins; cleared by pickup) | `erase_item` (2) | counts |
| `retention` (`consent_version`, three windows, `updated_ms`) | IDS/config | `set_retention` | forever | survives `erase_profile` (settings) | yes |
| `migrations` (`migration_id`, `from_version`, `counts`, `at_ms`, `actor`) | IDS/counts | `migrate_v1` | forever | never | yes |
| `episode_revisions.packet` after reduction: `landmark_summary[{frame_id, t_ms, hands[{hand_bbox, busy, basis}]}]` | IDS/numbers (a box, a boolean, a rule name from the closed set in `hand_busy.py:26-28`) | `apply_retention` (c) | 90 days with the packet | expiry (a); erasure (5) | - |
| `perception/hand_hull.py` mask | HAND-derived, **in memory only** (`mask_rle` is never stored, `episode_store.py:434`) | worker | not stored | - | - |
| **Outside SQLite** | | | | | |
| `<db>-journal` (PERSIST rollback journal) | **pre-images of every page the last write transaction modified**, i.e. the content that was just erased (Appendix A, measured) | SQLite | until the next transaction overwrites it | **not in the brief** (§4.3) | - |
| Browser IndexedDB `pam-memory-mirror-v1` (`memory-queue.js:37`): serialised packets until a matching ack; `meta.device_id` forever (`:54-55`) | IMG + HAND (unsent packets); IDS | browser | until ack (`:126-129`); unsent rows kept past 7 days with a warning (`:98-99`) | ack; browser storage clear | - |
| Served images | IMG | `/api/items/{id}/image`, `.../observations/{obs}/image` | `Cache-Control: no-store` (`memory_app.py:913, :923`; every response `:620-623`) | not cached by a conforming browser; decoded bitmaps live in page memory until re-render | - |
| Exports, backups, log files | none exist in the tree (no export route, no backup job, no `logging`/`print` in `memory_app.py`, no `.backup()`; the only copy ever made is the `VACUUM INTO` target) | - | - | - | - |

### 1.3 What the brief leaves personal data in forever (flags for the coordinator)

1. **Promoted idle frames** ("promoted=1, never expires"). A promoted frame is an image
   of the home kept outside every window: it is not in a packet, so rule (a) never
   NULLs it. The re-observation path thereby becomes the one way an image outlives
   `episodes_days`. Required: promoted frames follow the same `episodes_days` window as
   packets (`jpeg` → NULL, `redacted_reason = "retention"`, the observation shows
   "evidence image expired" exactly as an expired keyframe does). This also keeps the
   consent sentence simple ("photos are kept for N days").
2. **`embeddings` after the keyframe expires** (rule (a): "embeddings stay"). CP3 §3.3(e)
   recorded the default as "the keyframe's (90 days)". The brief keeps the vector of a
   photo that no longer exists, indefinitely. The product reason is real (the bank must
   keep recognising a long-lived item), so I do not ask for expiry; I ask for (i) the
   disclosure to say it ("Pam keeps a numerical appearance signature of each item after
   the photo is gone, until you erase the item"), (ii) the hand hull (CP4 deliverable)
   to be in place before any rig run that stores vectors, since an expired-photo vector
   can no longer be checked for a hand, and (iii) erasure to reach it (it does). Decision
   for the coordinator (§8 Q2).
3. **`reobservations` rows** have no window and accumulate per item per idle frame
   (continuous mode, §8 Q1: up to 2,880 frames/day × placed items). Required: rows with
   `result = "unknown"` expire with their frame; `present`/`gone` rows follow
   `episodes_days`.
4. **`local_observations.record`** (location text, label, bbox) is forever by design: it
   is the ledger the product exists to keep. Acceptable, with the disclosure saying
   "the written record of where Pam saw your items is kept until you erase it". Nothing
   to change.
5. **v1 content tables** (`objects.name`, `candidates.payload/verification`,
   `observations.record`, `decisions.detail`) are not touched by `erase_profile` in the
   brief ("everything in the profile" is ambiguous; "calibrations stay" is the only
   exclusion named). They hold VLM prose, geolocation and file paths (§6). Required:
   `erase_profile` erases them too, keeping `api_calls` (MONEY) and ids.

## 2. Biometric and legal review of the landmark reduction, the idle keyframes and the embeddings

### 2.1 The statute texts (verified as stated in the header)

**Illinois BIPA, 740 ILCS 14/10** (P.A. 103-769, eff. 8-2-24), fetched today:

> "Biometric identifier" means a retina or iris scan, fingerprint, voiceprint, or scan of
> hand or face geometry. Biometric identifiers do not include writing samples, written
> signatures, photographs, human biological samples used for valid scientific testing or
> screening, demographic data, tattoo descriptions, or physical descriptions such as
> height, weight, hair color, or eye color. [...] Biometric identifiers do not include
> information captured from a patient in a health care setting or information collected,
> used, or stored for health care treatment, payment, or operations under the federal
> Health Insurance Portability and Accountability Act of 1996.
>
> "Biometric information" means any information, regardless of how it is captured,
> converted, stored, or shared, based on an individual's biometric identifier used to
> identify an individual. Biometric information does not include information derived
> from items or procedures excluded under the definition of biometric identifiers.

The structural point everything below turns on: **"biometric identifier" has no
"used to identify" element; "biometric information" does.** A "scan of hand geometry"
is an identifier because of what it is, whether or not anyone matches it to a person.

740 ILCS 14/20(b), fetched today at the P.A. page: a private entity that "in more than
one instance, collects, captures, [...] the same biometric identifier or biometric
information from the same person using the same method of collection has committed a
single violation of subsection (b) of Section 15 for which the aggrieved person is
entitled to, at most, one recovery under this Section." Damages: $1,000 negligent /
$5,000 intentional or reckless per `COMMERCIAL.md` §4.4 [V].

740 ILCS 14/15(a) and (b) [UNVERIFIED in this pass; URL in the header]: 15(a) requires a
written, public retention schedule and guidelines for permanently destroying identifiers
"when the initial purpose for collecting or obtaining such identifiers or information has
been satisfied or within 3 years of the individual's last interaction with the private
entity, whichever occurs first"; 15(b) forbids collecting, capturing or otherwise
obtaining an identifier unless the entity first (1) informs the subject in writing that
it is being collected or stored, (2) informs the subject in writing of the specific
purpose and length of term, and (3) receives a written release. Note 15(b) attaches at
**collection**, not at storage.

**Texas CUBI, Tex. Bus. & Com. Code § 503.001** (secondary reproduction, today):
"biometric identifier" means "a retina or iris scan, fingerprint, voiceprint, or record
of hand or face geometry"; (b) a person "may not capture an individual's biometric
identifier for a commercial purpose unless the person: (1) informs the individual before
capturing the biometric identifier; and (2) receives the individual's consent to capture
the biometric identifier"; (c)(2) "shall store, transmit, and protect from disclosure the
biometric identifier using reasonable care"; (c)(3) "shall destroy the biometric
identifier within a reasonable time, but not later than the first anniversary of the
date the purpose for collecting the identifier expires"; (d) civil penalty "of not more
than $25,000 for each violation", enforced by the attorney general (no private action).
Like BIPA, the definition has no "used to identify" element and no photograph exclusion
in the text; unlike BIPA, it needs no written release and no retention policy document.

**Washington RCW 19.375.010** (primary archive, today): "'Biometric identifier' means data
generated by automatic measurements of an individual's biological characteristics, such
as a fingerprint, voiceprint, eye retinas, irises, or other unique biological patterns or
characteristics that is used to identify a specific individual. 'Biometric identifier'
does not include a physical or digital photograph, video or audio recording or data
generated therefrom, or information collected, used, or stored for health care treatment,
payment, or operations under [HIPAA]." "'Enroll' means to capture a biometric identifier
of an individual, convert it into a reference template that cannot be reconstructed into
the original output image, and store it in a database that matches the biometric
identifier to a specific individual." "'Commercial purpose' means a purpose in
furtherance of the sale or disclosure to a third party of a biometric identifier for the
purpose of marketing of goods or services when such goods or services are unrelated to
the initial transaction [...]". RCW 19.375.020(1) regulates enrolling "for a commercial
purpose" without notice, consent or a mechanism to prevent subsequent use; .020(4) limits
retention to "no longer than is reasonably necessary" for the listed purposes.

### 2.2 Are 21-point hand landmarks a "scan of hand geometry"?

What the packet stores (`perception/episode.py:69-86`): per analysed frame, per hand, 21
`ImagePoint`s (x, y normalised to the frame, z relative), an optional 21 `world_landmarks`
(metric, hand-centred), `hand_bbox`, `handedness`; up to 128 samples per episode, every
hand in view (the user's and anyone else's), stored as raw packet bytes
(`episode_store.py:350-351`).

- **Illinois.** On the text, the honest answer is "arguably yes, and no court has said
  otherwise for pose keypoints". The 21 points are literally geometry of a hand produced
  by an automated scan of an image; MediaPipe's own description is a hand-landmark
  *detector*, and `world_landmarks` are metric distances between joints, which is the
  kind of measurement a hand-geometry biometric uses. The defence argument is that a
  per-frame pose estimate in image coordinates, varying with pose, distance and
  occlusion, is not a measurement of *the individual's* hand geometry and cannot
  identify anyone; the plaintiff's argument is the statute's words plus the absence of a
  use element. Illinois courts have read "scan of face geometry" to cover templates
  derived from photographs rather than from a live scan; I do not cite the cases here
  because I could not open them in this pass (counsel will). CP2 §3.1 already said the
  cheap engineering answer is not to keep the points; that remains the answer, and the
  plan's reduction is that answer implemented with a 72 h lag. **Verdict: treat raw
  landmarks as a biometric identifier for compliance planning in Illinois; do not rely
  on the "never matched" argument.**
- **Texas.** Same words ("record of hand ... geometry"), same answer, lower stakes:
  AG-only enforcement, inform-and-consent (no written release form), destroy within a
  year of the purpose expiring. 72 h satisfies (c)(3) by a wide margin; (b) still
  attaches at capture.
- **Washington (19.375).** Two elements PAM does not meet: the identifier must be "used
  to identify a specific individual", and the operative prohibition is on *enrolling*
  "for a commercial purpose" in the narrow sale-or-disclosure-for-marketing sense. PAM
  never matches a hand to a person (no template, no `which other person`; CP2 §3.1
  constraint (b)) and discloses nothing to anyone. **On the text, raw landmarks are not
  a Washington biometric identifier and nothing in CP4 is an enrollment.** The broader
  exposure in Washington is RCW 19.373 (My Health My Data: consumer health data includes
  biometric data and medication-related data; UNVERIFIED here), which `COMMERCIAL.md`
  §4.8 names for counsel.

### 2.3 Is 72 h retention of raw landmarks defensible for a consumer rig with consent?

Yes as a **retention** schedule, no as a **collection** answer. Under BIPA 15(a) any
schedule under "purpose satisfied or 3 years" is lawful, and 72 h with an automatic,
audited destruction job (rule (c), `reduced_ms` recorded) is a strong one. But 15(b)
and CUBI (b) attach the moment the points are captured; 72 h does not shorten the
notice-and-release obligation, it shortens the exposure window and the 15(a) record.
Consequences:

1. For the **rig** (the team's own hands, `consent_version = "rig-2026-10"`), the
   consent is the team's: write it down (one page, the data, the purpose "to tell when a
   hand is busy and to mask the hand out of item photos", the 72 h term), have each
   person whose hands will be in frame sign it, and keep it with the research record. That
   is a 15(b)-shaped release and costs an hour.
2. For a **household** in Illinois or Texas, the points are also collected from aides and
   visitors, whose written release cannot be obtained in-app. `COMMERCIAL.md` §4.3(4) and
   §4.4(d) already say: written releases from every regular entrant, or do not pilot
   there. CP4 does not change that; it makes the exposure 72 h instead of forever.
3. A shorter window is better than a longer one and costs nothing: the only consumer of
   raw landmarks is `process_pending` (busy classification already happened on the phone;
   the server uses the points for the hand hull at embedding time, CP4). Once the
   revision's job is `completed`/`context_only`/`failed`, nothing reads the points again
   except the superset check on a later revision (`_superset`,
   `episode_store.py:146-159`), and that check becomes vacuous once `landmarks` is empty
   (§4.1 E8: a revision arriving after reduction must be `conflict`, as the MEMORY
   review's rule has it, or be checked against the summary's frame ids). Recommendation:
   `landmarks_hours` default 72, the reduction running as soon as the revision's job is
   terminal *and* the window has passed; never reduce a revision whose job is still
   `pending`/`processing` (otherwise the hand hull silently degrades to "no hull"). The
   tester should pin both.

### 2.4 Does the reduced form fall outside the definitions?

`landmark_summary: [{frame_id, t_ms, hands: [{hand_bbox, busy, basis}]}]`:

- `hand_bbox`: four normalised numbers saying where in the frame a hand was. That is a
  measurement of the frame, not of a biological characteristic; it carries no joint,
  finger or palm geometry. Not "a scan [or record] of hand geometry" (IL, TX), not "data
  generated by automatic measurements of an individual's biological characteristics"
  (WA). `COMMERCIAL.md` §4.7 reached the same conclusion for bbox and handedness.
- `busy`: a boolean. `basis`: one of a closed set of six rule names
  (`hand_busy.py:26-28`: "curled", "lower-frame", "curled+lower-frame", "open hand",
  "no hand", "degenerate hand"). Neither is geometry.
- **What must not slip into the summary**: `reference` (a palm-to-knuckle distance, the
  hand-size proxy), `palm_centre`, `curl_ratio` (`hand_busy.py:107`) and
  `world_landmarks`. `reference` in particular is exactly the "hand-size scalar" the
  COMMERCIAL review treats as the wearer's template. The plan's field list excludes
  them; the tester's schema check must make `landmark_summary` a closed shape
  (`extra="forbid"`, the project's `StrictModel`) so a future field cannot be added
  silently. With that, **the reduced form is outside all three definitions on their
  text.**
- The hull mask is computed from the points at processing time and never stored
  (`mask_rle` excluded from the record, `episode_store.py:434`); the plan's
  `hand_hull_mask` must keep it that way (no `hull` column, no mask in the observation
  record).

### 2.5 What the landmark consent and disclosure must say

For the rig release and, later, the household packet (plain words; counsel edits):

1. *What*: "While the camera is on, the phone works out where your hands are (21 points
   per hand) in each picture it analyses."
2. *Purpose*: "to tell when a hand is busy with an object and to leave the hand out of the
   item's photo signature; never to recognise whose hand it is."
3. *Term*: "the hand points are kept on the laptop for up to 3 days and then replaced by a
   box showing where the hand was and whether it was busy; the box is kept with the
   episode for N days."
4. *Others*: "other people's hands in view are treated the same way; Pam never builds a
   record that tells one person's hands from another's."
5. *Erasure*: "erasing an item or everything also removes these."
6. Illinois: "written release" means a signature (electronic is fine); the retention
   schedule above must also exist as a written policy "made available to the public"
   (15(a)), which for a product means a page; for the rig, the consent document itself.

### 2.6 Idle keyframes: photographs, bystanders, 24 h, promotion

- **Not biometric.** An idle JPEG is a photograph: excluded by BIPA's definition
  ("photographs"), by Washington's ("physical or digital photograph, video ... or data
  generated therefrom"); CUBI's definition names a "record of hand or face geometry",
  which a photograph is not. No face detection, face embedding or person
  re-identification exists or is planned (CP2 §3.1 constraint 1 stands; the
  re-observation embeds the *item's* region of the registered frame, never a person).
- **The applicable regime** is recording/consent and privacy torts (`COMMERCIAL.md`
  §4.3): silent stills, so no wiretap exposure; a disclosed camera in common areas with
  a visible indicator and a pause reachable by an aide. The Part 1 bystander plan
  (`MEMORY_SYSTEM_V4.md:99`): indicator, one-touch pause, disclosure, retention policy
  for frames with other people's faces. The camera page already carries the gate
  sentence (`phone/memory.html:72`: "Start only when everyone in view has agreed to be
  recorded") and Pause/Stop buttons.
- **What changes with CP4.** The camera now takes a picture every 30 s when *nothing* is
  happening, which is the opposite of the episode trigger's "only when a hand moves
  something". The "no hand present for 2 s" condition keeps the user's hands out but does
  not keep a person across the room out. So the disclosure must now say (new sentence,
  Builder C's camera page + the rig consent): "While the camera is on and nothing is
  being handled, Pam takes one still picture every 30 seconds and keeps it on the laptop
  for 24 hours to check whether your items are still where it last saw them. If Pam
  recognises one of your items in such a picture, that picture is kept as the item's
  evidence for up to N days [§1.3 item 1], and it may show other people who were in the
  room."
- **24 h cache**: an engineering value (`COMMERCIAL.md` §4.7 table: "No" to counsel
  fixing it), covered by the general frames sentence. Fine as designed: hard delete,
  caps, never listed or served unless promoted.
- **Promotion needs disclosure wording and UI marking.** Promotion changes a frame's
  class from a 24 h cache to item evidence. Two requirements: the sentence above, and in
  the evidence list the promoted photo must say where it came from ("Seen by Pam while
  idle, {time}", not "Photo recorded {time}") so a user looking at their evidence knows
  which pictures were taken with nobody handling anything. `/api/items/{id}/evidence`
  already carries `identity_source`; add `source: "reobservation"` to the DTO whitelist
  (`memory_app.py:752-768`) so the browser can label it.
- **Over-erasure note.** One promoted frame can be evidence for two items (two
  placements in view). Erasing one item deletes the frame; the other item's
  re-observation row then points at nothing. Either extend the CP1 co-visibility closure
  to promoted frames (items sharing a promoted frame are co-visible; over-erasure is the
  safe direction, as `redact_item` already says) or keep the row and make
  `observation_image` return `None` with "evidence image erased". I recommend the
  closure, for consistency with the packet rule (§4.1 E5).

### 2.7 DINOv2 object embeddings: nothing in CP4 changes the CP3 verdict

CP3 §3.1: not biometric by definition (a 384-float appearance vector of an object is not
a retina/iris/fingerprint/voiceprint/hand-or-face scan; under Washington it is "data
generated [from a photograph]" and not used to identify a person); personal data by
linkage. CP4 either leaves that alone or strengthens it:

1. The hand hull (`hand_hull_mask`, 3 % dilation) and `CROP_PAD = 0.10` reduce the
   incidental case CP3 §3.1 worried about (a crop that is mostly hand). Recipe `r2`
   invalidates `r1` calibrations, correctly.
2. Re-observation embeds the item's registered region of an idle frame; by construction
   no hand was present for 2 s, so the incidental-hand case is smaller there. If that
   vector is stored (the brief writes an observation row; it does not say whether an
   `embeddings` row is written for `source: "reobservation"`): it is the same class, same
   erasure. The plan should say which (§8 Q7).
3. Nothing matches a vector against a person, and no route returns one (CP3 §3.2, pass 2
   confirmed). The CP4 routes (`/api/retention`, `/api/idle`, erase, migrate) return
   counts and reports; the tester's "no array of 64+ numbers" assertion must extend to
   them.

### 2.8 Rule 13 as specified versus as planned (a privacy note, not a legal one)

Part 1 rule 13 (`MEMORY_SYSTEM_V4.md:83`, `:316`): re-observation "runs bounded and on
demand (when asked about item X, match X's trusted exemplars against recent idle
keyframes, most recent first), not as a shelf catalog." `docs/FINANCE.md:181` costs it
that way ("20 queries/day × ≤ 40 idle keyframes"). The plan runs `reobserve` continuously
in the worker for every placed item against every new idle frame and promotes frames
with no query. That is an architect decision, but it has three privacy consequences the
coordinator should weigh: more rows (§1.3 item 3), more promoted images (§1.3 item 1),
and a continuous inference about the household's activity ("gone at 14:02") without
anyone asking. A bounded version (at most one evaluation per item per `REOBS_MIN_GAP_MS`,
promotion of at most one frame per item per day, and `gone` only after two consecutive
negatives) keeps the product behaviour the plan wants (stale without a hand event) with
a fraction of the data. §8 Q1.

## 3. Consent-version semantics: the rule I recommend

The brief gives `retention.consent_version` (default `"rig-2026-10"`) and lets
`PUT /api/retention` change it from the browser. A consent version is the name of a
disclosure text, not a user preference; the user can *acknowledge* it, not *set* it.
Recommended rule (coordinator to adopt or amend):

1. **Definition.** `CONSENT_VERSION` is a constant in server code, next to the disclosure
   text the camera page shows (`memory.html`); the retention row records
   `consent_version` (what the build requires) and `acknowledged_version`,
   `acknowledged_ms` (what this profile has agreed to). The string is constrained
   (`[A-Za-z0-9._-]{1,40}`); it is never a request field a client can set (drop
   `consent_version?` from `PUT /api/retention`; keep the three windows there).
2. **A bump is a code change** (new disclosure text, new constant). On the first store
   open after the bump, `consent_version != acknowledged_version`.
3. **What a bump triggers.**
   - *Capture stops until re-consent.* `POST /api/episodes` and `POST /api/idle` return
     409 `{"code": "consent_required"}` while unacknowledged; the camera page shows the
     new text and a "I agree" control that calls `POST /api/retention/acknowledge` (audited,
     actor literal, no body but the version it acknowledges, which must equal the
     current constant). The browser mirror keeps unsent packets (they were captured under
     the old text) and uploads them after acknowledgement; see §4.2 item 1 for the
     erasure interaction.
   - *Retention never lengthens silently.* Every `episode_revisions` and `idle_frames` row
     is stamped with the `consent_version` acknowledged when it was ingested (one new
     TEXT column each); `apply_retention` uses `min(window at the row's version, current
     window)`. Simplest implementation: keep a `retention_history(consent_version,
     episodes_days, idle_hours, landmarks_hours, from_ms)` row per version; a shorter new
     window applies to old rows at once, a longer one applies only to rows ingested under
     the new version.
   - *No automatic erasure.* A bump never deletes anything by itself; the explicit paths
     are `erase_item`/`erase_profile`. If a new version withdraws a purpose (say, no
     re-observation), the data collected for that purpose is erased by an explicit,
     audited call made as part of the upgrade, with the old and new versions in the audit
     row. CP4 does not need a per-class eraser; `erase_profile` is the withdrawal path.
   - *Audit.* `consent_acknowledged {from_version, to_version}` and `retention_changed
     {field, old, new}` rows: ids and numbers only.
4. **Migration (B-10)** stamps imported rows `consent_version = "legacy-v1"` (collected
   under no recorded consent) and requires the operator to pass the current constant as
   `acknowledge=` to the real run (§6).
5. **Windows edits are not a bump.** Changing `episodes_days` from 90 to 30 in the Privacy
   view is a retention change under the same consent text (audited, applied at the next
   `apply_retention`); it is a bump only if the disclosed number was a fixed promise, in
   which case the page text and the constant change together.

Why this and not "re-consent resets retention" or "bump erases old data": the first
lengthens exposure by accident, the second makes a wording fix destructive. The
measured facts of §4.3 also argue for keeping erasure explicit: it is the only path that
runs the file swap.

## 4. Erasure review

### 4.1 Coverage of the brief's `erase_item` / `erase_profile` against C-04 and the code

| Target | Brief | Code today (`redact_item`, `episode_store.py:1238-1283`) | Finding |
| --- | --- | --- | --- |
| Item + co-visibility closure tombstoned | (1) | `:1256-1268` | fine; keep the processing-time *and* effective assignment ("over-erasure is the safe direction", `:1269-1272`) |
| `embeddings` | (2) delete | `:1275` | fine; banks are a view over `embeddings` (`_banks`, `:620-640`), so they shrink with it (CP3 §3.3 b, accepted) |
| `reobservations`, `containment`, promoted idle frames | (2) delete | n/a | fine; **E5**: a promoted frame shared by two items (§2.6 last bullet) |
| `corrections` rows | (2) **delete** and (4) **blank payload, keep row `erased=1`** | n/a | **E2: the brief says both; pick one.** I recommend (4) (an audit that a correction existed, with ids gone) *and* `_corrections`/`_assignments` (`:571-574, :589-618`) filtering `erased=0`, because `json.loads(NULL)` raises and a blanked row would otherwise break every replay. Either way, every correction touching an erased item touches only items inside the closure (a link merges their observations, an unlink/assign creates an item holding one of the erased episodes), so replay of the survivors is unaffected; the tester should assert that `rebuild_all` after erasure equals `current_items`. |
| `local_observations.record` | (3) stub `{"erased": true, "observed_at_ms"}` | `record=NULL, candidates=NULL` (`:1274`) | **E3: the stub breaks the sentinel.** Eleven readers select `record IS NOT NULL` (`:526, :589, :628, :659, :750, :906, :960, :981, :1053, :1109, :1120`) and then index `observation["label"]`, `["frame_id"]`, `["bbox"]`. A stub passes the filter and crashes, or worse projects. `observed_at_ms` is already a column of the row (`:89`), so the stub adds nothing. Keep `record = NULL` and add `erased_ms INTEGER` if a marker is wanted. If the coordinator insists on the stub, every reader changes and the tester covers each. |
| Late revision of an expired or reduced episode | silent | `ingest_episode` `:346-347` parses the newest accepted revision's bytes for the superset check | **E8: two crash/acceptance paths.** (i) After rule (a) the newest accepted revision has `packet = NULL` but no tombstone, so `bytes(None)` raises inside the request (today only `redact_item` NULLs packets, and it tombstones first, `:1279-1280`, so `:331-337` returns before `:347`). Expiry must set `redacted = 1` with the reason and the ingest must answer `conflict`/`processing_status: "expired"` for a late revision, not 500. (ii) After reduction the stored `landmarks` list is empty, and `_superset` (`:155-158`) tests `all(... for value in old[field])` over an empty list, which is True: any later landmark list passes, so a revision arriving after 72 h is accepted as `revised`, queued, and brings raw landmarks back for another window. Decide: compare against the summary's frame ids, or classify a revision arriving after reduction as `conflict` (the MEMORY review's rule). In both cases reduction and expiry are per revision (`received_at_ms` of the row), never per episode. |
| `item_names.name`, `local_audit.detail`, `corrections.payload` | (4) blank, row kept `erased=1` | names `:1276`; audit and corrections untouched | fine (audit detail is ids-only today, §1.2; blanking is future-proofing) |
| Packet bytes | (5) NULL + `redacted_reason = "erasure"` | `packet=NULL, redacted=1` (`:1280`) | fine; `_keyframe_bytes` (`:943`) and `process_pending` (`:373`) already honour `redacted=0` |
| `current_items` | **not listed** | `DELETE` (`:1277`) + projection rebuild by the next writer | **E6: say it.** The projection carries name, location text and bbox; `erase_item` must delete the rows and rebuild in the same transaction, and `erase_profile` must empty it. |
| `local_cannot_links` | not listed | untouched | ids only; keep; say so in the report (`cannot_links_kept`) |
| `episode_jobs` | not listed | `status='redacted'` (`:1281`) | keep |
| Audit row with counts only | (6) | `:1282` | fine; the report returned to the route must also be counts (never item ids of third parties in the closure) |
| v1 tables on `erase_profile` | silent | n/a | **E7**: §1.3 item 5 and §6 |
| `calibrations` on `erase_profile` | "stay (not personal)" | n/a | true for `synthetic`/`cute`/`holoassist`; `own-footage` is derived from the household's images: delete those rows (§8 Q6) |
| `retention`, `migrations`, tombstones, audit rows | survive | n/a | correct: they are the record that erasure and consent happened |
| `VACUUM INTO` + swap | `erase_profile` only | n/a | §4.3 |
| `rebuild_all`, `as_of`, `/history`, `/evidence`, chat never resurrect | required | `_project` filters `record IS NOT NULL` (`:750`); tombstones apply by `at_ms` (`:757`), so an `as_of` *before* the erasure does not apply the tombstone, and the only thing that keeps erased content out of a pre-erasure `as_of` view is the NULL record | holds today **because of the NULL sentinel** (E3 again). The tester's P-107 markers must include an `as_of` earlier than the erasure. |
| Resent packet refused | required | `ingest_episode` `:331-337` | holds for episodes already ingested; **not for episodes never ingested** (§4.2 item 1) |

### 4.2 Where erased content could resurrect

1. **The browser mirror's unsent packets.** `RetryQueue` keeps a packet in IndexedDB
   until a matching ack (`memory-queue.js:126-129`) and retains rows older than 7 days
   with a warning (`:98-99`). A packet captured *before* "Erase everything" and uploaded
   *after* it has a new `episode_id`, is not tombstoned, and is ingested. That is not the
   erased content coming back, but it is a picture of the home from before the user
   said "erase everything", arriving after. Fix (two halves): the browser clears its own
   mirror when the erase-all report arrives (it issued the request); and the server
   refuses a packet whose wall-clock end (`clock_anchor.wall_ms + t_end_ms -
   clock_anchor.mono_ms`, already computed at `:327`) precedes the profile's last
   `erased_at_ms` (a new column on `retention`), ack `status: "conflict"`,
   `processing_status: "erased_before"`. Same rule for `POST /api/idle`. A second device
   still holding packets is then covered.
2. **The persistent rollback journal.** Measured (Appendix A): after the erasing
   transaction, `<db>-journal` holds the pre-images of every page that transaction
   modified, i.e. the erased content, until later transactions overwrite those bytes; the
   `VACUUM INTO` copy holds none of it, and the swap as described leaves the old journal
   beside the new file. §4.3.
3. **Freelist pages in the main file** when `secure_delete` is off (`erase_item` does not
   vacuum): 61 marker copies survived a `UPDATE ... NULL` + `DELETE` transaction in the
   probe with `secure_delete=OFF`; 0 with it ON. The sandbox build compiles
   `SQLITE_SECURE_DELETE` (default ON); the laptop's Python 3.11.0 `sqlite3` DLL is
   python.org's and I expect the default OFF there (UNVERIFIED; the tester prints
   `PRAGMA secure_delete` and `PRAGMA compile_options`). A P-107 byte scan that passes
   on CI can fail on the laptop. §4.3.
4. **`current_items`** if the projection is not rebuilt in the erasing transaction (E6).
5. **`corrections` replay** if blanked rows are not filtered (E2).
6. **A stub record** if E3 is implemented as written.
7. **Legacy v1 tables** untouched by `erase_profile`, then surfaced by a later
   `migrate_v1` as `source: "legacy_v1"` rows (E7): not erased content returning, but
   content the user believed erased.
8. **Page memory in the browser**: decoded evidence bitmaps and `blob:` URLs live until
   the view re-renders; after an erase the Privacy view must reset the item/evidence
   views (`resetPrivateUI`-style) rather than leave the last photo on screen. Safari's
   tab snapshots and the OS screenshot cache are outside the app; the UI copy must not
   claim them (§4.4).
9. **Logs**: none write payloads (`memory_app.py` has no `logging`/`print`; the worker
   stores the literal `local_processing_failed`, `episode_store.py:513`). Uvicorn access
   logs carry item ids in URLs: ids only. Keep it that way; the new routes must not log
   bodies.
10. **Exports and backups: none exist** (no export route, no backup job, no `.backup()`
    call anywhere in `perception/` or `server/`; `migration_plan` is read-only). Say so in
    the Privacy view ("Pam makes no copies of its database") and keep it true: the first
    export feature is a G-PRIV item of its own (CP3 §3.3 f: an embedding export is a
    personal-data export).

### 4.3 Is the `VACUUM INTO` swap described truthfully?

The brief's words ("documented as reducing, not guaranteeing, residue — no forensic
claim") are the right claim. They are true of the mechanism only if three things the
brief does not say are also done; without them the claim is still "no forensic
guarantee" but the reduction is much smaller than the reader assumes:

1. **Pre-create the target through `private_append_fd`.** Measured: a `VACUUM INTO`
   target that SQLite creates itself is `0644` under umask 022 (world-readable, the exact
   B-09 failure); a pre-created empty `0600` file keeps `0600` and `VACUUM INTO` fills it.
   On Windows the same pre-creation gives the protected DACL (`private_files.py:52-97`).
2. **Discard the old `-journal` (and any `-wal`/`-shm`) in the swap.** Measured: after the
   erasing transaction the PERSIST journal holds 34-60 copies of the planted marker (the
   pre-images), survives `close()`, and survives the swap. The swap sequence must be:
   `VACUUM INTO <private tmp>`; close every connection; `os.replace(tmp, db)`; truncate
   the old journal to zero bytes through its private fd and unlink it (truncate first,
   so the unlink's residue is of zeros); open the new file and let SQLite create a fresh
   journal through the existing `_private_file` path. The `sidecar_report()` the brief
   adds should run after the swap and be part of the erase-all test.
3. **`PRAGMA secure_delete=ON` on every connection** (`object_memory.py:176-179`, one
   line next to `journal_mode`). It is the documented SQLite mechanism for overwriting
   deleted content with zeros in the main file *and* in the journal/WAL as pages are
   freed; it costs a little I/O. It makes `erase_item` (which does not vacuum) leave no
   plaintext in freelist pages, and makes the P-107 byte scan meaningful on the laptop.
   Record `PRAGMA secure_delete` in `sidecar_report()`.

What remains outside the app's control after all three, and must be said rather than
hidden: the unlinked old file's blocks on disk (SSD wear levelling means even an
overwrite is not a guarantee), the OS page cache, and any backup or sync the computer
makes of the folder (Time Machine, File History, OneDrive/iCloud if the folder is in a
synced location). That is the content of the "no forensic claim".

### 4.4 UI copy that must change or must be written carefully (Builder C)

- Existing copy is fine: "Nothing is deleted." (`memory.js:402, :425`) and "Corrections
  are recorded, never deleted" (`memory.html:81`) are true statements about corrections.
- New copy, required wording (or equivalent that keeps every clause):
  - Erase item: "Erase this item? Pam will remove its photos, its appearance signature
    and its written record from Pam's database on this computer, and also any items
    that appear in the same photos. This cannot be undone. Residue in this computer's
    storage, in the file Pam keeps until its next write, and in any backups your computer
    makes is not guaranteed to be gone."
  - Erase everything: same, plus "the camera's own stored captures on this phone that
    have not yet been uploaded will also be discarded" (once §4.2 item 1 is built) and
    "settings and the record that an erasure happened are kept".
  - Never: "permanently deleted", "securely wiped", "removed from your device", "gone
    forever". "Erased from Pam's database" is the phrase.
  - Retention settings: "Photos are kept for {N} days, hand positions for {H} hours, and
    background stills for {I} hours. Shortening a window applies at Pam's next clean-up
    (within 5 minutes while Pam is running)."
  - Reports: counts only ("Erased 3 items, 7 photos, 7 signatures"); never list the
    ids of the co-visible items that went with the one the user chose, by name, unless
    the user is told *before* confirming which other items will go (better: show their
    names in the confirmation dialog, since over-erasure of a named item without warning
    is its own surprise).

## 5. B-08: no SQL roles, no permission triggers

Confirmed in the design and in the tree: the schema has no `TRIGGER`, `ROLE` or
`SET ROLE` anywhere (`grep -i` over `*.py`: none); erasure is a method
(`redact_item` today, `erase_item`/`erase_profile` in the plan) behind the same closed
`ACTORS` rule as corrections (`episode_store.py:33-42`), with the server passing the
literal role (`memory_app.py:31`, `CORRECTION_ACTOR`) and the request body carrying only
a confirmation token (`{"confirm": "<item_id>"}` / `"ERASE EVERYTHING"`), never an actor.
Two things to keep it that way:

1. The `redact_item` alias must take `actor` too (`redact_item(item_id, actor)`); an
   alias without it would be an unaudited door around the rule.
2. `erase_profile` is the one operation whose authorisation is thin in a one-PIN app:
   the caregiver PIN session can erase the whole ledger. That is by design (the family
   owns the data), but the typed confirmation is the only brake; the route should also
   require the session to be fresh (re-enter the PIN within the last N minutes, or
   re-authenticate in the dialog) so a left-open tab cannot erase everything in one tap.
   Coordinator's call (§8 Q8); not a B-08 point.

## 6. Migration (B-10)

Converting legacy evidence as **provisional-only** is correct and is the only honest
option: v1 identity was a VLM's "match"/"new" verdict against a gallery, with no
calibration record, no embedder tag and no approval (`object_memory.py:364-382`); the
contract forbids a "guessed legacy-to-trusted model identity migration". `source:
"legacy_v1"`, `identity_state: "provisional"`, no image, `actor: "unknown"`.

What the legacy data carries and what migration must not copy (table in §1.2):

| Legacy field | Content | Rule for `migrate_v1` |
| --- | --- | --- |
| `candidates.payload.frames[]`, `.crop`; `observations.record.frames/crop` | **file-system paths** (they reveal the OS user name and folder layout; `_media_path` requires them under the DB directory, `:223-229`) | never copied into the new record; `reference_image: null` (the brief says so). The files themselves are outside the ledger; the report should count them ("legacy media files on disk: N, not imported, not deleted") so the user can delete the run folder knowingly. |
| `payload.location` (`location_at`: `{lat, lon, accuracy_m}` or a status) | **geolocation** | never copied; the CP1+ schema has no geolocation field and must not grow one by accident (not into `location_text`, not into `record`). |
| `verification.scene.description`, `.appearance`, `.identity_evidence`, `.reason`, `.actor_evidence[]` | VLM prose, up to 600 chars each, about the scene and the people in it ("a woman in a blue cardigan ...") | never copied. `location_text` comes from `scene.room` and `scene.surface` only (short structured fields), joined as "{surface}, {room}" when both exist, else whichever exists, else null. The brief's "from the legacy description" must be read this narrowly. |
| `verification.actor` (wearer/bystander + confidence) | a heuristic attribution (CLAUDE.md: contact is not ownership) | never copied as `actor`; the new record's `actor` is `"unknown"`. |
| `objects.name` (VLM label or user name) | NAME | copied as the observation `label` (it is the item's name); if the v1 object was user-confirmed/renamed (`decisions` action `confirm_tracking`/`resolve_identity`), also write an `item_names` row so the name survives the way a CP1 name does. |
| `observations.action` (`placed`/`picked_up`/`unknown`) | event type | `outcome`: `placed_on_surface`/`picked_up`/`uncertain`; `location_status` follows the contract (a provisional identity is never `placed`). |
| `observed_at` (seconds, float) | timestamp | `observed_at_ms = round(observed_at * 1000)`; `clock_status: "ok"` only if plausible, else `"implausible"` as `ingest_episode` would. |
| `candidates` in `review`/`failed`/`rejected`/`dropped` | not evidence | not migrated (only `observations` rows, which exist only for verified or user-resolved events). |
| `api_calls`, budgets, leases | MONEY | untouched (contract). |
| `bindings`, `decisions` | IDS; `decisions.detail` can hold a name | untouched by migration; erased by `erase_profile` (E7). |

Consent acknowledgement: yes, required. The legacy rows were collected under the HackMIT
pipeline with no recorded consent or retention; importing them under the current
disclosure would misstate their provenance. `migrate_v1(dry_run=False, actor,
acknowledge=<CONSENT_VERSION>)` where the value must equal the current constant (else
`ValueError`, 400), recorded in the `migrations` row, and every imported record carries
`consent_version: "legacy-v1"` so the data-class map and any later per-class erasure can
find them. The `PAM_ALLOW_MIGRATION=1` env gate and the dry-run-first flow are right;
dry-run samples (up to 5) must be the *converted* rows, not the legacy rows, so the
operator sees that no prose, path or coordinate made it through.

Transaction and idempotence as planned (one transaction, `already_migrated` on a second
run, rollback on any exception) are what B-10 asked for.

## 7. Commercial path (short; the analysis in `COMMERCIAL.md` §4.2, §4.6-4.7 and `OVERSIGHT_CP2.md` §2-§3 stands)

- **Agency (HIPAA business associate) customer.** A BAA requires return or destruction of
  PHI at termination and audit controls; CP4's `erase_profile` (destruction) and
  `local_audit` (who-as-role, when, what-as-counts) are the mechanisms, and the
  configurable windows (7..365 days) let an agency's retention policy be applied without
  code. Two things an agency questionnaire will ask that CP4 should get right now: the
  audit rows must not be erasable by the user (they are not, by design), and
  `set_retention` changes must be audited with old and new values (they are, if §3 item
  3 is adopted). The 24 h idle cache enlarges the PHI-adjacent surface on the laptop
  (images of a client's home every 30 s); the agency data-flow diagram must show it.
- **Family customer (FTC HBNR).** No change to the "very likely applies" analysis;
  "breach of security" includes unauthorised access to the laptop's database, so the
  B-09 sidecar privacy and the secure-delete point (§4.3) are breach-surface controls,
  not only hygiene. The breach plan should name the idle cache and the journal.
- **Biometric states.** CP4 is the engineering half of `COMMERCIAL.md` §4.4(c) ("store
  landmarks only ... as long as the localizer needs them, then reduce"); the legal half
  (written releases or no pilot in IL/TX/WA) is unchanged, §2.3.
- **Nothing new in the dependency register.** CP4 adds no runtime dependency by the
  plan's acceptance line; `docs/LICENSES.md` needs no row in pass 1 (pass 2 checks the
  requirements files). The CP3 deferral "re-pin onnxruntime at CP4" (CP3 §7 Q10) is open
  and is a one-line register edit when the coordinator decides.

## 8. Open questions for the coordinator

1. **Rule 13 mode.** Continuous `reobserve` in the worker (plan) versus on-demand (Part
   1 rule 13, FINANCE §9 costing)? If continuous stays: adopt the bounds in §2.8
   (per-item minimum gap, one promotion per item per day, two negatives before `gone`)?
2. **Embeddings after keyframe expiry** (§1.3 item 2): keep with the item and disclose, or
   expire with the keyframe?
3. **Promoted idle frames** (§1.3 item 1): confirm they follow `episodes_days` rather than
   "never expires".
4. **E2/E3**: confirm `record = NULL` (not a stub) and "blank + `erased=1` + replay filter"
   (not delete) for `corrections`.
5. **§4.3 additions**: pre-created private target, journal discard in the swap,
   `secure_delete=ON` on every connection. Any objection to the I/O cost of secure
   delete?
6. **`calibrations` on `erase_profile`**: delete `source = 'own-footage'` rows (derived
   from the household's images), keep the rest?
7. **Re-observation embeddings**: is an `embeddings` row written for a `present`
   observation (then it is in the map as VEC, erased with the item) or is the vector
   discarded after matching?
8. **Erase-all authorisation**: require a fresh PIN in the dialog (§5 item 2)?
9. **`consent_version` ownership** (§3): constant in code with an acknowledge route,
   removed from `PUT /api/retention`? And the row stamps (`consent_version` on
   `episode_revisions`/`idle_frames`) now, or at CP5 with the notices page?
10. **Pre-erasure captures arriving after erase-all** (§4.2 item 1): server rule
    (`erased_at_ms` on `retention`, refuse older packets) plus browser mirror clear, in
    CP4?
11. **Legacy content on `erase_profile`** (E7) and the legacy media files on disk (count
    and report, never delete) — confirm.
12. **The rig's own landmark release** (§2.3 item 1): who signs, where it is kept. A
    human action; I can draft the page.
13. **BIPA 15(a)/(b) text**: I could not open the section page in this pass (permission);
    the wording in §2.1 is from memory. Someone with a browser confirms it before any
    consent text is drafted from this document.

## 9. Go/no-go conditions for closing G-PRIV at the end of CP4

The diff review (pass 2) must confirm each of these with `file:line` evidence; any one
open keeps G-PRIV pending. Conditions 1-9 are what the gate itself demands
(`RESEARCH_LOG.md`: "Data-class map covering SQL and derived copies, not just files; an
approved deletion/replay policy and synthetic deletion tests"); 10-13 are this
document's additions.

1. **Every table and column in the map exists as described, and nothing else was added
   to the schema** (a new column that holds content is a new row in §1.2).
2. **Erasure reaches every content cell in the map's "removed by" column** in one
   transaction: packet bytes, promoted idle frames, embeddings, reobservations,
   containment, observation records (NULL), names, audit detail, corrections payload
   (blanked, filtered on replay), `current_items`; the report is counts only.
3. **P-107 synthetic markers vanish** from every table, from `rebuild_all`, from `as_of`
   views both before and after the erasure time, from `/api/items`, `/history`,
   `/evidence`, chat, the observation-image routes, and from a byte scan of the main
   file **and the `-journal`** after `erase_profile`, with `PRAGMA secure_delete` reported
   and the test run at least once with it forced ON and once with it forced OFF (the OFF
   run must still pass after `erase_profile`, and the ON run after `erase_item`).
4. **Tombstones refuse resends**; and (if §8 Q10 is adopted) a packet whose wall-clock end
   precedes `erased_at_ms` is refused.
5. **Landmark reduction**: packets older than `landmarks_hours` carry `landmarks: []` and
   a `landmark_summary` whose schema is closed (`extra="forbid"`) with exactly
   `frame_id, t_ms, hands[{hand_bbox, busy, basis}]`; no `world_landmarks`, `reference`,
   `curl_ratio`, `palm_centre` anywhere in a stored packet after reduction; a client
   packet carrying `landmark_summary` is 400; digests unchanged; `item_image` still
   serves; a revision whose job is not terminal is not reduced; a revision arriving
   after reduction is `conflict` (or checked against the summary's frame ids) and a
   late revision of an expired episode is answered, never a 500 (E8); reduction and
   expiry are per revision.
6. **Idle frames**: never listed or served unless promoted; hard-deleted at expiry;
   caps enforced; promoted frames follow `episodes_days` (§8 Q3); the evidence DTO marks
   `source: "reobservation"`.
7. **B-09**: both database file and journal pre-created privately; `sidecar_report()`
   true after writes and after the erase-all swap; the `VACUUM INTO` target pre-created
   through `private_append_fd` (mode `0600` / protected DACL measured by the tester, not
   assumed); the old journal truncated and removed in the swap.
8. **B-08**: no triggers, no roles; `erase_item`, `erase_profile` and the `redact_item`
   alias all require `actor` from the closed set; bodies carry only the confirmation
   token; 409 on mismatch; the env gate on migration.
9. **B-10**: a v1 fixture with planted prose, a path and a coordinate migrates to rows
   that contain none of them (`location_text` from `room`/`surface` only), all
   `provisional`, `source: "legacy_v1"`, `consent_version: "legacy-v1"`; dry-run writes
   nothing; second run `already_migrated`; injected failure rolls back everything;
   `api_calls` untouched; the real run requires `acknowledge=` equal to the current
   version.
10. **Consent-version rule** (§3) adopted in some form, with `consent_version` not
    settable from the browser and a capture stop on an unacknowledged bump; or the
    coordinator records a different rule in this document.
11. **No new runtime dependency; no request leaves the origin** (the Playwright
    no-egress assertion with idle capture running); the CP4 JSON routes satisfy the CP3
    "no vector" assertion.
12. **UI copy** per §4.4: no "permanently deleted"/"securely wiped"/"removed from your
    device" anywhere in `phone/`; the residue sentence present in both erase dialogs; the
    idle-capture disclosure sentence on the camera page; promoted photos labelled as
    idle captures.
13. **Open questions 1-11 answered** and reflected in `BUILD_PLAN.md` or in pass 2 of this
    file.

Until pass 2: **G-PRIV stays pending** (the plan is reviewable; the gate closes on code).

## Diff review, pass 2 (2026-10-10, after the coordinator's decisions)

Reviewed read-only in the working tree over `77b769e`: `git diff` (17 modified files,
3,705 insertions) and the untracked files `perception/consent.py`, `hand_hull.py`,
`reobservation.py`, `scripts/cp4_selfcheck.py`, `server/test_cp4_*.py`,
`server/fixtures/cp4/`. Line numbers below are the working tree at review time. What I
ran (read-only, sandbox Python 3.13, SQLite 3.45.1): `server.test_cp4_erasure` +
`server.test_cp4_retention` 16 tests, **1 failure** (a test-fixture defect, T1 below, not
a production defect); `server.test_cp4_idle` + `test_cp4_containment` +
`test_cp4_migration` 35 green; `server.test_cp4_api` 10 green; the earlier
`test_cp3_identity`, `test_cp3_api`, `test_memory_bootstrap`, `test_cp2_staleness` 75
green. `phone/test/test_ui_smoke.py` (Playwright) not run here. The tester's suites are
the tester's verdict; where I ran something I say so.

Coordinator decisions received and checked against the code: (1) bounded continuous
rule 13; (2) embeddings kept and disclosed; (3) promoted frames follow `episodes_days`;
(4) stub + `erased` column, corrections blanked and filtered; (5) `secure_delete=ON`,
private `VACUUM INTO` target, journal truncated and unlinked; (6) `own-footage`
calibrations deleted on erase-all; (7) no embeddings row from re-observation; (8)
erase-all needs the PIN again; (9) consent rule adopted (`perception/consent.py`,
`acknowledged_version`, 409 `consent_required`, `consent_version` removed from PUT,
rows stamped); (10) 409 `erased_before` with a 5-minute tolerance; (11) `erase_profile`
erases v1 rows, legacy media counted, migration copies `surface`/`room` only; (12)/(13)
human; plus `episodes_days` default 30, superseded revisions NULLed at 72 h,
`reobservations` rows expire with `episodes_days`.

**Verdict in one line: the diff implements every coordinator decision and every §9
condition that code can meet, the P-107 byte scan passes on the main file and the
sidecars, and no forensic claim appears anywhere; one medium finding (a hand-dominated
crop still embeds the hand because the pooling fallback ignores the hull, F1) and one
tester gap (no test exercises the hull at all, T2) should be closed before any rig run
that stores vectors; G-PRIV can close on this diff for the deterministic path, with the
human items listed in P2.6.**

### P2.1 Decisions and plan items against the tree

| Decision / plan item | Status | Evidence (file:line, working tree) |
| --- | --- | --- |
| (1) Rule 13 continuous but bounded: hourly refresh per item, unchanged-frame gate, per-UTC-day budget 300 s with `reobs_deferred` | done | `perception/reobservation.py:58-70` (`REOBS_REFRESH_MS = 3600 * 1000`, `REOBS_CPU_BUDGET_S = 300`, `REOBS_GATE_MAX`), `:308-322` (budget read, previous frame per item), `:335-350` (gate: `gated=1`, no registration, no promotion since `refresh` stays False), `:361-366` (budget spent → `reobs_deferred`, decision stays diff-only), `:382-384` (promotion only when `refresh_due`), `:394-395` (`maintenance_counters` per day); the `gated` and `bbox` columns `episode_store.py:188-193, :236-237` |
| (2) Embeddings kept until item erasure, disclosed | done | `episode_store.py:2048-2057` docstring and `:2069-2075` (expiry NULLs the packet only); `consent.py:27-28` ("numeric appearance signature of each item until you erase that item"); erasure deletes them `:1656`, `:1774` |
| (3) Promoted frames follow `episodes_days` | done (rows deleted, not `jpeg` NULLed; the observation then reads `evidence_expired`) | `episode_store.py:2088` (`DELETE FROM idle_frames ... promoted=1 AND received_ms<cutoff`), `_evidence_expired` `:1080-1083` (missing frame → expired, `reference_image` null), `_keyframe_bytes` `:1266-1269` |
| (4) Stub `{"erased": true, "observed_at_ms"}` + `erased` column; every reader filters; corrections blanked and filtered | done, **verified reader by reader** (P2.2 item 1) | `LIVE = "record IS NOT NULL AND erased=0"` `episode_store.py:90`; stub written `:1653-1654`, `:1771-1772`; corrections `:1669-1683` blanked `payload='{}'`, `erased=1`; replay filter `_corrections` `:754` (`erased=0`) |
| (5) `secure_delete=ON`; private `VACUUM INTO` target; old journal truncated then unlinked | done | `object_memory.py:202-205` (every connection); `_vacuum_swap` `episode_store.py:1796-1848`: target and its would-be journal pre-created through `private_append_fd` `:1808-1809`, `VACUUM INTO` `:1812`, `quick_check` + `user_version` `:1815-1822`, fsync + `os.replace` `:1823-1825`, `_drop_sidecar` (ftruncate 0, fsync, unlink) `:1828-1829, :1851-1868`, directory fsync `:1830`; in-place `VACUUM` fallback reported as `in_place`, never raised over a committed erasure `:1832-1848` |
| (6) `own-footage` calibrations deleted on erase-all | done | `episode_store.py:1784` |
| (7) No embeddings row from re-observation | done | `reobservation.py` has no `INSERT INTO embeddings`; the matched vector is discarded after `ConformalMatcher.match` `:369-375` |
| (8) Erase-all requires the PIN again, constant time, under the login rate limit | done | `memory_app.py:1192-1219`: `pin_attempt(request)` (shared counters with login, `:1021-1039`), `hmac.compare_digest` for the phrase `:1206` and the PIN `:1213`, 409 `pin_mismatch`; `processing_lock` + exclusive `StoreGate` `:176-215, :1216-1217` |
| (9) Consent rule: constant + disclosure in `perception/consent.py`; `acknowledged_version`; capture refused 409 until acknowledged; `consent_version` not in PUT; rows stamped | done | `consent.py:18, :21-34, :36`; `episode_store.py:1983-1998` (`acknowledge_consent`, audited, must equal the constant), `:2000-2013` (`_capture_allowed`), `:446` and `:1905` (called in `ingest_episode` / `ingest_idle`), `:474-475` and `:1925-1927` (rows stamped `CONSENT_VERSION`); `memory_app.py:164` (`STORE_REFUSALS` → coded 409), `:1128-1147` (`GET/POST /api/consent`), `:1159-1174` (`PUT /api/retention` allowlist is the three windows only; any other key 400 through `json_body`); browser gate `memory.js:316-334` (camera start disabled until `ok`; disclosure rendered with `textContent`) |
| (10) Pre-erasure captures refused, 5-minute tolerance | done | `episode_store.py:86` (`ERASED_BEFORE_TOLERANCE_MS`), `:2012-2013`, `:1787-1789` (`erased_at_ms` written by `erase_profile`); episode check uses the packet's wall **start** `:442, :446`; browser: `memory-queue.js` drops an `erased_before` packet and counts a gap, keeps a `consent_required` one; `queue.clear()` + `discardUnsaved()` after erase-all `memory.js:526` |
| (11) `erase_profile` erases v1 rows; legacy media counted never touched; migration copies `surface`/`room` only | done | `episode_store.py:1775-1781` (objects, candidates, observations, bindings deleted; `decisions.detail` blanked; `api_calls` kept), `:1695-1705` (a migrated item's legacy rows on `erase_item`); `_legacy_media` `:2148-2161` (paths counted, never opened), `:2237`; `location_text` from `scene.surface`/`scene.room` only `:2214-2219`; `actor: "unknown"`, `identity_state: "provisional"`, `reference_image` null `:2225-2234` |
| Retention default 30 days; superseded revisions NULLed at 72 h; `reobservations` expire with `episodes_days` | done | `episode_store.py:71` (`RETENTION_DEFAULTS`), `:76` (`SUPERSEDED_TTL_MS`), `:2076-2087` (`redacted_reason='superseded'`; the keyframe is still served from the newer accepted revision, `_episode_packets` `:1276-1294`), `:2089` |
| Idle keyframes: strict schema, 256 KiB cap, caps and eviction, never listed or served unless promoted | done | `episode.py:245-279` (`IdleFrame`, `StrictModel`), `:304-309` (`parse_idle`); `episode_store.py:1889-1928` (`ingest_idle`: consent, idempotent resend, per-device daily cap, byte cap with oldest-unpromoted eviction), `:1930-1944` (`expire_idle` hard delete); no route reads `idle_frames` except through an assigned re-observation row (`_keyframe_bytes` `:1266-1269`); `memory_app.py:1103-1126` (`POST /api/idle`, ack never echoes the frame) |
| Landmark reduction: `landmarks: []` + closed `landmark_summary`; client packets carrying it 400; digests unchanged; `item_image` works; per revision | done; superset rule changed (see F2/E8) | `episode.py:92-111` (`SummaryHand` = `hand_bbox`, `busy`, `basis`; `LandmarkSummary`; both `StrictModel`, `extra="forbid"`), `:200` (server-only field), `:241` (excluded from the semantic digest); `episode_store.py:433-436` (client packet refused), `:2090-2104` (per revision by `received_at_ms`), `_reduce_landmarks` `:2113-2145` (summary built from `hand_bbox` + `hand_busy` verdict only; parse check; keyframes preserved); `_superset` `:257-262` (landmarks superset-neutral once reduced) |
| Hand hull and crop pad; `RECIPE = "r2"` | done, in memory only; **F1** on the fallback | `hand_hull.py:45-70`, `:73-85`; `episode_store.py:531-532` (hull per keyframe, passed to `_embed_region`), `:682-721` (hull subtracted from the pooling mask; no mask or hull is ever stored); `identity.py:82-92` (`CROP_PAD`, `padded_crop_box`), `:210` (`RECIPE = "r2"`) |
| B-09: db and journal pre-created privately; `sidecar_report()`; `is_private` on both platforms | done (Windows path unverified here) | `object_memory.py:189-192`, `:166-176` (`sidecar_report`, names only); `private_files.py:112-134` (`is_private`), `:137-200` (`_windows_is_private`: owner SID, protected DACL, allowed ACEs for the user only) |
| B-08: no triggers or roles; erasure behind the actor rule; confirm tokens only | done | no `TRIGGER`/`ROLE` in the tree; `erase_item` `:1717`, `erase_profile` `:1749` `_check_actor`; `redact_item` alias `:1595-1597` (F6); routes pass `CORRECTION_ACTOR` (`memory_app.py:1190, :1217`), bodies `{confirm}` / `{confirm, pin}` only |
| B-10: dry-run writes nothing; real run one transaction + `migrations` row; idempotent; env gate; samples are converted rows | done | `episode_store.py:2163-2256`; `memory_app.py:1221-1235` (`PAM_ALLOW_MIGRATION` read per request, actor `operator`) |
| Server: `/api/retention` GET/PUT, `/api/items/{id}/erase`, `/api/erase-all`, `/api/migrate`, `/api/consent`, worker maintenance every batch-with-work or 5 min, health counts, `present_item` whitelists `inference`/`stale_since_ms`/`evidence_expired`, evidence rows carry `source` | done | `memory_app.py:1149-1235`, `:655-666` (`maintain_once`), `:1077-1095` (health: numeric counts, consent state, last reobserve counts), `:899-912`, `:978` |
| Browser: idle capture conditions, counters, Privacy view, erase flows, inferred / negative-reobservation / expired rendering, consent gate | done; **F3** (promoted photos not labelled) | `memory-camera.js:18` (constants), `:236-266` (`idleTick`: controller idle, motion off, a *measured* no-hand run ≥ 2 s, one post per 30 s, no mirror), `:268-281`; `memory.html:72-106` (Privacy view, consent gate, erase cards); `memory.js:86` (expired), `:107` (negative re-observation), `:116-135` (inferred), `:410-555` (Privacy view, erase-all), `:678-702` (erase item) |
| Tester: the six suites + smoke extension; no skipped-green | present; my runs above; **T1-T4** | `server/test_cp4_*.py`; `phone/test/test_ui_smoke.py` tests 10/20/30/40/50/99 added |
| No new runtime dependency; no request leaves the origin | done for the first (requirements files untouched in `git status`); the second is the smoke test's `test_99_no_request_left_the_origin`, not run here | - |

### P2.2 The confirmations the coordinator asked for

1. **Every reader filters erased rows.** The 14 `SELECT ... FROM local_observations`
   sites in `episode_store.py` and 3 in `reobservation.py`, each classified:
   - filter `LIVE`/`erased=0`: `:656` (`_continuity_item`), `:770` (`_assignments`),
     `:809` (`_banks` join), `:840` (`_co_visible_items`), `:935` (`_project`), `:1219`
     (`_item_rows` → history, evidence), `:1305` (`observation_image`), `:1326`
     (`item_image`), `:1398` (`unlink_observation`), `:1454`, `:1465`
     (`assign_observation`), `:1046` (`item_names ... erased=0`); `reobservation.py:218`
     (`_reobservation_targets`);
   - correctly unfiltered: `:565` and `reobservation.py:416` (signature-existence
     checks, so an erased observation id is never re-created), `:1076` and
     `reobservation.py:459` (read the projection's own `observation_id`, which is live
     by construction; `:1079` also tolerates a NULL record), `:1605, :1638, :1641,
     :1755, :1770` (the erasure itself, which must see every row);
   - `_keyframe_bytes` `:1261-1265` additionally refuses a NULL record and a stub.
   The P-107 suite plants markers in every text field and checks every table, the
   routes, `rebuild_all` and `as_of` before and after the erasure
   (`test_cp4_erasure.py:114-145, :255-265`); green in my run. **Confirmed.**
2. **`secure_delete` and the private `VACUUM` target.** `PRAGMA secure_delete=ON` on
   every connection (`object_memory.py:205`); the target and a would-be journal are
   created through `private_append_fd` before `VACUUM INTO` (`episode_store.py:1808-1809`),
   so the measured `0644` case of Appendix A cannot occur; the old journal is truncated
   to zero, fsynced and unlinked (`:1851-1868`), which is exactly the Appendix A
   remedy; the swapped file is checked (`quick_check`, `user_version`) before it
   replaces the original. The tester scans the main file **and every sidecar present**
   after `erase_profile` (`test_cp4_fixtures.py:510-520`, `test_cp4_erasure.py:291-293`)
   and asserts `0600` on the file and the sidecars (`:309, :377-380`); green here.
   **Confirmed** (T3: no test asserts the PRAGMA itself).
3. **No forensic claim in UI copy or docs.** `grep -i "forensic|permanently|securely
   wiped|wipe"` over `phone/`, `perception/`, `server/memory_app.py`, `scripts/`,
   `docs/BUILD_PLAN.md`, `docs/FINANCE.md` finds only negations ("not a forensic wipe",
   `forensic_erasure: False`, "no forensic claim"). Every erase sentence carries the
   residue clause: `memory.html:104` ("Traces may remain on the device or in backups;
   this is a removal from the app's database, not a forensic wipe"), `:118` (erase
   item), `memory.js:508, :531, :685, :697`; the report sentence for the swap says
   "reduces leftover residue" (`:552-553`), not "removes". `consent.py:29-31` says
   "complete removal is not guaranteed". **Confirmed.**
4. **The disclosure text** (`perception/consent.py:21-34`, 889 characters, served by
   `GET /api/consent`, rendered verbatim), sentence by sentence against the §1.2 map.
   Marked **[CHANGE]** where a sentence is inaccurate or a class is missing; everything
   else is acceptable as written.

   > "Pam keeps camera stills on this laptop, not in the cloud." — OK (IMG; the rig).
   >
   > "When a hand moves something, a few stills of that moment are saved with the
   > memory." — OK (keyframes and the carry burst).
   >
   > "While nothing is happening, one still is taken every 30 seconds and kept for 24
   > hours, unless it confirms where an item still is; then it is kept with that
   > item." — **[CHANGE, small]**: "kept with that item" now means "for the same
   > retention window as the memory" (decision 3); say so: "...then it is kept with
   > that item for the same number of days as its other photos."
   >
   > "Hand positions are kept for 72 hours and then reduced to a plain box around the
   > hand." — **[CHANGE, small]**: the HAND class is collected from everyone in view
   > (§2.3 item 2, §2.5 item 4); add "including other people's hands" and the purpose:
   > "Hand positions, including other people's, are used to tell when a hand is busy
   > and to keep hands out of item photos' signatures; they are kept for 72 hours and
   > then reduced to a plain box around the hand. Pam never records whose hand it is."
   >
   > "Stored memories expire after the retention window, 30 days unless you change
   > it." — **[CHANGE, required]**: not what the code does. Only the photos expire
   > (`apply_retention` (a): packet bytes NULL); the written record (what, where,
   > when), the names and the appearance signature stay until erased (§1.3 items 2
   > and 4). The sentence promises more than the system delivers, which is the one
   > kind of inaccuracy a disclosure must not have. Replace with: "The photos of a
   > memory are removed after the retention window, 30 days unless you change it;
   > the written record of what Pam saw, where and when stays until you erase the
   > item."
   >
   > "The app keeps a numeric appearance signature of each item until you erase that
   > item." — OK (decision 2; VEC).
   >
   > "\"Erase this item\" and \"Erase everything\" remove memories from the app's
   > database; traces may remain on the device or in backups, so complete removal is
   > not guaranteed." — OK; optional addition: "Erasing an item also erases the items
   > that appear in the same photos" (the dialog says it; the disclosure could).
   >
   > "Other household members and visitors may appear in the stills and must be told
   > about the camera." — OK (bystander plan sentence; the posted notice and the
   > releases remain the human list).
   >
   > "Nothing is sent to the cloud unless you turn cloud chat on." — OK (cloud chat is
   > 503 "not configured"; when it exists it sends text only, CP3 §3.2 item 2).

   Not covered and acceptable to leave out of the 1,200-character text: names you
   type (NAME; the user's own words, erased with the item), corrections and the audit
   log (ids only), and the earlier app's imported records (say it at migration time).
   Because the text is the thing the user acknowledges, the three changes above are a
   `CONSENT_VERSION` bump by the project's own rule (`consent.py:3-8`): do them together,
   once, before the first rig session, as `rig-2026-10b` (or the next date), so there
   is one acknowledgement, not two.
5. **Consent enforcement order.** `ingest_episode` `:444-453`: `BEGIN IMMEDIATE` →
   `_capture_allowed` (consent `:2010-2011`, then `erased_before` `:2012-2013`) → the
   tombstone check `:447, :450`. `ingest_idle` `:1903-1909`: consent → `erased_before` →
   the idempotent-resend check. Order **consent → erased_before → tombstone,
   confirmed**; the route maps the two store messages to coded 409s before the generic
   400 (`memory_app.py:606-608`), and nothing in the store's message reaches a body.
6. **The landmark summary schema is closed.** `SummaryHand` has exactly `hand_bbox`,
   `busy`, `basis` under `StrictModel` (`extra="forbid"`, `episode.py:28, :92-104`);
   `_reduce_landmarks` writes only those three from `hand.hand_bbox` and the
   `hand_busy` verdict (`episode_store.py:2126-2131`); `reference`, `curl_ratio`,
   `palm_centre` (`hand_busy.py:107`) and `world_landmarks` are never read into the
   summary, and the tester asserts the reduced bytes carry neither `world_landmarks`
   nor the planted raw-coordinate marker and that the hand keys are exactly the three
   (`test_cp4_retention.py:297-325`). `basis` is `str` ≤ 40 rather than the closed
   `hand_busy` set (low, T-note: a `Literal` would pin it). **Confirmed.**
7. **Migration never copies prose, lat/lon or paths.** `location_text` is built from
   `scene.surface` and `scene.room` only (`:2217-2219`); the record (`:2225-2234`) has
   no field for `description`, `appearance`, `identity_evidence`, `reason`,
   `actor_evidence`, `location`, `frames` or `crop`; `actor` is the literal `"unknown"`;
   paths are counted by `_legacy_media` and never stored; `bbox` is `None` and
   `reference_image` therefore null. The tester plants a free description and a
   geolocation in the v1 fixture (`test_cp4_fixtures.py:545, :573`) and asserts the
   description and the media root never appear (`test_cp4_migration.py:120, :124,
   :168-170`); the fixture's coordinates are `1.0`/`2.0`, which no assertion looks for
   (T4). **Confirmed** on the code; the lat/lon assertion is a tester improvement.
8. **Erase-all PIN handling never logs the PIN.** `memory_app.py` has no `logging` or
   `print`; `json_body` raises fixed strings (`:798-805`); the PIN is compared with
   `hmac.compare_digest` and never stored, echoed or put in an exception
   (`:1209-1214`); the only identifiers in a Refused body are the fixed sentences in
   `REFUSALS` (`:155-161`); uvicorn's access log sees the path and status. The browser
   clears the field before sending and after (`memory.js:519`), and the page says so
   (`memory.html:109`). **Confirmed.**
9. **Hosted variant: per-household database files are the design.** The store keys
   every table by `profile_id` and scopes every statement by it; `erase_profile`
   erases rows `WHERE profile_id=?` but `_vacuum_swap` rewrites the **whole file**, so on
   a multi-tenant file one household's erase-all would copy every other household's
   data into a new file (and the P-107 byte scan would be meaningless). The tester's
   `test_cp4_erasure.py:330-337` already shows a second profile sharing the file is
   untouched by the erasure; `docs/FINANCE.md` §9.5 and its open question 15 record
   per-household files as the hosted design for the same reasons (headroom, scan,
   snapshots). From the privacy side: **confirmed and required** — one SQLite file per
   `profile_id` in any hosted deployment (erasure isolation, a scannable file, a smaller
   breach blast radius). I add it to the §9 conditions as a design rule, not a CP4
   code change.

### P2.3 Findings, ranked

- **F1 (medium, production, `perception/identity.py:165-172` with
  `episode_store.py:714-717`): a hand-dominated crop still embeds the hand.** The hull
  is subtracted from the pooling mask, but `_patch_selection` returns `None` ("use all
  patches") when fewer than `MIN_MASK_PATCHES = 4` patches survive — so when the hull
  covers most of the crop (the late-release case CP3 §3.1 named), the fallback pools
  every patch, hand included, and stores that vector under the item. That is the
  opposite of the hull's purpose and recreates the incidental-biometric case §2.7 says
  the hull removes. Fix (small): in `_embed_region`, when a hull is given and the
  surviving mask area is below a share of the crop (CP3's unmeasured 50 %, P-104),
  raise so the observation stays provisional with no embedding (counted as
  `embedding_failed`, which already means "no vector, identity provisional"); and never
  let the all-patches fallback apply when a hull was subtracted. Bump nothing: the
  recipe tag `r2` already names the hull rule, and a calibration made before this fix
  would have been made on hand-polluted vectors anyway.
- **F2 (low-medium, production, `episode_store.py:2091-2092`): reduction can run before
  processing.** The reduction query selects on `received_at_ms` and `reduced_ms` only;
  a revision whose job is still `pending`/`processing` after `landmarks_hours` (the
  laptop was closed for three days) is reduced first, and `_hand_hull` then finds no
  sample (`:686-688`), so the identity crop silently loses the hull (F1 makes that
  worse). Fix: exclude revisions with a non-terminal job (`NOT EXISTS (... status IN
  ('pending','processing'))`), or run the batch after `process_pending` drained (it
  already runs after it; the exclusion is the safe form). §9 item 5 asked for this.
  E8(ii) was resolved differently from my two options: a revision arriving after
  reduction is accepted as a superset when its keyframes, burst and gaps are
  (`:257-262`), which brings raw landmarks in for one more per-revision window and lets
  a client change the landmark list unnoticed. Acceptable (landmarks are not item
  evidence; the window is per revision), recorded as a deviation.
- **F3 (low-medium, browser, `memory.js:601-619`): promoted idle photos are not labelled
  as such.** The server now sends `source: "reobservation"` on evidence rows
  (`memory_app.py:978`), but `evidenceRow` ignores it and captions every photo "Photo
  recorded {when}". §2.6 asked for "Seen by Pam while idle, {time}" so the user can
  tell which pictures were taken with nobody handling anything (the disclosure's
  "unless it confirms where an item still is" sentence is otherwise invisible in the
  evidence list). One string branch.
- **F4 (low, production, `episode_store.py:1658-1659`): a promoted frame shared by two
  items.** Erasing item A deletes the frame A was `present` in; if B had its own
  `present` on the same frame, B's re-observation row now reads "evidence image
  expired" (`_evidence_expired` `:1080-1083`) rather than "erased", and B's
  `reobservations` row stays. No leak (over-erasure is the safe direction, as §2.6
  said); the wording is slightly wrong. Either extend the closure to items sharing a
  promoted frame or add `redacted_reason`-style `erased` marking on the observation
  that lost its frame. Cosmetic until the UI distinguishes the two.
- **F5 (low, production, `episode_store.py:2245-2249`): migrated rows carry no consent
  stamp.** The synthetic `episode_revisions` row has `redacted_reason='legacy_v1'` and
  `consent_version` NULL, and the record has no consent field; §3 item 4 asked for
  `consent_version = "legacy-v1"` so the class is findable. NULL + `legacy_v1` is
  distinguishable today; one literal makes it explicit. Acknowledgement at migration
  time stays open for CP5 by decision.
- **F6 (low, production, `episode_store.py:1595-1597`): `redact_item` alias fixes the
  actor to `"operator"`** instead of taking it. No route calls the alias
  (`memory_app.py` greps clean), so nothing is misattributed today; the alias should
  take `actor` so a future caller cannot bypass the attribution rule.
- **F7 (low, audit, `episode_store.py:2044-2045`): `retention_set` records the new
  fields only**, not the previous values; §3 item 3 asked for `{field, old, new}` so a
  BAA audit can show what the window was. One dict.
- **F8 (low, docs, `docs/BUILD_PLAN.md` "CP4 in detail"): the plan text still says
  `PUT /api/retention {consent_version?, ...}` and "`location_text` from the legacy
  description", and `erase_item` step (2) still says corrections are deleted.** The
  coordinator's decisions supersede them and the code follows the decisions; the plan
  should be edited to match so the next reader is not misled (architect).
- **T1 (tester, `server/test_cp4_erasure.py:349-353`): the one failing test is a
  fixture defect.** `packet_starting` scripts an observation with `self.tagged(...)`
  without the `frame_id` that `place()` would fill in (`test_cp4_fixtures.py:717-720`),
  so the processor's output fails `LocalObservation` validation (`frame_id` None) and
  `process_pending` reports `failed=1` (traced in the scratchpad with `sys.settrace`;
  the store swallows the text by design). The production path (a capture one minute
  before the erasure is accepted, ten minutes before is refused) is exercised by the
  earlier assertions in the same test and by the API suite; the "then processed into
  an item" assertion is not currently verified. Fix the fixture, not the store.
- **T2 (tester, medium gap): nothing tests the hand hull.** `grep hull` over every
  test file finds nothing: `hand_hull_mask`, `nearest_sample`, the mask subtraction in
  `_embed_region`, and the `r2` recipe invalidating an `r1` calibration are untested.
  The plan's tester paragraph did not name a file for it; F1 is exactly the kind of
  defect such a test finds (a hull covering 95 % of the crop must yield no stored
  vector).
- **T3 (tester, low): no assertion that `PRAGMA secure_delete` is ON** on a store
  connection; the P-107 byte scan passes here because the PRAGMA is set and because
  this build compiles `SQLITE_SECURE_DELETE`; one `PRAGMA secure_delete` read in
  `SidecarPrivacyTests` makes the laptop run meaningful.
- **T4 (tester, low): plant a recognisable geolocation** (e.g. `51.5007, -0.1246`) in
  the v1 fixture and assert the digits appear in no migrated row or sample; the
  current `1.0`/`2.0` cannot be searched for.
- **T5 (human/laptop): `_windows_is_private` and the Windows swap path** (`os.replace`
  over an open-handle refusal → `in_place` fallback) are unverified on this platform;
  the tester's "checks both paths it can" clause applies, and the laptop run must
  include `sidecar_report()` after an erase-all.

### P2.4 Data-class map deltas (columns the diff added that §1.2 did not list)

| Table.column | Class | Retention / removal |
| --- | --- | --- |
| `reobservations.gated`, `.bbox` (region coordinates of the decision), `.decided_ms` | IDS/numbers | with the row (`episodes_days`; erased with the item) |
| `maintenance_counters(day, name, value)` | counts | forever (a number per day); keep |
| `idle_frames.session_id`, `.consent_version`; `episode_revisions.consent_version`, `.redacted_reason`, `.reduced_ms` | IDS | as the row |
| `local_observations.erased`; `item_names/local_audit/corrections.erased` | flags | forever (they are the erasure record) |
| `retention.acknowledged_version`, `.erased_at_ms` | IDS/config | survive erase-all (by design: the refusal clock) |
| re-observation observation records: `region_diff`, `match{state,set,scores}`, `placement_observation_id`, `registered`, `embedded` | numbers + ids (`scores` scrubbed on `/history`, `memory_app.py:788-794`) | as the row |
| migrated records: `legacy_object_id`, `legacy_event_id`, `legacy_action`, `session_id` (v1), `label` (v1 name) | IDS + NAME | forever until erased; `erase_item` reaches the v1 rows too (`:1690-1692`) |

### P2.5 §9 go/no-go, updated

| Condition (§9) | State after pass 2 |
| --- | --- |
| 1. Map complete, no unlisted content column | **done** (P2.4 lists the additions; none holds new content) |
| 2. Erasure reaches every content cell in one transaction; counts-only report | **done** (`_erase_items` `:1622-1693`; `present_report` `memory_app.py:923-937`; `current_items` deleted and rebuilt `:1666, :1731, :1768`) |
| 3. P-107 markers vanish everywhere incl. `as_of` before/after and the byte scan of file + journal | **done** in my run (`test_cp4_erasure`; the journal is scanned as a sidecar); the forced-OFF/ON `secure_delete` runs are moot because the PRAGMA is explicit (T3 for the assertion) |
| 4. Tombstones refuse resends; pre-erasure packets refused | **done** (`:447-453`, `:2012-2013`, browser drop) |
| 5. Landmark reduction: closed schema, nothing else, 400 from clients, digests stable, `item_image` works, not before processing, late revisions handled | **done except "not before processing"** (F2); E8(i) handled (`:465-469`), E8(ii) resolved as superset-neutral (accepted deviation) |
| 6. Idle frames never listed/served unless promoted; expiry; caps; promoted follow `episodes_days`; evidence DTO marks the source | **done** on the server; the browser does not show the source (F3) |
| 7. B-09: private pre-creation, `sidecar_report()`, private `VACUUM` target measured, journal truncated and removed | **done** on POSIX (tester asserts `0600` on file and sidecars after the swap); Windows unverified (T5) |
| 8. B-08: no triggers/roles; actor on `erase_item`, `erase_profile`, the alias; confirm tokens only; env gate | **done** (alias actor fixed to `operator`, F6, low) |
| 9. B-10: prose/path/coordinate never copied; provisional-only; dry-run writes nothing; idempotent; rollback; `api_calls` untouched; acknowledgement | **done** except the consent stamp (F5) and the acknowledgement (open for CP5 by decision); coordinates assertion T4 |
| 10. Consent rule adopted; `consent_version` not settable; capture stops until acknowledged | **done** (`consent.py`, `:2000-2013`, PUT allowlist, browser gate); the disclosure text needs the three edits of P2.2 item 4 and therefore one version bump |
| 11. No new runtime dependency; no egress; CP4 JSON routes satisfy the no-vector assertion | requirements untouched; egress is the smoke test (not run here); `present_report`/`present_retention`/`present_migration`/`present_consent` are whitelists with numbers, fixed strings and ids only, and the embeddings count is renamed `appearance_signatures` (`memory_app.py:37, :931`) |
| 12. UI copy: no forensic words; residue sentence in both dialogs; idle disclosure on the camera page; promoted photos labelled | **done** except the label (F3); the camera page carries the idle sentence (`memory.html:78`) |
| 13. Open questions answered and reflected | answered (the coordinator's message); the plan text lags (F8) |
| New: per-household files in any hosted deployment (P2.2 item 9) | design rule recorded; no CP4 code |

### P2.6 Final G-PRIV verdict and what remains human

**G-PRIV: go for closing at CP4 on this diff**, from Oversight's side, subject to the
tester's verdict on the smoke test and to three fixes that are each a few lines and
do not change the design: F1 (refuse a hand-dominated crop; with T2's test), F2 (no
reduction before a terminal job), and the disclosure edits of P2.2 item 4 under one
`CONSENT_VERSION` bump. F3-F8 and T1, T3, T4 are improvements the coordinator can
schedule; none keeps personal data where the map says it leaves, and none makes a
claim the system cannot keep.

What remains human and is not a code gate:

1. The rig landmark release (§2.3 item 1, §8 Q12): one page, signed by everyone whose
   hands will be in frame, kept with the research record.
2. BIPA §15(a)/(b) wording confirmed at the primary URL (§8 Q13) before the household
   consent packet is drafted from §2.5; the household packet itself, the posted
   notice and the per-state decision (IL/TX/WA) stay with counsel (`COMMERCIAL.md`
   §4.3-4.4).
3. The Windows run on the laptop: `sidecar_report()` after writes and after an
   erase-all, `PRAGMA secure_delete` and `PRAGMA compile_options` printed, the swap
   path exercised (T5); the Playwright smoke suite including
   `test_99_no_request_left_the_origin` with idle capture running.
4. The P-105 thresholds (`REOBS_SAME_MAX`, `REOBS_GONE_MIN`, the gate, the budget) and
   P-104's hand-dominance share are initial values until the device experiments
   replace them; nothing in this verdict depends on their accuracy, only on their
   being labelled initial, which they are (`reobservation.py:36-38`, `identity.py:13-15`).
5. The notices page (CP5) and the `onnxruntime` re-pin (CP3 §7 Q10) are register
   items, not G-PRIV items.

## Interface notes (as built, after pass 2)

- The live-row sentinel is `LIVE = "record IS NOT NULL AND erased=0"`
  (`episode_store.py:90`): an erased observation is a stub `{"erased": true,
  "observed_at_ms"}` with `erased=1`. Every new reader of `local_observations`,
  `item_names`, `local_audit` or `corrections` must filter `erased=0`; a reader that
  forgets it projects a stub, which the P-107 suite will catch only if the stub holds
  a marker (it holds none), so review new readers by hand.
- `landmark_summary` is `list[LandmarkSummary]` of `{frame_id, t_ms, hands:
  [SummaryHand{hand_bbox, busy, basis}]}`, both `StrictModel` (`extra="forbid"`);
  server-only; excluded from the semantic digest; a client packet carrying it is 400.
- `CONSENT_VERSION` and `DISCLOSURE_TEXT` live in `perception/consent.py`; the profile
  acknowledges the version through `POST /api/consent {"acknowledge": version}`;
  capture (`/api/episodes`, `/api/idle`) is 409 `consent_required` until then; any
  change to the text is a version bump. `PUT /api/retention` takes the three windows
  only.
- Erase-all swap as built: private pre-created target → `VACUUM INTO` → `quick_check`
  + `user_version` → fsync → `os.replace` → truncate-then-unlink the old journal →
  directory fsync; `in_place` VACUUM fallback reported, never raised. `secure_delete=ON`
  on every connection. `sidecar_report()` is a debug method, not a route.
- A capture whose wall **start** (episode) or wall time (idle frame) precedes
  `retention.erased_at_ms - 5 min` is 409 `erased_before`; the browser drops such a
  mirrored packet and clears its mirror after a successful erase-all.
- Migration copies `scene.surface`/`scene.room` only; `actor` is `"unknown"`; no
  description, appearance, evidence prose, geolocation, frame or crop path; legacy media
  files are counted, never touched.
- The erase report crosses the boundary as counts only; the embeddings count is named
  `appearance_signatures`.
- UI phrases in use: "removal from the app's database, not a forensic wipe"; "Traces may
  remain on the device or in backups." Keep both; never "permanently", "securely" or
  "removed from your device".
- Any hosted deployment uses one SQLite file per `profile_id` (P2.2 item 9).

## Appendix A. Measured SQLite residue behaviour (sandbox, 2026-10-09)

Method: a scratch script (not in the repository) created a database with the store's
PRAGMAs (`journal_mode=PERSIST`, `synchronous=FULL`), inserted 20 rows each holding a
3 KB BLOB and a TEXT with a 31-byte marker, then in one transaction `UPDATE ... SET
packet=NULL, note=NULL` on ten rows and `DELETE` on the other ten (the shape of
`erase_item`), committed, ran `VACUUM INTO` a new file, closed, and simulated the swap
(`os.replace(copy, main)`) leaving the old `-journal` in place. Marker occurrences were
counted by reading each file's bytes. Runtime: SQLite 3.45.1 (Python 3.12 on Linux);
`PRAGMA compile_options` includes `SECURE_DELETE`, so `secure_delete` defaults to ON on
this build.

| Setting | Main file after the erasing transaction | `-journal` after it | `VACUUM INTO` copy | Main after swap | Old journal after swap |
| --- | ---: | ---: | ---: | ---: | ---: |
| `secure_delete=OFF` | **61** | 34 | 0 | 0 | **34** |
| `secure_delete=ON` | 0 | **60** | 0 | 0 | **60** |

Second probe (file modes under umask 022): a `VACUUM INTO` target created by SQLite is
`0644`; a pre-created empty `0600` file stays `0600`; a database and journal created by
a bare `sqlite3.connect` are `0644` (which is why the store pre-creates both through
`private_append_fd`, `object_memory.py:169-170`). The copy opens in journal mode
`delete` until the store sets PERSIST.

Reading: `VACUUM INTO` does what the brief wants for the main file; the persistent
journal is where the erased pages live afterwards, in both settings; without
`secure_delete` the main file itself keeps them until the pages are reused; a target
file SQLite creates is not private. These three facts are the basis of §4.3.
