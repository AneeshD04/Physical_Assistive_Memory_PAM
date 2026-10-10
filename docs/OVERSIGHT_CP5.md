# Oversight, CP5: resolver contract, scoring harness, frame accounting, notices, rig checklist

Pass 1 (plan review, 2026-10-10), written while the builders worked; pass 2 (diff review
against the plan, the coordinator's decisions and the requirements below, with
`file:line` evidence) is the section "Diff review, pass 2" at the end, with the ranked
findings in P2.7 and the final verdict in P2.9. Pass 1 is kept as written; where pass 2
supersedes a pass-1 line (checklist steps 2, 17, 19), P2.8 says so. Tree at the start of this pass: `7ab0e5e` (CP4 commit) with only
`docs/BUILD_PLAN.md` modified; no CP5 builder file existed, so every code citation
below is to the CP4 tree the resolver must replace or extend. While this pass was
being written the builders' files appeared in the working tree (`perception/resolver.py`,
`rubric.py`, `scenario_runner.py`, `scenario_frames.py`, `scripts/run_scenarios.py`,
the `frame_counters` table and `ingest_telemetry` in `episode_store.py`, six
`server/test_cp5_*.py` suites, `server/fixtures/cp5/`); they are pass 2's object and are
not reviewed here, with one exception noted in §4.1 item 3. Read-only; no git state
changed.

Authority and inputs: `docs/BUILD_PLAN.md` "CP5 in detail" (L550-668, the plan under
review); `docs/MEMORY_SYSTEM_V4.md` Part 1 (design authority; line numbers below are
in that file): rule 2 L72, rule 3 L73, rule 5 L75, rule 7 L77, rule 8 L78, rule 11 L81,
**rule 12 L82**, rule 13 L83, "The photo is the answer" L89, "Printed labels" L91,
"Abstention is a first-class answer" L93, "Corrections" L95, bystanders L99, frame
accounting L142, browser rig L148-158, indexing L195, **"Answer (resolver)" L197**,
pilot criteria L218-240, scripted cases L375-384, round-2 rule 12 L338 and rubric
L341, the rig record L371, C1 L416; `docs/OVERSIGHT_CP2.md` §0 and §2-§4;
`docs/OVERSIGHT_CP3.md` §0, §2.1-2.5, §4.2-4.3, P2.5; `docs/OVERSIGHT_CP4.md` §1.2, §2.3,
§2.5, §2.6, §8 Q12-Q13, P2.4, P2.6; `docs/LICENSES.md` (every row); `docs/RESEARCH_LOG.md`
C-05, C-10, D-008, B-14, B-15; `docs/RESEARCH_EXPERIMENTS.md` P-101, P-103, P-105,
X-007..X-009. Code read: `perception/episode_store.py` (`_project` L958-1088,
`_age_item` L885-909, `_evidence_expired` L1099-1123, `answer_text` L1522-1586,
calibration L344-399, `CALIBRATION_SOURCES` L56, `ACTORS` L60), `server/memory_app.py`
(`present_item` L874-905, `present_answer` L989-1005, `protect` L739-777, health
L1069-1094, pages and assets L1362-1417, `main` L1425-1431), `phone/assets/memory.js`
(`describe` L138-157, `itemCard` L158-163, `ask` L837-867), the threshold constants
named in §5, `perception/consent.py`, `perception/object_memory.py:166-209`,
`scripts/cp4_selfcheck.py`, `phone/assets/tabler-license.txt`.

Fetched today (primary sources, bytes hashed in the review scratchpad, not committed):

| Source | Result | SHA-256 |
| --- | --- | --- |
| https://raw.githubusercontent.com/google-ai-edge/mediapipe/master/NOTICE | **404: the MediaPipe repository has no NOTICE file at `master`** (so Apache-2.0 §4(d) adds nothing beyond the licence text and the copyright line) | - |
| https://raw.githubusercontent.com/google-ai-edge/mediapipe/master/LICENSE | 200, 12,331 B, the stock Apache-2.0 text with the `Copyright [yyyy] [name of copyright owner]` placeholder (identical to the 2026-10-08 fetch) | `8707eef0533987efc5b155d64761eeb6e20793f50b9bd1a68dad1cf4719d0ed8` |
| https://raw.githubusercontent.com/google-ai-edge/mediapipe/master/mediapipe/tasks/web/vision/index.ts and `.../hand_landmarker/hand_landmarker.ts` | 200; header line **"Copyright 2022 The MediaPipe Authors."** (not "Google LLC"; register §5 corrected today) | `ad6d0651ef5d1a8138f5e4a0211a7c2ac938e99198768c66ea517831d2139610` / `1ed18e2e0bee2d2f963bfe4af7700b965ebeef58569a407bd5175d860cefe939` |
| https://raw.githubusercontent.com/google-ai-edge/mediapipe/master/mediapipe/tasks/web/vision/README.md | 200, 9,259 B; "Privacy Notice, Last modified: June 5, 2026" with the consent sentence quoted in register §2a | `8326ed0beb1983b69cccb190937c2e368388969cb3ade06010fe51e0d5339308` |
| https://raw.githubusercontent.com/facebookresearch/dinov2/7764ea0f912e53c92e82eb78a2a1631e92725fc8/NOTICE | **404: no NOTICE file at the pinned commit** (register §3 already said so) | - |
| same commit, `dinov2/models/vision_transformer.py` | 200; header "Copyright (c) Meta Platforms, Inc. and affiliates." | `7799a260f2d7d0fe197331d08502fb8c542f9b7424723650f6a39b64fa2639ea` (= register §3) |
| https://raw.githubusercontent.com/microsoft/onnxruntime/main/LICENSE | 200, 1,073 B, "MIT License / Copyright (c) Microsoft Corporation" | `2f07c72751aed99790b8a4869cf2311df85a860b22ded05fa22803587a48922c` (= register) |
| https://raw.githubusercontent.com/tabler/tabler-icons/main/LICENSE | 200, 1,073 B, "MIT License / Copyright (c) 2020-2026 Paweł Kuna"; **byte-identical to `phone/assets/tabler-license.txt`** | `b740a1d46122672da62833e97f7e7c8a13fa85cbc7445b584b297cc00dde93db` |
| https://raw.githubusercontent.com/opencv/opencv-python/4.x/LICENSE-3RD-PARTY.txt | 200, 179,306 B (branch head). The **wheel-bundled** copy in `opencv-python-headless` 5.0.0.93 (`cv2/LICENSE-3RD-PARTY.txt`, also under `dist-info/`) is 179,634 B, SHA-256 `2537f5653345db7231ff12f307bcfa4c89807d45ed1c4bb8ebfb6f26f61b160a`; its lines 1-2 "OpenCV library is redistributed within opencv-python package", L243 "FFmpeg is redistributed within all opencv-python packages" followed by the LGPL-2.1 text, L710 "Qt 5 is redistributed within non-headless opencv-python Linux and macOS packages" | `36bae33968d5e67f66906bc595949cb78d65978604e7392f552a79006c93cf2c` |
| `cv2/LICENSE.txt` in the same wheel | 1,070 B, "MIT License / Copyright (c) Olli-Pekka Heinisuo" | `09d719058e782ac7bc71ba21c944e1136cde2bb957c0e888121f0218d6b5f02c` (= register §7) |
| https://raw.githubusercontent.com/google/flatbuffers/master/LICENSE | 200, stock Apache-2.0 text; the `flatbuffers` 25.12.19 **wheel ships no licence file** (checked with `importlib.metadata`), so the notices page must carry the text itself | `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` |
| Wheel licence files present in the sandbox installs (`importlib.metadata`): fastapi, starlette, uvicorn, pydantic, pydantic-core, anyio, h11, click, typing-extensions, annotated-types, idna, sniffio (`LICENSE`, `LICENSE.APACHE2`, `LICENSE.MIT`), packaging (`LICENSE`, `LICENSE.APACHE`, `LICENSE.BSD`), protobuf, numpy (six files incl. highway, libdivide, dragon4, x86-simd-sort, pythoncapi-compat), onnxruntime (`LICENSE`, `ThirdPartyNotices.txt`) | every one of these distributions carries its licence text inside the wheel; only flatbuffers does not | - |

**Not reachable today** (egress 403 on CONNECT; WebFetch permission not granted in
time): the hand-model card PDF on `storage.googleapis.com` (B-05/C-03 still open) and
740 ILCS 14/15 on `ilga.gov` (§15(a)/(b) wording stays **UNVERIFIED**, as in CP4). Nothing
below is guessed from those; the checklist assigns both to a human with a browser.

Verdict in one line: **the CP5 plan is the right shape and nothing in it needs a new
dependency, a new personal-data class or a new licence; what it needs before the rig is
(1) the resolver's text templates rewritten so every hedge names its own axis and every
shape obeys the field invariants in §1.2 (the CP4 `answer_text` has two sentences that
hedge on the wrong axis and one that promises nothing but states no time), (2) a fixed
no-claim sentence and metric labels that never say "accuracy" on synthetic data (§2),
(3) `server/notices.json` built from the list in §3.1 with the sync rule in §3.4 and the
three corrections I made to the register today (§3.5), (4) telemetry treated as
counts-only, expired and erased with the profile (§4), and (5) the 26-step human
checklist in §5, of which the ten steps 1-4, 6, 10 and 16-19 are the gate for "ready for
the rig" (§6); the calibration (23) and the household items (24-25) gate later things.**

## 1. Answer-contract truthfulness requirements

### 1.1 What the contract says (the lines every template is checked against)

- L82 (rule 12): a reference image **only when a reliable sighting exists**; a target
  indication **only when supported**; capture time; identity status; location-evidence
  status (observed placement, sighting, or inference); room or "room unknown". "An
  abstention does not say 'the last time I saw it,' because that asserts an identity
  match, and the nearest candidate is never shown as if it were a match. `unknown` is a
  valid answer even when the nearest embedding has a large margin."
- L93 (§6): confident = "a reliable sighting and no later uncertain event: photo, time,
  room when known"; hedged = "a reliable sighting followed by an unobserved gap or an
  unknown actor: 'I saw it here at 3 pm, but someone may have moved it since,' with the
  photo"; abstain = "no reliable sighting: 'I'm not sure where it is,' with no photo and
  no claimed sighting". "A confident wrong answer is worse than no answer."
- L89: the photo "can still be the wrong bottle, the wrong episode, a pre-placement
  frame or stale, so it is shown only under the answer contract in rule 12 and never
  when no reliable sighting exists."
- L197 (§7): the field list; a *reliable sighting* needs `matched_trusted` or
  `matched_provisional` **with margin at or above the trusted threshold**, `placed` or
  `sighted`, and **the item's most recent observation**; `index_pending` may accompany
  any shape.
- L195: "never answer 'I haven't seen it' while a candidate is pending."
- L72 (rule 2): a candidate handled once today is answerable, "with the answer
  qualified ('something I saw once, this afternoon')".
- L73 (rule 3): "Uncertain invalidates, never invents."
- L75 (rule 5): containment is inferred; "both facts keep their own timestamps ('I saw
  the keys go into the purse at 2 pm; I saw the purse on the chair at 3 pm')".
- L81 (rule 11) and L338: a lookalike group is "one answer surface, not one database
  row"; B-14: a group never upgrades a member's certainty or identity.
- L83 (rule 13): a re-observation is "sighted", never "placed".
- L78 (rule 8) and B-15: actor is `wearer | other_person | unknown`; a role or a shared
  PIN is never a named person.
- L230: "Prior location marked stale; never a confident stale answer."
- L91: dose text "is never an input to any medication-taking or dosing feature".

### 1.2 Field invariants per shape (the tester's first fixture table)

