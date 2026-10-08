"""Keyless local memory application. No legacy services or provider startup hooks."""
from __future__ import annotations

import asyncio
from collections import deque
from contextlib import asynccontextmanager
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from starlette.background import BackgroundTask

ROOT = Path(__file__).resolve().parents[1]
PHONE = ROOT / "phone"
MAX_EPISODE_BYTES = 4 * 1024 * 1024
SESSION_TTL = 8 * 60 * 60
COOKIE = "pam_session"
ITEM_ID = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
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
# A relative path of safe segments: no leading "/", no "..", no backslash, no
# hidden or empty segment, no control characters (the worker applies the same shape).
MODEL_NAME = re.compile(r"^(?:[A-Za-z0-9][A-Za-z0-9._-]*/)*[A-Za-z0-9][A-Za-z0-9._-]*$")
HAND_REASONS = {
    "unprovisioned": "Hand model assets are not provisioned on this server.",
    "unlicensed": "Hand model licence is not recorded as VERIFIED-COMMERCIAL in docs/LICENSES.md.",
    "disabled": "Automatic hand recognition is not enabled (PAM_ENABLE_HAND_MODEL).",
}


def _model_name(value):
    """A validated manifest asset name, or None. Exactly this name is servable."""
    if not isinstance(value, str) or not 1 <= len(value) <= MAX_MODEL_NAME or not value.isascii():
        return None
    if not MODEL_NAME.fullmatch(value) or ".." in value.split("/"):
        return None
    if Path(value).suffix.lower() not in MODEL_MEDIA_TYPES or value.rsplit("/", 1)[-1] == MANIFEST_NAME:
        return None
    return value


def _model_field(value, *, required):
    if value is None and not required:
        return None
    if not isinstance(value, str) or len(value) > MAX_MODEL_FIELD or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Invalid manifest field")
    return value


