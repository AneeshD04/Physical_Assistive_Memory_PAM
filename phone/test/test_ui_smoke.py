"""CP2 acceptance: browser smoke test of the real page against the real app.

    python3 -B phone/test/test_ui_smoke.py -v

The app (server.app.create_app) runs in-process under uvicorn on a random
loopback port with a temporary database, a synthetic PIN, a temporary model
directory and licence register, and PAM_ENABLE_HAND_MODEL unset. Chromium
(Playwright, headless) loads the page with a fake camera (a static synthetic
y4m clip; no real footage) and EVERY browser request is intercepted: a request
to any origin other than the local server fails the suite. Chromium is also
started with a host-resolver rule that refuses every non-loopback name, so a
request that escaped interception could not resolve either.

The hand landmarker is never loaded: with the real worker the server has no
manifest, so the worker reports "not provisioned"; the automatic-capture case
substitutes window.Worker with a scripted fake (installed before page scripts
run) that replies with the golden landmark sets from
server/fixtures/cp2/hand_goldens.json. The fake reproduces the worker protocol,
not hand recognition; the packet it causes is a controller/packet-path check,
not evidence of recognition accuracy. The server-side processor is a trusted
test injection that turns any packet into one synthetic observation so the
catalogue can be checked end to end; it is not reachable through HTTP.

If Chromium or the fake camera cannot run here the affected tests FAIL with the
reason; nothing is skipped.

CP3 (IdentitySmokeTests, at the end of this file): a second app with the synthetic
embedder from server/test_cp3_identity.py injected, lookalike items seeded over the
API, and the group answer, evidence list, "Not this one" and "Same as another item…"
flows driven in the browser. The element ids/classes it expects are listed above
that class.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from urllib.parse import urlsplit
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
FIXTURES = ROOT / "server" / "fixtures" / "cp2"
import test_memory_bootstrap as bootstrap  # noqa: E402  (synthetic_jpeg / encode_packet only; its fixture is not used)
PIN = "synthetic-smoke-pin-2026"
SHA = "0123456789abcdef" * 4
HAND_CAPABILITY = "automatic_hand_recognition"
UNPROVISIONED = "Hand model assets are not provisioned on this server."
FAKE_REASON = "Fake worker: hand model deliberately unavailable in this test."
MODEL_FILES = ("hand_landmarker.task", "vision_bundle.mjs", "vision_wasm_internal.js", "vision_wasm_internal.wasm")

# Installed before any page script runs. window.Worker is replaced only when the
# page's localStorage names a fake mode ("unavailable" or "ready"); otherwise the
# real worker runs. The fake implements exactly the protocol controller.js uses.
FAKE_WORKER_SCRIPT = r"""
(() => {
  let mode = null;
  try { mode = localStorage.getItem('pam-test-fake-worker'); } catch (error) { mode = null; }
  const config = { mode, reason: %(reason)s, script: [], replies: 0, frames: [], inits: [], constructed: [], terminated: 0, errors: [] };
  window.__pamFake = config;
  if (mode !== 'unavailable' && mode !== 'ready') return;
  const RealWorker = window.Worker;
  class FakeWorker {
    constructor(url, options) {
      config.constructed.push(String(url));
      if (String(url) !== '/assets/hand-worker.js') { config.errors.push('unexpected worker url ' + url); throw new Error('unexpected worker url'); }
      this.listeners = { message: new Set(), error: new Set() };
      this.terminated = false;
    }
    addEventListener(type, listener) { if (this.listeners[type]) this.listeners[type].add(listener); }
    removeEventListener(type, listener) { if (this.listeners[type]) this.listeners[type].delete(listener); }
    deliver(message) {
      if (this.terminated) return;
      setTimeout(() => { if (this.terminated) return; for (const listener of [...this.listeners.message]) listener({ data: message }); }, 0);
    }
    postMessage(message, transfer) {
      if (!message || typeof message !== 'object') { config.errors.push('non-object message'); return; }
      if (message.type === 'init') {
        config.inits.push({ base: message.base });
        if (config.mode === 'ready') this.deliver({ type: 'ready', version: 'fake-0.0', delegate: 'CPU', runtime: 'fake' });
        else this.deliver({ type: 'unavailable', reason: config.reason });
        return;
      }
      if (message.type === 'frame') {
        const bitmap = message.bitmap;
        config.frames.push({ t_ms: message.t_ms, transferred: Array.isArray(transfer) && transfer.includes(bitmap),
          width: bitmap && bitmap.width, height: bitmap && bitmap.height });
        try { if (bitmap && typeof bitmap.close === 'function') bitmap.close(); } catch (error) { config.errors.push('close failed'); }
        if (config.mode !== 'ready') return;
        const index = config.replies++;
        const hands = config.script.length ? config.script[Math.min(index, config.script.length - 1)] : [];
        this.deliver({ type: 'hands', t_ms: message.t_ms, hands: JSON.parse(JSON.stringify(hands)), infer_ms: 1 });
        return;
      }
      config.errors.push('unknown message type ' + message.type);
    }
    terminate() { this.terminated = true; config.terminated++; }
  }
  window.Worker = FakeWorker;
  window.__pamRealWorker = RealWorker;
})();
"""


def write_static_y4m(path: Path, width=320, height=240, frames=20):
    """A YUV4MPEG clip of identical frames: a flat mid-grey surface with a darker
    rectangle. Identical frames give zero frame-difference energy, so the
    controller sees motion=false once two frames exist (no carry; the rest
    settles). Synthetic pixels only."""
    y = bytearray([128] * (width * height))
    for row in range(height // 3, 2 * height // 3):
        for col in range(width // 4, 3 * width // 4):
            y[row * width + col] = 60
    u = bytes([128] * ((width // 2) * (height // 2)))
    v = bytes([128] * ((width // 2) * (height // 2)))
    with open(path, "wb") as handle:
        handle.write(f"YUV4MPEG2 W{width} H{height} F10:1 Ip A1:1 C420jpeg\n".encode("ascii"))
        for _ in range(frames):
            handle.write(b"FRAME\n")
            handle.write(bytes(y))
            handle.write(u)
            handle.write(v)


class AnyPacketProcessor:
    """Trusted code-only injection: one synthetic trusted placement per packet,
    anchored on its last keyframe. This is how the catalogue can show an item
    for a browser-made packet; it says nothing about recognition."""
    def __init__(self):
        self.packets = []

    def __call__(self, packet):
        from perception.localizer import LocalObservation
        self.packets.append({"episode_id": packet.episode_id, "capture_mode": packet.capture_mode,
                             "roles": [frame.role for frame in packet.keyframes], "landmarks": len(packet.landmarks),
                             "burst": len(packet.carry_burst), "gaps": len(packet.gaps)})
        last = packet.keyframes[-1]
        width, height = packet.capture.width, packet.capture.height
        label = "synthetic test object" if packet.capture_mode == "automatic" else "synthetic manual object"
        return [LocalObservation(frame_id=last.frame_id, bbox=[width * 0.25, height / 3, width * 0.75, 2 * height / 3],
                                 label=label, actor="wearer", outcome="placed_on_surface",
                                 continuity_id="smoke-continuity", identity_state="trusted", location_text="the synthetic surface",
                                 confidence=1.0, confidence_basis="TEST ONLY: any-packet fixture processor",
                                 calibration={"approved": True, "fixture_only": True, "calibration_id": "synthetic-smoke-1"})]


class LocalServer:
    """The real app under uvicorn in a daemon thread on a random loopback port."""
    def __init__(self, app):
        import uvicorn
        self.config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on", access_log=False)
        self.server = uvicorn.Server(self.config)
        self.thread = threading.Thread(target=self.server.run, name="pam-smoke-uvicorn", daemon=True)
        self.port = None

    def start(self):
        self.thread.start()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            servers = getattr(self.server, "servers", None)
            if self.server.started and servers:
                sockets = servers[0].sockets
                if sockets:
                    self.port = sockets[0].getsockname()[1]
                    break
            time.sleep(0.05)
        if self.port is None:
            raise RuntimeError("uvicorn did not start on a loopback port within 20 s")
        self.origin = f"http://127.0.0.1:{self.port}"
        return self.origin

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=10)


class SmokeFixture(unittest.TestCase):
    """One server, one browser, one context; each test reloads the page in the
    worker mode it needs. Tests are independent of each other's state except
    that they share the (initially empty) temporary database."""
    @classmethod
    def make_processor(cls):
        """The trusted processor injected into the app (a subclass may replace it)."""
        return AnyPacketProcessor()

    @classmethod
    def app_kwargs(cls):
        """Extra create_app keyword arguments (a subclass may add test seams)."""
        return {}

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="pam-ui-smoke-")
        cls.root = Path(cls.temp.name).resolve()
        cls.models_dir = cls.root / "models"
        cls.models_dir.mkdir()
        cls.register = cls.root / "LICENSES.md"
        cls.db = cls.root / "smoke.sqlite3"
        cls.clip = cls.root / "static.y4m"
        write_static_y4m(cls.clip)
        cls.saved_env = {key: os.environ.get(key) for key in ("PAM_ENABLE_HAND_MODEL", "PAM_OBJECT_DB", "PAM_AUTH_PIN")}
        os.environ.pop("PAM_ENABLE_HAND_MODEL", None)
        os.environ["PAM_OBJECT_DB"] = str(cls.db)
        os.environ["PAM_AUTH_PIN"] = PIN
        import importlib
        module = importlib.import_module("server.app")
        cls.processor = cls.make_processor()
        cls.app = module.create_app(database_path=cls.db, profile_id="local", processor=cls.processor, clock=None,
                                    auth_pin=PIN, models_dir=cls.models_dir, licence_register=cls.register,
                                    **cls.app_kwargs())
        cls.server = LocalServer(cls.app)
        cls.origin = cls.server.start()
        cls.acknowledge_consent()
        cls.requests = []
        cls.foreign = []
        cls.posted_packets = []
        cls.console = []
        cls.page_errors = []
        cls.launch_error = None
        try:
            from playwright.sync_api import sync_playwright
            cls.playwright = sync_playwright().start()
            cls.browser = cls.playwright.chromium.launch(headless=True, args=[
                "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
                f"--use-file-for-fake-video-capture={cls.clip}",
                "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1",
                "--disable-background-timer-throttling", "--disable-renderer-backgrounding"])
            cls.context = cls.browser.new_context(viewport={"width": 1024, "height": 900}, base_url=cls.origin)
            cls.context.grant_permissions(["camera"], origin=cls.origin)
            cls.context.add_init_script(FAKE_WORKER_SCRIPT % {"reason": json.dumps(FAKE_REASON)})
            cls.context.route("**/*", cls._route)
            cls.context.on("request", lambda request: cls._observe(request.url, "event"))
            cls.responses = []
            cls.context.on("response", lambda response: cls.responses.append((response.url, response.status)))
            cls.page = cls.context.new_page()
            cls.page.on("console", lambda message: cls.console.append(f"{message.type}: {message.text}"))
            cls.page.on("pageerror", lambda error: cls.page_errors.append(str(error)))
        except Exception as error:  # reported by every test, never skipped
            cls.launch_error = f"{type(error).__name__}: {error}"

    @classmethod
    def acknowledge_consent(cls):
        """CP4 (coordinator ruling 1): capture is refused until the build's consent
        version is acknowledged for the profile. Done once per server over the API (one
        sign-in, charged to the shared rate limit), so the browser's camera gate is open
        for the cases that start the camera; the Privacy view shows the acknowledged
        state. The page's own "I understand" control is exercised by the Privacy case."""
        import httpx
        with httpx.Client(base_url=cls.origin, timeout=10) as client:
            response = client.post("/api/auth/login", json={"pin": PIN}, headers={"origin": cls.origin})
            if response.status_code != 200:
                raise RuntimeError(f"sign-in for the consent acknowledgement failed: {response.status_code} {response.text}")
            response = client.post("/api/consent", json={"acknowledge": bootstrap.CONSENT_VERSION}, headers={"origin": cls.origin})
            if response.status_code != 200 or response.json().get("ok") is not True:
                raise RuntimeError(f"consent acknowledgement failed: {response.status_code} {response.text}")

    @classmethod
    def _observe(cls, url, source):
        cls.requests.append((source, url))
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin != cls.origin:
            cls.foreign.append(url)

    @classmethod
    def _route(cls, route, request):
        cls._observe(request.url, "route")
        if request.method == "POST" and request.url == cls.origin + "/api/episodes":
            try:
                cls.posted_packets.append(json.loads(request.post_data or ""))
            except ValueError:
                cls.posted_packets.append({"error": "unparseable body"})
        if urlsplit(request.url).netloc != urlsplit(cls.origin).netloc:
            route.abort("blockedbyclient")
            return
        route.continue_()

    @classmethod
    def tearDownClass(cls):
        for name in ("page", "context", "browser"):
            handle = getattr(cls, name, None)
            try:
                if handle is not None:
                    handle.close()
            except Exception:
                pass
        if getattr(cls, "playwright", None) is not None:
            try:
                cls.playwright.stop()
            except Exception:
                pass
        cls.server.stop()
        for key, value in cls.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cls.temp.cleanup()

    # --- helpers -------------------------------------------------------------------
    def setUp(self):
        if self.launch_error:
            self.fail(f"Chromium could not be launched for the smoke test: {self.launch_error}")
        self.console_mark = len(self.console)

    def load(self, mode=None):
        """Load the page with the worker mode: None (real worker), 'unavailable' or
        'ready' (fake). The session cookie persists across loads."""
        page = self.page
        if page.url.startswith(self.origin):
            page.evaluate("mode => { if (mode) localStorage.setItem('pam-test-fake-worker', mode); else localStorage.removeItem('pam-test-fake-worker'); }", mode)
            page.goto(self.origin + "/", wait_until="load")
        else:
            page.goto(self.origin + "/", wait_until="load")
            page.evaluate("mode => { if (mode) localStorage.setItem('pam-test-fake-worker', mode); else localStorage.removeItem('pam-test-fake-worker'); }", mode)
            page.reload(wait_until="load")
        self.assertEqual(page.evaluate("() => window.__pamFake && window.__pamFake.mode"), mode)
        return page

    def ensure_signed_in(self):
        page = self.page
        # A persisted session signs in silently (the auth-status text is untouched then).
        page.wait_for_function("() => !document.getElementById('app').hidden || document.getElementById('auth-status').textContent !== 'Checking sign-in availability…'", timeout=10000)
        if not page.locator("#app").is_hidden():
            return
        page.fill("#pin", PIN)
        page.click("#login")
        page.wait_for_selector("#app:not([hidden])", timeout=10000)
        self.assertTrue(page.locator("#signin").is_hidden())

    def show(self, view):
        self.page.click(f"nav button[data-view={view}]")
        self.page.wait_for_selector(f"#view-{view}:not([hidden])", timeout=5000)

    def text(self, selector):
        return self.page.locator(selector).text_content() or ""

    def pump(self, seconds=0.1):
        """Sleep while letting Playwright dispatch events. The sync API runs the
        context.route handler (which continues every page request to the server)
        and the response/request listeners only while a Playwright call is in
        progress, so a plain time.sleep() poll that waits for the server-side effect
        of a browser request can stall for the whole deadline: the POST is parked
        in the route handler until the next Playwright call. Every wait that
        depends on a request the page sent must pump, not sleep."""
        self.page.wait_for_timeout(int(seconds * 1000))

    def wait_text(self, selector, needle, timeout=10000):
        self.page.wait_for_function("([selector, needle]) => (document.querySelector(selector)?.textContent || '').includes(needle)",
                                    arg=[selector, needle], timeout=timeout)

    def api(self):
        import httpx
        client = httpx.Client(base_url=self.origin, timeout=10)
        response = client.post("/api/auth/login", json={"pin": PIN}, headers={"origin": self.origin})
        self.assertEqual(response.status_code, 200, response.text)
        return client

    def golden_hands(self):
        data = json.loads((FIXTURES / "hand_goldens.json").read_text(encoding="utf-8"))
        return {case["name"]: case["hands"] for case in data["cases"]}

    def provision_server(self):
        self.models_dir.mkdir(exist_ok=True)
        for name in MODEL_FILES:
            (self.models_dir / name).write_bytes(b"SYNTHETIC-BYTES-NOT-A-MODEL-" + name.encode())
        (self.models_dir / "MANIFEST.json").write_text(json.dumps({"assets": [
            {"name": name, "version": "fake-0.0", "sha256": SHA, "licence": "Apache-2.0",
             "url": "https://example.invalid/" + name, "fetched_at": "2026-10-08T00:00:00Z"} for name in MODEL_FILES]}), encoding="utf-8")
        self.register.write_text("# synthetic register for the smoke test\n" + "".join(f"| {name} | Apache-2.0 | synthetic | status: VERIFIED-COMMERCIAL |\n" for name in MODEL_FILES), encoding="utf-8")
        os.environ["PAM_ENABLE_HAND_MODEL"] = "1"
        self.addCleanup(self.unprovision_server)

    def unprovision_server(self):
        os.environ.pop("PAM_ENABLE_HAND_MODEL", None)
        for path in list(self.models_dir.iterdir()):
            path.unlink()
        if self.register.exists():
            self.register.unlink()


