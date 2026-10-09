"""CP3 acceptance, HTTP level: the identity routes, the group answer over /api/chat and
the physical_instance_recognition capability gate.

    python3 -B server/test_cp3_api.py -v

Reuses bootstrap.MemoryApiFixture (temp DB, PIN, egress and private-file guards) and
test_cp3_identity's synthetic embedder, tagged frames and fixture processor, and
builds its own apps with create_app(..., embedder=<SyntheticEmbedder>, models_dir=
<temp>, licence_register=<temp file>) so nothing under phone/assets/models or docs/
is read. The identity "model file" is synthetic bytes under the manifest name
dinov2_vits14.onnx: no model is downloaded, loaded or run; the injected embedder is
what decides identity. Routes under test (docs/BUILD_PLAN.md, CP3 "Server"):

  POST /api/items/{id}/link {other_item_id}            -> Item (409 on cannot-link)
  POST /api/items/{id}/observations/{obs}/unlink       -> Item (the new one)
  GET  /api/items/{id}/evidence                        -> {observations: [...]}
  GET  /api/items/{id}/observations/{obs}/image        -> that observation's keyframe
  POST /api/chat                                       -> shape "group" passed through
  capability physical_instance_recognition on /api/health and /api/items, from the
  CP2 policy pattern: manifest asset dinov2_vits14.onnx provisioned + licence row
  + PAM_ENABLE_IDENTITY_MODEL=1.
"""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
import test_memory_bootstrap as bootstrap  # noqa: E402
import test_cp3_identity as identity  # noqa: E402

ORIGIN = bootstrap.ORIGIN
PIN = bootstrap.PIN
ITEM_FIELDS = bootstrap.ITEM_FIELDS
CAPABILITY = identity.CAPABILITY
HAND = "automatic_hand_recognition"
ENV = "PAM_ENABLE_IDENTITY_MODEL"
MODEL = "dinov2_vits14.onnx"
MODEL_VERSION = "vits14-export-1"
SHA = "fedcba9876543210" * 4
EVIDENCE_API_FIELDS = {"observation_id", "observed_at_ms", "reference_image", "image_url", "identity_status", "outcome", "location_text"}
LEAK_MARKERS = ("Traceback", "ValueError", "KeyError", "sqlite", ".py")
# Coordinator ruling 7: no route ever returns identity internals: a key named like a
# vector, embedding, bank or score list, or a long numeric list (a 384-d vector).
INTERNAL_KEY = re.compile(r"vector|embedding|bank|scores", re.IGNORECASE)
MAX_NUMERIC_LIST = 32
# Coordinator ruling 1: without an approved calibration for the loaded embedder the
# capability is False with the store's own reason.
UNCALIBRATED_REASON = "no approved calibration: identity stays provisional"
region, LEFT, MIDDLE, RIGHT = identity.region, identity.LEFT, identity.MIDDLE, identity.RIGHT
GLASSES, BOTTLE = identity.GLASSES, identity.BOTTLE


def identity_internals(value, path="$"):
    """Paths inside a JSON value that name identity internals (ruling 7)."""
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and INTERNAL_KEY.search(key):
                found.append(f"{path}.{key}")
            found.extend(identity_internals(child, f"{path}.{key}"))
    elif isinstance(value, list):
        if len(value) > MAX_NUMERIC_LIST and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
            found.append(f"{path}[numeric list of {len(value)}]")
        for index, child in enumerate(value):
            found.extend(identity_internals(child, f"{path}[{index}]"))
    return found


