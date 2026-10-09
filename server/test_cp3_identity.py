"""CP3 acceptance, store level: the identity stage with a deterministic synthetic
embedder. No HTTP, temporary database, injected embedder and trusted fixture
observations.

    python3 -B server/test_cp3_identity.py -v

Authority: docs/BUILD_PLAN.md "CP3 in detail: identity" (architect, 2026-10-09) and
docs/BUILD_CONTRACT.md "Contract decisions after CP0". Interfaces under test (binding
on the builders; one adapter function each so a small rename is a one-line fix here):

  perception/identity.py: Embedder protocol (name, version, dim, embed(crop, mask)
    -> float32 L2-normalised), ItemBank(item_id) with score(query) and a 32-vector
    cap, calibrate(pairs, alpha) -> quantile, ConformalMatcher(calibration_record)
    .match(query, banks, excluded) -> {"set", "scores", "state"}.
  perception/episode_store.py: set_embedder / embedder=, register_calibration,
    approve_calibration, link_items, unlink_observation, item_evidence,
    observation_image, rebuild_all replaying embeddings and corrections, items with
    identity_status "ambiguous" and lookalikes, answer_text shape "group".

The synthetic embedder lives in this file on purpose (a fixture module under
server/fixtures/ must never be importable by production). It reads an instance tag
that the fixture frames encode in the GREEN channel of a blue square (the middle
channel is the same under BGR and RGB, so the crop's channel order does not matter)
and maps it to a seeded prototype plus bounded noise in a disjoint subspace, so that
"same object" pairs score cosine ~0.98, "lookalike" pairs ~0.88 and "different" pairs
~0.0 by construction, deterministically. Nothing here measures a real model.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import sys
import unittest
import uuid

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
import test_memory_bootstrap as bootstrap  # noqa: E402

FIXTURES = ROOT / "server" / "fixtures" / "cp3"
PAIRS_FILE = FIXTURES / "calibration_pairs.json"
ANCHOR_MS = bootstrap.ANCHOR_MS
DEVICE = bootstrap.DEVICE
SESSION = bootstrap.SESSION
ACTOR = "caregiver_pin"            # the session role string, never a named person (B-15)
CAPABILITY = "physical_instance_recognition"
EMBEDDER_TAG = "synthetic@1"       # Embedder.name @ Embedder.version
CAL_WIDE = "cp3-synthetic-wide"    # quantile 0.17 (from the pairs fixture): lookalikes are inside the set
CAL_TIGHT = "cp3-synthetic-tight"  # quantile 0.05: only same-object pairs are inside the set
WIDE_Q = 0.17
TIGHT_Q = 0.05
GLASSES = "synthetic glasses"
BOTTLE = "synthetic bottle"
ASK_GLASSES = "where are my synthetic glasses"
ASK_BOTTLE = "where is my synthetic bottle"
GROUP_TEXT = "I have {n} items that look alike; which one is yours?"
IDENTITY_VOCABULARY = {"provisional", "ambiguous", "trusted"}
EVIDENCE_FIELDS = {"observation_id", "observed_at_ms", "reference_image", "identity_status", "outcome", "location_text"}

# --- synthetic frames: a checkerboard with colour-tagged squares -----------------------
TAG_BASE, TAG_STEP, TAG_COUNT = 30, 36, 7
SQUARE = 24
LEFT, MIDDLE, RIGHT = (20, 40), (60, 40), (100, 40)


def tag_colour(tag):
    """BGR colour of the square carrying instance tag `tag` (0..6): a saturated blue
    with the tag in the green channel. The checkerboard is grey (B == R), so tagged
    pixels are those with max(B, R) >= 150 and min(B, R) <= 90, whichever order the
    channels arrive in."""
    if not 0 <= tag < TAG_COUNT:
        raise ValueError("tag out of range")
    return (230, TAG_BASE + TAG_STEP * tag, 30)


def tagged_jpeg(regions=(), width=160, height=120):
    """A base64 JPEG (quality 95) of the bootstrap checkerboard with one square per
    (x, y, tag) region. Verified below (FixtureSelfTests) to round-trip every tag."""
    y, xx = np.indices((height, width))
    gray = (35 + ((xx // 8 + y // 8) % 2) * 50).astype(np.uint8)
    image = np.repeat(gray[:, :, None], 3, axis=2)
    for x, y0, tag in regions:
        image[y0:y0 + SQUARE, x:x + SQUARE] = tag_colour(tag)
    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise AssertionError("Synthetic JPEG encoding failed")
    return base64.b64encode(data.tobytes()).decode("ascii")


def region(position, tag):
    return (position[0], position[1], tag)


def bbox(reg):
    x, y, _ = reg
    return [float(x), float(y), float(x + SQUARE), float(y + SQUARE)]


# --- the synthetic embedder --------------------------------------------------------------
NOISE_EPS = 0.1428  # 1 / (1 + eps^2) = 0.98: the expected same-object cosine


class SyntheticEmbedder:
    """Deterministic Embedder for tests. Prototypes live in dims 0..7, noise in dims
    8..15 (orthogonal to every prototype), so cosines are set by construction:
      same tag      (1 + eps^2 * n1.n2) / (1 + eps^2)   ~ 0.98  (0.96 .. 1.00)
      lookalike     (0.90 + eps^2 * n1.n2) / (1 + eps^2) ~ 0.88  (0.86 .. 0.90)
      different     eps^2 * n1.n2 / (1 + eps^2)          ~ 0.00  (|.| <= 0.02)
    Tags 0 and 1 are lookalikes (prototype cosine 0.90), tags 2 and 4 likewise;
    tags 0, 2, 3, 5, 6 are mutually orthogonal."""
    name = "synthetic"
    version = "1"
    LOOKALIKE_COS = 0.90

    def __init__(self, dim=16, eps=NOISE_EPS):
        if dim < 16:
            raise ValueError("SyntheticEmbedder needs dim >= 16")
        self.dim, self.eps = dim, eps
        self.calls = []
        basis = np.eye(dim, dtype=np.float64)
        side = math.sqrt(1 - self.LOOKALIKE_COS ** 2)
        self.prototypes = {
            0: basis[0], 1: self.LOOKALIKE_COS * basis[0] + side * basis[1],
            2: basis[2], 3: basis[3], 4: self.LOOKALIKE_COS * basis[2] + side * basis[4],
            5: basis[5], 6: basis[6]}

    @property
    def tag(self):
        return f"{self.name}@{self.version}"

    def prototype(self, tag):
        return self.prototypes[tag].astype(np.float32)

    def vector(self, tag, draw):
        """Prototype `tag` plus bounded noise whose direction is seeded by `draw`."""
        rng = np.random.default_rng(int(draw) & 0xFFFFFFFF)
        noise = np.zeros(self.dim)
        direction = rng.standard_normal(self.dim - 8)
        noise[8:] = direction / np.linalg.norm(direction)
        value = self.prototypes[tag] + self.eps * noise
        return (value / np.linalg.norm(value)).astype(np.float32)

    @staticmethod
    def read_tag(crop, mask=None):
        """The instance tag encoded in the crop, or a ValueError naming why not."""
        if not isinstance(crop, np.ndarray) or crop.ndim != 3 or crop.shape[2] != 3 or crop.dtype != np.uint8:
            raise ValueError(f"SyntheticEmbedder expects an HxWx3 uint8 crop, got {getattr(crop, 'shape', None)} {getattr(crop, 'dtype', None)}")
        pixels = crop.reshape(-1, 3).astype(int)
        if mask is not None:
            mask = np.asarray(mask)
            if mask.shape != crop.shape[:2]:
                raise ValueError(f"mask shape {mask.shape} does not match crop {crop.shape[:2]}")
            if mask.astype(bool).any():
                pixels = crop[mask.astype(bool)].astype(int)
        outer = np.maximum(pixels[:, 0], pixels[:, 2])
        inner = np.minimum(pixels[:, 0], pixels[:, 2])
        tagged = pixels[(outer >= 150) & (inner <= 90)]
        if len(tagged) < 4:
            raise ValueError(f"SyntheticEmbedder found no tagged pixels in a {crop.shape} crop")
        green = float(np.median(tagged[:, 1]))
        tag = int(round((green - TAG_BASE) / TAG_STEP))
        if not 0 <= tag < TAG_COUNT or abs(green - (TAG_BASE + TAG_STEP * tag)) > 12:
            raise ValueError(f"SyntheticEmbedder could not decode a tag from median green {green}")
        return tag

    def embed(self, crop, mask=None):
        record = {"shape": getattr(crop, "shape", None), "mask": None if mask is None else tuple(np.asarray(mask).shape), "tag": None}
        self.calls.append(record)
        tag = self.read_tag(crop, mask)
        record["tag"] = tag
        draw = int(hashlib.sha256(np.ascontiguousarray(crop).tobytes()).hexdigest()[:8], 16)
        return self.vector(tag, draw)

    @staticmethod
    def cosine(a, b):
        a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
        return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


# --- fixture processor, calibration records, packets -------------------------------------
class Cp3Processor:
    """Trusted code-only injection: a list of observation dicts per episode id. Never
    reachable through HTTP (the bootstrap suite proves that for the fixture seam)."""
    def __init__(self):
        self.observations = {}
        self.calls = []

    def __call__(self, packet):
        from perception.localizer import LocalObservation
        self.calls.append(packet.episode_id)
        return [LocalObservation(**json.loads(json.dumps(value))) for value in self.observations.get(packet.episode_id, [])]


def cp3_calibration(calibration_id=CAL_WIDE):
    """What the processor's LocalObservation.calibration names: the id of a stored
    record. Approval lives in the calibrations table, never in this dict."""
    return {"calibration_id": calibration_id}


def cp3_observation(frame_id, reg, *, label=GLASSES, location="fixture shelf", calibration_id=CAL_WIDE,
                    outcome="placed_on_surface", identity_state="trusted", **extra):
    value = {"frame_id": frame_id, "bbox": bbox(reg), "label": label, "actor": "wearer", "outcome": outcome,
             "continuity_id": None, "identity_state": identity_state, "location_text": location,
             "confidence": 1.0, "confidence_basis": "TEST ONLY: CP3 synthetic colour-tagged region",
             "calibration": cp3_calibration(calibration_id)}
    value.update(extra)
    return value


def calibration_record(calibration_id=CAL_WIDE, *, quantile=WIDE_Q, embedder=EMBEDDER_TAG, approved=False,
                       n=40, alpha=0.05, source="synthetic", created_ms=ANCHOR_MS):
    return {"calibration_id": calibration_id, "embedder": embedder, "alpha": alpha, "quantile": quantile,
            "n": n, "source": source, "created_ms": created_ms, "approved": approved}


def cp3_packet(serial, *, rest, before=(), phase=0, device=DEVICE, session=SESSION, wall_ms=ANCHOR_MS):
    eid = str(uuid.UUID(int=0xC3000000 + serial, version=4))
    start, end = 1000 + phase * 10000, 2200 + phase * 10000
    return {"schema_version": 1, "episode_id": eid, "device_id": device, "session_id": session,
            "t_start_ms": start, "t_end_ms": end, "clock_anchor": {"mono_ms": 0, "wall_ms": wall_ms},
            "capture": {"width": 160, "height": 120}, "analysis": {"width": 80, "height": 60},
            "keyframes": [{"frame_id": eid + "-before", "t_ms": start, "role": "pre_contact", "jpeg_b64": tagged_jpeg(before)},
                          {"frame_id": eid + "-rest", "t_ms": end, "role": "rest", "jpeg_b64": tagged_jpeg(rest)}],
            "carry_burst": [], "landmarks": [], "gaps": [], "outcome_hint": "released", "capture_mode": "manual"}


def rest_frame_id(packet):
    return packet["keyframes"][-1]["frame_id"]


def rest_jpeg_bytes(packet):
    return base64.b64decode(packet["keyframes"][-1]["jpeg_b64"])


# --- adapters (the one place to touch if Builder A's spelling differs) ---------------------
def attach_embedder(store, embedder):
    """The plan names set_embedder(embedder | None) (and a constructor argument)."""
    store.set_embedder(embedder)
    return store


def make_matcher(quantile, embedder_tag=EMBEDDER_TAG):
    """The plan writes ConformalMatcher(calibration); Builder A's spelling is
    ConformalMatcher(quantile, embedder_tag, calibration_id)."""
    from perception.identity import ConformalMatcher
    return ConformalMatcher(quantile, embedder_tag, "adapter")


def match(matcher, query, banks, excluded=()):
    """match(query, banks, excluded): banks travel as {item_id: ItemBank}."""
    return matcher.match(query, {bank.item_id: bank for bank in banks}, set(excluded))


def bank_add(bank, *, observation_id, frame_id, vector, embedder=EMBEDDER_TAG):
    """ItemBank entries are {observation_id, frame_id, embedder, vector} (positional add)."""
    bank.add(observation_id, frame_id, embedder, vector)


def bank_entries(bank):
    """The bank's stored entries, oldest first (the plan: 'holds [{...}]', max 32)."""
    return list(bank.entries)


