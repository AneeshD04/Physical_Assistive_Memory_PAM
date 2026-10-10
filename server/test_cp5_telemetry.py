"""CP5 acceptance, store level: frame accounting (telemetry ingest, storage, coverage,
expiry).

    python3 -B server/test_cp5_telemetry.py -v

Authority: docs/BUILD_PLAN.md "CP5 in detail", *Frame accounting (C -> B -> A)*:

  ObjectStore.ingest_telemetry(raw: bytes) -> ack      strict closed key sets, integer /
      finite-float bounds, no free text, no vectors; PacketTooLarge (a ValueError) over
      MAX_TELEMETRY_BYTES (64 KiB); ValueError for anything malformed
  ObjectStore.coverage(day_utc: "YYYY-MM-DD") -> {camera_on_ms, gap_ms, episodes, packets,
      idle_sent, idle_dropped, sessions} (a superset is tolerated; ValueError for a bad day)
  table frame_counters(profile_id, device_id, session_id, t_ms, received_ms, window_ms,
      counters JSON, timing JSON, settings JSON)
  retention: telemetry rows expire with episodes_days (apply_retention)

Coverage arithmetic assumes per-window deltas (each post reports the counts of the
window_ms it covers; camera_on_ms is the sum of window_ms), summed over every post
whose wall time (clock_anchor.wall_ms + t_ms - mono_ms) falls in the UTC day; sessions
counts distinct session ids. Nothing here is a measurement of a browser.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
import test_cp4_fixtures as fx  # noqa: E402
import test_cp5_fixtures as cp5  # noqa: E402
from test_cp5_fixtures import (ANCHOR_MS, COUNTER_KEYS, COVERAGE_KEYS, DAY_MS, HOUR_MS, OTHER_SESSION, SETTINGS_KEYS,  # noqa: E402
                               TELEMETRY_TOP, TIMING_KEYS, encode, expected_coverage, packet_for_day, telemetry_packet,
                               telemetry_wall_ms, utc_day)

TODAY = utc_day(ANCHOR_MS)                 # the fixture clock's UTC day (2026-09-21)
YESTERDAY = utc_day(ANCHOR_MS - DAY_MS)
TWO_DAYS_AGO = utc_day(ANCHOR_MS - 2 * DAY_MS)
ZERO = {key: 0 for key in COVERAGE_KEYS}


def packet_too_large():
    from perception.episode import PacketTooLarge
    return PacketTooLarge


class TelemetryFixture(cp5.Cp5Fixture):
    def ingest_telemetry(self, packet, store=None, raw=None):
        store = self.store if store is None else store
        return store.ingest_telemetry(encode(packet) if raw is None else raw)

    def rows(self, table="frame_counters", where="WHERE profile_id='local' ORDER BY received_ms, session_id, t_ms", params=()):
        return fx.table_rows(self.db, table, where, params)

    def coverage(self, day, store=None):
        value = (self.store if store is None else store).coverage(day)
        self.assertIsInstance(value, dict, value)
        self.assertTrue(COVERAGE_KEYS <= set(value), sorted(COVERAGE_KEYS - set(value)))
        for key in COVERAGE_KEYS:
            self.assertIsInstance(value[key], int, key)
            self.assertNotIsInstance(value[key], bool, key)
            self.assertGreaterEqual(value[key], 0, key)
        return {key: value[key] for key in COVERAGE_KEYS}

    def assert_refused(self, packet=None, *, raw=None, what=""):
        with self.assertRaises(ValueError, msg=what):
            self.ingest_telemetry(packet, raw=raw)


class IngestTests(TelemetryFixture):
    def test_constant_and_table(self):
        self.assertEqual(fx.constant("MAX_TELEMETRY_BYTES"), cp5.MAX_TELEMETRY_BYTES)
        self.assertTrue(fx.table_exists(self.db, "frame_counters"), "frame_counters table")
        self.assertTrue(cp5.FRAME_COUNTER_COLUMNS <= set(fx.columns(self.db, "frame_counters")), fx.columns(self.db, "frame_counters"))

    def test_valid_window_is_stored_as_json_columns_without_free_text(self):
        packet = telemetry_packet()
        ack = self.ingest_telemetry(packet)
        self.assertIsInstance(ack, dict, ack)
        self.assertNotIn("counters", ack, "the ack never echoes the body")
        rows = self.rows()
        self.assertEqual(len(rows), 1, rows)
        row = rows[0]
        self.assertEqual((row["profile_id"], row["device_id"], row["session_id"]), ("local", packet["device_id"], packet["session_id"]))
        self.assertEqual(row["received_ms"], self.now_ms())
        self.assertEqual(row["window_ms"], packet["window_ms"])
        self.assertIn(row["t_ms"], (packet["t_ms"], telemetry_wall_ms(packet)), "t_ms is the window's monotonic end or its wall time")
        counters, timing, settings = (json.loads(row[name]) for name in ("counters", "timing", "settings"))
        self.assertEqual(counters, packet["counters"])
        self.assertEqual(timing, packet["timing"])
        self.assertEqual(settings, packet["settings"])
        for column in ("counters", "timing", "settings"):
            values = json.loads(row[column])
            self.assertTrue(all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values.values()), values)
        # Idempotent: the same window twice is stored once.
        self.ingest_telemetry(packet)
        self.assertEqual(len(self.rows()), 1, "a resend of the same (device, session, t_ms) window is stored once")
        # Another profile sees nothing.
        other = self.make_store(profile="other-profile")
        self.assertEqual(self.rows(where="WHERE profile_id='other-profile'"), [])
        self.assertEqual(self.coverage(TODAY, other), ZERO)

    def test_closed_key_sets_and_bounds_are_enforced(self):
        good = telemetry_packet()
        cases = {}
        for key in TELEMETRY_TOP:
            cases[f"missing {key}"] = {k: v for k, v in good.items() if k != key}
        cases["extra top-level key"] = {**good, "profile_id": "other"}
        cases["free text at top level"] = {**good, "note": "wearer was in the kitchen"}
        cases["schema_version 2"] = {**good, "schema_version": 2}
        cases["schema_version string"] = {**good, "schema_version": "1"}
        cases["device not a uuid"] = {**good, "device_id": "device-1"}
        cases["session not a uuid"] = {**good, "session_id": "session-1"}
        cases["device free text"] = {**good, "device_id": "Mary's phone"}
        cases["t_ms negative"] = {**good, "t_ms": -1}
        cases["t_ms float"] = {**good, "t_ms": 1.5}
        cases["t_ms bool"] = {**good, "t_ms": True}
        cases["clock anchor extra"] = {**good, "clock_anchor": {**good["clock_anchor"], "tz": "UTC"}}
        cases["clock anchor missing wall"] = {**good, "clock_anchor": {"mono_ms": 0}}
        cases["window zero"] = {**good, "window_ms": 0}
        cases["window negative"] = {**good, "window_ms": -60000}
        cases["window over a day"] = {**good, "window_ms": DAY_MS + 1}
        cases["window float"] = {**good, "window_ms": 60000.5}
        for key in COUNTER_KEYS:
            cases[f"counters missing {key}"] = {**good, "counters": {k: v for k, v in good["counters"].items() if k != key}}
        cases["counters extra key"] = {**good, "counters": {**good["counters"], "frames_lost": 1}}
        cases["counters free text"] = {**good, "counters": {**good["counters"], "frames_captured": "many"}}
        cases["counters negative"] = {**good, "counters": {**good["counters"], "frames_captured": -1}}
        cases["counters float"] = {**good, "counters": {**good["counters"], "frames_captured": 1.5}}
        cases["counters bool"] = {**good, "counters": {**good["counters"], "gaps": True}}
        cases["counters vector"] = {**good, "counters": {**good["counters"], "bytes_sent": [1, 2, 3]}}
        cases["counters nested"] = {**good, "counters": {**good["counters"], "gap_ms": {"total": 5}}}
        cases["counters huge"] = {**good, "counters": {**good["counters"], "bytes_sent": 2 ** 53 + 1}}
        cases["counters not an object"] = {**good, "counters": [1, 2, 3]}
        for key in TIMING_KEYS:
            cases[f"timing missing {key}"] = {**good, "timing": {k: v for k, v in good["timing"].items() if k != key}}
        cases["timing extra key"] = {**good, "timing": {**good["timing"], "infer_ms_max": 50.0}}
        cases["timing negative"] = {**good, "timing": {**good["timing"], "fps_observed": -1.0}}
        cases["timing text"] = {**good, "timing": {**good["timing"], "fps_observed": "fast"}}
        cases["timing bool"] = {**good, "timing": {**good["timing"], "fps_observed": False}}
        cases["timing vector"] = {**good, "timing": {**good["timing"], "infer_ms_p50": [20.0] * 40}}
        cases["timing absurd fps"] = {**good, "timing": {**good["timing"], "fps_observed": 100000.0}}
        for key in SETTINGS_KEYS:
            cases[f"settings missing {key}"] = {**good, "settings": {k: v for k, v in good["settings"].items() if k != key}}
        cases["settings extra key"] = {**good, "settings": {**good["settings"], "label": "rear camera"}}
        cases["settings width zero"] = {**good, "settings": {**good["settings"], "width": 0}}
        cases["settings width absurd"] = {**good, "settings": {**good["settings"], "width": 100000}}
        cases["settings frame_rate negative"] = {**good, "settings": {**good["settings"], "frame_rate": -30}}
        cases["settings text"] = {**good, "settings": {**good["settings"], "frame_rate": "30"}}
        for name, bad in cases.items():
            with self.subTest(case=name):
                self.assert_refused(bad, what=name)
        for name, raw in {"not json": b"{", "a list": b"[]", "a string": b'"telemetry"', "empty": b"",
                          "duplicate key": b'{"schema_version":1,"schema_version":1}',
                          "nan": encode(good).replace(b"9.8", b"NaN"), "infinity": encode(good).replace(b"9.8", b"Infinity")}.items():
            with self.subTest(case=name):
                self.assert_refused(raw=raw, what=name)
        self.assertEqual(self.rows(), [], "nothing is stored for a refused window")
        # Still accepted: zero counters, integer-valued timing, a one-second window.
        self.ingest_telemetry(telemetry_packet(t_ms=1000, window_ms=1000, counters={k: 0 for k in COUNTER_KEYS}, timing={k: 0 for k in TIMING_KEYS}))
        self.assertEqual(len(self.rows()), 1)

    def test_byte_cap_is_64_kib(self):
        raw = encode(telemetry_packet())
        over = raw + b" " * (cp5.MAX_TELEMETRY_BYTES + 1 - len(raw))
        with self.assertRaises(packet_too_large()):
            self.ingest_telemetry(None, raw=over)
        self.assertEqual(self.rows(), [])
        within = raw + b" " * (cp5.MAX_TELEMETRY_BYTES - len(raw))
        self.assertEqual(len(within), cp5.MAX_TELEMETRY_BYTES)
        self.ingest_telemetry(None, raw=within)
        self.assertEqual(len(self.rows()), 1, "a body at the cap is accepted")

    def test_future_dated_window_is_refused(self):
        far_future = telemetry_packet(wall_ms=self.now_ms() + DAY_MS)
        self.assert_refused(far_future, what="a window dated a day in the future")
        self.assertEqual(self.rows(), [])


class CoverageTests(TelemetryFixture):
    def test_bad_day_is_refused(self):
        for day in ("2026-13-01", "2026-10-1", "20261001", "", "2026-10-01T00", "2026-02-30", "yesterday", "2026-10-01 ", None, 20261001):
            with self.subTest(day=day), self.assertRaises((ValueError, TypeError)):
                self.store.coverage(day)

    def test_empty_day_reads_zero(self):
        self.assertEqual(self.coverage(TODAY), ZERO)
        self.assertEqual(self.coverage(YESTERDAY), ZERO)

    def test_coverage_sums_windows_across_two_sessions_and_reports_gaps(self):
        first = packet_for_day(YESTERDAY, offset_ms=9 * HOUR_MS, session=cp5.SESSION, window_ms=60000,
                               counters={"gaps": 1, "gap_ms": 1500, "episodes_finished": 1, "packets_sent": 1, "idle_sent": 2, "idle_dropped": 1})
        second = packet_for_day(YESTERDAY, offset_ms=9 * HOUR_MS + 60000, session=cp5.SESSION, window_ms=60000,
                                counters={"gaps": 0, "gap_ms": 0, "episodes_finished": 0, "packets_sent": 0, "idle_sent": 2, "idle_dropped": 0})
        stopped = packet_for_day(YESTERDAY, offset_ms=9 * HOUR_MS + 90000, session=cp5.SESSION, window_ms=30000,
                                 counters={"gaps": 2, "gap_ms": 20000, "episodes_finished": 1, "packets_sent": 1, "idle_sent": 0, "idle_dropped": 0})
        other = packet_for_day(YESTERDAY, offset_ms=18 * HOUR_MS, session=OTHER_SESSION, window_ms=60000,
                               counters={"gaps": 0, "gap_ms": 0, "episodes_finished": 3, "packets_sent": 3, "idle_sent": 1, "idle_dropped": 2})
        today = packet_for_day(TODAY, offset_ms=HOUR_MS, session=OTHER_SESSION, window_ms=60000, counters={"episodes_finished": 5, "packets_sent": 5})
        packets = [first, second, stopped, other, today]
        for packet in packets:
            self.ingest_telemetry(packet)
        self.assertEqual(len(self.rows()), 5)
        expected = expected_coverage(packets, YESTERDAY)
        self.assertEqual(expected, {"camera_on_ms": 210000, "gap_ms": 21500, "episodes": 5, "packets": 5, "idle_sent": 5, "idle_dropped": 3, "sessions": 2})
        self.assertEqual(self.coverage(YESTERDAY), expected)
        self.assertEqual(self.coverage(TODAY), expected_coverage(packets, TODAY))
        self.assertEqual(self.coverage(TODAY)["sessions"], 1)
        self.assertEqual(self.coverage(TWO_DAYS_AGO), ZERO)
        # Coverage loss is reported, never hidden: the gaps of yesterday are in gap_ms.
        self.assertEqual(self.coverage(YESTERDAY)["gap_ms"], 21500)
        # A day is the wall-clock day of the window, not the day it was received.
        self.assertTrue(all(row["received_ms"] == self.now_ms() for row in self.rows()))

    def test_day_boundary_is_the_wall_time_of_the_window(self):
        before_midnight = packet_for_day(YESTERDAY, offset_ms=DAY_MS - 1, session=cp5.SESSION, window_ms=60000, counters={"episodes_finished": 1})
        at_midnight = packet_for_day(TODAY, offset_ms=0, session=OTHER_SESSION, window_ms=60000, counters={"episodes_finished": 2})
        self.assertEqual(utc_day(telemetry_wall_ms(before_midnight)), YESTERDAY)
        self.assertEqual(utc_day(telemetry_wall_ms(at_midnight)), TODAY)
        self.ingest_telemetry(before_midnight)
        self.ingest_telemetry(at_midnight)
        self.assertEqual(self.coverage(YESTERDAY)["episodes"], 1)
        self.assertEqual(self.coverage(TODAY)["episodes"], 2)
        self.assertEqual(self.coverage(YESTERDAY)["sessions"], 1)
        self.assertEqual(self.coverage(TODAY)["sessions"], 1)
        # The wall time comes from the anchor arithmetic, not from t_ms alone.
        shifted = telemetry_packet(session="55555555-5555-4555-8555-555555555555", t_ms=5 * 60000, mono_ms=4 * 60000,
                                   wall_ms=cp5.day_start_ms(TODAY) + 6 * HOUR_MS, window_ms=60000, counters={"episodes_finished": 4})
        self.assertEqual(telemetry_wall_ms(shifted), cp5.day_start_ms(TODAY) + 6 * HOUR_MS + 60000)
        self.ingest_telemetry(shifted)
        self.assertEqual(self.coverage(TODAY)["episodes"], 6)
        self.assertEqual(self.coverage(TODAY)["sessions"], 2)

    def test_telemetry_rows_expire_with_episodes_days_but_the_day_rollup_survives(self):
        # Coordinator ruling 5: the live rows expire with episodes_days; coverage(day)
        # then returns the day's rollup (source "rollup", the same integers), kept 365 days.
        old = packet_for_day(YESTERDAY, offset_ms=9 * HOUR_MS, window_ms=60000, counters={"episodes_finished": 1, "gap_ms": 1500, "idle_sent": 2})
        self.ingest_telemetry(old)
        received = self.rows()[0]["received_ms"]
        live = self.store.coverage(YESTERDAY)
        self.assertEqual(live.get("source"), "live")
        before = self.coverage(YESTERDAY)
        self.assertEqual(before["episodes"], 1)
        counts = self.store.apply_retention(received + 29 * DAY_MS)
        self.assertEqual(len(self.rows()), 1, "29 days: inside the 30-day default window")
        counts = self.store.apply_retention(received + 31 * DAY_MS)
        self.assertEqual(self.rows(), [], f"31 days: the telemetry rows are gone with the episodes ({counts})")
        expired_counts = [v for k, v in counts.items() if "telemetry" in k or "counter" in k]
        self.assertTrue(expired_counts and expired_counts[0] >= 1, f"apply_retention reports the expired telemetry rows: {counts}")
        rolled = self.store.coverage(YESTERDAY)
        self.assertEqual(rolled.get("source"), "rollup", rolled)
        self.assertEqual(self.coverage(YESTERDAY), before, "the rollup carries the same integers")
        self.assertEqual(self.store.coverage(TWO_DAYS_AGO).get("source"), "none")
        self.assertEqual(self.coverage(TWO_DAYS_AGO), ZERO)
        # The rollup itself expires after 365 days.
        self.store.apply_retention(received + 366 * DAY_MS)
        self.assertEqual(self.coverage(YESTERDAY), ZERO)
        self.assertEqual(self.store.coverage(YESTERDAY).get("source"), "none")
        # A shorter window set later applies on the next pass.
        fresh = packet_for_day(TODAY, offset_ms=HOUR_MS, window_ms=60000)
        self.ingest_telemetry(fresh)
        self.store.set_retention(actor=fx.ACTOR, episodes_days=7)
        self.store.apply_retention(self.now_ms() + 8 * DAY_MS)
        self.assertEqual(self.rows(), [])
        # Erasing the profile removes every telemetry row, the day rollups and the
        # maintenance counters (coordinator ruling 3): coverage reads "none" with zeros,
        # and the report counts both tables.
        self.ingest_telemetry(packet_for_day(TODAY, offset_ms=2 * HOUR_MS, window_ms=60000, counters={"episodes_finished": 3}))
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.store.coverage(TODAY).get("source"), "live")
        self.assertEqual(self.coverage(TODAY)["episodes"], 3)
        report = self.store.erase_profile(actor=fx.ACTOR, confirm=fx.ERASE_ALL_PHRASE)
        self.assertEqual(self.rows(), [])
        counts = report.get("counts") if isinstance(report, dict) else None
        self.assertIsInstance(counts, dict, report)
        for key in ("coverage_days", "maintenance_counters"):
            self.assertIn(key, counts, "the erase report counts the aggregate tables too")
            self.assertIsInstance(counts[key], int)
            self.assertGreaterEqual(counts[key], 0)
        self.assertGreaterEqual(counts["coverage_days"], 1, "today's rollup existed and was erased")
        erased = self.store.coverage(TODAY)
        self.assertEqual(erased.get("source"), "none", erased)
        self.assertEqual({k: erased[k] for k in COVERAGE_KEYS}, ZERO)
        self.assertEqual(fx.table_rows(self.db, "coverage_days"), [])

    def test_telemetry_needs_no_consent_acknowledgement(self):
        # Coordinator ruling 10: counters are numbers only; a profile that never
        # acknowledged the disclosure still accounts for its frames.
        store = self.make_store(profile="unacknowledged", consent=False)
        self.assertIs(store.consent_state().get("ok"), False)
        store.ingest_telemetry(encode(packet_for_day(TODAY, offset_ms=HOUR_MS, window_ms=60000, counters={"episodes_finished": 2})))
        self.assertEqual(self.coverage(TODAY, store)["episodes"], 2)
        self.assertEqual(len(self.rows(where="WHERE profile_id='unacknowledged'")), 1)

    def test_packet_gap_reasons_are_never_copied_out_of_the_packet(self):
        """Coordinator pin a: capture_gaps.reason IS NULL always. A packet gap's free-text
        reason stays in the packet it arrived in (episode_revisions.packet, erased with
        it) and is copied to no other table; a telemetry-derived gap has no reason at all."""
        marker = "PII-GAP-REASON-cp5-4e9d"
        packet = self.place([fx.observation(None, fx.BLOCK_BBOX, label="synthetic cp5 block", location="fixture cp5 table")],
                            gaps=[{"t_from_ms": 1100, "t_to_ms": 1600, "reason": marker}])
        self.ingest_telemetry(telemetry_packet(wall_ms=fx.rest_wall_ms(packet), t_ms=60000, window_ms=60000, counters={"gaps": 1, "gap_ms": 5000}))
        self.assertTrue(fx.table_exists(self.db, "capture_gaps"), "capture_gaps table")
        rows = fx.table_rows(self.db, "capture_gaps", "WHERE profile_id='local' ORDER BY t_to_ms")
        self.assertGreaterEqual(len(rows), 2, rows)
        self.assertEqual({row["reason"] for row in rows}, {None}, "capture_gaps.reason IS NULL always")
        self.assertEqual({row["source"] for row in rows} & {"packet", "telemetry"}, {"packet", "telemetry"}, rows)
        packet_gap = next(row for row in rows if row["source"] == "packet")
        self.assertEqual(packet_gap["gap_ms"], 500)
        self.assertEqual(packet_gap["t_to_ms"] - packet_gap["t_from_ms"], 500)
        hits = fx.scan_database(self.db, {"gap": marker})
        self.assertEqual({(table, column) for table, column, _ in hits}, {("episode_revisions", "packet")},
                         f"the reason lives only in the raw packet bytes it arrived in: {hits}")
        # The gap still counts for the answer (hedged with coverage_gap) and the item.
        self.assertIn("coverage_gap", self.store.answer_text("where is my synthetic cp5 block")["basis"])
        self.assertNotIn(marker, str(self.store.answer_text("where is my synthetic cp5 block")))
        self.assertNotIn(marker, str(self.store.list_items()))
        self.assertNotIn(marker, str(self.store.item_history(self.item_by_name("synthetic cp5 block")["item_id"])))

    def test_counters_never_enter_the_catalogue_or_the_answer(self):
        self.ingest_telemetry(packet_for_day(TODAY, offset_ms=HOUR_MS, window_ms=60000))
        self.assertEqual(self.store.list_items(), [])
        self.assertEqual(self.store.answer_text("where is my frames_captured")["shape"], "abstain")


if __name__ == "__main__":
    unittest.main(verbosity=2)
