"""First-milestone contract tests: real app/store, synthetic pixels, no paid IO.

Authority: docs/BUILD_CONTRACT.md (2026-10-07). Run this file explicitly with -B.
The fixture processor is injected into create_app; no HTTP input selects it.
Scores/calibration records are fabricated test inputs, never accuracy evidence.
"""
from __future__ import annotations

import base64
import builtins
import copy
from contextlib import ExitStack
import hashlib
import importlib
import io
import itertools
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

import cv2
import httpx
import numpy as np
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ORIGIN = "https://testserver"
PIN = "synthetic-bootstrap-pin"
SECRET = "SYNTHETIC-CHAT-SECRET-MUST-NOT-ESCAPE"
LEGACY = "SYNTHETIC-LEGACY-CONTENT-MUST-NOT-ESCAPE"
DEVICE = "11111111-1111-4111-8111-111111111111"
SESSION = "22222222-2222-4222-8222-222222222222"
ANCHOR_MS = 1790000000000
ITEM_FIELDS = {"item_id", "name", "identity_status", "relevance", "location_status",
               "observed_at_ms", "location_text", "stale_reason", "index_pending", "image_url", "source"}
RETIRED = ("/api/dg-token", "/api/agent-config", "/api/fake-dg", "/api/stt",
           "/api/face/save", "/api/face/who", "/api/face/sync", "/api/face/restore",
           "/api/pill-status", "/api/pill-answer", "/api/streak", "/api/calendar",
           "/api/reminders", "/api/flights", "/api/ride", "/api/fetch", "/api/es/index")


def encode_packet(packet, *, pretty=False):
    return json.dumps(packet, sort_keys=not pretty, indent=2 if pretty else None,
                      separators=None if pretty else (",", ":"), allow_nan=False).encode("utf-8")


