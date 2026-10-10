"""CP4 server self-check: exercises the idle, consent, retention, erasure and
migration routes of server.memory_app against a temporary database and prints
one line per step. Exit status 1 when any expectation fails.

    python3 -B scripts/cp4_selfcheck.py

Nothing here touches a real database, credential or environment file: the app is
built with an explicit temporary path and PIN, the processor is an in-script
injection that marks one synthetic frame as a trusted placement (fixture-only
calibration, the same shape the bootstrap tests use), and no network is used.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ORIGIN = "https://selfcheck.local"
PIN = "self-check-pin-0000"
WIDTH, HEIGHT = 160, 120
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


def now_ms():
    return int(time.time() * 1000)


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


def episode(device, session):
    eid = str(uuid.uuid4())
    wall = now_ms()
    return {"schema_version": 1, "episode_id": eid, "device_id": device, "session_id": session,
            "t_start_ms": 1000, "t_end_ms": 2200, "clock_anchor": {"mono_ms": 0, "wall_ms": wall},
            "capture": {"width": WIDTH, "height": HEIGHT}, "analysis": {"width": WIDTH // 2, "height": HEIGHT // 2},
            "keyframes": [{"frame_id": eid + "-before", "t_ms": 1000, "role": "pre_contact", "jpeg_b64": jpeg_b64()},
                          {"frame_id": eid + "-rest", "t_ms": 2200, "role": "rest", "jpeg_b64": jpeg_b64(20)}],
            "carry_burst": [], "landmarks": [], "gaps": [], "outcome_hint": "released", "capture_mode": "manual"}


def idle(device, session, **overrides):
    frame = {"schema_version": 1, "device_id": device, "session_id": session, "frame_id": str(uuid.uuid4()),
             "t_ms": 0, "clock_anchor": {"mono_ms": 0, "wall_ms": now_ms()}, "capture": {"width": WIDTH, "height": HEIGHT},
             "jpeg_b64": jpeg_b64(20), "motion_energy": 0.0}
    frame.update(overrides)
    return frame


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
            detail = check(body)
            if detail is None:
                detail = ""
            elif detail is not False:
                detail = f" {detail}"
            else:
                ok, detail = False, " (body check failed)"
        except Exception as exc:  # noqa: BLE001 - a failed check is a failed step
            ok, detail = False, f" (body check raised {type(exc).__name__})"
    mark = "ok  " if ok else "FAIL"
    print(f"{mark} {name:<58} -> {response.status_code}{' ' + got_code if got_code else ''}{detail}")
    if not ok:
        failures.append(name)
    return body


def main():
    from server.memory_app import create_app
    with tempfile.TemporaryDirectory(prefix="pam-cp4-selfcheck-") as temp:
        db = Path(temp) / "selfcheck.sqlite3"
        app = create_app(database_path=str(db), auth_pin=PIN, processor=Processor())
        device, session = str(uuid.uuid4()), str(uuid.uuid4())
        with TestClient(app, base_url=ORIGIN, raise_server_exceptions=False) as client:
            anonymous = TestClient(app, base_url=ORIGIN, raise_server_exceptions=False)
            h = {"origin": ORIGIN, "content-type": "application/json"}
            print("== idle: auth, origin, validation, cap")
            step("idle without a session", anonymous.post("/api/idle", content=encode(idle(device, session)), headers=h), 401)
            r = client.post("/api/auth/login", json={"pin": PIN}, headers={"origin": ORIGIN})
            step("login", r, 200)
            step("idle with a foreign origin", client.post("/api/idle", content=encode(idle(device, session)),
                                                           headers={**h, "origin": "https://evil.invalid"}), 403)
            step("idle without an origin", client.post("/api/idle", content=encode(idle(device, session)),
                                                       headers={"content-type": "application/json"}), 403)
            step("idle malformed JSON", client.post("/api/idle", content=b"{", headers=h), 400)
            step("idle extra field", client.post("/api/idle", content=encode(idle(device, session, promoted=1)), headers=h), 400)
            over = encode(idle(device, session))
            over += b" " * (256 * 1024 + 1 - len(over))
            step("idle over 256 KiB", client.post("/api/idle", content=over, headers=h), 413)
            print("== consent: refused before, allowed after")
            step("idle before consent", client.post("/api/idle", content=encode(idle(device, session)), headers=h), 409, "consent_required")
            step("episode before consent", client.post("/api/episodes", content=encode(episode(device, session)), headers=h), 409, "consent_required")
            consent = step("GET /api/consent", client.get("/api/consent"), 200,
                           check=lambda b: f"required={b['required_version']} acknowledged={b['acknowledged_version']} ok={b['ok']} text={len(b['disclosure_text'])} chars"
                           if b["ok"] is False and isinstance(b["disclosure_text"], str) else False)
            step("acknowledge a wrong version", client.post("/api/consent", json={"acknowledge": "not-a-version"}, headers=h), 400)
            step("acknowledge the required version", client.post("/api/consent", json={"acknowledge": consent["required_version"]}, headers=h), 200,
                 check=lambda b: f"ok={b['ok']}" if b["ok"] is True else False)
            ack = step("idle after consent", client.post("/api/idle", content=encode(idle(device, session)), headers=h), 200,
                       check=lambda b: f"retained={b['retained']} evicted={b['evicted']} expires_at_ms={b['expires_at_ms']}"
                       if b["retained"] is True and not ({"jpeg", "jpeg_b64", "packet"} & set(b)) else False)
            resend = idle(device, session, frame_id=ack["frame_id"])
            step("idle resend of the same frame_id", client.post("/api/idle", content=encode(resend), headers=h), 200,
                 check=lambda b: "idempotent" if b["retained"] is True else False)
            print("== retention")
            step("GET /api/retention", client.get("/api/retention"), 200,
                 check=lambda b: f"windows={b['retention']['episodes_days']}/{b['retention']['idle_hours']}/{b['retention']['landmarks_hours']} "
                 f"acknowledged={b['retention']['acknowledged_version']} erased_at_ms={b['retention']['erased_at_ms']} counts={b['counts']}")
            step("PUT retention episodes_days=30", client.put("/api/retention", json={"episodes_days": 30}, headers=h), 200,
                 check=lambda b: f"updated_ms={b['updated_ms']}" if b["episodes_days"] == 30 and b["idle_hours"] == 24 else False)
            step("PUT retention all three windows", client.put("/api/retention", json={"episodes_days": 7, "idle_hours": 72, "landmarks_hours": 168}, headers=h), 200,
                 check=lambda b: None if (b["episodes_days"], b["idle_hours"], b["landmarks_hours"]) == (7, 72, 168) else False)
            for body in ({}, {"episodes_days": 6}, {"episodes_days": 366}, {"idle_hours": 0}, {"idle_hours": 73}, {"landmarks_hours": 169},
                         {"episodes_days": "30"}, {"episodes_days": True}, {"consent_version": "rig-2026-11"}, {"actor": "operator", "episodes_days": 40}):
                step(f"PUT retention {json.dumps(body)}", client.put("/api/retention", json=body, headers=h), 400)
            step("PUT retention without an origin", client.put("/api/retention", json={"episodes_days": 40}), 403)
            print("== erase item")
            packet = episode(device, session)
            step("episode after consent", client.post("/api/episodes", content=encode(packet), headers=h), 200)
            deadline = time.monotonic() + 5
            items = []
            while time.monotonic() < deadline:
                items = client.get("/api/items").json()["items"]
                if items and not any(i["index_pending"] for i in items):
                    break
                time.sleep(0.05)
            item = items[0] if items else None
            if item is None:
                print("FAIL the episode was not processed into an item")
                failures.append("processing")
                item = {"item_id": "missing"}
            else:
                print(f"ok   item {item['item_id'][:8]}... {item['location_status']}/{item['identity_status']} inference={item['inference']} "
                      f"stale_since_ms={item['stale_since_ms']} evidence_expired={item['evidence_expired']}")
            ident = item["item_id"]
            step("erase with a mismatching confirm", client.post(f"/api/items/{ident}/erase", json={"confirm": "wrong"}, headers=h), 409, "confirm_mismatch")
            step("erase without confirm", client.post(f"/api/items/{ident}/erase", json={}, headers=h), 400)
            step("erase an unknown item", client.post("/api/items/no-such-item/erase", json={"confirm": "no-such-item"}, headers=h), 404)
            step("erase with the matching confirm", client.post(f"/api/items/{ident}/erase", json={"confirm": ident}, headers=h), 200,
                 check=lambda b: f"affected_items={b['affected_items']} forensic_erasure={b['forensic_erasure']} counts={sorted(b['counts'])}"
                 if b["erased"] is True and b["forensic_erasure"] is False and "embeddings" not in b["counts"] else False)
            step("the erased item is gone", client.get(f"/api/items/{ident}"), 404)
            print("== erase all")
            step("erase-all wrong phrase", client.post("/api/erase-all", json={"confirm": "erase everything", "pin": PIN}, headers=h), 409, "confirm_mismatch")
            step("erase-all without a pin", client.post("/api/erase-all", json={"confirm": "ERASE EVERYTHING"}, headers=h), 400)
            step("erase-all wrong pin", client.post("/api/erase-all", json={"confirm": "ERASE EVERYTHING", "pin": "wrong"}, headers=h), 409, "pin_mismatch")
            step("erase-all", client.post("/api/erase-all", json={"confirm": "ERASE EVERYTHING", "pin": PIN}, headers=h), 200,
                 check=lambda b: f"swap={b['swap']} forensic_erasure={b['forensic_erasure']} counts={sorted(b['counts'])}"
                 if b["erased"] is True and b["forensic_erasure"] is False else False)
            step("the session survives erase-all", client.get("/api/items"), 200, check=lambda b: f"items={len(b['items'])}" if b["items"] == [] else False)
            step("chat still answers", client.post("/api/chat", json={"text": "where is my self-check block"}, headers=h), 200,
                 check=lambda b: f"shape={b['shape']}" if b["shape"] == "abstain" else False)
            time.sleep(0.01)
            step("idle after erase-all (fresh capture)", client.post("/api/idle", content=encode(idle(device, session)), headers=h), 200)
            stale = idle(device, session, clock_anchor={"mono_ms": 0, "wall_ms": now_ms() - 60000})
            step("idle captured before erase-all", client.post("/api/idle", content=encode(stale), headers=h), 409, "erased_before")
            print("== migrate")
            os.environ.pop("PAM_ALLOW_MIGRATION", None)
            step("migrate default (dry run)", client.post("/api/migrate", json={}, headers=h), 200,
                 check=lambda b: f"status={b['status']} counts={b['counts']}" if b["dry_run"] is True and b["mutates_data"] is False else False)
            step("migrate dry_run not a bool", client.post("/api/migrate", json={"dry_run": "false"}, headers=h), 400)
            step("migrate real run without the env", client.post("/api/migrate", json={"dry_run": False}, headers=h), 503, "migration_disabled")
            os.environ["PAM_ALLOW_MIGRATION"] = "0"
            step("migrate real run with PAM_ALLOW_MIGRATION=0", client.post("/api/migrate", json={"dry_run": False}, headers=h), 503, "migration_disabled")
            os.environ.pop("PAM_ALLOW_MIGRATION", None)
            print("== health")
            step("GET /api/health", client.get("/api/health"), 200,
                 check=lambda b: f"keys={sorted(b)} retention={b['retention']} consent={b['consent']} reobservation={sorted(b['reobservation'])} processing={b['processing']}"
                 if {"status", "capabilities", "models", "processing", "retention", "consent", "reobservation", "chat"} <= set(b)
                 and b["consent"]["ok"] is True and "disclosure_text" not in b["consent"] else False)
            print("== retired and unknown")
            step("GET /api/retention/counts is retired", client.get("/api/retention/counts"), 410)
            step("POST /api/erase is retired", client.post("/api/erase", json={}, headers=h), 410)
    print()
    print("SELF-CHECK", "FAILED: " + ", ".join(failures) if failures else "PASSED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
