#!/usr/bin/env python3
"""Download pinned model assets into phone/assets/models/ and write MANIFEST.json.

Usage (run explicitly by an operator; never by tests or at app startup):

    python3 scripts/fetch_models.py --dry-run                 # validate pins + licence register, no network
    python3 scripts/fetch_models.py                           # fetch every pinned asset
    python3 scripts/fetch_models.py --only hand_landmarker.task --only vision_bundle.mjs
    python3 scripts/fetch_models.py --pins scripts/model_pins.json \
        --models-dir phone/assets/models --licences docs/LICENSES.md

Rules (CP2 build plan, G-PROV):
  * Standard library only (argparse, hashlib, json, urllib). No new dependency.
  * An entry is downloaded only when its pin has an https url, a 64-hex sha256,
    a version and a licence, AND docs/LICENSES.md (Oversight's register) has a
    line that names the asset's base file name together with the literal
    `VERIFIED-COMMERCIAL` status token (and no UNVERIFIED/REJECTED token) and
    that licence identifier. A null sha256 or url is a refusal, never a guess.
    Refusals are per entry: the other pins still proceed, so the verified
    runtime can be fetched while an unverified model stays blocked.
  * Bytes are streamed to a temporary file inside the models directory, hashed
    on the way, verified against the pin, then moved into place atomically. A
    hash mismatch discards the download. An existing file with a different hash
    is never overwritten (refusal); one with the matching hash is kept.
  * MANIFEST.json lists only files that exist on disk with a verified hash, as
    {"assets": [{name, version, sha256, url, licence, fetched_at}]}. It is written
    atomically and is what server/memory_app.load_model_manifest validates.
  * Output names files, sizes and statuses only; it prints no credentials and no
    response bodies. Pinned URLs are public artifacts (printed as host only).

Exit status: 0 every selected asset present and verified; 1 a download or hash
failed; 2 at least one pin or licence refusal (refused entries are never
downloaded; the others may still have been fetched and manifested).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PINS = ROOT / "scripts" / "model_pins.json"
DEFAULT_MODELS_DIR = ROOT / "phone" / "assets" / "models"
DEFAULT_LICENCES = ROOT / "docs" / "LICENSES.md"
MANIFEST_NAME = "MANIFEST.json"
MAX_ASSET_BYTES = 256 * 1024 * 1024
MAX_PINS_BYTES = 256 * 1024
MAX_LICENCES_BYTES = 1024 * 1024
CHUNK = 1024 * 1024
TIMEOUT_S = 60
ALLOWED_SUFFIXES = {".task", ".wasm", ".js", ".mjs", ".cjs", ".json"}
# Mirrors server/memory_app.MODEL_NAME: relative path of safe segments, no "..",
# no leading "/", no backslash, no hidden segment, at most 120 characters.
ASSET_NAME = re.compile(r"^(?:[A-Za-z0-9][A-Za-z0-9._-]*/)*[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
# Mirrors server/memory_app.licence_verified: docs/LICENSES.md rule 2 puts exactly
# one status token on each asset row, on the same line as the base file name.
VERIFIED_TOKEN = "VERIFIED-COMMERCIAL"
BLOCKING_TOKENS = ("UNVERIFIED", "REJECTED")


class Refusal(Exception):
    """A pin or licence problem: the entry is not downloaded."""


class HttpsOnlyRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise urllib.error.URLError("redirect to a non-https URL refused")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def valid_name(name) -> bool:
    return (isinstance(name, str) and 1 <= len(name) <= 120 and name.isascii()
            and bool(ASSET_NAME.fullmatch(name)) and ".." not in name.split("/")
            and Path(name).suffix.lower() in ALLOWED_SUFFIXES
            and name.rsplit("/", 1)[-1] != MANIFEST_NAME)


def read_text_bounded(path: Path, limit: int) -> str:
    if path.is_symlink() or not path.is_file():
        raise Refusal(f"{path.name} is missing")
    with open(path, "rb") as handle:
        raw = handle.read(limit + 1)
    if len(raw) > limit:
        raise Refusal(f"{path.name} is larger than {limit} bytes")
    return raw.decode("utf-8")


def load_pins(path: Path) -> list[dict]:
    try:
        pins = json.loads(read_text_bounded(path, MAX_PINS_BYTES))
    except (OSError, ValueError, UnicodeError) as exc:
        raise Refusal(f"pin file is unreadable: {type(exc).__name__}") from None
    if not isinstance(pins, dict) or not isinstance(pins.get("assets"), list):
        raise Refusal('pin file must be a JSON object with an "assets" list')
    if not all(isinstance(entry, dict) for entry in pins["assets"]):
        raise Refusal("every pin must be a JSON object")
    return pins["assets"]


def check_pin(entry: dict, register: str) -> dict:
    """The validated pin fields, or a Refusal naming the first problem."""
    name = entry.get("name")
    if not valid_name(name):
        raise Refusal("invalid asset name (relative path, safe characters, allowed suffix)")
    base = name.rsplit("/", 1)[-1]
    version = entry.get("version")
    if not isinstance(version, str) or not version.strip() or len(version) > 200:
        raise Refusal("version is not pinned (fill it from the primary source)")
    licence = entry.get("licence")
    if not isinstance(licence, str) or not licence.strip() or len(licence) > 200:
        raise Refusal("licence identifier is missing")
    url = entry.get("url")
    if not isinstance(url, str) or urllib.parse.urlsplit(url).scheme != "https" or not urllib.parse.urlsplit(url).netloc:
        raise Refusal("url is null or not https (Oversight fills it after the licence verdict)")
    sha256 = entry.get("sha256")
    if not isinstance(sha256, str) or not SHA256.fullmatch(sha256.lower()):
        raise Refusal("sha256 is null or not 64 hex characters (never guessed; computed from the pinned artifact)")
    rows = [line for line in register.splitlines() if base in line]
    if not rows:
        raise Refusal(f"docs/LICENSES.md does not record {base}")
    verified = [line for line in rows if VERIFIED_TOKEN in line and not any(token in line for token in BLOCKING_TOKENS)]
    if not verified:
        raise Refusal(f"docs/LICENSES.md has no {VERIFIED_TOKEN} row for {base}")
    if not any(licence in line for line in verified):
        raise Refusal(f"docs/LICENSES.md does not list the licence {licence} on the {VERIFIED_TOKEN} row for {base}")
    return {"name": name, "version": version.strip(), "url": url, "sha256": sha256.lower(), "licence": licence.strip()}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, expected: str) -> int:
    """Stream url into destination (atomic), verifying the SHA-256. Returns bytes."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(HttpsOnlyRedirects)
    request = urllib.request.Request(url, headers={"User-Agent": "pam-fetch-models/1"})
    digest = hashlib.sha256()
    size = 0
    fd, temp_name = tempfile.mkstemp(prefix=".fetch-", dir=str(destination.parent))
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as out, opener.open(request, timeout=TIMEOUT_S) as response:
            if response.status != 200:
                raise RuntimeError(f"HTTP {response.status}")
            while True:
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_ASSET_BYTES:
                    raise RuntimeError("asset exceeds the size cap")
                digest.update(chunk)
                out.write(chunk)
        if digest.hexdigest() != expected:
            raise RuntimeError("SHA-256 mismatch; download discarded")
        os.chmod(temp, 0o644)
        os.replace(temp, destination)
    except BaseException:
        try:
            temp.unlink()
        except OSError:
            pass
        raise
    return size


