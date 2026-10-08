# PAM first integrated build contract

Coordinator decision, 2026-10-07. This closes the design gate for the first functional software milestone, not the real-model/device/pilot gates. It supersedes conflicting agent proposals for this milestone. Do not expand the research scope while implementing it.

## Required product behavior

- Capture/ingestion/local processing/persistence/catalogue work with every chatbot credential unset. No paid VLM on the new memory write path.
- Authenticated stored-items browser and ordinary text chat. No Deepgram, STT, TTS, voice-agent or microphone integration.
- Local evidence-grounded query responses require no provider key. Optional cloud-chat mode is lazy, explicit and unavailable unless a provider AND a bounded policy are configured. No real paid requests in development/tests.
- Real camera/hand/model capabilities must be accurately reported. Missing hand weights means explicitly labeled manual-mark/fixture mode, NOT automatic hand recognition. The automatic daily-memory capability remains a required subsequent checkpoint, not fulfilled by a simulation.
- Safari lock/background interruptions are coverage gaps. No promise of all-day background capture.

## Shared ownership

A: production code in perception/, including ObjectStore extensions and packet/controller/localizer modules. Preserve old APIs and unaffected regressions. No test/doc files.
B: production server/ plus phone/serve.py. No perception/ or browser files. Preserve old comments; prefer narrow edits or a new memory application module over rewriting unrelated code.
C: new phone/memory.html and phone/assets/ browser modules/styles. Do not edit serve.py, server/, perception/, tests or docs. Existing legacy pages may remain unlinked rather than being deleted.
Tester: all test files/fixtures and checkpoint verdicts. Existing assertions change only with explicit retirement mapping. Documentation lead: CLAUDE/docs and source/provenance logs.
No agent commits, pushes, deletes existing files, touches real credentials/databases or installs new dependencies without coordination.

## Configuration and application boundary

B exposes `server.app.create_app(database_path=None, profile_id='local', processor=None, clock=None, auth_pin=None, chat_provider=None)` and `app`. If splitting into memory_app.py, re-export these without importing the retired application/modules. Import/startup never reads real .env files, contacts, memories or provider credentials from disk, and never constructs a provider client. Environment strings may configure paths/PIN; never log values.

`PAM_OBJECT_DB` configures the database path; tests always supply a temp path. `PAM_AUTH_PIN` (or legacy CAREGIVER_PIN) configures prototype local-service auth. No default PIN. Missing PIN means fail-closed setup required, NOT public access. Chatbot credentials are independent of this local access control.

For this milestone one app instance has a trusted configured profile; no request selects profile/household. Two apps/stores sharing a database must remain isolated. Device_id is recorded from authorized input, not proof of a separately enrolled identity. Do not claim named-caregiver authentication from a shared PIN.

Public static page: GET / serves memory.html. Approved local assets only; no unrestricted StaticFiles root. Legacy agent.html route redirects to the new page or is retired. Local app is the supported combined UI/API entry point.

Auth API consumed by browser and tests:
- GET /api/auth/session -> {authenticated: bool, configured: bool}; public, no private data.
- POST /api/auth/login JSON {pin: string} -> {authenticated: true}; opaque random server-side session, HttpOnly/SameSite=Strict cookie, Secure on HTTPS, finite expiry, rate-limited attempts.
- POST /api/auth/logout -> {authenticated: false}; revoke server-side before returning and clear cookie.
- State-changing requests require exact same-origin Origin. Deny cross-origin before effects; no wildcard CORS. Same-origin reads require a live session. Every protected route is gated even when DB is absent/corrupt.
- GET /api/health is protected -> {status, capabilities, chat:{configured,enabled}}. Never expose keys, full paths, upstream responses or patient payloads in errors.

## Packet and ingestion protocol

A publishes `perception/episode.py` with strict EpisodePacket and `parse_packet(raw: bytes)` before other work. C produces exactly this JSON (optional collections default empty):

```
{
  "schema_version": 1,
  "episode_id": "UUID", "device_id": "UUID", "session_id": "UUID",
  "t_start_ms": 1000, "t_end_ms": 2200,
  "clock_anchor": {"mono_ms": 0, "wall_ms": 1790000000000},
  "capture": {"width": 1280, "height": 720},
  "analysis": {"width": 320, "height": 180},
  "keyframes": [
    {"frame_id": "unique-string", "t_ms": 1000, "role": "pre_contact", "jpeg_b64": "..."},
    {"frame_id": "another-string", "t_ms": 2200, "role": "rest", "jpeg_b64": "..."}
  ],
  "carry_burst": [], "landmarks": [], "gaps": [],
  "outcome_hint": "released", "capture_mode": "manual"
}
```

