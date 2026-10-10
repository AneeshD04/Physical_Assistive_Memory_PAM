"""CP4 shared fixtures and their self-tests (tester, 2026-10-09).

    python3 -B server/test_cp4_fixtures.py -v            # self-tests (no builder code needed)
    python3 -B server/test_cp4_fixtures.py --write-goldens  # regenerate server/fixtures/cp4/*.json

Authority: docs/BUILD_PLAN.md "CP4 in detail: re-observation, retention and erasure"
(architect, 2026-10-09) and docs/BUILD_CONTRACT.md. Everything the CP4 suites share
lives here so that a builder spelling that differs from the plan is a one-line fix:

  * synthetic re-observation frames (a seeded smooth-blob texture plus a distinctive
    block at the item bbox; present / gone / partial / translated / flat variants) and
    an independent registration + region_diff oracle that copies the localizer's
    arithmetic (LK + partial affine, same bounds) and perception.motion.box_blur3;
  * the stored goldens server/fixtures/cp4/reobservation_goldens.json (base64 JPEGs,
    the oracle's measured region_diff at full and half resolution, the expected
    verdicts, the basis string);
  * idle-packet and episode-packet builders, scripted observations, a store-level
    fixture (Cp4Fixture) on the bootstrap guards, the v1 ObjectStore fixture builder
    for the migration suite, the synthetic PII markers and the database/file scanners
    for the erasure suite, and `constant()` / `call()` adapters for builder spellings.

Why not the bootstrap checkerboard: measured here (FixtureSelfTests), pyramidal LK
aliases on a periodic 8 px checkerboard once the block is removed (only ~100 of 242
corners track, RANSAC inliers ~0.56), so the localizer's registration REFUSES the
"gone" frame and no decision could ever be reached. A seeded blob texture (unique
local structure) registers in every case, which is what the re-observation rule
needs. Nothing here measures a real camera; thresholds are the plan's initial values.
"""
from __future__ import annotations

import base64
import contextlib
import copy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import uuid

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
import test_memory_bootstrap as bootstrap  # noqa: E402
import test_cp3_identity as identity  # noqa: E402

FIXTURES = ROOT / "server" / "fixtures" / "cp4"
GOLDENS = FIXTURES / "reobservation_goldens.json"
BASIS = "synthetic golden, authored by the tester 2026-10-09; thresholds are initial values"
ANCHOR_MS = bootstrap.ANCHOR_MS
DEVICE = bootstrap.DEVICE
SESSION = bootstrap.SESSION
OTHER_DEVICE = "33333333-3333-4333-8333-333333333333"
ACTOR = "test"                      # closed actor set (B-15): caregiver_pin | operator | test
HOUR_MS = 3600 * 1000
DAY_MS = 24 * HOUR_MS

# Plan values (CP4 interfaces). The suites read the builder's constants through
# constant() and pin them against these.
PLAN = {
    "IDLE_KEYFRAME_MS": 30000, "MAX_IDLE_BYTES": 256 * 1024, "IDLE_TTL_MS": 24 * HOUR_MS,
    "IDLE_MAX_PER_DAY": 2880, "IDLE_CACHE_BYTES": 200 * 1024 * 1024,
    "REOBS_SAME_MAX": 0.06, "REOBS_GONE_MIN": 0.18, "CROP_PAD": 0.10,
    # Coordinator ruling 8 (Finance): episodes_days 30, not the plan's 90; ranges unchanged.
    "CONSENT_VERSION": "rig-2026-10", "EPISODES_DAYS": 30, "IDLE_HOURS": 24, "LANDMARKS_HOURS": 72,
}
CONSENT_VERSION = bootstrap.CONSENT_VERSION
ERASE_ALL_PHRASE = "ERASE EVERYTHING"
RETENTION_FIELDS = {"consent_version", "episodes_days", "idle_hours", "landmarks_hours", "updated_ms"}
RETENTION_COUNTS = {"idle_cached", "idle_promoted", "revisions_expired", "landmarks_reduced"}
IDLE_FIELDS = {"schema_version", "device_id", "session_id", "frame_id", "t_ms", "clock_anchor", "capture", "jpeg_b64", "motion_energy"}
# CP2 code-only trusted injection (docs/BUILD_CONTRACT.md decision 2).
FIXTURE_CAL = {"approved": True, "fixture_only": True, "calibration_id": "synthetic-only-cp4"}

# --- synthetic scene ------------------------------------------------------------------------
SCENE_W, SCENE_H = 160, 120
ANALYSIS_W, ANALYSIS_H = 80, 60
BLOCK_BBOX = [60.0, 40.0, 100.0, 80.0]      # the item: a 40x40 block, capture pixels
BLOCK_COLOUR = (40, 220, 240)               # BGR; grey ~205 against a texture of mean ~128
PARTIAL_FRACTION = 0.6                      # "partial": only this fraction of the block remains (diff ~0.12, mid-band)
TEXTURE_SEED, TEXTURE_CELL, TEXTURE_PAD = 2026, 4, 16
TRANSLATION = (3, 2)                        # the "translated" variant: (dx, dy) capture pixels
SQUARE = identity.SQUARE                    # 24: CP3 tagged square (instance tag in the green channel)
TAG_LEFT, TAG_RIGHT = identity.LEFT, identity.RIGHT  # (20, 40), (100, 40)