def previous_manifest(models_dir: Path) -> dict:
    path = models_dir / MANIFEST_NAME
    try:
        manifest = json.loads(read_text_bounded(path, 64 * 1024))
        entries = manifest.get("assets") if isinstance(manifest, dict) else None
        return {entry["name"]: entry for entry in entries if isinstance(entry, dict) and isinstance(entry.get("name"), str)} if isinstance(entries, list) else {}
    except (Refusal, OSError, ValueError, UnicodeError, KeyError, TypeError):
        return {}


def write_manifest(models_dir: Path, assets: list[dict]) -> None:
    body = json.dumps({"schema_version": 1, "generated_by": "scripts/fetch_models.py", "assets": assets},
                      indent=2, sort_keys=True) + "\n"
    fd, temp_name = tempfile.mkstemp(prefix=".manifest-", dir=str(models_dir))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(body)
        os.chmod(temp_name, 0o644)
        os.replace(temp_name, models_dir / MANIFEST_NAME)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pins", type=Path, default=DEFAULT_PINS, help="pin file (default scripts/model_pins.json)")
    ap.add_argument("--models-dir", type=Path, default=DEFAULT_MODELS_DIR, help="destination (default phone/assets/models)")
    ap.add_argument("--licences", type=Path, default=DEFAULT_LICENCES, help="licence register (default docs/LICENSES.md)")
    ap.add_argument("--only", action="append", default=[], metavar="NAME", help="fetch only this pinned asset (repeatable)")
    ap.add_argument("--dry-run", action="store_true", help="validate pins and licences; no network, no writes")
    args = ap.parse_args(argv)

    try:
        pins = load_pins(args.pins)
        register = read_text_bounded(args.licences, MAX_LICENCES_BYTES)
    except Refusal as exc:
        print(f"refused: {exc}")
        return 2
    selected = [entry for entry in pins if not args.only or entry.get("name") in args.only]
    missing = sorted(set(args.only) - {entry.get("name") for entry in pins})
    if missing:
        print("refused: not pinned: " + ", ".join(missing))
        return 2
    if not selected:
        print("refused: no assets selected")
        return 2

    # Refusals are per entry (printed first, never downloaded); the remaining pins
    # proceed so a verified runtime is not held hostage by an unverified model.
    checked, refused = [], []
    for entry in selected:
        try:
            checked.append(check_pin(entry, register))
        except Refusal as exc:
            refused.append((str(entry.get("name", "?"))[:120], str(exc)))
    for name, reason in refused:
        print(f"refused  {name}: {reason}")
    if not checked:
        return 2

    models_dir = args.models_dir
    previous = previous_manifest(models_dir)
    failures = 0
    manifest_assets = []
    for pin in checked:
        destination = models_dir / pin["name"]
        host = urllib.parse.urlsplit(pin["url"]).netloc
        status = None
        if destination.is_symlink():
            print(f"refused  {pin['name']}: destination is a symlink")
            failures += 1
            continue
        if destination.is_file():
            if file_sha256(destination) == pin["sha256"]:
                status = ("present", destination.stat().st_size)
            else:
                print(f"refused  {pin['name']}: an existing file has a different SHA-256; not overwritten")
                failures += 1
                continue
        elif args.dry_run:
            print(f"would fetch  {pin['name']} from {host} ({pin['licence']}, version {pin['version']})")
            continue
        else:
            try:
                size = download(pin["url"], destination, pin["sha256"])
            except (urllib.error.URLError, OSError, RuntimeError, ValueError) as exc:
                print(f"failed   {pin['name']}: {type(exc).__name__}: {str(exc)[:120]}")
                failures += 1
                continue
            status = ("fetched", size)
        fetched_at = previous.get(pin["name"], {}).get("fetched_at") if status[0] == "present" else None
        if not isinstance(fetched_at, str):
            fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        manifest_assets.append({"name": pin["name"], "version": pin["version"], "sha256": pin["sha256"],
                                "url": pin["url"], "licence": pin["licence"], "fetched_at": fetched_at})
        print(f"{status[0]:<8} {pin['name']} ({status[1]} bytes, verified)")

    exit_code = 2 if refused else (1 if failures else 0)
    if args.dry_run:
        print("dry run: nothing downloaded, manifest unchanged")
        return exit_code
    # Keep previously manifested assets that are still present and verified but
    # were not selected this run, so --only never drops the other files. An asset
    # refused in this run (for example a register row that lost its verified
    # status) is dropped even if its file is present, so the server stops serving it.
    listed = {asset["name"] for asset in manifest_assets} | {name for name, _ in refused}
    for name, entry in previous.items():
        path = models_dir / name
        if name in listed or not valid_name(name) or path.is_symlink() or not path.is_file():
            continue
        strings = all(isinstance(entry.get(key), str) for key in ("version", "sha256", "licence"))
        optional = all(entry.get(key) is None or isinstance(entry.get(key), str) for key in ("url", "fetched_at"))
        if strings and optional and SHA256.fullmatch(entry["sha256"]) and file_sha256(path) == entry["sha256"]:
            manifest_assets.append({key: entry.get(key) for key in ("name", "version", "sha256", "url", "licence", "fetched_at")})
    # The manifest always reflects exactly the verified files on disk at the end
    # of a run: a tampered or missing file drops out, so the server stops serving it.
    if manifest_assets or models_dir.is_dir():
        models_dir.mkdir(parents=True, exist_ok=True)
        write_manifest(models_dir, sorted(manifest_assets, key=lambda asset: asset["name"]))
        print(f"wrote {MANIFEST_NAME} with {len(manifest_assets)} asset(s)")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
