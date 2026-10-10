"""CP4 acceptance, store level: idle keyframes and rule-13 re-observation.

    python3 -B server/test_cp4_idle.py -v

Authority: docs/BUILD_PLAN.md "CP4 in detail" (architect, 2026-10-09), sections
*Idle keyframes* and *Re-observation*. Interfaces under test (binding on Builder A):

  ObjectStore.ingest_idle(raw: bytes) -> {"frame_id", "retained": True, "expires_at_ms"}
      (retained False with reason "idle_cap" at IDLE_MAX_PER_DAY; ValueError on an
      invalid body, PacketTooLarge (a ValueError) over MAX_IDLE_BYTES)
  ObjectStore.expire_idle(now_ms)                  hard-deletes expired unpromoted rows
  ObjectStore.reobserve(now_ms, *, limit=16) -> counts (a dict)
  constants MAX_IDLE_BYTES, IDLE_TTL_MS, IDLE_MAX_PER_DAY, IDLE_CACHE_BYTES,
      REOBS_SAME_MAX, REOBS_GONE_MIN (perception.episode_store or perception.episode)
  tables idle_frames(profile_id, device_id, frame_id, t_wall_ms, received_ms, width,
      height, jpeg, motion_energy, expires_at_ms, promoted) and reobservations(
      profile_id, item_id, frame_id, t_wall_ms, result, region_diff, registered, embedded)

Frames come from server/fixtures/cp4/reobservation_goldens.json (test_cp4_fixtures);
the builder's region_diff must land inside the oracle's measured band and its verdict
must match. Thresholds are the plan's initial values pending P-105.
"""
from __future__ import annotations

import base64
import hashlib
import importlib
import json
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
import test_memory_bootstrap as bootstrap  # noqa: E402
import test_cp3_identity as identity  # noqa: E402
import test_cp4_fixtures as fx  # noqa: E402

ANCHOR_MS = fx.ANCHOR_MS
HOUR_MS = fx.HOUR_MS
LABEL = "synthetic cp4 block"
LOCATION = "fixture cp4 table"
ASK = "where is my synthetic cp4 block"
IDLE_COLUMNS = {"profile_id", "device_id", "frame_id", "t_wall_ms", "received_ms", "width", "height", "jpeg", "motion_energy", "expires_at_ms", "promoted"}
REOBS_COLUMNS = {"profile_id", "item_id", "frame_id", "t_wall_ms", "result", "region_diff", "registered", "embedded"}


def constant_module(name):
    for module_name in ("perception.episode_store", "perception.episode", "perception.object_memory", "perception.reobservation"):
        try:
            module = importlib.import_module(module_name)
        except ImportError:
            continue
        if hasattr(module, name):
            return module
    raise AssertionError(f"constant {name} is not a module attribute of perception.episode_store / episode / object_memory / reobservation")


class RemappingEmbedder(identity.SyntheticEmbedder):
    """The CP3 synthetic embedder with a test knob: tags in `remap` embed as another
    prototype, so a crop that is pixel-identical to the bank's evidence can be made
    to NOT match (identity withheld) without touching the frame."""
    def __init__(self):
        super().__init__()
        self.remap = {}

    def embed(self, crop, mask=None):
        record = {"shape": getattr(crop, "shape", None), "mask": None if mask is None else tuple(np.asarray(mask).shape), "tag": None}
        self.calls.append(record)
        tag = self.read_tag(crop, mask)
        record["tag"] = tag
        draw = int(hashlib.sha256(np.ascontiguousarray(crop).tobytes()).hexdigest()[:8], 16)
        return self.vector(self.remap.get(tag, tag), draw)


class IdleFixture(fx.Cp4Fixture):
    def place_block(self, *, location=LOCATION, label=LABEL, wall_ms=ANCHOR_MS, **kwargs):
        """One trusted placement of the block item at BLOCK_BBOX on the reference
        golden; returns (packet, item)."""
        packet = self.place([fx.observation(None, fx.BLOCK_BBOX, label=label, location=location)], wall_ms=wall_ms, **kwargs)
        item = self.item_by_name(label)
        self.assertEqual(item["location_status"], "placed", item)
        self.assertEqual(item["identity_status"], "trusted", item)
        self.assertEqual(item["observed_at_ms"], fx.rest_wall_ms(packet))
        return packet, item

    def idle_rows(self):
        return self.rows("idle_frames", "WHERE profile_id='local' ORDER BY t_wall_ms, received_ms, frame_id")

    def reobs_rows(self, item_id=None):
        rows = self.rows("reobservations", "WHERE profile_id='local' ORDER BY t_wall_ms, frame_id")
        return [r for r in rows if item_id is None or r["item_id"] == item_id]

    def evidence(self, item_id):
        return self.store.item_evidence(item_id)

    def assert_band(self, name, value):
        # +/- 0.04 around the oracle's four measurements: the builder registers at analysis
        # resolution with its own window rounding (measured 0.279 for "gone" against the
        # oracle's 0.299 at half resolution); the verdict thresholds are the hard pins.
        low, high = fx.golden_band(name, margin=0.04)
        self.assertIsNotNone(value, f"{name}: region_diff must be recorded when registration succeeds")
        self.assertTrue(low <= float(value) <= high, f"{name}: region_diff {value} outside the oracle band [{low:.4f}, {high:.4f}]")


