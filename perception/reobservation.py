"""Re-observation of placed items from idle keyframes (CP4, Part 1 rule 13).

The controller only produces evidence when a hand moves something. Idle keyframes
(perception.episode.IdleFrame, stored by EpisodeStoreMixin.ingest_idle) let the
store notice, without any hand event, that an item is still where it was placed
or is no longer there:

1. The idle frame is registered onto the item's reference keyframe with the
   localizer's own registration (perception.localizer.register_frames: LK +
   partial affine, identical bounds). A failed registration decides nothing
   (``unknown``).
2. ``region_diff`` is the mean absolute difference / 255 over the item's bbox
   (mapped through the registration) after the integer 3x3 box blur of
   perception.motion.box_blur3: ``<= REOBS_SAME_MAX`` is ``present``,
   ``>= REOBS_GONE_MIN`` is ``gone``, between is ``unknown``.
3. With an identity embedder AND an active calibration, ``present`` additionally
   requires the registered region's embedding to match the item's bank (the
   conformal set contains the item); otherwise the decision is diff-only and the
   written observation's identity stays ``provisional``.

Effects are written by ``ReobservationMixin.reobserve`` into the ``reobservations``
table (one row per item and frame, so a frame is never re-registered for the same
item) and, for ``present``, a promoted idle frame plus a ``local_observations`` row
with ``source: "reobservation"`` that the projection replays (observed_at_ms
advances, ageing resets). ``gone`` is derived by the projection from the table
(``stale_reason: "negative_reobservation"``); a later ``present`` reverses it.

Compute budget (Finance, coordinator fix round): the wall time of the
registration + embedding work is measured with time.perf_counter and summed per
profile and UTC day in the ``maintenance_counters`` table; once the day's
REOBS_CPU_BUDGET_S is spent, embeds are skipped (decisions stay diff-only and
``reobs_deferred`` counts them). A frame-level gate also skips the registration
and embedding of a frame that barely differs from the previous frame that showed
the item present (``gated`` decisions, result present, registered 0).

REOBS_SAME_MAX, REOBS_GONE_MIN, REOBS_REFRESH_MS and REOBS_CPU_BUDGET_S are
INITIAL VALUES from the build plan / finance review, not measurements
(experiment P-105).
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import time
from datetime import datetime, timezone

try:
    from .localizer import gray_at, register_frames
    from .motion import box_blur3
    from .identity import ConformalMatcher, padded_crop_box, l2_normalise
except ImportError:
    from localizer import gray_at, register_frames
    from motion import box_blur3
    from identity import ConformalMatcher, padded_crop_box, l2_normalise

REOBS_SAME_MAX = 0.06
REOBS_GONE_MIN = 0.18
# Unchanged-frame gate: whole-frame blurred mean difference below this against the
# previous frame that showed the item present reads present without registration.
REOBS_GATE_MAX = REOBS_SAME_MAX / 2
# A present decision promotes the frame and writes an observation row the first
# time after a hand event, whenever it reverses a stale or inferred state, and
# otherwise at most once per REOBS_REFRESH_MS (the ledger is not fed one row per
# 30 s idle frame; the reobservations table still records every decision).
REOBS_REFRESH_MS = 3600 * 1000
# Per-profile, per-UTC-day wall-time budget for re-observation work (seconds).
REOBS_CPU_BUDGET_S = 300
MAX_REOBS_LIMIT = 256


def utc_day(now_ms) -> str:
    """UTC calendar day key of an epoch-millisecond time ("YYYY-MM-DD")."""
    return datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def frame_diff(jpeg_a, jpeg_b, analysis, bbox=None, capture=None) -> float:
    """Unregistered blurred mean absolute difference / 255 of two JPEGs at the
    analysis resolution: the whole frame, and, when bbox (capture pixels) is
    given, the larger of that and the difference over the bbox window. The
    region term matters: a small item vanishing moves the whole-frame mean by
    far less than REOBS_GATE_MAX (measured 0.006 for a 20x20 block in 160x120),
    so a frame-only gate would read it as unchanged."""
    aw, ah = analysis
    a = gray_at(base64.b64encode(jpeg_a).decode("ascii"), aw, ah)
    b = gray_at(base64.b64encode(jpeg_b).decode("ascii"), aw, ah)
    value = region_diff(a, b, (0, 0, aw, ah))
    if bbox is not None and capture is not None:
        sx, sy = aw / capture[0], ah / capture[1]
        window, kept = _window([bbox[0] * sx, bbox[1] * sy, bbox[2] * sx, bbox[3] * sy], aw, ah)
        if window is None or kept < MIN_REGION_COVERAGE:
            return 1.0  # no usable region: never gate
        value = max(value, region_diff(a, b, window))
    return value
# The registered region must keep this share of its pixels inside the frame and
# inside the registration's valid (non-border) area, else the frame decides nothing.
MIN_REGION_COVERAGE = 0.9
# Containment (CP4): A's rest bbox at least this far inside B's rest bbox.
CONTAINMENT_INSIDE = 0.8


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def inside_fraction(inner, outer) -> float:
    """Share of inner's area that lies inside outer (both [x1, y1, x2, y2])."""
    ax1, ay1, ax2, ay2 = (float(v) for v in inner)
    bx1, by1, bx2, by2 = (float(v) for v in outer)
    area = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    if area <= 0:
        return 0.0
    overlap = max(0.0, min(ax2, bx2) - max(ax1, bx1)) * max(0.0, min(ay2, by2) - max(ay1, by1))
    return overlap / area


