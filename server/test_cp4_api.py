"""CP4 acceptance, HTTP level: the idle, retention, erasure and migration routes, the
worker's maintenance calls and the item DTO additions.

    python3 -B server/test_cp4_api.py -v

Authority: docs/BUILD_PLAN.md "CP4 in detail", *Server (B)*:

  POST /api/idle                      protected, origin-checked; 400/413 as for episodes;
                                      200 -> {"frame_id", "retained": true, "expires_at_ms"}
  GET  /api/retention                 the retention row plus live counts idle_cached,
                                      idle_promoted, revisions_expired, landmarks_reduced
  PUT  /api/retention                 {consent_version?, episodes_days 7..365, idle_hours 1..72,
                                      landmarks_hours 1..168} -> the row (audited, actor literal)
  POST /api/items/{id}/erase          {"confirm": "<item_id>"} -> report; 409 on mismatch
  POST /api/erase-all                 {"confirm": "ERASE EVERYTHING"} -> report
  POST /api/migrate                   {"dry_run": true|false}; dry_run defaults true; a real run
                                      needs PAM_ALLOW_MIGRATION=1 (503 otherwise)
  the worker calls expire_idle, apply_retention and reobserve after each processing
  batch; /api/health carries "retention" counts; items carry inference and
  stale_since_ms; no route returns vectors, scores or banks (CP3 ruling 7 guard).

Reuses bootstrap.MemoryApiFixture (temp DB, PIN, egress and private-file guards, the
injected clock) with the CP3 scripted processor and the CP4 fixtures.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
import test_memory_bootstrap as bootstrap  # noqa: E402
import test_cp3_api as cp3_api  # noqa: E402
import test_cp3_identity as identity  # noqa: E402
import test_cp4_fixtures as fx  # noqa: E402

ORIGIN = bootstrap.ORIGIN
ANCHOR_MS = fx.ANCHOR_MS
HOUR_MS, DAY_MS = fx.HOUR_MS, fx.DAY_MS
ITEM_FIELDS = bootstrap.ITEM_FIELDS | {"inference", "stale_since_ms", "reference_image", "aged", "lookalikes", "evidence_expired"}
CONSENT_VERSION = bootstrap.CONSENT_VERSION
CONSENT_FIELDS = {"required_version", "acknowledged_version", "ok"}
LABEL, LOCATION = "synthetic api block", "fixture api table"
BASKET, KEYS = "synthetic api basket", "synthetic api keys"
API_MARKER = "PII-API-7a1c"
MIGRATION_ENV = "PAM_ALLOW_MIGRATION"


def counts_of(body):
    """The live counts of GET /api/retention ({retention, counts}: coordinator ruling 2)
    or of /api/health's "retention" (flat)."""
    nested = body.get("counts")
    return nested if isinstance(nested, dict) else body


def assert_inference(case, value, *, container, since_ms, container_name=None):
    """Coordinator ruling 5: {container, container_name, since_ms} as a superset."""
    case.assertIsInstance(value, dict, value)
    case.assertEqual(value.get("container"), container, value)
    case.assertEqual(value.get("since_ms"), since_ms, value)
    case.assertIn("container_name", value, value)
    if container_name is not None:
        case.assertEqual(value.get("container_name"), container_name, value)


