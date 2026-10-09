"""Additive keyless episode ledger. Legacy v1 records are never reinterpreted.

Evidence/decisions are append-only through ordinary APIs. Redaction is a separate,
audited logical erasure, not a promise about filesystem remnants or backups.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from datetime import datetime, timezone

try:
    from .episode import parse_packet, jpeg_bytes, decode_jpeg, RevisionLimitError
    from .localizer import LocalObservation, localize
    from .identity import ConformalMatcher, ItemBank, crop_box, l2_normalise, mask_from_rle, validate_embedder
except ImportError:
    from episode import parse_packet, jpeg_bytes, decode_jpeg, RevisionLimitError
    from localizer import LocalObservation, localize
    from identity import ConformalMatcher, ItemBank, crop_box, l2_normalise, mask_from_rle, validate_embedder


class CannotLinkError(ValueError):
    """link_items refused: a cannot-link exists between the two items (str() == "cannot-link")."""
    def __init__(self):
        super().__init__("cannot-link")


CALIBRATION_SOURCES = ("synthetic", "cute", "own-footage", "holoassist")
CALIBRATION_ID = re.compile(r"[A-Za-z0-9._:-]{1,100}")
# Closed actor set (Oversight, B-15): a correction or approval is attributed to the
# session role that made it, never to a named person. Anything else is refused.
ACTORS = ("caregiver_pin", "operator", "test")
MAX_CANDIDATES = 32


def _check_actor(actor):
    if not isinstance(actor, str) or actor not in ACTORS:
        raise ValueError("invalid actor")
    return actor


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _vector_bytes(vector) -> bytes:
    import numpy as np
    return np.ascontiguousarray(l2_normalise(vector), dtype="<f4").tobytes()


def _vector_from_bytes(blob, dim):
    import numpy as np
    vector = np.frombuffer(bytes(blob), dtype="<f4")
    if vector.size != dim:
        raise ValueError("Stored embedding has the wrong dimension")
    return vector.astype(np.float32)


# Clock-only staleness (B-11, CP2). A 'placed' location ages by the evaluation clock
# alone: no write is needed for an answer to age, and the stored projection never
# carries an evaluated age. Ageing is applied when a projection is READ, at as_of
# when the caller gives one, else at the injected clock. Initial values from the
# build plan; a re-observation stage (CP4) is what refreshes observed_at_ms.
AGE_STALE_MS = 24 * 3600 * 1000        # age > this: still 'placed', stale_reason "age", aged true, answer hedged
AGE_ABSTAIN_MS = 7 * 24 * 3600 * 1000  # age > this: location_status 'stale', location_text kept, answer abstains


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
CREATE TABLE IF NOT EXISTS calibrations (
 profile_id TEXT NOT NULL, calibration_id TEXT NOT NULL, embedder TEXT NOT NULL,
 alpha REAL NOT NULL, quantile REAL NOT NULL, n INTEGER NOT NULL, source TEXT NOT NULL,
 created_ms INTEGER NOT NULL, approved INTEGER NOT NULL DEFAULT 0, approved_by TEXT, approved_ms INTEGER,
 PRIMARY KEY(profile_id,calibration_id));
CREATE TABLE IF NOT EXISTS embeddings (
 profile_id TEXT NOT NULL, observation_id TEXT NOT NULL, embedder TEXT NOT NULL,
 dim INTEGER NOT NULL, vector BLOB NOT NULL, created_ms INTEGER NOT NULL,
 PRIMARY KEY(profile_id,observation_id),
 FOREIGN KEY(profile_id,observation_id) REFERENCES local_observations(profile_id,observation_id));
CREATE TABLE IF NOT EXISTS corrections (
 correction_no INTEGER PRIMARY KEY AUTOINCREMENT, profile_id TEXT NOT NULL,
 correction_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('link','unlink','assign')),
 at_ms INTEGER NOT NULL, actor TEXT NOT NULL, payload TEXT NOT NULL,
 UNIQUE(profile_id,correction_id));
"""

# CP3 (schema user_version 3): columns added to existing tables, applied by
# ensure_episode_columns as ALTER TABLE ADD COLUMN guarded by PRAGMA table_info, so
# a v2 database gains them without a rewrite and a v3 one is left alone.
# local_observations.candidates: JSON list of the item_ids an ambiguous match
# could not separate (NULL for every other observation).
EPISODE_COLUMNS = (("local_observations", "candidates", "TEXT"),)


def ensure_episode_columns(db):
    """Additive column migration for EPISODE_COLUMNS; idempotent, same transaction."""
    for table, column, declaration in EPISODE_COLUMNS:
        present = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in present:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def _superset(old, new):
    # Contract (2026-10-07): a revision is a superset only when it keeps every prior
    # evidence frame and the same interpretation. A changed outcome_hint retracts the
    # phone's earlier claim, so it is a conflict, not a revision.
    for field in ("schema_version", "episode_id", "device_id", "session_id", "clock_anchor", "capture", "analysis", "capture_mode", "outcome_hint"):
        if old[field] != new[field]:
            return False
    if new["t_start_ms"] > old["t_start_ms"] or new["t_end_ms"] < old["t_end_ms"]:
        return False
    for field in ("keyframes", "carry_burst", "landmarks", "gaps"):
        values = {_json(value) for value in new[field]}
        if not all(_json(value) in values for value in old[field]):
            return False
    return True


def _named_calibration_id(observation):
    calibration = observation.calibration if isinstance(observation.calibration, dict) else {}
    value = calibration.get("calibration_id")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _calibration_approved(observation) -> bool:
    """Contract (2026-10-07): an observation is trusted only when the processor says
    identity_state == "trusted" AND its calibration record is explicitly approved and
    named. A 'valid' flag, a confidence number or a fixture marker is not approval.

    CP3 (build plan, identity): this dict rule is the code-only fixture injection,
    identified by fixture_only: true next to approved: true and the calibration_id;
    a processor cannot approve itself by writing approved: true against a real
    calibration record. The second, production path is
    EpisodeStoreMixin._observation_trusted: the named calibration_id is a stored
    record approved through approve_calibration for the store's embedder."""
    calibration = observation.calibration
    return (observation.identity_state == "trusted" and calibration.get("approved") is True
            and calibration.get("fixture_only") is True and _named_calibration_id(observation) is not None)