def transform_bbox(matrix, bbox) -> list[float]:
    """Axis-aligned bounds of bbox's four corners under the 2x3 affine matrix."""
    x1, y1, x2, y2 = (float(v) for v in bbox)
    xs, ys = [], []
    for x, y in ((x1, y1), (x2, y1), (x1, y2), (x2, y2)):
        xs.append(matrix[0][0] * x + matrix[0][1] * y + matrix[0][2])
        ys.append(matrix[1][0] * x + matrix[1][1] * y + matrix[1][2])
    return [min(xs), min(ys), max(xs), max(ys)]


def _window(bbox, width, height):
    """Integer window [x1, y1, x2, y2) of a float bbox clamped to the frame, and
    the share of the unclamped area that survived clamping (0 when empty)."""
    x1, y1, x2, y2 = (float(v) for v in bbox)
    if not all(math.isfinite(v) for v in (x1, y1, x2, y2)) or x2 <= x1 or y2 <= y1:
        return None, 0.0
    full = (x2 - x1) * (y2 - y1)
    cx1, cy1 = max(0, int(math.floor(x1))), max(0, int(math.floor(y1)))
    cx2, cy2 = min(width, int(math.ceil(x2))), min(height, int(math.ceil(y2)))
    if cx2 <= cx1 or cy2 <= cy1:
        return None, 0.0
    kept = (min(x2, width) - max(x1, 0)) * (min(y2, height) - max(y1, 0))
    return (cx1, cy1, cx2, cy2), max(0.0, kept / full)


def region_diff(gray_a, gray_b, window) -> float:
    """Mean absolute difference / 255 between box_blur3(gray_a) and
    box_blur3(gray_b) over the integer window [x1, y1, x2, y2)."""
    import numpy as np
    x1, y1, x2, y2 = window
    a = box_blur3(gray_a).astype(np.int32)[y1:y2, x1:x2]
    b = box_blur3(gray_b).astype(np.int32)[y1:y2, x1:x2]
    if a.size == 0:
        raise ValueError("Empty region")
    return float(np.abs(a - b).mean()) / 255.0


