"""Keyless local memory application. No legacy services or provider startup hooks."""
from __future__ import annotations

import asyncio
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
import hmac
import html
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.background import BackgroundTask

ROOT = Path(__file__).resolve().parents[1]
PHONE = ROOT / "phone"
MAX_EPISODE_BYTES = 4 * 1024 * 1024
# CP4 idle keyframes (POST /api/idle): the route enforces this body cap before the
# store parses a byte, exactly as MAX_EPISODE_BYTES does for episodes. Equal to
# perception.episode.MAX_IDLE_BYTES (the store raises PacketTooLarge above it too).
MAX_IDLE_BYTES = 256 * 1024
# CP5 frame accounting (POST /api/telemetry): the same pattern; equal to
# perception.episode.MAX_TELEMETRY_BYTES. Counters only (numbers and two ids), so
# the route is session-protected and origin-checked but not consent-gated.
MAX_TELEMETRY_BYTES = 64 * 1024
# GET /api/coverage?day= and the health "coverage": a UTC calendar day. The route
# validates the shape and the calendar before the store is asked (400 otherwise).
DAY_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
# The seven plan keys of coverage(day) first, then the store's integer extras; the
# maintenance counters (Finance) are flattened to integers. Every value of the
# response except "day" is a nonnegative integer: aggregates only, never a row.
COVERAGE_KEYS = ("camera_on_ms", "gap_ms", "episodes", "packets", "idle_sent", "idle_dropped", "sessions")
COVERAGE_EXTRA_KEYS = ("effective_ms", "packets_acked", "episodes_started", "frames_captured", "frames_analysed",
                       "frames_dropped", "bytes_sent", "windows")
COVERAGE_COUNTERS = ("chat_local", "image_serves", "image_bytes")
COVERAGE_CPU = {"process_cpu_ms": "process_cpu_s", "reobs_cpu_ms": "reobs_cpu_s"}
# CP4 erasure: the phrase the caregiver types for POST /api/erase-all; equal to
# perception.episode_store.ERASE_PROFILE_CONFIRM, which the store checks again.
ERASE_ALL_PHRASE = "ERASE EVERYTHING"
# CP4 migration (B-10): a real run of POST /api/migrate needs this environment
# variable to be exactly "1" (read per request, never logged) and is attributed to
# the operator, not to the PIN session, because it is a one-off reviewed conversion.
MIGRATION_ENV = "PAM_ALLOW_MIGRATION"
MIGRATION_ACTOR = "operator"
# Erase report counts are the store's names except the embeddings count, which the
# browser sees as appearance_signatures (the disclosure's own wording).
REPORT_COUNT_NAMES = {"embeddings": "appearance_signatures"}
# CP4 worker maintenance: after a processing batch the worker runs apply_retention
# (at most RETENTION_LIMIT packets reduced) then reobserve (at most REOBS_LIMIT
# item/frame pairs), and in any case at least every MAINTENANCE_INTERVAL seconds of
# the app's clock (the injected clock in tests, wall time in production).
MAINTENANCE_INTERVAL = 300.0
RETENTION_LIMIT = 64
REOBS_LIMIT = 16
SESSION_TTL = 8 * 60 * 60
COOKIE = "pam_session"
ITEM_ID = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
# CP3: an observation id is the store's SHA-256 signature of the observation (64
# lowercase hex). Anything else on a path is a 404 before the store is asked.
OBSERVATION_ID = re.compile(r"^[0-9a-f]{64}$")
# CP3 corrections are attributed to the session role, never to a named person
# (B-15): the server passes this literal and never reads an actor from a request.
CORRECTION_ACTOR = "caregiver_pin"
# as_of (B-11, deterministic replay): epoch milliseconds as at most 16 ASCII digits
# on the query string, or a nonnegative JSON integer in a chat body. The store
# replays its stored decisions up to that time; no model is rerun.
AS_OF_DIGITS = re.compile(r"^[0-9]{1,16}$")
AS_OF_MAX = 10 ** 16 - 1
# Explicit public resources, never a directory mount or extension-only whitelist.
# Exactly the files phone/memory.html and its module graph load. The bootstrap
# suite walks that graph through this app, so a module C adds must be listed
# here or the page fails to load at the supported entry point. hand-worker.js is
# loaded with new Worker('/assets/hand-worker.js'); controller-replay.mjs is a
# Node-only entry point and is deliberately NOT served.
PUBLIC_ASSETS = frozenset({
    "memory.css", "memory.js", "memory-camera.js", "memory-queue.js",
    "controller.js", "grayscale-jpeg.js", "pam-logo.png",
    "motion.js", "hand-busy.js", "hand-worker.js",
})

# Model assets (CP2, G-PROV). Never committed: scripts/fetch_models.py downloads
# pinned files into MODELS_DIR and writes MANIFEST.json there. The app serves a
# model file only when the manifest lists exactly that name, the file resolves
# inside MODELS_DIR, and PAM_ENABLE_HAND_MODEL == "1"; the same inventory decides
# the automatic_hand_recognition capability, so the server is the policy
# authority even when the browser worker could load the files. The licence
# register is Oversight's docs/LICENSES.md, read read-only and bounded.
# CP3 adds a second, server-side inventory (SERVER_MODELS_DIR below) for the
# identity model, gated the same way with PAM_ENABLE_IDENTITY_MODEL.
MODELS_DIR = PHONE / "assets" / "models"
LICENCE_REGISTER = ROOT / "docs" / "LICENSES.md"
MANIFEST_NAME = "MANIFEST.json"
MAX_MANIFEST_BYTES = 64 * 1024
MAX_LICENCE_REGISTER_BYTES = 1024 * 1024
MAX_MODEL_NAME = 120
MAX_MODEL_FIELD = 200
HAND_MODEL_ENV = "PAM_ENABLE_HAND_MODEL"
HAND_CAPABILITY = "automatic_hand_recognition"
# Licence register gate (docs/LICENSES.md rule 2): every asset row carries exactly one
# of `status: VERIFIED-COMMERCIAL`, `status: UNVERIFIED`, `status: REJECTED` on the
# same line as the base file name. A licence counts as recorded only when a line
# names the file AND carries the literal VERIFIED-COMMERCIAL token AND carries
# neither of the other two tokens; a file name inside an UNVERIFIED row is not a grant.
LICENCE_VERIFIED_TOKEN = "VERIFIED-COMMERCIAL"
LICENCE_BLOCKING_TOKENS = ("UNVERIFIED", "REJECTED")
MODEL_MEDIA_TYPES = {
    ".task": "application/octet-stream", ".wasm": "application/wasm",
    ".js": "text/javascript", ".mjs": "text/javascript", ".cjs": "text/javascript",
    ".json": "application/json",
}
# Server-side model assets (CP3, docs/OVERSIGHT_CP3.md section 1.5). The identity
# model is a second, separate inventory: server/models/MANIFEST.json (same entry
# shape, written by scripts/fetch_models.py in local-export mode) whose names may
# only carry these suffixes. Nothing in it is ever served: the browser route
# /assets/models/ reads the browser inventory only and rejects these suffixes
# outright, so the ~85 MB model can never be fetched from the page. The browser
# inventory keeps rejecting .onnx (fail closed), so the two manifests cannot be
# merged by mistake.
SERVER_MODELS_DIR = ROOT / "server" / "models"
SERVER_MODEL_SUFFIXES = frozenset({".onnx"})
IDENTITY_MODEL_NAME = "dinov2_vits14.onnx"
IDENTITY_MODEL_ENV = "PAM_ENABLE_IDENTITY_MODEL"
IDENTITY_CAPABILITY = "physical_instance_recognition"
# A relative path of safe segments: no leading "/", no "..", no backslash, no
# hidden or empty segment, no control characters (the worker applies the same shape).
MODEL_NAME = re.compile(r"^(?:[A-Za-z0-9][A-Za-z0-9._-]*/)*[A-Za-z0-9][A-Za-z0-9._-]*$")
HAND_REASONS = {
    "unprovisioned": "Hand model assets are not provisioned on this server.",
    "unlicensed": "Hand model licence is not recorded as VERIFIED-COMMERCIAL in docs/LICENSES.md.",
    "disabled": "Automatic hand recognition is not enabled (PAM_ENABLE_HAND_MODEL).",
}
IDENTITY_REASONS = {
    "unprovisioned": "Identity model assets are not provisioned on this server.",
    "unlicensed": "Identity model licence is not recorded as VERIFIED-COMMERCIAL in docs/LICENSES.md.",
    "disabled": "Physical-instance recognition is not enabled (PAM_ENABLE_IDENTITY_MODEL).",
}
# CP3 correction refusals: 409 with a fixed safe sentence and a code the browser
# can branch on. The store's own error text never reaches a response body. A
# sentence names only what the server can know: a cannot-link row exists, but
# its source (two outputs of one frame, "Not this one", a group choice, or a row
# inherited through an earlier merge) is not reported by the store, so the
# cannot_link sentence lists the possible sources instead of asserting one
# (Oversight F1).
CORRECTION_REFUSALS = {
    "cannot_link": ("Pam has evidence these are different items: they were seen at the same time, or an earlier "
                    "correction marked one as not the other. They cannot be merged."),
    "not_ambiguous": "That sighting is not waiting for a choice; it is already attributed to an item.",
    "invalid_correction": "That correction cannot be applied to this item.",
}
# Third-party notices (CP5, docs/OVERSIGHT_CP5.md section 3). server/notices.json is
# derived from the licence register (docs/LICENSES.md section 8, the source); the
# app never reads the register's expected list at runtime: scripts/check_notices.py
# compares the two. GET /notices (public, no session, HTML, everything escaped,
# no script) reads the file per request under MAX_NOTICES_BYTES and renders each
# entry only while its `condition` holds on this server. The closed condition set:
#   always                 rendered in full on every server
#   provisioned:hand       the @mediapipe/tasks-vision runtime files are provisioned
#                          in the browser inventory (phone/assets/models/MANIFEST.json)
#   provisioned:identity   dinov2_vits14.onnx is provisioned in the server inventory
#   served:tabler          a served page embeds Tabler icon paths: NEVER today (no
#                          served file does: phone/memory.html has no <svg> and
#                          PUBLIC_ASSETS lists no icon file; agent.html, which embeds
#                          Tabler-derived symbols, redirects). TABLER_SERVED flips to
#                          True, with the icon-set version recorded in notices.json and
#                          the register, the moment a served page carries the icons.
#   calibration:cute       the profile holds an APPROVED calibration record with
#                          source "cute" (the only store read of the page: a boolean)
# A provisioned:* entry whose component is absent renders as a one-line "present on
# this server: no" (truthful and complete, the Oversight recommendation); the CUTE
# attribution is omitted entirely without such a calibration (an attribution for
# data never used would itself be a false provenance statement).
NOTICES_PATH = ROOT / "server" / "notices.json"
MAX_NOTICES_BYTES = 2 * 1024 * 1024
NOTICE_KEYS = frozenset({"component", "version", "licence", "source_url", "notice_text", "condition"})
NOTICE_CONDITIONS = frozenset({"always", "provisioned:hand", "provisioned:identity", "calibration:cute", "served:tabler"})
MAX_NOTICE_FIELD = 400
TABLER_SERVED = False
# The @mediapipe/tasks-vision 1.0.1 files (docs/LICENSES.md section 2a; scripts/model_pins.json).
TASKS_VISION_FILES = frozenset({"vision_bundle.mjs", "vision_wasm_internal.js", "vision_wasm_internal.wasm",
                                "vision_wasm_nosimd_internal.js", "vision_wasm_nosimd_internal.wasm"})
