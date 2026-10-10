"""CP5 acceptance, HTTP level: telemetry and coverage routes, health coverage, the
notices page and the chat Answer DTO.

    python3 -B server/test_cp5_api.py -v

Authority: docs/BUILD_PLAN.md "CP5 in detail":

  POST /api/telemetry               protected, origin-checked, 64 KiB cap (413), 400 for an
                                    unknown key or anything malformed, 200 -> a small ack
  GET  /api/coverage?day=YYYY-MM-DD protected; 400 for a bad day; the seven coverage keys
  GET  /api/health                  carries "coverage" for today (the same seven keys)
  GET  /notices                     public (no session), renders server/notices.json: every
                                    component with its version, licence and source URL;
                                    the CUTE attribution only when such a calibration exists
  POST /api/chat                    present_answer whitelists exactly the Answer keys (shape,
                                    text, members, reference_image, target_indicated,
                                    capture_time_ms, identity_status, location_status, room,
                                    index_pending, basis; question/options/
                                    unresolved_observation_id for clarify/group) and nothing
                                    numeric from identity internals (CP3 ruling 7 guard)

Reuses test_cp4_api.Cp4ApiFixture (bootstrap guards, injected clock, scripted processor,
the internals guard on every response).
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
import test_memory_bootstrap as bootstrap  # noqa: E402
import test_cp3_api as cp3_api  # noqa: E402
import test_cp3_identity as identity  # noqa: E402
import test_cp4_api as cp4_api  # noqa: E402
import test_cp4_fixtures as fx  # noqa: E402
import test_cp5_fixtures as cp5  # noqa: E402
from test_cp5_fixtures import (ANCHOR_MS, COUNTER_KEYS, COVERAGE_KEYS, DAY_MS, HOUR_MS, NOTICE_KEYS, REQUIRED_COMPONENTS,  # noqa: E402
                               check_answer, encode, expected_coverage, packet_for_day, telemetry_packet, utc_day)

ORIGIN = bootstrap.ORIGIN
TODAY = utc_day(ANCHOR_MS)
YESTERDAY = utc_day(ANCHOR_MS - DAY_MS)
LABEL, LOCATION = "synthetic api block", "fixture api table"
ASK = "where is my synthetic api block"


class Cp5ApiFixture(cp4_api.Cp4ApiFixture):
    def coverage_body(self, body):
        self.assertIsInstance(body, dict, body)
        self.assertTrue(COVERAGE_KEYS <= set(body), sorted(COVERAGE_KEYS - set(body)))
        for key, value in body.items():
            if key == "day":
                self.assertRegex(value, r"^\d{4}-\d{2}-\d{2}$")
                continue
            self.assertIsInstance(value, int, key)
            self.assertNotIsInstance(value, bool, key)
            self.assertGreaterEqual(value, 0, key)
        return {key: body[key] for key in COVERAGE_KEYS}

    def post_telemetry(self, packet=None, *, raw=None, client=None, origin=ORIGIN):
        return self.post("/api/telemetry", client=client, origin=origin, raw=encode(packet) if raw is None else raw)

    def chat(self, text, client=None, **extra):
        body = self.ok(self.post("/api/chat", {"text": text, **extra}, client=client))
        return check_answer(self, body)


class TelemetryRouteTests(Cp5ApiFixture):
    def test_auth_origin_validation_cap_and_ack(self):
        anonymous = self.new_client(processor=self.scripted)
        self.safe(self.post_telemetry(telemetry_packet(), client=anonymous), 401)
        for origin in (None, "https://evil.invalid", ORIGIN + ".evil.invalid"):
            with self.subTest(origin=origin):
                self.safe(self.post_telemetry(telemetry_packet(), origin=origin), 403)
        good = telemetry_packet()
        for name, bad in {"extra key": {**good, "profile_id": "other"}, "free text": {**good, "note": "kitchen"},
                          "unknown counter": {**good, "counters": {**good["counters"], "frames_lost": 1}},
                          "text counter": {**good, "counters": {**good["counters"], "frames_captured": "many"}},
                          "vector": {**good, "timing": {**good["timing"], "infer_ms_p50": [1.0] * 64}},
                          "negative": {**good, "window_ms": -1}, "missing settings": {k: v for k, v in good.items() if k != "settings"}}.items():
            with self.subTest(case=name):
                body = self.safe(self.post_telemetry(bad), 400)
                self.assertNotIn("counters", body)
        for raw in (b"{", b"[]", b"", b'{"schema_version":1,"schema_version":1}'):
            with self.subTest(raw=raw):
                self.safe(self.post("/api/telemetry", raw=raw), 400)
        raw = encode(good)
        over = raw + b" " * (cp5.MAX_TELEMETRY_BYTES + 1 - len(raw))
        self.safe(self.post("/api/telemetry", raw=over), 413)
        self.assertEqual(fx.table_rows(self.db, "frame_counters"), [], "nothing is stored for a refused body")
        ack = self.ok(self.post_telemetry(good))
        self.assertIsInstance(ack, dict)
        self.assertNotIn("counters", ack, "the ack never echoes the body")
        self.assertFalse(any(isinstance(v, str) and len(v) > 80 for v in ack.values()), ack)
        rows = fx.table_rows(self.db, "frame_counters")
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual((rows[0]["profile_id"], rows[0]["session_id"]), ("local", good["session_id"]))
        # Resent: still one row (idempotent), still 200.
        self.ok(self.post_telemetry(good))
        self.assertEqual(len(fx.table_rows(self.db, "frame_counters")), 1)
        # GET is not a telemetry verb; a retired-looking path stays retired.
        self.assertIn(self.client.get("/api/telemetry").status_code, (404, 405, 410))

    def test_coverage_route_validation_shape_and_health(self):
        anonymous = self.new_client(processor=self.scripted)
        self.safe(self.get("/api/coverage", anonymous, day=TODAY), 401)
        for day in ("2026-13-01", "2026-10-1", "20261001", "", "2026-02-30", "yesterday", "2026-10-01T00", "x" * 11):
            with self.subTest(day=day):
                self.safe(self.get("/api/coverage", day=day), 400)
        default = self.ok(self.get("/api/coverage"))
        self.assertEqual(default.get("day"), TODAY, "no day means today by the app's clock (ruling 7)")
        zero = self.coverage_body(self.ok(self.get("/api/coverage", day=TODAY)))
        self.assertEqual(zero, {key: 0 for key in COVERAGE_KEYS})
        packets = [packet_for_day(TODAY, offset_ms=HOUR_MS, session=bootstrap.SESSION, window_ms=60000, counters={"gap_ms": 2000, "gaps": 1, "episodes_finished": 1, "packets_sent": 1, "idle_sent": 2}),
                   packet_for_day(TODAY, offset_ms=2 * HOUR_MS, session=cp5.OTHER_SESSION, window_ms=30000, counters={"episodes_finished": 2, "packets_sent": 2, "idle_dropped": 1}),
                   packet_for_day(YESTERDAY, offset_ms=2 * HOUR_MS, session=cp5.OTHER_SESSION, window_ms=60000, counters={"episodes_finished": 7, "packets_sent": 7})]
        for packet in packets:
            self.ok(self.post_telemetry(packet))
        today = self.coverage_body(self.ok(self.get("/api/coverage", day=TODAY)))
        self.assertEqual(today, expected_coverage(packets, TODAY))
        self.assertEqual(today["sessions"], 2)
        self.assertEqual(today["gap_ms"], 2000, "coverage loss is reported, never hidden")
        self.assertEqual(self.coverage_body(self.ok(self.get("/api/coverage", day=YESTERDAY))), expected_coverage(packets, YESTERDAY))
        self.assertEqual(self.coverage_body(self.ok(self.get("/api/coverage", day=YESTERDAY)))["episodes"], 7)
        self.assertEqual(self.coverage_body(self.ok(self.get("/api/coverage", day=utc_day(ANCHOR_MS - 3 * DAY_MS)))), {key: 0 for key in COVERAGE_KEYS})
        health = self.ok(self.get("/api/health"))
        self.assertIn("coverage", health, health.keys())
        self.assertEqual(self.coverage_body(health["coverage"]), today, "health carries today's coverage")
        # The store's own arithmetic agrees with the route.
        self.assertEqual({k: self.store().coverage(TODAY)[k] for k in COVERAGE_KEYS}, today)
        # Another profile sees zero.
        other = self.new_client(profile="other-profile", processor=self.scripted)
        self.login(other)
        self.assertEqual(self.coverage_body(self.ok(self.get("/api/coverage", other, day=TODAY))), {key: 0 for key in COVERAGE_KEYS})
        # Coordinator ruling 3 / pin b: erase-all removes the day rollups and maintenance
        # counters too; the report counts both and the day reads zeros afterwards.
        report = self.ok(self.post("/api/erase-all", {"confirm": fx.ERASE_ALL_PHRASE, "pin": bootstrap.PIN}))
        self.assertIs(report.get("erased"), True, report)
        for key in ("coverage_days", "maintenance_counters"):
            self.assertIn(key, report["counts"], report)
            self.assertIsInstance(report["counts"][key], int)
        self.assertGreaterEqual(report["counts"]["coverage_days"], 1, "today's rollup existed")
        self.assertEqual(self.coverage_body(self.ok(self.get("/api/coverage", day=TODAY))), {key: 0 for key in COVERAGE_KEYS})
        self.assertEqual(self.coverage_body(self.ok(self.get("/api/coverage", day=YESTERDAY))), {key: 0 for key in COVERAGE_KEYS})
        self.assertEqual(self.store().coverage(TODAY).get("source"), "none")
        self.assertEqual(fx.table_rows(self.db, "frame_counters", "WHERE profile_id='local'"), [])
        self.assertEqual(fx.table_rows(self.db, "coverage_days", "WHERE profile_id='local'"), [])


class NoticesTests(Cp5ApiFixture):
    def test_notices_json_entries_have_the_five_keys_and_cover_the_register(self):
        entries = cp5.load_notices()
        self.assertGreaterEqual(len(entries), len(REQUIRED_COMPONENTS))
        names = []
        for entry in entries:
            with self.subTest(component=entry.get("component")):
                self.assertEqual(set(entry), NOTICE_KEYS, entry.keys())
                for key in NOTICE_KEYS:
                    self.assertIsInstance(entry[key], str, key)
                    self.assertTrue(entry[key].strip(), f"{key} is empty for {entry.get('component')}")
                self.assertIn(entry["condition"], cp5.NOTICE_CONDITIONS, "ruling 6: a closed condition vocabulary")
                self.assertRegex(entry["source_url"], r"^https://", "a primary source URL")
                self.assertGreaterEqual(len(entry["notice_text"]), 40, "the notice text is the licence text or statement, not a label")
                names.append(entry["component"])
        cute = [e for e in entries if e["condition"] == "calibration:cute"]
        self.assertEqual(len(cute), 1, "exactly one CUTE attribution entry, conditional on a calibration")
        self.assertIn(cp5.CUTE_URL, cute[0]["source_url"] + cute[0]["notice_text"])
        for key, pattern in REQUIRED_COMPONENTS.items():
            with self.subTest(required=key):
                self.assertTrue(any(re.search(pattern, name, re.IGNORECASE) for name in names), f"{key} is missing from server/notices.json: {names}")
        # Apache-2.0 NOTICE obligation: the MediaPipe entry reproduces the Apache licence text.
        mediapipe = [e for e in entries if re.search(REQUIRED_COMPONENTS["mediapipe"], e["component"], re.IGNORECASE)]
        self.assertTrue(any("Apache" in e["licence"] for e in mediapipe), mediapipe)
        self.assertTrue(any("Apache License" in e["notice_text"] and "Version 2.0" in e["notice_text"] for e in mediapipe), "the Apache-2.0 text travels with MediaPipe")
        for entry in entries:
            if entry["licence"] == "MIT":
                self.assertIn("Permission is hereby granted", entry["notice_text"], entry["component"])
            if entry["licence"].startswith("BSD"):
                self.assertIn("Redistributions of source code", entry["notice_text"], entry["component"])
        # Nothing personal and nothing from this checkout in the notices file.
        self.assertNotIn(str(ROOT), json.dumps(entries))

    def test_notices_page_is_public_and_lists_every_component(self):
        anonymous = self.new_client(processor=self.scripted)
        response = anonymous.get("/notices")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("text/html", response.headers.get("content-type", ""))
        self.assertNotIn(str(self.root), response.text)
        self.assertNotIn("pam_session", response.headers.get("set-cookie", ""), "the page opens no session")
        page = response.text
        import html
        for entry in cp5.load_notices():
            with self.subTest(component=entry["component"]):
                if entry["condition"] == "calibration:cute":
                    self.assertNotIn(entry["component"], page, "ruling 6: no CUTE entry without an approved cute calibration")
                    self.assertNotIn(cp5.CUTE_URL, page)
                    continue
                self.assertIn(html.escape(entry["component"], quote=True), page)
                self.assertIn(html.escape(entry["licence"], quote=True), page)
                self.assertIn(html.escape(entry["source_url"], quote=True), page)
                self.assertIn(html.escape(entry["version"], quote=True), page)
                if entry["condition"] == "always":
                    # The notice text is rendered as escaped paragraphs / <pre> blocks: its
                    # first non-empty line and its copyright line must be on the page.
                    lines = [line.strip() for line in entry["notice_text"].split("\n") if line.strip()]
                    self.assertIn(html.escape(lines[0], quote=True), page, "an always-on component carries its notice text")
                    copyright_lines = [line for line in lines if "copyright" in line.lower()]
                    if copyright_lines:
                        self.assertIn(html.escape(copyright_lines[0], quote=True), page, entry["component"])
                else:
                    # A provisioned or served component this test server lacks renders as a
                    # heading with its availability line (ruling 6): the hand/identity models
                    # and the icon set are not provisioned here.
                    needle = "present on this server: no" if entry["condition"].startswith("provisioned:") else "served by this server: no"
                    self.assertIn(needle, page.lower(), entry["component"])
        self.assertNotIn("<script", page.lower(), "a plain page")
        # The CSP and content-type headers still apply; the page is not an API route (no 401/410).
        self.assertEqual(response.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(self.client.get("/notices").status_code, 200, "signed in or not, the same page")

    def test_cute_attribution_follows_an_approved_calibration(self):
        page = self.client.get("/notices").text
        self.assertNotIn(cp5.CUTE_URL, page, "no CUTE-derived calibration exists: no attribution is shown")
        store = self.store()
        store.register_calibration(identity.calibration_record("cp5-cute-derived", quantile=identity.WIDE_Q, source="cute"))
        page = self.client.get("/notices").text
        self.assertNotIn(cp5.CUTE_URL, page, "ruling 6: a registered but unapproved cute calibration shows nothing")
        store.approve_calibration("cp5-cute-derived", identity.ACTOR)
        page = self.client.get("/notices").text
        self.assertIn(cp5.CUTE_URL, page, "an APPROVED CUTE-derived calibration makes the CC BY 4.0 attribution appear")
        self.assertIn("Creative Commons Attribution 4.0", page)
        self.assertIn("Kotar", page)
        anonymous = self.new_client(processor=self.scripted)
        self.assertIn(cp5.CUTE_URL, anonymous.get("/notices").text, "the same page without a session")


class ChatAnswerDtoTests(Cp5ApiFixture):
    def test_present_answer_whitelists_the_answer_keys_and_no_internals(self):
        no_match = self.chat("where is my unseen thing")
        self.assertEqual(set(no_match), cp5.ANSWER_KEYS)
        self.assertEqual(no_match["shape"], "abstain")
        self.assertEqual(no_match["basis"], ["no_evidence"])
        self.assertEqual(no_match["room"], cp5.ROOM_UNKNOWN)
        packet, block = self.seed_block()
        confident = self.chat(ASK)
        self.assertEqual(set(confident), cp5.ANSWER_KEYS)
        self.assertEqual(confident["shape"], "confident")
        self.assertEqual(confident["basis"], ["trusted_match", "placed"])
        self.assertEqual(confident["reference_image"], {"frame_id": fx.rest_frame_id(packet), "bbox": fx.BLOCK_BBOX})
        self.assertIs(confident["target_indicated"], True)
        self.assertEqual(confident["capture_time_ms"], fx.rest_wall_ms(packet))
        self.assertEqual(confident["identity_status"], "matched_trusted")
        self.assertEqual(confident["location_status"], "placed")
        member = confident["members"][0]
        self.assertTrue(cp4_api.ITEM_FIELDS <= set(member), sorted(cp4_api.ITEM_FIELDS - set(member)))
        self.assertEqual(member["image_url"], f"/api/items/{block['item_id']}/image")
        self.assertNotIn("last_event_ms", member, "store internals never cross the boundary")
        self.assertEqual(cp3_api.identity_internals(confident), [])
        # A forged field in the store's answer would not pass: the DTO is a whitelist.
        self.seed_block(label=LABEL + " spare", location="fixture api desk")
        clarify = self.chat(ASK)
        self.assertEqual(set(clarify) - {"unresolved_observation_id"}, cp5.CLARIFY_KEYS)
        self.assertEqual(clarify["shape"], "clarify")
        self.assertEqual(clarify["basis"], ["name_ambiguous"])
        self.assertIsNone(clarify["reference_image"])
        self.assertEqual([o["item_id"] for o in clarify["options"]], [m["item_id"] for m in clarify["members"]])
        # Aged by the clock alone: hedged with the aged basis, then abstain with no image.
        self.advance(25 * 3600)
        spare = self.chat("where is my synthetic api block spare")
        self.assertEqual(spare["shape"], "hedged")
        self.assertIn("aged", spare["basis"])
        self.assertIsNotNone(spare["reference_image"])
        self.advance(7 * 86400)
        week = self.chat("where is my synthetic api block spare")
        self.assertEqual(week["shape"], "abstain")
        self.assertIn("aged", week["basis"])
        self.assertEqual(week["members"], [])
        # as_of replays the confident answer with the same key set.
        replayed = self.chat("where is my synthetic api block spare", as_of=fx.rest_wall_ms(packet) + 20000)
        self.assertEqual(replayed["shape"], "confident")
        self.assertEqual(set(replayed), cp5.ANSWER_KEYS)

    def test_group_answer_dto_carries_provenance_and_the_parked_observation(self):
        # One app only (its worker claims every job): the fixture's app is closed and a
        # second one with the synthetic embedder injected serves this test; the
        # lookalikes are seeded over its API exactly as the CP3 API suite does.
        import importlib
        self.client.__exit__(None, None, None)
        module = importlib.import_module("server.app")
        app = module.create_app(database_path=self.db, profile_id="local", processor=self.scripted, clock=self.clock, auth_pin=bootstrap.PIN,
                                models_dir=self.root / "models", licence_register=self.root / "LICENSES.md", embedder=identity.SyntheticEmbedder())
        self.apps.append(app)
        from fastapi.testclient import TestClient
        client = TestClient(app, base_url=ORIGIN, raise_server_exceptions=False)
        self.enterContext(client)
        self.login(client)
        store = self.store()
        store.register_calibration(identity.calibration_record())
        store.approve_calibration(identity.CAL_WIDE, identity.ACTOR)
        serial = 900
        def sight(regions, locations):
            nonlocal serial
            serial += 1
            packet = identity.cp3_packet(serial, rest=regions, phase=serial - 900)
            frame = identity.rest_frame_id(packet)
            self.scripted.observations[packet["episode_id"]] = [identity.cp3_observation(frame, reg, location=locations[i]) for i, reg in enumerate(regions)]
            self.assert_ack(self.post_packet(packet, client=client), packet, status="stored")
        sight([identity.region(identity.LEFT, 0), identity.region(identity.RIGHT, 1)], ["fixture shelf left", "fixture shelf right"])
        self.wait_items(client, minimum=2)
        sight([identity.region(identity.MIDDLE, 0)], ["fixture shelf middle"])
        items = self.wait_until(lambda: (lambda rows: rows if rows and all(i["identity_status"] == "ambiguous" for i in rows) else None)(self.wait_items(client, minimum=2)), "both glasses ambiguous")
        self.assertEqual(len(items), 2, items)
        group = self.chat(identity.ASK_GLASSES, client=client)
        self.assertEqual(group["shape"], "group")
        self.assertEqual(set(group), cp5.GROUP_KEYS)
        self.assertEqual(group["identity_status"], "group")
        self.assertIsNone(group["reference_image"])
        self.assertIs(group["target_indicated"], False)
        self.assertRegex(group["unresolved_observation_id"], r"^[0-9a-f]{64}$")
        for member in group["members"]:
            self.assertEqual(set(member["provenance"]), {"observation_id", "identity_status"})
            self.assertEqual(member["identity_status"], "ambiguous")
            self.assertEqual(cp3_api.identity_internals(member), [])
        self.assertEqual(cp3_api.identity_internals(group), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
