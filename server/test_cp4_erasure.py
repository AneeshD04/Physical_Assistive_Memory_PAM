"""CP4 acceptance, store level: erasure (B-07, B-08, P-107) and sidecar privacy (B-09).

    python3 -B server/test_cp4_erasure.py -v

Authority: docs/BUILD_PLAN.md "CP4 in detail", *Erasure* and *WAL and journal privacy*:

  ObjectStore.erase_item(item_id, actor) -> report   (redact_item kept as an alias)
    one transaction: tombstone the item and its co-visibility closure; delete their
    embeddings, reobservations, containment, promoted idle frames and corrections;
    rewrite local_observations.record to {"erased": true, "observed_at_ms"}; blank
    item_names.name, local_audit.detail and corrections.payload (row kept, erased=1);
    NULL the packets of the affected revisions with redacted_reason "erasure"; one
    audit row "erased" carrying only counts.
  ObjectStore.erase_profile(actor, confirm) -> report
    everything in the profile, unpromoted idle frames too, calibrations stay, then
    VACUUM INTO a fresh file swapped in under the private-file rules.
  ObjectStore.sidecar_report() -> every sidecar present is owner-only (POSIX 0600).

P-107: synthetic PII markers are planted in every text field a user or the pipeline
can write (label, location text, confidence basis, continuity id, packet frame ids, a
gap reason, a user name) across two co-visible items and a linked item, and must
vanish from every table cell, from rebuild_all, from as_of views before and after
the erasure time, from history/evidence/chat and from the database file bytes after
erase_profile. The markers are nonsense strings; nothing personal is used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
import test_memory_bootstrap as bootstrap  # noqa: E402
import test_cp3_identity as identity  # noqa: E402
import test_cp4_fixtures as fx  # noqa: E402

M = fx.MARKERS
ANCHOR_MS = fx.ANCHOR_MS
ORIGIN = bootstrap.ORIGIN
X_MARKERS = {k: v for k, v in M.items() if k.startswith("x_")}
Y_MARKERS = {k: v for k, v in M.items() if k.startswith("y_")}
W_MARKERS = {k: v for k, v in M.items() if k.startswith("w_")}
Z_MARKERS = {k: v for k, v in M.items() if k.startswith("z_")}
ERASED_MARKERS = {**X_MARKERS, **Y_MARKERS, **W_MARKERS}
# Nested tagged squares on the texture: Y (tag 3, 48 px) contains X (tag 0, 16 px).
Y_SQUARE, X_SQUARE = (56, 36, 48, 3), (72, 52, 16, 0)
Y_BBOX, X_BBOX = fx.square_bbox(56, 36, 48), fx.square_bbox(72, 52, 16)
W_SQUARE, Z_SQUARE = (100, 40, 24, 6), (100, 40, 24, 5)
W_BBOX = Z_BBOX = fx.square_bbox(100, 40, 24)
STUB_FIELDS = {"erased", "observed_at_ms"}


class ErasureFixture(fx.Cp4Fixture):
    EMBEDDER = True

    def setUp(self):
        super().setUp()
        self.register_calibration()

    def tagged(self, label, bbox, location, **extra):
        return fx.observation(None, bbox, label=label, location=location, calibration=identity.cp3_calibration(), **extra)

    def seed(self):
        """X inside Y in one frame (markers everywhere a text can go), W seen alone and
        linked into X, Z on another device, two idle frames (one promoted by a positive
        re-observation of X and Y, one unknown and unpromoted), user names on X, Y, Z."""
        nested = fx.scene_jpeg(block="absent", squares=[Y_SQUARE, X_SQUARE])
        self.nested_packet = self.place(
            [self.tagged(M["y_label"], Y_BBOX, M["y_location"], confidence_basis=M["y_basis"]),
             self.tagged(M["x_label"], X_BBOX, M["x_location"], confidence_basis=M["x_basis"], continuity_id=M["x_continuity"])],
            rest=nested, frame_ids=(M["x_frame"] + "-before", M["x_frame"] + "-rest"),
            gaps=[{"t_from_ms": 1100, "t_to_ms": 1150, "reason": M["x_gap"]}])
        self.x = self.item_by_name(M["x_label"])["item_id"]
        self.y = self.item_by_name(M["y_label"])["item_id"]
        base = fx.rest_wall_ms(self.nested_packet)
        self.promoted, _ = self.idle(nested, wall_ms=base + 60000)
        self.unpromoted, _ = self.idle("flat", wall_ms=base + 120000)
        self.now += 120
        self.reobserve()
        self.place([self.tagged(M["w_label"], W_BBOX, M["w_location"])], rest=fx.scene_jpeg(block="absent", squares=[W_SQUARE]))
        self.w = self.item_by_name(M["w_label"])["item_id"]
        self.store.link_items(self.x, self.w, fx.ACTOR)
        self.place([self.tagged(M["z_label"], Z_BBOX, M["z_location"])], rest=fx.scene_jpeg(block="absent", squares=[Z_SQUARE]), device=fx.OTHER_DEVICE)
        self.z = self.item_by_name(M["z_label"])["item_id"]
        self.store.rename_item(self.x, M["x_rename"])
        self.store.rename_item(self.y, M["y_rename"])
        self.store.rename_item(self.z, M["z_rename"])
        self.erase_ms = self.now_ms() + 1000
        self.now += 1
        return self.x, self.y, self.z

    def assert_seeded(self):
        items = {i["item_id"]: i for i in self.items()}
        self.assertEqual(set(items), {self.x, self.y, self.z}, items)
        self.assertEqual(items[self.x]["name"], M["x_rename"])
        self.assertEqual(items[self.y]["location_text"], M["y_location"])
        self.assertEqual(len(self.store.item_evidence(self.x)), 3, "placement + linked W + the positive re-observation")
        self.assertGreaterEqual(len(self.rows("embeddings")), 4, "X, Y, W, Z placements were embedded")
        reobs = {(r["item_id"], r["result"]) for r in self.rows("reobservations")}
        self.assertEqual({r for r in reobs if r[1] == "present"}, {(self.x, "present"), (self.y, "present")}, reobs)
        self.assertEqual([(r["inner_item"], r["outer_item"]) for r in self.rows("containment")], [(self.x, self.y)])
        self.assertEqual({r["frame_id"]: r["promoted"] for r in self.rows("idle_frames")}, {self.promoted["frame_id"]: 1, self.unpromoted["frame_id"]: 0})
        self.assertEqual(len(self.rows("corrections")), 1)
        hits = fx.scan_database(self.db, M)
        self.assertEqual({marker for _, _, marker in hits}, set(M.values()), f"every marker must be planted before erasure (control): {hits}")
        self.assertEqual({marker for _, marker in fx.scan_files(self.db, M)} & set(ERASED_MARKERS.values()), set(ERASED_MARKERS.values()), "control: the file bytes carry the markers")

    def assert_absent_everywhere(self, markers, *, item_ids):
        hits = fx.scan_database(self.db, markers)
        self.assertEqual(hits, [], f"markers survived erasure in: {hits}")
        for item_id in item_ids:
            with self.assertRaises(KeyError):
                self.store.get_item(item_id)
            with self.assertRaises(KeyError):
                self.store.item_history(item_id)
            with self.assertRaises(KeyError):
                self.store.item_evidence(item_id)
            self.assertIsNone(self.store.item_image(item_id))
        listed = json.dumps(self.items())
        for marker in markers.values():
            self.assertNotIn(marker, listed)
        rebuilt = json.dumps(self.store.rebuild_all())
        for marker in markers.values():
            self.assertNotIn(marker, rebuilt, "rebuild_all must not resurrect erased content")
        for as_of in (ANCHOR_MS + 2200, self.erase_ms - 1, self.erase_ms + 10, self.now_ms() + 10 ** 9):
            view = json.dumps({"items": self.items(as_of=as_of), "rebuild": self.store.rebuild_all(as_of=as_of),
                               "answer": self.store.answer_text("where is my " + M["x_label"], as_of=as_of)})
            for marker in markers.values():
                self.assertNotIn(marker, view, f"as_of={as_of} view carries an erased marker")
            for item_id in item_ids:
                with self.assertRaises(KeyError):
                    self.store.get_item(item_id, as_of=as_of)
        for question in (M["x_label"], M["y_rename"], M["w_label"], "basket", "keys"):
            answer = self.store.answer_text(f"where is my {question}")
            self.assertNotEqual(answer["shape"], "confident")
            dumped = json.dumps(answer)
            for marker in markers.values():
                self.assertNotIn(marker, dumped)
            self.assertFalse({m["item_id"] for m in answer["members"]} & set(item_ids))


class EraseItemTests(ErasureFixture):
    def test_erase_item_removes_the_closure_from_every_table_and_read_path(self):
        x, y, z = self.seed()
        self.assert_seeded()
        x_observations = {r["observation_id"] for r in self.rows("local_observations") if r["item_id"] in (x, y, self.w)}
        audits_before = len(self.audit())
        report = self.store.erase_item(x, fx.ACTOR)
        self.assertIsInstance(report, dict, report)
        self.assertIs(report.get("forensic_erasure", False), False, "no forensic claim")
        self.assertGreaterEqual(report.get("affected_items", 0), 2, report)
        self.assert_absent_everywhere(ERASED_MARKERS, item_ids=(x, y, self.w))
        # Z and its markers survive untouched.
        survivor = self.item_by_name(M["z_rename"])
        self.assertEqual((survivor["item_id"], survivor["location_text"], survivor["identity_status"]), (z, M["z_location"], "trusted"))
        self.assertEqual({marker for _, _, marker in fx.scan_database(self.db, Z_MARKERS)}, set(Z_MARKERS.values()))
        self.assertEqual(self.store.answer_text("where is my " + M["z_rename"])["shape"], "confident", "Z answers under its user name")
        # Derived rows of the erased items are gone; Z's embedding stays.
        embeddings = self.rows("embeddings")
        self.assertEqual(len(embeddings), 1, embeddings)
        self.assertEqual(self.store.item_evidence(z)[0]["observation_id"], embeddings[0]["observation_id"])
        self.assertEqual(self.rows("reobservations"), [])
        self.assertEqual(self.rows("containment"), [])
        self.assertEqual({r["frame_id"]: r["promoted"] for r in self.rows("idle_frames")}, {self.unpromoted["frame_id"]: 0}, "promoted frames of the erased items are deleted; the plain cache stays")
        # Observation rows are stubs, names and corrections blanked with erased=1.
        for row in self.rows("local_observations"):
            if row["observation_id"] in x_observations:
                self.assertIsNotNone(row["record"], "the stub replaces the record")
                stub = json.loads(row["record"])
                self.assertEqual(set(stub), STUB_FIELDS, stub)
                self.assertIs(stub["erased"], True)
                self.assertIsInstance(stub["observed_at_ms"], int)
                self.assertIsNone(row["candidates"])
        self.assertIn("erased", fx.columns(self.db, "item_names"))
        self.assertIn("erased", fx.columns(self.db, "corrections"))
        self.assertIn("erased", fx.columns(self.db, "local_audit"))
        for row in self.rows("item_names", "WHERE item_id IN (?,?,?)", (x, y, self.w)):
            self.assertFalse(row["name"], row)
            self.assertEqual(row["erased"], 1, row)
        for row in self.rows("item_names", "WHERE item_id=?", (z,)):
            self.assertEqual((row["name"], row["erased"]), (M["z_rename"], 0))
        for row in self.rows("corrections"):
            self.assertEqual(row["erased"], 1, row)
            self.assertNotIn(x, row["payload"] or "")
            self.assertNotIn(self.w, row["payload"] or "")
        for row in self.rows("local_audit", "WHERE item_id IN (?,?,?) AND audit_id<=?", (x, y, self.w, audits_before)):
            self.assertEqual(row["erased"], 1, row)
            self.assertNotIn(M["x_rename"], row["detail"] or "")
        for row in self.rows("episode_revisions"):
            if row["device_id"] == fx.OTHER_DEVICE:
                self.assertIsNotNone(row["packet"], "Z's episode is untouched")
            else:
                self.assertIsNone(row["packet"], row["episode_id"])
                self.assertEqual(row["redacted_reason"], "erasure")
        tombstoned = {r["item_id"] for r in self.rows("item_tombstones")}
        self.assertTrue({x, y, self.w} <= tombstoned)
        self.assertNotIn(z, tombstoned)
        erased = self.audit("erased")
        self.assertEqual(len(erased), 1, self.audit()[audits_before:])
        detail = json.loads(erased[0]["detail"])
        self.assertTrue(fx.counts_only(detail), f"the audit row carries counts only (plus the role literal): {detail}")
        self.assertNotIn(x, erased[0]["detail"])
        # A resent packet for an erased episode is refused by the tombstone and never processed.
        ack = self.store.ingest_episode(bootstrap.encode_packet(self.nested_packet))
        self.assertIs(ack["retained"], False, ack)
        self.assertEqual(ack["status"], "conflict")
        self.assertEqual(self.process()["processed"], 0, "a tombstoned episode is never reprocessed")
        self.assertEqual(len(self.rows("episode_jobs", "WHERE status='pending'")), 0)
        self.assert_absent_everywhere(ERASED_MARKERS, item_ids=(x, y, self.w))
        # Idempotent and safe to repeat; unknown ids and bad actors are refused.
        self.assertIsInstance(self.store.erase_item(x, fx.ACTOR), dict)
        with self.assertRaises(KeyError):
            self.store.erase_item("no-such-item", fx.ACTOR)
        for actor in ("Dr Smith", "", None, "admin"):
            with self.subTest(actor=actor), self.assertRaises((ValueError, TypeError)):
                self.store.erase_item(z, actor)
        self.assertEqual(self.item_by_name(M["z_rename"])["item_id"], z, "a refused actor erases nothing")

    def test_redact_item_is_an_alias_of_erase_item(self):
        x, y, z = self.seed()
        report = self.store.redact_item(z)
        self.assertIsInstance(report, dict)
        self.assertIs(report.get("forensic_erasure", False), False)
        self.assertEqual(fx.scan_database(self.db, Z_MARKERS), [])
        with self.assertRaises(KeyError):
            self.store.get_item(z)
        self.assertEqual({i["item_id"] for i in self.items()}, {x, y})
        for row in self.rows("local_observations"):
            if row["item_id"] == z:
                self.assertEqual(set(json.loads(row["record"])), STUB_FIELDS)
        self.assertEqual(len(self.audit("erased")), 1)

    def test_erased_content_is_absent_from_the_http_read_paths(self):
        x, y, z = self.seed()
        self.store.erase_item(x, fx.ACTOR)
        client = self.new_client()
        self.login(client)
        listing = client.get("/api/items")
        self.assertEqual(listing.status_code, 200, listing.text)
        for marker in ERASED_MARKERS.values():
            self.assertNotIn(marker, listing.text)
        self.assertEqual({i["item_id"] for i in listing.json()["items"]}, {z})
        for item_id in (x, y, self.w):
            for suffix in ("", "/history", "/evidence", "/image"):
                response = client.get(f"/api/items/{item_id}{suffix}")
                self.assertEqual(response.status_code, 404, f"{item_id}{suffix}: {response.text}")
                for marker in ERASED_MARKERS.values():
                    self.assertNotIn(marker, response.text)
        for as_of in (ANCHOR_MS + 2200, self.erase_ms - 1, self.now_ms() + 10 ** 6):
            response = client.get("/api/items", params={"as_of": str(as_of)})
            self.assertEqual(response.status_code, 200)
            for marker in ERASED_MARKERS.values():
                self.assertNotIn(marker, response.text)
            self.assertEqual(client.get(f"/api/items/{x}", params={"as_of": str(as_of)}).status_code, 404)
        for question in (M["x_label"], M["y_rename"], M["w_label"]):
            response = client.post("/api/chat", json={"text": "where is my " + question}, headers={"origin": ORIGIN})
            self.assertEqual(response.status_code, 200, response.text)
            for marker in ERASED_MARKERS.values():
                self.assertNotIn(marker, response.text)
            self.assertNotEqual(response.json()["shape"], "confident")
            self.assertEqual(response.json()["members"], [])
        response = client.post("/api/chat", json={"text": "where is my " + M["z_rename"]}, headers={"origin": ORIGIN})
        self.assertEqual(response.json()["shape"], "confident")


class EraseProfileTests(ErasureFixture):
    def test_erase_profile_leaves_no_marker_in_any_table_or_file_byte(self):
        x, y, z = self.seed()
        self.assert_seeded()
        calibrations = self.store.list_calibrations()
        self.assertEqual(len(calibrations), 1)
        # Wrong confirmation: nothing changes.
        for confirm in ("", "erase everything", None, "ERASE", x):
            with self.subTest(confirm=confirm), self.assertRaises((ValueError, TypeError)):
                self.store.erase_profile(actor=fx.ACTOR, confirm=confirm)
        with self.assertRaises((ValueError, TypeError)):
            self.store.erase_profile(actor="Dr Smith", confirm=fx.ERASE_ALL_PHRASE)
        self.assertEqual({i["item_id"] for i in self.items()}, {x, y, z}, "a refused confirmation erases nothing")
        self.assertEqual({marker for _, _, marker in fx.scan_database(self.db, M)}, set(M.values()))
        report = self.store.erase_profile(actor=fx.ACTOR, confirm=fx.ERASE_ALL_PHRASE)
        self.assertIsInstance(report, dict, report)
        self.assertIs(report.get("forensic_erasure", False), False, "no forensic claim (the disclosure's own 'not guaranteed' wording is the honest one; ruling 9)")
        self.assertEqual(self.items(), [])
        self.assert_absent_everywhere(M, item_ids=(x, y, z, self.w))
        self.assertEqual(fx.scan_database(self.db, M), [])
        hits = fx.scan_files(self.db, M)
        self.assertEqual(hits, [], f"marker bytes survived in the database file or a sidecar: {hits}")
        for table in ("embeddings", "reobservations", "containment", "idle_frames", "current_items"):
            self.assertEqual(self.rows(table, "WHERE profile_id='local'"), [], table)
        # Corrections may stay as blanked rows (the plan's (4): row kept, erased=1) or go.
        for row in self.rows("corrections", "WHERE profile_id='local'"):
            self.assertEqual(row["erased"], 1, row)
            self.assertIn(row["payload"], ("", "{}", None), row)
        for row in self.rows("episode_revisions", "WHERE profile_id='local'"):
            self.assertIsNone(row["packet"])
            self.assertEqual(row["redacted_reason"], "erasure")
        self.assertEqual(self.store.list_calibrations(), calibrations, "calibrations are not personal and stay")
        erased = [r for r in self.audit() if r["action"] in ("erased", "profile_erased")]
        self.assertGreaterEqual(len(erased), 1, [r["action"] for r in self.audit()])
        self.assertTrue(fx.counts_only(json.loads(erased[-1]["detail"])), erased[-1]["detail"])
        self.assertEqual(erased[-1]["erased"], 0, "the erasure's own counts-only audit row is kept readable")
        # The swapped-in file is private and the store keeps working afterwards.
        self.assertEqual(stat.S_IMODE(os.stat(self.db).st_mode), 0o600)
        self.assertEqual(self.store.capabilities()[0]["name"], "local_processing")
        fresh = self.make_store()
        self.assertEqual(fresh.list_items(), [])
        erased_at = fx.read_retention(fresh).get("erased_at_ms")
        self.assertEqual(erased_at, self.now_ms(), "the profile records when everything was erased")
        self.assertEqual(fx.read_retention(fresh).get("acknowledged_version"), fx.CONSENT_VERSION, "the consent acknowledgement survives")
        self.now += 60
        packet = self.place([self.tagged("synthetic after erasure", Z_BBOX, "fixture cp4 later")], rest=fx.scene_jpeg(block="absent", squares=[Z_SQUARE]),
                            store=fresh, wall_ms=self.now_ms())
        self.assertEqual(len(fresh.list_items()), 1)
        self.assertEqual(fresh.list_items()[0]["location_text"], "fixture cp4 later")
        # A resend of an erased episode is refused on the fresh file: by the tombstone
        # (retained false) or, being dated before the erasure, by erased_before (ruling 13).
        try:
            resent = fresh.ingest_episode(bootstrap.encode_packet(self.nested_packet))
        except ValueError:
            resent = None
        if resent is not None:
            self.assertIs(resent["retained"], False, resent)
        self.assertEqual([i["name"] for i in fresh.list_items()], ["synthetic after erasure"], "the resend added nothing")
        # Another profile sharing the file is untouched by this profile's erasure.
        other = self.make_store(profile="other-profile")
        other_packet = self.place([self.tagged("synthetic other profile", Z_BBOX, "fixture other")], rest=fx.scene_jpeg(block="absent", squares=[Z_SQUARE]),
                                  store=other, wall_ms=self.now_ms())
        self.assertEqual(len(other.list_items()), 1)
        self.store.erase_profile(actor=fx.ACTOR, confirm=fx.ERASE_ALL_PHRASE)
        self.assertEqual(len(other.list_items()), 1, "erase_profile is scoped to the store's profile")
        self.assertEqual(fresh.list_items(), [])

    def test_captures_dated_before_the_erasure_are_refused_with_a_five_minute_tolerance(self):
        # Coordinator ruling 13: after erase_profile, a capture whose wall start is more
        # than 300 s before erased_at_ms is refused (ValueError "captured before erasure",
        # 409 erased_before at the API); phone-clock skew inside the tolerance is accepted.
        self.seed()
        self.store.erase_profile(actor=fx.ACTOR, confirm=fx.ERASE_ALL_PHRASE)
        erased_at = fx.read_retention(self.store)["erased_at_ms"]
        self.assertEqual(erased_at, self.now_ms())
        self.now += 30

        def packet_starting(wall_start_ms):
            packet = self.next_packet(rest=fx.scene_jpeg(block="absent", squares=[Z_SQUARE]), wall_ms=wall_start_ms - 1000, phase=0)
            self.assertEqual(packet["clock_anchor"]["wall_ms"] + packet["t_start_ms"] - packet["clock_anchor"]["mono_ms"], wall_start_ms)
            observation = self.tagged("synthetic after erasure", Z_BBOX, "fixture cp4 later")
            observation["frame_id"] = fx.rest_frame_id(packet)   # as place() fills it
            self.scripted.observations[packet["episode_id"]] = [observation]
            return packet

        ten_minutes_before = packet_starting(erased_at - 600000)
        with self.assertRaises(ValueError) as caught:
            self.store.ingest_episode(bootstrap.encode_packet(ten_minutes_before))
        self.assertIn("before erasure", str(caught.exception))
        self.assertEqual(self.rows("episode_revisions", "WHERE episode_id=?", (ten_minutes_before["episode_id"],)), [], "nothing retained")
        one_minute_before = packet_starting(erased_at - 60000)
        ack = self.store.ingest_episode(bootstrap.encode_packet(one_minute_before))
        self.assertEqual((ack["status"], ack["retained"]), ("stored", True), ack)
        self.process()
        self.assertEqual([i["location_text"] for i in self.items()], ["fixture cp4 later"])
        # The same tolerance applies to idle frames.
        with self.assertRaises(ValueError):
            self.store.ingest_idle(bootstrap.encode_packet(fx.idle_packet(fx.golden("present"), wall_ms=erased_at - 600000)))
        self.assertIs(self.store.ingest_idle(bootstrap.encode_packet(fx.idle_packet(fx.golden("present"), wall_ms=erased_at - 60000)))["retained"], True)


class SidecarPrivacyTests(fx.Cp4Fixture):
    def test_store_connections_run_with_secure_delete_on(self):
        # Oversight T3: freed pages and deleted rows are overwritten with zeros, so a
        # logical erasure does not leave the erased text in free space of the live file.
        self.place([fx.observation(None, fx.BLOCK_BBOX)])
        with self.store._connection() as db:
            self.assertEqual(db.execute("PRAGMA secure_delete").fetchone()[0], 1, "PRAGMA secure_delete must be ON on every store connection")
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0].lower(), "persist")
        with self.make_store(profile="other-profile")._connection() as db:
            self.assertEqual(db.execute("PRAGMA secure_delete").fetchone()[0], 1)

    def test_sidecars_are_owner_only_after_writes_and_the_report_says_so(self):
        self.place([fx.observation(None, fx.BLOCK_BBOX)])
        self.store.rename_item(self.only_item()["item_id"], "named")
        present = [path for path in fx.sidecar_paths(self.db) if path.exists()]
        self.assertTrue(present, "PERSIST journal mode leaves a -journal sidecar after writes")
        self.assertEqual(stat.S_IMODE(os.stat(self.db).st_mode), 0o600)
        for path in present:
            with self.subTest(sidecar=path.name):
                self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600, f"{path.name} is not owner-only")
        report = self.store.sidecar_report()
        self.assertIsInstance(report, (dict, list), report)
        self.assertNotIn(str(self.root), json.dumps(report), "no paths in the report")
        entries = fx.sidecar_entries(report)
        self.assertTrue({"-journal", "-wal", "-shm"} <= set(entries), f"the report names every sidecar kind: {report}")
        for suffix, entry in entries.items():
            with self.subTest(sidecar=suffix):
                self.assertIn("present", entry, entry)
                self.assertIn("private", entry, entry)
                exists = Path(str(self.db) + suffix).exists()
                self.assertIs(entry["present"], exists)
                if exists:
                    self.assertIs(entry["private"], True)
        # A sidecar made world-readable behind the store's back is reported, not hidden.
        journal = Path(str(self.db) + "-journal")
        if journal.exists():
            os.chmod(journal, 0o644)
            self.addCleanup(lambda: journal.exists() and os.chmod(journal, 0o600))
            tampered = fx.sidecar_entries(self.store.sidecar_report())
            self.assertIs(tampered["-journal"]["private"], False, tampered)
            # The next write re-asserts privacy (the store opens the sidecar through private_append_fd).
            self.store.rename_item(self.only_item()["item_id"], "named again")
            self.assertEqual(stat.S_IMODE(os.stat(journal).st_mode), 0o600)


if __name__ == "__main__":
    unittest.main(verbosity=2)