NOTICE_BLOCK_START = "---- "
NOTICE_BLOCK_END = "---- end of "


class CorrectionRefused(Exception):
    """A CP3 correction the store refused; rendered as 409 {detail, code}."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code if code in CORRECTION_REFUSALS else "invalid_correction"


# CP4 refusals: {code: (status, fixed safe sentence)}, rendered as {detail, code}
# so the browser can branch on the code. consent_required and erased_before are
# the store's two capture refusals (ValueError "consent required" / "captured
# before erasure" from ingest_episode and ingest_idle); the browser must drop its
# IndexedDB mirror of a packet refused with erased_before. The store's own message
# never reaches a body.
REFUSALS = {
    "consent_required": (409, "Capture is paused until the current privacy disclosure has been acknowledged in the Privacy view."),
    "erased_before": (409, "This capture is from before everything was erased and cannot be stored again."),
    "confirm_mismatch": (409, "The typed confirmation does not match."),
    "pin_mismatch": (409, "The PIN does not match."),
    "migration_disabled": (503, "Migration is not enabled on this server."),
}
# The store's fixed refusal messages that become a coded 409 (checked before the
# generic 400 for any other ValueError).
STORE_REFUSALS = {"consent required": "consent_required", "captured before erasure": "erased_before"}


class Refused(Exception):
    """A CP4 refusal; rendered as REFUSALS[code] = (status, detail) plus the code."""
    def __init__(self, code):
        if code not in REFUSALS:
            raise ValueError("unknown refusal code")
        super().__init__(code)
        self.code = code


class StoreGate:
    """Shared/exclusive gate over store calls. erase_profile swaps the database
    file under the store, so it runs alone (exclusive); every other store call
    runs shared and may overlap with the others as before. Writers waiting are
    served before new readers, so an erase-all cannot starve."""
    def __init__(self):
        self._cond = threading.Condition()
        self._shared = 0
        self._exclusive = False
        self._waiting = 0

    @contextmanager
    def shared(self):
        with self._cond:
            while self._exclusive or self._waiting:
                self._cond.wait()
            self._shared += 1
        try:
            yield
        finally:
            with self._cond:
                self._shared -= 1
                if not self._shared:
                    self._cond.notify_all()

    @contextmanager
    def exclusive(self):
        with self._cond:
            self._waiting += 1
            try:
                while self._exclusive or self._shared:
                    self._cond.wait()
            finally:
                self._waiting -= 1
            self._exclusive = True
        try:
            yield
        finally:
            with self._cond:
                self._exclusive = False
                self._cond.notify_all()


def _model_name(value, suffixes=None):
    """A validated manifest asset name, or None. Exactly this name is servable
    (browser inventory, suffixes None = MODEL_MEDIA_TYPES) or loadable (server
    inventory, suffixes = SERVER_MODEL_SUFFIXES)."""
    allowed = MODEL_MEDIA_TYPES if suffixes is None else suffixes
    if not isinstance(value, str) or not 1 <= len(value) <= MAX_MODEL_NAME or not value.isascii():
        return None
    if not MODEL_NAME.fullmatch(value) or ".." in value.split("/"):
        return None
    if Path(value).suffix.lower() not in allowed or value.rsplit("/", 1)[-1] == MANIFEST_NAME:
        return None
    return value


def _model_field(value, *, required):
    if value is None and not required:
        return None
    if not isinstance(value, str) or len(value) > MAX_MODEL_FIELD or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Invalid manifest field")
    return value


def load_model_manifest(models_dir=None, *, suffixes=None):
    """The validated asset list of <models_dir>/MANIFEST.json, or None.

    None means "not provisioned": no manifest, unreadable, larger than
    MAX_MANIFEST_BYTES, not a JSON object with an "assets" list, or any entry
    invalid (fail closed: a manifest with one bad entry serves nothing). Each
    entry is {name, version, sha256, licence, url, fetched_at}: name a relative
    path validated by _model_name; version, sha256 and licence strings
    (sha256 64 lowercase hex); url and fetched_at optional strings. Nothing here
    opens a model file; only the manifest is read. suffixes selects the
    inventory: None is the browser inventory (MODEL_MEDIA_TYPES), the server
    inventory passes SERVER_MODEL_SUFFIXES; an entry of the other kind makes the
    whole manifest invalid, so a .onnx listed in the browser manifest serves
    nothing and a .task listed in the server manifest loads nothing.
    """
    directory = Path(models_dir) if models_dir is not None else MODELS_DIR
    path = directory / MANIFEST_NAME
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MANIFEST_BYTES:
            return None
        with open(path, "rb") as handle:
            raw = handle.read(MAX_MANIFEST_BYTES + 1)
        if len(raw) > MAX_MANIFEST_BYTES:
            return None
        manifest = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None
    if not isinstance(manifest, dict) or not isinstance(manifest.get("assets"), list) or len(manifest["assets"]) > 64:
        return None
    assets, names = [], set()
    for entry in manifest["assets"]:
        if not isinstance(entry, dict):
            return None
        name = _model_name(entry.get("name"), suffixes)
        if name is None or name in names:
            return None
        try:
            asset = {"name": name, "version": _model_field(entry.get("version"), required=True),
                     "sha256": _model_field(entry.get("sha256"), required=True),
                     "licence": _model_field(entry.get("licence"), required=True),
                     "url": _model_field(entry.get("url"), required=False),
                     "fetched_at": _model_field(entry.get("fetched_at"), required=False)}
        except ValueError:
            return None
        if not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"]):
            return None
        names.add(name)
        assets.append(asset)
    return assets


def model_file(models_dir, name, *, suffixes=None):
    """The on-disk file for a validated manifest name, or None if it is absent or
    does not resolve inside models_dir (no symlink anywhere in the chain).
    suffixes selects the inventory as in load_model_manifest."""
    directory = Path(models_dir) if models_dir is not None else MODELS_DIR
    if _model_name(name, suffixes) is None:
        return None
    path = directory / name
    try:
        root = directory.resolve()
        if path.is_symlink() or not path.is_file() or path.resolve() != root / name:
            return None
        if any((directory / Path(*Path(name).parts[:depth])).is_symlink() for depth in range(1, len(Path(name).parts))):
            return None
    except (OSError, ValueError, RuntimeError):
        return None
    return path


def _licence_register_text(licence_register=None):
    path = Path(licence_register) if licence_register is not None else LICENCE_REGISTER
    try:
        if path.is_symlink() or not path.is_file():
            return ""
        with open(path, "rb") as handle:
            return handle.read(MAX_LICENCE_REGISTER_BYTES).decode("utf-8", "replace")
    except (OSError, ValueError):
        return ""


def licence_verified(register_text, base_name):
    """True when some line of the register names base_name together with the
    literal VERIFIED-COMMERCIAL token and no UNVERIFIED/REJECTED token. A
    structured row check, not a substring search over the whole file."""
    if not base_name:
        return False
    for line in register_text.splitlines():
        if base_name in line and LICENCE_VERIFIED_TOKEN in line and not any(token in line for token in LICENCE_BLOCKING_TOKENS):
            return True
    return False


def model_inventory(models_dir=None, licence_register=None, *, suffixes=None):
    """Health "models": one entry per manifest asset, empty when no manifest.

    provisioned: the file exists where the asset route would serve it (browser
    inventory) or where the server would load it (server inventory, suffixes =
    SERVER_MODEL_SUFFIXES). licence_recorded: the manifest entry carries a
    non-empty licence AND the licence register (docs/LICENSES.md) has a
    VERIFIED-COMMERCIAL row for the asset's base file name (licence_verified).
    Never includes file system paths. Both inventories share this entry shape
    {name, provisioned, licence_recorded, version}.
    """
    assets = load_model_manifest(models_dir, suffixes=suffixes)
    if not assets:
        return []
    register = _licence_register_text(licence_register)
    inventory = []
    for asset in assets:
        base = asset["name"].rsplit("/", 1)[-1]
        inventory.append({"name": asset["name"],
                          "provisioned": model_file(models_dir, asset["name"], suffixes=suffixes) is not None,
                          "licence_recorded": bool(asset["licence"].strip()) and licence_verified(register, base),
                          "version": asset["version"]})
    return inventory


def server_model_inventory(server_models_dir=None, licence_register=None):
    """The server-side inventory (CP3): <server_models_dir>/MANIFEST.json read with
    SERVER_MODEL_SUFFIXES, default server/models. Same entry shape as the browser
    inventory; nothing in it is reachable through /assets/models/."""
    directory = Path(server_models_dir) if server_models_dir is not None else SERVER_MODELS_DIR
    return model_inventory(directory, licence_register, suffixes=SERVER_MODEL_SUFFIXES)


def hand_model_entry(models):
    """The hand landmarker entry of an inventory (a *.task whose file name contains
    "hand_landmarker", the lookup the browser worker performs), or None."""
    for entry in models:
        base = entry["name"].rsplit("/", 1)[-1]
        if base.endswith(".task") and "hand_landmarker" in base:
            return entry
    return None


def hand_model_enabled():
    """The operator's explicit opt-in, read at request time, never logged."""
    return os.environ.get(HAND_MODEL_ENV) == "1"


def hand_model_capability(models):
    """The automatic_hand_recognition capability decided by the server policy:
    enabled only when the hand model is provisioned, its licence is recorded and
    PAM_ENABLE_HAND_MODEL == "1". One function feeds /api/health and /api/items so
    the two can never disagree, and it overrides whatever the store reports."""
    entry = hand_model_entry(models)
    if entry is None or not entry["provisioned"]:
        reason = HAND_REASONS["unprovisioned"]
    elif not entry["licence_recorded"]:
        reason = HAND_REASONS["unlicensed"]
    elif not hand_model_enabled():
        reason = HAND_REASONS["disabled"]
    else:
        return {"name": HAND_CAPABILITY, "enabled": True,
                "reason": f"Hand model {entry['version']} provisioned; accuracy unmeasured on this device."}
    return {"name": HAND_CAPABILITY, "enabled": False, "reason": reason}


