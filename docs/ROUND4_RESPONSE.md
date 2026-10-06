# Response to review round 4

Spec: `docs/MEMORY_SYSTEM_V4.md`, revision 4, commit `f7ca543` on `main` of `AneeshD04/Physical_Assistive_Memory_PAM`.
Line numbers below refer to that file at that commit. The review was against the pre-revision export (377 lines); the file is now 440 lines.

Every finding in the round 4 review is accepted and merged. No architecture changed. The spec is frozen for build, and section 10 steps 1 and 2 are cleared.

## 1. Contradictions (C1 to C3, S1, S2)

| Finding | Resolution | Where |
| --- | --- | --- |
| C1: abstention example asserted a sighting and showed a photo | Paragraph rewritten to the rule 12 shapes. Abstain: "I'm not sure where it is," no photo, no claimed sighting. | L85 |
| C2: section 3 promised phone benchmarks for every stage | Row 5 now reads "benchmarked where it runs: rig stages on the iPhone in JavaScript and on the laptop now, native stages on-device later." | L37 |
| C3: "event keyframes only" vs. idle keyframes | Storage now has two stores: durable event keyframes (6 to 8 per episode plus crops), and a 24-hour rolling idle cache for re-observation under rule 13. | L130 |
| S1: localization at 10 fps on the phone, and on the laptop | Tier 3 is evidence acquisition on the phone and says "Localization does not run here." Tier 4 runs localization on the packet, per episode, never per frame; on the rig that is the laptop, on the target it is on-device. | L114 to L115 |
| S2: optional write-path VLM row read as allowed | Row relabeled "Write-path VLM, September brief (not in v1)" with the cost cell "Excluded from v1; shown only to compare with the brief's 10 calls/day." | L203 |

## 2. The four contracts, now five

New section "Stage contracts" (L169 to L189). Each is written as an interface; values marked *initial* are starting points for the week 1 and week 2 measurements.

| Contract | What the section now fixes | Where |
| --- | --- | --- |
| Episode packet (added; the producer-consumer boundary the localizer needed) | Fields: `episode_id`, `device_id`, observation-clock `t_start`/`t_end` with wall-clock anchor, `keyframes[]` with `role`, `landmarks[]` in pixel coordinates of the named frame, `imu[]`, `location`, `gaps[]`, `quality`, `outcome_hint`. The server never needs a frame not in the packet. | L173 |
| Object-region localizer | Input is the packet. Output: `target_region {frame_id, x, y, w, h}` in that frame's pixel coordinates; `region_source` in `pre_rest_diff / carry_flow / proposer / none`; `region_confidence`; three association fields; `crops[]` with `purpose`. `none` with confidence 0 is valid and yields a context-only episode. Initial acceptance thresholds given. | L175 |
| Capture-mode controller | Transition predicates with initial values: Idle to Escalating (hand in 2 consecutive analysis frames, or motion within 1 s of a hand); Escalating to Active (grasp positive in 3 consecutive 10 fps frames); Escalating to Idle (no hand 1.5 s); Active to Settled (region stationary 1.0 s with no hand within 1.5 hand-widths, outcome `placed`; hand leaves with no region, `lost_from_view`; 3 s max gap, `uncertain`); Settled to Idle after 0.5 s refractory. Every transition logged. | L177 to L185 |
| Immediate indexing | Trigger on candidate creation; queue most-recent-episode first; readiness target 5 min, max 15, then synchronous on the next query; answer from indexed items, attach `index_pending` if any candidate from the last 24 h is unindexed, re-run the resolver on completion. | L187 |
| Answer | Fields with null rules (`capture_time` null when no reference image; `target_indicated` false then); enums for `identity_status`, `location_status`, `shape`; definition of a *reliable sighting* (trusted or provisional match with margin at or above the initial 0.15 cosine threshold, `placed` or `sighted`, most recent observation); the decision rule for confident / hedged / abstain. | L189 |

## 3. Rig-versus-target leakage

| Finding | Resolution | Where |
| --- | --- | --- |
| "Upper bound on native" (section 2 and section 7 twice) | All three now "a measurement of the rig implementation, not a bound on the target" or "a rig measurement; not a bound on the target." | L23, L132, transfer table |
| Rig counters promoted to wearable feasibility | "They are proxies that inform the design; native feasibility is established only by the native build." Bytes per hour is labeled rig transport that the target keeps internal. | L132 |

## 4. Assertions presented as evidence

| Quotation in the review | Replacement | Where |
| --- | --- | --- |
| "a handful a day" | "expected to be low after the first days and high on day one; it is measured, not assumed, including the identity fragmentation that inflates it" | L120 |
| "lower idle rate is acceptable because nothing is happening" | "rests on the assumption that nothing happens between samples; the missed-transition test evaluates that assumption rather than granting it" | L134 |
| "never stalled" by the Web Worker | "that synchronous call does not block capture or the UI; shared compute, memory and transfer contention can still stall them, and the frame counters are what will show it" | L141 |
| WebGPU on iOS 18 | "shipped by default in Safari 26" | L144 |
| resolution switching "unreliable" and "costs a stream restart" | "a frozen policy choice, not a platform fact," with the justification qualified | L128 |
| "the most common elder-care scenario there is" (sections 1 and 3) | "the scenario we prioritize above all others" and "the scenario we prioritize" | L13, section 3 table |
| "Pam's value is highest exactly when" | "We expect Pam's value to be highest when ... the pilot measures whether that holds." | L57 |
| "the single largest schedule and cash saving available" | "a large schedule and cash saving" | L89 |
| ring buffer "in every case" | A requirement, not a browser guarantee: in-memory queue for the page lifetime, IndexedDB best-effort mirror, losses recorded as coverage loss | L148 |

## 5. Not changed, deliberately

- The 69% chain in the section 3 table stays as the illustration of why end-to-end testing matters; it was never presented there as a forecast.
- "The camera is believed to be the dominant power draw" stays, labeled a hypothesis to measure alongside screen, compute, location and radio.
- Historical subagent results are recorded as historical in Part 2 (rates verified at the time; 42 of 49 integration tests passing before the SQLite fix, not rerun).

## 6. Go-ahead

Section 10 steps 1 and 2 are cleared:

1. Generate a fresh certificate and key for `phone/` (the pair from `hackmit` was not copied and may have been exposed on a shared LAN), and close the unrestricted static route in `phone/serve.py` that served `key.pem`.
2. Rerun the suite: `perception/test_capture.py`, `perception/test_interaction.py`, `server/test_memory_lifecycle.py`, `server/test_personal_pipeline.py`. Report pass/fail counts; the SQLite cleanup fix has never been rerun.

Then step 3 (the data model: three independent fields, object-centric outcomes, versioned hypotheses, retention tiers, re-observation) and step 4 (the week 1 rig benchmark and frame accounting). The `server/app.py` trim and the `auth.py` shim for `object_api.py` come with step 3.