def reference_quantile(pairs, alpha):
    """Independent oracle: the ceil((n+1)(1-alpha))-th smallest same-pair
    nonconformity (the tie in the fixture makes the numpy 'higher' spelling agree)."""
    scores = sorted(1.0 - float(cosine) for cosine, same in pairs if same)
    n = len(scores)
    k = math.ceil((n + 1) * (1 - alpha))
    return scores[min(k, n) - 1]


# --- fixture ----------------------------------------------------------------------------------
class IdentityFixture(bootstrap.MemoryApiFixture):
    """Reuses the bootstrap guards (egress, private files, env) and temp DB; the app it
    builds is unused here. Everything below talks to ObjectStore directly."""
    def setUp(self):
        super().setUp()
        # The bootstrap app's lifespan worker polls process_pending every second with
        # the bootstrap processor on this same database; close it so it cannot claim a
        # job between ingest_episode and the synchronous process_pending below.
        self.client.__exit__(None, None, None)
        self.embedder = SyntheticEmbedder()
        self.cp3 = Cp3Processor()
        self.phase = 0
        self.store = self.make_store(self.embedder)

    def make_store(self, embedder, profile="local"):
        from perception.object_memory import ObjectStore
        return attach_embedder(ObjectStore(self.db, profile_id=profile, clock=self.clock), embedder)

    def register(self, calibration_id=CAL_WIDE, *, quantile=None, embedder=EMBEDDER_TAG, approve=True, approved_field=False, store=None, created_ms=ANCHOR_MS):
        store = self.store if store is None else store
        quantile = (TIGHT_Q if calibration_id == CAL_TIGHT else WIDE_Q) if quantile is None else quantile
        store.register_calibration(calibration_record(calibration_id, quantile=quantile, embedder=embedder, approved=approved_field, created_ms=created_ms))
        if approve:
            store.approve_calibration(calibration_id, ACTOR)

    def parked_observation_ids(self, store=None):
        """Observations the matcher parked as ambiguous (candidates recorded) that no
        item's evidence currently holds. Rows are never rewritten (decisions are
        versioned), so "parked" is judged through the effective evidence view."""
        store = self.store if store is None else store
        with self.sql() as db:
            rows = db.execute("SELECT observation_id,record,candidates FROM local_observations WHERE profile_id=? AND record IS NOT NULL ORDER BY observed_at_ms", (store.profile_id,)).fetchall()
        ambiguous = [r["observation_id"] for r in rows if json.loads(r["record"]).get("identity_state") == "ambiguous" and r["candidates"]]
        held = {observation_id for item in store.list_items() for observation_id in self.evidence_ids(item["item_id"], store)}
        return [observation_id for observation_id in ambiguous if observation_id not in held]

    def seed_separable_lookalikes(self):
        """A (tag 0) and B (tag 1) first seen apart under the tight calibration (no
        cannot-link between them), then the wide calibration is approved and a lone
        tag-0 sighting is ambiguous between them. Returns (a_id, b_id, parked_id)."""
        self.register(CAL_TIGHT, created_ms=ANCHOR_MS)
        self.sight([region(LEFT, 0)], calibration_id=CAL_TIGHT, locations=["fixture shelf left"])
        self.sight([region(RIGHT, 1)], calibration_id=CAL_TIGHT, locations=["fixture shelf right"])
        a, b = (i["item_id"] for i in sorted(self.items(), key=lambda i: i["location_text"]))
        self.assertEqual(self.cannot_links(), set())
        self.register(CAL_WIDE, created_ms=ANCHOR_MS + 1000)
        self.sight([region(MIDDLE, 0)], locations=["fixture shelf middle"])
        self.assertEqual({i["identity_status"] for i in self.items()}, {"ambiguous"})
        parked = self.parked_observation_ids()
        self.assertEqual(len(parked), 1, parked)
        return a, b, parked[0]

    def sight(self, regions, *, labels=None, locations=None, calibration_id=CAL_WIDE, store=None, extra=None, expect_failed=0, before=()):
        """Ingest one packet whose rest frame shows `regions` and register one
        trusted-claim observation per region, then process. Returns the packet."""
        store = self.store if store is None else store
        packet = cp3_packet(next(self.serial), rest=regions, before=before, phase=self.phase)
        self.phase += 1
        frame = rest_frame_id(packet)
        labels = [GLASSES] * len(regions) if labels is None else labels
        locations = [f"fixture shelf {i}" for i in range(len(regions))] if locations is None else locations
        self.cp3.observations[packet["episode_id"]] = [
            cp3_observation(frame, reg, label=labels[i], location=locations[i], calibration_id=calibration_id, **(extra or {}))
            for i, reg in enumerate(regions)]
        ack = store.ingest_episode(bootstrap.encode_packet(packet))
        self.assertEqual(ack["status"], "stored", ack)
        counts = store.process_pending(processor=self.cp3)
        self.assertEqual(counts["failed"], expect_failed, f"local processing: {counts}; last embedder calls: {self.embedder.calls[-4:]}")
        self.assertEqual(counts["pending"], 0, counts)
        return packet

    def items(self, store=None, **kwargs):
        store = self.store if store is None else store
        return store.list_items(**kwargs)

    def only_item(self, store=None, **kwargs):
        items = self.items(store, **kwargs)
        self.assertEqual(len(items), 1, items)
        return items[0]

    def evidence_ids(self, item_id, store=None):
        store = self.store if store is None else store
        return [row["observation_id"] for row in store.item_evidence(item_id)]

    def observation_ids(self, store=None):
        store = self.store if store is None else store
        with self.sql() as db:
            return [r[0] for r in db.execute("SELECT observation_id FROM local_observations WHERE profile_id=? AND record IS NOT NULL ORDER BY observed_at_ms", (store.profile_id,))]

    @contextlib.contextmanager
    def sql(self):
        db = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        try:
            yield db
        finally:
            db.close()

    def table_exists(self, name):
        with self.sql() as db:
            return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None

    def embedding_rows(self, observation_ids=None):
        """Rows of the `embeddings` table as dicts (empty when the table is absent)."""
        if not self.table_exists("embeddings"):
            return []
        with self.sql() as db:
            rows = [dict(row) for row in db.execute("SELECT * FROM embeddings")]
        if rows and "observation_id" not in rows[0]:
            self.fail(f"embeddings table is not keyed by observation_id: columns {list(rows[0])}")
        if observation_ids is not None:
            rows = [row for row in rows if row["observation_id"] in set(observation_ids)]
        return rows

    @staticmethod
    def stored_vector(row):
        blobs = [value for value in row.values() if isinstance(value, (bytes, memoryview))]
        if len(blobs) != 1:
            raise AssertionError(f"expected exactly one BLOB column (the float32 vector) in {row}")
        return np.frombuffer(bytes(blobs[0]), dtype=np.float32)

    def cannot_links(self):
        with self.sql() as db:
            return {(r[0], r[1]) for r in db.execute("SELECT item_a,item_b FROM local_cannot_links WHERE profile_id='local'")}

    def audit_rows(self, action=None):
        with self.sql() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM local_audit WHERE profile_id='local' ORDER BY audit_id")]
        return [r for r in rows if action is None or r["action"] == action]

    def delete_projection_rows(self):
        db = sqlite3.connect(str(self.db))
        try:
            with db:
                db.execute("DELETE FROM current_items WHERE profile_id='local'")
        finally:
            db.close()

    def snapshot(self, store=None):
        store = self.store if store is None else store
        items = store.list_items()
        return {"items": items,
                "get": {item["item_id"]: store.get_item(item["item_id"]) for item in items},
                "evidence": {item["item_id"]: store.item_evidence(item["item_id"]) for item in items},
                "glasses": store.answer_text(ASK_GLASSES), "bottle": store.answer_text(ASK_BOTTLE)}