def _replace_capability(capabilities, policy):
    """capabilities with the entry named policy["name"] replaced in place exactly
    once (duplicates dropped), or appended when the store did not report one."""
    result, replaced = [], False
    for cap in capabilities:
        if isinstance(cap, dict) and cap.get("name") == policy["name"]:
            if not replaced:
                result.append(policy)
                replaced = True
            continue
        result.append(cap)
    if not replaced:
        result.append(policy)
    return result


def with_hand_policy(capabilities, models):
    """The store's capabilities with the hand capability replaced in place (or
    appended when the store did not report one)."""
    return _replace_capability(capabilities, hand_model_capability(models))


def identity_model_entry(models):
    """The identity model entry of an inventory (the server-side .onnx whose base
    file name is IDENTITY_MODEL_NAME, the file DinoV2Embedder is written for), or None."""
    for entry in models:
        if entry["name"].rsplit("/", 1)[-1] == IDENTITY_MODEL_NAME:
            return entry
    return None


def identity_model_enabled():
    """The operator's explicit opt-in (PAM_ENABLE_IDENTITY_MODEL == "1"), read at
    request time, never logged. Default off."""
    return os.environ.get(IDENTITY_MODEL_ENV) == "1"


def identity_model_gate(models):
    """(entry, refusal) of the identity policy gate: refusal is one of
    IDENTITY_REASONS' keys (precedence unprovisioned > unlicensed > disabled) or
    None when the gate is open (provisioned, licence recorded, env flag "1")."""
    entry = identity_model_entry(models)
    if entry is None or not entry["provisioned"]:
        return entry, "unprovisioned"
    if not entry["licence_recorded"]:
        return entry, "unlicensed"
    if not identity_model_enabled():
        return entry, "disabled"
    return entry, None


def identity_model_capability(models, store_capability=None, load_error=None):
    """The physical_instance_recognition capability decided by the server policy,
    mirroring hand_model_capability: enabled only when the identity model is
    provisioned in the server inventory, its licence is recorded and
    PAM_ENABLE_IDENTITY_MODEL == "1". Then, in order: a model that failed to load
    reports that (load_error, never a silent fallback to provisional identity);
    the store's own entry passes through while it reports enabled False (an
    embedder loaded without an approved calibration for its tag can only ever
    produce provisional identity, which is the honest reason); otherwise enabled
    with "accuracy unmeasured on this device". One function feeds /api/health and
    /api/items so the two can never disagree."""
    name = IDENTITY_CAPABILITY
    entry, refusal = identity_model_gate(models)
    if refusal is not None:
        return {"name": name, "enabled": False, "reason": IDENTITY_REASONS[refusal]}
    if load_error:
        return {"name": name, "enabled": False, "reason": str(load_error)}
    if not isinstance(store_capability, dict) or store_capability.get("enabled") is not True:
        reason = store_capability.get("reason") if isinstance(store_capability, dict) else None
        return {"name": name, "enabled": False,
                "reason": reason if isinstance(reason, str) and reason.strip() else "Identity model provisioned; the memory store reports no identity stage."}
    return {"name": name, "enabled": True,
            "reason": f"Identity model {entry['version']} provisioned and calibrated; accuracy unmeasured on this device."}


def with_identity_policy(capabilities, models, load_error=None):
    """The store's capabilities with the identity capability replaced in place by
    identity_model_capability (the store's entry is its input), or appended."""
    store_capability = next((cap for cap in capabilities if isinstance(cap, dict) and cap.get("name") == IDENTITY_CAPABILITY), None)
    return _replace_capability(capabilities, identity_model_capability(models, store_capability, load_error))


def identity_load_failure(exc):
    """The capability reason for an identity model that failed to construct: a
    ValueError's own text when it is short and names no path (DinoV2Embedder
    raises those with the file's base name at most), else the error's class name."""
    text = str(exc) if isinstance(exc, ValueError) else ""
    if not text or len(text) > 160 or any(sep in text for sep in ("/", "\\")) or any(ord(c) < 32 or ord(c) == 127 for c in text):
        text = type(exc).__name__
    return f"Identity model failed to load: {text}"


def _notice_field(entry, key, *, maximum=MAX_NOTICE_FIELD):
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f"notices entry {key} is missing, empty, too long or not printable")
    return value


def validate_notices(data):
    """The validated notices document: {"components": [entries], "application":
    {...} | None}. ValueError (never a path) when the document is not an object
    with a "components" list of 1..64 entries, when an entry does not carry
    exactly NOTICE_KEYS with non-empty strings (the short fields printable and at
    most MAX_NOTICE_FIELD characters; source_url https; condition in
    NOTICE_CONDITIONS; notice_text non-empty), or when a component name repeats.
    The register comparison is scripts/check_notices.py's job, not the app's."""
    if not isinstance(data, dict) or not isinstance(data.get("components"), list) or not 1 <= len(data["components"]) <= 64:
        raise ValueError("notices document must be an object with a components list")
    components, names = [], set()
    for entry in data["components"]:
        if not isinstance(entry, dict) or set(entry) != NOTICE_KEYS:
            raise ValueError("notices entry must carry exactly component, version, licence, source_url, notice_text, condition")
        component = _notice_field(entry, "component")
        if component in names:
            raise ValueError("notices entry component repeats")
        names.add(component)
        version, licence = _notice_field(entry, "version"), _notice_field(entry, "licence")
        source_url = _notice_field(entry, "source_url", maximum=1000)
        if not source_url.startswith("https://") or any(c.isspace() for c in source_url):
            raise ValueError("notices entry source_url must be an https URL")
        condition = _notice_field(entry, "condition")
        if condition not in NOTICE_CONDITIONS:
            raise ValueError("notices entry condition is outside the closed set")
        notice_text = entry.get("notice_text")
        if not isinstance(notice_text, str) or not notice_text.strip():
            raise ValueError("notices entry notice_text is empty")
        components.append({"component": component, "version": version, "licence": licence, "source_url": source_url,
                           "notice_text": notice_text, "condition": condition})
    application = data.get("application")
    if application is not None:
        if not isinstance(application, dict):
            raise ValueError("notices application must be an object")
        application = {"heading": _notice_field(application, "heading"), "licence": _notice_field(application, "licence"),
                       "copyright": _notice_field(application, "copyright"),
                       "notice_text": application.get("notice_text") if isinstance(application.get("notice_text"), str) else ""}
    return {"components": components, "application": application}


def load_notices(path=None):
    """server/notices.json (or `path`) read and validated per call: at most
    MAX_NOTICES_BYTES, UTF-8 JSON, validate_notices. ValueError (no path in the
    message) when absent, unreadable, over the cap or invalid: the app's startup
    self-check raises it; GET /notices answers 503."""
    target = Path(path) if path is not None else NOTICES_PATH
    try:
        if target.is_symlink() or not target.is_file():
            raise ValueError("notices file is not installed")
        with open(target, "rb") as handle:
            raw = handle.read(MAX_NOTICES_BYTES + 1)
    except OSError:
        raise ValueError("notices file is not readable") from None
    if len(raw) > MAX_NOTICES_BYTES:
        raise ValueError("notices file exceeds the size cap")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError):
        raise ValueError("notices file is not valid JSON") from None
    return validate_notices(data)


def hand_runtime_provisioned(models):
    """provisioned:hand holds when any @mediapipe/tasks-vision runtime file is
    provisioned in the browser inventory (the hand model bundle itself has no
    notices entry while its register row is UNVERIFIED)."""
    return any(entry.get("provisioned") is True and entry["name"].rsplit("/", 1)[-1] in TASKS_VISION_FILES for entry in models)


def identity_provisioned(models):
    """provisioned:identity holds when dinov2_vits14.onnx is provisioned in the
    server inventory (the file exists where DinoV2Embedder would load it)."""
    entry = identity_model_entry(models)
    return entry is not None and entry.get("provisioned") is True


def _notice_text_html(text):
    """notice_text as HTML: the reproduced licence files (between a "---- <title>
    (...) ----" line and its "---- end of <title> ----" line) as <pre>, the prose
    paragraphs between them as <p>. Everything is escaped; nothing is markup."""
    parts, prose, block = [], [], None

    def flush_prose():
        if prose:
            paragraph = "\n".join(prose).strip()
            if paragraph:
                parts.append("<p>" + html.escape(paragraph, quote=True).replace("\n", "<br>\n") + "</p>")
            prose.clear()
    for line in text.split("\n"):
        if block is not None:
            block.append(line)
            if line.startswith(NOTICE_BLOCK_END):
                parts.append("<pre>" + html.escape("\n".join(block), quote=True) + "</pre>")
                block = None
        elif line.startswith(NOTICE_BLOCK_START) and not line.startswith(NOTICE_BLOCK_END):
            flush_prose()
            block = [line]
        elif line.strip():
            prose.append(line)
        else:
            flush_prose()
    flush_prose()
    if block is not None:
        parts.append("<pre>" + html.escape("\n".join(block), quote=True) + "</pre>")
    return "\n".join(parts)