class IdleIngestTests(IdleFixture):
    def test_constants_match_the_plan(self):
        for name in ("MAX_IDLE_BYTES", "IDLE_TTL_MS", "IDLE_MAX_PER_DAY", "IDLE_CACHE_BYTES", "REOBS_SAME_MAX", "REOBS_GONE_MIN"):
            with self.subTest(constant=name):
                self.assertEqual(fx.constant(name), fx.PLAN[name])

    def test_valid_idle_frame_is_retained_in_the_cache_table_and_listed_nowhere(self):
        self.assertTrue(fx.table_exists(self.db, "idle_frames"), "idle_frames table")
        self.assertTrue(IDLE_COLUMNS <= set(fx.columns(self.db, "idle_frames")), fx.columns(self.db, "idle_frames"))
        packet, ack = self.idle("present", t_ms=500, mono_ms=100, wall_ms=ANCHOR_MS + 60000, motion_energy=0.0123)
        self.assertTrue({"frame_id", "retained", "expires_at_ms"} <= set(ack), ack)
        self.assertEqual(ack["frame_id"], packet["frame_id"])
        self.assertIs(ack["retained"], True)
        self.assertEqual(ack["expires_at_ms"], self.now_ms() + fx.PLAN["IDLE_TTL_MS"])
        rows = self.idle_rows()
        self.assertEqual(len(rows), 1, rows)
        row = rows[0]
        self.assertEqual((row["device_id"], row["frame_id"], row["profile_id"]), (fx.DEVICE, packet["frame_id"], "local"))
        self.assertEqual(row["t_wall_ms"], fx.idle_wall_ms(packet))
        self.assertEqual(row["received_ms"], self.now_ms())
        self.assertEqual((row["width"], row["height"]), (fx.SCENE_W, fx.SCENE_H))
        self.assertEqual(bytes(row["jpeg"]), fx.golden_bytes("present"))
        self.assertAlmostEqual(row["motion_energy"], 0.0123, places=6)
        self.assertEqual(row["expires_at_ms"], ack["expires_at_ms"])
        self.assertEqual(row["promoted"], 0)
        # A cache row, not evidence: no item, observation, revision or job comes from it.
        self.assertEqual(self.items(), [])
        for table in ("local_observations", "episode_revisions", "episode_jobs"):
            self.assertEqual(self.rows(table), [], table)
        # Another profile on the same database sees none of it.
        other = self.make_store(profile="other-profile")
        self.assertEqual(fx.table_rows(self.db, "idle_frames", "WHERE profile_id='other-profile'"), [])
        self.assertEqual(other.list_items(), [])

    def test_invalid_idle_bodies_are_refused_without_a_row(self):
        small = fx.jpeg_b64(cv2.resize(fx.scene_image(), (fx.SCENE_W // 2, fx.SCENE_H // 2)))
        good = fx.idle_packet()
        cases = {
            "not json": b"{",
            "a list": b"[]",
            "duplicate key": b'{"schema_version":1,"schema_version":1}',
            "missing jpeg": {k: v for k, v in good.items() if k != "jpeg_b64"},
            "extra field": {**good, "profile_id": "other"},
            "trusted field": {**good, "promoted": 1},
            "schema version 2": {**good, "schema_version": 2},
            "schema version string": {**good, "schema_version": "1"},
            "device not a uuid": {**good, "device_id": "device-1"},
            "session not a uuid": {**good, "session_id": "session-1"},
            "dimension mismatch": {**good, "jpeg_b64": small},
            "capture too large": {**good, "capture": {"width": 4000, "height": 4000}},
            "invalid base64": {**good, "jpeg_b64": "not-base64!"},
            "not a jpeg": {**good, "jpeg_b64": base64.b64encode(b"PNG-NOT-JPEG" * 20).decode()},
            "negative t_ms": {**good, "t_ms": -1},
            "boolean t_ms": {**good, "t_ms": True},
            "wall_ms zero": {**good, "clock_anchor": {"mono_ms": 0, "wall_ms": 0}},
            "motion energy negative": {**good, "motion_energy": -0.1},
            "motion energy above one": {**good, "motion_energy": 1.5},
            "motion energy boolean": {**good, "motion_energy": True},
            "motion energy string": {**good, "motion_energy": "0.1"},
            "empty frame id": {**good, "frame_id": ""},
            "frame id too long": {**good, "frame_id": "f" * 101},
        }
        for name, body in cases.items():
            with self.subTest(case=name):
                raw = body if isinstance(body, bytes) else bootstrap.encode_packet(body)
                with self.assertRaises(ValueError):
                    self.store.ingest_idle(raw)
        with self.assertRaises(ValueError):
            self.store.ingest_idle(bootstrap.encode_packet(good).decode("utf-8"))  # str, not bytes
        self.assertEqual(self.idle_rows(), [])

    def test_body_cap_is_256_kib_of_actual_bytes(self):
        raw = bootstrap.encode_packet(fx.idle_packet())
        padded = raw + b" " * (fx.PLAN["MAX_IDLE_BYTES"] - len(raw))
        self.assertEqual(len(padded), fx.PLAN["MAX_IDLE_BYTES"])
        self.assertIs(self.store.ingest_idle(padded)["retained"], True, "exactly the cap is accepted")
        over = bootstrap.encode_packet(fx.idle_packet()) + b" " * (fx.PLAN["MAX_IDLE_BYTES"] + 1 - len(raw))
        self.assertGreater(len(over), fx.PLAN["MAX_IDLE_BYTES"])
        with self.assertRaises(ValueError) as caught:
            self.store.ingest_idle(over)
        from perception.episode import PacketTooLarge
        self.assertIsInstance(caught.exception, PacketTooLarge, "over the cap is the 413 error class, as for episodes")
        self.assertEqual(len(self.idle_rows()), 1)

    def test_daily_cap_refuses_with_reason_idle_cap_until_the_next_day(self):
        module = constant_module("IDLE_MAX_PER_DAY")
        with patch.object(module, "IDLE_MAX_PER_DAY", 3):
            acks = [self.idle("present", wall_ms=ANCHOR_MS + 1000 * i)[1] for i in range(3)]
            self.assertTrue(all(ack["retained"] is True for ack in acks), acks)
            packet, refused = self.idle("present", wall_ms=ANCHOR_MS + 9000)
            self.assertIs(refused["retained"], False, "the 4th frame of the day must be refused (the cap is read from the module attribute at call time; "
                                                      "if the store binds IDLE_MAX_PER_DAY differently this patch cannot reach it)")
            self.assertEqual(refused.get("reason"), "idle_cap", refused)
            self.assertEqual(refused.get("frame_id"), packet["frame_id"])
            self.assertEqual(len(self.idle_rows()), 3, "a refused frame leaves no row")
            self.assertNotIn(packet["frame_id"], {r["frame_id"] for r in self.idle_rows()})
            # Another profile has its own count.
            other = self.make_store(profile="other-profile")
            self.assertIs(other.ingest_idle(bootstrap.encode_packet(fx.idle_packet()))["retained"], True)
            # The next day the cap opens again (the expired rows of yesterday are also gone).
            self.now += 25 * 3600
            self.store.expire_idle(self.now_ms())
            self.assertIs(self.idle("present", wall_ms=ANCHOR_MS + 25 * HOUR_MS)[1]["retained"], True)

    def test_expiry_at_24_hours_deletes_unpromoted_rows_only(self):
        received = self.now_ms()
        packet, ack = self.idle("present", wall_ms=ANCHOR_MS + 60000)
        self.assertEqual(ack["expires_at_ms"], received + fx.PLAN["IDLE_TTL_MS"])
        self.store.expire_idle(received + fx.PLAN["IDLE_TTL_MS"] - 1)
        self.assertEqual([r["frame_id"] for r in self.idle_rows()], [packet["frame_id"]], "one millisecond before expiry the row stays")
        self.store.expire_idle(received + fx.PLAN["IDLE_TTL_MS"] + 1)
        self.assertEqual(self.idle_rows(), [], "an expired unpromoted frame is hard-deleted")
        # A promoted frame (a positive re-observation) never expires.
        placement, item = self.place_block()
        promoted, _ = self.idle("present", wall_ms=fx.rest_wall_ms(placement) + 60000)
        self.reobserve()
        rows = {r["frame_id"]: r for r in self.idle_rows()}
        self.assertEqual(rows[promoted["frame_id"]]["promoted"], 1, rows)
        self.store.expire_idle(received + 10 * fx.DAY_MS)
        self.assertEqual([r["frame_id"] for r in self.idle_rows()], [promoted["frame_id"]])

    def test_cache_byte_cap_evicts_the_oldest_unpromoted_first_and_never_a_promoted_frame(self):
        frame_bytes = len(fx.golden_bytes("gone"))
        module = constant_module("IDLE_CACHE_BYTES")
        placement, item = self.place_block()
        base = fx.rest_wall_ms(placement)
        with patch.object(module, "IDLE_CACHE_BYTES", int(frame_bytes * 2.5)):
            a, _ = self.idle("gone", wall_ms=base + 1000)
            b, _ = self.idle("gone", wall_ms=base + 2000)
            self.assertEqual([r["frame_id"] for r in self.idle_rows()], [a["frame_id"], b["frame_id"]], "two frames fit under 2.5 frames")
            c, ack = self.idle("gone", wall_ms=base + 3000)
            self.assertIs(ack["retained"], True, "eviction makes room; the new frame is retained")
            ids = [r["frame_id"] for r in self.idle_rows()]
            self.assertNotIn(a["frame_id"], ids, "the oldest unpromoted frame is evicted first (if the cap is not read from the module "
                                                 "attribute at call time this patch cannot reach it)")
            self.assertEqual(ids, [b["frame_id"], c["frame_id"]])
            d, _ = self.idle("gone", wall_ms=base + 4000)
            self.assertEqual([r["frame_id"] for r in self.idle_rows()], [c["frame_id"], d["frame_id"]])
            # Promote one frame (a positive re-observation of the placement): it is never evicted.
            e, _ = self.idle("present", wall_ms=base + 5000)
            self.now += 120
            self.reobserve()
            rows = {r["frame_id"]: r["promoted"] for r in self.idle_rows()}
            self.assertEqual(rows.get(e["frame_id"]), 1, rows)
            for n in range(6, 10):
                self.idle("gone", wall_ms=base + 1000 * n)
                rows = {r["frame_id"]: r["promoted"] for r in self.idle_rows()}
                self.assertEqual(rows.get(e["frame_id"]), 1, f"the promoted frame survived every eviction: {rows}")
                self.assertLessEqual(sum(1 for promoted in rows.values() if not promoted), 2, rows)
            latest = self.idle_rows()[-1]
            self.assertEqual(latest["t_wall_ms"], base + 9000, "the newest frame is always kept")


class ReobservationTests(IdleFixture):
    def test_present_promotes_the_frame_writes_a_sighting_and_is_processed_once(self):
        self.assertTrue(fx.table_exists(self.db, "reobservations"), "reobservations table")
        self.assertTrue(REOBS_COLUMNS <= set(fx.columns(self.db, "reobservations")), fx.columns(self.db, "reobservations"))
        placement, item = self.place_block()
        before = self.evidence(item["item_id"])
        self.assertEqual(len(before), 1)
        idle, _ = self.idle("present", wall_ms=fx.rest_wall_ms(placement) + 60000)
        self.now += 120
        counts = self.reobserve()
        self.assertIsInstance(counts, dict, counts)
        self.assertTrue(all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in counts.values()), counts)
        self.assertEqual((counts.get("present"), counts.get("promoted")), (1, 1), counts)
        rows = self.reobs_rows()
        self.assertEqual(len(rows), 1, rows)
        row = rows[0]
        self.assertEqual((row["item_id"], row["frame_id"], row["t_wall_ms"]), (item["item_id"], idle["frame_id"], fx.idle_wall_ms(idle)))
        self.assertEqual(row["result"], "present")
        self.assertEqual((row["registered"], row["embedded"]), (1, 0), "diff-only without an embedder")
        self.assert_band("present", row["region_diff"])
        # Promoted, never expires.
        self.assertEqual({r["frame_id"]: r["promoted"] for r in self.idle_rows()}, {idle["frame_id"]: 1})
        # The sighting: outcome sighted, source reobservation, location inherited, identity provisional (diff only).
        after = self.store.get_item(item["item_id"])
        self.assertEqual(after["observed_at_ms"], fx.idle_wall_ms(idle), "ageing resets without a hand event")
        self.assertEqual(after["location_status"], "placed")
        self.assertEqual(after["location_text"], LOCATION)
        self.assertEqual(after["identity_status"], "trusted", "a diff-only sighting refreshes the placement; it does not downgrade the item")
        self.assertIsNone(after["stale_reason"])
        self.assertIs(after["aged"], False)
        evidence = self.evidence(item["item_id"])
        self.assertEqual(len(evidence), 2, evidence)
        newest = max(evidence, key=lambda r: r["observed_at_ms"])
        self.assertEqual(newest["observed_at_ms"], fx.idle_wall_ms(idle))
        self.assertEqual(newest["outcome"], "sighted")
        self.assertEqual(newest["identity_status"], "provisional")
        self.assertEqual(newest["reference_image"]["frame_id"], idle["frame_id"])
        self.assertEqual(newest["reference_image"]["bbox"], fx.BLOCK_BBOX)
        history = self.store.item_history(item["item_id"])
        sighting = next(r for r in history if r.get("observed_at_ms") == fx.idle_wall_ms(idle))
        self.assertEqual(sighting.get("source"), "reobservation")
        self.assertEqual(sighting.get("location_text"), LOCATION)
        # The promoted idle frame serves as an ordinary observation image, unmodified.
        self.assertEqual(self.store.observation_image(item["item_id"], newest["observation_id"]), fx.golden_bytes("present"))
        # A frame is processed once: a second pass adds nothing.
        self.reobserve()
        self.assertEqual(len(self.reobs_rows()), 1)
        self.assertEqual(len(self.evidence(item["item_id"])), 2)
        self.assertEqual(self.store.answer_text(ASK)["shape"], "confident")

    def test_gone_sets_stale_negative_reobservation_and_a_later_present_reverses_it(self):
        placement, item = self.place_block()
        base = fx.rest_wall_ms(placement)
        gone, _ = self.idle("gone", wall_ms=base + 60000)
        self.now += 120
        self.reobserve()
        rows = self.reobs_rows()
        self.assertEqual([r["result"] for r in rows], ["gone"], rows)
        self.assertEqual(rows[0]["registered"], 1)
        self.assert_band("gone", rows[0]["region_diff"])
        stale = self.store.get_item(item["item_id"])
        self.assertEqual(stale["location_status"], "stale")
        self.assertEqual(stale["stale_reason"], "negative_reobservation")
        self.assertEqual(stale["stale_since_ms"], fx.idle_wall_ms(gone))
        self.assertEqual(stale["observed_at_ms"], item["observed_at_ms"], "a negative re-observation is not a sighting of the item")
        self.assertEqual(stale["location_text"], LOCATION, "the last known place is kept as history")
        self.assertEqual(stale["identity_status"], "trusted")
        self.assertEqual(len(self.evidence(item["item_id"])), 1, "gone writes no observation row")
        self.assertEqual({r["frame_id"]: r["promoted"] for r in self.idle_rows()}, {gone["frame_id"]: 0}, "a negative frame is not promoted")
        listed = self.only_item()
        self.assertEqual((listed["location_status"], listed["stale_reason"], listed["stale_since_ms"]), ("stale", "negative_reobservation", fx.idle_wall_ms(gone)))
        answer = self.store.answer_text(ASK)
        self.assertNotEqual(answer["shape"], "confident", answer)
        self.assertEqual(answer["shape"], "hedged", answer)
        self.assertEqual([m["item_id"] for m in answer["members"]], [item["item_id"]])
        self.assertEqual(answer["members"][0]["stale_reason"], "negative_reobservation")
        # A later positive frame reverses it.
        present, _ = self.idle("present", wall_ms=base + 120000)
        self.now += 120
        self.reobserve()
        self.assertEqual([r["result"] for r in self.reobs_rows()], ["gone", "present"])
        fresh = self.store.get_item(item["item_id"])
        self.assertEqual(fresh["location_status"], "placed")
        self.assertIsNone(fresh["stale_reason"])
        self.assertIsNone(fresh["stale_since_ms"])
        self.assertEqual(fresh["observed_at_ms"], fx.idle_wall_ms(present))
        self.assertEqual(fresh["location_text"], LOCATION)
        self.assertEqual(self.store.answer_text(ASK)["shape"], "confident")

    def test_unknown_results_change_nothing(self):
        placement, item = self.place_block()
        base = fx.rest_wall_ms(placement)
        partial, _ = self.idle("partial", wall_ms=base + 60000)
        flat, _ = self.idle("flat", wall_ms=base + 90000)
        self.now += 120
        self.reobserve()
        rows = {r["frame_id"]: r for r in self.reobs_rows()}
        self.assertEqual(set(rows), {partial["frame_id"], flat["frame_id"]}, rows)
        self.assertEqual(rows[partial["frame_id"]]["result"], "unknown")
        self.assertEqual(rows[partial["frame_id"]]["registered"], 1, "the partial frame registers; its diff sits between the thresholds")
        self.assert_band("partial", rows[partial["frame_id"]]["region_diff"])
        self.assertEqual(rows[flat["frame_id"]]["result"], "unknown")
        self.assertEqual(rows[flat["frame_id"]]["registered"], 0, "a featureless frame fails registration: no decision")
        unchanged = self.store.get_item(item["item_id"])
        for key in ("location_status", "location_text", "observed_at_ms", "stale_reason", "identity_status"):
            self.assertEqual(unchanged[key], item[key], key)
        self.assertIsNone(unchanged.get("stale_since_ms"))
        self.assertEqual(len(self.evidence(item["item_id"])), 1)
        self.assertEqual({r["promoted"] for r in self.idle_rows()}, {0})
        # Processed once: nothing more on a second pass.
        self.reobserve()
        self.assertEqual(len(self.reobs_rows()), 2)

    def test_translated_frames_register_and_decide(self):
        placement, item = self.place_block()
        base = fx.rest_wall_ms(placement)
        moved, _ = self.idle("translated", wall_ms=base + 60000)
        self.now += 120
        self.reobserve()
        rows = {r["frame_id"]: r for r in self.reobs_rows()}
        self.assertEqual(rows[moved["frame_id"]]["result"], "present", rows)
        self.assertEqual(rows[moved["frame_id"]]["registered"], 1)
        self.assert_band("translated", rows[moved["frame_id"]]["region_diff"])
        self.assertEqual(self.store.get_item(item["item_id"])["observed_at_ms"], fx.idle_wall_ms(moved))
        moved_gone, _ = self.idle("translated_gone", wall_ms=base + 120000)
        self.now += 120
        self.reobserve()
        rows = {r["frame_id"]: r for r in self.reobs_rows()}
        self.assertEqual(rows[moved_gone["frame_id"]]["result"], "gone", rows)
        self.assert_band("translated_gone", rows[moved_gone["frame_id"]]["region_diff"])
        self.assertEqual(self.store.get_item(item["item_id"])["stale_reason"], "negative_reobservation")

    def test_ageing_resets_on_a_positive_re_observation(self):
        placement, item = self.place_block()
        observed = fx.rest_wall_ms(placement)
        self.now = (observed + 25 * HOUR_MS) / 1000
        aged = self.store.get_item(item["item_id"])
        self.assertIs(aged["aged"], True)
        self.assertEqual(aged["stale_reason"], "age")
        self.assertEqual(self.store.answer_text(ASK)["shape"], "hedged")
        idle, _ = self.idle("present", wall_ms=observed + 25 * HOUR_MS - 60000)
        self.reobserve()
        fresh = self.store.get_item(item["item_id"])
        self.assertEqual(fresh["observed_at_ms"], fx.idle_wall_ms(idle))
        self.assertIs(fresh["aged"], False)
        self.assertIsNone(fresh["stale_reason"])
        self.assertEqual(fresh["location_status"], "placed")
        self.assertEqual(self.store.answer_text(ASK)["shape"], "confident", "a fresh positive sighting makes the placement current again")
        # The stored projection carries the advanced time (no evaluated age in storage).
        with fx.sql(self.db) as db:
            record = json.loads(db.execute("SELECT record FROM current_items WHERE profile_id='local' AND item_id=?", (item["item_id"],)).fetchone()[0])
        self.assertEqual(record["observed_at_ms"], fx.idle_wall_ms(idle))
        self.assertIs(record["aged"], False)

    def test_frames_of_another_device_or_older_than_the_placement_are_never_used(self):
        placement, item = self.place_block()
        base = fx.rest_wall_ms(placement)
        foreign, _ = self.idle("gone", wall_ms=base + 60000, device=fx.OTHER_DEVICE)
        older, _ = self.idle("gone", wall_ms=base - 1000)
        same_time, _ = self.idle("gone", wall_ms=base)
        self.now += 120
        self.reobserve()
        self.assertEqual(self.reobs_rows(), [], "no decision from another device's frame or a frame not newer than the placement")
        unchanged = self.store.get_item(item["item_id"])
        self.assertEqual((unchanged["location_status"], unchanged["stale_reason"], unchanged["observed_at_ms"]), ("placed", None, base))
        self.assertEqual({r["frame_id"]: r["promoted"] for r in self.idle_rows()}, {foreign["frame_id"]: 0, older["frame_id"]: 0, same_time["frame_id"]: 0})
        # Still cached (they may serve a later placement on that device), still expiring.
        self.store.expire_idle(self.now_ms() + 2 * fx.DAY_MS)
        self.assertEqual(self.idle_rows(), [])

    def test_limit_bounds_one_pass_and_the_rest_waits(self):
        placement, item = self.place_block()
        base = fx.rest_wall_ms(placement)
        frames = [self.idle("present", wall_ms=base + 1000 * (i + 1))[0] for i in range(3)]
        self.now += 120
        self.reobserve(limit=1)
        self.assertEqual(len(self.reobs_rows()), 1)
        self.reobserve(limit=16)
        self.assertEqual({r["frame_id"] for r in self.reobs_rows()}, {f["frame_id"] for f in frames}, "every decision is recorded")
        self.assertEqual({r["result"] for r in self.reobs_rows()}, {"present"})
        # The projection advanced on the first positive frame. (Whether every later
        # positive frame within the same hour also writes a sighting is a plan-vs-builder
        # question flagged in the CP4 verdict; the acceptance effect is the reset itself.)
        observed = self.store.get_item(item["item_id"])["observed_at_ms"]
        self.assertGreaterEqual(observed, fx.idle_wall_ms(frames[0]))
        self.assertLessEqual(observed, fx.idle_wall_ms(frames[-1]))
        with self.assertRaises(ValueError):
            self.reobserve(limit=0)

    def test_unchanged_repeat_frame_is_gated_present_without_registration(self):
        # Coordinator ruling 11: a frame that barely differs from the previous frame
        # that showed the item present is decided present by the whole-frame gate
        # (reobservations.gated = 1, registered 0, no region_diff) and, inside the
        # hourly refresh window, neither promotes nor writes a sighting.
        placement, item = self.place_block()
        base = fx.rest_wall_ms(placement)
        first, _ = self.idle("present", wall_ms=base + 60000)
        self.now += 120
        counts = self.reobserve()
        self.assertEqual(counts.get("gated", 0), 0, counts)
        repeat, _ = self.idle("present", wall_ms=base + 90000)
        self.now += 120
        counts = self.reobserve()
        self.assertEqual(counts.get("gated"), 1, counts)
        rows = {r["frame_id"]: r for r in self.reobs_rows()}
        self.assertEqual(set(rows), {first["frame_id"], repeat["frame_id"]})
        self.assertEqual((rows[first["frame_id"]]["result"], rows[first["frame_id"]]["registered"], rows[first["frame_id"]].get("gated", 0)), ("present", 1, 0))
        gated = rows[repeat["frame_id"]]
        self.assertEqual((gated["result"], gated["registered"], gated.get("gated")), ("present", 0, 1), gated)
        self.assertIsNone(gated["region_diff"])
        self.assertEqual({r["frame_id"]: r["promoted"] for r in self.idle_rows()}, {first["frame_id"]: 1, repeat["frame_id"]: 0})
        self.assertEqual(len(self.evidence(item["item_id"])), 2, "the gated frame adds no sighting inside the refresh window")
        self.assertEqual(self.store.get_item(item["item_id"])["observed_at_ms"], fx.idle_wall_ms(first))
        # A changed frame is never gated: the gone frame registers and decides.
        gone, _ = self.idle("gone", wall_ms=base + 120000)
        self.now += 120
        self.reobserve()
        rows = {r["frame_id"]: r for r in self.reobs_rows()}
        self.assertEqual((rows[gone["frame_id"]]["result"], rows[gone["frame_id"]]["registered"], rows[gone["frame_id"]].get("gated", 0)), ("gone", 1, 0))

    def test_rebuild_all_and_as_of_replay_reobservation_effects_from_storage(self):
        placement, item = self.place_block()
        base = fx.rest_wall_ms(placement)
        gone, _ = self.idle("gone", wall_ms=base + 60000)
        self.now += 120
        self.reobserve()
        present, _ = self.idle("present", wall_ms=base + 120000)
        self.now += 120
        self.reobserve()
        current = self.store.get_item(item["item_id"])
        self.assertEqual((current["location_status"], current["observed_at_ms"]), ("placed", fx.idle_wall_ms(present)))
        # Replay from stored decisions: no model rerun, same projection.
        import sqlite3
        connection = sqlite3.connect(str(self.db))
        with connection:
            connection.execute("DELETE FROM current_items WHERE profile_id='local'")
        connection.close()
        result = self.store.rebuild_all()
        self.assertIs(result["model_rerun"], False)
        rebuilt = self.store.get_item(item["item_id"])
        for key in ("location_status", "location_text", "observed_at_ms", "stale_reason", "identity_status", "reference_image"):
            self.assertEqual(rebuilt[key], current[key], key)
        self.assertIsNone(rebuilt.get("stale_since_ms"))
        # as_of between the negative and the positive frame shows the stale state; before the negative frame, placed.
        between = self.store.get_item(item["item_id"], as_of=fx.idle_wall_ms(gone) + 1000)
        self.assertEqual((between["location_status"], between["stale_reason"], between["stale_since_ms"]), ("stale", "negative_reobservation", fx.idle_wall_ms(gone)))
        earlier = self.store.get_item(item["item_id"], as_of=fx.idle_wall_ms(gone) - 1)
        self.assertEqual((earlier["location_status"], earlier["stale_reason"], earlier["observed_at_ms"]), ("placed", None, base))
        self.assertEqual(self.store.answer_text(ASK, as_of=fx.idle_wall_ms(gone) + 1000)["shape"], "hedged")
        self.assertEqual(self.store.answer_text(ASK, as_of=fx.idle_wall_ms(gone) - 1)["shape"], "confident")


class EmbedderReobservationTests(IdleFixture):
    EMBEDDER = True

    def setUp(self):
        super().setUp()
        self.embedder = RemappingEmbedder()
        self.store = self.make_store()
        self.register_calibration()

    def place_tagged(self):
        packet = self.place([fx.observation(None, fx.TAGGED_BBOX, label=identity.GLASSES, location="fixture cp4 shelf",
                                            calibration=identity.cp3_calibration())], rest=fx.golden("tagged_reference"))
        item = self.item_by_name(identity.GLASSES)
        self.assertEqual(item["identity_status"], "trusted", item)
        self.assertEqual(item["location_status"], "placed", item)
        self.assertEqual(len(self.embedder.calls), 1)
        return packet, item

    def test_embedder_confirmed_present_keeps_identity_trusted(self):
        placement, item = self.place_tagged()
        base = fx.rest_wall_ms(placement)
        idle, _ = self.idle("tagged_present", wall_ms=base + 60000)
        self.now += 120
        self.reobserve()
        rows = self.reobs_rows()
        self.assertEqual([r["result"] for r in rows], ["present"], rows)
        self.assertEqual((rows[0]["registered"], rows[0]["embedded"]), (1, 1))
        self.assert_band("tagged_present", rows[0]["region_diff"])
        self.assertEqual(len(self.embedder.calls), 2, "the registered region was embedded once")
        self.assertEqual(self.embedder.calls[-1]["tag"], 0)
        evidence = self.evidence(item["item_id"])
        self.assertEqual(len(evidence), 2)
        newest = max(evidence, key=lambda r: r["observed_at_ms"])
        self.assertEqual(newest["identity_status"], "trusted", "embedder-confirmed: the sighting carries the item's identity state")
        self.assertEqual(newest["outcome"], "sighted")
        self.assertEqual(newest["reference_image"]["frame_id"], idle["frame_id"])
        after = self.store.get_item(item["item_id"])
        self.assertEqual((after["identity_status"], after["location_status"], after["observed_at_ms"]), ("trusted", "placed", fx.idle_wall_ms(idle)))
        self.assertEqual(self.store.answer_text(identity.ASK_GLASSES)["shape"], "confident")
        # The promoted frame now also seeds the bank: a later hand placement of tag 0 rematches.
        self.assertEqual({r["promoted"] for r in self.idle_rows()}, {1})

    def test_unmatched_embedding_withholds_present(self):
        placement, item = self.place_tagged()
        base = fx.rest_wall_ms(placement)
        self.embedder.remap = {0: 2}   # the same pixels now embed as a different object
        idle, _ = self.idle("tagged_present", wall_ms=base + 60000)
        self.now += 120
        self.reobserve()
        rows = self.reobs_rows()
        self.assertEqual(len(rows), 1, rows)
        self.assertNotEqual(rows[0]["result"], "present", "present requires the item in the matcher's set")
        self.assertEqual(rows[0]["result"], "unknown", "an unchanged region whose identity does not match is no decision")
        self.assertEqual((rows[0]["registered"], rows[0]["embedded"]), (1, 1))
        self.assertEqual(self.embedder.calls[-1]["tag"], 0)
        self.assertEqual(len(self.evidence(item["item_id"])), 1, "no sighting is written")
        self.assertEqual({r["promoted"] for r in self.idle_rows()}, {0}, "no promotion")
        unchanged = self.store.get_item(item["item_id"])
        self.assertEqual((unchanged["location_status"], unchanged["stale_reason"], unchanged["observed_at_ms"]), ("placed", None, base))
        # A changed region is 'gone' whatever the embedder says.
        self.embedder.remap = {}
        gone, _ = self.idle("tagged_gone", wall_ms=base + 120000)
        self.now += 120
        self.reobserve()
        rows = {r["frame_id"]: r for r in self.reobs_rows()}
        self.assertEqual(rows[gone["frame_id"]]["result"], "gone")
        self.assert_band("tagged_gone", rows[gone["frame_id"]]["region_diff"])
        self.assertEqual(self.store.get_item(item["item_id"])["stale_reason"], "negative_reobservation")

    def test_spent_compute_budget_defers_the_embedding_and_keeps_the_sighting_provisional(self):
        # Coordinator ruling 11: with REOBS_CPU_BUDGET_S patched to 0 the embed is
        # skipped (reobs_deferred), the decision stays diff-only and the sighting's
        # identity is provisional; the embedder is never asked for the idle region.
        import perception.reobservation as reobservation
        placement, item = self.place_tagged()
        base = fx.rest_wall_ms(placement)
        idle, _ = self.idle("tagged_present", wall_ms=base + 60000)
        self.now += 120
        with patch.object(reobservation, "REOBS_CPU_BUDGET_S", 0):
            counts = self.reobserve()
        self.assertGreaterEqual(counts.get("reobs_deferred", 0), 1, counts)
        self.assertEqual(counts.get("embedded"), 0, counts)
        rows = self.reobs_rows()
        self.assertEqual([(r["result"], r["registered"], r["embedded"]) for r in rows], [("present", 1, 0)], rows)
        self.assert_band("tagged_present", rows[0]["region_diff"])
        self.assertEqual(len(self.embedder.calls), 1, "no embed call for the deferred decision")
        newest = max(self.evidence(item["item_id"]), key=lambda r: r["observed_at_ms"])
        self.assertEqual(newest["identity_status"], "provisional", "diff-only: never upgraded")
        self.assertEqual(newest["outcome"], "sighted")
        self.assertEqual({r["promoted"] for r in self.idle_rows()}, {1}, "a diff-only present still promotes the first positive frame")
        self.assertEqual(self.store.get_item(item["item_id"])["identity_status"], "trusted")

    def test_without_an_approved_calibration_the_sighting_stays_provisional(self):
        # Embedder loaded but (on its own database) the only approved record belongs to
        # another embedder: nothing can be confirmed, so the diff-only rule applies and the
        # sighting is provisional while the item keeps its placement identity.
        from perception.object_memory import ObjectStore
        path = self.root / "no-calibration.sqlite3"
        store = ObjectStore(path, profile_id="local", clock=self.clock, embedder=RemappingEmbedder())
        store.acknowledge_consent(fx.CONSENT_VERSION, fx.ACTOR)
        store.register_calibration(identity.calibration_record("cp4-other-embedder", quantile=identity.WIDE_Q, embedder="other@9"))
        store.approve_calibration("cp4-other-embedder", identity.ACTOR)
        packet = self.place([fx.observation(None, fx.TAGGED_BBOX, label=identity.GLASSES, location="fixture cp4 shelf")], rest=fx.golden("tagged_reference"), store=store)
        item = self.item_by_name(identity.GLASSES, store)
        self.assertEqual(item["identity_status"], "trusted", "the CP2 fixture dict rule still trusts the placement")
        idle, _ = self.idle("tagged_present", wall_ms=fx.rest_wall_ms(packet) + 60000, store=store)
        self.now += 120
        counts = store.reobserve(self.now_ms())
        rows = fx.table_rows(path, "reobservations")
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual((rows[0]["result"], rows[0]["registered"], rows[0]["embedded"]), ("present", 1, 0), "no active calibration for this embedder: diff-only")
        newest = max(store.item_evidence(item["item_id"]), key=lambda r: r["observed_at_ms"])
        self.assertEqual(newest["outcome"], "sighted")
        self.assertEqual(newest["identity_status"], "provisional", "unconfirmed identity never upgrades the sighting")
        self.assertEqual(store.get_item(item["item_id"])["identity_status"], "trusted")
        self.assertEqual(store.get_item(item["item_id"])["observed_at_ms"], fx.idle_wall_ms(idle))


if __name__ == "__main__":
    unittest.main(verbosity=2)
