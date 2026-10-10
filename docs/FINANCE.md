# PAM finance model v1.3: cost per user-month, subscription sensitivity, caps

Finance agent. **v1** 2026-10-08, written for the coordinator after CP1 (`fbf6719`), before
CP2 landed. **v1.1** 2026-10-09, after CP2, for the CP3 identity stage
(`BUILD_PLAN.md` "CP3 in detail: identity", *Finance* line): adds §8 (CP3 delta: DINOv2
compute, embedding storage, one-time export and calibration costs), Appendix B (its
arithmetic), open questions 8–11, and three additive cross-reference notes marked
"v1.1" in §2.2, §5 and §7. **v1.2** 2026-10-09, at `77b769e`, for the CP4 stage
(`BUILD_PLAN.md` "CP4 in detail: re-observation, retention and erasure", *Finance* line):
adds §9 (CP4 delta: idle cache, re-observation, retention, erasure), Appendix C (its
arithmetic), open questions 12–17 and a v1.2 addendum in §5. Because the expected hosted
delta at the plan's 90-day retention default exceeds $0.05/user-month (§9.6), the hosted
and chat rows of §2.4, §3.2 and §3.3 are recomputed at `A_b = 0.72` and marked "v1.2";
the v1 values (`A_b = 0.50`) are preserved side by side in §9.6 and remain valid within
$0.05 at a 30-day retention default. §1, §4, §6, §8 and Appendices A–B are unchanged.
**v1.3** 2026-10-10, at `7ab0e5e` (CP4 landed, 341/341; the architect's "CP5 in detail" is
an uncommitted edit of `docs/BUILD_PLAN.md` in the working tree), for the CP5 stage (that
section's *Finance* line): adds §10 (CP5: the telemetry cost, the support-cost measurement
plan for the first households, the list of rig measurements that replace each assumption,
and a pre-rig bottom line with every value labelled), Appendix D (its arithmetic) and open
questions 18–22. No table in §2–§3 is recomputed: CP4's decision 2 made `episodes_days = 30`
the default [M-code], at which §9.6 already gives `A_b = 0.5413`; §10.4 tabulates that value
beside the 90-day `0.72` the §3 tables keep as the conservative case. §1–§9 and Appendices
A–C are unchanged. Nothing is measured on a device yet; §10.3 is the list of what will be.
Scope and authority: `BUILD_PLAN.md` §0 ("Finance: unit economics, cost caps the builders
must respect") and §2 ("FINANCE.md v1"). This file proposes; the coordinator decides.
Nothing here is a selected price, a measured margin or a commercial term (RESEARCH_LOG
D-010, D-013, B-17, C-10).

Arithmetic was done with Python `Decimal` (the scripts are Appendix A (v1), Appendix B
(v1.1) and Appendix C (v1.2) of this file; every row below also shows its formula, so it
can be re-run by hand). The handoff's margin formula (`CONTINUATION_HANDOFF.md` §10) is
reused unchanged; see §3.

**Provenance warning that applies to every external price in this file.** In this session
both live-fetch paths were blocked: `WebFetch` permission requests were withdrawn
unanswered, and direct HTTPS egress returned `403 connect_rejected` from the organisation
egress proxy (hosts attempted 2026-10-08: `docs.claude.com`, `stripe.com`, `anthropic.com`,
`hetzner.com`). Web search returned URLs and titles only, no page text. Therefore every
external price is labelled **`[Q-UNVERIFIED]`**: it is the last list price known to the
author (knowledge through mid-2026) at the cited canonical URL, with the attempted access
date, and **must be re-read at that URL by a human before any number in this file is
quoted outside the team.** The only prices with in-repo provenance are the Anthropic rates
the round-B cost agent recorded on 2026-10-06 (`docs/agent-round-b-raw.tar.gz`,
`45a3f1e1/content.txt` §1) and the measured 2026-09-19 VLM token counts in `CLAUDE.md`.

*v1.1 session (2026-10-09):* `raw.githubusercontent.com` was reachable by curl through the
egress proxy, so §8 cites two files fetched and hashed in session (the DINOv2 model card,
whose SHA-256 matches `docs/LICENSES.md` §7, and a timm benchmark CSV). `huggingface.co`
returned `403` at the proxy; `arxiv.org`, `aws.amazon.com` and `purl.stanford.edu` did not
connect. No public **CPU** latency figure for ViT-S/14 was obtainable, so the per-crop
time in §8 is an assumption bounded by FLOP arithmetic, not a quoted benchmark. The v1
`[Q-UNVERIFIED]` prices were not re-read and keep their label.

*v1.2 session (2026-10-09):* the same four price hosts were attempted again
(`aws.amazon.com/ebs/pricing/`, `aws.amazon.com/s3/pricing/`, `hetzner.com/cloud/`,
`backblaze.com/cloud-storage/pricing`): `WebFetch` permission requests were withdrawn
unanswered and `curl` through the egress proxy returned `CONNECT tunnel failed, response
403` for all four, so **no price was re-read and every price in §9 reuses the v1 figure
with its `[Q-UNVERIFIED]` label.** What this session could do instead was run the
repository's own code in the sandbox: the landmark byte counts in §9.1 are measured with
the real `perception/episode.py` schema classes, and the registration/blur timings in §9.2
are measured with the real `perception/motion.py` and the localizer's own OpenCV calls on
synthetic frames. Those carry a new label, **[M-sandbox]**: measured on this session's
Linux sandbox (Intel Xeon @ 2.10 GHz, 2 vCPU, OpenCV 5.0.0, numpy 2.5.3, single thread),
which is neither the household laptop nor a t3.medium; they bound the order of magnitude
and nothing more. The coordinator measures on-device later (§9.7).

*v1.3 session (2026-10-10):* `WebFetch` permission requests for `aws.amazon.com/ebs/pricing/`,
`aws.amazon.com/s3/pricing/` and `stripe.com/pricing` were withdrawn unanswered, and web
search again returned titles and URLs only (no page text), so **no price was re-read and
every price in §10 reuses the v1 figure with its `[Q-UNVERIFIED]` label.** The one new
in-session measurement is the byte size of the plan's telemetry body, sized with
`json.dumps` on the architect's fixed schema with representative values ([M-sandbox],
§10.1). CP5 code does not exist in the commit `7ab0e5e`; where §10 names a CP5 counter it
is the architect's fixed interface name, and where it names a CP4 counter (`reobs_cpu_s`,
`reobs_deferred`, `retention_counts`, `maintenance_counters`) it is [M-code] at `7ab0e5e`.
While this section was being written an **uncommitted builder draft** of the CP5 store
side (`perception/episode.py` `Telemetry*` models and `parse_telemetry`,
`perception/episode_store.py` `frame_counters`, `ingest_telemetry`, `coverage`,
`telemetry_expired` in `apply_retention`) appeared in the working tree; it is read, not
reviewed, and noted where it confirms or extends a name used here.

Labels used throughout: **[A]** assumption (ours), **[Q-UNVERIFIED]** quoted list price not
verified in session, **[Q-REPO]** price recorded in this repository's research notes with
its own URL and date, **[M]** measured in this repository (with date and machine),
**[M-sandbox]** measured in the v1.2 session's sandbox on synthetic inputs (see above),
**[M-code]** a constant read from the code at the stated commit,
**[D]** design parameter taken from the spec or contract.

---

## 1. Scope and assumptions

**Product as costed.** Text chat plus an authenticated stored-items browser, fed by a phone
camera that records episodes when the wearer's hands set something down; the answer to
"where are my glasses" is a stored photo with the region outlined (`BUILD_CONTRACT.md`
"Catalogue and text chat"; decision 4 "the photo is the answer").

Included:

