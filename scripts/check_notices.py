"""Keep server/notices.json in sync with the licence register (CP5, Builder B).

    python3 -B scripts/check_notices.py              # drift between the two files -> exit 1
    python3 -B scripts/check_notices.py --installed  # also compare the Python pins with this environment

The register (docs/LICENSES.md section 8) is the source; server/notices.json is
derived; this script fails when they disagree in either direction
(docs/OVERSIGHT_CP5.md section 3.4). The served app never reads docs/ at runtime:
its startup self-check (server.memory_app.load_notices) validates only the shape
of notices.json, and this script is where the expected list is enforced. Checks:

  1. the fenced ```json notices-expected block parses and lists unique components;
  2. the set of `component` names is equal in both files (missing / extra listed);
  3. per component: `licence` and `condition` equal, `version` equal to the
     register's pin; for the asset rows also equal to scripts/model_pins.json;
  4. every notice_text is non-empty, carries the identifying first line of each
     licence in its SPDX expression (Apache License / MIT License / BSD
     "Redistributions of source code" / GNU LESSER GENERAL PUBLIC LICENSE /
     Attribution 4.0 International / PYTHON SOFTWARE FOUNDATION LICENSE), the
     register's `copyright` line, and, when the register names a bundled
     third-party file with its SHA-256, a reproduced copy of that file whose
     bytes hash to that value;
  5. no component is named on a register line that carries UNVERIFIED or
     REJECTED without VERIFIED-COMMERCIAL (the row-structured read of
     server.memory_app.licence_verified, against the notices component name);
  6. with --installed: importlib.metadata.version() of every Python component
     equals the pin, else "update docs/LICENSES.md section 1, section 8 and
     server/notices.json together".

Exit status 0 when everything agrees, 1 on any drift; one line per finding.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REGISTER = ROOT / "docs" / "LICENSES.md"
NOTICES = ROOT / "server" / "notices.json"
PINS = ROOT / "scripts" / "model_pins.json"
MAX_REGISTER_BYTES = 1024 * 1024
FENCE = re.compile(r"^```json notices-expected\s*$")
# The identifying line each SPDX identifier's text must carry (OVERSIGHT_CP5 section 3.4 item 2).
LICENCE_MARKERS = {
    "Apache-2.0": ("Apache License",),
    "MIT": ("MIT License",),
    "BSD-3-Clause": ("Redistributions of source code",),
    "BSD-2-Clause": ("Redistributions of source code",),
    "LGPL-2.1-only": ("GNU LESSER GENERAL PUBLIC LICENSE",),
    "CC-BY-4.0": ("Attribution 4.0 International",),
    "PSF-2.0": ("PYTHON SOFTWARE FOUNDATION LICENSE",),
}
# Components that are not Python distributions (no importlib.metadata version).
ASSET_COMPONENTS = {"@mediapipe/tasks-vision": "vision_bundle.mjs", "dinov2_vits14.onnx": "dinov2_vits14.onnx"}
NON_PYTHON = set(ASSET_COMPONENTS) | {"tabler-icons", "CUTE"}
MESSAGE = "update docs/LICENSES.md section 1, section 8 and server/notices.json together"
BLOCK_HEADER = re.compile(r"^---- (?P<title>.+?) \((?P<origin>.*); (?P<size>[0-9,]+) bytes; SHA-256 (?P<sha>[0-9a-f]{64})\) ----$", re.M)


def expected_entries(register_text):
    """The parsed `notices-expected` list of the register, or a ValueError."""
    lines = register_text.splitlines()
    for index, line in enumerate(lines):
        if FENCE.match(line):
            body = []
            for inner in lines[index + 1:]:
                if inner.startswith("```"):
                    break
                body.append(inner)
            else:
                raise ValueError("notices-expected block is not closed")
            entries = json.loads("\n".join(body))
            if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
                raise ValueError("notices-expected block is not a list of objects")
            return entries
    raise ValueError("docs/LICENSES.md has no ```json notices-expected block")


def embedded_blocks(notice_text):
    """{title: (sha_in_header, bytes)} of every reproduced file in a notice_text."""
    blocks = {}
    for match in BLOCK_HEADER.finditer(notice_text):
        title = match.group("title")
        end = notice_text.find(f"\n---- end of {title} ----", match.end())
        if end < 0:
            continue
        segment = notice_text[match.end() + 1:end]
        blocks[title] = (match.group("sha"), segment)
    return blocks


def names_on_line(line, component):
    """True when the register line names the component as a token (not inside
    another identifier), case-insensitive."""
    pattern = r"(?<![A-Za-z0-9_@./-])" + re.escape(component) + r"(?![A-Za-z0-9_./-])"
    return re.search(pattern, line, re.IGNORECASE) is not None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--installed", action="store_true", help="also compare the Python pins with importlib.metadata")
    args = parser.parse_args(argv)
    findings = []

    def finding(text):
        findings.append(text)
        print("DRIFT " + text)

    try:
        register_text = REGISTER.read_bytes()[:MAX_REGISTER_BYTES].decode("utf-8", "replace")
        expected = expected_entries(register_text)
    except (OSError, ValueError) as exc:
        print(f"DRIFT register unreadable: {exc}")
        return 1
    try:
        from server.memory_app import LICENCE_BLOCKING_TOKENS, LICENCE_VERIFIED_TOKEN, load_notices
        document = load_notices(NOTICES)
    except ValueError as exc:
        print(f"DRIFT server/notices.json fails the app's startup self-check: {exc}")
        return 1
    actual = {entry["component"]: entry for entry in document["components"]}
    wanted = {}
    for entry in expected:
        name = entry.get("component")
        if not isinstance(name, str) or name in wanted:
            finding(f"register entry without a unique component name: {entry}")
            continue
        wanted[name] = entry
    for name in sorted(set(wanted) - set(actual)):
        finding(f"{name}: in the register's expected list but not in server/notices.json")
    for name in sorted(set(actual) - set(wanted)):
        finding(f"{name}: in server/notices.json but not in the register's expected list")
    try:
        pins = {asset["name"]: asset.get("version") for asset in json.loads(PINS.read_text(encoding="utf-8"))["assets"]}
    except (OSError, ValueError, KeyError, TypeError):
        pins = {}
        finding("scripts/model_pins.json unreadable")
    register_lines = register_text.splitlines()
    for name in sorted(set(wanted) & set(actual)):
        want, have = wanted[name], actual[name]
        for key in ("licence", "condition", "version"):
            if want.get(key) != have[key]:
                finding(f"{name}: {key} is {have[key]!r} in server/notices.json but {want.get(key)!r} in the register ({MESSAGE})")
        if name in ASSET_COMPONENTS:
            pinned = pins.get(ASSET_COMPONENTS[name])
            if pinned != have["version"]:
                finding(f"{name}: version {have['version']!r} differs from scripts/model_pins.json {pinned!r}")
        text = have["notice_text"]
        if not text.strip():
            finding(f"{name}: notice_text is empty")
        for identifier in re.split(r"\s+(?:AND|OR)\s+", have["licence"]):
            markers = LICENCE_MARKERS.get(identifier)
            if markers is None:
                finding(f"{name}: licence identifier {identifier!r} has no known identifying line")
            elif not any(marker in text for marker in markers):
                finding(f"{name}: notice_text lacks the {identifier} identifying line {markers[0]!r}")
        copyright_line = want.get("copyright")
        if isinstance(copyright_line, str) and copyright_line not in text:
            finding(f"{name}: notice_text lacks the register's copyright line {copyright_line!r}")
        third_party = want.get("third_party_file")
        if isinstance(third_party, str):
            blocks = {title.rsplit("/", 1)[-1]: value for title, value in embedded_blocks(text).items()}
            if third_party not in blocks:
                finding(f"{name}: notice_text does not reproduce {third_party}")
            else:
                header_sha, segment = blocks[third_party]
                digests = {hashlib.sha256(segment.encode("utf-8")).hexdigest(), hashlib.sha256((segment + "\n").encode("utf-8")).hexdigest()}
                recorded = want.get("third_party_sha256") or header_sha
                if recorded not in digests:
                    finding(f"{name}: the reproduced {third_party} does not hash to {recorded[:12]}... (register / block header)")
                elif isinstance(want.get("third_party_sha256"), str) and header_sha != want["third_party_sha256"]:
                    finding(f"{name}: the block header records SHA-256 {header_sha[:12]}... but the register says {want['third_party_sha256'][:12]}...")
        for line in register_lines:
            if names_on_line(line, name) and any(token in line for token in LICENCE_BLOCKING_TOKENS) and LICENCE_VERIFIED_TOKEN not in line:
                finding(f"{name}: a register line naming it carries UNVERIFIED/REJECTED: {line.strip()[:90]!r}")
                break
        if args.installed and name not in NON_PYTHON:
            try:
                installed = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                installed = None
            if installed != have["version"]:
                finding(f"{name}: installed {installed!r} but pinned {have['version']!r} ({MESSAGE})")
    print(f"checked {len(wanted)} expected / {len(actual)} actual components; {len(findings)} finding(s)")
    print("NOTICES SYNC", "FAILED" if findings else "OK")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
