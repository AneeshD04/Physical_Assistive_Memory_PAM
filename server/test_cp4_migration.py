"""CP4 acceptance, store level: the real v1 migration (B-10).

    python3 -B server/test_cp4_migration.py -v

Authority: docs/BUILD_PLAN.md "CP4 in detail", *v1 migration (B-10; A)*:

  ObjectStore.migrate_v1(*, dry_run=True, actor) -> report
    reads the legacy tables (objects, candidates, observations, decisions, api_calls)
    and converts each confirmed legacy observation into a local_observations row
    with source "legacy_v1", identity_state "provisional" (never trusted), outcome
    from the legacy event type (placed -> placed_on_surface, picked_up ->
    picked_up, anything else -> uncertain), location_text from the legacy
    description, observed_at_ms from its timestamp, no image (reference_image
    null); legacy budgets, unknown spend and leases untouched; dry_run returns
    counts and up to 5 sample rows without writing; a real run is one transaction
    with a migrations row {migration_id, from_version, counts, at_ms, actor}, is
    idempotent (a second run reports already_migrated) and any exception rolls
    back everything.

The v1 database is built with the retained v1 ObjectStore API only
(test_cp4_fixtures.V1Builder, the lifecycle suite's patterns): two tracked objects
(placed / picked_up / placed again; placed / a bystander "unknown"), one ignored
object (user-rejected: not migrated), a rejected background sighting, a processing
lease with a reserved API call, a budget_wait candidate and one raw observations row
with an event type the migration cannot know ("levitated").
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
import test_memory_bootstrap as bootstrap  # noqa: E402
import test_cp4_fixtures as fx  # noqa: E402

LEGACY_TABLES = ("objects", "candidates", "observations", "bindings", "api_calls", "decisions")
MIGRATION_COLUMNS = {"migration_id", "from_version", "counts", "at_ms", "actor"}
OUTCOMES = {"placed_on_surface", "picked_up", "uncertain"}
ASK_BOTTLE = "where is my legacy pill bottle"


def already_migrated(report):
    return report.get("status") == "already_migrated" or report.get("already_migrated") is True


class MigrationFixture(bootstrap.MemoryApiFixture):
    def setUp(self):
        super().setUp()
        self.client.__exit__(None, None, None)
        self.now = fx.V1_T0 + 60
        self.expected = fx.build_v1_fixture(self.db, self.clock)
        self.a = next(k for k, v in self.expected["objects"].items() if v == "Legacy pill bottle")
        self.b = next(k for k, v in self.expected["objects"].items() if v == "Legacy glasses")
        self.now = fx.V1_T0 + 3600 * 24 * 300   # the migration runs much later than the legacy records
        self.store = self.make_store()

    def make_store(self, cls=None):
        from perception.object_memory import ObjectStore
        store = (cls or ObjectStore)(self.db, profile_id="local", clock=self.clock)
        store.acknowledge_consent(fx.CONSENT_VERSION, fx.ACTOR)   # coordinator ruling 1
        return store

    def now_ms(self):
        return int(self.now * 1000)

    def legacy_snapshot(self):
        return {table: fx.table_snapshot(self.db, table) for table in LEGACY_TABLES}

    def new_rows(self):
        return [dict(r, record=json.loads(r["record"]) if r["record"] else None) for r in fx.table_rows(self.db, "local_observations", "WHERE profile_id='local' ORDER BY observed_at_ms, observation_id")]

    def legacy_rows(self):
        return [r for r in self.new_rows() if r["record"] and r["record"].get("source") == "legacy_v1"]

    def migrations(self):
        return fx.table_rows(self.db, "migrations") if fx.table_exists(self.db, "migrations") else []

    def assert_untouched(self, snapshot):
        # Snapshots only: claim_next itself would recycle the expired lease and spend the
        # new day's budget, so the legacy tables are compared byte for byte instead.
        self.assertEqual(self.legacy_snapshot(), snapshot, "legacy rows, budgets, unknown spend and leases are untouched")
        self.assertEqual(self.store.usage(), self.expected["usage"])

    def assert_report(self, report, *, dry_run):
        self.assertIsInstance(report, dict, report)
        self.assertIs(report.get("dry_run"), dry_run, report)
        counts = report.get("counts")
        self.assertIsInstance(counts, dict, report)
        self.assertTrue(all(isinstance(v, int) and not isinstance(v, bool) for v in counts.values()), counts)
        # Coordinator ruling 7: "observations" counts every legacy observations row (the
        # ignored object's included); the rows of confirmed objects are the converted ones.
        self.assertEqual(counts.get("observations"), self.expected["observation_rows"], counts)
        self.assertEqual(counts.get("converted"), self.expected["converted"], f"four observations of A (incl. the raw unknown type) and two of B; the ignored object is not converted: {counts}")
        self.assertEqual(counts.get("objects"), 3, counts)
        self.assertEqual(counts.get("objects_confirmed", 2), 2, counts)
        self.assertIn("legacy_media_files", counts, "ruling 14: legacy media are counted, never read")
        self.assertGreaterEqual(counts["legacy_media_files"], 4)
        return counts


class DryRunTests(MigrationFixture):
    def test_dry_run_reports_counts_and_at_most_five_samples_and_writes_nothing(self):
        snapshot = self.legacy_snapshot()
        before = fx.row_counts(self.db)
        audits = len(fx.table_rows(self.db, "local_audit"))
        report = self.store.migrate_v1(dry_run=True, actor=fx.ACTOR)
        self.assert_report(report, dry_run=True)
        samples = report.get("samples")
        self.assertIsInstance(samples, list, report)
        self.assertTrue(1 <= len(samples) <= 5, samples)
        for sample in samples:
            self.assertIsInstance(sample, dict)
            self.assertEqual(sample.get("identity_state"), "provisional", sample)
            self.assertIn(sample.get("outcome"), OUTCOMES, sample)
            self.assertIn(sample.get("location_text"), set(fx.V1_LOCATION_TEXT.values()), sample)
            self.assertNotIn(sample.get("location_text"), set(fx.V1_DESCRIPTIONS.values()), "the VLM's free description is never migrated (ruling 14)")
            self.assertIsInstance(sample.get("observed_at_ms"), int)
            self.assertIsNone(sample.get("reference_image"))
            self.assertNotIn(str(self.root), json.dumps(sample))
            self.assertNotIn("legacy-", json.dumps({k: v for k, v in sample.items() if k != "legacy_event_id"}), "no media path in a sample")
        self.assertEqual(fx.row_counts(self.db), before, "a dry run writes nothing")
        self.assertEqual(self.legacy_rows(), [])
        self.assertEqual(self.migrations(), [])
        self.assertEqual(len(fx.table_rows(self.db, "local_audit")), audits)
        self.assertEqual(self.store.list_items(), [])
        self.assert_untouched(snapshot)
        # dry_run is the default.
        default = self.store.migrate_v1(actor=fx.ACTOR)
        self.assertIs(default.get("dry_run"), True)
        self.assertEqual(default.get("counts"), report.get("counts"))
        self.assertEqual(fx.row_counts(self.db), before)
        # A bad actor is refused before anything is read into a report.
        for actor in ("Dr Smith", "", None, "admin"):
            with self.subTest(actor=actor), self.assertRaises((ValueError, TypeError)):
                self.store.migrate_v1(dry_run=False, actor=actor)
        self.assertEqual(fx.row_counts(self.db), before)


class RealRunTests(MigrationFixture):
    def test_real_run_writes_provisional_only_rows_and_a_migrations_row(self):
        snapshot = self.legacy_snapshot()
        dry = self.store.migrate_v1(dry_run=True, actor=fx.ACTOR)
        report = self.store.migrate_v1(dry_run=False, actor=fx.ACTOR)
        counts = self.assert_report(report, dry_run=False)
        self.assertEqual(counts, dry["counts"], "the real run converts exactly what the dry run announced")
        self.assertFalse(already_migrated(report))
        rows = self.migrations()
        self.assertEqual(len(rows), 1, rows)
        self.assertTrue(MIGRATION_COLUMNS <= set(rows[0]), rows[0])
        self.assertIsInstance(rows[0]["migration_id"], str)
        self.assertIsNotNone(rows[0]["from_version"], rows[0])
        self.assertEqual(rows[0]["at_ms"], self.now_ms())
        self.assertEqual(rows[0]["actor"], fx.ACTOR)
        stored_counts = rows[0]["counts"]
        self.assertEqual(json.loads(stored_counts) if isinstance(stored_counts, str) else stored_counts, counts)
        legacy = self.legacy_rows()
        self.assertEqual(len(legacy), 6, [r["record"] for r in legacy])
        by_time = {}
        for row in legacy:
            record = row["record"]
            self.assertEqual(record["identity_state"], "provisional", record)
            self.assertEqual(record["source"], "legacy_v1")
            self.assertIn(record["outcome"], OUTCOMES, record)
            self.assertIsNone(record.get("reference_image"), "legacy frames are paths on disk, not stored bytes")
            self.assertNotIn("jpeg_b64", json.dumps(record))
            self.assertNotIn(str(self.root), json.dumps(record), "no legacy media path travels into the new row")
            self.assertNotIn(record["location_text"], set(fx.V1_DESCRIPTIONS.values()), "ruling 14: surface, room only")
            self.assertEqual(row["observed_at_ms"], record["observed_at_ms"])
            by_time[record["observed_at_ms"]] = (row["item_id"], record)
        for object_id, action, observed_at, description in self.expected["observations"]:
            at = int(round(observed_at * 1000))
            self.assertIn(at, by_time, (action, description))
            item_id, record = by_time[at]
            self.assertEqual(record["outcome"], fx.V1_OUTCOME[action], (action, record))
            self.assertEqual(record["location_text"], description)
        a_items = {by_time[int(round(at * 1000))][0] for obj, _, at, _ in self.expected["observations"] if obj == self.a}
        b_items = {by_time[int(round(at * 1000))][0] for obj, _, at, _ in self.expected["observations"] if obj == self.b}
        self.assertEqual(len(a_items), 1, "every observation of one legacy object lands in one item")
        self.assertEqual(len(b_items), 1)
        self.assertNotEqual(a_items, b_items)
        # The catalogue: two provisional items, never placed, never confident; the ignored object is absent.
        items = {i["name"]: i for i in self.store.list_items()}
        self.assertEqual(set(items), {"Legacy pill bottle", "Legacy glasses"}, items)
        for item in items.values():
            self.assertEqual(item["identity_status"], "provisional", item)
            self.assertNotEqual(item["location_status"], "placed")
            self.assertEqual(item["source"], "legacy_v1", item)
            self.assertIsNone(item["reference_image"])
            self.assertIsNone(self.store.item_image(item["item_id"]))
            self.assertEqual(len(self.store.item_evidence(item["item_id"])), 4 if item["name"] == "Legacy pill bottle" else 2)
        self.assertEqual(len(self.store.item_history(items["Legacy pill bottle"]["item_id"])), 4)
        answer = self.store.answer_text(ASK_BOTTLE)
        self.assertNotEqual(answer["shape"], "confident", answer)
        self.assertNotEqual(self.store.answer_text("where are my legacy glasses")["shape"], "confident")
        self.assertEqual(self.store.answer_text("where is my legacy mug")["shape"], "abstain", "the ignored object was not resurrected")
        self.assert_untouched(snapshot)
        self.assertEqual(self.store.migration_plan()["legacy_counts"]["observations"], self.expected["observation_rows"], "legacy rows stay readable")
        # Oversight T4: the legacy geolocation stays in the legacy tables (control) and
        # reaches no table the migration writes.
        hits = fx.scan_database(self.db, fx.V1_GEO_MARKERS)
        self.assertEqual({marker for _, _, marker in hits}, set(fx.V1_GEO_MARKERS.values()), "control: the fix is in the legacy rows")
        leaked = [(table, column, marker) for table, column, marker in hits if table not in LEGACY_TABLES]
        self.assertEqual(leaked, [], f"lat/lon leaked into a migrated table: {leaked}")
        for item in self.store.list_items():
            dumped = json.dumps({"item": item, "history": self.store.item_history(item["item_id"]), "evidence": self.store.item_evidence(item["item_id"])})
            for marker in fx.V1_GEO_MARKERS.values():
                self.assertNotIn(marker, dumped)
            self.assertNotIn("maps_url", dumped)
        # Replay keeps them provisional; nothing is re-run.
        result = self.store.rebuild_all()
        self.assertIs(result["model_rerun"], False)
        self.assertEqual({i["identity_status"] for i in self.store.list_items()}, {"provisional"})
        # A fresh store sees the same.
        fresh = self.make_store()
        self.assertEqual({i["name"] for i in fresh.list_items()}, {"Legacy pill bottle", "Legacy glasses"})
        self.assertTrue(already_migrated(fresh.migrate_v1(dry_run=True, actor=fx.ACTOR)), "even a dry run reports the migration already done")

    def test_second_run_reports_already_migrated_and_writes_nothing(self):
        self.store.migrate_v1(dry_run=False, actor=fx.ACTOR)
        before = fx.row_counts(self.db)
        legacy = self.legacy_rows()
        report = self.store.migrate_v1(dry_run=False, actor=fx.ACTOR)
        self.assertIsInstance(report, dict)
        self.assertTrue(already_migrated(report), report)
        self.assertEqual(fx.row_counts(self.db), before)
        self.assertEqual(self.legacy_rows(), legacy)
        self.assertEqual(len(self.migrations()), 1)
        # Another store instance agrees.
        self.assertTrue(already_migrated(self.make_store().migrate_v1(dry_run=False, actor=fx.ACTOR)))
        self.assertEqual(len(self.migrations()), 1)

    def test_an_injected_failure_rolls_back_everything(self):
        from perception.object_memory import ObjectStore

        class FailingStore(ObjectStore):
            def _rebuild_projection(self, db):
                raise RuntimeError("synthetic failure injected by the tester")

        failing = self.make_store(FailingStore)   # (its consent acknowledgement is audited: snapshot after it)
        snapshot = self.legacy_snapshot()
        before = fx.row_counts(self.db)
        audits = len(fx.table_rows(self.db, "local_audit"))
        try:
            report = failing.migrate_v1(dry_run=False, actor=fx.ACTOR)
        except Exception as error:  # the plan: any exception rolls back everything
            self.assertNotIsInstance(error, (KeyError, TypeError), error)
            report = None
        if report is not None:
            self.assertTrue(report.get("status") in ("failed", "error", "rolled_back") or report.get("error"), f"a failed run must say so: {report}")
            self.assertFalse(already_migrated(report))
        self.assertEqual(fx.row_counts(self.db), before, "nothing of the failed run remains")
        self.assertEqual(self.legacy_rows(), [])
        self.assertEqual(self.migrations(), [])
        self.assertEqual(len(fx.table_rows(self.db, "local_audit")), audits)
        self.assertEqual(self.store.list_items(), [])
        self.assert_untouched(snapshot)
        # The database is not marked migrated: a healthy store converts it now.
        report = self.store.migrate_v1(dry_run=False, actor=fx.ACTOR)
        self.assertFalse(already_migrated(report), report)
        self.assertEqual(report["counts"]["converted"], self.expected["converted"])
        self.assertEqual(len(self.legacy_rows()), self.expected["converted"])
        self.assertEqual(len(self.migrations()), 1)

    def test_unknown_legacy_event_types_become_uncertain_and_never_a_location(self):
        self.store.migrate_v1(dry_run=False, actor=fx.ACTOR)
        legacy = {r["record"]["location_text"]: r["record"] for r in self.legacy_rows()}
        self.assertEqual(legacy[fx.V1_LOCATION_TEXT["raw-levitated"]]["outcome"], "uncertain")
        self.assertEqual(legacy[fx.V1_LOCATION_TEXT["B-unknown"]]["outcome"], "uncertain")
        self.assertEqual(legacy[fx.V1_LOCATION_TEXT["A-picked-up"]]["outcome"], "picked_up")
        self.assertEqual(legacy[fx.V1_LOCATION_TEXT["A-placed-2"]]["outcome"], "placed_on_surface")
        self.assertNotIn(fx.V1_LOCATION_TEXT["C-placed"], legacy, "the ignored object's row was not converted")
        glasses = next(i for i in self.store.list_items() if i["name"] == "Legacy glasses")
        self.assertEqual(glasses["location_status"], "unknown", "the newest legacy event of the glasses is of an unknown type")
        self.assertIsNone(glasses["location_text"])
        bottle = next(i for i in self.store.list_items() if i["name"] == "Legacy pill bottle")
        self.assertEqual(bottle["location_status"], "unknown", "the raw 'levitated' row is the bottle's newest event")
        self.assertIsNone(bottle["location_text"])

    def test_migrated_evidence_never_merges_with_or_upgrades_new_evidence(self):
        self.store.migrate_v1(dry_run=False, actor=fx.ACTOR)
        scripted = fx.identity.Cp3Processor()
        packet = fx.episode_packet(1, rest=fx.golden("reference"), wall_ms=self.now_ms() - 5000)
        scripted.observations[packet["episode_id"]] = [fx.observation(fx.rest_frame_id(packet), fx.BLOCK_BBOX, label="Legacy pill bottle", location="fixture cp4 table")]
        self.assertEqual(self.store.ingest_episode(bootstrap.encode_packet(packet))["status"], "stored")
        counts = self.store.process_pending(processor=scripted)
        self.assertEqual(counts["failed"], 0, counts)
        bottles = [i for i in self.store.list_items() if i["name"] == "Legacy pill bottle"]
        self.assertEqual(len(bottles), 2, "a new trusted placement is a separate item; legacy evidence is never guessed to be the same instance")
        statuses = sorted((i["identity_status"], i["location_status"]) for i in bottles)
        self.assertEqual(statuses, [("provisional", "unknown"), ("trusted", "placed")])
        answer = self.store.answer_text(ASK_BOTTLE)
        self.assertEqual(answer["shape"], "clarify", answer)


if __name__ == "__main__":
    unittest.main(verbosity=2)