class EpisodeStoreMixin:
    # CP3: the identity embedder (perception.identity.Embedder) or None. None means no
    # embedding, no matching, identity never above provisional; nothing is simulated.
    # Set through ObjectStore(..., embedder=) or set_embedder(); the server constructs
    # a DinoV2Embedder only when its model manifest gate allows it.
    embedder = None

    def _now_ms(self):
        return int(self.clock() * 1000)

    def set_embedder(self, embedder) -> None:
        """Install (or remove, with None) the identity embedder after validating the
        Embedder protocol: name, version, int dim, callable embed. ValueError otherwise."""
        self.embedder = validate_embedder(embedder)

    def _identity_capability(self) -> dict:
        name = "physical_instance_recognition"
        if self.embedder is None:
            return {"name": name, "enabled": False, "reason": "No identity model provisioned; identity stays provisional."}
        tag = self.embedder.tag if hasattr(self.embedder, "tag") else f"{self.embedder.name}@{self.embedder.version}"
        with self._connection() as db:
            approved = self._active_calibration(db, tag)
        # Coordinator ruling (CP3 fix round): "enabled" means recognition can produce a
        # trusted identity, so it needs the embedder AND an approved calibration for
        # its tag; an embedder alone still matches, but only ever provisionally.
        if approved is not None and approved["approved"]:
            return {"name": name, "enabled": True, "reason": f"Identity embedder {tag} loaded; calibration {approved['calibration_id']} approved"}
        return {"name": name, "enabled": False, "reason": f"Identity embedder {tag} loaded; no approved calibration: identity stays provisional"}

    def capabilities(self) -> list[dict]:
        return [
            {"name": "local_processing", "enabled": True, "reason": "OpenCV registered image differences; provisional regions only"},
            {"name": "local_text_chat", "enabled": True, "reason": "Stored evidence lookup; no provider required"},
            {"name": "automatic_hand_recognition", "enabled": False, "reason": "No cleared hand model enabled; manual marking only"},
            self._identity_capability(),
            {"name": "automatic_daily_tracker", "enabled": False, "reason": "Pending model-enable and held-out device/coverage gates"},
            {"name": "semantic_object_recognition", "enabled": False, "reason": "No semantic/OCR model enabled; changed regions are unknown"},
        ]

    # Calibration records (CP3). A record is registered unapproved and only
    # approve_calibration (audited) can flip it; the processor's observation-level
    # calibration dict (CP2 rule, _calibration_approved) is a separate, code-only path.
    @staticmethod
    def _calibration_dict(row) -> dict:
        return {"calibration_id": row["calibration_id"], "embedder": row["embedder"], "alpha": row["alpha"],
                "quantile": row["quantile"], "n": row["n"], "source": row["source"], "created_ms": row["created_ms"],
                "approved": bool(row["approved"]), "approved_by": row["approved_by"], "approved_ms": row["approved_ms"]}

    def register_calibration(self, record) -> dict:
        """Store a calibration record {calibration_id, embedder, alpha, quantile, n,
        source, created_ms?}; approved is always False here. ValueError on an
        invalid or duplicate record. Audit row calibration_registered."""
        if not isinstance(record, dict):
            raise ValueError("Invalid calibration record")
        allowed = {"calibration_id", "embedder", "alpha", "quantile", "n", "source", "created_ms", "approved"}
        if set(record) - allowed:
            raise ValueError("Invalid calibration record")
        calibration_id, embedder, source = record.get("calibration_id"), record.get("embedder"), record.get("source")
        if not isinstance(calibration_id, str) or not CALIBRATION_ID.fullmatch(calibration_id):
            raise ValueError("Invalid calibration_id")
        if not isinstance(embedder, str) or not 3 <= len(embedder) <= 161 or embedder.count("@") != 1 or any(ord(c) < 33 for c in embedder):
            raise ValueError("Invalid calibration embedder tag")
        if source not in CALIBRATION_SOURCES:
            raise ValueError("Invalid calibration source")
        alpha, quantile, n = record.get("alpha"), record.get("quantile"), record.get("n")
        for value, low, high in ((alpha, 0, 1), (quantile, 0, 2)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError("Invalid calibration numbers")
        if not 0 < alpha < 1 or type(n) is not int or n < 1:
            raise ValueError("Invalid calibration numbers")
        created = record.get("created_ms", None)
        created = self._now_ms() if created is None else created
        if isinstance(created, bool) or type(created) is not int or created < 0:
            raise ValueError("Invalid calibration time")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM calibrations WHERE profile_id=? AND calibration_id=?", (self.profile_id, calibration_id)).fetchone():
                raise ValueError("Calibration already registered")
            db.execute("INSERT INTO calibrations(profile_id,calibration_id,embedder,alpha,quantile,n,source,created_ms,approved) VALUES(?,?,?,?,?,?,?,?,0)",
                       (self.profile_id, calibration_id, embedder, float(alpha), float(quantile), n, source, created))
            db.execute("INSERT INTO local_audit(profile_id,at_ms,action,item_id,detail) VALUES(?,?,?,?,?)",
                       (self.profile_id, self._now_ms(), "calibration_registered", None, _json({"calibration_id": calibration_id, "embedder": embedder, "source": source, "n": n})))
            return self._calibration_dict(db.execute("SELECT * FROM calibrations WHERE profile_id=? AND calibration_id=?", (self.profile_id, calibration_id)).fetchone())

    def approve_calibration(self, calibration_id, actor) -> dict:
        """Approve a registered calibration (idempotent). actor is the session role
        string, never a named person. KeyError for an unknown id; audit row
        calibration_approved."""
        _check_actor(actor)
        if not isinstance(calibration_id, str) or not CALIBRATION_ID.fullmatch(calibration_id):
            raise KeyError("Unknown calibration")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM calibrations WHERE profile_id=? AND calibration_id=?", (self.profile_id, calibration_id)).fetchone()
            if row is None:
                raise KeyError("Unknown calibration")
            if not row["approved"]:
                now = self._now_ms()
                db.execute("UPDATE calibrations SET approved=1,approved_by=?,approved_ms=? WHERE profile_id=? AND calibration_id=?", (actor, now, self.profile_id, calibration_id))
                db.execute("INSERT INTO local_audit(profile_id,at_ms,action,item_id,detail) VALUES(?,?,?,?,?)",
                           (self.profile_id, now, "calibration_approved", None, _json({"calibration_id": calibration_id, "actor": actor})))
            return self._calibration_dict(db.execute("SELECT * FROM calibrations WHERE profile_id=? AND calibration_id=?", (self.profile_id, calibration_id)).fetchone())

    def list_calibrations(self) -> list[dict]:
        with self._connection() as db:
            return [self._calibration_dict(row) for row in db.execute("SELECT * FROM calibrations WHERE profile_id=? ORDER BY created_ms,calibration_id", (self.profile_id,))]

    def _active_calibration(self, db, embedder_tag):
        """The calibration process_pending matches with when the processor names none
        for this embedder tag: the newest approved record, else the newest unapproved
        one (matching still runs but identity stays provisional), else None (no
        matching at all)."""
        row = db.execute("SELECT * FROM calibrations WHERE profile_id=? AND embedder=? ORDER BY approved DESC,created_ms DESC,calibration_id DESC LIMIT 1", (self.profile_id, embedder_tag)).fetchone()
        return self._calibration_dict(row) if row else None

    def _observation_trusted(self, db, observation, embedder_tag):
        """(trusted, named_record) for one processor observation.

        trusted when identity_state == "trusted" AND either the CP2 dict rule holds
        (_calibration_approved: approved: true + calibration_id, the code-only fixture
        injection) or the named calibration_id is a stored record, approved through
        approve_calibration, whose embedder is the store's current embedder tag (so
        with no embedder a table record never trusts anything). named_record is the
        stored record the observation names, if any, whatever its approval.
        """
        named = None
        calibration_id = _named_calibration_id(observation)
        if calibration_id is not None:
            row = db.execute("SELECT * FROM calibrations WHERE profile_id=? AND calibration_id=?", (self.profile_id, calibration_id)).fetchone()
            named = self._calibration_dict(row) if row else None
        if named is None:
            return _calibration_approved(observation), None
        # A stored record decides for itself; the dict's own flags are not consulted.
        trusted = (observation.identity_state == "trusted" and named["approved"]
                   and embedder_tag is not None and named["embedder"] == embedder_tag)
        return trusted, named

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
        counts = {"processed": 0, "failed": 0, "context_only": 0, "observations": 0,
                  "embedded": 0, "embedding_failed": 0, "matched": 0, "ambiguous": 0}
        embedder = self.embedder
        embedder_tag = embedder.tag if embedder is not None else None
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
                    if len(_json(observation.model_dump(exclude={"mask_rle"}))) > 16000:
                        raise ValueError("Observation metadata too large")
                # CP3: embed every region before taking the write lock (model time is
                # not transaction time). vectors[i] is None when no embedder is set or
                # that crop could not be embedded; a failed embedding never fails the
                # job and never removes evidence, the observation just stays provisional.
                vectors = [None] * len(observations)
                if embedder is not None:
                    decoded = {}
                    for index, observation in enumerate(observations):
                        try:
                            if observation.frame_id not in decoded:
                                decoded[observation.frame_id] = self._rgb_frame(frames[observation.frame_id])
                            vectors[index] = self._embed_region(embedder, decoded[observation.frame_id], observation)
                            counts["embedded"] += 1
                        except Exception:
                            # Never persist or count exception text; the crop is personal evidence.
                            counts["embedding_failed"] += 1
                with self._connection() as db:
                    db.execute("BEGIN IMMEDIATE")
                    current = db.execute("SELECT token,status,lease_until FROM episode_jobs WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no=?", key).fetchone()
                    if current["token"] != token or current["status"] != "processing" or current["lease_until"] <= self.clock():
                        continue
                    assign, _, resolved = self._assignments(db)
                    tombstoned = {row[0] for row in db.execute("SELECT item_id FROM item_tombstones WHERE profile_id=?", (self.profile_id,))}
                    embedding = embedder is not None and any(v is not None for v in vectors)
                    active = self._active_calibration(db, embedder_tag) if embedding else None
                    banks = self._banks(db, assign, resolved, tombstoned, embedder_tag) if embedding else {}
                    touched = []
                    for index, observation in enumerate(observations):
                        # The default never claims calibration; trusted injection is a code-only
                        # boundary (CP2 dict rule) or a calibration_id approved in the table for
                        # this embedder (CP3); anything else is provisional.
                        trusted, named = self._observation_trusted(db, observation, embedder_tag)
                        embedding_failed = embedder is not None and vectors[index] is None
                        if embedding_failed:
                            # The identity model was supposed to see this region and could not:
                            # without that evidence the claim is not trusted (and no match runs).
                            trusted = False
                        if not trusted:
                            observation = observation.model_copy(update={"identity_state": "ambiguous" if observation.identity_state == "ambiguous" else "provisional", "outcome": "sighted", "actor": "unknown", "location_text": None})
                        # The mask only steered the embedding; it is not evidence and keeps
                        # the observation signature identical to the pre-CP3 one.
                        record = observation.model_dump(exclude={"mask_rle"})
                        record["session_id"] = packet.session_id
                        signature = hashlib.sha256(_json([packet.device_id, packet.episode_id, record]).encode()).hexdigest()
                        if db.execute("SELECT 1 FROM local_observations WHERE profile_id=? AND observation_id=?", (self.profile_id, signature)).fetchone():
                            continue
                        # Continuity (trusted fixture observations) is the first-choice
                        # association; appearance matching runs only when it yields nothing.
                        item_id = self._continuity_item(db, packet, observation, assign) if trusted else None
                        match, candidates = None, None
                        if embedding_failed:
                            match = {"embedder": embedder_tag, "calibration_id": None, "state": "new", "set": [], "scores": {},
                                     "reason": "embedding failed; identity provisional"}
                        if item_id is None and vectors[index] is not None:
                            # The processor's named calibration (when it is a record for this
                            # embedder, approved or not) sets the quantile, else the active one.
                            calibration = named if named is not None and named["embedder"] == embedder_tag else active
                            if calibration is None:
                                match = {"embedder": embedder_tag, "calibration_id": None, "state": "new", "set": [], "scores": {},
                                         "reason": "no calibration registered for this embedder"}
                            else:
                                matcher = ConformalMatcher(calibration["quantile"], embedder_tag, calibration["calibration_id"])
                                # Cannot-links (B-03): any item holding an observation co-visible with
                                # this one (same device, episode and frame), plus this packet's own
                                # outputs, is excluded from the set even if it scores inside it.
                                excluded = self._co_visible_items(db, packet, observation.frame_id, assign) | set(touched)
                                result_match = matcher.match(vectors[index], banks, excluded)
                                top = sorted(result_match["scores"].items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_CANDIDATES]
                                match = {"embedder": embedder_tag, "calibration_id": calibration["calibration_id"],
                                         "calibration_approved": calibration["approved"], "state": result_match["state"],
                                         "set": list(result_match["set"])[:MAX_CANDIDATES],
                                         "scores": {k: round(float(v), 6) for k, v in top},
                                         "excluded": sorted(excluded)[:MAX_CANDIDATES]}
                                if result_match["state"] == "match":
                                    item_id = result_match["set"][0]
                                    counts["matched"] += 1
                                    # Identity is trusted through the matcher only when its calibration
                                    # is approved in the table (the tag already matches by construction).
                                    if calibration["approved"] and observation.identity_state != "ambiguous":
                                        observation = observation.model_copy(update={"identity_state": "trusted"})
                                        record["identity_state"] = "trusted"
                                elif result_match["state"] == "ambiguous":
                                    # B-14: an observation the matcher cannot attribute is stored
                                    # (with its embedding and candidates) under a placeholder item
                                    # that the projection never lists; it only marks the candidates
                                    # as lookalikes. It upgrades nobody and updates nobody.
                                    candidates = list(result_match["set"])[:MAX_CANDIDATES]
                                    observation = observation.model_copy(update={"identity_state": "ambiguous", "outcome": "sighted", "actor": "unknown", "location_text": None})
                                    record.update(identity_state="ambiguous", outcome="sighted", actor="unknown", location_text=None)
                                    counts["ambiguous"] += 1
                        if item_id in touched:
                            item_id = None  # Two co-visible outputs never collapse into one identity.
                        item_id = item_id or str(uuid.uuid4())
                        touched.append(item_id)
                        observed_ms = packet.clock_anchor.wall_ms + frames[observation.frame_id].t_ms - packet.clock_anchor.mono_ms
                        record.update(clock_status=job["clock_status"], capture_mode=packet.capture_mode,
                                      observed_at_ms=observed_ms, item_id=item_id, observation_id=signature,
                                      device_id=packet.device_id, episode_id=packet.episode_id,
                                      revision_no=job["revision_no"], source="local_evidence",
                                      identity_source="processor")
                        if match is not None:
                            record["match"] = match
                        db.execute("INSERT INTO local_observations(profile_id,observation_id,item_id,device_id,episode_id,revision_no,observed_at_ms,decided_at_ms,record,candidates) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                   (self.profile_id, signature, item_id, packet.device_id, packet.episode_id, job["revision_no"], observed_ms, self._now_ms(), _json(record), _json(candidates) if candidates else None))
                        if vectors[index] is not None:
                            db.execute("INSERT INTO embeddings VALUES(?,?,?,?,?,?)", (self.profile_id, signature, embedder_tag, int(embedder.dim), _vector_bytes(vectors[index]), self._now_ms()))
                        assign[signature] = item_id
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

    def _continuity_item(self, db, packet, observation, assign=None):
        if not observation.continuity_id:
            return None
        if assign is None:
            assign, _, _ = self._assignments(db)
        candidates = set()
        for row in db.execute("SELECT observation_id,item_id,record FROM local_observations WHERE profile_id=? AND device_id=? AND record IS NOT NULL", (self.profile_id, packet.device_id)):
            record = json.loads(row["record"])
            if record.get("session_id") == packet.session_id and record.get("continuity_id") == observation.continuity_id and record.get("identity_state") == "trusted":
                candidates.add(assign.get(row["observation_id"], row["item_id"]))
        # Conflicting continuity IDs stay ambiguous even if new geometry is absent.
        if len(candidates) != 1:
            return None
        item_id = next(iter(candidates))
        if db.execute("SELECT 1 FROM item_tombstones WHERE profile_id=? AND item_id=?", (self.profile_id, item_id)).fetchone():
            return None
        return item_id

    # CP3 helpers: embedding geometry, effective assignments after corrections,
    # banks from the embeddings table, and frame co-visibility.
    @staticmethod
    def _rgb_frame(frame):
        """The keyframe decoded to RGB uint8 [H, W, 3] (the decoder yields BGR)."""
        import cv2
        image = decode_jpeg(frame.jpeg_b64)
        if image.ndim == 2:
            return cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
        if image.shape[2] == 4:
            return cv2.cvtColor(image, cv2.COLOR_BGRA2RGB)
        return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    @staticmethod
    def _embed_region(embedder, rgb, observation):
        """Crop the observation's bbox at capture resolution, decode its mask_rle over
        the same integer window (an invalid mask is dropped, not fatal) and embed.
        Raises if the embedder returns anything but a finite vector of its dim."""
        import numpy as np
        height, width = rgb.shape[:2]
        x1, y1, x2, y2 = crop_box(observation.bbox, width, height)
        crop = np.ascontiguousarray(rgb[y1:y2, x1:x2])
        mask = None
        if observation.mask_rle:
            try:
                mask = mask_from_rle(observation.mask_rle, x2 - x1, y2 - y1)
            except ValueError:
                mask = None
        vector = np.asarray(embedder.embed(crop, mask), dtype=np.float32).reshape(-1)
        if vector.size != embedder.dim:
            raise ValueError("Embedder returned the wrong dimension")
        return l2_normalise(vector)

    def _corrections(self, db, at=None):
        """Stored corrections in replay order, limited to at_ms <= at when given."""
        rows = db.execute("SELECT correction_no,correction_id,kind,at_ms,actor,payload FROM corrections WHERE profile_id=? ORDER BY correction_no", (self.profile_id,))
        return [dict(row, payload=json.loads(row["payload"])) for row in rows if at is None or row["at_ms"] <= at]

    def _assignments(self, db, at=None):
        """Effective observation -> item map after replaying corrections up to at.

        Returns (assign, merged, resolved): assign maps every non-redacted
        observation_id to its current item; merged maps a linked-away item_id to
        the item it was merged into (chains resolved); resolved maps an
        observation_id to "cleared" (a link settled its identity: no candidates,
        ambiguous reads provisional) or to a dict with "assigned": item_id (the
        user attributed a parked observation: no candidates, parked no longer,
        identity trusted/user_assigned) and/or "remove": item_id (an unlink ruled
        that item out; after an assign it withdraws the assertion). local_observations
        .item_id itself is the processing-time decision and is never rewritten.
        """
        assign = {row[0]: row[1] for row in db.execute("SELECT observation_id,item_id FROM local_observations WHERE profile_id=? AND record IS NOT NULL", (self.profile_id,))}
        merged, resolved = {}, {}
        for correction in self._corrections(db, at):
            payload = correction["payload"]
            if correction["kind"] == "link":
                keep, other = payload["keep_id"], payload["other_id"]
                for observation_id, item_id in assign.items():
                    if item_id == other:
                        assign[observation_id] = keep
                    if item_id in (other, keep) and not isinstance(resolved.get(observation_id), dict):
                        resolved[observation_id] = "cleared"
                for source, target in merged.items():
                    if target == other:
                        merged[source] = keep
                merged[other] = keep
            elif correction["kind"] == "unlink":
                observation_id = payload["observation_id"]
                if observation_id in assign:
                    assign[observation_id] = payload["new_item_id"]
                    current = resolved.get(observation_id)
                    if isinstance(current, dict):
                        current["remove"] = payload["from_item_id"]
                    elif current != "cleared":
                        resolved[observation_id] = {"remove": payload["from_item_id"]}
            elif correction["kind"] == "assign":
                observation_id = payload["observation_id"]
                if observation_id in assign:
                    assign[observation_id] = payload["item_id"]
                    resolved[observation_id] = {"assigned": payload["item_id"]}
        return assign, merged, resolved

    def _banks(self, db, assign, resolved, tombstoned, embedder_tag):
        """ItemBank per live item from the embeddings table (oldest first so FIFO
        eviction keeps the newest 32), only vectors of embedder_tag. A parked
        observation seeds no bank; once assigned, its stored vector seeds the
        chosen item's bank (never re-embedded)."""
        banks = {}
        rows = db.execute("""SELECT e.observation_id,e.dim,e.vector,o.record,o.candidates FROM embeddings e
            JOIN local_observations o USING(profile_id,observation_id)
            WHERE e.profile_id=? AND e.embedder=? AND o.record IS NOT NULL
            ORDER BY o.observed_at_ms,o.decided_at_ms,o.observation_id""", (self.profile_id, embedder_tag))
        for row in rows:
            item_id = assign.get(row["observation_id"])
            if item_id is None or item_id in tombstoned or self._parked(row, resolved):
                continue
            try:
                vector = _vector_from_bytes(row["vector"], row["dim"])
            except ValueError:
                continue
            frame_id = json.loads(row["record"]).get("frame_id")
            banks.setdefault(item_id, ItemBank(item_id)).add(row["observation_id"], frame_id, embedder_tag, vector)
        return banks

    @staticmethod
    def _parked(row, resolved) -> bool:
        """True for an observation the matcher could not attribute (B-14) and no
        correction has attributed since: it has a candidates list, is stored under
        a placeholder item the projection never lists, seeds no bank and only marks
        its candidates as lookalikes. assign_observation (replayed as "assigned" in
        resolved) ends that state."""
        try:
            value = row["candidates"]
        except (IndexError, KeyError):
            return False
        resolution = resolved.get(row["observation_id"])
        attributed = resolution == "cleared" or (isinstance(resolution, dict) and "assigned" in resolution)
        return bool(value) and value != "[]" and not attributed

    def _co_visible_items(self, db, packet, frame_id, assign):
        """Items holding an observation of the same device, episode and frame."""
        rows = db.execute("SELECT observation_id,item_id,record FROM local_observations WHERE profile_id=? AND device_id=? AND episode_id=? AND record IS NOT NULL", (self.profile_id, packet.device_id, packet.episode_id))
        items = set()
        for row in rows:
            if json.loads(row["record"]).get("frame_id") == frame_id:
                items.add(assign.get(row["observation_id"], row["item_id"]))
        return items

    @staticmethod
    def _as_of_ms(as_of):
        if as_of is None:
            return None
        if isinstance(as_of, bool) or not isinstance(as_of, (int, float)) or not math.isfinite(as_of) or as_of < 0:
            raise ValueError("as_of must be nonnegative epoch milliseconds")
        return int(as_of)

    @staticmethod
    def _age_item(item, eval_ms):
        """Clock-only ageing (B-11) of one projected item, evaluated at eval_ms.

        Pure and idempotent: returns a copy. Only a 'placed' location ages (a
        pickup, an uncertain outcome or a bad capture clock already says so).
        age = eval_ms - observed_at_ms; age > AGE_ABSTAIN_MS -> location_status
        'stale', stale_reason "age", location_text kept as history; otherwise
        age > AGE_STALE_MS -> still 'placed', stale_reason "age". Both set
        aged=True; everything else reads aged=False.
        """
        aged = dict(item, aged=False)
        aged.setdefault("lookalikes", [])  # CP3 field; a projection stored before CP3 lacks it
        observed = item.get("observed_at_ms")
        if eval_ms is None or observed is None or item.get("location_status") != "placed":
            return aged
        age = eval_ms - observed
        if age > AGE_ABSTAIN_MS:
            aged.update(location_status="stale", stale_reason="age", aged=True)
        elif age > AGE_STALE_MS:
            aged.update(stale_reason="age", aged=True)
        return aged

    @staticmethod
    def _resolved_identity(row, observation, item_id, merged, resolved):
        """(identity_state, candidates, identity_source) of one observation after
        corrections: a link or an assign clears its candidates (ambiguous reads
        provisional), an unlink removes the ruled-out item; candidate ids follow
        item merges and never name the item itself. An assigned observation reads
        trusted with source "user_assigned" while the assertion stands (the stored
        record says the same); an unlink after it withdraws the assertion, so it
        reads provisional again. Every other record's source is "processor"."""
        def follow(candidate):
            seen = set()
            while candidate in merged and candidate not in seen:
                seen.add(candidate)
                candidate = merged[candidate]
            return candidate
        state = observation["identity_state"]
        source = observation.get("identity_source") or "processor"
        raw = json.loads(row["candidates"]) if row["candidates"] else []
        resolution = resolved.get(row["observation_id"])
        candidates = raw
        if resolution == "cleared" or (isinstance(resolution, dict) and "assigned" in resolution):
            candidates = []
        if isinstance(resolution, dict) and "remove" in resolution:
            removed = follow(resolution["remove"])
            candidates = [candidate for candidate in candidates if follow(candidate) != removed]
        mapped = []
        for candidate in candidates:
            candidate = follow(candidate)
            if candidate != item_id and candidate not in mapped:
                mapped.append(candidate)
        if isinstance(resolution, dict) and "assigned" in resolution:
            state, source = ("trusted", "user_assigned") if "remove" not in resolution else ("provisional", "user_assigned")
        # A processor-declared 'ambiguous' without candidates stays ambiguous; one the
        # matcher produced reads provisional once every candidate is settled.
        elif state == "ambiguous" and not mapped and (resolution is not None or raw):
            state = "provisional"
        return state, mapped, source

    def _projection(self, db, as_of=None, *, age=True):
        """Items replayed from stored decisions up to as_of (default: everything).

        With age=True (every reader) the items are aged at as_of when given, else at
        the injected clock. _rebuild_projection passes age=False so current_items
        never depends on wall-clock time.
        """
        return self._project(db, as_of, age=age)[0]

    def _project(self, db, as_of=None, *, age=True):
        """(items, parked) as of as_of: the projection of _projection plus the parked
        observations still unattributed at that time, oldest first, each
        {observation_id, observed_at_ms, candidates: [item_id...]} with candidates
        mapped through merges (answer_text names the newest one for a group)."""
        at = self._as_of_ms(as_of)
        rows = db.execute("""SELECT o.* FROM local_observations o WHERE o.profile_id=? AND o.record IS NOT NULL
            ORDER BY o.observed_at_ms,o.decided_at_ms,o.observation_id""", (self.profile_id,)).fetchall()
        # CP3: observations are read through the effective assignment (corrections up
        # to as_of replayed in order; a correction after as_of is not applied) and an
        # item tombstone applies only once written (a linked-away item is visible
        # before its link). Redacted rows have record NULL whatever the time.
        assign, merged, resolved = self._assignments(db, at)
        tombstoned = {row[0] for row in db.execute("SELECT item_id,at_ms FROM item_tombstones WHERE profile_id=?", (self.profile_id,)) if at is None or row[1] <= at}
        items, latest_candidates, parked, own_label = {}, {}, [], {}
        for row in rows:
            if at is not None and row["observed_at_ms"] > at:
                continue
            item_id = assign.get(row["observation_id"], row["item_id"])
            if item_id in tombstoned:
                continue
            observation = json.loads(row["record"])
            identity_state, candidates, _ = self._resolved_identity(row, observation, item_id, merged, resolved)
            if self._parked(row, resolved):
                # B-14: an unattributed observation is not an item and updates no item;
                # it only says that its candidates cannot be told apart (below).
                parked.append({"observation_id": row["observation_id"], "observed_at_ms": row["observed_at_ms"], "candidates": candidates})
                continue
            # The name is the processor's latest label for an observation it assigned
            # to this item itself; evidence linked in by a correction never renames the
            # kept item (an unlink-created item has only linked-in evidence and takes
            # that label). A user name (item_names) overrides both.
            if row["item_id"] == item_id or item_id not in own_label:
                own_label[item_id] = observation["label"]
            trusted = identity_state == "trusted"
            placed = bool(trusted and observation["outcome"] == "placed_on_surface" and observation.get("location_text"))
            clock_bad = observation.get("clock_status") != "ok"
            # Contract (2026-10-07): location_status uses the spec vocabulary
            # placed | sighted | inferred | stale | unknown. 'inferred' (containment)
            # has no producer yet and is never emitted here. Location evidence and
            # identity are independent fields: a provisional identity can still have
            # a sighting; only a trusted identity with a recorded surface is 'placed'.
            stale = None
            if observation["outcome"] == "picked_up":
                location_status, stale = "stale", "Observed pickup; resting location is unknown"
            elif observation["outcome"] == "uncertain":
                location_status, stale = "unknown", "Episode outcome was uncertain; no resting location recorded"
            elif placed:
                location_status = "placed"
            else:
                location_status = "sighted"
                stale = ("Only a sighting; no resting placement recorded" if trusted
                         else "Only a sighting; placement and identity are unverified")
            if clock_bad:
                location_status, stale = "unknown", "Capture clock is implausible; location time is uncertain"
            items[item_id] = {
                "item_id": item_id, "name": observation["label"],
                "identity_status": identity_state, "relevance": "candidate",
                "location_status": location_status,
                "observed_at_ms": row["observed_at_ms"] if row["observed_at_ms"] > 0 else None,
                "location_text": observation.get("location_text") if placed else None,
                "stale_reason": stale, "index_pending": False, "image_url": None,
                # aged is an evaluated field: always False in storage, set by _age_item on read.
                "aged": False,
                "source": "local_evidence", "observation_id": row["observation_id"],
                # The photo is the answer: the whole keyframe is the reference image and
                # the target region travels with it (spec answer contract, reference_image).
                "reference_image": {"frame_id": observation["frame_id"], "bbox": list(observation["bbox"])},
                # CP3: items this one could not be told apart from (filled below).
                "lookalikes": [],
            }
            latest_candidates[item_id] = candidates
        for item_id, item in items.items():
            item["name"] = own_label[item_id]
        # CP3 lookalikes: every parked observation's candidates form a group, as does
        # an item whose latest observation is ambiguous with candidates; every member
        # lists the others and reads 'ambiguous' (a group never upgrades anyone; it
        # can only withhold confidence). A link that merges the candidates, or the
        # erasure of all but one, dissolves the group.
        lookalikes = {item_id: set() for item_id in items}
        groups = [set(entry["candidates"]) for entry in parked]
        groups += [{item_id} | set(candidates) for item_id, candidates in latest_candidates.items()
                   if items[item_id]["identity_status"] == "ambiguous" and candidates]
        for group in groups:
            group = {member for member in group if member in items}
            if len(group) < 2:
                continue
            for member in group:
                lookalikes[member] |= group - {member}
        for item_id, others in lookalikes.items():
            if others:
                items[item_id]["identity_status"] = "ambiguous"
                items[item_id]["lookalikes"] = sorted(others)
        for row in db.execute("SELECT item_id,name,at_ms FROM item_names WHERE profile_id=? AND name IS NOT NULL ORDER BY at_ms,name_id", (self.profile_id,)):
            if row["item_id"] in items and (at is None or row["at_ms"] <= at):
                items[row["item_id"]]["name"] = row["name"]
                items[row["item_id"]]["source"] = "user_named_local_evidence"
        if age:
            eval_ms = at if at is not None else self._now_ms()
            items = {item_id: self._age_item(item, eval_ms) for item_id, item in items.items()}
        return items, parked

    def _rebuild_projection(self, db):
        # Stored without ageing: the projection must not depend on wall-clock time.
        items = self._projection(db, age=False)
        db.execute("DELETE FROM current_items WHERE profile_id=?", (self.profile_id,))
        for item_id, record in items.items():
            db.execute("INSERT INTO current_items VALUES(?,?,?)", (self.profile_id, item_id, _json(record)))
        return items

    def _pending(self, db):
        return bool(db.execute("SELECT 1 FROM episode_jobs WHERE profile_id=? AND status IN ('pending','processing') LIMIT 1", (self.profile_id,)).fetchone())

    def list_items(self, query='', limit=50, *, as_of=None) -> list[dict]:
        """The catalogue, aged at as_of (epoch ms) or at the injected clock.

        Without as_of this reads the stored projection and ages it on the way out;
        with as_of it replays stored decisions up to that time (the same view
        answer_text uses), so items and answers agree at any evaluation time.
        Neither path writes current_items.
        """
        if not isinstance(query, str) or len(query) > 2000 or type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError("Invalid catalogue query")
        at = self._as_of_ms(as_of)
        with self._connection() as db:
            if at is None:
                now = self._now_ms()
                items = [self._age_item(json.loads(row[0]), now) for row in db.execute("SELECT record FROM current_items WHERE profile_id=?", (self.profile_id,))]
            else:
                items = list(self._projection(db, at).values())
            pending = self._pending(db)
        words = self._query_words(query)
        items = [dict(item, index_pending=pending) for item in items if self._matches(item, words, query)]
        return sorted(items, key=lambda x: (-(x["observed_at_ms"] or 0), x["item_id"]))[:limit]

    @staticmethod
    def _query_words(query):
        return set(re.findall(r"[\w]+", query.casefold())) - {"where", "is", "are", "my", "the", "a", "an", "did", "i", "leave", "find", "please", "can", "you", "me", "show"}

    def _matches(self, item, words, query):
        return not words or query.strip() == item["item_id"] or words <= self._query_words(item["name"])

    def get_item(self, item_id, *, as_of=None) -> dict:
        """One catalogue item aged at as_of or at the injected clock (see list_items)."""
        if not isinstance(item_id, str) or len(item_id) > 100:
            raise KeyError("Unknown item")
        at = self._as_of_ms(as_of)
        with self._connection() as db:
            if at is None:
                row = db.execute("SELECT record FROM current_items WHERE profile_id=? AND item_id=?", (self.profile_id, item_id)).fetchone()
                if row is None:
                    raise KeyError("Unknown item")
                item = self._age_item(json.loads(row["record"]), self._now_ms())
            else:
                item = self._projection(db, at).get(item_id)
                if item is None:
                    raise KeyError("Unknown item")
            return dict(item, index_pending=self._pending(db))

    def _item_rows(self, db, item_id):
        """The observation rows effectively assigned to item_id (corrections applied), oldest first."""
        assign, _, _ = self._assignments(db)
        rows = db.execute("SELECT * FROM local_observations WHERE profile_id=? AND record IS NOT NULL ORDER BY observed_at_ms,decided_at_ms,observation_id", (self.profile_id,))
        return [row for row in rows if assign.get(row["observation_id"]) == item_id]

    def item_history(self, item_id) -> list[dict]:
        self.get_item(item_id)
        with self._connection() as db:
            return [json.loads(row["record"]) for row in self._item_rows(db, item_id)]

    def item_evidence(self, item_id) -> list[dict]:
        """CP3: the item's observations as evidence rows, oldest first:
        {observation_id, item_id, observed_at_ms, frame_id, reference_image
        {frame_id, bbox}, identity_status, identity_source, outcome, location_text,
        candidates, embedded}. identity_status and candidates are the observation's
        own after corrections (not the item's group status); identity_source is
        "processor" or "user_assigned"; location_text is set only for a trusted
        placement. KeyError for an unknown item."""
        self.get_item(item_id)
        with self._connection() as db:
            _, merged, resolved = self._assignments(db)
            embedded = {row[0] for row in db.execute("SELECT observation_id FROM embeddings WHERE profile_id=?", (self.profile_id,))}
            evidence = []
            for row in self._item_rows(db, item_id):
                record = json.loads(row["record"])
                identity_state, candidates, identity_source = self._resolved_identity(row, record, item_id, merged, resolved)
                placed = identity_state == "trusted" and record.get("outcome") == "placed_on_surface" and bool(record.get("location_text"))
                evidence.append({"observation_id": row["observation_id"], "item_id": item_id,
                                 "observed_at_ms": row["observed_at_ms"] if row["observed_at_ms"] > 0 else None,
                                 "frame_id": record["frame_id"],
                                 "reference_image": {"frame_id": record["frame_id"], "bbox": list(record["bbox"])},
                                 "identity_status": identity_state, "identity_source": identity_source, "outcome": record["outcome"],
                                 "location_text": record.get("location_text") if placed else None,
                                 "candidates": candidates, "embedded": row["observation_id"] in embedded})
            return evidence

    def _keyframe_bytes(self, db, row):
        """The stored keyframe bytes of one observation row, or None when its
        revision is redacted or the frame is absent (the item_image rules)."""
        revision = db.execute("SELECT packet FROM episode_revisions WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no=? AND redacted=0", (self.profile_id, row["device_id"], row["episode_id"], row["revision_no"])).fetchone()
        if revision is None or revision[0] is None:
            return None
        packet = parse_packet(bytes(revision[0]))
        observation = json.loads(row["record"])
        frame = next((f for f in packet.keyframes if f.frame_id == observation["frame_id"]), None)
        return None if frame is None else jpeg_bytes(frame.jpeg_b64)

    def observation_image(self, item_id, observation_id) -> bytes | None:
        """CP3: that observation's keyframe bytes, unmodified, when the observation
        is currently assigned to item_id in this profile; None otherwise (unknown
        item or observation, other profile, redacted), never an error."""
        if not isinstance(item_id, str) or not isinstance(observation_id, str) or len(item_id) > 100 or len(observation_id) > 100:
            return None
        with self._connection() as db:
            if not db.execute("SELECT 1 FROM current_items WHERE profile_id=? AND item_id=?", (self.profile_id, item_id)).fetchone():
                return None
            row = db.execute("SELECT * FROM local_observations WHERE profile_id=? AND observation_id=? AND record IS NOT NULL", (self.profile_id, observation_id)).fetchone()
            if row is None:
                return None
            assign, _, _ = self._assignments(db)
            if assign.get(observation_id) != item_id:
                return None
            return self._keyframe_bytes(db, row)

    def item_image(self, item_id) -> bytes | None:
        """The item's reference image: the stored keyframe bytes, unmodified.

        Contract (2026-10-07): the photo is the answer, so the whole keyframe is
        returned and the target region travels as reference_image.bbox on the item.
        No derived crop is written to disk; identity crops are a later stage's
        in-memory concern.
        """
        with self._connection() as db:
            item = db.execute("SELECT record FROM current_items WHERE profile_id=? AND item_id=?", (self.profile_id, item_id)).fetchone()
            if item is None:
                return None
            item = json.loads(item[0])
            row = db.execute("SELECT * FROM local_observations WHERE profile_id=? AND observation_id=? AND record IS NOT NULL", (self.profile_id, item["observation_id"])).fetchone()
            if row is None:
                return None
            return self._keyframe_bytes(db, row)

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

    # CP3 corrections. Both append a corrections row that _assignments replays in
    # order (so rebuild_all and as_of reproduce them from storage) and an audit row;
    # local_observations.item_id is never rewritten. actor is the session role
    # string (e.g. "caregiver_pin"), never a named person (B-15).
    def link_items(self, keep_id, other_id, actor) -> dict:
        """"Same object": merge other_id into keep_id. Refuses with CannotLinkError
        (a ValueError whose str() is "cannot-link") when a cannot-link exists
        between them; KeyError when either item is unknown; ValueError for the same
        id twice or a bad actor. other_id's cannot-links transfer to keep_id,
        other_id is tombstoned, keep_id's name is kept, every observation of both
        reads as settled (no candidates). Audit row user_linked. Returns keep_id's item."""
        _check_actor(actor)
        for value in (keep_id, other_id):
            if not isinstance(value, str) or not 1 <= len(value) <= 100:
                raise KeyError("Unknown item")
        if keep_id == other_id:
            raise ValueError("An item cannot be linked to itself")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            for value in (keep_id, other_id):
                if not db.execute("SELECT 1 FROM current_items WHERE profile_id=? AND item_id=?", (self.profile_id, value)).fetchone():
                    raise KeyError("Unknown item")
            a, b = sorted((keep_id, other_id))
            if db.execute("SELECT 1 FROM local_cannot_links WHERE profile_id=? AND item_a=? AND item_b=?", (self.profile_id, a, b)).fetchone():
                raise CannotLinkError()
            now = self._now_ms()
            correction_id = str(uuid.uuid4())
            db.execute("INSERT INTO corrections(profile_id,correction_id,kind,at_ms,actor,payload) VALUES(?,?,?,?,?,?)",
                       (self.profile_id, correction_id, "link", now, actor, _json({"keep_id": keep_id, "other_id": other_id})))
            # Whatever could not be other_id cannot be keep_id either; the original rows stay.
            for row in db.execute("SELECT item_a,item_b FROM local_cannot_links WHERE profile_id=? AND (item_a=? OR item_b=?)", (self.profile_id, other_id, other_id)).fetchall():
                third = row["item_b"] if row["item_a"] == other_id else row["item_a"]
                if third != keep_id:
                    x, y = sorted((keep_id, third))
                    db.execute("INSERT OR IGNORE INTO local_cannot_links VALUES(?,?,?)", (self.profile_id, x, y))
            db.execute("INSERT OR IGNORE INTO item_tombstones VALUES(?,?,?)", (self.profile_id, other_id, now))
            db.execute("INSERT INTO local_audit(profile_id,at_ms,action,item_id,detail) VALUES(?,?,?,?,?)",
                       (self.profile_id, now, "user_linked", keep_id, _json({"other_item_id": other_id, "actor": actor, "correction_id": correction_id})))
            self._rebuild_projection(db)
        return self.get_item(keep_id)

    def unlink_observation(self, observation_id, actor, *, item_id=None) -> dict:
        """"Not this one": move observation_id out of its current item into a new
        item and record a cannot-link between the two. KeyError for an unknown or
        redacted observation, or (with item_id given) one not currently assigned to
        that item; ValueError when it is the item's only observation (nothing to
        separate) or for a bad actor. Audit row user_unlinked. Returns the new item."""
        _check_actor(actor)
        if not isinstance(observation_id, str) or not 1 <= len(observation_id) <= 100:
            raise KeyError("Unknown observation")
        if item_id is not None and (not isinstance(item_id, str) or not 1 <= len(item_id) <= 100):
            raise KeyError("Unknown item")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT observation_id FROM local_observations WHERE profile_id=? AND observation_id=? AND record IS NOT NULL", (self.profile_id, observation_id)).fetchone()
            if row is None:
                raise KeyError("Unknown observation")
            assign, _, _ = self._assignments(db)
            from_item = assign.get(observation_id)
            if from_item is None or not db.execute("SELECT 1 FROM current_items WHERE profile_id=? AND item_id=?", (self.profile_id, from_item)).fetchone():
                raise KeyError("Unknown observation")
            if item_id is not None and item_id != from_item:
                raise KeyError("Unknown observation")
            if sum(1 for item in assign.values() if item == from_item) < 2:
                raise ValueError("Cannot unlink the only observation of an item")
            now = self._now_ms()
            new_item = str(uuid.uuid4())
            correction_id = str(uuid.uuid4())
            db.execute("INSERT INTO corrections(profile_id,correction_id,kind,at_ms,actor,payload) VALUES(?,?,?,?,?,?)",
                       (self.profile_id, correction_id, "unlink", now, actor, _json({"observation_id": observation_id, "from_item_id": from_item, "new_item_id": new_item})))
            x, y = sorted((from_item, new_item))
            db.execute("INSERT OR IGNORE INTO local_cannot_links VALUES(?,?,?)", (self.profile_id, x, y))
            db.execute("INSERT INTO local_audit(profile_id,at_ms,action,item_id,detail) VALUES(?,?,?,?,?)",
                       (self.profile_id, now, "user_unlinked", new_item, _json({"from_item_id": from_item, "observation_id": observation_id, "actor": actor, "correction_id": correction_id})))
            self._rebuild_projection(db)
        return self.get_item(new_item)

    def assign_observation(self, observation_id, item_id, actor) -> dict:
        """"Which one is yours" -> this one: attribute a parked ambiguous observation
        to item_id. It becomes that item's evidence (its stored embedding seeds the
        bank; nothing is re-embedded) with no candidates, and its identity is
        user-asserted: the stored record is rewritten to identity_state "trusted",
        identity_source "user_assigned" (processor-derived records carry
        "processor"); outcome and location fields stay exactly as stored, so a
        sighting is still a sighting and answers stay hedged.

        What is inferred and what is not (Oversight, CP3): the user said "this
        sighting is item_id", nothing more. The placeholder's own cannot-links (the
        items co-visible with this sighting) transfer to item_id, because an item
        holding this sighting cannot be one seen beside it. NO cannot-link is added
        between item_id and the other candidates: they may be fragmented duplicates
        of one object that a later link should be free to merge; they are recorded
        in the payload as other_candidates for information only.

        KeyError for an unknown or redacted observation or an unknown item;
        ValueError("not-ambiguous") when the observation is not parked (ordinary
        evidence, or already assigned); CannotLinkError when item_id holds an
        observation co-visible with this one (same device, episode and frame) or a
        cannot-link row already separates them. Recorded as a corrections row of
        kind 'assign' (replayed in order by rebuild_all; a fresh store and as_of
        derive the same trusted/user_assigned reading from it) and an audit row
        user_assigned. A later unlink of the observation withdraws the assertion:
        it then reads provisional again. Returns item_id's item."""
        _check_actor(actor)
        if not isinstance(observation_id, str) or not 1 <= len(observation_id) <= 100:
            raise KeyError("Unknown observation")
        if not isinstance(item_id, str) or not 1 <= len(item_id) <= 100:
            raise KeyError("Unknown item")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM local_observations WHERE profile_id=? AND observation_id=? AND record IS NOT NULL", (self.profile_id, observation_id)).fetchone()
            if row is None:
                raise KeyError("Unknown observation")
            if not db.execute("SELECT 1 FROM current_items WHERE profile_id=? AND item_id=?", (self.profile_id, item_id)).fetchone():
                raise KeyError("Unknown item")
            assign, merged, resolved = self._assignments(db)
            if not self._parked(row, resolved):
                raise ValueError("not-ambiguous")
            placeholder = assign.get(observation_id, row["item_id"])
            record = json.loads(row["record"])
            co_visible = set()
            for other in db.execute("SELECT observation_id,item_id,record FROM local_observations WHERE profile_id=? AND device_id=? AND episode_id=? AND record IS NOT NULL", (self.profile_id, row["device_id"], row["episode_id"])):
                if other["observation_id"] != observation_id and json.loads(other["record"]).get("frame_id") == record.get("frame_id"):
                    co_visible.add(assign.get(other["observation_id"], other["item_id"]))
            a, b = sorted((placeholder, item_id))
            if item_id in co_visible or db.execute("SELECT 1 FROM local_cannot_links WHERE profile_id=? AND item_a=? AND item_b=?", (self.profile_id, a, b)).fetchone():
                raise CannotLinkError()
            _, candidates, _ = self._resolved_identity(row, record, placeholder, merged, {})
            other_candidates = sorted(candidate for candidate in candidates if candidate != item_id)
            now = self._now_ms()
            correction_id = str(uuid.uuid4())
            db.execute("INSERT INTO corrections(profile_id,correction_id,kind,at_ms,actor,payload) VALUES(?,?,?,?,?,?)",
                       (self.profile_id, correction_id, "assign", now, actor,
                        _json({"observation_id": observation_id, "item_id": item_id, "from_item_id": placeholder, "other_candidates": other_candidates})))
            # The stored record is immutable (ledger invariant: observations are
            # evidence, interpretations are versioned). The user-asserted reading
            # (identity trusted, identity_source "user_assigned") is derived from this
            # correction by _resolved_identity for the projection, evidence and history.
            # Whatever was co-visible with this observation cannot be item_id either.
            for link in db.execute("SELECT item_a,item_b FROM local_cannot_links WHERE profile_id=? AND (item_a=? OR item_b=?)", (self.profile_id, placeholder, placeholder)).fetchall():
                third = link["item_b"] if link["item_a"] == placeholder else link["item_a"]
                if third != item_id:
                    x, y = sorted((item_id, third))
                    db.execute("INSERT OR IGNORE INTO local_cannot_links VALUES(?,?,?)", (self.profile_id, x, y))
            db.execute("INSERT INTO local_audit(profile_id,at_ms,action,item_id,detail) VALUES(?,?,?,?,?)",
                       (self.profile_id, now, "user_assigned", item_id, _json({"observation_id": observation_id, "actor": actor, "correction_id": correction_id, "other_candidates": other_candidates})))
            self._rebuild_projection(db)
        return self.get_item(item_id)

    def answer_text(self, text, *, as_of=None) -> dict:
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise ValueError("Invalid question")
        at = self._as_of_ms(as_of)
        with self._connection() as db:
            projected, parked = self._project(db, at)
            items = list(projected.values())
            pending = self._pending(db)
        words = self._query_words(text)
        members = [dict(item, index_pending=pending) for item in items if self._matches(item, words, text)] if words else []
        answer = {"shape": "abstain", "text": "I have no matching stored evidence.", "members": [], "index_pending": pending}
        if not members:
            return answer
        if len(members) > 1:
            members = members[:8]
            options = [{"item_id": x["item_id"], "name": x["name"]} for x in members]
            # CP3 group (B-14): the matched items are mutual lookalikes (each lists
            # every other), so the question is which physical one, not which name.
            # Each member keeps its own evidence and certainty; nothing is upgraded.
            ids = {x["item_id"] for x in members}
            if all(ids - {x["item_id"]} <= set(x.get("lookalikes") or ()) for x in members):
                group = [dict(x, provenance={"observation_id": x.get("observation_id"), "identity_status": x["identity_status"]}) for x in members]
                # The newest parked observation whose candidates are exactly these
                # members: the browser passes it to assign_observation when the user
                # picks one ("which one is yours" -> this one). null when none.
                unresolved = next((entry["observation_id"] for entry in reversed(parked) if set(entry["candidates"]) == ids), None)
                return dict(answer, shape="group", text=f"I have {len(group)} items that look alike; which one is yours?",
                            members=group, question="Which one is yours?", options=options,
                            unresolved_observation_id=unresolved)
            return dict(answer, shape="clarify", text="Which stored item do you mean?", members=members, question="Which stored item?", options=options)
        item = members[0]
        shape = "hedged"
        # Clock-only staleness (B-11): the projection above is already aged at as_of
        # (or now). Confident needs trusted + placed AND not aged; an aged placement
        # is hedged with its observed date; beyond AGE_ABSTAIN_MS the historical
        # location_text is not usable evidence, so the answer abstains without members.
        if item["identity_status"] == "trusted" and item["location_status"] == "placed" and not item.get("aged"):
            message = f"The recorded location of {item['name']} is {item['location_text']}."
            shape = "confident"
        elif item.get("stale_reason") == "age" and item["location_text"]:
            if item["location_status"] == "stale":
                return dict(answer, text=f"I have no recent evidence for {item['name']}.")
            message = (f"I recorded {item['name']} at {item['location_text']} on {self._date_text(item['observed_at_ms'])}, "
                       "but that was more than a day ago; it may have moved since.")
        elif item["location_text"]:
            message = f"Earlier evidence recorded {item['name']} at {item['location_text']}; its current location is uncertain."
        elif item.get("lookalikes"):
            # CP3: one name matched, but the item has lookalikes that did not; the
            # identity is not separable, so the answer hedges without a location.
            message = (f"I have evidence for {item['name']}, but it looks like {len(item['lookalikes'])} other stored "
                       f"item{'s' if len(item['lookalikes']) != 1 else ''} and I cannot tell them apart.")
        else:
            message = f"I have a stored sighting for {item['name']}, but cannot confirm its identity or current resting location."
        return dict(answer, shape=shape, text=message, members=members)

    @staticmethod
    def _date_text(observed_ms):
        """UTC calendar date of an observation for answer text (deterministic across
        machines; the store has no user time zone)."""
        try:
            return datetime.fromtimestamp(observed_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        except (OverflowError, OSError, ValueError, TypeError):
            return "an unknown date"

    def rebuild_all(self, *, as_of=None) -> dict:
        """Replay stored decisions (observation assignments, stored embeddings'
        decisions, corrections in order, names) into the projection. No model is
        rerun and nothing is re-embedded; with as_of the replay stops there and
        current_items is left untouched."""
        at = self._as_of_ms(as_of)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if at is None:
                now = self._now_ms()
                items = {item_id: self._age_item(item, now) for item_id, item in self._rebuild_projection(db).items()}
            else:
                items = self._projection(db, at)
            return {"items": list(items.values()), "count": len(items), "as_of": at, "model_rerun": False,
                    "corrections_replayed": len(self._corrections(db, at)),
                    "embeddings_replayed": db.execute("SELECT count(*) FROM embeddings WHERE profile_id=?", (self.profile_id,)).fetchone()[0],
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
            # CP3: observations belong to items through the effective assignment
            # (corrections applied), so a linked-in observation is erased with its item.
            assign, _, _ = self._assignments(db)
            location = {row["observation_id"]: (row["device_id"], row["episode_id"]) for row in
                        db.execute("SELECT observation_id,device_id,episode_id FROM local_observations WHERE profile_id=?", (self.profile_id,))}
            def episodes_of(target):
                return {location[o] for o, item in assign.items() if item == target and o in location}
            def items_in(device, episode):
                return {assign[o] for o, where in location.items() if where == (device, episode) and o in assign}
            episodes = episodes_of(item_id)
            affected = {item_id}
            # Transitive closure prevents a second packet from restoring a co-item.
            changed = True
            while changed:
                before = (len(episodes), len(affected))
                for device, episode in list(episodes):
                    affected.update(items_in(device, episode))
                for target in list(affected):
                    episodes.update(episodes_of(target))
                changed = before != (len(episodes), len(affected))
            for target in affected:
                db.execute("INSERT OR IGNORE INTO item_tombstones VALUES(?,?,?)", (self.profile_id, target, self._now_ms()))
                # Erase by effective AND processing-time assignment (over-erasure is the
                # safe direction); the embedding derived from an erased crop goes with it.
                erased = {o for o, item in assign.items() if item == target}
                erased.update(r[0] for r in db.execute("SELECT observation_id FROM local_observations WHERE profile_id=? AND item_id=?", (self.profile_id, target)))
                for observation_id in erased:
                    db.execute("UPDATE local_observations SET record=NULL,candidates=NULL WHERE profile_id=? AND observation_id=?", (self.profile_id, observation_id))
                    db.execute("DELETE FROM embeddings WHERE profile_id=? AND observation_id=?", (self.profile_id, observation_id))
                db.execute("UPDATE item_names SET name=NULL WHERE profile_id=? AND item_id=?", (self.profile_id, target))
                db.execute("DELETE FROM current_items WHERE profile_id=? AND item_id=?", (self.profile_id, target))
            for device, episode in episodes:
                db.execute("INSERT OR IGNORE INTO episode_tombstones VALUES(?,?,?,?)", (self.profile_id, device, episode, self._now_ms()))
                db.execute("UPDATE episode_revisions SET packet=NULL,redacted=1 WHERE profile_id=? AND device_id=? AND episode_id=?", (self.profile_id, device, episode))
                db.execute("UPDATE episode_jobs SET status='redacted',token=NULL,lease_until=NULL,error=NULL WHERE profile_id=? AND device_id=? AND episode_id=?", (self.profile_id, device, episode))
            db.execute("INSERT INTO local_audit(profile_id,at_ms,action,item_id,detail) VALUES(?,?,?,?,?)", (self.profile_id, self._now_ms(), "logical_redaction", item_id, _json({"affected_items": len(affected), "episodes": len(episodes)})))
            return {"item_id": item_id, "redacted": True, "affected_items": len(affected), "scope": "logical", "forensic_erasure": False}