class Cp4ApiFixture(bootstrap.MemoryApiFixture):
    def setUp(self):
        super().setUp()
        self.client.__exit__(None, None, None)
        self.scripted = identity.Cp3Processor()
        self.serial_ids = 0
        self.phase = 0
        self.client = self.new_client(processor=self.scripted)
        self.login()

    # --- requests with the CP3 internals guard ------------------------------------------
    def check(self, response):
        self.assertEqual(response.headers.get("cache-control"), "no-store", response.request.url.path)
        self.assertNotIn(str(self.root), response.text)
        if "application/json" in response.headers.get("content-type", ""):
            found = cp3_api.identity_internals(response.json())
            self.assertEqual(found, [], f"{response.request.method} {response.request.url.path} exposes identity internals: {found}")
        return response

    def get(self, path, client=None, **params):
        return self.check((client or self.client).get(path, params=params or None))

    def post(self, path, body=None, *, client=None, origin=ORIGIN, raw=None):
        client = client or self.client
        headers = {} if origin is None else {"origin": origin}
        if raw is not None:
            return self.check(client.post(path, content=raw, headers={**headers, "content-type": "application/json"}))
        return self.check(client.post(path, json=body, headers=headers))

    def put(self, path, body, *, client=None, origin=ORIGIN):
        client = client or self.client
        headers = {} if origin is None else {"origin": origin}
        return self.check(client.put(path, json=body, headers=headers))

    def ok(self, response, status=200):
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def safe(self, response, status):
        self.assertEqual(response.status_code, status, response.text)
        self.assert_safe_error(response)
        for marker in cp3_api.LEAK_MARKERS:
            self.assertNotIn(marker, response.text)
        return response.json()

    # --- seeding ---------------------------------------------------------------------------
    def store(self, profile="local"):
        from perception.object_memory import ObjectStore
        return ObjectStore(self.db, profile_id=profile, clock=self.clock)

    def seed(self, observations, *, rest=None, client=None, **packet_kwargs):
        self.serial_ids += 1
        packet_kwargs.setdefault("phase", self.phase)
        self.phase += 1
        packet = fx.episode_packet(self.serial_ids, rest=fx.golden("reference") if rest is None else rest, **packet_kwargs)
        frame = fx.rest_frame_id(packet)
        scripted = []
        for value in observations:
            value = dict(value)
            if value.get("frame_id") is None:
                value["frame_id"] = frame
            scripted.append(value)
        self.scripted.observations[packet["episode_id"]] = scripted
        self.assert_ack(self.post_packet(packet, client=client), packet, status="stored")
        return packet

    def seed_block(self, label=LABEL, location=LOCATION, **kwargs):
        packet = self.seed([fx.observation(None, fx.BLOCK_BBOX, label=label, location=location)], **kwargs)
        items = self.wait_items(minimum=1)
        item = next(i for i in items if i["name"] == label)
        self.assertEqual((item["location_status"], item["identity_status"]), ("placed", "trusted"), item)
        return packet, item

    def post_idle(self, name_or_b64="present", *, client=None, origin=ORIGIN, **kwargs):
        jpeg = fx.golden(name_or_b64) if name_or_b64 in fx.goldens()["frames"] else name_or_b64
        packet = fx.idle_packet(jpeg, **kwargs)
        return packet, self.post("/api/idle", client=client, origin=origin, raw=bootstrap.encode_packet(packet))

    def wait_until(self, predicate, what, timeout=8.0, interval=0.1):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            last = predicate()
            if last:
                return last
            time.sleep(interval)
        self.fail(f"timed out waiting for {what}; last value: {last!r}")

    def item(self, item_id):
        response = self.get(f"/api/items/{item_id}")
        return response.json() if response.status_code == 200 else None

    def advance(self, seconds):
        self.now += seconds
        self.login()

    def retention(self):
        """GET /api/retention -> {retention: row, counts: live counts} (ruling 2)."""
        body = self.ok(self.get("/api/retention"))
        self.assertEqual(set(body), {"retention", "counts"}, body)
        return body

    def retention_row(self):
        return self.retention()["retention"]

    def audit(self, action=None):
        rows = fx.table_rows(self.db, "local_audit", "WHERE profile_id='local' ORDER BY audit_id")
        return [r for r in rows if action is None or r["action"] == action]


