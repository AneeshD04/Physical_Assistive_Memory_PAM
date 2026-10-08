"""CP2 acceptance: model inventory, manifest-gated /assets/models/ serving and the
server-decided automatic_hand_recognition capability.

    python3 -B server/test_cp2_models.py -v

Reuses bootstrap.MemoryApiFixture (temp DB, PIN, egress and private-file guards)
but builds its own apps with create_app(models_dir=<temp>, licence_register=<temp
file>) so nothing under phone/assets/models or docs/ is read. Model "files" are
synthetic bytes: no model is downloaded, loaded or run. PAM_ENABLE_HAND_MODEL is
unset by the fixture and set per test with patch.dict.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
import test_memory_bootstrap as bootstrap  # noqa: E402

ORIGIN = bootstrap.ORIGIN
HAND = "automatic_hand_recognition"
ENV = "PAM_ENABLE_HAND_MODEL"
SHA = "0123456789abcdef" * 4
ASSETS = (("hand_landmarker.task", b"SYNTHETIC-TASK-BYTES-NOT-A-MODEL", "application/octet-stream"),
          ("vision_bundle.mjs", b"export const synthetic = true;\n", "text/javascript"),
          ("vision_wasm_internal.js", b"// synthetic loader\n", "text/javascript"),
          ("vision_wasm_internal.wasm", b"\x00asm\x01\x00\x00\x00", "application/wasm"))
REASONS = {
    "unprovisioned": "Hand model assets are not provisioned on this server.",
    "unlicensed": "Hand model licence is not recorded as VERIFIED-COMMERCIAL in docs/LICENSES.md.",
    "disabled": "Automatic hand recognition is not enabled (PAM_ENABLE_HAND_MODEL).",
}


def entry(name, version="float16/1", sha256=SHA, licence="Apache-2.0", **extra):
    value = {"name": name, "version": version, "sha256": sha256, "licence": licence,
             "url": "https://example.invalid/" + name, "fetched_at": "2026-10-08T00:00:00Z"}
    value.update(extra)
    return value


class ModelsFixture(bootstrap.MemoryApiFixture):
    def setUp(self):
        super().setUp()
        self.models_dir = self.root / "models"
        self.models_dir.mkdir()
        self.register = self.root / "LICENSES.md"
        self.app_client = self.models_client()

    def models_client(self, *, models_dir=None, licence_register=None, database=None, login=True):
        module = importlib.import_module("server.app")
        app = module.create_app(database_path=self.db if database is None else database, profile_id="local",
                                processor=self.processor, clock=self.clock, auth_pin=bootstrap.PIN,
                                models_dir=self.models_dir if models_dir is None else models_dir,
                                licence_register=self.register if licence_register is None else licence_register)
        self.apps.append(app)
        client = TestClient(app, base_url=ORIGIN, raise_server_exceptions=False)
        self.enterContext(client)
        if login:
            self.login(client)
        return client

    def write_manifest(self, assets=None, raw=None):
        path = self.models_dir / "MANIFEST.json"
        if raw is not None:
            path.write_bytes(raw)
        else:
            path.write_text(json.dumps({"assets": [entry(name) for name, _, _ in ASSETS] if assets is None else assets}), encoding="utf-8")
        return path

    def write_files(self, names=None):
        for name, content, _ in ASSETS:
            if names is None or name in names:
                target = self.models_dir / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)

    # docs/LICENSES.md rule 2 (contract change 2026-10-08): a licence counts as recorded
    # only when a register LINE names the base file name AND carries the literal token
    # VERIFIED-COMMERCIAL AND carries neither UNVERIFIED nor REJECTED.
    VERIFIED_ROWS = "".join(f"| {name} | Apache-2.0 | synthetic | status: VERIFIED-COMMERCIAL |\n" for name, _, _ in ASSETS)

    def write_register(self, text=None):
        text = self.VERIFIED_ROWS if text is None else text
        self.register.write_text("# Synthetic licence register (tester fixture, not docs/LICENSES.md)\n" + text, encoding="utf-8")

    def provision(self, *, register=True, env=True):
        self.write_manifest()
        self.write_files()
        if register:
            self.write_register()
        if env:
            self.enterContext(patch.dict(os.environ, {ENV: "1"}))

    def health(self, client=None):
        client = self.app_client if client is None else client
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertNotIn(str(self.root), response.text)
        body = response.json()
        self.assertIsInstance(body["models"], list)
        for model in body["models"]:
            self.assertEqual(set(model), {"name", "provisioned", "licence_recorded", "version"}, model)
            self.assertIsInstance(model["provisioned"], bool)
            self.assertIsInstance(model["licence_recorded"], bool)
        return body

    def hand(self, capabilities):
        entries = [cap for cap in capabilities if cap.get("name") == HAND]
        self.assertEqual(len(entries), 1, capabilities)
        self.assertEqual(set(entries[0]), {"name", "enabled", "reason"})
        return entries[0]

    def capability_everywhere(self, client=None):
        """The hand capability from /api/health and from /api/items must be identical."""
        client = self.app_client if client is None else client
        from_health = self.hand(self.health(client)["capabilities"])
        items = client.get("/api/items")
        self.assertEqual(items.status_code, 200, items.text)
        from_items = self.hand(items.json()["capabilities"])
        self.assertEqual(from_health, from_items, "health and items disagree on the hand capability")
        return from_health

    def model_get(self, name, client=None):
        client = self.app_client if client is None else client
        return client.get("/assets/models/" + name)

    def raw_get(self, path, client=None):
        """A GET with the path placed verbatim in the ASGI scope (an HTTP client
        would normalise dot segments before they reach the server)."""
        client = self.app_client if client is None else client
        app = client.app
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "https",
                 "path": path, "raw_path": path.encode(), "query_string": b"", "root_path": "",
                 "headers": [(b"host", b"testserver")], "client": ("127.0.0.1", 50000), "server": ("testserver", 443)}
        messages = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        asyncio.run(app(scope, receive, send))
        status = next(m["status"] for m in messages if m["type"] == "http.response.start")
        body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        return status, body

    def assert_served(self, name, content, media_type):
        response = self.model_get(name)
        self.assertEqual(response.status_code, 200, f"{name}: {response.text}")
        self.assertEqual(response.content, content)
        self.assertEqual(response.headers.get("content-type", "").split(";")[0], media_type, name)
        self.assertEqual(response.headers.get("cache-control"), "private, max-age=86400", name)
        self.assertEqual(response.headers.get("x-content-type-options"), "nosniff")


class ModelInventoryTests(ModelsFixture):
    def test_no_manifest_means_models_empty_and_unprovisioned_even_with_env_flag(self):
        for flag in (None, "1"):
            with self.subTest(env=flag):
                with patch.dict(os.environ, {} if flag is None else {ENV: flag}):
                    body = self.health()
                    self.assertEqual(body["models"], [])
                    capability = self.capability_everywhere()
                    self.assertEqual(capability, {"name": HAND, "enabled": False, "reason": REASONS["unprovisioned"]})
                    self.assertEqual(self.model_get("MANIFEST.json").status_code, 404)
                    self.assertEqual(self.model_get("hand_landmarker.task").status_code, 404)

    def test_manifest_and_files_without_env_flag(self):
        self.write_manifest()
        self.write_files()
        # Register names the file: provisioned and licensed, only the flag is missing.
        self.write_register()
        body = self.health()
        self.assertEqual(body["models"], [{"name": name, "provisioned": True, "licence_recorded": True, "version": "float16/1"}
                                          for name, _, _ in ASSETS])
        self.assertEqual(self.capability_everywhere(), {"name": HAND, "enabled": False, "reason": REASONS["disabled"]})
        for name, _, _ in ASSETS:
            self.assertEqual(self.model_get(name).status_code, 404, name)
        response = self.model_get("MANIFEST.json")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Asset not found."})
        self.assert_safe_error(response)
        # Register missing: the licence is not recorded.
        self.register.unlink()
        self.assertEqual([m["licence_recorded"] for m in self.health()["models"]], [False] * len(ASSETS))
        self.assertEqual(self.capability_everywhere(), {"name": HAND, "enabled": False, "reason": REASONS["unlicensed"]})
        # Register present but naming a different file: still not recorded.
        self.write_register("| other_model.task | Apache-2.0 | not the hand model | status: VERIFIED-COMMERCIAL |\n")
        self.assertFalse(self.health()["models"][0]["licence_recorded"])
        self.assertEqual(self.capability_everywhere()["reason"], REASONS["unlicensed"])
        # Register names the file but the manifest entry has a blank licence.
        self.write_register()
        self.write_manifest([entry("hand_landmarker.task", licence="   ")] + [entry(name) for name, _, _ in ASSETS[1:]])
        self.assertFalse(self.health()["models"][0]["licence_recorded"])
        self.assertEqual(self.capability_everywhere()["reason"], REASONS["unlicensed"])
        self.write_manifest()
        # Structured gate: the file name alone, or with a blocking token, is not a grant.
        others = "".join(f"| {name} | Apache-2.0 | synthetic | status: VERIFIED-COMMERCIAL |\n" for name, _, _ in ASSETS[1:])
        negatives = {
            "no_token": "| hand_landmarker.task | Apache-2.0 | synthetic |\n",
            "verified_and_unverified_same_line": "| hand_landmarker.task | Apache-2.0 | was VERIFIED-COMMERCIAL, now status: UNVERIFIED |\n",
            "verified_and_rejected_same_line": "| hand_landmarker.task | Apache-2.0 | VERIFIED-COMMERCIAL REJECTED |\n",
            "unverified_only": "| hand_landmarker.task | Apache-2.0 | status: UNVERIFIED |\n",
            "token_on_another_line": "| hand_landmarker.task | Apache-2.0 | synthetic |\nstatus: VERIFIED-COMMERCIAL\n",
            "name_split_across_lines": "| hand_landmarker\n.task | Apache-2.0 | status: VERIFIED-COMMERCIAL |\n",
        }
        for name, row in negatives.items():
            with self.subTest(register=name):
                self.write_register(row + others)
                models = {m["name"]: m for m in self.health()["models"]}
                self.assertFalse(models["hand_landmarker.task"]["licence_recorded"], name)
                self.assertTrue(models["vision_bundle.mjs"]["licence_recorded"], name)
                self.assertEqual(self.capability_everywhere()["reason"], REASONS["unlicensed"], name)
        # A later UNVERIFIED row does not cancel an earlier verified row (line-scoped), and vice versa.
        self.write_register("| hand_landmarker.task | Apache-2.0 | status: VERIFIED-COMMERCIAL |\n"
                            "| hand_landmarker.task | Apache-2.0 | older entry, status: UNVERIFIED |\n" + others)
        self.assertTrue({m["name"]: m for m in self.health()["models"]}["hand_landmarker.task"]["licence_recorded"])
        self.assertEqual(self.capability_everywhere()["reason"], REASONS["disabled"])
        from server.memory_app import licence_verified
        self.assertFalse(licence_verified("| hand_landmarker.task | VERIFIED-COMMERCIAL UNVERIFIED |", "hand_landmarker.task"))
        self.assertFalse(licence_verified("| hand_landmarker.task | VERIFIED-COMMERCIAL |", ""))
        self.assertTrue(licence_verified("| hand_landmarker.task | VERIFIED-COMMERCIAL |", "hand_landmarker.task"))

    def test_reason_precedence_unprovisioned_over_unlicensed_over_disabled(self):
        self.write_manifest()
        self.write_files(names=[name for name, _, _ in ASSETS[1:]])  # hand model file absent
        with patch.dict(os.environ, {ENV: "1"}):
            self.assertEqual(self.capability_everywhere()["reason"], REASONS["unprovisioned"])
            models = {m["name"]: m for m in self.health()["models"]}
            self.assertFalse(models["hand_landmarker.task"]["provisioned"])
            self.assertTrue(models["vision_bundle.mjs"]["provisioned"])
            self.assertEqual(self.model_get("hand_landmarker.task").status_code, 404)
            self.assertEqual(self.model_get("vision_bundle.mjs").status_code, 200, "other listed files are served")
        self.write_files()
        self.assertEqual(self.capability_everywhere()["reason"], REASONS["unlicensed"], "no register: unlicensed beats disabled")
        self.write_register()
        self.assertEqual(self.capability_everywhere()["reason"], REASONS["disabled"])
        with patch.dict(os.environ, {ENV: "1"}):
            self.assertTrue(self.capability_everywhere()["enabled"])
        with patch.dict(os.environ, {ENV: "true"}):
            self.assertEqual(self.capability_everywhere()["reason"], REASONS["disabled"], 'only "1" enables')
        with patch.dict(os.environ, {ENV: "0"}):
            self.assertEqual(self.capability_everywhere()["reason"], REASONS["disabled"])

    def test_manifest_without_a_hand_landmarker_entry_is_unprovisioned(self):
        self.write_manifest([entry(name) for name, _, _ in ASSETS[1:]])
        self.write_files()
        self.write_register()
        with patch.dict(os.environ, {ENV: "1"}):
            self.assertEqual(len(self.health()["models"]), 3)
            self.assertEqual(self.capability_everywhere()["reason"], REASONS["unprovisioned"])
            self.assertEqual(self.model_get("hand_landmarker.task").status_code, 404, "on disk but unlisted")

    def test_env_flag_and_register_are_read_per_request(self):
        self.provision(env=False)
        self.assertEqual(self.capability_everywhere()["reason"], REASONS["disabled"])
        with patch.dict(os.environ, {ENV: "1"}):
            self.assertTrue(self.capability_everywhere()["enabled"])
            self.assertEqual(self.model_get("MANIFEST.json").status_code, 200)
            self.register.unlink()
            self.assertEqual(self.capability_everywhere()["reason"], REASONS["unlicensed"])
            self.assertEqual(self.model_get("MANIFEST.json").status_code, 200, "serving is gated by manifest and flag, the capability by the register too")
        self.assertEqual(self.model_get("MANIFEST.json").status_code, 404)

    def test_store_capability_is_overridden_not_duplicated(self):
        self.provision()
        capabilities = self.health()["capabilities"]
        self.assertEqual([cap["name"] for cap in capabilities].count(HAND), 1)
        names = [cap["name"] for cap in capabilities]
        self.assertIn("local_processing", names)
        self.assertIn("local_text_chat", names)
        hand = self.hand(capabilities)
        self.assertTrue(hand["enabled"])
        self.assertIn("float16/1", hand["reason"])
        self.assertIn("unmeasured", hand["reason"].lower(), "an enabled model is still not a measured accuracy claim")
        from server.memory_app import hand_model_capability, HAND_REASONS, model_inventory
        self.assertEqual(HAND_REASONS, REASONS)
        self.assertEqual(hand, hand_model_capability(model_inventory(self.models_dir, self.register)))


class ModelServingTests(ModelsFixture):
    def test_enabled_serving_headers_and_media_types(self):
        self.provision()
        self.assertTrue(self.capability_everywhere()["enabled"])
        manifest = self.model_get("MANIFEST.json")
        self.assertEqual(manifest.status_code, 200, manifest.text)
        self.assertEqual(manifest.headers.get("cache-control"), "no-store")
        self.assertEqual(manifest.headers.get("content-type", "").split(";")[0], "application/json")
        self.assertEqual(manifest.json(), json.loads((self.models_dir / "MANIFEST.json").read_text()))
        for name, content, media_type in ASSETS:
            with self.subTest(name=name):
                self.assert_served(name, content, media_type)
        # Unauthenticated clients get the same gating; model files carry no personal data.
        anonymous = self.models_client(login=False)
        self.assertEqual(anonymous.get("/api/items").status_code, 401)
        self.assertEqual(anonymous.get("/assets/models/vision_bundle.mjs").status_code, 200)

    def test_unlisted_traversal_symlink_and_odd_names_are_404(self):
        self.provision()
        (self.models_dir / "unlisted.task").write_bytes(b"SYNTHETIC-UNLISTED")
        (self.models_dir / "notes.txt").write_bytes(b"SYNTHETIC-TEXT")
        outside = self.root / "outside.task"
        outside.write_bytes(b"SYNTHETIC-OUTSIDE")
        # (An HTTP client normalises "./" and strips "?query"/"#fragment" before the
        # path reaches the server; those spellings are exercised through raw_get below.)
        for name in ("unlisted.task", "notes.txt", "", ".", "..", "MANIFEST.json/", "hand_landmarker.task/",
                     "%2e%2e/outside.task", "..%2Foutside.task", "%2e%2e%2f%2e%2e%2fmemory.html",
                     "hand_landmarker.task%00", "HAND_LANDMARKER.TASK", "models/hand_landmarker.task"):
            with self.subTest(name=name):
                response = self.model_get(name)
                self.assertEqual(response.status_code, 404, f"{name!r}: {response.status_code} {response.text[:80]}")
                self.assertNotIn("SYNTHETIC", response.text)
        for path in ("/assets/models/../outside.task", "/assets/models/../../memory.html", "/assets/models/../../server/memory_app.py",
                     "/assets/models/./hand_landmarker.task", "/assets/models/sub/../hand_landmarker.task", "/assets/models/..",
                     "/assets/../phone/assets/models/hand_landmarker.task"):
            with self.subTest(raw=path):
                status, body = self.raw_get(path)
                self.assertEqual(status, 404, f"{path}: {status} {body[:80]!r}")
                self.assertNotIn(b"SYNTHETIC", body)
                self.assertNotIn(b"<!doctype", body.lower())
        # A symlink in place of a listed file: never served, reported unprovisioned.
        (self.models_dir / "hand_landmarker.task").unlink()
        os.symlink(outside, self.models_dir / "hand_landmarker.task")
        self.assertEqual(self.model_get("hand_landmarker.task").status_code, 404)
        self.assertFalse({m["name"]: m for m in self.health()["models"]}["hand_landmarker.task"]["provisioned"])
        self.assertEqual(self.capability_everywhere()["reason"], REASONS["unprovisioned"])
        # A symlinked directory segment is refused too.
        real_dir = self.root / "realwasm"
        real_dir.mkdir()
        (real_dir / "vision_wasm_internal.wasm").write_bytes(b"\x00asm")
        os.symlink(real_dir, self.models_dir / "wasm")
        self.write_manifest([entry("hand_landmarker.task")] + [entry(name) for name, _, _ in ASSETS[1:3]] + [entry("wasm/vision_wasm_internal.wasm")])
        self.assertEqual(self.model_get("wasm/vision_wasm_internal.wasm").status_code, 404)
        self.assertFalse({m["name"]: m for m in self.health()["models"]}["wasm/vision_wasm_internal.wasm"]["provisioned"])
        # A symlinked manifest is not a manifest.
        (self.models_dir / "MANIFEST.json").unlink()
        real_manifest = self.root / "real-manifest.json"
        real_manifest.write_text(json.dumps({"assets": [entry("vision_bundle.mjs")]}))
        os.symlink(real_manifest, self.models_dir / "MANIFEST.json")
        self.assertEqual(self.health()["models"], [])
        self.assertEqual(self.model_get("MANIFEST.json").status_code, 404)
        self.assertEqual(self.model_get("vision_bundle.mjs").status_code, 404)

    def test_nested_listed_name_is_served_and_the_bare_name_is_not(self):
        self.write_manifest([entry("hand_landmarker.task")] + [entry(name) for name, _, _ in ASSETS[1:3]] + [entry("wasm/vision_wasm_internal.wasm")])
        self.write_files(names=[name for name, _, _ in ASSETS[:3]])
        (self.models_dir / "wasm").mkdir()
        (self.models_dir / "wasm" / "vision_wasm_internal.wasm").write_bytes(b"\x00asm\x01\x00\x00\x00")
        self.write_register()
        with patch.dict(os.environ, {ENV: "1"}):
            self.assert_served("wasm/vision_wasm_internal.wasm", b"\x00asm\x01\x00\x00\x00", "application/wasm")
            self.assertEqual(self.model_get("vision_wasm_internal.wasm").status_code, 404)
            self.assertTrue({m["name"]: m for m in self.health()["models"]}["wasm/vision_wasm_internal.wasm"]["provisioned"])
            self.assertTrue(self.capability_everywhere()["enabled"])

    def test_invalid_manifests_serve_nothing_and_report_no_models(self):
        self.write_files()
        self.write_register()
        good = [entry(name) for name, _, _ in ASSETS]
        cases = {
            "not_an_object": json.dumps([entry("hand_landmarker.task")]).encode(),
            "assets_not_a_list": json.dumps({"assets": {"hand_landmarker.task": entry("hand_landmarker.task")}}).encode(),
            "no_assets_key": json.dumps({"files": good}).encode(),
            "entry_not_object": json.dumps({"assets": good + ["hand_landmarker.task"]}).encode(),
            "bad_name_traversal": json.dumps({"assets": good + [entry("../outside.task")]}).encode(),
            "bad_name_absolute": json.dumps({"assets": good + [entry("/etc/hostname.task")]}).encode(),
            "bad_name_backslash": json.dumps({"assets": good + [entry("wasm\\vision.wasm")]}).encode(),
            "bad_name_hidden": json.dumps({"assets": good + [entry(".hidden.task")]}).encode(),
            "bad_name_suffix": json.dumps({"assets": good + [entry("weights.pt")]}).encode(),
            "bad_name_manifest_itself": json.dumps({"assets": good + [entry("MANIFEST.json")]}).encode(),
            "bad_name_too_long": json.dumps({"assets": good + [entry("a" * 120 + ".task")]}).encode(),
            "bad_name_non_ascii": json.dumps({"assets": good + [entry("modèle.task")]}).encode(),
            "duplicate_name": json.dumps({"assets": good + [entry("hand_landmarker.task")]}).encode(),
            "bad_sha256_short": json.dumps({"assets": [entry("hand_landmarker.task", sha256="abc")] + good[1:]}).encode(),
            "bad_sha256_uppercase": json.dumps({"assets": [entry("hand_landmarker.task", sha256=SHA.upper())] + good[1:]}).encode(),
            "missing_version": json.dumps({"assets": [entry("hand_landmarker.task", version=None)] + good[1:]}).encode(),
            "missing_licence": json.dumps({"assets": [entry("hand_landmarker.task", licence=None)] + good[1:]}).encode(),
            "control_character_field": json.dumps({"assets": [entry("hand_landmarker.task", version="1\n2")] + good[1:]}).encode(),
            "too_many_entries": json.dumps({"assets": [entry(f"file{i}.task") for i in range(65)]}).encode(),
            "not_json": b"{not json",
            "not_utf8": b"\xff\xfe\x00",
            "empty": b"",
            "oversized": (json.dumps({"assets": good, "padding": "x" * (64 * 1024)})).encode(),
        }
        self.assertGreater(len(cases["oversized"]), 64 * 1024)
        with patch.dict(os.environ, {ENV: "1"}):
            for name, raw in cases.items():
                with self.subTest(manifest=name):
                    self.write_manifest(raw=raw)
                    self.assertEqual(self.health()["models"], [], name)
                    self.assertEqual(self.capability_everywhere(), {"name": HAND, "enabled": False, "reason": REASONS["unprovisioned"]})
                    self.assertEqual(self.model_get("MANIFEST.json").status_code, 404, name)
                    self.assertEqual(self.model_get("hand_landmarker.task").status_code, 404, name)
            # The boundary: exactly 64 KiB is still a valid manifest.
            exact = json.dumps({"assets": good, "padding": ""})
            exact = exact[:-2] + "x" * (64 * 1024 - len(exact)) + '"}'
            self.assertEqual(len(exact.encode()), 64 * 1024)
            self.write_manifest(raw=exact.encode())
            self.assertEqual(len(self.health()["models"]), len(ASSETS))
            self.assertEqual(self.model_get("MANIFEST.json").status_code, 200)

    def test_default_models_dir_is_absent_in_this_checkout(self):
        # No model weights are committed: the default inventory on this checkout is empty.
        from server.memory_app import MODELS_DIR, model_inventory
        self.assertFalse((MODELS_DIR / "MANIFEST.json").exists(), "a manifest under phone/assets/models would mean provisioned weights in the tree")
        self.assertEqual(model_inventory(), [])


class FetchModelsScriptTests(ModelsFixture):
    """scripts/fetch_models.py under the fixture's egress guard: every path exercised
    here must refuse or dry-run WITHOUT a network call (a urlopen is a guard failure)."""
    def script(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("pam_fetch_models_under_test", ROOT / "scripts" / "fetch_models.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def invoke(self, module, *argv):
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = module.main(list(argv))
        return code, out.getvalue()

    def test_repository_pins_are_refused_until_oversight_fills_them(self):
        module = self.script()
        pins = ROOT / "scripts" / "model_pins.json"
        self.assertTrue(pins.is_file())
        assets = {asset["name"]: asset for asset in json.loads(pins.read_text(encoding="utf-8"))["assets"]}
        # The hand model's licence is UNVERIFIED (B-05, C-03): its sha256 must stay null in git.
        self.assertIsNone(assets["hand_landmarker.task"]["sha256"], "hand_landmarker.task gained a sha256 without Oversight's verdict")
        target = self.root / "fetched"
        # No register at all: refused before any pin is examined.
        code, out = self.invoke(module, "--pins", str(pins), "--models-dir", str(target), "--licences", str(self.register))
        self.assertEqual(code, 2, out)
        self.assertIn("refused", out)
        self.assertFalse(target.exists())
        # A synthetic register verifying everything does not help the hand model while
        # its sha256 is null: the entry is refused (exit 2) while the five verified
        # runtime files would be fetched. Dry run only: no network under this fixture.
        self.write_register("".join(f"| {name} | Apache-2.0 | synthetic | status: VERIFIED-COMMERCIAL |\n" for name in
                                    ("hand_landmarker.task", "vision_bundle.mjs", "vision_wasm_internal.js", "vision_wasm_internal.wasm",
                                     "vision_wasm_nosimd_internal.js", "vision_wasm_nosimd_internal.wasm")))
        code, out = self.invoke(module, "--dry-run", "--pins", str(pins), "--models-dir", str(target), "--licences", str(self.register))
        self.assertEqual(code, 2, out)
        self.assertIn("refused  hand_landmarker.task", out)
        self.assertIn("null", out)
        self.assertEqual(out.count("would fetch"), len(assets) - 1, out)
        self.assertNotIn("would fetch  hand_landmarker.task", out)
        self.assertFalse(target.exists(), "a dry run writes nothing")
        # Against the REAL register (docs/LICENSES.md) the verdict is the same: the hand
        # model is refused and nothing is fetched in a dry run.
        real_register = ROOT / "docs" / "LICENSES.md"
        self.assertTrue(real_register.is_file(), "docs/LICENSES.md (Oversight) is missing")
        code, out = self.invoke(module, "--dry-run", "--pins", str(pins), "--models-dir", str(target), "--licences", str(real_register))
        self.assertEqual(code, 2, out)
        self.assertIn("refused  hand_landmarker.task", out)
        self.assertFalse(target.exists())
        self.assertFalse((ROOT / "phone" / "assets" / "models").exists(), "the script must not have touched the real models directory")

    def test_dry_run_with_complete_pins_touches_nothing(self):
        module = self.script()
        pins = self.root / "pins.json"
        pins.write_text(json.dumps({"assets": [
            {"name": "hand_landmarker.task", "version": "float16/1", "url": "https://example.invalid/hand_landmarker.task", "sha256": SHA, "licence": "Apache-2.0"},
            {"name": "vision_bundle.mjs", "version": "1.1.0", "url": "https://example.invalid/vision_bundle.mjs", "sha256": SHA, "licence": "Apache-2.0"}]}), encoding="utf-8")
        target = self.root / "fetched"
        self.write_register("| hand_landmarker.task | Apache-2.0 | status: VERIFIED-COMMERCIAL |\n| vision_bundle.mjs | Apache-2.0 | status: VERIFIED-COMMERCIAL |\n")
        code, out = self.invoke(module, "--dry-run", "--pins", str(pins), "--models-dir", str(target), "--licences", str(self.register))
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("would fetch"), 2, out)
        self.assertIn("dry run: nothing downloaded", out)
        self.assertFalse(target.exists(), "a dry run must not create the models directory or a manifest")
        # Licence identifier not on the verified row: every entry refused, no network, even without --dry-run.
        self.write_register("| hand_landmarker.task | MIT | status: VERIFIED-COMMERCIAL |\n| vision_bundle.mjs | MIT | status: VERIFIED-COMMERCIAL |\n")
        code, out = self.invoke(module, "--pins", str(pins), "--models-dir", str(target), "--licences", str(self.register))
        self.assertEqual(code, 2, out)
        self.assertIn("does not list the licence Apache-2.0", out)
        self.assertFalse(target.exists())
        # Rows without the VERIFIED-COMMERCIAL token, or with a blocking token: refused, no network.
        for rows in ("| hand_landmarker.task | Apache-2.0 |\n| vision_bundle.mjs | Apache-2.0 |\n",
                     "| hand_landmarker.task | Apache-2.0 | status: UNVERIFIED |\n| vision_bundle.mjs | Apache-2.0 | VERIFIED-COMMERCIAL REJECTED |\n"):
            self.write_register(rows)
            code, out = self.invoke(module, "--pins", str(pins), "--models-dir", str(target), "--licences", str(self.register))
            self.assertEqual(code, 2, out)
            self.assertIn("has no VERIFIED-COMMERCIAL row", out)
            self.assertFalse(target.exists())
        # --only with an unpinned name is a refusal.
        self.write_register("| hand_landmarker.task | Apache-2.0 | status: VERIFIED-COMMERCIAL |\n| vision_bundle.mjs | Apache-2.0 | status: VERIFIED-COMMERCIAL |\n")
        code, out = self.invoke(module, "--dry-run", "--only", "other.task", "--pins", str(pins), "--models-dir", str(target), "--licences", str(self.register))
        self.assertEqual(code, 2, out)
        self.assertIn("not pinned", out)

    def test_existing_file_with_a_different_hash_is_never_overwritten(self):
        module = self.script()
        pins = self.root / "pins.json"
        pins.write_text(json.dumps({"assets": [
            {"name": "hand_landmarker.task", "version": "float16/1", "url": "https://example.invalid/hand_landmarker.task", "sha256": SHA, "licence": "Apache-2.0"}]}), encoding="utf-8")
        self.write_register("| hand_landmarker.task | Apache-2.0 | status: VERIFIED-COMMERCIAL |\n")
        target = self.root / "fetched"
        target.mkdir()
        (target / "hand_landmarker.task").write_bytes(b"SYNTHETIC-EXISTING-DIFFERENT-HASH")
        code, out = self.invoke(module, "--pins", str(pins), "--models-dir", str(target), "--licences", str(self.register))
        self.assertEqual(code, 1, out)
        self.assertIn("not overwritten", out)
        self.assertEqual((target / "hand_landmarker.task").read_bytes(), b"SYNTHETIC-EXISTING-DIFFERENT-HASH")
        # The manifest written at the end lists only verified files: none here.
        manifest = json.loads((target / "MANIFEST.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["assets"], [])
        from server.memory_app import model_inventory
        self.assertEqual(model_inventory(target, self.register), [], "an empty manifest provisions nothing")


class PublicAssetAllowlistTests(ModelsFixture):
    def test_cp2_browser_modules_are_served_and_the_node_entry_is_not(self):
        for name in ("motion.js", "hand-busy.js", "hand-worker.js", "controller.js"):
            with self.subTest(asset=name):
                response = self.app_client.get("/assets/" + name)
                self.assertEqual(response.status_code, 200, name)
                self.assertIn("javascript", response.headers.get("content-type", ""))
                self.assertEqual(response.headers.get("cache-control"), "no-store")
                self.assertEqual(response.content, (ROOT / "phone" / "assets" / name).read_bytes())
        for name in ("controller-replay.mjs", "models", "models/", "MANIFEST.json", "tabler-license.txt", "../serve.py"):
            with self.subTest(denied=name):
                self.assertEqual(self.app_client.get("/assets/" + name).status_code, 404, name)
        self.assertEqual(self.raw_get("/assets/../phone/assets/controller-replay.mjs")[0], 404)

    def test_served_modules_never_reference_a_cdn_or_absolute_remote_url(self):
        for name in ("motion.js", "hand-busy.js", "hand-worker.js", "controller.js", "memory-camera.js", "memory.js"):
            text = self.app_client.get("/assets/" + name).text
            with self.subTest(asset=name):
                for marker in ("https://", "http://", "cdn.jsdelivr", "unpkg.com", "storage.googleapis", "importScripts('http"):
                    self.assertNotIn(marker, text.replace("https://example.invalid", ""), f"{name} references {marker}")

    def test_serve_py_suffix_allowlist_never_serves_assets_models(self):
        # phone/serve.py (the TLS static server) must not expose model files or the
        # manifest through its suffix allowlist: only the gated app route serves them.
        import importlib
        import io
        from types import SimpleNamespace
        serve = importlib.import_module("phone.serve")
        public = self.root / "public"
        (public / "assets" / "models").mkdir(parents=True)
        (public / "assets" / "models" / "MANIFEST.json").write_text('{"assets":[]}', encoding="utf-8")
        (public / "assets" / "models" / "hand_landmarker.task").write_bytes(b"SYNTHETIC-TASK")
        (public / "assets" / "models" / "vision_bundle.mjs").write_text("export const synthetic = 1; // SYNTHETIC-MJS", encoding="utf-8")
        (public / "assets" / "motion.js").write_text("// SYNTHETIC-PUBLIC-JS", encoding="utf-8")

        class Connection:
            def __init__(self, request):
                self.input, self.output = io.BytesIO(request), io.BytesIO()

            def makefile(self, mode, *args, **kwargs):
                return self.input

            def sendall(self, data):
                self.output.write(data)

            def setsockopt(self, *args):
                pass

        def request(path):
            connection = Connection(f"GET {path} HTTP/1.0\r\nHost: testserver\r\n\r\n".encode("ascii"))
            with patch.object(serve.PublicFiles, "log_message", lambda *args: None):
                serve.PublicFiles(connection, ("127.0.0.1", 12345), SimpleNamespace(server_name="testserver", server_port=8443), directory=str(public))
            header, _, body = connection.output.getvalue().partition(b"\r\n\r\n")
            return int(header.split(b" ", 2)[1]), body

        status, body = request("/assets/motion.js")
        self.assertEqual(status, 200)
        self.assertIn(b"SYNTHETIC-PUBLIC-JS", body)
        for path in ("/assets/models/MANIFEST.json", "/assets/models/hand_landmarker.task", "/assets/models/vision_bundle.mjs", "/assets/models/"):
            with self.subTest(path=path):
                status, body = request(path)
                self.assertIn(status, (400, 403, 404), path)
                self.assertNotIn(b"SYNTHETIC", body)

    def test_worker_module_loads_only_under_the_model_base_path(self):
        text = self.app_client.get("/assets/hand-worker.js").text
        self.assertIn("sameOriginURL", text)
        self.assertIn("MANIFEST.json", text)
        self.assertNotIn("new URL('http", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