- UUID generated once per episode and retained with exact serialized bytes on retry; device UUID persistent, session UUID per page load. No timestamp-derived hash/rounding ambiguity.
- Monotonic times are nonnegative safe integer milliseconds, start<=end, strictly increasing keyframe times within the episode. Positive bounded wall anchor; record received time separately. Do not reject legitimate delayed upload with legacy30s policy; validate internal ordering/bounds and visibly flag implausible clocks.
- New endpoint max4MiB of actual request bytes; 1..8 unique keyframes, roles pre_contact/hand_busy/carry/release/rest. Never pad short captures. Valid base64 JPEG, actual dimensions equal capture dimensions, bounded dimensions/pixels (each dimension<=1920, area<=2073600). Distinct captures with identical pixels remain valid.
- carry_burst: <=10 {frame_id,t_ms,jpeg_b64,width,height}, analysis-resolution grayscale JPEGs, finite integer times; sparse/missing burst can disable carry localization rather than manufacture evidence.
- landmarks: bounded samples {frame_id,t_ms,hands:[{landmarks:[{x,y,z} x21],world_landmarks:[{x,y,z} x21] or null,hand_bbox:[x1,y1,x2,y2],handedness:'left'|'right'|'unknown'}]}; max2 hands. Image x/y normalized; z signed relative wrist depth, NOT metres. World XYZ metres are optional and can be retained in development traces for actual heuristic replay; absence prevents world-dependent classification. All floats finite. No claim that an absent measurement is stillness.
- gaps: bounded {t_from_ms,t_to_ms,reason}; capture_mode manual|automatic. Hints released|hand_gone|gap are NOT verified ledger outcomes. No client-supplied trusted identities, fixture observations, profile IDs or provider verdicts in this DTO.
- Exact transport SHA256 is the ack digest, computed over received raw bytes. Separately compute canonical semantic digest server-side for idempotency; do not require JS to reproduce Python float serialization. Ack echoes transport digest corresponding to this submission, not a prior differently serialized body.

POST /api/episodes protected and origin-checked, JSON body above -> {ack:{episode_id,device_id,digest,revision_no,retained,status},processing:{status}}. Status stored|duplicate|revised|conflict. Ack only after packet+DB evidence durable. Same authorized ID/semantic digest has no duplicate effects. Changed packets stored as bounded revisions, max8; superset must preserve prior evidence and anchors, otherwise conflict and no reinterpretation of current state. Repeated revision digests are idempotent. Unauthorized/malformed/oversize/revision-cap -> 401/403,400,413,409 respectively; no retained=true for rejected data. Cookie-auth profile never comes from request JSON. Mirror deletes only after matching episode/device/exact-transport digest with retained=true. Conflicts can be durably retained and surfaced as such, not treated as accepted interpretation.

## Store and local processing boundary

A extends ObjectStore with:
- `ingest_episode(raw: bytes) -> dict` (ack fields without server wrapper).
- `process_pending(*, processor=None, limit=8) -> dict` (bounded, idempotent, fenced claims; defaults real localizer, never a provider).
- `list_items(query='', limit=50) -> list[dict]`, `get_item(item_id) -> dict`, `item_history(item_id) -> list[dict]`.
- `item_image(item_id) -> Path | None` (profile-scoped approved evidence only).
- `rename_item(item_id, name) -> dict` (explicit user naming, audit).
- `answer_text(text, *, as_of=None) -> dict` (local, evidence-grounded).
- `rebuild_all(*, as_of=None) -> dict`, `migration_plan() -> dict` (non-destructive inspection), `redact_item(item_id) -> dict` (explicit authorized logical deletion, tests only until privacy endpoint approved).
- `capabilities() -> list[dict]` with name/enabled/reason; no keys/paths.

A owns DTO definitions and B delegates, without duplicating state logic. ObjectStore profile_id is trusted constructor configuration. Existing v1 methods and records remain supported; extend transactionally without resetting user_version or silently dropping data. Unsupported versions fail before mutation. Preserve v1 budgets/unknown spend/leases; no guessed legacy-to-trusted model identity migration. Migration plan reports what an explicit conversion would do. Do not run conversion on a real DB in this session.

Retain PERSIST/FULL and private DB/journal permissions. New evidence media is protected before writing. Raw evidence cannot be silently rewritten through ordinary APIs. Store versioned decisions/current projection with explicit as_of; replay uses stored decisions, not model reruns. Schema must distinguish mutable job/current-state tables from evidence. Use profile-scoped composite references. Sensitive payloads are separately erasable; explicit audited erasure may delete/redact them and invalidate derived data, with tombstone checks on resend/rebuild. No SQL roles, fake PRAGMA permissions, filesystem/backup forensic-erasure claims or automatic real-data deletion. Remaining metadata stays private and is not declared anonymous.

