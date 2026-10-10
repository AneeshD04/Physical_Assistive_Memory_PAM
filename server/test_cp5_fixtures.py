"""CP5 shared fixtures and their self-tests (tester, 2026-10-10).

    python3 -B server/test_cp5_fixtures.py -v        # self-tests (no builder code needed)

Authority: docs/BUILD_PLAN.md "CP5 in detail: resolver, scoring harness, frame
accounting, notices" (architect, 2026-10-10) and docs/MEMORY_SYSTEM_V4.md Part 1
(rule 12, "Answer (resolver)", the five-outcome rubric, the scripted cases).
Everything the CP5 suites share lives here so that a builder spelling that differs
from the plan is a one-line fix:

  * the Answer contract: the exact key sets per shape, the closed vocabularies
    (shape, identity_status, location_status, basis in precedence order) and
    check_answer(), the one place every suite validates an Answer;
  * hand-built projection items (what ObjectStore._projection emits today, every
    field) for the pure-function resolver rows, with observation ids of the
    store's shape (64 hex);
  * the telemetry packet (POST /api/telemetry) with its closed key sets and bounds,
    and the coverage keys;
  * rubric answer/truth builders for the five outcomes;
  * the notices entry keys and the components the plan requires;
  * the scenario directory, its schema check and the per-query expectations;
  * Cp5Fixture, a store-level fixture on the CP4 one (bootstrap guards, consent
    acknowledged, scripted processor) with one helper per decision-table state.

Nothing here measures a real camera or a real model; every expectation is a
software-correctness expectation on synthetic data, never an accuracy claim.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
import test_memory_bootstrap as bootstrap  # noqa: E402
import test_cp3_identity as identity  # noqa: E402
import test_cp4_fixtures as fx  # noqa: E402

FIXTURES = ROOT / "server" / "fixtures" / "cp5"
SCENARIOS = FIXTURES / "scenarios"
SCENARIO_BASIS = "synthetic scenario, authored by the tester 2026-10-10; software-correctness expectations, not accuracy"
ANCHOR_MS = bootstrap.ANCHOR_MS
DEVICE = bootstrap.DEVICE
SESSION = bootstrap.SESSION
OTHER_SESSION = "44444444-4444-4444-8444-444444444444"
HOUR_MS = fx.HOUR_MS
DAY_MS = fx.DAY_MS
ACTOR = fx.ACTOR
ROOM_UNKNOWN = "room unknown"

# --- the Answer contract (plan: "Answer is a dict with exactly ...") --------------------------
SHAPES = ("confident", "hedged", "abstain", "group", "clarify")
IDENTITY_STATUSES = ("matched_trusted", "matched_provisional", "group", "unknown")
LOCATION_STATUSES = ("placed", "sighted", "inferred", "stale", "unknown")
# The closed basis vocabulary IN PRECEDENCE ORDER (the plan lists it in this order;
# an answer's basis is a subsequence of it).
BASIS_VOCABULARY = ("trusted_match", "provisional_match", "placed", "sighted", "inferred", "aged", "expired",
                    "negative_reobservation", "coverage_gap", "picked_up", "lookalikes", "name_ambiguous", "no_evidence",
                    "index_pending", "consent_pending")  # coordinator ruling 2: 15 tokens
BASIS_RANK = {token: index for index, token in enumerate(BASIS_VOCABULARY)}
IDENTITY_TOKENS = ("trusted_match", "provisional_match")
FLAG_TOKENS = ("index_pending", "consent_pending")


def in_vocabulary_order(basis):
    ranks = [BASIS_RANK[token] for token in basis]
    return ranks == sorted(ranks)
ANSWER_KEYS = frozenset({"shape", "text", "members", "reference_image", "target_indicated", "capture_time_ms",
                         "identity_status", "location_status", "room", "index_pending", "basis"})
CLARIFY_KEYS = ANSWER_KEYS | {"question", "options"}
GROUP_KEYS = CLARIFY_KEYS | {"unresolved_observation_id"}
# Phrases an abstention (and a hedge about an item it has no sighting of) never uses:
# "the last time I saw it" asserts an identity match (rule 12).
SIGHTING_CLAIMS = ("last saw", "last seen", "i saw", "the last time")
PENDING_DENIALS = ("haven't seen", "have not seen", "never seen")
GROUP_TEXT = identity.GROUP_TEXT
CP2_PICKUP_REASON = "Observed pickup; resting location is unknown"


def observation_id(seed):
    """A 64-hex observation id of the store's shape, deterministic in `seed`."""
    return hashlib.sha256(f"cp5-observation-{seed}".encode()).hexdigest()


def item(serial=1, *, name="synthetic cp5 block", identity_status="trusted", location_status="placed",
         location_text="fixture cp5 table", observed_at_ms=ANCHOR_MS + 2200, stale_reason=None, stale_since_ms=None,
         aged=False, lookalikes=(), inference=None, evidence_expired=False, reference_image="default",
         source="local_evidence", index_pending=False, gap_since=False, **extra):
    """A projection item exactly as ObjectStore._projection emits it today (every
    field, including the internal last_event_ms the DTO whitelist drops), aged by
    the caller. reference_image "default" is {frame_id, bbox} on the rest frame;
    None is the no-image case (expired evidence or a legacy row)."""
    item_id = f"cp5-item-{serial:03d}"
    frame_id = f"cp5-frame-{serial:03d}-rest"
    value = {"item_id": item_id, "name": name, "identity_status": identity_status, "relevance": "candidate",
             "location_status": location_status, "observed_at_ms": observed_at_ms, "location_text": location_text,
             "stale_reason": stale_reason, "index_pending": index_pending, "image_url": None, "aged": aged, "source": source,
             "observation_id": observation_id(serial),
             "reference_image": {"frame_id": frame_id, "bbox": list(fx.BLOCK_BBOX)} if reference_image == "default" else copy.deepcopy(reference_image),
             "lookalikes": list(lookalikes), "stale_since_ms": stale_since_ms, "inference": copy.deepcopy(inference),
             "evidence_expired": evidence_expired, "gap_since": gap_since, "last_event_ms": observed_at_ms}
    value.update(extra)
    return value