def registered_region_diff(reference_jpeg, idle_jpeg, bbox, capture, analysis) -> dict | None:
    """Register the reference keyframe onto the idle frame and difference the
    item's region.

    reference_jpeg / idle_jpeg: raw JPEG bytes, both at capture resolution
    (capture = (width, height)); the registration runs at analysis resolution
    (analysis = (width, height)) exactly as localize does. bbox is the item's
    capture-resolution [x1, y1, x2, y2] in the reference frame. Returns None when
    the registration is unsupported or the mapped region leaves the frame, else
    {"region_diff": float, "bbox": [..] (the region in the idle frame, capture
    pixels), "inliers": int}.
    """
    import cv2
    import numpy as np
    width, height = capture
    aw, ah = analysis
    ref = gray_at(base64.b64encode(reference_jpeg).decode("ascii"), aw, ah)
    idle = gray_at(base64.b64encode(idle_jpeg).decode("ascii"), aw, ah)
    matrix, inliers = register_frames(ref, idle)
    if matrix is None:
        return None
    sx, sy = aw / width, ah / height
    scaled = [bbox[0] * sx, bbox[1] * sy, bbox[2] * sx, bbox[3] * sy]
    mapped = transform_bbox(matrix, scaled)
    window, kept = _window(mapped, aw, ah)
    if window is None or kept < MIN_REGION_COVERAGE:
        return None
    warped = cv2.warpAffine(ref, matrix, (aw, ah))
    valid = cv2.warpAffine(np.full_like(ref, 255), matrix, (aw, ah))
    valid = cv2.erode(valid, np.ones((7, 7), np.uint8))
    x1, y1, x2, y2 = window
    if float((valid[y1:y2, x1:x2] == 255).mean()) < MIN_REGION_COVERAGE:
        return None
    diff = region_diff(warped, idle, window)
    out = [max(0.0, min(width, mapped[0] / sx)), max(0.0, min(height, mapped[1] / sy)),
           max(0.0, min(width, mapped[2] / sx)), max(0.0, min(height, mapped[3] / sy))]
    if out[2] <= out[0] or out[3] <= out[1]:
        return None
    return {"region_diff": round(diff, 6), "bbox": [round(v, 3) for v in out], "inliers": int(inliers)}


def diff_result(value) -> str:
    """present | gone | unknown from a region_diff (boundary inclusive both ways)."""
    if value <= REOBS_SAME_MAX:
        return "present"
    if value >= REOBS_GONE_MIN:
        return "gone"
    return "unknown"