def synthetic_jpeg(x=None):
    """Independent pixel golden: checkerboard plus an optional 20x20 rectangle."""
    y, xx = np.indices((120, 160))
    gray = (35 + ((xx // 8 + y // 8) % 2) * 50).astype(np.uint8)
    image = np.repeat(gray[:, :, None], 3, axis=2)
    if x is not None:
        image[40:60, x:x + 20] = (30, 60, 230)
    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise AssertionError("Synthetic JPEG encoding failed")
    return base64.b64encode(data.tobytes()).decode("ascii")


class FixtureProcessor:
    """Only a trusted factory injection can access this independent observation map."""
    def __init__(self):
        self.observations = {}
        self.calls = []

    def __call__(self, packet):
        from perception.localizer import LocalObservation
        self.calls.append(packet.episode_id)
        values = self.observations.get(packet.episode_id)
        return [] if values is None else [LocalObservation(**copy.deepcopy(values))]


class MemoryApiFixture(unittest.TestCase):
    """No test methods here: shared by the new suite and explicitly ported legacy tests."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pam-memory-bootstrap-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.db = self.root / "objects.sqlite3"
        self.now = ANCHOR_MS / 1000 + 100
        self.serial = itertools.count(1)
        self.processor = FixtureProcessor()
        self.forbidden_calls = []
        keys = ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "COMSPEC", "PATHEXT")
        env = {key: os.environ[key] for key in keys if key in os.environ}
        env.update(PYTHONPATH="", PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1",
                   PAM_OBJECT_DB=str(self.db), PAM_AUTH_PIN=PIN,
                   LOCALAPPDATA=str(self.root / "appdata"), APPDATA=str(self.root / "appdata"),
                   USERPROFILE=str(self.root / "home"))
        self.enterContext(patch.dict(os.environ, env, clear=True))
        self._guard_private_reads_and_writes()
        self._guard_egress()
        self.addCleanup(self._assert_no_forbidden_io)
        self.apps = []
        self.client = self.new_client()

    def clock(self):
        return self.now

    def _assert_no_forbidden_io(self):
        self.assertEqual(self.forbidden_calls, [], "Guarded IO was attempted, even if production swallowed the error")

    def _deny(self, boundary):
        def deny(*args, **kwargs):
            self.forbidden_calls.append(boundary)
            raise AssertionError("Forbidden bootstrap IO: " + boundary)
        return deny

    def _guard_egress(self):
        # Windows asyncio uses an internal loopback socketpair. Permit only that
        # implementation while it constructs the pair, not arbitrary loopback IO.
        pair_state = threading.local()
        real_pair = socket.socketpair
        originals = {name: getattr(socket.socket, name) for name in ("connect", "connect_ex", "bind", "listen")}
        def socketpair(*args, **kwargs):
            pair_state.active = True
            try:
                return real_pair(*args, **kwargs)
            finally:
                pair_state.active = False
        self.enterContext(patch.object(socket, "socketpair", socketpair))
        for name, original in originals.items():
            def guarded(sock, *args, _name=name, _original=original, **kwargs):
                if getattr(pair_state, "active", False):
                    if _name != "listen" and args and isinstance(args[0], tuple):
                        if args[0][0] not in ("127.0.0.1", "::1", "localhost"):
                            return self._deny("non-loopback socketpair")()
                    return _original(sock, *args, **kwargs)
                return self._deny("socket." + _name)()
            self.enterContext(patch.object(socket.socket, name, guarded))
        for target in ("socket.create_connection", "urllib.request.urlopen", "subprocess.run", "subprocess.Popen"):
            self.enterContext(patch(target, side_effect=self._deny(target)))
        self.enterContext(patch("httpx.HTTPTransport.handle_request", side_effect=self._deny("external HTTP")))
        self.enterContext(patch("httpx.AsyncHTTPTransport.handle_async_request",
                                new=AsyncMock(side_effect=self._deny("external async HTTP"))))
        # Installed dependency only; never an archive application import.
        import anthropic
        for name in ("Anthropic", "AsyncAnthropic"):
            self.enterContext(patch.object(anthropic, name, side_effect=self._deny("provider construction")))

    def _guard_private_reads_and_writes(self):
        def inspect(path, mode="r", flags=None):
            if isinstance(path, int):
                return
            try:
                p = Path(os.fsdecode(path)).resolve()
            except (TypeError, ValueError):
                return
            if p.is_relative_to(self.root):
                return
            writing = (bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
                       if flags is not None else any(char in str(mode) for char in "wax+"))
            private = p.name in {".env", "key.pem", "contacts.json", "google-calendar.dat"}
            private |= p.is_relative_to(ROOT) and (p.suffix in {".pem", ".jsonl", ".sqlite3"}
                or any(part in {"runs", "photos", "faces", "gallery", "object_evidence"} for part in p.parts))
            if writing or private:
                self._deny("outside-fixture file access")()
        for module, name in ((builtins, "open"), (io, "open")):
            original = getattr(module, name)
            def guarded(path, mode="r", *args, _original=original, **kwargs):
                inspect(path, mode)
                return _original(path, mode, *args, **kwargs)
            self.enterContext(patch.object(module, name, guarded))
        original_os_open = os.open
        def os_open(path, flags, *args, **kwargs):
            inspect(path, flags=flags)
            return original_os_open(path, flags, *args, **kwargs)
        self.enterContext(patch.object(os, "open", os_open))

    def new_client(self, *, profile="local", database=None, pin=PIN, processor="fixture", chat_provider=None):
        module = importlib.import_module("server.app")
        self.assertTrue(callable(getattr(module, "create_app", None)), "server.app.create_app is the frozen app boundary")
        app = module.create_app(database_path=self.db if database is None else database,
                               profile_id=profile, processor=self.processor if processor == "fixture" else processor,
                               clock=self.clock, auth_pin=pin, chat_provider=chat_provider)
        self.apps.append(app)
        client = TestClient(app, base_url=ORIGIN, raise_server_exceptions=False)
        self.enterContext(client)
        return client

    def login(self, client=None):
        client = self.client if client is None else client
        response = client.post("/api/auth/login", json={"pin": PIN}, headers={"origin": ORIGIN})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"authenticated": True})
        return response

    def packet(self, *, phase=0, identity="trusted", register=True):
        n = next(self.serial)
        eid = str(uuid.UUID(int=n, version=4))
        start, end = 1000 + phase * 10000, 2200 + phase * 10000
        x = 20 if phase == 0 else 85
        packet = {"schema_version": 1, "episode_id": eid, "device_id": DEVICE, "session_id": SESSION,
                  "t_start_ms": start, "t_end_ms": end, "clock_anchor": {"mono_ms": 0, "wall_ms": ANCHOR_MS},
                  "capture": {"width": 160, "height": 120}, "analysis": {"width": 80, "height": 60},
                  "keyframes": [{"frame_id": eid + "-before", "t_ms": start, "role": "pre_contact",
                                 "jpeg_b64": synthetic_jpeg(None if phase == 0 else 20)},
                                {"frame_id": eid + "-rest", "t_ms": end, "role": "rest", "jpeg_b64": synthetic_jpeg(x)}],
                  "carry_burst": [], "landmarks": [], "gaps": [], "outcome_hint": "released", "capture_mode": "manual"}
        if register:
            self.processor.observations[eid] = {
                "frame_id": eid + "-rest", "bbox": [float(x), 40.0, float(x + 20), 60.0],
                "label": "synthetic red block", "actor": "wearer" if phase == 0 else "other_person",
                "outcome": "placed_on_surface", "continuity_id": "fixture-continuity-001",
                "identity_state": identity, "location_text": "fixture left" if phase == 0 else "fixture right",
                "confidence": 1.0, "confidence_basis": "TEST ONLY: manually authored synthetic pixel golden",
                "calibration": {"approved": True, "fixture_only": True, "calibration_id": "synthetic-only-1"}}
        return packet

    def post_packet(self, packet, *, client=None, raw=None):
        client = self.client if client is None else client
        raw = encode_packet(packet) if raw is None else raw
        return client.post("/api/episodes", content=raw,
                           headers={"origin": ORIGIN, "content-type": "application/json"})

    def assert_ack(self, response, packet, raw=None, status=None):
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIn("processing", body)
        ack = body["ack"]
        self.assertEqual(ack["episode_id"], packet["episode_id"])
        self.assertEqual(ack["device_id"], DEVICE)
        self.assertEqual(ack["digest"], hashlib.sha256(encode_packet(packet) if raw is None else raw).hexdigest())
        self.assertIs(ack["retained"], True)
        self.assertIsInstance(ack["revision_no"], int)
        if status:
            self.assertEqual(ack["status"], status)
        return ack

    def catalogue(self, client=None):
        client = self.client if client is None else client
        response = client.get("/api/items")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertNotIn(str(self.root), response.text)
        self.assertNotIn(SECRET, response.text)
        body = response.json()
        self.assertIsInstance(body["capabilities"], list)
        for item in body["items"]:
            self.assertTrue(ITEM_FIELDS <= item.keys(), item)
            if item["image_url"] is not None:
                self.assertEqual(item["image_url"], f"/api/items/{item['item_id']}/image")
        return body["items"]

    def wait_items(self, client=None, *, minimum=1):
        """The catalogue once local processing has drained: at least `minimum` items
        and no index_pending flag. A durable ack precedes processing in the app's own
        worker, so an item count alone can return the projection from before the
        latest episode (a relocation would read as the old location)."""
        deadline = time.monotonic() + 3
        while True:
            items = self.catalogue(client)
            drained = not any(item["index_pending"] for item in items)
            if (len(items) >= minimum and drained) or time.monotonic() >= deadline:
                self.assertGreaterEqual(len(items), minimum, "Durable episode was not locally processed into catalogue evidence")
                self.assertTrue(drained, "Local processing did not drain within the wait")
                return items
            time.sleep(.02)

    def seeded_item(self):
        self.login()
        packet = self.packet()
        self.assert_ack(self.post_packet(packet), packet, status="stored")
        return packet, self.wait_items()[0]

    def assert_safe_error(self, response):
        self.assertGreaterEqual(response.status_code, 400, response.text)
        for value in (SECRET, LEGACY, str(self.root), "UPSTREAM-PRIVATE"):
            self.assertNotIn(value, response.text)
            self.assertNotIn(value, str(response.headers))
        self.assertEqual(response.headers.get("cache-control"), "no-store")

    # Named helpers are also the explicit replacement oracles for the 23 legacy methods.
    def check_synthetic_startup(self):
        self.assertFalse(any(os.environ.get(key) for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DEEPGRAM_API_KEY")))
        self.assertEqual(self.client.get("/api/auth/session").json(), {"authenticated": False, "configured": True})
        self.login()
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.catalogue(), [])

    def check_unauthenticated(self):
        for path in ("/api/health", "/api/items", "/api/items/missing", "/api/items/missing/history", "/api/items/missing/image"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 401, response.text)
                self.assert_safe_error(response)
        for path, body in (("/api/episodes", self.packet()), ("/api/chat", {"text": "hello"}),
                           ("/api/items/missing/name", {"name": "new"})):
            response = self.client.post(path, json=body, headers={"origin": ORIGIN})
            self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(self.processor.calls, [])

    def check_expiry_and_missing_pin(self):
        self.login()
        self.now += 366 * 86400
        self.assertEqual(self.client.get("/api/items").status_code, 401)
        no_pin = self.new_client(database=self.root / "unconfigured.sqlite3", pin="")
        self.assertEqual(no_pin.get("/api/auth/session").json(), {"authenticated": False, "configured": False})
        self.assertEqual(no_pin.post("/api/auth/login", json={"pin": PIN}, headers={"origin": ORIGIN}).status_code, 503)
        self.assertEqual(no_pin.get("/api/items").status_code, 401)

    def check_catalogue_history_evidence(self):
        packet, item = self.seeded_item()
        ident = item["item_id"]
        self.assertEqual(self.client.get(f"/api/items/{ident}").json()["item_id"], ident)
        history = self.client.get(f"/api/items/{ident}/history")
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(len(history.json()["observations"]), 1)
        self.assertNotIn(str(self.root), history.text)
        self.assertIsNotNone(item["image_url"], item)
        image = self.client.get(item["image_url"])
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.headers.get("cache-control"), "no-store")
        expected = base64.b64decode(packet["keyframes"][-1]["jpeg_b64"])
        self.assertEqual(image.content, expected)

    def check_no_evidence_abstains(self):
        self.login()
        response = self.client.post("/api/chat", json={"text": "where is an unseen object"}, headers={"origin": ORIGIN})
        self.assertEqual(response.status_code, 200, response.text)
        answer = response.json()
        self.assertEqual(answer["shape"], "abstain")
        self.assertEqual(answer["members"], [])
        self.assertNotIn("last saw", answer["text"].lower())

    def check_rename(self):
        _, item = self.seeded_item()
        response = self.client.post(f"/api/items/{item['item_id']}/name", json={"name": "My test block"}, headers={"origin": ORIGIN})
        self.assertEqual(response.status_code, 200, response.text)
        items = self.catalogue()
        self.assertEqual(len(items), 1)
        self.assertEqual((items[0]["item_id"], items[0]["name"]), (item["item_id"], "My test block"))

    def check_origin_and_forged_identity(self):
        self.login()
        packet = self.packet()
        for origin in (None, "https://evil.invalid", ORIGIN + ".evil.invalid"):
            headers = {} if origin is None else {"origin": origin}
            response = self.client.post("/api/episodes", json=packet, headers=headers)
            self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.processor.calls, [])
        for field, value in (("profile_id", "other"), ("processor", "fixture"), ("identity_state", "trusted"),
                             ("observations", [self.processor.observations[packet["episode_id"]]])):
            response = self.post_packet({**packet, field: value})
            self.assertEqual(response.status_code, 400, response.text)
            self.assertNotIn("ack", response.json())
        self.assertEqual(self.catalogue(), [])

    def check_profile_image_isolation(self):
        _, item = self.seeded_item()
        other = self.new_client(profile="other-profile")
        self.login(other)
        self.assertEqual(self.catalogue(other), [])
        for suffix in ("", "/history", "/image"):
            response = other.get(f"/api/items/{item['item_id']}{suffix}")
            self.assertEqual(response.status_code, 404, response.text)
        for path in ("/api/items/..%5Cprivate/image", "/api/items/%2e%2e%2fkey.pem/image", "/key.pem", "/cert.pem"):
            self.assertIn(self.client.get(path).status_code, (400, 404, 410))

    def check_corrupt_database(self):
        path = self.root / "corrupt.sqlite3"
        path.write_bytes(b"SYNTHETIC-NOT-SQLITE")
        client = self.new_client(database=path)
        self.assertEqual(client.get("/api/items").status_code, 401)
        self.login(client)
        self.assert_safe_error(client.get("/api/items"))
        self.assertEqual(path.read_bytes(), b"SYNTHETIC-NOT-SQLITE")

    def check_database_independent_auth(self):
        absent = self.root / "absent.sqlite3"
        self.assertFalse(absent.exists())
        client = self.new_client(database=absent)
        self.assertEqual(client.get("/api/items").status_code, 401)
        self.login(client)
        self.assertEqual(self.catalogue(client), [])

    def check_retired(self):
        for client_authenticated in (False, True):
            if client_authenticated:
                self.login()
            for path in RETIRED:
                for method in ("GET", "POST"):
                    with self.subTest(path=path, method=method, authenticated=client_authenticated):
                        response = self.client.request(method, path, headers={"origin": ORIGIN})
                        self.assertIn(response.status_code, (404, 410), response.text)
                        self.assert_safe_error(response)
        self.assertEqual(self.processor.calls, [])

    def check_invalid_location_payload(self):
        self.login()
        for fix in ({"status": "denied"}, {"lat": 1, "lon": 2}, {"place": "invented home"}):
            packet = self.packet()
            response = self.post_packet({**packet, "location": fix})
            self.assertEqual(response.status_code, 400)
            self.assertNotIn("ack", response.json())
        self.assertEqual(self.catalogue(), [])

    def check_duplicate(self):
        self.login()
        packet = self.packet()
        self.assert_ack(self.post_packet(packet), packet, status="stored")
        raw = encode_packet(packet, pretty=True)
        self.assertNotEqual(raw, encode_packet(packet))
        self.assert_ack(self.post_packet(packet, raw=raw), packet, raw, "duplicate")
        self.assertEqual(len(self.wait_items()), 1)
        self.assertEqual(self.processor.calls.count(packet["episode_id"]), 1)

    def check_raw_rejected(self):
        self.login()
        response = self.client.post("/api/episodes", content=base64.b64decode(synthetic_jpeg(20)), headers={"origin": ORIGIN})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertNotIn("ack", response.json())
        self.assertEqual(self.processor.calls, [])

    def check_logout(self):
        self.login()
        stolen = dict(self.client.cookies)
        response = self.client.post("/api/auth/logout", headers={"origin": ORIGIN})
        self.assertEqual(response.status_code, 200)
        for key, value in stolen.items():
            self.client.cookies.set(key, value)
        response = self.post_packet(self.packet())
        self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(self.processor.calls, [])

    def check_cloud_disabled(self):
        self.login()
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": SECRET, "DEEPGRAM_API_KEY": SECRET}):
            response = self.client.post("/api/chat", json={"text": "hello", "mode": "cloud"}, headers={"origin": ORIGIN})
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["code"], "chat_not_configured")
        self.assert_safe_error(response)

    def check_cloud_error_does_not_stop_memory(self):
        # Provider-only injection is NOT policy authorization. The milestone must
        # reject it before invocation. Actual configured-provider fault handling
        # belongs to the separate bounded-cost integration gate, not a fake pass.
        provider = MagicMock(side_effect=RuntimeError(SECRET + " UPSTREAM-PRIVATE"))
        client = self.new_client(chat_provider=provider)
        self.login(client)
        response = client.post("/api/chat", json={"text": "hello", "mode": "cloud"}, headers={"origin": ORIGIN})
        self.assertEqual(response.status_code, 503, response.text)
        self.assert_safe_error(response)
        provider.assert_not_called()
        packet = self.packet()
        self.assert_ack(self.post_packet(packet, client=client), packet)
        self.assertEqual(len(self.wait_items(client)), 1)


class BootstrapContractTests(MemoryApiFixture):
    def test_T_NO_CHAT_KEY_real_app_store_process_restart_catalogue(self):
        self.check_synthetic_startup()
        first = self.packet()
        self.assert_ack(self.post_packet(first), first, status="stored")
        original = self.wait_items()[0]
        self.assertEqual(original["location_status"], "placed")
        self.assertEqual(original["location_text"], "fixture left")
        second = self.packet(phase=1)
        self.assert_ack(self.post_packet(second), second, status="stored")
        moved = self.wait_items()[0]
        self.assertEqual(moved["item_id"], original["item_id"])
        self.assertEqual(moved["location_text"], "fixture right")
        self.assertEqual(moved["observed_at_ms"], ANCHOR_MS + 12200)
        self.client.__exit__(None, None, None)
        restarted = self.new_client()
        self.login(restarted)
        recovered = self.catalogue(restarted)
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0], moved)
        history = restarted.get(f"/api/items/{moved['item_id']}/history")
        self.assertEqual(len(history.json()["observations"]), 2)
        self.assertEqual(len(self.processor.calls), 2)

    def test_authentication_is_independent_of_missing_database(self):
        self.check_database_independent_auth()

    def test_login_cookie_and_logout_revocation(self):
        response = self.login()
        cookie = response.headers["set-cookie"].lower()
        for flag in ("httponly", "samesite=strict", "secure", "max-age="):
            self.assertIn(flag, cookie)
        self.assertNotIn(PIN, cookie)
        self.check_logout()

    def test_missing_pin_and_expiry_fail_closed(self):
        self.check_expiry_and_missing_pin()

    def test_origin_and_client_trusted_processor_fields_are_rejected(self):
        self.check_origin_and_forged_identity()

    def test_semantic_duplicate_echoes_this_transport_digest(self):
        self.check_duplicate()

    def test_conflict_is_retained_but_not_reinterpreted(self):
        packet, item = self.seeded_item()
        conflict = copy.deepcopy(packet)
        conflict["outcome_hint"] = "gap"
        ack = self.assert_ack(self.post_packet(conflict), conflict, status="conflict")
        again = self.assert_ack(self.post_packet(conflict), conflict)
        self.assertEqual(again["revision_no"], ack["revision_no"])
        self.assertEqual(self.catalogue()[0], item)
        self.assertEqual(self.processor.calls.count(packet["episode_id"]), 1)

    def test_revision_cap_returns_409_without_durable_ack(self):
        packet, item = self.seeded_item()
        last = None
        for n in range(1, 9):
            revision = copy.deepcopy(packet)
            revision["clock_anchor"]["wall_ms"] += n
            last = self.post_packet(revision)
            if n < 8:
                self.assert_ack(last, revision, status="conflict")
        self.assertEqual(last.status_code, 409, last.text)
        self.assertNotIn("ack", last.json())
        self.assertEqual(self.catalogue()[0], item)

    def test_cross_profile_cannot_select_or_read_another_profile(self):
        self.check_profile_image_isolation()

    def test_actual_request_byte_cap_returns_413_without_ack(self):
        self.login()
        packet = self.packet()
        raw = encode_packet(packet)
        raw += b" " * (4 * 1024 * 1024 + 1 - len(raw))
        response = self.post_packet(packet, raw=raw)
        self.assertEqual(response.status_code, 413, response.text)
        self.assertNotIn("ack", response.json())
        self.assertEqual(self.processor.calls, [])
        self.assertEqual(self.catalogue(), [])

    def test_malformed_packet_returns_400_without_processing(self):
        self.login()
        for raw in (b"{", b"[]", b'{"schema_version":1,"schema_version":1}'):
            response = self.client.post("/api/episodes", content=raw, headers={"origin": ORIGIN})
            self.assertEqual(response.status_code, 400, response.text)
            self.assertNotIn("ack", response.json())
        self.assertEqual(self.processor.calls, [])

    def test_chat_credentials_alone_do_not_authorize_cloud(self):
        self.check_cloud_disabled()

    def test_chat_error_does_not_stop_memory(self):
        self.check_cloud_error_does_not_stop_memory()

    def test_catalogue_image_and_history(self):
        self.check_catalogue_history_evidence()

    def test_no_reliable_evidence_abstains_without_image(self):
        self.check_no_evidence_abstains()

    def test_retired_deepgram_and_nonmemory_routes_never_execute(self):
        self.check_retired()

    def test_unknown_processorless_evidence_cannot_claim_confidence(self):
        client = self.new_client(processor=None, database=self.root / "default-local.sqlite3")
        self.login(client)
        packet = self.packet(register=False)
        self.assert_ack(self.post_packet(packet, client=client), packet)
        response = client.post("/api/chat", json={"text": "where is my medication"}, headers={"origin": ORIGIN})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotEqual(response.json()["shape"], "confident")

    def test_served_page_module_graph_is_complete(self):
        # The combined app is the supported entry point: every stylesheet, script and
        # ES-module import reachable from GET / must be served by the asset allowlist.
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("text/html", page.headers.get("content-type", ""))
        pending = re.findall(r'(?:src|href)="(/assets/[^"]+)"', page.text)
        self.assertTrue(pending, "memory.html references no /assets files")
        seen = set()
        while pending:
            path = pending.pop()
            if path in seen:
                continue
            seen.add(path)
            with self.subTest(asset=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, f"{path} is not served by the app")
                if path.endswith(".js"):
                    self.assertIn("javascript", response.headers.get("content-type", ""))
                    for relative in re.findall(r"""from\s+['"](\.\/[^'"]+)['"]""", response.text):
                        pending.append("/assets/" + relative[2:])
        self.assertGreaterEqual(len(seen), 4)


class PacketContractTests(unittest.TestCase):
    def packet(self):
        jpeg = synthetic_jpeg(20)
        return {"schema_version": 1, "episode_id": str(uuid.UUID(int=77, version=4)),
                "device_id": DEVICE, "session_id": SESSION, "t_start_ms": 0, "t_end_ms": 1000,
                "clock_anchor": {"mono_ms": 0, "wall_ms": ANCHOR_MS}, "capture": {"width": 160, "height": 120},
                "analysis": {"width": 80, "height": 60}, "keyframes": [
                    {"frame_id": "first", "t_ms": 0, "role": "pre_contact", "jpeg_b64": jpeg},
                    {"frame_id": "last", "t_ms": 1000, "role": "rest", "jpeg_b64": jpeg}],
                "capture_mode": "manual", "outcome_hint": "released"}

    def test_real_synthetic_jpegs_identical_pixels_and_short_packet_are_valid(self):
        from perception.episode import parse_packet
        packet = self.packet()
        self.assertEqual(len(parse_packet(encode_packet(packet)).keyframes), 2)
        packet["keyframes"] = packet["keyframes"][:1]
        self.assertEqual(len(parse_packet(encode_packet(packet)).keyframes), 1)

    def test_invalid_time_dimension_and_image_cases_hit_the_intended_guard(self):
        from perception.episode import parse_packet
        cases = []
        packet = self.packet()
        packet["keyframes"][1]["t_ms"] = 0
        cases.append((packet, "frame ordering"))
        packet = self.packet()
        packet["capture"]["width"] = 159
        cases.append((packet, "dimensions do not match"))
        packet = self.packet()
        packet["keyframes"][1]["jpeg_b64"] = "not-base64!"
        cases.append((packet, "Invalid JPEG base64"))
        for packet, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                parse_packet(encode_packet(packet))

    def test_signed_image_depth_world_coordinates_and_finite_numbers(self):
        from perception.episode import parse_packet
        packet = self.packet()
        hand = {"landmarks": [{"x": .5, "y": .5, "z": -.25} for _ in range(21)],
                "world_landmarks": [{"x": -.03, "y": .02, "z": -.01} for _ in range(21)],
                "hand_bbox": [.2, .2, .8, .8], "handedness": "unknown"}
        packet["landmarks"] = [{"frame_id": "analysis-1", "t_ms": 500, "hands": [hand]}]
        parsed = parse_packet(encode_packet(packet))
        self.assertEqual(parsed.landmarks[0].hands[0].landmarks[0].z, -.25)
        for field, value in (("t_start_ms", True), ("t_end_ms", 9007199254740992)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                parse_packet(encode_packet({**packet, field: value}))
        hand["landmarks"][0]["x"] = 1.01
        with self.assertRaises(ValueError):
            parse_packet(encode_packet(packet))


if __name__ == "__main__":
    unittest.main(verbosity=2)