def inferred_item(serial, container, *, container_name, since_ms, **kwargs):
    kwargs.setdefault("location_status", "inferred")
    kwargs.setdefault("inference", {"container": container, "container_name": container_name, "since_ms": since_ms})
    return item(serial, **kwargs)


def lookalike_pair(serial_a=1, serial_b=2, *, name=identity.GLASSES, **kwargs):
    """Two mutual lookalikes (each lists the other), both 'ambiguous'; the group
    never upgrades either (B-14)."""
    a = item(serial_a, name=name, identity_status="ambiguous", location_text="fixture shelf left", **kwargs)
    b = item(serial_b, name=name, identity_status="ambiguous", location_text="fixture shelf right",
             observed_at_ms=kwargs.get("observed_at_ms", ANCHOR_MS + 2200), **{k: v for k, v in kwargs.items() if k != "observed_at_ms"})
    a["lookalikes"], b["lookalikes"] = [b["item_id"]], [a["item_id"]]
    return a, b


def resolve(query, items, *, as_of_ms, index_pending=False, policy=None):
    """The plan's pure function perception.resolver.resolve(query, items, *, as_of_ms,
    index_pending, policy). Items are deep-copied first: the resolver must not need
    to mutate them and the tests compare inputs afterwards."""
    from perception.resolver import resolve as builder_resolve
    frozen = copy.deepcopy(items)
    if policy is None:
        return builder_resolve(query, frozen, as_of_ms=as_of_ms, index_pending=index_pending)
    return builder_resolve(query, frozen, as_of_ms=as_of_ms, index_pending=index_pending, policy=policy)


def check_answer(case, answer, *, shape=None, members=None):
    """Validate an Answer against the contract. Returns the answer."""
    case.assertIsInstance(answer, dict, answer)
    actual_shape = answer.get("shape")
    case.assertIn(actual_shape, SHAPES, answer)
    if shape is not None:
        case.assertEqual(actual_shape, shape, answer)
    expected_keys = {"group": GROUP_KEYS, "clarify": CLARIFY_KEYS}.get(actual_shape, ANSWER_KEYS)
    keys = set(answer)
    if actual_shape == "clarify" and keys == GROUP_KEYS:
        # A clarify may carry unresolved_observation_id as null (the CP3 suite tolerates it).
        case.assertIsNone(answer["unresolved_observation_id"], answer)
        keys = keys - {"unresolved_observation_id"}
    case.assertEqual(keys, set(expected_keys), f"Answer key set for shape {actual_shape}: {sorted(keys ^ set(expected_keys))}")
    case.assertIsInstance(answer["text"], str)
    case.assertTrue(answer["text"].strip(), answer)
    case.assertIsInstance(answer["members"], list)
    for member in answer["members"]:
        case.assertIsInstance(member, dict)
        case.assertIsInstance(member.get("item_id"), str)
    if members is not None:
        case.assertEqual([m["item_id"] for m in answer["members"]], list(members), answer)
    reference = answer["reference_image"]
    if reference is not None:
        case.assertIsInstance(reference, dict, answer)
        case.assertEqual(set(reference), {"frame_id", "bbox"}, reference)
        case.assertIsInstance(reference["frame_id"], str)
        case.assertIsInstance(reference["bbox"], list)
        case.assertEqual(len(reference["bbox"]), 4)
    case.assertIsInstance(answer["target_indicated"], bool, answer)
    if reference is None:
        case.assertIs(answer["target_indicated"], False, "target_indicated is false when reference_image is null")
    # Oversight pass 2 (coordinator pin c): the outline is indicated as a VERIFIED target
    # only for a trusted identity; a provisional or group answer keeps its image with
    # target_indicated false (the page draws the dashed, unverified outline).
    if answer.get("identity_status") == "matched_trusted" and reference is not None:
        case.assertIs(answer["target_indicated"], True, "a trusted identity with an image indicates the target")
    if answer.get("identity_status") != "matched_trusted":
        case.assertIs(answer["target_indicated"], False, "only a trusted identity indicates the target")
    case.assertIn(answer["identity_status"], IDENTITY_STATUSES, answer)
    case.assertIn(answer["location_status"], LOCATION_STATUSES, answer)
    case.assertEqual(answer["room"], ROOM_UNKNOWN, "room reads 'room unknown' until a room source exists")
    case.assertIsInstance(answer["index_pending"], bool)
    capture = answer["capture_time_ms"]
    case.assertTrue(capture is None or (type(capture) is int and capture > 0), answer)
    basis = answer["basis"]
    case.assertIsInstance(basis, list, answer)
    case.assertTrue(basis, "basis is never empty")
    case.assertTrue(all(isinstance(token, str) for token in basis), basis)
    unknown = [token for token in basis if token not in BASIS_RANK]
    case.assertEqual(unknown, [], f"basis tokens outside the closed vocabulary: {unknown}")
    case.assertEqual(len(set(basis)), len(basis), f"basis repeats a token: {basis}")
    # Ordering (the strict vocabulary-order pin is test_cp5_resolver's own test): the
    # identity token, when present, comes first; the cross-cutting flags come last.
    identity_tokens = [token for token in basis if token in IDENTITY_TOKENS]
    case.assertLessEqual(len(identity_tokens), 1, f"two identity tokens: {basis}")
    if identity_tokens:
        case.assertEqual(basis[0], identity_tokens[0], f"the identity token leads the basis: {basis}")
    flags = [token for token in basis if token in FLAG_TOKENS]
    case.assertEqual(basis[len(basis) - len(flags):], flags, f"flags come last: {basis}")
    if actual_shape == "abstain":
        case.assertIsNone(reference, "an abstention carries no image")
        case.assertIs(answer["target_indicated"], False)
        case.assertIsNone(capture, "an abstention carries no capture time")
        case.assertEqual(answer["members"], [], "an abstention names no member")
        case.assertEqual(answer["identity_status"], "unknown")
        lowered = answer["text"].lower()
        for phrase in SIGHTING_CLAIMS:
            case.assertNotIn(phrase, lowered, f"an abstention never claims a sighting: {answer['text']!r}")
    if actual_shape in ("clarify", "group"):
        case.assertIsInstance(answer["question"], str)
        case.assertTrue(answer["question"].strip())
        case.assertIsInstance(answer["options"], list)
        case.assertEqual([o["item_id"] for o in answer["options"]], [m["item_id"] for m in answer["members"]], answer)
        for option in answer["options"]:
            case.assertEqual(set(option), {"item_id", "name"}, option)
        case.assertGreaterEqual(len(answer["members"]), 2, "a question needs at least two candidates")
    if actual_shape == "group":
        case.assertEqual(answer["identity_status"], "group")
        case.assertIn("lookalikes", basis)
        ids = {m["item_id"] for m in answer["members"]}
        for member in answer["members"]:
            case.assertEqual(set(member.get("provenance", {})), {"observation_id", "identity_status"}, member)
            case.assertNotEqual(member["identity_status"], "trusted", "a group never upgrades a member (B-14)")
            case.assertTrue(ids - {member["item_id"]} <= set(member.get("lookalikes") or ()), member)
        unresolved = answer["unresolved_observation_id"]
        case.assertTrue(unresolved is None or isinstance(unresolved, str), answer)
    if actual_shape == "clarify":
        case.assertIn("name_ambiguous", basis)
    if actual_shape == "confident":
        case.assertEqual(len(answer["members"]), 1)
        case.assertEqual(answer["identity_status"], "matched_trusted")
        case.assertEqual(answer["location_status"], "placed")
        case.assertEqual(basis[:2], ["trusted_match", "placed"], basis)
    if actual_shape == "hedged":
        case.assertEqual(len(answer["members"]), 1)
        # "group" is allowed for a single member that cannot be told apart from its lookalikes.
        case.assertIn(answer["identity_status"], ("matched_trusted", "matched_provisional", "group"))
    if answer["index_pending"]:
        case.assertIn("index_pending", basis)
    return answer