class ReobservationMixin:
    """reobserve() for EpisodeStoreMixin; everything it needs from the store is
    the connection, the projection, banks and the calibration lookup."""

    def _reobservation_targets(self, db, limit):
        """(tasks, state) for one reobserve call: tasks are (item, row, record,
        reference bytes, frame row) tuples in idle-frame time order, at most limit;
        state carries per-item fields the write phase updates as it goes."""
        tasks = []
        items = self._projection(db, age=False)
        for item_id, item in sorted(items.items()):
            if not self._reobservable(item):
                continue
            row = db.execute("SELECT * FROM local_observations WHERE profile_id=? AND observation_id=? AND record IS NOT NULL AND erased=0",
                             (self.profile_id, item["observation_id"])).fetchone()
            if row is None:
                continue
            record = json.loads(row["record"])
            if not isinstance(record.get("bbox"), list) or not record.get("location_text"):
                continue
            # Frames first (cheap); the reference packet is parsed only when there is
            # something to check against it.
            frames = db.execute("""SELECT f.frame_id,f.device_id,f.session_id,f.t_wall_ms,f.width,f.height,f.jpeg FROM idle_frames f
                WHERE f.profile_id=? AND f.device_id=? AND f.t_wall_ms>? AND f.jpeg IS NOT NULL
                AND NOT EXISTS (SELECT 1 FROM reobservations r WHERE r.profile_id=f.profile_id AND r.item_id=? AND r.device_id=f.device_id AND r.frame_id=f.frame_id)
                ORDER BY f.t_wall_ms,f.frame_id LIMIT ?""", (self.profile_id, row["device_id"], item["observed_at_ms"] or 0, item_id, limit)).fetchall()
            if not frames:
                continue
            reference = self._keyframe_bytes(db, row)
            if reference is None:
                continue
            geometry = self._reference_geometry(db, row, record)
            if geometry is None:
                continue
            had_present = db.execute("SELECT 1 FROM reobservations WHERE profile_id=? AND item_id=? AND result='present' AND t_wall_ms>? LIMIT 1",
                                     (self.profile_id, item_id, item.get("last_event_ms") or 0)).fetchone() is not None
            for frame in frames:
                tasks.append({"item": dict(item, had_present=had_present), "row": row, "record": record,
                              "reference": reference, "geometry": geometry, "frame": frame})
        tasks.sort(key=lambda task: (task["frame"]["t_wall_ms"], task["frame"]["frame_id"], task["item"]["item_id"]))
        return tasks[:limit]

    def _reference_geometry(self, db, row, record):
        """(capture (w, h), analysis (w, h)) of the frame the reference bytes
        come from: the placement packet's dimensions, or for a reobservation row
        the idle frame's dimensions with the placement packet's analysis size
        (or a 2x downscale when that packet is gone)."""
        revision = db.execute("SELECT packet FROM episode_revisions WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no=?",
                              (self.profile_id, row["device_id"], row["episode_id"], row["revision_no"])).fetchone()
        analysis = None
        capture = None
        if revision is not None and revision[0] is not None:
            try:
                from .episode import parse_packet
            except ImportError:
                from episode import parse_packet
            packet = parse_packet(bytes(revision[0]))
            capture = (packet.capture.width, packet.capture.height)
            analysis = (packet.analysis.width, packet.analysis.height)
        if record.get("source") == "reobservation":
            frame = db.execute("SELECT width,height FROM idle_frames WHERE profile_id=? AND device_id=? AND frame_id=?",
                               (self.profile_id, row["device_id"], record.get("frame_id"))).fetchone()
            if frame is None:
                return None
            capture = (frame["width"], frame["height"])
            if analysis is None:
                analysis = (max(1, capture[0] // 2), max(1, capture[1] // 2))
        if capture is None or analysis is None:
            return None
        return capture, analysis

    def reobserve(self, now_ms=None, *, limit=16) -> dict:
        """Run rule 13 over at most `limit` (item, idle frame) pairs and return
        counts: checked, present, gone, unknown, gated (pairs decided present by
        the unchanged-frame gate without a registration), promoted (frames
        promoted and observation rows written), embedded (identity-checked
        decisions), reobs_deferred (embeds skipped because the day's compute
        budget is spent), reobs_cpu_s (wall seconds this call charged to the
        budget), pending (pairs still unchecked). now_ms defaults to the injected
        clock. Idle frames are per device; only frames newer than the item's
        current placement time are considered, oldest first.
        """
        if type(limit) is not int or not 1 <= limit <= MAX_REOBS_LIMIT:
            raise ValueError("Invalid re-observation limit")
        now = self._now_ms() if now_ms is None else now_ms
        if isinstance(now, bool) or type(now) is not int or now < 0:
            raise ValueError("now_ms must be nonnegative epoch milliseconds")
        counts = {"checked": 0, "present": 0, "gone": 0, "unknown": 0, "gated": 0, "promoted": 0, "embedded": 0,
                  "reobs_deferred": 0, "reobs_cpu_s": 0.0, "pending": 0}
        embedder = self.embedder
        tag = embedder.tag if embedder is not None else None
        day = utc_day(now)
        with self._connection() as db:
            if not db.execute("SELECT 1 FROM idle_frames WHERE profile_id=? AND jpeg IS NOT NULL LIMIT 1", (self.profile_id,)).fetchone():
                return counts  # an empty cache: nothing to register, no projection replay
            tasks = self._reobservation_targets(db, limit)
            active, banks = None, {}
            if tasks and embedder is not None:
                active = self._active_calibration(db, tag)
                if active is not None:
                    assign, _, resolved = self._assignments(db)
                    tombstoned = {r[0] for r in db.execute("SELECT item_id FROM item_tombstones WHERE profile_id=?", (self.profile_id,))}
                    banks = self._banks(db, assign, resolved, tombstoned, tag)
            used = db.execute("SELECT value FROM maintenance_counters WHERE profile_id=? AND day=? AND name='reobs_cpu_s'", (self.profile_id, day)).fetchone()
            used = float(used[0]) if used else 0.0
            # The previous decided frame per item (for the unchanged-frame gate):
            # its result and, while it is still cached, its bytes.
            previous = {}
            for task in tasks:
                item_id = task["item"]["item_id"]
                if item_id in previous:
                    continue
                row = db.execute("""SELECT r.result,r.t_wall_ms,r.bbox,f.jpeg FROM reobservations r
                    LEFT JOIN idle_frames f ON f.profile_id=r.profile_id AND f.device_id=r.device_id AND f.frame_id=r.frame_id
                    WHERE r.profile_id=? AND r.item_id=? AND r.device_id=? AND r.t_wall_ms<?
                    ORDER BY r.t_wall_ms DESC LIMIT 1""", (self.profile_id, item_id, task["frame"]["device_id"], task["frame"]["t_wall_ms"])).fetchone()
                previous[item_id] = None if row is None else {"result": row["result"], "jpeg": None if row["jpeg"] is None else bytes(row["jpeg"]),
                                                               "bbox": json.loads(row["bbox"]) if row["bbox"] else None}
        decisions = []
        states = {}
        spent = 0.0
        for task in tasks:
            frame, record, item = task["frame"], task["record"], task["item"]
            item_id = item["item_id"]
            capture, analysis = task["geometry"]
            state = states.setdefault(item_id, {"observed_at_ms": item["observed_at_ms"] or 0, "had_present": item["had_present"],
                                                 "location_status": item["location_status"]})
            decision = {"task": task, "result": "unknown", "region_diff": None, "registered": 0, "embedded": 0, "gated": 0,
                        "bbox": None, "match": None, "refresh": False}
            started = time.perf_counter()
            refresh_due = (not state["had_present"] or state["location_status"] != "placed"
                           or frame["t_wall_ms"] - state["observed_at_ms"] >= REOBS_REFRESH_MS)
            last = previous.get(item_id)
            gated = False
            if (not refresh_due and last is not None and last["result"] == "present" and last["jpeg"] is not None
                    and last["bbox"] is not None):
                # Unchanged-frame gate: neither the whole frame nor the item's region
                # (the previous decision's bbox, same static camera, no registration)
                # differs from the frame that last showed the item present, so the item
                # is still present and no registration or embedding is spent on it.
                try:
                    gated = frame_diff(last["jpeg"], bytes(frame["jpeg"]), analysis, last["bbox"], capture) < REOBS_GATE_MAX
                except Exception:
                    gated = False
            if gated:
                decision.update(result="present", gated=1, bbox=list(last["bbox"]))
            else:
                try:
                    if (frame["width"], frame["height"]) == capture:
                        outcome = registered_region_diff(task["reference"], bytes(frame["jpeg"]), record["bbox"], capture, analysis)
                    else:
                        outcome = None
                except Exception:
                    outcome = None
                if outcome is not None:
                    decision.update(registered=1, region_diff=outcome["region_diff"], bbox=outcome["bbox"], result=diff_result(outcome["region_diff"]))
                    if decision["result"] == "present" and embedder is not None and active is not None and item_id in banks:
                        if used + spent + (time.perf_counter() - started) >= REOBS_CPU_BUDGET_S:
                            # Budget spent for today (Finance): the decision stays
                            # diff-only, so the observation's identity is provisional.
                            counts["reobs_deferred"] += 1
                        else:
                            decision["embedded"] = 1
                            try:
                                vector = self._embed_idle_region(embedder, bytes(frame["jpeg"]), outcome["bbox"], capture)
                                matched = ConformalMatcher(active["quantile"], tag, active["calibration_id"]).match(vector, banks, set())
                                decision["match"] = {"embedder": tag, "calibration_id": active["calibration_id"], "calibration_approved": active["approved"],
                                                     "state": matched["state"], "set": list(matched["set"])[:32],
                                                     "scores": {k: round(float(v), 6) for k, v in sorted(matched["scores"].items())[:32]}}
                                if item_id not in matched["set"]:
                                    decision["result"] = "unknown"
                            except Exception:
                                # Never persist exception text; without the identity check a
                                # 'present' the embedder was supposed to confirm is not decided.
                                decision["result"] = "unknown"
                                decision["match"] = {"embedder": tag, "calibration_id": active["calibration_id"], "state": "failed", "set": [], "scores": {}}
            spent += time.perf_counter() - started
            if decision["result"] == "present" and not gated and refresh_due:
                decision["refresh"] = True
                state.update(observed_at_ms=frame["t_wall_ms"], had_present=True, location_status="placed")
            previous[item_id] = {"result": decision["result"], "jpeg": bytes(frame["jpeg"]), "bbox": decision["bbox"]}
            decisions.append(decision)
        counts["reobs_cpu_s"] = round(spent, 4)
        if not decisions:
            with self._connection() as db:
                counts["pending"] = self._reobservation_pending(db)
            return counts
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO maintenance_counters(profile_id,day,name,value) VALUES(?,?,'reobs_cpu_s',?) "
                       "ON CONFLICT(profile_id,day,name) DO UPDATE SET value=value+excluded.value", (self.profile_id, day, spent))
            rebuild = False
            for decision in decisions:
                task = decision["task"]
                frame, item, row, record = task["frame"], task["item"], task["row"], task["record"]
                item_id = item["item_id"]
                db.execute("INSERT OR IGNORE INTO reobservations(profile_id,item_id,device_id,frame_id,t_wall_ms,result,region_diff,registered,embedded,decided_ms,gated,bbox) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                           (self.profile_id, item_id, frame["device_id"], frame["frame_id"], frame["t_wall_ms"], decision["result"],
                            decision["region_diff"], decision["registered"], decision["embedded"], now, decision["gated"],
                            _json(decision["bbox"]) if decision["bbox"] is not None else None))
                counts["checked"] += 1
                counts[decision["result"]] += 1
                counts["embedded"] += decision["embedded"]
                counts["gated"] += decision["gated"]
                if not decision["refresh"]:
                    continue
                confirmed = decision["embedded"] == 1 and decision["match"] is not None and decision["match"]["state"] in ("match", "ambiguous")
                identity_state = item["identity_status"] if confirmed and decision["match"].get("calibration_approved") else "provisional"
                if identity_state == "ambiguous":
                    identity_state = "provisional"
                signature = hashlib.sha256(_json([self.profile_id, item_id, frame["device_id"], frame["frame_id"], "reobservation"]).encode()).hexdigest()
                if db.execute("SELECT 1 FROM local_observations WHERE profile_id=? AND observation_id=?", (self.profile_id, signature)).fetchone():
                    continue
                placement_id = record.get("placement_observation_id") or row["observation_id"]
                new_record = {
                    "frame_id": frame["frame_id"], "bbox": decision["bbox"], "label": record.get("label", "unknown"),
                    "actor": "unknown", "outcome": "sighted", "continuity_id": None, "identity_state": identity_state,
                    "location_text": record.get("location_text"), "confidence": 0.0,
                    "confidence_basis": "registered idle-frame difference against the placement keyframe; not object or identity recognition",
                    "calibration": {"calibration_id": decision["match"]["calibration_id"]} if confirmed else {},
                    "session_id": frame["session_id"], "clock_status": "ok", "capture_mode": "automatic",
                    "observed_at_ms": frame["t_wall_ms"], "item_id": item_id, "observation_id": signature,
                    "device_id": row["device_id"], "episode_id": row["episode_id"], "revision_no": row["revision_no"],
                    "source": "reobservation", "identity_source": "reobservation", "location_status": "placed",
                    "placement_observation_id": placement_id, "region_diff": decision["region_diff"],
                    "registered": True, "embedded": decision["embedded"] == 1}
                if decision["match"] is not None:
                    new_record["match"] = decision["match"]
                # CP5: the row carries the consent version the idle frame was captured under.
                consent = db.execute("SELECT consent_version FROM idle_frames WHERE profile_id=? AND device_id=? AND frame_id=?",
                                     (self.profile_id, frame["device_id"], frame["frame_id"])).fetchone()
                db.execute("INSERT INTO local_observations(profile_id,observation_id,item_id,device_id,episode_id,revision_no,observed_at_ms,decided_at_ms,record,candidates,erased,consent_version) VALUES(?,?,?,?,?,?,?,?,?,NULL,0,?)",
                           (self.profile_id, signature, item_id, row["device_id"], row["episode_id"], row["revision_no"], frame["t_wall_ms"], now, _json(new_record),
                            consent[0] if consent is not None else None))
                db.execute("UPDATE idle_frames SET promoted=1 WHERE profile_id=? AND device_id=? AND frame_id=?", (self.profile_id, frame["device_id"], frame["frame_id"]))
                counts["promoted"] += 1
                rebuild = True
            if rebuild or counts["gone"]:
                self._rebuild_projection(db)
            counts["pending"] = self._reobservation_pending(db)
        return counts

    @staticmethod
    def _reobservable(item) -> bool:
        """Placed or inferred items with a reference image, plus items stale only
        by a negative re-observation (so a later present can reverse it)."""
        if not item.get("reference_image"):
            return False
        status = item.get("location_status")
        return status in ("placed", "inferred") or (status == "stale" and item.get("stale_reason") == "negative_reobservation")

    def _reobservation_pending(self, db) -> int:
        """Unchecked (item, frame) pairs for re-observable items (bounded count)."""
        items = self._projection(db, age=False)
        total = 0
        for item in items.values():
            if not self._reobservable(item):
                continue
            row = db.execute("SELECT device_id FROM local_observations WHERE profile_id=? AND observation_id=?", (self.profile_id, item["observation_id"])).fetchone()
            if row is None:
                continue
            total += db.execute("""SELECT count(*) FROM idle_frames f WHERE f.profile_id=? AND f.device_id=? AND f.t_wall_ms>? AND f.jpeg IS NOT NULL
                AND NOT EXISTS (SELECT 1 FROM reobservations r WHERE r.profile_id=f.profile_id AND r.item_id=? AND r.device_id=f.device_id AND r.frame_id=f.frame_id)""",
                               (self.profile_id, row["device_id"], item["observed_at_ms"] or 0, item["item_id"])).fetchone()[0]
        return total

    @staticmethod
    def _embed_idle_region(embedder, jpeg, bbox, capture):
        """Embed the registered region of an idle frame (padded crop, no mask: an
        idle frame has no hand by construction and no diff mask)."""
        import cv2
        import numpy as np
        try:
            from .episode import decode_jpeg
        except ImportError:
            from episode import decode_jpeg
        image = decode_jpeg(base64.b64encode(jpeg).decode("ascii"))
        if image.ndim == 2:
            rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        elif image.shape[2] == 4:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGRA2RGB)
        else:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        width, height = capture
        x1, y1, x2, y2 = padded_crop_box(bbox, width, height)
        crop = np.ascontiguousarray(rgb[y1:y2, x1:x2])
        vector = np.asarray(embedder.embed(crop, None), dtype=np.float32).reshape(-1)
        if vector.size != embedder.dim:
            raise ValueError("Embedder returned the wrong dimension")
        return l2_normalise(vector)
