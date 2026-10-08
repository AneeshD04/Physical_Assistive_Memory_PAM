# PAM finance model v1: cost per user-month, subscription sensitivity, caps

Finance agent, 2026-10-08. Written for the coordinator after CP1 (`fbf6719`), before
CP2 lands. Scope and authority: `BUILD_PLAN.md` §0 ("Finance: unit economics, cost caps
the builders must respect") and §2 ("FINANCE.md v1"). This file proposes; the coordinator
decides. Nothing here is a selected price, a measured margin or a commercial term
(RESEARCH_LOG D-010, D-013, B-17, C-10).

Arithmetic was done with Python `Decimal` (the script is Appendix A of this file; every
row below also shows its formula, so it can be re-run by hand).
The handoff's margin formula (`CONTINUATION_HANDOFF.md` §10) is reused unchanged; see §3.

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

Labels used throughout: **[A]** assumption (ours), **[Q-UNVERIFIED]** quoted list price not
verified in session, **[Q-REPO]** price recorded in this repository's research notes with
its own URL and date, **[M]** measured in this repository (with date and machine),
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

### 2.4 Summary table: cost per user-month by variant

Costs before support, at P=$10 (fee = 0.029 × 10 + 0.30 = 0.59), BYOD hardware:

| Variant | Metered cloud `A` | Fee | `H` | Subtotal (no S, no W) | + S=3 | + S=8 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| (a) Rig | 0.0000 | 0.5900 | 0.7500 | **1.3400** | 4.3400 | 9.3400 |
| (b) Hosted, AWS batched | 0.5000 | 0.5900 | 0.7500 | **1.8400** | 4.8400 | 9.8400 |
| (b) Hosted, worst | 1.1000 | 0.5900 | 0.7500 | 2.4400 | 5.4400 | 10.4400 |
| (c) + chat, cheap tier | 0.6350 | 0.5900 | 0.7500 | **1.9750** | 4.9750 | 9.9750 |
| (c) + chat, $1/$5 tier | 1.8500 | 0.5900 | 0.7500 | 3.1900 | 6.1900 | 11.1900 |
| (c) + chat, $2/$10 tier | 3.2000 | 0.5900 | 0.7500 | 4.5400 | 7.5400 | 12.5400 |

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
rig `10 − 0.59 − 0 − 0.75 − 3 = 5.66 → 56.60 %`; hosted `10 − 0.59 − 0.50 − 0.75 − 3 =
5.16 → 51.60 %`; hosted + $1/$5 chat `10 − 0.59 − 1.85 − 0.75 − 3 = 3.81 → 38.10 %`.

| Variant (A, W) | P=$5 S=3 | P=$10 S=3 | P=$15 S=3 | P=$5 S=8 | P=$10 S=8 | P=$15 S=8 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| (a) Rig, BYOD (A=0, W=0) | 16.10 % | **56.60 %** | **70.10 %** | −83.90 % | 6.60 % | 36.77 % |
| (a) Rig, bundled mount (A=0, W=1.0417) | −4.73 % | 46.18 % | 63.16 % | −104.73 % | −3.82 % | 29.82 % |
| (b) Hosted (A=0.50) | 6.10 % | **51.60 %** | **66.77 %** | −93.90 % | 1.60 % | 33.43 % |
| (b) Hosted worst (A=1.10) = handoff A1.10 | −5.90 % | 45.60 % | 62.77 % | −105.90 % | −4.40 % | 29.43 % |
| (c) + chat cheap tier (A=0.635) | 3.40 % | 50.25 % | 65.87 % | −96.60 % | 0.25 % | 32.53 % |
| (c) + chat $1/$5 tier (A=1.85) | −20.90 % | 38.10 % | 57.77 % | −120.90 % | −11.90 % | 24.43 % |
| (c) + chat $2/$10 tier (A=3.20) | −47.90 % | 24.60 % | 48.77 % | −147.90 % | −25.40 % | 15.43 % |

Break-even price `P* = (0.30 + A + 0.75 + S + W) / 0.971` and the price at which margin
reaches 40 % (`P = (0.30 + A + 0.75 + S + W) / (1 − 0.029 − 0.40)`; 40 % is a
consumer-subscription rule of thumb [A] leaving room for acquisition cost and churn, not a
target the user has set):

| Variant | P* break-even, S=3 | P* S=8 | P at 40 % margin, S=3 | P at 40 %, S=8 |
| --- | ---: | ---: | ---: | ---: |
| (a) Rig, BYOD | $4.17 | $9.32 | **$7.09** | $15.85 |
| (a) Rig, bundled mount | $5.24 | $10.39 | $8.92 | $17.67 |
| (b) Hosted | $4.69 | $9.84 | **$7.97** | $16.73 |
| (b) Hosted worst | $5.30 | $10.45 | $9.02 | $17.78 |
| (c) + chat cheap tier | $4.82 | $9.97 | $8.20 | $16.96 |
| (c) + chat $1/$5 tier | $6.08 | $11.23 | $10.33 | $19.09 |
| (c) + chat $2/$10 tier | $7.47 | $12.62 | $12.70 | $21.45 |

Readings (sensitivity, not forecasts):

1. **$5 is not viable in any variant** once support is counted: best case (rig, BYOD,
   S=3) leaves $0.81 per user-month; any support load above ~$3.80 loses money.
2. **$10 works only if support stays near $3/user-month.** Rig and hosted-without-chat
   sit at 52–57 %; at S=8 all variants are within ±7 % of zero.
3. **$15 keeps at least 24 % at S=8 in every variant except the $2/$10 chat tier**
   (15.43 %), the only configuration where a cloud line, not support, decides the outcome.
4. The difference between rig and hosted is $0.50/user-month (5 points at $10). Hosting
   is not what makes or breaks this product; support and the chat tier are.

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
| (b) Hosted (A=0.50) | 5 | 3 | 1.0550 | 143 | 3,934 |
| (b) Hosted | 10 | 3 | 5.9100 | **26** | **703** |
| (b) Hosted | 15 | 3 | 10.7650 | 14 | 386 |
| (b) Hosted | 10 | 8 | 0.9100 | 165 | 4,561 |
| (b) Hosted | 15 | 8 | 5.7650 | 27 | 720 |
| (c) + chat $1/$5 (A=1.85) | 10 | 3 | 4.5600 | 33 | 911 |
| (c) + chat $1/$5 | 15 | 3 | 9.4150 | 16 | 441 |
| (c) + chat $1/$5 | 10 | 8 | −0.4400 | never | never |
| (c) + chat $1/$5 | 15 | 8 | 4.4150 | 34 | 940 |
| (c) + chat $2/$10 (A=3.20) | 10 | 3 | 3.2100 | 47 | 1,293 |
| (c) + chat $2/$10 | 15 | 3 | 8.0650 | 19 | 515 |
| (c) + chat $2/$10 | 15 | 8 | 3.0650 | 49 | 1,354 |

(Rows with bundled-mount `W` and the cheap chat tier are printed by Appendix A; they
move each count by a few users and do not change the picture.)

Reading: covering infrastructure alone takes a few dozen households at $10–15; covering
one founder's draw takes 400–900 households at $10–15 with lean support, and is
unreachable at $10 if support runs at $8. At 648–703 households the hosted variant needs
7–8 VMs at 100 users/VM; the rig needs 648–703 always-on home laptops kept healthy, which is
where the `S=3` assumption will be tested.

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