def _texture():
    rng = np.random.default_rng(TEXTURE_SEED)
    shape = ((SCENE_H + 2 * TEXTURE_PAD) // TEXTURE_CELL, (SCENE_W + 2 * TEXTURE_PAD) // TEXTURE_CELL)
    coarse = rng.integers(20, 236, shape).astype(np.uint8)
    return cv2.resize(coarse, (SCENE_W + 2 * TEXTURE_PAD, SCENE_H + 2 * TEXTURE_PAD), interpolation=cv2.INTER_CUBIC)


TEXTURE = _texture()


def scene_image(*, block="present", dx=0, dy=0, flat=False, squares=()):
    """BGR uint8 scene: the seeded blob texture shifted by (dx, dy), the item block
    ("present", "absent" or "partial") and optional CP3 tagged squares
    [(x, y, size, tag)], all shifted with the texture. flat=True is a featureless frame."""
    if flat:
        return np.full((SCENE_H, SCENE_W, 3), 128, np.uint8)
    if not (abs(dx) <= TEXTURE_PAD and abs(dy) <= TEXTURE_PAD):
        raise ValueError("translation exceeds the texture padding")
    gray = TEXTURE[TEXTURE_PAD - dy:TEXTURE_PAD - dy + SCENE_H, TEXTURE_PAD - dx:TEXTURE_PAD - dx + SCENE_W]
    image = np.repeat(gray[:, :, None], 3, axis=2).copy()
    x1, y1, x2, y2 = (int(v) for v in BLOCK_BBOX)
    if block == "present":
        image[y1 + dy:y2 + dy, x1 + dx:x2 + dx] = BLOCK_COLOUR
    elif block == "partial":
        image[y1 + dy:y2 + dy, x1 + dx:x1 + dx + int((x2 - x1) * PARTIAL_FRACTION)] = BLOCK_COLOUR
    elif block != "absent":
        raise ValueError("block must be present, absent or partial")
    for x, y, size, tag in squares:
        image[y + dy:y + dy + size, x + dx:x + dx + size] = identity.tag_colour(tag)
    return image


def jpeg_b64(image, quality=90):
    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise AssertionError("Synthetic JPEG encoding failed")
    return base64.b64encode(data.tobytes()).decode("ascii")


def scene_jpeg(quality=90, **kwargs):
    return jpeg_b64(scene_image(**kwargs), quality)


def decode_gray(encoded):
    image = cv2.imdecode(np.frombuffer(base64.b64decode(encoded), np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError("not a JPEG")
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image


def square_bbox(x, y, size=SQUARE):
    return [float(x), float(y), float(x + size), float(y + size)]


# --- registration and region_diff oracle (perception/localizer.py lines 66-82, motion.box_blur3) ---
def register(before, after):
    """(matrix, reason): the localizer's registration of `after` to `before`, or (None,
    why). Identical arithmetic and bounds; generalised to any grey array pair."""
    if min(float(before.std()), float(after.std())) < 8:
        return None, "flat"
    points = cv2.goodFeaturesToTrack(before, 250, .02, 7)
    if points is None or len(points) < 12:
        return None, "few corners"
    tracked, status, _ = cv2.calcOpticalFlowPyrLK(before, after, points, None)
    if tracked is None or status is None:
        return None, "lk"
    keep = status.ravel() == 1
    if int(keep.sum()) < 12:
        return None, "few tracked"
    matrix, inliers = cv2.estimateAffinePartial2D(points[keep], tracked[keep], method=cv2.RANSAC, ransacReprojThreshold=2)
    if matrix is None or inliers is None or float(inliers.mean()) < .8:
        return None, "inliers"
    scale = float(np.linalg.norm(matrix[:, 0]))
    if not .95 <= scale <= 1.05 or float(np.linalg.norm(matrix[:, 2])) > min(before.shape) * .1:
        return None, "bounds"
    return matrix, "ok"


def region_diff(reference, probe, bbox, *, scale=1.0, convention="reference"):
    """The plan's region_diff: mean |blur3(a) - blur3(b)| / 255 over the item bbox after
    registering the probe (idle frame) to the reference keyframe; None when the
    registration fails. convention "reference" warps the probe into reference space
    (bbox as given); "probe" is the localizer's own direction (reference warped onto
    the probe, bbox mapped through the matrix). The two agree to ~1e-3 on these frames."""
    from perception import motion
    matrix, why = register(reference, probe)
    if matrix is None:
        return None, why
    height, width = reference.shape
    if convention == "reference":
        warped = cv2.warpAffine(probe, matrix, (width, height), flags=cv2.WARP_INVERSE_MAP)
        x1, y1, x2, y2 = (int(round(v * scale)) for v in bbox)
        a, b = reference, warped
    else:
        warped = cv2.warpAffine(reference, matrix, (width, height))
        corners = np.array([[bbox[0] * scale, bbox[1] * scale], [bbox[2] * scale, bbox[3] * scale]], dtype=np.float64)
        mapped = corners @ matrix[:, :2].T + matrix[:, 2]
        x1, y1 = (int(round(v)) for v in mapped[0])
        x2, y2 = (int(round(v)) for v in mapped[1])
        a, b = warped, probe
    blurred_a = motion.box_blur3(np.ascontiguousarray(a))[y1:y2, x1:x2].astype(int)
    blurred_b = motion.box_blur3(np.ascontiguousarray(b))[y1:y2, x1:x2].astype(int)
    return float(np.abs(blurred_a - blurred_b).mean() / 255), why


def oracle(reference_b64, probe_b64, bbox):
    """region_diff at capture resolution and at half (analysis) resolution, both
    conventions: {"full_reference", "full_probe", "half_reference", "half_probe"} each
    {"region_diff": float | None, "reason": str}."""
    reference, probe = decode_gray(reference_b64), decode_gray(probe_b64)
    half = (reference.shape[1] // 2, reference.shape[0] // 2)
    small_reference, small_probe = cv2.resize(reference, half), cv2.resize(probe, half)
    out = {}
    for name, (a, b, scale) in {"full": (reference, probe, 1.0), "half": (small_reference, small_probe, 0.5)}.items():
        for convention in ("reference", "probe"):
            value, why = region_diff(a, b, bbox, scale=scale, convention=convention)
            out[f"{name}_{convention}"] = {"region_diff": value, "reason": why}
    return out


def classify(value, same_max=PLAN["REOBS_SAME_MAX"], gone_min=PLAN["REOBS_GONE_MIN"]):
    if value is None:
        return "unknown"
    return "present" if value <= same_max else "gone" if value >= gone_min else "unknown"


def oracle_band(measurements):
    """(low, high) of every registered region_diff in an oracle() result, or (None, None)."""
    values = [m["region_diff"] for m in measurements.values() if m["region_diff"] is not None]
    return (min(values), max(values)) if values else (None, None)


# --- goldens --------------------------------------------------------------------------------
# name -> (generator kwargs, expected verdict). The reference is the placement's rest
# keyframe (block present); every other frame plays the idle frame.
GOLDEN_FRAMES = {
    "reference": (dict(block="present"), None),
    "before": (dict(block="absent"), None),                        # the placement's pre_contact keyframe
    "present": (dict(block="present"), "present"),                 # identical pixels, separately encoded
    "present_q50": (dict(block="present", quality=50), "present"),  # the browser's idle quality
    "gone": (dict(block="absent"), "gone"),
    "partial": (dict(block="partial"), "unknown"),                 # between the thresholds
    "translated": (dict(block="present", dx=TRANSLATION[0], dy=TRANSLATION[1]), "present"),
    "translated_gone": (dict(block="absent", dx=TRANSLATION[0], dy=TRANSLATION[1]), "gone"),
    "flat": (dict(flat=True), "unknown"),                          # registration fails
    "tagged_reference": (dict(block="absent", squares=[(TAG_LEFT[0], TAG_LEFT[1], SQUARE, 0)]), None),
    "tagged_present": (dict(block="absent", squares=[(TAG_LEFT[0], TAG_LEFT[1], SQUARE, 0)]), "present"),
    "tagged_gone": (dict(block="absent"), "gone"),
}
TAGGED_BBOX = square_bbox(*TAG_LEFT)


def build_goldens():
    frames = {}
    for name, (kwargs, expected) in GOLDEN_FRAMES.items():
        kwargs = dict(kwargs)
        quality = kwargs.pop("quality", 90)
        frames[name] = {"jpeg_b64": scene_jpeg(quality, **kwargs), "generator": {**kwargs, "quality": quality}, "expected": expected}
    for name, frame in frames.items():
        if frame["expected"] is None:
            continue
        reference = "tagged_reference" if name.startswith("tagged_") else "reference"
        bbox = TAGGED_BBOX if name.startswith("tagged_") else BLOCK_BBOX
        frame["reference"] = reference
        frame["bbox"] = bbox
        frame["oracle"] = oracle(frames[reference]["jpeg_b64"], frame["jpeg_b64"], bbox)
        verdicts = {classify(m["region_diff"]) for m in frame["oracle"].values()}
        if verdicts != {frame["expected"]}:
            raise AssertionError(f"golden {name}: oracle verdicts {verdicts} != expected {frame['expected']}")
    return {"description": "CP4 re-observation goldens: a placement rest keyframe (reference, the item block at bbox) and idle frames "
                           "to register against it. region_diff is the oracle's value at capture and half resolution, two warp "
                           "conventions; the builder's value must fall within that band (+/- 0.02) and the verdict must match.",
            "basis": BASIS, "thresholds": {"REOBS_SAME_MAX": PLAN["REOBS_SAME_MAX"], "REOBS_GONE_MIN": PLAN["REOBS_GONE_MIN"]},
            "scene": {"width": SCENE_W, "height": SCENE_H, "block_bbox": BLOCK_BBOX, "tagged_bbox": TAGGED_BBOX,
                      "texture": {"seed": TEXTURE_SEED, "cell": TEXTURE_CELL, "pad": TEXTURE_PAD}, "translation": list(TRANSLATION)},
            "frames": frames}


def write_goldens():
    FIXTURES.mkdir(parents=True, exist_ok=True)
    GOLDENS.write_text(json.dumps(build_goldens(), indent=1, sort_keys=True), encoding="utf-8")


_GOLDENS = None


def goldens():
    global _GOLDENS
    if _GOLDENS is None:
        _GOLDENS = json.loads(GOLDENS.read_text(encoding="utf-8"))
    return _GOLDENS


def golden(name):
    return goldens()["frames"][name]["jpeg_b64"]


def golden_bytes(name):
    return base64.b64decode(golden(name))


def golden_band(name, margin=0.02):
    """The region_diff interval the builder's value must fall in for golden `name`."""
    low, high = oracle_band(goldens()["frames"][name]["oracle"])
    return (None, None) if low is None else (max(0.0, low - margin), high + margin)


# --- packets --------------------------------------------------------------------------------
def idle_packet(jpeg=None, *, device=DEVICE, session=SESSION, frame_id=None, t_ms=0, mono_ms=0,
                wall_ms=ANCHOR_MS, width=SCENE_W, height=SCENE_H, motion_energy=0.0):
    """The CP4 idle keyframe body. t_wall_ms = wall_ms + t_ms - mono_ms."""
    return {"schema_version": 1, "device_id": device, "session_id": session,
            "frame_id": frame_id or str(uuid.uuid4()), "t_ms": t_ms,
            "clock_anchor": {"mono_ms": mono_ms, "wall_ms": wall_ms}, "capture": {"width": width, "height": height},
            "jpeg_b64": golden("present") if jpeg is None else jpeg, "motion_energy": motion_energy}


def idle_wall_ms(packet):
    return packet["clock_anchor"]["wall_ms"] + packet["t_ms"] - packet["clock_anchor"]["mono_ms"]


def episode_packet(serial, *, rest, before=None, phase=0, device=DEVICE, session=SESSION, wall_ms=ANCHOR_MS,
                   width=SCENE_W, height=SCENE_H, landmarks=(), gaps=(), frame_ids=None, capture_mode="manual"):
    """A two-keyframe episode packet whose rest frame is `rest` (base64) at
    wall_ms + 2200 + 10000 * phase; before defaults to the "before" golden."""
    eid = str(uuid.UUID(int=0xC4000000 + serial, version=4))
    start, end = 1000 + phase * 10000, 2200 + phase * 10000
    before_id, rest_id = frame_ids or (eid + "-before", eid + "-rest")
    return {"schema_version": 1, "episode_id": eid, "device_id": device, "session_id": session,
            "t_start_ms": start, "t_end_ms": end, "clock_anchor": {"mono_ms": 0, "wall_ms": wall_ms},
            "capture": {"width": width, "height": height}, "analysis": {"width": width // 2, "height": height // 2},
            "keyframes": [{"frame_id": before_id, "t_ms": start, "role": "pre_contact", "jpeg_b64": golden("before") if before is None else before},
                          {"frame_id": rest_id, "t_ms": end, "role": "rest", "jpeg_b64": rest}],
            "carry_burst": [], "landmarks": list(landmarks), "gaps": list(gaps), "outcome_hint": "released", "capture_mode": capture_mode}


def rest_frame_id(packet):
    return packet["keyframes"][-1]["frame_id"]


def rest_wall_ms(packet):
    return packet["clock_anchor"]["wall_ms"] + packet["t_end_ms"] - packet["clock_anchor"]["mono_ms"]


def observation(frame_id, bbox, *, label="synthetic cp4 block", location="fixture cp4 table", outcome="placed_on_surface",
                identity_state="trusted", continuity_id=None, actor="wearer", calibration=None, **extra):
    """A LocalObservation dict for the scripted processor: trusted + placed under the
    CP2 code-only fixture calibration unless another calibration is given."""
    value = {"frame_id": frame_id, "bbox": [float(v) for v in bbox], "label": label, "actor": actor, "outcome": outcome,
             "continuity_id": continuity_id, "identity_state": identity_state, "location_text": location,
             "confidence": 1.0, "confidence_basis": "TEST ONLY: CP4 synthetic scene", "calibration": copy.deepcopy(FIXTURE_CAL if calibration is None else calibration)}
    value.update(extra)
    return value


def hand_sample(frame_id, t_ms, *, bbox=(0.3, 0.3, 0.6, 0.8), x=0.45, y=0.55):
    """One landmark sample with one hand whose 21 points sit near (x, y); the first
    point carries a distinctive coordinate so a byte scan can tell raw landmarks apart."""
    points = [{"x": round(min(1.0, x + 0.01 * i), 4), "y": round(min(1.0, y + 0.005 * i), 4), "z": -0.02 * i} for i in range(21)]
    return {"frame_id": frame_id, "t_ms": t_ms, "hands": [{"landmarks": points, "world_landmarks": None,
                                                           "hand_bbox": list(bbox), "handedness": "right"}]}


# --- adapters for builder spellings ---------------------------------------------------------
def constant(name):
    """A CP4 constant from perception.episode_store / episode / object_memory / identity
    (the plan names them without a module). AssertionError names what was tried."""
    import importlib
    tried = []
    for module_name in ("perception.episode_store", "perception.episode", "perception.object_memory", "perception.reobservation", "perception.identity", "server.memory_app"):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        if hasattr(module, name):
            return getattr(module, name)
        tried.append(module_name)
    raise AssertionError(f"constant {name} (plan) is not exposed by any of {tried}")


def call(target, names, *args, **kwargs):
    """Call the first method of `target` named in `names`; AssertionError lists them
    when none exists (a builder spelling that differs from the plan)."""
    for name in names:
        method = getattr(target, name, None)
        if callable(method):
            return method(*args, **kwargs)
    raise AssertionError(f"{type(target).__name__} has none of {list(names)}")


def read_retention(store):
    """The retention row as a dict (plan: GET /api/retention returns the row). The store
    spelling is not fixed by the plan: get_retention / retention / retention_settings,
    else the table read directly."""
    for name in ("get_retention", "retention", "retention_settings"):
        method = getattr(store, name, None)
        if callable(method):
            value = method()
            return dict(value) if isinstance(value, dict) else value
    with sql(store.path) as db:
        row = db.execute("SELECT * FROM retention WHERE profile_id=?", (store.profile_id,)).fetchone()
    return None if row is None else dict(row)


@contextlib.contextmanager
def sql(path):
    db = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def table_exists(path, name):
    with sql(path) as db:
        return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def table_rows(path, name, where="", params=()):
    with sql(path) as db:
        return [dict(row) for row in db.execute(f"SELECT * FROM {name} {where}", params)]


def columns(path, name):
    with sql(path) as db:
        return [row[1] for row in db.execute(f"PRAGMA table_info({name})")]


def row_counts(path):
    """{table: count} for every table in sqlite_master."""
    with sql(path) as db:
        names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        return {name: db.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in names}


def table_snapshot(path, name):
    """Every row of a table as a sorted list of JSON strings (bytes rendered as hex)."""
    def render(value):
        if isinstance(value, (bytes, memoryview)):
            return "0x" + bytes(value).hex()
        return value
    with sql(path) as db:
        rows = [json.dumps({k: render(v) for k, v in dict(row).items()}, sort_keys=True) for row in db.execute(f"SELECT * FROM {name}")]
    return sorted(rows)


# --- synthetic PII markers and scanners (P-107) ------------------------------------------------
MARKERS = {
    "x_label": "PII-NAME-9c1b", "x_location": "PII-LOCATION-7f3a", "x_basis": "PII-BASIS-5e2c", "x_continuity": "PII-CONT-1a2b",
    "x_frame": "PII-FRAME-3c4d", "x_gap": "PII-GAP-6d7e", "x_rename": "PII-RENAME-2b4d",
    "y_label": "PII-NAME-y4e8", "y_location": "PII-LOCATION-y1f9", "y_basis": "PII-BASIS-y8a1", "y_rename": "PII-RENAME-y7c3",
    "z_label": "PII-NAME-z2d6", "z_location": "PII-LOCATION-z5b0", "z_rename": "PII-RENAME-z9e4",
    "w_label": "PII-NAME-w3f7", "w_location": "PII-LOCATION-w6c2",
}


def counts_only(detail):
    """True when an audit detail carries only counts: every leaf is an int (nested
    dicts allowed), except an "actor" key holding a closed-set role literal (B-15)."""
    if not isinstance(detail, dict) or not detail:
        return False
    for key, value in detail.items():
        if key == "actor":
            if value not in ("caregiver_pin", "operator", "test"):
                return False
        elif isinstance(value, dict):
            if not counts_only(value):
                return False
        elif isinstance(value, bool) or not isinstance(value, int):
            return False
    return True


def sidecar_entries(report):
    """{suffix: entry} for the -journal / -wal / -shm entries of a sidecar_report(),
    whether it is a dict keyed by name or a list of dicts with a name/path key.
    Each entry is normalised to carry "present" (from "present" or "exists") and "private"."""
    pairs = list(report.items()) if isinstance(report, dict) else [(e.get("name", e.get("path", e.get("sidecar"))), e) for e in report]
    entries = {}
    for key, entry in pairs:
        if not isinstance(entry, dict):
            continue
        key = str(key)
        for suffix in ("-journal", "-wal", "-shm"):
            if key.endswith(suffix) or key == suffix.lstrip("-"):
                normalised = dict(entry)
                if "present" not in normalised and "exists" in normalised:
                    normalised["present"] = normalised["exists"]
                entries[suffix] = normalised
    return entries


def scan_database(path, markers):
    """[(table, column, marker)] for every cell of every table (TEXT and BLOB alike)
    that contains one of the markers (UTF-8 for BLOBs)."""
    hits = []
    needles = {name: value for name, value in markers.items()}
    with sql(path) as db:
        names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for table in names:
            cols = [r[1] for r in db.execute(f"PRAGMA table_info({table})")]
            for row in db.execute(f"SELECT * FROM {table}"):
                for col in cols:
                    value = row[col]
                    if isinstance(value, (bytes, memoryview)):
                        text = bytes(value).decode("utf-8", "replace")
                    elif isinstance(value, str):
                        text = value
                    else:
                        continue
                    for name, needle in needles.items():
                        if needle in text:
                            hits.append((table, col, needle))
    return hits


def scan_files(path, markers):
    """[(file name, marker)] over the main database file and every sidecar present."""
    hits = []
    for candidate in sidecar_paths(path, include_main=True):
        if candidate.is_file():
            data = candidate.read_bytes()
            for needle in markers.values():
                if needle.encode("utf-8") in data:
                    hits.append((candidate.name, needle))
    return hits


def sidecar_paths(path, *, include_main=False):
    path = Path(path)
    out = [path] if include_main else []
    return out + [Path(str(path) + suffix) for suffix in ("-journal", "-wal", "-shm")]


# --- v1 fixture (legacy ObjectStore API, as server/test_memory_lifecycle.py drives it) --------------
V1_T0 = datetime(2026, 1, 15, 12, tzinfo=timezone.utc).timestamp()
V1_SESSION = "camera-session-v1-0001"
V1_TRACKS = {"A": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "B": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
             "C": "cccccccc-cccc-4ccc-8ccc-cccccccccccc", "D": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
             "E": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", "S": "55555555-5555-4555-8555-555555555555"}
# (surface, room) of each legacy observation's scene. Coordinator ruling 14: the
# migrated location_text is "{surface}, {room}" (never the VLM's free description).
V1_SCENES = {
    "A-placed-1": ("legacy table A", "legacy kitchen"),
    "A-picked-up": ("legacy table A edge", "legacy kitchen"),
    "A-placed-2": ("legacy table B", "legacy lounge"),
    "B-placed": ("legacy shelf, second row", "legacy hall"),
    "B-unknown": ("legacy shelf front", "legacy hall"),
    "C-placed": ("legacy desk", "legacy study"),
    "raw-levitated": ("legacy ceiling", "legacy lounge"),
}
V1_DESCRIPTIONS = {key: f"Free-text VLM description for {key} (must never be migrated)." for key in V1_SCENES}
V1_LOCATION_TEXT = {key: f"{surface}, {room}" for key, (surface, room) in V1_SCENES.items()}
V1_OUTCOME = {"placed": "placed_on_surface", "picked_up": "picked_up", "unknown": "uncertain", "levitated": "uncertain"}
# Oversight T4: a searchable geolocation planted in every legacy candidate's fix; it
# must never appear in any table the migration writes (lat/lon are personal).
V1_LATITUDE, V1_LONGITUDE = 51.4321, -0.9876
V1_GEO_MARKERS = {"lat": "51.4321", "lon": "-0.9876"}


class V1Builder:
    """Builds a legacy (v1) object-memory database with the retained v1 ObjectStore API
    only: objects, candidates, observations, bindings, api_calls and decisions rows,
    including placed / picked_up / unknown observations, a rejected 'sighted'
    candidate, a budget_wait candidate, a processing lease with a reserved API call,
    an ignored object and one raw observation row with an unknown event type."""
    def __init__(self, path, clock):
        from perception.object_memory import ObjectStore
        self.path = Path(path)
        self.clock = clock
        self.serial = 0
        self.store = ObjectStore(self.path, profile_id="local", clock=clock)
        self.expected = {"objects": {}, "observations": [], "ignored_object": None}

    def candidate(self, *, at, action, track, label, session=V1_SESSION):
        self.serial += 1
        n = self.serial
        return {"event_id": f"legacy-event-{n:04d}", "session_id": session, "track_id": track, "observed_at": at,
                "sequence": n, "event_type": action, "object": label, "time_source": "capture",
                "evidence": {"contact_candidate": True, "motion_valid": True, "released": action == "placed",
                             "track_continuous": True, "track_started_at": V1_T0 - 10},
                "co_visible_track_ids": [], "frames": [str(self.path.parent / f"legacy-{n}-{role}.jpg") for role in ("before", "during", "after")],
                "crop": str(self.path.parent / f"legacy-{n}-crop.jpg"),
                "location": {"lat": V1_LATITUDE, "lon": V1_LONGITUDE, "accuracy_m": 8.0, "observed_at": at - 1}}

    @staticmethod
    def verification(*, action="placed", identity="new", object_id=None, label="legacy pill bottle", scene="A-placed-1", actor="wearer"):
        from perception.object_memory import Verification
        surface, room = V1_SCENES[scene]
        description = V1_DESCRIPTIONS[scene]
        return Verification.model_validate({
            "actor": actor, "actor_confidence": .99, "actor_evidence": ["Synthetic legacy wearer contact"],
            "action": action, "action_confidence": .99, "contact_observed": True,
            "released": action == "placed", "resting_after": action == "placed",
            "object": label, "appearance": "Synthetic legacy appearance text",
            "identity": identity, "matched_object_id": object_id, "identity_confidence": .99,
            "identity_basis": "continuous_track" if identity == "match" else "distinctive_features",
            "identity_evidence": "Synthetic legacy segment" if identity == "match" else "Synthetic legacy marking",
            "scene": {"room": room, "surface": surface, "landmarks": ["legacy cube"], "description": description}})

    def verify(self, candidate, result, *, cost_usd=0.0):
        self.store.enqueue(candidate)
        self.store.gallery(candidate["event_id"])
        return self.store.apply_result(candidate["event_id"], result, cost_usd=cost_usd)

    def build(self):
        store = self.store
        # Object A: placed, picked up, placed again (three observations, tracked).
        first = self.candidate(at=V1_T0, action="placed", track=V1_TRACKS["A"], label="legacy pill bottle")
        result = self.verify(first, self.verification(scene="A-placed-1"))
        a = store.confirm_object(result["object_id"], name="Legacy pill bottle")["object_id"]
        pickup = self.candidate(at=V1_T0 + 10, action="picked_up", track=V1_TRACKS["A"], label="legacy pill bottle")
        self.verify(pickup, self.verification(action="picked_up", identity="match", object_id=a, scene="A-picked-up"))
        again = self.candidate(at=V1_T0 + 20, action="placed", track=V1_TRACKS["A"], label="legacy pill bottle")
        self.verify(again, self.verification(identity="match", object_id=a, scene="A-placed-2"))
        self.expected["objects"][a] = "Legacy pill bottle"
        self.expected["observations"] += [(a, "placed", V1_T0, V1_LOCATION_TEXT["A-placed-1"]), (a, "picked_up", V1_T0 + 10, V1_LOCATION_TEXT["A-picked-up"]),
                                          (a, "placed", V1_T0 + 20, V1_LOCATION_TEXT["A-placed-2"])]
        # Object B: placed (resolved through review), then a bystander pickup -> action "unknown".
        b_candidate = self.candidate(at=V1_T0 + 100, action="placed", track=V1_TRACKS["B"], label="legacy glasses")
        result = self.verify(b_candidate, self.verification(label="legacy glasses", scene="B-placed"))
        b = store.confirm_object(result["object_id"], name="Legacy glasses")["object_id"]
        bystander = self.candidate(at=V1_T0 + 110, action="picked_up", track=V1_TRACKS["B"], label="legacy glasses")
        self.verify(bystander, self.verification(action="picked_up", actor="bystander", label="legacy glasses", scene="B-unknown"))
        self.expected["objects"][b] = "Legacy glasses"
        self.expected["observations"] += [(b, "placed", V1_T0 + 100, V1_LOCATION_TEXT["B-placed"]), (b, "unknown", V1_T0 + 110, V1_LOCATION_TEXT["B-unknown"])]
        # Object C: placed, then the user ignored the review (object status ignored).
        c_candidate = self.candidate(at=V1_T0 + 200, action="placed", track=V1_TRACKS["C"], label="legacy mug")
        result = self.verify(c_candidate, self.verification(label="legacy mug", scene="C-placed"))
        store.ignore(c_candidate["event_id"])
        self.expected["ignored_object"] = result["object_id"]
        # A rejected background sighting (never an observation).
        store.enqueue(self.candidate(at=V1_T0 + 300, action="sighted", track=V1_TRACKS["S"], label="legacy keys"))
        # Budgets and leases: one claimed candidate left processing (lease + reserved call),
        # one waiting on the daily budget.
        store.enqueue(self.candidate(at=V1_T0 + 400, action="placed", track=V1_TRACKS["D"], label="legacy phone"))
        store.enqueue(self.candidate(at=V1_T0 + 401, action="placed", track=V1_TRACKS["E"], label="legacy remote"))
        claimed = store.claim_next(daily_calls=1, monthly_usd=1.0, reserve_usd=.10)
        if claimed is None or claimed["event_id"] != f"legacy-event-{self.serial - 1:04d}":
            raise AssertionError("v1 fixture: the phone candidate should have been claimed")
        if store.claim_next(daily_calls=1, monthly_usd=1.0, reserve_usd=.10) is not None:
            raise AssertionError("v1 fixture: the second claim should wait on the daily budget")
        # One raw observations row with an event type the migration cannot know.
        db = sqlite3.connect(str(self.path))
        try:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM observations WHERE object_id=? ORDER BY observed_at DESC LIMIT 1", (a,)).fetchone()
            record = json.loads(row["record"])
            record.update(event_id="legacy-raw-levitated", action="levitated", observed_at=V1_T0 + 30, sequence=99)
            record["scene"].update(description=V1_DESCRIPTIONS["raw-levitated"], surface=V1_SCENES["raw-levitated"][0], room=V1_SCENES["raw-levitated"][1])
            with db:
                db.execute("INSERT INTO observations VALUES(?,?,?,?,?,?,?)",
                           ("legacy-raw-levitated", "local", a, V1_T0 + 30, 99, "levitated", json.dumps(record, sort_keys=True, separators=(",", ":"))))
        finally:
            db.close()
        self.expected["observations"].append((a, "levitated", V1_T0 + 30, V1_LOCATION_TEXT["raw-levitated"]))
        self.expected["ignored_location_text"] = V1_LOCATION_TEXT["C-placed"]
        self.expected["observation_rows"] = 7          # every legacy observations row, the ignored object's included
        self.expected["converted"] = 6                 # rows of confirmed (tracked) objects
        self.expected["usage"] = store.usage()
        self.expected["api_calls"] = table_snapshot(self.path, "api_calls")
        self.expected["candidates"] = table_snapshot(self.path, "candidates")
        self.expected["objects_rows"] = table_snapshot(self.path, "objects")
        self.expected["decisions"] = table_snapshot(self.path, "decisions")
        self.expected["bindings"] = table_snapshot(self.path, "bindings")
        return self.expected


def build_v1_fixture(path, clock):
    return V1Builder(path, clock).build()


# --- store-level fixture ---------------------------------------------------------------------
class Cp4Fixture(bootstrap.MemoryApiFixture):
    """The bootstrap guards (egress, private files, env, temp DB, injected clock) with
    the app's worker closed, a scripted list processor and a direct ObjectStore. A
    subclass sets EMBEDDER = True to attach the CP3 synthetic embedder."""
    EMBEDDER = False

    def setUp(self):
        super().setUp()
        self.client.__exit__(None, None, None)   # the bootstrap worker must not claim jobs under us
        self.scripted = identity.Cp3Processor()
        self.embedder = identity.SyntheticEmbedder() if self.EMBEDDER else None
        self.serial_ids = 0
        self.phase = 0
        self.store = self.make_store()

    def make_store(self, profile="local", embedder="default", *, consent=True):
        from perception.object_memory import ObjectStore
        value = self.embedder if embedder == "default" else embedder
        store = ObjectStore(self.db, profile_id=profile, clock=self.clock, embedder=value)
        # Coordinator ruling 1: store-level fixtures acknowledge the build's consent
        # version before any capture (idempotent per profile).
        if consent:
            store.acknowledge_consent(CONSENT_VERSION, ACTOR)
        return store

    def now_ms(self):
        return int(self.now * 1000)

    def next_packet(self, **kwargs):
        self.serial_ids += 1
        kwargs.setdefault("phase", self.phase)
        self.phase += 1
        return episode_packet(self.serial_ids, **kwargs)

    def ingest(self, packet, store=None):
        store = self.store if store is None else store
        ack = store.ingest_episode(bootstrap.encode_packet(packet))
        self.assertIn(ack["status"], ("stored", "revised"), ack)
        return ack

    def process(self, store=None, expect_failed=0):
        store = self.store if store is None else store
        counts = store.process_pending(processor=self.scripted)
        self.assertEqual(counts["failed"], expect_failed, counts)
        self.assertEqual(counts["pending"], 0, counts)
        return counts

    def place(self, observations, *, rest=None, store=None, **packet_kwargs):
        """Ingest a packet whose rest frame is `rest` (default: the "reference" golden)
        with the scripted observations (callables of the rest frame id or dicts whose
        frame_id is filled in), then process. Returns the packet."""
        packet = self.next_packet(rest=golden("reference") if rest is None else rest, **packet_kwargs)
        frame = rest_frame_id(packet)
        scripted = []
        for value in observations:
            value = dict(value(frame) if callable(value) else value)
            if value.get("frame_id") is None:
                value["frame_id"] = frame
            scripted.append(value)
        self.scripted.observations[packet["episode_id"]] = scripted
        self.ingest(packet, store)
        self.process(store)
        return packet

    def idle(self, name_or_b64="present", *, store=None, **kwargs):
        """ingest_idle one frame (a golden name or base64); returns (packet, ack)."""
        store = self.store if store is None else store
        jpeg = golden(name_or_b64) if name_or_b64 in goldens()["frames"] else name_or_b64
        packet = idle_packet(jpeg, **kwargs)
        ack = store.ingest_idle(bootstrap.encode_packet(packet))
        return packet, ack

    def reobserve(self, now_ms=None, store=None, **kwargs):
        store = self.store if store is None else store
        return store.reobserve(self.now_ms() if now_ms is None else now_ms, **kwargs)

    def items(self, store=None, **kwargs):
        return (self.store if store is None else store).list_items(**kwargs)

    def only_item(self, store=None, **kwargs):
        items = self.items(store, **kwargs)
        self.assertEqual(len(items), 1, items)
        return items[0]

    def item_by_name(self, name, store=None):
        matches = [item for item in self.items(store) if item["name"] == name]
        self.assertEqual(len(matches), 1, [(i["name"], i["item_id"]) for i in self.items(store)])
        return matches[0]

    def rows(self, table, where="", params=()):
        return table_rows(self.db, table, where, params)

    def audit(self, action=None):
        rows = self.rows("local_audit", "WHERE profile_id='local' ORDER BY audit_id")
        return [r for r in rows if action is None or r["action"] == action]

    def register_calibration(self, calibration_id=identity.CAL_WIDE, *, quantile=identity.WIDE_Q, store=None):
        store = self.store if store is None else store
        store.register_calibration(identity.calibration_record(calibration_id, quantile=quantile))
        store.approve_calibration(calibration_id, identity.ACTOR)


# --- self-tests (green before any builder code) -----------------------------------------------
class FixtureSelfTests(unittest.TestCase):
    def test_goldens_file_matches_the_generator_and_the_basis(self):
        data = goldens()
        self.assertEqual(data["basis"], BASIS)
        self.assertEqual(data["thresholds"], {"REOBS_SAME_MAX": 0.06, "REOBS_GONE_MIN": 0.18})
        self.assertEqual(set(data["frames"]), set(GOLDEN_FRAMES))
        regenerated = build_goldens()["frames"]
        for name, frame in data["frames"].items():
            with self.subTest(frame=name):
                stored = decode_gray(frame["jpeg_b64"])
                fresh = decode_gray(regenerated[name]["jpeg_b64"])
                self.assertEqual(stored.shape, (SCENE_H, SCENE_W))
                self.assertLessEqual(float(np.abs(stored.astype(int) - fresh.astype(int)).mean()), 1.5, "stored golden drifted from its generator")
                self.assertEqual(frame["expected"], GOLDEN_FRAMES[name][1])
                self.assertTrue(base64.b64decode(frame["jpeg_b64"]).startswith(b"\xff\xd8"))

    def test_oracle_verdicts_pin_the_thresholds_with_margin(self):
        data = goldens()
        for name, frame in data["frames"].items():
            if frame["expected"] is None:
                continue
            with self.subTest(frame=name):
                values = {k: m["region_diff"] for k, m in frame["oracle"].items()}
                verdicts = {classify(v) for v in values.values()}
                self.assertEqual(verdicts, {frame["expected"]}, values)
                low, high = oracle_band(frame["oracle"])
                if frame["expected"] == "present":
                    self.assertLessEqual(high, 0.03, f"present must sit well under REOBS_SAME_MAX: {values}")
                elif frame["expected"] == "gone":
                    self.assertGreaterEqual(low, 0.25, f"gone must sit well over REOBS_GONE_MIN: {values}")
                elif name == "partial":
                    self.assertGreaterEqual(low, 0.09)
                    self.assertLessEqual(high, 0.15)
                elif name == "flat":
                    self.assertIsNone(low)
                    self.assertEqual({m["reason"] for m in frame["oracle"].values()}, {"flat"})
        # The translated frames register (the point of the texture) and the measured
        # translation is the one generated.
        matrix, why = register(decode_gray(golden("reference")), decode_gray(golden("translated")))
        self.assertEqual(why, "ok")
        self.assertAlmostEqual(float(matrix[0, 2]), TRANSLATION[0], delta=0.5)
        self.assertAlmostEqual(float(matrix[1, 2]), TRANSLATION[1], delta=0.5)

    def test_checkerboard_is_not_a_usable_registration_target_once_the_block_is_gone(self):
        # Documented reason for the blob texture: the bootstrap checkerboard aliases under LK.
        y, xx = np.indices((SCENE_H, SCENE_W))
        board = (35 + ((xx // 8 + y // 8) % 2) * 50).astype(np.uint8)
        with_block = board.copy()
        with_block[40:80, 60:100] = 205
        matrix, why = register(with_block, board)
        self.assertIsNone(matrix, "if this registers now, the checkerboard became usable: revisit the fixture choice")
        self.assertEqual(why, "inliers")

    def test_real_localizer_finds_the_block_on_the_scene(self):
        # The scene is a legitimate localizer input: before (absent) -> rest (present)
        # yields one provisional region around the block at capture resolution.
        from perception.episode import parse_packet
        from perception.localizer import localize
        packet = episode_packet(1, rest=golden("reference"))
        found = localize(parse_packet(bootstrap.encode_packet(packet)))
        self.assertEqual(len(found), 1, [f.bbox for f in found])
        x1, y1, x2, y2 = found[0].bbox
        self.assertLessEqual(abs(x1 - BLOCK_BBOX[0]), 6)
        self.assertLessEqual(abs(y1 - BLOCK_BBOX[1]), 6)
        self.assertLessEqual(abs(x2 - BLOCK_BBOX[2]), 6)
        self.assertLessEqual(abs(y2 - BLOCK_BBOX[3]), 6)
        self.assertEqual(found[0].identity_state, "provisional")

    def test_tagged_goldens_decode_for_the_synthetic_embedder(self):
        embedder = identity.SyntheticEmbedder()
        image = cv2.imdecode(np.frombuffer(golden_bytes("tagged_present"), np.uint8), cv2.IMREAD_UNCHANGED)
        x1, y1, x2, y2 = (int(v) for v in TAGGED_BBOX)
        self.assertEqual(embedder.read_tag(image[y1:y2, x1:x2]), 0)
        padded = image[max(0, y1 - 3):y2 + 3, max(0, x1 - 3):x2 + 3]
        self.assertEqual(embedder.read_tag(padded), 0, "a CROP_PAD-padded crop still decodes")
        with self.assertRaises(ValueError):
            embedder.read_tag(image[0:SQUARE, 100:100 + SQUARE])  # plain texture: no tag
        gone = cv2.imdecode(np.frombuffer(golden_bytes("tagged_gone"), np.uint8), cv2.IMREAD_UNCHANGED)
        with self.assertRaises(ValueError):
            embedder.read_tag(gone[y1:y2, x1:x2])

    def test_idle_and_episode_packet_shapes(self):
        packet = idle_packet(t_ms=500, mono_ms=100, wall_ms=ANCHOR_MS)
        self.assertEqual(set(packet), IDLE_FIELDS)
        self.assertEqual(idle_wall_ms(packet), ANCHOR_MS + 400)
        self.assertEqual(str(uuid.UUID(packet["frame_id"])), packet["frame_id"])
        self.assertEqual(decode_gray(packet["jpeg_b64"]).shape, (SCENE_H, SCENE_W))
        from perception.episode import parse_packet
        episode = episode_packet(7, rest=golden("reference"), landmarks=[hand_sample("lm-1", 1500)], gaps=[{"t_from_ms": 1100, "t_to_ms": 1200, "reason": "synthetic gap"}])
        parsed = parse_packet(bootstrap.encode_packet(episode))
        self.assertEqual(len(parsed.landmarks[0].hands[0].landmarks), 21)
        self.assertEqual(rest_wall_ms(episode), ANCHOR_MS + 2200)

    def test_v1_fixture_builder_produces_the_legacy_rows(self):
        with tempfile.TemporaryDirectory(prefix="pam-cp4-v1-") as temp:
            path = Path(temp) / "legacy.sqlite3"
            now = [V1_T0 + 60]
            expected = build_v1_fixture(path, lambda: now[0])
            counts = row_counts(path)
            self.assertEqual(counts["objects"], 3)
            self.assertEqual(counts["observations"], 7)
            self.assertEqual(counts["api_calls"], 1)
            self.assertGreaterEqual(counts["decisions"], 5)
            self.assertEqual(counts["local_observations"], 0)
            self.assertEqual(len(expected["objects"]), 2)
            self.assertIsNotNone(expected["ignored_object"])
            actions = sorted(action for _, action, _, _ in expected["observations"])
            self.assertEqual(actions, ["levitated", "picked_up", "placed", "placed", "placed", "unknown"])
            with sql(path) as db:
                statuses = {r["event_id"]: (r["status"], r["reason"]) for r in db.execute("SELECT event_id,status,reason FROM candidates")}
                objects = {r["object_id"]: r["status"] for r in db.execute("SELECT object_id,status FROM objects")}
            self.assertIn(("rejected", "background_sighting"), statuses.values())
            self.assertIn(("budget_wait", "api_budget"), statuses.values())
            self.assertIn(("processing", ""), statuses.values())
            self.assertEqual(objects[expected["ignored_object"]], "ignored")
            self.assertEqual(sorted(objects.values()), ["ignored", "tracked", "tracked"])
            self.assertEqual(expected["usage"]["api_calls"], 1)
            self.assertAlmostEqual(expected["usage"]["cost_or_reserved_usd"], .10)

    def test_marker_scanners_see_text_and_blob_cells_and_file_bytes(self):
        with tempfile.TemporaryDirectory(prefix="pam-cp4-scan-") as temp:
            path = Path(temp) / "scan.sqlite3"
            db = sqlite3.connect(str(path))
            db.execute("CREATE TABLE t(a TEXT, b BLOB, c INTEGER)")
            db.execute("INSERT INTO t VALUES(?,?,?)", ("hello " + MARKERS["x_label"], json.dumps({"k": MARKERS["y_location"]}).encode(), 7))
            db.commit()
            db.close()
            hits = scan_database(path, MARKERS)
            self.assertEqual(sorted(hits), [("t", "a", MARKERS["x_label"]), ("t", "b", MARKERS["y_location"])])
            files = scan_files(path, MARKERS)
            self.assertEqual({marker for _, marker in files}, {MARKERS["x_label"], MARKERS["y_location"]})
            self.assertEqual(scan_database(path, {"none": "PII-NOT-PLANTED"}), [])

    def test_constant_adapter_reads_existing_constants_and_names_the_search(self):
        self.assertEqual(constant("AGE_STALE_MS"), 24 * HOUR_MS)
        self.assertEqual(constant("MAX_PACKET_BYTES"), 4 * 1024 * 1024)
        with self.assertRaisesRegex(AssertionError, "NO_SUCH_CP4_CONSTANT"):
            constant("NO_SUCH_CP4_CONSTANT")


if __name__ == "__main__":
    if "--write-goldens" in sys.argv:
        write_goldens()
        print(f"wrote {GOLDENS}")
    else:
        unittest.main(verbosity=2)