def render_notices(document, conditions):
    """The /notices page (plain HTML, no script, no style, every value escaped)
    for a validated document and the conditions evaluated on this server
    ({condition: bool | None}; None = unknown). An "always" entry and any entry
    whose condition holds render in full; a provisioned:* or served:tabler entry
    whose condition does not hold renders as its heading, version, licence and
    source URL plus a one-line "present on this server: no"; a calibration:cute
    entry whose condition does not hold (or is unknown) is omitted. The page
    carries no personal data: no names, counts, ids or calibration numbers."""
    def e(value):
        return html.escape(str(value), quote=True)
    parts = ["<!DOCTYPE html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             "<title>Third-party notices</title>", "</head>", "<body>", "<h1>Third-party notices</h1>",
             "<p>The third-party software this PAM server serves to the browser or runs on the laptop, with the "
             "copyright lines, licence texts and statements their licences require. Optional components say "
             "whether they are present on this server; a notice for data or icons this server does not use is "
             "not shown. Source URLs are printed, not linked: this page makes no request outside its own origin.</p>"]
    rendered = []
    for entry in document["components"]:
        condition = entry["condition"]
        holds = conditions.get(condition) if condition != "always" else True
        if condition == "calibration:cute" and holds is not True:
            continue
        rendered.append((entry, holds is True))
    parts.append("<h2>Contents</h2>")
    parts.append("<ol>")
    for index, (entry, _) in enumerate(rendered, 1):
        parts.append(f'<li><a href="#notice-{index}">{e(entry["component"])}</a> ({e(entry["licence"])})</li>')
    if document.get("application"):
        parts.append(f'<li><a href="#application">{e(document["application"]["heading"])}</a></li>')
    parts.append("</ol>")
    for index, (entry, holds) in enumerate(rendered, 1):
        condition = entry["condition"]
        parts.append(f'<section id="notice-{index}">')
        parts.append(f"<h2>{e(entry['component'])}</h2>")
        parts.append("<dl>")
        parts.append(f"<dt>Version</dt><dd>{e(entry['version'])}</dd>")
        parts.append(f"<dt>Licence</dt><dd>{e(entry['licence'])}</dd>")
        parts.append(f"<dt>Source</dt><dd><code>{e(entry['source_url'])}</code></dd>")
        if condition.startswith("provisioned:"):
            parts.append(f"<dt>Availability</dt><dd>Optional component; present on this server: {'yes' if holds else 'no'}</dd>")
        elif condition == "served:tabler":
            parts.append("<dt>Availability</dt><dd>" + ("Embedded in a page served by this server: yes" if holds else
                         "Embedded in a page served by this server: no (no served page carries these icons, so no notice is owed today)") + "</dd>")
        elif condition == "calibration:cute":
            parts.append("<dt>Availability</dt><dd>An approved identity calibration derived from this dataset exists on this server: yes</dd>")
        parts.append("</dl>")
        if holds:
            parts.append(_notice_text_html(entry["notice_text"]))
        elif condition == "served:tabler":
            parts.append("<p>Not embedded in any served page; the licence text is shown when it is.</p>")
        else:
            parts.append("<p>Not present on this server; the licence text is shown when it is.</p>")
        parts.append("</section>")
    application = document.get("application")
    if application:
        parts.append('<section id="application">')
        parts.append(f"<h2>{e(application['heading'])}</h2>")
        parts.append(f"<dl><dt>Licence</dt><dd>{e(application['licence'])}</dd><dt>Copyright</dt><dd>{e(application['copyright'])}</dd></dl>")
        if application["notice_text"].strip():
            parts.append("<pre>" + html.escape(application["notice_text"], quote=True) + "</pre>")
        parts.append("</section>")
    parts.extend(["</body>", "</html>", ""])
    return "\n".join(parts)


