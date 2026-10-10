"""CP5 server self-check: the telemetry and coverage routes, the health coverage,
the public notices page with its conditions, the chat Answer DTO and the notices
sync script, against a temporary database. One line per step; exit status 1
when any expectation fails.

    python3 -B scripts/cp5_selfcheck.py

Nothing here touches a real database, credential or environment file: the app is
built with an explicit temporary path, PIN and clock, the processor is an in-script
injection (one synthetic trusted placement, fixture-only calibration), the model
inventory it provisions is a synthetic manifest in the temporary directory, and no
network is used. Numbers here are software-correctness checks on synthetic input,
never a measurement of a camera or a model.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ORIGIN = "https://selfcheck.local"
PIN = "self-check-pin-0000"
WIDTH, HEIGHT = 160, 120
# A fixed app clock: 2026-10-10T12:00:00Z. Every window below is placed relative to it.
ANCHOR_S = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc).timestamp()
TODAY = "2026-10-10"
YESTERDAY = "2026-10-09"
COVERAGE_KEYS = ("camera_on_ms", "gap_ms", "episodes", "packets", "idle_sent", "idle_dropped", "sessions")
ANSWER_KEYS = {"shape", "text", "members", "reference_image", "target_indicated", "capture_time_ms",
               "identity_status", "location_status", "room", "index_pending", "basis"}
CUTE_URL = "purl.stanford.edu/gj714cj0414"
failures = []


def jpeg_b64(x=None):
    y, xx = np.indices((HEIGHT, WIDTH))
    gray = (35 + ((xx // 8 + y // 8) % 2) * 50).astype(np.uint8)
    image = np.repeat(gray[:, :, None], 3, axis=2)
    if x is not None:
        image[40:60, x:x + 20] = (30, 60, 230)
    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    assert ok
    return base64.b64encode(data.tobytes()).decode("ascii")


class Processor:
    """Trusted injection at the create_app boundary: every packet yields one
    placed, trusted observation of a synthetic block (fixture-only calibration)."""
    def __call__(self, packet):
        from perception.localizer import LocalObservation
        rest = packet.keyframes[-1]
        return [LocalObservation(frame_id=rest.frame_id, bbox=[20.0, 40.0, 40.0, 60.0], label="self-check block",
                                 actor="wearer", outcome="placed_on_surface", continuity_id="self-check-1",
                                 identity_state="trusted", location_text="self-check table", confidence=1.0,
                                 confidence_basis="SELF-CHECK ONLY: synthetic frame",
                                 calibration={"approved": True, "fixture_only": True, "calibration_id": "self-check-1"})]


def episode(device, session, wall_ms):
    eid = str(uuid.uuid4())
    return {"schema_version": 1, "episode_id": eid, "device_id": device, "session_id": session,
            "t_start_ms": 1000, "t_end_ms": 2200, "clock_anchor": {"mono_ms": 0, "wall_ms": wall_ms},
            "capture": {"width": WIDTH, "height": HEIGHT}, "analysis": {"width": WIDTH // 2, "height": HEIGHT // 2},
            "keyframes": [{"frame_id": eid + "-before", "t_ms": 1000, "role": "pre_contact", "jpeg_b64": jpeg_b64()},
                          {"frame_id": eid + "-rest", "t_ms": 2200, "role": "rest", "jpeg_b64": jpeg_b64(20)}],
            "carry_burst": [], "landmarks": [], "gaps": [], "outcome_hint": "released", "capture_mode": "manual"}


def telemetry(device, session, *, wall_ms, window_ms=60000, **counters):
    """One window ending at wall_ms (the anchor carries the wall time; t_ms = mono_ms)."""
    base = {name: 0 for name in ("frames_captured", "frames_analysed", "frames_skipped_busy", "frames_dropped_backpressure",
                                 "landmark_results", "landmark_timeouts", "episodes_started", "episodes_finished",
                                 "episodes_aborted", "packets_sent", "packets_acked", "idle_sent", "idle_dropped", "gaps",
                                 "gap_ms", "bytes_sent")}
    base.update(frames_captured=600, frames_analysed=300)
    base.update(counters)
    return {"schema_version": 1, "device_id": device, "session_id": session, "t_ms": 60000,
            "clock_anchor": {"mono_ms": 60000, "wall_ms": wall_ms}, "window_ms": window_ms, "counters": base,
            "timing": {"fps_observed": 9.8, "infer_ms_p50": 21.0, "infer_ms_p95": 38.5, "tick_ms_p95": 110.0},
            "settings": {"width": WIDTH, "height": HEIGHT, "frame_rate": 30}}


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def step(name, response, status, code=None, check=None):
    body = None
    try:
        body = response.json()
    except ValueError:
        pass
    got_code = body.get("code") if isinstance(body, dict) else None
    ok = response.status_code == status and (code is None or got_code == code)
    detail = ""
    if ok and check is not None:
        try:
            detail = check(body if body is not None else response.text)
            if detail is None:
                detail = ""
            elif detail is not False:
                detail = f" {detail}"
            else:
                ok, detail = False, " (body check failed)"
        except Exception as exc:  # noqa: BLE001 - a failed check is a failed step
            ok, detail = False, f" (body check raised {type(exc).__name__}: {exc})"
    mark = "ok  " if ok else "FAIL"
    print(f"{mark} {name:<62} -> {response.status_code}{' ' + got_code if got_code else ''}{detail}")
    if not ok:
        failures.append(name)
    return body


def expect(name, condition, detail=""):
    print(f"{'ok  ' if condition else 'FAIL'} {name:<62}{(' ' + detail) if detail else ''}")
    if not condition:
        failures.append(name)


def coverage_of(body, **expected):
    got = {key: body[key] for key in expected}
    return f"{got}" if got == expected else False


def main():
    from server.memory_app import create_app, validate_notices
    with tempfile.TemporaryDirectory(prefix="pam-cp5-selfcheck-") as temp:
        root = Path(temp)
        db = root / "selfcheck.sqlite3"
        models = root / "models"
        models.mkdir()
        clock = {"now": ANCHOR_S}
        app = create_app(database_path=str(db), auth_pin=PIN, processor=Processor(), clock=lambda: clock["now"],
                         models_dir=models, server_models_dir=models)
        device, session_a, session_b = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
        anchor_ms = int(ANCHOR_S * 1000)
        with TestClient(app, base_url=ORIGIN, raise_server_exceptions=False) as client:
            anonymous = TestClient(app, base_url=ORIGIN, raise_server_exceptions=False)
            h = {"origin": ORIGIN, "content-type": "application/json"}
            print("== telemetry: auth, origin, validation, cap, ack, idempotence")
            window = telemetry(device, session_a, wall_ms=anchor_ms - 3600 * 1000, episodes_finished=1, packets_sent=1, idle_sent=2)
            step("telemetry without a session", anonymous.post("/api/telemetry", content=encode(window), headers=h), 401)
            step("login", client.post("/api/auth/login", json={"pin": PIN}, headers={"origin": ORIGIN}), 200)
            step("telemetry with a foreign origin", client.post("/api/telemetry", content=encode(window), headers={**h, "origin": "https://evil.invalid"}), 403)
            step("telemetry without an origin", client.post("/api/telemetry", content=encode(window), headers={"content-type": "application/json"}), 403)
            step("telemetry malformed JSON", client.post("/api/telemetry", content=b"{", headers=h), 400)
            step("telemetry unknown top-level key", client.post("/api/telemetry", content=encode({**window, "note": "kitchen"}), headers=h), 400)
            step("telemetry unknown counter", client.post("/api/telemetry", content=encode({**window, "counters": {**window["counters"], "frames_lost": 1}}), headers=h), 400)
            step("telemetry text where a number belongs", client.post("/api/telemetry", content=encode({**window, "counters": {**window["counters"], "gap_ms": "many"}}), headers=h), 400)
            step("telemetry negative window", client.post("/api/telemetry", content=encode({**window, "window_ms": -1}), headers=h), 400)
            future = telemetry(device, session_a, wall_ms=anchor_ms + 3600 * 1000)
            step("telemetry implausible (future) clock", client.post("/api/telemetry", content=encode(future), headers=h), 400)
            over = encode(window)
            over += b" " * (64 * 1024 + 1 - len(over))
            step("telemetry over 64 KiB", client.post("/api/telemetry", content=over, headers=h), 413)
            step("coverage shows nothing stored for the refused bodies", client.get("/api/coverage", params={"day": TODAY}), 200,
                 check=lambda b: coverage_of(b, windows=0, sessions=0))
            ack = step("telemetry window A (60 s, session A, 1 episode, 2 idle)", client.post("/api/telemetry", content=encode(window), headers=h), 200,
                       check=lambda b: f"retained={b['retained']} t_ms={b['t_ms']}" if b["retained"] is True and type(b["t_ms"]) is int
                       and "counters" not in b and b["t_ms"] == anchor_ms - 3600 * 1000 else False)
            step("telemetry window A resent (idempotent, one row)", client.post("/api/telemetry", content=encode(window), headers=h), 200,
                 check=lambda b: "retained again" if b["retained"] is True else False)
            step("coverage counts window A once", client.get("/api/coverage", params={"day": TODAY}), 200,
                 check=lambda b: coverage_of(b, windows=1, camera_on_ms=60000, sessions=1))
            step("GET /api/telemetry is not a route", client.get("/api/telemetry"), 405)
            print("== coverage: two windows, a gap, another day, validation, health")
            window_b = telemetry(device, session_b, wall_ms=anchor_ms - 1800 * 1000, window_ms=30000, gaps=1, gap_ms=5000,
                                 episodes_finished=2, packets_sent=2, idle_dropped=1)
            step("telemetry window B (30 s, session B, 5 s gap, 2 episodes)", client.post("/api/telemetry", content=encode(window_b), headers=h), 200)
            yesterday = telemetry(device, session_b, wall_ms=anchor_ms - 20 * 3600 * 1000, episodes_finished=7, packets_sent=7)
            step("telemetry window C (yesterday UTC)", client.post("/api/telemetry", content=encode(yesterday), headers=h), 200)
            today = step("coverage today = A + B, gap reported", client.get("/api/coverage", params={"day": TODAY}), 200,
                         check=lambda b: coverage_of(b, camera_on_ms=90000, gap_ms=5000, episodes=3, packets=3, idle_sent=2, idle_dropped=1,
                                                     sessions=2, effective_ms=85000, windows=2, day=TODAY))
            step("coverage yesterday = C only", client.get("/api/coverage", params={"day": YESTERDAY}), 200,
                 check=lambda b: coverage_of(b, camera_on_ms=60000, gap_ms=0, episodes=7, packets=7, sessions=1, windows=1))
            step("coverage of an empty day is zeros", client.get("/api/coverage", params={"day": "2026-10-01"}), 200,
                 check=lambda b: coverage_of(b, **{key: 0 for key in COVERAGE_KEYS}))
            step("coverage without a day defaults to today", client.get("/api/coverage"), 200,
                 check=lambda b: f"day={b['day']}" if b["day"] == TODAY and b["windows"] == 2 else False)
            expect("coverage values are integers (day aside), no raw rows", today is not None and all(type(v) is int and v >= 0 for k, v in today.items() if k != "day")
                   and "counters" not in today, f"keys={sorted(today)}" if today else "")
            for bad in ("2026-13-01", "2026-10-1", "20261001", "", "2026-02-30", "yesterday", "2026-10-01T00", "x" * 11):
                step(f"coverage day={bad!r}", client.get("/api/coverage", params={"day": bad}), 400)
            step("coverage without a session", anonymous.get("/api/coverage", params={"day": TODAY}), 401)
            step("health carries today's coverage (same DTO)", client.get("/api/health"), 200,
                 check=lambda b: f"coverage.sessions={b['coverage']['sessions']}" if b.get("coverage") == today else False)
            print("== notices: public page, conditions, CUTE attribution")
            page = step("GET /notices without a session", anonymous.get("/notices"), 200,
                        check=lambda t: f"{len(t):,} chars html" if isinstance(t, str) and "<h1>Third-party notices</h1>" in t else False)
            response = anonymous.get("/notices")
            expect("notices is text/html, no-store, nosniff, no cookie", "text/html" in response.headers.get("content-type", "")
                   and response.headers.get("cache-control") == "no-store" and response.headers.get("x-content-type-options") == "nosniff"
                   and "set-cookie" not in response.headers)
            lowered = response.text.lower()
            for name in ("@mediapipe/tasks-vision", "dinov2_vits14.onnx", "onnxruntime", "fastapi", "starlette", "uvicorn", "pydantic",
                         "numpy", "opencv-python-headless", "tabler-icons"):
                expect(f"notices names {name}", name in lowered)
            expect("notices carries the Apache License text (always: opencv)", "apache license" in lowered and "version 2.0, january 2004" in lowered)
            expect("notices carries MIT and BSD texts", "permission is hereby granted" in lowered and "redistributions of source code" in lowered)
            expect("notices carries the FFmpeg LGPL-2.1 note and text", "ffmpeg is dynamically linked" in lowered and "gnu lesser general public license" in lowered)
            expect("notices has no script and no inline style", "<script" not in lowered and "<style" not in lowered and "style=" not in lowered)
            expect("notices names no filesystem path of this checkout", str(ROOT) not in response.text and temp not in response.text)
            expect("optional components read 'present on this server: no'", lowered.count("present on this server: no") >= 6)
            expect("DINOv2 modification notice absent while not provisioned", "the weights were converted, not retrained" not in lowered)
            expect("MediaPipe copyright absent while not provisioned", "copyright 2022 the mediapipe authors" not in lowered)
            expect("CUTE attribution absent without a calibration", CUTE_URL not in lowered and "kotar" not in lowered)
            step("HEAD /notices", anonymous.head("/notices"), 200)
            from perception.object_memory import ObjectStore
            store = ObjectStore(str(db), profile_id="local", clock=lambda: clock["now"])
            record = {"calibration_id": "self-check-cute", "embedder": "synthetic@selfcheck", "alpha": 0.1, "quantile": 0.5, "n": 10, "source": "cute"}
            store.register_calibration(record)
            lowered = anonymous.get("/notices").text.lower()
            expect("CUTE attribution still absent while the record is unapproved", CUTE_URL not in lowered)
            store.register_calibration({**record, "calibration_id": "self-check-synthetic", "source": "synthetic"})
            store.approve_calibration("self-check-synthetic", "operator")
            lowered = anonymous.get("/notices").text.lower()
            expect("an approved synthetic calibration renders nothing", CUTE_URL not in lowered)
            store.approve_calibration("self-check-cute", "operator")
            text = anonymous.get("/notices").text
            expect("CUTE attribution present after approving the cute calibration", CUTE_URL in text and "Kotar" in text
                   and "Creative Commons Attribution 4.0" in text and "no CUTE image is included in PAM" in text)
            expect("the page prints no calibration number or id", "self-check-cute" not in text and "0.5" not in text.split("CUTE")[1][:400])
            # Provision the identity model in the (synthetic) server inventory: the files
            # exist, no model is loaded (PAM_ENABLE_IDENTITY_MODEL is unset).
            (models / "dinov2_vits14.onnx").write_bytes(b"SYNTHETIC-ONNX-BYTES-NOT-A-MODEL")
            (models / "MANIFEST.json").write_text(json.dumps({"assets": [{"name": "dinov2_vits14.onnx", "version": "dinov2_vits14@7764ea0f-opset17-224",
                                                                           "sha256": "0" * 64, "licence": "Apache-2.0"}]}), encoding="utf-8")
            os.environ.pop("PAM_ENABLE_IDENTITY_MODEL", None)
            text = anonymous.get("/notices").text
            expect("identity entries read 'present on this server: yes' once provisioned",
                   text.count("present on this server: yes") == 5 and "the weights were converted, not retrained" in text
                   and "Copyright (c) Meta Platforms, Inc. and affiliates." in text and "Copyright (c) Microsoft Corporation" in text)
            expect("hand runtime entry still 'no' (browser inventory rejects .onnx)", "Copyright 2022 The MediaPipe Authors." not in text)
            print("== chat answer DTO")
            consent = client.get("/api/consent").json()
            step("acknowledge consent", client.post("/api/consent", json={"acknowledge": consent["required_version"]}, headers=h), 200)
            answer = step("chat with no evidence abstains with the Answer keys", client.post("/api/chat", json={"text": "where is my self-check block"}, headers=h), 200,
                          check=lambda b: f"shape={b['shape']} basis={b['basis']}" if set(b) == ANSWER_KEYS and b["shape"] == "abstain"
                          and b["basis"] == ["no_evidence"] and b["members"] == [] and b["reference_image"] is None and b["target_indicated"] is False
                          and b["capture_time_ms"] is None and b["identity_status"] == "unknown" and b["location_status"] == "unknown"
                          and b["room"] == "room unknown" else False)
            packet = episode(device, session_a, anchor_ms - 60000)
            step("episode", client.post("/api/episodes", content=encode(packet), headers=h), 200)
            deadline = time.monotonic() + 5
            items = []
            while time.monotonic() < deadline:
                items = client.get("/api/items").json()["items"]
                if items and not any(i["index_pending"] for i in items):
                    break
                time.sleep(0.05)
            expect("the episode was processed into an item", bool(items), f"items={len(items)}")
            confident = step("chat answers confidently with the Answer keys", client.post("/api/chat", json={"text": "where is my self-check block"}, headers=h), 200,
                             check=lambda b: f"shape={b['shape']} basis={b['basis']} target_indicated={b['target_indicated']}"
                             if set(b) == ANSWER_KEYS and b["shape"] == "confident" and b["basis"] == ["trusted_match", "placed"]
                             and b["reference_image"] == {"frame_id": packet["keyframes"][-1]["frame_id"], "bbox": [20.0, 40.0, 40.0, 60.0]}
                             and b["target_indicated"] is True and b["capture_time_ms"] == anchor_ms - 60000 + 2200
                             and b["identity_status"] == "matched_trusted" and b["location_status"] == "placed" and len(b["members"]) == 1 else False)
            if confident:
                member = confident["members"][0]
                expect("member DTO carries no store internals", "last_event_ms" not in member and "observation_id" not in member
                       and not any(k in json.dumps(member).lower() for k in ("vector", "embedding", "bank", "scores")), f"keys={sorted(member)}")
            step("coverage counts the local chats (maintenance counter)", client.get("/api/coverage", params={"day": TODAY}), 200,
                 check=lambda b: f"chat_local={b['chat_local']}" if b["chat_local"] == 2 else False)
            step("item image is served and counted", client.get(f"/api/items/{items[0]['item_id']}/image") if items else client.get("/api/items/none/image"), 200 if items else 404)
            step("coverage counts the image serve and its bytes", client.get("/api/coverage", params={"day": TODAY}), 200,
                 check=lambda b: f"image_serves={b['image_serves']} image_bytes={b['image_bytes']}" if b["image_serves"] == 1 and b["image_bytes"] > 100 else False)
            print("== notices document validation (startup self-check rules)")
            good = json.loads((ROOT / "server" / "notices.json").read_text(encoding="utf-8"))
            expect("server/notices.json validates", bool(validate_notices(good)["components"]), f"{len(good['components'])} components")
            for name, broken in (("five keys only", {"components": [{k: v for k, v in good["components"][0].items() if k != "condition"}]}),
                                 ("unknown condition", {"components": [{**good["components"][0], "condition": "model:hand"}]}),
                                 ("duplicate component", {"components": [good["components"][0], good["components"][0]]}),
                                 ("http source", {"components": [{**good["components"][0], "source_url": "http://example.invalid"}]}),
                                 ("empty notice", {"components": [{**good["components"][0], "notice_text": " "}]}),
                                 ("not an object", [])):
                try:
                    validate_notices(broken)
                    expect(f"validator rejects: {name}", False)
                except ValueError as exc:
                    expect(f"validator rejects: {name}", True, f"({exc})")
            print("== register sync")
            result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "check_notices.py")], capture_output=True, text=True, cwd=str(ROOT))
            expect("scripts/check_notices.py agrees with docs/LICENSES.md section 8", result.returncode == 0, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else result.stderr[-200:])
    print()
    print("SELF-CHECK", "FAILED: " + ", ".join(failures) if failures else "PASSED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
