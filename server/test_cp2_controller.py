"""CP2 acceptance: the Python and browser controllers are the same machine.

    python3 -B server/test_cp2_controller.py -v

Every golden trace in server/fixtures/cp2/ is replayed through BOTH command-line
entry points in subprocesses (python3 -m perception.episode_controller and
node phone/assets/controller-replay.mjs) and the two must agree byte for byte on
stdout, and exactly on stderr and the exit code. The traces' "expected" logs were
authored by hand from the contract (docs/BUILD_PLAN.md section 2), so the suite
also checks that both machines do what the contract says, not merely that two
ports agree with each other. motionEnergy/motionStep and handBusy/handMetrics are
checked in-process in Python and through a generated Node script against the same
golden inputs, comparing parsed numbers.

This suite deliberately spawns python3 and node. No network, no model, no camera.
A missing node binary is a FAILURE here (the browser port cannot be verified
without it), never a skip.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURES = ROOT / "server" / "fixtures" / "cp2"
NODE_REPLAY = ROOT / "phone" / "assets" / "controller-replay.mjs"
BASIS = "synthetic golden, authored by the tester 2026-10-08; thresholds are initial values"
TIMEOUT = 60
NODE = shutil.which("node")


def clean_env():
    keys = ("PATH", "HOME", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC", "PATHEXT", "LANG", "LC_ALL")
    env = {key: os.environ[key] for key in keys if key in os.environ}
    env.update(PYTHONPATH="", PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8",
               NODE_OPTIONS="")
    return env


def run_python(trace: Path):
    return subprocess.run([sys.executable, "-B", "-m", "perception.episode_controller", str(trace)],
                          cwd=str(ROOT), env=clean_env(), capture_output=True, timeout=TIMEOUT)


def run_node(trace: Path):
    return subprocess.run([NODE, str(NODE_REPLAY), str(trace)],
                          cwd=str(ROOT), env=clean_env(), capture_output=True, timeout=TIMEOUT)


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --- independent oracles (plain Python, no numpy; written from the normative arithmetic) ---
MOTION_ON, MOTION_OFF = 0.035, 0.015


def oracle_blur(pixels, width, height):
    out = []
    for y in range(height):
        for x in range(width):
            total = 0
            for dy in (-1, 0, 1):
                yy = min(max(y + dy, 0), height - 1)
                for dx in (-1, 0, 1):
                    xx = min(max(x + dx, 0), width - 1)
                    total += pixels[yy * width + xx]
            out.append(total // 9)
    return out


def oracle_energy(prev, nxt, width, height):
    before, after = oracle_blur(prev, width, height), oracle_blur(nxt, width, height)
    total = sum(abs(a - b) for a, b in zip(after, before))
    denominator = width * height * 255
    scaled = (2 * total * 1000000 + denominator) // (2 * denominator)
    return scaled / 1000000


def oracle_replay(samples):
    """Hand-written restatement of the contract's machine, used only for the random
    property traces (the golden traces carry hand-authored expectations)."""
    phase, busy_since, rest_since, burst = "idle", None, None, False
    log = []
    for sample in samples:
        t = sample["t_ms"]
        busy, motion = sample.get("busy"), sample.get("motion")
        valid, gap = sample.get("frame_valid", False), sample.get("gap", False)
        actions = []
        if gap:
            actions = ["gap"] + (["abort"] if phase != "idle" else [])
            phase, busy_since, rest_since, burst = "idle", None, None, False
            log.append({"t_ms": t, "actions": actions, "phase": phase})
            continue
        if phase == "idle":
            if busy is True:
                phase, busy_since, rest_since, burst = "busy", t, None, False
                actions = ["start", "select_pre_contact"] + (["select_hand_busy"] if valid else [])
        elif t - busy_since >= 10000:
            phase, busy_since, rest_since, burst = "idle", None, None, False
            log.append({"t_ms": t, "actions": ["gap", "abort"], "phase": phase})
            continue
        if phase != "idle":
            if busy is True:
                phase, rest_since = "busy", None
                if motion is True and valid and not burst:
                    actions.append("select_carry")
                    burst = True
            elif busy is False and motion is False and valid and t - busy_since >= 200:
                if rest_since is None:
                    phase, rest_since = "settling", t
                    actions.append("select_release")
                elif t - rest_since >= 600:
                    actions += ["select_rest", "finish"]
                    phase, busy_since, rest_since, burst = "idle", None, None, False
            else:
                phase, rest_since = "busy", None
        log.append({"t_ms": t, "actions": actions, "phase": phase})
    return log


def random_trace(rng: random.Random):
    samples, t = [], rng.randint(0, 500)
    for _ in range(rng.randint(1, 40)):
        sample = {"t_ms": t, "busy": rng.choice([True, True, True, False, False, None]),
                  "motion": rng.choice([True, False, False, None])}
        if rng.random() < 0.85:
            sample["frame_valid"] = rng.random() < 0.8
        if rng.random() < 0.05:
            sample["gap"] = True
        samples.append(sample)
        t += rng.choice([1, 50, 100, 100, 100, 250, 700, 3000])
    return samples


class ToolingTests(unittest.TestCase):
    def test_node_and_entry_points_exist(self):
        self.assertIsNotNone(NODE, "node is not on PATH: the browser controller port cannot be verified (FAIL, not skip)")
        self.assertTrue(NODE_REPLAY.is_file(), NODE_REPLAY)
        self.assertTrue((ROOT / "perception" / "episode_controller.py").is_file())

    def test_no_runtime_dependency_was_added(self):
        # CP2 acceptance: no new npm or pip dependency at runtime. The Node entry is
        # plain ESM over node:fs; nothing under phone/ declares a package.
        for forbidden in ("package.json", "package-lock.json", "node_modules"):
            self.assertFalse((ROOT / "phone" / forbidden).exists(), forbidden)
            self.assertFalse((ROOT / forbidden).exists(), forbidden)
        imports = re.findall(r"""^\s*import\s.*?from\s+['"]([^'"]+)['"]""", NODE_REPLAY.read_text(encoding="utf-8"), re.M)
        self.assertEqual(sorted(imports), ["./controller.js", "node:fs"], imports)
        for name in ("motion.js", "hand-busy.js", "controller.js", "hand-worker.js"):
            text = (ROOT / "phone" / "assets" / name).read_text(encoding="utf-8")
            for found in re.findall(r"""(?:import\s.*?from\s+|importScripts\(|import\()\s*['"]([^'"]+)['"]""", text):
                self.assertTrue(found.startswith("./"), f"{name} loads {found!r}, which is not a sibling module")
        for requirements in (ROOT / "server" / "requirements.txt", ROOT / "perception" / "requirements.txt"):
            text = requirements.read_text(encoding="utf-8").lower()
            for forbidden in ("mediapipe", "tasks-vision"):
                self.assertNotIn(forbidden, text, f"{requirements.name} gained {forbidden}")

    def test_fixture_files_carry_the_tester_basis(self):
        traces = sorted(FIXTURES.glob("trace_*.json"))
        self.assertGreaterEqual(len(traces), 7, "the seven planned golden traces plus boundaries")
        names = {path.stem for path in traces}
        for required in ("trace_fast_put_down", "trace_long_carry", "trace_mid_episode_gap", "trace_short_busy_no_release",
                         "trace_missing_measurements_never_settle", "trace_max_episode_timeout", "trace_back_to_back"):
            self.assertIn(required, names)
        for path in traces + [FIXTURES / "motion_goldens.json", FIXTURES / "hand_goldens.json"]:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data.get("basis"), BASIS, path.name)
        for path in traces:
            data = json.loads(path.read_text(encoding="utf-8"))
            for sample in data["samples"]:
                self.assertIs(type(sample["t_ms"]), int, f"{path.name}: golden t_ms must be an integer literal")
            self.assertEqual([s["t_ms"] for s in data["samples"]], [e["t_ms"] for e in data["expected"]], path.name)


class GoldenTraceEquivalenceTests(unittest.TestCase):
    """Every golden trace: both CLIs agree, and both match the hand-authored expectation."""

    def check_trace(self, path):
        data = json.loads(path.read_text(encoding="utf-8"))
        py, js = run_python(path), run_node(path)
        self.assertEqual(py.returncode, 0, f"{path.name}: python stderr={py.stderr!r}")
        self.assertEqual(js.returncode, 0, f"{path.name}: node stderr={js.stderr!r}")
        self.assertEqual(py.stderr, b"", path.name)
        self.assertEqual(js.stderr, b"", path.name)
        self.assertEqual(py.stdout, js.stdout, f"{path.name}: the two controllers printed different logs")
        self.assertTrue(py.stdout.endswith(b"\n") and not py.stdout.endswith(b"\n\n"), "exactly one trailing newline")
        self.assertEqual(py.stdout, json.dumps(data["expected"], sort_keys=True, separators=(",", ":")).encode() + b"\n",
                         f"{path.name}: machine output differs from the contract expectation")
        # The in-process reference agrees with its own CLI (the CLI adds nothing).
        from perception.episode_controller import replay
        self.assertEqual(replay(data["samples"]), data["expected"], path.name)
        return data

    def test_fast_put_down(self):
        data = self.check_trace(FIXTURES / "trace_fast_put_down.json")
        actions = [a for record in data["expected"] for a in record["actions"]]
        self.assertEqual(actions, ["start", "select_pre_contact", "select_hand_busy", "select_carry",
                                   "select_release", "select_rest", "finish"])

    def test_long_carry_selects_exactly_one_carry(self):
        data = self.check_trace(FIXTURES / "trace_long_carry.json")
        actions = [a for record in data["expected"] for a in record["actions"]]
        self.assertEqual(actions.count("select_carry"), 1)
        self.assertEqual(actions.count("finish"), 1)
        busy_span = [r["t_ms"] for r in data["expected"] if r["phase"] == "busy"]
        self.assertGreater(busy_span[-1] - busy_span[0], 2000, "the carry lasts more than 2 s")

    def test_mid_episode_gap_aborts_without_rest(self):
        data = self.check_trace(FIXTURES / "trace_mid_episode_gap.json")
        records = {r["t_ms"]: r for r in data["expected"]}
        self.assertEqual(records[300]["actions"], ["gap", "abort"])
        self.assertEqual(records[300]["phase"], "idle")
        self.assertEqual(records[1400]["actions"], ["gap"])
        self.assertEqual(sum(r["actions"].count("finish") for r in data["expected"]), 1)

    def test_short_busy_never_releases_before_busy_min(self):
        data = self.check_trace(FIXTURES / "trace_short_busy_no_release.json")
        actions = [a for record in data["expected"] for a in record["actions"]]
        self.assertNotIn("select_release", actions)
        self.assertNotIn("select_rest", actions)
        self.assertNotIn("finish", actions)

    def test_missing_measurements_never_settle(self):
        data = self.check_trace(FIXTURES / "trace_missing_measurements_never_settle.json")
        for record, sample in zip(data["expected"], data["samples"]):
            if sample.get("busy") is None or sample.get("motion") is None or not sample.get("frame_valid", False):
                self.assertNotIn("select_release", record["actions"], record)
                self.assertNotIn("finish", record["actions"], record)
                self.assertNotIn("select_carry", record["actions"], record)
                self.assertNotIn("select_hand_busy", record["actions"], record)

    def test_max_episode_timeout(self):
        data = self.check_trace(FIXTURES / "trace_max_episode_timeout.json")
        records = {r["t_ms"]: r for r in data["expected"]}
        self.assertEqual(records[10099]["actions"], [])
        self.assertEqual(records[10100]["actions"], ["gap", "abort"])
        self.assertEqual(records[10200]["actions"][0], "start")

    def test_two_back_to_back_episodes(self):
        data = self.check_trace(FIXTURES / "trace_back_to_back.json")
        actions = [a for record in data["expected"] for a in record["actions"]]
        self.assertEqual(actions.count("start"), 2)
        self.assertEqual(actions.count("finish"), 2)
        self.assertEqual(actions.count("select_carry"), 2)

    def test_boundaries_and_optional_fields(self):
        self.check_trace(FIXTURES / "trace_boundaries_and_defaults.json")


class InvalidTraceTests(unittest.TestCase):
    def test_invalid_traces_fail_identically(self):
        paths = sorted(FIXTURES.glob("invalid_*.json"))
        self.assertGreaterEqual(len(paths), 12)
        for path in paths:
            with self.subTest(trace=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                py, js = run_python(path), run_node(path)
                self.assertEqual(py.returncode, 1, f"{path.name}: python {py.stdout!r} {py.stderr!r}")
                self.assertEqual(js.returncode, 1, f"{path.name}: node {js.stdout!r} {js.stderr!r}")
                self.assertEqual(py.stdout, b"", path.name)
                self.assertEqual(js.stdout, b"", path.name)
                self.assertTrue(py.stderr.startswith(b"error: "), py.stderr)
                self.assertEqual(py.stderr, js.stderr, f"{path.name}: the two CLIs gave different reasons")
                if isinstance(data, dict) and "expected_stderr" in data:
                    self.assertEqual(py.stderr.decode(), data["expected_stderr"], path.name)
                    self.assertEqual(py.returncode, data["expected_exit"])

    def test_integral_float_time_literal_gets_the_same_verdict_from_both(self):
        # The contract says t_ms is an int. "100.0" is a float literal in JSON text
        # even though its value is integral; both CLIs must give the same verdict.
        with tempfile.TemporaryDirectory(prefix="pam-cp2-") as temp:
            path = Path(temp) / "integral_float.json"
            path.write_text('{"samples":[{"t_ms":0,"busy":false,"motion":false,"frame_valid":true},'
                            '{"t_ms":100.0,"busy":true,"motion":false,"frame_valid":true}]}', encoding="utf-8")
            py, js = run_python(path), run_node(path)
            self.assertEqual((py.returncode, py.stdout, py.stderr), (js.returncode, js.stdout, js.stderr),
                             "python and node disagree on an integral float t_ms literal (100.0)")
            # Coordinator ruling (2026-10-08): accepted at the trace boundary, normalised to 100.
            self.assertEqual(py.returncode, 0, py.stderr)
            self.assertEqual(json.loads(py.stdout)[1]["t_ms"], 100)
            from perception.episode_controller import replay, step
            self.assertEqual(replay([{"t_ms": 100.0, "busy": True, "motion": False, "frame_valid": True}])[0]["t_ms"], 100)
            with self.assertRaises(ValueError):
                step(None, {"t_ms": 100.0, "busy": True, "motion": False, "frame_valid": True})  # step() itself stays strict

    def test_usage_and_missing_file_exit_codes(self):
        self.assertEqual(subprocess.run([sys.executable, "-B", "-m", "perception.episode_controller"], cwd=str(ROOT),
                                        env=clean_env(), capture_output=True, timeout=TIMEOUT).returncode, 2)
        self.assertEqual(subprocess.run([NODE, str(NODE_REPLAY)], cwd=str(ROOT), env=clean_env(),
                                        capture_output=True, timeout=TIMEOUT).returncode, 2)
        with tempfile.TemporaryDirectory(prefix="pam-cp2-") as temp:
            missing = Path(temp) / "missing.json"
            py, js = run_python(missing), run_node(missing)
            self.assertEqual((py.returncode, py.stdout, py.stderr), (1, b"", b"error: trace file not found\n"))
            self.assertEqual((js.returncode, js.stdout, js.stderr), (1, b"", b"error: trace file not found\n"))
            broken = Path(temp) / "broken.json"
            broken.write_text("{not json", encoding="utf-8")
            py, js = run_python(broken), run_node(broken)
            self.assertEqual((py.returncode, py.stdout, py.stderr), (1, b"", b"error: trace file is not valid JSON\n"))
            self.assertEqual((js.returncode, js.stdout, js.stderr), (1, b"", b"error: trace file is not valid JSON\n"))
            binary = Path(temp) / "binary.json"
            binary.write_bytes(b"\xff\xfe\x00")
            py, js = run_python(binary), run_node(binary)
            self.assertEqual((py.returncode, py.stderr), (1, b"error: trace file is not valid JSON\n"))
            self.assertEqual((js.returncode, js.stderr), (1, b"error: trace file is not valid JSON\n"))


class RandomTracePropertyTests(unittest.TestCase):
    def test_100_random_valid_traces_are_identical_across_languages(self):
        from perception.episode_controller import replay
        rng = random.Random(20261008)
        with tempfile.TemporaryDirectory(prefix="pam-cp2-random-") as temp:
            for index in range(100):
                samples = random_trace(rng)
                path = Path(temp) / f"random_{index:03d}.json"
                path.write_text(json.dumps({"samples": samples}), encoding="utf-8")
                py, js = run_python(path), run_node(path)
                with self.subTest(trace=index):
                    self.assertEqual((py.returncode, py.stderr), (0, b""), f"trace {index}: {py.stderr!r} {samples}")
                    self.assertEqual((js.returncode, js.stderr), (0, b""), f"trace {index}: {js.stderr!r} {samples}")
                    self.assertEqual(py.stdout, js.stdout, f"trace {index} differs across languages: {samples}")
                    self.assertEqual(json.loads(py.stdout), replay(samples))
                    self.assertEqual(json.loads(py.stdout), oracle_replay(samples),
                                     f"trace {index}: machine disagrees with the contract restatement: {samples}")


NODE_GOLDEN_SCRIPT = r"""
import { readFileSync } from 'node:fs';
import { motionEnergy, motionStep, MOTION_ON, MOTION_OFF, boxBlur3 } from %(motion)s;
import { handBusy, handMetrics, CURL_RATIO, LOWER_FRAME_Y, LOWER_FRAME_MIN_AREA, DEGENERATE_REFERENCE } from %(hand)s;
const motion = JSON.parse(readFileSync(%(motion_json)s, 'utf8'));
const hands = JSON.parse(readFileSync(%(hand_json)s, 'utf8'));
const out = { constants: { MOTION_ON, MOTION_OFF, CURL_RATIO, LOWER_FRAME_Y, LOWER_FRAME_MIN_AREA, DEGENERATE_REFERENCE },
  motion: [], motion_invalid: [], hysteresis: [], hands: [], hands_invalid: [], random_motion: [] };
for (const c of motion.cases) {
  const r = motionEnergy(Uint8Array.from(c.prev), Uint8Array.from(c.next), c.width, c.height);
  const rows = []; for (let y = 0; y < c.height; y++) rows.push(c.next.slice(y * c.width, (y + 1) * c.width));
  const viaRows = motionEnergy(c.prev, rows, c.width, c.height);
  out.motion.push({ name: c.name, energy: r.energy, moving: r.moving, same_via_plain_arrays: viaRows.energy === r.energy && viaRows.moving === r.moving,
    blur_next: Array.from(boxBlur3(Uint8Array.from(c.next), c.width, c.height)) });
}
for (const c of motion.invalid) {
  try { motionEnergy(c.prev, c.next, c.width, c.height); out.motion_invalid.push({ name: c.name, threw: false }); }
  catch (e) { out.motion_invalid.push({ name: c.name, threw: true, message: e.message }); }
}
let state = null;
for (const energy of motion.hysteresis.energies) { let moving; [state, moving] = motionStep(state, energy); out.hysteresis.push(moving); }
for (const c of hands.cases) {
  const verdict = handBusy(c.hands);
  const entry = { name: c.name, verdict };
  if (c.metrics) entry.metrics = handMetrics(c.hands[0]);
  out.hands.push(entry);
}
for (const c of hands.invalid) {
  try { handBusy(c.hands); out.hands_invalid.push({ name: c.name, threw: false }); }
  catch (e) { out.hands_invalid.push({ name: c.name, threw: true, message: e.message }); }
}
const random = JSON.parse(readFileSync(%(random_json)s, 'utf8'));
for (const c of random) { const r = motionEnergy(Uint8Array.from(c.prev), Uint8Array.from(c.next), c.width, c.height); out.random_motion.push(r.energy); }
process.stdout.write(JSON.stringify(out));
"""


NODE_ADAPTER_SCRIPT = r"""
import { createAutomaticAdapter, NO_WORKER_REASON } from %(controller)s;
import { readFileSync } from 'node:fs';
const hands = JSON.parse(readFileSync(%(hand_json)s, 'utf8'));
const byName = Object.fromEntries(hands.cases.map(c => [c.name, c.hands]));
const out = { steps: [] };
class FakeWorker {
  constructor() { this.listeners = { message: [], error: [] }; this.posted = []; this.terminated = 0; this.replies = []; }
  addEventListener(type, fn) { this.listeners[type].push(fn); }
  removeEventListener(type, fn) { this.listeners[type] = this.listeners[type].filter(f => f !== fn); }
  postMessage(message, transfer) {
    this.posted.push({ type: message.type, t_ms: message.t_ms ?? null, base: message.base ?? null, transferred: Array.isArray(transfer) && transfer.includes(message.bitmap) });
    if (message.type === 'frame') { message.bitmap.close(); }
    const reply = this.replies.shift();
    if (reply) setTimeout(() => this.emit(reply(message)), 0);
  }
  emit(data) { for (const fn of [...this.listeners.message]) fn({ data }); }
  terminate() { this.terminated++; }
}
const bitmap = () => { const b = { closed: 0, close() { this.closed++; } }; return b; };
const gray = fill => ({ data: new Uint8Array(12).fill(fill), width: 4, height: 3 });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const noWorker = createAutomaticAdapter({});
out.no_worker = { enabled: noWorker.enabled, reason: noWorker.reason, analyze: noWorker.analyze === null, same_as_constant: noWorker.reason === NO_WORKER_REASON };
const worker = new FakeWorker();
const changes = [];
worker.replies.push(m => ({ type: 'ready', version: 'fake-0.0', delegate: 'CPU', runtime: 'fake' }));
const adapter = createAutomaticAdapter({ worker, timeoutMs: 60, changed: a => changes.push({ enabled: a.enabled, state: a.state, reason: a.reason }) });
out.before_ready = { enabled: adapter.enabled, state: adapter.state, analyze: adapter.analyze === null };
await sleep(5);
out.after_ready = { enabled: adapter.enabled, state: adapter.state, version: adapter.version, delegate: adapter.delegate, reason: adapter.reason, analyze: typeof adapter.analyze };
// 1. first frame: no hand, no previous gray
worker.replies.push(m => ({ type: 'hands', t_ms: m.t_ms, hands: [], infer_ms: 1 }));
let b = bitmap();
let r = await adapter.analyze(100, gray(10), b);
out.steps.push({ step: 'no_hand', busy: r.busy, motion: r.motion, frame_valid: r.frame_valid, hands: r.hands, basis: r.basis, closed: b.closed, energy: r.energy });
// 2. identical gray, lower-frame hand
worker.replies.push(m => ({ type: 'hands', t_ms: m.t_ms, hands: byName.open_hand_lower_frame, infer_ms: 2 }));
b = bitmap();
r = await adapter.analyze(200, gray(10), b);
out.steps.push({ step: 'busy_hand', busy: r.busy, motion: r.motion, frame_valid: r.frame_valid, hands: Array.isArray(r.hands) ? r.hands.length : r.hands, basis: r.basis, closed: b.closed, energy: r.energy, infer_ms: r.infer_ms });
// 3. changed gray (black -> white), no reply within timeout: frame invalid, busy is the latest value
b = bitmap();
r = await adapter.analyze(300, gray(255), b);
out.steps.push({ step: 'timeout', busy: r.busy, motion: r.motion, frame_valid: r.frame_valid, hands: r.hands, basis: r.basis, closed: b.closed, energy: r.energy });
// 4. the late reply for 300 arrives: ignored for settling but not an error; next frame is fine
worker.emit({ type: 'hands', t_ms: 300, hands: byName.open_hand_high, infer_ms: 1 });
worker.replies.push(m => ({ type: 'hands', t_ms: m.t_ms, hands: byName.open_hand_high, infer_ms: 1 }));
b = bitmap();
r = await adapter.analyze(400, gray(255), b);
out.steps.push({ step: 'open_high', busy: r.busy, motion: r.motion, frame_valid: r.frame_valid, basis: r.basis, closed: b.closed, energy: r.energy });
// 5. malformed hands from the worker: not a verdict, frame invalid, no throw
worker.replies.push(m => ({ type: 'hands', t_ms: m.t_ms, hands: [{ landmarks: [] }], infer_ms: 1 }));
b = bitmap();
r = await adapter.analyze(500, gray(255), b);
out.steps.push({ step: 'malformed', busy: r.busy, frame_valid: r.frame_valid, hands: r.hands, closed: b.closed });
// 6. unavailable report: disabled with the reason; a later analyze call is impossible (analyze is null)
worker.emit({ type: 'unavailable', reason: 'The hand model failed during analysis; automatic capture stopped.' });
out.after_unavailable = { enabled: adapter.enabled, state: adapter.state, reason: adapter.reason, analyze: adapter.analyze === null };
adapter.close();
out.closed = { terminated: worker.terminated, posted: worker.posted, changes, listeners: worker.listeners.message.length };
process.stdout.write(JSON.stringify(out));
"""


def random_motion_cases(count=25, seed=8):
    rng = random.Random(seed)
    cases = []
    for _ in range(count):
        width, height = rng.randint(1, 12), rng.randint(1, 9)
        n = width * height
        prev = [rng.randint(0, 255) for _ in range(n)]
        nxt = [min(255, max(0, p + rng.randint(-20, 20))) if rng.random() < 0.7 else rng.randint(0, 255) for p in prev]
        cases.append({"width": width, "height": height, "prev": prev, "next": nxt})
    return cases


class AutomaticAdapterProtocolTests(unittest.TestCase):
    """createAutomaticAdapter (phone/assets/controller.js) against a scripted fake
    worker in Node: the worker protocol, missing-measurement handling and
    bitmap ownership, independent of any browser."""
    def test_adapter_protocol_in_node(self):
        self.assertIsNotNone(NODE, "node is not on PATH (FAIL, not skip)")
        with tempfile.TemporaryDirectory(prefix="pam-cp2-adapter-") as temp:
            script = NODE_ADAPTER_SCRIPT % {"controller": json.dumps((ROOT / "phone" / "assets" / "controller.js").as_uri()),
                                            "hand_json": json.dumps(str(FIXTURES / "hand_goldens.json"))}
            path = Path(temp) / "adapter.mjs"
            path.write_text(script, encoding="utf-8")
            result = subprocess.run([NODE, str(path)], cwd=str(ROOT), env=clean_env(), capture_output=True, timeout=TIMEOUT, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertEqual(out["no_worker"], {"enabled": False, "reason": out["no_worker"]["reason"], "analyze": True, "same_as_constant": True})
        self.assertEqual(out["before_ready"], {"enabled": False, "state": "starting", "analyze": True})
        self.assertEqual(out["after_ready"]["enabled"], True)
        self.assertEqual(out["after_ready"]["state"], "ready")
        self.assertEqual(out["after_ready"]["version"], "fake-0.0")
        self.assertEqual(out["after_ready"]["delegate"], "CPU")
        self.assertIsNone(out["after_ready"]["reason"])
        self.assertEqual(out["after_ready"]["analyze"], "function")
        steps = {step["step"]: step for step in out["steps"]}
        self.assertEqual(steps["no_hand"], {"step": "no_hand", "busy": None, "motion": None, "frame_valid": True, "hands": [],
                                            "basis": "no hand", "closed": 1, "energy": None})
        self.assertEqual((steps["busy_hand"]["busy"], steps["busy_hand"]["motion"], steps["busy_hand"]["frame_valid"],
                          steps["busy_hand"]["hands"], steps["busy_hand"]["basis"], steps["busy_hand"]["closed"],
                          steps["busy_hand"]["energy"], steps["busy_hand"]["infer_ms"]),
                         (True, False, True, 1, "lower-frame", 1, 0, 2))
        timeout = steps["timeout"]
        self.assertEqual((timeout["frame_valid"], timeout["hands"], timeout["busy"], timeout["motion"], timeout["energy"], timeout["closed"]),
                         (False, None, True, True, 0.960784, 1), "a late landmark result invalidates the frame; busy is the latest verdict, motion still measured (245/255)")
        self.assertIn("no landmark result for this frame within 60 ms", timeout["basis"])
        self.assertEqual((steps["open_high"]["busy"], steps["open_high"]["motion"], steps["open_high"]["frame_valid"], steps["open_high"]["basis"], steps["open_high"]["energy"]),
                         (False, False, True, "open hand", 0), "identical white frames: energy 0 is below MOTION_OFF, so moving turns off")
        self.assertEqual(steps["malformed"], {"step": "malformed", "busy": False, "frame_valid": False, "hands": None, "closed": 1})
        self.assertEqual(out["after_unavailable"], {"enabled": False, "state": "unavailable",
                                                    "reason": "The hand model failed during analysis; automatic capture stopped.", "analyze": True})
        self.assertEqual(out["closed"]["terminated"], 1)
        self.assertEqual(out["closed"]["listeners"], 0, "close() removes the listeners")
        posted = out["closed"]["posted"]
        self.assertEqual(posted[0], {"type": "init", "t_ms": None, "base": "/assets/models/", "transferred": False})
        self.assertEqual([p["t_ms"] for p in posted[1:]], [100, 200, 300, 400, 500])
        self.assertTrue(all(p["transferred"] for p in posted[1:]), "every frame bitmap is transferred to the worker")
        self.assertEqual([c["state"] for c in out["closed"]["changes"]], ["ready", "unavailable"])


class MotionAndHandGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.motion = load("motion_goldens.json")
        cls.hands = load("hand_goldens.json")
        cls.random_cases = random_motion_cases()
        cls.node = None
        if NODE is None:
            return
        cls.temp = tempfile.TemporaryDirectory(prefix="pam-cp2-node-")
        temp = Path(cls.temp.name)
        (temp / "random.json").write_text(json.dumps(cls.random_cases), encoding="utf-8")
        script = NODE_GOLDEN_SCRIPT % {
            "motion": json.dumps((ROOT / "phone" / "assets" / "motion.js").as_uri()),
            "hand": json.dumps((ROOT / "phone" / "assets" / "hand-busy.js").as_uri()),
            "motion_json": json.dumps(str(FIXTURES / "motion_goldens.json")),
            "hand_json": json.dumps(str(FIXTURES / "hand_goldens.json")),
            "random_json": json.dumps(str(temp / "random.json"))}
        (temp / "goldens.mjs").write_text(script, encoding="utf-8")
        result = subprocess.run([NODE, str(temp / "goldens.mjs")], cwd=str(ROOT), env=clean_env(),
                                capture_output=True, timeout=TIMEOUT, text=True)
        cls.node_result = result
        if result.returncode == 0:
            cls.node = json.loads(result.stdout)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "temp", None):
            cls.temp.cleanup()

    def node_output(self):
        self.assertIsNotNone(NODE, "node is not on PATH; the browser modules cannot be verified (FAIL, not skip)")
        self.assertIsNotNone(self.node, f"node golden script failed: {getattr(self, 'node_result', None) and self.node_result.stderr}")
        return self.node

    def test_constants_are_mirrored(self):
        from perception import motion, hand_busy
        node = self.node_output()
        self.assertEqual((motion.MOTION_ON, motion.MOTION_OFF), (0.035, 0.015))
        self.assertEqual((hand_busy.CURL_RATIO, hand_busy.LOWER_FRAME_Y, hand_busy.LOWER_FRAME_MIN_AREA, hand_busy.DEGENERATE_REFERENCE),
                         (0.55, 0.40, 0.02, 1e-6))
        self.assertEqual(node["constants"], {"MOTION_ON": 0.035, "MOTION_OFF": 0.015, "CURL_RATIO": 0.55,
                                             "LOWER_FRAME_Y": 0.40, "LOWER_FRAME_MIN_AREA": 0.02, "DEGENERATE_REFERENCE": 1e-6})

    def test_motion_goldens_python(self):
        from perception.motion import motion_energy, motion_step
        import numpy as np
        for case in self.motion["cases"]:
            with self.subTest(case=case["name"]):
                oracle = oracle_energy(case["prev"], case["next"], case["width"], case["height"])
                self.assertEqual(oracle, case["energy"], "the hand-worked golden and the plain-Python oracle disagree")
                for prev, nxt in ((case["prev"], case["next"]), (bytes(case["prev"]), bytes(case["next"])),
                                  (np.array(case["prev"], dtype=np.uint8).reshape(case["height"], case["width"]),
                                   np.array(case["next"], dtype=np.uint8).reshape(case["height"], case["width"]))):
                    result = motion_energy(prev, nxt, case["width"], case["height"])
                    self.assertEqual(result["energy"], case["energy"], case["name"])
                    self.assertIs(result["moving"], case["moving"], case["name"])
        state, flags = None, []
        for energy in self.motion["hysteresis"]["energies"]:
            state, moving = motion_step(state, energy)
            flags.append(moving)
        self.assertEqual(flags, self.motion["hysteresis"]["moving"])
        for case in self.motion["invalid"]:
            with self.subTest(invalid=case["name"]), self.assertRaises(ValueError):
                motion_energy(case["prev"], case["next"], case["width"], case["height"])
        with self.assertRaises(ValueError):
            motion_step({"moving": "yes"}, 0.1)
        with self.assertRaises(ValueError):
            motion_step(None, float("nan"))

    def test_motion_goldens_node(self):
        node = self.node_output()
        by_name = {entry["name"]: entry for entry in node["motion"]}
        for case in self.motion["cases"]:
            with self.subTest(case=case["name"]):
                entry = by_name[case["name"]]
                self.assertEqual(entry["energy"], case["energy"])
                self.assertIs(entry["moving"], case["moving"])
                self.assertTrue(entry["same_via_plain_arrays"], "plain arrays and typed arrays must agree")
                self.assertEqual(entry["blur_next"], oracle_blur(case["next"], case["width"], case["height"]))
        self.assertEqual(node["hysteresis"], self.motion["hysteresis"]["moving"])
        for entry in node["motion_invalid"]:
            self.assertTrue(entry["threw"], entry)

    def test_random_frames_identical_in_python_node_and_oracle(self):
        from perception.motion import motion_energy
        node = self.node_output()
        self.assertEqual(len(node["random_motion"]), len(self.random_cases))
        for case, js_energy in zip(self.random_cases, node["random_motion"]):
            py_energy = motion_energy(case["prev"], case["next"], case["width"], case["height"])["energy"]
            self.assertEqual(py_energy, oracle_energy(case["prev"], case["next"], case["width"], case["height"]))
            self.assertEqual(py_energy, js_energy, case)

    def test_hand_goldens_python(self):
        from perception.hand_busy import hand_busy, hand_metrics
        for case in self.hands["cases"]:
            with self.subTest(case=case["name"]):
                self.assertEqual(hand_busy(case["hands"]), case["expected"])
                if "metrics" in case:
                    metrics = hand_metrics(case["hands"][0])
                    for key, value in case["metrics"].items():
                        if isinstance(value, float):
                            self.assertAlmostEqual(metrics[key], value, places=12, msg=f"{case['name']}.{key}")
                        elif isinstance(value, list):
                            for a, b in zip(metrics[key], value):
                                self.assertAlmostEqual(a, b, places=12, msg=f"{case['name']}.{key}")
                        else:
                            self.assertEqual(metrics[key], value, f"{case['name']}.{key}")
        for case in self.hands["invalid"]:
            with self.subTest(invalid=case["name"]), self.assertRaisesRegex(ValueError, case["message"]):
                hand_busy(case["hands"])

    def test_hand_goldens_node(self):
        node = self.node_output()
        by_name = {entry["name"]: entry for entry in node["hands"]}
        for case in self.hands["cases"]:
            with self.subTest(case=case["name"]):
                self.assertEqual(by_name[case["name"]]["verdict"], case["expected"])
        by_name = {entry["name"]: entry for entry in node["hands_invalid"]}
        for case in self.hands["invalid"]:
            with self.subTest(invalid=case["name"]):
                self.assertTrue(by_name[case["name"]]["threw"], case["name"])
                self.assertEqual(by_name[case["name"]]["message"], case["message"])

    def test_hand_metrics_bit_identical_across_languages(self):
        from perception.hand_busy import hand_metrics
        node = self.node_output()
        by_name = {entry["name"]: entry for entry in node["hands"]}
        for case in self.hands["cases"]:
            if "metrics" not in case:
                continue
            with self.subTest(case=case["name"]):
                py, js = hand_metrics(case["hands"][0]), by_name[case["name"]]["metrics"]
                self.assertEqual(py["reference"], js["reference"])
                self.assertEqual(py["palm_centre"], js["palm_centre"])
                self.assertEqual(py["curl_ratio"], js["curl_ratio"])
                self.assertEqual(py["bbox_centre_y"], js["bbox_centre_y"])
                self.assertEqual(py["bbox_area"], js["bbox_area"])

    def test_hand_verdict_matches_rule_restatement(self):
        # Independent restatement of the heuristic for every golden: largest box, then
        # curled OR lower-frame, computed with plain math from the fixture coordinates.
        from perception.hand_busy import hand_busy
        for case in self.hands["cases"]:
            hands = case["hands"]
            if not hands:
                continue
            chosen = max(hands, key=lambda h: (h["hand_bbox"][2] - h["hand_bbox"][0]) * (h["hand_bbox"][3] - h["hand_bbox"][1]))
            first_max = [h for h in hands if (h["hand_bbox"][2] - h["hand_bbox"][0]) * (h["hand_bbox"][3] - h["hand_bbox"][1])
                         == (chosen["hand_bbox"][2] - chosen["hand_bbox"][0]) * (chosen["hand_bbox"][3] - chosen["hand_bbox"][1])][0]
            pts = [(p["x"], p["y"]) for p in first_max["landmarks"]]
            palm = (sum(pts[i][0] for i in (0, 5, 9, 13, 17)) / 5, sum(pts[i][1] for i in (0, 5, 9, 13, 17)) / 5)
            reference = math.sqrt((pts[0][0] - pts[9][0]) ** 2 + (pts[0][1] - pts[9][1]) ** 2)
            x1, y1, x2, y2 = first_max["hand_bbox"]
            if reference < 1e-6:
                expected = {"present": True, "busy": None, "basis": "degenerate hand"}
            else:
                curl = sum(math.sqrt((pts[i][0] - palm[0]) ** 2 + (pts[i][1] - palm[1]) ** 2) / reference for i in (4, 8, 12, 16, 20)) / 5
                curled, lower = curl < 0.55, (y1 + y2) / 2 > 0.40 and (x2 - x1) * (y2 - y1) >= 0.02
                basis = "curled+lower-frame" if curled and lower else "curled" if curled else "lower-frame" if lower else "open hand"
                expected = {"present": True, "busy": curled or lower, "basis": basis}
            with self.subTest(case=case["name"]):
                self.assertEqual(expected, case["expected"], "fixture expectation disagrees with the rule restatement")
                self.assertEqual(hand_busy(hands), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