class SmokeTests(SmokeFixture):
    def test_00_egress_controls_detect_and_block_a_foreign_request(self):
        # Negative control for test_99: a foreign request IS observable by the
        # interception used there, and the resolver rule refuses it regardless.
        seen = []
        probe = self.browser.new_context()
        try:
            probe.route("**/*", lambda route, request: (seen.append(request.url), route.abort("blockedbyclient")))
            page = probe.new_page()
            with self.assertRaises(Exception):
                page.goto("http://example.invalid/probe", wait_until="commit", timeout=5000)
            self.assertEqual(seen, ["http://example.invalid/probe"])
        finally:
            probe.close()
        unrouted = self.browser.new_context()
        try:
            page = unrouted.new_page()
            with self.assertRaises(Exception) as caught:
                page.goto("http://example.invalid/probe", wait_until="commit", timeout=5000)
            self.assertIn("ERR_NAME_NOT_RESOLVED", str(caught.exception), "the host-resolver rule must refuse non-loopback names")
            response = unrouted.new_page().goto(self.origin + "/api/auth/session", wait_until="commit", timeout=5000)
            self.assertEqual(response.status, 200, "loopback must still resolve")
        finally:
            unrouted.close()

    def test_01_sign_in_empty_catalogue_and_abstaining_chat(self):
        page = self.load(None)
        page.wait_for_selector("#signin:not([hidden])", timeout=10000)
        self.assertTrue(page.locator("#app").is_hidden())
        self.ensure_signed_in()
        self.show("items")
        self.wait_text("#items-status", "0 stored items")
        self.wait_text("#items-grid", "No stored items yet.")
        self.assertEqual(page.locator("#items-grid article").count(), 0)
        self.show("chat")
        page.fill("#chat-text", "where are my glasses")
        page.click("#chat-send")
        self.wait_text("#chat-status", "Answer received.")
        assistant = page.locator("#conversation .message.assistant").last
        body = assistant.text_content() or ""
        self.assertIn("Answer type: abstain", body)
        self.assertIn("no matching stored evidence", body.lower())
        self.assertNotIn("last saw", body.lower())
        self.assertEqual(assistant.locator("img").count(), 0)
        self.assertEqual(page.locator("#conversation img").count(), 0)
        self.assertEqual(self.page_errors, [])

    def test_02_real_worker_reports_unprovisioned_and_camera_is_manual(self):
        page = self.load(None)
        self.ensure_signed_in()
        self.assertFalse(page.evaluate("() => Boolean(window.__pamRealWorker)"), "the real Worker must be in use for this case")
        self.show("camera")
        self.wait_text("#automatic-description", "Unavailable:")
        self.wait_text("#automatic-description", UNPROVISIONED)
        self.assertTrue(page.locator("#automatic-toggle").is_disabled())
        self.assertFalse(page.locator("#automatic-toggle").is_checked())
        self.assertEqual(self.text("#camera-mode-badge"), "Manual mark mode")
        self.assertIn("unavailable", self.text("#automatic-notice").lower())
        self.assertIn(UNPROVISIONED, self.text("#automatic-notice"))
        # The capability list on the Stored items view says the same, with the reason.
        self.show("items")
        self.wait_text("#capabilities", HAND_CAPABILITY)
        self.assertIn(f"{HAND_CAPABILITY}: unavailable", self.text("#capabilities"))
        self.assertIn(UNPROVISIONED, self.text("#capabilities"))
        self.show("camera")
        # Starting the camera stays manual; nothing automatic starts.
        page.click("#camera-start")
        self.wait_text("#camera-status", "manual marks only", timeout=15000)
        self.assertIn("manual mode", self.text("#camera-summary"))
        self.assertTrue(page.locator("#automatic-toggle").is_disabled())
        self.assertTrue(page.locator("#mark-before").is_enabled())
        time.sleep(0.6)
        self.assertEqual(self.text("#episode-status"), self.text("#camera-status"))
        page.click("#camera-stop")
        self.wait_text("#camera-status", "Camera off")
        self.assertEqual(self.posted_packets, [], "no packet may be produced without a user mark or an enabled adapter")
        worker_requests = [url for _, url in self.requests if url.endswith("/assets/hand-worker.js")]
        self.assertTrue(worker_requests, "the real worker script was never fetched")
        manifest_requests = [url for _, url in self.requests if "/assets/models/MANIFEST.json" in url]
        self.assertTrue(manifest_requests, "the real worker must look for the manifest on this origin (and only there)")
        self.assertTrue(all(url == self.origin + "/assets/models/MANIFEST.json" for url in manifest_requests), manifest_requests)
        statuses = {status for url, status in self.responses if url == self.origin + "/assets/models/MANIFEST.json"}
        self.assertEqual(statuses, {404}, "without a manifest the server answers 404 and the worker reports not provisioned")
        self.assertEqual(self.page_errors, [])

    def test_03_fake_worker_unavailable_disables_the_toggle_even_when_the_server_allows(self):
        # The server grants the capability (synthetic manifest, register, env flag) but
        # the worker reports unavailable: the toggle stays disabled with the worker's reason.
        self.provision_server()
        page = self.load("unavailable")
        self.ensure_signed_in()
        self.show("camera")
        page.wait_for_function("() => window.__pamFake.inits.length >= 1", timeout=10000)
        self.assertEqual(page.evaluate("() => window.__pamFake.constructed"), ["/assets/hand-worker.js"])
        self.assertEqual(page.evaluate("() => window.__pamFake.inits"), [{"base": "/assets/models/"}])
        self.wait_text("#automatic-description", "Unavailable:")
        self.wait_text("#automatic-description", FAKE_REASON)
        self.assertTrue(page.locator("#automatic-toggle").is_disabled())
        self.assertFalse(page.locator("#automatic-toggle").is_checked())
        self.assertEqual(self.text("#camera-mode-badge"), "Manual mark mode")
        self.assertIn(FAKE_REASON, self.text("#automatic-notice"))
        self.assertEqual(page.evaluate("() => window.__pamFake.errors"), [])
        page.click("#camera-start")
        self.wait_text("#camera-status", "manual marks only", timeout=15000)
        time.sleep(0.6)
        self.assertEqual(page.evaluate("() => window.__pamFake.frames.length"), 0, "an unavailable worker never receives frames")
        self.assertTrue(page.locator("#automatic-toggle").is_disabled())
        page.click("#camera-stop")
        self.wait_text("#camera-status", "Camera off")
        self.assertEqual(self.posted_packets, [])

    def test_04_fake_worker_ready_but_server_policy_disabled_keeps_toggle_disabled(self):
        page = self.load("ready")
        self.ensure_signed_in()
        self.show("camera")
        page.wait_for_function("() => window.__pamFake.inits.length >= 1", timeout=10000)
        # Give the page every chance to enable the toggle wrongly: health and items both answered.
        self.show("items")
        self.wait_text("#capabilities", HAND_CAPABILITY)
        self.show("camera")
        time.sleep(0.5)
        self.assertTrue(page.locator("#automatic-toggle").is_disabled(), "the server is the policy authority: a ready worker alone must not enable automatic capture")
        description = self.text("#automatic-description")
        self.assertIn("Unavailable:", description)
        self.assertIn(UNPROVISIONED, description, "the server's reason must be shown, not the worker's readiness")
        self.assertEqual(self.text("#camera-mode-badge"), "Manual mark mode")
        page.click("#camera-start")
        self.wait_text("#camera-status", "manual marks only", timeout=15000)
        time.sleep(0.7)
        self.assertEqual(page.evaluate("() => window.__pamFake.frames.length"), 0, "no frame may reach the worker while the server denies the capability")
        page.click("#camera-stop")
        self.wait_text("#camera-status", "Camera off")
        self.assertEqual(self.posted_packets, [])

    def test_05_automatic_capture_produces_one_automatic_packet(self):
        self.provision_server()
        api = self.api()
        health = api.get("/api/health").json()
        hand = next(cap for cap in health["capabilities"] if cap["name"] == HAND_CAPABILITY)
        self.assertTrue(hand["enabled"], hand)
        page = self.load("ready")
        self.ensure_signed_in()
        self.show("camera")
        page.wait_for_function("() => !document.getElementById('automatic-toggle').disabled", timeout=10000)
        self.assertIn("Off · hand model fake-0.0", self.text("#automatic-description"))
        hands = self.golden_hands()
        script = [hands["no_hand"]] * 2 + [hands["open_hand_lower_frame"]] * 3 + [hands["open_hand_high"]] * 40
        page.evaluate("script => { window.__pamFake.script = script; window.__pamFake.replies = 0; }", script)
        posted_before = len(self.posted_packets)
        page.click("#camera-start")
        self.wait_text("#camera-status", "manual marks only", timeout=15000)
        page.check("#automatic-toggle")
        self.wait_text("#camera-status", "automatic capture (hand model fake-0.0)")
        self.assertEqual(self.text("#camera-mode-badge"), "Automatic capture mode")
        self.assertIn("automatic mode", self.text("#camera-summary"))
        self.assertIn("a busy-hand heuristic, not verified recognition", self.text("#automatic-notice"))
        self.assertTrue(page.locator("#mark-before").is_enabled(), "manual marks keep working beside automatic capture")
        self.wait_text("#episode-status", "Automatic episode started", timeout=10000)
        self.wait_text("#episode-status", "Automatic episode saved locally", timeout=15000)
        deadline = time.monotonic() + 15
        while len(self.posted_packets) <= posted_before and time.monotonic() < deadline:
            self.pump(0.1)
        self.assertEqual(len(self.posted_packets), posted_before + 1, "exactly one POST /api/episodes")
        packet = self.posted_packets[-1]
        self.assertEqual(packet["capture_mode"], "automatic")
        roles = [frame["role"] for frame in packet["keyframes"]]
        self.assertEqual(roles[:2], ["pre_contact", "hand_busy"])
        self.assertEqual(roles[-2:], ["release", "rest"])
        self.assertTrue(set(roles) <= {"pre_contact", "hand_busy", "carry", "release", "rest"}, roles)
        self.assertEqual(packet["outcome_hint"], "released")
        self.assertGreaterEqual(len(packet["landmarks"]), 3, "the busy and open-hand samples travel with the packet")
        self.assertTrue(any(sample["hands"] for sample in packet["landmarks"]))
        busy_samples = [sample for sample in packet["landmarks"] if sample["hands"] and sample["hands"][0]["hand_bbox"] == [0.3, 0.3, 0.6, 0.8]]
        self.assertGreaterEqual(len(busy_samples), 1, "the lower-frame golden hand that started the episode is in the packet")
        self.assertEqual(len(busy_samples[0]["hands"][0]["landmarks"]), 21)
        self.assertEqual(packet["gaps"], [])
        self.assertEqual(page.locator("#coverage-log li").count(), 0, "no coverage gap during a clean automatic episode")
        self.assertLessEqual(packet["analysis"]["width"], min(320, packet["capture"]["width"]))
        self.assertLessEqual(packet["analysis"]["height"], min(320, packet["capture"]["height"]))
        self.assertLessEqual(len(packet["carry_burst"]), 10)  # no carry on a static clip is acceptable (carry is optional here)
        times = [frame["t_ms"] for frame in packet["keyframes"]]
        self.assertEqual(times, sorted(set(times)))
        self.assertEqual(packet["t_start_ms"], times[0])
        # The fake worker saw transferred bitmaps and closed them.
        frames = page.evaluate("() => window.__pamFake.frames")
        self.assertGreaterEqual(len(frames), 10)
        self.assertTrue(all(frame["transferred"] for frame in frames), frames[:3])
        self.assertEqual(page.evaluate("() => window.__pamFake.errors"), [])
        # Durable ack reaches the page, then the server stores and processes the packet.
        self.wait_text("#app-status", "Capture durably retained", timeout=15000)
        deadline = time.monotonic() + 15
        items = []
        while time.monotonic() < deadline:
            items = api.get("/api/items").json()["items"]
            if items and not any(item["index_pending"] for item in items):
                break
            time.sleep(0.1)
        self.assertEqual(len(items), 1, items)
        self.assertEqual(items[0]["name"], "synthetic test object")
        self.assertEqual(items[0]["location_status"], "placed")
        self.assertEqual(len(self.processor.packets), 1, self.processor.packets)
        self.assertEqual(self.processor.packets[0]["capture_mode"], "automatic")
        self.assertEqual(self.processor.packets[0]["episode_id"], packet["episode_id"])
        processing = api.get("/api/health").json()["processing"]
        self.assertEqual(processing.get("status"), "available", processing)
        self.assertGreaterEqual(processing.get("processed", 0) + processing.get("observations", 0), 1, processing)
        stored = self.stored_packets()
        self.assertEqual([p["capture_mode"] for p in stored], ["automatic"])
        self.assertEqual(stored[0]["episode_id"], packet["episode_id"])
        # The catalogue view shows the item.
        self.show("items")
        self.wait_text("#items-status", "1 stored item", timeout=15000)
        self.wait_text("#items-grid", "synthetic test object")
        self.assertIn("the synthetic surface", self.text("#items-grid"))
        page.click("nav button[data-view=camera]")
        page.click("#camera-stop")
        self.wait_text("#camera-status", "Camera off")
        api.close()

    def test_06_aged_placement_is_rendered_as_older_evidence(self):
        # Clock-only staleness in the UI: a placement observed 25 h ago (a synthetic
        # manual packet posted over the API with an old wall anchor) renders the age
        # notice in Stored items and a hedged chat answer with its member card.
        import uuid
        api = self.api()
        eid = str(uuid.uuid4())
        wall_ms = int(time.time() * 1000) - 25 * 3600 * 1000
        packet = {"schema_version": 1, "episode_id": eid, "device_id": str(uuid.uuid4()), "session_id": str(uuid.uuid4()),
                  "t_start_ms": 1000, "t_end_ms": 2200, "clock_anchor": {"mono_ms": 0, "wall_ms": wall_ms},
                  "capture": {"width": 160, "height": 120}, "analysis": {"width": 80, "height": 60},
                  "keyframes": [{"frame_id": eid + "-before", "t_ms": 1000, "role": "pre_contact", "jpeg_b64": bootstrap.synthetic_jpeg(None)},
                                {"frame_id": eid + "-rest", "t_ms": 2200, "role": "rest", "jpeg_b64": bootstrap.synthetic_jpeg(20)}],
                  "carry_burst": [], "landmarks": [], "gaps": [], "outcome_hint": "released", "capture_mode": "manual"}
        response = api.post("/api/episodes", content=bootstrap.encode_packet(packet), headers={"origin": self.origin, "content-type": "application/json"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["ack"]["status"], "stored")
        deadline = time.monotonic() + 15
        aged = None
        while time.monotonic() < deadline:
            items = api.get("/api/items").json()["items"]
            aged = next((item for item in items if item["name"] == "synthetic manual object"), None)
            if aged and not aged["index_pending"]:
                break
            time.sleep(0.1)
        self.assertIsNotNone(aged, "the aged packet was not processed into an item")
        self.assertIs(aged["aged"], True)
        self.assertEqual(aged["stale_reason"], "age")
        self.assertEqual(aged["location_status"], "placed")
        page = self.load(None)
        self.ensure_signed_in()
        self.show("items")
        self.wait_text("#items-grid", "synthetic manual object", timeout=15000)
        card = page.locator("#items-grid article", has_text="synthetic manual object")
        self.assertEqual(card.count(), 1)
        body = card.text_content() or ""
        self.assertIn("Older evidence: recorded more than a day ago; it may have moved.", body)
        self.assertIn("Location: placed · older evidence", body)
        self.assertIn("the synthetic surface", body)
        self.show("chat")
        page.fill("#chat-text", "where is my synthetic manual object")
        page.click("#chat-send")
        self.wait_text("#chat-status", "Answer received.")
        assistant = page.locator("#conversation .message.assistant").last
        text = assistant.text_content() or ""
        self.assertIn("Answer type: hedged", text)
        self.assertIn("more than a day ago", text)
        self.assertNotIn("last saw", text.lower())
        self.assertIn("Older evidence: recorded more than a day ago", text)
        self.assertEqual(assistant.locator("article.item-card").count(), 1)
        image = assistant.locator("img")
        self.assertEqual(image.count(), 1, "the hedged answer carries the member's evidence photo")
        self.assertEqual(image.get_attribute("src"), f"/api/items/{aged['item_id']}/image")
        page.wait_for_function("() => { const img = document.querySelector('#conversation img'); return img && img.complete && img.naturalWidth > 0; }", timeout=10000)
        api.close()

    def test_07_repeated_release_keeps_one_release_pin_and_the_rest_frame(self):
        # Coordinator ruling (2026-10-08): when settling is reset by a missing
        # measurement the controller re-emits select_release; the camera must keep
        # only the latest release pin so the rest keyframe always fits, and never ship
        # an automatic packet without its rest frame.
        self.provision_server()
        api = self.api()
        page = self.load("ready")
        self.ensure_signed_in()
        self.show("camera")
        page.wait_for_function("() => !document.getElementById('automatic-toggle').disabled", timeout=10000)
        hands = self.golden_hands()
        # no hand, busy x3, open (release), open, NO HAND (busy null: settling resets), open ... (release again, then rest)
        script = [hands["no_hand"]] * 2 + [hands["open_hand_lower_frame"]] * 3 + [hands["open_hand_high"]] * 2 + [hands["no_hand"]] + [hands["open_hand_high"]] * 40
        page.evaluate("script => { window.__pamFake.script = script; window.__pamFake.replies = 0; }", script)
        posted_before = len(self.posted_packets)
        gaps_before = page.locator("#coverage-log li").count()
        page.click("#camera-start")
        self.wait_text("#camera-status", "manual marks only", timeout=15000)
        page.check("#automatic-toggle")
        self.wait_text("#episode-status", "Automatic episode started", timeout=10000)
        self.wait_text("#episode-status", "Automatic episode saved locally", timeout=15000)
        deadline = time.monotonic() + 15
        while len(self.posted_packets) <= posted_before and time.monotonic() < deadline:
            self.pump(0.1)
        self.assertEqual(len(self.posted_packets), posted_before + 1, "exactly one packet for the episode")
        packet = self.posted_packets[-1]
        roles = [frame["role"] for frame in packet["keyframes"]]
        self.assertEqual(roles, ["pre_contact", "hand_busy", "release", "rest"], "one release pin, the rest keyframe present")
        times = [frame["t_ms"] for frame in packet["keyframes"]]
        self.assertEqual(times, sorted(set(times)))
        samples = packet["landmarks"]
        kinds = ["busy" if s["hands"] and s["hands"][0]["hand_bbox"] == [0.3, 0.3, 0.6, 0.8] else "open" if s["hands"] else "none" for s in samples]
        first_open = kinds.index("open")
        self.assertIn("none", kinds[first_open:], f"the missing-measurement sample must sit inside the episode: {kinds}")
        release_t = packet["keyframes"][2]["t_ms"]
        reset_t = samples[first_open + kinds[first_open:].index("none")]["t_ms"]
        self.assertGreater(release_t, reset_t, "the retained release frame is the one selected AFTER the reset")
        self.assertEqual(packet["gaps"], [])
        self.assertEqual(page.locator("#coverage-log li").count(), gaps_before, "no abort: the rest pin fitted")
        self.wait_text("#app-status", "Capture durably retained", timeout=15000)
        stored = self.stored_packets()
        self.assertEqual([p["capture_mode"] for p in stored if p["capture_mode"] == "automatic"].count("automatic"), 2)
        page.click("#camera-stop")
        self.wait_text("#camera-status", "Camera off")
        api.close()

    def stored_packets(self):
        connection = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)
        try:
            rows = connection.execute("SELECT packet FROM episode_revisions ORDER BY received_at_ms").fetchall()
        finally:
            connection.close()
        return [json.loads(bytes(row[0]).decode("utf-8")) for row in rows if row[0] is not None]

    def test_99_no_request_left_the_origin(self):
        # Runs last (alphabetical): every request seen by interception and by the
        # request event, across all cases, targeted the local server.
        self.assertGreater(len(self.requests), 20, "interception saw too few requests to be meaningful")
        self.assertEqual(self.foreign, [], f"requests left the origin: {self.foreign}")
        paths = {urlsplit(url).path for _, url in self.requests}
        for expected in ("/", "/assets/memory.js", "/assets/memory-camera.js", "/assets/controller.js",
                         "/assets/motion.js", "/assets/hand-busy.js", "/api/auth/session", "/api/health", "/api/items", "/api/chat"):
            self.assertIn(expected, paths)
        self.assertEqual(self.page_errors, [], self.page_errors)


