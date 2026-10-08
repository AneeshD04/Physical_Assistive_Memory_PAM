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
# Explicit public resources, never a directory mount or extension-only whitelist.
# Exactly the files phone/memory.html and its module graph load. The bootstrap
# suite walks that graph through this app, so a module C adds must be listed
# here or the page fails to load at the supported entry point.
PUBLIC_ASSETS = frozenset({
    "memory.css", "memory.js", "memory-camera.js", "memory-queue.js",
    "controller.js", "grayscale-jpeg.js", "pam-logo.png",
})


def create_app(database_path=None, profile_id="local", processor=None, clock=None,
               auth_pin=None, chat_provider=None):
    """Construct without opening files; trusted injections belong only to this boundary.

    clock is a callable returning epoch seconds. An injected cloud provider alone
    does not authorize paid work: policy/integration approval is a separate gate.
    """
    now = clock or time.time
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
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
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

    def present_item(item):
        # Only the catalogue DTO crosses the boundary, never internal image paths.
        fields = ("item_id", "name", "identity_status", "relevance", "location_status",
                  "observed_at_ms", "location_text", "stale_reason", "index_pending", "source")
        result = {key: item.get(key) for key in fields}
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
        capabilities = await call_store("capabilities") if db_path else []
        return {"status": "ok" if db_path else "setup_required", "capabilities": capabilities,
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
    async def items(q: str = "", limit: str = "50"):
        if len(q) > 200 or len(limit) > 3 or not limit.isascii() or not limit.isdigit() or not 1 <= int(limit) <= 100:
            raise HTTPException(400, "Invalid catalogue query.")
        records = await call_store("list_items", query=q, limit=int(limit))
        return {"items": [present_item(record) for record in records],
                "capabilities": await call_store("capabilities")}

    @app.get("/api/items/{ident}")
    async def item(ident: str):
        return present_item(await call_store("get_item", item_id(ident)))

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
        data = await json_body(request, {"text", "mode"})
        text = bounded_text(data.get("text"), 2000)
        mode = data.get("mode", "local")
        if not isinstance(mode, str) or mode not in {"local", "cloud"}:
            raise HTTPException(400, "Invalid chat mode.")
        if mode == "cloud":
            return JSONResponse({"code": "chat_not_configured", "error": "Cloud chat is not configured with an approved bounded policy. Local memory remains available."}, status_code=503)
        answer = await call_store("answer_text", text)
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