# --- fixture self-tests: these need no builder code and pass today ---------------------------
class FixtureSelfTests(unittest.TestCase):
    def test_tag_round_trips_through_jpeg_in_either_channel_order_and_under_a_mask(self):
        embedder = SyntheticEmbedder()
        for tag in range(TAG_COUNT):
            for position in (LEFT, MIDDLE, RIGHT):
                encoded = tagged_jpeg([region(position, tag), region(LEFT if position != LEFT else RIGHT, (tag + 3) % TAG_COUNT)])
                image = cv2.imdecode(np.frombuffer(base64.b64decode(encoded), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
                x1, y1, x2, y2 = (int(v) for v in bbox(region(position, tag)))
                crop = image[y1:y2, x1:x2]
                self.assertEqual(embedder.read_tag(crop), tag)
                self.assertEqual(embedder.read_tag(crop[..., ::-1]), tag, "the tag must not depend on BGR/RGB order")
                mask = np.zeros(crop.shape[:2], dtype=bool)
                mask[4:20, 4:20] = True
                self.assertEqual(embedder.read_tag(crop, mask), tag)
                padded = image[max(0, y1 - 8):y2 + 8, max(0, x1 - 8):x2 + 8]
                self.assertEqual(embedder.read_tag(padded), tag, "a padded crop still decodes")
                with self.assertRaises(ValueError):
                    embedder.read_tag(image[0:SQUARE, 0:SQUARE])  # plain checkerboard: no tag
                vector = embedder.embed(crop, None)
                self.assertEqual(vector.dtype, np.float32)
                self.assertEqual(vector.shape, (16,))
                self.assertAlmostEqual(float(np.linalg.norm(vector)), 1.0, places=5)
                self.assertGreater(SyntheticEmbedder.cosine(vector, embedder.prototype(tag)), 0.98)

    def test_prototype_geometry_is_as_documented(self):
        embedder = SyntheticEmbedder()
        same = [SyntheticEmbedder.cosine(embedder.vector(0, a), embedder.vector(0, b)) for a in range(20) for b in range(20, 40)]
        lookalike = [SyntheticEmbedder.cosine(embedder.vector(0, a), embedder.vector(1, b)) for a in range(20) for b in range(20, 40)]
        different = [SyntheticEmbedder.cosine(embedder.vector(0, a), embedder.vector(2, b)) for a in range(20) for b in range(20, 40)]
        self.assertGreaterEqual(min(same), 0.96)
        self.assertAlmostEqual(float(np.mean(same)), 0.98, delta=0.005)
        self.assertGreaterEqual(min(lookalike), 0.86)
        self.assertLessEqual(max(lookalike), 0.905)
        self.assertLessEqual(max(abs(v) for v in different), 0.025)
        self.assertAlmostEqual(SyntheticEmbedder.cosine(embedder.prototype(2), embedder.prototype(4)), embedder.LOOKALIKE_COS, places=6)
        # Deterministic: the same draw gives the same vector.
        np.testing.assert_array_equal(embedder.vector(3, 7), embedder.vector(3, 7))

    def test_calibration_pairs_fixture_arithmetic(self):
        data = json.loads(PAIRS_FILE.read_text(encoding="utf-8"))
        pairs = [(p["cosine"], p["same"]) for p in data["pairs"]]
        expected = data["expected"]
        self.assertEqual(sum(1 for _, same in pairs if same), expected["n_same"])
        self.assertEqual(sum(1 for _, same in pairs if not same), expected["n_different"])
        self.assertEqual(expected["n_same"], 40)
        self.assertEqual(expected["k"], math.ceil((expected["n_same"] + 1) * (1 - data["alpha"])))
        scores = sorted(1 - c for c, same in pairs if same)
        self.assertEqual([round(s, 3) for s in scores], expected["same_nonconformities_sorted"])
        self.assertAlmostEqual(reference_quantile(pairs, data["alpha"]), expected["quantile"], delta=1e-9)
        # Both spellings of the finite-sample rule agree on this fixture (the designed tie).
        self.assertAlmostEqual(float(np.quantile(scores, expected["k"] / expected["n_same"], method="higher")), expected["quantile"], delta=1e-9)
        # And the wrong spellings do not.
        self.assertNotAlmostEqual(scores[math.ceil(expected["n_same"] * (1 - data["alpha"])) - 1], expected["quantile"], delta=1e-9)
        self.assertNotAlmostEqual(float(np.quantile(scores, 1 - data["alpha"])), expected["quantile"], delta=1e-9)
        self.assertTrue(all(1 - c > expected["quantile"] for c, same in pairs if not same))
        self.assertTrue(all(-1 <= c <= 1 for c, _ in pairs))


# --- perception/identity.py units ------------------------------------------------------------
class CalibrateTests(unittest.TestCase):
    def pairs(self):
        data = json.loads(PAIRS_FILE.read_text(encoding="utf-8"))
        return [(p["cosine"], p["same"]) for p in data["pairs"]], data

    def test_quantile_matches_the_hand_computed_fixture(self):
        from perception.identity import calibrate
        pairs, data = self.pairs()
        quantile = calibrate(pairs, data["alpha"])
        self.assertIsInstance(quantile, float)
        self.assertAlmostEqual(quantile, data["expected"]["quantile"], delta=1e-6)
        self.assertAlmostEqual(calibrate(pairs, alpha=0.05), quantile, delta=1e-9)

    def test_different_pairs_do_not_enter_the_quantile(self):
        from perception.identity import calibrate
        pairs, data = self.pairs()
        same_only = [p for p in pairs if p[1]]
        self.assertAlmostEqual(calibrate(same_only, data["alpha"]), calibrate(pairs, data["alpha"]), delta=1e-9)
        # Shifting every different pair much closer still changes nothing.
        shifted = same_only + [(0.80, False)] * 40
        self.assertAlmostEqual(calibrate(shifted, data["alpha"]), data["expected"]["quantile"], delta=1e-6)

    def test_fewer_than_20_same_pairs_raises(self):
        from perception.identity import calibrate
        pairs, data = self.pairs()
        same_only = [p for p in pairs if p[1]]
        with self.assertRaises(ValueError):
            calibrate(same_only[:19], data["alpha"])
        with self.assertRaises(ValueError):
            calibrate(same_only[:19] + [p for p in pairs if not p[1]], data["alpha"])  # n counts SAME pairs
        with self.assertRaises(ValueError):
            calibrate([], data["alpha"])
        self.assertIsInstance(calibrate(same_only[:20], data["alpha"]), float)

    def test_coverage_on_held_out_synthetic_same_pairs(self):
        """Split-conformal guarantee: P(nonconformity of a fresh same pair <= q) >= 1 - alpha,
        marginally over the calibration draw. With n = 40 the realised coverage of one
        calibration set is Beta(39, 2) (mean 0.951, sd 0.033; 5th percentile ~0.89), and
        200 held-out pairs add sampling sd 0.015. Everything here is seeded, so the
        number is fixed; the tolerance 0.05 (coverage >= 0.90) sits inside that spread
        while still failing a quantile that is off by one sorted position in the wrong
        direction at this spread. Different pairs must all fall outside the set."""
        from perception.identity import calibrate
        embedder = SyntheticEmbedder()
        def pair(tag_a, tag_b, draw):
            return SyntheticEmbedder.cosine(embedder.vector(tag_a, 1000 + draw), embedder.vector(tag_b, 5000 + draw))
        calibration = [(pair(t % 7, t % 7, t), True) for t in range(40)] + [(pair(0, 2, t), False) for t in range(40)]
        quantile = calibrate(calibration, 0.05)
        self.assertGreater(quantile, 0.0)
        self.assertLess(quantile, 0.1)
        held_out_same = [pair(t % 7, t % 7, 100 + t) for t in range(200)]
        covered = sum(1 for cosine in held_out_same if 1 - cosine <= quantile) / len(held_out_same)
        self.assertGreaterEqual(covered, 0.90, f"held-out coverage {covered:.3f} with quantile {quantile:.4f}")
        held_out_different = [pair(0, 2, 300 + t) for t in range(100)] + [pair(3, 5, 400 + t) for t in range(100)]
        self.assertTrue(all(1 - cosine > quantile for cosine in held_out_different))
        # Lookalikes (prototype cosine 0.90) are OUTSIDE a quantile calibrated on this
        # embedder's same pairs: ambiguity in the pipeline tests below therefore needs
        # the explicitly registered wide record (0.17), never this one.
        lookalikes = [pair(0, 1, 500 + t) for t in range(100)]
        self.assertTrue(all(1 - cosine > quantile for cosine in lookalikes))


class BankAndMatcherTests(unittest.TestCase):
    def setUp(self):
        self.embedder = SyntheticEmbedder()

    def bank(self, item_id, tag, count=1):
        from perception.identity import ItemBank
        bank = ItemBank(item_id)
        for i in range(count):
            bank_add(bank, observation_id=f"{item_id}-obs-{i}", frame_id=f"{item_id}-frame-{i}", vector=self.embedder.vector(tag, 10 * i + 1))
        return bank

    def test_bank_scores_max_cosine_and_keeps_at_most_32_vectors(self):
        bank = self.bank("A", 0, count=3)
        query = self.embedder.vector(0, 999)
        expected = max(SyntheticEmbedder.cosine(query, self.embedder.vector(0, 10 * i + 1)) for i in range(3))
        self.assertAlmostEqual(bank.score(query), expected, places=5)
        self.assertLess(abs(bank.score(self.embedder.vector(2, 7))), 0.03)
        big = self.bank("B", 0, count=40)
        entries = bank_entries(big)
        self.assertEqual(len(entries), 32, "max 32 vectors, oldest evicted")
        self.assertEqual([entry["observation_id"] for entry in entries][:2], ["B-obs-8", "B-obs-9"])
        self.assertEqual(set(entries[0]), {"observation_id", "frame_id", "embedder", "vector"})
        self.assertEqual(big.item_id, "B")

    def test_matcher_states_scores_and_exclusions(self):
        banks = [self.bank("A", 0), self.bank("B", 1), self.bank("C", 2)]
        query = self.embedder.vector(0, 4242)
        matcher = make_matcher(WIDE_Q)
        result = match(matcher, query, banks)
        self.assertEqual(set(result), {"set", "scores", "state"})
        self.assertEqual(sorted(result["set"]), ["A", "B"])
        self.assertEqual(result["state"], "ambiguous")
        self.assertTrue({"A", "B"} <= set(result["scores"]))
        for item_id, bank in zip("ABC", banks):
            if item_id in result["scores"]:
                self.assertAlmostEqual(result["scores"][item_id], bank.score(query), places=5)
        excluded = match(matcher, query, banks, {"A"})
        self.assertEqual((excluded["set"], excluded["state"]), (["B"], "match"))
        both = match(matcher, query, banks, {"A", "B"})
        self.assertEqual((both["set"], both["state"]), ([], "new"))
        self.assertEqual(match(matcher, query, [])["state"], "new")
        tight = make_matcher(TIGHT_Q)
        self.assertEqual(match(tight, query, banks)["set"], ["A"])
        self.assertEqual(match(tight, query, banks)["state"], "match")
        self.assertEqual(match(tight, self.embedder.vector(3, 1), banks)["state"], "new")
        # The boundary is inclusive: nonconformity == quantile is inside the set.
        exact = make_matcher(1 - banks[2].score(self.embedder.vector(2, 55)))
        self.assertIn("C", match(exact, self.embedder.vector(2, 55), banks)["set"])


# --- the pipeline: new -> match -> ambiguous -> group -------------------------------------------
class IdentityPipelineTests(IdentityFixture):
    def test_first_sighting_creates_a_new_trusted_item_with_a_stored_embedding(self):
        self.register()
        packet = self.sight([region(LEFT, 0)], locations=["fixture shelf left"])
        item = self.only_item()
        self.assertEqual(item["identity_status"], "trusted")
        self.assertEqual(item["location_status"], "placed")
        self.assertEqual(item["location_text"], "fixture shelf left")
        self.assertEqual(item["name"], GLASSES)
        self.assertFalse(item.get("lookalikes"), item)
        self.assertEqual(item["reference_image"], {"frame_id": rest_frame_id(packet), "bbox": bbox(region(LEFT, 0))})
        self.assertEqual(len(self.embedder.calls), 1, "one embed per observation with a region")
        self.assertEqual(self.embedder.calls[0]["tag"], 0)
        rows = self.embedding_rows()
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["observation_id"], item["observation_id"])
        self.assertIn(EMBEDDER_TAG, [v for v in rows[0].values() if isinstance(v, str)], "the embedder name@version is stored with the vector")
        vector = self.stored_vector(rows[0])
        self.assertEqual(vector.shape, (16,))
        self.assertGreater(SyntheticEmbedder.cosine(vector, self.embedder.prototype(0)), 0.98)
        self.assertEqual(self.store.answer_text(ASK_GLASSES)["shape"], "confident")

    def test_second_sighting_rematches_into_one_item_with_two_observations(self):
        self.register()
        first = self.sight([region(LEFT, 0)], locations=["fixture shelf left"])
        original = self.only_item()
        second = self.sight([region(RIGHT, 0)], locations=["fixture shelf right"])
        item = self.only_item()
        self.assertEqual(item["item_id"], original["item_id"])
        self.assertEqual(item["identity_status"], "trusted")
        self.assertEqual(item["location_status"], "placed")
        self.assertEqual(item["location_text"], "fixture shelf right")
        self.assertEqual(item["observed_at_ms"], ANCHOR_MS + 12200)
        self.assertEqual(item["reference_image"]["frame_id"], rest_frame_id(second))
        evidence = self.store.item_evidence(item["item_id"])
        self.assertEqual(len(evidence), 2)
        self.assertTrue(all(EVIDENCE_FIELDS <= set(row) for row in evidence), evidence)
        self.assertEqual(sorted(row["observed_at_ms"] for row in evidence), [ANCHOR_MS + 2200, ANCHOR_MS + 12200])
        self.assertEqual({row["identity_status"] for row in evidence}, {"trusted"})
        self.assertEqual({row["reference_image"]["frame_id"] for row in evidence}, {rest_frame_id(first), rest_frame_id(second)})
        self.assertEqual(len(self.embedding_rows()), 2)
        self.assertEqual(len(self.embedder.calls), 2)
        self.assertEqual(len(self.store.item_history(item["item_id"])), 2)
        answer = self.store.answer_text(ASK_GLASSES)
        self.assertEqual(answer["shape"], "confident")
        self.assertIn("fixture shelf right", answer["text"])

    def test_unapproved_calibration_never_yields_trusted(self):
        # The record claims approved: true, but approval comes only from approve_calibration.
        self.register(approve=False, approved_field=True)
        # A processor cannot approve itself either: an observation dict that says
        # approved: true while naming an unapproved record is provisional (only a
        # fixture_only record keeps the CP2 code-only semantics, bootstrap suite).
        self.sight([region(LEFT, 0)], extra={"calibration": {"calibration_id": CAL_WIDE, "approved": True}})
        self.sight([region(RIGHT, 0)])
        for item in self.items():
            self.assertEqual(item["identity_status"], "provisional", item)
            self.assertNotEqual(item["location_status"], "placed")
            self.assertIsNone(item["location_text"])
        self.assertNotEqual(self.store.answer_text(ASK_GLASSES)["shape"], "confident")
        before_ids = self.observation_ids()
        self.store.approve_calibration(CAL_WIDE, ACTOR)
        self.sight([region(MIDDLE, 0)])
        items = self.items()
        trusted = [item for item in items if item["identity_status"] == "trusted"]
        self.assertEqual(len(trusted), 1, items)
        self.assertEqual(trusted[0]["location_status"], "placed")
        self.assertLessEqual(len(items), 2)
        # Decisions are versioned at processing time: approval does not rewrite history.
        for item in items:
            for row in self.store.item_evidence(item["item_id"]):
                if row["observation_id"] in before_ids:
                    self.assertEqual(row["identity_status"], "provisional", row)

    def test_unknown_calibration_id_or_other_embedder_stays_provisional(self):
        self.register()                                                        # synthetic@1, approved
        self.register("cp3-other-embedder", quantile=WIDE_Q, embedder="other@9")  # approved, wrong embedder
        self.sight([region(LEFT, 0)], calibration_id="no-such-calibration")
        self.sight([region(LEFT, 2)], labels=[BOTTLE], calibration_id="cp3-other-embedder")
        items = self.items()
        self.assertEqual(len(items), 2, items)
        for item in items:
            self.assertEqual(item["identity_status"], "provisional", item)
            self.assertIsNone(item["location_text"])
        self.assertEqual(self.store.answer_text(ASK_BOTTLE)["shape"], "hedged")

    def test_different_objects_stay_separate_items(self):
        self.register()
        self.sight([region(LEFT, 0)], labels=[GLASSES])
        self.sight([region(LEFT, 2)], labels=[BOTTLE])
        items = {item["name"]: item for item in self.items()}
        self.assertEqual(set(items), {GLASSES, BOTTLE})
        self.assertEqual({item["identity_status"] for item in items.values()}, {"trusted"})
        self.assertEqual(self.cannot_links(), set(), "separate frames create no cannot-link")
        self.sight([region(RIGHT, 2)], labels=[BOTTLE], locations=["fixture shelf right"])
        after = {item["name"]: item for item in self.items()}
        self.assertEqual(after[BOTTLE]["item_id"], items[BOTTLE]["item_id"])
        self.assertEqual(after[BOTTLE]["location_text"], "fixture shelf right")
        self.assertEqual(len(self.evidence_ids(after[BOTTLE]["item_id"])), 2)
        self.assertEqual(len(self.evidence_ids(after[GLASSES]["item_id"])), 1)
        self.assertEqual(self.store.answer_text(ASK_BOTTLE)["shape"], "confident")

    def test_lookalikes_become_ambiguous_with_a_group_answer_that_upgrades_nobody(self):
        self.register()
        # Two lookalikes (tags 0 and 1, prototype cosine 0.90) first seen together in
        # one frame: B-03 keeps them distinct; both are trusted and placed.
        first = self.sight([region(LEFT, 0), region(RIGHT, 1)], locations=["fixture shelf left", "fixture shelf right"])
        items = sorted(self.items(), key=lambda i: i["location_text"])
        self.assertEqual(len(items), 2, items)
        self.assertEqual({i["identity_status"] for i in items}, {"trusted"})
        self.assertEqual({i["location_status"] for i in items}, {"placed"})
        a, b = items
        self.assertEqual(self.cannot_links(), {tuple(sorted((a["item_id"], b["item_id"])))})
        clarify = self.store.answer_text(ASK_GLASSES)
        self.assertEqual(clarify["shape"], "clarify", "distinct items with the same words clarify")
        self.assertEqual({m["item_id"] for m in clarify["members"]}, {a["item_id"], b["item_id"]})
        # A later single sighting of tag 0 is inside the wide quantile for BOTH banks.
        self.sight([region(MIDDLE, 0)], locations=["fixture shelf middle"])
        items = {i["item_id"]: i for i in self.items()}
        self.assertEqual(set(items), {a["item_id"], b["item_id"]}, "an ambiguous observation is not a third catalogue item")
        for item_id, other in ((a["item_id"], b["item_id"]), (b["item_id"], a["item_id"])):
            item = items[item_id]
            self.assertEqual(item["identity_status"], "ambiguous", item)
            self.assertEqual(item["lookalikes"], [other], item)
            self.assertEqual(item["observed_at_ms"], ANCHOR_MS + 2200, "an ambiguous match never updates a candidate (B-14)")
            self.assertEqual(item["reference_image"]["frame_id"], rest_frame_id(first))
        with self.sql() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM local_observations WHERE profile_id='local' AND record IS NOT NULL")]
        ambiguous = [r for r in rows if json.loads(r["record"]).get("identity_state") == "ambiguous"]
        self.assertEqual(len(ambiguous), 1, [json.loads(r["record"]).get("identity_state") for r in rows])
        self.assertIn("candidates", ambiguous[0], "local_observations gains a candidates column")
        candidates = ambiguous[0]["candidates"]
        candidates = json.loads(candidates) if isinstance(candidates, str) else candidates
        self.assertEqual(sorted(candidates), sorted((a["item_id"], b["item_id"])))
        self.assertEqual(len(self.embedding_rows()), 3, "the ambiguous observation's embedding is stored too")
        # The group answer.
        answer = self.store.answer_text(ASK_GLASSES)
        self.assertEqual(answer["shape"], "group", answer)
        self.assertEqual(answer["text"], GROUP_TEXT.format(n=2))
        self.assertEqual({m["item_id"] for m in answer["members"]}, {a["item_id"], b["item_id"]})
        # Coordinator ruling 5: the group names the parked observation the user's
        # choice will resolve (assign_observation).
        self.assertEqual(answer["unresolved_observation_id"], ambiguous[0]["observation_id"])
        for member in answer["members"]:
            self.assertEqual(member["identity_status"], "ambiguous")
            self.assertEqual(set(member["provenance"]), {"observation_id", "identity_status"}, member)
            self.assertIn(member["provenance"]["observation_id"], self.evidence_ids(member["item_id"]))
            self.assertIn(member["provenance"]["identity_status"], IDENTITY_VOCABULARY)
            self.assertEqual(member["reference_image"]["frame_id"], rest_frame_id(first))
            self.assertEqual(member["observed_at_ms"], ANCHOR_MS + 2200)
            self.assertIn("location_text", member)
            self.assertIn(member["lookalikes"], ([a["item_id"]], [b["item_id"]]))
        # Asking for one member by id is still not a confident answer.
        single = self.store.answer_text(a["item_id"])
        self.assertEqual([m["item_id"] for m in single["members"]], [a["item_id"]])
        self.assertNotEqual(single["shape"], "confident")
        # Seeing the same pair again does not grow the group or the catalogue: an
        # ambiguous observation is one of the candidates, never a further item, and
        # it never enters a bank (an ambiguous match never writes to the bank).
        self.sight([region(RIGHT, 0)], locations=["fixture shelf right"])
        self.assertEqual({i["item_id"] for i in self.items()}, {a["item_id"], b["item_id"]}, "a repeated ambiguous sighting must not add a catalogue item")
        again = self.store.answer_text(ASK_GLASSES)
        self.assertEqual(again["shape"], "group")
        self.assertEqual(again["text"], GROUP_TEXT.format(n=2))
        self.assertEqual(len(self.embedding_rows()), 4)
        # A distinct item with the same words breaks mutuality: clarify, not group.
        self.sight([region(LEFT, 2)], labels=[GLASSES])
        mixed = self.store.answer_text(ASK_GLASSES)
        self.assertEqual(mixed["shape"], "clarify", mixed)
        self.assertEqual(len(mixed["members"]), 3)

    def test_tight_calibration_keeps_lookalikes_apart(self):
        self.register(CAL_TIGHT)
        self.sight([region(LEFT, 0), region(RIGHT, 1)], calibration_id=CAL_TIGHT, locations=["fixture shelf left", "fixture shelf right"])
        a, b = sorted(self.items(), key=lambda i: i["location_text"])
        self.sight([region(MIDDLE, 0)], calibration_id=CAL_TIGHT, locations=["fixture shelf middle"])
        items = {i["item_id"]: i for i in self.items()}
        self.assertEqual(set(items), {a["item_id"], b["item_id"]})
        self.assertEqual({i["identity_status"] for i in items.values()}, {"trusted"}, "nonconformity 0.12 is outside a 0.05 quantile")
        self.assertEqual(items[a["item_id"]]["location_text"], "fixture shelf middle")
        self.assertEqual(items[b["item_id"]]["location_text"], "fixture shelf right")
        self.assertEqual(len(self.evidence_ids(a["item_id"])), 2)
        self.sight([region(MIDDLE, 1)], calibration_id=CAL_TIGHT, locations=["fixture shelf back"])
        self.assertEqual(self.store.get_item(b["item_id"])["location_text"], "fixture shelf back")
        self.assertEqual(self.store.answer_text(ASK_GLASSES)["shape"], "clarify")

    def test_covisible_identical_outputs_never_merge_even_without_a_mask(self):
        # B-03: two regions in ONE frame with the same tag (cosine ~0.98, well inside the
        # quantile) and mask_rle None (registration gave no diff mask).
        self.register()
        self.sight([region(LEFT, 0), region(RIGHT, 0)], extra={"mask_rle": None}, locations=["fixture shelf left", "fixture shelf right"])
        items = self.items()
        self.assertEqual(len(items), 2, items)
        self.assertEqual({i["identity_status"] for i in items}, {"trusted"})
        pair = tuple(sorted(i["item_id"] for i in items))
        self.assertEqual(self.cannot_links(), {pair})
        self.assertEqual([c["mask"] for c in self.embedder.calls], [None, None])
        with self.assertRaisesRegex(ValueError, "cannot-link"):
            self.store.link_items(pair[0], pair[1], ACTOR)
        # Seen alone later, the system cannot tell them apart: ambiguous, not merged.
        self.sight([region(MIDDLE, 0)])
        after = {i["item_id"]: i for i in self.items()}
        self.assertEqual(set(after), set(pair))
        self.assertEqual({i["identity_status"] for i in after.values()}, {"ambiguous"})
        self.assertEqual(self.store.answer_text(ASK_GLASSES)["shape"], "group")

    def test_cannot_link_survives_failed_registration_and_a_missing_embedder(self):
        self.register()
        self.sight([region(LEFT, 0), region(RIGHT, 0)], locations=["fixture shelf left", "fixture shelf right"])
        pair = tuple(sorted(i["item_id"] for i in self.items()))
        self.assertEqual(self.cannot_links(), {pair})
        # A region with no decodable tag: the embedder raises. Whether the job fails or
        # the observation falls back to provisional, the cannot-link must survive.
        packet = cp3_packet(next(self.serial), rest=[], phase=self.phase)
        self.phase += 1
        self.cp3.observations[packet["episode_id"]] = [cp3_observation(rest_frame_id(packet), region(MIDDLE, 0), location="fixture shelf middle")]
        self.store.ingest_episode(bootstrap.encode_packet(packet))
        counts = self.store.process_pending(processor=self.cp3)
        self.assertEqual(counts["pending"], 0, counts)
        self.assertGreaterEqual(len(self.embedder.calls), 2)
        self.assertEqual(self.cannot_links(), {pair}, "a failed embedding never removes a cannot-link")
        self.assertTrue({pair[0], pair[1]} <= {i["item_id"] for i in self.items()})
        with self.assertRaisesRegex(ValueError, "cannot-link"):
            self.store.link_items(pair[0], pair[1], ACTOR)
        # The identity model goes away (embedder None): still provisional-only processing,
        # still no merge, still refused.
        without = self.make_store(None)
        before = len(self.embedding_rows())
        self.sight([region(MIDDLE, 0)], store=without)
        self.assertEqual(len(self.embedding_rows()), before, "no embedder, no embedding rows")
        self.assertEqual(self.cannot_links(), {pair})
        items = {i["item_id"]: i for i in self.items(without)}
        self.assertTrue(set(pair) <= set(items))
        for item_id, item in items.items():
            if item_id not in pair:
                self.assertEqual(item["identity_status"], "provisional", item)
        with self.assertRaisesRegex(ValueError, "cannot-link"):
            without.link_items(pair[0], pair[1], ACTOR)

    def test_embedder_absent_means_provisional_only_no_embeddings_and_capability_false(self):
        store = self.make_store(None)
        self.register(store=store)
        self.sight([region(LEFT, 0)], store=store, locations=["fixture shelf left"])
        self.sight([region(RIGHT, 0)], store=store, locations=["fixture shelf right"])
        items = self.items(store)
        self.assertGreaterEqual(len(items), 1)
        for item in items:
            self.assertEqual(item["identity_status"], "provisional", item)
            self.assertEqual(item["location_status"], "sighted")
            self.assertIsNone(item["location_text"])
            self.assertFalse(item.get("lookalikes"))
        self.assertEqual(self.embedding_rows(), [])
        self.assertEqual(self.embedder.calls, [])
        self.assertNotEqual(store.answer_text(ASK_GLASSES)["shape"], "confident")
        capability = [c for c in store.capabilities() if c["name"] == CAPABILITY]
        self.assertEqual(len(capability), 1)
        self.assertIs(capability[0]["enabled"], False)
        self.assertEqual(set(capability[0]), {"name", "enabled", "reason"})
        self.assertNotIn(str(self.root), capability[0]["reason"])
        # Detaching the embedder from a store that had one has the same effect.
        attach_embedder(self.store, None)
        self.sight([region(LEFT, 2)], labels=[BOTTLE])
        self.assertEqual(self.embedder.calls, [])
        self.assertEqual(self.embedding_rows(), [])
        self.assertEqual([i["identity_status"] for i in self.items() if i["name"] == BOTTLE], ["provisional"])

    def test_item_evidence_and_observation_image(self):
        self.register()
        first = self.sight([region(LEFT, 0)], locations=["fixture shelf left"])
        second = self.sight([region(RIGHT, 0)], locations=["fixture shelf right"])
        other = self.sight([region(LEFT, 2)], labels=[BOTTLE])
        glasses = next(i for i in self.items() if i["name"] == GLASSES)
        bottle = next(i for i in self.items() if i["name"] == BOTTLE)
        evidence = self.store.item_evidence(glasses["item_id"])
        self.assertEqual(len(evidence), 2)
        by_frame = {row["reference_image"]["frame_id"]: row for row in evidence}
        self.assertEqual(set(by_frame), {rest_frame_id(first), rest_frame_id(second)})
        for row in evidence:
            self.assertTrue(EVIDENCE_FIELDS <= set(row), row)
            self.assertEqual(row["identity_status"], "trusted")
            self.assertEqual(row["outcome"], "placed_on_surface")
            self.assertEqual(row["reference_image"]["bbox"], bbox(region(LEFT if row["reference_image"]["frame_id"] == rest_frame_id(first) else RIGHT, 0)))
            self.assertNotIn(str(self.root), json.dumps(row))
        self.assertEqual(by_frame[rest_frame_id(first)]["location_text"], "fixture shelf left")
        self.assertEqual(by_frame[rest_frame_id(first)]["observed_at_ms"], ANCHOR_MS + 2200)
        self.assertEqual(self.store.observation_image(glasses["item_id"], by_frame[rest_frame_id(first)]["observation_id"]), rest_jpeg_bytes(first))
        self.assertEqual(self.store.observation_image(glasses["item_id"], by_frame[rest_frame_id(second)]["observation_id"]), rest_jpeg_bytes(second))
        bottle_obs = self.evidence_ids(bottle["item_id"])[0]
        self.assertEqual(self.store.observation_image(bottle["item_id"], bottle_obs), rest_jpeg_bytes(other))
        # Wrong item for the observation, unknown observation, unknown item: nothing served.
        for item_id, observation_id in ((glasses["item_id"], bottle_obs), (glasses["item_id"], "no-such-observation"), ("no-such-item", bottle_obs)):
            with self.subTest(item=item_id, observation=observation_id):
                try:
                    data = self.store.observation_image(item_id, observation_id)
                except KeyError:
                    continue
                self.assertIsNone(data)
        with self.assertRaises(KeyError):
            self.store.item_evidence("no-such-item")
        # Another profile sees nothing of this one.
        foreign = self.make_store(self.embedder, profile="other-profile")
        with self.assertRaises(KeyError):
            foreign.item_evidence(glasses["item_id"])
        try:
            self.assertIsNone(foreign.observation_image(glasses["item_id"], bottle_obs))
        except KeyError:
            pass


# --- corrections and replay --------------------------------------------------------------------
class CorrectionTests(IdentityFixture):
    def test_link_items_merges_observations_and_banks_with_an_audit_row(self):
        self.register()
        self.sight([region(LEFT, 0)], locations=["fixture shelf left"])
        self.sight([region(LEFT, 2)], locations=["fixture shelf back"])
        keep, other = (i["item_id"] for i in sorted(self.items(), key=lambda i: i["observed_at_ms"]))
        other_obs = self.evidence_ids(other)
        audits = len(self.audit_rows())
        result = self.store.link_items(keep, other, ACTOR)
        self.assertEqual(result["item_id"], keep)
        self.assertEqual(bootstrap.ITEM_FIELDS - set(result), set(), result)
        item = self.only_item()
        self.assertEqual(item["item_id"], keep)
        self.assertEqual(item["identity_status"], "trusted")
        self.assertEqual(item["location_text"], "fixture shelf back", "the merged item's latest observation wins")
        with self.assertRaises(KeyError):
            self.store.get_item(other)
        self.assertEqual(set(self.evidence_ids(keep)), set(self.evidence_ids(keep)) | set(other_obs))
        self.assertEqual(len(self.evidence_ids(keep)), 2)
        linked = self.audit_rows("user_linked")
        self.assertEqual(len(linked), 1, self.audit_rows()[audits:])
        self.assertEqual(linked[0]["item_id"], keep)
        self.assertIn(ACTOR, linked[0]["detail"])
        self.assertTrue(self.table_exists("corrections"))
        with self.sql() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM corrections").fetchone()[0], 1)
        # Banks merged: a fresh sighting of the OTHER prototype now matches the kept item.
        self.sight([region(RIGHT, 2)], locations=["fixture shelf right"])
        self.assertEqual(self.only_item()["item_id"], keep)
        self.assertEqual(len(self.evidence_ids(keep)), 3)
        self.assertEqual(self.only_item()["location_text"], "fixture shelf right")
        for a, b in ((keep, "no-such-item"), ("no-such-item", keep)):
            with self.assertRaises(KeyError):
                self.store.link_items(a, b, ACTOR)

    def test_link_items_refuses_a_cannot_linked_pair(self):
        self.register()
        self.sight([region(LEFT, 0), region(RIGHT, 1)])
        a, b = (i["item_id"] for i in self.items())
        before = self.snapshot()
        for keep, other in ((a, b), (b, a)):
            with self.assertRaisesRegex(ValueError, "cannot-link"):
                self.store.link_items(keep, other, ACTOR)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.audit_rows("user_linked"), [])
        with self.sql() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM corrections").fetchone()[0], 0)

    def test_unlink_observation_moves_it_to_a_new_item_with_a_cannot_link(self):
        self.register()
        first = self.sight([region(LEFT, 0)], locations=["fixture shelf left"])
        self.sight([region(RIGHT, 0)], locations=["fixture shelf right"])
        item = self.only_item()
        evidence = {row["reference_image"]["frame_id"]: row["observation_id"] for row in self.store.item_evidence(item["item_id"])}
        o1, o2 = evidence[rest_frame_id(first)], next(v for k, v in evidence.items() if k != rest_frame_id(first))
        result = self.store.unlink_observation(o2, ACTOR)
        self.assertEqual(bootstrap.ITEM_FIELDS - set(result), set(), result)
        new_id = result["item_id"]
        self.assertNotEqual(new_id, item["item_id"])
        items = {i["item_id"]: i for i in self.items()}
        self.assertEqual(set(items), {item["item_id"], new_id})
        self.assertEqual(self.evidence_ids(item["item_id"]), [o1])
        self.assertEqual(self.evidence_ids(new_id), [o2])
        self.assertEqual(items[item["item_id"]]["observed_at_ms"], ANCHOR_MS + 2200, "the original item falls back to its remaining evidence")
        self.assertEqual(items[item["item_id"]]["reference_image"]["frame_id"], rest_frame_id(first))
        self.assertEqual(items[new_id]["observed_at_ms"], ANCHOR_MS + 12200)
        self.assertEqual(self.cannot_links(), {tuple(sorted((item["item_id"], new_id)))})
        for keep, other in ((item["item_id"], new_id), (new_id, item["item_id"])):
            with self.assertRaisesRegex(ValueError, "cannot-link"):
                self.store.link_items(keep, other, ACTOR)
        unlinked = self.audit_rows("user_unlinked")
        self.assertEqual(len(unlinked), 1)
        self.assertIn(ACTOR, unlinked[0]["detail"])
        with self.assertRaises(KeyError):
            self.store.unlink_observation("no-such-observation", ACTOR)
        self.assertEqual(len(self.embedding_rows()), 2, "unlinking moves evidence; it never re-embeds or drops a vector")
        self.assertEqual(len(self.embedder.calls), 2)

    def test_rebuild_all_replays_corrections_from_stored_embeddings_without_embedding(self):
        self.register()
        self.sight([region(LEFT, 0), region(RIGHT, 1)], locations=["fixture shelf left", "fixture shelf right"])
        a, b = (i["item_id"] for i in sorted(self.items(), key=lambda i: i["location_text"]))
        self.sight([region(LEFT, 2)], labels=[BOTTLE], locations=["fixture shelf back"])
        self.sight([region(RIGHT, 2)], labels=[BOTTLE], locations=["fixture shelf front"])
        c = next(i["item_id"] for i in self.items() if i["name"] == BOTTLE)
        c_obs = self.store.item_evidence(c)
        self.assertEqual(len(c_obs), 2)
        moved = max(c_obs, key=lambda row: row["observed_at_ms"])["observation_id"]
        d = self.store.unlink_observation(moved, ACTOR)["item_id"]
        self.store.link_items(b, d, ACTOR)                       # allowed: B and D were never co-visible
        with self.assertRaises(KeyError):
            self.store.link_items(c, d, ACTOR)                   # D is merged away (tombstoned)
        with self.assertRaisesRegex(ValueError, "cannot-link"):
            # The user said D's observation is not C's; merging D into B must not let
            # C and B merge afterwards (the cannot-link follows the moved evidence).
            self.store.link_items(c, b, ACTOR)
        self.sight([region(MIDDLE, 0)], locations=["fixture shelf middle"])  # ambiguous between A and B
        before = self.snapshot()
        self.assertEqual({i["item_id"] for i in before["items"]}, {a, b, c})
        self.assertEqual(before["glasses"]["shape"], "group")
        self.assertEqual(len(self.evidence_ids(b)), 2)
        embeds = len(self.embedder.calls)
        self.delete_projection_rows()
        self.assertEqual(self.items(), [], "the stored projection was cleared for this replay check")
        result = self.store.rebuild_all()
        self.assertIs(result["model_rerun"], False)
        self.assertEqual(result["count"], 3)
        self.assertEqual(len(self.embedder.calls), embeds, "rebuild_all replays stored embeddings; it never calls embed()")
        self.assertEqual(self.snapshot(), before)
        # Replay on a fresh store instance (no in-memory state) gives the same projection.
        fresh = self.make_store(SyntheticEmbedder())
        self.delete_projection_rows()
        fresh.rebuild_all()
        self.assertEqual(self.snapshot(fresh), before)

    def test_as_of_before_a_correction_shows_the_pre_correction_state(self):
        self.register()
        self.sight([region(LEFT, 0)], locations=["fixture shelf left"])
        self.sight([region(LEFT, 2)], locations=["fixture shelf back"])
        a, c = (i["item_id"] for i in sorted(self.items(), key=lambda i: i["observed_at_ms"]))
        before_link_ms = self.store._now_ms()
        self.now += 10
        self.store.link_items(a, c, ACTOR)
        self.assertEqual([i["item_id"] for i in self.items()], [a])
        self.assertEqual(self.store.answer_text(ASK_GLASSES)["shape"], "confident")
        earlier = self.items(as_of=before_link_ms)
        self.assertEqual({i["item_id"] for i in earlier}, {a, c})
        self.assertEqual(self.store.get_item(c, as_of=before_link_ms)["item_id"], c)
        with self.assertRaises(KeyError):
            self.store.get_item(c)
        replayed = self.store.answer_text(ASK_GLASSES, as_of=before_link_ms)
        self.assertEqual(replayed["shape"], "clarify")
        self.assertEqual({m["item_id"] for m in replayed["members"]}, {a, c})
        self.assertEqual([i["item_id"] for i in self.items(as_of=self.store._now_ms() + 1)], [a])
        self.assertEqual(self.store.rebuild_all(as_of=before_link_ms)["count"], 2)
        # Same for an unlink: before it, the moved observation still belongs to its item.
        self.sight([region(RIGHT, 0)], locations=["fixture shelf right"])
        moved = max(self.store.item_evidence(a), key=lambda row: row["observed_at_ms"])["observation_id"]
        before_unlink_ms = self.store._now_ms()
        self.now += 10
        new_id = self.store.unlink_observation(moved, ACTOR)["item_id"]
        self.assertEqual({i["item_id"] for i in self.items()}, {a, new_id})
        self.assertEqual([i["item_id"] for i in self.items(as_of=before_unlink_ms)], [a])
        self.assertEqual(self.store.get_item(a, as_of=before_unlink_ms)["location_text"], "fixture shelf right")
        self.assertEqual(self.store.get_item(a)["location_text"], "fixture shelf back")

    def test_assign_observation_resolves_the_group_without_inferring_cannot_links_and_replays(self):
        # Coordinator ruling 5 (CP3), cannot-link clause reversed after Oversight's
        # review: the user said "this sighting is A", not "A and B are different
        # objects". A parked ambiguous observation becomes A's evidence with a
        # user-asserted identity (trusted, identity_source "user_assigned"), its
        # outcome/location untouched; the group dissolves; NO cannot-link is inferred
        # between A and the other candidates (they may be fragmented duplicates a later
        # link merges); a second assign is refused as not-ambiguous; rebuild_all
        # reproduces the result without embedding; an unlink withdraws the assertion.
        a, b, parked = self.seed_separable_lookalikes()
        group = self.store.answer_text(ASK_GLASSES)
        self.assertEqual(group["shape"], "group")
        self.assertEqual(group["unresolved_observation_id"], parked)
        for item_id in (a, b):
            self.assertNotIn(parked, self.evidence_ids(item_id), "a parked observation belongs to no item")
        with self.sql() as db:
            stored = json.loads(db.execute("SELECT record FROM local_observations WHERE observation_id=?", (parked,)).fetchone()[0])
        self.assertEqual((stored["identity_state"], stored["outcome"], stored.get("location_text")), ("ambiguous", "sighted", None))
        audits = len(self.audit_rows())
        result = self.store.assign_observation(parked, a, ACTOR)
        self.assertEqual(result["item_id"], a)
        self.assertEqual(bootstrap.ITEM_FIELDS - set(result), set(), result)
        self.assertIn(parked, self.evidence_ids(a))
        self.assertNotIn(parked, self.evidence_ids(b))
        self.assertEqual(self.parked_observation_ids(), [], "nothing is parked any more")
        items = {i["item_id"]: i for i in self.items()}
        self.assertEqual(set(items), {a, b})
        for item in items.values():
            self.assertNotEqual(item["identity_status"], "ambiguous", item)
            self.assertEqual(item["lookalikes"], [], item)
        # The assertion is on the sighting's identity only; evidence says who said so.
        rows = {row["observation_id"]: row for row in self.store.item_evidence(a)}
        self.assertEqual(rows[parked]["identity_status"], "trusted")
        self.assertEqual(rows[parked]["identity_source"], "user_assigned")
        self.assertEqual((rows[parked]["outcome"], rows[parked]["location_text"]), (stored["outcome"], None), "outcome and location are not rewritten by a user's identity choice")
        for observation_id, row in rows.items():
            if observation_id != parked:
                self.assertEqual(row["identity_source"], "processor", row)
        for row in self.store.item_evidence(b):
            self.assertEqual(row["identity_source"], "processor", row)
        self.assertEqual(self.cannot_links(), set(), "no cannot-link is inferred between the chosen item and the other candidates")
        dissolved = self.store.answer_text(ASK_GLASSES)
        self.assertEqual(dissolved["shape"], "clarify", dissolved)
        self.assertNotIn("unresolved_observation_id", {k for k, v in dissolved.items() if v})
        chosen = self.store.answer_text(a)
        self.assertEqual([m["item_id"] for m in chosen["members"]], [a])
        self.assertEqual(chosen["shape"], "hedged", "a user-attributed sighting is still only a sighting: hedged, never confident")
        assigned = self.audit_rows("user_assigned")
        self.assertEqual(len(assigned), 1, self.audit_rows()[audits:])
        self.assertEqual(assigned[0]["item_id"], a)
        self.assertIn(ACTOR, assigned[0]["detail"])
        # A second assign of the same observation, an ordinary (never parked)
        # observation, and unknown ids are refused.
        with self.assertRaisesRegex(ValueError, "not-ambiguous"):
            self.store.assign_observation(parked, b, ACTOR)
        with self.assertRaisesRegex(ValueError, "not-ambiguous"):
            self.store.assign_observation(self.evidence_ids(b)[0], a, ACTOR)
        with self.assertRaises(KeyError):
            self.store.assign_observation("no-such-observation", a, ACTOR)
        with self.assertRaises(KeyError):
            self.store.assign_observation(parked, "no-such-item", ACTOR)
        # Replay: the stored assign reproduces the projection with no embed() call.
        before = self.snapshot()
        embeds = len(self.embedder.calls)
        self.delete_projection_rows()
        self.assertEqual(self.items(), [])
        result = self.store.rebuild_all()
        self.assertIs(result["model_rerun"], False)
        self.assertEqual(len(self.embedder.calls), embeds, "rebuild_all never embeds")
        self.assertEqual(self.snapshot(), before)
        fresh = self.make_store(SyntheticEmbedder())
        self.delete_projection_rows()
        fresh.rebuild_all()
        self.assertEqual(self.snapshot(fresh), before)
        self.assertEqual(len(self.embedding_rows()), 3, "assigning moves evidence; it never re-embeds or drops a vector")
        # The two candidates were never separated by the user's choice: a later
        # "same as" merges them (fragmented duplicates), and the assigned evidence
        # travels with the kept item.
        merged = self.store.link_items(a, b, ACTOR)
        self.assertEqual(merged["item_id"], a)
        self.assertEqual([i["item_id"] for i in self.items()], [a])
        self.assertEqual(len(self.evidence_ids(a)), 3)
        self.assertIn(parked, self.evidence_ids(a))
        # "Not this one" on the assigned sighting withdraws the assertion: under its
        # new item it reads provisional again (and a cannot-link now separates them).
        new_id = self.store.unlink_observation(parked, ACTOR)["item_id"]
        self.assertEqual(self.evidence_ids(new_id), [parked])
        withdrawn = self.store.item_evidence(new_id)[0]
        self.assertEqual(withdrawn["identity_status"], "provisional", withdrawn)
        self.assertNotEqual(self.store.get_item(new_id)["identity_status"], "trusted")
        self.assertEqual(self.cannot_links(), {tuple(sorted((a, new_id)))})
        self.assertEqual(len(self.evidence_ids(a)), 2)
        replayed = self.snapshot()
        self.delete_projection_rows()
        self.store.rebuild_all()
        self.assertEqual(self.snapshot(), replayed)
        self.assertEqual(len(self.embedder.calls), embeds)

    def test_actor_is_a_closed_role_set_never_a_person(self):
        # Coordinator ruling 6 (B-15): corrections and approvals are attributed to a
        # session role from a closed set; a name, an empty string or a non-string is refused.
        self.register(approve=False)
        for actor in ("Dr Smith", "", "caregiver_pin ", "CAREGIVER_PIN", None, 7, "admin"):
            with self.subTest(actor=actor), self.assertRaises((ValueError, TypeError)):
                self.store.approve_calibration(CAL_WIDE, actor)
        self.store.approve_calibration(CAL_WIDE, "test")
        self.sight([region(LEFT, 0)], labels=[GLASSES])
        self.sight([region(LEFT, 2)], labels=[GLASSES])
        a, c = (i["item_id"] for i in sorted(self.items(), key=lambda i: i["observed_at_ms"]))
        for actor in ("Dr Smith", "", None, "admin"):
            with self.subTest(actor=actor), self.assertRaises((ValueError, TypeError)):
                self.store.link_items(a, c, actor)
        self.assertEqual(len(self.items()), 2, "a refused actor merges nothing")
        self.store.link_items(a, c, "operator")
        self.assertEqual(len(self.items()), 1)
        with self.sql() as db:
            actors = {r[0] for r in db.execute("SELECT actor FROM corrections WHERE profile_id='local'")}
        self.assertEqual(actors, {"operator"})
        self.sight([region(RIGHT, 0)], labels=[GLASSES])
        moved = max(self.store.item_evidence(a), key=lambda row: row["observed_at_ms"])["observation_id"]
        with self.assertRaises((ValueError, TypeError)):
            self.store.unlink_observation(moved, "Dr Smith")
        self.store.unlink_observation(moved, "caregiver_pin")

    def test_redact_item_removes_or_nulls_its_embeddings(self):
        self.register()
        self.sight([region(LEFT, 0)], locations=["fixture shelf left"])
        self.sight([region(RIGHT, 0)], locations=["fixture shelf right"])
        self.sight([region(LEFT, 2)], labels=[BOTTLE])
        glasses = next(i for i in self.items() if i["name"] == GLASSES)
        bottle = next(i for i in self.items() if i["name"] == BOTTLE)
        glasses_obs = self.evidence_ids(glasses["item_id"])
        bottle_obs = self.evidence_ids(bottle["item_id"])
        self.assertEqual(len(self.embedding_rows(glasses_obs)), 2)
        result = self.store.redact_item(glasses["item_id"])
        self.assertIs(result["redacted"], True)
        for row in self.embedding_rows(glasses_obs):
            self.assertFalse(any(isinstance(v, (bytes, memoryview)) for v in row.values()), f"vector survived redaction: {row}")
        self.assertEqual(len(self.embedding_rows(bottle_obs)), 1, "an unrelated item keeps its embedding")
        self.assertEqual([i["item_id"] for i in self.items()], [bottle["item_id"]])
        with self.assertRaises(KeyError):
            self.store.item_evidence(glasses["item_id"])
        # Replay does not resurrect the redacted vectors or item.
        embeds = len(self.embedder.calls)
        self.store.rebuild_all()
        self.assertEqual(len(self.embedder.calls), embeds)
        self.assertEqual([i["item_id"] for i in self.items()], [bottle["item_id"]])
        self.sight([region(RIGHT, 0)])
        self.assertNotIn(glasses["item_id"], {i["item_id"] for i in self.items()})


if __name__ == "__main__":
    unittest.main(verbosity=2)