def strip_internal(item_record):
    """A projection item without the store-internal field the DTO never carries."""
    return {k: v for k, v in item_record.items() if k != "last_event_ms"}


# --- telemetry (POST /api/telemetry) ---------------------------------------------------------
TELEMETRY_TOP = frozenset({"schema_version", "device_id", "session_id", "t_ms", "clock_anchor", "window_ms", "counters", "timing", "settings"})
COUNTER_KEYS = frozenset({"frames_captured", "frames_analysed", "frames_skipped_busy", "frames_dropped_backpressure",
                          "landmark_results", "landmark_timeouts", "episodes_started", "episodes_finished", "episodes_aborted",
                          "packets_sent", "packets_acked", "idle_sent", "idle_dropped", "gaps", "gap_ms", "bytes_sent"})
TIMING_KEYS = frozenset({"fps_observed", "infer_ms_p50", "infer_ms_p95", "tick_ms_p95"})
SETTINGS_KEYS = frozenset({"width", "height", "frame_rate"})
COVERAGE_KEYS = frozenset({"camera_on_ms", "gap_ms", "episodes", "packets", "idle_sent", "idle_dropped", "sessions"})
MAX_TELEMETRY_BYTES = 64 * 1024
FRAME_COUNTER_COLUMNS = {"profile_id", "device_id", "session_id", "t_ms", "received_ms", "window_ms", "counters", "timing", "settings"}


def telemetry_packet(*, device=DEVICE, session=SESSION, t_ms=60000, mono_ms=0, wall_ms=ANCHOR_MS, window_ms=60000,
                     counters=None, timing=None, settings=None):
    """One telemetry post: the counters of the last window_ms ending at t_ms on
    the monotonic clock (wall time = wall_ms + t_ms - mono_ms). Integers only in
    counters; bounded finite floats in timing; no free text anywhere."""
    base_counters = {"frames_captured": 600, "frames_analysed": 300, "frames_skipped_busy": 5, "frames_dropped_backpressure": 1,
                     "landmark_results": 295, "landmark_timeouts": 0, "episodes_started": 2, "episodes_finished": 2,
                     "episodes_aborted": 0, "packets_sent": 2, "packets_acked": 2, "idle_sent": 2, "idle_dropped": 0,
                     "gaps": 0, "gap_ms": 0, "bytes_sent": 40960}
    base_timing = {"fps_observed": 9.8, "infer_ms_p50": 21.0, "infer_ms_p95": 38.5, "tick_ms_p95": 110.0}
    base_settings = {"width": 1280, "height": 720, "frame_rate": 30}
    if counters:
        base_counters.update(counters)
    if timing:
        base_timing.update(timing)
    if settings:
        base_settings.update(settings)
    return {"schema_version": 1, "device_id": device, "session_id": session, "t_ms": t_ms,
            "clock_anchor": {"mono_ms": mono_ms, "wall_ms": wall_ms}, "window_ms": window_ms,
            "counters": base_counters, "timing": base_timing, "settings": base_settings}


