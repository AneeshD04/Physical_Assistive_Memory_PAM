"""Additive keyless episode ledger. Legacy v1 records are never reinterpreted.

Evidence/decisions are append-only through ordinary APIs. Redaction is a separate,
audited logical erasure, not a promise about filesystem remnants or backups.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import uuid

try:
    from .episode import parse_packet, jpeg_bytes, RevisionLimitError
    from .localizer import LocalObservation, localize
    from .private_files import private_append_fd
except ImportError:
    from episode import parse_packet, jpeg_bytes, RevisionLimitError
    from localizer import LocalObservation, localize
    from private_files import private_append_fd


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


EPISODE_SCHEMA = """
CREATE TABLE IF NOT EXISTS episode_revisions (
 profile_id TEXT NOT NULL, device_id TEXT NOT NULL, episode_id TEXT NOT NULL,
 revision_no INTEGER NOT NULL, semantic_digest TEXT NOT NULL, transport_digest TEXT NOT NULL,
 packet BLOB, received_at_ms INTEGER NOT NULL, accepted INTEGER NOT NULL,
 clock_status TEXT NOT NULL, redacted INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(profile_id,device_id,episode_id,revision_no),
 UNIQUE(profile_id,device_id,episode_id,semantic_digest));
CREATE TABLE IF NOT EXISTS episode_jobs (
 profile_id TEXT NOT NULL, device_id TEXT NOT NULL, episode_id TEXT NOT NULL,
 revision_no INTEGER NOT NULL, status TEXT NOT NULL, token TEXT, lease_until REAL,
 attempts INTEGER NOT NULL DEFAULT 0, result_count INTEGER NOT NULL DEFAULT 0, error TEXT,
 PRIMARY KEY(profile_id,device_id,episode_id,revision_no),
 FOREIGN KEY(profile_id,device_id,episode_id,revision_no)
 REFERENCES episode_revisions(profile_id,device_id,episode_id,revision_no));
CREATE TABLE IF NOT EXISTS local_observations (
 profile_id TEXT NOT NULL, observation_id TEXT NOT NULL, item_id TEXT NOT NULL,
 device_id TEXT NOT NULL, episode_id TEXT NOT NULL, revision_no INTEGER NOT NULL,
 observed_at_ms INTEGER NOT NULL, decided_at_ms INTEGER NOT NULL, record TEXT,
 PRIMARY KEY(profile_id,observation_id),
 FOREIGN KEY(profile_id,device_id,episode_id,revision_no)
 REFERENCES episode_revisions(profile_id,device_id,episode_id,revision_no));
CREATE INDEX IF NOT EXISTS local_observations_item
 ON local_observations(profile_id,item_id,observed_at_ms);
CREATE TABLE IF NOT EXISTS current_items (
 profile_id TEXT NOT NULL, item_id TEXT NOT NULL, record TEXT NOT NULL,
 PRIMARY KEY(profile_id,item_id));
CREATE TABLE IF NOT EXISTS item_names (
 profile_id TEXT NOT NULL, name_id INTEGER PRIMARY KEY AUTOINCREMENT,
 item_id TEXT NOT NULL, at_ms INTEGER NOT NULL, name TEXT);
CREATE TABLE IF NOT EXISTS episode_tombstones (
 profile_id TEXT NOT NULL, device_id TEXT NOT NULL, episode_id TEXT NOT NULL,
 at_ms INTEGER NOT NULL, PRIMARY KEY(profile_id,device_id,episode_id));
CREATE TABLE IF NOT EXISTS item_tombstones (
 profile_id TEXT NOT NULL, item_id TEXT NOT NULL, at_ms INTEGER NOT NULL,
 PRIMARY KEY(profile_id,item_id));