def load_model_manifest(models_dir=None):
    """The validated asset list of <models_dir>/MANIFEST.json, or None.

    None means "not provisioned": no manifest, unreadable, larger than
    MAX_MANIFEST_BYTES, not a JSON object with an "assets" list, or any entry
    invalid (fail closed: a manifest with one bad entry serves nothing). Each
    entry is {name, version, sha256, licence, url, fetched_at}: name a relative
    path validated by _model_name; version, sha256 and licence strings
    (sha256 64 lowercase hex); url and fetched_at optional strings. Nothing here
    opens a model file; only the manifest is read.
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
        name = _model_name(entry.get("name"))
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


def model_file(models_dir, name):
    """The on-disk file for a validated manifest name, or None if it is absent or
    does not resolve inside models_dir (no symlink anywhere in the chain)."""
    directory = Path(models_dir) if models_dir is not None else MODELS_DIR
    if _model_name(name) is None:
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


def model_inventory(models_dir=None, licence_register=None):
    """Health "models": one entry per manifest asset, empty when no manifest.

    provisioned: the file exists where the asset route would serve it.
    licence_recorded: the manifest entry carries a non-empty licence AND the
    licence register (docs/LICENSES.md) has a VERIFIED-COMMERCIAL row for the
    asset's base file name (licence_verified). Never includes file system paths.
    """
    assets = load_model_manifest(models_dir)
    if not assets:
        return []
    register = _licence_register_text(licence_register)
    inventory = []
    for asset in assets:
        base = asset["name"].rsplit("/", 1)[-1]
        inventory.append({"name": asset["name"],
                          "provisioned": model_file(models_dir, asset["name"]) is not None,
                          "licence_recorded": bool(asset["licence"].strip()) and licence_verified(register, base),
                          "version": asset["version"]})
    return inventory


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


def with_hand_policy(capabilities, models):
    """The store's capabilities with the hand capability replaced in place (or
    appended when the store did not report one)."""
    policy = hand_model_capability(models)
    result, replaced = [], False
    for cap in capabilities:
        if isinstance(cap, dict) and cap.get("name") == HAND_CAPABILITY:
            if not replaced:
                result.append(policy)
                replaced = True
            continue
        result.append(cap)
    if not replaced:
        result.append(policy)
    return result


def create_app(database_path=None, profile_id="local", processor=None, clock=None,
               auth_pin=None, chat_provider=None, models_dir=None, licence_register=None):
    """Construct without opening files; trusted injections belong only to this boundary.

    clock is a callable returning epoch seconds. An injected cloud provider alone
    does not authorize paid work: policy/integration approval is a separate gate.
    models_dir (default phone/assets/models) holds MANIFEST.json and the pinned
    model files; licence_register (default docs/LICENSES.md) is Oversight's
    register. Both are read per request, never at construction, and only tests
    point them elsewhere.
    """
    now = clock or time.time
    models_path = Path(models_dir) if models_dir is not None else MODELS_DIR
    register_path = Path(licence_register) if licence_register is not None else LICENCE_REGISTER
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

    def get_store():
        nonlocal store
        if not db_path:
            raise HTTPException(503, "Local memory storage is not configured.")
        with store_lock:
            if store is None:
                from perception.object_memory import ObjectStore
                store = ObjectStore(db_path, profile_id=profile_id, clock=now)
            return store

    async def call_store(method, *args, **kwargs):
        def invoke():
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
            raise HTTPException(400, "Invalid memory request.") from None
        except Exception:
            raise HTTPException(503, "Local memory is temporarily unavailable.") from None

    async def process_once():
        nonlocal processing_stats
        # A single in-flight batch per app, not one unbounded task per episode.
        if not db_path or processing_lock.locked():
            return
        async with processing_lock:
            try:
                result = await call_store("process_pending", processor=processor, limit=8)
                processing_stats = {"status": "available", **{key: result[key] for key in
                    ("processed", "failed", "context_only", "observations", "pending", "context_only_total")
                    if type(result.get(key)) is int and result[key] >= 0}}
            except Exception:
                # Durable jobs remain recoverable; never expose evidence in logs.
                processing_stats = {"status": "unavailable"}

    async def worker():
        while True:
            wake.clear()
            await process_once()
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
                         "/api/health", "/api/episodes", "/api/items", "/api/chat"} or path.startswith("/api/items/")
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
        if not ITEM_ID.fullmatch(value):
            raise HTTPException(404, "Item not found.")
        return value

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
        # One inventory read feeds both the health "models" list and, through
        # with_hand_policy/hand_model_capability, the hand capability on health
        # AND items, so the two responses cannot disagree.
        return model_inventory(models_path, register_path)

    def present_item(item):
        # Only the catalogue DTO crosses the boundary, never internal image paths.
        fields = ("item_id", "name", "identity_status", "relevance", "location_status",
                  "observed_at_ms", "location_text", "stale_reason", "index_pending", "source")
        result = {key: item.get(key) for key in fields}
        # aged (B-11): the store evaluated this placement as older than AGE_STALE_MS
        # at the evaluation time (as_of or now). Always a bool, default False.
        result["aged"] = item.get("aged") is True
        # reference_image = {frame_id, bbox}: where the target is in the evidence image
        # (capture-resolution pixels). Present only when the store recorded one.
        reference = item.get("reference_image")
        result["reference_image"] = (dict(reference) if isinstance(reference, dict)
                                     and isinstance(reference.get("frame_id"), str)
                                     and isinstance(reference.get("bbox"), list) else None)
        ident = item.get("item_id", "")
        result["image_url"] = (f"/api/items/{ident}/image" if isinstance(ident, str)
                               and ITEM_ID.fullmatch(ident) else None)
        return result

    @app.get("/api/auth/session")
    async def session(request: Request):
        return {"authenticated": authenticated(request), "configured": bool(pin)}

    @app.post("/api/auth/login")
    async def login(request: Request):
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
        """Protected status. "models" lists every manifest asset as
        {name, provisioned, licence_recorded, version} (empty without a manifest);
        "capabilities" carries the server-decided automatic_hand_recognition entry
        (hand_model_capability), identical to the one /api/items returns."""
        capabilities = await call_store("capabilities") if db_path else []
        models = await asyncio.to_thread(models_now)
        return {"status": "ok" if db_path else "setup_required",
                "capabilities": with_hand_policy(capabilities, models), "models": models,
                "processing": dict(processing_stats),
                "chat": {"configured": False, "enabled": False}}

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
        capabilities = await call_store("capabilities")
        models = await asyncio.to_thread(models_now)
        return {"items": [present_item(record) for record in records],
                "capabilities": with_hand_policy(capabilities, models)}

    @app.get("/api/items/{ident}")
    async def item(ident: str, as_of: str = None):
        """One item. Optional as_of (epoch ms, at most 16 ASCII digits) is the same
        deterministic replay as /api/items (B-11): an item first observed after
        as_of is 404 at that time. Invalid as_of -> 400."""
        at = as_of_query(as_of)
        return present_item(await call_store("get_item", item_id(ident), as_of=at))

    @app.get("/api/items/{ident}/history")
    async def history(ident: str):
        return {"observations": await call_store("item_history", item_id(ident))}

    @app.get("/api/items/{ident}/image")
    async def image(ident: str):
        # The stored keyframe bytes, unmodified; nothing is written to disk to serve it.
        data = await call_store("item_image", item_id(ident))
        if not data:
            raise HTTPException(404, "Image not found.")
        return Response(content=bytes(data), media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.post("/api/items/{ident}/name")
    async def rename(ident: str, request: Request):
        data = await json_body(request, {"name"})
        return present_item(await call_store("rename_item", item_id(ident), bounded_text(data.get("name"), 120)))

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
        answer = await call_store("answer_text", text, as_of=at)
        answer["members"] = [present_item(member) for member in answer.get("members", [])]
        return answer

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
        register are the gates, not the session."""
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
