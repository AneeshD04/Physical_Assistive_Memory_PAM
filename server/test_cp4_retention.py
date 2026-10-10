"""CP4 acceptance, store level: retention windows, packet expiry, idle expiry and
landmark reduction.

    python3 -B server/test_cp4_retention.py -v

Authority: docs/BUILD_PLAN.md "CP4 in detail", *Retention and consent* (A, B):

  table retention(profile_id PRIMARY KEY, consent_version, episodes_days, idle_hours,
      landmarks_hours, updated_ms); defaults "rig-2026-10", 90, 24, 72
  ObjectStore.set_retention(**fields, actor) -> row (audited; ranges 7..365, 1..72, 1..168)
  ObjectStore.apply_retention(now_ms) -> counts:
    (a) revisions older than episodes_days: packet NULL, redacted_reason "retention";
        metadata, digests, observations and embeddings stay; the item is still
        listed with reference_image / image bytes gone;
    (b) idle expiry (the idle_hours window);
    (c) landmark reduction after landmarks_hours: the stored packet is rewritten
        with landmarks [] and a server-only landmark_summary [{frame_id, t_ms, hands:
        [{hand_bbox, busy, basis}]}], episode_revisions.reduced_ms set once, the
        digest columns untouched (duplicate detection uses the columns), the packet
        still parseable and item_image still served. parse_packet accepts
        landmark_summary; ingest_episode refuses a client packet carrying it.

The hands in the reduced packets come from server/fixtures/cp2/hand_goldens.json, so
busy/basis are checked against the golden's expected values, not re-derived.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
import test_memory_bootstrap as bootstrap  # noqa: E402
import test_cp3_identity as identity  # noqa: E402
import test_cp4_fixtures as fx  # noqa: E402

ANCHOR_MS = fx.ANCHOR_MS
HOUR_MS, DAY_MS = fx.HOUR_MS, fx.DAY_MS
HAND_GOLDENS = ROOT / "server" / "fixtures" / "cp2" / "hand_goldens.json"
LABEL, LOCATION = "synthetic cp4 block", "fixture cp4 table"
AUTO_LABEL = "synthetic cp4 automatic block"
# A coordinate that only raw landmarks carry (hand bboxes are 0.3/0.56/0.6/0.8 ...).
RAW_MARK = "0.4321"
SUMMARY_HAND_FIELDS = {"hand_bbox", "busy", "basis"}


def golden_hands():
    data = json.loads(HAND_GOLDENS.read_text(encoding="utf-8"))
    return {case["name"]: case for case in data["cases"]}


def landmark_samples(serial, offset=0):
    """Three samples: a busy lower-frame hand, a curled hand, an open hand (one hand each,
    so per-hand and per-sample busy readings coincide), at offset + 1300/1600/1900 ms.
    Returns (samples, expected [{frame_id, t_ms, hands: [{hand_bbox, busy, basis}]}])."""
    cases = golden_hands()
    chosen = [("open_hand_lower_frame", offset + 1300), ("fist_high", offset + 1600), ("open_hand_high", offset + 1900)]
    samples, expected = [], []
    for index, (name, t_ms) in enumerate(chosen):
        hand = json.loads(json.dumps(cases[name]["hands"][0]))
        hand["landmarks"][0]["x"] = float(RAW_MARK) if index == 0 else hand["landmarks"][0]["x"]
        hand["world_landmarks"] = [{"x": 0.01 * i, "y": -0.02, "z": 0.003} for i in range(21)]
        frame_id = f"lm-{serial}-{index}"
        samples.append({"frame_id": frame_id, "t_ms": t_ms, "hands": [hand]})
        expected.append({"frame_id": frame_id, "t_ms": t_ms,
                         "hands": [{"hand_bbox": list(hand["hand_bbox"]), "busy": cases[name]["expected"]["busy"], "basis": cases[name]["expected"]["basis"]}]})
    return samples, expected


class RetentionFixture(fx.Cp4Fixture):
    def place_block(self, label=LABEL, **kwargs):
        packet = self.place([fx.observation(None, fx.BLOCK_BBOX, label=label, location=LOCATION)], **kwargs)
        return packet, self.item_by_name(label)

    def revision(self, packet):
        rows = self.rows("episode_revisions", "WHERE profile_id='local' AND episode_id=?", (packet["episode_id"],))
        self.assertEqual(len(rows), 1, rows)
        return rows[0]

    def set_retention(self, **fields):
        return self.store.set_retention(actor=fx.ACTOR, **fields)

    def apply(self, now_ms):
        counts = self.store.apply_retention(now_ms)
        self.assertIsInstance(counts, dict, counts)
        self.assertTrue(all(isinstance(v, int) and not isinstance(v, bool) for v in counts.values()), counts)
        return counts


class RetentionSettingsTests(RetentionFixture):
    def test_defaults_and_table(self):
        self.assertTrue(fx.table_exists(self.db, "retention"), "retention table")
        self.assertTrue(fx.RETENTION_FIELDS | {"profile_id"} <= set(fx.columns(self.db, "retention")), fx.columns(self.db, "retention"))
        row = fx.read_retention(self.store)
        self.assertIsNotNone(row, "the profile's retention row (or defaults) must be readable")
        self.assertEqual(row["consent_version"], fx.PLAN["CONSENT_VERSION"])
        self.assertEqual((row["episodes_days"], row["idle_hours"], row["landmarks_hours"]), (30, 24, 72), "coordinator ruling 8: 30-day default")
        self.assertIsInstance(row["updated_ms"], (int, type(None)))
        from perception import episode_store
        self.assertEqual(episode_store.RETENTION_DEFAULTS, {"episodes_days": 30, "idle_hours": 24, "landmarks_hours": 72})
        other = self.make_store(profile="other-profile")
        self.assertEqual(fx.read_retention(other)["episodes_days"], 30)

    def test_set_retention_updates_within_ranges_with_an_audit_row(self):
        before = len(self.audit())
        self.now += 5
        result = self.set_retention(episodes_days=60)
        self.assertIsInstance(result, dict, result)
        self.assertEqual(result["episodes_days"], 60)
        self.assertEqual(result["updated_ms"], self.now_ms())
        row = fx.read_retention(self.store)
        self.assertEqual((row["episodes_days"], row["idle_hours"], row["landmarks_hours"], row["consent_version"]), (60, 24, 72, fx.PLAN["CONSENT_VERSION"]))
        audits = self.audit()[before:]
        self.assertEqual(len(audits), 1, audits)
        self.assertIn("retention", audits[0]["action"])
        detail = json.loads(audits[0]["detail"])
        self.assertEqual(detail.get("actor"), fx.ACTOR)
        self.assertIn("episodes_days", json.dumps(detail))
        # Every window at both ends of its range; consent_version is a build constant
        # (coordinator ruling 3) and is refused as a setting.
        self.set_retention(episodes_days=7, idle_hours=1, landmarks_hours=1)
        self.set_retention(episodes_days=365, idle_hours=72, landmarks_hours=168)
        row = fx.read_retention(self.store)
        self.assertEqual((row["episodes_days"], row["idle_hours"], row["landmarks_hours"], row["consent_version"]), (365, 72, 168, fx.PLAN["CONSENT_VERSION"]))
        with self.assertRaises((ValueError, TypeError)):
            self.set_retention(consent_version="rig-2026-11")
        self.assertEqual(fx.read_retention(self.store)["consent_version"], fx.PLAN["CONSENT_VERSION"])
        other = self.make_store(profile="other-profile")
        self.assertEqual(fx.read_retention(other)["episodes_days"], 30, "settings are per profile")
        # A fresh store instance reads the stored row.
        self.assertEqual(fx.read_retention(self.make_store())["episodes_days"], 365)

    def test_out_of_range_or_malformed_settings_are_refused_unchanged(self):
        self.set_retention(episodes_days=60)
        snapshot = fx.read_retention(self.store)
        audits = len(self.audit())
        bad = [dict(episodes_days=6), dict(episodes_days=366), dict(idle_hours=0), dict(idle_hours=73),
               dict(landmarks_hours=0), dict(landmarks_hours=169), dict(episodes_days=True), dict(episodes_days=30.0),
               dict(episodes_days="30"), dict(idle_hours=None), dict(consent_version=""), dict(consent_version="rig-2026-11"),
               dict(consent_version=7), dict(unknown_window=5), dict(profile_id="other"), dict(), dict(acknowledged_version="rig-2026-10"),
               dict(erased_at_ms=0)]
        for fields in bad:
            with self.subTest(fields=fields), self.assertRaises((ValueError, TypeError)):
                self.set_retention(**fields)
        for actor in ("Dr Smith", "", None, "admin", 7):
            with self.subTest(actor=actor), self.assertRaises((ValueError, TypeError)):
                self.store.set_retention(episodes_days=40, actor=actor)
        self.assertEqual(fx.read_retention(self.store), snapshot, "a refused update changes nothing")
        self.assertEqual(len(self.audit()), audits, "a refused update is not audited as a change")


class ApplyRetentionTests(RetentionFixture):
    def test_packets_expire_after_episodes_days_but_the_item_and_its_decisions_stay(self):
        packet, item = self.place_block()
        received = self.revision(packet)["received_at_ms"]
        self.assertEqual(received, self.now_ms())
        digests = (self.revision(packet)["semantic_digest"], self.revision(packet)["transport_digest"])
        history_before = self.store.item_history(item["item_id"])
        self.assertEqual(self.store.item_image(item["item_id"]), fx.golden_bytes("reference"))
        self.apply(received + 29 * DAY_MS)
        row = self.revision(packet)
        self.assertIsNotNone(row["packet"], "29 days: inside the 30-day default window")
        self.assertIsNone(row.get("redacted_reason"))
        self.assertIs(self.item_by_name(LABEL).get("evidence_expired", False), False)
        counts = self.apply(received + 31 * DAY_MS)
        self.assertGreaterEqual(counts.get("revisions_expired", 0), 1, counts)
        row = self.revision(packet)
        self.assertIsNone(row["packet"], "the packet bytes are replaced by NULL")
        self.assertEqual(row["redacted_reason"], "retention")
        self.assertEqual((row["semantic_digest"], row["transport_digest"]), digests, "digest columns stay")
        self.assertEqual(row["received_at_ms"], received)
        # The item is still listed with its decisions; only the evidence image is gone.
        listed = self.item_by_name(LABEL)
        self.assertEqual(listed["item_id"], item["item_id"])
        self.assertEqual(listed["location_text"], LOCATION)
        self.assertEqual(listed["observed_at_ms"], item["observed_at_ms"])
        self.assertIsNone(listed["reference_image"], "no evidence image: reference_image is null")
        self.assertIs(listed.get("evidence_expired"), True, "the item carries the 'evidence image expired' marker")
        self.assertIsNone(self.store.item_image(item["item_id"]))
        evidence = self.store.item_evidence(item["item_id"])
        self.assertEqual(len(evidence), 1)
        self.assertIsNone(self.store.observation_image(item["item_id"], evidence[0]["observation_id"]))
        self.assertEqual(self.store.item_history(item["item_id"]), history_before, "observations stay")
        self.assertEqual(len(self.rows("local_observations", "WHERE profile_id='local' AND record IS NOT NULL")), 1)
        # Not an erasure: the episode is not tombstoned, a duplicate resend is still a duplicate.
        self.assertEqual(self.rows("episode_tombstones"), [])
        ack = self.store.ingest_episode(bootstrap.encode_packet(packet))
        self.assertEqual((ack["status"], ack["retained"]), ("duplicate", True), ack)
        # Idempotent: a second pass expires nothing more and changes nothing.
        again = self.apply(received + 32 * DAY_MS)
        self.assertEqual(again.get("revisions_expired", 0), 0, again)
        self.assertEqual(self.revision(packet)["redacted_reason"], "retention")
        # A shorter window set later applies to the next pass.
        newer, newer_item = self.place_block(label=LABEL + " newer")
        self.set_retention(episodes_days=7)
        self.apply(self.revision(newer)["received_at_ms"] + 8 * DAY_MS)
        self.assertIsNone(self.revision(newer)["packet"])
        self.assertEqual(self.revision(newer)["redacted_reason"], "retention")

    def test_superseded_revisions_lose_their_bytes_after_72_hours_but_the_item_image_survives(self):
        # Coordinator ruling 12: an accepted revision superseded by a newer accepted one
        # keeps its packet 72 h, then packet NULL with redacted_reason 'superseded';
        # the item image is still served from the newer accepted revision.
        packet, item = self.place_block()
        revision = copy.deepcopy(packet)
        revision["gaps"] = [{"t_from_ms": packet["t_start_ms"] + 100, "t_to_ms": packet["t_start_ms"] + 150, "reason": "synthetic later gap"}]
        ack = self.store.ingest_episode(bootstrap.encode_packet(revision))
        self.assertEqual((ack["status"], ack["revision_no"], ack["retained"]), ("revised", 2, True), ack)
        self.scripted.observations[revision["episode_id"]] = self.scripted.observations[packet["episode_id"]]
        self.process()
        rows = self.rows("episode_revisions", "WHERE episode_id=? ORDER BY revision_no", (packet["episode_id"],))
        self.assertEqual([r["revision_no"] for r in rows], [1, 2])
        self.assertEqual([r["accepted"] for r in rows], [1, 1])
        received = rows[0]["received_at_ms"]
        self.assertEqual(self.store.item_image(item["item_id"]), fx.golden_bytes("reference"))
        self.apply(received + 71 * HOUR_MS)
        rows = self.rows("episode_revisions", "WHERE episode_id=? ORDER BY revision_no", (packet["episode_id"],))
        self.assertIsNotNone(rows[0]["packet"], "71 h: the superseded revision keeps its bytes")
        counts = self.apply(received + 73 * HOUR_MS)
        self.assertGreaterEqual(counts.get("revisions_superseded", 0), 1, counts)
        rows = self.rows("episode_revisions", "WHERE episode_id=? ORDER BY revision_no", (packet["episode_id"],))
        self.assertIsNone(rows[0]["packet"], "73 h: the superseded revision's bytes are released")
        self.assertEqual(rows[0]["redacted_reason"], "superseded")
        self.assertIsNotNone(rows[1]["packet"], "the newest accepted revision keeps its bytes")
        self.assertIsNone(rows[1]["redacted_reason"])
        listed = self.item_by_name(LABEL)
        self.assertIsNotNone(listed["reference_image"])
        self.assertIs(listed.get("evidence_expired", False), False, "a superseded revision is not an expired item")
        self.assertEqual(self.store.item_image(item["item_id"]), fx.golden_bytes("reference"), "served from the newer accepted revision")
        for row in self.store.item_evidence(item["item_id"]):
            self.assertEqual(self.store.observation_image(item["item_id"], row["observation_id"]), fx.golden_bytes("reference"))
        # Nothing else changed: digests and the duplicate rule still hold.
        self.assertEqual(self.store.ingest_episode(bootstrap.encode_packet(revision))["status"], "duplicate")

    def test_packet_expiry_with_an_embedder_keeps_embeddings_and_banks(self):
        store = self.make_store(embedder=identity.SyntheticEmbedder())
        self.register_calibration(store=store)
        packet = self.place([fx.observation(None, fx.TAGGED_BBOX, label=identity.GLASSES, location="fixture cp4 shelf",
                                            calibration=identity.cp3_calibration())], rest=fx.golden("tagged_reference"), store=store)
        item = self.item_by_name(identity.GLASSES, store)
        self.assertEqual(len(self.rows("embeddings")), 1)
        store.apply_retention(self.revision(packet)["received_at_ms"] + 31 * DAY_MS)
        self.assertIsNone(self.revision(packet)["packet"])
        self.assertEqual(len(self.rows("embeddings")), 1, "embeddings stay")
        self.assertEqual(store.item_evidence(item["item_id"])[0]["embedded"], True)
        # The bank still matches a later sighting of the same tag (no image needed for that).
        self.place([fx.observation(None, fx.TAGGED_BBOX, label=identity.GLASSES, location="fixture cp4 desk",
                                   calibration=identity.cp3_calibration())], rest=fx.golden("tagged_reference"), store=store)
        self.assertEqual(len(store.item_evidence(item["item_id"])), 2, "the expired placement still anchors the item's identity")

    def test_idle_expiry_follows_the_idle_hours_window(self):
        placement, item = self.place_block()
        base = fx.rest_wall_ms(placement)
        received = self.now_ms()
        unpromoted, _ = self.idle("gone", wall_ms=base + 1000)
        promoted, _ = self.idle("present", wall_ms=base + 2000)
        self.now += 120
        self.reobserve()
        rows = {r["frame_id"]: r["promoted"] for r in self.rows("idle_frames")}
        self.assertEqual(rows, {unpromoted["frame_id"]: 0, promoted["frame_id"]: 1}, rows)
        self.apply(received + 23 * HOUR_MS)
        self.assertEqual(set(r["frame_id"] for r in self.rows("idle_frames")), {unpromoted["frame_id"], promoted["frame_id"]}, "23 h: inside the default window")
        self.apply(received + 25 * HOUR_MS)
        self.assertEqual([r["frame_id"] for r in self.rows("idle_frames")], [promoted["frame_id"]], "25 h: the unpromoted frame is gone, the promoted one stays")
        # A two-hour window applies to frames cached afterwards.
        self.set_retention(idle_hours=2)
        self.now += 26 * 3600
        short, ack = self.idle("gone", wall_ms=self.now_ms() - 1000)
        self.assertLessEqual(ack["expires_at_ms"], self.now_ms() + 2 * HOUR_MS, "expires_at_ms follows the configured idle window")
        self.apply(self.now_ms() + HOUR_MS)
        self.assertIn(short["frame_id"], {r["frame_id"] for r in self.rows("idle_frames")})
        self.apply(self.now_ms() + 3 * HOUR_MS)
        self.assertNotIn(short["frame_id"], {r["frame_id"] for r in self.rows("idle_frames")})
        self.assertIn(promoted["frame_id"], {r["frame_id"] for r in self.rows("idle_frames")})


class LandmarkReductionTests(RetentionFixture):
    def place_with_landmarks(self):
        offset = self.phase * 10000
        samples, expected = landmark_samples(self.serial_ids + 1, offset)
        gaps = [{"t_from_ms": offset + 1100, "t_to_ms": offset + 1150, "reason": "synthetic gap"}]
        packet = self.place([fx.observation(None, fx.BLOCK_BBOX, label=AUTO_LABEL, location=LOCATION)], landmarks=samples, gaps=gaps, capture_mode="automatic")
        return packet, self.item_by_name(AUTO_LABEL), expected

    def test_reduction_after_landmarks_hours_keeps_packets_parseable_images_served_and_digests_stable(self):
        from perception.episode import parse_packet
        packet, item, expected_summary = self.place_with_landmarks()
        row = self.revision(packet)
        received = row["received_at_ms"]
        digests = (row["semantic_digest"], row["transport_digest"])
        original = bytes(row["packet"])
        self.assertIn(RAW_MARK.encode(), original, "the fixture's raw landmark coordinate is in the stored packet")
        self.assertIn(b"world_landmarks", original)
        self.assertIsNone(row.get("reduced_ms"))
        self.apply(received + 71 * HOUR_MS)
        row = self.revision(packet)
        self.assertEqual(bytes(row["packet"]), original, "71 h: not reduced")
        self.assertIsNone(row["reduced_ms"])
        counts = self.apply(received + 73 * HOUR_MS)
        self.assertGreaterEqual(counts.get("landmarks_reduced", 0), 1, counts)
        row = self.revision(packet)
        self.assertEqual(row["reduced_ms"], received + 73 * HOUR_MS, "reduced_ms records the apply time")
        self.assertEqual((row["semantic_digest"], row["transport_digest"]), digests, "digest columns are never re-hashed")
        self.assertIsNone(row.get("redacted_reason"))
        reduced = bytes(row["packet"])
        self.assertNotEqual(reduced, original)
        self.assertNotIn(RAW_MARK.encode(), reduced, "no raw landmark coordinate survives")
        self.assertNotIn(b"world_landmarks", reduced)
        parsed = parse_packet(reduced)
        self.assertEqual(parsed.landmarks, [])
        self.assertEqual(len(parsed.keyframes), 2)
        self.assertEqual(len(parsed.gaps), 1)
        self.assertEqual(parsed.capture_mode, "automatic")
        summary = json.loads(reduced)["landmark_summary"]
        self.assertEqual(len(summary), len(expected_summary))
        for got, want in zip(summary, expected_summary):
            self.assertEqual(set(got), {"frame_id", "t_ms", "hands"}, got)
            self.assertEqual((got["frame_id"], got["t_ms"]), (want["frame_id"], want["t_ms"]))
            self.assertEqual(len(got["hands"]), 1)
            self.assertEqual(set(got["hands"][0]), SUMMARY_HAND_FIELDS, got["hands"][0])
            self.assertEqual(got["hands"][0], want["hands"][0])
        model_summary = getattr(parsed, "landmark_summary", None)
        self.assertIsNotNone(model_summary, "parse_packet exposes landmark_summary")
        self.assertEqual(len(model_summary), len(expected_summary))
        # Evidence and images are untouched.
        self.assertEqual(self.store.item_image(item["item_id"]), fx.golden_bytes("reference"))
        evidence = self.store.item_evidence(item["item_id"])
        self.assertEqual(len(evidence), 1)
        self.assertEqual(self.store.observation_image(item["item_id"], evidence[0]["observation_id"]), fx.golden_bytes("reference"))
        self.assertEqual(self.item_by_name(AUTO_LABEL)["reference_image"], item["reference_image"])
        # Duplicate detection uses the stored columns: the original client packet is a duplicate.
        ack = self.store.ingest_episode(bootstrap.encode_packet(packet))
        self.assertEqual((ack["status"], ack["retained"], ack["revision_no"]), ("duplicate", True, 1), ack)
        self.assertEqual(len(self.rows("episode_revisions", "WHERE episode_id=?", (packet["episode_id"],))), 1)
        # Set once: a later pass leaves reduced_ms and the bytes alone.
        self.apply(received + 100 * HOUR_MS)
        row = self.revision(packet)
        self.assertEqual(row["reduced_ms"], received + 73 * HOUR_MS)
        self.assertEqual(bytes(row["packet"]), reduced)
        # Processing is unaffected afterwards: rebuild replays the same projection.
        before = self.items()
        self.store.rebuild_all()
        self.assertEqual(self.items(), before)

    def test_reduction_respects_the_configured_window_and_packets_without_landmarks(self):
        plain, plain_item = self.place_block()
        packet, item, _ = self.place_with_landmarks()
        self.set_retention(landmarks_hours=1)
        received = self.revision(packet)["received_at_ms"]
        self.apply(received + 2 * HOUR_MS)
        self.assertIsNotNone(self.revision(packet)["reduced_ms"], "a one-hour window reduces after two hours")
        self.assertEqual(json.loads(bytes(self.revision(packet)["packet"]))["landmarks"], [])
        plain_row = self.revision(plain)
        self.assertEqual(json.loads(bytes(plain_row["packet"])).get("landmarks"), [], "a packet without landmarks is left as it was")
        self.assertNotIn("landmark_summary", json.loads(bytes(plain_row["packet"])), "nothing to summarise, nothing added")
        # The reduced packet is still ingest-refused as a CLIENT packet (landmark_summary is server-only).
        with self.assertRaises(ValueError):
            self.store.ingest_episode(bytes(self.revision(packet)["packet"]))

    def test_client_packets_may_not_carry_landmark_summary_but_parse_packet_accepts_it(self):
        from perception.episode import parse_packet
        samples, expected = landmark_samples(99)
        packet = self.next_packet(rest=fx.golden("reference"), landmarks=samples)
        for value in ([], expected):
            with self.subTest(landmark_summary=value):
                with self.assertRaises(ValueError):
                    self.store.ingest_episode(bootstrap.encode_packet({**packet, "landmark_summary": value}))
        self.assertEqual(self.rows("episode_revisions"), [], "a refused packet leaves no revision")
        # The server-side reduced shape parses, with landmark_summary bounded like landmarks.
        reduced = {**packet, "landmarks": [], "landmark_summary": expected}
        parsed = parse_packet(bootstrap.encode_packet(reduced))
        self.assertEqual(parsed.landmarks, [])
        self.assertEqual(len(parsed.landmark_summary), 3)
        too_many = {**reduced, "landmark_summary": [dict(expected[0], frame_id=f"lm-{i}", t_ms=1100 + i) for i in range(129)]}
        with self.assertRaises(ValueError):
            parse_packet(bootstrap.encode_packet(too_many))
        three_hands = {**reduced, "landmark_summary": [dict(expected[0], hands=expected[0]["hands"] * 3)]}
        with self.assertRaises(ValueError):
            parse_packet(bootstrap.encode_packet(three_hands))
        raw_in_summary = {**reduced, "landmark_summary": [dict(expected[0], hands=[dict(expected[0]["hands"][0], landmarks=samples[0]["hands"][0]["landmarks"])])]}
        with self.assertRaises(ValueError):
            parse_packet(bootstrap.encode_packet(raw_in_summary))


if __name__ == "__main__":
    unittest.main(verbosity=2)