class IdentityApiFixture(bootstrap.MemoryApiFixture):
    def setUp(self):
        super().setUp()
        # The bootstrap app's worker would process this database's jobs with the
        # bootstrap processor (context only); the app under test is the one below.
        self.client.__exit__(None, None, None)
        self.embedder = identity.SyntheticEmbedder()
        self.cp3 = identity.Cp3Processor()
        self.phase = 0
        self.models_dir = self.root / "models"
        self.models_dir.mkdir()
        self.register = self.root / "LICENSES.md"
        self.client = self.identity_client()

    # --- app construction --------------------------------------------------------------
    def identity_client(self, *, embedder="synthetic", processor="cp3", database=None, profile="local", login=True):
        """create_app with the test seams: the synthetic embedder (or None / omitted
        with embedder="absent"), the CP3 fixture processor, temp models dir and register."""
        module = importlib.import_module("server.app")
        kwargs = dict(database_path=self.db if database is None else database, profile_id=profile,
                      processor=self.cp3 if processor == "cp3" else processor, clock=self.clock, auth_pin=PIN,
                      models_dir=self.models_dir, licence_register=self.register)
        if embedder != "absent":
            kwargs["embedder"] = self.embedder if embedder == "synthetic" else embedder
        app = module.create_app(**kwargs)
        self.apps.append(app)
        client = TestClient(app, base_url=ORIGIN, raise_server_exceptions=False)
        self.enterContext(client)
        if login:
            self.login(client)
        return client

    # --- model provisioning (CP2 pattern with the identity asset) -----------------------
    def write_manifest(self, names=(MODEL,)):
        entries = [{"name": name, "version": MODEL_VERSION, "sha256": SHA, "licence": "Apache-2.0",
                    "url": "https://example.invalid/" + name, "fetched_at": "2026-10-09T00:00:00Z"} for name in names]
        (self.models_dir / "MANIFEST.json").write_text(json.dumps({"assets": entries}), encoding="utf-8")

    def write_model_file(self):
        (self.models_dir / MODEL).write_bytes(b"SYNTHETIC-ONNX-BYTES-NOT-A-MODEL")

    def write_register(self, text=None):
        rows = f"| {MODEL} | Apache-2.0 | synthetic | status: VERIFIED-COMMERCIAL |\n" if text is None else text
        self.register.write_text("# Synthetic licence register (tester fixture, not docs/LICENSES.md)\n" + rows, encoding="utf-8")

    def provision(self, *, register=True, env=True):
        self.write_manifest()
        self.write_model_file()
        if register:
            self.write_register()
        if env:
            self.enterContext(patch.dict(os.environ, {ENV: "1"}))

    # --- seeding through the API ---------------------------------------------------------
    def store(self, profile="local"):
        from perception.object_memory import ObjectStore
        return ObjectStore(self.db, profile_id=profile, clock=self.clock)

    def seed_calibration(self, calibration_id=identity.CAL_WIDE, *, approve=True, quantile=identity.WIDE_Q):
        store = self.store()
        store.register_calibration(identity.calibration_record(calibration_id, quantile=quantile))
        if approve:
            store.approve_calibration(calibration_id, identity.ACTOR)

    def post(self, regions, *, client=None, labels=None, locations=None, calibration_id=identity.CAL_WIDE, extra=None):
        client = self.client if client is None else client
        packet = identity.cp3_packet(next(self.serial), rest=regions, phase=self.phase)
        self.phase += 1
        frame = identity.rest_frame_id(packet)
        labels = [GLASSES] * len(regions) if labels is None else labels
        locations = [f"fixture shelf {i}" for i in range(len(regions))] if locations is None else locations
        self.cp3.observations[packet["episode_id"]] = [
            identity.cp3_observation(frame, reg, label=labels[i], location=locations[i], calibration_id=calibration_id, **(extra or {}))
            for i, reg in enumerate(regions)]
        self.assert_ack(self.post_packet(packet, client=client), packet, status="stored")
        return packet

    def seed_lookalike_pair(self):
        """A and B (tags 0 and 1) first seen together, then a lone sighting of tag 0:
        both become ambiguous lookalikes. Returns (a, b) catalogue items."""
        self.seed_calibration()
        self.post([region(LEFT, 0), region(RIGHT, 1)], locations=["fixture shelf left", "fixture shelf right"])
        items = sorted(self.wait_items(minimum=2), key=lambda i: i["location_text"] or "")
        self.assertEqual([i["location_text"] for i in items], ["fixture shelf left", "fixture shelf right"], items)
        a, b = items
        self.post([region(MIDDLE, 0)], locations=["fixture shelf middle"])
        self.wait_processed()
        return a, b

    def wait_processed(self, client=None, minimum=0):
        """Wait until the app's worker has drained processing (index_pending False)."""
        client = self.client if client is None else client
        deadline = time.monotonic() + 3
        while True:
            response = client.get("/api/items")
            self.assertEqual(response.status_code, 200, response.text)
            items = response.json()["items"]
            drained = not any(item["index_pending"] for item in items)
            if (drained and len(items) >= minimum) or time.monotonic() >= deadline:
                self.assertTrue(drained, "Local processing did not drain within the wait")
                return items
            time.sleep(0.02)

    def assert_no_internals(self, response):
        """Ruling 7: a JSON response carries no vector/embedding/bank/scores key and no
        long numeric list, at any depth."""
        if "application/json" not in response.headers.get("content-type", ""):
            return
        found = identity_internals(response.json())
        self.assertEqual(found, [], f"{response.request.method} {response.request.url.path} exposes identity internals: {found}")

    def get(self, path, client=None, **params):
        client = self.client if client is None else client
        response = client.get(path, params=params or None)
        self.assertEqual(response.headers.get("cache-control"), "no-store", path)
        self.assertNotIn(str(self.root), response.text)
        self.assert_no_internals(response)
        return response

    def post_json(self, path, body, client=None, origin=ORIGIN):
        client = self.client if client is None else client
        headers = {} if origin is None else {"origin": origin}
        response = client.post(path, json=body, headers=headers)
        self.assertNotIn(str(self.root), response.text)
        self.assert_no_internals(response)
        return response

    def audit_actors(self, action):
        connection = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)
        try:
            rows = connection.execute("SELECT detail FROM local_audit WHERE profile_id='local' AND action=?", (action,)).fetchall()
            corrections = [r[0] for r in connection.execute("SELECT actor FROM corrections WHERE profile_id='local'")]
        finally:
            connection.close()
        return [json.loads(r[0]).get("actor") for r in rows], corrections

    def cannot_links(self):
        connection = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)
        try:
            return {(r[0], r[1]) for r in connection.execute("SELECT item_a,item_b FROM local_cannot_links WHERE profile_id='local'")}
        finally:
            connection.close()

    def evidence(self, item_id, client=None):
        response = self.get(f"/api/items/{item_id}/evidence", client)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(set(body), {"observations"}, body)
        for row in body["observations"]:
            self.assertTrue(EVIDENCE_API_FIELDS <= set(row), row)
            self.assertEqual(row["image_url"], f"/api/items/{item_id}/observations/{row['observation_id']}/image")
            self.assertIn(row["identity_status"], identity.IDENTITY_VOCABULARY)
            self.assertIsInstance(row["reference_image"], dict)
            self.assertEqual(set(row["reference_image"]), {"frame_id", "bbox"})
        return body["observations"]

    def chat(self, text, client=None, **extra):
        response = self.post_json("/api/chat", {"text": text, **extra}, client)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        return response.json()

    def capability(self, capabilities, name=CAPABILITY):
        entries = [cap for cap in capabilities if cap.get("name") == name]
        self.assertEqual(len(entries), 1, capabilities)
        self.assertEqual(set(entries[0]), {"name", "enabled", "reason"})
        self.assertIsInstance(entries[0]["enabled"], bool)
        self.assertIsInstance(entries[0]["reason"], str)
        self.assertNotIn(str(self.root), entries[0]["reason"])
        return entries[0]

    def capability_everywhere(self, client=None, name=CAPABILITY):
        client = self.client if client is None else client
        health = self.get("/api/health", client)
        self.assertEqual(health.status_code, 200, health.text)
        from_health = self.capability(health.json()["capabilities"], name)
        items = self.get("/api/items", client)
        self.assertEqual(items.status_code, 200, items.text)
        from_items = self.capability(items.json()["capabilities"], name)
        self.assertEqual(from_health, from_items, f"health and items disagree on {name}")
        return from_health

    def assert_safe_error(self, response):
        super().assert_safe_error(response)
        for marker in LEAK_MARKERS:
            self.assertNotIn(marker, response.text, f"error text leaks internals: {response.text[:200]}")
        self.assertIsInstance(response.json(), dict)