`Answer` keys are exactly the plan's (`shape, text, members, reference_image,
target_indicated, capture_time_ms, identity_status, location_status, room,
index_pending, question, options, unresolved_observation_id, basis`). Required values:

| Shape | `members` | `reference_image` / `target_indicated` | `capture_time_ms` | `identity_status` | `location_status` | `room` | `question`/`options`/`unresolved_observation_id` | `basis` must contain |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| confident | exactly 1 | the member's `{frame_id, bbox}` / true; **null / false when `evidence_expired`** | the member's `observed_at_ms` (never null) | `matched_trusted` | `placed` or `sighted` | "room unknown" (no source exists) | absent | `trusted_match` and (`placed` or `sighted`); never `aged`, `expired`, `negative_reobservation`, `picked_up`, `inferred`, `lookalikes`, `provisional_match`, `no_evidence` |
| hedged | exactly 1 | the member's image when a sighting exists and bytes exist; null / false when `evidence_expired` **or** when the hedge is on identity with no reliable sighting (provisional below the trusted margin) | the member's `observed_at_ms`, or null when `reference_image` is null | `matched_trusted` or `matched_provisional` | `placed`, `sighted`, `inferred` or `stale` | "room unknown" | absent | at least one hedge reason: `provisional_match`, `inferred`, `aged`, `negative_reobservation`, `picked_up`, `lookalikes`, `expired`; the reason named must be the one the text states |
| abstain | **always `[]`** | null / false | null | `unknown` | `unknown` | "room unknown" | absent | `no_evidence`, or `aged` (over 7 d), or `index_pending`, or `consent_pending`; never `trusted_match`/`placed`/`sighted` |
| group | 2..`max_members` mutual lookalikes, **each with `provenance {observation_id, identity_status}` and its own unaltered fields** | null / false at the top level (the group has no single image; each member card carries its own) | null | `group` | `unknown` at the top level (members keep their own) | "room unknown" | `question`, `options` (item_id + name only), `unresolved_observation_id` (string or null) | `lookalikes`; per-member reasons are in the member DTOs, not here |
| clarify | 2..`max_members` distinct items matched by the words | null / false | null | `unknown` | `unknown` | "room unknown" | `question`, `options` (item_id + name only) | `name_ambiguous` |

Two cross-shape invariants: `target_indicated` is true only when `reference_image` is
non-null **and** the member's `identity_status` is trusted (an outlined region on a
provisional match reads "this is it"; `memory.js:97-99` already distinguishes the alt
text, the resolver must set the flag the same way); and `index_pending` true never turns
an abstain into "I haven't seen it" (L195): the abstain text then says processing is
pending.

### 1.3 Permitted and forbidden sentences, by shape

The tester can turn the forbidden column into regular expressions over `text`
(case-insensitive) and the permitted column into the templates the resolver ships.
`{name}` is the member's current name, `{place}` its `location_text`, `{when}` its
observed time rendered as a date or "today at 15:02" (the store has no time zone; UTC
date today, `_date_text` L1588-1595), `{since}` the `stale_since_ms` rendering.

| Shape | Permitted (templates; all of them state the time when a time exists) | Forbidden (a fixture per line) |
| --- | --- | --- |
| confident | "I saw {name} at {place} ({when})." / "{name} is at {place}; I saw it there {when}." / with a re-observation: "... and it was still there when I looked {since_last_present}." / "Room unknown" is implicit; the text never names a room | any room name (no source, L82); "always", "still there" without a positive re-observation time; "hasn't moved" / "nobody has moved it" (unobserved absence is not evidence, L73); "safe", "correct", "your dose", "take" (L91); a person's name or "your caregiver moved it" (B-15; "someone" is the only allowed actor word, and only in hedged); "probably", "I think", "may" (a confident answer does not hedge; if a hedge word is needed the shape is wrong); "the last time I saw it" phrased as a hedge; any sentence about a second candidate |
| hedged, identity provisional (`provisional_match`) | "I have a sighting that may be {name}, at {place}, {when}; I am not certain it is the same item." / rule-2 wording for a once-seen candidate: "Something I saw once, {when}, that may be {name}, was at {place}." | "I saw {name}" (asserts the match); "{name} is at"; "its current location is uncertain" when the location evidence is in fact `placed` and fresh (hedge on the wrong axis; this is `answer_text` L1577-1578 today for a provisional+placed item: see §1.6 F1); "recognised", "verified", "matched" |
| hedged, inferred (`inferred`) | "I think {name} is with {container}: I saw {name} go into {container} {when_inner}, and I saw {container} at {place} {when_outer}." / when the container's place is unknown: "I think {name} is with {container} (seen going in {when_inner}), but I do not know where {container} is now." | "I saw {name} at {place}" (the keys were never seen at the chair, L75); a single timestamp for the two facts; "is in {container}" without "I think"; a container's location older than 7 d stated as current |
| hedged, negative re-observation (`negative_reobservation`) | "I recorded {name} at {place} {when}, but it was no longer there when I looked {since}. I do not know where it is now." (the CP4 sentence at L1570-1571 is acceptable with the last clause added) | "{name} is at {place}" / "last seen at {place}" without the "no longer there" clause; "someone took it" (the actor is unknown); any new place (rule 3) |
| hedged, aged 24 h-7 d (`aged`) | "I saw {name} at {place} {when}; that was {N} days ago, so it may have moved since." (the age in days or hours is required, not only "more than a day ago") | "{name} is at {place}" in the present tense; omitting the age; "still" |
| hedged, picked up / stale by pickup (`picked_up`) | "I saw {name} picked up from {place} {when}; I did not see where it was put down." | naming {place} as the current location; "it is probably nearby"; "it was put back" |
| hedged, lookalikes on a single name match (`lookalikes`) | "I have evidence for {name}, but it looks like {k} other stored item(s) and I cannot tell them apart; here is what I have for each." (then the answer should normally be `group`; a hedged single answer here is allowed only when the other members did not match the words) | a location for {name} stated without the lookalike sentence; a "recognised" badge |
| hedged, evidence expired (`expired`) | the same sentence as the underlying reason plus "The photo from that time has expired under the retention window." | "here is the photo", "in this picture", "the outlined item"; the nearest *other* image of the item (a different observation's frame) shown in its place |
| abstain, nothing matches (`no_evidence`) | "I'm not sure where {query_noun} is. I have no stored evidence that matches." | "the last time I saw it", "I saw", "I last saw", "recorded ... at", any `location_text`, any observation date, any item name that was not in the question, "it might be", "probably", "the closest match is", "here is a photo"; "I will tell you when I next see it" (a notification path does not exist in CP5; a promise the software cannot keep is a capability claim: §6 Q4) |
| abstain, aged over 7 d (`aged`) | "I'm not sure where {name} is: my last evidence is more than a week old, and I do not treat that as a current location." | the old place; the old date beyond "more than a week old"; the photo |
| abstain, index pending (`index_pending`) | "I'm still processing a recent sighting and cannot answer yet; ask again in a few minutes." | "I haven't seen it" / "I have never seen it" / "no stored evidence" while `index_pending` is true (L195) |
| abstain, consent pending (`consent_pending`) | "The camera is paused until the disclosure is acknowledged, so I have no new evidence." | any location |
| group | "I have {n} items that look alike; which one is yours?" (L1548 today) + per-member cards each with **its own** identity badge, location sentence in its own hedged form, and provenance | "one of these is yours" (asserts the true item is in the set); "your {name} is on the counter or in the drawer" (a merged location upgrades both); a trusted badge or an outlined target on a member whose own status is provisional/ambiguous; a group text that names a location at all |
| clarify | "Which stored item do you mean: {name_1}, {name_2}, ...?" + options as names | any location sentence for any option in `text` (an option card that shows a place and a photo is an answer for an item the user may not have meant: `memory.js:853-855` renders full `itemCard`s for clarify today, §1.6 F4); "the nearest", "probably {name_1}" |

Words forbidden in **every** shape (fixture: a single regex over all templates):
"guarantee", "verified identity", "recognised" next to a provisional/ambiguous member,
"biometric", "medication safety", "accuracy", "95 %"; a named person; a room name; the
present tense "is at/in/on" without "I think"/"may" outside the confident shape.

### 1.4 Per-basis-token requirements

`basis` is "ordered" (plan L572): the order must be the precedence order of §1.5, most
restrictive first, so the "Why this answer" panel reads top-down as the reason the shape
is what it is. Every token must be true of the member it describes; a token that merely
describes history (e.g. `placed` on an item that is now `stale`) is forbidden unless the
staleness token precedes it.

| Token | May appear only when | Must force | Must never appear with |
| --- | --- | --- | --- |
| `trusted_match` | the member's `identity_status` is `trusted` (store vocabulary) | nothing by itself | `provisional_match`, `lookalikes`, `no_evidence`, shape abstain |
| `provisional_match` | `identity_status` is `provisional` (or `ambiguous` without a group) | shape ≤ hedged; `target_indicated` false; the text says "may be" | `trusted_match`, shape confident |
| `placed` | the member's current `location_status` is `placed` (a hand event or a positive re-observation refreshed it) | nothing | `stale`-class tokens unless preceded by them (see above) |
| `sighted` | `location_status` is `sighted` (rule 13: no placement witnessed) | the text says "saw", never "put down"/"placed" | `placed` |
| `inferred` | `location_status` is `inferred` with an `inference` dict | shape ≤ hedged; two timestamps in the text; "I think" | shape confident |
| `aged` | `aged` is true (24 h < age ≤ 7 d: hedged; > 7 d: abstain) | hedged: the age stated; abstain: no place, no date | shape confident |
| `expired` | `evidence_expired` is true | `reference_image` null, `target_indicated` false, `capture_time_ms` null, the expiry sentence | an image of another observation |
| `negative_reobservation` | `stale_reason == "negative_reobservation"` | shape ≤ hedged; old place as history; "I do not know where it is now" | shape confident; a new place |
| `picked_up` | `stale_reason` is the pickup sentence (L1017) / `location_status` `stale` from a pickup | shape ≤ hedged; no current place | shape confident |
| `lookalikes` | the member's `lookalikes` is non-empty | group when all matched members are mutual lookalikes (L1542); otherwise the lookalike sentence | a trusted badge for that member |
| `name_ambiguous` | ≥ 2 distinct (non-lookalike) items matched the words | shape clarify | any location in the text |
| `no_evidence` | `members == []` and nothing matched | shape abstain | every other evidence token |
| `index_pending` | the store's `_pending` is true | the abstain text variant of L195 when abstaining; a pending note otherwise | the words "haven't seen" |
| `consent_pending` | the profile has not acknowledged `CONSENT_VERSION` (capture is 409) | an abstain or a note that no new evidence can arrive | - |

### 1.5 Per-member precedence (B-14): the rule and the fixture table

The rule, in one sentence: **certainty is monotone non-increasing across the decision
table: whichever condition forces the lowest shape wins, every member keeps its own
fields, and no later step may raise a member's identity or location status above what
its own evidence supports.** The plan's row order (L575-583) lists "identity provisional
→ hedged" before "aged over 7 d → abstain"; the monotone rule resolves that case to
abstain (§6 Q1 asks the architect to confirm). The resolver therefore evaluates abstain
conditions first, then group/clarify, then the hedge reasons, and reaches confident only
when no reason remains.

Fixture table (one resolver test per row; `evidence_expired` is a modifier that may be
added to any non-abstain row and must remove the image without changing the shape):

| # | Match set (after word match) | Member evidence (identity / location / stale_reason / aged / lookalikes / inference) | Expected shape | Expected per-member status in the DTO | Image on the member card | Text must contain / must not contain |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | none | - | abstain | - | none | "not sure" / no place, no date, no name |
| 2 | 1 | trusted / placed / None / false / [] / None | confident | trusted, placed | yes, outlined | place + time / no hedge word |
| 3 | 1 | trusted / sighted / sighting note / false / [] / None | confident (sighting) | trusted, sighted | yes, outlined | "saw" + time / "put down", "placed" |
| 4 | 1 | provisional / placed / None / false / [] / None | hedged (provisional) | provisional, placed | yes, **not** outlined | "may be" / "its current location is uncertain" |
| 5 | 1 | provisional / sighted / unverified note / false / [] / None | hedged (provisional) | provisional, sighted | yes, not outlined | "may be" + "saw" / "placed" |
| 6 | 1 | trusted / inferred / None / false / [] / {container_name, since_ms} with container placed | hedged (inferred) | trusted, inferred | the inner item's last image, not outlined as current | "I think", two times / "saw {name} at {container's place}" |
| 7 | 1 | as 6 but the container itself `stale` | hedged (inferred) | trusted, inferred | as 6 | "do not know where {container} is now" |
| 8 | 1 | trusted / stale / negative_reobservation / false / [] / None | hedged (negative re-observation) | trusted, stale | the last placed frame, labelled as past | "no longer there" + both times / "is at" |
| 9 | 1 | trusted / placed / age / true (24 h-7 d) / [] / None | hedged (aged) | trusted, placed, aged true | yes, labelled "older evidence" | the age / "still" |
| 10 | 1 | trusted / stale / age / true (> 7 d) / [] / None | **abstain** | not in `members` | none | "more than a week" / the place |
| 11 | 1 | provisional / stale / age / true (> 7 d) / [] / None | abstain (monotone rule; §6 Q1) | not in `members` | none | as 10 |
| 12 | 1 | trusted / stale / pickup / false / [] / None | hedged (picked up) | trusted, stale | the pickup frame | "picked up" + time / the place as current |
| 13 | 1 | ambiguous / placed / None / false / [A, B] but A, B did not match the words / None | hedged (lookalikes) | ambiguous, placed | yes, not outlined | "cannot tell them apart" |
| 14 | 2 mutual lookalikes | A: trusted / placed; B: provisional / sighted | **group** | A trusted-placed, B provisional-sighted, each with `provenance` | each its own; only A outlined | the group question / any location in `text`; B must not read "trusted" |
| 15 | 2 mutual lookalikes | A: trusted / placed / fresh; B: trusted / stale / negative_reobservation | group | A as is; B stale with its own history sentence on its card | A outlined; B's past frame labelled | "which one is yours" / a merged place |
| 16 | 2 mutual lookalikes, one `evidence_expired` | A: trusted / placed / expired; B: trusted / placed | group | unchanged statuses | A: "evidence image expired", B: its image | - |
| 17 | 2 distinct items, not lookalikes | both trusted / placed | **clarify** | names only in `options` | none in `text`; option cards without a location sentence (F4) | "which ... do you mean" / either place |
| 18 | 3 (A, B lookalikes; C distinct) | mixed | clarify (distinct items present), with A and B presented as one option group | names | none | - |
| 19 | 1, but `index_pending` true | trusted / placed / fresh | confident with `index_pending` true | as 2 | yes | a pending note / "haven't seen" |
| 20 | none, `index_pending` true | - | abstain (`index_pending`) | - | none | "still processing" / "haven't seen", "no stored evidence" |
| 21 | 1, `consent_pending` | trusted / placed / fresh | the ordinary shape plus `consent_pending` in `basis` and a note | as 2 | yes | the pause note |
| 22 | 1, `policy.max_members` = 1 with 3 mutual lookalikes | - | group truncated to 1 is **not allowed**: `max_members` bounds the list but a group of 1 is a hedged single answer with the lookalike sentence, never a confident one | - | - | "look alike" |
| 23 | 1, `as_of` before a correction that later made it trusted | provisional at as_of | hedged (provisional) | provisional | not outlined | "may be" |

Rows 4 and 13 fail against the CP4 code (§1.6 F1, F2); rows 10-11 and 20 fix the
sentences the current code emits at L1574 and L1532 respectively; row 17 needs the
browser change F4.

### 1.6 Findings against the CP4 `answer_text` that the resolver must change

| # | Where | What is wrong under rule 12 | Required |
| --- | --- | --- | --- |
| F1 | `episode_store.py:1577-1578` "Earlier evidence recorded {name} at {place}; its current location is uncertain." is reached for a **provisional** identity with a fresh `placed` location (the `trusted` test at L1558 fails, nothing else matches) | hedges on the wrong axis: the location is fresh, the identity is the doubt | the provisional template of §1.3 ("may be {name}"), `basis` `provisional_match`, `target_indicated` false |
| F2 | `:1579-1583` lookalike sentence is emitted only when `location_text` is empty | an ambiguous item with a place gets the F1 sentence instead of the lookalike sentence | row 13 of §1.5 |
| F3 | `:1559` confident text has no time; `:1565-1567` inferred text has one time for two facts | L93 "photo, time, room when known"; L75 two timestamps | times in every confident/hedged template (§1.3) |
| F4 | `memory.js:853-855` renders full `itemCard`s (photo + location + status) for **clarify** | a location and a photo for every option is an answer for items the user may not have meant; L82 "nearest candidate is never shown as if it were a match" | clarify renders names (and at most an unlabelled thumbnail); location sentences only after the user picks |
| F5 | `:1574` abstain text for > 7 d names the item ("no recent evidence for {name}") and the DTO carries `members: []` but the plan's `Answer` adds `reference_image`/`capture_time_ms` at the top level | fine as abstain; the new fields must be null and `identity_status`/`location_status` `unknown` | §1.2 abstain row |
| F6 | `:1532` abstain text "I have no matching stored evidence." is also used when `index_pending` is true | L195 | the pending variant (§1.3) |
| F7 | `present_item` (`memory_app.py:874-905`) passes `identity_status` in the **store** vocabulary (`trusted/provisional/ambiguous`), the plan's `Answer.identity_status` uses the **spec** vocabulary (`matched_trusted/matched_provisional/group/unknown`) | two vocabularies on one DTO will be confused by the browser and the rubric | the resolver maps store → spec at the top level and leaves member DTOs as they are; `rubric.score` reads only the top-level field; the tester pins the mapping (`trusted → matched_trusted`, `provisional → matched_provisional`, `ambiguous` in a group → `group`, else `unknown`) |
| F8 | "Why this answer" (Builder C) | none yet | the panel lists `basis` tokens in the order given, each mapped to one plain sentence (table below); it never adds a reason the server did not send, never shows a score, margin or vector, and for abstain never shows a place |

Plain-word mapping for the panel (fixed strings; the tester asserts them):
`trusted_match` "Pam recognised this item from earlier photos" · `provisional_match`
"Pam is not sure this is the same item" · `placed` "Pam saw it being put down there" ·
`sighted` "Pam saw it resting there; it did not see it being put down" · `inferred`
"Pam thinks it is inside something else it saw" · `aged` "The evidence is more than a
day old" / "...more than a week old" · `expired` "The photo from that time has expired"
· `negative_reobservation` "Pam later saw that place without the item" · `picked_up`
"Pam saw it picked up and not put down" · `lookalikes` "Other stored items look the
same" · `name_ambiguous` "More than one stored item matches those words" ·
`no_evidence` "Nothing stored matches" · `index_pending` "A recent sighting is still
being processed" · `consent_pending` "The camera is paused until the disclosure is
acknowledged".

## 2. Rubric claims language (C-05, C-10, D-008)

### 2.1 What the summary may and may not say

May say (and must, each time it prints): that the numbers are **software-correctness
outcomes on scripted synthetic scenarios** (generated frames, the deterministic
embedder, a fixture processor); counts with denominators for every rate; the five
outcomes by name; coverage **separately** from the correct share among answered
(L220: "so a system cannot look good by abstaining"); the medication subset
**separately** and from `truth.medication` only; the historical-fidelity count
separately from the current-usefulness outcome (L220, L341); the number of abstentions
where the truth had a visible answer (separates capture coverage from logic, L228);
the scenario names and which expected outcomes matched.

May not say: "accuracy" as the label of any number (C-10: literature metrics and
synthetic counts "are not directly comparable PAM outcomes"; the only place the word
appears is inside the no-claim sentence's negation); "reliability", "success rate",
"validated", "calibrated" (C-05: "No calibrated model or guarantee exists at this
checkpoint"), "guarantee", "safe", "medication safety", "95 %" or any α-coverage figure
next to an outcome rate (C-05/D-008: the conformal bound is conditional on the true item
being in the bank and on exchangeability, and the scenarios' embedder is synthetic);
any comparison of a synthetic rate with the Part 1 pilot targets (0.70, ≤ 0.05, zero
medication) as a pass or fail: the pilot targets are for held-out real households
(L224-238), the scenarios' pass criterion is "every expected outcome matched". The
summary must not print the pilot targets at all.

### 2.2 The no-claim sentence

The plan says "the summary prints that sentence" without fixing it. Fix it as a constant
in `perception/rubric.py` and assert it byte-for-byte in `test_cp5_scenarios.py`:

```
NO_CLAIM_SENTENCE = (
    "These outcomes measure software correctness on scripted synthetic scenarios "
    "(generated frames, a deterministic embedder, a fixture processor). They are not "
    "an accuracy, coverage, reliability or safety measurement of PAM on real footage, "
    "real devices or real households, and no such measurement exists at this checkpoint."
)
```

`scripts/run_scenarios.py` prints it as the first line and the last line of the
summary, and `summarize()` returns it under the key `claim` so a JSON consumer carries
it too. Any report that quotes a number from the summary without the sentence is a C-10
violation.

### 2.3 Additions I require in `summarize()` and the printout

1. Metric keys and labels: `correct_among_answered` (not `accuracy`), `coverage`
   (answered / asked, where answered = confident + hedged and asked = every `query`
   step; clarify and group are asked, not answered), `confident_wrong_rate` (over all
   queries), `hedged_wrong_rate` (reported, L226), the same four under `medication`,
   `fidelity_ok` (count of answers whose member is the true item whatever the place),
   `useful` (count whose place is current), `abstain_with_truth_available` (abstain
   where `truth.item_id` is set and `location_status_now` is `placed`/`sighted`),
   `abstain_index_pending`, and every count's denominator.
2. `score()` reads **structured fields only** (`shape`, the member's `item_id`,
   `location_text`, `location_status`, `basis`), never the text: hedged-correct is
   "the true item and (the place equals `location_text_now`, or `moved_since` is true
   and `basis` carries one of `negative_reobservation | aged | picked_up | inferred |
   expired` so the place is marked historical)"; hedged with the true item but a stale
   place and none of those tokens is hedged-wrong. Text truthfulness is §1's job.
3. Medication is `truth.medication` alone; the item's name or label never sets it
   (names are user text; "pills" in a name is not a scoring category).
4. Corrections are chronological: a record is written when the `query` step runs and
   is never re-scored after a later `correction` step (L220, L340).
5. A `gap` step records coverage loss in the run record (the scenario's `gaps` count
   is printed), and a query after a gap whose truth says the move happened inside the
   gap is scored like any other; the summary's `abstain_with_truth_available` then shows
   whether the logic hedged or abstained, which is the honest outcome for an unobserved
   move (L230, L380).
6. The seven mandatory cases carry `basis` strings naming the Part 1 line they test
   (L379-384) and the run record names the fixture processor and embedder versions.

## 3. Notices page requirements

### 3.1 Components that must appear in `server/notices.json`

Entry shape (plan): `{component, version, licence, source_url, notice_text}`; add
`condition` (closed set: `always | provisioned:hand | provisioned:identity |
calibration:cute | served:tabler`) so the page can render truthfully whether the
optional component is present on this server (§3.3). Every `notice_text` carries the
full licence text once (Apache-2.0 and LGPL-2.1 texts are long; one copy each,
referenced by the entries that share them is acceptable if the JSON uses a
`licence_texts` map keyed by SPDX id and the page inlines it).

| # | Component (register row) | Version | Licence | `source_url` | `notice_text` must contain | `condition` |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `@mediapipe/tasks-vision` (`vision_bundle.mjs`, `vision_wasm_internal.js`, `vision_wasm_internal.wasm`, `vision_wasm_nosimd_internal.js`, `vision_wasm_nosimd_internal.wasm`) (§2a) | 1.0.1 | Apache-2.0 | https://registry.npmjs.org/@mediapipe/tasks-vision/1.0.1 and https://raw.githubusercontent.com/google-ai-edge/mediapipe/master/LICENSE | the Apache-2.0 text; the line **"Copyright 2022 The MediaPipe Authors."** (as in the source headers; the repository has no NOTICE file, verified 404 today, so nothing else is owed under §4(d)); the privacy disclosure: "The MediaPipe runtime contains a metrics logger that attempts to send usage statistics to Google (odml.pa.googleapis.com). PAM's Content-Security-Policy (`connect-src 'self'`) blocks that request, so no metrics leave this origin. Google's notice: 'You are responsible for obtaining informed consent from your app users about Google's processing of MediaPipe metrics data as required by applicable law.'" | `provisioned:hand` (the files are optional and fetched by the operator) |
| 2 | `hand_landmarker.task` (§2b) | float16/1 | **none until the model card is read** | the canonical URL in §2b | **no entry** while the register row is UNVERIFIED (the sync test asserts it); when the row flips, the model card's licence line verbatim | `provisioned:hand` |
| 3 | `dinov2_vits14.onnx` (§3b), our export of DINOv2 ViT-S/14 | `dinov2_vits14@7764ea0f-opset17-224` | Apache-2.0 | https://raw.githubusercontent.com/facebookresearch/dinov2/7764ea0f912e53c92e82eb78a2a1631e92725fc8/LICENSE | the Apache-2.0 text; "Copyright (c) Meta Platforms, Inc. and affiliates."; the §4(b) modification notice from register §5 ("dinov2_vits14.onnx is an ONNX export, made by PAM with scripts/export_dinov2_onnx.py, of the DINOv2 ViT-S/14 weights (facebookresearch/dinov2 at commit 7764ea0f, Apache-2.0); the weights were converted, not retrained."); no NOTICE exists upstream (verified today) | `provisioned:identity` |
| 4 | `onnxruntime` (§1) | 1.30.0 | MIT | https://raw.githubusercontent.com/microsoft/onnxruntime/main/LICENSE | "MIT License / Copyright (c) Microsoft Corporation" + the MIT text; and the wheel's `ThirdPartyNotices.txt` (338,088 B for 1.30.0, SHA-256 `143764b9…`) reproduced or served (§3.3 item 4) | `provisioned:identity` (imported only when the identity model is enabled; listing it always is acceptable) |
| 5 | `flatbuffers` (§1) | 25.12.19 | Apache-2.0 | https://raw.githubusercontent.com/google/flatbuffers/master/LICENSE | the Apache-2.0 text and the copyright line from the project's source headers (the **wheel ships no licence file**, verified today) | as 4 |
| 6 | `packaging` (§1) | 26.3 | Apache-2.0 OR BSD-2-Clause | PyPI | both texts as shipped in the wheel (`LICENSE.APACHE`, `LICENSE.BSD`) | as 4 |
| 7 | `protobuf` (§1) | 7.36.2 | BSD-3-Clause | PyPI | the wheel's `LICENSE` ("Copyright 2008 Google Inc.") | as 4 |
| 8 | `fastapi` (§1) | 0.142.4 | MIT | https://raw.githubusercontent.com/fastapi/fastapi/master/LICENSE | MIT text, "Copyright (c) 2018 Sebastián Ramírez" | `always` |
| 9 | `starlette` (§1) | 1.6.0 | BSD-3-Clause | https://raw.githubusercontent.com/Kludex/starlette/main/LICENSE.md | BSD text, "Copyright © 2018, Encode OSS Ltd." | `always` |
| 10 | `uvicorn` (§1) and whichever of its `[standard]` extras are installed (httptools MIT, uvloop MIT/Apache-2.0, watchfiles MIT, websockets BSD-3-Clause, python-dotenv BSD-3-Clause, pyyaml MIT) | 0.53.0 | BSD-3-Clause | https://raw.githubusercontent.com/Kludex/uvicorn/master/LICENSE.md | BSD text, "Copyright © 2017-present, Encode OSS Ltd."; one sub-entry per installed extra with its wheel text | `always` |
| 11 | `pydantic`, `pydantic-core` (§1) | 2.13.5, 2.46.5 | MIT | https://raw.githubusercontent.com/pydantic/pydantic/main/LICENSE | MIT text, "Copyright (c) 2017 to present Pydantic Services Inc. and individual contributors" | `always` |
| 12 | `numpy` (§1) | 2.5.3 | BSD-3-Clause (+ bundled 0BSD, MIT, Zlib, CC0-1.0, Apache-2.0 components) | https://raw.githubusercontent.com/numpy/numpy/main/LICENSE.txt | "Copyright (c) 2005-2025, NumPy Developers." + BSD text; the wheel's `dist-info/licenses/` directory (OpenBLAS, highway, libdivide, dragon4, x86-simd-sort, pythoncapi-compat) reproduced or served when the server is distributed | `always` |
| 13 | `opencv-python-headless` (§1; the register's recommended wheel, `cv2`) | 5.0.0.93 | MIT (packaging) + Apache-2.0 (OpenCV) + LGPL-2.1 (bundled FFmpeg) + the other `LICENSE-3RD-PARTY.txt` components | https://raw.githubusercontent.com/opencv/opencv-python/4.x/README.md ; https://raw.githubusercontent.com/opencv/opencv/4.x/LICENSE | `cv2/LICENSE.txt` ("Copyright (c) Olli-Pekka Heinisuo", MIT); the Apache-2.0 text exactly as `opencv/LICENSE` at `4.x` reads (the stock text with the `[name of copyright owner]` placeholder; neither it nor the first section of `LICENSE-3RD-PARTY.txt` names the OpenCV copyright holders, so the entry says "OpenCV, the OpenCV contributors, Apache-2.0" and does not invent a holder list); and this **FFmpeg/LGPL note** verbatim: "This server uses the opencv-python-headless wheel, which bundles FFmpeg shared libraries licensed under the GNU LGPL v2.1 (the wheel's LICENSE-3RD-PARTY.txt, line 243: 'FFmpeg is redistributed within all opencv-python packages'). The LGPL-2.1 text is reproduced below. FFmpeg is dynamically linked and may be replaced by a compatible build; its source is available from https://ffmpeg.org/ and the build configuration from https://github.com/opencv/opencv-python. The headless wheel ships no Qt." followed by the LGPL-2.1 text and the rest of `LICENSE-3RD-PARTY.txt` (179,634 B, SHA-256 `2537f565…`) reproduced or served | `always` |
| 14 | `anyio`, `h11`, `click`, `typing-extensions`, `annotated-types`, `idna`, `sniffio` (§1, transitive) | 4.15.1, 0.16.0, 8.5.0, 4.16.0, 0.8.0, 3.20 (3.19 in the sandbox), 1.3.1 | MIT, MIT, BSD-3-Clause, PSF-2.0, MIT, BSD-3-Clause, MIT OR Apache-2.0 | PyPI | each wheel's licence file(s) (sniffio ships `LICENSE.MIT` and `LICENSE.APACHE2`) | `always` |
| 15 | Tabler Icons (`phone/assets/tabler-license.txt`, identical to upstream `LICENSE`) | the icon set version the page embeds (Builder C records it; none is served today: `memory.html` has no `<svg>`, `agent.html` redirects, `PUBLIC_ASSETS` lists no icon file) | MIT | https://raw.githubusercontent.com/tabler/tabler-icons/main/LICENSE | "MIT License / Copyright (c) 2020-2026 Paweł Kuna" + the MIT text | `served:tabler` (required the moment any served file carries a Tabler path; the test greps `phone/memory.html` and every `PUBLIC_ASSETS` file for `icon-tabler` or a path string taken from the embedded symbols) |
| 16 | CUTE calibration attribution (§4) | the `calibration_id` and the DOI | CC-BY-4.0 | https://purl.stanford.edu/gj714cj0414 | the attribution paragraph of register §4 verbatim (authors, title, repository, DOI, licence URL, "no CUTE image is included in PAM") | `calibration:cute` (rendered only when the store has an **approved** calibration with `source == "cute"`; a `synthetic`, `own-footage` or `holoassist` record renders nothing, CDLA-Permissive-2.0 §3.1) |
| 17 | PAM itself (repository `LICENSE`) | the git describe/commit | MIT | the repository | "Copyright (c) 2026 Praneeth Samineni" + the MIT text, headed "This application" (not a third-party notice; the contracting-entity question of CP2 §5 Q10 stays open) | `always` (recommended, not required) |

**Not in notices.json** (the sync test asserts their absence as licence-bearing entries):
every REJECTED or UNVERIFIED row (§2b hand model until read; §3 SigLIP 2 HF card; §6);
every dev-only row (§1b: torch, onnx, playwright, Node); every "legacy dep" row (`httpx`,
`anthropic`, `elasticsearch`, `icalendar`, `python-dateutil`, `google-auth-oauthlib`,
`opencv-python` non-headless): they are declared in `server/requirements.txt` /
`perception/requirements.txt` but not imported by `memory_app` (register §1 header). If
the coordinator keeps them in `server/requirements.txt` for the rig install, they are
installed on the laptop but not distributed to anyone, so no notice is owed; the cleaner
answer is the purge (§6 Q6). The CP3+ planned rows (SigLIP 2, SAM 2.1, RepViT-SAM,
PaddleOCR, onnxruntime-web) are not shipped and get no entry until pinned.

### 3.2 Register facts the entries must match

- MediaPipe: Apache-2.0, copyright "The MediaPipe Authors" (today's header read),
  **no NOTICE**; the telemetry disclosure is an obligation from the package README, not
  a licence term, and belongs on the notices page *and* in the privacy disclosure
  (register §2a; CP2 §3.3). It must say the POST is attempted and blocked, not that the
  code does not try.
- DINOv2: Apache-2.0 for code and weights at the pinned commit, no NOTICE, the §4(b)
  modification notice is mandatory because the ONNX is a Derivative Work (register §3b).
- ONNX Runtime: MIT; the `ThirdPartyNotices.txt` is the union over build
  configurations (70 entries incl. the Intel Simplified Software License for MKL);
  reproduce it whole rather than curate it (register §1).
- OpenCV: Apache-2.0 + FFmpeg LGPL-2.1 in every wheel; the headless wheel avoids the
  LGPL-3.0 Qt; "the user's ability to replace the library" is the LGPL §6 condition
  the dynamic link satisfies, which is why the note names the dynamic link and the source
  (register §1 row).
- Tabler: MIT, the local file is byte-identical to upstream (today).
- CUTE: a quantile is not Adapted Material, attribution is given anyway (CP3 §2.2); the
  attribution appears only when such a calibration exists (plan L632-633) because an
  attribution for data never used would itself be a false provenance statement.

### 3.3 `GET /notices` rendering requirements

1. Public (no session cookie), not under `/api/` (so `protect` leaves it alone and the
   `known` set at `memory_app.py:746-748` is not touched), served from
   `server/notices.json` read at request time with a size cap (the register reads are
   capped at 1 MiB, L84; the notices file with two long texts reproduced will be a few
   hundred KiB: cap at 2 MiB), plain HTML or `text/plain`, no script, no inline style
   needed, CSP unchanged, `X-Content-Type-Options: nosniff` as every response.
2. **No personal data on the page**: no item names, counts, retention windows, consent
   state, device ids, profile ids or calibration numbers. The only store read is the
   boolean "an approved `cute` calibration exists" (entry 16) and the boolean
   "provisioned on this server" per optional component from the two inventories
   (`models_synced`). The page prints "Optional component; present on this server: yes/no"
   for `provisioned:*` entries so the list is truthful on a laptop where the model was
   never fetched.
3. Every entry whose `condition` holds is rendered in full (component, version, licence
   id, source URL, the notice text); an entry whose condition does not hold is rendered
   as a one-line "not present on this server" or omitted (the coordinator's call; §6 Q7).
   The hand-model entry (2) never renders a licence until the register row is flipped.
4. The two large third-party files (ONNX Runtime `ThirdPartyNotices.txt`, OpenCV
   `LICENSE-3RD-PARTY.txt`) may be served as `/notices/<file>` from the installed
   distribution (`importlib.metadata.distribution(...).files`, read-only, text/plain,
   bounded at 1 MiB) **only if** the route checks the file's SHA-256 against the value
   recorded in `notices.json` and returns 404 on a mismatch (so an upgraded wheel cannot
   silently serve a different notice than the register verified). Otherwise embed them.
5. The Privacy view links to `/notices` with the text "Third-party notices" and the
   link opens same-origin (the no-egress smoke assertion covers it).
6. `test_cp5_api.py` asserts: 200 without a session; every entry with a holding
   condition appears by component name and licence id; the hand-model licence string is
   absent while §2b is UNVERIFIED; the CUTE paragraph appears exactly when an approved
   `cute` calibration exists and not for `synthetic`; no `item_id`, no number from the
   retention counts, no vector key.

### 3.4 Keeping `notices.json` in sync with the register (the rule and the test)

Rule: **the register is the source; `notices.json` is derived; the test fails when they
disagree in either direction.** Concretely:

1. `docs/LICENSES.md` carries (from today) a §8 fenced JSON block `notices-expected`
   listing, per expected entry, `{component, version, licence, condition}` for exactly
   the rows of §3.1 whose status is VERIFIED-COMMERCIAL. Oversight owns both lists.
2. `server/test_cp5_api.py` (or a `test_cp5_notices.py`) parses that block and
   `server/notices.json` and asserts: the set of `component` names is equal; for each,
   `licence` and `condition` are equal and `version` matches the register's pin (and, for
   `vision_*`, `hand_landmarker.task`, `dinov2_vits14.onnx`, the `version` in
   `scripts/model_pins.json`); every `notice_text` is non-empty and contains the licence
   text's identifying first line (`Apache License` / `MIT License` / `BSD` /
   `GNU LESSER GENERAL PUBLIC LICENSE` / `Attribution 4.0 International`) and the
   copyright line named in §3.1; no entry names a component whose register row carries
   `UNVERIFIED` or `REJECTED` on the line that names it (reuse `licence_verified`'s
   row-structured read, `memory_app.py:176-184`, against the notices component name).
3. For Python dependencies the test also compares `version` with
   `importlib.metadata.version(component)` of the environment running the tests and
   **fails** on a mismatch with the message "update docs/LICENSES.md §1, §8 and
   server/notices.json together"; the register's 7-day rule for new upstream versions
   applies to the re-pin (CP3 §7 Q10 for onnxruntime).
4. A new runtime dependency, asset or dataset use follows register rule 1 ("register
   first, code second") and now also adds its `notices-expected` line and its
   `notices.json` entry in the same change; the bootstrap module-graph test is the
   place that catches an import the register does not list.

### 3.5 Register changes made today (`docs/LICENSES.md`)

| Change | Where |
| --- | --- |
| MediaPipe copyright line corrected to "Copyright 2022 The MediaPipe Authors." (source headers); "no NOTICE file at `master`" recorded with today's 404 | §5 row, §7 |
| OpenCV: the wheel-bundled `LICENSE-3RD-PARTY.txt` (179,634 B, SHA-256 `2537f565…`) and `cv2/LICENSE.txt` identified as the texts to ship; the FFmpeg note wording of §3.1 entry 13 | §5 row, §7 |
| flatbuffers wheel ships no licence file (text from the repository) | §1 row note, §5 |
| Tabler row: upstream `LICENSE` fetched, identical to the local file; condition "only when a served page embeds the icons" | §5 row, §7 |
| New §8 "Notices sync list" with the `notices-expected` JSON block and the rule of §3.4 | §8 (new) |
| CP5 fetch-method paragraph and evidence hashes (today's table) | preamble, §7 |

No status token changed; no row gained the words UNVERIFIED or REJECTED.

## 4. Frame accounting privacy

### 4.1 The telemetry schema against the CP4 data-class map (`OVERSIGHT_CP4.md` §1.2, P2.4)

| Field group | Values | Class | Already in the map? |
| --- | --- | --- | --- |
| `schema_version`, `t_ms`, `clock_anchor`, `window_ms` | integers | IDS | yes (timestamps) |
| `device_id` | the browser's stored id | IDS | yes (`episode_revisions.device_id`, `idle_frames.device_id`, IndexedDB `meta.device_id`) |
| `session_id` | a random id per capture session | IDS | new column, same class; must be random, never derived from a name, the PIN or the cookie |
| `counters` (16 named integers: `frames_captured … bytes_sent`) | counts | counts | new table; the same class as `maintenance_counters` and the `reobservations` counts |
| `timing` (`fps_observed`, `infer_ms_p50/p95`, `tick_ms_p95`) | bounded floats | numbers | new |
| `settings` (`width`, `height`, `frame_rate`) | the negotiated `getSettings()` values | numbers | new; the camera mode, not an image |

**No new personal-data class.** No image, no landmark, no location text, no name, no
free text, no geolocation. What is new is a **behavioural trace at one-minute
resolution** (when the camera was on, how often episodes started), the same kind of
trace the map already carries for `reobservations` ("gone at 14:02") and
`maintenance_counters`; it is personal by linkage (it describes a household's day) and
private, not anonymous (BUILD_CONTRACT: metadata "is not declared anonymous").
Requirements that follow:

1. **Closed key sets, enforced at ingest** with the project's `StrictModel`
   (`extra="forbid"`): exactly the counter names of plan L615-618, the four timing names,
   the three settings names; every value an integer or finite float within a stated
   bound (counters ≥ 0 and ≤ 10^9; `window_ms` ≤ 3,600,000; `fps_observed` 0..240;
   `infer_ms_*`, `tick_ms_p95` 0..60,000; `width`/`height` ≤ 8192; `frame_rate` ≤ 240;
   `device_id`/`session_id` matching the existing id regexes). Anything else is 400,
   never stored partially. The 64 KiB body cap applies before parsing.
2. **No free text anywhere**: no `reason`, `user_agent`, `note`, `error` string; the
   browser's gap reasons stay in the packet's `gaps[]` (already in the map) and the
   telemetry carries only `gaps` and `gap_ms` counts. A `user_agent` or iOS version is
   a human-recorded rig fact (L371), not a telemetry field.
3. **Retention and erasure**: rows expire with `episodes_days` (plan) **and**
   `erase_profile` deletes the table (the plan does not say so; "everything in the
   profile" must include it, as CP4 §1.3 item 5 required for the v1 tables);
   `erase_item` leaves it (not item-linked). The erase report counts it
   (`frame_counters` → a plain number). Observed while writing this pass: the working
   tree's `erase_profile` already deletes `frame_counters` and reports `telemetry: 0`
   (`episode_store.py:1756` in the uncommitted tree; a scratch-database run of the
   §5 step-3 snippet printed `"telemetry": 0` in the counts). Pass 2 confirms it with
   the tester's assertion.
4. **Local only**: `POST /api/telemetry` is same-origin, session-protected, in the
   `known` set; nothing is forwarded; no third-party endpoint; the Playwright no-egress
   assertion covers a session with telemetry posting.
5. **Read paths return aggregates**: `GET /api/coverage?day=` returns the
   `coverage(day_utc)` dict only (`camera_on_ms, gap_ms, episodes, packets, idle_sent,
   idle_dropped, sessions`); `/api/health` adds today's dict; **no route returns raw
   `frame_counters` rows**, no per-minute series leaves the server in CP5 (the Status
   panel's "live counters" are the browser's own in-memory counters, which it already
   has; it does not need them back). If a per-session series is wanted later it is a
   protected route and a map row.
6. **Clock**: `t_ms` is the browser's clock with `clock_anchor`; the server stores
   `received_ms` from the injected clock (as `episode_revisions.received_at_ms`) and
   `coverage()` is computed on observation time, never arrival time (L156); a window
   whose `t_ms` is implausible (the CP1 `clock_status` rule) is stored with the
   anomaly flagged, not dropped silently, so coverage loss is reported and not hidden
   (plan L626).
7. **Numbers are not accuracy**: `fps_observed` and `infer_ms` are rig-implementation
   measurements (L167: "a measurement of the rig implementation, not a bound on the
   target"); the Status panel and any summary label them as such.

### 4.2 What the Status panel (Privacy view) may show

May show: today's coverage (camera-on time, gap time, number of gaps, episodes, packets
sent/acknowledged, idle stills sent/dropped), the live counters of the current session
(frames captured/analysed/skipped/dropped, landmark results and timeouts, inference ms
p50/p95, observed fps), the negotiated capture settings, and the sentence "Coverage
loss is time the camera was off or the page was hidden; Pam cannot know what happened
then" (L148, L156: every stop is coverage loss and is reported, never hidden).

May not show: any claim that a gap "was quiet" or "nothing happened"; a battery, thermal
or power figure (the rig cannot measure them, L140, L367); a "recognition rate",
"accuracy" or "success" number; counters labelled as native-target performance; a
per-minute history beyond today's aggregates; anything from another profile or device.
The panel is in the Privacy view because it describes what the camera did, which is
what the disclosure promises to be honest about.

## 5. The consolidated rig checklist (the user executes this on the laptop + iPhone)

Conventions: the laptop is the Windows 11 machine with Python 3.11 (`CLAUDE.md`,
handoff §5); commands are given for PowerShell (`PS>`) and for bash (Git Bash/macOS,
`$`); run from the PAM checkout root; `python` is the venv interpreter. "Record" names
the file: **RE** = `docs/RESEARCH_EXPERIMENTS.md` (a new X-ID per run, with the minimum
run record of its last section), **LIC** = `docs/LICENSES.md`, **PINS** =
`scripts/model_pins.json`, **HO** = `docs/CONTINUATION_HANDOFF.md` §5. "Unblocks" names
the capability or gate. Steps marked **GATE** are the go/no-go conditions of §6; the
others are required before the measurement they feed. Nothing is skipped: a step that
cannot be done is recorded as blocked (RE), which is a result about the blocker.

| # | Step | Commands | Expected output | Unblocks | Record |
| --- | --- | --- | --- | --- | --- |
| 1 **GATE** | **Laptop environment** (CP3 §0 step 1 generalised; no AGPL package): a PAM venv with the served app's runtime deps and the test deps; never `pip install -r perception/requirements.txt` (it declares `ultralytics` and the AGPL `CLIP` fork, register §6) | `PS> py -3.11 -m venv .venv; .\.venv\Scripts\Activate.ps1; python -m pip install -U pip; python -m pip install -r server/requirements.txt pydantic numpy opencv-python-headless playwright==1.63.0; python -m playwright install chromium; python -c "import fastapi, starlette, pydantic, numpy, cv2, onnxruntime; print('ok', cv2.__version__, onnxruntime.__version__)"; python -m pip show ultralytics` · `$ python3.11 -m venv .venv && . .venv/bin/activate && python -m pip install -U pip && python -m pip install -r server/requirements.txt pydantic numpy opencv-python-headless playwright==1.63.0 && python -m playwright install chromium && python -c "import fastapi, starlette, pydantic, numpy, cv2, onnxruntime; print('ok', cv2.__version__, onnxruntime.__version__)"; python -m pip show ultralytics` | `ok 5.0.0.93 1.30.0`; `pip show ultralytics` prints "Package(s) not found"; `python -c "import cv2; print(cv2.getBuildInformation())" \| findstr /i "GUI"` (PS) / `grep -i gui` (bash) shows no Qt | every later step; the laptop run of every suite on 3.11 (CP2 §0 step 4) | HO §5 (versions actually installed: `python -m pip freeze > ` a scratch file, paste the pinned lines) |
| 2 **GATE** | **Every suite on Python 3.11, zero skips** (CP2 §0 step 4 covered one suite; the sandbox proves 3.13 only) incl. the CP5 suites, the self-check and the scenario runner | `PS> $env:PYTHONPATH=""; $env:PYTHONNOUSERSITE="1"; $env:PYTHONDONTWRITEBYTECODE="1"` · `$ export PYTHONPATH="" PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1` then, both shells: `python -B perception/test_capture.py -v` · `python -B perception/test_interaction.py -v` · `python -B perception/test_private_files.py -v` · `python -B server/test_memory_lifecycle.py -v` · `python -B server/test_personal_pipeline.py -v` · `python -B server/test_memory_bootstrap.py -v` · `python -B server/test_cp2_controller.py -v` · `python -B server/test_cp2_models.py -v` · `python -B server/test_cp2_staleness.py -v` · `python -B server/test_cp3_identity.py -v` · `python -B server/test_cp3_api.py -v` · `python -B server/test_cp4_api.py -v` (and `_containment`, `_erasure`, `_fixtures`, `_hull`, `_idle`, `_migration`, `_retention`) · `python -B server/test_cp5_resolver.py -v` (and `_rubric`, `_scenarios`, `_telemetry`, `_api`, `_fixtures`, and any further `server/test_cp5_*.py` the tester adds) · `python -B phone/test/test_ui_smoke.py -v` · `python -B scripts/cp4_selfcheck.py` · `python -B scripts/cp5_selfcheck.py` · `python -B scripts/check_notices.py --installed` · `python -B scripts/run_scenarios.py server/fixtures/cp5/scenarios` | every file ends `OK` with no `skipped=` on the line; both self-checks print `SELF-CHECK PASSED`; `check_notices.py --installed` prints `NOTICES SYNC OK` (a `DRIFT` line means the laptop's wheel differs from the pin: stop and re-pin the register §1/§8 and `notices.json` together); the scenario runner prints every query `OK`, the summary, and the no-claim sentence as its last line, exit 0 (sandbox 2026-10-10: 24 queries OK); `test_private_files` exercises the Windows DACL branch | G-TEST on the laptop; the Windows branch of B-09's private-file tests | RE (new X-ID: "CP5 laptop run, Python 3.11, Windows 11 build …", per-suite counts); HO §5 |
| 3 **GATE** | **Windows privacy branch** (CP4 P2.6 item 3, T5): `sidecar_report()` after writes and after an erase-all, `PRAGMA secure_delete`, `PRAGMA compile_options`, the `VACUUM INTO` swap path, on a scratch database | both shells, from the repo root: `python -B -c "import tempfile, pathlib, json; from perception.object_memory import ObjectStore; from perception.consent import CONSENT_VERSION; d=pathlib.Path(tempfile.mkdtemp()); s=ObjectStore(d/'rig-check.db', profile_id='local'); print('create', json.dumps(s.sidecar_report())); s.acknowledge_consent(CONSENT_VERSION, 'operator'); print('write', json.dumps(s.sidecar_report())); cm=s._connection(); c=cm.__enter__(); print('secure_delete', c.execute('PRAGMA secure_delete').fetchone()[0], 'journal', c.execute('PRAGMA journal_mode').fetchone()[0], 'opts', [r[0] for r in c.execute('PRAGMA compile_options') if 'SECURE' in r[0]]); cm.__exit__(None, None, None); print('erase', json.dumps(s.erase_profile(actor='operator', confirm='ERASE EVERYTHING'))); print('after', json.dumps(s.sidecar_report()))"` | every `exists: true` entry reads `private: true` in all three reports (sandbox run today: db and `-journal` private after create and write; after the swap the old journal is gone); `secure_delete 1`, `journal persist`, `opts ['SECURE_DELETE']`; the erase report reads `"swap": "replaced"` (not `in_place`), `"scope": "logical"`, `"forensic_erasure": false` and counts only; no path printed | G-PRIV's Windows branch (closes the "Windows unverified" line of CP4 P2.5 item 7) | RE (P-107 Windows branch, the three JSON lines); HO §5 |
| 4 **GATE** | **Certificate pair, firewall, Safari trust** (CP1/CP2; `CLAUDE.md` "Firewall"): the server generates or reuses `phone/cert.pem`/`key.pem` for the LAN IP; Windows Defender must allow inbound 8443; the iPhone trusts the certificate once | `PS> python -c "from phone.serve import lan_ip; print(lan_ip())"; python server/memory_app.py` (first run: allow the Defender prompt) · `$ python -c "from phone.serve import lan_ip; print(lan_ip())"; python server/memory_app.py` · then `PS> openssl x509 -in phone/cert.pem -noout -subject -ext subjectAltName -dates; icacls phone\key.pem` · `$ openssl x509 -in phone/cert.pem -noout -subject -ext subjectAltName -dates; ls -l phone/key.pem` · on the iPhone (Safari): open `https://<lan-ip>:8443/api/health`, accept the certificate warning, expect `{"error":"Sign in is required."}`; open `https://<lan-ip>:8443/`, sign in with the PIN (`PAM_AUTH_PIN`) | the SAN lists the LAN IP; the key file is owner-only (`icacls` shows only the current user; `ls -l` shows `-rw-------`); the health JSON (401) proves TLS and the port; the page loads | the secure context Safari needs for `getUserMedia` (L148, L351); every phone step | HO §5 (iPhone model, iOS and Safari versions, standalone or tab: L371) |
| 5 | **Store-trip connectivity decision** (L154): choose carry-the-laptop on a hotspot, an authenticated tunnel, or record-and-replay, **before** any store trip; nothing in CP5 depends on it, but the choice must exist before the scripted trip | none (a decision) | one line in HO stating the choice and its exposure/bandwidth note | the scripted store-trip scenario (Part 1 L250, L380) | HO §5 |
| 6 **GATE** | **The rig landmark release** (CP4 §2.3 item 1, §2.5, §8 Q12; required **before** any capture with the hand model on a real hand, i.e. before step 10's iPhone run): one page in plain words with the five elements of CP4 §2.5 (what: 21 points per hand per analysed picture; purpose: busy detection and masking the hand out of item photos, never recognising whose hand; term: 72 h then a box; others' hands treated the same; erasure), signed (electronic signature is fine) by **everyone** whose hands will be in frame, kept with the research record; the user alone on the user's own device still signs it (it is the 15(b)-shaped record) | none (a document) | a signed page per person, dated before the first automatic-capture session | the hand-model rig run (step 10) with any person in frame; CP2 §4 "use beyond the rig" | RE (the release's date and the count of signatories, no names); HO §5 |
| 7 | **Hand-model licence at the primary source** (CP2 §0 step 1; B-05/C-03): open the model card PDF, transcribe its licence line verbatim into LIC §2b; flip the row token only if the terms permit commercial use **and** redistribution; otherwise leave UNVERIFIED and raise with counsel | browser: `https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Hand%20Tracking%20(Lite_Full)%20with%20Fairness%20Oct%202021.pdf` (the "Model Card" link on `https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker`); then `PS> Select-String -Path docs\LICENSES.md -Pattern "hand_landmarker.task"` · `$ grep -n "hand_landmarker.task" docs/LICENSES.md` | the row names the file, the licence id and exactly one `status:` token; a verified row contains neither UNVERIFIED nor REJECTED anywhere on the line | `automatic_hand_recognition` (CP2 §4 condition 1); the notices entry 2 | LIC §2b (verbatim quote, date, your name as "read by"); PINS unchanged yet |
| 8 | **Download and hash the pinned hand model** (CP2 §0 step 2; never `/latest/`) | `PS> curl.exe -L -o hand_landmarker.task "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"; Get-FileHash .\hand_landmarker.task -Algorithm SHA256; (Get-Item .\hand_landmarker.task).Length` · `$ curl -L -o hand_landmarker.task "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"; sha256sum hand_landmarker.task; stat -c %s hand_landmarker.task` | a 64-hex digest and a size in bytes | step 9 | PINS (`sha256` of the `hand_landmarker.task` entry; `url` is filled); LIC §2b (hash, size, date) |
| 9 | **Fetch under the gates and provision** (CP2 §0 step 3) | both: `python scripts/fetch_models.py --dry-run` then `python scripts/fetch_models.py` then `PS> git status --short phone\assets\models` · `$ git status --short phone/assets/models` | dry run: before steps 7-8 the five tasks-vision entries "would fetch", the hand model "refused … sha256 is null" (sandbox today: exactly that, plus `dinov2_vits14.onnx` refused for the same reason until step 14; a refused entry does not stop the others, `fetch_models.py:282-291`); after 7-8: the six browser entries "would fetch"/"present"; the fetch writes `phone/assets/models/MANIFEST.json` with 6 assets; `git status` lists nothing (`.gitignore` carries `*.task`, `*.wasm`, `phone/assets/models/`) | the manifest the server reads; step 10 | RE (the fetch log line per asset with its hash); HO §5 |
| 10 **GATE** | **Enable the hand model and verify on the devices** (CP2 §0 step 5, §4 conditions 2-3), after step 6 | `PS> $env:PAM_ENABLE_HAND_MODEL="1"; $env:PAM_AUTH_PIN="<pin>"; python server/memory_app.py` · `$ PAM_ENABLE_HAND_MODEL=1 PAM_AUTH_PIN=<pin> python server/memory_app.py` · laptop Chromium and iPhone Safari: sign in, `GET /api/health` in the page's console (`fetch('/api/health').then(r=>r.json()).then(console.log)`), Camera view: turn the automatic toggle on · then in a second terminal with the server stopped: `PS> $env:PAM_ENABLE_HAND_MODEL="1"; python -B phone/test/test_ui_smoke.py -v` · `$ PAM_ENABLE_HAND_MODEL=1 python -B phone/test/test_ui_smoke.py -v` | health: the hand model `provisioned: true, licence_recorded: true`, capability `enabled: true` with a reason that still says "accuracy unmeasured"; the status line "Camera on · automatic capture (hand model float16/1)"; the toggle enabled on both browsers; the smoke suite green with `test_00_egress_controls_detect_and_block_a_foreign_request` and `test_99_no_request_left_the_origin` covering the live worker (the only foreign attempt is the `odml.pa.googleapis.com` POST, blocked or absent) | `automatic_hand_recognition` on the user's own device (CP2 §4 go); P-101 and P-103 can start | RE (X-ID: the health JSON's `models`/`capabilities`, the browsers' versions, the smoke counts); HO §5; the start of P-101 is recorded as "not yet measured" |
| 11 | **Export environment for DINOv2** (CP3 §0 step 1; dev-only, never the served venv) | `PS> py -3.11 -m venv .venv-export; .\.venv-export\Scripts\Activate.ps1; python -m pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu; python -m pip install -r requirements-dev.txt` · `$ python3.11 -m venv .venv-export && . .venv-export/bin/activate && python -m pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu && python -m pip install -r requirements-dev.txt` | `python -c "import torch, onnx, onnxruntime; print(torch.__version__, onnx.__version__, onnxruntime.__version__)"` prints `2.14.1+cpu 1.23.1 1.30.0` | steps 12-14 | HO §5 |
| 12 | **Clone DINOv2 at the pinned commit** (CP3 §0 step 2) | both: `git clone https://github.com/facebookresearch/dinov2.git ../dinov2; git -C ../dinov2 checkout 7764ea0f912e53c92e82eb78a2a1631e92725fc8; git -C ../dinov2 rev-parse HEAD` | prints `7764ea0f912e53c92e82eb78a2a1631e92725fc8` | step 14 | - |
| 13 | **Download and hash the upstream weights** (CP3 §0 step 3; the LVD-142M ViT-S/14 backbone, not `_reg4_`, nothing from XRay-DINO/Cell-DINO) | `PS> curl.exe -L -o ..\dinov2_vits14_pretrain.pth "https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth"; Get-FileHash ..\dinov2_vits14_pretrain.pth -Algorithm SHA256; (Get-Item ..\dinov2_vits14_pretrain.pth).Length` · `$ curl -L -o ../dinov2_vits14_pretrain.pth "https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth"; sha256sum ../dinov2_vits14_pretrain.pth; stat -c %s ../dinov2_vits14_pretrain.pth` | a digest and a size (~88 MB) | step 14 | PINS (`upstream_sha256` of `dinov2_vits14.onnx`); LIC §3b (`.pth` hash, size, date) |
| 14 | **Export, parity, hash** (CP3 §0 step 4) | `PS> $env:XFORMERS_DISABLED="1"; python scripts/export_dinov2_onnx.py --repo ..\dinov2 --weights ..\dinov2_vits14_pretrain.pth --expect-weights-sha256 <hash from 13> --out server\models\dinov2_vits14.onnx; Get-FileHash .\server\models\dinov2_vits14.onnx -Algorithm SHA256; Get-Content .\server\models\dinov2_vits14.onnx.provenance.json` · `$ XFORMERS_DISABLED=1 python scripts/export_dinov2_onnx.py --repo ../dinov2 --weights ../dinov2_vits14_pretrain.pth --expect-weights-sha256 <hash> --out server/models/dinov2_vits14.onnx; sha256sum server/models/dinov2_vits14.onnx; cat server/models/dinov2_vits14.onnx.provenance.json` | the sidecar shows the commit, the weight hash, opset 17, input `[1,3,224,224]`, output `[1,256,384]`, and `max_abs_diff` **below 1e-3**; if not, stop and report, do not record the hash | step 15 | PINS (`sha256`); LIC §3b (ONNX hash, size, export date, torch/onnx versions from the sidecar) |
| 15 | **Register the local export and manifest it** (CP3 §0 step 5, P2.5) | both: `python scripts/fetch_models.py --dry-run; python scripts/fetch_models.py --only dinov2_vits14.onnx; git status --short server/models ../dinov2_vits14_pretrain.pth` (PS: `server\models`) | dry run before 14: `missing` (exit 1); after: `present … local export` (exit 0); `server/models/MANIFEST.json` written; `git status` lists nothing (`server/models/`, `*.pth`, `*.onnx` ignored) | step 16 | RE; HO §5 |
| 16 **GATE** | **Enable the identity model and verify** (CP3 §0 step 6, §6 conditions 1-3, 6) | `PS> $env:PAM_ENABLE_IDENTITY_MODEL="1"; $env:PAM_ENABLE_HAND_MODEL="1"; python server/memory_app.py` · `$ PAM_ENABLE_IDENTITY_MODEL=1 PAM_ENABLE_HAND_MODEL=1 python server/memory_app.py` · in the page: `fetch('/api/health')…`; `fetch('/assets/models/dinov2_vits14.onnx').then(r=>console.log(r.status))` · with the server stopped: `PS> $env:PAM_ENABLE_IDENTITY_MODEL="1"; python -B server/test_cp3_identity.py -v; python -B server/test_cp3_api.py -v; python -B phone/test/test_ui_smoke.py -v` · `$ PAM_ENABLE_IDENTITY_MODEL=1 python -B server/test_cp3_identity.py -v && python -B server/test_cp3_api.py -v && python -B phone/test/test_ui_smoke.py -v` | health lists `dinov2_vits14.onnx` `provisioned: true, licence_recorded: true`; `physical_instance_recognition` **`enabled: false`** with "no approved calibration: identity stays provisional" (correct until step 23); the browser route returns **404**; suites green; no egress | P-104 measurement with identity provisional (CP3 §6 "go for the rig … for P-104 measurement") | RE (X-ID: P-104 start, "not an accuracy result"); HO §5 |
| 17 **GATE** | **Notices page** (CP5): every shipped component listed, conditions truthful, linked from the Privacy view | both: `python -B scripts/check_notices.py --installed` and `python -B server/test_cp5_api.py -v` (the sync rule of §3.4); iPhone and laptop: open `https://<lan-ip>:8443/notices` without signing in; Privacy view → "Licences and notices" | `NOTICES SYNC OK`; 200 without a session; the MediaPipe entry reads "Optional component; present on this server: yes" after step 9 (and "no" before); no `hand_landmarker` entry until step 7 flips the register row and the entry is added to §8 and `notices.json` together; the DINOv2 and ONNX Runtime entries read "present on this server: yes" after step 15; no CUTE section before step 23; the Tabler section reads "Embedded in a page served by this server: no"; the page shows no item name or count | register rule 6 ("needs its licence text … in a third-party-notices page"); CP2 §2 and CP3 §7 Q9 closed | LIC §8 (date verified on the device); HO §5 |
| 18 **GATE** | **First rig session on the iPhone, standalone** (L148, L362, L371; CP4 consent gate): add the page to the home screen, open it standalone, verify `getUserMedia`, the wake lock and `DeviceMotion` in standalone on the test iOS **before mounting anything**; acknowledge the disclosure; record the device facts | iPhone: Share → Add to Home Screen → open; Privacy view → read the disclosure → "I understand"; Camera view → Start (manual first), then the automatic toggle; Settings: auto-lock Never, brightness minimum for the session | the consent status shows the acknowledged version `rig-2026-10`; before acknowledging, Start is refused with the consent sentence (409 `consent_required` server side); the camera status shows the delivered mode (`getSettings()` width/height/fps) and "Camera on · automatic capture …"; a motion permission prompt appears once from a tap; denying it leaves the camera running with motion "unknown" | every measurement (P-101, P-103, P-105); the record L371 asks for | RE (X-ID: iPhone model, iOS, Safari, standalone yes/no, the delivered capture mode, the mount, the laptop; the consent version acknowledged) |
| 19 **GATE** | **Status panel and coverage** (CP5 frame accounting): counters post every 60 s and at stop; a screen lock shows as a gap, never hidden | iPhone: run the camera for 3 minutes, lock the screen for 60 s, unlock, stop; laptop page console: `fetch('/api/coverage?day='+new Date().toISOString().slice(0,10)).then(r=>r.json()).then(console.log)` | the Privacy view Status panel shows "Camera on" ≈ 3 min, "Gaps while the camera was on" ≈ 60 s, the sentence "The camera was interrupted for about 1 minute today (screen lock or app switch); captures during that time were not possible", the live counters and timings; `/api/coverage` returns the same aggregates (`gap_ms ≈ 60000`, `sessions 1`); health `coverage` matches; every value in the JSON but `day` is an integer. After finding 2 of P2.7 is fixed: an erase-all on the rig database leaves today's coverage at zeros | P-105's data path; the "coverage loss is reported, never hidden" acceptance line (plan L625-626) | RE (the coverage JSON for the session) |
| 20 | **P-101: hand landmarker on the mount** (replaces the worker-latency and busy-threshold initial values) | protocol: on the agreed mount, hands at 0.3 / 0.6 / 1.0 m, three grips (open hand, hand curled around a pill bottle, pinch on keys), 20 s per condition, each at analysis sizes 256 and 384 px (`HAND_FRAME_MAX`, `memory-camera.js:8`) and, if the worker exposes it, GPU vs CPU delegate; read per condition from the telemetry window and the worker: `landmark_results / frames_analysed` (presence), `infer_ms_p50/p95`, `landmark_timeouts` (against `ANALYSIS_TIMEOUT_MS = 250`, `controller.js:86`), `frames_skipped_busy`, `fps_observed`; export the per-frame `hands[]` samples of a few episodes (development trace, within the 72 h window) and compute `curl_ratio` per labelled grip | a table per condition; the threshold that separates "curled around an object" from "open hand" on this device and mount replaces `CURL_RATIO = 0.55` (`hand_busy.py:39`, `hand-busy.js:27`), `LOWER_FRAME_Y`/`LOWER_FRAME_MIN_AREA` likewise from the bbox distributions; `ANALYSIS_TIMEOUT_MS` set above the measured p95 with margin; the 256-vs-384 decision | the busy heuristic becomes a measured value; `automatic_hand_recognition`'s reason may drop "unmeasured" only for *this device and mount* | RE (X-ID under P-101: device, package 1.0.1, model float16/1, counts, p50/p95; "old browser timing estimates are not the acceptance result"); the new constants land in both languages with the tester re-pinning the goldens |
| 21 | **P-103: fast put-downs and escalation** (replaces the motion thresholds, the controller timings and the idle cadence) | protocol: 20 scripted fast put-downs (hand enters, places, leaves within ~1 s) with a second camera or a phone video as ground truth, 10 at idle analysis 2 fps and 10 at 5 fps, plus one long carry (> 3 s) to check the burst pin; for each: time from hand-in-frame to `episodes_started`, whether the packet holds `pre_contact` and `rest` keyframes, `episodes_aborted`, `frames_dropped_backpressure`, `gaps`; collect the per-frame motion `energy` on (a) a still scene for 60 s and (b) during the hand's motion | time-to-Active p50/p95 per idle rate; packets with required evidence / 20; the still-scene energy p99 and the moving-hand energy p1 set `MOTION_ON`/`MOTION_OFF` (`motion.py:36-37`, `motion.js:18-19`) with hysteresis between them; `BUSY_MIN_MS = 200`, `REST_MIN_MS = 600` (`controller.js:4-5`) checked against the measured grasp and rest durations; the idle analysis rate chosen (2 vs 5 fps) by the missed-transition rate (L142: "a lower idle rate rests on the assumption that nothing happens between samples"); `IDLE_KEYFRAME_MS = 30000` stays a product value unless the missed-transition data says otherwise | the capture controller's initial values become measured; scripted case 3 (L381) | RE (X-ID under P-103 with C-07's long-carry extension; "no interpolated hull labelled observed") |
| 22 | **P-105: 20-minute sustain and re-observation thresholds** (replaces the frame-accounting assumptions and the CP4 initial values) | protocol: a 20-minute standalone session on the named phone/iOS/Safari/mount with the user's own 3-5 objects placed and, at minute 10, one object removed from view and one moved; telemetry every 60 s; after the run: `/api/coverage`, the `reobservations` rows' `region_diff` distributions for present-unchanged, removed and lighting-changed frames (`python -c` over the store, local), the day's `maintenance_counters` (`reobs_cpu_s`, `reobs_deferred`), Safari's memory high-water (Web Inspector) | fps trend, `infer_ms`/`tick_ms` p50/p95 over time, `frames_dropped_backpressure`, `bytes_sent` per hour, gaps and recovery after a lock; the `region_diff` separation sets `REOBS_SAME_MAX = 0.06`, `REOBS_GONE_MIN = 0.18`, `REOBS_GATE_MAX = 0.03` (`reobservation.py:57-62`) and checks the 300 CPU-s/day budget against the measured per-frame cost; escalation rate (share of frames reaching the hand stage and opening an episode) and bytes/hour as the Part 1 design proxies (L140, L369), labelled rig measurements, not native bounds | the re-observation thresholds and the budget become measured; the "initial value" labels in `reobservation.py` and `identity.py:13-15` can be replaced for this device | RE (X-ID under P-105; stage p50/p95, fps trend, memory high-water, coverage loss; "not a native battery-life inference"); `docs/FINANCE.md` v1.3's P-105 list is filled from it |
| 23 | **Calibration for real use** (CP3 §0 step 7, §2, §6 condition 4; data-gated, after step 16): re-open the CUTE PURL page and confirm the licence line is unchanged (CP3 §2.1); run the P-104 calibration on the laptop from `cute` or the user's **own objects only** (`own-footage`, CP3 §2.4); register and approve on the laptop; record the held-out coverage; never a `synthetic` record on the rig database | browser: `https://purl.stanford.edu/gj714cj0414`; then `python -B -c "from perception.object_memory import ObjectStore; s=ObjectStore('<rig db path>'); print(s.register_calibration({'calibration_id': '<id>', 'embedder': '<tag from /api/health>', 'alpha': 0.05, 'quantile': <q>, 'n': <n>, 'source': 'cute'})); print(s.approve_calibration('<id>', 'operator'))"` (the tag is `dinov2_vits14@<hash16>-r2`) | the record reads `approved: true, approved_by: operator`; health flips `physical_instance_recognition` to `enabled: true` "… calibrated; accuracy unmeasured on this device"; `/notices` now renders the CUTE paragraph (entry 16) | identity `trusted` on the rig; CP3 §6 go | RE (the P-104 record with n, alpha, quantile, the held-out coverage, the crop/recipe tag); LIC §4 (PURL re-read date) |
| 24 | **BIPA §15(a)/(b) wording at the primary source** (CP4 §8 Q13, P2.6 item 2; still UNVERIFIED today, the sandbox cannot reach `ilga.gov`): a human opens the section, confirms the retention-schedule and written-release wording before any consent packet is drafted from CP4 §2.5 | browser: `https://www.ilga.gov/legislation/ilcs/documents/074000140K15.htm` (and the P.A. 103-769 page already read for §20) | the quoted elements of CP4 §2.1 ("purpose satisfied or within 3 years"; inform in writing; purpose and term; "written release") confirmed or corrected | the household consent packet (G-PILOT); nothing in the own-device rig | CP4 header table (date, by whom); HO §5 |
| 25 | **Before any household** (G-PILOT; not for the own-device rig): IRB or institutional determination (L253), the bystander plan (indicator, one-touch pause, posted disclosure that keyframes go to the laptop, retention policy for frames with other people's faces: L99, L158), written landmark releases from every regular entrant or no pilot in IL/TX (CP4 §2.3 item 2), the per-state decision (IL/TX/WA incl. RCW 19.373 UNVERIFIED), the trademark question on the name "PAM" (CP2 §3.5), the contracting entity for `LICENSE` (CP2 §5 Q10) | none (documents and counsel) | each item recorded as done or open; no household recording before all are done | G-PILOT | RESEARCH_LOG gate table; HO §5 |
| 26 | **Record the run** (every step above): the new X-IDs in RE with the minimum run record (timestamp, commit `git rev-parse HEAD` and `git status --short`, commands, hardware/OS/runtime, fixture ids, rights/consent, counts, failures by phase, blocked steps named as blocked), HO §5 updated, LIC/PINS fields filled; no raw frames, names or paths pasted into any document | `PS> git rev-parse HEAD; git status --short` · `$ git rev-parse HEAD; git status --short` | the records exist; nothing personal in them | the next checkpoint's review | RE, HO, LIC, PINS |

Twenty-six steps; the ten marked GATE (1-4, 6, 10, 16-19) are the §6 conditions; steps
7-9 and 11-15 are the human provisioning the gates depend on (10 and 16 are conditional
on them); 20-22 are the measurements that replace the initial values; 23 gates trusted
identity; 5 gates the store trip; 24-25 are the household gate, not the rig gate; 26 is
the record.

## 6. Open questions for the coordinator, and the go/no-go for "ready for the rig"

### 6.1 Open questions

1. **Provisional + aged over 7 d.** The plan's row order gives hedged; the monotone rule
   (§1.5) gives abstain. I require abstain (a sighting that is both doubtful in identity
   and more than a week old is not a reliable sighting under L197). Confirm, and the
   tester pins row 11.
2. **`identity_status` vocabulary on the DTO** (§1.6 F7): the top-level `Answer` uses
   the spec vocabulary, members keep the store's. Confirm so the browser and the rubric
   read one field each.
3. **Clarify presentation** (§1.6 F4): options as names (and at most a thumbnail without
   a location sentence) until the user picks. Builder C change; confirm.
4. **The abstain "offer"** (L93: "the offer to say when it is next seen"): no
   notification path exists, so the sentence is forbidden in CP5 (§1.3). If the
   coordinator wants the offer, it needs a feature (a "tell me when seen" flag and a
   Status-panel line), not a sentence.
5. **Metric naming** (§2.3 item 1): the plan says `summarize` reports "accuracy among
   answered"; the C-10/C-05 language requires the key and label
   `correct_among_answered` and the word "accuracy" only inside `NO_CLAIM_SENTENCE`.
   Confirm the rename.
6. **Legacy declared dependencies** (`httpx`, `elasticsearch`, `icalendar`,
   `python-dateutil`, `google-auth-oauthlib` in `server/requirements.txt`; `ultralytics`
   and the AGPL `CLIP` fork in `perception/requirements.txt`): the rig install in step 1
   avoids the AGPL file by not using it, which is a workaround. The purge
   (handoff §9 step 0, CP2 §3.7) is still waiting for the user's authorisation; CP5 is
   the natural place because the notices page now states what ships.
7. **Rendering of absent optional components** on `/notices` (§3.3 item 3): one line
   "not present on this server" (my recommendation: truthful and complete) or omitted.
8. **Large third-party notice files** (§3.3 item 4): embed in `notices.json` (simple,
   ~520 KiB) or serve from the installed wheel with a hash check. Either is acceptable;
   embedding needs the 2 MiB cap.
9. **`erase_profile` and `frame_counters`** (§4.1 item 3): the plan does not list the
   telemetry table among the erased ones; it must be.
10. **`source_note` on calibration records** (CP3 §2.5): `register_calibration`'s
    allowed keys (`episode_store.py:350`) do not include it, so the CUTE attribution
    cannot travel with the record; the notices page therefore keys the attribution on
    `source == "cute"` (§3.1 entry 16). Add the field at CP5 or record the omission.
11. **Telemetry `session_id` generation**: random per capture session in the browser
    (never derived from `device_id` or the cookie); confirm the tester asserts it.
12. **Tabler icons**: if Builder C adds icons to the chat view or the Status panel, the
    `served:tabler` entry becomes required and the version must be recorded (§3.1
    entry 15). Decide now so the notices test does not flip later.
13. **BIPA §15 text** (step 24) remains a human action; I could not fetch it in CP4 or
    today.

### 6.2 Go/no-go conditions for "ready for the rig" (the user's own device, own objects)

All required; each is a checklist step whose "expected output" is the evidence:

1. Steps 1-3: the laptop venv without AGPL code; every suite green on Python 3.11 with
   zero skips, including the five CP5 suites, the self-check and the scenario runner
   printing `NO_CLAIM_SENTENCE`; the Windows sidecar/PRAGMA/swap run private throughout.
2. Step 4: TLS on the LAN IP, the key owner-only, the iPhone trusting the certificate.
3. Step 6: the landmark release signed by everyone whose hands will be in frame.
4. Step 10, **conditional on step 7's outcome**: the hand model enabled only if the
   model card permits commercial use and redistribution and the hash is recorded;
   otherwise the rig runs in manual-marks mode (`MANUAL_STATUS`,
   `memory-camera.js:12`) and P-101/P-103 are recorded as blocked, not skipped. The
   smoke suite's no-egress assertions green with whatever worker state applies.
5. Step 16: the identity model provisioned with `physical_instance_recognition`
   `enabled: false` ("no approved calibration") until step 23; the browser route 404.
6. Step 17: `/notices` lists every `notices-expected` component with truthful
   conditions; the sync test green.
7. Steps 18-19: standalone capture verified before mounting; the disclosure
   acknowledged in-app; the Status panel reports a forced gap.
8. From pass 2 (code): the resolver meets §1.2-§1.5 with the fixture rows green; the
   rubric meets §2; telemetry meets §4.1 items 1-6; no new runtime dependency; no
   request leaves the origin; no personal data on `/notices`.

Not conditions for the rig (they gate later things): step 23's calibration
(identity stays provisional until then: the correct P-104 state), steps 24-25 (the
household gate), step 5 (the store trip).

At pass 1: **no-go**, for the same structural reason as CP2-CP4 (the code was not
there yet); the plan itself is **go** with the requirements above. The pass-2 verdict
(P2.9): code go subject to findings 1-2; the rig stays no-go until the human steps run.

## Interface notes (for the builders and the tester, pass 1)

- `Answer.identity_status` and `location_status` at the top level use the Part 1
  vocabulary; member DTOs keep the store's; `basis` is ordered most restrictive first and
  drawn from the closed list of plan L573-575 only.
- Abstain always has `members: []`, null image/time, `unknown` statuses, and never a
  place, a date, a candidate name or a promise.
- `NO_CLAIM_SENTENCE` is a constant in `perception/rubric.py`, printed first and last by
  `scripts/run_scenarios.py`, returned as `summary["claim"]`; metric keys never contain
  "accuracy".
- `server/notices.json` entries carry `condition` from the closed set of §3.1; the
  expected list is the `notices-expected` block in `docs/LICENSES.md` §8; the test
  compares both ways and the installed versions.
- Telemetry: closed key sets, bounded numbers, no strings beyond the two ids; expires
  with `episodes_days`; deleted by `erase_profile`; aggregates only on read.
- The hand-model entry on the notices page carries no licence while
  `docs/LICENSES.md` §2b is UNVERIFIED; the CUTE paragraph appears only with an
  approved `cute` calibration.

## Diff review, pass 2 (2026-10-10, after the coordinator's decisions)

Reviewed read-only in the working tree over `7ab0e5e`: `git status` shows 17 modified
files (2,478 insertions) and the new `perception/resolver.py` (508 lines),
`perception/rubric.py` (220), `perception/scenario_runner.py` (627),
`perception/scenario_frames.py`, `scripts/run_scenarios.py`, `scripts/check_notices.py`,
`scripts/cp5_selfcheck.py`, `server/notices.json` (757,801 B, 22 entries), six
`server/test_cp5_*.py` suites and `server/fixtures/cp5/scenarios/` (eight scenarios +
README). Line numbers below are in that tree.

What I ran (sandbox, Python 3.13; the laptop's 3.11 run is checklist step 2):
`test_cp5_resolver` 36, `_rubric` 12, `_scenarios` 9, `_telemetry` 12, `_api` 7,
`_fixtures` 6, `test_cp2_staleness` 13, `test_cp3_identity` 28, `test_cp3_api` 13,
`test_cp4_api` 10, `test_cp4_erasure` 7, `test_cp4_retention` 10, `test_memory_bootstrap`
21, `phone/test/test_ui_smoke.py` **26/26** (Chromium; the CP5 class incl. the Status
panel under the fake clock, the notices link and the no-egress assertion): all `OK`, no
skips. `scripts/run_scenarios.py server/fixtures/cp5/scenarios`: 24 queries, every
expectation `OK`, exit 0. `scripts/check_notices.py`: `NOTICES SYNC OK` (22/22);
`--installed`: two DRIFT lines for the sandbox's own `onnxruntime 1.29.0` and `protobuf
7.36.1` wheels against the 1.30.0 / 7.36.2 pins, exit 1, which is the designed behaviour
(the laptop install must match; step 17). `scripts/cp5_selfcheck.py`: PASSED. Plus the
scratch probes quoted under each finding.

### P2.1 The coordinator's decisions against the tree

| # | Decision | State | Evidence |
| --- | --- | --- | --- |
| 1 | provisional + aged > 7 d → abstain (monotone) | done | `resolver.py:351-370` (`row_provisional`: `age > abstain_ms` → abstain with `members=[]`, no image); `test_cp5_resolver.py:116-125` |
| 2 | DTO vocabulary split | done | `resolver.py:238-239` (`_identity_status` store → spec), `:71-72`; `present_answer` re-validates against `IDENTITY_STATUSES`/`LOCATION_STATUSES` (`memory_app.py:1239, :1257-1258`); member DTOs unchanged (`present_item`) |
| 3 | clarify = names + last-seen date, no photo, no location | done | `memory.js:964-975` (`clarifyOption`), `:1014-1019` (names only; the comment cites F4); the resolver's `options` carry `item_id` + `name` only (`resolver.py:345`) |
| 4 | no abstain "offer" | done | the three abstain templates `resolver.py:104-105, :113` contain no promise |
| 5 | `correct_among_answered` | done | `rubric.py:57, :189`; printed by `run_scenarios.py:74-76`; no key or printed label contains "accuracy" (checked over the full output) |
| 6 | purge deferred | recorded | `server/requirements.txt` unchanged; checklist step 1 installs around it |
| 7 | absent optional component = header + "present on this server: no"; CUTE omitted | done | `render_notices` `memory_app.py:676-681, :697-710` (provisioned:* and served:tabler render heading + availability + one line; calibration:cute skipped unless `True`); scratch render: "present on this server: no", no CUTE, no `hand_landmarker` string |
| 8 | large files embedded with origin/bytes/SHA blocks, re-verified | done | `notices.json` blocks `---- cv2/LICENSE-3RD-PARTY.txt (... 179,634 bytes; SHA-256 2537f565...)` and `---- onnxruntime/ThirdPartyNotices.txt (... 338,088 bytes; SHA-256 143764b9...)`; my independent hash of each embedded block (with its trailing newline) equals the register value; `check_notices.py:174-179` does the same |
| 9 | `erase_profile` covers `frame_counters` and `capture_gaps`; `coverage_days` kept 365 d | done as stated, **with a consequence** (finding 2): `episode_store.py:1860-1861` delete the two tables; `coverage_days` is not deleted, so `coverage(day)` after erase-all still answers from the rollup (`:2167-2199`, scratch probe: `camera_on_ms 60000, source rollup` after `erase_profile`) |
| 10 | `register_calibration` gained `source_note` | done | `episode_store.py:403` (`MAX_SOURCE_NOTE = 400`, `:117`) |
| 11 | `session_id` random per start | done | `memory-camera.js:108, :249` (`uuid()` = `crypto.randomUUID()`, `memory-queue.js:5`) |
| 12 | Tabler entry present, never rendered today | done | `notices.json` entry `tabler-icons` with `served:tabler`; `TABLER_SERVED = False` (`memory_app.py:184`); the page prints "Embedded in a page served by this server: no" |
| 13 | BIPA text human | unchanged | checklist step 24 |
| A | new basis token `coverage_gap`; gap after a reliable sighting → hedged with the fixed text | done | `resolver.py:76, :121-122, :385-393`; the flag `gap_since` is derived from `capture_gaps` (`episode_store.py:1262-1286`), fed by packet gaps (`:538-544`) and telemetry windows with `gap_ms > 0` (`:2063-2066`); `test_cp5_resolver.py:148, :466` |
| B | telemetry not consent-gated | done | `memory_app.py:1407-1421`; `test_cp5_telemetry.py:273` |
| C | word-subset name matching intended | recorded | `resolver.py:154-157`; a stop-word-only question gives abstain with no catalogue dump (scratch probe) |
| D | `frame_rate` may be 0 | done | `episode.py:325-327` (`ge=0`); the browser sends 0 when `getSettings()` has none (`memory-camera.js:141`) |

### P2.2 Resolver templates against §1 (every template, verbatim)

| Template (`resolver.py` line) | Text | Verdict | Note |
| --- | --- | --- | --- |
| `TEXT_NO_MATCH` (104) | "I have no matching stored evidence." | pass | no place, date, name or promise |
| `TEXT_NO_MATCH_PENDING` (105) | "I have no matching stored evidence yet; recent events are still being processed." | pass | L195: it does not say "I haven't seen it"; "yet … still being processed" is the honest pending state |
| `TEXT_CLARIFY` (106) | "Which stored item do you mean?" | pass | no location; options are names (P2.1 item 3) |
| `TEXT_GROUP` (107) | "I have {n} items that look alike; which one is yours?" | pass | no merged location; members keep their own cards |
| `TEXT_CONFIDENT` (108) | "The recorded location of {name} is {location}." | **fail (missing time), not a false claim** | §1.3 requires the time in every confident/hedged sentence (L93 "photo, time, room"); the card shows "Observed: {date}" (`memory.js:955-961`), so the visual path has it; the sentence alone (a future spoken path) does not. Finding 4 |
| `TEXT_INFERRED` (109) | "I think {name} is with {container}, which I last saw at {location}." | **fail (missing both times), not a false claim** | L75: "I saw the keys go into the purse at 2 pm; I saw the purse on the chair at 3 pm"; `inference.since_ms` is in the projection and unused. Finding 4 |
| `TEXT_INFERRED_LOST` (110) | "I think {name} is with {container}, but I do not know where {container} is now." | pass (time recommended) | truthful: no place claimed |
| `TEXT_NEGATIVE_REOBSERVATION` (111-112) | "I recorded {name} at {location} on {date}, but it was no longer there when I looked on {since}." | pass | old place as history with both times; the closing "I do not know where it is now" of §1.3 is recommended, not required |
| `TEXT_AGED_ABSTAIN` (113) | "I have no recent evidence for {name}." | pass | no place, no date, no image; names only the matched item |
| `TEXT_AGED_HEDGED` (114) | "I recorded {name} at {location} on {date}, but that was more than a day ago; it may have moved since." | pass (age in days recommended) | the date is given; the age itself is not computed for the listener |
| `TEXT_PICKED_UP` (115) | "I recorded {name} being picked up on {date}, but I did not record where it was put down." | pass | no current place |
| `TEXT_HISTORICAL` (116) | "Earlier evidence recorded {name} at {location}; its current location is uncertain." | pass for the implausible-clock case; **wrong axis for an ambiguous identity** | reached by `row_historical_location` (`:446-453`) for an `ambiguous` item that still has a placement (scratch probe: basis `['placed', 'lookalikes']`, identity_status `group`, text says the location is uncertain and never that another item looks the same). Truthful (a lookalike seen elsewhere may be this item) but it hides the reason. Finding 6 |
| `TEXT_LOOKALIKES` (117) | "I have evidence for {name}, but it looks like {n} other stored item{s} and I cannot tell them apart." | pass | reached only when the ambiguous item has no place (`:456-463`) |
| `TEXT_PROVISIONAL` (118) | "I have a sighting that may be {name}, but I cannot confirm its identity or where it is now." | pass | "may be"; no place (a provisional identity never carries `location_text`, `episode_store.py:1033`) |
| `TEXT_PROVISIONAL_AGED` (119-120) | "I have a sighting that may be {name}, but it was more than a day ago and I cannot confirm its identity or where it is now." | pass | |
| `TEXT_COVERAGE_GAP` (121-122) | "I recorded {name} at {location} on {date}, but the camera was off or interrupted for a while since, so it may have moved." | pass | the coordinator's text; place as history with its date, hedge names coverage |
| `TEXT_SIGHTED_ONLY` (123) | "I have a sighting of {name} on {date}, but no recorded resting place for it." | pass | trusted + sighted → hedged (more conservative than my §1.2, which allowed confident on a sighting; accepted) |
| `QUESTION_CLARIFY` / `QUESTION_GROUP` (124-125) | "Which stored item?" / "Which one is yours?" | pass | |

The all-shape forbidden list (§1.3): none of the templates contains "guarantee",
"verified", "recognised", "biometric", "medication safety", "accuracy", a person's
name, a room name, or an unqualified present-tense place outside the confident shape.
Field invariants (§1.2), checked by probe and by the tester's `check_answer`: abstain
always `members: []`, image/time null, statuses `unknown` (`_answer`, `:257-272`); group
and clarify null image/time, `group`/`unknown` identity; `expired` removes the image and
sets `target_indicated` false on every shape (`:247-254`, `:281-282`). Two deviations
from §1.2, both accepted: `capture_time_ms` stays set when the image has expired
(`:266`; Part 1 L197 ties the time to the image, the plan L569 only to abstain; the time
is the observation's and the text states it, so keeping it is more informative and not
a claim), and abstain `basis` carries the identity token (`:362, :425`; see finding 1
for the consequence in the browser).

### P2.3 Rubric, runner and printout (claims language)

- `NO_CLAIM_SENTENCE` (`rubric.py:56`): "These outcomes are software-correctness checks
  on synthetic scenarios, not accuracy measurements." Shorter than §2.2 but carries the
  three load-bearing words (software-correctness, synthetic, not accuracy); returned
  under `summary["no_claim"]` (`:219`) and printed by the runner (`run_scenarios.py:80`)
  **last only**, not first (§2.2 asked for both). Recommended, not blocking: print it
  before `== summary` as well and add "no such measurement exists at this checkpoint".
- Metric keys (`rubric.py:57-58`, `:188-191`): `correct_among_answered`, `coverage` =
  answered / asked with clarify and group in the denominator only (`:180-186`),
  `confident_wrong_rate` and `hedged_wrong_rate` over all asked, the same block over
  `truth.medication` only (`:217`; never from the item's name), the fidelity split
  (`:203-215`). No key, label or printed line says "accuracy", "reliability", "success",
  "validated", "guarantee" or a Part 1 target (the full runner output was checked).
- `score()` reads structured fields only (`:124-141`); "truthfully marked historical" is
  stricter than my §2.3 item 2: only `negative_reobservation`/`picked_up` or a `stale`
  member count (`HISTORICAL_BASIS`, `:55`); an aged or coverage-gap hedge that still
  points at the old place after a move is hedged-wrong (`:27-35`, probe confirmed). That
  is Part 1 L226 applied literally; accepted as better than my floor.
- Corrections are scored chronologically: the record is appended when the `query` step
  runs (`scenario_runner.py:594-609`) and `summarize` only re-checks a present outcome
  (`rubric.py:207-209`).
- Limitation to state (finding 9): `fidelity()` grants `fidelity_ok` to any claimed
  place once `truth.moved_since` is true (`:158`; probe: a place that was never true
  scores `confident-wrong` + `fidelity_ok`), because the truth record has no
  `location_text_then`. Harmless in the shipped scenarios (the runner derives truth from
  the painted scene) but the docstring should say it.
- The seven mandatory cases plus containment and the medication set run (24 queries,
  all `OK`); every scenario file carries the `basis` sentence; the scenarios README says
  "software-correctness expectations on synthetic data, never accuracy claims" and
  "Nothing here was measured on a camera".

### P2.4 Notices

- `server/notices.json`: 22 entries = the register's §8 `notices-expected` list
  (component, version, licence, condition all equal; `check_notices.py` OK). The hand
  model has no entry (§3.1 entry 2); CUTE's `notice_text` is the register §4 paragraph
  verbatim; Tabler carries "Copyright (c) 2020-2026 Paweł Kuna"; the MediaPipe entry
  carries **"Copyright 2022 The MediaPipe Authors."**, no "Google LLC", the no-NOTICE
  statement and the privacy disclosure with the `odml.pa.googleapis.com` sentence and
  Google's consent sentence; DINOv2 carries the Meta line, the §4(b) modification notice
  and "No NOTICE file exists upstream"; OpenCV carries `cv2/LICENSE.txt` (Heinisuo), the
  Apache text, the LGPL-2.1 text, the FFmpeg "redistributed within all opencv-python
  packages / dynamically linked / ffmpeg.org / no Qt in the headless wheel" note and
  the whole `LICENSE-3RD-PARTY.txt`; ONNX Runtime carries the Microsoft line and the
  whole `ThirdPartyNotices.txt`; flatbuffers carries the Apache text (the wheel ships
  none). `application` = PAM's own MIT with the repository copyright line.
- `GET /notices` (`memory_app.py:1723-1742`): public, not under `/api/`, HTML with
  every value escaped, zero `<script>` (scratch render), CSP unchanged, per-request
  read under `MAX_NOTICES_BYTES = 2 MiB` (`:180`, `:590-609`), the closed condition set
  validated at startup (`:550-589`, `:752-757`), conditions computed from the two
  inventories, `TABLER_SERVED` and one store boolean (`:1710-1720`). No personal data
  on the page: no item name, count, id or calibration number (the only 32-hex strings
  are the SHA-256 values in the block headers). Source URLs printed, not linked
  (`:671-674`): no request leaves the origin from that page.
- Privacy view link: "Licences and notices" (`memory.html:84`), `target="_blank"
  rel="noopener"`, same origin; smoke `test_60` covers it.
- Residual, low: the public route does a file read, two inventory scans and a store
  call per request with no cache or per-path limit (the `/api/` concurrency cap does not
  apply; `:739-760`). LAN-only today; a 5-second cache would remove the only
  unauthenticated way to make the server do work. Finding 10.

### P2.5 Telemetry and the privacy map

- Schema (`episode.py:292-396`): `StrictModel` (`extra="forbid", strict=True`, `:38-39`)
  on every level; 16 counters as bounded ints (`MAX_COUNT = 10**12`, `:22`), four timings
  as bounded floats, settings through `Dimensions` (`width/height` 1..1920) plus
  `frame_rate` 0..240, `window_ms` 1..86,400,000, UUID ids, `schema_version` literal 1;
  no string field but the two ids. Body cap 64 KiB enforced in the route before parsing
  (`memory_app.py:1417`) and again in `parse_telemetry` (`:398-405`). Clock plausibility
  as for packets (`episode_store.py:2053-2056`).
- Tables: `frame_counters` (ids, times, three JSON number maps), `capture_gaps` (ids,
  times, `gap_ms`, `source` in a CHECK set, `reason` **NULL**), `coverage_days` (day,
  integer aggregates). **The packet gap's free-text `reason` is not copied**: `_record_gap`
  inserts the literal `NULL` (`episode_store.py:1258`) and the browser's telemetry body
  never carries a reason (`memory-camera.js:7, :174-182`); scratch probe: `capture_gaps`
  row `(1, None)`. The `reason` column is therefore always NULL; harmless, but the
  tester's "no free text" assertion should pin it (finding 11).
- Read paths: `coverage()` returns aggregates (`:2167-2199`); `present_coverage` copies
  only the seven plan keys, the integer extras and the maintenance counters as integers
  (`memory_app.py:1290-1306`); no route returns a `frame_counters` row; `/api/telemetry`
  and `/api/coverage` are in the `known` set and session-protected (401 without a
  session, probe), same-origin checked, not consent-gated (decision B).
- Retention and erasure: rows expire with `episodes_days` after a per-day rollup
  (`:2366-2378`); `coverage_days` expire after 365 days (`:110`); `erase_profile` deletes
  `frame_counters` and `capture_gaps` and reports `telemetry`/`gaps` counts
  (`:1860-1861`) but **leaves `coverage_days`**, so after "Erase everything" the Status
  panel's "Today's coverage" still shows the pre-erase camera-on time (probe:
  `camera_on_ms 60000, source rollup`), and the erase dialog (`memory.html:148`) does
  not say that daily totals survive. Finding 2.
- Data-class map delta: `frame_counters`, `capture_gaps`, `coverage_days` = IDS +
  counts, a behavioural trace at one-minute / one-day resolution, personal by linkage
  (same class as `reobservations` counts and `maintenance_counters`); no new class, no
  image, no text, no geolocation. §4.1 stands.

### P2.6 Browser strings

Basis plain words (`memory.js:29-44`, `BASIS_WORDS`). The coordinator's strings stand
except one:

| Token | String as built | Verdict |
| --- | --- | --- |
| `trusted_match` | "identity matched with an approved calibration" | **forbidden by §1 in two cases** (finding 1): (a) a `trusted` identity can come from the user's own correction (`_resolved_identity`, `episode_store.py:998`: `("trusted", "user_assigned")`) or from the CP2 fixture-only calibration, where no approved calibration matched anything, so the sentence is false; (b) on an abstain (`row_aged_abstain` keeps the identity token, `resolver.py:425`) it asserts an identity match for an abstention, which is the L82 problem in other words. Replace with a neutral sentence: "identity recognised from earlier evidence or from your correction" |
| `provisional_match` | "identity only provisional" | stands |
| `placed` / `sighted` / `inferred` | "an observed placement" / "only a sighting" / "with a container" | stand |
| `aged` | "the placement is more than a day old" | stands (true; on a > 7 d abstain "more than a week old" would be more exact; low) |
| `expired` | "the evidence image has been deleted by retention" | stands |
| `negative_reobservation` / `coverage_gap` / `picked_up` | "it was seen gone from that place" / "the camera was off or interrupted since the placement" / "last seen being picked up" | stand |
| `lookalikes` / `name_ambiguous` / `no_evidence` / `index_pending` / `consent_pending` | as built | stand |

`whyAnswer` (`:938-952`) lists only the server's tokens in order, adds nothing, and
reports unknown tokens as "not explained by this page". `answerMeta` (`:955-961`) shows
"Observed: {date}" only when `capture_time_ms` is set and the room exactly as sent.
Group (`:918-935`): a member's outlined figure only when its own `identity_status` is
`trusted`; a provisional member gets a plain image and its own badge (B-14). Clarify
(`:964-975`, `:1014-1019`): names + "last seen {date}", no photo, no location (F4
closed). The answer card (`:1022-1023`) suppresses the outline when
`target_indicated` is false; when it is true for a provisional member, `image()` draws
the dashed `target-unverified` style with the "identity is unverified" alt text
(`:124-128`, `:99`), which is why finding 3 is low.

Status panel (`memory.html:103-130`, `memory.js:323-334`): "These are counts and times
of this rig's own implementation; none of them says how well items are recognised";
"Coverage loss is time the camera was off or the page was hidden; Pam cannot know what
happened then"; "The camera was interrupted for N minutes today (screen lock or app
switch); captures during that time were not possible". No battery, thermal, "accuracy"
or "quiet gap" wording anywhere in the diff (grep over `memory.js`, `memory.html`,
`memory-camera.js`). The panel sits in the Privacy view. All pass.

### P2.7 Findings, ranked

| # | Severity | Where | What | Fix |
| --- | --- | --- | --- | --- |
| 1 | **medium** (truthfulness) | `memory.js:30`; `resolver.py:362, :425` | "identity matched with an approved calibration" is false for a user-assigned or fixture-trusted identity and asserts a match on an abstention (P2.6) | change the string to "identity recognised from earlier evidence or from your correction"; optionally drop the identity token from the two abstain rows (then `test_cp5_resolver.py:124` changes) |
| 2 | **medium** (privacy/consistency) | `episode_store.py:1828-1861`, `:2167-2199`; `memory.html:148` | "Erase everything" leaves `coverage_days`, so today's coverage and up to a year of daily camera-usage totals survive and the Status panel shows them after the erase; the dialog does not say so | add `DELETE FROM coverage_days WHERE profile_id=?` (and report `coverage_days`) to `erase_profile`, or add "daily camera-usage totals (numbers only) are kept" to the dialog; I recommend the delete |
| 3 | low-medium (contract) | `resolver.py:265` (`target_indicated = reference is not None`) | `target_indicated` is true for a provisional or ambiguous member (probe: provisional → `target True`); Part 1 L82 "a target indication in the image only when supported". The browser mitigates (dashed outline, unverified alt), another consumer would not | `target_indicated = reference is not None and item identity trusted`; `present_answer:1255` already passes it through |
| 4 | low-medium (contract) | `resolver.py:108-110` | confident and inferred sentences carry no time (L93; L75 wants two) | add `{date}` to `TEXT_CONFIDENT` and `since_ms`/the container's date to the inferred templates; the CP2-CP4 expectations that pin the old strings move with it |
| 5 | low (robustness) | `resolver.py:211-228, :498-501` | `policy={"max_members": 1}` with two matches raises `TypeError` (probe) instead of `ValueError` | `_check_policy` rejects `max_members < 2`, or the cut keeps the group/clarify shape over the first member |
| 6 | low (wording) | `resolver.py:446-453` | an ambiguous identity with a placement gets `TEXT_HISTORICAL` (location axis) although the doubt is identity (P2.2) | prefer a combined sentence: "Earlier evidence recorded {name} at {location}, but another stored item looks the same, so I cannot be sure this is it or that it is still there." |
| 7 | low (wording) | `resolver.py:363` | `sighted` is appended for every provisional item, incl. `location_status` `unknown` (uncertain outcome / implausible clock); the panel then says "only a sighting" | append `sighted` only when `location_status == "sighted"` |
| 8 | low (vocabulary) | `resolver.py:75-77`, `:446-453` | the implausible-clock hedge has no basis token (`['trusted_match']` only, probe), so "Why this answer" gives no reason for the hedge | an architect decision: add a `clock_uncertain` token to the closed list, or accept |
| 9 | low (documentation) | `rubric.py:144-160` | `fidelity_ok` is over-granted when `moved_since` is true and the claimed place was never true (P2.3) | state the limitation in the docstring and the scenarios README, or add `location_text_then` to the truth |
| 10 | low (robustness) | `memory_app.py:1723-1742` | public `/notices` does file + inventory + store work per request with no cap | cache the rendered page for a few seconds or apply the active-request cap |
| 11 | low (test) | `episode_store.py:1258`; `test_cp5_telemetry.py:78` | `capture_gaps.reason` is always NULL by construction; no test pins it | one assertion |
| 12 | low (printout) | `run_scenarios.py:72-80` | the no-claim sentence prints last only; rates print without a "(synthetic)" label | print it before `== summary` too |

None of the twelve is a false capability claim or a new personal-data class; 1 and 2
are the two I ask to see fixed before the first rig session (each is a few lines); 3-4
before any spoken or third-party consumer of the Answer; the rest can be scheduled.

### P2.8 Checklist refresh (§5)

- Step 2: add `python -B scripts/cp5_selfcheck.py` (prints `SELF-CHECK PASSED`) and
  `python -B scripts/check_notices.py --installed` (prints `NOTICES SYNC OK`; on a
  laptop whose wheels differ from the pins it prints `DRIFT ...` lines and exits 1, which
  is a stop: re-pin the register, §8 and `notices.json` together, never silence it).
  The scenario runner prints the no-claim sentence as its last line (not first).
- Step 17: the sync check is `scripts/check_notices.py` (the tester's `test_cp5_api.py`
  covers the page); the Privacy-view link text is "Licences and notices".
- Step 19: the forced-gap sentence to expect is "The camera was interrupted for about
  1 minute today (screen lock or app switch); captures during that time were not
  possible" (browser side) and, after the next 60 s post, `gap_ms ≈ 60000` in
  "Today's coverage" and in `/api/coverage`.
- New step 2b (after finding 2 is fixed): after an erase-all on the rig database,
  `GET /api/coverage` for today returns zeros and the Status panel shows "0 ms".
- No other step changed; the count stays 26 (+ 2b).

### P2.9 Final go/no-go

**CP5 code: go from Oversight's side**, subject to the tester's verdict and to findings
1 and 2 (string + one DELETE). The resolver obeys the field invariants and the
forbidden-sentence list; the rubric and the runner make no accuracy claim; the notices
page lists every shipped component with the corrected copyright lines and omits the
unverified model; telemetry adds counts only, never the gap reason text; nothing leaves
the origin (smoke 26/26).

**"Ready for the rig": still no-go until the human steps run**, unchanged from §6.2:
steps 1-4 (laptop 3.11 run incl. the two self-checks and `check_notices.py --installed`
clean, the Windows sidecar run, TLS and Safari trust), 6 (the signed landmark release),
10 conditional on 7 (hand model only if the card permits; otherwise manual mode with
P-101/P-103 recorded as blocked), 16 (identity model provisioned, `enabled: false` until
a real calibration), 17 (notices on the device), 18-19 (standalone verification,
in-app acknowledgement, a forced gap on the Status panel), plus findings 1-2 landed and
re-tested. Calibration (23), BIPA §15 (24) and the household items (25) gate later
things, not the rig.