class IdleRouteTests(Cp4ApiFixture):
    def test_idle_route_auth_origin_validation_cap_and_ack(self):
        anonymous = self.new_client(processor=self.scripted)
        packet, response = self.post_idle(client=anonymous)
        self.safe(response, 401)
        for origin in (None, "https://evil.invalid", ORIGIN + ".evil.invalid"):
            with self.subTest(origin=origin):
                _, response = self.post_idle(origin=origin)
                self.safe(response, 403)
        for raw in (b"{", b"[]", b'{"schema_version":1,"schema_version":1}', b""):
            with self.subTest(raw=raw):
                body = self.safe(self.post("/api/idle", raw=raw), 400)
                self.assertNotIn("frame_id", body)
        good = fx.idle_packet()
        small = fx.jpeg_b64(fx.cv2.resize(fx.scene_image(), (fx.SCENE_W // 2, fx.SCENE_H // 2)))
        for name, bad in {"dimension mismatch": {**good, "jpeg_b64": small}, "extra field": {**good, "profile_id": "other"},
                          "promoted field": {**good, "promoted": 1}, "missing capture": {k: v for k, v in good.items() if k != "capture"},
                          "bad device": {**good, "device_id": "device"}, "bad energy": {**good, "motion_energy": 2}}.items():
            with self.subTest(case=name):
                body = self.safe(self.post("/api/idle", raw=bootstrap.encode_packet(bad)), 400)
                self.assertNotIn("frame_id", body)
        raw = bootstrap.encode_packet(fx.idle_packet())
        over = raw + b" " * (fx.PLAN["MAX_IDLE_BYTES"] + 1 - len(raw))
        body = self.safe(self.post("/api/idle", raw=over), 413)
        self.assertNotIn("frame_id", body)
        self.assertEqual(fx.table_rows(self.db, "idle_frames"), [], "nothing is retained for a refused body")
        packet, response = self.post_idle(wall_ms=ANCHOR_MS + 60000, motion_energy=0.002)
        ack = self.ok(response)
        self.assertEqual(ack["frame_id"], packet["frame_id"])
        self.assertIs(ack["retained"], True)
        self.assertIsInstance(ack["expires_at_ms"], int)
        self.assertEqual(ack["expires_at_ms"], int(self.now * 1000) + fx.PLAN["IDLE_TTL_MS"])
        self.assertFalse({"jpeg", "jpeg_b64", "packet"} & set(ack), "the ack never echoes the frame")
        rows = fx.table_rows(self.db, "idle_frames")
        self.assertEqual([r["frame_id"] for r in rows], [packet["frame_id"]])
        self.assertEqual(rows[0]["profile_id"], "local")
        # Idle frames are never listed or served: the catalogue stays empty and no image route reaches the cache.
        self.assertEqual(self.catalogue(), [])
        self.assertIn(self.client.get(f"/api/items/{packet['frame_id']}/image").status_code, (400, 404))
        self.assertIn(self.client.get(f"/api/items/x/observations/{packet['frame_id']}/image").status_code, (400, 404))
        # Another profile's app does not see the frame.
        other = self.new_client(profile="other-profile", processor=self.scripted)
        self.login(other)
        self.assertEqual(fx.table_rows(self.db, "idle_frames", "WHERE profile_id='other-profile'"), [])
        self.assertEqual(self.ok(self.get("/api/health", other)).get("retention", {}).get("idle_cached", 0), 0)


class ConsentRouteTests(Cp4ApiFixture):
    def setUp(self):
        super().setUp()
        # A second app client signed in WITHOUT the fixture's automatic acknowledgement,
        # on its own profile (consent is acknowledged per profile).
        self.fresh = self.new_client(profile="fresh-profile", processor=self.scripted)
        self.login(self.fresh, consent=False)

    def test_capture_is_refused_until_the_build_version_is_acknowledged(self):
        from perception.consent import CONSENT_VERSION as BUILD_VERSION, DISCLOSURE_TEXT
        self.assertEqual(BUILD_VERSION, CONSENT_VERSION, "perception.consent.CONSENT_VERSION is the build constant the tests pin")
        state = self.ok(self.get("/api/consent", self.fresh))
        self.assertEqual(set(state), CONSENT_FIELDS | {"disclosure_text"}, state)
        self.assertEqual(state["required_version"], CONSENT_VERSION)
        self.assertIsNone(state["acknowledged_version"])
        self.assertIs(state["ok"], False)
        self.assertEqual(state["disclosure_text"], DISCLOSURE_TEXT)
        self.assertIn("not guaranteed", state["disclosure_text"], "the disclosure is the honest one (ruling 9)")
        self.assertNotIn(str(self.root), state["disclosure_text"])
        health = self.ok(self.get("/api/health", self.fresh))
        self.assertEqual(health.get("consent"), {"required_version": CONSENT_VERSION, "acknowledged_version": None, "ok": False}, health.get("consent"))
        # Episodes and idle frames are refused with 409 consent_required and nothing is retained.
        packet = fx.episode_packet(1, rest=fx.golden("reference"))
        self.scripted.observations[packet["episode_id"]] = [fx.observation(fx.rest_frame_id(packet), fx.BLOCK_BBOX)]
        response = self.post_packet(packet, client=self.fresh)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json().get("code"), "consent_required", response.text)
        self.assertNotIn("ack", response.json())
        self.assert_safe_error(response)
        _, idle = self.post_idle("present", client=self.fresh, wall_ms=ANCHOR_MS + 60000)
        self.assertEqual(idle.status_code, 409, idle.text)
        self.assertEqual(idle.json().get("code"), "consent_required")
        self.assertEqual(fx.table_rows(self.db, "episode_revisions", "WHERE profile_id='fresh-profile'"), [])
        self.assertEqual(fx.table_rows(self.db, "idle_frames", "WHERE profile_id='fresh-profile'"), [])
        self.assertEqual(self.catalogue(self.fresh), [])
        # A wrong, empty or non-string version is 400 and changes nothing.
        for body in ({"acknowledge": "rig-2026-09"}, {"acknowledge": ""}, {"acknowledge": 7}, {}, {"acknowledge": CONSENT_VERSION, "actor": "operator"},
                     {"acknowledge": CONSENT_VERSION.upper()}, {"version": CONSENT_VERSION}):
            with self.subTest(body=body):
                self.safe(self.post("/api/consent", body, client=self.fresh), 400)
        self.assertIs(self.ok(self.get("/api/consent", self.fresh))["ok"], False)
        self.safe(self.post("/api/consent", {"acknowledge": CONSENT_VERSION}, client=self.fresh, origin="https://evil.invalid"), 403)
        anonymous = self.new_client(profile="fresh-profile", processor=self.scripted)
        self.safe(self.post("/api/consent", {"acknowledge": CONSENT_VERSION}, client=anonymous), 401)
        self.safe(self.get("/api/consent", anonymous), 401)
        # The exact version: acknowledged, audited with the actor literal, capture allowed.
        acknowledged = self.ok(self.post("/api/consent", {"acknowledge": CONSENT_VERSION}, client=self.fresh))
        self.assertEqual(acknowledged, {"required_version": CONSENT_VERSION, "acknowledged_version": CONSENT_VERSION, "ok": True})
        self.assertIs(self.ok(self.get("/api/consent", self.fresh))["ok"], True)
        audits = fx.table_rows(self.db, "local_audit", "WHERE profile_id='fresh-profile' AND action LIKE '%consent%'")
        self.assertEqual(len(audits), 1, audits)
        self.assertEqual(json.loads(audits[0]["detail"]).get("actor"), "caregiver_pin")
        self.assert_ack(self.post_packet(packet, client=self.fresh), packet, status="stored")
        self.assertEqual(len(self.wait_items(self.fresh, minimum=1)), 1)
        _, idle = self.post_idle("present", client=self.fresh, wall_ms=ANCHOR_MS + 60000)
        self.assertIs(self.ok(idle)["retained"], True)
        self.assertEqual(self.ok(self.get("/api/retention", self.fresh))["retention"]["acknowledged_version"], CONSENT_VERSION)
        # The other profile's acknowledgement never counted for this one.
        self.assertIs(self.ok(self.get("/api/consent"))["ok"], True)


class RetentionRouteTests(Cp4ApiFixture):
    def test_get_put_ranges_audit_and_health_counts(self):
        body = self.retention()
        row = body["retention"]
        self.assertTrue(fx.RETENTION_FIELDS <= set(row), row)
        self.assertEqual(row["consent_version"], fx.PLAN["CONSENT_VERSION"])
        self.assertEqual((row["episodes_days"], row["idle_hours"], row["landmarks_hours"]), (30, 24, 72), "coordinator ruling 8: 30-day default")
        self.assertEqual(row.get("acknowledged_version"), CONSENT_VERSION)
        self.assertIsNone(row.get("erased_at_ms"))
        counts = body["counts"]
        self.assertTrue(fx.RETENTION_COUNTS <= set(counts), body)
        self.assertEqual({k: counts[k] for k in fx.RETENTION_COUNTS}, {k: 0 for k in fx.RETENTION_COUNTS})
        health = self.ok(self.get("/api/health"))
        self.assertIsInstance(health.get("retention"), dict, health)
        self.assertTrue(fx.RETENTION_COUNTS <= set(counts_of(health["retention"])), health["retention"])
        self.assertEqual(health.get("consent", {}).get("ok"), True, health.get("consent"))
        updated = self.ok(self.put("/api/retention", {"episodes_days": 60}))
        self.assertEqual(updated["episodes_days"], 60)
        self.assertEqual((updated["idle_hours"], updated["landmarks_hours"]), (24, 72))
        self.assertEqual(self.retention_row()["episodes_days"], 60)
        self.assertEqual(fx.read_retention(self.store())["episodes_days"], 60, "persisted in the store")
        audits = [r for r in self.audit() if "retention" in r["action"]]
        self.assertEqual(len(audits), 1, self.audit())
        self.assertEqual(json.loads(audits[0]["detail"]).get("actor"), "caregiver_pin", "the server's role literal, never a request field")
        self.ok(self.put("/api/retention", {"idle_hours": 1, "landmarks_hours": 168}))
        row = self.retention_row()
        self.assertEqual((row["consent_version"], row["idle_hours"], row["landmarks_hours"]), (fx.PLAN["CONSENT_VERSION"], 1, 168))
        # consent_version is a build constant (ruling 3): never a setting.
        for body in ({"episodes_days": 6}, {"episodes_days": 366}, {"idle_hours": 0}, {"idle_hours": 73}, {"landmarks_hours": 0},
                     {"landmarks_hours": 169}, {"episodes_days": "30"}, {"episodes_days": 30.5}, {"episodes_days": True},
                     {"consent_version": "rig-2026-11"}, {"consent_version": fx.PLAN["CONSENT_VERSION"], "episodes_days": 40},
                     {"acknowledged_version": CONSENT_VERSION}, {"erased_at_ms": 0},
                     {"unknown": 1}, {"actor": "operator", "episodes_days": 40}, {"profile_id": "other", "episodes_days": 40}, {}):
            with self.subTest(body=body):
                self.safe(self.put("/api/retention", body), 400)
        self.assertEqual(self.retention_row()["episodes_days"], 60, "a refused update changes nothing")
        self.safe(self.put("/api/retention", {"episodes_days": 40}, origin="https://evil.invalid"), 403)
        self.safe(self.put("/api/retention", {"episodes_days": 40}, origin=None), 403)
        anonymous = self.new_client(processor=self.scripted)
        self.safe(self.put("/api/retention", {"episodes_days": 40}, client=anonymous), 401)
        self.safe(self.get("/api/retention", anonymous), 401)
        self.assertEqual(self.retention_row()["episodes_days"], 60)
        # Live counts move with the cache.
        self.post_idle(wall_ms=ANCHOR_MS + 60000)
        self.assertEqual(counts_of(self.retention())["idle_cached"], 1)
        self.assertEqual(counts_of(self.ok(self.get("/api/health"))["retention"])["idle_cached"], 1)
        other = self.new_client(profile="other-profile", processor=self.scripted)
        self.login(other)
        self.assertEqual(self.ok(self.get("/api/retention", other))["retention"]["episodes_days"], 30, "settings are per profile")


class EraseRouteTests(Cp4ApiFixture):
    def test_erase_item_confirmation_report_and_404_afterwards(self):
        packet = self.seed([fx.observation(None, fx.BLOCK_BBOX, label=API_MARKER + " basket", location=LOCATION),
                            fx.observation(None, [68.0, 48.0, 92.0, 72.0], label=KEYS, location=LOCATION)])
        items = {i["name"]: i for i in self.wait_items(minimum=2)}
        basket, keys = items[API_MARKER + " basket"]["item_id"], items[KEYS]["item_id"]
        self.seed_block(label="synthetic api other", location="fixture api desk")
        other = next(i["item_id"] for i in self.catalogue() if i["name"] == "synthetic api other")
        before = self.catalogue()
        for body, status in (({"confirm": "wrong"}, 409), ({"confirm": keys}, 409), ({"confirm": ""}, 409), ({}, 400),
                             ({"confirm": basket, "extra": 1}, 400), ({"confirm": 7}, 400)):
            with self.subTest(body=body):
                response = self.post(f"/api/items/{basket}/erase", body)
                self.safe(response, status)
                if status == 409:
                    self.assertIsInstance(response.json().get("detail"), str)
        self.safe(self.post(f"/api/items/{basket}/erase", {"confirm": basket}, origin="https://evil.invalid"), 403)
        anonymous = self.new_client(processor=self.scripted)
        self.safe(self.post(f"/api/items/{basket}/erase", {"confirm": basket}, client=anonymous), 401)
        self.safe(self.post("/api/items/no-such-item/erase", {"confirm": "no-such-item"}), 404)
        self.assertEqual(self.catalogue(), before, "nothing is erased by a refused request")
        report = self.ok(self.post(f"/api/items/{basket}/erase", {"confirm": basket}))
        self.assertIsInstance(report, dict)
        self.assertIn("affected_items", report)
        self.assertGreaterEqual(report["affected_items"], 2, "the co-visible keys go with the basket")
        self.assertIs(report.get("forensic_erasure", False), False)
        self.assertNotIn(API_MARKER, json.dumps(report))
        for item_id in (basket, keys):
            for suffix in ("", "/history", "/evidence", "/image"):
                self.safe(self.get(f"/api/items/{item_id}{suffix}"), 404)
        listing = self.get("/api/items")
        self.assertNotIn(API_MARKER, listing.text)
        self.assertEqual([i["item_id"] for i in listing.json()["items"]], [other])
        self.assertEqual(self.get("/api/items", as_of=str(ANCHOR_MS + 2200)).json()["items"], [], "as_of views never resurrect erased items")
        answer = self.ok(self.post("/api/chat", {"text": "where is my " + API_MARKER + " basket"}))
        self.assertEqual(answer["shape"], "abstain")
        self.assertNotIn(API_MARKER, json.dumps(answer))
        self.assertEqual(fx.scan_database(self.db, {"api": API_MARKER}), [])
        # A resend of the erased episode is refused and never processed.
        response = self.post_packet(packet)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIs(response.json()["ack"]["retained"], False)
        self.assertEqual(response.json()["ack"]["status"], "conflict")
        time.sleep(0.3)
        self.assertEqual([i["item_id"] for i in self.catalogue()], [other])
        self.assertIn(self.post(f"/api/items/{basket}/erase", {"confirm": basket}).status_code, (200, 404))
        self.assertEqual(self.get(f"/api/items/{other}").status_code, 200, "an unrelated item is untouched")
        erased = self.audit("erased")
        self.assertGreaterEqual(len(erased), 1)
        self.assertTrue(fx.counts_only(json.loads(erased[0]["detail"])), erased[0]["detail"])
        self.assertNotIn(basket, erased[0]["detail"])
        self.assertIsNone(self.retention_row().get("erased_at_ms"), "erasing one item is not the profile erasure")

    def test_erase_all_needs_the_typed_phrase_and_clears_the_file(self):
        self.seed_block(label=API_MARKER + " block")
        self.seed_block(label="synthetic api second", location="fixture api desk")
        self.assertEqual(len(self.catalogue()), 2)
        self.assertTrue(fx.scan_files(self.db, {"api": API_MARKER}), "control: the marker is in the file bytes")
        good = {"confirm": fx.ERASE_ALL_PHRASE, "pin": bootstrap.PIN}
        # Coordinator ruling 4: the typed phrase AND the PIN. The phrase is checked
        # first (409 confirm_mismatch, no PIN comparison charged), then the PIN under the
        # sign-in rate limit (409 pin_mismatch). Logins are budgeted: one wrong PIN here.
        for body, status, code in (({"confirm": "erase everything", "pin": bootstrap.PIN}, 409, "confirm_mismatch"),
                                   ({"confirm": "ERASE", "pin": bootstrap.PIN}, 409, "confirm_mismatch"), ({"confirm": "", "pin": bootstrap.PIN}, 409, "confirm_mismatch"),
                                   ({}, 400, None), ({"confirm": fx.ERASE_ALL_PHRASE}, 400, None), ({"pin": bootstrap.PIN}, 400, None),
                                   ({**good, "extra": 1}, 400, None), ({"confirm": 7, "pin": bootstrap.PIN}, 400, None), ({"confirm": fx.ERASE_ALL_PHRASE, "pin": 7}, 400, None),
                                   ({"confirm": fx.ERASE_ALL_PHRASE, "pin": "not-the-pin"}, 409, "pin_mismatch")):
            with self.subTest(body=body):
                response = self.safe(self.post("/api/erase-all", body), status)
                if code:
                    self.assertEqual(response.get("code"), code, response)
                    self.assertNotIn(bootstrap.PIN, json.dumps(response))
        self.safe(self.post("/api/erase-all", good, origin="https://evil.invalid"), 403)
        anonymous = self.new_client(processor=self.scripted)
        self.safe(self.post("/api/erase-all", good, client=anonymous), 401)
        self.assertEqual(len(self.catalogue()), 2, "a refused request erases nothing")
        report = self.ok(self.post("/api/erase-all", good))
        self.assertIsInstance(report, dict)
        self.assertIs(report.get("forensic_erasure", False), False)
        self.assertNotIn(API_MARKER, json.dumps(report))
        self.assertNotIn(bootstrap.PIN, json.dumps(report))
        self.assertEqual(self.catalogue(), [])
        self.assertEqual(fx.scan_database(self.db, {"api": API_MARKER}), [])
        hits = fx.scan_files(self.db, {"api": API_MARKER})
        self.assertEqual(hits, [], f"marker bytes survived in the database file or a sidecar: {hits}")
        self.assertEqual(self.ok(self.post("/api/chat", {"text": "where is my " + API_MARKER + " block"}))["shape"], "abstain")
        self.assertEqual(self.get("/api/health").status_code, 200, "the app keeps working on the swapped-in file")
        self.assertEqual({k: counts_of(self.retention())[k] for k in ("idle_cached", "idle_promoted")}, {"idle_cached": 0, "idle_promoted": 0})
        self.assertEqual(self.retention_row().get("erased_at_ms"), int(self.now * 1000))
        # New evidence dated after the erasure is accepted and processed; a capture dated
        # before it is refused with erased_before (ruling 13).
        self.now += 60
        self.seed_block(label="synthetic api after", location="fixture api later", wall_ms=int(self.now * 1000))
        self.assertEqual([i["name"] for i in self.catalogue()], ["synthetic api after"])
        stale = fx.episode_packet(99, rest=fx.golden("reference"), wall_ms=int(self.now * 1000) - 20 * 60 * 1000)
        response = self.post_packet(stale)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json().get("code"), "erased_before", response.text)
        self.assertNotIn("ack", response.json())
        _, idle = self.post_idle("present", wall_ms=int(self.now * 1000) - 20 * 60 * 1000)
        self.assertEqual(idle.status_code, 409, idle.text)
        self.assertEqual(idle.json().get("code"), "erased_before")


class MigrateRouteTests(Cp4ApiFixture):
    def setUp(self):
        super().setUp()
        self.enterContext(patch.dict(os.environ, {}, clear=False))
        os.environ.pop(MIGRATION_ENV, None)
        self.expected = fx.build_v1_fixture(self.db, self.clock)

    def test_dry_run_default_env_gate_and_real_run(self):
        before = fx.row_counts(self.db)
        report = self.ok(self.post("/api/migrate", {}))
        self.assertIs(report.get("dry_run"), True, report)
        self.assertEqual(report["counts"]["observations"], self.expected["observation_rows"], report)
        self.assertEqual(report["counts"]["converted"], self.expected["converted"], report)
        self.assertIn("legacy_media_files", report["counts"])
        self.assertLessEqual(len(report.get("samples", [])), 5)
        for sample in report.get("samples", []):
            self.assertIn(sample.get("location_text"), set(fx.V1_LOCATION_TEXT.values()), sample)
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertEqual(fx.row_counts(self.db), before, "a dry run writes nothing")
        self.assertEqual(self.ok(self.post("/api/migrate", {"dry_run": True}))["counts"], report["counts"])
        for body in ({"dry_run": "false"}, {"dry_run": 0}, {"dry_run": None}, {"actor": "operator"}, {"dry_run": False, "extra": 1}):
            with self.subTest(body=body):
                self.safe(self.post("/api/migrate", body), 400)
        self.safe(self.post("/api/migrate", {"dry_run": False}, origin="https://evil.invalid"), 403)
        anonymous = self.new_client(processor=self.scripted)
        self.safe(self.post("/api/migrate", {}, client=anonymous), 401)
        # A real run is refused without the operator's explicit environment opt-in.
        for value in (None, "0", "true", "yes", " 1"):
            with self.subTest(env=value):
                with patch.dict(os.environ, {} if value is None else {MIGRATION_ENV: value}):
                    if value is None:
                        os.environ.pop(MIGRATION_ENV, None)
                    self.safe(self.post("/api/migrate", {"dry_run": False}), 503)
        self.assertEqual(fx.row_counts(self.db), before, "a refused real run writes nothing")
        self.assertEqual(self.catalogue(), [])
        with patch.dict(os.environ, {MIGRATION_ENV: "1"}):
            real = self.ok(self.post("/api/migrate", {"dry_run": False}))
            self.assertIs(real.get("dry_run"), False, real)
            self.assertEqual(real["counts"], report["counts"])
            self.assertFalse(real.get("status") == "already_migrated")
            migrations = fx.table_rows(self.db, "migrations")
            self.assertEqual(len(migrations), 1)
            self.assertEqual(migrations[0]["actor"], "operator", "coordinator ruling 6: the migration actor literal")
            self.assertEqual(real.get("migration", {}).get("actor"), "operator", real)
            items = self.wait_items(minimum=2)
            self.assertEqual({i["name"] for i in items}, {"Legacy pill bottle", "Legacy glasses"})
            for item in items:
                self.assertEqual(item["identity_status"], "provisional", item)
                self.assertNotEqual(item["location_status"], "placed")
                self.assertIsNone(item["reference_image"])
                # The DTO's image_url is the item's route (never a path); for a migrated
                # item there are no stored bytes, so it answers 404 (noted in the verdict:
                # the plan's "image_url null" is realised as a 404, not a null).
                if item["image_url"] is not None:
                    self.assertEqual(item["image_url"], f"/api/items/{item['item_id']}/image")
                self.assertEqual(self.get(f"/api/items/{item['item_id']}/image").status_code, 404)
                history = self.ok(self.get(f"/api/items/{item['item_id']}/history"))["observations"]
                self.assertTrue(history)
                self.assertTrue(all(row.get("identity_state") == "provisional" for row in history), history)
                self.assertNotIn(str(self.root), json.dumps(history), "no legacy media path leaves the server")
            again = self.ok(self.post("/api/migrate", {"dry_run": False}))
            self.assertTrue(again.get("status") == "already_migrated" or again.get("already_migrated") is True, again)
            self.assertEqual(len(fx.table_rows(self.db, "migrations")), 1)
        answer = self.ok(self.post("/api/chat", {"text": "where is my legacy pill bottle"}))
        self.assertNotEqual(answer["shape"], "confident")


class ItemDtoAndWorkerTests(Cp4ApiFixture):
    def test_items_carry_inference_and_stale_since_ms(self):
        packet, item = self.seed_block()
        self.assertTrue(ITEM_FIELDS <= set(item), item)
        self.assertIsNone(item["inference"])
        self.assertIsNone(item["stale_since_ms"])
        self.assertIs(item["evidence_expired"], False)
        single = self.ok(self.get(f"/api/items/{item['item_id']}"))
        self.assertTrue(ITEM_FIELDS <= set(single), single)
        self.assertIsNone(single["inference"])
        # Containment through the API: the keys inside the basket, then the basket moves.
        nest = self.seed([fx.observation(None, fx.BLOCK_BBOX, label=BASKET, location="fixture api counter", continuity_id="api-basket"),
                          fx.observation(None, [68.0, 48.0, 92.0, 72.0], label=KEYS, location="fixture api counter", continuity_id="api-keys")])
        items = {i["name"]: i for i in self.wait_items(minimum=3)}
        basket, keys = items[BASKET]["item_id"], items[KEYS]["item_id"]
        self.seed([fx.observation(None, fx.BLOCK_BBOX, label=BASKET, location="fixture api shelf", continuity_id="api-basket")])
        inferred = self.wait_until(lambda: next((i for i in self.catalogue() if i["item_id"] == keys and i["location_status"] == "inferred"), None), "the keys to read inferred")
        self.assertEqual(inferred["location_text"], "fixture api shelf")
        assert_inference(self, inferred["inference"], container=basket, since_ms=fx.rest_wall_ms(nest), container_name=BASKET)
        self.assertEqual(set(inferred["inference"]), {"container", "container_name", "since_ms"}, "ruling 5: the DTO whitelist")
        self.assertIsNone(inferred["stale_since_ms"])
        self.assertIs(inferred["evidence_expired"], False)
        self.assertEqual(self.ok(self.get(f"/api/items/{keys}"))["inference"]["container"], basket)
        answer = self.ok(self.post("/api/chat", {"text": "where are my synthetic api keys"}))
        self.assertEqual(answer["shape"], "hedged", answer)
        self.assertEqual(answer["text"], f"I think {KEYS} is with {BASKET}, which I last saw at fixture api shelf.")
        assert_inference(self, answer["members"][0]["inference"], container=basket, since_ms=fx.rest_wall_ms(nest), container_name=BASKET)
        # The whitelist passes nothing else through for a client-shaped forgery: inference is server-derived.
        self.assertEqual(self.post_packet({**packet, "inference": {"container": basket}}).status_code, 400)

    def test_worker_reobserves_expires_and_applies_retention_with_the_fixture_clock(self):
        packet, item = self.seed_block()
        base = fx.rest_wall_ms(packet)
        ident = item["item_id"]
        # A negative idle frame -> stale / negative_reobservation through the worker alone.
        gone, response = self.post_idle("gone", wall_ms=base + 60000)
        self.ok(response)
        self.now += 6 * 60
        stale = self.wait_until(lambda: (lambda i: i if i and i["stale_reason"] == "negative_reobservation" else None)(self.item(ident)), "negative re-observation by the worker")
        self.assertEqual(stale["location_status"], "stale")
        self.assertEqual(stale["stale_since_ms"], fx.idle_wall_ms(gone))
        self.assertEqual(stale["location_text"], LOCATION)
        answer = self.ok(self.post("/api/chat", {"text": "where is my synthetic api block"}))
        self.assertEqual(answer["shape"], "hedged", answer)
        self.assertEqual(answer["members"][0]["stale_reason"], "negative_reobservation")
        self.assertEqual(answer["members"][0]["stale_since_ms"], fx.idle_wall_ms(gone))
        # A positive frame -> fresh again, promoted, observed_at advanced; the promoted frame serves as evidence.
        present, response = self.post_idle("present", wall_ms=base + 120000)
        self.ok(response)
        self.now += 6 * 60
        fresh = self.wait_until(lambda: (lambda i: i if i and i["location_status"] == "placed" and i["observed_at_ms"] == fx.idle_wall_ms(present) else None)(self.item(ident)), "positive re-observation by the worker")
        self.assertIsNone(fresh["stale_reason"])
        self.assertIsNone(fresh["stale_since_ms"])
        counts = counts_of(self.retention())
        self.assertEqual((counts["idle_cached"], counts["idle_promoted"]), (1, 1), counts)
        evidence = self.ok(self.get(f"/api/items/{ident}/evidence"))["observations"]
        self.assertEqual(len(evidence), 2)
        newest = max(evidence, key=lambda r: r["observed_at_ms"])
        self.assertEqual(newest["outcome"], "sighted")
        self.assertEqual(newest["identity_status"], "provisional")
        image = self.get(newest["image_url"])
        self.assertEqual(image.status_code, 200, image.text)
        self.assertEqual(image.content, fx.golden_bytes("present"))
        # 25 h later the unpromoted frame expires through the worker; the promoted one stays.
        self.advance(25 * 3600)
        self.wait_until(lambda: counts_of(self.retention())["idle_cached"] == 0 or None, "idle expiry by the worker")
        self.assertEqual(counts_of(self.retention())["idle_promoted"], 1)
        self.assertEqual(self.get(newest["image_url"]).status_code, 200, "a promoted frame never expires")
        # 31 days later (ruling 8: a 30-day default) the placement packet expires: item listed, image gone.
        self.advance(31 * 86400)
        self.wait_until(lambda: counts_of(self.retention())["revisions_expired"] >= 1 or None, "packet expiry by the worker")
        expired = self.item(ident)
        self.assertIsNotNone(expired)
        self.assertEqual(expired["location_text"], LOCATION)
        self.assertIs(expired["evidence_expired"], True, "the 'evidence image expired' marker")
        self.assertIsNone(expired["reference_image"])
        self.assertEqual(self.get(f"/api/items/{ident}/history").status_code, 200)
        placement = next(r for r in self.ok(self.get(f"/api/items/{ident}/evidence"))["observations"] if r["observed_at_ms"] == base)
        self.assertEqual(self.get(placement["image_url"]).status_code, 404, "the expired packet's image is gone")
        self.assertEqual(len(self.ok(self.get(f"/api/items/{ident}/evidence"))["observations"]), 2, "observations stay")

    def test_worker_reduces_landmarks_after_72_hours(self):
        import test_cp4_retention as retention
        samples, expected = retention.landmark_samples(1)
        packet = self.seed([fx.observation(None, fx.BLOCK_BBOX, label=LABEL, location=LOCATION)], landmarks=samples, capture_mode="automatic")
        self.wait_items(minimum=1)
        received = fx.table_rows(self.db, "episode_revisions", "WHERE episode_id=?", (packet["episode_id"],))[0]["received_at_ms"]
        self.advance(73 * 3600)
        self.wait_until(lambda: counts_of(self.retention())["landmarks_reduced"] >= 1 or None, "landmark reduction by the worker")
        row = fx.table_rows(self.db, "episode_revisions", "WHERE episode_id=?", (packet["episode_id"],))[0]
        self.assertIsNotNone(row["reduced_ms"])
        self.assertGreaterEqual(row["reduced_ms"], received + 73 * HOUR_MS)
        stored = json.loads(bytes(row["packet"]))
        self.assertEqual(stored["landmarks"], [])
        self.assertEqual([s["hands"][0]["basis"] for s in stored["landmark_summary"]], [s["hands"][0]["basis"] for s in expected])
        self.assertNotIn(retention.RAW_MARK.encode(), bytes(row["packet"]))
        item = self.catalogue()[0]
        self.assertEqual(self.get(item["image_url"]).status_code, 200, "images are untouched by reduction")
        self.assertEqual(self.get(f"/api/items/{item['item_id']}/history").status_code, 200)

    def test_new_routes_are_known_to_the_middleware_and_everything_else_stays_retired(self):
        anonymous = self.new_client(processor=self.scripted)
        for method, path in (("POST", "/api/idle"), ("GET", "/api/retention"), ("PUT", "/api/retention"), ("GET", "/api/consent"), ("POST", "/api/consent"),
                             ("POST", "/api/erase-all"), ("POST", "/api/migrate"), ("POST", "/api/items/x/erase")):
            with self.subTest(path=path):
                response = anonymous.request(method, path, headers={"origin": ORIGIN})
                self.assertEqual(response.status_code, 401, f"{method} {path} must be a known protected route: {response.text}")
        for path in ("/api/idle-frames", "/api/erase", "/api/retention/counts"):
            with self.subTest(path=path):
                self.assertIn(self.client.get(path).status_code, (404, 410))


if __name__ == "__main__":
    unittest.main(verbosity=2)