def create_app(database_path=None, profile_id="local", processor=None, clock=None,
               auth_pin=None, chat_provider=None, models_dir=None, licence_register=None,
               embedder=None, server_models_dir=None):
    """Construct without opening files; trusted injections belong only to this boundary.

    clock is a callable returning epoch seconds. An injected cloud provider alone
    does not authorize paid work: policy/integration approval is a separate gate.
    models_dir (default phone/assets/models) holds MANIFEST.json and the pinned
    model files; licence_register (default docs/LICENSES.md) is Oversight's
    register. Both are read per request, never at construction, and only tests
    point them elsewhere.

    CP3: embedder is a trusted injection (tests pass a deterministic
    perception.identity.Embedder; None = decide by policy). server_models_dir
    (default server/models) holds the server-side MANIFEST.json and the identity
    model file; when only models_dir is relocated and no server directory is
    named, the server inventory reads that same directory (one relocated models
    root; the two inventories still accept disjoint suffixes). With no injected
    embedder, DinoV2Embedder is constructed from the server inventory only when
    the identity gate is open (dinov2_vits14.onnx provisioned, licence
    VERIFIED-COMMERCIAL, PAM_ENABLE_IDENTITY_MODEL == "1"); a construction error
    becomes the capability's reason, never a silent fallback.
    """
    now = clock or time.time
    models_path = Path(models_dir) if models_dir is not None else MODELS_DIR
    server_models_path = (Path(server_models_dir) if server_models_dir is not None
                          else (models_path if models_dir is not None else SERVER_MODELS_DIR))
    register_path = Path(licence_register) if licence_register is not None else LICENCE_REGISTER
    # CP5 startup self-check: server/notices.json must be present and well-formed
    # (every entry exactly NOTICE_KEYS, a closed condition, no duplicate component);
    # a ValueError here names no path. Whether its component set equals the
    # register's expected list is scripts/check_notices.py's check, never a
    # runtime read of docs/.
    load_notices()
    pin = auth_pin if auth_pin is not None else os.environ.get("PAM_AUTH_PIN", os.environ.get("CAREGIVER_PIN"))
    if not isinstance(pin, str) or not pin.strip():
        pin = None
    db_path = database_path if database_path is not None else os.environ.get("PAM_OBJECT_DB")
    store = None
    store_lock = threading.Lock()
    processing_lock = asyncio.Lock()
    wake = asyncio.Event()
    sessions = {}
    attempts = {}
    global_attempts = deque()
    active_requests = 0
    processing_stats = {"status": "idle"}
    # CP4 maintenance state: when the last apply_retention + reobserve pass ran
    # (app clock seconds) and the counts of the last reobserve pass (health).
    maintenance = {"at": None, "reobservation": {}}
    gate = StoreGate()
    # Identity model state (CP3): injected embedders are never replaced; a
    # server-constructed one follows the gate, and a failed construction is
    # remembered (reason only, never a path) until the gate closes again.
    identity_state = {"injected": embedder is not None, "load_error": None}
    identity_lock = threading.Lock()

    def server_models_now():
        return server_model_inventory(server_models_path, register_path)

    def sync_embedder(server_models):
        """Construct or drop the server-side embedder so it matches the gate read
        now (the env flag and register are read per request, like the hand gate).
        Runs in a worker thread: loading the model is file IO and runtime setup.
        identity_lock serialises only this; get_store is never blocked by a load."""
        if identity_state["injected"] or store is None:
            return
        entry, refusal = identity_model_gate(server_models)
        with identity_lock:
            if refusal is None:
                if store.embedder is None and identity_state["load_error"] is None:
                    path = model_file(server_models_path, entry["name"], suffixes=SERVER_MODEL_SUFFIXES)
                    try:
                        if path is None:
                            raise ValueError("Identity model file is not provisioned")
                        from perception.identity import DinoV2Embedder
                        store.set_embedder(DinoV2Embedder(path))
                    except (ValueError, OSError) as exc:
                        identity_state["load_error"] = identity_load_failure(exc)
            elif store.embedder is not None or identity_state["load_error"] is not None:
                store.set_embedder(None)
                identity_state["load_error"] = None

    def get_store():
        nonlocal store
        if not db_path:
            raise HTTPException(503, "Local memory storage is not configured.")
        with store_lock:
            if store is None:
                from perception.object_memory import ObjectStore
                store = ObjectStore(db_path, profile_id=profile_id, clock=now, embedder=embedder)
                constructed = True
            else:
                constructed = False
        if constructed:
            sync_embedder(server_models_now())
        return store

    async def call_gated(acquire, method, args, kwargs):
        """One store call off the event loop under the gate (shared or exclusive),
        with the store's errors mapped to safe responses: KeyError 404; ValueError
        413 (PacketTooLarge), 409 (RevisionLimitError), a coded 409 for the store's
        capture refusals (STORE_REFUSALS: consent_required, erased_before, mapped
        before the generic case), else 400; anything else 503."""
        def invoke():
            with acquire():
                return getattr(get_store(), method)(*args, **kwargs)
        try:
            return await asyncio.to_thread(invoke)
        except HTTPException:
            raise
        except KeyError:
            raise HTTPException(404, "Item not found.") from None
        except ValueError as exc:
            from perception.episode import PacketTooLarge, RevisionLimitError
            if isinstance(exc, PacketTooLarge):
                raise HTTPException(413, "Request body is too large.") from None
            if isinstance(exc, RevisionLimitError):
                raise HTTPException(409, "Episode revision limit reached.") from None
            if str(exc) in STORE_REFUSALS:
                raise Refused(STORE_REFUSALS[str(exc)]) from None
            raise HTTPException(400, "Invalid memory request.") from None
        except Exception:
            raise HTTPException(503, "Local memory is temporarily unavailable.") from None

    async def call_store(method, *args, **kwargs):
        return await call_gated(gate.shared, method, args, kwargs)

    async def call_store_exclusive(method, *args, **kwargs):
        """The same call alone: no other store call runs while it does (erase_profile
        swaps the database file). The caller also holds processing_lock so the
        worker's batch cannot start around it."""
        return await call_gated(gate.exclusive, method, args, kwargs)

    async def call_correction(method, *args, **kwargs):
        """A CP3 correction (link / unlink / assign) with the actor fixed to the
        session role literal (the positional argument after *args). Refusals are
        409 with a safe sentence and a code the browser can branch on; unknown ids
        404; nothing from the store's message reaches the body except through
        these fixed strings."""
        def invoke():
            return getattr(get_store(), method)(*args, CORRECTION_ACTOR, **kwargs)
        try:
            return await asyncio.to_thread(invoke)
        except HTTPException:
            raise
        except KeyError:
            raise HTTPException(404, "Item not found.") from None
        except ValueError as exc:
            from perception.episode_store import CannotLinkError
            if isinstance(exc, CannotLinkError):
                raise CorrectionRefused("cannot_link") from None
            if str(exc) == "not-ambiguous":
                raise CorrectionRefused("not_ambiguous") from None
            # Every id and the actor are validated before the store is asked, so a
            # remaining ValueError is a semantic refusal (an item linked to itself,
            # an item's only observation unlinked).
            raise CorrectionRefused("invalid_correction") from None
        except Exception:
            raise HTTPException(503, "Local memory is temporarily unavailable.") from None

    def numeric_counts(value):
        """A counts dict reduced to its finite numeric entries (no ids, no text)."""
        if not isinstance(value, dict):
            return {}
        return {key: item for key, item in value.items() if isinstance(key, str) and not isinstance(item, bool)
                and (type(item) is int or (type(item) is float and item == item and abs(item) != float("inf")))}

    async def maintain_once():
        """CP4 worker maintenance, inside processing_lock: apply_retention (which
        expires idle frames itself) then reobserve, both bounded. A failure is
        swallowed like a processing failure (durable rows stay; nothing is logged)
        and the pass still counts as run, so a broken store is retried on the
        interval rather than every second."""
        try:
            await call_store("apply_retention", limit=RETENTION_LIMIT)
            maintenance["reobservation"] = numeric_counts(await call_store("reobserve", limit=REOBS_LIMIT))
        except Exception:
            pass
        maintenance["at"] = now()

    async def process_once(maintain=False):
        nonlocal processing_stats
        # A single in-flight batch per app, not one unbounded task per episode.
        if not db_path or processing_lock.locked():
            return
        async with processing_lock:
            worked = False
            try:
                result = await call_store("process_pending", processor=processor, limit=8)
                processing_stats = {"status": "available", **{key: result[key] for key in
                    ("processed", "failed", "context_only", "observations", "pending", "context_only_total")
                    if type(result.get(key)) is int and result[key] >= 0}}
                worked = any(processing_stats.get(key, 0) > 0 for key in ("processed", "failed"))
            except Exception:
                # Durable jobs remain recoverable; never expose evidence in logs.
                processing_stats = {"status": "unavailable"}
            # Maintenance follows a batch that did work or a wake (a new packet or a
            # retained idle frame), and runs anyway once MAINTENANCE_INTERVAL of the
            # app's clock has passed since the last pass, so idle frames expire and
            # placements are re-observed with no new packets at all.
            last = maintenance["at"]
            if maintain or worked or last is None or now() - last >= MAINTENANCE_INTERVAL:
                await maintain_once()

    async def worker():
        while True:
            woken = wake.is_set()
            wake.clear()
            await process_once(maintain=woken)
            try:
                await asyncio.wait_for(wake.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(worker())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    app = FastAPI(title="PAM Local Memory", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)

    @app.exception_handler(CorrectionRefused)
    async def correction_refused(request, exc):
        return JSONResponse({"detail": CORRECTION_REFUSALS[exc.code], "code": exc.code}, status_code=409)

    @app.exception_handler(Refused)
    async def refused(request, exc):
        status, detail = REFUSALS[exc.code]
        return JSONResponse({"detail": detail, "code": exc.code}, status_code=status)

    def authenticated(request):
        t = now()
        for token, expires in list(sessions.items()):
            if expires <= t:
                sessions.pop(token, None)
        token = request.cookies.get(COOKIE, "")
        return bool(pin and token and sessions.get(token, 0) > t)

    def same_origin(request):
        origin = request.headers.get("origin")
        expected = f"{request.url.scheme}://{request.url.netloc}"
        return origin == expected

    @app.middleware("http")
    async def protect(request, call_next):
        nonlocal active_requests
        path = request.url.path
        is_api = path.startswith("/api/")
        public = path in {"/api/auth/session", "/api/auth/login"}
        # Unknown legacy endpoints remain retired, even if their original verbs changed.
        known = path in {"/api/auth/session", "/api/auth/login", "/api/auth/logout",
                         "/api/health", "/api/episodes", "/api/items", "/api/chat",
                         "/api/idle", "/api/consent", "/api/retention", "/api/erase-all", "/api/migrate",
                         "/api/telemetry", "/api/coverage"} or path.startswith("/api/items/")
        if is_api and not known:
            response = JSONResponse({"error": "Route retired."}, status_code=410)
        elif is_api and not public and not authenticated(request):
            response = JSONResponse({"error": "Sign in is required."}, status_code=401)
        elif is_api and ((request.method not in {"GET", "HEAD", "OPTIONS"} and not same_origin(request))
                         or (request.headers.get("origin") is not None and not same_origin(request))
                         or request.headers.get("sec-fetch-site") == "cross-site"):
            response = JSONResponse({"error": "Same-origin request required."}, status_code=403)
        elif is_api and active_requests >= 8:
            response = JSONResponse({"error": "Local service is busy."}, status_code=429)
        else:
            if is_api:
                active_requests += 1
            try:
                response = await call_next(request)
            except Exception:
                response = JSONResponse({"error": "Local service is temporarily unavailable."}, status_code=503)
            finally:
                if is_api:
                    active_requests -= 1
        # Every response is no-store except a manifest-listed model file, whose
        # route sets its own private cache policy (it carries no personal data).
        if not (path.startswith("/assets/models/") and "cache-control" in response.headers):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        # script-src 'wasm-unsafe-eval' (never 'unsafe-eval'): Chromium and WebKit
        # refuse WebAssembly.compile/instantiate under a bare 'self', so the hand
        # worker could never reach `ready`. worker-src 'self' pins the worker script
        # to this origin. connect-src 'self' is what blocks the MediaPipe runtime's
        # telemetry POST to https://odml.pa.googleapis.com/v1/log (attempted every
        # 60 s by vision_bundle.mjs); keep it.
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; style-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        return response

    async def body_bytes(request, maximum):
        if request.headers.get("content-encoding", "identity") != "identity":
            raise HTTPException(400, "Encoded request bodies are not supported.")
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > maximum:
                raise HTTPException(413, "Request body is too large.")
            raw.extend(chunk)
        return bytes(raw)

    async def json_body(request, fields, maximum=16384):
        try:
            value = json.loads(await body_bytes(request, maximum))
        except (ValueError, UnicodeError):
            raise HTTPException(400, "Invalid JSON body.") from None
        if not isinstance(value, dict) or set(value) - set(fields):
            raise HTTPException(400, "Invalid request fields.")
        return value

    def bounded_text(value, maximum):
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum or len(value) > maximum:
            raise HTTPException(400, "Invalid text length.")
        return value.strip()

    def item_id(value):
        if not isinstance(value, str) or not ITEM_ID.fullmatch(value):
            raise HTTPException(404, "Item not found.")
        return value

    def observation_id(value):
        if not isinstance(value, str) or not OBSERVATION_ID.fullmatch(value):
            raise HTTPException(404, "Observation not found.")
        return value

    async def empty_body(request):
        """A POST that carries no fields: an empty body or an empty JSON object."""
        raw = await body_bytes(request, 1024)
        if raw.strip():
            try:
                value = json.loads(raw)
            except (ValueError, UnicodeError):
                raise HTTPException(400, "Invalid JSON body.") from None
            if value != {}:
                raise HTTPException(400, "Invalid request fields.")

    def as_of_query(value):
        """Optional as_of query string -> epoch ms int or None (B-11 replay).
        At most 16 ASCII digits; anything else is a 400 with a safe message."""
        if value is None:
            return None
        if not isinstance(value, str) or not value.isascii() or not AS_OF_DIGITS.fullmatch(value):
            raise HTTPException(400, "Invalid as_of value.")
        return int(value)

    def as_of_body(value):
        """Optional as_of JSON field -> epoch ms int or None. A nonnegative integer
        of at most 16 digits; null means absent; anything else is a 400."""
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= AS_OF_MAX:
            raise HTTPException(400, "Invalid as_of value.")
        return value

    def models_now():
        # One read of both inventories feeds the health "models" list (browser
        # entries first, then server entries, one shape) and, through the two
        # policy helpers, the hand and identity capabilities on health AND items,
        # so the two responses cannot disagree.
        return model_inventory(models_path, register_path) + server_models_now()

    def models_synced():
        """models_now() after bringing the server-side embedder in step with the
        gate as read now, so the store's capability report that follows describes
        the embedder this inventory implies. Worker thread only (model loading)."""
        models = models_now()
        if db_path:
            get_store()
            sync_embedder(models)
        return models

    def policy(capabilities, models):
        """The store's capabilities under the server's hand and identity policies."""
        return with_hand_policy(with_identity_policy(capabilities, models, identity_state["load_error"]), models)

    def reference_image(value):
        # reference_image = {frame_id, bbox}: where the target is in the evidence image
        # (capture-resolution pixels). Present only when the store recorded one.
        return (dict(value) if isinstance(value, dict) and isinstance(value.get("frame_id"), str)
                and isinstance(value.get("bbox"), list) else None)

    def present_item(item):
        # Only the catalogue DTO crosses the boundary, never internal image paths,
        # vectors, scores or banks (a whitelist, not a scrub).
        fields = ("item_id", "name", "identity_status", "relevance", "location_status",
                  "observed_at_ms", "location_text", "stale_reason", "index_pending", "source")
        result = {key: item.get(key) for key in fields}
        # aged (B-11): the store evaluated this placement as older than AGE_STALE_MS
        # at the evaluation time (as_of or now). Always a bool, default False.
        result["aged"] = item.get("aged") is True
        result["reference_image"] = reference_image(item.get("reference_image"))
        ident = item.get("item_id", "")
        result["image_url"] = (f"/api/items/{ident}/image" if isinstance(ident, str)
                               and ITEM_ID.fullmatch(ident) else None)
        # lookalikes (CP3, B-14): the item ids this one could not be told apart from;
        # always a list (sorted, same profile), empty when the identity is settled.
        lookalikes = item.get("lookalikes")
        result["lookalikes"] = (sorted({x for x in lookalikes if isinstance(x, str) and ITEM_ID.fullmatch(x)})
                                if isinstance(lookalikes, list) else [])
        # provenance (CP3 group members only): which observation this member's
        # evidence is, and that observation's own identity status. Nothing numeric.
        provenance = item.get("provenance")
        if isinstance(provenance, dict):
            observation = provenance.get("observation_id")
            result["provenance"] = {"observation_id": observation if isinstance(observation, str) and OBSERVATION_ID.fullmatch(observation) else None,
                                    "identity_status": provenance.get("identity_status") if isinstance(provenance.get("identity_status"), str) else None}
        # CP4 fields. inference (location_status "inferred" only): the container
        # item this one is thought to be with, {container (item id),
        # container_name (its name or null), since_ms}; null otherwise.
        # stale_since_ms: when a stale location became stale (an age cut-off or
        # the negative re-observation; stale_reason then reads
        # "negative_reobservation"); null otherwise. evidence_expired: the
        # placement's packet bytes were expired by retention, so image_url will
        # 404 and reference_image is null ("evidence image expired"). The store's
        # internal last_event_ms never crosses (the whitelist above omits it).
        result["inference"] = inference(item.get("inference"))
        stale_since = item.get("stale_since_ms")
        result["stale_since_ms"] = stale_since if type(stale_since) is int and stale_since >= 0 else None
        result["evidence_expired"] = item.get("evidence_expired") is True
        return result

    def inference(value):
        if not isinstance(value, dict) or not isinstance(value.get("container"), str) or not ITEM_ID.fullmatch(value["container"]):
            return None
        since = value.get("since_ms")
        name = value.get("container_name")
        return {"container": value["container"],
                "container_name": name if isinstance(name, str) and 0 < len(name) <= 120 else None,
                "since_ms": since if type(since) is int and since >= 0 else None}

    def present_report(report, **extra):
        """An erase report (erase_item / erase_profile): counts only, never ids or
        text, and never a forensic claim: erased, already, affected_items, counts
        {name: int}, scope "logical", forensic_erasure false, plus the caller's
        fixed extras (item_id; swap for erase-all)."""
        counts = report.get("counts") if isinstance(report, dict) else None
        # The store's "embeddings" count is renamed: no response carries a key that
        # reads as an identity internal (CP3 ruling 7), even for a count.
        counts = {REPORT_COUNT_NAMES.get(key, key): value for key, value in counts.items()
                  if isinstance(key, str) and type(value) is int and value >= 0} if isinstance(counts, dict) else {}
        affected = report.get("affected_items") if isinstance(report, dict) else None
        return {"erased": isinstance(report, dict) and report.get("erased") is True,
                "already": isinstance(report, dict) and report.get("already") is True,
                "affected_items": affected if type(affected) is int and affected >= 0 else counts.get("items", 0),
                "counts": counts, "scope": "logical", "forensic_erasure": False, **extra}

    def present_retention(row):
        """The retention row: the build's consent_version, the three windows,
        updated_ms, acknowledged_version and erased_at_ms (null until set)."""
        return {key: row.get(key) for key in ("consent_version", "episodes_days", "idle_hours", "landmarks_hours",
                                              "updated_ms", "acknowledged_version", "erased_at_ms")}

    def present_consent(state):
        return {"required_version": state.get("required_version"), "acknowledged_version": state.get("acknowledged_version"),
                "ok": state.get("ok") is True}

    def present_migration(report):
        """The migrate_v1 report: status, dry_run, from_version, counts (ints),
        samples (at most 5 of the store's sample rows, fixed keys), mutates_data
        and the migrations row {migration_id, from_version, counts, at_ms, actor}.
        Nothing here is a path: legacy media are counted by the store, never named."""
        result = {"status": report.get("status"), "dry_run": report.get("dry_run") is True,
                  "from_version": report.get("from_version"), "counts": numeric_counts(report.get("counts")),
                  "mutates_data": report.get("mutates_data") is True}
        samples = report.get("samples")
        if isinstance(samples, list):
            result["samples"] = [{key: sample.get(key) for key in ("item_id", "label", "outcome", "location_text", "observed_at_ms", "identity_state", "legacy_event_id")}
                                 for sample in samples[:5] if isinstance(sample, dict)]
        migration = report.get("migration")
        if isinstance(migration, dict):
            result["migration"] = {"migration_id": migration.get("migration_id"), "from_version": migration.get("from_version"),
                                   "counts": numeric_counts(migration.get("counts")), "at_ms": migration.get("at_ms"), "actor": migration.get("actor")}
        return result

    def present_evidence(ident, row):
        """One evidence row of GET /api/items/{id}/evidence: the plan's fields plus
        candidates (item ids) and embedded (bool); image_url names the
        observation-image route. No vectors or scores. CP4: source names where
        the row came from ("local_evidence" a processed packet, "reobservation" a
        promoted idle frame, "legacy_v1" the migrated ledger)."""
        observation = row.get("observation_id")
        valid = isinstance(observation, str) and OBSERVATION_ID.fullmatch(observation) is not None
        candidates = row.get("candidates")
        source = row.get("source")
        return {"observation_id": observation if valid else None, "item_id": ident,
                "source": source if isinstance(source, str) and 0 < len(source) <= 40 and source.isascii() else "local_evidence",
                "observed_at_ms": row.get("observed_at_ms"), "frame_id": row.get("frame_id"),
                "reference_image": reference_image(row.get("reference_image")),
                "identity_status": row.get("identity_status"),
                "identity_source": row.get("identity_source") if row.get("identity_source") in ("processor", "user_assigned") else None,
                "outcome": row.get("outcome"),
                "location_text": row.get("location_text"),
                "candidates": [x for x in candidates if isinstance(x, str) and ITEM_ID.fullmatch(x)] if isinstance(candidates, list) else [],
                "embedded": row.get("embedded") is True,
                "image_url": f"/api/items/{ident}/observations/{observation}/image" if valid else None}

    def present_answer(answer):
        """The chat Answer DTO (CP5): a whitelist of exactly the resolver's keys,
        each re-validated against perception.resolver's closed vocabularies:
        shape, text, members (present_item, with provenance on group members),
        reference_image ({frame_id, bbox} or null; null for abstain),
        target_indicated (false whenever reference_image is null), capture_time_ms
        (null for abstain), identity_status, location_status, room ("room unknown"
        until a source exists), index_pending, basis (tokens from resolver.BASIS
        only, order kept, no repeats); and for clarify/group only the question,
        options and the parked observation the browser hands to .../assign.
        Nothing numeric from identity internals and no store-internal field
        crosses (a forged key in the store's answer is simply not copied)."""
        from perception.resolver import BASIS, IDENTITY_STATUSES, LOCATION_STATUSES, ROOM_UNKNOWN, SHAPES
        shape = answer.get("shape")
        if shape not in SHAPES:
            raise ValueError("Invalid answer shape")
        abstain = shape == "abstain"
        reference = None if abstain else reference_image(answer.get("reference_image"))
        capture = answer.get("capture_time_ms")
        room = answer.get("room")
        tokens = []
        for token in (answer.get("basis") if isinstance(answer.get("basis"), list) else []):
            if token in BASIS and token not in tokens:
                tokens.append(token)
        identity_status, location_status = answer.get("identity_status"), answer.get("location_status")
        result = {"shape": shape, "text": answer.get("text") if isinstance(answer.get("text"), str) else "",
                  "members": [] if abstain else [present_item(member) for member in answer.get("members", []) if isinstance(member, dict)],
                  "reference_image": reference,
                  "target_indicated": reference is not None and answer.get("target_indicated") is True,
                  "capture_time_ms": capture if not abstain and type(capture) is int and capture > 0 else None,
                  "identity_status": identity_status if not abstain and identity_status in IDENTITY_STATUSES else "unknown",
                  "location_status": location_status if not abstain and location_status in LOCATION_STATUSES else "unknown",
                  "room": room if isinstance(room, str) and 0 < len(room) <= 120 and room.isprintable() else ROOM_UNKNOWN,
                  "index_pending": answer.get("index_pending") is True,
                  "basis": tokens}
        if shape in ("clarify", "group"):
            if isinstance(answer.get("question"), str):
                result["question"] = answer["question"]
            if isinstance(answer.get("options"), list):
                result["options"] = [{"item_id": option.get("item_id"), "name": option.get("name")}
                                     for option in answer["options"] if isinstance(option, dict)
                                     and isinstance(option.get("item_id"), str) and ITEM_ID.fullmatch(option["item_id"])]
            if "unresolved_observation_id" in answer:
                unresolved = answer["unresolved_observation_id"]
                result["unresolved_observation_id"] = unresolved if isinstance(unresolved, str) and OBSERVATION_ID.fullmatch(unresolved) else None
        return result

    def utc_day(seconds):
        return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%d")

    def day_query(value):
        """The day query string -> "YYYY-MM-DD" (a real UTC calendar day) or 400;
        None (absent) -> today by the app's clock."""
        if value is None:
            return utc_day(now())
        if not isinstance(value, str) or len(value) != 10 or not value.isascii() or not DAY_UTC.fullmatch(value):
            raise HTTPException(400, "Invalid day value.")
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "Invalid day value.") from None
        return value

    def present_coverage(value, day):
        """The coverage DTO for one UTC day: the seven plan keys, the store's
        integer extras, the maintenance counters as integers (cpu seconds as
        milliseconds) and day. Every value but day is a nonnegative int; the
        store's source tag and anything else is not copied (aggregates only)."""
        source = value if isinstance(value, dict) else {}
        counters = source.get("counters") if isinstance(source.get("counters"), dict) else {}

        def count(item, scale=1):
            if isinstance(item, bool) or not isinstance(item, (int, float)) or item != item or abs(item) == float("inf"):
                return 0
            return max(0, int(round(item * scale)))
        result = {key: count(source.get(key)) for key in COVERAGE_KEYS + COVERAGE_EXTRA_KEYS}
        result.update({name: count(counters.get(name)) for name in COVERAGE_COUNTERS})
        result.update({name: count(counters.get(seconds), 1000) for name, seconds in COVERAGE_CPU.items()})
        result["day"] = day
        return result

    def zero_coverage(day):
        return present_coverage({}, day)

    def without_identity_internals(value):
        """A copy of a stored record with embedding internals removed at any depth
        (Oversight CP3 section 3.2: no route returns vectors, scores or banks)."""
        if isinstance(value, dict):
            return {key: without_identity_internals(item) for key, item in value.items()
                    if key not in {"vector", "vectors", "embedding", "embeddings", "bank", "banks", "scores"}}
        if isinstance(value, list):
            return [without_identity_internals(item) for item in value]
        return value

    @app.get("/api/auth/session")
    async def session(request: Request):
        return {"authenticated": authenticated(request), "configured": bool(pin)}

    def pin_attempt(request):
        """Charge one PIN comparison to the sign-in rate limit (5 per client and
        60 overall per minute; 429 beyond) and return the app time. Login and the
        CP4 erase-all PIN check share these counters, so neither is a cheaper way
        to guess the PIN than the other."""
        t = now()
        while global_attempts and global_attempts[0] <= t - 60:
            global_attempts.popleft()
        client = request.client.host if request.client else "unknown"
        for address, entries in list(attempts.items()):
            while entries and entries[0] <= t - 60:
                entries.popleft()
            if not entries:
                attempts.pop(address, None)
        if len(global_attempts) >= 60 or len(attempts.get(client, ())) >= 5:
            raise HTTPException(429, "Too many sign-in attempts. Try again later.")
        global_attempts.append(t)
        attempts.setdefault(client, deque()).append(t)
        return t

    @app.post("/api/auth/login")
    async def login(request: Request):
        t = pin_attempt(request)
        data = await json_body(request, {"pin"}, maximum=1024)
        supplied = data.get("pin")
        if not pin:
            raise HTTPException(503, "Local sign-in setup is required.")
        if not isinstance(supplied, str) or not hmac.compare_digest(supplied.encode(), pin.encode()):
            raise HTTPException(401, "Sign-in failed.")
        authenticated(request)  # Expire old entries before enforcing the bounded session cap.
        sessions.pop(request.cookies.get(COOKIE, ""), None)
        if len(sessions) >= 256:
            raise HTTPException(429, "Too many active sessions.")
        token = secrets.token_urlsafe(32)
        sessions[token] = t + SESSION_TTL
        response = JSONResponse({"authenticated": True})
        response.set_cookie(COOKIE, token, max_age=SESSION_TTL, httponly=True,
                            secure=request.url.scheme == "https", samesite="strict", path="/")
        return response

    @app.post("/api/auth/logout")
    async def logout(request: Request):
        sessions.pop(request.cookies.get(COOKIE, ""), None)
        response = JSONResponse({"authenticated": False})
        response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict",
                               secure=request.url.scheme == "https")
        return response

    @app.get("/api/health")
    async def health():
        """Protected status. "models" lists every manifest asset of both
        inventories (browser phone/assets/models first, then the server-side
        server/models) as {name, provisioned, licence_recorded, version} (empty
        without a manifest); "capabilities" carries the server-decided
        automatic_hand_recognition and physical_instance_recognition entries
        (hand_model_capability, identity_model_capability), identical to the ones
        /api/items returns. CP5: "coverage" is today's frame accounting, the same
        DTO GET /api/coverage returns for the app clock's UTC day."""
        models = await asyncio.to_thread(models_synced)
        capabilities = await call_store("capabilities") if db_path else []
        # CP4: "retention" is the store's live counts (retention_counts), "consent"
        # its consent state without the disclosure text, "reobservation" the counts
        # of the worker's last reobserve pass ({} before the first). "processing"
        # keeps its CP1 shape.
        # CP5: "coverage" is today's frame accounting (the same DTO as
        # GET /api/coverage for the app clock's UTC day; zeros without a store).
        today = utc_day(now())
        if db_path:
            retention = numeric_counts(await call_store("retention_counts"))
            consent = present_consent(await call_store("consent_state"))
            coverage = present_coverage(await call_store("coverage", today), today)
        else:
            retention, consent = {}, {"required_version": consent_constants()[0], "acknowledged_version": None, "ok": False}
            coverage = zero_coverage(today)
        return {"status": "ok" if db_path else "setup_required",
                "capabilities": policy(capabilities, models), "models": models,
                "processing": dict(processing_stats),
                "retention": retention, "consent": consent,
                "reobservation": dict(maintenance["reobservation"]),
                "coverage": coverage,
                "chat": {"configured": False, "enabled": False}}

    @app.post("/api/telemetry")
    async def telemetry(request: Request):
        """CP5 frame accounting: one browser telemetry window (the counters of the
        last window_ms, posted every 60 s and at stop). Protected and
        origin-checked by the middleware; the body cap MAX_TELEMETRY_BYTES is
        enforced here (413) before the store parses it (PacketTooLarge 413, any
        other ValueError 400: an unknown key, a string where a number belongs, an
        out-of-range value or an implausible clock). Not consent-gated: the window
        is numbers and two ids, never an image or text. 200 {retained: true,
        t_ms}; a resend of the same (device, session, t_ms) is idempotent."""
        raw = await body_bytes(request, MAX_TELEMETRY_BYTES)
        ack = await call_store("ingest_telemetry", raw)
        t_ms = ack.get("t_ms") if isinstance(ack, dict) else None
        return {"retained": isinstance(ack, dict) and ack.get("retained") is True,
                "t_ms": t_ms if type(t_ms) is int and t_ms >= 0 else None}

    @app.get("/api/coverage")
    async def coverage(day: str = None):
        """Frame accounting for one UTC calendar day (?day=YYYY-MM-DD; default
        today by the app's clock): the store's coverage(day) as present_coverage
        (aggregates only, every value but day an integer). 400 for a day that is
        not a real calendar date."""
        chosen = day_query(day)
        return present_coverage(await call_store("coverage", chosen), chosen)

    def consent_constants():
        """(CONSENT_VERSION, DISCLOSURE_TEXT) from perception.consent, read when a
        route needs them so importing this module stays free of perception."""
        from perception.consent import CONSENT_VERSION, DISCLOSURE_TEXT
        return CONSENT_VERSION, DISCLOSURE_TEXT

    @app.post("/api/idle")
    async def idle(request: Request):
        """CP4 idle keyframe (the browser's 30 s still while nothing happens):
        protected and origin-checked by the middleware; the body cap MAX_IDLE_BYTES
        is enforced here (413) before the store parses it (400 for anything
        malformed, 409 consent_required / erased_before). 200 with the store's
        ack: {frame_id, retained: true, expires_at_ms, evicted} or, over a cap,
        {frame_id, retained: false, reason: "idle_cap" | "idle_cache_full"}. The
        ack never echoes the frame. A retained frame wakes the worker so it is
        re-observed promptly."""
        raw = await body_bytes(request, MAX_IDLE_BYTES)
        ack = await call_store("ingest_idle", raw)
        retained = ack.get("retained") is True
        result = {"frame_id": ack.get("frame_id") if isinstance(ack.get("frame_id"), str) else None, "retained": retained}
        if retained:
            expires = ack.get("expires_at_ms")
            evicted = ack.get("evicted")
            result["expires_at_ms"] = expires if type(expires) is int else None
            result["evicted"] = evicted if type(evicted) is int and evicted >= 0 else 0
            wake.set()
        else:
            reason = ack.get("reason")
            result["reason"] = reason if reason in ("idle_cap", "idle_cache_full") else "idle_cap"
        return result

    @app.get("/api/consent")
    async def consent():
        """{required_version, acknowledged_version, ok, disclosure_text}: the
        build's consent version, what this profile acknowledged, whether capture
        is allowed, and the disclosure the Privacy view shows verbatim. Session
        required like every other route (the text itself is not personal)."""
        state = present_consent(await call_store("consent_state"))
        return {**state, "disclosure_text": consent_constants()[1]}

    @app.post("/api/consent")
    async def acknowledge(request: Request):
        """{"acknowledge": "<version>"} records that the disclosure for exactly the
        required version was shown and acknowledged (audited, actor literal) ->
        {required_version, acknowledged_version, ok}. Any other version is 400:
        a bump of the build constant makes the browser re-acknowledge."""
        data = await json_body(request, {"acknowledge"}, maximum=1024)
        version = data.get("acknowledge")
        if not isinstance(version, str) or not 1 <= len(version) <= 80 or not version.isascii():
            raise HTTPException(400, "Invalid request fields.")
        return present_consent(await call_store("acknowledge_consent", version, CORRECTION_ACTOR))

    @app.get("/api/retention")
    async def retention_get():
        """{retention: the row (consent_version, episodes_days, idle_hours,
        landmarks_hours, updated_ms, acknowledged_version, erased_at_ms), counts:
        the live counts (idle_cached, idle_promoted, revisions_expired,
        landmarks_reduced, revisions_erased)}."""
        row = present_retention(await call_store("get_retention"))
        counts = numeric_counts(await call_store("retention_counts"))
        return {"retention": row, "counts": counts}

    @app.put("/api/retention")
    async def retention_put(request: Request):
        """{episodes_days? 7..365, idle_hours? 1..72, landmarks_hours? 1..168}
        (integers, at least one) -> the row (audited with the actor literal).
        400 for an empty or invalid update, and for any other key: consent_version
        is a build constant, never a setting."""
        ranges = {"episodes_days": (7, 365), "idle_hours": (1, 72), "landmarks_hours": (1, 168)}
        data = await json_body(request, set(ranges), maximum=1024)
        if not data:
            raise HTTPException(400, "Invalid request fields.")
        for name, (low, high) in ranges.items():
            if name in data:
                value = data[name]
                if isinstance(value, bool) or type(value) is not int or not low <= value <= high:
                    raise HTTPException(400, "Invalid retention window.")
        return present_retention(await call_store("set_retention", actor=CORRECTION_ACTOR, **data))

    @app.post("/api/items/{ident}/erase")
    async def erase(ident: str, request: Request):
        """Erase this item and everything seen with it (B-07): {"confirm":
        "<item_id>"} -> the report (counts only). 400 without a string confirm,
        409 confirm_mismatch when it is not this item's id, 404 for an unknown
        item. Audited by the store with the actor literal; logical erasure, no
        forensic claim."""
        target = item_id(ident)
        data = await json_body(request, {"confirm"}, maximum=1024)
        confirm = data.get("confirm")
        if not isinstance(confirm, str):
            raise HTTPException(400, "Invalid request fields.")
        if not hmac.compare_digest(confirm.encode(), target.encode()):
            raise Refused("confirm_mismatch")
        return present_report(await call_store("erase_item", target, CORRECTION_ACTOR), item_id=target)

    @app.post("/api/erase-all")
    async def erase_all(request: Request):
        """Erase everything in the profile (B-07, P-107): {"confirm": "ERASE
        EVERYTHING", "pin": "<pin>"} -> the report. In order: 400 unless confirm
        is a string, 409 confirm_mismatch for any phrase but the exact one, 400
        unless pin is a string, then the PIN is compared in constant time under
        the sign-in rate limit (429) and 409 pin_mismatch on a mismatch. The store
        runs alone (processing_lock and the exclusive gate) because it swaps the
        database file; sessions live in memory and survive. After a success the
        browser must clear its IndexedDB mirror: anything captured before this
        instant is refused with erased_before from now on."""
        data = await json_body(request, {"confirm", "pin"}, maximum=1024)
        confirm, supplied = data.get("confirm"), data.get("pin")
        if not isinstance(confirm, str):
            raise HTTPException(400, "Invalid request fields.")
        if not hmac.compare_digest(confirm.encode(), ERASE_ALL_PHRASE.encode()):
            raise Refused("confirm_mismatch")
        if not isinstance(supplied, str):
            raise HTTPException(400, "Invalid request fields.")
        pin_attempt(request)
        if not pin:
            raise HTTPException(503, "Local sign-in setup is required.")
        if not hmac.compare_digest(supplied.encode(), pin.encode()):
            raise Refused("pin_mismatch")
        async with processing_lock:
            report = await call_store_exclusive("erase_profile", actor=CORRECTION_ACTOR, confirm=ERASE_ALL_PHRASE)
        swap = report.get("swap") if isinstance(report, dict) else None
        return present_report(report, swap=swap if swap in ("replaced", "in_place", "none") else None)

    @app.post("/api/migrate")
    async def migrate(request: Request):
        """The v1 ledger conversion (B-10): {"dry_run": true|false}, default true;
        anything but a JSON boolean is 400. A dry run reports counts and samples
        without writing. A real run additionally requires the environment variable
        PAM_ALLOW_MIGRATION to be exactly "1" (503 migration_disabled otherwise),
        is attributed to "operator", and is idempotent (status already_migrated)."""
        data = await json_body(request, {"dry_run"}, maximum=1024)
        dry_run = data.get("dry_run", True)
        if type(dry_run) is not bool:
            raise HTTPException(400, "Invalid request fields.")
        if not dry_run and os.environ.get(MIGRATION_ENV) != "1":
            raise Refused("migration_disabled")
        return present_migration(await call_store("migrate_v1", dry_run=dry_run, actor=MIGRATION_ACTOR))

    @app.post("/api/episodes")
    async def episodes(request: Request):
        raw = await body_bytes(request, MAX_EPISODE_BYTES)
        # A owns all packet validation, digests, revision rules and durable acknowledgement.
        ack = dict(await call_store("ingest_episode", raw))
        processing_status = ack.pop("processing_status", "pending")
        wake.set()
        return JSONResponse({"ack": ack, "processing": {"status": processing_status}},
                            background=BackgroundTask(process_once))

    @app.get("/api/items")
    async def items(q: str = "", limit: str = "50", as_of: str = None):
        """The catalogue. Optional as_of (epoch ms, at most 16 ASCII digits) is a
        deterministic replay (B-11): the store replays its stored decisions up to
        that time and ages placements at it, so items observed later are absent
        and no model is rerun. Invalid as_of -> 400. Capabilities carry the same
        server-decided hand policy as /api/health."""
        if len(q) > 200 or len(limit) > 3 or not limit.isascii() or not limit.isdigit() or not 1 <= int(limit) <= 100:
            raise HTTPException(400, "Invalid catalogue query.")
        at = as_of_query(as_of)
        records = await call_store("list_items", query=q, limit=int(limit), as_of=at)
        models = await asyncio.to_thread(models_synced)
        capabilities = await call_store("capabilities")
        return {"items": [present_item(record) for record in records],
                "capabilities": policy(capabilities, models)}

    @app.get("/api/items/{ident}")
    async def item(ident: str, as_of: str = None):
        """One item. Optional as_of (epoch ms, at most 16 ASCII digits) is the same
        deterministic replay as /api/items (B-11): an item first observed after
        as_of is 404 at that time. Invalid as_of -> 400."""
        at = as_of_query(as_of)
        return present_item(await call_store("get_item", item_id(ident), as_of=at))

    @app.get("/api/items/{ident}/history")
    async def history(ident: str):
        # Stored observation records minus embedding internals (match scores and
        # the like never leave the store; CP3, Oversight section 3.2).
        rows = await call_store("item_history", item_id(ident))
        return {"observations": [without_identity_internals(row) for row in rows]}

    @app.get("/api/items/{ident}/evidence")
    async def evidence(ident: str):
        """CP3: the item's observations as evidence rows, oldest first, each with
        an image_url for GET /api/items/{id}/observations/{obs}/image. 404 for an
        unknown item (or one of another profile)."""
        rows = await call_store("item_evidence", item_id(ident))
        return {"observations": [present_evidence(ident, row) for row in rows if isinstance(row, dict)]}

    @app.get("/api/items/{ident}/image")
    async def image(ident: str):
        # The stored keyframe bytes, unmodified; nothing is written to disk to serve it.
        data = await call_store("item_image", item_id(ident))
        if not data:
            raise HTTPException(404, "Image not found.")
        return Response(content=bytes(data), media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/items/{ident}/observations/{obs}/image")
    async def observation_image(ident: str, obs: str):
        """CP3: that observation's keyframe bytes, unmodified, only while the
        observation is assigned to this item in this profile (the item-image rules);
        otherwise 404, never a hint about where else it lives."""
        data = await call_store("observation_image", item_id(ident), observation_id(obs))
        if not data:
            raise HTTPException(404, "Image not found.")
        return Response(content=bytes(data), media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.post("/api/items/{ident}/name")
    async def rename(ident: str, request: Request):
        data = await json_body(request, {"name"})
        return present_item(await call_store("rename_item", item_id(ident), bounded_text(data.get("name"), 120)))

    # CP3 corrections (B-15): protected and origin-checked by the middleware like
    # rename; the actor is the server's role literal, never a request field, and the
    # bodies are bounded allowlists. Refusals: 409 {detail, code} (CorrectionRefused).
    @app.post("/api/items/{ident}/link")
    async def link(ident: str, request: Request):
        """"Same as another item": merge other_item_id into this item -> the kept
        Item. 404 unknown ids; 409 cannot_link (seen together, B-03) or
        invalid_correction (itself)."""
        keep = item_id(ident)
        data = await json_body(request, {"other_item_id"}, maximum=1024)
        other = data.get("other_item_id")
        if not isinstance(other, str):
            raise HTTPException(400, "Invalid request fields.")
        other = item_id(other)
        if other == keep:
            raise CorrectionRefused("invalid_correction")
        return present_item(await call_correction("link_items", keep, other))

    @app.post("/api/items/{ident}/observations/{obs}/unlink")
    async def unlink(ident: str, obs: str, request: Request):
        """"Not this one": move the observation out of this item into a new item
        with a cannot-link between the two -> the NEW Item. 404 when the
        observation is not this item's; 409 invalid_correction for an item's only
        observation."""
        keep, observation = item_id(ident), observation_id(obs)
        await empty_body(request)
        return present_item(await call_correction("unlink_observation", observation, item_id=keep))

    @app.post("/api/items/{ident}/observations/{obs}/assign")
    async def assign(ident: str, obs: str, request: Request):
        """"Which one is yours" -> this one: attribute a parked ambiguous
        observation (a group answer's unresolved_observation_id) to this item ->
        the Item. 404 unknown ids; 409 not_ambiguous or cannot_link."""
        target, observation = item_id(ident), observation_id(obs)
        await empty_body(request)
        return present_item(await call_correction("assign_observation", observation, target))

    @app.post("/api/chat")
    async def chat(request: Request):
        """Text chat {text, mode, as_of}. Optional as_of (nonnegative integer epoch
        ms, at most 16 digits; null = absent) evaluates the local answer at that
        time as a deterministic replay of stored decisions (B-11): placements age
        by that clock and later evidence is invisible. Invalid as_of -> 400."""
        data = await json_body(request, {"text", "mode", "as_of"})
        text = bounded_text(data.get("text"), 2000)
        mode = data.get("mode", "local")
        if not isinstance(mode, str) or mode not in {"local", "cloud"}:
            raise HTTPException(400, "Invalid chat mode.")
        at = as_of_body(data.get("as_of"))
        if mode == "cloud":
            return JSONResponse({"code": "chat_not_configured", "error": "Cloud chat is not configured with an approved bounded policy. Local memory remains available."}, status_code=503)
        # CP3: group answers pass through with per-member provenance, the question,
        # the options and the parked observation id the browser hands to .../assign.
        return present_answer(await call_store("answer_text", text, as_of=at))

    @app.get("/")
    @app.get("/memory.html")
    async def page():
        path = PHONE / "memory.html"
        if path.is_symlink() or path.resolve().parent != PHONE.resolve() or not path.is_file():
            raise HTTPException(503, "Memory interface is not installed.")
        return FileResponse(path, media_type="text/html")

    @app.get("/agent.html")
    async def old_page():
        return RedirectResponse("/", status_code=307)

    async def cute_calibration_approved():
        """True when the profile holds an approved calibration with source "cute",
        False when it does not, None when there is no store to ask (no database
        configured or the store is unavailable): the page's only store read, a
        boolean, never a number or an id."""
        if not db_path:
            return None
        try:
            rows = await call_store("list_calibrations")
        except HTTPException:
            return None
        return any(isinstance(row, dict) and row.get("source") == "cute" and row.get("approved") is True for row in rows)

    @app.api_route("/notices", methods=["GET", "HEAD"])
    async def notices():
        """Third-party notices: public (no session, not under /api/), plain HTML
        with every value escaped and no script, rendered per request from
        server/notices.json (load_notices, 503 when it is missing or invalid).
        Conditions are evaluated now: provisioned:hand and provisioned:identity
        from the two model inventories (files only, no model is loaded),
        served:tabler from TABLER_SERVED, calibration:cute from the store. No
        personal data: the only store read is the boolean above."""
        try:
            document = await asyncio.to_thread(load_notices)
        except ValueError:
            raise HTTPException(503, "Third-party notices are not installed.") from None
        models = await asyncio.to_thread(models_now)
        conditions = {"always": True,
                      "provisioned:hand": hand_runtime_provisioned(models),
                      "provisioned:identity": identity_provisioned(models),
                      "served:tabler": TABLER_SERVED,
                      "calibration:cute": await cute_calibration_approved()}
        return HTMLResponse(render_notices(document, conditions))

    @app.get("/assets/models/{name:path}")
    async def model_asset(name: str):
        """Manifest-gated model files for the hand worker (registered before the
        generic asset route so it wins the match). Served only when MANIFEST.json
        is present and valid, PAM_ENABLE_HAND_MODEL == "1", and either the name is
        MANIFEST.json itself (no-store) or the manifest lists exactly that name
        and the file resolves inside the models directory without symlinks
        (private, max-age=86400). Everything else is the generic 404.

        Public like the rest of /assets/ (no session cookie required): these are
        non-personal upstream artifacts (the pinned runtime and model bytes) that
        the worker fetches same-origin; the manifest, env flag and licence
        register are the gates, not the session.

        CP3: this route reads the browser inventory only. A server-side model
        suffix (.onnx) is refused before any lookup, so the identity model is a
        404 here even when it is provisioned and enabled on the server, and even
        if a copy were placed under the browser directory."""
        if Path(name).suffix.lower() in SERVER_MODEL_SUFFIXES:
            raise HTTPException(404, "Asset not found.")
        assets = await asyncio.to_thread(load_model_manifest, models_path)
        if assets is None or not hand_model_enabled():
            raise HTTPException(404, "Asset not found.")
        if name == MANIFEST_NAME:
            path = models_path / MANIFEST_NAME
            if path.is_symlink() or not path.is_file():
                raise HTTPException(404, "Asset not found.")
            return FileResponse(path, media_type="application/json", headers={"Cache-Control": "no-store"})
        if not any(asset["name"] == name for asset in assets):
            raise HTTPException(404, "Asset not found.")
        path = model_file(models_path, name)
        if path is None:
            raise HTTPException(404, "Asset not found.")
        return FileResponse(path, media_type=MODEL_MEDIA_TYPES[path.suffix.lower()],
                            headers={"Cache-Control": "private, max-age=86400"})

    @app.get("/assets/{name:path}")
    async def asset(name: str):
        if name not in PUBLIC_ASSETS:
            raise HTTPException(404, "File not found.")
        path = PHONE / "assets" / name
        if path.is_symlink() or not path.is_file() or path.resolve().parent != PHONE.resolve() / "assets":
            raise HTTPException(404, "File not found.")
        return FileResponse(path)

    return app


app = create_app()


def main():
    import uvicorn
    from phone.serve import CERT, KEY, ensure_cert, lan_ip
    ip = lan_ip()
    ensure_cert(ip)
    uvicorn.run(app, host="0.0.0.0", port=8443, ssl_certfile=str(CERT), ssl_keyfile=str(KEY),
                proxy_headers=False)
