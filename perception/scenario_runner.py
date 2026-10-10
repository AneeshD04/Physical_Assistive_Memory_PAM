"""Scripted scenario runner (CP5): a JSON scenario against a real store.

    run_scenario(path, *, store_factory, embedder=None) -> list[record]

The runner materialises each scripted step as the browser would have produced
it (episode packets and idle frames from perception.scenario_frames, telemetry
windows), feeds them to the store through its public API (ingest_episode,
process_pending, ingest_idle, reobserve, apply_retention, ingest_telemetry,
corrections, answer_text) under the scenario's clock, and scores every query
with perception.rubric.score against the scenario's ground truth.

TEST-TIME INJECTION, NOT A PRODUCTION PATH. The runner is the "fixture
processor": it knows where it painted every item, so it hands
process_pending(processor=...) LocalObservation rows built from that ground
truth (identity_state "trusted" under the CP2 code-only fixture calibration when
the scenario says calibrated, "provisional" otherwise). The real localizer never
runs here, and the store's processor= hook is the same seam the CP2-CP4 suites
use. Identity is likewise injected through the store's embedder hook
(set_embedder / the factory): perception.scenario_frames.SyntheticTagEmbedder
recognises painted tags, not objects. Nothing a scenario reports is an accuracy
measurement (perception.rubric.NO_CLAIM_SENTENCE).

store_factory(clock) -> store: the caller builds the store (a temporary
ObjectStore on a temporary database) around the runner's clock, a zero-argument
callable returning epoch seconds. The runner acknowledges the build's consent
version for the store's profile before any capture (actor "test").

Scenario schema (JSON object):

  name             str, the scenario's name (also seeds its device/session ids)
  basis            str, one sentence on what the scenario rests on (synthetic)
  clock_start_ms   int, the wall clock (epoch ms) at the first step
  calibrated       bool, default true: fixture observations are trusted
  identity         optional {"embedder": "synthetic_tag" | "none",
                             "calibration": {"calibration_id", "quantile", "n"?, "alpha"?, "approve"?}}
                   An embedder needs a calibration (registered, approved unless
                   approve is false). The caller's embedder= overrides "embedder".
  items            {handle: {"label": str, "tag": 0..6, "medication": bool?}}
                   label is what the fixture processor reports (the catalogue
                   name); tag selects the painted core colour (and the synthetic
                   embedder's prototype).
  steps            list of steps, each {"kind": ...}:

    episode   {"after_ms"?: int (default 1000), "duration_ms"?: int (default 1200),
               "actor"?: wearer | other_person | unknown (default wearer),
               "placements": [{"item": handle, "outcome": placed_on_surface | picked_up |
                               uncertain | sighted, "to"?: [x1, y1, x2, y2], "location"?: str,
                               "continuity"?: bool}],
               "calibrated"?: bool, "process"?: bool (default true)}
              or the one-placement shorthand "item" / "outcome" / "to" / "location"
              at the step level. The packet's pre_contact keyframe shows the
              scene before the placements, the rest keyframe after; the fixture
              processor emits one observation per placement at the rest frame
              (a pickup's region is where the item was taken from; a picked-up
              or uncertain item leaves the scene). continuity (default: true
              without an embedder, false with one) gives the observation the
              handle's continuity id, the store's first-choice association for
              trusted observations within a session (the CP2 fixture rule);
              without it, and without an embedder, every observation is a new item.
    idle      {"after_ms"?: int (default 30000), "absent"?: [handle, ...]}
              one idle keyframe of the scene; items listed absent leave their
              place (unobserved). The runner runs reobserve right after it.
    correction {"op": "link", "keep": handle, "other": handle}
               {"op": "unlink", "item": handle, "observation": "latest" | int, "as"?: new handle}
               {"op": "assign", "item": handle, "observation": "unresolved" | observation_id}
               {"op": "rename", "item": handle, "name": str}
    gap       {"reason": str, "duration_ms": int,
               "moves"?: [{"item": handle, "to": [..] | null, "location"?: str}]}
              coverage loss: the clock advances, nothing is captured, the moves
              happen unobserved, and a telemetry window reporting the gap is
              posted (so coverage() shows it and every item placed before the
              gap reads gap_since: a later query is hedged by ROW_COVERAGE_GAP
              until fresh evidence of the item arrives).
    advance   {"ms" | "minutes" | "hours" | "days": number, "process"?: bool}
    query     {"text": str, "truth": {"item": handle | null, "medication"?: bool,
                                      any explicit rubric truth key},
               "expect"?: {"outcome"?: rubric outcome, "shape"?: answer shape},
               "process"?: bool}
              runs apply_retention + reobserve (and process_pending when asked),
              posts the telemetry window since the last post, answers, scores.
              The truth's item handle resolves to the store's item id through the
              handle's attributed evidence (None when unresolved); location_text_now,
              location_status_now and moved_since come from the scene state
              unless given explicitly.

Each query yields one record: {"step", "kind": "query", "clock_ms", "query",
"answer", "truth", "outcome", "fidelity", "expected", "ok", "coverage"}; "ok"
is None without expectations, else whether every expectation held. The list
returned is these records in order (rubric.summarize takes it as is).

Example (scripts/scenario_example.json is the same text):

{
  "name": "example_fast_put_down",
  "basis": "synthetic scene; expectations are software-correctness checks, not accuracy",
  "clock_start_ms": 1790000000000,
  "items": {"pills": {"label": "pill bottle", "tag": 2, "medication": true}},
  "steps": [
    {"kind": "episode", "duration_ms": 600, "item": "pills", "outcome": "placed_on_surface",
     "to": [60, 40, 100, 80], "location": "kitchen counter"},
    {"kind": "query", "text": "where is my pill bottle", "truth": {"item": "pills", "medication": true},
     "expect": {"outcome": "correct", "shape": "confident"}},
    {"kind": "gap", "reason": "screen_lock", "duration_ms": 300000,
     "moves": [{"item": "pills", "to": [20, 20, 56, 56], "location": "sofa"}]},
    {"kind": "idle", "after_ms": 30000},
    {"kind": "query", "text": "where is my pill bottle", "truth": {"item": "pills", "medication": true},
     "expect": {"outcome": "hedged-correct", "shape": "hedged"}}
  ]
}
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

try:
    from . import scenario_frames as frames
    from .consent import CONSENT_VERSION
    from .episode import MAX_WINDOW_MS
    from .localizer import LocalObservation
    from .reobservation import utc_day
    from .rubric import TRUTH_KEYS, fidelity, score
except ImportError:
    import scenario_frames as frames
    from consent import CONSENT_VERSION
    from episode import MAX_WINDOW_MS
    from localizer import LocalObservation
    from reobservation import utc_day
    from rubric import TRUTH_KEYS, fidelity, score

STEP_KINDS = ("episode", "idle", "correction", "gap", "advance", "query")
OUTCOMES = ("placed_on_surface", "picked_up", "uncertain", "sighted")
ACTORS = ("wearer", "other_person", "unknown")
CORRECTION_OPS = ("link", "unlink", "assign", "rename")
CORRECTION_ACTOR = "test"
DEFAULT_EPISODE_AFTER_MS = 1000
DEFAULT_EPISODE_DURATION_MS = 1200
DEFAULT_IDLE_AFTER_MS = 30000
MAX_STEPS = 500
HANDLE = re.compile(r"[A-Za-z0-9_-]{1,40}")
# The CP2 code-only fixture calibration: trusted only through the processor seam.
FIXTURE_CALIBRATION = {"approved": True, "fixture_only": True, "calibration_id": "synthetic-scenario-cp5"}
# Synthetic analysis rate behind the telemetry windows the runner posts.
TELEMETRY_FPS = 5.0


class ScenarioError(ValueError):
    pass


def _int(value, name, *, low=0, high=10 ** 15):
    if isinstance(value, bool) or type(value) is not int or not low <= value <= high:
        raise ScenarioError(f"{name} must be an int in {low}..{high}")
    return value


def _handle(value, items):
    if not isinstance(value, str) or value not in items:
        raise ScenarioError(f"unknown item handle {value!r}")
    return value


class ScenarioProcessor:
    """The fixture processor: observation dicts per episode id, returned as
    LocalObservation rows when the store processes that episode."""
    def __init__(self):
        self.observations = {}
        self.calls = []

    def __call__(self, packet):
        self.calls.append(packet.episode_id)
        return [LocalObservation.model_validate(dict(value)) for value in self.observations.get(packet.episode_id, [])]


class _Scene:
    """Ground truth: where each item is (bbox + place text), where it was last
    observed placed, and the frames rendered from it."""
    def __init__(self, items):
        self.place = {handle: None for handle in items}        # (bbox, location) or None
        self.observed = {handle: None for handle in items}     # the place of the last observed placement
        self.tags = {handle: spec["tag"] for handle, spec in items.items()}

    def blocks(self, absent=()):
        return [(place[0], self.tags[handle]) for handle, place in self.place.items() if place is not None and handle not in absent]

    def jpeg_b64(self, absent=()):
        return frames.scene_jpeg_b64(self.blocks(absent))

    def moved_since(self, handle) -> bool:
        current, observed = self.place.get(handle), self.observed.get(handle)
        if observed is None:
            return current is not None
        return current is None or current[1] != observed[1] or current[0] != observed[0]


class ScenarioRun:
    def __init__(self, scenario, *, store_factory, embedder=None):
        self.scenario = self._check(scenario)
        self.now_ms = self.scenario["clock_start_ms"]
        self.store = store_factory(self.clock)
        self.embedder = self._attach_identity(embedder)
        self.processor = ScenarioProcessor()
        self.scene = _Scene(self.scenario["items"])
        self.device_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"pam-cp5-device:{self.scenario['name']}"))
        self.session_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"pam-cp5-session:{self.scenario['name']}"))
        # handle -> [(frame_id, bbox)] of the observations the processor emitted for it
        self.emitted = {handle: [] for handle in self.scenario["items"]}
        self.records = []
        self.events = []
        self.last_group = None
        self.window = {"since_ms": self.now_ms, "episodes": 0, "packets": 0, "idle": 0, "gaps": 0, "gap_ms": 0}
        self.store.acknowledge_consent(CONSENT_VERSION, CORRECTION_ACTOR)

    # --- clock -----------------------------------------------------------------
    def clock(self):
        return self.now_ms / 1000.0

    def _advance(self, ms):
        self.now_ms += _int(ms, "advance", high=10 ** 12)

    # --- validation --------------------------------------------------------------
    @staticmethod
    def _check(scenario):
        if not isinstance(scenario, dict):
            raise ScenarioError("scenario must be a JSON object")
        for key in ("name", "basis", "clock_start_ms", "steps"):
            if key not in scenario:
                raise ScenarioError(f"scenario lacks {key}")
        if not isinstance(scenario["name"], str) or not HANDLE.fullmatch(scenario["name"]):
            raise ScenarioError("scenario name must match [A-Za-z0-9_-]{1,40}")
        if not isinstance(scenario["basis"], str) or not scenario["basis"].strip():
            raise ScenarioError("scenario basis must be a sentence")
        _int(scenario["clock_start_ms"], "clock_start_ms", low=1)
        if type(scenario.get("calibrated", True)) is not bool:
            raise ScenarioError("calibrated must be a bool")
        items = scenario.get("items", {})
        if not isinstance(items, dict) or len(items) > frames.TAG_COUNT:
            raise ScenarioError(f"items must be an object of at most {frames.TAG_COUNT} handles")
        for handle, spec in items.items():
            if not HANDLE.fullmatch(handle) or not isinstance(spec, dict) or set(spec) - {"label", "tag", "medication"}:
                raise ScenarioError(f"item {handle!r} is malformed")
            if not isinstance(spec.get("label"), str) or not 1 <= len(spec["label"].strip()) <= 100:
                raise ScenarioError(f"item {handle!r} needs a label")
            _int(spec.get("tag", 0), "tag", high=frames.TAG_COUNT - 1)
            spec.setdefault("tag", 0)
            if type(spec.get("medication", False)) is not bool:
                raise ScenarioError(f"item {handle!r}: medication must be a bool")
        if len({spec["tag"] for spec in items.values()}) != len(items):
            raise ScenarioError("every item needs its own tag")
        steps = scenario["steps"]
        if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
            raise ScenarioError(f"steps must be a list of 1..{MAX_STEPS} steps")
        for index, step in enumerate(steps):
            if not isinstance(step, dict) or step.get("kind") not in STEP_KINDS:
                raise ScenarioError(f"step {index}: kind must be one of {STEP_KINDS}")
        identity = scenario.get("identity")
        if identity is not None and (not isinstance(identity, dict) or set(identity) - {"embedder", "calibration"}):
            raise ScenarioError("identity must be {embedder?, calibration?}")
        scenario["items"] = items
        return scenario

    # --- identity injection ----------------------------------------------------------
    def _attach_identity(self, embedder):
        identity = self.scenario.get("identity") or {}
        if embedder is None:
            choice = identity.get("embedder", "none")
            if choice == "synthetic_tag":
                embedder = frames.SyntheticTagEmbedder()
            elif choice not in (None, "none"):
                raise ScenarioError("identity.embedder must be 'synthetic_tag' or 'none'")
        if embedder is not None:
            self.store.set_embedder(embedder)
        calibration = identity.get("calibration")
        self.calibration_id = None
        if embedder is not None and calibration is None:
            raise ScenarioError("an embedder needs identity.calibration")
        if calibration is not None:
            if embedder is None:
                raise ScenarioError("identity.calibration needs an embedder")
            if not isinstance(calibration, dict) or not isinstance(calibration.get("calibration_id"), str):
                raise ScenarioError("identity.calibration needs a calibration_id")
            record = {"calibration_id": calibration["calibration_id"], "embedder": embedder.tag,
                      "alpha": calibration.get("alpha", 0.05), "quantile": calibration.get("quantile"),
                      "n": calibration.get("n", 40), "source": "synthetic", "created_ms": self.now_ms}
            self.store.register_calibration(record)
            if calibration.get("approve", True):
                self.store.approve_calibration(calibration["calibration_id"], CORRECTION_ACTOR)
            self.calibration_id = calibration["calibration_id"]
        return embedder

    def _calibration_dict(self):
        """What a trusted fixture observation names: the registered calibration
        when identity runs through the embedder (the store decides trust from the
        table), else the CP2 code-only fixture dict."""
        if self.calibration_id is not None:
            return {"calibration_id": self.calibration_id}
        return dict(FIXTURE_CALIBRATION)

    # --- handles -------------------------------------------------------------------
    def _resolve_handle(self, handle):
        """The store item that currently holds the handle's newest attributed
        observation (corrections applied), or None."""
        if handle is None:
            return None
        _handle(handle, self.scenario["items"])
        emitted = self.emitted.get(handle) or []
        if not emitted:
            return None
        evidence = {}
        for item in self.store.list_items(limit=200):
            for row in self.store.item_evidence(item["item_id"]):
                image = row.get("reference_image") or {}
                key = (row.get("frame_id"), tuple(image.get("bbox") or ()))
                evidence.setdefault(key, item["item_id"])
        for frame_id, bbox in reversed(emitted):
            found = evidence.get((frame_id, tuple(bbox)))
            if found is not None:
                return found
        return None

    def _item_id(self, handle):
        item_id = self._resolve_handle(handle)
        if item_id is None:
            raise ScenarioError(f"item {handle!r} is not attributed in the store")
        return item_id

    # --- telemetry -------------------------------------------------------------------
    def _post_telemetry(self):
        """Post the telemetry window(s) covering the time since the last post, the
        way the browser does every 60 s and at stop: window_ms is the wall time
        covered, gap_ms the part of it with no capture. A span longer than a day
        is posted as consecutive day-long windows (the counters ride on the last)."""
        total_ms = max(0, self.now_ms - self.window["since_ms"])
        if total_ms == 0:
            return  # a window covers time; the counters wait for the next post
        end = self.window["since_ms"]
        remaining = total_ms
        while True:
            window_ms = min(remaining, MAX_WINDOW_MS)
            end += window_ms
            remaining -= window_ms
            last = remaining <= 0
            counters = self.window if last else {"episodes": 0, "packets": 0, "idle": 0, "gaps": 0, "gap_ms": 0}
            analysed = max(0, int(round((window_ms - min(window_ms, counters["gap_ms"])) / 1000.0 * TELEMETRY_FPS)))
            body = {"schema_version": 1, "device_id": self.device_id, "session_id": self.session_id,
                    "t_ms": end - self.scenario["clock_start_ms"],
                    "clock_anchor": {"mono_ms": 0, "wall_ms": self.scenario["clock_start_ms"]}, "window_ms": window_ms,
                    "counters": {"frames_captured": analysed, "frames_analysed": analysed, "frames_skipped_busy": 0,
                                 "frames_dropped_backpressure": 0, "landmark_results": 0, "landmark_timeouts": 0,
                                 "episodes_started": counters["episodes"], "episodes_finished": counters["episodes"], "episodes_aborted": 0,
                                 "packets_sent": counters["packets"], "packets_acked": counters["packets"],
                                 "idle_sent": counters["idle"], "idle_dropped": 0, "gaps": counters["gaps"], "gap_ms": min(window_ms, counters["gap_ms"]),
                                 "bytes_sent": 0},
                    "timing": {"fps_observed": TELEMETRY_FPS, "infer_ms_p50": 0.0, "infer_ms_p95": 0.0, "tick_ms_p95": 0.0},
                    "settings": {"width": frames.SCENE_W, "height": frames.SCENE_H, "frame_rate": TELEMETRY_FPS}}
            self.store.ingest_telemetry(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            if last:
                break
        self.window = {"since_ms": self.now_ms, "episodes": 0, "packets": 0, "idle": 0, "gaps": 0, "gap_ms": 0}

    # --- steps -----------------------------------------------------------------------
    def run(self):
        for index, step in enumerate(self.scenario["steps"]):
            getattr(self, "_step_" + step["kind"])(index, step)
        self._post_telemetry()
        return self.records

    def _step_episode(self, index, step):
        items = self.scenario["items"]
        placements = step.get("placements")
        if placements is None:
            placements = [{key: step[key] for key in ("item", "outcome", "to", "location") if key in step}]
        if not isinstance(placements, list) or not 1 <= len(placements) <= 8:
            raise ScenarioError(f"step {index}: placements must list 1..8 items")
        actor = step.get("actor", "wearer")
        if actor not in ACTORS:
            raise ScenarioError(f"step {index}: actor must be one of {ACTORS}")
        calibrated = step.get("calibrated", self.scenario.get("calibrated", True))
        if type(calibrated) is not bool:
            raise ScenarioError(f"step {index}: calibrated must be a bool")
        self._advance(step.get("after_ms", DEFAULT_EPISODE_AFTER_MS))
        duration = _int(step.get("duration_ms", DEFAULT_EPISODE_DURATION_MS), "duration_ms", low=1, high=3600000)
        episode_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"pam-cp5-episode:{self.scenario['name']}:{index}"))
        start_ms = self.now_ms
        end_ms = start_ms + duration
        pre_jpeg = self.scene.jpeg_b64()
        observations, seen = [], set()
        for placement in placements:
            if not isinstance(placement, dict) or set(placement) - {"item", "outcome", "to", "location", "continuity"}:
                raise ScenarioError(f"step {index}: placement keys are item, outcome, to, location, continuity")
            handle = _handle(placement.get("item"), items)
            continuity = placement.get("continuity", self.embedder is None)
            if type(continuity) is not bool:
                raise ScenarioError(f"step {index}: continuity must be a bool")
            if handle in seen:
                raise ScenarioError(f"step {index}: {handle!r} placed twice")
            seen.add(handle)
            outcome = placement.get("outcome", "placed_on_surface")
            if outcome not in OUTCOMES:
                raise ScenarioError(f"step {index}: outcome must be one of {OUTCOMES}")
            location = placement.get("location")
            if location is not None and (not isinstance(location, str) or not 1 <= len(location.strip()) <= 600):
                raise ScenarioError(f"step {index}: location must be a short string")
            previous = self.scene.place[handle]
            if outcome == "placed_on_surface":
                if placement.get("to") is None or location is None:
                    raise ScenarioError(f"step {index}: a placement needs 'to' and 'location'")
                bbox = frames.check_bbox(placement["to"])
                self.scene.place[handle] = (bbox, location)
                self.scene.observed[handle] = (bbox, location)
            elif outcome == "sighted":
                bbox = frames.check_bbox(placement["to"]) if placement.get("to") is not None else (previous[0] if previous else None)
                if bbox is None:
                    raise ScenarioError(f"step {index}: a sighting of {handle!r} needs 'to' (it is not in the scene)")
                place = location if location is not None else (previous[1] if previous else None)
                self.scene.place[handle] = (bbox, place) if place is not None else (bbox, None)
            else:  # picked_up, uncertain: the item leaves the scene
                if previous is None and placement.get("to") is None:
                    raise ScenarioError(f"step {index}: {handle!r} is not in the scene to be picked up")
                bbox = frames.check_bbox(placement["to"]) if placement.get("to") is not None else previous[0]
                self.scene.place[handle] = None
                self.scene.observed[handle] = None
            observations.append((handle, bbox, outcome, location if outcome == "placed_on_surface" else None, continuity))
        rest_jpeg = self.scene.jpeg_b64()
        pre_id, rest_id = episode_id + "-pre", episode_id + "-rest"
        packet = {"schema_version": 1, "episode_id": episode_id, "device_id": self.device_id, "session_id": self.session_id,
                  "t_start_ms": start_ms - self.scenario["clock_start_ms"], "t_end_ms": end_ms - self.scenario["clock_start_ms"],
                  "clock_anchor": {"mono_ms": 0, "wall_ms": self.scenario["clock_start_ms"]},
                  "capture": {"width": frames.SCENE_W, "height": frames.SCENE_H}, "analysis": {"width": frames.ANALYSIS_W, "height": frames.ANALYSIS_H},
                  "keyframes": [{"frame_id": pre_id, "t_ms": start_ms - self.scenario["clock_start_ms"], "role": "pre_contact", "jpeg_b64": pre_jpeg},
                                {"frame_id": rest_id, "t_ms": end_ms - self.scenario["clock_start_ms"], "role": "rest", "jpeg_b64": rest_jpeg}],
                  "carry_burst": [], "landmarks": [], "gaps": [], "outcome_hint": "released" if any(o[2] == "placed_on_surface" for o in observations) else "hand_gone",
                  "capture_mode": "automatic"}
        scripted = []
        for handle, bbox, outcome, location, continuity in observations:
            spec = items[handle]
            # Continuity (the fixture's "the tracker never lost it") is the store's
            # first-choice association for trusted observations within one session;
            # it is withheld when identity is meant to go through the embedder.
            scripted.append({"frame_id": rest_id, "bbox": [float(v) for v in bbox], "label": spec["label"], "actor": actor, "outcome": outcome,
                             "continuity_id": f"scenario-{handle}" if continuity and calibrated else None,
                             "identity_state": "trusted" if calibrated else "provisional",
                             "location_text": location, "confidence": 1.0 if calibrated else 0.0,
                             "confidence_basis": "SYNTHETIC scenario ground truth (fixture processor); not recognition",
                             "calibration": self._calibration_dict() if calibrated else {}})
            self.emitted[handle].append((rest_id, [float(v) for v in bbox]))
        self.processor.observations[episode_id] = scripted
        self.now_ms = end_ms
        ack = self.store.ingest_episode(json.dumps(packet, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        self.window["episodes"] += 1
        self.window["packets"] += 1
        self.events.append({"step": index, "kind": "episode", "episode_id": episode_id, "ack": ack["status"], "clock_ms": self.now_ms})
        if step.get("process", True):
            self._process()

    def _process(self):
        counts = self.store.process_pending(processor=self.processor)
        if counts["failed"]:
            raise ScenarioError("local processing failed for a scripted episode")
        return counts

    def _step_idle(self, index, step):
        absent = step.get("absent", [])
        if not isinstance(absent, list):
            raise ScenarioError(f"step {index}: absent must be a list of handles")
        for handle in absent:
            _handle(handle, self.scenario["items"])
        self._advance(step.get("after_ms", DEFAULT_IDLE_AFTER_MS))
        for handle in absent:
            self.scene.place[handle] = None
        frame_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"pam-cp5-idle:{self.scenario['name']}:{index}"))
        body = {"schema_version": 1, "device_id": self.device_id, "session_id": self.session_id, "frame_id": frame_id,
                "t_ms": self.now_ms - self.scenario["clock_start_ms"], "clock_anchor": {"mono_ms": 0, "wall_ms": self.scenario["clock_start_ms"]},
                "capture": {"width": frames.SCENE_W, "height": frames.SCENE_H}, "jpeg_b64": self.scene.jpeg_b64(), "motion_energy": 0.0}
        ack = self.store.ingest_idle(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        self.window["idle"] += 1
        # The server's worker re-observes within its maintenance interval; the
        # runner does it at once so a later retention pass cannot expire the frame first.
        counts = self.store.reobserve(self.now_ms)
        self.events.append({"step": index, "kind": "idle", "frame_id": frame_id, "retained": ack.get("retained"), "reobserve": counts, "clock_ms": self.now_ms})

    def _step_correction(self, index, step):
        op = step.get("op")
        if op not in CORRECTION_OPS:
            raise ScenarioError(f"step {index}: op must be one of {CORRECTION_OPS}")
        items = self.scenario["items"]
        if op == "link":
            keep, other = self._item_id(_handle(step.get("keep"), items)), self._item_id(_handle(step.get("other"), items))
            result = self.store.link_items(keep, other, CORRECTION_ACTOR)
        elif op == "unlink":
            handle = _handle(step.get("item"), items)
            item_id = self._item_id(handle)
            evidence = self.store.item_evidence(item_id)
            which = step.get("observation", "latest")
            row = evidence[-1] if which == "latest" else evidence[_int(which, "observation", high=len(evidence) - 1)]
            result = self.store.unlink_observation(row["observation_id"], CORRECTION_ACTOR, item_id=item_id)
            new_handle = step.get("as")
            if new_handle is not None:
                if not isinstance(new_handle, str) or not HANDLE.fullmatch(new_handle) or new_handle in items:
                    raise ScenarioError(f"step {index}: 'as' must be a fresh handle")
                items[new_handle] = dict(items[handle])
                image = row.get("reference_image") or {}
                self.emitted[new_handle] = [(row.get("frame_id"), list(image.get("bbox") or []))]
                self.scene.place[new_handle] = None
                self.scene.observed[new_handle] = None
                self.scene.tags[new_handle] = items[handle]["tag"]
        elif op == "assign":
            item_id = self._item_id(_handle(step.get("item"), items))
            which = step.get("observation", "unresolved")
            if which == "unresolved":
                if not self.last_group or not self.last_group.get("unresolved_observation_id"):
                    raise ScenarioError(f"step {index}: no group answer with an unresolved observation precedes this assign")
                which = self.last_group["unresolved_observation_id"]
            if not isinstance(which, str):
                raise ScenarioError(f"step {index}: observation must be 'unresolved' or an observation id")
            result = self.store.assign_observation(which, item_id, CORRECTION_ACTOR)
        else:
            item_id = self._item_id(_handle(step.get("item"), items))
            result = self.store.rename_item(item_id, step.get("name"))
        self.events.append({"step": index, "kind": "correction", "op": op, "item_id": result.get("item_id"), "clock_ms": self.now_ms})

    def _step_gap(self, index, step):
        reason = step.get("reason")
        if not isinstance(reason, str) or not 1 <= len(reason) <= 160:
            raise ScenarioError(f"step {index}: a gap needs a short reason")
        duration = _int(step.get("duration_ms"), "duration_ms", low=1, high=24 * 3600 * 1000)
        moves = step.get("moves", [])
        if not isinstance(moves, list):
            raise ScenarioError(f"step {index}: moves must be a list")
        from_ms = self.now_ms
        self._advance(duration)
        for move in moves:
            if not isinstance(move, dict) or set(move) - {"item", "to", "location"}:
                raise ScenarioError(f"step {index}: a move is {{item, to, location?}}")
            handle = _handle(move.get("item"), self.scenario["items"])
            if move.get("to") is None:
                self.scene.place[handle] = None
            else:
                bbox = frames.check_bbox(move["to"])
                location = move.get("location")
                if location is None:
                    raise ScenarioError(f"step {index}: a move to a place needs its location text")
                self.scene.place[handle] = (bbox, location)
        self.window["gaps"] += 1
        self.window["gap_ms"] += duration
        self._post_telemetry()
        self.events.append({"step": index, "kind": "gap", "reason": reason, "from_ms": from_ms, "to_ms": self.now_ms, "moves": len(moves)})

    def _step_advance(self, index, step):
        units = {"ms": 1, "minutes": 60000, "hours": 3600000, "days": 24 * 3600000}
        given = [key for key in units if key in step]
        if len(given) != 1:
            raise ScenarioError(f"step {index}: advance takes exactly one of {tuple(units)}")
        value = step[given[0]]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0 or value * units[given[0]] > 10 ** 12:
            raise ScenarioError(f"step {index}: invalid advance")
        self._advance(int(round(value * units[given[0]])))
        if step.get("process", False):
            self._process()
        self.events.append({"step": index, "kind": "advance", "clock_ms": self.now_ms})

    def _truth(self, index, spec):
        if not isinstance(spec, dict) or set(spec) - (set(TRUTH_KEYS) | {"item"}):
            raise ScenarioError(f"step {index}: truth keys are item, medication and the rubric keys")
        handle = spec.get("item")
        if handle is not None:
            _handle(handle, self.scenario["items"])
        place = self.scene.place.get(handle) if handle is not None else None
        truth = {"item_id": self._resolve_handle(handle) if handle is not None else None,
                 "location_status_now": "placed" if place is not None and place[1] is not None else "unknown",
                 "location_text_now": place[1] if place is not None else None,
                 "moved_since": self.scene.moved_since(handle) if handle is not None else False,
                 "medication": self.scenario["items"][handle].get("medication", False) if handle is not None else False}
        for key in TRUTH_KEYS:
            if key in spec:
                truth[key] = spec[key]
        return truth

    def _step_query(self, index, step):
        text = step.get("text")
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise ScenarioError(f"step {index}: a query needs text")
        if step.get("process", False):
            self._process()
        self.store.apply_retention(self.now_ms)
        self.store.reobserve(self.now_ms)
        self._post_telemetry()
        answer = self.store.answer_text(text)
        if answer["shape"] == "group":
            self.last_group = answer
        truth = self._truth(index, step.get("truth", {"item": None}))
        outcome = score(answer, truth)
        expected = step.get("expect")
        ok = None
        if expected is not None:
            if not isinstance(expected, dict) or set(expected) - {"outcome", "shape"}:
                raise ScenarioError(f"step {index}: expect takes outcome and/or shape")
            ok = True
            if "shape" in expected and answer["shape"] != expected["shape"]:
                ok = False
            if "outcome" in expected and outcome != expected["outcome"]:
                ok = False
        record = {"step": index, "kind": "query", "clock_ms": self.now_ms, "query": text, "answer": answer, "truth": truth,
                  "outcome": outcome, "fidelity": fidelity(answer, truth), "expected": expected, "ok": ok,
                  "coverage": self.store.coverage(utc_day(self.now_ms))}
        self.records.append(record)
        self.events.append({"step": index, "kind": "query", "shape": answer["shape"], "outcome": outcome, "ok": ok, "clock_ms": self.now_ms})


def load_scenario(path) -> dict:
    """The parsed scenario file (UTF-8 JSON object); ScenarioError when malformed."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ScenarioError(f"cannot read scenario {Path(path).name}: {type(exc).__name__}") from None
    return data


def run_scenario(path, *, store_factory, embedder=None) -> list:
    """Run the scenario file at `path` against store_factory(clock) and return the
    query records (see the module docstring). ScenarioError for a malformed
    scenario or a step the store refused."""
    scenario = load_scenario(path) if not isinstance(path, dict) else path
    run = ScenarioRun(scenario, store_factory=store_factory, embedder=embedder)
    return run.run()