Localizer module exposes `localize(packet) -> list[LocalObservation]`. It can use registered image differences/OpenCV and emit real regions or none. LocalObservation internal fields: region frame_id/bbox, label (unknown unless evidence/user supplied), actor wearer|other_person|unknown, outcome sighted|placed_on_surface|picked_up|uncertain, continuity_id optional, identity_state provisional|ambiguous|trusted, location text optional, confidence basis/calibration metadata. This is a server-internal interface; a fixture processor is trusted test injection only, never an HTTP field/mode enabled by a public request. A publishes exact class early with packet schema.

Default uncalibrated observations create at most provisional candidates/sightings; they cannot establish confident physical-instance matches, ownership, medication contents, room names or placement solely from a hand-busy hint. Missing meaningful evidence yields context_only, visibly counted, not successful recognition. Known cannot-links survive unavailable new geometry. Trusted identity needs approved evidence/calibration; missing artifacts must be disclosed.

Ingest durability and processing are separate. B calls process_pending off the event loop after authorized ingest and in a bounded lifecycle worker; processing failure does not erase durable packet or stop subsequent jobs. Restart resumes pending jobs. No cloud client is reachable from processing.

## Catalogue and text chat

GET /api/items?q=&limit= -> {items:[Item],capabilities:[...]}; GET /api/items/{id} -> Item; GET /api/items/{id}/history -> {observations:[...]}; GET /api/items/{id}/image -> authenticated no-store image or404; POST /api/items/{id}/name {name} -> Item. Use bounded text/query limits; IDs cannot expose another profile or arbitrary files.

Item minimum fields: item_id, name, identity_status, relevance, location_status, observed_at_ms (or null), location_text (or null), stale_reason (or null), index_pending, image_url (or null), source. B adds only a validated relative image URL, never filesystem paths. All personal responses no-store. Photos are evidence for that candidate/member, not invented matches.

POST /api/chat {text,mode:'local'|'cloud'} -> Answer. text1..2000chars, mode defaults local. Answer minimum: shape confident|hedged|abstain|group|clarify, text, members:[Item], index_pending, question/options when clarifying. Local answer requires no chat keys; uncalibrated default cannot be confident. No matching evidence -> abstain without nearest-candidate image. Stale prior evidence -> hedged; no historical evidence -> abstain. Multiple clear query candidates -> bounded clarification; UI can resubmit selected item/name as text. Do not let cloud prose override ledger identity/location certainty.

Cloud mode returns503 {code:'chat_not_configured',error:safe-text} unless explicit server-only provider AND policy exist. First milestone does not choose a paid provider or implement billing from assumptions. Test-injected failing provider must not expose its error/body/keys or impede memory work. Real optional provider integration is a separate bounded-cost checkpoint (keys alone do not authorize spend). No /api/stt or speech routes. Deepgram and non-memory legacy routes return404/410, never execute their bodies or import missing apps. Preserve old source/comments unlinked if necessary rather than deleting files.

## Browser/controller

C builds one app in memory.html with sign-in, Text chat, Stored items, Camera. No microphone/voice library or telemetry/CDN fetch. Preserve white/blue simple accessible UI. Use textContent for data, safe relative image URLs, keyboard/focus/44px targets, truthful empty/unavailable/pending/gap states.

Camera getUserMedia requests audio:false. Capture-resolution bitmaps retained2s with <=20 active ring entries; separately <=8 selected keyframes and <=10 downscaled burst entries. Causal first-valid burst after observed busy/motion; no future midpoint. Close all resources on eviction/abort/pause/stop and track queue/byte caps. Model unavailable -> clearly labeled manual episode marking, not false automatic capture. Page visibility/track-ended/worker failure records coverage gaps. Serialized packets persist with their UUID/digest until matching durable ack; storage denial/full/expiry produces explicit coverage loss. Do not collect bystanders/real household footage during automated tests.

A publishes pure controller reference and its exact state input/output early; C ports the same thresholds. Tester owns shared golden traces and executes both languages, not comparing two copied expected outputs.

## Acceptance and next stages

Tester owns test files. CP0=141attempted118pass23setup errors. Replace approved legacy positive expectations only with explicit retirement/replacement tests, never skips. Preserve image-validation/static-denial/storage/budget regressions.

First gates: actualapp imports; keyless authorized ingest->local-processing fixture->placement/relocation->restart->catalogue; no provider egress; missing/failed cloudchat cannotstopingest; auth independentofDBexistence; origin/sessionexpiry/logout; strictpacket/revisions/ackdigest; PERSISTprivacy; exactTLSfailure/permission behavior ontemporarypairs; no realkeyoverwrite; independentprojectionreplay; boundedresources; textchat/catalogue UI smoke test. Test-only fixture processors must not be reachable through untrusted request payloads.

No certification of real object identity or automatic daily tracking from these tests. Subsequent required model-enable gate: pin/verify exact commercial artifacts, integrate local hand/appearance/OCR models, test real licensed images, then actual iPhone/mount/thermal/coverage and held-out end-to-end trials. Any unresolved artifact permission is reported as a blocker with safe development fallback, not silently treated as done.