class EvidenceRouteTests(IdentityApiFixture):
    def test_evidence_list_and_observation_images(self):
        self.seed_calibration()
        first = self.post([region(LEFT, 0)], locations=["fixture shelf left"])
        self.wait_items()
        second = self.post([region(RIGHT, 0)], locations=["fixture shelf right"])
        items = self.wait_items()
        self.assertEqual(len(items), 1, items)
        item = items[0]
        self.assertEqual(item["identity_status"], "trusted")
        self.assertEqual(item["location_text"], "fixture shelf right")
        rows = self.evidence(item["item_id"])
        self.assertEqual(len(rows), 2)
        by_frame = {row["reference_image"]["frame_id"]: row for row in rows}
        self.assertEqual(set(by_frame), {identity.rest_frame_id(first), identity.rest_frame_id(second)})
        for packet, position, location, at in ((first, LEFT, "fixture shelf left", 2200), (second, RIGHT, "fixture shelf right", 12200)):
            row = by_frame[identity.rest_frame_id(packet)]
            self.assertEqual(row["observed_at_ms"], bootstrap.ANCHOR_MS + at)
            self.assertEqual(row["reference_image"]["bbox"], identity.bbox(region(position, 0)))
            self.assertEqual(row["identity_status"], "trusted")
            self.assertEqual(row["outcome"], "placed_on_surface")
            self.assertEqual(row["location_text"], location)
            image = self.get(row["image_url"])
            self.assertEqual(image.status_code, 200, image.text)
            self.assertEqual(image.headers.get("content-type", "").split(";")[0], "image/jpeg")
            self.assertEqual(image.content, identity.rest_jpeg_bytes(packet))
        # The item image is the latest observation's keyframe; evidence images are each their own.
        self.assertEqual(self.get(item["image_url"]).content, identity.rest_jpeg_bytes(second))
        # History still works beside evidence.
        self.assertEqual(len(self.get(f"/api/items/{item['item_id']}/history").json()["observations"]), 2)

    def test_evidence_routes_are_authenticated_profile_scoped_and_404_for_strangers(self):
        self.seed_calibration()
        self.post([region(LEFT, 0)], labels=[GLASSES])
        self.post([region(LEFT, 2)], labels=[BOTTLE])
        items = {i["name"]: i for i in self.wait_items(minimum=2)}
        glasses, bottle = items[GLASSES]["item_id"], items[BOTTLE]["item_id"]
        glasses_obs = self.evidence(glasses)[0]["observation_id"]
        bottle_obs = self.evidence(bottle)[0]["observation_id"]
        # Unauthenticated: 401 with a safe body.
        anonymous = self.identity_client(login=False)
        for path in (f"/api/items/{glasses}/evidence", f"/api/items/{glasses}/observations/{glasses_obs}/image"):
            with self.subTest(path=path):
                response = anonymous.get(path)
                self.assertEqual(response.status_code, 401, response.text)
                self.assert_safe_error(response)
        self.assertEqual(anonymous.post(f"/api/items/{glasses}/link", json={"other_item_id": bottle}, headers={"origin": ORIGIN}).status_code, 401)
        self.assertEqual(anonymous.post(f"/api/items/{glasses}/observations/{glasses_obs}/unlink", headers={"origin": ORIGIN}).status_code, 401)
        # Another profile on the same database sees nothing of this one.
        other = self.identity_client(profile="other-profile")
        self.assertEqual(self.get("/api/items", other).json()["items"], [])
        for path in (f"/api/items/{glasses}/evidence", f"/api/items/{glasses}/observations/{glasses_obs}/image",
                     f"/api/items/{glasses}/image", f"/api/items/{glasses}"):
            with self.subTest(profile="other", path=path):
                response = other.get(path)
                self.assertEqual(response.status_code, 404, response.text)
                self.assert_safe_error(response)
        self.assertEqual(other.post(f"/api/items/{glasses}/link", json={"other_item_id": bottle}, headers={"origin": ORIGIN}).status_code, 404)
        self.assertEqual(other.post(f"/api/items/{glasses}/observations/{glasses_obs}/unlink", headers={"origin": ORIGIN}).status_code, 404)
        # Unknown ids, an observation under the wrong item, and odd spellings: 404 (or 400), never a leak.
        for path in (f"/api/items/no-such-item/evidence", f"/api/items/no-such-item/observations/{glasses_obs}/image",
                     f"/api/items/{glasses}/observations/no-such-observation/image",
                     f"/api/items/{glasses}/observations/{bottle_obs}/image",
                     f"/api/items/{bottle}/observations/{glasses_obs}/image",
                     f"/api/items/{glasses}/observations/%2e%2e%2fkey.pem/image",
                     f"/api/items/{glasses}/observations/..%5C..%5Cserver%5Cmemory_app.py/image",
                     f"/api/items/{glasses}/observations/{glasses_obs}%00/image",
                     f"/api/items/{glasses}/observations/{'a' * 400}/image",
                     f"/api/items/%2e%2e%2fkey.pem/evidence", f"/api/items/{glasses}/observations//image"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertIn(response.status_code, (400, 404), f"{path}: {response.status_code} {response.text[:120]}")
                self.assert_safe_error(response)
                self.assertNotIn(b"\xff\xd8", response.content, "no image bytes on a refused path")
        # The real pair still works after all that.
        self.assertEqual(self.client.get(f"/api/items/{glasses}/observations/{glasses_obs}/image").status_code, 200)


class CorrectionRouteTests(IdentityApiFixture):
    def test_link_merges_and_returns_the_kept_item(self):
        self.seed_calibration()
        self.post([region(LEFT, 0)], labels=[GLASSES], locations=["fixture shelf left"])
        self.post([region(LEFT, 2)], labels=[GLASSES], locations=["fixture shelf back"])
        items = sorted(self.wait_items(minimum=2), key=lambda i: i["observed_at_ms"])
        keep, other = items[0]["item_id"], items[1]["item_id"]
        other_obs = [row["observation_id"] for row in self.evidence(other)]
        self.assertEqual(self.chat(identity.ASK_GLASSES)["shape"], "clarify")
        response = self.post_json(f"/api/items/{keep}/link", {"other_item_id": other})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        merged = response.json()
        self.assertTrue(ITEM_FIELDS <= set(merged), merged)
        self.assertEqual(merged["item_id"], keep)
        self.assertEqual(merged["image_url"], f"/api/items/{keep}/image")
        self.assertEqual(merged["identity_status"], "trusted")
        self.assertEqual(merged["location_text"], "fixture shelf back")
        self.assertEqual([i["item_id"] for i in self.catalogue()], [keep])
        self.assertEqual(self.get(f"/api/items/{other}").status_code, 404)
        self.assertEqual(self.get(f"/api/items/{other}/evidence").status_code, 404)
        self.assertEqual(self.get(f"/api/items/{other}/image").status_code, 404)
        rows = self.evidence(keep)
        self.assertEqual(len(rows), 2)
        self.assertTrue(set(other_obs) <= {row["observation_id"] for row in rows})
        for row in rows:
            self.assertEqual(self.get(row["image_url"]).status_code, 200)
        answer = self.chat(identity.ASK_GLASSES)
        self.assertEqual(answer["shape"], "confident", answer)
        self.assertEqual([m["item_id"] for m in answer["members"]], [keep])
        # The item id in the body must be a real other item: itself, unknown or garbage are refused.
        for body, statuses in (({"other_item_id": keep}, (400, 409)), ({"other_item_id": "no-such-item"}, (404,)),
                               ({"other_item_id": other}, (404,)), ({}, (400,)), ({"other_item_id": 7}, (400,)),
                               ({"other_item_id": keep, "extra": 1}, (400,)), ({"other_item_id": "x" * 400}, (400, 404))):
            with self.subTest(body=body):
                response = self.post_json(f"/api/items/{keep}/link", body)
                self.assertIn(response.status_code, statuses, response.text)
                self.assert_safe_error(response)
        self.assertEqual(self.post_json("/api/items/no-such-item/link", {"other_item_id": keep}).status_code, 404)
        self.assertEqual([i["item_id"] for i in self.catalogue()], [keep])

    def test_link_of_a_cannot_linked_pair_is_409_with_a_safe_message(self):
        self.seed_calibration()
        self.post([region(LEFT, 0), region(RIGHT, 0)], locations=["fixture shelf left", "fixture shelf right"])
        a, b = (i["item_id"] for i in self.wait_items(minimum=2))
        before = self.catalogue()
        from server.memory_app import CORRECTION_REFUSALS
        for keep, other in ((a, b), (b, a)):
            with self.subTest(keep=keep):
                response = self.post_json(f"/api/items/{keep}/link", {"other_item_id": other})
                self.assertEqual(response.status_code, 409, response.text)
                self.assert_safe_error(response)
                detail = response.json().get("detail")
                self.assertIsInstance(detail, str)
                self.assertTrue(detail.strip(), "the 409 must carry a human-readable reason")
                self.assertNotIn("cannot-link", detail, "the safe message is prose, not the internal error token")
                self.assertEqual(response.json().get("code"), "cannot_link")
                # Approved wording (coordinator, CP3 fix round).
                self.assertEqual(detail, CORRECTION_REFUSALS["cannot_link"])
                self.assertIn("They cannot be merged.", detail)
        self.assertEqual(self.catalogue(), before)
        self.assertEqual(len(self.evidence(a)), 1)
        self.assertEqual(len(self.evidence(b)), 1)

    def test_unlink_moves_the_observation_to_a_new_item_and_refuses_a_relink(self):
        self.seed_calibration()
        first = self.post([region(LEFT, 0)], locations=["fixture shelf left"])
        self.wait_items()
        self.post([region(RIGHT, 0)], locations=["fixture shelf right"])
        item = self.wait_items()[0]
        rows = {row["reference_image"]["frame_id"]: row["observation_id"] for row in self.evidence(item["item_id"])}
        o1 = rows[identity.rest_frame_id(first)]
        o2 = next(v for k, v in rows.items() if k != identity.rest_frame_id(first))
        response = self.post_json(f"/api/items/{item['item_id']}/observations/{o2}/unlink", {})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        new = response.json()
        self.assertTrue(ITEM_FIELDS <= set(new), new)
        self.assertNotEqual(new["item_id"], item["item_id"])
        self.assertEqual(new["image_url"], f"/api/items/{new['item_id']}/image")
        self.assertEqual([row["observation_id"] for row in self.evidence(new["item_id"])], [o2])
        self.assertEqual([row["observation_id"] for row in self.evidence(item["item_id"])], [o1])
        self.assertEqual({i["item_id"] for i in self.catalogue()}, {item["item_id"], new["item_id"]})
        self.assertEqual(self.get(f"/api/items/{item['item_id']}").json()["location_text"], "fixture shelf left")
        self.assertEqual(self.get(f"/api/items/{new['item_id']}/observations/{o2}/image").status_code, 200)
        self.assertEqual(self.get(f"/api/items/{item['item_id']}/observations/{o2}/image").status_code, 404, "the moved observation no longer serves under the old item")
        response = self.post_json(f"/api/items/{item['item_id']}/link", {"other_item_id": new["item_id"]})
        self.assertEqual(response.status_code, 409, response.text)
        self.assert_safe_error(response)
        # Unlinking again (an item's only observation), unknown ids and the wrong item: refused safely.
        for path, statuses in ((f"/api/items/{new['item_id']}/observations/{o2}/unlink", (400, 409)),
                               (f"/api/items/{item['item_id']}/observations/{o2}/unlink", (404,)),
                               (f"/api/items/{item['item_id']}/observations/no-such-observation/unlink", (404,)),
                               (f"/api/items/no-such-item/observations/{o1}/unlink", (404,)),
                               (f"/api/items/{item['item_id']}/observations/{o1}%2F..%2Fx/unlink", (400, 404))):
            with self.subTest(path=path):
                response = self.post_json(path, {})
                self.assertIn(response.status_code, statuses, response.text)
                self.assert_safe_error(response)
        self.assertEqual({i["item_id"] for i in self.catalogue()}, {item["item_id"], new["item_id"]})

    def test_corrections_require_same_origin(self):
        self.seed_calibration()
        self.post([region(LEFT, 0)], labels=[GLASSES])
        self.post([region(LEFT, 2)], labels=[BOTTLE])
        items = {i["name"]: i["item_id"] for i in self.wait_items(minimum=2)}
        obs = self.evidence(items[GLASSES])[0]["observation_id"]
        for origin in (None, "https://evil.invalid", ORIGIN + ".evil.invalid"):
            with self.subTest(origin=origin):
                response = self.post_json(f"/api/items/{items[GLASSES]}/link", {"other_item_id": items[BOTTLE]}, origin=origin)
                self.assertEqual(response.status_code, 403, response.text)
                self.assert_safe_error(response)
                response = self.post_json(f"/api/items/{items[GLASSES]}/observations/{obs}/unlink", {}, origin=origin)
                self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(len(self.catalogue()), 2)
        self.assertEqual(len(self.evidence(items[GLASSES])), 1)


class GroupChatTests(IdentityApiFixture):
    def test_group_answer_passes_members_with_provenance_and_photos(self):
        a, b = self.seed_lookalike_pair()
        ids = {a["item_id"], b["item_id"]}
        items = {i["item_id"]: i for i in self.catalogue()}
        self.assertEqual(set(items), ids, "an ambiguous sighting is not a third catalogue item")
        for item_id, other in ((a["item_id"], b["item_id"]), (b["item_id"], a["item_id"])):
            self.assertEqual(items[item_id]["identity_status"], "ambiguous", items[item_id])
            self.assertEqual(items[item_id]["lookalikes"], [other], items[item_id])
            single = self.get(f"/api/items/{item_id}").json()
            self.assertEqual((single["identity_status"], single["lookalikes"]), ("ambiguous", [other]))
        answer = self.chat(identity.ASK_GLASSES)
        self.assertEqual(answer["shape"], "group", answer)
        self.assertEqual(answer["text"], identity.GROUP_TEXT.format(n=2))
        self.assertIs(answer["index_pending"], False)
        self.assertEqual({m["item_id"] for m in answer["members"]}, ids)
        # Ruling 5: the group names the parked observation the member tap resolves.
        parked = answer["unresolved_observation_id"]
        self.assertIsInstance(parked, str)
        self.assertTrue(parked)
        for item_id in ids:
            self.assertNotIn(parked, [row["observation_id"] for row in self.evidence(item_id)], "a parked observation belongs to no item yet")
        for member in answer["members"]:
            self.assertTrue(ITEM_FIELDS <= set(member), member)
            self.assertEqual(member["identity_status"], "ambiguous")
            self.assertEqual(set(member["provenance"]), {"observation_id", "identity_status"})
            self.assertIn(member["provenance"]["identity_status"], identity.IDENTITY_VOCABULARY)
            self.assertIn(member["provenance"]["observation_id"], [row["observation_id"] for row in self.evidence(member["item_id"])])
            self.assertEqual(set(member["reference_image"]), {"frame_id", "bbox"})
            self.assertEqual(member["observed_at_ms"], bootstrap.ANCHOR_MS + 2200)
            self.assertIn("location_text", member)
            self.assertEqual(member["image_url"], f"/api/items/{member['item_id']}/image")
            self.assertEqual(self.get(member["image_url"]).status_code, 200)
            self.assertEqual(member["lookalikes"], sorted(ids - {member["item_id"]}))
        self.assertNotIn(str(self.root), json.dumps(answer))
        # Selecting one member (the browser resubmits its id) is a non-group answer about it alone.
        chosen = self.chat(a["item_id"])
        self.assertNotEqual(chosen["shape"], "group")
        self.assertNotEqual(chosen["shape"], "confident", "a group member's certainty is never upgraded")
        self.assertEqual([m["item_id"] for m in chosen["members"]], [a["item_id"]])
        # as_of before the ambiguous sighting: the two were distinct (clarify), not a group.
        earlier = self.chat(identity.ASK_GLASSES, as_of=bootstrap.ANCHOR_MS + 12199)
        self.assertEqual(earlier["shape"], "clarify", earlier)
        self.assertEqual({m["identity_status"] for m in earlier["members"]}, {"trusted"})

    def test_group_cannot_be_merged_and_a_distinct_item_makes_it_a_clarify(self):
        a, b = self.seed_lookalike_pair()
        # "Same as another item": the user merges the two; the group dissolves into one item.
        response = self.post_json(f"/api/items/{a['item_id']}/link", {"other_item_id": b["item_id"]})
        self.assertEqual(response.status_code, 409, "co-visible lookalikes can never be one item (B-03)")
        self.assertEqual(response.json().get("code"), "cannot_link")
        # A third, distinct object with the same words makes it a clarify instead.
        self.post([region(LEFT, 2)], labels=[GLASSES], locations=["fixture shelf back"])
        items = self.wait_items(minimum=3)
        self.assertEqual(len(items), 3)
        mixed = self.chat(identity.ASK_GLASSES)
        self.assertEqual(mixed["shape"], "clarify", mixed)
        self.assertEqual(len(mixed["members"]), 3)
        self.assertEqual(len(mixed["options"]), 3)

    def seed_separable_lookalikes(self):
        """A (tag 0) and B (tag 1) seen apart under the tight calibration (no
        cannot-link between them), then the wide calibration approved and a lone
        tag-0 sighting parked as ambiguous. Returns (a_id, b_id, parked_id)."""
        store = self.store()
        store.register_calibration(identity.calibration_record(identity.CAL_TIGHT, quantile=identity.TIGHT_Q, created_ms=bootstrap.ANCHOR_MS))
        store.approve_calibration(identity.CAL_TIGHT, identity.ACTOR)
        self.post([region(LEFT, 0)], calibration_id=identity.CAL_TIGHT, locations=["fixture shelf left"])
        self.wait_items()
        self.post([region(RIGHT, 1)], calibration_id=identity.CAL_TIGHT, locations=["fixture shelf right"])
        items = sorted(self.wait_items(minimum=2), key=lambda i: i["location_text"] or "")
        self.assertEqual({i["identity_status"] for i in items}, {"trusted"})
        a, b = items[0]["item_id"], items[1]["item_id"]
        store.register_calibration(identity.calibration_record(identity.CAL_WIDE, quantile=identity.WIDE_Q, created_ms=bootstrap.ANCHOR_MS + 1000))
        store.approve_calibration(identity.CAL_WIDE, identity.ACTOR)
        self.post([region(MIDDLE, 0)], locations=["fixture shelf middle"])
        items = self.wait_processed()
        self.assertEqual({i["identity_status"] for i in items}, {"ambiguous"}, items)
        answer = self.chat(identity.ASK_GLASSES)
        self.assertEqual(answer["shape"], "group", answer)
        parked = answer["unresolved_observation_id"]
        self.assertIsInstance(parked, str)
        return a, b, parked

    def test_assign_resolves_the_parked_observation_and_dissolves_the_group(self):
        # Coordinator ruling 5: POST /api/items/{id}/observations/{obs}/assign.
        a, b, parked = self.seed_separable_lookalikes()
        self.assertEqual(self.cannot_links(), set(), "seen apart: nothing separates A and B before the user's choice")
        response = self.post_json(f"/api/items/{a}/observations/{parked}/assign", {})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        item = response.json()
        self.assertTrue(ITEM_FIELDS <= set(item), item)
        self.assertEqual(item["item_id"], a)
        self.assertNotEqual(item["identity_status"], "ambiguous")
        self.assertEqual(item["lookalikes"], [])
        rows = self.evidence(a)
        self.assertIn(parked, [row["observation_id"] for row in rows])
        self.assertEqual(len(rows), 2)
        self.assertEqual(self.get(f"/api/items/{a}/observations/{parked}/image").status_code, 200)
        self.assertEqual(self.get(f"/api/items/{b}/observations/{parked}/image").status_code, 404)
        self.assertNotIn(parked, [row["observation_id"] for row in self.evidence(b)])
        items = {i["item_id"]: i for i in self.catalogue()}
        self.assertEqual(set(items), {a, b})
        self.assertEqual({i["identity_status"] for i in items.values()} & {"ambiguous"}, set())
        self.assertEqual([i["lookalikes"] for i in items.values()], [[], []])
        dissolved = self.chat(identity.ASK_GLASSES)
        self.assertEqual(dissolved["shape"], "clarify", dissolved)
        self.assertFalse(dissolved.get("unresolved_observation_id"))
        chosen = self.chat(a)
        self.assertNotEqual(chosen["shape"], "group")
        self.assertEqual([m["item_id"] for m in chosen["members"]], [a])
        self.assertEqual(chosen["shape"], "hedged", "a user-attributed sighting is still only a sighting: never confident")
        # Evidence says who asserted the identity; outcome and location are untouched.
        by_id = {row["observation_id"]: row for row in rows}
        self.assertEqual(by_id[parked]["identity_status"], "trusted")
        self.assertEqual((by_id[parked]["outcome"], by_id[parked]["location_text"]), ("sighted", None))
        self.assertEqual(by_id[parked].get("identity_source"), "user_assigned",
                         f"GET /evidence must say who asserted the identity (identity_source); row: {by_id[parked]}")
        self.assertEqual({row.get("identity_source") for oid, row in by_id.items() if oid != parked}, {"processor"})
        self.assertEqual({row.get("identity_source") for row in self.evidence(b)}, {"processor"})
        # Reversed clause (Oversight): the user said "this sighting is A", not "A and B
        # are different objects", so nothing separates A and B.
        self.assertEqual(self.cannot_links(), set(), "assign infers no cannot-link to the other candidates")
        # A second assign (the observation is attributed), an ordinary observation,
        # and unknown ids.
        again = self.post_json(f"/api/items/{b}/observations/{parked}/assign", {})
        self.assertEqual(again.status_code, 409, again.text)
        self.assertEqual(again.json().get("code"), "not_ambiguous")
        self.assertEqual(again.json().get("detail"), "That sighting is not waiting for a choice; it is already attributed to an item.")
        self.assert_safe_error(again)
        ordinary = [row["observation_id"] for row in self.evidence(b)][0]
        plain = self.post_json(f"/api/items/{a}/observations/{ordinary}/assign", {})
        self.assertEqual(plain.status_code, 409, plain.text)
        self.assertEqual(plain.json().get("code"), "not_ambiguous")
        for path in (f"/api/items/no-such-item/observations/{parked}/assign", f"/api/items/{a}/observations/no-such-observation/assign",
                     f"/api/items/{a}/observations/{'z' * 400}/assign"):
            with self.subTest(path=path):
                response = self.post_json(path, {})
                self.assertIn(response.status_code, (400, 404), response.text)
                self.assert_safe_error(response)
        self.assertEqual(self.post_json(f"/api/items/{a}/observations/{ordinary}/assign", {}, origin="https://evil.invalid").status_code, 403)
        anonymous = self.identity_client(login=False)
        self.assertEqual(anonymous.post(f"/api/items/{a}/observations/{ordinary}/assign", json={}, headers={"origin": ORIGIN}).status_code, 401)
        other = self.identity_client(profile="other-profile")
        self.assertEqual(other.post(f"/api/items/{a}/observations/{ordinary}/assign", json={}, headers={"origin": ORIGIN}).status_code, 404)
        self.assertEqual(len(self.evidence(a)), 2)
        # The candidates may be fragmented duplicates: "same as" between them succeeds
        # and the assigned evidence travels with the kept item.
        merged = self.post_json(f"/api/items/{a}/link", {"other_item_id": b})
        self.assertEqual(merged.status_code, 200, merged.text)
        self.assertEqual(merged.json()["item_id"], a)
        self.assertEqual([i["item_id"] for i in self.catalogue()], [a])
        self.assertEqual(len(self.evidence(a)), 3)
        # "Not this one" on the assigned sighting withdraws the assertion: it reads
        # provisional under its new item.
        withdrawn = self.post_json(f"/api/items/{a}/observations/{parked}/unlink", {})
        self.assertEqual(withdrawn.status_code, 200, withdrawn.text)
        new_id = withdrawn.json()["item_id"]
        self.assertNotEqual(new_id, a)
        rows = self.evidence(new_id)
        self.assertEqual([row["observation_id"] for row in rows], [parked])
        self.assertEqual(rows[0]["identity_status"], "provisional", rows[0])
        self.assertNotEqual(withdrawn.json()["identity_status"], "trusted")
        self.assertEqual(len(self.evidence(a)), 2)
        self.assertEqual(self.post_json(f"/api/items/{a}/link", {"other_item_id": new_id}).status_code, 409, "an unlink does separate the two")

    def test_request_bodies_never_carry_an_actor(self):
        # Coordinator ruling 6 (B-15): the server attributes every correction to the
        # session role "caregiver_pin"; an actor in a request body is ignored or
        # rejected, never recorded.
        a, b, parked = self.seed_separable_lookalikes()
        attempts = ((f"/api/items/{a}/observations/{parked}/assign", {"actor": "operator"}),
                    (f"/api/items/{a}/observations/{parked}/assign", {"actor": "Dr Smith"}),
                    (f"/api/items/{a}/link", {"other_item_id": b, "actor": "operator"}))
        for path, body in attempts:
            with self.subTest(path=path, body=body):
                response = self.post_json(path, body)
                if response.status_code == 200:
                    self.fail(f"{path} accepted a body with an actor; the spec allows ignoring it only if nothing is recorded under it: {response.text}")
                self.assertEqual(response.status_code, 400, response.text)
                self.assert_safe_error(response)
        self.assertEqual(self.audit_actors("user_assigned"), ([], []))
        # A legitimate correction is attributed to the server's role literal.
        self.assertEqual(self.post_json(f"/api/items/{a}/observations/{parked}/assign", {}).status_code, 200)
        self.post([region(LEFT, 2)], labels=[BOTTLE])
        bottle = next(i["item_id"] for i in self.wait_items(minimum=3) if i["name"] == BOTTLE)
        self.assertEqual(self.post_json(f"/api/items/{b}/link", {"other_item_id": bottle}).status_code, 200)
        rows = [row["observation_id"] for row in self.evidence(b)]
        self.assertEqual(len(rows), 2)
        self.assertEqual(self.post_json(f"/api/items/{b}/observations/{rows[-1]}/unlink", {}).status_code, 200)
        for action in ("user_assigned", "user_linked", "user_unlinked"):
            audits, corrections = self.audit_actors(action)
            self.assertEqual(audits, ["caregiver_pin"], action)
        self.assertEqual(set(corrections), {"caregiver_pin"})
        self.assertNotIn("operator", json.dumps(corrections))


class IdentityCapabilityTests(IdentityApiFixture):
    def test_no_identity_model_means_capability_false_and_provisional_only(self):
        # The default app (no embedder injected, no manifest): nothing is simulated.
        client = self.identity_client(embedder="absent", database=self.root / "no-model.sqlite3")
        from perception.object_memory import ObjectStore
        store = ObjectStore(self.root / "no-model.sqlite3", profile_id="local", clock=self.clock)
        store.register_calibration(identity.calibration_record())
        store.approve_calibration(identity.CAL_WIDE, identity.ACTOR)
        self.assertEqual(self.get("/api/health", client).json()["models"], [])
        capability = self.capability_everywhere(client)
        self.assertIs(capability["enabled"], False)
        self.post([region(LEFT, 0)], client=client, locations=["fixture shelf left"])
        self.wait_items(client)
        self.post([region(RIGHT, 0)], client=client, locations=["fixture shelf right"])
        items = self.wait_items(client)
        self.assertGreaterEqual(len(items), 1)
        for item in items:
            self.assertEqual(item["identity_status"], "provisional", item)
            self.assertEqual(item["location_status"], "sighted")
            self.assertIsNone(item["location_text"])
        self.assertNotEqual(self.chat(identity.ASK_GLASSES, client)["shape"], "confident")
        self.assertEqual(self.embedder.calls, [])
        self.assertIs(self.capability_everywhere(client)["enabled"], False)

    def test_capability_gate_mirrors_cp2_manifest_licence_and_env(self):
        # The policy helper pattern of CP2 with the identity asset: unprovisioned >
        # unlicensed > disabled, and only PAM_ENABLE_IDENTITY_MODEL == "1" enables.
        reasons = {}
        with patch.dict(os.environ, {ENV: "1"}):
            unprovisioned = self.capability_everywhere()
        self.assertIs(unprovisioned["enabled"], False)
        reasons["unprovisioned"] = unprovisioned["reason"]
        self.assertEqual(self.get("/api/health").json()["models"], [])
        self.write_manifest()
        with patch.dict(os.environ, {ENV: "1"}):
            self.assertIs(self.capability_everywhere()["enabled"], False, "listed but the file is absent")
            self.assertEqual(self.capability_everywhere()["reason"], reasons["unprovisioned"])
        self.write_model_file()
        models = {m["name"]: m for m in self.get("/api/health").json()["models"]}
        self.assertIn(MODEL, models, "an .onnx manifest entry must be accepted by the inventory")
        self.assertEqual(models[MODEL], {"name": MODEL, "provisioned": True, "licence_recorded": False, "version": MODEL_VERSION})
        with patch.dict(os.environ, {ENV: "1"}):
            unlicensed = self.capability_everywhere()
        self.assertIs(unlicensed["enabled"], False)
        reasons["unlicensed"] = unlicensed["reason"]
        self.write_register("| other_model.onnx | Apache-2.0 | not the identity model | status: VERIFIED-COMMERCIAL |\n")
        self.assertFalse({m["name"]: m for m in self.get("/api/health").json()["models"]}[MODEL]["licence_recorded"])
        self.write_register(f"| {MODEL} | Apache-2.0 | status: UNVERIFIED |\n")
        with patch.dict(os.environ, {ENV: "1"}):
            self.assertEqual(self.capability_everywhere()["reason"], reasons["unlicensed"])
        self.write_register()
        self.assertTrue({m["name"]: m for m in self.get("/api/health").json()["models"]}[MODEL]["licence_recorded"])
        disabled = self.capability_everywhere()
        self.assertIs(disabled["enabled"], False)
        reasons["disabled"] = disabled["reason"]
        for value in ("true", "0", "yes", " 1"):
            with patch.dict(os.environ, {ENV: value}):
                self.assertEqual(self.capability_everywhere(), disabled, f'only "1" enables (got {value!r})')
        with patch.dict(os.environ, {ENV: "1"}):
            # Coordinator ruling 1: the gate being open is not enough; the loaded embedder
            # also needs an approved calibration for its tag, else False with the
            # store's reason. A registered-but-unapproved record changes nothing.
            uncalibrated = self.capability_everywhere()
            self.assertIs(uncalibrated["enabled"], False, uncalibrated)
            self.assertIn(UNCALIBRATED_REASON, uncalibrated["reason"])
            reasons["uncalibrated"] = uncalibrated["reason"]
            self.seed_calibration(approve=False)
            self.assertEqual(self.capability_everywhere(), uncalibrated, "registration without approval does not enable")
            self.store().approve_calibration(identity.CAL_WIDE, identity.ACTOR)
            enabled = self.capability_everywhere()
            self.assertIs(enabled["enabled"], True, enabled)
            self.assertIn(MODEL_VERSION, enabled["reason"])
            self.assertIn("unmeasured", enabled["reason"].lower(), "an enabled model is still not a measured accuracy claim")
            self.register.unlink()
            self.assertEqual(self.capability_everywhere()["reason"], reasons["unlicensed"], "the register is read per request")
        self.assertEqual(len(set(reasons.values())), 4, reasons)
        for reason in reasons.values():
            self.assertTrue(reason.strip())
            self.assertNotIn(str(self.root), reason)
        # The hand capability is untouched and each capability appears exactly once.
        self.write_register()
        with patch.dict(os.environ, {ENV: "1"}):
            health = self.get("/api/health").json()
        names = [cap["name"] for cap in health["capabilities"]]
        self.assertEqual(names.count(CAPABILITY), 1)
        self.assertEqual(names.count(HAND), 1)
        self.assertIs(self.capability(health["capabilities"], HAND)["enabled"], False)

    def test_identity_gate_is_independent_of_the_hand_gate(self):
        self.provision()
        with patch.dict(os.environ, {"PAM_ENABLE_HAND_MODEL": "1"}):
            self.assertIs(self.capability_everywhere()["enabled"], False, "no approved calibration yet (ruling 1)")
            self.assertIn(UNCALIBRATED_REASON, self.capability_everywhere()["reason"])
            self.seed_calibration()
            self.assertIs(self.capability_everywhere()["enabled"], True)
            self.assertIs(self.capability_everywhere(name=HAND)["enabled"], False, "hand assets are not provisioned here")
        with patch.dict(os.environ, {ENV: "0"}):
            self.assertIs(self.capability_everywhere()["enabled"], False)
        # The identity asset is never fetched by the browser: the gated model route
        # serves manifest files only under the hand flag, and the page's module graph
        # does not reference it (no identity model leaves the server).
        self.assertEqual(self.client.get("/assets/models/" + MODEL).status_code, 404)
        page = self.client.get("/").text
        self.assertNotIn(MODEL, page)
        for name in ("memory.js", "memory-camera.js"):
            self.assertNotIn(MODEL, self.client.get("/assets/" + name).text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