- Payment processing (card, web billing; no app store).
- A fixed hosting base for sign-in, updates, backups and monitoring, allocated per user
  (the handoff's `0.75`), plus a stated absolute fixed base for the break-even table.
- Support and onboarding allocation `S`, stated explicitly with its rationale (§3.1).
- Hardware amortisation `W` as a separate line (zero under BYOD, per the handoff's note
  that its table set hardware subsidy to zero "in this particular table ONLY").
- For the hosted variants: compute for the localizer and DINOv2 CPU inference per
  episode, on-demand re-observation, object/block storage for keyframes and the 24 h idle
  cache, per-request charges, egress for photo answers, snapshots.
- For variant (c) only: an explicitly bounded cloud text-chat policy.

Excluded, and why:

- **Speech of any kind.** Out of scope (`CONTINUATION_HANDOFF.md` §10: "Current scope is
  TEXT ONLY"; `BUILD_PLAN.md` §1 "Out of scope ... Deepgram or any speech"). The
  `MEMORY_SYSTEM_V4.md` "Corrected cost model" STT/TTS lines ($5.85 Flux, Aura-2 ~$5) and
  the COMMERCIAL review's Nova-3 re-pricing are historical inputs for a deferred feature
  and are **not** carried into any table here.
- **Write-path VLM.** None in v1 (v4 "Corrected cost model": "Write-path VLM, none in v1,
  $0"). The only measured cloud number in the repo (`CLAUDE.md`, 2026-09-19,
  `claude-sonnet-5` at $2/$10 per MTok: `placed` 3 images = 1,975 in / 79 out tokens =
  $0.0047 [M]) belongs to that retired path and is cited only as the one real token
  measurement we have.
- **Cloud chat by default.** Off unless a provider AND a bounded policy are configured;
  returns `503 chat_not_configured` otherwise (`BUILD_CONTRACT.md`). Variant (b) therefore
  has no chat line; variant (c) adds one under a hard cap.
- App-store fees (no native app in scope; §3.4 shows the effect if one appears later),
  customer-acquisition cost, insurance beyond a token line in the fixed base, HIPAA/BAA
  programmes for agency customers (COMMERCIAL §6 lists these as "tens of thousands per
  year"; a go/no-go for the agency channel, not a per-user line), labelling, IRB and pilot
  costs (tracked separately per v4), taxes.

Deployment variants costed:

| Variant | Where processing and storage live | Cloud spend per user |
| --- | --- | --- |
| (a) Rig as built | iPhone browser capture + the household's own laptop running `server/memory_app.py`; zero cloud | $0 metered; still pays fees, fixed base share, support, hardware |
| (b) Hosted | Episodes uploaded to a small VM we operate; keyframes in object/block storage; photo answers served from it | compute + storage + requests + egress + snapshots |
| (c) Hosted + optional cloud text chat | (b) plus a text-only LLM call for descriptive questions, bounded by policy | (b) + chat cap |

Workload parameters common to all variants (all **[A]/[D]**, none measured; RESEARCH_LOG
B-17 forbids margin claims until they are):

| Parameter | Value | Label and source |
| --- | --- | --- |
| Episodes (handlings) per day | 50 | [D] v4 "Storage and radio": "roughly 50 handlings per day" (estimate; measure) |
| Durable keyframe bytes per day | 20 MB | [D] v4 same line: "on the order of 20 MB per day (estimate; measure)"; 50 episodes × ~8 keyframes × ~50 KB |
| Keyframes per episode | ≤ 8 selected, ≤ 10 burst | [D] `BUILD_CONTRACT.md` "Browser/controller" |
| Packet size cap | 4 MiB | [M-code] `perception/episode.py` `MAX_PACKET_BYTES = 4 * 1024 * 1024`; `phone/assets/memory-queue.js` same |
| Idle keyframes | 1 per 30 s while capturing = up to 2,880/day; 24 h cache | [D] v4 "Storage and radio"; `BUILD_PLAN.md` CP4 |
| 24 h idle cache size | ~150 MB | [A] round-B cost agent estimate ("~150 MB raw + ~77 MB index"); unmeasured |
| Queries (chats) per day | 20 | [A] coordinator's bounded policy for this file |
| Photo answer size | ~100 KB | [A] one stored keyframe at capture resolution; the `CLAUDE.md` 720p q0.7 frame was ~20 KB [M], capture-resolution keyframes are larger; unmeasured |
| CPU per episode (localizer + DINOv2 ViT-S/14 on CPU) | 0.3 to 1.0 s | [A] coordinator's range; round-B MEMORY agent "0.3–1 s [B, unmeasured]" |
| Month | 30 days for per-day lines; 730 h for VM hours | [A]; a 31-day month raises per-day lines by 31/30 (shown where it matters) |
| Tenure for hardware amortisation | 24 months | [A]; elder-care churn (death, moves to care, product abandonment) could make this far shorter |
| USD/EUR | 1.08 | [A] for Hetzner lines only |

*v1.2 note (CP4): two rows above are superseded by §9, not edited here.* "Durable keyframe
bytes per day 20 MB" counted raw JPEG bytes; the store keeps the packet **as the raw JSON
it received** (`perception/episode_store.py:ingest_episode` inserts `raw` into
`episode_revisions.packet` [M-code]), so keyframes are stored base64-encoded (× 4/3) and
the packet also carries the carry burst and up to 128 hand-landmark samples: **≈ 39 MB/day
as stored at 50 episodes/day, falling to ≈ 33 MB/day after the 72 h landmark reduction**
(§9.1.2). "24 h idle cache ~150 MB" becomes the plan's **200 MiB cap inside the SQLite
file**, which holds 60 MiB at 8 h of camera-on time and 180 MiB at 24 h (§9.1.1).

---

## 2. Cost per user-month, line by line

### 2.1 Variant (a): rig as built (laptop at home, zero cloud)

| Line | Formula | $/user-month | Label |
| --- | --- | ---: | --- |
| Metered cloud (compute, storage, egress, chat) | none; all processing on the household laptop | 0.0000 | [D] zero-cloud rig; local answers need no key (`BUILD_CONTRACT.md`) |
| Payment fee (Stripe-class card, web billing) | 0.029 × P + 0.30 | at P=5: 0.4450; P=10: 0.5900; P=15: 0.7350 | [Q-UNVERIFIED] https://stripe.com/pricing (US standard online card rate 2.9% + $0.30; access attempted 2026-10-08, blocked). Stripe Billing add-on (~0.5–0.7% of recurring volume) and +1.5% international cards are NOT in the formula |
| Fixed hosting share `H` (sign-in/licence check, update server, backups, monitoring, domain, email) | handoff allocation; equals `F_lean / 200 users` = 150 / 200 | 0.7500 | [A] handoff §10 `0.75`, kept for comparability; §3.3 shows the true share below 200 users |
| Support and onboarding `S` | §3.1 | 3.00 (lean) / 8.00 (heavy) | [A] |
| Hardware `W` | mount $25 / 24 months (only if we supply it) | 0.0000 (BYOD) / 1.0417 (bundled mount) | [Q-UNVERIFIED] retail range §4 |
| **Total cost before support** | fee + H + W | at P=10, BYOD: 0.5900 + 0.7500 = **1.3400** | |
| **Total with S=3 / S=8** | | at P=10, BYOD: **4.3400 / 9.3400** | |

Real costs the rig hides from the subscription line (not company spend, but they decide
whether a household keeps the product and what support costs):

- Household electricity for an always-on laptop: [A] ~25 W average × 24 h × 30 d =
  18 kWh × $0.17/kWh ≈ $3.06/month, paid by the household. (US average residential rate
  is roughly in that range [Q-UNVERIFIED]; https://www.eia.gov/electricity/monthly/, blocked.)
- The laptop must stay awake, on the home LAN, with a valid self-signed certificate the
  phone trusts (`phone/serve.py`; B-13 forbids automatic rotation). Every one of those is
  a support call waiting to happen; this is why `S` for the rig is not lower than for the
  hosted variant even though cloud spend is zero.
- Safari background/screen-lock gaps (handoff: "must be reported, not hidden") reduce
  coverage, not cost; they raise churn risk, which shortens the hardware tenure assumption.

### 2.2 Variant (b): hosted (episodes uploaded to a cloud server)

Per-user compute, from the workload table (formulae shown):

| Compute line | Formula | Result |
| --- | --- | --- |
| Episode write path | 50 ep/day × (0.3 … 1.0 s) × 30 d | 450 … 1,500 CPU-s/month = **0.1250 … 0.4167 vCPU-h** |
| On-demand re-observation (rule 13), capped | 20 queries/day × ≤ 40 idle keyframes × 0.1 s × 30 d | 2,400 CPU-s/month = **0.6667 vCPU-h** (this is the cap, not a forecast; [A] 0.1 s per 224 px DINOv2 compare, unmeasured) |
| Chat (local resolver) | negligible vs. the above | ~0 |
| **Total** | | **0.7917 … 1.0833 vCPU-h/user-month** |

Capacity check: a 2-vCPU VM has 2 × 730 = 1,460 vCPU-h/month; at a 25 % target
utilisation (evening peaks, unmeasured p95) that is 365 usable vCPU-h, i.e. ~337 users at
the high workload. This file provisions **100 users per 2-vCPU/4 GB VM** [A], a ~3×
safety factor for unmeasured workloads and the 24 h cache held on local disk.

*v1.1 note (CP3):* the DINOv2 ViT-S/14 share of the 0.3 … 1.0 s "episode write path"
line is broken out in §8.1: at the stated assumptions (2–4 crops × 60–150 ms) it is
0.12–0.6 s per episode, i.e. inside this line, so the table above and the 100-users/VM
provisioning are unchanged. The embeddings it stores are costed in §8.2 and amount to
≤ $0.003/user-month; the sensitivity tables' `A_b = 0.50` absorbs them (§8.3).

VM list prices (730 h/month; **all [Q-UNVERIFIED]**, access attempted 2026-10-08, blocked):

| Provider / instance | Formula | $/VM-month | $/user at 100 users/VM | Source |
| --- | --- | ---: | ---: | --- |
| AWS t3.medium (2 vCPU, 4 GB) us-east-1 on-demand + 30 GB gp3 | 0.0416 × 730 + 30 × 0.08 = 30.3680 + 2.4000 | 32.7680 | 0.3277 | https://aws.amazon.com/ec2/pricing/on-demand/ ; https://aws.amazon.com/ebs/pricing/ |
| GCP e2-medium (2 shared vCPU, 4 GB) us-central1 + 30 GB pd-balanced | 0.033503 × 730 + 30 × 0.10 = 24.4572 + 3.0000 | 27.4572 | 0.2746 | https://cloud.google.com/compute/vm-instance-pricing (before sustained-use discount) |
| Hetzner CX22/CX23-class (2 vCPU, 4 GB, 40 GB, 20 TB traffic) | €3.79 … €4.50 × 1.08 | 4.0932 … 4.8600 | 0.0409 … 0.0486 | https://www.hetzner.com/cloud/ (search-result titles 2026-10-08 show "from €3.79" and "€4.50"; the plan was renamed CX23; EU regions; US locations priced higher) |

Storage, requests, egress, snapshots (AWS S3/EBS rates unless stated; **[Q-UNVERIFIED]**
https://aws.amazon.com/s3/pricing/ , https://aws.amazon.com/ec2/pricing/on-demand/#Data_Transfer ,
https://developers.cloudflare.com/r2/pricing/ , https://www.backblaze.com/cloud-storage/pricing ;
all access attempts 2026-10-08, blocked):

| Line | Formula | $/user-month |
| --- | --- | ---: |
| Durable keyframes, 30-day retention, steady state | 20 MB × 30 = 0.6 GB × $0.023 (S3 Standard) | 0.0138 (R2 $0.015: 0.0090; B2 $0.006: 0.0036) |
| Durable keyframes, 90-day retention, steady state | 20 MB × 90 = 1.8 GB × $0.023 | **0.0414** (R2: 0.0270; B2: 0.0108) |
| 24 h idle cache on VM block storage | 0.15 GB × $0.08 (gp3) | **0.0120** (on S3: 0.0035) |
| PUT requests, **batched design**: one object per episode packet + one hourly idle bundle | (50 + 24) × 30 = 2,220 × $0.005/1,000 | **0.0111** (R2 class A $4.50/M: 0.0100) |
| PUT requests, **per-keyframe design** (for contrast) | (50 × 8 + 2,880) × 30 = 98,400 × $0.005/1,000 | 0.4920 (R2: 0.4428) |
| GET requests (photo answers + caregiver browsing) | (20 × 30 + 200) = 800 × $0.0004/1,000 | 0.0003 |
| Egress, photo answers | 800 serves × 100 KB = 0.08 GB × $0.09 (AWS, beyond the account-wide 100 GB/month free allowance) | **0.0072** (GCP premium $0.12: 0.0096; Hetzner: inside 20 TB included; R2: $0) |
| Ingress (uploads) | 0.6 GB/month; AWS/GCP/Hetzner ingress $0 | 0.0000 |
| Snapshots/backups of the 90-day set | (1.8 + 0.15) GB × $0.05 (EBS snapshot) | **0.0975** |

**Variant (b) metered total `A_b`** (90-day retention, batched objects):

| Stack | Formula | `A_b` $/user-month |
| --- | --- | ---: |
| AWS (t3.medium share + S3 + gp3 + requests + egress + snapshot) | 0.3277 + 0.0414 + 0.0120 + 0.0111 + 0.0003 + 0.0072 + 0.0975 | **0.4972** |
| AWS with per-keyframe objects instead of batched | 0.4972 − 0.0111 + 0.4920 | 0.9781 |
| Hetzner VM + Backblaze B2 + Hetzner volume (€0.044/GB [Q-UNVERIFIED]) + snapshot | 0.0486 + 0.0108 + 0.0071 + 0.0975 | **0.1640** |

For the sensitivity tables, variant (b) uses **`A_b = 0.50`** (AWS, batched; rounded up
from 0.4972) and a worst case **`A_b = 1.10`** (2× compute for unmeasured p95 plus
per-keyframe objects; this is also the handoff's `A1.10` column, so those rows reproduce
the handoff table exactly). The Hetzner stack is ~3× cheaper but EU-resident by default;
data residency for US households is a product/legal choice, not a finance one.

*v1.2 note (CP4):* at the plan's 90-day retention default the expected hosted metered
cost is **`A_b = 0.72`** (0.7175: AWS, batched objects, CP4 caps of §9.4, stored-packet
bytes of §9.1.2); the sensitivity tables now use 0.72 and keep 1.10 as the worst case,
which covers the capped CP4 worst (0.9352) only together with cap 4 (batched objects).
At a 30-day default `A_b` is 0.5413 and the v1 value 0.50 stands within $0.05. The
Hetzner stack moves from 0.1640 to 0.3019. Arithmetic in §9.6 and Appendix C.

### 2.3 Variant (c): hosted + optional cloud text chat

Policy costed (the coordinator's bounded example): **20 chats/day × ~1,500 input + 150
output tokens, text only, no images to the provider** (the photo is served from our store;
`BUILD_CONTRACT.md`: cloud prose never overrides ledger identity/location).

| Quantity | Formula | Value |
| --- | --- | --- |
| Chats per 30-day month | 20 × 30 | 600 |
| Input tokens | 600 × 1,500 | 900,000 = 0.9 MTok |
| Output tokens | 600 × 150 | 90,000 = 0.09 MTok |

Cost by price tier (per-MTok input/output). Tiers are given as **price classes** because
exact current model names/prices could not be re-read in session; the policy must be
parameterised by a price table and **fail closed on an undefined price** (handoff §10).

| Tier (input / output per MTok) | Formula | 30-day $/user | 31-day | Worst case with 1 retry on every call (×2) | Provenance |
| --- | --- | ---: | ---: | ---: | --- |
| $0.10 / $0.50 | 0.9 × 0.10 + 0.09 × 0.50 | **0.1350** | 0.1395 | 0.2700 | Round-B cost agent saw a `claude-haiku-5.5` line at $0.10/$0.50 on https://docs.anthropic.com/en/about-claude/pricing on 2026-10-06 but declined to rely on it [Q-REPO, not confirmed]; Gemini 2.5 Flash-Lite was last known at $0.10/$0.40 [Q-UNVERIFIED] https://ai.google.dev/gemini-api/docs/pricing |
| $0.25 / $2.00 | 0.9 × 0.25 + 0.09 × 2.00 | 0.4050 | 0.4185 | 0.8100 | OpenAI "mini"-class last known at $0.25/$2.00 [Q-UNVERIFIED] https://openai.com/api/pricing/ (search titles on 2026-10-08 already list GPT-5.4/5.5; re-read) |
| $0.30 / $2.50 | 0.9 × 0.30 + 0.09 × 2.50 | 0.4950 | 0.5115 | 0.9900 | Gemini 2.5 Flash last known [Q-UNVERIFIED], same URL |
| $1.00 / $5.00 | 0.9 × 1.00 + 0.09 × 5.00 | **1.3500** | 1.3950 | 2.7000 | `claude-haiku-4.5` [Q-REPO] round-B cost agent, 2026-10-06, docs.anthropic.com pricing page |
| $2.00 / $10.00 | 0.9 × 2.00 + 0.09 × 10.00 | **2.7000** | 2.7900 | 5.4000 | `claude-sonnet-5` [Q-REPO] same record; also the rate behind the measured 2026-09-19 VLM calls in `CLAUDE.md` |

Reading: the 20/day policy costs between $0.14 and $2.70 per user-month depending only on
the tier, and a naive retry policy doubles it. **The chat line is the single largest
controllable cloud cost in the product; at the $2/$10 tier it exceeds every other hosted
line combined by 5×.** The sensitivity below uses three (c) rows: cheap tier
(`A_c = 0.50 + 0.135 = 0.635`), $1/$5 tier (`A_c = 1.85`) and $2/$10 tier (`A_c = 3.20`).
*v1.2:* with `A_b = 0.72` these become `A_c = 0.855`, `2.07` and `3.42`; the chat line
itself is unchanged.

### 2.4 Summary table: cost per user-month by variant

Costs before support, at P=$10 (fee = 0.029 × 10 + 0.30 = 0.59), BYOD hardware.
*v1.2 (CP4): hosted and chat rows recomputed at `A_b = 0.72` (90-day retention, CP4 caps;
§9.6). The v1 rows at `A_b = 0.50` were 1.8400 / 1.9750 / 3.1900 / 4.5400 before support
and stand within $0.05 at a 30-day retention default.*

| Variant | Metered cloud `A` | Fee | `H` | Subtotal (no S, no W) | + S=3 | + S=8 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| (a) Rig | 0.0000 | 0.5900 | 0.7500 | **1.3400** | 4.3400 | 9.3400 |
| (b) Hosted, AWS batched (v1.2, A=0.72) | 0.7200 | 0.5900 | 0.7500 | **2.0600** | 5.0600 | 10.0600 |
| (b) Hosted, worst | 1.1000 | 0.5900 | 0.7500 | 2.4400 | 5.4400 | 10.4400 |
| (c) + chat, cheap tier (v1.2) | 0.8550 | 0.5900 | 0.7500 | **2.1950** | 5.1950 | 10.1950 |
| (c) + chat, $1/$5 tier (v1.2) | 2.0700 | 0.5900 | 0.7500 | 3.4100 | 6.4100 | 11.4100 |
| (c) + chat, $2/$10 tier (v1.2) | 3.4200 | 0.5900 | 0.7500 | 4.7600 | 7.7600 | 12.7600 |

---

## 3. Subscription sensitivity and break-even

### 3.1 Formula and the stated allocations

Handoff formula, reused exactly:

```
margin = (P - (0.029*P + 0.30) - A - 0.75 - S) / P
```

with one additive term `W` (hardware amortisation) that is **zero in every row unless the
row says "bundled mount"**; with `W = 0` the formula is the handoff's. This is an
extension the handoff itself anticipated ("hardware subsidy is zero in this particular
table ONLY"), not a correction.

Check against D-013: at P=25, A=5, S=0 the formula's fee is 0.029 × 25 + 0.30 = 1.025
and the residual 25 − 1.025 − 5 − 0.75 = 18.225 → 72.90 %; D-013's 72.88 % used the
fee pre-rounded to $1.03 (18.22 / 25). Same conclusion (not ≥ 75 %); no change to the
formula. The handoff's `A1.10/S3` and `A1.10/S8` columns are reproduced to the cent by
variant (b)-worst below.

- **Payment fee** 2.9 % + $0.30: US domestic card, web billing [Q-UNVERIFIED]. Not
  included: Stripe Billing (+0.5–0.7 %), international cards (+1.5 %), disputes ($15 each),
  app-store IAP (15–30 %, §3.4).
- **Hosting allocation `H` = 0.75**: kept from the handoff. Rationale: the lean fixed base
  `F_lean` below is $150/month; 150 / 200 = 0.75, so `H` is exact at 200 users and
  understates the per-user share below that (§3.3 handles this honestly).
- **Support allocation `S`** [A]: two values.
  - `S = 3.00` (lean): onboarding ~45 min once, amortised over an expected 12-month
    tenure = 3.75 min/month, plus ~6 min/month of ongoing help (mount, Wi-Fi, laptop
    asleep, "it didn't see it"), ~10 min/month at a fully loaded $18/h = $3.00. Assumes
    family self-serve, good in-app diagnostics (§5, item 8) and no phone-support SLA.
  - `S = 8.00` (heavy): ~25 min/month at $19.20/h loaded: agency onboarding, a monthly
    check-in call, certificate/laptop incidents on the rig. COMMERCIAL §6 calls support
    "the dominant cost in elder-care products [B]"; the round-B cost agent calls `s`
    "UNVERIFIED, UNBOUNDED". Nothing in this file bounds `S`; only a pilot measures it.

### 3.2 Margin sensitivity at $5 / $10 / $15

Each cell is `(P − fee − A − 0.75 − S − W) / P`. Worked rows for P=10, S=3:
rig `10 − 0.59 − 0 − 0.75 − 3 = 5.66 → 56.60 %`; hosted (v1.2) `10 − 0.59 − 0.72 − 0.75 −
3 = 4.94 → 49.40 %` (v1 at A=0.50: 5.16 → 51.60 %); hosted + $1/$5 chat (v1.2) `10 − 0.59
− 2.07 − 0.75 − 3 = 3.59 → 35.90 %` (v1 at A=1.85: 3.81 → 38.10 %).

*v1.2 (CP4): the four hosted/chat rows below are recomputed at `A_b = 0.72`; the worst
row (1.10) is unchanged. The v1 rows at `A_b = 0.50` are reproduced in §9.6 and stand
within $0.05 at a 30-day retention default.*

| Variant (A, W) | P=$5 S=3 | P=$10 S=3 | P=$15 S=3 | P=$5 S=8 | P=$10 S=8 | P=$15 S=8 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| (a) Rig, BYOD (A=0, W=0) | 16.10 % | **56.60 %** | **70.10 %** | −83.90 % | 6.60 % | 36.77 % |
| (a) Rig, bundled mount (A=0, W=1.0417) | −4.73 % | 46.18 % | 63.16 % | −104.73 % | −3.82 % | 29.82 % |
| (b) Hosted (A=0.72, v1.2) | 1.70 % | **49.40 %** | **65.30 %** | −98.30 % | −0.60 % | 31.97 % |
| (b) Hosted worst (A=1.10) = handoff A1.10 | −5.90 % | 45.60 % | 62.77 % | −105.90 % | −4.40 % | 29.43 % |
| (c) + chat cheap tier (A=0.855, v1.2) | −1.00 % | 48.05 % | 64.40 % | −101.00 % | −1.95 % | 31.07 % |
| (c) + chat $1/$5 tier (A=2.07, v1.2) | −25.30 % | 35.90 % | 56.30 % | −125.30 % | −14.10 % | 22.97 % |
| (c) + chat $2/$10 tier (A=3.42, v1.2) | −52.30 % | 22.40 % | 47.30 % | −152.30 % | −27.60 % | 13.97 % |

Break-even price `P* = (0.30 + A + 0.75 + S + W) / 0.971` and the price at which margin
reaches 40 % (`P = (0.30 + A + 0.75 + S + W) / (1 − 0.029 − 0.40)`; 40 % is a
consumer-subscription rule of thumb [A] leaving room for acquisition cost and churn, not a
target the user has set):

| Variant | P* break-even, S=3 | P* S=8 | P at 40 % margin, S=3 | P at 40 %, S=8 |
| --- | ---: | ---: | ---: | ---: |
| (a) Rig, BYOD | $4.17 | $9.32 | **$7.09** | $15.85 |
| (a) Rig, bundled mount | $5.24 | $10.39 | $8.92 | $17.67 |
| (b) Hosted (v1.2, A=0.72) | $4.91 | $10.06 | **$8.35** | $17.11 |
| (b) Hosted worst | $5.30 | $10.45 | $9.02 | $17.78 |
| (c) + chat cheap tier (v1.2) | $5.05 | $10.20 | $8.59 | $17.35 |
| (c) + chat $1/$5 tier (v1.2) | $6.30 | $11.45 | $10.72 | $19.47 |
| (c) + chat $2/$10 tier (v1.2) | $7.69 | $12.84 | $13.08 | $21.84 |

(v1 values at `A_b = 0.50`: hosted $4.69 / $9.84 / $7.97 / $16.73; cheap chat $4.82 /
$9.97 / $8.20 / $16.96; $1/$5 $6.08 / $11.23 / $10.33 / $19.09; $2/$10 $7.47 / $12.62 /
$12.70 / $21.45. Each v1.2 break-even price is the v1 price + 0.22 / 0.971 = +$0.23 and
each 40 %-margin price + 0.22 / 0.571 = +$0.39, §9.6.)

Readings (sensitivity, not forecasts):

1. **$5 is not viable in any variant** once support is counted: best case (rig, BYOD,
   S=3) leaves $0.81 per user-month; any support load above ~$3.80 loses money.
2. **$10 works only if support stays near $3/user-month.** Rig and hosted-without-chat
   sit at 52–57 %; at S=8 all variants are within ±7 % of zero.
3. **$15 keeps at least 24 % at S=8 in every variant except the $2/$10 chat tier**
   (15.43 %), the only configuration where a cloud line, not support, decides the outcome.
4. The difference between rig and hosted is $0.50/user-month (5 points at $10). Hosting
   is not what makes or breaks this product; support and the chat tier are.

*v1.2 (CP4) addendum to the readings:* with `A_b = 0.72` the hosted rows lose 2.2 points
at $10 (49.40 % at S=3; −0.60 % at S=8) and the rig–hosted gap becomes $0.72 (7 points at
$10); at $15/S=8 the $1/$5 chat tier drops to 22.97 % and the $2/$10 tier to 13.97 %.
Readings 1–4 stand with those numbers: support and the chat tier still decide the
outcome, and the one new way a cloud line could decide it is an **uncapped** CP4
re-observation/promotion design, which would cost more than the subscription (§9.6).

### 3.3 Break-even users against a fixed monthly base

Here `H` is removed from the per-user cost (it is the allocation of the fixed base), and
the fixed base `F` is paid from contribution: `N = ceil(F / (P − fee − A − S − W))`.

Fixed bases [A], stated so they can be replaced:

- `F_lean = $150/month`: control-plane VM for sign-in/updates/licence $15; domain and DNS
  $2; transactional email $10; uptime/error monitoring $10; off-site backups $5; business
  insurance (product + cyber, a small-company token line) $100; Stripe dashboard/accounting
  $0; no payroll. (Apple Developer Program $99/yr is excluded; the rig is a browser app.)
- `F_founder = $4,150/month`: `F_lean` plus one founder draw of $4,000.

| Variant | P | S | Contribution/user | Users for F=150 | Users for F=4,150 |
| --- | ---: | ---: | ---: | ---: | ---: |
| (a) Rig, BYOD | 5 | 3 | 1.5550 | 97 | 2,669 |
| (a) Rig, BYOD | 10 | 3 | 6.4100 | **24** | **648** |
| (a) Rig, BYOD | 15 | 3 | 11.2650 | 14 | 369 |
| (a) Rig, BYOD | 5 | 8 | −3.4450 | never | never |
| (a) Rig, BYOD | 10 | 8 | 1.4100 | 107 | 2,944 |
| (a) Rig, BYOD | 15 | 8 | 6.2650 | 24 | 663 |
| (b) Hosted (A=0.72, v1.2) | 5 | 3 | 0.8350 | 180 | 4,971 |
| (b) Hosted (v1.2) | 10 | 3 | 5.6900 | **27** | **730** |
| (b) Hosted (v1.2) | 15 | 3 | 10.5450 | 15 | 394 |
| (b) Hosted (v1.2) | 10 | 8 | 0.6900 | 218 | 6,015 |
| (b) Hosted (v1.2) | 15 | 8 | 5.5450 | 28 | 749 |
| (c) + chat $1/$5 (A=2.07, v1.2) | 10 | 3 | 4.3400 | 35 | 957 |
| (c) + chat $1/$5 (v1.2) | 15 | 3 | 9.1950 | 17 | 452 |
| (c) + chat $1/$5 (v1.2) | 10 | 8 | −0.6600 | never | never |
| (c) + chat $1/$5 (v1.2) | 15 | 8 | 4.1950 | 36 | 990 |
| (c) + chat $2/$10 (A=3.42, v1.2) | 10 | 3 | 2.9900 | 51 | 1,388 |
| (c) + chat $2/$10 (v1.2) | 15 | 3 | 7.8450 | 20 | 529 |
| (c) + chat $2/$10 (v1.2) | 15 | 8 | 2.8450 | 53 | 1,459 |

(Rows with bundled-mount `W` and the cheap chat tier are printed by Appendix A; they
move each count by a few users and do not change the picture. *v1.2:* the hosted and
chat rows above are recomputed at `A_b = 0.72` by Appendix C §C.8; the v1 counts at
`A_b = 0.50` were hosted 143 / 3,934, **26 / 703**, 14 / 386, 165 / 4,561, 27 / 720;
$1/$5 chat 33 / 911, 16 / 441, never, 34 / 940; $2/$10 chat 47 / 1,293, 19 / 515,
49 / 1,354. The rows that work (P=10–15, S=3) move by 1–4 households at F=150 and by
8–95 at F=4,150; the rows near zero contribution (P=10/S=8) move more because the
divisor is small, which changes nothing about their reading.)

Reading: covering infrastructure alone takes a few dozen households at $10–15; covering
one founder's draw takes 400–900 households at $10–15 with lean support, and is
unreachable at $10 if support runs at $8. At 648–703 households the hosted variant needs
7–8 VMs at 100 users/VM; the rig needs 648–703 always-on home laptops kept healthy, which is
where the `S=3` assumption will be tested. (*v1.2:* 648–730 households and 7–8 VMs; the
VMs now need 80 GB of disk each rather than 30, §9.5.)

### 3.4 Channel note: app-store billing

Not in scope and not in the formula (handoff: "No app-store fee included"). If a native
app ever bills through IAP, replace `0.029 × P + 0.30` with `0.15 × P` (Small Business
Program, < $1M/yr [Q-UNVERIFIED] https://developer.apple.com/app-store/small-business-program/)
or `0.30 × P`. At P=10 that is $1.50 or $3.00 instead of $0.59: −9 or −24 margin points.

---

## 4. Hardware: one-time costs, and bundle / finance / BYOD

All retail figures **[Q-UNVERIFIED]** (search on 2026-10-08 returned listings only; prices
not read). Ranges are deliberately wide.

| Item | Retail (one-time) | / 24 months | Source to verify |
| --- | ---: | ---: | --- |
| Chest-mount harness with phone clamp (generic; Neewer GP18 / Ulanzi CM028 class) | $15 … $35 | 0.63 … 1.46 | https://www.amazon.com/s?k=phone+chest+mount ; https://uk.neewer.com/products/neewer-gp18-chest-mount-harness-for-action-camera-phone-66605595 ; Walmart "chest mount" category https://www.walmart.com/c/kp/chest-mount |
| Neck lanyard / pendant phone holder (lighter, lower camera, more sway) | $8 … $15 | 0.33 … 0.63 | same searches |
| Table stand (the original propped-phone rig, not wearable) | $10 … $20 | 0.42 … 0.83 | same |
| Spare USB-C/Lightning cable + 20 W charger | $10 … $20 | 0.42 … 0.83 | same |
| 10,000 mAh power bank (screen-on capture drains a phone; **battery draw unmeasured**, D-011) | $20 … $30 | 0.83 … 1.25 | same |
| **Mount kit as costed in §2 (`W`)** | **$25** | **1.0417** | [A] mid-range harness only |
| Mount kit, full (harness + cable + power bank) | ~$60 | 2.5000 | [A] |
| Dedicated phone, refurbished iPhone 12/13 class | $200 … $350 | 8.33 … 14.58 | https://www.backmarket.com/ ; https://www.apple.com/shop/refurbished/iphone |
| Dedicated phone, new iPhone 16e | $599 | 24.96 | https://www.apple.com/shop/buy-iphone/iphone-16e |
| Home server instead of the family laptop (N100-class mini PC) | $150 … $250 | 6.25 … 10.42 | general retail; only if the rig variant is productised |
| Glasses, Meta "Audio" tier | $349 | 14.54 | **Coordinator-supplied from the project's research notes.** Not located in `docs/` on 2026-10-08 (a grep for 349, 449, 799 and Ray-Ban finds only a 2024 Meta news link in `review/MEMORY.md`); not re-verified. Search-result titles on 2026-10-08 (e.g. https://www.techspot.com/news/109524-meta-unveils-ray-ban-meta-gen-2-oakley.html , https://idevice.com/smart-glasses/meta-ray-ban/roadmap/gen-2?view=price) suggest the 2025 lineup was Gen 2 $379 / Oakley Vanguard $499 / Display $799; reconcile before use. https://www.meta.com/ai-glasses/ |
| Glasses, Meta "Gen 3" tier | $449 | 18.71 | same note |
| Glasses, Meta "Display" tier | $799 | 33.29 | same note |

Decision table (P is the monthly price; 24-month tenure [A]):

| Hardware | Bundle into P? | Finance separately? | BYOD? | Finance view |
| --- | --- | --- | --- | --- |
| Mount kit ($25–60) | Possible: adds $1.04–2.50/user-month; at P=10/S=3 it costs 10 margin points (56.6 % → 46.2 %) | Not worth the paperwork | Yes, with a recommended SKU list | **Charge it once as a setup fee at cost ($29–69) or ship with the first month**; do not bury $60 of hardware in a $10 price |
| Dedicated phone ($200–599) | No: $8–25/user-month exceeds every tested P | Only via a third party (carrier/Apple financing); we must not carry the receivable | **Yes, default**: the user's or the family's spare iPhone | BYOD; a refurbished-phone offer at cost for households without one, paid upfront |
| Home mini PC ($150–250) | No ($6–10/user-month) | No | The family laptop (rig as built) | If the rig is the long-term product this becomes a hosted-vs-mini-PC decision; hosted costs $0.50/user-month, the mini PC $6–10 amortised plus the same support |
| Glasses ($349–799) | **No**: $14.54–33.29/user-month, each larger than P=15 alone | Meta's own financing or the buyer's card; never on our books | **Yes, the only option**: glasses are the customer's device | Glasses change the capture coverage story, not the subscription economics; a glasses-only tier would need P ≥ $20–25 to carry even partial subsidy, which D-010 does not contemplate |

---

## 5. Cost drivers CP2–CP5 can move, and proposed per-user caps

All caps are **proposals for the coordinator** (`BUILD_PLAN.md` §0 step 2: "Finance states
the cost constraints the checkpoint must respect"). Each names the owner, the checkpoint,
the dollar reason and what existing code already enforces. Caps must degrade to the
`budget_wait` / coverage-loss semantics already in the contract: queue or report, never
drop silently, never stop memory workers, never cut off human support with a code budget
(handoff §10).

| # | Driver | Owner / CP | Proposed cap (per household unless stated) | Rationale (numbers from §2) |
| --- | --- | --- | --- | --- |
| 1 | **Cloud chat spend** | B (CP2 `as_of` chat plumbing; the real provider is "a separate bounded-cost checkpoint" per the contract) | **Hard cap $1.50 per household per UTC calendar month**, integer micro-USD ledger; **≤ 20 calls/day**; per-call bounds `max_input_tokens = 2,000`, `max_output_tokens = 200`, `max_retries = 1`; **no images to the chat provider**; worst-case reservation before egress = `price × bounds × (1 + max_retries)`; cap exhausted → local answer with a visible "cloud chat paused until <date>" state; undefined price or model → fail closed | $1.50 holds the full 20/day policy at any tier ≤ $1/$5 (1.35 + 31-day drift = 1.395) and the cheap tiers with retries (0.27–0.99). At the $2/$10 tier the policy costs 2.70: the cap would stop chat around day 16, so **either the default tier is ≤ $1/$5 or the policy drops to ≤ 10 calls/day** (open question 1). With the cap, (c) can never cost more than (b) + $1.50, which keeps P=10/S=3 at ≥ 36.6 % (10 − 0.59 − 2.00 − 0.75 − 3 = 3.66) |
| 2 | **Episodes per day** | A (controller), B (ingest), C (queue) | Soft cap **100/day** (2× the design value) → backpressure with `coverage_loss` counted; hard cap **200/day** → packets held locally and reported, never deleted | Hosted compute scales linearly: 200/day at 1 s = 200 s/day = 1.67 vCPU-h/month (4× §2.2) and 80 MB/day storage. A runaway controller (B-01/B-03 failure modes, a hand in frame for an hour) must not quadruple cost silently |
| 3 | **Bytes per episode and per day** | C (keyframe selection), A (packet schema) | Keep `MAX_PACKET_BYTES = 4 MiB` as the absolute; add **median packet target ≤ 500 KB** (8 keyframes × ~50 KB + burst) and a **durable upload soft cap of 50 MB/day, hard 150 MB/day** | 20 MB/day is the spec's estimate; 4 MiB × 50 = 200 MB/day is what the cap alone allows (10× the estimate: 18 GB at 90 days = $0.41/month S3 storage instead of $0.04, and 10× the snapshot line). The target and daily cap keep the §2 storage line true |
| 4 | **Object-store write pattern** | B (CP4 storage adapter) | **One object per episode packet; idle keyframes bundled hourly** (or kept on block storage); never one object per keyframe | Per-keyframe PUTs cost $0.49/user-month vs $0.011 batched (§2.2): the single largest avoidable hosted line, larger than the whole VM share ($0.33) |
| 5 | **Idle keyframes** | C (CP4 `POST /api/idle`), B | ≤ 1 per 30 s (**≤ 2,880/day**), analysis resolution, **≤ 25 KB each**, 24 h cache **≤ 200 MB**, dropped at 24 h unless promoted by rule 13 | 2,880 × 25 KB = 72 MB/day worst case within a 200 MB cache; per-request charges are the risk (driver 4), not bytes |
| 6 | **Durable storage per household** | B/A (CP4 retention windows, `consent_version`) | **≤ 2 GB durable evidence** (≈ 90 days at 20 MB/day plus promoted idle frames); retention default **90 days** with 30 days as the lean option; expiry is logical erasure per B-07 (tombstones; replay must not resurrect) | 90-day steady state is $0.04 (S3) to $0.01 (B2); storage is cheap, **unbounded growth with tenure is not** (COMMERCIAL §6: "growing with tenure"). 2 GB × $0.023 = $0.046 ceiling per household |
| 7 | **On-demand re-observation** | A (CP4 rule 13) | **≤ 40 idle keyframes scanned per query, ≤ 2 s CPU per query**, most recent first, stop at first confident hit | This is 0.67 vCPU-h/month at 20 queries/day, already the biggest compute line (§2.2); an unbounded scan of the 24 h cache (2,880 frames × 0.1 s = 288 s) per query would be 72× that |
| 8 | **Photo serves / egress** | B (`GET /api/items/{id}/image`, `no-store`) | **≤ 100 image serves/day per household**, each ≤ 150 KB; count them in the frame counters (CP5) | 0.08 GB/month today; `no-store` (correct for privacy) means every caregiver scroll is a serve. The cap is 15 MB/day = 0.45 GB/month = $0.04 at AWS rates; it exists to make a runaway browser loop visible, not to save money |
| 9 | **Support load** (not a code cap) | C (UI states), B (`/api/health`), Tester (smoke) | Ship the self-serve diagnostics the contract already requires: truthful `manual / automatic / unavailable` camera states, coverage-gap counters, health `models[]`, a "laptop asleep / certificate expired / phone not on home Wi-Fi" explanation page | Every 1 minute/user-month of support avoided is worth ~$0.30 (at $18/h), i.e. 3 margin points at P=10. `S` is the decisive variable in §3; the only lever CP2–CP5 has on it is making failures self-explanatory |
| 10 | **Monetary accounting** | A (ledger), B | Integer micro-USD; UTC calendar month windows; reservation before egress; `fail()` keeps the reservation until the provider confirms no charge (round-B cost agent §4.3); receipts/idempotency keys | Required by handoff §10; a float ledger and a refund-on-failure rule can both under-count real spend against cap 1 |

Caps 2–8 cost nothing on the rig but keep the rig's episode/packet accounting identical to
the hosted variant, so a later move to hosting does not change the browser or the
controller (`BUILD_PLAN.md` CP5 frame counters are the measurement hook).

*v1.1 addendum (CP3, 2026-10-09): no cap changes.* The identity stage adds no cloud call
and no object-store write, and every quantity it adds is already bounded by a cap above or
by an interface parameter the architect fixed (§8.5 shows the arithmetic):

- **Compute** rides on cap 2. Under the hard cap of 200 episodes/day, 4 crops × 150 ms is
  at most 120 CPU-s/day = 1.0 vCPU-h/user-month, the same order as the whole v1 compute
  line; at the design value of 50/day it is 0.05–0.25 vCPU-h ($0.001–0.005 at AWS rates).
- **Embedding storage** rides on cap 6. One 384-float32 vector (1,536 B; ~1.7 KB as a
  row) per observation is 0.43 % of the ~400 KB of keyframes an episode already stores;
  cap 6's "≤ 2 GB durable evidence" is read as **including** the `embeddings` table and
  the bank copies, with the **same retention window and tombstone/erasure semantics as the
  observation the vector belongs to** (B-07): a tombstoned observation's vector must not
  survive it in a bank. This is a reading of cap 6, not a new cap.
- **Banks** are bounded by the architect's `ItemBank` cap of 32 vectors (48 KiB per item)
  [D], which is the right place for that bound; no finance cap is added over it.
- **Cap 7** (re-observation, CP4) assumed 0.1 s per 224 px DINOv2 compare; the CP3
  assumption range (60–150 ms) brackets that, and the "≤ 2 s CPU per query" bound governs
  either way. **Forward flag for CP4, not a CP3 change:** if CP4 adopts the MEMORY
  review's arrival-time indexing of every idle frame at 518 px, that is 2,880 frames/day ×
  0.24–0.9 s ≈ 5.8–21.6 vCPU-h/user-month, 5–20× the entire v1 compute line, and 100
  users/VM becomes 16–53 (§8.5). CP4 must carry its own cap for it (index at 224 px, or
  only on scene change, or lazily within cap 7's 2 s) before Finance accepts it.

*v1.2 addendum (CP4, 2026-10-09): caps 5, 6 and 7 change; cap 3 gains a note; cap 4 is
now load-bearing.* The arithmetic is §9; the proposals in full are §9.4. In brief:

- **Cap 5 (idle keyframes), adjusted to the plan's numbers:** ≤ 1 per 30 s, ≤ 2,880/day,
  target ≤ 64 KiB (capture resolution, JPEG q0.5; replaces v1's 25 KB), body cap 256 KiB,
  cache ≤ 200 MiB, 24 h TTL. At the target the **count cap binds** (2,880 × 64 KiB =
  180 MiB < 200 MiB); the byte cap binds once the mean frame exceeds 71.1 KiB and then
  shortens idle coverage (16.6 h at 103 KiB, 6.7 h at the 256 KiB body cap). Add: the
  hours of idle coverage the cache holds and an `idle_oversize` counter are reported, so a
  byte-bound cache is visible coverage, never silent.
- **Cap 6 (durable storage), adjusted:** the 2 GB figure assumed 20 MB/day of raw
  keyframes; packets are stored as received (base64, burst, landmarks), ≈ 39 MB/day
  typical, so 90 days needs ≈ 3.0 GB typical and 5.5 GB at high packet sizes. Proposal:
  **≤ 2 GiB per household with a 30-day default** (Finance's cost-only preference; the
  privacy agent owns the final retention call), or ≤ 4 GiB if 90 days is chosen; in both
  cases promoted idle frames and their observation/embedding rows are **inside** the cap
  and **follow `episodes_days`** (the plan's "never expires" would otherwise be an
  unbounded line: 6.9 GB/year at 10 % promotion); superseded accepted revisions have
  their packet bytes NULLed at the 72 h pass (digest columns kept), so the 8-revision
  limit cannot multiply a packet by 8.
- **Cap 7 (re-observation), replaced:** v1 assumed a query-time scan (≤ 40 frames,
  ≤ 2 s per query); CP4 is arrival-time, every placed item × every idle frame. As written,
  a static scene with 30 items at 24 h of camera-on is 86,400 pairs/day and, with an
  embed on each `present` candidate, **115 vCPU-h/user-month ($2.40 at AWS rates), more
  than the whole subscription margin**. New cap 7: (a) `limit=16` per worker pass
  (confirmed; bounds a pass to ≤ 2.7 s at 150 ms embeds); (b) a frame-level gate: an idle
  frame unchanged against the previous processed idle frame of the same device inherits
  its results (one blur-diff per frame, 0.5–2 ms); (c) promotion, observation row and
  embed **at most once per item per hour**; diff-only decisions on changed frames are
  unlimited within (d); (d) **≤ 300 CPU-s per household-day** of re-observation time
  (2.5 vCPU-h/user-month, 0.35 % of a core), measured by the worker; beyond it frames stay
  unprocessed, are counted (`reobs_deferred`) and expire as coverage, never silently as
  evidence. Under (b)–(d) the same worst household costs ≈ 1.7 vCPU-h ($0.035).
- **Cap 3 note:** the "median packet target ≤ 500 KB" was raw keyframe bytes; as stored,
  a typical automatic packet is ≈ 786 KB (654 KB after the 72 h reduction) and the
  daily soft/hard caps (50 / 150 MB) should count stored bytes **including revisions**.
- **Cap 4** (one object per packet, idle frames never per-object) now carries the
  worst-case table: `A_b = 1.10` covers the capped CP4 worst (0.9352) only with batched
  objects; per-frame idle uploads alone would add $0.16–0.47/user-month (§9.3).

---

## 6. What must be measured before any margin claim, and the riskiest assumptions

Nothing in §2–3 is a measurement. The research log (B-17, C-10) and the handoff forbid a
margin claim until the following exist, each on the stated configuration:

| # | Measurement | Where it comes from | Replaces |
| --- | --- | --- | --- |
| 1 | Episodes/day, bytes/episode, keyframe bytes at capture resolution, idle keyframe bytes, over whole days on the rig | P-105 frame counters (CP5), then the user's iPhone runs (P-101/P-103) | 50/day, 20 MB/day, 100 KB photo, 150 MB cache |
| 2 | Localizer ms and DINOv2 ViT-S/14 ms per episode **on the server class actually used** (a t3.medium is not the dev laptop); p50/p95 under 100 concurrent households | CP3 identity stage on synthetic crops, then a load test | 0.3–1.0 s/episode; 100 users/VM; 25 % utilisation |
| 3 | Re-observation frames scanned per query and ms per frame | CP4 rule 13 | 40 frames × 0.1 s |
| 4 | Chat tokens per call **including** the system prompt and the ledger context actually sent (the 2026-09-19 measurement showed the prompt and schema were most of the 1,132 tokens, not the content), retries and provider error rates | the separate bounded-cost provider checkpoint | 1,500 in / 150 out, 1 retry |
| 5 | Photo serves per household-day, caregiver browsing pattern | CP5 counters | 800/month |
| 6 | **Support minutes per household-month** and onboarding minutes per household, by channel (family vs agency), on the rig and hosted | the pilot (v4 "Pilot criteria"), ticket log | S = 3 / 8 |
| 7 | Tenure / monthly churn | pilot and first paying cohort | 24-month hardware amortisation; 12-month onboarding amortisation |
| 8 | Payment mix: international cards, failed payments, disputes, Billing add-on | first Stripe statements | 2.9 % + $0.30 |
| 9 | Every `[Q-UNVERIFIED]` list price re-read at its URL by a human, with date | this file's next revision | all of §2.2–2.3, §4 |
| 10 | Rig-specific: laptop uptime, certificate incidents, Wi-Fi/LAN changes, Safari background gaps per household-month | pilot | the "S is not lower on the rig" claim |

Riskiest assumptions, in order of how much they move the answer:

1. **Support `S`.** It is the only line that can make $10 negative in every variant, it is
   unmeasured, and no code can bound it. A heavy-touch elder-care channel (agency
   onboarding, monthly check-ins) is the S=8 column.
2. **The cloud chat tier and policy.** 20/day at $2/$10 costs $2.70 — more than hosting,
   storage and egress together; one retry doubles it. Cap 1 bounds it only if adopted.
3. **Episodes/day and bytes/day** (50; 20 MB). Both are spec estimates with "measure"
   written next to them; a hand-busy heuristic that fires 4× too often quadruples compute
   and storage before anyone notices unless caps 2–3 exist.
4. **Tenure.** 24 months for hardware, 12 for onboarding; elder-care churn can halve both
   and double `W` and the onboarding share of `S`.
5. **100 users per 2-vCPU VM at 25 % utilisation.** Chosen for a 3× safety factor; a
   measured p95 could justify 300 (cutting the VM line to $0.11) or force 30 (raising it
   to $1.09).
6. **Prices.** Every external price is unverified in session; the Anthropic rates are the
   only ones with an in-repo date and URL (2026-10-06).
7. **Per-keyframe object writes.** A natural implementation choice that costs $0.49/user-
   month; invisible in a storage-only estimate.

---

## 7. Bottom line

Under these assumptions the product's direct cost is small and the cloud is not the
problem: hosting adds about $0.50 per user-month over the zero-cloud rig (AWS; ~$0.16 on
a Hetzner/Backblaze stack), and storage, requests and egress together are under $0.20 if
episode packets are written as single objects. What decides the margin is support (`S`)
and, in variant (c), the chat tier. **$5 is not viable in any variant** once support is
counted (best case +16 %, and negative at S=8 or with a bundled mount). **$10 is viable
for the rig and for hosted-without-chat only if support stays near $3/user-month**
(56.6 % and 51.6 %); at S=8 every variant is within a few points of zero. **$15 is the
first price that keeps a working margin (≥ 24 %) under heavy support in all variants**
except hosted plus a $2/$10 chat tier (15 %). The minimum viable price at a 40 % margin with lean support is about $7.10
(rig, BYOD) to $8.00 (hosted), rounding to **$10 as the lowest of the three tested points
that works**, with cloud chat either capped at $1.50/household-month on a ≤ $1/$5 tier or
left off. None of this is a measured margin: it depends on 50 episodes/day, 20 MB/day,
unverified list prices and an unmeasured support load, and must be recomputed from the
CP5 counters and a pilot ticket log before anyone quotes it.

*v1.1 (CP3): the bottom line does not move.* The identity stage changes the hosted metered
cost by at most +$0.013/user-month even when its compute is counted on top of the v1
budget it actually sits inside (§8.3): at P=10/S=3 the hosted margin is 51.50–51.61 %
instead of 51.60 %, and no break-even price or user count in §3 changes by more than one
cent or one household. The one CP3 number that could matter is conditional: if conformal
calibration ever has to be done **per household** rather than once on CUTE plus pilot
footage, it is a support cost of $1.20–1.60/user-month (12–16 margin points at P=10;
§8.4), which is why open question 9 exists.

*v1.2 (CP4): the bottom line moves by two points, and one new line could move it by
thirty.* At the plan's 90-day retention default the expected hosted metered cost rises
from $0.50 to **$0.72** per user-month (AWS; $0.30 on the Hetzner/B2 stack): +$0.085 is
the stored-packet correction surfaced by the retention arithmetic (base64 keyframes,
burst and landmarks: ≈ 39 MB/day, not 20; its object bytes and snapshot share), +$0.040
the larger VM disk (80 GB instead of 30), +$0.057 the SQLite-resident idle cache,
promoted frames and rows with their snapshot, and +$0.038 the net re-observation budget
of 2.5 vCPU-h (§9.6). Hosted at $10/S=3 is 49.4 % instead of 51.6 %; every
hosted break-even price moves by +$0.23; **$5, $10 and $15 keep exactly the readings of
§3**. Retention is now a $0.18/user-month lever (30 vs 90 days), not $0.03, which is why
Finance's cost-only proposal is a 30-day default (§9.4) while the privacy agent owns the
call. The number that is not small is conditional: **the re-observation and promotion
rules as written in the plan, uncapped, would cost 115 vCPU-h and ~42 GB per household
in a static 30-item home with 24 h of camera** ($8.28/user-month at AWS rates, a −31 %
margin at $10/S=3), so the §9.4 caps are a condition of CP4 acceptance for Finance, not
a saving.

---

## 8. CP3 delta: the identity stage (v1.1, 2026-10-09)

What CP3 adds (`BUILD_PLAN.md` "CP3 in detail: identity"): a DINOv2 ViT-S/14 embedding
(ONNX Runtime, CPU) of the localized crop(s) of each episode, one 384-float32 vector
stored per observation in a new `embeddings` table, per-item banks capped at 32 vectors,
and a conformal matcher (a max-cosine over ≤ 32 vectors per candidate item: negligible).
No cloud call, no object-store write, no new upload bytes: in the rig everything runs on
the household laptop; in the hosted variant on the VM that already runs the localizer.
Projection rebuilds replay stored vectors and never re-embed (architect's open decision
5), so rebuilds cost no DINOv2 time.

Inputs specific to this section:

| Parameter | Value | Label and source |
| --- | --- | --- |
| Crops embedded per episode | 2 … 4 at 224 px | [D] `MEMORY_SYSTEM_V4.md` Part 1 tier table "2 to 4 crops at 224 px"; coordinator's CP3 brief |
| CPU time per 224 px crop, modern x86 core, ONNX Runtime fp32 | **60 … 150 ms** | **[A] coordinator's assumed range; no public CPU benchmark was fetchable (header note).** Bounded by the FLOP arithmetic below |
| Pessimistic per-crop time (burstable or shared vCPU) | 300 ms | [A] a t3 vCPU is one hyperthread, not "a modern core" ([Q-UNVERIFIED] https://aws.amazon.com/ec2/physicalcores/ ; https://aws.amazon.com/ec2/instance-types/t3/ , baseline 20 % per vCPU for t3.medium; not connectable 2026-10-09) |
| Observations embedded per episode | 1 … 2 | [A] one target region; up to two rival regions each with a mask (PERCEPTION review §C). 4/episode shown only as a "stored every crop" contrast |
| Vector | 384 × float32 = **1,536 B** | [D] `MODEL_CARD.md` "384 for ViT-S"; `BUILD_PLAN.md` `embeddings` table "float32 bytes" |
| Row overhead (observation_id text, `embedder name@version`, SQLite record + index) | ~200 B → **~1,736 B/row** | [A] |
| Bank cap | 32 vectors per item = 49,152 B = 48 KiB | [D] architect's `ItemBank` |
| Episodes/day, days, retention, prices | 50; 30; 90 days; v1 rates | as §1–2 (all [A]/[D]/[Q-UNVERIFIED]) |

**Why 60–150 ms is a defensible assumption (arithmetic, not a measurement).** From the
model card's architecture (patch 14, width 384, 21 M params; depth 12 and MLP ratio 4 are
the standard ViT-S values, [A]): at 224 px there are 16 × 16 + 1 = 257 tokens; linear
layers cost 12 · N · D² per layer and attention 2 · N² · D, so one crop is 5.515 GMACs of
linear work + 0.609 GMACs of attention = **6.12 GMACs ≈ 12.2 GFLOP**. Cross-check: the
same formula without the attention term gives 29.40 GMACs at 518 px, against **29.46
GMACs** published for `vit_small_patch14_dinov2` (22.06 M params) in timm's benchmark CSV
(https://raw.githubusercontent.com/huggingface/pytorch-image-models/main/results/benchmark-infer-amp-nchw-pt210-cu121-rtx3090.csv ,
fetched 2026-10-09, SHA-256 `b4fd25732fc610388c92974c00f7de82cd002ea0049c0afb3259de865345ab07`;
that file's timing column is an RTX 3090 GPU number and is **not** used here). At a
sustained 50 / 100 / 200 GFLOP/s of fp32 on one core, 12.2 GFLOP is 245 / 122 / 61 ms:
the assumed 60–150 ms corresponds to 80–200 GFLOP/s, plausible for AVX2/AVX-512 GEMM
kernels on one modern core [A]; the 300 ms pessimistic column is a hyperthread on a
burstable instance. The PERCEPTION review's peer estimate for the same model at 518 px
(4–6× the 224 px cost) was 60–200 ms on a 4-core laptop CPU (the review's own "[B]"
label, i.e. an unmeasured belief), which implies ~10–50 ms per 224 px crop on four cores
or ~40–200 ms of single-core time: the same order as the range assumed here, not a
confirmation of it. **The number that replaces all of this is §6 item 2**, taken on the
dev laptop and on a t3.medium-class VM at CP3 acceptance.

### 8.1 Compute per user-month (hosted variant)

Per-episode DINOv2 time = crops × ms/crop; per month × 1,500 episodes; vCPU-hour prices
from §2.2 (AWS t3.medium $0.0416/h ÷ 2 vCPU = $0.0208; Hetzner €4.50 × 1.08 ÷ 2 ÷ 730 h =
$0.00333; both [Q-UNVERIFIED]):

| Case | s/episode | CPU-s/month | vCPU-h/user-month | $ AWS | $ Hetzner | Localizer headroom under the v1 1.0 s/episode line |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Low: 2 crops × 60 ms | 0.12 | 180 | **0.0500** | 0.0010 | 0.0002 | 0.88 s |
| Mid: 3 crops × 100 ms | 0.30 | 450 | 0.1250 | 0.0026 | 0.0004 | 0.70 s |
| High: 4 crops × 150 ms | 0.60 | 900 | **0.2500** | **0.0052** | 0.0008 | 0.40 s |
| Pessimistic: 4 crops × 300 ms | 1.20 | 1,800 | 0.5000 | 0.0104 | 0.0017 | −0.20 s (exceeds the line on its own) |

Reading: at the assumed range the identity stage is **0.05–0.25 vCPU-h/user-month**,
inside the 0.125–0.4167 vCPU-h "episode write path" line that v1 already carried for
"localizer + DINOv2", so it is not an addition to `A_b`; its dollar value as a share of
the VM is **$0.001–0.005 per user-month** at AWS rates. The capacity check also holds
even if it were additive: v1's high total 1.0833 vCPU-h + 0.25 = 1.333 → 274 users per
2-vCPU VM at 25 % utilisation (219 under a 20 % t3 baseline); + 0.5 pessimistic → 231
(184). The 100-users/VM provisioning stands. Latency is not a user-facing cost: the
packet processor runs after the episode is stored, and a 0.6 s identity step per episode
at 5,000 episodes/day per VM is 3,000 CPU-s/day, ~2 % of two vCPUs.

### 8.2 Storage of embeddings

| Case | Rows/month | MB/month | 90-day steady state | gp3 $0.08/GB | S3 $0.023/GB | Hetzner volume €0.044 × 1.08 | Snapshot $0.05/GB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 observation/episode | 1,500 | 2.60 | 7.8 MB | 0.00062 | 0.00018 | 0.00037 | 0.00039 |
| 2 observations/episode (rival regions) | 3,000 | 5.21 | **15.6 MB** | **0.00125** | 0.00036 | 0.00074 | **0.00078** |
| Every crop stored (4/episode; not the design) | 6,000 | 10.42 | 31.2 MB | 0.00250 | 0.00072 | 0.00148 | 0.00156 |

Formula: rows × 1,736 B; 90-day steady state = 3 months of rows. The table lives in the
SQLite ledger on the VM's block storage (gp3 column; the S3 column is shown only for
contrast), so it adds **no PUT/GET requests** (cap 4 is untouched) and it is covered by
the snapshot line. Bank copies: 48 KiB per item, 480 KiB for the rig's 10-item set, 9.8 MB
at an improbable 200 items, bounded by the 32-vector cap regardless of tenure. Relative
scale: a 1.7 KB row against ~400 KB of keyframes per episode is **0.43 %** of the bytes
the episode already stores. On the rig the same bytes sit on the laptop disk; Oversight's
CP3 condition that no embedding leaves the device holds by construction, so there is no
upload or egress line.

One future driver to name, not cap: an **embedder version change** (`name@version`) would
re-embed the retained set once, 4.5–22.5 CPU-min per household (4,500–9,000 rows × 60–150
ms), 7.5–37.5 CPU-h for 100 households on one VM: a scheduled background job, never
on the query path.

### 8.3 Effect on the hosted per-user cost table (variants b and c)

Strictly additive items are the embedding rows and their snapshot (compute is inside the
v1 line); the two lower rows count the compute on top anyway, to bound the error:

| Case | Added $/user-month | `A_b` (from 0.4972) | P=10, S=3 hosted margin (v1: 51.60 % at `A_b` = 0.50) |
| --- | ---: | ---: | ---: |
| Storage + snapshot only (2 obs/episode) | +0.0023 | 0.4995 | 51.61 % |
| Fully additive, high compute | +0.0075 | 0.5047 | 51.55 % |
| Fully additive, pessimistic compute | +0.0127 | 0.5099 | 51.50 % |

Formula for the margin row: (10 − 0.59 − `A_b` − 0.75 − 3) / 10. The sensitivity tables in
§3 keep **`A_b = 0.50`** (it absorbs the design-consistent +0.0023) and the worst case
**`A_b = 1.10`** covers the pessimistic row with $0.59 to spare. Variant (c) inherits the
same delta on top of its chat line. Every break-even price in §3.2 moves by $0.0131 in
the pessimistic case (ΔP* = ΔA / 0.971). In §3.3 the rows that already work (P=10–15,
S=3) move by at most one household (hosted P=10/S=3: 26 → 26 at F=150, 703 → 704 at
F=4,150); the rows whose contribution is near $1 move more in absolute terms because the
divisor is small (hosted P=5/S=3 founder count 3,934 → 3,982; P=10/S=8: 165 → 168 and
4,561 → 4,625, pessimistic case), which changes nothing about their reading: thousands
of households to cover one founder draw, before and after.

### 8.4 One-time costs: ONNX export and calibration data

All [A]; engineering at a loaded $75/h, support at the v1 heavy rate $19.20/h; dollars for
compute are zero because every step runs on a laptop (BUILD_PLAN: "no export runs in the
sandbox"; the export needs torch at dev time only).

| Item | Estimate | Basis |
| --- | --- | --- |
| ONNX export of `dinov2_vits14` + verification against the PyTorch outputs + hash/commit/script recorded in `LICENSES.md` | **$225–375 once** | 2–4 h engineering + 1 h Oversight review; weights Apache-2.0 (`LICENSES.md` §3, `VERIFIED-COMMERCIAL`) so no licence fee |
| CUTE calibration set | **$375–675 once**; licence **$0** | CC BY 4.0 (`LICENSES.md` §4, `VERIFIED-COMMERCIAL`, attribution required in any report that uses it). 1 h to acquire and record attribution + 4–8 h to run `calibrate`, the held-out coverage check and `approve_calibration`. Embedding the set is ≤ 50 CPU-min on a laptop even at 20,000 images (the exact count is in the dataset record, not re-read here) |
| Own-footage calibration, **global, one-time** (the rig's 10 items × 10 crops, P-104) | **≈ $492 once** | 10 pilot households × ~1 h of support (45 min guided, consented capture + 15 min consent paperwork) at $19.20 + 4 h engineering. The calibration record is one approved product-wide `calibration_id`, not a per-household artefact |
| **Total one-time** | **$1,092–1,542** | amortised over 24 months: $0.46–0.64/user-month at 100 households, $0.07–0.10 at 648 (the founder break-even cohort), $0.05–0.06 at 1,000 |

The conditional case that is not negligible: if P-104 finds that a household's own
objects and lighting shift the nonconformity distribution enough that **per-household
calibration** is required, then each onboarding gains 45–60 min of support, i.e. $14.40–
19.20 once = **$1.20–1.60/user-month over the 12-month tenure assumed in §3.1, which is
12–16 margin points at P=10** and would move `S=3` to ≈ 4.2–4.6. The in-app, self-serve
alternative (the family photographs the item set during setup; no support minutes) costs
nothing on this line, which is the finance reason to prefer it if the question arises.

### 8.5 Caps: conclusion and the bounds that already exist

No cap changes; see the v1.1 addendum in §5 for the reading of caps 2, 6 and 7. The
numbers behind it: cap 2's hard limit (200 episodes/day) bounds CP3 compute at 800 crops ×
0.15 s = 120 CPU-s/day = **1.0 vCPU-h/user-month** for the worst household; the 32-vector
bank cap bounds bank bytes at 48 KiB/item; retention bounds the `embeddings` table at 3
months of rows. The one exposure is not CP3's: a CP4 design that indexes every idle frame
with the same embedder at 518 px would cost 2,880 × (0.24–0.9 s) per day = **5.8–21.6
vCPU-h/user-month**, 5–20× the whole v1 compute line, dropping 100 users/VM to 53–16.
Finance asks that CP4 state its own cap for that before it is built.

### 8.6 The rig (variant a)

Zero company spend, as before. The household pays the electricity: 900 CPU-s/month at the
high case at an incremental ~15 W [A] is ~4 Wh, under $0.001 at $0.17/kWh, against the
$3.06 the always-on laptop already costs. The support-relevant fact is different: the
laptop now needs `onnxruntime` and an ONNX file of roughly 88 MB in fp32 (22.06 M params
× 4 B [A, arithmetic from the timm row; the exported file is not measured]) provisioned
by `scripts/fetch_models.py`; a missing or unprovisioned model is the
"identity stays `provisional`, capability false" state, which the browser must explain
(cap 9), or it becomes a support call.

### 8.7 What replaces these numbers

§6 item 2 already names the measurement (localizer ms and DINOv2 ms per episode on the
server class actually used, p50/p95 under 100 concurrent households). CP3 adds: crops
actually embedded per episode and observations per episode (1 vs 2), rows in
`embeddings` per household-day after a synthetic run, the ONNX file size, and the hours
the export and the CUTE calibration actually took. None of §8 is a measurement.

---

## 9. CP4 delta: idle cache, re-observation and retention (v1.2, 2026-10-09)

What CP4 adds (`BUILD_PLAN.md` "CP4 in detail"): idle keyframes, one capture-resolution
JPEG every 30 s while the camera is on and idle, posted to `POST /api/idle` (target
≤ 64 KiB, body cap 256 KiB), kept in a new SQLite table `idle_frames` as a rolling 24 h
cache capped at 2,880 frames/day and 200 MiB; a worker-side re-observation pass
(`reobserve(limit=16)`) that, for every placed or inferred item and every newer
unprocessed idle frame from the same device, registers the frame to the item's reference
keyframe (the localizer's LK + partial-affine), box-blurs and diffs the item's bbox, and,
with an embedder present, embeds the registered region for `present`; a `present`
promotes the idle frame (never expires) and writes an observation row; retention windows
(`episodes_days` 90, `idle_hours` 24, `landmarks_hours` 72) that NULL packet bytes after
`episodes_days`, hard-delete expired idle frames and rewrite packets older than 72 h with
`landmarks: []` plus a bounded `landmark_summary`; and erasure that ends with `VACUUM
INTO` a fresh file. No cloud call; no new upload path besides the idle post; on the rig
every byte and every millisecond lands on the household laptop.

Inputs specific to this section (every one labelled; nothing here is an on-device
measurement):

| Parameter | Value | Label and source |
| --- | --- | --- |
| Idle frames | ≤ 1 / 30 s, `IDLE_MAX_PER_DAY = 2880`, `IDLE_CACHE_BYTES = 200 MiB`, `IDLE_TTL_MS = 24 h` | [D] BUILD_PLAN CP4 |
| Idle frame bytes | target ≤ 64 KiB (q0.5), `MAX_IDLE_BYTES = 256 KiB` | [D]; a synthetic worst-case-texture 1280×720 frame at q50 was 65 KiB, 1920×1080 103 KiB [M-sandbox]; real room scenes are expected below the target at 720p [A] |
| Capture / analysis resolution | ≤ 1280×720 at JPEG q0.72; analysis ≤ 320 px long side | [M-code] `phone/assets/memory-camera.js` (`scale = min(1, 1280/w, 720/h)`, `analysisScale = 320/...`, `toDataURL('image/jpeg', .72)`) |
| Camera-on hours per day | 8 (worked example); 24 (bound) | [A]; 8 h gives 960 idle frames/day, 24 h the full 2,880 |
| Episodes/day | 50 | [D] as §1 |
| Keyframe raw bytes | 50 KB typical, 100 KB high | [A] v1's 50 KB; the synthetic q72 720p frame was 84 KiB [M-sandbox] |
| Burst frames | ≤ 10 grayscale 320×180 JPEGs, ~8 KB each | [D] `BURST_MAX = 10`; [A] bytes (synthetic 13–18 KiB [M-sandbox]) |
| Landmark samples | ≤ 128 per packet; ≤ 2 hands × 21 image points + 21 world points, 6-decimal floats; typical 75 | [D] `LANDMARK_SAMPLES_MAX = 128`; [M-code] the camera tick is every 100 ms and `MAX_EPISODE_MS = 10000`, so an automatic episode holds ≤ 100; `hand-worker.js` `round6` and world landmarks whenever MediaPipe returns them; [A] 75 = 10 Hz × 7.5 s |
| Packet storage form | the received JSON bytes, verbatim, in `episode_revisions.packet` (base64 JPEGs inside); ≤ 8 revisions per episode, each a full packet | [M-code] `perception/episode_store.py` |
| Tracked items with a placed location | 10 … 30 | [A] coordinator's range |
| Registration + blur per (item × frame) pair | **8.5 ms** incl. both JPEG decodes; 3.6 ms with decodes cached; a frame-level motion-energy check 0.5 ms | [M-sandbox] at 320×180 analysis size, the localizer's own calls (`goodFeaturesToTrack 250`, `calcOpticalFlowPyrLK`, `estimateAffinePartial2D` RANSAC, `warpAffine`) and `motion.box_blur3`; used as **10 ms laptop-class [A], 20 ms burstable-vCPU [A]** |
| DINOv2-S/14 embed per candidate | 50 … 150 ms, 300 ms pessimistic | [A] §8's range; the sandbox core sustains 150 GFLOP/s of fp32 GEMM single-threaded, i.e. ≥ 81 ms for the 12.2 GFLOP crop if the whole model ran at GEMM speed [M-sandbox], consistent with the range |
| Observation row, embedding row | ~1,500 B; 1,736 B | [A] `local_observations.record` JSON; [A] §8.2 |
| Prices | v1 rates: S3 $0.023/GB, gp3 $0.08/GB, snapshot $0.05/GB, PUT $0.005/1k, GET $0.0004/1k, t3.medium $0.0208/vCPU-h; Hetzner volume €0.044 × 1.08, B2 $0.006/GB, $0.00333/vCPU-h | all **[Q-UNVERIFIED]**, re-read attempted and blocked 2026-10-09 (header note) |

### 9.1 Storage per user-day and per user at steady state

#### 9.1.1 The idle cache: which cap binds

| Mean idle frame | 2,880 × bytes per day | vs 200 MiB cap (209,715,200 B) | Frames the byte cap holds | Idle coverage at the byte cap |
| --- | ---: | --- | ---: | ---: |
| 64 KiB (65,536 B) target | 188,743,680 B = **180.0 MiB = 188.7 MB** | **under: the count cap binds** (20 MiB spare) | 3,200 | 26.7 h (> 24 h TTL) |
| 64 KB decimal (64,000 B) | 184,320,000 B = 175.8 MiB = 184.3 MB | under: the count cap binds | 3,276 | 27.3 h |
| 71.1 KiB (72,818 B) | 209,715,200 B | the cross-over: above this mean the byte cap binds | 2,880 | 24.0 h |
| 103 KiB (1080p synthetic) | 303,759,360 B = 289.7 MiB | **byte cap binds** | 1,988 | **16.6 h** |
| 256 KiB body cap | 754,974,720 B = 720.0 MiB | byte cap binds | 800 | **6.7 h** |

So the brief's "2,880 × 64 KB = 184 MB/day > 200 MiB?" is **no**: 184.3 MB (decimal KB) or
188.7 MB (KiB) against 209.7 MB; the count cap is the binding one at the target, with
10–12 % to spare. The byte cap is a guard that only engages when frames come in above
71 KiB, and when it engages it **costs coverage, not money**: the cache then holds fewer
than 24 h of idle frames (16.6 h at 103 KiB; 6.7 h at the body cap), and the plan's
"oldest unpromoted evicted first" rule silently shortens the window inside which a
placement can be re-observed. That is why §9.4 asks for the held coverage (hours) and an
oversize counter to be reported. At the worked example's 8 h of camera-on time the cache
holds 960 × 64 KiB = **60.0 MiB**, far inside both caps. The cache lives in the SQLite
file (`idle_frames.jpeg BLOB`), so on the hosted variant it is block storage (gp3), not
object storage, and it adds no PUT/GET requests (§9.3).

#### 9.1.2 Episode packets as stored, and the 72 h landmark reduction

**Landmark bytes.** The brief's bound is 128 samples × 2 hands × 21 points × 3 floats =
16,128 floats; as compact JSON at six decimals one point is
`{"x":0.847434,"y":0.763775,"z":-0.048986}` = **41 B** (13.7 B per float), so the image
landmarks alone are ≤ 215 KiB. Measured with the real schema classes
(`LandmarkSample`/`Hand`/`ImagePoint`, `json.dumps(..., separators=(",", ":"))`, which is
what `semantic_digest()` and the browser's `JSON.stringify` produce) [M-sandbox]:

| Landmark set | Bytes | Note |
| --- | ---: | --- |
| 128 samples × 2 hands, `world_landmarks` present | **484,864 B = 473.5 KiB** | the hand worker emits world landmarks whenever MediaPipe returns them [M-code], so this is the real worst case; 1,869 B per hand |
| 128 samples × 2 hands, no world landmarks | 258,816 B = 252.8 KiB | 986 B per hand |
| Typical: 75 samples × 1 hand, world present | **143,925 B = 140.6 KiB** | [A] sample count |
| `landmark_summary` after 72 h, worst / typical | 33,280 B / 12,000 B | [A] ~60 B per sample + ~100 B per hand (`hand_bbox` 4 floats, `busy`, `basis`) |

The reduction therefore removes **93.1 % (worst) / 91.7 % (typical) of landmark bytes**:
−452 KB / −132 KB per packet.

**Packet bytes as stored.** `ingest_episode` inserts the received bytes verbatim
(base64 JPEGs inside the JSON), so:

| Packet | Keyframes (8 × raw × 4/3) | Burst (10 × 8 KB × 4/3) | Landmarks | JSON | **Stored** | **After 72 h** |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Typical (50 KB keyframes, 75 samples) | 533.3 KB | 106.7 KB | 143.9 KB | 2 KB | **785.9 KB** | **654.0 KB** |
| High (100 KB keyframes, worst landmarks) | 1,066.7 KB | 106.7 KB | 484.9 KB | 2 KB | 1,660.2 KB | 1,208.6 KB |
| Cap | | | | | 4,194.3 KB (4 MiB) | |

Per day at 50 episodes: **39.3 MB/day typical** (v1 and `MEMORY_SYSTEM_V4.md` said 20
MB/day, counting raw keyframes only), 83.0 MB/day high; the reduction gives back 6.6
MB/day (typical) to 22.6 MB/day (high) once a day-cohort passes 72 h. Two further
multipliers the v1 line did not see: up to **8 revisions per episode, each a full
packet** (a resent superset is a new row; the previous revision's bytes stay), and the
observation rows and embeddings per episode (≈ 6.5 KB, negligible).

#### 9.1.3 Promoted idle frames

A `present` result promotes the idle frame (64 KiB kept, "never expires") and writes one
observation row per (item × frame) `present`, plus an embedding row when the embedder
confirmed it (≈ 3.2 KB per row pair). The brief asks for 0–10 % promotion; the design as
written promotes **every** idle frame in which any placed item is still visible, which in
a quiet home with the items in view is nearly all of them, so a third column is shown:

| Promotion rate | Camera 8 h (960 frames/day) | Camera 24 h (2,880 frames/day) | If promoted frames never expire |
| --- | ---: | ---: | ---: |
| 0 % | 0 | 0 | 0 |
| 10 %, 1 row per frame | 6.3 MB/day frames + 0.3 MB/day rows | 18.9 MB/day + 0.9 MB/day | **6.9 GB/year of frames alone, unbounded with tenure** |
| 100 %, 30 items (design as written, static scene) | 62.9 MB/day frames + 93.2 MB/day rows | 188.7 MB/day + 279.6 MB/day | 171 GB/year, frames + rows |
| **Capped: ≤ 1 promotion per item per hour** (§9.4), 30 items, frames shared (≤ 24/day) | 1.6 MB/day frames + 2.3 MB/day rows | same | n/a: follows `episodes_days` |

At 90-day retention the 10 % case adds 0.59 GB (8 h) to 1.78 GB (24 h); the as-written
case adds 14–42 GB; the capped case 0.35 GB (141.6 MB of frames + 209.7 MB of rows). The
rows, not the frames, dominate the as-written case, because every item in view writes a
row every 30 s: 86,400 rows/day at 30 items and 24 h.

#### 9.1.4 Formula, retention 30 vs 90, and the worked example

Durable bytes per household at steady state, retention `R` days (`R ≥ 3`):

```
D(R) = E × [3 × P_full + (R − 3) × P_reduced]            # packets, landmarks reduced after 72 h
     + E × o × (r_obs + r_emb) × R                         # observation + embedding rows per episode
     + F_p × b_idle × R + F_p × k × (r_obs + r_emb) × R    # promoted idle frames and their rows
C    = min(F × b_idle, 200 MiB)                            # the 24 h idle cache, not retention-scaled
```

with `E` episodes/day, `P_full`/`P_reduced` stored packet bytes before/after 72 h, `o`
observations per episode (2), `r_obs`/`r_emb` row bytes (1,500 / 1,736), `F` idle
frames/day, `F_p` promoted frames/day, `k` rows per promoted frame, `b_idle` 64 KiB.

Worked example, **50 episodes/day, 8 h/day of camera-on time** (F = 960), typical packet
(785.9 → 654.0 KB), promotion capped (F_p = 24, k × F_p = 720 rows/day):

| Component | Per user-day | R = 30 days | R = 90 days |
| --- | ---: | ---: | ---: |
| Packets (after reduction for cohorts > 72 h) | 39.3 MB ingested; 32.7 MB retained | 1.001 GB | **2.963 GB** |
| Observation + embedding rows (episodes) | 0.32 MB | 9.7 MB | 29.1 MB |
| Promoted idle frames (capped) | 1.57 MB | 47.2 MB | 141.6 MB |
| Promoted-frame rows (capped, 30 items) | 2.33 MB | 69.9 MB | 209.7 MB |
| Idle cache (rolling, 24 h) | 60.0 MiB held | 62.9 MB | 62.9 MB |
| **Total per household** | **≈ 43.5 MB/day ingested** | **1.19 GB** | **3.41 GB** |
| Same with high packets (100 KB keyframes, worst landmarks) | 87.2 MB/day | 2.1 GB | 5.9 GB |

Where the bytes live: on the **rig** all of it sits in one SQLite file on the laptop
(§9.5), zero company spend, and the file does not shrink when retention NULLs packet
bytes (SQLite reuses free pages; only `VACUUM INTO` at `erase_profile` rewrites it), so
it plateaus at the steady-state maximum. On the **hosted** variant, v1's model stands:
packets as one object each (S3-class, cap 4), everything else (idle cache, promoted
frames, rows, embeddings) in the per-VM block storage: **0.34 GB (R=30) / 0.59 GB (R=90)
of block storage per household**, idle cache counted at its 200 MiB cap. If the hosted
variant kept packets in SQLite as the rig does, the 2.96 GB would move from $0.023/GB to
$0.08/GB (+$0.17/user-month) and the multi-tenant file would be 355 GB (§9.5), which is
why the storage adapter or per-household files matter.

### 9.2 Compute: re-observation

**Per pair.** Registration (decode both JPEGs, grey, resize to 320×180, 250 corners, LK,
partial affine with RANSAC, warp) plus the blurred bbox diff measured **8.5 ms** on the
sandbox core (3.6 ms when the idle frame and reference decodes are cached across items of
the same frame); the figure used below is **10 ms laptop-class [A], 20 ms on a burstable
vCPU [A]**. The embed runs only on `present` candidates (diff ≤ 0.06), 50–150 ms [A],
300 ms pessimistic. "Tens of ms" for registration + blur is confirmed in order of
magnitude; the embed dominates whenever it runs.

**Worst case per worker pass, `limit=16`:** 16 × 20 ms = **0.32 s** diff-only; 16 ×
(20 + 150) ms = **2.72 s** with embeds; 16 × (20 + 300) ms = 5.12 s pessimistic. That
bounds a pass, which is what keeps the store responsive (passes run in a thread, the
API interleaves). It does **not** bound the day: the worker loop in `server/memory_app.py`
wakes every 1 s [M-code], so `limit=16` is a per-second ceiling of 16 pairs, and the daily
work is simply pairs = items × idle frames:

| Camera, items | Pairs/day | Diff-only (10 ms) | Diff + embed 150 ms on every pair (static scene) | Hosted vCPU-h/user-month (diff / +embed) | $ AWS (diff / +embed) | $ Hetzner |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 h, 10 items | 9,600 | 96 CPU-s/day (0.11 % of a core) | 1,536 CPU-s/day (1.78 %) | 0.8 / 12.8 | 0.017 / 0.266 | 0.003 / 0.043 |
| 8 h, 30 items | 28,800 | 288 (0.33 %) | 4,608 (5.33 %) | 2.4 / 38.4 | 0.050 / **0.799** | 0.008 / 0.128 |
| 24 h, 10 items | 28,800 | 288 (0.33 %) | 4,608 (5.33 %) | 2.4 / 38.4 | 0.050 / 0.799 | 0.008 / 0.128 |
| 24 h, 30 items | 86,400 | 864 (1.00 %) | 13,824 (16.00 %) | 7.2 / **115.2** | 0.150 / **2.396** | 0.024 / 0.383 |

Readings:

- **Diff-only is cheap everywhere**: ≤ 1 % of one core on the laptop, ≤ $0.15/user-month
  hosted even at 24 h and 30 items. The laptop stays idle-capable on diff alone.
- **The embed is not.** As written, a static 30-item scene with the camera on all day
  embeds 86,400 crops/day: 16 % of a core continuously (≈ 5 W more at the wall, ~$0.6/month
  of household electricity [A], and a laptop that never cools), and hosted **115
  vCPU-h/user-month = $2.40 at AWS rates, 100× the whole v1 compute line and more than the
  margin at $10**. This is exactly the exposure §8.5 flagged (arrival-time indexing of
  every idle frame), in a cheaper per-frame form multiplied by the item count.
- **`limit=16` keeps the server responsive, not the laptop idle.** With a continuous
  backlog the worker runs 16 pairs every second until it clears; at 170 ms per pair that
  is a core at 100 % for as long as the backlog lasts, and at 2,880 frames × 30 items a
  day the backlog never clears (it expires at 24 h instead, as coverage).

**Under the §9.4 caps** (frame-level unchanged gate at 2 ms; diff on changed frames,
assumed ≤ 10 % of idle frames [A]; promotion/embed ≤ 1 per item per hour; 300 CPU-s/day
budget), the same 24 h, 30-item household is 5.8 + 86.4 + 108.0 = **200 CPU-s/day = 1.67
vCPU-h/user-month = $0.035** (AWS); the budget's ceiling is **2.5 vCPU-h = $0.052 AWS /
$0.008 Hetzner**, a 0.35 % duty cycle on the laptop. v1's cap-7 line was 0.6667 vCPU-h
for a query-time scan; the budget replaces it, net **+1.83 vCPU-h = +$0.038** at AWS
rates.

### 9.3 Hosted object storage and requests for the idle cache (if it were uploaded)

The brief keeps idle frames on the laptop (rig) or on the server disk (hosted). The
hosted variant must keep it that way: per-frame objects would cost

| Camera | PUTs/month | S3 PUT $ | R2 class A $ | Storage at the 200 MiB cap (S3) | GETs for re-observation (1 per frame) | Total S3 | Batched-objects line for comparison |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 h | 28,800 | 0.1440 | 0.1296 | 0.0048 | 0.0115 | **0.1603** | 0.0111 |
| 24 h | 86,400 | 0.4320 | 0.3888 | 0.0048 | 0.0346 | **0.4714** | 0.0111 |

i.e. **$0.16–0.47/user-month, 14–42× the entire batched request line**, for bytes that
expire in 24 h. The CP2 rule (cap 4: one object per episode packet, idle frames bundled
or on block storage, never one object per keyframe) is reused unchanged and extended:
**idle frames are never written to object storage per frame.** On the VM they are block
storage inside the SQLite file: 0.21 GB × $0.08 = $0.0168/user-month at the cap (v1
carried $0.012 for a 150 MB cache), and $0 of requests. If a hosted design ever needs
idle frames off the VM (for example a snapshot), it is one hourly bundle at most, the
rule v1 already priced at $0.0111.

### 9.4 Caps: confirm or adjust §5 items 5–7, and the retention default

Every cap keeps the contract's semantics: queue or report, never drop silently, never
stop memory workers (handoff §10; `budget_wait` / coverage-loss states).

**Cap 5, idle keyframes: adjusted to the plan's exact numbers, with one addition.**
≤ 1 per 30 s, **≤ 2,880/day** [D, confirmed]; **target ≤ 64 KiB** at capture resolution
(JPEG q0.5) [D; replaces v1's 25 KB, which assumed analysis resolution; the plan chose
capture resolution so a promoted frame can serve as an ordinary observation image, and
the 720p synthetic worst case landed at 65 KiB, so the target is realistic at 720p and
not at 1080p]; body cap 256 KiB [D]; **cache ≤ 200 MiB** [D, confirmed; v1 wrote 200 MB];
24 h TTL [D]. Addition: because the count cap binds at the target and the byte cap only
engages above a 71.1 KiB mean, when it does engage it shortens coverage (§9.1.1), so the
store reports the **hours of idle coverage currently held** and an **`idle_oversize`
counter** (frames above 96 KiB [A]), and the browser steps JPEG quality down one notch
(0.5 → 0.4) when its last idle frame exceeded 96 KiB. Cost of the cache at the cap:
$0.017/user-month (gp3) or $0.010 (Hetzner volume); nothing to save, only coverage to
keep visible.

**Cap 6, durable storage per household: adjusted.** v1's "≤ 2 GB (≈ 90 days at 20
MB/day plus promoted idle frames)" is not achievable by the design at 90 days: as stored,
packets are ≈ 39 MB/day typical and the 90-day set is 2.96 GB typical, 5.5 GB high
(§9.1.2). Proposal:

- **≤ 2 GiB per household at a 30-day `episodes_days` default** (1.19 GB typical, 2.1 GB
  high in §9.1.4, so the high case needs the 72 h reduction and the revision rule below to
  fit), **or ≤ 4 GiB at 90 days** (3.41 GB typical; the high case, 5.9 GB, does not fit,
  which makes cap 3's per-day bytes cap the operative one).
- **Promoted idle frames and their observation/embedding rows are inside the cap and
  follow `episodes_days`** (jpeg → NULL with the same "evidence image expired" state as
  packets). The plan's "promoted = never expires" is an unbounded line otherwise: 6.9
  GB/year at 10 % promotion, 171 GB/year as written.
- **Superseded accepted revisions have their packet bytes NULLed at the 72 h pass**
  (digest columns stay, so B-16's duplicate detection is untouched); otherwise the
  8-revision limit lets one episode hold 8 × 4 MiB.
- Cap 3's daily soft/hard caps (50 / 150 MB) count **stored bytes including revisions**;
  its "median packet target ≤ 500 KB" becomes **≤ 800 KB as stored** (786 KB typical).

**Retention default, from cost alone: 30 days.** Expected difference 30 → 90 days is
**$0.176/user-month at AWS rates ($0.135 on Hetzner/B2)**: 1.8 margin points at $10, the
largest single lever CP4 has after the re-observation caps, and six times v1's $0.03
(which was computed on raw keyframe bytes without the snapshot share). Retention (a) keeps
metadata, digests, observations and embeddings and NULLs only the packet bytes, so what a
30-day default loses is the **evidence photo** for placements older than 30 days ("evidence
image expired"), not the answer; most "where is X" questions concern the last placement,
which is days old, not months. **The privacy agent owns the final call** (G-PRIV
data-class map, `consent_version` semantics); Finance's input is the number above and
the observation that 90 days also doubles the VACUUM headroom and snapshot lines.

**Cap 7, on-demand re-observation: replaced.** v1's "≤ 40 frames per query, ≤ 2 s CPU
per query" assumed a query-time scan; CP4's rule 13 is arrival-time. New cap 7:

- (a) **`limit=16` pairs per worker pass** [D, confirmed]: bounds one pass to ≤ 0.32 s
  diff-only / ≤ 2.72 s with embeds at the assumed rates, which keeps the store and API
  responsive. It is not a rate cap (§9.2).
- (b) **Frame-level gate:** an idle frame whose motion energy against the previously
  processed idle frame of the same device is below the controller's idle threshold
  inherits that frame's per-item results (one `box_blur3` diff per frame, 0.5–2 ms); only
  changed frames go through per-item registration. In a quiet home that removes most
  pairs at no decision cost, because an unchanged frame cannot change `present/gone`.
- (c) **Promotion, observation row and embed at most once per item per hour**
  (`REOBS_PROMOTE_INTERVAL_MS = 3,600,000` [A]; the architect may choose longer: the
  ageing threshold the promotion exists to reset is 24 h, `AGE_STALE_MS` [M-code]).
  Diff-only `present/gone/unknown` decisions on changed frames stay unlimited inside (d),
  so `gone` latency is unaffected.
- (d) **≤ 300 CPU-s of re-observation time per household-day** (2.5 vCPU-h/user-month;
  $0.052 AWS, $0.008 Hetzner; 0.35 % of a laptop core), measured by the worker with the
  same clock the tests inject; beyond it idle frames stay unprocessed, are counted
  (`reobs_deferred`, in `/api/retention` and health) and expire at 24 h as **coverage,
  never silently as evidence**.

With (b)–(d) the worst household (24 h, 30 items, static) is ≈ 1.7 vCPU-h ($0.035) against
115.2 vCPU-h ($2.40) as written; with (a) alone it is unbounded. Finance treats (b)–(d) as
conditions of CP4 acceptance, not optimisations, because without them the hosted variant's
worst case is not 1.10 but 8.78 (§9.6).

*Where the builder's draft already stands (read, not reviewed: `perception/reobservation.py`
is an untracked file in the working tree at `77b769e`, not yet in any commit).* It
already has the **promotion and observation-row half of (c)**: `REOBS_REFRESH_MS = 3600 ×
1000`, a `present` promotes and writes a row the first time after a hand event, on a
state reversal, and otherwise at most hourly. Two things it does not yet have: the
**embed runs on every `present` pair before the refresh check** (the expensive half of
(c) is ungated: the compute table of §9.2 is the draft's behaviour), and the
**`reobservations` table records one row per pair with no retention window** (~120 B
[A] × 86,400 pairs/day in the as-written scene ≈ 10 MB/day, 0.9 GB at 90 days; under the
frame gate (b) it shrinks with the pairs; it should follow `episodes_days` as well).
Neither (b) nor (d) is present.

### 9.5 Erasure: `VACUUM INTO` headroom

`erase_profile` runs `VACUUM INTO` a fresh file and swaps it in, so the disk must hold
**two copies of the database** for the duration:

| Database | Size | Free space needed (2×) | Matters? |
| --- | ---: | ---: | --- |
| Rig, one household, everything in SQLite, R=90 typical, promotion capped | 3.55 GB (5.9 GB high) | 7.1 GB (12 GB) | No: any laptop with a ≥ 128 GB SSD; a 3.5 GB copy on a laptop SSD is tens of seconds [A], once, at erase-all |
| Rig, R=30 | 1.2 GB (2.1 GB high) | 2.4 GB (4.2 GB) | No |
| Hosted, one household's block-storage share (packets in objects) | 0.59 GB (R=90) / 0.34 GB (R=30) | 1.2 GB / 0.7 GB | No, **if each household is its own database file** |
| Hosted, **one multi-tenant file** for 100 households | 59 GB (R=90); 355 GB if packets were also in SQLite | **118 GB; 711 GB** | **Yes**: one household's "erase everything" copies every other household's data, needs ≥ 2× the whole file free, and takes minutes of I/O on a 2-vCPU VM; the v1 30 GB disk cannot hold even one copy |

Consequence for the hosted variant: **per-household SQLite files** (the schema already
keys every table by `profile_id`, so the change is file placement, not schema), which
makes `VACUUM INTO` headroom 2 × 0.6 GB, lets P-107's byte-scan after `erase_profile`
run on that household's file alone, and makes snapshots per household. With that, the VM
disk goes from v1's 30 GB to **80 GB** (100 × 0.59 GB + OS + one household's headroom;
120 GB in the worst-with-caps case): +$4.00/VM-month = **+$0.040/user-month** at gp3
rates (+$0.024 on a Hetzner volume). Without per-household files the disk would need to
be sized at 2× the whole set (120–240 GB) and the erase-all path would be the most
expensive operation in the product. On the laptop none of this matters beyond the free
space check `erase_profile` must make before it starts (refuse with a clear message if
free space < 2× the file; never half-swap).

### 9.6 Bottom line: does CP4 move the $5 / $10 / $15 sensitivity?

Per-user-month delta on `A_b`, Decimal arithmetic (Appendix C §C.7), against v1's lines
for the same items (durable storage, idle cache, snapshot, re-observation compute, VM
disk). "Expected" = 90-day retention (the plan's default), 8 h camera-on, typical packets,
promotion capped at 1/item/h, re-observation at its 2.5 vCPU-h budget, 80 GB VM disk.

| Case | Packets | Block storage (DB) | Snapshot | Re-obs compute | Extra VM disk | New lines | v1 lines | **Δ $/user-month** | **`A_b`** | P=10/S=3 hosted margin |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **AWS, expected, R=90** | 2.96 GB, 0.0681 | 0.59 GB, 0.0472 | 0.1777 | 0.0520 | 0.0400 | 0.3850 | 0.1648 | **+0.2203** | **0.7175 → 0.72** | **49.43 %** |
| AWS, expected, R=30 | 1.00 GB, 0.0230 | 0.34 GB, 0.0269 | 0.0669 | 0.0520 | 0.0400 | 0.2088 | 0.1648 | +0.0441 | 0.5413 (0.50 stands) | 51.19 % |
| AWS, CP4-only at R=90 (v1 packet bytes kept, isolates CP4 from the CP2 size correction) | 1.80 GB, 0.0414 | 0.59 GB, 0.0472 | 0.1195 | 0.0520 | 0.0400 | 0.3001 | 0.1648 | +0.1354 | 0.6326 | 50.27 % |
| AWS, worst **with** the §9.4 caps (high packets, 24 h, 120 GB disk) | 5.51 GB, 0.1266 | 0.59 GB, 0.0472 | 0.3048 | 0.0520 | 0.0720 | 0.6027 | 0.1648 | +0.4380 | 0.9352 (< 1.10) | 47.25 % |
| AWS, worst **without** caps (every frame promoted and embedded, 30 items, 24 h, 200 GB disk) | 5.51 GB, 0.1266 | 42.39 GB, 3.3911 | 2.3948 | 2.3962 | 0.1360 | 8.4447 | 0.1648 | **+8.2800** | 8.7772 | **−31.17 %** |
| Hetzner/B2, expected, R=90 | 0.0178 | 0.0281 | 0.1777 | 0.0083 | 0.0238 | 0.2556 | 0.1176 | +0.1379 | 0.3019 | 53.58 % |
| Hetzner/B2, expected, R=30 | 0.0060 | 0.0160 | 0.0669 | 0.0083 | 0.0238 | 0.1210 | 0.1176 | +0.0033 | 0.1673 | 54.93 % |
| Hetzner/B2, worst with caps | 0.0330 | 0.0281 | 0.3048 | 0.0083 | 0.0428 | 0.4170 | 0.1176 | +0.2994 | 0.4634 | 51.97 % |
| Hetzner/B2, worst without caps | 0.0330 | 2.0143 | 2.3948 | 0.3835 | 0.0808 | 4.9064 | 0.1176 | +4.7888 | 4.9528 | 7.07 % |

Readings:

1. **Expected delta at the plan's 90-day default: +$0.22/user-month (AWS), above the
   $0.05 threshold, so §2.4, §3.2 and §3.3 are recomputed at `A_b = 0.72`.** Of the
   0.22, 0.085 is the stored-packet correction (a CP2 fact that the retention arithmetic
   exposed), 0.040 the VM disk, 0.057 the SQLite-resident cache, promoted frames and rows
   with their snapshot share, 0.038 the net re-observation budget. The CP4-only delta is
   +$0.14; it exceeds the threshold on its own.
2. **At a 30-day default the delta is +$0.04 and the v1 tables stand within rounding.**
   This is the retention lever of §9.4 ($0.18/user-month).
3. **The worst case with caps (0.94) stays under the tables' 1.10**, with $0.17 to spare,
   but 1.10 no longer also covers per-keyframe objects (+0.48 would make it 1.42): cap 4
   is now load-bearing, not a saving.
4. **Without the §9.4 caps there is no worst case to tabulate**: +$8.28 at AWS rates
   (+$4.79 Hetzner), a −31 % hosted margin at $10/S=3. Nothing in v1's 1.10 anticipated
   a per-item, per-30-s durable write path.
5. The **sensitivity readings of §3 do not change**: $5 is not viable; $10 works only
   near S=3 (hosted now 49.4 %, not 51.6 %); $15 keeps 23 % or more at S=8 (22.97 % at
   the $1/$5 tier) outside the $2/$10 chat tier (14.0 %). Every hosted break-even price
   moves by +$0.23 (= 0.22 / 0.971) and every 40 %-margin price by +$0.39 (= 0.22 /
   0.571); the rows that work in §3.3 move by 1–4 households at F=150.

Before/after at P=10, S=3 (hosted rows; v1 → v1.2): margin 51.60 % → 49.40 %; break-even
P* $4.69 → $4.91; P at 40 % $7.97 → $8.35; households for F=150 26 → 27, for F=4,150
703 → 730; subtotal before support 1.84 → 2.06. Rig rows are untouched: CP4 costs the
rig nothing in money and ≈ 0.35 % of a core under cap 7(d).

### 9.7 What replaces these numbers

The tester's synthetic CP4 runs (`BUILD_PLAN.md` *Finance* line for CP4) should report,
per household-day: stored packet bytes per revision (not raw keyframe bytes), landmark
bytes before and after the 72 h pass, idle frame bytes at q0.5 on the fake camera and on
one real 720p room scene, promoted frames and `reobservations` rows per day with the
item count, pairs processed and ms per pair on the dev laptop (diff-only and with the
embedder), and the database file size before and after `apply_retention` and after
`erase_profile`. On device (P-105) the same counters replace every [A] above; §6 items 1
and 3 are the slots. None of §9 is an on-device measurement.

---

## 10. CP5: telemetry, the support-cost measurement plan, and the rig measurements that replace assumptions (v1.3, 2026-10-10)

What CP5 adds (`BUILD_PLAN.md` "CP5 in detail"): the resolver, the rubric and the scenario
runner (pure functions and a test harness: no cost line), the notices page (static), and
**frame accounting**: the browser keeps counters per capture session and posts them every
60 s and at stop to `POST /api/telemetry` (`schema_version`, `device_id`, `session_id`,
`t_ms`, `clock_anchor`, `window_ms`, 16 integer `counters`, 4 `timing` floats, 3
`settings` values; "all integers/floats, bounded; no free text"; 64 KiB body cap); the
store keeps them in `frame_counters` and derives `coverage(day_utc) -> {camera_on_ms,
gap_ms, episodes, packets, idle_sent, idle_dropped, sessions}`; `GET /api/coverage?day=`
and health `coverage` expose today's; the Privacy view gains a **Status panel** with the
coverage and the live counters; telemetry rows expire with `episodes_days`. Two things in
that list matter to this file. The telemetry is the measurement hook §5 and §6 have pointed
at since v1 ("CP5 frame counters are the measurement hook"; §6 items 1, 3, 5), so §10.3
names, for every assumption in §1–§9, the field that replaces it. The Status panel is the
only lever CP2–CP5 have on `S` (cap 9: "the only lever ... is making failures
self-explanatory"), so §10.2 says what the ticket log must record for that lever to be
measured rather than assumed. §10.1 prices the telemetry itself; §10.4 restates the cost
table with every value labelled, which is what the rig will be measured against.

### 10.1 Telemetry cost: negligible, with the arithmetic

Inputs:

| Parameter | Value | Label and source |
| --- | --- | --- |
| Posts per session | one per 60 s while the camera is on, plus one at stop | [D] plan: "every 60 s and at stop" |
| Camera-on hours per day | 8 (worked example); 24 (bound) | [A] as §9: 481 rows/day; 1,441 rows/day |
| Body bytes, the plan's schema with representative values, compact JSON | **656 B** (716 B with default spacing; 805 B with every counter at 2³¹ − 1) | [M-sandbox] v1.3 session, `json.dumps` of the schema in Appendix D.1 |
| Stored row (three JSON columns + `profile_id`, `device_id`, `session_id`, `t_ms`, `received_ms`, `window_ms`, SQLite record and index) | ~848 B typical; **2 KB used as the bound** | [A] ~192 B of key columns and overhead |
| Body cap | 64 KiB | [D] plan |
| Retention | `episodes_days`: 30 default; 90 shown | [M-code] `RETENTION_DEFAULTS` at `7ab0e5e`; [D] plan: "telemetry rows expire with `episodes_days`" |
| Ingest CPU | ~1 ms per post (JSON parse, validation, one INSERT) | [A] |
| Prices | gp3 $0.08/GB, snapshot $0.05/GB, egress $0.09/GB, t3.medium $0.0208/vCPU-h; Hetzner volume €0.044 × 1.08 | all [Q-UNVERIFIED] (header note) |

Results (Appendix D.2; rows × bytes × days; storage and its snapshot at the rates above):

| Case | Rows/day | Bytes/day | Held at R = 30 | $/user-month, R = 30 (AWS gp3 + snapshot) | Held at R = 90 | $/user-month, R = 90 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 8 h camera, typical 848 B row | 481 | 408 KB | 12.2 MB | 0.0016 | 36.7 MB | 0.0048 |
| **8 h camera, 2 KB bound** | 481 | **985 KB** | **29.6 MB** | **0.0038** | 88.7 MB | 0.0115 |
| 24 h camera, 2 KB bound | 1,441 | 2.95 MB | 88.5 MB | 0.0115 | 265.6 MB | 0.0345 |
| 8 h camera, every post at the 64 KiB cap (a broken client, not the schema) | 481 | 31.5 MB | 946 MB | 0.1229 | 2.84 GB | 0.3688 |
| 24 h camera, every post at the cap | 1,441 | 94.4 MB | 2.83 GB | 0.3683 | 8.50 GB | 1.1049 |

The other lines: ingest CPU 14,430 posts/month × ~1 ms = 14.4 CPU-s = 0.004 vCPU-h =
**$0.00008**; the Status panel's `GET /api/coverage` at 20 reads/day × 2 KB = 1.2 MB/month of
egress = **$0.0001**; **no object-store request** (the posts hit our own VM, not S3, so cap 4
is untouched); ingress is free. On the phone's radio the telemetry is 985 KB/day at the
bound against ≈ 39 MB/day of episode packets (§9.1.2): **2.5 %**. On the rig it is 0.4–1
MB/day inside the laptop's SQLite file, 12–30 MB at 30 days: no consequence for the
`VACUUM INTO` headroom of §9.5. Hetzner figures are 0.75× the AWS ones (D.2).

**Reading: telemetry costs under one cent per user-month in every case the schema allows
(the maximum under the schema is $0.035, at 24 h of camera, 90-day retention and the 2 KB
bound), i.e. below the $0.05 threshold this file uses for recomputing tables, and it is
not added to `A_b`.** The only way above the threshold is a client that posts cap-sized
bodies every minute, which the fixed schema cannot produce (656–805 B), so Finance
proposes no new cap; it asks only that `ingest_telemetry` enforce what the plan already
says (closed key set, numeric values, no free text), which bounds the row at ~1 KB without
a byte cap of its own. *Where the builder's draft already stands (read, not reviewed;
uncommitted at the time of writing):* `Telemetry`, `TelemetryCounters`, `TelemetryTiming`
and `TelemetrySettings` are `StrictModel`s (closed key sets, every counter a bounded
nonnegative int, `MAX_TELEMETRY_BYTES = 64 * 1024`), `ingest_telemetry` stores the three
`model_dump()` JSON columns and is idempotent on `(device, session, t_ms)`, and
`apply_retention` counts `telemetry_expired` with `episodes_days`: exactly the bound
assumed above. Cap 9's diagnostic value exceeds any cost here by orders of
magnitude: one support minute avoided per household-month ($0.30, §5 item 9) pays for a
year of telemetry at the bound. One retention note for the privacy agent, not a cost
one: the raw 60 s rows can expire at 30 days, but the dozen integers of `coverage(day)` are
the only durable record of camera-on hours and episodes per day that §10.3 depends on; if
they also expire at `episodes_days`, the one-week template below must be filled in from
the live panel within the window (open question 20).

### 10.2 Support-cost measurement plan for the first households

`S` is the only line in this file that can make $10 negative in every variant (§6, riskiest
assumption 1), it is unmeasured, and the pilot's ticket log is the only instrument that
measures it (§6 item 6; open question 7 asked who keeps it). This section says what the log
must contain so that `S` is a number at the first monthly report, what number ends the $10
case, and which calls CP5's Status panel is expected to turn into self-service.

#### 10.2.1 What the log records: one row per contact

A flat table (a spreadsheet outside the product is fine; it must never hold a name, an
address, a phone number, a photo or any item name; the pseudonym map is held by the pilot
lead alone and is not needed for any number here). Closed vocabularies everywhere a number
is later computed from the field.

| Field | Values | Why Finance needs it |
| --- | --- | --- |
| `household_id` | pseudonymous (`hh-007`); not the `profile_id`, not the `device_id` | per-household minutes, the p50/p90 split, and the join to the roster below |
| `contact_date` | UTC date | the monthly window |
| `channel` | one of `phone`, `video`, `visit`, `text`, `email`, `self_serve` (a contact the household resolved from the Status panel or notices page and only told us about; 0 staff minutes) | the channel mix decides the loaded rate; `self_serve` rows measure cap 9's effect |
| `minutes` | integer staff minutes, including write-up; travel minutes in a separate `travel_minutes` column for visits | the numerator of `S` |
| `staff` | `founder`, `support`, `agency` | founder time is unpaid cash but real cost: it is counted at the loaded rate, never at zero |
| `kind` | `onboarding` (first-contact setup) or `ongoing` | onboarding is amortised over tenure, ongoing is not (§3.1) |
| `category` | **closed list:** `setup/mount`, `consent questions`, `Wi-Fi/TLS`, `camera permission`, `false answer`, `missed capture`, `erasure request`, `other` | the category shares say which failures the product should explain itself; `other` above 20 % of minutes means the list needs a new entry, not a bigger `other` |
| `self_explanatory` | `yes` (the Status panel / "Why this answer" / notices page showed the cause and the caller could have acted on it), `no` (the state was not visible), `n/a` | measures, rather than assumes, the minute reduction §10.2.4 expects from CP5 |
| `resolution` | `explained`, `setting_changed`, `reprovisioned` (model assets, certificate), `hardware_replaced`, `escalated`, `unresolved` | repeat contacts and hardware cost |
| `hardware_cost_usd` | dollars of parts shipped, if any | the `W` line of §2.1 becomes a measured number |
| `coverage_day` | the `GET /api/coverage?day=` day the staff looked at, if any | ties the call to the counters that explain it |
| `variant` | `rig` or `hosted` | §6 item 10: the claim that `S` is not lower on the rig |

A second, smaller table, the **roster**: `household_id`, `channel_class` (`family` /
`agency`), `variant`, `enrolled` (date), `hardware_supplied` ($, the mount kit if any),
`ended` (date) and `end_reason` (closed list: `death`, `moved_to_care`, `abandoned`,
`dissatisfied`, `pilot_ended`, `other`). It gives the denominators (active
household-months) and, by the second month, the first tenure number (§6 item 7), which
replaces the 12-month onboarding amortisation and the 24-month hardware amortisation.

#### 10.2.2 How `S` is computed from the log, monthly

```
N          = active household-months in the month (roster: enrolled, not ended)
M_ongoing  = Σ minutes over contacts with kind = ongoing in the month (all channels, incl. founder)
M_onboard  = Σ minutes over contacts with kind = onboarding in the month
N_onboard  = households whose first contact fell in the month
T          = tenure in months (12 [A] until the roster measures it)
r          = loaded $/h: 18.00 lean, 19.20 heavy [A] until payroll replaces it (§3.1)

S = r/60 × ( M_ongoing / N  +  (M_onboard / N_onboard) / T )
```

Reported alongside, every month: minutes per household p50 and p90 (support in elder care
is heavy-tailed; a mean of 10 min can be nine quiet households and one at 90 min, and the
two cases need different products), minutes by category, contacts per household-month,
the `self_explanatory = yes` share of minutes, travel minutes (visits are a different
business), and the three numbers of §10.2.3 next to the measured `S`. Appendix D.4 shows
the formula on an illustrative month (10 households, 200 ongoing minutes, 450 onboarding
minutes: `S` = $7.13), which is an input-format check and not a prediction. **`S` is
reported as a measurement only from a month with ≥ 10 active households and every
contact logged**; until then it is a running estimate with the household count beside it.

#### 10.2.3 The threshold at which $10 stops working

From the §3.1 formula at P = 10 (fee 0.59, `H` 0.75): margin is zero at **`S` = 8.66 − `A`**
and 40 % at **`S` = 4.66 − `A`**; in minutes at $18/h (Appendix D.3):

| Variant (`A` $/user-month) | `S` at zero margin | = minutes/household-month | `S` for a 40 % margin | = minutes | Where the §3 assumptions sit |
| --- | ---: | ---: | ---: | ---: | --- |
| (a) Rig (0) | **$8.66** | 28.9 | **$4.66** | 15.5 | S=3 is 10 min at $18/h; S=8 is 25 min at $19.20/h |
| (b) Hosted, CP4 30-day default (0.5413) | **$8.12** | 27.1 | **$4.12** | 13.7 | |
| (b) Hosted at 90 days (0.72, the §3 table value) | $7.94 | 26.5 | $3.94 | 13.1 | |
| (b) Hosted worst (1.10) | $7.56 | 25.2 | $3.56 | 11.9 | |
| (c) + chat, cheap tier (0.676) | $7.98 | 26.6 | $3.98 | 13.3 | |
| (c) + chat, $1/$5 tier (1.891) | $6.77 | 22.6 | $2.77 | 9.2 | lean support no longer reaches 40 % |
| (c) + chat, $2/$10 tier (3.241) | $5.42 | 18.1 | $1.42 | 4.7 | |

Reading, as a rule for the monthly report: **every minute of support per household-month
costs $0.30 = 3 margin points at $10.** $10 earns a working margin (≥ 40 %) only while
support stays under **≈ 14–15 minutes per household-month all-in** (onboarding amortised),
and loses money above **≈ 27–29 minutes**. The §3 readings stand ("$10 works only if
support stays near $3/user-month" = 10 min): the log turns that sentence into a monthly
number. Two early-warning rules for the first report, before `S` is a measurement: an
onboarding contact above **45 min** (the §3.1 lean assumption) or ongoing minutes above
**10 per household** in the first full month each means the heavy column (S=8) is the one
to read, and the §3.2 table says what that does at $10 (−4.4 % to +6.6 % without chat).

#### 10.2.4 The self-explanatory failure states that reduce minutes

v1's `S = 3` assumed "good in-app diagnostics (§5, item 8)". CP5 is the checkpoint that
ships them, so this table maps each log category to the CP5 state that lets the family
or the caregiver see the cause without a call. The reduction is not assumed here: the
`self_explanatory` field of §10.2.1 measures it, and the first month's share of minutes
with `self_explanatory = no` is the backlog for the next UI checkpoint.

| Category | What the caller sees at CP4 | CP5 state that explains it (counter / panel) | Where |
| --- | --- | --- | --- |
| `missed capture` ("it didn't see me put it down") | nothing: a missed episode is silent | `coverage.camera_on_ms` and `gap_ms` ("camera on 3 h 10 min today, 2 gaps: screen lock 41 min"), `episodes_started / finished / aborted`, `frames_skipped_busy`, `landmark_timeouts` (the phone could not keep up), `idle_sent / idle_dropped` | Status panel; `GET /api/coverage` |
| `Wi-Fi/TLS` (phone not on the home LAN, certificate not trusted, laptop asleep) | queue retries; a "retained/dropped" notice | `packets_sent` vs `packets_acked` ("4 captures waiting to upload"), `gaps` / `gap_ms` (the counters are counts; the reason text stays in the Camera view's gap log and the packet's `gaps` entries [M-code `memory-camera.js`]), `bytes_sent` flat while the camera is on; health unreachable = the laptop/cert explanation page (cap 9) | Status panel; health |
| `camera permission` | "Waiting for camera permission" | `sessions = 0` and `camera_on_ms = 0` for the day; `settings.width/height/frame_rate` present means the camera did start | Status panel |
| `setup/mount` | the camera preview | `fps_observed`, `settings` (the delivered resolution and rate), `frames_captured` per minute: the mount and phone are delivering what the controller expects | Status panel |
| `false answer` ("it showed the wrong place") | the photo answer | the "Why this answer" basis list (`aged`, `expired`, `provisional_match`, `lookalikes`, `negative_reobservation`, `index_pending`): the caregiver reads why before calling; `revisions_expired` explains a missing photo (30-day retention) | chat view; `GET /api/retention` counts |
| `consent questions` | the Privacy view disclosure; 409 `consent_required` | health `consent.ok` / `required_version`; the `/notices` page for "what is in this thing" | Privacy view |
| `erasure request` | the CP4 erase flows and their count-only report | unchanged; `revisions_erased` in the retention counts confirms it happened | Privacy view |
| `other` (model not provisioned, worker behind) | health `models[]`, `processing.status` | `reobs_deferred` and `reobs_cpu_s` against the 300 s budget ("the laptop is behind on re-observation today"), `processing.pending` | health |

Two categories have no self-serve state and should not: `erasure request` is a human
obligation whatever the UI says, and `consent questions` are answered by a person. The
minutes Finance expects the panel to remove are in `missed capture` and `Wi-Fi/TLS`, the
two silent failures of the rig (§2.1: "every one of those is a support call waiting to
happen"); if the first month's log shows those two categories at `self_explanatory = yes`
and still consuming minutes, the panel is visible but not understood, which is a UI
finding for C, not a finance one.

### 10.3 The rig measurement list: what replaces each assumption

Every assumption row of §1, §8 and §9, the CP5 counter, CP4 counter or store query that
measures it, and the experiment it belongs to (`RESEARCH_EXPERIMENTS.md` "Proposed
experiment queue"). "Counter" means a `POST /api/telemetry` field (browser, per 60 s
window, summed by `coverage(day)`), "health" the `GET /api/health` block, "retention
counts" `GET /api/retention` / `retention_counts()`, "reobservation" the worker's last
`reobserve()` counts in health, "query" a read-only SQL over the household's SQLite file
by Builder B (never a route; packet bytes never leave the store). The builder's
uncommitted draft of `coverage(day)` returns, beyond the plan's seven keys, `packets_acked`,
`episodes_started`, `frames_captured`, `frames_analysed`, `frames_dropped`, `bytes_sent`
and `windows` per day, which gives rows 1, 7, 8, 10 and 21 below a per-day number without
summing the 60 s rows by hand.

| # | Assumption (section) | Current value and label | What measures it at CP5 | Protocol |
| --- | --- | --- | --- | --- |
| 1 | Episodes per day (§1) | 50 [D, "estimate; measure"] | `episodes_finished` (and `episodes_started`, `episodes_aborted`) summed per day = `coverage.episodes`; cross-check `count(*)` of accepted `episode_revisions` per day | P-105 (20-min sustain gives the hourly rate), then whole rig days on the user's iPhone (P-101/P-103 as §6 item 1 names them) |
| 2 | Keyframes per episode (§1) | ≤ 8 selected [D] | query: keyframe count per stored packet | same |
| 3 | Packet bytes as stored (§9.1.2) | 786 KB typical / 1,660 KB high [A] | query: `length(packet)` per revision, p50/p95; wire bytes per packet = `bytes_sent / packets_sent` from the counters | P-105, P-103 |
| 4 | Keyframe bytes at capture resolution (§1, §9) | 50 KB typical / 100 KB high [A]; synthetic 84 KiB at 720p q0.72 [M-sandbox] | query: base64 length × 3/4 per keyframe inside the packet; `settings.width/height` says the resolution it was taken at | P-105 |
| 5 | Burst bytes (§9) | 10 × ~8 KB [A]; synthetic 13–18 KiB [M-sandbox] | query: burst frame lengths per packet | P-105 |
| 6 | Landmark bytes and the 72 h reduction (§9.1.2) | 140.6 KB typical / 473.5 KiB worst [M-sandbox on the real schema]; −92 % after reduction | query: `length(packet)` before vs after `reduced_ms` is set; retention counts `landmarks_reduced` | P-105 (first packets pass 72 h on day 4) |
| 7 | Camera-on hours per day (§9) | 8 [A] | `coverage.camera_on_ms`, `sessions`, `gap_ms` per day | P-105, then whole days |
| 8 | Idle frames per day (§9.1.1) | 960 at 8 h; 2,880 bound [D] | `idle_sent`, `idle_dropped` (counters); the browser's drop reasons `oversize / capped / failed` [M-code `memory-camera.js`]; retention counts `idle_cached` | P-105 |
| 9 | Idle frame bytes (§9.1.1) | ≤ 64 KiB target [D]; synthetic 65 KiB at 720p q50 [M-sandbox] | query: `sum(length(jpeg))` / count over `idle_frames`; cross-check `bytes_sent` minus packet bytes | P-105 |
| 10 | Phone uplink per day (§1) | 39 MB/day packets + idle [A] | `bytes_sent` per day | P-105 |
| 11 | Items with a placed location (§9) | 10–30 [A] | query: `count(*)` of items with `location_status = placed` | P-105 |
| 12 | Promotion rate (§9.1.3) | ≤ 24 per item-day under the hourly refresh [D]; 0–10 % of frames [A] | reobservation `promoted` per pass, retention counts `idle_promoted`, `apply_retention` `idle_promoted_expired` | P-105 |
| 13 | Re-observation CPU per pair (§9.2) | 10 ms laptop-class [A]; 8.5 ms [M-sandbox] | ≈ `reobs_cpu_s / (checked − gated)` per pass (gated frames cost a 0.5–2 ms diff each, inside the same clock); the day total in `maintenance_counters` (`reobs_cpu_s`) against `REOBS_CPU_BUDGET_S = 300`; `reobs_deferred > 0` means the budget bound | P-105 |
| 14 | Pairs per day and the gate's share (§9.2, cap 7b) | ≤ 10 % of frames change [A] | reobservation `checked`, `gated`, `pending` per pass, summed per day | P-105 |
| 15 | DINOv2 ViT-S/14 ms per 224 px crop (§8) | 60–150 ms [A]; FLOP-bounded | `(reobs_cpu_s − registered pairs × t_pair) / embedded` per pass on the laptop; the ONNX export benchmark on the laptop and on a t3.medium-class VM | P-104 (export + calibration), §6 item 2 |
| 16 | Write-path CPU per episode (localizer + crops + embed) (§1, §2.2) | 0.3–1.0 s [A] | **no CP5 field.** `processing_stats` carries counts only (`processed`, `failed`, `observations`, `pending`). Proposed: a per-UTC-day `maintenance_counters` row `process_cpu_s` charged by `process_pending` with the same `perf_counter` pattern as `reobs_cpu_s` (open question 18) | P-105; the hosted load test (§6 item 2) |
| 17 | Queries (chats) per day (§1, §2.3) | 20 [A] | **no CP5 field** (cloud chat is 503 `chat_not_configured`; local answers are not counted). Proposed: `chat_local` per day in `maintenance_counters` (open question 18); the provider checkpoint's micro-USD ledger (cap 10) measures tokens and retries | the bounded-cost provider checkpoint; §6 item 4 |
| 18 | Photo serves per day and photo answer bytes (§1, §2.2, cap 8) | 800/month; ~100 KB [A] | **no CP5 field** (cap 8 asked for it "in the frame counters (CP5)"; the plan's counters are browser-side and do not see `GET /api/items/{id}/image`). Proposed: `image_serves` and `image_bytes` per day in `maintenance_counters` (open question 18) | P-105; the caregiver browsing pattern needs whole days |
| 19 | Support minutes per household-month (§3.1) | S = 3 / 8 [A] | the ticket log of §10.2, not telemetry | the pilot (v4 "Pilot criteria") |
| 20 | Tenure / churn (§3.1, §4) | 12 months onboarding, 24 months hardware [A] | the roster of §10.2.1 | the pilot and the first paying cohort |
| 21 | Laptop uptime, certificate and LAN incidents (§2.1, §6 item 10) | "S is not lower on the rig" [A] | `gaps` and `gap_ms` with reasons; `packets_sent − packets_acked` per day; log categories `Wi-Fi/TLS` | P-105 and the log |
| 22 | 100 users per 2-vCPU VM at 25 % (§2.2) | [A], 3× safety factor | **not a rig measurement**: needs the hosted load test with rows 15–16 measured first; the rig gives the per-episode and per-day CPU that feeds it | §6 item 2 |
| 23 | Telemetry row bytes (§10.1) | 656 B body [M-sandbox]; 2 KB bound [A] | query: `length(counters) + length(timing) + length(settings)` per `frame_counters` row | P-105 (first run) |

Rows 16–18 are the gaps: three finance assumptions that CP5's browser-side counters cannot
see because the quantity is produced on the server. Each is one `maintenance_counters`
row per UTC day (the table and the upsert pattern already exist for `reobs_cpu_s`
[M-code]), exposed as integers in `GET /api/coverage`; without them §6 items 2, 4 and 5
have no slot after the rig run and stay assumptions. This is open question 18 for the
architect; it is not a cap.

**One-week measurement template.** To be filled from the first seven rig days (the
`coverage(day)` aggregates for each day, the health and retention counts at the end of
each day, the queries once at the end of the week, the log continuously). "Who" names the
role: the rig operator is the user running the iPhone (`CONTINUATION_HANDOFF.md`: real
iPhone tests are the user's), Builder B runs the read-only queries on the household file,
the Tester supplies the same numbers from the synthetic scenario runs as a software
baseline (they are not device numbers and are labelled so), the pilot lead keeps the log,
and Finance compiles the column into v1.4.

| Assumption | Current value | Source after one week | Who records it |
| --- | ---: | --- | --- |
| Episodes/day | 50 [D] | mean and max of `coverage.episodes` over 7 days; `episodes_aborted` share | rig operator (panel), Tester (baseline) |
| Camera-on h/day; gaps | 8 h [A] | `camera_on_ms`, `gap_ms`, `sessions` per day | rig operator |
| Stored packet bytes, p50/p95 | 786 KB [A] | `length(packet)` query at day 7, split by `reduced_ms` null / set | Builder B |
| Keyframe bytes; resolution | 50 KB [A] | base64 lengths × 3/4; `settings.width × height` | Builder B; rig operator |
| Landmark bytes, before/after 72 h | 141 KB → 12 KB [M-sandbox] | packet length delta for the day-1..3 cohort at day 7; `landmarks_reduced` | Builder B |
| Idle frames/day; dropped; reasons | 960 [D] | `idle_sent`, `idle_dropped`; browser reasons | rig operator |
| Idle frame bytes | 64 KiB [D] | `sum(length(jpeg))/count` over `idle_frames` | Builder B |
| Uplink bytes/day | 39 MB [A] | `bytes_sent` per day | rig operator |
| Items placed | 10–30 [A] | `location_status = placed` count | Builder B |
| Promotions/day | ≤ 24 per item [D] | `promoted` per day; `idle_promoted` | rig operator (health), Builder B |
| Re-obs CPU per pair; per day; deferred | 10 ms [A]; ≤ 300 s [D] | `reobs_cpu_s`, `checked`, `gated`, `embedded`, `reobs_deferred` per day | rig operator (health), Builder B (`maintenance_counters`) |
| Embed ms per crop | 60–150 ms [A] | derived from the row above; the P-104 laptop benchmark | Builder B; Tester |
| Write-path s per episode | 0.3–1.0 s [A] | `process_cpu_s / processed` if open question 18 is adopted; otherwise a one-off timer run by Builder B | Builder B |
| Local chat questions/day | 20 [A] | `chat_local` if adopted; otherwise the operator's count | rig operator |
| Image serves/day; bytes | 27/day; 100 KB [A] | `image_serves` if adopted; otherwise the uvicorn access log count for the week | Builder B |
| Support minutes; categories; self-explanatory share | S=3 (10 min) [A] | the ticket log, week 1 (onboarding week: expect the 45 min row) | pilot lead |
| Telemetry row bytes | 656 B [M-sandbox] | `frame_counters` row lengths | Builder B |
| Database file size at day 7 | 43.5 MB/day → 0.3 GB [A] | `stat` of the SQLite file before and after `apply_retention` | Builder B |

Every value entered goes into `RESEARCH_EXPERIMENTS.md` under the X-ID the run creates
(its "Minimum run record": device, OS, browser, mount, commit, uncommitted changes), with
the [M] label and the date; Finance then recomputes §2–§3 from the measured column and the
labels in §10.4 change from [A] to [M] one row at a time.

### 10.4 Pre-rig bottom line: the cost table as it stands after CP4, every value labelled

Costs before and with support, at P = $10 (fee = 0.029 × 10 + 0.30 = 0.59), BYOD, 30-day
retention as CP4 decided (`A_b = 0.5413`, §9.6 R=30 row; the 90-day `0.72` the §3 tables
keep is shown beside it; Appendix D.5):

| Variant | `A` metered cloud | Fee | `H` | Subtotal (no S) | + S=3 → margin | + S=8 → margin | Label of each value |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| (a) Rig, BYOD | 0.0000 | 0.5900 | 0.7500 | **1.3400** | 4.3400 → **56.60 %** | 9.3400 → 6.60 % | A: [D] zero cloud; fee: [Q-UNVERIFIED] rate at an [A] price point; H: [A]; S: [A]; W: 0 by [A] policy |
| (b) Hosted, CP4 30-day default | 0.5413 | 0.5900 | 0.7500 | **1.8813** | 4.8813 → **51.19 %** | 9.8813 → 1.19 % | A: [A] workload × [Q-UNVERIFIED] prices, composition below |
| (b) Hosted at 90 days (the §3 table value) | 0.7200 | 0.5900 | 0.7500 | 2.0600 | 5.0600 → 49.40 % | 10.0600 → −0.60 % | same |
| (b) Hosted, worst with the §9.4 caps | 1.1000 | 0.5900 | 0.7500 | 2.4400 | 5.4400 → 45.60 % | 10.4400 → −4.40 % | [A] bound |
| (c) + chat, cheap tier, 30-day | 0.6763 | 0.5900 | 0.7500 | 2.0163 | 5.0163 → 49.84 % | 10.0163 → −0.16 % | chat: [A] 20/day × 1,650 tokens × [Q-REPO/Q-UNVERIFIED] tier |
| (c) + chat, $1/$5 tier, 30-day | 1.8913 | 0.5900 | 0.7500 | 3.2313 | 6.2313 → 37.69 % | 11.2313 → −12.31 % | same; tier [Q-REPO] 2026-10-06 |
| (c) + chat, $2/$10 tier, 30-day | 3.2413 | 0.5900 | 0.7500 | 4.5813 | 7.5813 → 24.19 % | 12.5813 → −25.81 % | same |

Composition of the hosted `A_b = 0.5413` (AWS, batched objects, 30 days; §9.6 and Appendix
D.5), each line with the label of the quantity and of the price it multiplies:

| Line | $/user-month | Quantity label | Price label |
| --- | ---: | --- | --- |
| VM share, t3.medium at 100 users/VM (write-path compute inside) | 0.3277 | [A] 100 users/VM at 25 % utilisation | [Q-UNVERIFIED] $0.0416/h |
| Packet objects, 1.00 GB × $0.023 | 0.0230 | [A] 50 ep/day × 786 KB (the bytes are [M-sandbox] on the real schema; the counts are [A]) | [Q-UNVERIFIED] |
| Block storage: idle cache at its cap, promoted frames, rows; 0.34 GB × $0.08 | 0.0269 | [D] caps, [A] rates of promotion | [Q-UNVERIFIED] |
| Snapshot of both, 1.34 GB × $0.05 | 0.0669 | [A] daily snapshot of the full set | [Q-UNVERIFIED] |
| Re-observation budget, 2.5 vCPU-h net of v1's 0.6667 | 0.0381 | [D] `REOBS_CPU_BUDGET_S = 300` [M-code], taken as fully used | [Q-UNVERIFIED] |
| Extra VM disk, (80 − 30) GB × $0.08 / 100 | 0.0400 | [A] per-household files (CP4 decision 8) | [Q-UNVERIFIED] |
| PUT requests, batched (cap 4) | 0.0111 | [A] 74 objects/day | [Q-UNVERIFIED] |
| GET requests | 0.0003 | [A] 800/month | [Q-UNVERIFIED] |
| Egress, photo answers | 0.0072 | [A] 800 × 100 KB | [Q-UNVERIFIED] |
| **Sum** | **0.5412** (0.5413 unrounded) | | |

Status of the inputs, counted: of the 23 assumption rows in §10.3, **0 are measured on a
device**; 6 carry [M-sandbox] bounds on synthetic inputs (synthetic keyframe, burst and
idle-frame sizes, landmark bytes on the real schema, registration ms, the telemetry body);
the [D]/[M-code] constants in rows 2, 8, 12 and 13 are caps and budgets that bound rather
than measure; everything else is [A]. Every external price is [Q-UNVERIFIED] except the
two Anthropic tiers [Q-REPO]. The §7 sentence therefore stands unchanged: none of this is
a margin claim (RESEARCH_LOG B-17, C-10), and the difference between the rig and the
hosted variant ($0.54 at 30 days, 5.4 points at $10) is less than two support minutes
($0.60).

**The three numbers that most change the margin and must be measured first**, in order of
leverage at P = 10, with the instrument that measures each from day one of the rig:

1. **Support minutes per household-month (`S`).** 3 margin points per minute; the
   assumed range (10–25 min) spans 50 points, from +56.6 % to +6.6 % on the rig, and
   crosses zero at 27–29 min. Instrument: the ticket log of §10.2 from the first
   onboarding contact, with the roster for the denominator and the `self_explanatory`
   field for cap 9's effect. Nothing in the code measures it; nothing in the code can
   bound it.
2. **Episodes per day × stored bytes per episode** (`coverage.episodes`,
   `length(packet)`), together with camera-on hours. It is the multiplier on every metered
   hosted line (the VM share through its compute; the packet, packet-snapshot and PUT
   lines directly: $0.084 of the $0.54 at 30 days, $0.227 of the $0.72 at 90) and on the
   rig's disk and laptop load; a 2× miss is +$0.08 (30 days) to +$0.23 (90 days), the 10×
   that cap 3 exists for would be +$0.76 to +$2.04; and it is the number that decides
   whether caps 2–3 ever engage. Instrument: the CP5 counters and one SQL query, available
   on day one.
3. **CPU per episode on the write path and per day in re-observation** (`reobs_cpu_s`,
   `reobs_deferred`, and the proposed `process_cpu_s`). It sets users per VM, the
   largest hosted line: a measured p95 could move the $0.33 VM share to $0.11 or $1.09
   (§6 item 5: +2 to −8 margin points at $10), and on the rig it is whether the household
   laptop keeps up (`reobs_deferred > 0` is coverage lost, not money). Instrument: CP4's
   `maintenance_counters` today and open question 18 for the write path.

The chat tier is the fourth lever (up to 26 points between tiers at 20/day, §2.3) and is
deliberately not in the list: at CP5 it is a decision bounded by cap 1, not a measurement,
because no provider exists (`POST /api/chat` `mode=cloud` returns 503). What the rig can
measure now is the local question count per day (the proxy for the 20/day policy), which
is why `chat_local` is in open question 18.

---

## Open questions for the coordinator

1. **Chat policy vs cap.** The 20/day × 1.5k/150 policy on a $2/$10 model costs $2.70;
   the proposed cap is $1.50. Which gives: the cap (raise to $3.00, which costs 15 margin
   points at P=10), the policy (≤ 10/day), or the tier (default to a ≤ $1/$5 model)?
2. **Which variant is the product?** The rig's "zero cloud" is a privacy and cost story
   but moves ops onto the family laptop and into `S`; hosted costs $0.50/user-month and
   makes the server observable. Finance can model both, not choose. Data residency (EU
   Hetzner vs US AWS) is part of the same decision.
3. **Retention default**: 30 vs 90 days (storage cost difference is $0.03/user-month;
   the real question is the G-PRIV data-class map and `consent_version`).
4. **Hardware policy**: setup fee at cost for the mount kit vs. ship-with-first-month, and
   a refurbished-phone offer for households without a spare iPhone.
5. **Glasses price tiers**: the $349 / $449 / $799 figures were supplied as "from the
   research notes" but are not in `docs/`; public 2025 prices appear to differ. Where
   should they be recorded, with URL and date, so this file can cite them properly?
6. **Price verification**: every `[Q-UNVERIFIED]` figure needs a human re-read at its URL
   (or egress permission for this agent) before FINANCE.md v2.
7. **Support model for the pilot**: who answers, by which channel, and will the ticket
   log record minutes per household so `S` becomes a measurement at the first pilot
   report?

*Added in v1.1 (CP3):*

8. **Per-crop CPU time is assumed, not measured.** 60–150 ms per 224 px crop is the
   coordinator's range, bounded only by FLOP arithmetic (§8); no public CPU benchmark
   could be fetched. Will CP3 acceptance include the §6 item 2 measurement on the dev
   laptop **and** on a t3.medium-class VM (where a vCPU is one hyperthread of a
   burstable core), with the crop count per episode recorded alongside it?
9. **Calibration scope.** Is the approved `calibration_id` product-wide (CUTE plus the
   pilot's own footage, one-time ≈ $1,100–1,500 all in) as the architect's interface
   implies, or could P-104 force per-household calibration? The latter is $1.20–1.60 of
   support per user-month (12–16 margin points at P=10) unless it is self-serve in the
   app. Finance's preference is stated in §8.4; the decision is the architect's.
10. **CP4 arrival-time indexing.** If CP4 adopts the MEMORY review's DINOv2-S index of
    every idle frame at 518 px, compute is 5.8–21.6 vCPU-h/user-month, 5–20× the whole
    v1 line (§8.5). Which bound will CP4 carry: index at 224 px, only on scene change,
    or lazily at query time inside cap 7's 2 s?
11. **Embedding retention.** Confirm that the `embeddings` table and bank copies follow
    the observation's retention window and tombstone semantics (B-07) so cap 6 stays a
    single number; a vector that outlives its tombstoned observation is both a privacy
    defect and an unbounded storage line.

*Added in v1.2 (CP4):*

12. **Promotion and embed rate (cap 7 b–d).** Will the architect adopt the frame-level
    unchanged gate, the ≤ 1 promotion/observation-row/embed per item per hour rule and
    the 300 CPU-s/day budget with a `reobs_deferred` counter? As written, a static
    30-item scene with the camera on all day is 86,400 (item × frame) pairs and
    86,400 observation rows per day: 115 vCPU-h and ~42 GB per household-month hosted
    (§9.2, §9.6). The untracked draft already has the hourly promotion/row refresh
    (`REOBS_REFRESH_MS`) but embeds every `present` pair before it and keeps one
    `reobservations` row per pair with no retention (§9.4). Finance's acceptance of
    CP4 is conditional on some bound of this kind; the exact interval (1 h, 6 h, 24 h =
    `AGE_STALE_MS`) is the architect's.
13. **Promoted idle frames and retention.** The plan says promoted frames "never
    expire"; Finance proposes they and their rows follow `episodes_days` and sit inside
    cap 6 (§9.4). Privacy agent and architect: is a promoted frame evidence with the same
    window as a packet, or something else? If it never expires, cap 6 cannot be a number.
14. **Retention default.** Finance's cost-only proposal is **30 days** ($0.18/user-month
    less than 90 at AWS rates, 1.8 margin points at $10; §9.4), with cap 6 at 2 GiB; if
    the privacy agent chooses 90 days, cap 6 becomes 4 GiB and `A_b = 0.72` is the
    table value. Who decides, and does `consent_version` "rig-2026-10" fix the window?
15. **Per-household database files in the hosted variant.** `VACUUM INTO` needs 2× the
    file; one multi-tenant file for 100 households is 59–355 GB and one household's
    erase-all copies everyone else's data (§9.5). Finance asks the architect whether the
    hosted deployment can be one SQLite file per `profile_id` (the schema already keys
    every table by it), which also gives P-107's byte scan a single file to scan.
16. **Revisions × packet bytes.** Up to 8 accepted revisions per episode each keep a full
    packet. May the 72 h pass NULL the packet bytes of superseded accepted revisions
    (digest columns kept, B-16 untouched), so cap 3's daily bytes and cap 6 count one
    packet per episode? If not, cap 3's hard cap must count revisions.
17. **Packet bytes as stored vs the spec's 20 MB/day.** The stored form is ≈ 2× the
    spec's raw-keyframe estimate (base64, burst, landmarks; §9.1.2). Should
    `MEMORY_SYSTEM_V4.md` "Storage and radio" and cap 3's 500 KB median be restated in
    stored bytes, or should the store strip base64 to raw JPEG BLOBs (a CP2 change that
    would cut the stored set by a quarter and is not in CP4's scope)? Finance has no
    preference beyond consistency of the number; the tester's CP4 runs will measure it
    (§9.7).

*Added in v1.3 (CP5):*

18. **Three server-side daily counters the browser cannot see.** CP5's telemetry is
    browser-side, so three finance assumptions have no slot after the rig run: write-path
    CPU per episode (§6 item 2), local chat questions per day (the proxy for the 20/day
    policy, §6 item 4) and photo serves per day with their bytes (cap 8 asked for them "in
    the frame counters (CP5)", §6 item 5). May CP5 add one `maintenance_counters` row per
    UTC day for each (`process_cpu_s` charged by `process_pending` with the `perf_counter`
    pattern `reobs_cpu_s` already uses, `chat_local`, `image_serves`, `image_bytes`) and
    expose them as integers in `GET /api/coverage`? Counts only, no text; not a cap.
19. **The ticket log and roster (§10.2.1): owner, place and vocabulary.** Who keeps them,
    where (outside the product; no personal data; the pseudonym map with the pilot lead
    alone), and is the closed category list (`setup/mount`, `consent questions`,
    `Wi-Fi/TLS`, `camera permission`, `false answer`, `missed capture`, `erasure request`,
    `other`) accepted as the one the first monthly `S` is computed from? Founder minutes
    count at the loaded rate; the first report with ≥ 10 active households is the first
    `S` that is a measurement.
20. **Retention of the daily coverage aggregates.** The plan expires telemetry rows with
    `episodes_days` (30). The raw 60 s rows can go; the dozen integers of `coverage(day)`
    are the only durable record of camera-on hours, gaps and episodes per day, and §10.3
    needs them for weeks, not days. Privacy agent: are per-day integer aggregates keyed by
    `profile_id` and day personal data under the G-PRIV map, and if not, may they be kept
    for 365 days in a separate table?
21. **The loaded support rate.** $18/h lean and $19.20/h heavy are [A]; the pilot's
    support person is the founder. Finance will report minutes as the primary number and
    dollars at both rates until payroll exists; does the coordinator want a third rate
    (an agency's billed rate) carried for the agency channel?
22. **Status panel wording for the two silent failures.** §10.2.4 expects `missed
    capture` and `Wi-Fi/TLS` to become self-service; that needs the panel to say, in
    plain words, "camera on N h today, M gaps (reason)", "K captures waiting to upload",
    and "the laptop/certificate/Wi-Fi" explanation (cap 9), not only the raw counters. C
    and Oversight own the wording; Finance asks that the `self_explanatory` field of the
    log be read against it at the first report.

---

## Appendix A: reproducible arithmetic

The tables in §2–3 were produced by the script below (Python 3, `decimal` only, no floats). Run it with `python3 -I appendix_a.py` after pasting it to a file; it prints every line item, the sensitivity grid, the worked rows and the break-even counts.

```python
"""PAM FINANCE.md v1 arithmetic. Decimal only; no floats.

Every input is an assumption or an unverified list price; see docs/FINANCE.md for labels.
"""
from decimal import Decimal as D, getcontext, ROUND_HALF_UP

getcontext().prec = 28


def q(x, places="0.0001"):
    return x.quantize(D(places), rounding=ROUND_HALF_UP)


def pct(x):
    return (x * 100).quantize(D("0.01"), rounding=ROUND_HALF_UP)


FEE_RATE = D("0.029")
FEE_FIXED = D("0.30")
H = D("0.75")  # handoff hosting allocation, kept for comparability


def fee(P):
    return FEE_RATE * P + FEE_FIXED


def margin(P, A, S, W=D("0")):
    return (P - fee(P) - A - H - S - W) / P


def breakeven_price(A, S, W=D("0")):
    # P - 0.029P - 0.30 - A - H - S - W = 0  ->  P = (0.30 + A + H + S + W) / 0.971
    return (FEE_FIXED + A + H + S + W) / (D("1") - FEE_RATE)


def price_for_margin(m, A, S, W=D("0")):
    # (1 - 0.029 - m) P = 0.30 + A + H + S + W
    return (FEE_FIXED + A + H + S + W) / (D("1") - FEE_RATE - m)


print("=== Section 2: line items ===")
# --- Hosted compute ---
EPISODES_DAY = D("50")
DAYS = D("30")
SEC_PER_EP_LO, SEC_PER_EP_HI = D("0.3"), D("1.0")
ep_cpu_s_lo = EPISODES_DAY * SEC_PER_EP_LO * DAYS
ep_cpu_s_hi = EPISODES_DAY * SEC_PER_EP_HI * DAYS
print("episode CPU s/month lo/hi:", ep_cpu_s_lo, ep_cpu_s_hi, "=> vCPU-h", q(ep_cpu_s_lo / 3600), q(ep_cpu_s_hi / 3600))
# on-demand re-observation: 20 queries/day x <=40 idle keyframes x 0.1 s
QUERIES_DAY = D("20")
REOBS_FRAMES = D("40")
REOBS_S_PER_FRAME = D("0.1")
reobs_s = QUERIES_DAY * REOBS_FRAMES * REOBS_S_PER_FRAME * DAYS
print("re-observation CPU s/month (cap):", reobs_s, "=> vCPU-h", q(reobs_s / 3600))
total_vcpu_h_lo = (ep_cpu_s_lo + reobs_s) / 3600
total_vcpu_h_hi = (ep_cpu_s_hi + reobs_s) / 3600
print("total vCPU-h/user/month lo/hi:", q(total_vcpu_h_lo), q(total_vcpu_h_hi))

# VM monthly prices (unverified list prices, see doc)
HOURS = D("730")
aws_t3_medium = D("0.0416") * HOURS
aws_ebs_30 = D("30") * D("0.08")
aws_vm = aws_t3_medium + aws_ebs_30
gcp_e2_medium = D("0.033503") * HOURS
gcp_pd_30 = D("30") * D("0.10")
gcp_vm = gcp_e2_medium + gcp_pd_30
EURUSD = D("1.08")  # assumption
hetz_lo = D("3.79") * EURUSD
hetz_hi = D("4.50") * EURUSD
print("AWS t3.medium+30GB gp3 $/mo:", q(aws_t3_medium), "+", q(aws_ebs_30), "=", q(aws_vm))
print("GCP e2-medium+30GB pd $/mo:", q(gcp_e2_medium), "+", q(gcp_pd_30), "=", q(gcp_vm))
print("Hetzner CX22/CX23-class $/mo lo/hi:", q(hetz_lo), q(hetz_hi))
USERS_PER_VM = D("100")
print("per-user VM share @100 users: AWS", q(aws_vm / USERS_PER_VM), "GCP", q(gcp_vm / USERS_PER_VM), "Hetzner", q(hetz_lo / USERS_PER_VM), "-", q(hetz_hi / USERS_PER_VM))
# capacity check: 2 vCPU x 730 h = 1460 vCPU-h; at 25% target utilisation = 365 vCPU-h
cap_vcpu_h = D("2") * HOURS * D("0.25")
print("usable vCPU-h per 2-vCPU VM at 25% util:", q(cap_vcpu_h), "=> users supportable at hi workload:", q(cap_vcpu_h / total_vcpu_h_hi, "1"))

# --- Storage ---
MB_DAY = D("20")
durable_30 = MB_DAY * D("30") / D("1000")  # GB (decimal)
durable_90 = MB_DAY * D("90") / D("1000")
idle_cache_gb = D("0.15")
S3 = D("0.023")
R2 = D("0.015")
B2 = D("0.006")
EBS = D("0.08")
print("durable GB steady-state 30d/90d:", durable_30, durable_90)
for name, rate in (("S3", S3), ("R2", R2), ("B2", B2)):
    print(f"  {name} durable 30d ${q(durable_30*rate)} 90d ${q(durable_90*rate)}")
print("  idle cache 0.15 GB on EBS gp3:", q(idle_cache_gb * EBS), " on S3:", q(idle_cache_gb * S3))
# requests
S3_PUT = D("0.005") / D("1000")
S3_GET = D("0.0004") / D("1000")
R2_A = D("4.50") / D("1000000")
R2_B = D("0.36") / D("1000000")
puts_batched = (EPISODES_DAY + D("24")) * DAYS  # 1 object/episode + hourly idle bundle
puts_perframe = (EPISODES_DAY * D("8") + D("2880")) * DAYS
gets = (QUERIES_DAY * DAYS) + D("200")
print("PUTs/month batched:", puts_batched, "per-frame:", puts_perframe, "GETs:", gets)
print("  S3 PUT cost batched $", q(puts_batched * S3_PUT), " per-frame $", q(puts_perframe * S3_PUT), " GET $", q(gets * S3_GET))
print("  R2 class A batched $", q(puts_batched * R2_A), " per-frame $", q(puts_perframe * R2_A), " class B $", q(gets * R2_B))
# egress
PHOTO_KB = D("100")
photo_serves = QUERIES_DAY * DAYS + D("200")
egress_gb = photo_serves * PHOTO_KB / D("1000000")
AWS_EGRESS = D("0.09")
GCP_EGRESS = D("0.12")
print("photo serves/month:", photo_serves, "egress GB:", q(egress_gb), " AWS $", q(egress_gb * AWS_EGRESS), " GCP $", q(egress_gb * GCP_EGRESS))
# backups
snap = (durable_90 + idle_cache_gb) * D("0.05")
print("EBS snapshot of 90d set $", q(snap))

# --- totals A_b ---
A_b_aws = aws_vm / USERS_PER_VM + durable_90 * S3 + idle_cache_gb * EBS + puts_batched * S3_PUT + gets * S3_GET + egress_gb * AWS_EGRESS + snap
A_b_aws_perframe = A_b_aws - puts_batched * S3_PUT + puts_perframe * S3_PUT
A_b_hetz = hetz_hi / USERS_PER_VM + durable_90 * B2 + idle_cache_gb * D("0.044") * EURUSD + D("0") + D("0") + D("0") + snap
print("A_b AWS (90d, batched) $", q(A_b_aws), " per-frame objects $", q(A_b_aws_perframe))
print("A_b Hetzner+B2 (90d) $", q(A_b_hetz))

# --- Cloud chat ---
CHATS_DAY = D("20")
IN_TOK = D("1500")
OUT_TOK = D("150")
chats_mo = CHATS_DAY * DAYS
in_mtok = chats_mo * IN_TOK / D("1000000")
out_mtok = chats_mo * OUT_TOK / D("1000000")
print("chats/month:", chats_mo, "input MTok:", in_mtok, "output MTok:", out_mtok)
tiers = [
    ("$0.10 / $0.50 class", D("0.10"), D("0.50")),
    ("$0.25 / $2.00 class", D("0.25"), D("2.00")),
    ("$0.30 / $2.50 class", D("0.30"), D("2.50")),
    ("$1.00 / $5.00 class (claude-haiku-4.5 per A-round-B)", D("1.00"), D("5.00")),
    ("$2.00 / $10.00 class (claude-sonnet-5 per A-round-B / CLAUDE.md)", D("2.00"), D("10.00")),
]
chat_costs = {}
for name, pin, pout in tiers:
    c = in_mtok * pin + out_mtok * pout
    chat_costs[name] = c
    print(f"  {name}: {in_mtok}*{pin} + {out_mtok}*{pout} = ${q(c)}  ; with 1 retry worst-case x2 = ${q(c*2)} ; 31-day month = ${q(c*31/30)}")

# --- Hardware amortisation ---
TENURE = D("24")
for name, price in (("mount $25", D("25")), ("mount+cable+powerbank $60", D("60")), ("refurb iPhone $250", D("250")), ("iPhone 16e $599", D("599")), ("mini-PC $200", D("200")), ("glasses Audio $349", D("349")), ("glasses Gen 3 $449", D("449")), ("glasses Display $799", D("799"))):
    print(f"  {name} / 24 mo = ${q(price/TENURE)}")

print()
print("=== Section 3: sensitivity (margin %) ===")
A_rig = D("0")
A_host = D("0.50")
A_host_worst = D("1.10")
A_chat_cheap = A_host + chat_costs["$0.10 / $0.50 class"]
A_chat_haiku = A_host + chat_costs["$1.00 / $5.00 class (claude-haiku-4.5 per A-round-B)"]
A_chat_sonnet = A_host + chat_costs["$2.00 / $10.00 class (claude-sonnet-5 per A-round-B / CLAUDE.md)"]
W_mount = q(D("25") / TENURE)
scenarios = [
    ("(a) Rig, BYOD mount", A_rig, D("0")),
    ("(a) Rig, bundled mount W=1.0417", A_rig, D("25") / TENURE),
    ("(b) Hosted A=0.50", A_host, D("0")),
    ("(b) Hosted worst A=1.10", A_host_worst, D("0")),
    (f"(c) Hosted+chat cheap tier A={q(A_chat_cheap)}", A_chat_cheap, D("0")),
    (f"(c) Hosted+chat $1/$5 tier A={q(A_chat_haiku)}", A_chat_haiku, D("0")),
    (f"(c) Hosted+chat $2/$10 tier A={q(A_chat_sonnet)}", A_chat_sonnet, D("0")),
]
prices = [D("5"), D("10"), D("15")]
for name, A, W in scenarios:
    row = []
    for S in (D("3"), D("8")):
        for P in prices:
            m = margin(P, A, S, W)
            row.append(f"P={P} S={S}: {pct(m)}%")
    print(name)
    for r in row:
        print("   ", r)
    print("    break-even P* S=3:", q(breakeven_price(A, D('3'), W), '0.01'), " S=8:", q(breakeven_price(A, D('8'), W), '0.01'))
    print("    P for 40% margin S=3:", q(price_for_margin(D('0.40'), A, D('3'), W), '0.01'), " S=8:", q(price_for_margin(D('0.40'), A, D('8'), W), '0.01'))

print()
print("=== worked rows (show formula) ===")
for P in prices:
    f = fee(P)
    print(f"P={P}: fee = 0.029*{P} + 0.30 = {q(f)}")
    for name, A, W in scenarios[:1] + scenarios[2:3] + scenarios[5:6]:
        for S in (D("3"), D("8")):
            resid = P - f - A - H - S - W
            print(f"   {name} S={S}: {P} - {q(f)} - {q(A)} - 0.75 - {S} - {q(W)} = {q(resid)} ; /{P} = {pct(resid/P)}%")

print()
print("=== Section 3: fixed-base break-even users ===")
F_lean = D("150")
F_founder = D("4150")
for name, A, W in scenarios:
    print(name)
    for S in (D("3"), D("8")):
        for P in prices:
            contrib = P - fee(P) - A - S - W
            if contrib <= 0:
                print(f"    P={P} S={S}: contribution {q(contrib)} <= 0 -> never")
            else:
                n_lean = (F_lean / contrib).to_integral_value(rounding="ROUND_CEILING")
                n_f = (F_founder / contrib).to_integral_value(rounding="ROUND_CEILING")
                print(f"    P={P} S={S}: contribution {q(contrib)} -> {n_lean} users (F=150) / {n_f} users (F=4150)")

print()
print("=== D-013 check ===")
P = D("25")
print("fee(25) =", q(fee(P)), "; residual with formula fee:", q(P - fee(P) - D('5') - H), "=>", pct((P - fee(P) - D('5') - H) / P), "%")
print("residual with pre-rounded $1.03 fee:", q(P - D('1.03') - D('5') - H), "=>", pct((P - D('1.03') - D('5') - H) / P), "%")
print("H=0.75 equals F_lean/200 users:", q(F_lean / D('200')))
```

## Appendix B: CP3 arithmetic (v1.1)

The tables in §8 were produced by the script below (Python 3, `decimal` only, no floats). Run it with `python3 -I appendix_b.py` after pasting it to a file; it prints the FLOP sanity check, the compute, capacity and storage lines, the `A_b` and margin deltas, the one-time costs and the CP4 exposure.

```python
"""PAM FINANCE.md v1.1 Appendix B: CP3 identity-stage arithmetic. Decimal only; no floats.

Every input is an assumption [A], a design parameter [D] or an unverified list price
[Q-UNVERIFIED]; see docs/FINANCE.md section 8 for labels and sources.
"""
from decimal import Decimal as D, getcontext, ROUND_HALF_UP

getcontext().prec = 28


def q(x, places="0.0001"):
    return x.quantize(D(places), rounding=ROUND_HALF_UP)


def pct(x):
    return (x * 100).quantize(D("0.01"), rounding=ROUND_HALF_UP)


print("=== B.1 FLOP sanity check for ViT-S/14 at 224 px (architecture from MODEL_CARD.md) ===")
DIM = D("384")        # [D] MODEL_CARD.md: embedding dimension 384
LAYERS = D("12")      # [A] standard ViT-S depth (not printed in the model card)
MLP_RATIO = D("4")    # [A] standard ViT-S MLP ratio
PATCH = D("14")       # [D] MODEL_CARD.md: patch size 14
IMG = D("224")
n_patches = (IMG / PATCH) ** 2          # 16 x 16 = 256
N = n_patches + 1                       # + CLS token = 257
linear_per_layer = (D("3") + D("1") + D("2") * MLP_RATIO) * N * DIM * DIM   # qkv + proj + 2 MLP matmuls
attn_per_layer = D("2") * N * N * DIM                                        # QK^T and AV
patch_embed = n_patches * (D("3") * PATCH * PATCH) * DIM
gmacs_linear = (linear_per_layer * LAYERS + patch_embed) / D("1e9")
gmacs_attn = attn_per_layer * LAYERS / D("1e9")
gmacs_total = gmacs_linear + gmacs_attn
gflop_total = gmacs_total * 2
print(f"tokens N={N}; linear GMACs (incl. patch embed) {q(gmacs_linear, '0.001')}; attention GMACs {q(gmacs_attn, '0.001')}; total {q(gmacs_total, '0.001')} GMACs = {q(gflop_total, '0.001')} GFLOP")
# cross-check against timm's published 29.46 GMACs at 518 px (fvcore count, attention matmuls excluded)
IMG518 = D("518")
n518 = (IMG518 / PATCH) ** 2            # 37 x 37 = 1369
N518 = n518 + 1
linear518 = ((D("3") + D("1") + D("2") * MLP_RATIO) * N518 * DIM * DIM * LAYERS + n518 * (D("3") * PATCH * PATCH) * DIM) / D("1e9")
print(f"same formula at 518 px, linear only: {q(linear518, '0.01')} GMACs vs timm CSV 29.46 GMACs (fetched 2026-10-09)")
for gflops in (D("50"), D("100"), D("200")):
    print(f"  at {gflops} GFLOP/s sustained fp32 -> {q(gflop_total / gflops * 1000, '1')} ms per crop")

print()
print("=== B.2 CP3 compute per user-month, hosted variant ===")
EPISODES_DAY = D("50")   # [D]
DAYS = D("30")           # [A]
episodes_month = EPISODES_DAY * DAYS
cases = [
    ("low:  2 crops x 60 ms", D("2"), D("60")),
    ("mid:  3 crops x 100 ms", D("3"), D("100")),
    ("high: 4 crops x 150 ms", D("4"), D("150")),
    ("pessimistic: 4 crops x 300 ms (shared/burstable vCPU)", D("4"), D("300")),
]
AWS_VCPU_H = D("0.0416") / D("2")                 # t3.medium $/h over 2 vCPU [Q-UNVERIFIED]
HETZ_VCPU_H = D("4.50") * D("1.08") / D("2") / D("730")   # CX-class EUR 4.50 x 1.08 / 2 vCPU / 730 h [Q-UNVERIFIED]
print(f"vCPU-hour price: AWS t3.medium ${q(AWS_VCPU_H, '0.00001')}  Hetzner ${q(HETZ_VCPU_H, '0.00001')}")
V1_EP_LO, V1_EP_HI = D("0.3"), D("1.0")           # v1 write-path budget s/episode (localizer + DINOv2)
results = {}
for name, crops, ms in cases:
    s_per_ep = crops * ms / D("1000")
    cpu_s = episodes_month * s_per_ep
    vcpu_h = cpu_s / D("3600")
    results[name] = vcpu_h
    print(f"{name}: {s_per_ep} s/episode x {episodes_month} episodes = {cpu_s} CPU-s = {q(vcpu_h)} vCPU-h; AWS ${q(vcpu_h * AWS_VCPU_H)}  Hetzner ${q(vcpu_h * HETZ_VCPU_H)}; localizer headroom under the 1.0 s v1 cap: {q(V1_EP_HI - s_per_ep, '0.01')} s")

print()
print("=== B.3 Capacity check (v1: 100 users per 2-vCPU VM, 25 % utilisation) ===")
HOURS = D("730")
v1_total_hi = D("1.0833")                          # v1 section 2.2 total vCPU-h/user-month, high
usable_25 = D("2") * HOURS * D("0.25")
usable_t3_baseline = D("2") * HOURS * D("0.20")    # t3.medium baseline 20 % per vCPU [Q-UNVERIFIED]
for label, extra in (("CP3 inside the v1 budget (no addition)", D("0")),
                     ("CP3 high added on top of v1 high", results["high: 4 crops x 150 ms"]),
                     ("CP3 pessimistic added on top of v1 high", results["pessimistic: 4 crops x 300 ms (shared/burstable vCPU)"])):
    tot = v1_total_hi + extra
    print(f"{label}: {q(tot)} vCPU-h/user-month -> users per VM at 25 % util {q(usable_25 / tot, '1')}; under a 20 % t3 baseline {q(usable_t3_baseline / tot, '1')}")

print()
print("=== B.4 Embedding storage per user-month ===")
EMB_BYTES = D("384") * D("4")                      # [D] 384 float32
ROW_OVERHEAD = D("200")                            # [A] observation_id text, embedder name@version, SQLite record + index
row_bytes = EMB_BYTES + ROW_OVERHEAD
print(f"vector bytes {EMB_BYTES}; row estimate {row_bytes} B")
S3, GP3, SNAP = D("0.023"), D("0.08"), D("0.05")   # [Q-UNVERIFIED]
HETZ_VOL = D("0.044") * D("1.08")
for label, obs_per_ep in (("1 observation/episode", D("1")), ("2 observations/episode (rival regions)", D("2")), ("every crop stored (4/episode; not the design)", D("4"))):
    rows_month = episodes_month * obs_per_ep
    mb_month = rows_month * row_bytes / D("1e6")
    gb_90 = rows_month * 3 * row_bytes / D("1e9")
    print(f"{label}: {rows_month} rows/month = {q(mb_month, '0.01')} MB/month; 90-day steady state {q(gb_90 * 1000, '0.1')} MB -> gp3 ${q(gb_90 * GP3, '0.00001')}  S3 ${q(gb_90 * S3, '0.00001')}  Hetzner volume ${q(gb_90 * HETZ_VOL, '0.00001')}  snapshot ${q(gb_90 * SNAP, '0.00001')}")
bank_bytes = D("32") * EMB_BYTES
print(f"per-item bank cap: 32 x {EMB_BYTES} = {bank_bytes} B = {q(bank_bytes / 1024, '0.1')} KiB per item; 10 items {q(bank_bytes * 10 / 1024, '0.1')} KiB; 200 items {q(bank_bytes * 200 / D('1e6'), '0.01')} MB")
keyframe_bytes_per_ep = D("20000000") / EPISODES_DAY
print(f"share of keyframe bytes: {row_bytes} / {keyframe_bytes_per_ep} per episode = {pct(row_bytes / keyframe_bytes_per_ep)} %")

print()
print("=== B.5 Effect on A_b and the P=10/S=3 hosted margin ===")
A_b_v1 = D("0.4972")
storage_add = D("0.00139") + D("0.00087")          # 2 obs/episode, gp3 + snapshot (worst design-consistent case)
compute_hi = results["high: 4 crops x 150 ms"] * AWS_VCPU_H
compute_pess = results["pessimistic: 4 crops x 300 ms (shared/burstable vCPU)"] * AWS_VCPU_H
FEE10 = D("0.029") * 10 + D("0.30")
for label, add in (("storage + snapshot only (compute inside v1 budget)", storage_add),
                   ("fully additive, high compute", storage_add + compute_hi),
                   ("fully additive, pessimistic compute", storage_add + compute_pess)):
    A = A_b_v1 + add
    m = (D("10") - FEE10 - A - D("0.75") - D("3")) / D("10")
    print(f"{label}: +${q(add)} -> A_b = {q(A)}; P=10 S=3 margin {pct(m)} % (v1: 51.60 % at A_b=0.50)")

print()
print("=== B.6 One-time costs and the conditional per-household calibration ===")
ENG_H = D("75")      # [A] loaded engineering hour
SUP_H = D("19.20")   # [A] loaded support hour (v1 section 3.1 heavy case)
onnx = (D("2") * ENG_H, D("4") * ENG_H)
print(f"ONNX export + verification + hash/licence row: 2-4 h x ${ENG_H} + 1 h oversight = ${onnx[0] + ENG_H} - ${onnx[1] + ENG_H}")
cute = (D("1") * ENG_H + D("4") * ENG_H, D("1") * ENG_H + D("8") * ENG_H)
print(f"CUTE calibration (licence $0, CC BY 4.0): 1 h acquisition/attribution + 4-8 h calibrate/evaluate/approve = ${cute[0]} - ${cute[1]}")
own = D("10") * D("1") * SUP_H + D("4") * ENG_H
print(f"Own-footage pilot calibration, global, one-time: 10 households x 1 h x ${SUP_H} + 4 h x ${ENG_H} = ${q(own, '0.01')}")
total_lo = onnx[0] + ENG_H + cute[0] + own
total_hi = onnx[1] + ENG_H + cute[1] + own
for users in (D("100"), D("648"), D("1000")):
    um = users * D("24")
    print(f"  one-time total ${q(total_lo, '0.01')}-${q(total_hi, '0.01')} amortised over {users} households x 24 months = ${q(total_lo / um)} - ${q(total_hi / um)} per user-month")
per_hh_min = (D("45"), D("60"))
for mins in per_hh_min:
    once = mins / D("60") * SUP_H
    monthly = once / D("12")
    print(f"IF per-household calibration were required: {mins} min support at onboarding = ${q(once, '0.01')} once = ${q(monthly)} per user-month over a 12-month tenure = {pct(monthly / D('10'))} margin points at P=10")
calib_imgs = D("20000")
print(f"calibration-set embedding compute (bound): {calib_imgs} images x 0.15 s = {calib_imgs * D('0.15') / 60} CPU-minutes on a laptop, $0")

print()
print("=== B.7 Bounds that existing caps already give, and the CP4 exposure ===")
HARD_EP_DAY = D("200")   # cap 2 hard cap, section 5
crops_day_hard = HARD_EP_DAY * D("4")
print(f"cap 2 hard 200 episodes/day x 4 crops = {crops_day_hard} crops/day x 0.15 s = {crops_day_hard * D('0.15')} CPU-s/day = {q(crops_day_hard * D('0.15') * DAYS / 3600)} vCPU-h/month (the most CP3 compute any household can cost under cap 2)")
# re-embedding the retained set after an embedder version change (one-time per change)
for rows in (D("4500"), D("9000")):
    print(f"re-embed {rows} retained rows after an embedder version change: {q(rows * D('0.06') / 60, '0.1')}-{q(rows * D('0.15') / 60, '0.1')} CPU-min per household; x100 households per VM = {q(rows * D('0.06') * 100 / 3600, '0.1')}-{q(rows * D('0.15') * 100 / 3600, '0.1')} CPU-h")
# CP4 forward flag: arrival-time DINOv2-S indexing of every idle frame at 518 px (MEMORY review E), NOT a CP3 cost
IDLE_DAY = D("2880")
for mult, ms in ((D("4"), D("60")), (D("6"), D("150"))):
    s_frame = mult * ms / D("1000")
    cpu_s_day = IDLE_DAY * s_frame
    vcpu_h = cpu_s_day * DAYS / D("3600")
    tot = v1_total_hi + vcpu_h
    print(f"CP4 arrival indexing at 518 px, {s_frame} s/frame x {IDLE_DAY} idle frames/day: {cpu_s_day} CPU-s/day = {q(vcpu_h, '0.01')} vCPU-h/user-month; users per VM at 25 % util would be {q(usable_25 / tot, '1')}")
```

## Appendix C: CP4 arithmetic (v1.2)

The tables in §9 were produced by the script below (Python 3, `decimal` only, no floats). Run it with `python3 -I appendix_c.py` after pasting it to a file; it prints the idle-cache cap check, the landmark and packet byte counts, the steady-state storage grid, the re-observation compute grid and the proposed caps, the per-frame object-storage contrast, the `A_b` deltas for both price stacks, the v1.2 sensitivity rows and the `VACUUM INTO` headroom. The two [M-sandbox] inputs it consumes (1,869 / 986 B per hand of landmark JSON, 8.5 ms per registration + blur pair) were measured by a separate sandbox script that imported `perception/episode.py` and `perception/motion.py` from `77b769e` and timed the localizer's OpenCV calls on synthetic 1280×720 frames; its outputs are quoted in §9 and are not on-device measurements.

```python
"""PAM FINANCE.md v1.2 Appendix C: CP4 arithmetic (idle cache, re-observation, retention,
erasure). Decimal only; no floats.

Every input is an assumption [A], a design parameter [D] from BUILD_PLAN.md "CP4 in detail",
a code constant [M-code], a sandbox measurement [M-sandbox] (Intel Xeon 2.1 GHz vCPU, NOT the
laptop) or an unverified list price [Q-UNVERIFIED]; see docs/FINANCE.md section 9 for labels.
"""
from decimal import Decimal as D, getcontext, ROUND_HALF_UP, ROUND_CEILING

getcontext().prec = 28


def q(x, places="0.0001"):
    return x.quantize(D(places), rounding=ROUND_HALF_UP)


def pct(x):
    return (x * 100).quantize(D("0.01"), rounding=ROUND_HALF_UP)


KiB, MiB = D(1024), D(1024) ** 2
MB, GB = D("1e6"), D("1e9")

print("=== C.1 Idle cache: which cap binds ===")
IDLE_PER_DAY = D(2880)            # [D] IDLE_MAX_PER_DAY
IDLE_TARGET = 64 * KiB            # [D] target <= 64 KiB (JPEG q0.5)
IDLE_BODY_CAP = 256 * KiB         # [D] MAX_IDLE_BYTES
IDLE_CACHE_CAP = 200 * MiB        # [D] IDLE_CACHE_BYTES
for label, per_frame in (("64 KiB target", IDLE_TARGET), ("64 KB decimal", D(64000)), ("103 KiB (1080p synthetic, M-sandbox)", D(103) * KiB), ("256 KiB body cap", IDLE_BODY_CAP)):
    day_bytes = IDLE_PER_DAY * per_frame
    frames_in_cap = (IDLE_CACHE_CAP / per_frame).to_integral_value(rounding="ROUND_FLOOR")
    hours = frames_in_cap * 30 / 3600
    print(f"{label}: 2,880 x {per_frame} B = {day_bytes:,} B = {q(day_bytes / MiB, '0.1')} MiB = {q(day_bytes / MB, '0.1')} MB vs cap {IDLE_CACHE_CAP:,} B (200 MiB = {q(IDLE_CACHE_CAP / MB, '0.1')} MB): {'count cap binds (under)' if day_bytes <= IDLE_CACHE_CAP else 'BYTE CAP BINDS'}; frames held at the byte cap {frames_in_cap} = {q(hours, '0.1')} h of idle coverage")
mean_binding = IDLE_CACHE_CAP / IDLE_PER_DAY
print(f"byte cap binds when the mean idle frame exceeds {q(mean_binding, '0.1')} B = {q(mean_binding / KiB, '0.1')} KiB")
CAMERA_H = D(8)                   # [A] camera-on hours/day in the worked example
idle_8h = CAMERA_H * 3600 / 30
print(f"worked example {CAMERA_H} h camera-on: {idle_8h} idle frames/day x 64 KiB = {q(idle_8h * IDLE_TARGET / MiB, '0.1')} MiB in the 24 h cache")

print()
print("=== C.2 Landmark bytes per packet and the 72 h reduction ===")
# [M-sandbox] measured with the real schema classes, compact JSON, 6-decimal floats:
PT = D(41)                        # one {"x":..,"y":..,"z":..} point
HAND_WORLD = D(1869)              # one hand with world_landmarks (21 + 21 points + bbox + handedness)
HAND_NOWORLD = D(986)
SAMPLE_OVERHEAD = D(50)           # frame_id + t_ms + keys per sample
floats_max = D(128) * 2 * 21 * 3
print(f"floats, image landmarks only, max: 128 x 2 x 21 x 3 = {floats_max:,}; x ~{PT}/3 B per float as JSON = {q(floats_max * PT / 3 / KiB, '0.1')} KiB; measured compact JSON:")
for label, samples, hands, hb in (("worst: 128 samples x 2 hands, world_landmarks present", D(128), D(2), HAND_WORLD),
                                  ("worst without world_landmarks", D(128), D(2), HAND_NOWORLD),
                                  ("typical: 75 samples (10 Hz x 7.5 s [A]) x 1 hand, world present", D(75), D(1), HAND_WORLD)):
    b = samples * (SAMPLE_OVERHEAD + hands * hb)
    print(f"  {label}: {b:,} B = {q(b / KiB, '0.1')} KiB")
LM_WORST = D(128) * (SAMPLE_OVERHEAD + 2 * HAND_WORLD)
LM_TYP = D(75) * (SAMPLE_OVERHEAD + 1 * HAND_WORLD)
# landmark_summary [A]: per sample frame_id+t_ms (~60 B) + per hand {hand_bbox 4 floats, busy, basis} (~100 B)
SUM_SAMPLE, SUM_HAND = D(60), D(100)
SUM_WORST = D(128) * (SUM_SAMPLE + 2 * SUM_HAND)
SUM_TYP = D(75) * (SUM_SAMPLE + 1 * SUM_HAND)
print(f"landmark_summary after 72 h [A]: worst {SUM_WORST:,} B ({q(SUM_WORST / KiB, '0.1')} KiB), typical {SUM_TYP:,} B ({q(SUM_TYP / KiB, '0.1')} KiB); reduction removes {pct(1 - SUM_WORST / LM_WORST)} % / {pct(1 - SUM_TYP / LM_TYP)} % of landmark bytes")

print()
print("=== C.3 Packet bytes as stored (episode_revisions.packet = raw JSON, base64 JPEGs) ===")
KF_RAW_TYP, KF_RAW_HI = D(50000), D(100000)   # [A] v1 50 KB; synthetic q72 720p worst 84 KiB
KF_N = D(8)                                   # [D] max keyframes
BURST_N, BURST_RAW = D(10), D(8000)           # [D] max burst; [A] 320x180 grey ~8 KB (synthetic worst 13-18 KiB)
B64 = D(4) / D(3)
JSON_OVERHEAD = D(2000)
def packet(kf_raw, lm):
    return KF_N * kf_raw * B64 + BURST_N * BURST_RAW * B64 + lm + JSON_OVERHEAD
P_TYP = packet(KF_RAW_TYP, LM_TYP)
P_TYP_R = packet(KF_RAW_TYP, SUM_TYP)
P_HI = packet(KF_RAW_HI, LM_WORST)
P_HI_R = packet(KF_RAW_HI, SUM_WORST)
print(f"keyframes 8 x 50 KB raw -> base64 {q(KF_N * KF_RAW_TYP * B64 / 1000, '0.1')} KB; burst 10 x 8 KB -> {q(BURST_N * BURST_RAW * B64 / 1000, '0.1')} KB")
print(f"typical packet {q(P_TYP / 1000, '0.1')} KB -> after 72 h reduction {q(P_TYP_R / 1000, '0.1')} KB; high packet {q(P_HI / 1000, '0.1')} KB -> {q(P_HI_R / 1000, '0.1')} KB; v1 assumed 400 KB raw keyframes/episode; cap 4 MiB = {4 * MiB / 1000} KB")
EP_DAY = D(50)
print(f"per day at {EP_DAY} episodes: typical {q(EP_DAY * P_TYP / MB, '0.1')} MB/day (v1: 20 MB/day); high {q(EP_DAY * P_HI / MB, '0.1')} MB/day; reduction saves {q(EP_DAY * (P_TYP - P_TYP_R) / MB, '0.1')} / {q(EP_DAY * (P_HI - P_HI_R) / MB, '0.1')} MB/day")

print()
print("=== C.4 Durable storage per user at steady state, retention R, with the 72 h reduction ===")
EMB_ROW = D(1736)                 # [A] section 8.2
OBS_PER_EP = D(2)                 # [A] section 8.2
OBS_ROW = D(1500)                 # [A] local_observations.record JSON
ITEMS_LO, ITEMS_HI = D(10), D(30) # [A] tracked items
def durable(R, p_full, p_red, frames_day, promo_frac, promo_rows_per_frame, promoted_retained=True):
    days_full = min(D(3), R)
    packets = EP_DAY * (days_full * p_full + (R - days_full) * p_red)
    emb = EP_DAY * OBS_PER_EP * EMB_ROW * R
    obs = EP_DAY * OBS_PER_EP * OBS_ROW * R
    promo_frames = frames_day * promo_frac
    promo_bytes = promo_frames * IDLE_TARGET * (R if promoted_retained else D(365))
    promo_rows = promo_frames * promo_rows_per_frame * (OBS_ROW + EMB_ROW) * (R if promoted_retained else D(365))
    return packets, emb, obs, promo_bytes, promo_rows
rows = []
for R in (D(30), D(90)):
    for frames_day, fl in ((idle_8h, "8 h"), (IDLE_PER_DAY, "24 h")):
        for promo_frac, pl, rpf in ((D(0), "0 %", D(0)), (D("0.10"), "10 %", D(1)), (D(1), "100 % (design as written, static scene, 30 items)", ITEMS_HI)):
            p, e, o, pb, pr = durable(R, P_TYP, P_TYP_R, frames_day, promo_frac, rpf)
            tot = p + e + o + pb + pr
            print(f"R={R} d, camera {fl}, promoted {pl}: packets {q(p / GB, '0.001')} GB + emb {q(e / MB, '0.1')} MB + obs {q(o / MB, '0.1')} MB + promoted frames {q(pb / GB, '0.001')} GB + promoted rows {q(pr / GB, '0.001')} GB = {q(tot / GB, '0.001')} GB (at R, if promoted frames follow episodes_days)")
# promoted frames capped at <= 1 promotion per item per hour (proposal), 30 items, frames shared: <= 24 frames/day
PROMO_CAP_FRAMES = D(24)
for R in (D(30), D(90)):
    pb = PROMO_CAP_FRAMES * IDLE_TARGET * R
    pr = ITEMS_HI * 24 * (OBS_ROW + EMB_ROW) * R
    print(f"R={R} d, promotion capped at 1/item/h (30 items): frames {q(pb / MB, '0.1')} MB + rows {q(pr / MB, '0.1')} MB")
print(f"promoted frames NOT retained (never expires, as written): 10 % of 2,880/day x 64 KiB = {q(D('0.1') * IDLE_PER_DAY * IDLE_TARGET / MB, '0.1')} MB/day = {q(D('0.1') * IDLE_PER_DAY * IDLE_TARGET * 365 / GB, '0.2')} GB/year, unbounded with tenure")
print(f"high-size packets (100 KB keyframes, worst landmarks) at R=90: {q(durable(D(90), P_HI, P_HI_R, idle_8h, D(0), D(0))[0] / GB, '0.2')} GB packets; at R=30: {q(durable(D(30), P_HI, P_HI_R, idle_8h, D(0), D(0))[0] / GB, '0.2')} GB")

print()
print("=== C.5 Re-observation compute ===")
PAIR_DIFF = {"sandbox incl. decodes [M-sandbox]": D("0.0085"), "laptop-class [A]": D("0.010"), "burstable vCPU, 2x [A]": D("0.020")}
EMBED = {"low": D("0.050"), "high": D("0.150"), "pessimistic": D("0.300")}   # [A] section 8
LIMIT = D(16)
print(f"worst case per worker pass (limit=16): diff-only 16 x 20 ms = {q(LIMIT * PAIR_DIFF['burstable vCPU, 2x [A]'], '0.01')} s; diff + embed high = {q(LIMIT * (PAIR_DIFF['burstable vCPU, 2x [A]'] + EMBED['high']), '0.01')} s; + embed pessimistic = {q(LIMIT * (PAIR_DIFF['burstable vCPU, 2x [A]'] + EMBED['pessimistic']), '0.01')} s")
AWS_VCPU_H = D("0.0416") / 2
HETZ_VCPU_H = D("4.50") * D("1.08") / 2 / 730
DAYS = D(30)
for frames_day, fl in ((idle_8h, "8 h"), (IDLE_PER_DAY, "24 h")):
    for items in (ITEMS_LO, ITEMS_HI):
        pairs = frames_day * items
        diff_s = pairs * PAIR_DIFF["laptop-class [A]"]
        emb_s = pairs * (PAIR_DIFF["laptop-class [A]"] + EMBED["high"])
        for label, s in (("diff-only", diff_s), ("diff + embed 150 ms on every pair (static scene)", emb_s)):
            vh = s * DAYS / 3600
            print(f"camera {fl}, {items} items: {pairs:,} pairs/day, {label}: {q(s, '1')} CPU-s/day = {pct(s / 86400)} % of one core; {q(vh, '0.1')} vCPU-h/user-month = AWS ${q(vh * AWS_VCPU_H, '0.001')} / Hetzner ${q(vh * HETZ_VCPU_H, '0.001')}")
print("proposed caps: frame-level motion gate (0.5-2 ms/frame), diff on changed frames only (assume <= 10 % of idle frames change [A]), promotion/embed <= 1 per item per hour, daily budget 300 CPU-s")
gate_s = IDLE_PER_DAY * D("0.002")
changed_pairs = IDLE_PER_DAY * D("0.10") * ITEMS_HI
diff_s = changed_pairs * PAIR_DIFF["laptop-class [A]"]
emb_s = ITEMS_HI * 24 * EMBED["high"]
capped = gate_s + diff_s + emb_s
print(f"  24 h, 30 items under the proposed caps: gate {q(gate_s, '0.1')} + diff {q(diff_s, '0.1')} + embeds {q(emb_s, '0.1')} = {q(capped, '0.1')} CPU-s/day = {q(capped * DAYS / 3600, '0.2')} vCPU-h/user-month = AWS ${q(capped * DAYS / 3600 * AWS_VCPU_H, '0.004')}")
BUDGET_S = D(300)
print(f"  daily budget 300 CPU-s = {q(BUDGET_S * DAYS / 3600, '0.2')} vCPU-h/user-month = AWS ${q(BUDGET_S * DAYS / 3600 * AWS_VCPU_H, '0.0001')} / Hetzner ${q(BUDGET_S * DAYS / 3600 * HETZ_VCPU_H, '0.0001')}; duty cycle {pct(BUDGET_S / 86400)} % of one core (laptop idle-capable)")
v1_reobs = D("0.6667")
print(f"  v1 cap 7 line was {v1_reobs} vCPU-h (query-time scan); budget replaces it: net +{q(BUDGET_S * DAYS / 3600 - v1_reobs, '0.01')} vCPU-h")

print()
print("=== C.6 Hosted object storage IF idle frames were uploaded per frame (they must not be) ===")
S3_PUT, S3_GET, S3 = D("0.005") / 1000, D("0.0004") / 1000, D("0.023")
R2_A = D("4.50") / D("1e6")
for frames_day, fl in ((idle_8h, "8 h"), (IDLE_PER_DAY, "24 h")):
    puts = frames_day * DAYS
    print(f"camera {fl}: {puts:,} PUTs/month = S3 ${q(puts * S3_PUT)} / R2 class A ${q(puts * R2_A)}; storage at the 200 MiB cap on S3 ${q(IDLE_CACHE_CAP / GB * S3)}; GETs for re-observation (1 per frame, cached per pass) ${q(puts * S3_GET)}; total S3 ${q(puts * S3_PUT + IDLE_CACHE_CAP / GB * S3 + puts * S3_GET)} vs batched-objects line $0.0111")

print()
print("=== C.7 Hosted per-user-month delta on A_b (AWS and Hetzner/B2 stacks, all prices [Q-UNVERIFIED]) ===")
A_b_v1 = {"AWS": D("0.4972"), "Hetzner": D("0.1640")}
STACK = {  # object $/GB, block $/GB, snapshot $/GB, vCPU-h $, VM disk $/GB (AWS: gp3; Hetzner: volume EUR 0.044 x 1.08)
    "AWS": (D("0.023"), D("0.08"), D("0.05"), AWS_VCPU_H, D("0.08")),
    "Hetzner": (D("0.006"), D("0.044") * D("1.08"), D("0.05"), HETZ_VCPU_H, D("0.044") * D("1.08")),
}
v1_packets_gb, v1_idle_gb, V1_DISK = D("1.8"), D("0.15"), D(30)
def scenario(label, R, p_full, p_red, promo_frames_day, promo_rows_day, reobs_vcpu_h, disk_gb_vm, idle_gb, stack="AWS"):
    obj, blk, snp, vcpu, dsk = STACK[stack]
    packets_gb = EP_DAY * (min(D(3), R) * p_full + (R - min(D(3), R)) * p_red) / GB
    db_gb = (EP_DAY * OBS_PER_EP * (EMB_ROW + OBS_ROW) * R + promo_frames_day * IDLE_TARGET * R + promo_rows_day * (OBS_ROW + EMB_ROW) * R) / GB + idle_gb
    s3 = packets_gb * obj
    gp3 = db_gb * blk
    snap = (packets_gb + db_gb) * snp
    compute = reobs_vcpu_h * vcpu
    disk = (disk_gb_vm - V1_DISK) * dsk / 100   # extra VM disk over v1's 30 GB, shared by 100 users (v1 counted 30 GB inside the VM price)
    v1_lines = v1_packets_gb * obj + v1_idle_gb * blk + (v1_packets_gb + v1_idle_gb) * snp + v1_reobs * vcpu
    new_lines = s3 + gp3 + snap + compute + disk
    delta = new_lines - v1_lines
    A = A_b_v1[stack] + delta
    m10 = (D(10) - (D("0.029") * 10 + D("0.30")) - A - D("0.75") - 3) / 10
    print(f"[{stack}] {label}: packets {q(packets_gb, '0.01')} GB (object ${q(s3)}), DB on block {q(db_gb, '0.01')} GB (${q(gp3)}), snapshot ${q(snap)}, re-obs compute ${q(compute)}, extra VM disk ({disk_gb_vm} GB vs 30) share ${q(disk)}; v1 same lines ${q(v1_lines)} -> new ${q(new_lines)}; delta {'+' if delta >= 0 else ''}{q(delta)} -> A_b {q(A)}; P=10 S=3 hosted margin {pct(m10)} %")
    return delta, A
results = {}
for stack in ("AWS", "Hetzner"):
    results[stack, "exp90"] = scenario("expected: R=90, 8 h camera, typical packets, promotion <= 1/item/h, re-obs budget 2.5 vCPU-h, 80 GB VM disk", D(90), P_TYP, P_TYP_R, PROMO_CAP_FRAMES, ITEMS_HI * 24, D("2.5"), D(80), D("0.21"), stack)
    results[stack, "exp30"] = scenario("expected: R=30, otherwise the same", D(30), P_TYP, P_TYP_R, PROMO_CAP_FRAMES, ITEMS_HI * 24, D("2.5"), D(80), D("0.21"), stack)
    results[stack, "cp4only"] = scenario("CP4-only at R=90 (v1 20 MB/day packets kept, to isolate CP4 from the CP2 packet-size correction)", D(90), D(400000), D(400000), PROMO_CAP_FRAMES, ITEMS_HI * 24, D("2.5"), D(80), D("0.21"), stack)
    results[stack, "worstcap"] = scenario("worst WITH the CP4 caps: high packets, R=90, 24 h camera, promotion capped, budget 2.5 vCPU-h, 120 GB disk", D(90), P_HI, P_HI_R, PROMO_CAP_FRAMES, ITEMS_HI * 24, D("2.5"), D(120), D("0.21"), stack)
    results[stack, "uncapped"] = scenario("worst WITHOUT caps: high packets, R=90, 24 h, 30 items, every frame promoted + embedded, 200 GB disk", D(90), P_HI, P_HI_R, IDLE_PER_DAY, IDLE_PER_DAY * ITEMS_HI, D("115.2"), D(200), D("0.21"), stack)
    print(f"[{stack}] retention 30 vs 90 (expected): ${q(results[stack, 'exp90'][0] - results[stack, 'exp30'][0])} per user-month")

print()
print("=== C.8 Sensitivity rows at the v1.2 A_b (hosted rounded up) ===")
FEE_RATE, FEE_FIXED, H = D("0.029"), D("0.30"), D("0.75")
def fee(P):
    return FEE_RATE * P + FEE_FIXED
def margin(P, A, S):
    return (P - fee(P) - A - H - S) / P
A_new = D("0.72")
A_worst_tab = D("1.10")
chat_cheap, chat_haiku, chat_sonnet = D("0.135"), D("1.35"), D("2.70")
for label, A in (("(b) Hosted v1.2 A=0.72", A_new), ("(b) Hosted worst A=1.10 (unchanged)", A_worst_tab),
                 (f"(c) + chat cheap A={A_new + chat_cheap}", A_new + chat_cheap), (f"(c) + chat $1/$5 A={A_new + chat_haiku}", A_new + chat_haiku), (f"(c) + chat $2/$10 A={A_new + chat_sonnet}", A_new + chat_sonnet)):
    cells = [f"{pct(margin(P, A, S))} %" for S in (D(3), D(8)) for P in (D(5), D(10), D(15))]
    pstar = [(FEE_FIXED + A + H + S) / (1 - FEE_RATE) for S in (D(3), D(8))]
    p40 = [(FEE_FIXED + A + H + S) / (1 - FEE_RATE - D("0.40")) for S in (D(3), D(8))]
    print(f"{label}: " + " | ".join(cells) + f" ; P* S3 ${q(pstar[0], '0.01')} S8 ${q(pstar[1], '0.01')}; P@40% S3 ${q(p40[0], '0.01')} S8 ${q(p40[1], '0.01')}")
    for S in (D(3), D(8)):
        for P in (D(5), D(10), D(15)):
            contrib = P - fee(P) - A - S
            if contrib <= 0:
                print(f"    P={P} S={S}: contribution {q(contrib)} -> never")
            else:
                print(f"    P={P} S={S}: contribution {q(contrib)} -> {(D(150) / contrib).to_integral_value(rounding=ROUND_CEILING)} users (F=150) / {(D(4150) / contrib).to_integral_value(rounding=ROUND_CEILING)} users (F=4150)")
print(f"summary subtotal at P=10 (no S): hosted v1.2 {q(fee(D(10)) + A_new + H)} ; +S=3 {q(fee(D(10)) + A_new + H + 3)} ; +S=8 {q(fee(D(10)) + A_new + H + 8)}")

print()
print("=== C.9 Erasure / VACUUM INTO headroom ===")
for label, hh_db_gb in (("per-household DB, expected (idle at cap + promoted + rows + embeddings)", D("0.21") + (PROMO_CAP_FRAMES * IDLE_TARGET * 90 + (ITEMS_HI * 24 + EP_DAY * OBS_PER_EP) * (OBS_ROW + EMB_ROW) * 90) / GB),
                        ("per-household DB if packets also live in SQLite (the rig), R=90 typical", D("0.21") + (PROMO_CAP_FRAMES * IDLE_TARGET * 90 + (ITEMS_HI * 24 + EP_DAY * OBS_PER_EP) * (OBS_ROW + EMB_ROW) * 90) / GB + EP_DAY * (3 * P_TYP + 87 * P_TYP_R) / GB)):
    print(f"{label}: {q(hh_db_gb, '0.01')} GB -> VACUUM INTO needs 2x = {q(2 * hh_db_gb, '0.01')} GB free; x100 households in ONE multi-tenant file = {q(100 * hh_db_gb, '0.1')} GB -> 2x = {q(200 * hh_db_gb, '0.1')} GB")
```

## Appendix D: CP5 arithmetic (v1.3)

The tables in §10 were produced by the script below (Python 3, `decimal` for money, `json` only to size the telemetry body). Run it with `python3 -I appendix_d.py` after pasting it to a file; it prints the telemetry body size, the rows/bytes/storage/cost grid, the `S` thresholds at P=10, an illustrative month through the §10.2.2 formula, and the line-by-line hosted `A_b` at the CP4 30-day default with the sensitivity rows at that value. The one [M-sandbox] input is the body size it computes itself (656 B compact) from the architect's fixed schema with representative values; it is a size of the schema, not a device measurement.

```python
"""PAM FINANCE.md v1.3 (CP5) arithmetic. Decimal only for money; json only to size the
telemetry row. Every input is an assumption, a plan constant or an unverified list price;
see docs/FINANCE.md section 10 for labels.
"""
import json
from decimal import Decimal as D, getcontext, ROUND_HALF_UP, ROUND_CEILING

getcontext().prec = 28


def q(x, places="0.0001"):
    return x.quantize(D(places), rounding=ROUND_HALF_UP)


def pct(x):
    return (x * 100).quantize(D("0.01"), rounding=ROUND_HALF_UP)


print("=== D.1 Telemetry row size (the plan's POST /api/telemetry body, realistic values) ===")
body = {"schema_version": 1, "device_id": "d" * 32, "session_id": "s" * 32, "t_ms": 1760000000000,
        "clock_anchor": 1760000000000, "window_ms": 60000,
        "counters": {"frames_captured": 600, "frames_analysed": 598, "frames_skipped_busy": 2,
                     "frames_dropped_backpressure": 0, "landmark_results": 598, "landmark_timeouts": 0,
                     "episodes_started": 1, "episodes_finished": 1, "episodes_aborted": 0,
                     "packets_sent": 1, "packets_acked": 1, "idle_sent": 2, "idle_dropped": 0,
                     "gaps": 0, "gap_ms": 0, "bytes_sent": 804864},
        "timing": {"fps_observed": 9.97, "infer_ms_p50": 38.4, "infer_ms_p95": 71.2, "tick_ms_p95": 96.5},
        "settings": {"width": 1280, "height": 720, "frame_rate": 10}}
compact = len(json.dumps(body, separators=(",", ":")).encode())
pretty = len(json.dumps(body).encode())
worst = {**body, "counters": {k: 2**31 - 1 for k in body["counters"]},
         "timing": {k: 99999.99 for k in body["timing"]}}
worst_len = len(json.dumps(worst, separators=(",", ":")).encode())
row_overhead = 64 + 32 + 32 + 8 + 8 + 8 + 40  # profile_id, device_id, session_id, t_ms, received_ms, window_ms, SQLite record+index [A]
print(f"compact JSON body: {compact} B; with default spacing: {pretty} B; every counter at 2^31-1: {worst_len} B")
print(f"stored row = body JSON columns ({compact} B compact) + key columns/overhead ~{row_overhead} B = ~{compact + row_overhead} B; bound used: 2,048 B; body cap 65,536 B")

print()
print("=== D.2 Telemetry rows, bytes, storage, hosted cost ===")
ROW_BOUND, ROW_TYP, CAP = D(2048), D(compact + row_overhead), D(65536)
GB = D(10) ** 9
GP3, SNAP = D("0.08"), D("0.05")      # [Q-UNVERIFIED] v1 rates
HETZ_VOL = D("0.044") * D("1.08")
VCPU_H_AWS = D("0.0416") / 2
for hours, sessions in ((D(8), 1), (D(24), 1)):
    rows_day = hours * 60 + sessions          # one per 60 s + one at stop
    for label, rb in (("bound 2 KB", ROW_BOUND), (f"typical {ROW_TYP} B", ROW_TYP), ("every post at the 64 KiB cap", CAP)):
        day_b = rows_day * rb
        for R in (D(30), D(90)):
            held = day_b * R
            cost = held / GB * (GP3 + SNAP)
            print(f"camera {hours} h/day, {rows_day} rows/day x {label}: {q(day_b / 1000, '0.1')} KB/day; R={R}: {q(held / GB * 1000, '0.1')} MB held -> gp3+snapshot ${q(cost, '0.0001')}/user-month (Hetzner volume+snap ${q(held / GB * (HETZ_VOL + SNAP), '0.0001')})")
posts_month = (D(8) * 60 + 1) * 30
ingest_ms = D(1)  # [A] JSON parse + one INSERT
print(f"ingest CPU at 8 h: {posts_month} POSTs/month x {ingest_ms} ms = {q(posts_month * ingest_ms / 1000, '0.1')} CPU-s = {q(posts_month * ingest_ms / 1000 / 3600, '0.0001')} vCPU-h = ${q(posts_month * ingest_ms / 1000 / 3600 * VCPU_H_AWS, '0.00001')}")
coverage_gets = D(20) * 30 * D(2048)
print(f"Status panel GET /api/coverage: 20/day x 2 KB = {q(coverage_gets / 1000, '0.1')} KB/month egress = ${q(coverage_gets / GB * D('0.09'), '0.00001')} at $0.09/GB")
uplink = (D(8) * 60 + 1) * ROW_BOUND
print(f"phone uplink for telemetry at 8 h: {q(uplink / 1000, '0.1')} KB/day vs ~39,300 KB/day of packets = {pct(uplink / D(39300000))} %")

print()
print("=== D.3 Support: S thresholds at P=10 from the section 3 formula ===")
FEE_RATE, FEE_FIXED, H = D("0.029"), D("0.30"), D("0.75")
def fee(P):
    return FEE_RATE * P + FEE_FIXED
P = D(10)
RATE_LEAN, RATE_HEAVY = D(18), D("19.20")
A_rows = (("(a) rig", D(0)), ("(b) hosted, CP4 30-day default (A_b 0.5413)", D("0.5413")),
          ("(b) hosted at 90 days (A_b 0.72, the section 3 table value)", D("0.72")), ("(b) hosted worst (1.10)", D("1.10")),
          ("(c) + chat cheap tier, 30-day (0.5413+0.135)", D("0.5413") + D("0.135")),
          ("(c) + chat $1/$5 tier, 30-day (0.5413+1.35)", D("0.5413") + D("1.35")),
          ("(c) + chat $2/$10 tier, 30-day (0.5413+2.70)", D("0.5413") + D("2.70")))
for label, A in A_rows:
    s_zero = P - fee(P) - A - H
    s_40 = P * (1 - D("0.40")) - fee(P) - A - H
    print(f"{label}: margin 0 at S = ${q(s_zero, '0.01')} = {q(s_zero / RATE_LEAN * 60, '0.1')} min/household-month at $18/h; 40 % margin at S <= ${q(s_40, '0.01')} = {q(s_40 / RATE_LEAN * 60, '0.1')} min; S=3 is {q(D(3) / RATE_LEAN * 60, '0.1')} min, S=8 is {q(D(8) / RATE_HEAVY * 60, '0.1')} min at $19.20/h")
print("one minute per household-month = $", q(RATE_LEAN / 60, "0.01"), "= ", pct(RATE_LEAN / 60 / P), "margin points at P=10")

print()
print("=== D.4 Worked S from a hypothetical month of the ticket log (format check only) ===")
# households active, minutes by category; onboarding amortised over tenure T months [A]
N = D(10); T = D(12)
ongoing_min = {"setup/mount": 25, "consent questions": 10, "Wi-Fi/TLS": 60, "camera permission": 20,
               "false answer": 30, "missed capture": 40, "erasure request": 5, "other": 10}
onboard_min_total = D(450)  # 10 households x 45 min first contact [A], amortised
M_ongoing = D(sum(ongoing_min.values()))
S = (M_ongoing / N + onboard_min_total / N / T) * RATE_LEAN / 60
print(f"ongoing {M_ongoing} min / {N} households = {q(M_ongoing / N, '0.1')} min; onboarding {onboard_min_total} min / {N} / {T} months = {q(onboard_min_total / N / T, '0.1')} min; S = ${q(S, '0.01')} per household-month (illustrative input, not a measurement)")

print()
print("=== D.5 Hosted A_b at the CP4 30-day default, line by line (section 9.6 R=30 row) ===")
lines = (("VM share, t3.medium at 100 users/VM (write-path compute inside)", D("0.3277"), "[Q-UNVERIFIED] x [A]"),
         ("packet objects, 1.00 GB x $0.023", D("0.0230"), "[A] bytes x [Q-UNVERIFIED]"),
         ("block storage (idle cache at cap, promoted frames, rows), 0.34 GB x $0.08", D("0.0269"), "[D]/[A] x [Q-UNVERIFIED]"),
         ("snapshot of both, 1.34 GB x $0.05", D("0.0669"), "[A] x [Q-UNVERIFIED]"),
         ("re-observation budget, 2.5 vCPU-h net of v1's 0.6667", D("0.0520") - D("0.6667") * VCPU_H_AWS, "[D] budget x [Q-UNVERIFIED]"),
         ("extra VM disk, (80-30) GB x $0.08 / 100", D("0.0400"), "[A] x [Q-UNVERIFIED]"),
         ("PUT requests, batched", D("0.0111"), "[A] x [Q-UNVERIFIED]"),
         ("GET requests", D("0.0003"), "[A] x [Q-UNVERIFIED]"),
         ("egress, photo answers", D("0.0072"), "[A] x [Q-UNVERIFIED]"))
total = D(0)
for label, v, lab in lines:
    total += v
    print(f"  {label}: ${q(v)} {lab}")
print(f"  sum: ${q(total)} (section 9.6 prints 0.5413 from the unrounded C.7 lines)")
A30 = D("0.5413")
for label, A in (("rig", D(0)), ("hosted 30-day", A30), ("hosted 90-day", D("0.72")), ("hosted worst", D("1.10")),
                 ("chat cheap 30-day", A30 + D("0.135")), ("chat $1/$5 30-day", A30 + D("1.35")), ("chat $2/$10 30-day", A30 + D("2.70"))):
    sub = fee(P) + A + H
    m3 = (P - sub - 3) / P
    m8 = (P - sub - 8) / P
    print(f"{label}: A={q(A)} subtotal (no S) {q(sub)} ; +S=3 {q(sub + 3)} margin {pct(m3)} % ; +S=8 {q(sub + 8)} margin {pct(m8)} %")
```