def telemetry_wall_ms(packet):
    return packet["clock_anchor"]["wall_ms"] + packet["t_ms"] - packet["clock_anchor"]["mono_ms"]


def utc_day(wall_ms):
    return datetime.fromtimestamp(wall_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def day_start_ms(day):
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


def packet_for_day(day, *, offset_ms=12 * HOUR_MS, **kwargs):
    """A telemetry packet whose wall time is `day` (UTC) + offset_ms."""
    return telemetry_packet(wall_ms=day_start_ms(day) + offset_ms, t_ms=kwargs.pop("t_ms", 60000), mono_ms=kwargs.pop("mono_ms", 60000), **kwargs)


def encode(packet):
    return bootstrap.encode_packet(packet)


def expected_coverage(packets, day):
    """The coverage the tests expect for a UTC day: per-window deltas summed over
    every packet whose wall time falls in that day (camera_on_ms = sum of
    window_ms; gap_ms, episodes = episodes_finished, packets = packets_sent,
    idle_sent, idle_dropped summed; sessions = distinct session ids). Assumption to
    confirm with Builders A/C: the browser posts per-window deltas, not running totals."""
    chosen = [p for p in packets if utc_day(telemetry_wall_ms(p)) == day]
    return {"camera_on_ms": sum(p["window_ms"] for p in chosen),
            "gap_ms": sum(p["counters"]["gap_ms"] for p in chosen),
            "episodes": sum(p["counters"]["episodes_finished"] for p in chosen),
            "packets": sum(p["counters"]["packets_sent"] for p in chosen),
            "idle_sent": sum(p["counters"]["idle_sent"] for p in chosen),
            "idle_dropped": sum(p["counters"]["idle_dropped"] for p in chosen),
            "sessions": len({p["session_id"] for p in chosen})}


# --- rubric ------------------------------------------------------------------------------------
OUTCOMES = ("correct", "hedged-correct", "hedged-wrong", "confident-wrong", "abstain")
TRUTH_KEYS = frozenset({"item_id", "location_status_now", "location_text_now", "moved_since", "medication"})


def truth(item_id, *, location_status_now="placed", location_text_now="fixture cp5 table", moved_since=False, medication=False):
    return {"item_id": item_id, "location_status_now": location_status_now, "location_text_now": location_text_now,
            "moved_since": moved_since, "medication": medication}


def answer(shape, members=(), *, basis=None, index_pending=False, question=None, options=None, unresolved=None, text=None):
    """A full Answer of the contract shape built from projection items (for the rubric,
    which must read the member's item_id and location fields). reference_image and
    the statuses follow the single member when there is one."""
    members = [strip_internal(m) for m in members]
    single = members[0] if len(members) == 1 and shape in ("confident", "hedged") else None
    reference = single["reference_image"] if single and not single.get("evidence_expired") else None
    if single is None:
        identity_status, location_status = ("group" if shape == "group" else "unknown"), "unknown"
    else:
        identity_status = "matched_trusted" if single["identity_status"] == "trusted" else "matched_provisional"
        location_status = single["location_status"]
    if basis is None:
        basis = {"abstain": ["no_evidence"], "clarify": ["name_ambiguous"], "group": ["lookalikes"],
                 "confident": ["trusted_match", "placed"], "hedged": ["trusted_match", "aged"]}[shape]
    if text is None:
        text = {"abstain": "I have no matching stored evidence.", "clarify": "Which stored item do you mean?",
                "group": GROUP_TEXT.format(n=len(members))}.get(shape, f"synthetic {shape} answer about {single['name'] if single else 'items'}")
    value = {"shape": shape, "text": text, "members": members, "reference_image": reference,
             "target_indicated": bool(reference) and identity_status == "matched_trusted",
             "capture_time_ms": None if shape == "abstain" else (single["observed_at_ms"] if single else None),
             "identity_status": identity_status, "location_status": location_status, "room": ROOM_UNKNOWN,
             "index_pending": index_pending, "basis": list(basis)}
    if shape in ("clarify", "group"):
        value["question"] = question or ("Which one is yours?" if shape == "group" else "Which stored item?")
        value["options"] = options or [{"item_id": m["item_id"], "name": m["name"]} for m in members]
    if shape == "group":
        value["unresolved_observation_id"] = unresolved
        for member in value["members"]:
            member["provenance"] = {"observation_id": member["observation_id"], "identity_status": member["identity_status"]}
    return value


def rubric_record(answer_value, truth_value, *, query="where is it", outcome=None):
    """One scored record for summarize(): the shape run_scenario is expected to
    produce (query, answer, truth, outcome, medication). Adapter: the one place to
    touch if Builder A's record spelling differs."""
    from perception import rubric
    outcome = rubric.score(answer_value, truth_value) if outcome is None else outcome
    return {"query": query, "answer": answer_value, "truth": truth_value, "outcome": outcome,
            "medication": truth_value.get("medication") is True}


def find_value(summary, pattern, *, within=None):
    """The first value whose key matches `pattern` (regex, case-insensitive) at any
    depth of a summary dict, searching a nested dict named by `within` first when
    given. None when absent."""
    import re
    rx = re.compile(pattern, re.IGNORECASE)
    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(key, str) and rx.search(key):
                    return value
            for value in node.values():
                found = walk(value)
                if found is not None:
                    return found
        return None
    if within is not None:
        scope = find_value(summary, within)
        if isinstance(scope, dict):
            return walk(scope)
    return walk(summary)


def leaf_numbers(value):
    """Every finite number below a value (dicts and lists), bools excluded."""
    out = []
    if isinstance(value, bool):
        return out
    if isinstance(value, (int, float)):
        return [value] if math.isfinite(value) else out
    if isinstance(value, dict):
        for child in value.values():
            out.extend(leaf_numbers(child))
    elif isinstance(value, list):
        for child in value:
            out.extend(leaf_numbers(child))
    return out


# --- notices ------------------------------------------------------------------------------------
NOTICE_KEYS = frozenset({"component", "version", "licence", "source_url", "notice_text", "condition"})  # ruling 6: six keys
NOTICE_CONDITIONS = ("provisioned:hand", "provisioned:identity", "served:tabler", "calibration:cute", "always")
# The components the plan names for server/notices.json, as case-insensitive regexes
# matched against the `component` field (Tabler icons are MIT and listed in the
# register; the CUTE attribution is conditional on a calibration and tested apart).
REQUIRED_COMPONENTS = {
    "mediapipe": r"mediapipe|tasks-vision",
    "dinov2": r"dino",
    "onnxruntime": r"onnx ?runtime|onnxruntime",
    "fastapi": r"fastapi",
    "starlette": r"starlette",
    "uvicorn": r"uvicorn",
    "pydantic": r"pydantic",
    "numpy": r"numpy",
    "opencv": r"opencv|cv2",
    "tabler": r"tabler",
}
CUTE_URL = "purl.stanford.edu/gj714cj0414"


def load_notices():
    data = json.loads((ROOT / "server" / "notices.json").read_text(encoding="utf-8"))
    entries = data.get("components", data.get("notices")) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise AssertionError("server/notices.json must be a list of entries (or {components: [...]})")
    return entries


# --- scenarios -------------------------------------------------------------------------------------
STEP_KINDS = ("episode", "idle", "correction", "gap", "advance", "query")
MANDATORY_SCENARIOS = ("new_item_before_indexing", "fast_put_down", "caregiver_relocation_observed",
                       "unobserved_relocation_then_sighting", "two_refills_lookalikes", "coverage_loss", "medication_set")


def load_scenarios():
    """{name: scenario} for every JSON under server/fixtures/cp5/scenarios."""
    out = {}
    for path in sorted(SCENARIOS.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        data["_path"] = path
        out[path.stem] = data
    return out


SCENARIO_REQUIRED = {"name", "basis", "clock_start_ms", "steps"}
SCENARIO_OPTIONAL = {"identity", "description", "items", "calibrated"}
# The tester's own query-step keys (read by test_cp5_scenarios, ignored by the runner).
QUERY_EXTRAS = {"expected_basis", "expected_index_pending", "expected_gap_ms"}
CORRECTION_OPS = ("link", "unlink", "assign", "rename")


def check_scenario(case, scenario):
    """The runner's schema (perception/scenario_runner.py docstring): items as
    {handle: {label, tag, medication?}}, steps of the six kinds, query steps with
    text, truth {item, explicit rubric keys...} and expect {outcome, shape}."""
    keys = set(scenario) - {"_path"}
    case.assertTrue(SCENARIO_REQUIRED <= keys, sorted(SCENARIO_REQUIRED - keys))
    case.assertEqual(keys - SCENARIO_REQUIRED - SCENARIO_OPTIONAL, set(), "unknown scenario keys")
    case.assertEqual(scenario["basis"], SCENARIO_BASIS)
    case.assertIsInstance(scenario["clock_start_ms"], int)
    case.assertGreater(scenario["clock_start_ms"], 0)
    items = scenario.get("items", {})
    case.assertIsInstance(items, dict)
    case.assertLessEqual(len(items), 7)
    for handle, spec in items.items():
        case.assertRegex(handle, r"^[A-Za-z0-9_-]{1,40}$")
        case.assertTrue(set(spec) <= {"label", "tag", "medication"}, spec)
        case.assertIsInstance(spec["label"], str)
        case.assertIn(spec.get("tag", 0), range(7))
    case.assertEqual(len({spec.get("tag", 0) for spec in items.values()}), len(items), "one tag per item")
    case.assertIsInstance(scenario["steps"], list)
    case.assertTrue(scenario["steps"])
    for step in scenario["steps"]:
        case.assertIn(step["kind"], STEP_KINDS, step)
        if step["kind"] == "query":
            case.assertIsInstance(step["text"], str)
            case.assertTrue(set(step["truth"]) <= TRUTH_KEYS | {"item"}, step)
            case.assertIn("item", step["truth"])
            case.assertEqual(set(step["expect"]), {"outcome", "shape"}, step)
            case.assertIn(step["expect"]["outcome"], OUTCOMES, step)
            case.assertIn(step["expect"]["shape"], SHAPES, step)
            case.assertTrue(set(step) - {"kind", "text", "truth", "expect", "process"} <= QUERY_EXTRAS, step)
            if step["expect"]["shape"] in ("clarify", "group"):
                case.assertEqual(step["expect"]["outcome"], "abstain", "clarify/group score as abstain for accuracy")
        elif step["kind"] == "episode":
            placements = step.get("placements") or [step]
            for placement in placements:
                case.assertIn(placement["item"], items, placement)
                case.assertIn(placement.get("outcome", "placed_on_surface"), ("placed_on_surface", "picked_up", "sighted", "uncertain"), placement)
            case.assertIn(step.get("actor", "wearer"), ("wearer", "other_person", "unknown"), step)
        elif step["kind"] == "gap":
            case.assertIn(step["reason"], ("screen_lock", "network_loss", "backgrounded"), step)
            case.assertGreater(step["duration_ms"], 0)
        elif step["kind"] == "advance":
            case.assertEqual(len({"ms", "minutes", "hours", "days"} & set(step)), 1, step)
        elif step["kind"] == "correction":
            case.assertIn(step["op"], CORRECTION_OPS, step)
        elif step["kind"] == "idle":
            case.assertIsInstance(step.get("absent", []), list)
    queries = [step for step in scenario["steps"] if step["kind"] == "query"]
    case.assertTrue(queries, "a scenario asks at least one question")
    return queries


def scenario_queries(scenario):
    return [step for step in scenario["steps"] if step["kind"] == "query"]


def query_medication(scenario, step):
    """Whether a query step is a medication query: its truth's explicit flag, else
    the flag of the item handle it names."""
    truth_spec = step["truth"]
    if "medication" in truth_spec:
        return truth_spec["medication"] is True
    handle = truth_spec.get("item")
    return handle is not None and scenario.get("items", {}).get(handle, {}).get("medication", False) is True


# --- store-level fixture -----------------------------------------------------------------------------
class Cp5Fixture(fx.Cp4Fixture):
    """The CP4 store fixture (consent acknowledged, scripted processor, injected clock)
    plus one helper per decision-table state. self.store has no embedder (block
    placements are trusted through the CP2 code-only fixture calibration); the
    lookalike group uses a second store on the same profile with the CP3 synthetic
    embedder and the approved wide calibration."""
    def setUp(self):
        super().setUp()
        self.embedded_store = None

    def embedder_store(self):
        if self.embedded_store is None:
            self.embedded_store = self.make_store(embedder=identity.SyntheticEmbedder())
            self.register_calibration(store=self.embedded_store)
        return self.embedded_store

    def now_ms(self):
        return int(self.now * 1000)

    def place_block(self, label="synthetic cp5 block", location="fixture cp5 table", *, continuity=None, actor="wearer", **packet_kwargs):
        """One trusted placement of the block at BLOCK_BBOX; returns (packet, item)."""
        packet = self.place([fx.observation(None, fx.BLOCK_BBOX, label=label, location=location, continuity_id=continuity, actor=actor)], **packet_kwargs)
        return packet, self.item_by_name(label)

    def pickup_block(self, label="synthetic cp5 block", *, continuity, **packet_kwargs):
        packet = self.place([fx.observation(None, fx.BLOCK_BBOX, label=label, location=None, outcome="picked_up", continuity_id=continuity)], **packet_kwargs)
        return packet, self.item_by_name(label)

    def provisional_sighting(self, label="synthetic cp5 pebble", **packet_kwargs):
        packet = self.place([fx.observation(None, fx.BLOCK_BBOX, label=label, location=None, outcome="sighted",
                                            identity_state="provisional", calibration={})], **packet_kwargs)
        return packet, self.item_by_name(label)

    def negative_reobservation(self, placement):
        """An idle 'gone' frame after `placement`, re-observed: the placed item reads
        stale / negative_reobservation. Returns the idle packet."""
        gone, _ = self.idle("gone", wall_ms=fx.rest_wall_ms(placement) + 60000)
        self.now += 120
        self.reobserve()
        return gone

    def expire(self, packet, *, store=None):
        """Expire the packet's bytes by retention (31 days after receipt) without
        moving the fixture clock: the item then reads evidence_expired."""
        store = self.store if store is None else store
        received = self.rows("episode_revisions", "WHERE profile_id='local' AND episode_id=?", (packet["episode_id"],))[0]["received_at_ms"]
        store.apply_retention(received + 31 * DAY_MS)

    def nest(self, inner="synthetic cp5 keys", outer="synthetic cp5 basket", *, location="fixture cp5 counter"):
        packet = self.place([fx.observation(None, fx.BLOCK_BBOX, label=outer, location=location, continuity_id="cp5-outer"),
                             fx.observation(None, [68.0, 48.0, 92.0, 72.0], label=inner, location=location, continuity_id="cp5-inner")])
        return packet, self.item_by_name(inner), self.item_by_name(outer)

    def move_outer(self, outer="synthetic cp5 basket", *, location="fixture cp5 shelf"):
        return self.place([fx.observation(None, [8.0, 8.0, 56.0, 36.0], label=outer, location=location, continuity_id="cp5-outer")])

    def lookalike_group(self, label=identity.GLASSES):
        """A and B (tags 0 and 1) co-visible, then a lone tag-0 sighting: both ambiguous
        and the answer is a group. Returns (a_id, b_id, store)."""
        store = self.embedder_store()
        self.place([fx.observation(None, fx.square_bbox(*fx.TAG_LEFT), label=label, location="fixture shelf left", calibration=identity.cp3_calibration()),
                    fx.observation(None, fx.square_bbox(*fx.TAG_RIGHT), label=label, location="fixture shelf right", calibration=identity.cp3_calibration())],
                   rest=fx.scene_jpeg(block="absent", squares=[(fx.TAG_LEFT[0], fx.TAG_LEFT[1], fx.SQUARE, 0), (fx.TAG_RIGHT[0], fx.TAG_RIGHT[1], fx.SQUARE, 1)]), store=store)
        pair = sorted((i for i in self.items(store) if i["name"] == label), key=lambda i: i["location_text"] or "")
        self.assertEqual([i["location_text"] for i in pair], ["fixture shelf left", "fixture shelf right"], pair)
        a, b = (i["item_id"] for i in pair)
        self.place([fx.observation(None, fx.square_bbox(60, 40), label=label, location="fixture shelf middle", calibration=identity.cp3_calibration())],
                   rest=fx.scene_jpeg(block="absent", squares=[(60, 40, fx.SQUARE, 0)]), store=store)
        items = {i["item_id"]: i for i in self.items(store) if i["name"] == label}
        self.assertEqual(set(items), {a, b}, items)
        self.assertEqual({i["identity_status"] for i in items.values()}, {"ambiguous"}, items)
        return a, b, store

    def projection(self, store=None):
        """The aged projection as list_items returns it (every item, index_pending
        attached), the input answer_text hands to the resolver."""
        return (self.store if store is None else store).list_items(limit=200)

    def answer(self, question, store=None, **kwargs):
        return (self.store if store is None else store).answer_text(question, **kwargs)

    def direct(self, question, store=None, *, index_pending=False, policy=None):
        """resolve() on the store's own projection at the fixture clock."""
        return resolve(question, self.projection(store), as_of_ms=self.now_ms(), index_pending=index_pending, policy=policy)


# --- self-tests (green before any builder code) ---------------------------------------------------
class FixtureSelfTests(unittest.TestCase):
    def test_hand_built_item_matches_the_projection_shape_of_a_real_placement(self):
        # The pure-function rows feed hand-built dicts to the resolver; they must carry
        # exactly the fields the store's projection carries today (so the resolver that
        # answer_text delegates to sees the same keys both ways).
        from perception.object_memory import ObjectStore  # noqa: F401  (import check only)
        built = item(1)
        expected = {"item_id", "name", "identity_status", "relevance", "location_status", "observed_at_ms", "location_text",
                    "stale_reason", "index_pending", "image_url", "aged", "source", "observation_id", "reference_image",
                    "lookalikes", "stale_since_ms", "inference", "evidence_expired", "gap_since", "last_event_ms"}
        self.assertEqual(set(built), expected)
        self.assertRegex(built["observation_id"], r"^[0-9a-f]{64}$")
        a, b = lookalike_pair()
        self.assertEqual((a["lookalikes"], b["lookalikes"]), ([b["item_id"]], [a["item_id"]]))
        inferred = inferred_item(3, "cp5-item-002", container_name="synthetic basket", since_ms=ANCHOR_MS)
        self.assertEqual(inferred["location_status"], "inferred")
        self.assertEqual(set(inferred["inference"]), {"container", "container_name", "since_ms"})

    def test_check_answer_accepts_contract_answers_and_rejects_violations(self):
        good = answer("confident", [item(1)])
        check_answer(self, good, shape="confident", members=["cp5-item-001"])
        check_answer(self, answer("abstain"), shape="abstain")
        a, b = lookalike_pair()
        check_answer(self, answer("group", [a, b], unresolved=observation_id(9)), shape="group")
        check_answer(self, answer("clarify", [item(1), item(2, name="synthetic cp5 other block")]), shape="clarify")
        hedged = answer("hedged", [item(1, aged=True, stale_reason="age")])
        check_answer(self, hedged, shape="hedged")
        for name, bad in {
            "extra key": dict(good, extra=1),
            "missing key": {k: v for k, v in good.items() if k != "room"},
            "room": dict(good, room="kitchen"),
            "basis order": dict(good, basis=["placed", "trusted_match"]),
            "basis vocabulary": dict(good, basis=["trusted_match", "placed", "fresh"]),
            "basis repeat": dict(good, basis=["trusted_match", "placed", "placed"]),
            "target without image": dict(good, reference_image=None, target_indicated=True),
            "trusted image without target": dict(good, target_indicated=False),
            "provisional target indicated": dict(answer("hedged", [item(1, identity_status="provisional", location_status="sighted", location_text=None)], basis=["provisional_match", "sighted"]), target_indicated=True),
            "abstain with image": dict(answer("abstain"), reference_image=good["reference_image"]),
            "abstain with sighting claim": dict(answer("abstain"), text="The last time I saw it was on the counter."),
            "abstain with capture time": dict(answer("abstain"), capture_time_ms=ANCHOR_MS),
            "group upgrades a member": dict(answer("group", [a, b]), members=[dict(a, identity_status="trusted", provenance={"observation_id": a["observation_id"], "identity_status": "trusted"}), answer("group", [a, b])["members"][1]]),
            "wrong identity vocabulary": dict(good, identity_status="trusted"),
            "wrong location vocabulary": dict(good, location_status="current"),
            "pending without basis": dict(good, index_pending=True),
        }.items():
            with self.subTest(case=name), self.assertRaises(AssertionError):
                check_answer(self, bad)

    def test_telemetry_packet_shape_and_coverage_arithmetic(self):
        packet = telemetry_packet()
        self.assertEqual(set(packet), TELEMETRY_TOP)
        self.assertEqual(set(packet["counters"]), COUNTER_KEYS)
        self.assertEqual(set(packet["timing"]), TIMING_KEYS)
        self.assertEqual(set(packet["settings"]), SETTINGS_KEYS)
        self.assertTrue(all(type(v) is int and v >= 0 for v in packet["counters"].values()))
        self.assertTrue(all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0 for v in packet["timing"].values()))
        self.assertLess(len(encode(packet)), 2048)
        self.assertEqual(telemetry_wall_ms(packet), ANCHOR_MS + 60000)
        day = "2026-10-10"
        first = packet_for_day(day, session=SESSION, window_ms=60000, counters={"gap_ms": 1500, "episodes_finished": 1, "packets_sent": 1, "idle_sent": 2, "idle_dropped": 1})
        second = packet_for_day(day, session=SESSION, offset_ms=12 * HOUR_MS + 60000, window_ms=30000, counters={"gaps": 1, "gap_ms": 500, "episodes_finished": 0, "packets_sent": 0})
        other = packet_for_day(day, session=OTHER_SESSION, offset_ms=23 * HOUR_MS, window_ms=60000, counters={"episodes_finished": 3, "packets_sent": 3, "idle_sent": 1})
        tomorrow = packet_for_day("2026-10-11", offset_ms=0, window_ms=60000)
        self.assertEqual(utc_day(telemetry_wall_ms(first)), day)
        self.assertEqual(utc_day(telemetry_wall_ms(tomorrow)), "2026-10-11")
        self.assertEqual(expected_coverage([first, second, other, tomorrow], day),
                         {"camera_on_ms": 150000, "gap_ms": 2000, "episodes": 4, "packets": 4, "idle_sent": 5, "idle_dropped": 1, "sessions": 2})
        self.assertEqual(expected_coverage([first, second, other, tomorrow], "2026-10-09"),
                         {"camera_on_ms": 0, "gap_ms": 0, "episodes": 0, "packets": 0, "idle_sent": 0, "idle_dropped": 0, "sessions": 0})

    def test_rubric_builders_and_summary_accessors(self):
        value = answer("confident", [item(1)])
        self.assertEqual(value["members"][0]["location_text"], "fixture cp5 table")
        self.assertNotIn("last_event_ms", value["members"][0])
        t = truth("cp5-item-001")
        self.assertEqual(set(t), TRUTH_KEYS)
        summary = {"all": {"correct_among_answered": 0.75, "coverage": 0.8}, "medication": {"correct_among_answered": 0.5}, "note": "x"}
        self.assertEqual(find_value(summary, r"correct_among_answered"), 0.75)
        self.assertEqual(find_value(summary, r"correct_among_answered", within=r"medication"), 0.5)
        self.assertIsNone(find_value(summary, r"fidelity"))
        self.assertEqual(sorted(leaf_numbers(summary)), [0.5, 0.75, 0.8])

    def test_scenario_files_follow_the_schema_and_cover_the_mandatory_cases(self):
        scenarios = load_scenarios()
        self.assertTrue(set(MANDATORY_SCENARIOS) <= set(scenarios), sorted(set(MANDATORY_SCENARIOS) - set(scenarios)))
        medication_queries = 0
        for name, scenario in scenarios.items():
            with self.subTest(scenario=name):
                self.assertEqual(scenario["name"], name)
                queries = check_scenario(self, scenario)
                medication_queries += sum(1 for q in queries if query_medication(scenario, q))
        self.assertGreaterEqual(medication_queries, 4, "the medication set asks at least four medication questions")
        medication = scenarios["medication_set"]
        self.assertTrue(all(query_medication(medication, q) for q in scenario_queries(medication)), "every medication-set query is a medication query")
        # The medication scenarios never expect a confident-wrong (the pilot's zero bound
        # is a software expectation here: the synthetic truth is always observable).
        for step in scenario_queries(medication):
            self.assertNotEqual(step["expect"]["outcome"], "confident-wrong", step)
        # The unobserved-relocation scenario is the one that exercises the
        # fidelity/usefulness split: a truthful old photo offered after a coverage gap
        # (hedged, coverage_gap) is scored hedged-wrong for usefulness, fidelity ok.
        self.assertIn("hedged-wrong", [q["expect"]["outcome"] for q in scenario_queries(scenarios["unobserved_relocation_then_sighting"])])
        # The lookalike scenario expects a group, scored abstain, through the synthetic tag embedder.
        self.assertIn("group", [q["expect"]["shape"] for q in scenario_queries(scenarios["two_refills_lookalikes"])])
        self.assertEqual(scenarios["two_refills_lookalikes"].get("identity", {}).get("embedder"), "synthetic_tag")
        # The schema is the runner's: the example scenario Builder A ships passes the same check.
        example = ROOT / "scripts" / "scenario_example.json"
        if example.is_file():
            data = json.loads(example.read_text(encoding="utf-8"))
            self.assertTrue(SCENARIO_REQUIRED <= set(data), data.keys())
            self.assertTrue(all(step["kind"] in STEP_KINDS for step in data["steps"]))

    def test_cp5_fixture_states_through_the_real_store(self):
        # Each decision-table state the resolver suite drives through the store is
        # reachable today (CP4 store); nothing here needs the resolver.
        class Probe(Cp5Fixture):
            def runTest(self):
                pass
        probe = Probe()
        probe.setUp()
        try:
            placement, placed = probe.place_block()
            self.assertEqual((placed["identity_status"], placed["location_status"]), ("trusted", "placed"))
            _, pebble = probe.provisional_sighting()
            self.assertEqual((pebble["identity_status"], pebble["location_status"], pebble["location_text"]), ("provisional", "sighted", None))
            probe.negative_reobservation(placement)
            stale = probe.item_by_name("synthetic cp5 block")
            self.assertEqual((stale["location_status"], stale["stale_reason"]), ("stale", "negative_reobservation"))
            _, other = probe.place_block("synthetic cp5 cup", "fixture cp5 desk", continuity="cp5-cup")
            _, picked = probe.pickup_block("synthetic cp5 cup", continuity="cp5-cup")
            self.assertEqual((picked["location_status"], picked["stale_reason"], picked["location_text"]), ("stale", CP2_PICKUP_REASON, None))
            nest_packet, keys, basket = probe.nest()
            probe.move_outer()
            self.assertEqual(probe.item_by_name("synthetic cp5 keys")["location_status"], "inferred")
            a, b, store = probe.lookalike_group()
            group = probe.answer(identity.ASK_GLASSES, store)
            self.assertEqual(group["shape"], "group")
            expired_packet, expiring = probe.place_block("synthetic cp5 mug", "fixture cp5 sink")
            probe.expire(expired_packet)
            self.assertIs(probe.item_by_name("synthetic cp5 mug")["evidence_expired"], True)
            self.assertGreaterEqual(len(probe.projection()), 6)
        finally:
            probe.doCleanups()


if __name__ == "__main__":
    unittest.main(verbosity=2)