CREATE TABLE IF NOT EXISTS local_audit (
 audit_id INTEGER PRIMARY KEY AUTOINCREMENT, profile_id TEXT NOT NULL,
 at_ms INTEGER NOT NULL, action TEXT NOT NULL, item_id TEXT, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS local_cannot_links (
 profile_id TEXT NOT NULL, item_a TEXT NOT NULL, item_b TEXT NOT NULL,
 PRIMARY KEY(profile_id,item_a,item_b));
"""


def _superset(old, new):
    for field in ("schema_version", "episode_id", "device_id", "session_id", "clock_anchor", "capture", "analysis", "capture_mode"):
        if old[field] != new[field]:
            return False
    if new["t_start_ms"] > old["t_start_ms"] or new["t_end_ms"] < old["t_end_ms"]:
        return False
    for field in ("keyframes", "carry_burst", "landmarks", "gaps"):
        values = {_json(value) for value in new[field]}
        if not all(_json(value) in values for value in old[field]):
            return False
    return True


class EpisodeStoreMixin:
    def _now_ms(self):
        return int(self.clock() * 1000)

    def capabilities(self) -> list[dict]:
        return [
            {"name": "local_processing", "enabled": True, "reason": "OpenCV registered image differences; provisional regions only"},
            {"name": "local_text_chat", "enabled": True, "reason": "Stored evidence lookup; no provider required"},
            {"name": "automatic_hand_recognition", "enabled": False, "reason": "No cleared hand model enabled; manual marking only"},
            {"name": "physical_instance_recognition", "enabled": False, "reason": "No cleared calibrated appearance encoder enabled"},
            {"name": "automatic_daily_tracker", "enabled": False, "reason": "Pending model-enable and held-out device/coverage gates"},
            {"name": "semantic_object_recognition", "enabled": False, "reason": "No semantic/OCR model enabled; changed regions are unknown"},
        ]

    def ingest_episode(self, raw: bytes) -> dict:
        packet = parse_packet(raw)
        digest = hashlib.sha256(raw).hexdigest()
        semantic = packet.semantic_digest()
        key = (self.profile_id, packet.device_id, packet.episode_id)
        now = self._now_ms()
        wall_end = packet.clock_anchor.wall_ms + packet.t_end_ms - packet.clock_anchor.mono_ms
        clock_status = "implausible" if wall_end <= 0 or wall_end > now + 300000 else "ok"
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            tombstone = db.execute("SELECT 1 FROM episode_tombstones WHERE profile_id=? AND device_id=? AND episode_id=?", key).fetchone()
            previous = db.execute("SELECT * FROM episode_revisions WHERE profile_id=? AND device_id=? AND episode_id=? ORDER BY revision_no", key).fetchall()
            same = next((row for row in previous if row["semantic_digest"] == semantic), None)
            if tombstone:
                return {"episode_id": packet.episode_id, "device_id": packet.device_id, "digest": digest,
                        "revision_no": same["revision_no"] if same else (previous[-1]["revision_no"] if previous else 0),
                        "retained": False, "status": "conflict", "processing_status": "redacted", "clock_status": clock_status}
            if same:
                job = db.execute("SELECT status FROM episode_jobs WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no=?", key + (same["revision_no"],)).fetchone()
                return {"episode_id": packet.episode_id, "device_id": packet.device_id, "digest": digest,
                        "revision_no": same["revision_no"], "retained": True,
                        "status": "duplicate" if same["accepted"] else "conflict",
                        "processing_status": job["status"] if job else "conflict", "clock_status": same["clock_status"]}
            if len(previous) >= 8:
                raise RevisionLimitError("Episode revision limit reached")
            accepted_rows = [row for row in previous if row["accepted"]]
            accepted = not accepted_rows or _superset(parse_packet(bytes(accepted_rows[-1]["packet"])).model_dump(), packet.model_dump())
            revision = len(previous) + 1
            status = "stored" if not previous else ("revised" if accepted else "conflict")
            db.execute("INSERT INTO episode_revisions VALUES(?,?,?,?,?,?,?,?,?,?,0)",
                       key + (revision, semantic, digest, raw, now, int(accepted), clock_status))
            if accepted:
                db.execute("INSERT INTO episode_jobs(profile_id,device_id,episode_id,revision_no,status) VALUES(?,?,?,?,?)", key + (revision, "pending"))
            return {"episode_id": packet.episode_id, "device_id": packet.device_id, "digest": digest,
                    "revision_no": revision, "retained": True, "status": status,
                    "processing_status": "pending" if accepted else "conflict", "clock_status": clock_status}

    def process_pending(self, *, processor=None, limit=8) -> dict:
        if type(limit) is not int or not 1 <= limit <= 128:
            raise ValueError("Invalid processing limit")
        processor = localize if processor is None else processor
        if not callable(processor):
            raise ValueError("Processor must be callable")
        counts = {"processed": 0, "failed": 0, "context_only": 0, "observations": 0}
        for _ in range(limit):
            with self._connection() as db:
                db.execute("BEGIN IMMEDIATE")
                job = db.execute("""SELECT j.*,r.packet,r.clock_status FROM episode_jobs j
                    JOIN episode_revisions r USING(profile_id,device_id,episode_id,revision_no)
                    WHERE j.profile_id=? AND r.redacted=0 AND
                    (j.status='pending' OR (j.status='processing' AND j.lease_until<=?))
                    ORDER BY r.received_at_ms,j.revision_no LIMIT 1""", (self.profile_id, self.clock())).fetchone()
                if job is None:
                    break
                key = (self.profile_id, job["device_id"], job["episode_id"], job["revision_no"])
                token = str(uuid.uuid4())
                db.execute("UPDATE episode_jobs SET status='processing',token=?,lease_until=?,attempts=attempts+1 WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no=?", (token, self.clock()+60) + key)
            try:
                packet = parse_packet(bytes(job["packet"]))
                result = processor(packet)
                if not isinstance(result, (list, tuple)) or len(result) > 32:
                    raise ValueError("Invalid processor result")
                observations = [LocalObservation.model_validate(value) for value in result]
                frames = {f.frame_id: f for f in packet.keyframes}
                for observation in observations:
                    if observation.frame_id not in frames or observation.bbox[2] > packet.capture.width or observation.bbox[3] > packet.capture.height:
                        raise ValueError("Observation outside packet evidence")
                    if len(_json(observation.model_dump())) > 16000:
                        raise ValueError("Observation metadata too large")
                with self._connection() as db:
                    db.execute("BEGIN IMMEDIATE")
                    current = db.execute("SELECT token,status,lease_until FROM episode_jobs WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no=?", key).fetchone()
                    if current["token"] != token or current["status"] != "processing" or current["lease_until"] <= self.clock():
                        continue
                    touched = []
                    for observation in observations:
                        # The default never claims calibration; trusted injection is a code-only boundary.
                        trusted = observation.identity_state == "trusted" and observation.calibration.get("approved") is True
                        if not trusted:
                            observation = observation.model_copy(update={"identity_state": "ambiguous" if observation.identity_state == "ambiguous" else "provisional", "outcome": "sighted", "actor": "unknown", "location_text": None})
                        record = observation.model_dump()
                        record["session_id"] = packet.session_id
                        signature = hashlib.sha256(_json([packet.device_id, packet.episode_id, record]).encode()).hexdigest()
                        if db.execute("SELECT 1 FROM local_observations WHERE profile_id=? AND observation_id=?", (self.profile_id, signature)).fetchone():
                            continue
                        item_id = self._continuity_item(db, packet, observation) if trusted else None
                        if item_id in touched:
                            item_id = None  # Two co-visible outputs never collapse into one identity.
                        item_id = item_id or str(uuid.uuid4())
                        touched.append(item_id)
                        observed_ms = packet.clock_anchor.wall_ms + frames[observation.frame_id].t_ms - packet.clock_anchor.mono_ms
                        record.update(clock_status=job["clock_status"], capture_mode=packet.capture_mode,
                                      observed_at_ms=observed_ms, item_id=item_id, observation_id=signature,
                                      device_id=packet.device_id, episode_id=packet.episode_id,
                                      revision_no=job["revision_no"], source="local_evidence")
                        db.execute("INSERT INTO local_observations VALUES(?,?,?,?,?,?,?,?,?)", (self.profile_id, signature, item_id, packet.device_id, packet.episode_id, job["revision_no"], observed_ms, self._now_ms(), _json(record)))
                        counts["observations"] += 1
                    for i, a in enumerate(touched):
                        for b in touched[i+1:]:
                            a1, b1 = sorted((a, b))
                            db.execute("INSERT OR IGNORE INTO local_cannot_links VALUES(?,?,?)", (self.profile_id, a1, b1))
                    self._rebuild_projection(db)
                    status = "completed" if observations else "context_only"
                    db.execute("UPDATE episode_jobs SET status=?,token=NULL,lease_until=NULL,result_count=?,error=NULL WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no=? AND token=?", (status, len(observations)) + key + (token,))
                    counts["processed"] += 1
                    counts["context_only"] += not bool(observations)
            except Exception:
                # Never persist exception text: processor errors may contain sensitive payloads.
                with self._connection() as db:
                    db.execute("UPDATE episode_jobs SET status='failed',token=NULL,lease_until=NULL,error='local_processing_failed' WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no=? AND token=?", key + (token,))
                counts["failed"] += 1
        with self._connection() as db:
            counts["pending"] = db.execute("SELECT count(*) FROM episode_jobs WHERE profile_id=? AND status IN ('pending','processing')", (self.profile_id,)).fetchone()[0]
            counts["context_only_total"] = db.execute("SELECT count(*) FROM episode_jobs WHERE profile_id=? AND status='context_only'", (self.profile_id,)).fetchone()[0]
        return counts

    def _continuity_item(self, db, packet, observation):
        if not observation.continuity_id:
            return None
        candidates = set()
        for row in db.execute("SELECT item_id,record FROM local_observations WHERE profile_id=? AND device_id=? AND record IS NOT NULL", (self.profile_id, packet.device_id)):
            record = json.loads(row["record"])
            if record.get("session_id") == packet.session_id and record.get("continuity_id") == observation.continuity_id and record.get("identity_state") == "trusted":
                candidates.add(row["item_id"])
        # Conflicting continuity IDs stay ambiguous even if new geometry is absent.
        if len(candidates) != 1:
            return None
        item_id = next(iter(candidates))
        if db.execute("SELECT 1 FROM item_tombstones WHERE profile_id=? AND item_id=?", (self.profile_id, item_id)).fetchone():
            return None
        return item_id

    @staticmethod
    def _as_of_ms(as_of):
        if as_of is None:
            return None
        if isinstance(as_of, bool) or not isinstance(as_of, (int, float)) or not math.isfinite(as_of) or as_of < 0:
            raise ValueError("as_of must be nonnegative epoch milliseconds")
        return int(as_of)

    def _projection(self, db, as_of=None):
        at = self._as_of_ms(as_of)
        rows = db.execute("""SELECT o.* FROM local_observations o WHERE o.profile_id=? AND o.record IS NOT NULL
            AND NOT EXISTS(SELECT 1 FROM item_tombstones t WHERE t.profile_id=o.profile_id AND t.item_id=o.item_id)
            ORDER BY o.observed_at_ms,o.decided_at_ms,o.observation_id""", (self.profile_id,)).fetchall()
        items = {}
        for row in rows:
            if at is not None and row["observed_at_ms"] > at:
                continue
            observation = json.loads(row["record"])
            trusted = observation["identity_state"] == "trusted"
            placed = trusted and observation["outcome"] == "placed_on_surface" and observation.get("location_text")
            clock_bad = observation.get("clock_status") != "ok"
            location_status = "known" if placed and not clock_bad else "unknown"
            stale = None
            if observation["outcome"] == "picked_up":
                location_status, stale = "stale", "Observed pickup; resting location is unknown"
            elif not placed:
                stale = "Only a sighting; placement and identity are unverified"
            if clock_bad:
                stale = "Capture clock is implausible; location time is uncertain"
            items[row["item_id"]] = {
                "item_id": row["item_id"], "name": observation["label"],
                "identity_status": observation["identity_state"], "relevance": "candidate",
                "location_status": location_status,
                "observed_at_ms": row["observed_at_ms"] if row["observed_at_ms"] > 0 else None,
                "location_text": observation.get("location_text") if placed else None,
                "stale_reason": stale, "index_pending": False, "image_url": None,
                "source": "local_evidence", "observation_id": row["observation_id"],
            }
        for row in db.execute("SELECT item_id,name,at_ms FROM item_names WHERE profile_id=? AND name IS NOT NULL ORDER BY at_ms,name_id", (self.profile_id,)):
            if row["item_id"] in items and (at is None or row["at_ms"] <= at):
                items[row["item_id"]]["name"] = row["name"]
                items[row["item_id"]]["source"] = "user_named_local_evidence"
        return items

    def _rebuild_projection(self, db):
        items = self._projection(db)
        db.execute("DELETE FROM current_items WHERE profile_id=?", (self.profile_id,))
        for item_id, record in items.items():
            db.execute("INSERT INTO current_items VALUES(?,?,?)", (self.profile_id, item_id, _json(record)))
        return items

    def _pending(self, db):
        return bool(db.execute("SELECT 1 FROM episode_jobs WHERE profile_id=? AND status IN ('pending','processing') LIMIT 1", (self.profile_id,)).fetchone())

    def list_items(self, query='', limit=50) -> list[dict]:
        if not isinstance(query, str) or len(query) > 2000 or type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("Invalid catalogue query")
        with self._connection() as db:
            items = [json.loads(row[0]) for row in db.execute("SELECT record FROM current_items WHERE profile_id=?", (self.profile_id,))]
            pending = self._pending(db)
        words = self._query_words(query)
        items = [dict(item, index_pending=pending) for item in items if self._matches(item, words, query)]
        return sorted(items, key=lambda x: (-(x["observed_at_ms"] or 0), x["item_id"]))[:limit]

    @staticmethod
    def _query_words(query):
        return set(re.findall(r"[\w]+", query.casefold())) - {"where", "is", "are", "my", "the", "a", "an", "did", "i", "leave", "find", "please", "can", "you", "me", "show"}

    def _matches(self, item, words, query):
        return not words or query.strip() == item["item_id"] or words <= self._query_words(item["name"])

    def get_item(self, item_id) -> dict:
        if not isinstance(item_id, str) or len(item_id) > 100:
            raise KeyError("Unknown item")
        with self._connection() as db:
            row = db.execute("SELECT record FROM current_items WHERE profile_id=? AND item_id=?", (self.profile_id, item_id)).fetchone()
            if row is None:
                raise KeyError("Unknown item")
            return dict(json.loads(row["record"]), index_pending=self._pending(db))

    def item_history(self, item_id) -> list[dict]:
        self.get_item(item_id)
        with self._connection() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT record FROM local_observations WHERE profile_id=? AND item_id=? AND record IS NOT NULL ORDER BY observed_at_ms,decided_at_ms,observation_id", (self.profile_id, item_id))]

    def item_image(self, item_id) -> Path | None:
        # A derived crop is cached only in a private profile-specific artifact path.
        # Holding the transaction fences concurrent logical erasure while writing.
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            item = db.execute("SELECT record FROM current_items WHERE profile_id=? AND item_id=?", (self.profile_id, item_id)).fetchone()
            if item is None:
                return None
            item = json.loads(item[0])
            row = db.execute("SELECT * FROM local_observations WHERE profile_id=? AND observation_id=? AND record IS NOT NULL", (self.profile_id, item["observation_id"])).fetchone()
            if row is None:
                return None
            revision = db.execute("SELECT packet FROM episode_revisions WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no=? AND redacted=0", (self.profile_id, row["device_id"], row["episode_id"], row["revision_no"])).fetchone()
            if revision is None or revision[0] is None:
                return None
            packet = parse_packet(bytes(revision[0]))
            observation = json.loads(row["record"])
            frame = next((f for f in packet.keyframes if f.frame_id == observation["frame_id"]), None)
            if frame is None:
                return None
            import cv2
            try:
                from .episode import decode_jpeg
            except ImportError:
                from episode import decode_jpeg
            image = decode_jpeg(frame.jpeg_b64)
            x1, y1, x2, y2 = observation["bbox"]
            crop = image[int(y1):math.ceil(y2), int(x1):math.ceil(x2)]
            ok, encoded = cv2.imencode(".jpg", crop)
            if not ok:
                return None
            media_id = hashlib.sha256((self.profile_id + ':' + item_id + ':' + row["observation_id"]).encode()).hexdigest()
            path = self.path.parent / (self.path.name + "." + media_id + ".jpg")
            if not path.exists():
                fd = private_append_fd(path)
                try:
                    data = encoded.tobytes()
                    while data:
                        count = os.write(fd, data)
                        if count <= 0:
                            raise OSError("Incomplete private media write")
                        data = data[count:]
                    os.fsync(fd)
                finally:
                    os.close(fd)
            return path

    def rename_item(self, item_id, name) -> dict:
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 100 or any(ord(c) < 32 for c in name):
            raise ValueError("Invalid item name")
        name = name.strip()
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM current_items WHERE profile_id=? AND item_id=?", (self.profile_id, item_id)).fetchone():
                raise KeyError("Unknown item")
            db.execute("INSERT INTO item_names(profile_id,item_id,at_ms,name) VALUES(?,?,?,?)", (self.profile_id, item_id, self._now_ms(), name))
            db.execute("INSERT INTO local_audit(profile_id,at_ms,action,item_id,detail) VALUES(?,?,?,?,?)", (self.profile_id, self._now_ms(), "user_named", item_id, '{}'))
            self._rebuild_projection(db)
        return self.get_item(item_id)

    def answer_text(self, text, *, as_of=None) -> dict:
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise ValueError("Invalid question")
        at = self._as_of_ms(as_of)
        with self._connection() as db:
            items = list(self._projection(db, at).values())
            pending = self._pending(db)
        words = self._query_words(text)
        members = [dict(item, index_pending=pending) for item in items if self._matches(item, words, text)] if words else []
        answer = {"shape": "abstain", "text": "I have no matching stored evidence.", "members": [], "index_pending": pending}
        if not members:
            return answer
        if len(members) > 1:
            return dict(answer, shape="clarify", text="Which stored item do you mean?", members=members[:8], question="Which stored item?", options=[{"item_id": x["item_id"], "name": x["name"]} for x in members[:8]])
        item = members[0]
        shape = "hedged"
        if item["identity_status"] == "trusted" and item["location_status"] == "known":
            message = f"The recorded location of {item['name']} is {item['location_text']}."
            shape = "confident"
        elif item["location_text"]:
            message = f"Earlier evidence recorded {item['name']} at {item['location_text']}; its current location is uncertain."
        else:
            message = f"I have a stored sighting for {item['name']}, but cannot confirm its identity or current resting location."
        return dict(answer, shape=shape, text=message, members=members)

    def rebuild_all(self, *, as_of=None) -> dict:
        at = self._as_of_ms(as_of)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            items = self._rebuild_projection(db) if at is None else self._projection(db, at)
            return {"items": list(items.values()), "count": len(items), "as_of": at, "model_rerun": False,
                    "context_only": db.execute("SELECT count(*) FROM episode_jobs WHERE profile_id=? AND status='context_only'", (self.profile_id,)).fetchone()[0]}

    def migration_plan(self) -> dict:
        with self._connection() as db:
            counts = {table: db.execute(f"SELECT count(*) FROM {table} WHERE profile_id=?", (self.profile_id,)).fetchone()[0]
                      for table in ("objects", "candidates", "observations", "api_calls", "decisions")}
            return {"schema_version": db.execute("PRAGMA user_version").fetchone()[0], "legacy_counts": counts,
                    "automatic_conversion": False, "mutates_data": False,
                    "plan": "Preserve legacy records, budgets and leases. Explicit reviewed conversion may import legacy evidence as untrusted; never infer calibrated identity."}

    def redact_item(self, item_id) -> dict:
        # Conservatively invalidate ALL candidates sharing packet media. A whole-frame
        # packet may contain several people/items; retaining it would defeat erasure.
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM item_tombstones WHERE profile_id=? AND item_id=?", (self.profile_id, item_id)).fetchone():
                return {"item_id": item_id, "redacted": True, "scope": "logical", "forensic_erasure": False}
            if not db.execute("SELECT 1 FROM current_items WHERE profile_id=? AND item_id=?", (self.profile_id, item_id)).fetchone():
                raise KeyError("Unknown item")
            episodes = {(r[0], r[1]) for r in db.execute("SELECT device_id,episode_id FROM local_observations WHERE profile_id=? AND item_id=?", (self.profile_id, item_id))}
            affected = {item_id}
            # Transitive closure prevents a second packet from restoring a co-item.
            changed = True
            while changed:
                before = (len(episodes), len(affected))
                for device, episode in list(episodes):
                    affected.update(r[0] for r in db.execute("SELECT item_id FROM local_observations WHERE profile_id=? AND device_id=? AND episode_id=?", (self.profile_id, device, episode)))
                for target in list(affected):
                    episodes.update((r[0], r[1]) for r in db.execute("SELECT device_id,episode_id FROM local_observations WHERE profile_id=? AND item_id=?", (self.profile_id, target)))
                changed = before != (len(episodes), len(affected))
            for target in affected:
                for row in db.execute("SELECT observation_id FROM local_observations WHERE profile_id=? AND item_id=?", (self.profile_id, target)):
                    media_id = hashlib.sha256((self.profile_id + ':' + target + ':' + row[0]).encode()).hexdigest()
                    path = self.path.parent / (self.path.name + "." + media_id + ".jpg")
                    if path.exists():
                        fd = private_append_fd(path)
                        try:
                            os.ftruncate(fd, 0)
                            os.fsync(fd)
                        finally:
                            os.close(fd)
                db.execute("INSERT OR IGNORE INTO item_tombstones VALUES(?,?,?)", (self.profile_id, target, self._now_ms()))
                db.execute("UPDATE local_observations SET record=NULL WHERE profile_id=? AND item_id=?", (self.profile_id, target))
                db.execute("UPDATE item_names SET name=NULL WHERE profile_id=? AND item_id=?", (self.profile_id, target))
                db.execute("DELETE FROM current_items WHERE profile_id=? AND item_id=?", (self.profile_id, target))
            for device, episode in episodes:
                db.execute("INSERT OR IGNORE INTO episode_tombstones VALUES(?,?,?,?)", (self.profile_id, device, episode, self._now_ms()))
                db.execute("UPDATE episode_revisions SET packet=NULL,redacted=1 WHERE profile_id=? AND device_id=? AND episode_id=?", (self.profile_id, device, episode))
                db.execute("UPDATE episode_jobs SET status='redacted',token=NULL,lease_until=NULL,error=NULL WHERE profile_id=? AND device_id=? AND episode_id=?", (self.profile_id, device, episode))
            db.execute("INSERT INTO local_audit(profile_id,at_ms,action,item_id,detail) VALUES(?,?,?,?,?)", (self.profile_id, self._now_ms(), "logical_redaction", item_id, _json({"affected_items": len(affected), "episodes": len(episodes)})))
            return {"item_id": item_id, "redacted": True, "affected_items": len(affected), "scope": "logical", "forensic_erasure": False}