# --- CP3: identity in the browser --------------------------------------------------------
# A second app with the deterministic synthetic embedder (server/test_cp3_identity.py)
# injected through create_app(embedder=...), the CP3 fixture processor and an
# approved synthetic calibration. Items are seeded over the API with colour-tagged
# frames; the browser then has to render the group answer, the evidence list and
# the two corrections. Element ids/classes the page must provide (Builder C):
#   chat:   .group-members (container inside the assistant message), .group-member
#           (one per member, data-item-id, contains an <img> of that member's photo,
#           clickable: resubmits the chat for that item), text "which one is yours"
#   detail: #evidence-list with .evidence-row per observation (data-observation-id,
#           an <img> whose src is the observation image URL, a .unlink-observation
#           button "Not this one"), #link-item button ("Same as another item…"),
#           #confirm-dialog (<dialog>) with #link-target (<select>, option values are
#           item ids, present for a link) and #confirm-ok / #confirm-cancel buttons;
#           a refused link (409) shows its safe reason in #detail-status.
#   badge:  an ambiguous item's card text carries "ambiguous" and "lookalike".
IDENTITY_MODEL = "dinov2_vits14.onnx"
IDENTITY_ENV = "PAM_ENABLE_IDENTITY_MODEL"


class IdentitySmokeFixture(SmokeFixture):
    @classmethod
    def make_processor(cls):
        import test_cp3_identity as identity
        return identity.Cp3Processor()

    @classmethod
    def app_kwargs(cls):
        import test_cp3_identity as identity
        cls.embedder = identity.SyntheticEmbedder()
        return {"embedder": cls.embedder}

    @classmethod
    def setUpClass(cls):
        cls.saved_identity_env = os.environ.get(IDENTITY_ENV)
        super().setUpClass()
        import test_cp3_identity as identity
        cls.identity = identity
        # The identity capability's policy inputs: a manifest naming the identity asset
        # (synthetic bytes, never loaded: the injected embedder decides), a licence row
        # and the env flag. The hand model stays unprovisioned (PAM_ENABLE_HAND_MODEL unset).
        (cls.models_dir / IDENTITY_MODEL).write_bytes(b"SYNTHETIC-ONNX-BYTES-NOT-A-MODEL")
        (cls.models_dir / "MANIFEST.json").write_text(json.dumps({"assets": [
            {"name": IDENTITY_MODEL, "version": "vits14-export-1", "sha256": SHA, "licence": "Apache-2.0",
             "url": "https://example.invalid/" + IDENTITY_MODEL, "fetched_at": "2026-10-09T00:00:00Z"}]}), encoding="utf-8")
        cls.register.write_text("# synthetic register for the identity smoke test\n"
                                f"| {IDENTITY_MODEL} | Apache-2.0 | synthetic | status: VERIFIED-COMMERCIAL |\n", encoding="utf-8")
        os.environ[IDENTITY_ENV] = "1"
        from perception.object_memory import ObjectStore
        store = ObjectStore(cls.db, profile_id="local")
        store.register_calibration(identity.calibration_record())
        store.approve_calibration(identity.CAL_WIDE, identity.ACTOR)
        cls.serial = 0
        cls.phase = 0

    @classmethod
    def tearDownClass(cls):
        if cls.saved_identity_env is None:
            os.environ.pop(IDENTITY_ENV, None)
        else:
            os.environ[IDENTITY_ENV] = cls.saved_identity_env
        super().tearDownClass()

    # --- seeding over the API ---------------------------------------------------------
    def post_tagged(self, api, regions, *, labels=None, locations=None):
        identity = self.identity
        type(self).serial += 1
        type(self).phase += 1
        wall_ms = int(time.time() * 1000) - 3600 * 1000  # observed within the last hour: never aged
        packet = identity.cp3_packet(self.serial, rest=regions, phase=self.phase, wall_ms=wall_ms,
                                     device=str(uuid.uuid5(uuid.NAMESPACE_URL, "pam-identity-smoke-device")),
                                     session=str(uuid.uuid5(uuid.NAMESPACE_URL, "pam-identity-smoke-session")))
        frame = identity.rest_frame_id(packet)
        labels = [identity.GLASSES] * len(regions) if labels is None else labels
        locations = [f"synthetic shelf {i}" for i in range(len(regions))] if locations is None else locations
        self.processor.observations[packet["episode_id"]] = [
            identity.cp3_observation(frame, reg, label=labels[i], location=locations[i]) for i, reg in enumerate(regions)]
        response = api.post("/api/episodes", content=bootstrap.encode_packet(packet),
                            headers={"origin": self.origin, "content-type": "application/json"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["ack"]["status"], "stored")
        return packet

    def wait_catalogue(self, api, predicate, what):
        deadline = time.monotonic() + 15
        items = []
        while time.monotonic() < deadline:
            items = api.get("/api/items").json()["items"]
            if not any(item["index_pending"] for item in items) and predicate(items):
                return items
            time.sleep(0.1)
        self.fail(f"{what}; catalogue: {[(i['name'], i['identity_status'], i.get('lookalikes')) for i in items]}")

    def evidence(self, api, item_id):
        response = api.get(f"/api/items/{item_id}/evidence")
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["observations"]

    def seed_lookalikes(self, api):
        """A and B (tags 0 and 1) co-visible, then a lone tag-0 sighting: both ambiguous.
        Idempotent per class: seeds once and returns the two ids (sorted by location)."""
        if getattr(type(self), "pair", None):
            return self.pair
        identity = self.identity
        self.post_tagged(api, [identity.region(identity.LEFT, 0), identity.region(identity.RIGHT, 1)],
                         locations=["synthetic shelf left", "synthetic shelf right"])
        items = self.wait_catalogue(api, lambda items: len([i for i in items if i["name"] == identity.GLASSES]) == 2, "two glasses expected")
        self.post_tagged(api, [identity.region(identity.MIDDLE, 0)], locations=["synthetic shelf middle"])
        items = self.wait_catalogue(api, lambda items: all(i["identity_status"] == "ambiguous" for i in items if i["name"] == identity.GLASSES),
                                    "both glasses should be ambiguous lookalikes")
        glasses = sorted((i for i in items if i["name"] == identity.GLASSES), key=lambda i: i["location_text"] or "")
        self.assertEqual(len(glasses), 2, glasses)
        type(self).pair = (glasses[0]["item_id"], glasses[1]["item_id"])
        return self.pair

    def open_detail(self, item_id):
        page = self.page
        self.show("items")
        card = page.locator(f"#items-grid article[data-item-id='{item_id}']")
        page.wait_for_function("id => Boolean(document.querySelector(`#items-grid article[data-item-id='${id}']`))", arg=item_id, timeout=15000)
        card.locator("button", has_text="View evidence").first.click()
        page.wait_for_selector("#item-dialog[open]", timeout=5000)
        return card

    def wait_rows(self, count, timeout=10000):
        self.page.wait_for_function("n => document.querySelectorAll('#evidence-list .evidence-row').length === n", arg=count, timeout=timeout)
        return self.page.locator("#evidence-list .evidence-row")

    def confirm(self):
        page = self.page
        page.wait_for_selector("#confirm-dialog[open]", timeout=5000)
        page.click("#confirm-ok")


class IdentitySmokeTests(IdentitySmokeFixture):
    def test_10_group_answer_renders_members_with_photos_and_tapping_one_resolves(self):
        api = self.api()
        a, b = self.seed_lookalikes(api)
        health = api.get("/api/health").json()
        capability = next(cap for cap in health["capabilities"] if cap["name"] == "physical_instance_recognition")
        self.assertTrue(capability["enabled"], capability)
        page = self.load(None)
        self.ensure_signed_in()
        # Stored items: both cards carry the ambiguous badge with the lookalike count.
        self.show("items")
        self.wait_text("#items-grid", self.identity.GLASSES, timeout=15000)
        for item_id in (a, b):
            card = page.locator(f"#items-grid article[data-item-id='{item_id}']")
            self.assertEqual(card.count(), 1, item_id)
            body = (card.text_content() or "").lower()
            self.assertIn("ambiguous", body)
            self.assertIn("lookalike", body)
        self.show("chat")
        page.fill("#chat-text", self.identity.ASK_GLASSES)
        page.click("#chat-send")
        self.wait_text("#chat-status", "Answer received.")
        assistant = page.locator("#conversation .message.assistant").last
        text = assistant.text_content() or ""
        self.assertIn("Answer type: group", text)
        self.assertIn("which one is yours", text.lower())
        self.assertNotIn("last saw", text.lower())
        members = assistant.locator(".group-members .group-member")
        self.assertEqual(members.count(), 2, text)
        seen = set()
        for index in range(2):
            member = members.nth(index)
            item_id = member.get_attribute("data-item-id")
            self.assertIn(item_id, (a, b))
            seen.add(item_id)
            image = member.locator("img")
            self.assertEqual(image.count(), 1, "each member shows its own evidence photo")
            self.assertEqual(image.get_attribute("src"), f"/api/items/{item_id}/image")
        self.assertEqual(seen, {a, b})
        page.wait_for_function("() => [...document.querySelectorAll('.group-members img')].every(img => img.complete && img.naturalWidth > 0)", timeout=10000)
        # Tapping a member is the user's answer (coordinator ruling 5): the page records
        # it with POST .../observations/{parked}/assign, then re-asks by item id; the
        # answer is about that item alone and is not a group.
        parked_before = {row["observation_id"] for row in self.evidence(api, a)} | {row["observation_id"] for row in self.evidence(api, b)}
        answers_before = page.locator("#conversation .message.assistant").count()
        requests_before = len(self.requests)
        clicked = members.nth(0).get_attribute("data-item-id")
        members.nth(0).click()
        page.wait_for_function("n => document.querySelectorAll('#conversation .message.assistant').length > n", arg=answers_before, timeout=10000)
        self.wait_text("#chat-status", "Answer received.")
        # (every request is logged twice, by interception and by the request event)
        assigns = [url for source, url in self.requests[requests_before:] if source == "route" and urlsplit(url).path.endswith("/assign")]
        self.assertEqual(len(assigns), 1, f"exactly one assign call: {assigns}")
        self.assertTrue(urlsplit(assigns[0]).path.startswith(f"/api/items/{clicked}/observations/"), assigns[0])
        assign_statuses = {status for url, status in self.responses if url == assigns[0]}
        self.assertEqual(assign_statuses, {200}, "the choice must be recorded")
        resolved = page.locator("#conversation .message.assistant").last
        resolved_text = resolved.text_content() or ""
        self.assertNotIn("Answer type: group", resolved_text)
        self.assertNotIn("Answer type: confident", resolved_text, "a group member's certainty is never upgraded by selecting it")
        cards = resolved.locator("article.item-card")
        self.assertEqual(cards.count(), 1, resolved_text)
        self.assertEqual(cards.first.get_attribute("data-item-id"), clicked)
        # The parked sighting is now the chosen item's evidence and the group is dissolved.
        rows = {row["observation_id"] for row in self.evidence(api, clicked)}
        self.assertEqual(len(rows - parked_before), 1, "the chosen item gained the parked observation")
        other = b if clicked == a else a
        self.assertEqual({row["observation_id"] for row in self.evidence(api, other)} - parked_before, set())
        items = {i["item_id"]: i for i in api.get("/api/items").json()["items"]}
        self.assertEqual([items[a]["lookalikes"], items[b]["lookalikes"]], [[], []])
        page.fill("#chat-text", self.identity.ASK_GLASSES)
        page.click("#chat-send")
        page.wait_for_function("n => document.querySelectorAll('#conversation .message.assistant').length > n", arg=answers_before + 1, timeout=10000)
        self.wait_text("#chat-status", "Answer received.")
        again = page.locator("#conversation .message.assistant").last.text_content() or ""
        self.assertNotIn("Answer type: group", again, "once resolved the two are distinct items again (clarify), not a group")
        self.assertEqual(self.page_errors, [], self.page_errors)
        api.close()

    def test_20_evidence_rows_and_not_this_one_moves_the_observation_to_a_new_item(self):
        identity = self.identity
        api = self.api()
        self.post_tagged(api, [identity.region(identity.LEFT, 2)], labels=[identity.BOTTLE], locations=["synthetic shelf back"])
        self.wait_catalogue(api, lambda items: any(i["name"] == identity.BOTTLE for i in items), "bottle expected")
        self.post_tagged(api, [identity.region(identity.RIGHT, 2)], labels=[identity.BOTTLE], locations=["synthetic shelf front"])
        items = self.wait_catalogue(api, lambda items: any(i["name"] == identity.BOTTLE and i["location_text"] == "synthetic shelf front" for i in items),
                                    "the second bottle sighting should re-match")
        bottles = [i for i in items if i["name"] == identity.BOTTLE]
        self.assertEqual(len(bottles), 1, bottles)
        bottle = bottles[0]["item_id"]
        rows_api = self.evidence(api, bottle)
        self.assertEqual(len(rows_api), 2)
        page = self.load(None)
        self.ensure_signed_in()
        self.open_detail(bottle)
        rows = self.wait_rows(2)
        srcs = set()
        for index in range(2):
            row = rows.nth(index)
            observation_id = row.get_attribute("data-observation-id")
            self.assertIn(observation_id, {r["observation_id"] for r in rows_api})
            image = row.locator("img")
            self.assertEqual(image.count(), 1, "each evidence row shows that observation's photo")
            srcs.add(image.get_attribute("src"))
            self.assertEqual(row.locator(".unlink-observation").count(), 1)
            body = row.text_content() or ""
            self.assertNotIn("Time not recorded", body)
        self.assertEqual(srcs, {r["image_url"] for r in rows_api})
        page.wait_for_function("() => [...document.querySelectorAll('#evidence-list img')].every(img => img.complete && img.naturalWidth > 0)", timeout=10000)
        # "Not this one" on the second row, confirmed: the observation moves to a new item.
        moved = rows.nth(1).get_attribute("data-observation-id")
        rows.nth(1).locator(".unlink-observation").click()
        self.confirm()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            items = api.get("/api/items").json()["items"]
            bottles = [i for i in items if i["name"] == identity.BOTTLE]
            if len(bottles) == 2:
                break
            self.pump(0.1)
        self.assertEqual(len(bottles), 2, bottles)
        new_item = next(i["item_id"] for i in bottles if i["item_id"] != bottle)
        self.assertEqual([r["observation_id"] for r in self.evidence(api, new_item)], [moved])
        self.assertEqual(len(self.evidence(api, bottle)), 1)
        self.assertNotIn(moved, [r["observation_id"] for r in self.evidence(api, bottle)])
        # The dialog reflects the change without a reload: one row left on whichever item it shows.
        self.wait_rows(1)
        status = self.text("#detail-status")
        self.assertNotIn("HTTP", status)
        page.click("#detail-close")
        self.show("items")
        page.wait_for_function("() => document.querySelectorAll('#items-grid article').length >= 4", timeout=15000)
        self.assertEqual(page.locator("#items-grid article", has_text=identity.BOTTLE).count(), 2)
        type(self).bottle, type(self).unlinked = bottle, new_item
        self.assertEqual(self.page_errors, [], self.page_errors)
        api.close()

    def test_30_same_as_another_item_shows_the_409_reason_then_merges(self):
        identity = self.identity
        api = self.api()
        bottle, unlinked = getattr(type(self), "bottle", None), getattr(type(self), "unlinked", None)
        self.assertTrue(bottle and unlinked, "test_20 seeds the unlinked pair this case relies on")
        self.post_tagged(api, [identity.region(identity.MIDDLE, 3)], labels=[identity.BOTTLE], locations=["synthetic shelf side"])
        items = self.wait_catalogue(api, lambda items: len([i for i in items if i["name"] == identity.BOTTLE]) == 3, "a third bottle expected")
        third = next(i["item_id"] for i in items if i["name"] == identity.BOTTLE and i["item_id"] not in (bottle, unlinked))
        page = self.load(None)
        self.ensure_signed_in()
        self.open_detail(unlinked)
        self.wait_rows(1)
        # Same as the item it was just unlinked from: refused (cannot-link) with a safe reason.
        page.click("#link-item")
        page.wait_for_selector("#confirm-dialog[open]", timeout=5000)
        options = page.locator("#link-target option")
        values = [options.nth(i).get_attribute("value") for i in range(options.count())]
        self.assertIn(bottle, values)
        self.assertIn(third, values)
        self.assertNotIn(unlinked, values, "an item is never offered as its own match")
        page.select_option("#link-target", bottle)
        page.click("#confirm-ok")
        page.wait_for_function("() => { const t = document.getElementById('detail-status').textContent || ''; return t.length > 0 && !t.includes('Loading'); }", timeout=10000)
        status = self.text("#detail-status")
        self.assertNotIn("409", status, "a status code is not a reason")
        self.assertNotIn("Traceback", status)
        self.assertTrue(len(status.strip()) > 10, status)
        self.assertEqual(api.get(f"/api/items/{unlinked}").status_code, 200, "a refused link merges nothing")
        self.assertEqual(len(self.evidence(api, bottle)), 1)
        # Same as the third bottle: allowed; the two become one item with two evidence rows.
        page.click("#link-item")
        page.wait_for_selector("#confirm-dialog[open]", timeout=5000)
        page.select_option("#link-target", third)
        page.click("#confirm-ok")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if api.get(f"/api/items/{unlinked}").status_code == 404 or api.get(f"/api/items/{third}").status_code == 404:
                break
            self.pump(0.1)
        kept = third if api.get(f"/api/items/{third}").status_code == 200 else unlinked
        gone = unlinked if kept == third else third
        self.assertEqual(api.get(f"/api/items/{gone}").status_code, 404, "the merged-away item is gone")
        self.assertEqual(len(self.evidence(api, kept)), 2)
        items = api.get("/api/items").json()["items"]
        self.assertEqual(len([i for i in items if i["name"] == identity.BOTTLE]), 2)
        # The page shows the merged state (no reload): the dialog is closed or shows the kept item with two rows.
        if page.locator("#item-dialog[open]").count():
            self.wait_rows(2)
            page.click("#detail-close")
        self.show("items")
        page.wait_for_function("id => !document.querySelector(`#items-grid article[data-item-id='${id}']`)", arg=gone, timeout=15000)
        self.assertEqual(page.locator("#items-grid article", has_text=identity.BOTTLE).count(), 2)
        self.assertEqual(self.page_errors, [], self.page_errors)
        api.close()

    def test_99_no_request_left_the_origin(self):
        self.assertGreater(len(self.requests), 20, "interception saw too few requests to be meaningful")
        self.assertEqual(self.foreign, [], f"requests left the origin: {self.foreign}")
        paths = {urlsplit(url).path for _, url in self.requests}
        for expected in ("/", "/api/chat", "/api/items"):
            self.assertIn(expected, paths)
        self.assertTrue(any(path.endswith("/evidence") for path in paths), "the detail view must load the evidence list")
        self.assertTrue(any("/observations/" in path and path.endswith("/image") for path in paths), "evidence rows must load observation images")
        self.assertTrue(any(path.endswith("/link") for path in paths))
        self.assertTrue(any(path.endswith("/unlink") for path in paths))
        self.assertTrue(any(path.endswith("/assign") for path in paths))
        self.assertFalse(any(IDENTITY_MODEL in path for path in paths), "the identity model never leaves the server")
        self.assertEqual(self.page_errors, [], self.page_errors)


# --- CP4: idle keyframes, the Privacy view, erasure and the new renderings ------------------
# A third app (real time, no injected clock) with the CP3 scripted processor so API-seeded
# packets carry exactly the observations each case needs (nested placements for an
# inferred item, a placement whose idle "gone" frame the worker turns into
# negative_reobservation). The idle-keyframe case runs the fake camera in automatic mode
# (fake worker ready, server capability enabled as in test_05) with every frame reporting
# no hand, and drives time with Playwright's clock (page.clock) so the 30 s idle timer
# elapses in a few real seconds. Element ids/classes the page must provide (Builder C):
#   nav:      button[data-view=privacy], section #view-privacy
#   privacy:  #retention-form with number inputs #retention-episodes-days,
#             #retention-idle-hours, #retention-landmarks-hours, text #retention-consent
#             (the consent version), submit #retention-save (confirmed in #confirm-dialog /
#             #confirm-ok), status #retention-status; counts in #retention-counts as
#             elements [data-count=idle_cached|idle_promoted|revisions_expired|
#             landmarks_reduced] whose text is the integer; "Erase everything": input
#             #erase-all-phrase, button #erase-all (disabled until the phrase is exactly
#             "ERASE EVERYTHING"), confirmed in #confirm-dialog; the server report in
#             #privacy-status
#   detail:   #erase-item button in #item-dialog ("Erase this item"), confirmed in
#             #confirm-dialog; afterwards the item is gone from #items-grid
#   cards:    an inferred item's card text contains "probably with {container name}" and
#             the container's location; a negative_reobservation item's card text contains
#             "no longer there"
#   camera:   #camera-summary carries the idle keyframe counter (the word "idle" next to
#             the number of frames posted) while automatic capture runs
PRIVACY_PIN_PHRASE = "ERASE EVERYTHING"
IDLE_FIELDS = {"schema_version", "device_id", "session_id", "frame_id", "t_ms", "clock_anchor", "capture", "jpeg_b64", "motion_energy"}


class PrivacySmokeFixture(SmokeFixture):
    @classmethod
    def make_processor(cls):
        import test_cp3_identity as identity
        return identity.Cp3Processor()

    @classmethod
    def setUpClass(cls):
        cls.posted_idle = []
        cls.idle_statuses = []
        super().setUpClass()
        import test_cp4_fixtures as fx
        cls.fx = fx
        cls.serial = 0
        cls.phase = 0
        cls.device = str(uuid.uuid5(uuid.NAMESPACE_URL, "pam-privacy-smoke-device"))
        cls.session_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "pam-privacy-smoke-session"))
        if getattr(cls, "context", None) is not None:
            cls.context.on("response", lambda response: cls.idle_statuses.append(response.status) if response.url == cls.origin + "/api/idle" else None)

    @classmethod
    def _route(cls, route, request):
        if request.method == "POST" and request.url == cls.origin + "/api/idle":
            try:
                cls.posted_idle.append(json.loads(request.post_data or ""))
            except ValueError:
                cls.posted_idle.append({"error": "unparseable body"})
        super()._route(route, request)

    def api(self):
        """One signed-in httpx client for the whole class: the erase-all PIN check shares
        the sign-in rate limit (5 per client per minute), so logins are budgeted."""
        client = getattr(type(self), "shared_api", None)
        if client is None:
            client = super().api()
            type(self).shared_api = client
        return client

    @classmethod
    def tearDownClass(cls):
        client = getattr(cls, "shared_api", None)
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        super().tearDownClass()

    # --- seeding over the API (real time: wall anchors sit within the last hour) ----------
    def seed(self, api, observations, *, minutes_ago=60, rest=None, **packet_kwargs):
        fx = self.fx
        type(self).serial += 1
        type(self).phase += 1
        wall_ms = int(time.time() * 1000) - minutes_ago * 60 * 1000
        packet = fx.episode_packet(self.serial, rest=fx.golden("reference") if rest is None else rest, phase=self.phase,
                                   device=self.device, session=self.session_id, wall_ms=wall_ms, **packet_kwargs)
        frame = fx.rest_frame_id(packet)
        scripted = []
        for value in observations:
            value = dict(value)
            if value.get("frame_id") is None:
                value["frame_id"] = frame
            scripted.append(value)
        self.processor.observations[packet["episode_id"]] = scripted
        response = api.post("/api/episodes", content=bootstrap.encode_packet(packet),
                            headers={"origin": self.origin, "content-type": "application/json"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["ack"]["status"], "stored")
        return packet

    def post_idle(self, api, name, *, minutes_ago):
        fx = self.fx
        packet = fx.idle_packet(fx.golden(name), device=self.device, session=self.session_id,
                                wall_ms=int(time.time() * 1000) - minutes_ago * 60 * 1000)
        response = api.post("/api/idle", content=bootstrap.encode_packet(packet), headers={"origin": self.origin, "content-type": "application/json"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIs(response.json()["retained"], True, response.text)
        return packet

    def wait_catalogue(self, api, predicate, what, timeout=15):
        deadline = time.monotonic() + timeout
        items = []
        while time.monotonic() < deadline:
            items = api.get("/api/items").json()["items"]
            if not any(item["index_pending"] for item in items) and predicate(items):
                return items
            time.sleep(0.1)
        self.fail(f"{what}; catalogue: {[(i['name'], i['location_status'], i.get('stale_reason')) for i in items]}")

    def seed_renderings(self, api):
        """The keys inside the basket, the basket moved (keys inferred); a bottle placed,
        then an idle 'gone' frame the worker turns into negative_reobservation. Idempotent
        per class. Returns {name: item}."""
        if getattr(type(self), "rendered", None):
            return self.rendered
        fx = self.fx
        basket, keys, bottle = "synthetic smoke basket", "synthetic smoke keys", "synthetic smoke bottle"
        self.seed(api, [fx.observation(None, fx.BLOCK_BBOX, label=basket, location="fixture smoke counter", continuity_id="smoke-basket"),
                        fx.observation(None, [68.0, 48.0, 92.0, 72.0], label=keys, location="fixture smoke counter", continuity_id="smoke-keys")], minutes_ago=60)
        self.wait_catalogue(api, lambda items: {i["name"] for i in items} >= {basket, keys}, "basket and keys expected")
        self.seed(api, [fx.observation(None, [8.0, 8.0, 56.0, 36.0], label=basket, location="fixture smoke shelf", continuity_id="smoke-basket")], minutes_ago=45)
        self.wait_catalogue(api, lambda items: any(i["name"] == keys and i["location_status"] == "inferred" for i in items), "the keys should read inferred once the basket moved")
        self.seed(api, [fx.observation(None, fx.BLOCK_BBOX, label=bottle, location="fixture smoke table")], minutes_ago=40)
        self.wait_catalogue(api, lambda items: any(i["name"] == bottle and i["location_status"] == "placed" for i in items), "bottle expected")
        self.post_idle(api, "gone", minutes_ago=20)
        items = self.wait_catalogue(api, lambda items: any(i["name"] == bottle and i.get("stale_reason") == "negative_reobservation" for i in items),
                                    "the worker should turn the idle 'gone' frame into negative_reobservation")
        # The same frame shows the relocated basket (plain texture at its new place) still
        # present: the worker promotes it into a "reobservation" sighting. Wait for that
        # row deterministically (index_pending clear AND the row present) so no page load
        # races the worker (Builder C's "1 evidence row instead of 2" report).
        basket_id = next(i["item_id"] for i in items if i["name"] == basket)
        deadline = time.monotonic() + 15
        rows = []
        while time.monotonic() < deadline:
            catalogue = api.get("/api/items").json()["items"]
            rows = api.get(f"/api/items/{basket_id}/evidence").json()["observations"]
            if not any(i["index_pending"] for i in catalogue) and any(r.get("source") == "reobservation" for r in rows):
                break
            time.sleep(0.1)
        self.assertTrue(any(r.get("source") == "reobservation" for r in rows), f"the basket never gained its idle sighting: {rows}")
        type(self).basket_rows = rows
        type(self).rendered = {i["name"]: i for i in items}
        return self.rendered

    def show_privacy(self):
        self.page.click("nav button[data-view=privacy]")
        self.page.wait_for_selector("#view-privacy:not([hidden])", timeout=5000)

    def count(self, name):
        text = self.text(f"#retention-counts [data-count='{name}']").strip()
        self.assertRegex(text, r"^\d+$", f"{name} count must render as an integer, got {text!r}")
        return int(text)


class PrivacySmokeTests(PrivacySmokeFixture):
    def test_10_privacy_view_shows_retention_and_counts_and_an_edit_persists(self):
        api = self.api()
        # An idle frame dated before every placement the later cases seed (90 min ago):
        # it is cached (counted) but never re-observed against them. A frame dated AFTER
        # a later-seeded placement would be a legitimate sighting at that later time and
        # change what test_20 can expect (the order effect Builder C reported).
        self.post_idle(api, "present", minutes_ago=90)
        page = self.load(None)
        self.ensure_signed_in()
        self.show_privacy()
        page.wait_for_function("() => (document.getElementById('retention-episodes-days') || {}).value === '30'", timeout=10000, polling=100)
        self.assertEqual(page.input_value("#retention-episodes-days"), "30", "coordinator ruling 8: the 30-day default")
        self.assertEqual(page.input_value("#retention-idle-hours"), "24")
        self.assertEqual(page.input_value("#retention-landmarks-hours"), "72")
        self.assertIn("rig-2026-10", self.text("#retention-consent"))
        self.wait_text("#privacy-consent-state", "Acknowledged")
        self.assertIn("not guaranteed", self.text("#privacy-disclosure"), "the disclosure is shown verbatim (ruling 9)")
        page.wait_for_function("() => /^\\d+$/.test((document.querySelector('#retention-counts [data-count=idle_cached]') || {}).textContent || '')", timeout=10000, polling=100)
        self.assertEqual(self.count("idle_cached"), 1)
        for name in ("idle_promoted", "revisions_expired", "landmarks_reduced"):
            self.assertEqual(self.count(name), 0, name)
        # Edit episodes_days with confirmation; the PUT is observed and the value persists.
        page.fill("#retention-episodes-days", "60")
        page.click("#retention-save")
        self.confirm_dialog()
        page.wait_for_function("() => /saved|updated|retention/i.test(document.getElementById('retention-status').textContent || '') && !/loading|saving/i.test(document.getElementById('retention-status').textContent || '')", timeout=10000, polling=100)
        status = self.text("#retention-status")
        self.assertNotIn("HTTP", status)
        self.assertEqual(api.get("/api/retention").json()["retention"]["episodes_days"], 60, "the edit persisted on the server")
        puts = [(url, status) for url, status in self.responses if url == self.origin + "/api/retention"]
        self.assertTrue(any(status == 200 for _, status in puts), puts)
        page.reload(wait_until="load")
        self.ensure_signed_in()
        self.show_privacy()
        page.wait_for_function("() => (document.getElementById('retention-episodes-days') || {}).value === '60'", timeout=10000, polling=100)
        # Out-of-range input is refused by the page or the server without changing the setting.
        page.fill("#retention-episodes-days", "3")
        page.click("#retention-save")
        if page.locator("#confirm-dialog[open]").count():
            page.click("#confirm-ok")
        self.pump(0.8)
        self.assertEqual(api.get("/api/retention").json()["retention"]["episodes_days"], 60, "an out-of-range value never persists")
        self.assertEqual(self.page_errors, [], self.page_errors)

    def confirm_dialog(self):
        self.page.wait_for_selector("#confirm-dialog[open]", timeout=5000)
        self.page.click("#confirm-ok")

    def test_20_inferred_and_negative_reobservation_items_render_honestly(self):
        api = self.api()
        rendered = self.seed_renderings(api)
        keys, bottle = rendered["synthetic smoke keys"], rendered["synthetic smoke bottle"]
        self.assertEqual(keys["inference"]["container"], rendered["synthetic smoke basket"]["item_id"])
        page = self.load(None)
        self.ensure_signed_in()
        self.show("items")
        page.wait_for_function("id => Boolean(document.querySelector(`#items-grid article[data-item-id='${id}']`))", arg=keys["item_id"], timeout=15000)
        keys_card = page.locator(f"#items-grid article[data-item-id='{keys['item_id']}']")
        body = keys_card.text_content() or ""
        self.assertIn("probably with", body.lower())
        self.assertIn("synthetic smoke basket", body)
        self.assertIn("fixture smoke shelf", body)
        self.assertNotIn("Location: placed", body)
        bottle_card = page.locator(f"#items-grid article[data-item-id='{bottle['item_id']}']")
        self.assertEqual(bottle_card.count(), 1)
        body = bottle_card.text_content() or ""
        self.assertIn("no longer there", body.lower())
        self.assertNotIn("Location: placed", body)
        self.show("chat")
        page.fill("#chat-text", "where are my synthetic smoke keys")
        page.click("#chat-send")
        self.wait_text("#chat-status", "Answer received.")
        text = page.locator("#conversation .message.assistant").last.text_content() or ""
        self.assertIn("Answer type: hedged", text)
        self.assertIn("I think", text)
        self.assertIn("synthetic smoke basket", text)
        self.assertNotIn("last saw at fixture smoke counter", text)
        # F3: a promoted idle still is labelled as such in the evidence list, never as a
        # hand event. The basket's rows: the nested placement, the relocation and the
        # idle sighting (seeded and awaited over the API, so the count is deterministic).
        basket = rendered["synthetic smoke basket"]["item_id"]
        expected_rows = len(self.basket_rows)
        self.assertGreaterEqual(expected_rows, 3, self.basket_rows)
        self.show("items")
        page.wait_for_function("id => Boolean(document.querySelector(`#items-grid article[data-item-id='${id}']`))", arg=basket, timeout=15000)
        page.locator(f"#items-grid article[data-item-id='{basket}'] button", has_text="View evidence").first.click()
        page.wait_for_selector("#item-dialog[open]", timeout=5000)
        page.wait_for_function("n => document.querySelectorAll('#evidence-list .evidence-row').length === n", arg=expected_rows, timeout=15000)
        badges = page.locator("#evidence-list .evidence-row .badge-idle")
        self.assertEqual(badges.count(), sum(1 for r in self.basket_rows if r.get("source") == "reobservation"), "one idle badge per promoted still")
        self.assertIn("Seen while idle (automatic still), not a hand event", badges.first.text_content() or "")
        hand_rows = page.locator("#evidence-list .evidence-row:not(:has(.badge-idle))")
        self.assertEqual(hand_rows.count(), expected_rows - badges.count())
        page.click("#detail-close")
        self.assertEqual(self.page_errors, [], self.page_errors)

    def test_30_erase_this_item_removes_it_from_stored_items(self):
        api = self.api()
        rendered = self.seed_renderings(api)
        bottle = rendered["synthetic smoke bottle"]["item_id"]
        page = self.load(None)
        self.ensure_signed_in()
        self.show("items")
        page.wait_for_function("id => Boolean(document.querySelector(`#items-grid article[data-item-id='${id}']`))", arg=bottle, timeout=15000)
        page.locator(f"#items-grid article[data-item-id='{bottle}'] button", has_text="View evidence").first.click()
        page.wait_for_selector("#item-dialog[open]", timeout=5000)
        erase = page.locator("#item-dialog #erase-item")
        self.assertEqual(erase.count(), 1, "the detail view offers Erase this item")
        page.wait_for_function("() => !document.getElementById('erase-item').disabled", timeout=10000, polling=100)
        erase.click()
        self.confirm_dialog()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and api.get(f"/api/items/{bottle}").status_code != 404:
            self.pump(0.1)
        erase_responses = [(url, status) for url, status in self.responses if urlsplit(url).path == f"/api/items/{bottle}/erase"]
        self.assertEqual(api.get(f"/api/items/{bottle}").status_code, 404,
                         f"the item is erased on the server; erase responses: {erase_responses}; detail-status: {self.text('#detail-status')!r}; "
                         f"app-status: {self.text('#app-status')!r}; confirm open: {page.locator('#confirm-dialog[open]').count()}; console: {self.console[-6:]}")
        if page.locator("#item-dialog[open]").count():
            page.click("#detail-close")
        self.show("items")
        page.wait_for_function("id => !document.querySelector(`#items-grid article[data-item-id='${id}']`)", arg=bottle, timeout=15000)
        self.assertNotIn("synthetic smoke bottle", self.text("#items-grid"))
        self.assertIn("synthetic smoke keys", self.text("#items-grid"), "unrelated items stay")
        statuses = {status for url, status in self.responses if urlsplit(url).path == f"/api/items/{bottle}/erase"}
        self.assertEqual(statuses, {200}, "exactly the erase route was used, successfully")
        self.assertEqual(self.page_errors, [], self.page_errors)

    def test_40_erase_everything_requires_the_typed_phrase(self):
        api = self.api()
        self.seed_renderings(api)
        self.assertGreaterEqual(len(api.get("/api/items").json()["items"]), 2)
        page = self.load(None)
        self.ensure_signed_in()
        self.show_privacy()
        page.wait_for_selector("#erase-all", timeout=10000)
        page.wait_for_selector("#erase-all-phrase", timeout=10000)
        page.wait_for_selector("#erase-all-pin", timeout=10000)
        self.assertTrue(page.locator("#erase-all").is_disabled(), "disabled until the phrase and the PIN are typed")
        calls_before = sum(1 for source, url in self.requests if source == "route" and urlsplit(url).path == "/api/erase-all")
        page.fill("#erase-all-pin", PIN)
        page.fill("#erase-all-phrase", "erase everything")
        self.pump(0.3)
        self.assertTrue(page.locator("#erase-all").is_disabled(), "the wrong case is not the phrase")
        page.fill("#erase-all-phrase", PRIVACY_PIN_PHRASE[:-1])
        self.pump(0.3)
        self.assertTrue(page.locator("#erase-all").is_disabled(), "a prefix is not the phrase")
        page.fill("#erase-all-phrase", PRIVACY_PIN_PHRASE)
        page.fill("#erase-all-pin", "")
        self.pump(0.3)
        self.assertTrue(page.locator("#erase-all").is_disabled(), "the phrase alone is not enough (ruling 4: the PIN travels with the request)")
        self.assertEqual(sum(1 for source, url in self.requests if source == "route" and urlsplit(url).path == "/api/erase-all"), calls_before, "no request without the phrase and the PIN")
        page.fill("#erase-all-pin", PIN)
        page.wait_for_function("() => !document.getElementById('erase-all').disabled", timeout=5000, polling=100)
        page.click("#erase-all")
        self.confirm_dialog()
        # Ruling 10: VACUUM INTO runs before the response; wait for the page's status first.
        page.wait_for_function("() => (document.getElementById('privacy-status').textContent || '').trim().length > 0 && !/loading|erasing/i.test(document.getElementById('privacy-status').textContent || '')", timeout=20000, polling=100)
        status = self.text("#privacy-status")
        self.assertNotIn("HTTP", status)
        statuses = {status for url, status in self.responses if urlsplit(url).path == "/api/erase-all"}
        self.assertEqual(statuses, {200}, "the erase-all request succeeded once")
        self.assertEqual(api.get("/api/items").json()["items"], [], "everything is erased on the server")
        self.assertEqual(page.input_value("#erase-all-pin"), "", "the PIN is not kept in the page")
        self.show("items")
        self.wait_text("#items-status", "0 stored items", timeout=15000)
        self.assertEqual(page.locator("#items-grid article").count(), 0)
        type(self).rendered = None
        self.assertEqual(self.page_errors, [], self.page_errors)

    def test_50_idle_keyframe_is_posted_in_automatic_mode_without_a_hand(self):
        self.provision_server()
        api = self.api()
        hand = next(cap for cap in api.get("/api/health").json()["capabilities"] if cap["name"] == HAND_CAPABILITY)
        self.assertTrue(hand["enabled"], hand)
        # Fake timers from here on (the page's timers, Date and performance.now); the clock
        # keeps flowing at real-time rate and run_for() advances it on demand.
        self.page.clock.install()
        page = self.load("ready")
        self.ensure_signed_in()
        self.show("camera")
        page.wait_for_function("() => !document.getElementById('automatic-toggle').disabled", timeout=10000, polling=100)
        hands = self.golden_hands()
        page.evaluate("script => { window.__pamFake.script = script; window.__pamFake.replies = 0; }", [hands["no_hand"]])
        posted_before = len(self.posted_idle)
        episodes_before = len(self.posted_packets)
        page.click("#camera-start")
        self.wait_text("#camera-status", "manual marks only", timeout=15000)
        page.check("#automatic-toggle")
        self.wait_text("#camera-status", "automatic capture (hand model fake-0.0)")
        time.sleep(2.5)   # real time: the no-hand condition must hold for at least 2 s
        simulated = 0
        while simulated < 35000 and len(self.posted_idle) == posted_before:
            page.clock.run_for(500)
            simulated += 500
        self.assertGreaterEqual(len(self.posted_idle), posted_before + 1, f"no POST /api/idle within {simulated} ms of simulated time")
        self.assertLessEqual(len(self.posted_idle) - posted_before, 2, "at most one idle keyframe per 30 s")
        body = self.posted_idle[-1]
        self.assertEqual(set(body), IDLE_FIELDS, body.keys())
        self.assertEqual(body["schema_version"], 1)
        for key in ("device_id", "session_id"):
            self.assertEqual(str(uuid.UUID(body[key])), body[key].lower())
        self.assertIsInstance(body["frame_id"], str)
        self.assertTrue(body["frame_id"])
        self.assertIsInstance(body["t_ms"], int)
        self.assertEqual(set(body["clock_anchor"]), {"mono_ms", "wall_ms"})
        self.assertIsInstance(body["motion_energy"], (int, float))
        self.assertTrue(0 <= body["motion_energy"] <= 1)
        self.assertLess(body["motion_energy"], 0.035, "a static clip is not moving")
        import base64
        jpeg = base64.b64decode(body["jpeg_b64"])
        self.assertTrue(jpeg.startswith(b"\xff\xd8"))
        self.assertLessEqual(len(jpeg), 256 * 1024)
        import cv2
        import numpy as np
        image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_UNCHANGED)
        self.assertEqual(image.shape[:2], (body["capture"]["height"], body["capture"]["width"]), "a capture-resolution frame")
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and len(self.idle_statuses) < len(self.posted_idle) - posted_before:
            self.pump(0.1)
        self.assertTrue(self.idle_statuses, "the server answered the idle post")
        self.assertEqual(set(self.idle_statuses), {200}, self.idle_statuses)
        connection = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)
        try:
            rows = connection.execute("SELECT frame_id, promoted FROM idle_frames").fetchall()
        finally:
            connection.close()
        self.assertIn(body["frame_id"], {row[0] for row in rows}, "the frame is in the idle cache")
        page.wait_for_function("() => /idle/i.test(document.getElementById('camera-summary').textContent || '')", timeout=10000, polling=100)
        summary = self.text("#camera-summary")
        self.assertRegex(summary.lower(), r"idle\D{0,24}[1-9]\d*|[1-9]\d*\D{0,24}idle", f"the camera summary counts idle keyframes: {summary!r}")
        self.assertEqual(len(self.posted_packets), episodes_before, "no episode packet without a hand")
        self.assertEqual(page.evaluate("() => window.__pamFake.errors"), [])
        page.click("#camera-stop")
        self.wait_text("#camera-status", "Camera off")
        self.assertEqual(self.page_errors, [], self.page_errors)

    def test_99_no_request_left_the_origin(self):
        self.assertGreater(len(self.requests), 20, "interception saw too few requests to be meaningful")
        self.assertEqual(self.foreign, [], f"requests left the origin: {self.foreign}")
        paths = {urlsplit(url).path for _, url in self.requests}
        for expected in ("/", "/api/items", "/api/retention", "/api/erase-all", "/api/idle", "/api/consent"):
            self.assertIn(expected, paths)
        self.assertTrue(any(path.endswith("/erase") for path in paths))
        self.assertEqual(self.page_errors, [], self.page_errors)


# --- CP5: the full flow, "Why this answer", counters and the Status panel, notices -----------
# A fourth app (the identity app: synthetic embedder, CP3 scripted processor, approved
# synthetic calibration) so one class can seed a trusted placement AND lookalikes over
# the API. The browser then has to render the CP5 answer contract. Element ids/classes
# the page must provide (Builder C), beyond the CP3/CP4 ones above:
#   chat:    every assistant message carries <details class="why-answer"> whose <summary>
#            reads "Why this answer" and which lists one li.basis-reason[data-basis=<token>]
#            per `basis` token, each in plain words (no raw token text, no underscores);
#            the message text names the answer's room ("room unknown"); a confident or
#            hedged member card (article.item-card) shows the evidence photo with the
#            recorded region outlined (.evidence-figure .target once the image loads) and
#            "Observed: <time>" (never "Time not recorded")
#   privacy: a Status panel #status-panel with #coverage-today holding one element
#            [data-coverage=camera_on_ms|gap_ms|episodes|packets|idle_sent|idle_dropped|
#            sessions] whose text is an integer (today's /api/coverage), #live-counters with
#            [data-counter=<counter key>] integers for this browser's current capture
#            session, refreshed by #refresh-privacy; a link a[href="/notices"] to the
#            third-party notices page (same origin)
#   camera:  in automatic mode the page POSTs /api/telemetry every 60 s and at stop with
#            exactly the plan's key sets (see test_cp5_fixtures); the request is observed
#            through interception, so the fake clock (page.clock) drives the 60 s timer.
TELEMETRY_TOP = {"schema_version", "device_id", "session_id", "t_ms", "clock_anchor", "window_ms", "counters", "timing", "settings"}
COUNTER_KEYS = {"frames_captured", "frames_analysed", "frames_skipped_busy", "frames_dropped_backpressure", "landmark_results",
                "landmark_timeouts", "episodes_started", "episodes_finished", "episodes_aborted", "packets_sent", "packets_acked",
                "idle_sent", "idle_dropped", "gaps", "gap_ms", "bytes_sent"}
TIMING_KEYS = {"fps_observed", "infer_ms_p50", "infer_ms_p95", "tick_ms_p95"}
SETTINGS_KEYS = {"width", "height", "frame_rate"}
COVERAGE_KEYS = {"camera_on_ms", "gap_ms", "episodes", "packets", "idle_sent", "idle_dropped", "sessions"}
BASIS_VOCABULARY = {"trusted_match", "provisional_match", "placed", "sighted", "inferred", "aged", "expired", "negative_reobservation",
                    "coverage_gap", "picked_up", "lookalikes", "name_ambiguous", "no_evidence", "index_pending", "consent_pending"}
SPECTACLES = "synthetic spectacles"


class Cp5SmokeFixture(IdentitySmokeFixture):
    @classmethod
    def setUpClass(cls):
        cls.posted_telemetry = []
        cls.telemetry_statuses = []
        super().setUpClass()
        if getattr(cls, "context", None) is not None:
            cls.context.on("response", lambda response: cls.telemetry_statuses.append(response.status) if response.url == cls.origin + "/api/telemetry" else None)

    @classmethod
    def _route(cls, route, request):
        if request.method == "POST" and request.url == cls.origin + "/api/telemetry":
            try:
                cls.posted_telemetry.append(json.loads(request.post_data or ""))
            except ValueError:
                cls.posted_telemetry.append({"error": "unparseable body"})
        super()._route(route, request)

    def api(self):
        """One signed-in client for the class: sign-ins are rate limited (5 per client
        per minute) and every case here talks to the API."""
        client = getattr(type(self), "shared_api", None)
        if client is None:
            client = super().api()
            type(self).shared_api = client
        return client

    @classmethod
    def tearDownClass(cls):
        client = getattr(cls, "shared_api", None)
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        super().tearDownClass()

    def seed_spectacles(self, api):
        """One trusted placement (tag 2, a distinct item from the lookalike pair's tag 0/1
        glasses) observed within the last hour. Idempotent per class; returns the item."""
        existing = getattr(type(self), "spectacles", None)
        if existing:
            return existing
        self.post_tagged(api, [self.identity.region(self.identity.LEFT, 2)], labels=[SPECTACLES], locations=["synthetic reading table"])
        items = self.wait_catalogue(api, lambda items: any(i["name"] == SPECTACLES and i["location_status"] == "placed" for i in items), "spectacles expected")
        type(self).spectacles = next(i for i in items if i["name"] == SPECTACLES)
        return self.spectacles

    def ask(self, text):
        page = self.page
        before = page.locator("#conversation .message.assistant").count()
        page.fill("#chat-text", text)
        page.click("#chat-send")
        page.wait_for_function("n => document.querySelectorAll('#conversation .message.assistant').length > n", arg=before, timeout=10000)
        self.wait_text("#chat-status", "Answer received.")
        return page.locator("#conversation .message.assistant").last

    def why(self, message, expected_tokens=None):
        """The collapsible "Why this answer" of an assistant message: its reasons in
        plain words, one per basis token. Returns {token: text}."""
        details = message.locator("details.why-answer")
        self.assertEqual(details.count(), 1, "every answer carries one 'Why this answer'")
        summary = details.locator("summary")
        self.assertEqual(summary.count(), 1)
        self.assertIn("why this answer", (summary.text_content() or "").lower())
        self.assertFalse(details.evaluate("node => node.open"), "collapsed until opened")
        summary.click()
        self.page.wait_for_function("node => node.open", arg=details.element_handle(), timeout=5000)
        reasons = details.locator("li.basis-reason")
        self.assertGreaterEqual(reasons.count(), 1, "the basis is never empty")
        out = {}
        for index in range(reasons.count()):
            reason = reasons.nth(index)
            token = reason.get_attribute("data-basis")
            self.assertIn(token, BASIS_VOCABULARY, f"unknown basis token in the page: {token}")
            text = (reason.text_content() or "").strip()
            self.assertTrue(len(text) >= 8, f"a reason in plain words, got {text!r}")
            self.assertNotIn("_", text, f"plain words, not the token: {text!r}")
            self.assertNotEqual(text.lower(), token.replace("_", " "), "plain words, not the token with spaces")
            out[token] = text
        if expected_tokens is not None:
            self.assertEqual(list(out), list(expected_tokens), out)
        return out

    def wait_outline(self, message):
        self.page.wait_for_function("node => { const img = node.querySelector('article.item-card img'); return img && img.complete && img.naturalWidth > 0; }",
                                    arg=message.element_handle(), timeout=10000)
        self.pump(0.2)
        return message.locator("article.item-card .evidence-figure .target")


class Cp5SmokeTests(Cp5SmokeFixture):
    def test_10_placement_answers_with_photo_outline_time_room_and_why(self):
        api = self.api()
        item = self.seed_spectacles(api)
        answer = api.post("/api/chat", json={"text": "where are my synthetic spectacles"}, headers={"origin": self.origin}).json()
        self.assertEqual(answer["shape"], "confident", answer)
        self.assertEqual(answer["basis"], ["trusted_match", "placed"])
        page = self.load(None)
        self.ensure_signed_in()
        self.show("chat")
        message = self.ask("where are my synthetic spectacles")
        text = message.text_content() or ""
        self.assertIn("Answer type: confident", text)
        self.assertIn("synthetic reading table", text)
        self.assertIn("room unknown", text.lower(), "the answer names its room ('room unknown' until a source exists)")
        self.assertIn("Observed:", text, "the capture time is shown")
        self.assertNotIn("Time not recorded", text)
        year = time.strftime("%Y", time.gmtime(item["observed_at_ms"] / 1000))
        self.assertIn(year, text, "the capture time is a real date")
        card = message.locator("article.item-card")
        self.assertEqual(card.count(), 1)
        self.assertEqual(card.get_attribute("data-item-id"), item["item_id"])
        image = card.locator("img")
        self.assertEqual(image.count(), 1)
        self.assertEqual(image.get_attribute("src"), f"/api/items/{item['item_id']}/image")
        outline = self.wait_outline(message)
        self.assertEqual(outline.count(), 1, "the recorded region is outlined on the photo")
        self.assertNotIn("target-unverified", outline.get_attribute("class") or "", "a trusted placement is outlined as verified")
        reasons = self.why(message, ["trusted_match", "placed"])
        for token, words in reasons.items():
            self.assertNotIn("last saw", words.lower())
        self.assertEqual(self.page_errors, [], self.page_errors)

    def test_20_abstain_also_explains_itself_without_a_photo(self):
        page = self.load(None)
        self.ensure_signed_in()
        self.show("chat")
        message = self.ask("where is my unseen thing")
        text = message.text_content() or ""
        self.assertIn("Answer type: abstain", text)
        self.assertNotIn("last saw", text.lower())
        self.assertEqual(message.locator("img").count(), 0)
        self.why(message, ["no_evidence"])
        self.assertEqual(self.page_errors, [], self.page_errors)

    def test_30_rename_then_re_ask_answers_with_the_new_name(self):
        # Coordinator ruling 8: matching is word-subset (CP1 rule), so the new name's
        # words must not be a superset of the old name's for the old question to abstain.
        api = self.api()
        item = self.seed_spectacles(api)
        response = api.post(f"/api/items/{item['item_id']}/name", json={"name": "reading glasses"}, headers={"origin": self.origin})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["name"], "reading glasses")
        page = self.load(None)
        self.ensure_signed_in()
        self.show("chat")
        message = self.ask("where are my reading glasses")
        text = message.text_content() or ""
        self.assertIn("Answer type: confident", text)
        self.assertIn("reading glasses", text)
        self.assertIn("synthetic reading table", text)
        self.assertEqual(message.locator("article.item-card").get_attribute("data-item-id"), item["item_id"])
        self.why(message, ["trusted_match", "placed"])
        # The old name no longer matches: honest abstention, no photo.
        old = self.ask("where are my synthetic spectacles")
        self.assertIn("Answer type: abstain", old.text_content() or "")
        self.assertEqual(old.locator("img").count(), 0)
        self.assertEqual(self.page_errors, [], self.page_errors)

    def test_40_group_answer_tap_a_member_and_re_answer_with_why(self):
        api = self.api()
        a, b = self.seed_lookalikes(api)
        page = self.load(None)
        self.ensure_signed_in()
        self.show("chat")
        message = self.ask(self.identity.ASK_GLASSES)
        text = message.text_content() or ""
        self.assertIn("Answer type: group", text)
        self.assertIn("which one is yours", text.lower())
        self.assertIn("room unknown", text.lower())
        members = message.locator(".group-members .group-member")
        self.assertEqual(members.count(), 2, text)
        self.assertEqual({members.nth(i).get_attribute("data-item-id") for i in range(2)}, {a, b})
        page.wait_for_function("() => [...document.querySelectorAll('.group-members img')].every(img => img.complete && img.naturalWidth > 0)", timeout=10000)
        self.why(message, ["lookalikes"])
        answers_before = page.locator("#conversation .message.assistant").count()
        requests_before = len(self.requests)
        chosen = members.nth(0).get_attribute("data-item-id")
        members.nth(0).click()
        page.wait_for_function("n => document.querySelectorAll('#conversation .message.assistant').length > n", arg=answers_before, timeout=10000)
        self.wait_text("#chat-status", "Answer received.")
        assigns = [url for source, url in self.requests[requests_before:] if source == "route" and urlsplit(url).path.endswith("/assign")]
        self.assertEqual(len(assigns), 1, assigns)
        self.assertTrue(urlsplit(assigns[0]).path.startswith(f"/api/items/{chosen}/observations/"))
        resolved = page.locator("#conversation .message.assistant").last
        resolved_text = resolved.text_content() or ""
        self.assertNotIn("Answer type: group", resolved_text)
        self.assertNotIn("Answer type: confident", resolved_text, "a member's certainty is never upgraded by selecting it")
        self.assertEqual(resolved.locator("article.item-card").get_attribute("data-item-id"), chosen)
        reasons = self.why(resolved)
        self.assertNotIn("name_ambiguous", reasons)
        self.assertTrue(set(reasons) & {"trusted_match", "provisional_match", "sighted", "placed", "lookalikes"}, reasons)
        items = {i["item_id"]: i for i in api.get("/api/items").json()["items"]}
        self.assertEqual([items[a]["lookalikes"], items[b]["lookalikes"]], [[], []])
        self.assertEqual(self.page_errors, [], self.page_errors)

    def test_50_counters_are_posted_under_the_fake_clock_and_the_status_panel_shows_coverage(self):
        self.provision_server()
        api = self.api()
        hand = next(cap for cap in api.get("/api/health").json()["capabilities"] if cap["name"] == HAND_CAPABILITY)
        self.assertTrue(hand["enabled"], hand)
        # Fake timers for this page only (installed before the page scripts run on load).
        self.page.clock.install()
        page = self.load("ready")
        self.ensure_signed_in()
        self.show("camera")
        page.wait_for_function("() => !document.getElementById('automatic-toggle').disabled", timeout=10000, polling=100)
        hands = self.golden_hands()
        page.evaluate("script => { window.__pamFake.script = script; window.__pamFake.replies = 0; }", [hands["no_hand"]])
        posted_before = len(self.posted_telemetry)
        page.click("#camera-start")
        self.wait_text("#camera-status", "manual marks only", timeout=15000)
        page.check("#automatic-toggle")
        self.wait_text("#camera-status", "automatic capture (hand model fake-0.0)")
        time.sleep(1.0)   # real time: let a few frames flow before the clock jumps
        simulated = 0
        while simulated < 66000 and len(self.posted_telemetry) == posted_before:
            page.clock.run_for(500)
            simulated += 500
            self.pump(0.02)
        self.assertEqual(len(self.posted_telemetry), posted_before + 1, f"exactly one POST /api/telemetry within {simulated} ms of simulated time")
        body = self.posted_telemetry[-1]
        self.assertEqual(set(body), TELEMETRY_TOP, body.keys())
        self.assertEqual(body["schema_version"], 1)
        for key in ("device_id", "session_id"):
            self.assertEqual(str(uuid.UUID(body[key])), body[key].lower())
        self.assertIsInstance(body["t_ms"], int)
        self.assertEqual(set(body["clock_anchor"]), {"mono_ms", "wall_ms"})
        self.assertIsInstance(body["window_ms"], int)
        self.assertTrue(1000 <= body["window_ms"] <= 120000, body["window_ms"])
        self.assertEqual(set(body["counters"]), COUNTER_KEYS, body["counters"].keys())
        self.assertEqual(set(body["timing"]), TIMING_KEYS, body["timing"].keys())
        self.assertEqual(set(body["settings"]), SETTINGS_KEYS, body["settings"].keys())
        for key, value in body["counters"].items():
            self.assertIsInstance(value, int, key)
            self.assertNotIsInstance(value, bool, key)
            self.assertGreaterEqual(value, 0, key)
        for key, value in body["timing"].items():
            self.assertIsInstance(value, (int, float), key)
            self.assertNotIsInstance(value, bool, key)
            self.assertGreaterEqual(value, 0, key)
        for key, value in body["settings"].items():
            self.assertIsInstance(value, (int, float), key)
            # Coordinator ruling 9: frame_rate may read 0 when getSettings() lacks it; the
            # Chromium fake device used here reports it, so > 0 holds in this environment.
            self.assertGreater(value, 0, key)
        self.assertGreaterEqual(body["counters"]["frames_captured"], 1, "the fake camera produced frames")
        self.assertGreaterEqual(body["counters"]["frames_captured"], body["counters"]["frames_analysed"])
        self.assertEqual(body["counters"]["episodes_started"], 0, "no hand, no episode")
        self.assertEqual(body["counters"]["gaps"], 0)
        self.assertEqual(body["counters"]["gap_ms"], 0)
        self.assertGreaterEqual(body["settings"]["width"], 160, "the negotiated stream width (getSettings)")
        self.assertGreaterEqual(body["settings"]["height"], 120)
        # The server accepted it and it counts for the window's UTC day.
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and len(self.telemetry_statuses) < len(self.posted_telemetry) - posted_before:
            self.pump(0.1)
        self.assertEqual(set(self.telemetry_statuses), {200}, self.telemetry_statuses)
        wall_ms = body["clock_anchor"]["wall_ms"] + body["t_ms"] - body["clock_anchor"]["mono_ms"]
        day = time.strftime("%Y-%m-%d", time.gmtime(wall_ms / 1000))
        coverage = api.get("/api/coverage", params={"day": day}).json()
        self.assertTrue(COVERAGE_KEYS <= set(coverage), coverage)
        self.assertGreaterEqual(coverage["sessions"], 1)
        self.assertGreaterEqual(coverage["camera_on_ms"], body["window_ms"])
        # Stopping posts the final window (at most one more post) and the Status panel
        # shows today's coverage and this browser's live counters.
        page.click("#camera-stop")
        self.wait_text("#camera-status", "Camera off")
        self.pump(0.5)
        self.assertLessEqual(len(self.posted_telemetry) - posted_before, 2, "one post at 60 s and at most one at stop")
        self.show("privacy")
        page.wait_for_selector("#status-panel", timeout=10000)
        page.click("#refresh-privacy")
        page.wait_for_function("() => /^\\d+$/.test((document.querySelector('#status-panel #coverage-today [data-coverage=sessions]') || {}).textContent || '')", timeout=10000, polling=100)
        shown = {}
        for key in COVERAGE_KEYS:
            text = (self.text(f"#status-panel #coverage-today [data-coverage='{key}']") or "").strip()
            self.assertRegex(text, r"^\d+$", f"{key} renders as an integer, got {text!r}")
            shown[key] = int(text)
        self.assertGreaterEqual(shown["sessions"], 1)
        self.assertGreaterEqual(shown["camera_on_ms"], body["window_ms"])
        self.assertEqual(shown["gap_ms"], coverage["gap_ms"])
        live = page.locator("#status-panel #live-counters [data-counter]")
        self.assertGreaterEqual(live.count(), len(COUNTER_KEYS), "every counter of the current session is listed")
        for index in range(live.count()):
            element = live.nth(index)
            self.assertIn(element.get_attribute("data-counter"), COUNTER_KEYS)
            self.assertRegex((element.text_content() or "").strip(), r"^\d+$")
        self.assertEqual(page.evaluate("() => window.__pamFake.errors"), [])
        self.assertEqual(self.page_errors, [], self.page_errors)

    def test_60_privacy_view_links_to_the_notices_page(self):
        page = self.load(None)
        self.ensure_signed_in()
        self.show("privacy")
        link = page.locator("#view-privacy a[href='/notices']")
        self.assertEqual(link.count(), 1, "the Privacy view links to /notices")
        self.assertTrue((link.text_content() or "").strip(), "the link has text")
        href = link.get_attribute("href")
        self.assertEqual(href, "/notices")
        target = link.get_attribute("target")
        if target == "_blank":
            with self.context.expect_page(timeout=10000) as opened:
                link.click()
            notices = opened.value
            notices.wait_for_load_state("load")
            self.assertEqual(urlsplit(notices.url).netloc, urlsplit(self.origin).netloc, "same origin")
            self.assertEqual(urlsplit(notices.url).path, "/notices")
            body = notices.locator("body").text_content() or ""
            notices.close()
        else:
            link.click()
            page.wait_for_url(self.origin + "/notices", timeout=10000)
            body = page.locator("body").text_content() or ""
        lowered = body.lower()
        for name in ("mediapipe", "dino", "onnx", "fastapi", "starlette", "uvicorn", "pydantic", "numpy", "opencv"):
            self.assertIn(name, lowered, f"the notices page names {name}")
        self.assertIn("apache license", lowered)
        statuses = {status for url, status in self.responses if urlsplit(url).path == "/notices"}
        self.assertEqual(statuses, {200})
        self.assertEqual(self.page_errors, [], self.page_errors)

    def test_99_no_request_left_the_origin(self):
        self.assertGreater(len(self.requests), 20, "interception saw too few requests to be meaningful")
        self.assertEqual(self.foreign, [], f"requests left the origin: {self.foreign}")
        paths = {urlsplit(url).path for _, url in self.requests}
        for expected in ("/", "/api/chat", "/api/items", "/api/telemetry", "/notices", "/api/coverage"):
            self.assertIn(expected, paths)
        self.assertTrue(any(path.endswith("/assign") for path in paths))
        self.assertFalse(any(IDENTITY_MODEL in path for path in paths), "the identity model never leaves the server")
        self.assertEqual(self.page_errors, [], self.page_errors)


if __name__ == "__main__":
    unittest.main(verbosity=2)
