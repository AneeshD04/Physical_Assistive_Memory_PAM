"""Additive keyless episode ledger. Legacy v1 records are never reinterpreted.

Evidence/decisions are append-only through ordinary APIs. Erasure (erase_item,
erase_profile; redact_item is the CP1 alias) is a separate, audited operation that
rewrites personal content to non-identifying stubs and, for a whole profile,
rebuilds the database file with VACUUM INTO. That reduces residue in the live file;
it is not a forensic guarantee about filesystem remnants, journals already
overwritten, or backups, and nothing here claims one.

CP4 adds idle keyframes (a rolling cache, not evidence), re-observation
(perception/reobservation.py), containment -> inferred locations, retention tiers
with landmark reduction, and the explicit v1 migration. CP5 moves the answer
contract into perception/resolver.py (answer_text delegates to it), adds the
frame-accounting table frame_counters (ingest_telemetry / coverage; rows expire
with episodes_days) and stamps consent_version on observation rows. Windows,
thresholds and caps in this module are INITIAL VALUES from the build plan unless a
measurement is cited next to them.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
# datetime / timezone: coverage() turns a UTC day into its epoch window.

try:
    from .episode import parse_packet, parse_idle, parse_telemetry, jpeg_bytes, decode_jpeg, RevisionLimitError
    from .localizer import LocalObservation, localize
    from .identity import (ConformalMatcher, ItemBank, HandCoversRegion, crop_box, padded_crop_box, l2_normalise,
                           mask_from_rle, mask_sufficient, validate_embedder)
    from .hand_hull import hand_hull_mask, nearest_sample
    from .hand_busy import hand_busy
    from .reobservation import ReobservationMixin, inside_fraction, CONTAINMENT_INSIDE
    from .private_files import private_append_fd
    from .consent import CONSENT_VERSION
    from .resolver import (resolve, query_words, matches, age_item, date_text, AGE_STALE_MS, AGE_ABSTAIN_MS,
                           REASON_NEGATIVE_REOBSERVATION, REASON_PICKED_UP, REASON_UNCERTAIN,
                           REASON_SIGHTING_TRUSTED, REASON_SIGHTING_UNVERIFIED, REASON_CLOCK)
except ImportError:
    from episode import parse_packet, parse_idle, parse_telemetry, jpeg_bytes, decode_jpeg, RevisionLimitError
    from localizer import LocalObservation, localize
    from identity import (ConformalMatcher, ItemBank, HandCoversRegion, crop_box, padded_crop_box, l2_normalise,
                          mask_from_rle, mask_sufficient, validate_embedder)
    from hand_hull import hand_hull_mask, nearest_sample
    from hand_busy import hand_busy
    from reobservation import ReobservationMixin, inside_fraction, CONTAINMENT_INSIDE
    from private_files import private_append_fd
    from consent import CONSENT_VERSION
    from resolver import (resolve, query_words, matches, age_item, date_text, AGE_STALE_MS, AGE_ABSTAIN_MS,
                          REASON_NEGATIVE_REOBSERVATION, REASON_PICKED_UP, REASON_UNCERTAIN,
                          REASON_SIGHTING_TRUSTED, REASON_SIGHTING_UNVERIFIED, REASON_CLOCK)


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

# CP4 idle keyframe cache (build plan): a rolling cache, never evidence until a
# frame is promoted by a positive re-observation. Expiry uses the retention row's
# idle_hours (default IDLE_TTL_MS); the caps are per device (daily count) and per
# profile (bytes, oldest unpromoted evicted first).
IDLE_TTL_MS = 24 * 3600 * 1000
IDLE_MAX_PER_DAY = 2880
IDLE_CACHE_BYTES = 200 * 1024 * 1024
# Retention tiers (coordinator fix round: episodes_days default 30; validated
# ranges in set_retention). consent_version is the build constant
# perception.consent.CONSENT_VERSION, not a settable field.
RETENTION_DEFAULTS = {"episodes_days": 30, "idle_hours": 24, "landmarks_hours": 72}
RETENTION_RANGES = {"episodes_days": (7, 365), "idle_hours": (1, 72), "landmarks_hours": (1, 168)}
RETENTION_BATCH = 64
# A superseded accepted revision (a newer accepted revision of the same episode
# exists) keeps its packet bytes this long, then they are NULLed ('superseded').
SUPERSEDED_TTL_MS = 72 * 3600 * 1000
# erase_profile needs this exact confirmation (or True) from the caller; the
# server's route checks the user's typed text before calling the store.
ERASE_PROFILE_CONFIRM = "ERASE EVERYTHING"
# After erase_profile, a capture whose wall time is earlier than erased_at_ms
# minus this tolerance is refused (ValueError "captured before erasure"). The
# tolerance exists because a phone's clock can lag the laptop's by minutes; the
# trade-off is that a mirrored packet captured within the last five minutes
# before the erasure would be accepted again, which the browser covers by
# clearing its own mirror on erase-all (coordinator decision).
ERASED_BEFORE_TOLERANCE_MS = 5 * 60 * 1000
MIGRATION_V1_ID = "v1_observations"
LEGACY_OUTCOMES = {"placed": "placed_on_surface", "picked_up": "picked_up", "sighted": "sighted"}
# CP5: the consent_version stamped on every observation row the v1 migration writes
# (no disclosure of this build was acknowledged for that evidence).
LEGACY_CONSENT_VERSION = "legacy-v1"
# A live observation row: not redacted (record NULL) and not an erasure stub.
LIVE = "record IS NOT NULL AND erased=0"
# CP5 frame accounting: a telemetry window whose wall time is further than this
# ahead of the server clock is refused (same tolerance as packets and idle frames).
TELEMETRY_FUTURE_MS = 300000
DAY_UTC = re.compile(r"\d{4}-\d{2}-\d{2}")
# Daily coverage aggregates (coverage_days) are numbers only and are kept this long.
COVERAGE_DAYS_RETENTION_DAYS = 365
# Per-profile, per-UTC-day maintenance counters (Finance): bump_counter names.
# process_cpu_s / reobs_cpu_s are wall seconds of local processing / re-observation
# work; chat_local counts answer_text calls; image_serves / image_bytes count the
# evidence images (and their bytes) item_image / observation_image returned.
MAINTENANCE_COUNTERS = ("process_cpu_s", "reobs_cpu_s", "chat_local", "image_serves", "image_bytes")
MAX_SOURCE_NOTE = 400


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
# when the caller gives one, else at the injected clock. The windows AGE_STALE_MS
# (24 h: hedged) and AGE_ABSTAIN_MS (7 d: abstain) are defined in
# perception/resolver.py (imported above, re-exported here) so the resolver and
# the store age with one rule. Initial values from the build plan.


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
CREATE TABLE IF NOT EXISTS idle_frames (
 profile_id TEXT NOT NULL, device_id TEXT NOT NULL, frame_id TEXT NOT NULL, session_id TEXT NOT NULL,
 t_wall_ms INTEGER NOT NULL, received_ms INTEGER NOT NULL, width INTEGER NOT NULL, height INTEGER NOT NULL,
 jpeg BLOB, motion_energy REAL NOT NULL, expires_at_ms INTEGER NOT NULL,
 promoted INTEGER NOT NULL DEFAULT 0, consent_version TEXT, PRIMARY KEY(profile_id,device_id,frame_id));
CREATE INDEX IF NOT EXISTS idle_frames_time ON idle_frames(profile_id,device_id,t_wall_ms);
CREATE TABLE IF NOT EXISTS reobservations (
 profile_id TEXT NOT NULL, item_id TEXT NOT NULL, device_id TEXT NOT NULL, frame_id TEXT NOT NULL,
 t_wall_ms INTEGER NOT NULL, result TEXT NOT NULL CHECK(result IN ('present','gone','unknown')),
 region_diff REAL, registered INTEGER NOT NULL DEFAULT 0, embedded INTEGER NOT NULL DEFAULT 0,
 decided_ms INTEGER NOT NULL, gated INTEGER NOT NULL DEFAULT 0, bbox TEXT, PRIMARY KEY(profile_id,item_id,device_id,frame_id));
CREATE INDEX IF NOT EXISTS reobservations_item ON reobservations(profile_id,item_id,t_wall_ms);
CREATE TABLE IF NOT EXISTS containment (
 containment_no INTEGER PRIMARY KEY AUTOINCREMENT, profile_id TEXT NOT NULL,
 inner_item TEXT NOT NULL, outer_item TEXT NOT NULL, since_ms INTEGER NOT NULL, frame_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS retention (
 profile_id TEXT PRIMARY KEY, consent_version TEXT NOT NULL, episodes_days INTEGER NOT NULL,
 idle_hours INTEGER NOT NULL, landmarks_hours INTEGER NOT NULL, updated_ms INTEGER NOT NULL,
 acknowledged_version TEXT, erased_at_ms INTEGER);
CREATE TABLE IF NOT EXISTS migrations (
 profile_id TEXT NOT NULL, migration_id TEXT NOT NULL, from_version INTEGER NOT NULL,
 counts TEXT NOT NULL, at_ms INTEGER NOT NULL, actor TEXT NOT NULL,
 PRIMARY KEY(profile_id,migration_id));
CREATE TABLE IF NOT EXISTS maintenance_counters (
 profile_id TEXT NOT NULL, day TEXT NOT NULL, name TEXT NOT NULL, value REAL NOT NULL DEFAULT 0,
 PRIMARY KEY(profile_id,day,name));
CREATE TABLE IF NOT EXISTS frame_counters (
 profile_id TEXT NOT NULL, device_id TEXT NOT NULL, session_id TEXT NOT NULL, t_ms INTEGER NOT NULL,
 received_ms INTEGER NOT NULL, window_ms INTEGER NOT NULL, counters TEXT NOT NULL, timing TEXT NOT NULL,
 settings TEXT NOT NULL, PRIMARY KEY(profile_id,device_id,session_id,t_ms));
CREATE INDEX IF NOT EXISTS frame_counters_time ON frame_counters(profile_id,t_ms);
CREATE TABLE IF NOT EXISTS capture_gaps (
 gap_no INTEGER PRIMARY KEY AUTOINCREMENT, profile_id TEXT NOT NULL, device_id TEXT NOT NULL, session_id TEXT NOT NULL,
 source TEXT NOT NULL CHECK(source IN ('packet','telemetry')), t_from_ms INTEGER NOT NULL, t_to_ms INTEGER NOT NULL,
 gap_ms INTEGER NOT NULL, received_ms INTEGER NOT NULL, reason TEXT,
 UNIQUE(profile_id,device_id,session_id,source,t_from_ms,t_to_ms));
CREATE INDEX IF NOT EXISTS capture_gaps_time ON capture_gaps(profile_id,device_id,t_to_ms);
CREATE TABLE IF NOT EXISTS coverage_days (
 profile_id TEXT NOT NULL, day TEXT NOT NULL, aggregates TEXT NOT NULL, updated_ms INTEGER NOT NULL,
 PRIMARY KEY(profile_id,day));
"""

# CP3 (schema user_version 3) and CP4 (user_version 4): columns added to existing
# tables, applied by ensure_episode_columns as ALTER TABLE ADD COLUMN guarded by
# PRAGMA table_info, so an older database gains them without a rewrite and a
# current one is left alone.
# local_observations.candidates: JSON list of the item_ids an ambiguous match
# could not separate (NULL for every other observation).
# CP4: local_observations.erased marks an erasure stub ({"erased": true,
# "observed_at_ms"}); episode_revisions.redacted_reason is 'erasure' |
# 'retention' | 'legacy_v1' next to a NULL packet; episode_revisions.reduced_ms
# records the landmark reduction; item_names / local_audit / corrections.erased
# mark rows whose text was blanked by an erasure (the row itself is kept).
# consent_version on episode_revisions / idle_frames: the CONSENT_VERSION the row
# was ingested under; retention.acknowledged_version / erased_at_ms and
# reobservations.gated are the coordinator fix-round columns (guarded for a
# database created earlier in CP4).
# CP5 (user_version 5): local_observations.consent_version is the CONSENT_VERSION
# the observation's evidence was captured under (process_pending, reobserve) or
# LEGACY_CONSENT_VERSION for a row the v1 migration wrote; NULL on rows written
# before CP5.
# calibrations.source_note (CP5): an optional attribution / provenance note for
# the record (the CC BY 4.0 attribution text of a CUTE-derived calibration).
EPISODE_COLUMNS = (("local_observations", "candidates", "TEXT"),
                   ("local_observations", "erased", "INTEGER NOT NULL DEFAULT 0"),
                   ("local_observations", "consent_version", "TEXT"),
                   ("calibrations", "source_note", "TEXT"),
                   ("episode_revisions", "redacted_reason", "TEXT"),
                   ("episode_revisions", "reduced_ms", "INTEGER"),
                   ("episode_revisions", "consent_version", "TEXT"),
                   ("item_names", "erased", "INTEGER NOT NULL DEFAULT 0"),
                   ("local_audit", "erased", "INTEGER NOT NULL DEFAULT 0"),
                   ("corrections", "erased", "INTEGER NOT NULL DEFAULT 0"),
                   ("idle_frames", "consent_version", "TEXT"),
                   ("retention", "acknowledged_version", "TEXT"),
                   ("retention", "erased_at_ms", "INTEGER"),
                   ("reobservations", "gated", "INTEGER NOT NULL DEFAULT 0"),
                   ("reobservations", "bbox", "TEXT"))


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
        if field == "landmarks" and old.get("landmark_summary") is not None:
            # CP4: the stored packet was reduced (landmarks [] + landmark_summary),
            # so its raw landmarks cannot be compared; the field is superset-neutral
            # and the keyframes, burst and gaps of the reduced packet still decide.
            continue
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


class EpisodeStoreMixin(ReobservationMixin):
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
            # CP4 rule 13: diff-only unless physical_instance_recognition is enabled.
            {"name": "re_observation", "enabled": True,
             "reason": "Registered idle-frame differences refresh or stale a placement; identity confirmed only with an approved embedder calibration"},
            {"name": "automatic_daily_tracker", "enabled": False, "reason": "Pending model-enable and held-out device/coverage gates"},
            {"name": "semantic_object_recognition", "enabled": False, "reason": "No semantic/OCR model enabled; changed regions are unknown"},
        ]

    # Calibration records (CP3). A record is registered unapproved and only
    # approve_calibration (audited) can flip it; the processor's observation-level
    # calibration dict (CP2 rule, _calibration_approved) is a separate, code-only path.
    @staticmethod
    def _calibration_dict(row) -> dict:
        keys = row.keys() if hasattr(row, "keys") else ()
        return {"calibration_id": row["calibration_id"], "embedder": row["embedder"], "alpha": row["alpha"],
                "quantile": row["quantile"], "n": row["n"], "source": row["source"], "created_ms": row["created_ms"],
                "approved": bool(row["approved"]), "approved_by": row["approved_by"], "approved_ms": row["approved_ms"],
                "source_note": row["source_note"] if "source_note" in keys else None}

    def register_calibration(self, record) -> dict:
        """Store a calibration record {calibration_id, embedder, alpha, quantile, n,
        source, created_ms?, source_note?}; approved is always False here.
        source_note (CP5, optional, printable text of at most MAX_SOURCE_NOTE
        characters) is the record's attribution / provenance note: for a "cute"
        calibration it carries the CC BY 4.0 attribution text the notices page
        shows. ValueError on an invalid or duplicate record. Audit row
        calibration_registered."""
        if not isinstance(record, dict):
            raise ValueError("Invalid calibration record")
        allowed = {"calibration_id", "embedder", "alpha", "quantile", "n", "source", "created_ms", "approved", "source_note"}
        if set(record) - allowed:
            raise ValueError("Invalid calibration record")
        note = record.get("source_note")
        if note is not None and (not isinstance(note, str) or not 1 <= len(note.strip()) <= MAX_SOURCE_NOTE or any(ord(c) < 32 for c in note)):
            raise ValueError("Invalid calibration source_note")
        note = note.strip() if isinstance(note, str) else None
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
            db.execute("INSERT INTO calibrations(profile_id,calibration_id,embedder,alpha,quantile,n,source,created_ms,approved,source_note) VALUES(?,?,?,?,?,?,?,?,0,?)",
                       (self.profile_id, calibration_id, embedder, float(alpha), float(quantile), n, source, created, note))
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
        if packet.landmark_summary is not None:
            # CP4: the reduced form is written only by apply_retention; a client
            # claiming it would bypass the raw-landmark window (server maps to 400).
            raise ValueError("landmark_summary is server-only")
        digest = hashlib.sha256(raw).hexdigest()
        semantic = packet.semantic_digest()
        key = (self.profile_id, packet.device_id, packet.episode_id)
        now = self._now_ms()
        wall_end = packet.clock_anchor.wall_ms + packet.t_end_ms - packet.clock_anchor.mono_ms
        wall_start = packet.clock_anchor.wall_ms + packet.t_start_ms - packet.clock_anchor.mono_ms
        clock_status = "implausible" if wall_end <= 0 or wall_end > now + 300000 else "ok"
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._capture_allowed(db, wall_start)
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
            if not accepted_rows:
                accepted = True
            elif accepted_rows[-1]["packet"] is None:
                # CP4: the accepted bytes are gone (retention, superseded or erased):
                # nothing to compare against, so the revision is retained as a
                # conflict and never processed; the current state is not reinterpreted.
                accepted = False
            else:
                accepted = _superset(parse_packet(bytes(accepted_rows[-1]["packet"])).model_dump(), packet.model_dump())
            revision = len(previous) + 1
            status = "stored" if not previous else ("revised" if accepted else "conflict")
            db.execute("INSERT INTO episode_revisions(profile_id,device_id,episode_id,revision_no,semantic_digest,transport_digest,packet,received_at_ms,accepted,clock_status,redacted,consent_version) VALUES(?,?,?,?,?,?,?,?,?,?,0,?)",
                       key + (revision, semantic, digest, raw, now, int(accepted), clock_status, CONSENT_VERSION))
            if accepted:
                db.execute("INSERT INTO episode_jobs(profile_id,device_id,episode_id,revision_no,status) VALUES(?,?,?,?,?)", key + (revision, "pending"))
                # CP5 (coordinator ruling 1): the packet's observation gaps become
                # coverage-gap rows on the wall clock, so an item placed before a gap
                # reads gap_since and the resolver hedges it.
                for gap in packet.gaps:
                    self._record_gap(db, packet.device_id, packet.session_id, "packet",
                                     packet.clock_anchor.wall_ms + gap.t_from_ms - packet.clock_anchor.mono_ms,
                                     packet.clock_anchor.wall_ms + gap.t_to_ms - packet.clock_anchor.mono_ms,
                                     gap.t_to_ms - gap.t_from_ms, now)
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
                  "embedded": 0, "embedding_failed": 0, "embedding_skipped_hand": 0, "matched": 0, "ambiguous": 0, "containments": 0,
                  "process_cpu_s": 0.0}
        embedder = self.embedder
        embedder_tag = embedder.tag if embedder is not None else None
        import time as _time
        spent = 0.0
        for _ in range(limit):
            with self._connection() as db:
                db.execute("BEGIN IMMEDIATE")
                job = db.execute("""SELECT j.*,r.packet,r.clock_status FROM episode_jobs j
                    JOIN episode_revisions r USING(profile_id,device_id,episode_id,revision_no)
                    WHERE j.profile_id=? AND r.redacted=0 AND r.packet IS NOT NULL AND
                    (j.status='pending' OR (j.status='processing' AND j.lease_until<=?))
                    ORDER BY r.received_at_ms,j.revision_no LIMIT 1""", (self.profile_id, self.clock())).fetchone()
                if job is None:
                    break
                key = (self.profile_id, job["device_id"], job["episode_id"], job["revision_no"])
                token = str(uuid.uuid4())
                db.execute("UPDATE episode_jobs SET status='processing',token=?,lease_until=?,attempts=attempts+1 WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no=?", (token, self.clock()+60) + key)
            # Finance (CP5): the wall time of one job's work (parse, processor,
            # embedding, write) is charged to the day's process_cpu_s counter.
            started = _time.perf_counter()
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
                hand_covered = set()
                if embedder is not None:
                    decoded, hulls = {}, {}
                    for index, observation in enumerate(observations):
                        try:
                            if observation.frame_id not in decoded:
                                decoded[observation.frame_id] = self._rgb_frame(frames[observation.frame_id])
                                # CP4 (recipe r2): the hull of any hand in the landmark sample
                                # nearest the keyframe (within HAND_HULL_WINDOW_MS) is kept out
                                # of the pooling mask; no sample in the window means no hull.
                                hulls[observation.frame_id] = self._hand_hull(packet, frames[observation.frame_id])
                            vectors[index] = self._embed_region(embedder, decoded[observation.frame_id], observation, hulls.get(observation.frame_id))
                            counts["embedded"] += 1
                        except HandCoversRegion:
                            # CP4 F1: the hand leaves too little of the region; refused, not
                            # pooled over the hand. Identity stays provisional, no vector.
                            hand_covered.add(index)
                            counts["embedding_skipped_hand"] += 1
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
                    touched, placements = [], []
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
                        if index in hand_covered:
                            match = {"embedder": embedder_tag, "calibration_id": None, "state": "new", "set": [], "scores": {},
                                     "reason": "hand covers the region"}
                        elif embedding_failed:
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
                        db.execute("INSERT INTO local_observations(profile_id,observation_id,item_id,device_id,episode_id,revision_no,observed_at_ms,decided_at_ms,record,candidates,consent_version) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                   (self.profile_id, signature, item_id, packet.device_id, packet.episode_id, job["revision_no"], observed_ms, self._now_ms(), _json(record), _json(candidates) if candidates else None, CONSENT_VERSION))
                        if vectors[index] is not None:
                            db.execute("INSERT INTO embeddings VALUES(?,?,?,?,?,?)", (self.profile_id, signature, embedder_tag, int(embedder.dim), _vector_bytes(vectors[index]), self._now_ms()))
                        assign[signature] = item_id
                        counts["observations"] += 1
                        placements.append((item_id, record, observed_ms))
                    for i, a in enumerate(touched):
                        for b in touched[i+1:]:
                            a1, b1 = sorted((a, b))
                            db.execute("INSERT OR IGNORE INTO local_cannot_links VALUES(?,?,?)", (self.profile_id, a1, b1))
                    counts["containments"] += self._record_containment(db, placements)
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
            finally:
                spent += _time.perf_counter() - started
        if spent > 0:
            counts["process_cpu_s"] = round(spent, 4)
            self.bump_counter("process_cpu_s", spent)
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
        for row in db.execute(f"SELECT observation_id,item_id,record FROM local_observations WHERE profile_id=? AND device_id=? AND {LIVE}", (self.profile_id, packet.device_id)):
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
    def _hand_hull(packet, frame):
        """Full-frame bool hull mask (capture resolution) of the hands in the
        landmark sample nearest this keyframe within HAND_HULL_WINDOW_MS, or None
        when no sample is that close or it carries no hand."""
        sample = nearest_sample(packet.landmarks, frame.t_ms)
        if sample is None or not sample.hands:
            return None
        hull = hand_hull_mask(sample.hands, packet.capture.width, packet.capture.height)
        return hull if hull.any() else None

    @staticmethod
    def _embed_region(embedder, rgb, observation, hull=None):
        """Crop the observation's bbox padded by CROP_PAD (recipe r2) at capture
        resolution, decode its mask_rle over the localizer's unpadded window inside
        that crop (an invalid mask is dropped, not fatal), remove the hand hull if
        one is given, and embed. The mask is None when neither a diff mask nor a
        hull touching the crop exists.

        CP4 F1: when a hull was subtracted, the surviving mask must still cover
        MIN_MASK_SHARE of the crop and MIN_MASK_PATCHES patches (mask_sufficient);
        otherwise HandCoversRegion is raised and nothing is embedded, because the
        all-patches fallback would embed the hand. Embedders whose embed signature
        names hull_applied receive the flag so their own pooling refuses too.
        Raises if the embedder returns anything but a finite vector of its dim."""
        import inspect
        import numpy as np
        height, width = rgb.shape[:2]
        px1, py1, px2, py2 = padded_crop_box(observation.bbox, width, height)
        crop = np.ascontiguousarray(rgb[py1:py2, px1:px2])
        mask = None
        if observation.mask_rle:
            x1, y1, x2, y2 = crop_box(observation.bbox, width, height)
            try:
                inner = mask_from_rle(observation.mask_rle, x2 - x1, y2 - y1)
            except ValueError:
                inner = None
            if inner is not None:
                mask = np.zeros((py2 - py1, px2 - px1), dtype=bool)
                mask[y1 - py1:y2 - py1, x1 - px1:x2 - px1] = inner
        hull_applied = False
        if hull is not None:
            window = hull[py1:py2, px1:px2]
            if window.any():
                mask = (np.ones(window.shape, dtype=bool) if mask is None else mask) & ~window
                hull_applied = True
        if hull_applied and not mask_sufficient(mask, True):
            raise HandCoversRegion()
        kwargs = {}
        if hull_applied:
            try:
                if "hull_applied" in inspect.signature(embedder.embed).parameters:
                    kwargs["hull_applied"] = True
            except (TypeError, ValueError):
                pass
        vector = np.asarray(embedder.embed(crop, mask, **kwargs), dtype=np.float32).reshape(-1)
        if vector.size != embedder.dim:
            raise ValueError("Embedder returned the wrong dimension")
        return l2_normalise(vector)

    def _record_containment(self, db, placements) -> int:
        """CP4 containment: among this job's trusted placements in one frame, an
        item whose rest bbox lies at least CONTAINMENT_INSIDE inside another's is
        recorded as contained (inner, outer, since_ms, frame_id). Mutual overlap
        picks the smaller box as inner. Returns the number of rows written."""
        written = 0
        placed = [(item_id, record, observed_ms) for item_id, record, observed_ms in placements
                  if record.get("identity_state") == "trusted" and record.get("outcome") == "placed_on_surface"
                  and record.get("location_text") and isinstance(record.get("bbox"), list)]
        for inner_id, inner, since in placed:
            best = None
            for outer_id, outer, _ in placed:
                if outer_id == inner_id or outer.get("frame_id") != inner.get("frame_id"):
                    continue
                share = inside_fraction(inner["bbox"], outer["bbox"])
                if share < CONTAINMENT_INSIDE:
                    continue
                inner_area = (inner["bbox"][2] - inner["bbox"][0]) * (inner["bbox"][3] - inner["bbox"][1])
                outer_area = (outer["bbox"][2] - outer["bbox"][0]) * (outer["bbox"][3] - outer["bbox"][1])
                if outer_area < inner_area or (outer_area == inner_area and outer_id < inner_id):
                    continue
                if best is None or outer_area < best[1]:
                    best = (outer_id, outer_area)
            if best is not None:
                db.execute("INSERT INTO containment(profile_id,inner_item,outer_item,since_ms,frame_id) VALUES(?,?,?,?,?)",
                           (self.profile_id, inner_id, best[0], since, inner["frame_id"]))
                written += 1
        return written

    def _corrections(self, db, at=None):
        """Stored corrections in replay order, limited to at_ms <= at when given."""
        rows = db.execute("SELECT correction_no,correction_id,kind,at_ms,actor,payload FROM corrections WHERE profile_id=? AND erased=0 ORDER BY correction_no", (self.profile_id,))
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
        assign = {row[0]: row[1] for row in db.execute(f"SELECT observation_id,item_id FROM local_observations WHERE profile_id=? AND {LIVE}", (self.profile_id,))}
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
            WHERE e.profile_id=? AND e.embedder=? AND o.record IS NOT NULL AND o.erased=0
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
        rows = db.execute(f"SELECT observation_id,item_id,record FROM local_observations WHERE profile_id=? AND device_id=? AND episode_id=? AND {LIVE}", (self.profile_id, packet.device_id, packet.episode_id))
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
        """Clock-only ageing (B-11) of one projected item, evaluated at eval_ms:
        perception.resolver.age_item with the build's windows (pure, idempotent,
        returns a copy; only a 'placed' location ages)."""
        return age_item(item, eval_ms)

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
        rows = db.execute("""SELECT o.* FROM local_observations o WHERE o.profile_id=? AND o.record IS NOT NULL AND o.erased=0
            ORDER BY o.observed_at_ms,o.decided_at_ms,o.observation_id""", (self.profile_id,)).fetchall()
        # CP3: observations are read through the effective assignment (corrections up
        # to as_of replayed in order; a correction after as_of is not applied) and an
        # item tombstone applies only once written (a linked-away item is visible
        # before its link). Redacted rows have record NULL whatever the time; erased
        # rows (CP4 stubs) are excluded by the query, so no read path sees them.
        assign, merged, resolved = self._assignments(db, at)
        tombstoned = {row[0] for row in db.execute("SELECT item_id,at_ms FROM item_tombstones WHERE profile_id=?", (self.profile_id,)) if at is None or row[1] <= at}
        items, latest_candidates, parked, own_label, device_of = {}, {}, [], {}, {}
        for row in rows:
            if at is not None and row["observed_at_ms"] > at:
                continue
            item_id = assign.get(row["observation_id"], row["item_id"])
            if item_id in tombstoned:
                continue
            device_of[item_id] = row["device_id"]
            observation = json.loads(row["record"])
            if observation.get("source") == "reobservation":
                # CP4 rule 13: a positive re-observation refreshes the item's current
                # placement (time, image, location fields) and never its identity;
                # it only applies to the placement it was decided against (the item's
                # latest hand event is not newer than the frame) while that placement
                # is still in force.
                item = items.get(item_id)
                if item is None or item.get("location_status") != "placed" or (item.get("last_event_ms") or 0) > row["observed_at_ms"]:
                    continue
                item.update(observed_at_ms=row["observed_at_ms"] if row["observed_at_ms"] > 0 else None,
                            observation_id=row["observation_id"], location_status="placed",
                            location_text=observation.get("location_text"), stale_reason=None, stale_since_ms=None,
                            inference=None, reference_image=self._reference_image(observation))
                continue
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
            # The stale_reason sentences are perception.resolver constants (the
            # resolver's decision table keys on them).
            stale = None
            if observation["outcome"] == "picked_up":
                location_status, stale = "stale", REASON_PICKED_UP
            elif observation["outcome"] == "uncertain":
                location_status, stale = "unknown", REASON_UNCERTAIN
            elif placed:
                location_status = "placed"
            else:
                location_status = "sighted"
                stale = REASON_SIGHTING_TRUSTED if trusted else REASON_SIGHTING_UNVERIFIED
            if clock_bad:
                location_status, stale = "unknown", REASON_CLOCK
            items[item_id] = {
                "item_id": item_id, "name": observation["label"],
                "identity_status": identity_state, "relevance": "candidate",
                "location_status": location_status,
                "observed_at_ms": row["observed_at_ms"] if row["observed_at_ms"] > 0 else None,
                "location_text": observation.get("location_text") if placed else None,
                "stale_reason": stale, "index_pending": False, "image_url": None,
                # aged is an evaluated field: always False in storage, set by _age_item on read.
                "aged": False,
                "source": "legacy_v1" if observation.get("source") == "legacy_v1" else "local_evidence",
                "observation_id": row["observation_id"],
                # The photo is the answer: the whole keyframe is the reference image and
                # the target region travels with it (spec answer contract, reference_image).
                "reference_image": self._reference_image(observation),
                # CP3: items this one could not be told apart from (filled below).
                "lookalikes": [],
                # CP4: when the item became stale (pickup time, first negative
                # re-observation, or the ageing boundary), the containment inference
                # {container, container_name, since_ms} when the location is inferred,
                # whether the evidence image bytes are gone (retention), and the time
                # of the latest hand event (internal; re-observations never move it).
                "stale_since_ms": (row["observed_at_ms"] if location_status == "stale" and row["observed_at_ms"] > 0 else None),
                "inference": None, "evidence_expired": False,
                "last_event_ms": row["observed_at_ms"],
                # CP5: a coverage gap (packet gap or telemetry window with gap_ms > 0,
                # same device) ended after this evidence time; filled by _apply_gaps.
                "gap_since": False,
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
        for row in db.execute("SELECT item_id,name,at_ms FROM item_names WHERE profile_id=? AND name IS NOT NULL AND erased=0 ORDER BY at_ms,name_id", (self.profile_id,)):
            if row["item_id"] in items and (at is None or row["at_ms"] <= at):
                items[row["item_id"]]["name"] = row["name"]
                items[row["item_id"]]["source"] = "user_named_local_evidence"
        # CP4 passes run after the names so an inference carries the container's
        # user name; neither pass depends on lookalikes or names otherwise.
        self._apply_negative_reobservations(db, items, merged, at)
        self._apply_containment(db, items, merged, at)
        self._apply_gaps(db, items, device_of, at)
        for item in items.values():
            item["evidence_expired"] = self._evidence_expired(db, item)
        if age:
            eval_ms = at if at is not None else self._now_ms()
            items = {item_id: self._age_item(item, eval_ms) for item_id, item in items.items()}
        return items, parked

    @staticmethod
    def _reference_image(observation):
        """{frame_id, bbox} of a record, or None when it carries no region (a
        legacy v1 row has no stored image and no bbox)."""
        bbox = observation.get("bbox")
        if not isinstance(bbox, list) or len(bbox) != 4 or not isinstance(observation.get("frame_id"), str):
            return None
        return {"frame_id": observation["frame_id"], "bbox": list(bbox)}

    def _evidence_expired(self, db, item) -> bool:
        """True when the item's reference image was stored once and its bytes are
        gone (retention expiry of the packet or of a promoted idle frame). A legacy
        row that never had an image reads False; reference_image is then None."""
        if item.get("reference_image") is None or item.get("source") == "legacy_v1":
            return False
        row = db.execute("SELECT * FROM local_observations WHERE profile_id=? AND observation_id=?", (self.profile_id, item["observation_id"])).fetchone()
        if row is None:
            return False
        record = json.loads(row["record"]) if row["record"] else {}
        if record.get("source") == "reobservation":
            frame = db.execute("SELECT jpeg IS NOT NULL FROM idle_frames WHERE profile_id=? AND device_id=? AND frame_id=?",
                               (self.profile_id, row["device_id"], record.get("frame_id"))).fetchone()
            expired = frame is None or not frame[0]
        else:
            revision = db.execute("SELECT packet IS NOT NULL,redacted_reason FROM episode_revisions WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no=?",
                                  (self.profile_id, row["device_id"], row["episode_id"], row["revision_no"])).fetchone()
            expired = revision is not None and not revision[0] and revision[1] in ("retention", "superseded")
            if expired and revision[1] == "superseded":
                # A newer accepted revision may still carry the keyframe (see _episode_packets).
                frame_id = record.get("frame_id")
                expired = not any(any(f.frame_id == frame_id for f in packet.keyframes) for packet in self._episode_packets(db, row))
        if expired:
            item["reference_image"] = None
        return expired

    def _apply_negative_reobservations(self, db, items, merged, at):
        """CP4: a 'gone' decision newer than the item's current placement time (so
        not yet reversed by a later 'present', which writes a newer observation)
        makes a placed item stale with stale_reason "negative_reobservation" and
        stale_since_ms = the first such decision. Derived from the reobservations
        table, so rebuild_all and as_of reproduce it from storage."""
        def follow(item_id):
            seen = set()
            while item_id in merged and item_id not in seen:
                seen.add(item_id)
                item_id = merged[item_id]
            return item_id
        gone = {}
        for row in db.execute("SELECT item_id,t_wall_ms FROM reobservations WHERE profile_id=? AND result='gone' ORDER BY t_wall_ms", (self.profile_id,)):
            if at is not None and row["t_wall_ms"] > at:
                continue
            item_id = follow(row["item_id"])
            item = items.get(item_id)
            if item is None or item.get("location_status") != "placed" or row["t_wall_ms"] <= (item.get("observed_at_ms") or 0):
                continue
            gone.setdefault(item_id, row["t_wall_ms"])
        for item_id, since in gone.items():
            items[item_id].update(location_status="stale", stale_reason=REASON_NEGATIVE_REOBSERVATION, stale_since_ms=since)

    def _apply_containment(self, db, items, merged, at):
        """CP4: an item A recorded inside B (containment, most recent row wins;
        A's own later hand event clears it) reads location_status "inferred" with
        B's current location text once B's location has changed since (a new hand
        event of B, or B stale by pickup / negative re-observation) and A has not
        been seen in place after that change. Ageing of B is not a change here: A's
        own placement ages on its own clock. A negative re-observation of A at its
        old place never contradicts the inference (A is expected to be gone)."""
        def follow(item_id):
            seen = set()
            while item_id in merged and item_id not in seen:
                seen.add(item_id)
                item_id = merged[item_id]
            return item_id
        latest = {}
        for row in db.execute("SELECT inner_item,outer_item,since_ms FROM containment WHERE profile_id=? ORDER BY since_ms,containment_no", (self.profile_id,)):
            if at is not None and row["since_ms"] > at:
                continue
            inner, outer = follow(row["inner_item"]), follow(row["outer_item"])
            if inner == outer or inner not in items or outer not in items:
                continue
            latest[inner] = (outer, row["since_ms"])
        for _ in range(2):  # a second pass lets a container's own inference propagate
            for inner, (outer, since) in latest.items():
                a, b = items[inner], items[outer]
                if (a.get("last_event_ms") or 0) > since or a.get("location_status") not in ("placed", "stale", "inferred"):
                    continue
                if a.get("location_status") == "stale" and a.get("stale_reason") != REASON_NEGATIVE_REOBSERVATION:
                    continue
                changed_at = None
                if (b.get("last_event_ms") or 0) > since:
                    changed_at = b["last_event_ms"]
                elif b.get("location_status") == "stale" and b.get("stale_since_ms") is not None and b["stale_since_ms"] > since:
                    changed_at = b["stale_since_ms"]
                if changed_at is None or (a.get("observed_at_ms") or 0) > changed_at:
                    continue
                a.update(location_status="inferred", location_text=b.get("location_text"), stale_reason=None, stale_since_ms=None,
                         inference={"container": outer, "container_name": b.get("name"), "since_ms": since})

    def _record_gap(self, db, device_id, session_id, source, t_from_ms, t_to_ms, gap_ms, received_ms):
        """One coverage-gap row (CP5): a packet gap entry or a telemetry window
        that reported gap_ms > 0, on the wall clock. Times, ids and the source
        only: a packet gap's free-text reason stays in the packet (it is personal
        content under the erasure rules), so the reason column is left NULL.
        Idempotent for a resend. Returns True when a new row was written."""
        if gap_ms <= 0 or t_to_ms <= 0:
            return False
        cursor = db.execute("INSERT OR IGNORE INTO capture_gaps(profile_id,device_id,session_id,source,t_from_ms,t_to_ms,gap_ms,received_ms,reason) VALUES(?,?,?,?,?,?,?,?,NULL)",
                            (self.profile_id, device_id, session_id, source, int(t_from_ms), int(t_to_ms), int(gap_ms), int(received_ms)))
        return cursor.rowcount == 1

    def _apply_gaps(self, db, items, device_of, at):
        """CP5 (coordinator ruling 1): gap_since = a coverage gap of the item's
        device (a packet gap or a telemetry window with gap_ms > 0) ended after
        the item's current evidence time (and, under as_of, no later than at).
        A positive re-observation or a new placement moves the evidence time, so
        the flag clears on fresh evidence. Derived from capture_gaps, so a replay
        reproduces it from storage."""
        for item in items.values():
            item["gap_since"] = False
        times = [item["observed_at_ms"] for item in items.values() if item.get("observed_at_ms")]
        if not times:
            return
        rows = db.execute("SELECT device_id,t_to_ms FROM capture_gaps WHERE profile_id=? AND gap_ms>0 AND t_to_ms>?", (self.profile_id, min(times))).fetchall()
        if not rows:
            return
        latest = {}
        for row in rows:
            if at is not None and row["t_to_ms"] > at:
                continue
            latest[row["device_id"]] = max(latest.get(row["device_id"], 0), row["t_to_ms"])
        for item_id, item in items.items():
            observed = item.get("observed_at_ms")
            device = device_of.get(item_id)
            if observed and device in latest and latest[device] > observed:
                item["gap_since"] = True

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
        """perception.resolver.query_words: the catalogue and the resolver match
        the same words."""
        return query_words(query)

    @staticmethod
    def _matches(item, words, query):
        return matches(item, words, query)

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
        rows = db.execute(f"SELECT * FROM local_observations WHERE profile_id=? AND {LIVE} ORDER BY observed_at_ms,decided_at_ms,observation_id", (self.profile_id,))
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
                # CP4: a positive re-observation row inherits its placement's location.
                if record.get("source") == "reobservation" and record.get("location_status") == "placed":
                    placed = bool(record.get("location_text"))
                evidence.append({"observation_id": row["observation_id"], "item_id": item_id,
                                 "observed_at_ms": row["observed_at_ms"] if row["observed_at_ms"] > 0 else None,
                                 "frame_id": record["frame_id"],
                                 "reference_image": self._reference_image(record),
                                 "identity_status": identity_state, "identity_source": identity_source, "outcome": record["outcome"],
                                 "location_text": record.get("location_text") if placed else None,
                                 "candidates": candidates, "embedded": row["observation_id"] in embedded,
                                 "source": record.get("source", "local_evidence")})
            return evidence

    def _keyframe_bytes(self, db, row):
        """The stored keyframe bytes of one observation row, or None when its
        revision is redacted or expired or the frame is absent (the item_image
        rules). A re-observation row's image is its promoted idle frame."""
        if row["record"] is None:
            return None
        observation = json.loads(row["record"])
        if observation.get("erased"):
            return None
        if observation.get("source") == "reobservation":
            frame = db.execute("SELECT jpeg FROM idle_frames WHERE profile_id=? AND device_id=? AND frame_id=?",
                               (self.profile_id, row["device_id"], observation.get("frame_id"))).fetchone()
            return None if frame is None or frame[0] is None else bytes(frame[0])
        for packet in self._episode_packets(db, row):
            frame = next((f for f in packet.keyframes if f.frame_id == observation["frame_id"]), None)
            if frame is not None:
                return jpeg_bytes(frame.jpeg_b64)
        return None

    def _episode_packets(self, db, row):
        """Parsed packets that may hold the row's keyframe: its own revision
        first, then (when that one was superseded, i.e. its bytes were released
        because a newer accepted revision exists) the newer accepted revisions of
        the episode, newest first. A superset revision keeps every prior keyframe
        byte for byte, so the image served is the one the observation was
        decided on. Redacted (erased) episodes yield nothing."""
        own = db.execute("SELECT packet,redacted,redacted_reason FROM episode_revisions WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no=?",
                         (self.profile_id, row["device_id"], row["episode_id"], row["revision_no"])).fetchone()
        if own is None or own["redacted"]:
            return
        if own["packet"] is not None:
            yield parse_packet(bytes(own["packet"]))
            return
        if own["redacted_reason"] != "superseded":
            return
        for newer in db.execute("SELECT packet FROM episode_revisions WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no>? AND accepted=1 AND redacted=0 AND packet IS NOT NULL ORDER BY revision_no DESC",
                                (self.profile_id, row["device_id"], row["episode_id"], row["revision_no"])):
            yield parse_packet(bytes(newer[0]))

    def observation_image(self, item_id, observation_id) -> bytes | None:
        """CP3: that observation's keyframe bytes, unmodified, when the observation
        is currently assigned to item_id in this profile; None otherwise (unknown
        item or observation, other profile, redacted), never an error."""
        if not isinstance(item_id, str) or not isinstance(observation_id, str) or len(item_id) > 100 or len(observation_id) > 100:
            return None
        with self._connection() as db:
            if not db.execute("SELECT 1 FROM current_items WHERE profile_id=? AND item_id=?", (self.profile_id, item_id)).fetchone():
                return None
            row = db.execute(f"SELECT * FROM local_observations WHERE profile_id=? AND observation_id=? AND {LIVE}", (self.profile_id, observation_id)).fetchone()
            if row is None:
                return None
            assign, _, _ = self._assignments(db)
            if assign.get(observation_id) != item_id:
                return None
            data = self._keyframe_bytes(db, row)
        return self._count_image(data)

    def _count_image(self, data):
        """Finance (CP5): every evidence image served is counted (image_serves,
        image_bytes) on the day's maintenance counters; the bytes pass through."""
        if data is not None:
            self.bump_counter("image_serves")
            self.bump_counter("image_bytes", len(data))
        return data

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
            row = db.execute(f"SELECT * FROM local_observations WHERE profile_id=? AND observation_id=? AND {LIVE}", (self.profile_id, item["observation_id"])).fetchone()
            if row is None:
                return None
            data = self._keyframe_bytes(db, row)
        return self._count_image(data)

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
            row = db.execute(f"SELECT observation_id FROM local_observations WHERE profile_id=? AND observation_id=? AND {LIVE}", (self.profile_id, observation_id)).fetchone()
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
            row = db.execute(f"SELECT * FROM local_observations WHERE profile_id=? AND observation_id=? AND {LIVE}", (self.profile_id, observation_id)).fetchone()
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
            for other in db.execute(f"SELECT observation_id,item_id,record FROM local_observations WHERE profile_id=? AND device_id=? AND episode_id=? AND {LIVE}", (self.profile_id, row["device_id"], row["episode_id"])):
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
        """The Answer (perception.resolver.resolve) for a question over the
        projection aged at as_of (epoch ms) or at the injected clock. The store
        supplies what only it knows: the aged projection, the parked (B-14)
        observations for a group's unresolved_observation_id, whether a candidate
        is still unprocessed (index_pending) and whether the build's consent
        version is unacknowledged (basis consent_pending). ValueError for a bad
        question or as_of."""
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000:
            raise ValueError("Invalid question")
        at = self._as_of_ms(as_of)
        with self._connection() as db:
            projected, parked = self._project(db, at)
            pending = self._pending(db)
            consent_ok = self._consent_state(db)["ok"]
        eval_ms = at if at is not None else self._now_ms()
        self.bump_counter("chat_local")
        return resolve(text, list(projected.values()), as_of_ms=eval_ms, index_pending=pending,
                       parked=parked, consent_pending=not consent_ok)

    @staticmethod
    def _date_text(observed_ms):
        """perception.resolver.date_text (kept for callers)."""
        return date_text(observed_ms)

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

    # ------------------------------------------------------------------ erasure (CP4)
    def redact_item(self, item_id, actor="operator") -> dict:
        """CP1 alias kept for callers and tests: erase_item under `actor` (default
        "operator"; the closed ACTORS set applies, CP5 carried item)."""
        return self.erase_item(item_id, actor=actor)

    def _closure(self, db, item_id):
        """(affected item ids, affected (device, episode) keys): the CP1 co-visibility
        closure over the effective assignment. A whole-frame packet may show several
        people and items, so retaining it for a co-item would defeat erasure."""
        assign, _, _ = self._assignments(db)
        location = {row["observation_id"]: (row["device_id"], row["episode_id"]) for row in
                    db.execute("SELECT observation_id,device_id,episode_id FROM local_observations WHERE profile_id=?", (self.profile_id,))}
        def episodes_of(target):
            return {location[o] for o, item in assign.items() if item == target and o in location}
        def items_in(device, episode):
            return {assign[o] for o, where in location.items() if where == (device, episode) and o in assign}
        episodes = episodes_of(item_id)
        affected = {item_id}
        changed = True
        while changed:
            before = (len(episodes), len(affected))
            for device, episode in list(episodes):
                affected.update(items_in(device, episode))
            for target in list(affected):
                episodes.update(episodes_of(target))
            changed = before != (len(episodes), len(affected))
        return affected, episodes, assign

    def _erase_items(self, db, affected, episodes, assign, now) -> dict:
        """Steps (1)-(5) of erase_item for a set of items inside the caller's
        transaction; returns counts only (never ids or text)."""
        counts = {"items": 0, "observations": 0, "embeddings": 0, "reobservations": 0, "containment": 0,
                  "idle_frames": 0, "names": 0, "audit_rows": 0, "corrections": 0, "revisions": 0, "episodes": 0,
                  "cannot_links": 0, "legacy_objects": 0}
        erased_observations = set()
        legacy_objects = set()
        for target in sorted(affected):
            # (1) tombstone; the item never reappears through a resent packet, a
            # replay or a correction.
            db.execute("INSERT OR IGNORE INTO item_tombstones VALUES(?,?,?)", (self.profile_id, target, now))
            counts["items"] += 1
            # Erase by effective AND processing-time assignment (over-erasure is the
            # safe direction); the embedding derived from an erased crop goes with it.
            erased = {o for o, item in assign.items() if item == target}
            erased.update(r[0] for r in db.execute("SELECT observation_id FROM local_observations WHERE profile_id=? AND item_id=?", (self.profile_id, target)))
            erased_observations |= erased
            for observation_id in sorted(erased):
                row = db.execute("SELECT observed_at_ms,record FROM local_observations WHERE profile_id=? AND observation_id=?", (self.profile_id, observation_id)).fetchone()
                if row is None:
                    continue
                if row["record"]:
                    try:
                        legacy = json.loads(row["record"]).get("legacy_object_id")
                    except ValueError:
                        legacy = None
                    if isinstance(legacy, str):
                        legacy_objects.add(legacy)
                # (3) a minimal, non-identifying stub: no label, bbox, location text,
                # candidates or match survives.
                db.execute("UPDATE local_observations SET record=?,candidates=NULL,erased=1 WHERE profile_id=? AND observation_id=?",
                           (_json({"erased": True, "observed_at_ms": row["observed_at_ms"]}), self.profile_id, observation_id))
                counts["observations"] += 1
                counts["embeddings"] += db.execute("DELETE FROM embeddings WHERE profile_id=? AND observation_id=?", (self.profile_id, observation_id)).rowcount
            # (2) derived rows of the item.
            for frame in db.execute("SELECT device_id,frame_id FROM reobservations WHERE profile_id=? AND item_id=? AND result='present'", (self.profile_id, target)).fetchall():
                counts["idle_frames"] += db.execute("DELETE FROM idle_frames WHERE profile_id=? AND device_id=? AND frame_id=? AND promoted=1", (self.profile_id, frame["device_id"], frame["frame_id"])).rowcount
            counts["reobservations"] += db.execute("DELETE FROM reobservations WHERE profile_id=? AND item_id=?", (self.profile_id, target)).rowcount
            counts["containment"] += db.execute("DELETE FROM containment WHERE profile_id=? AND (inner_item=? OR outer_item=?)", (self.profile_id, target, target)).rowcount
            counts["cannot_links"] += db.execute("DELETE FROM local_cannot_links WHERE profile_id=? AND (item_a=? OR item_b=?)", (self.profile_id, target, target)).rowcount
            # (4) text blanked, rows kept with erased=1.
            counts["names"] += db.execute("UPDATE item_names SET name=NULL,erased=1 WHERE profile_id=? AND item_id=?", (self.profile_id, target)).rowcount
            counts["audit_rows"] += db.execute("UPDATE local_audit SET detail='{}',erased=1 WHERE profile_id=? AND item_id=? AND erased=0", (self.profile_id, target)).rowcount
            db.execute("DELETE FROM current_items WHERE profile_id=? AND item_id=?", (self.profile_id, target))
        # (4) corrections naming an affected item or observation: payload blanked
        # (so replay no longer sees them), row kept with erased=1.
        for row in db.execute("SELECT correction_no,payload FROM corrections WHERE profile_id=? AND erased=0", (self.profile_id,)).fetchall():
            try:
                payload = json.loads(row["payload"])
            except ValueError:
                payload = {}
            named = set()
            for key in ("keep_id", "other_id", "item_id", "from_item_id", "new_item_id"):
                if isinstance(payload.get(key), str):
                    named.add(payload[key])
            for candidate in payload.get("other_candidates") or []:
                if isinstance(candidate, str):
                    named.add(candidate)
            if named & affected or payload.get("observation_id") in erased_observations:
                db.execute("UPDATE corrections SET payload='{}',erased=1 WHERE correction_no=?", (row["correction_no"],))
                counts["corrections"] += 1
        # (5) packets of the affected episodes, tombstoned against a resend.
        for device, episode in sorted(episodes):
            db.execute("INSERT OR IGNORE INTO episode_tombstones VALUES(?,?,?,?)", (self.profile_id, device, episode, now))
            counts["revisions"] += db.execute("UPDATE episode_revisions SET packet=NULL,redacted=1,redacted_reason='erasure' WHERE profile_id=? AND device_id=? AND episode_id=?", (self.profile_id, device, episode)).rowcount
            db.execute("UPDATE episode_jobs SET status='redacted',token=NULL,lease_until=NULL,error=NULL WHERE profile_id=? AND device_id=? AND episode_id=?", (self.profile_id, device, episode))
            counts["episodes"] += 1
        # A migrated item: its legacy v1 rows carry the same personal text.
        for object_id in sorted(legacy_objects):
            counts["legacy_objects"] += self._erase_legacy_object(db, object_id)
        return counts

    def _erase_legacy_object(self, db, object_id) -> int:
        """Blank the v1 rows of one legacy object (name, verifications, observation
        records, bindings); api_calls (budgets, unknown spend) are untouched."""
        if not db.execute("SELECT 1 FROM objects WHERE profile_id=? AND object_id=?", (self.profile_id, object_id)).fetchone():
            return 0
        db.execute("UPDATE objects SET name='erased',category='erased',status='ignored' WHERE profile_id=? AND object_id=?", (self.profile_id, object_id))
        db.execute("DELETE FROM observations WHERE profile_id=? AND object_id=?", (self.profile_id, object_id))
        db.execute("DELETE FROM bindings WHERE profile_id=? AND object_id=?", (self.profile_id, object_id))
        db.execute("UPDATE candidates SET payload='{}',verification=NULL,reason='erased' WHERE profile_id=? AND object_id=?", (self.profile_id, object_id))
        db.execute("UPDATE decisions SET detail='{}' WHERE profile_id=? AND object_id=?", (self.profile_id, object_id))
        return 1

    def erase_item(self, item_id, actor) -> dict:
        """Explicit, audited erasure of one item and its CP1 co-visibility closure
        (B-07): one transaction that tombstones the items, rewrites their
        observation records to {"erased": true, "observed_at_ms"}, deletes their
        embeddings, re-observations, containment rows and promoted idle frames,
        blanks their names, audit details and correction payloads (rows kept with
        erased=1), NULLs the affected packets (redacted_reason "erasure") and
        writes one audit row "erased" carrying counts only. KeyError for an unknown
        item, ValueError for a bad actor; an already erased item returns
        already=True. Logical erasure of the live rows: no forensic claim."""
        _check_actor(actor)
        if not isinstance(item_id, str) or not 1 <= len(item_id) <= 100:
            raise KeyError("Unknown item")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            now = self._now_ms()
            if db.execute("SELECT 1 FROM item_tombstones WHERE profile_id=? AND item_id=?", (self.profile_id, item_id)).fetchone():
                return {"item_id": item_id, "erased": True, "already": True, "redacted": True, "scope": "logical", "forensic_erasure": False}
            if not db.execute("SELECT 1 FROM current_items WHERE profile_id=? AND item_id=?", (self.profile_id, item_id)).fetchone():
                raise KeyError("Unknown item")
            affected, episodes, assign = self._closure(db, item_id)
            counts = self._erase_items(db, affected, episodes, assign, now)
            db.execute("INSERT INTO local_audit(profile_id,at_ms,action,item_id,detail) VALUES(?,?,?,?,?)",
                       (self.profile_id, now, "erased", None, _json({"actor": actor, "counts": counts})))
            self._rebuild_projection(db)
            return {"item_id": item_id, "erased": True, "already": False, "redacted": True, "affected_items": counts["items"],
                    "counts": counts, "scope": "logical", "forensic_erasure": False}

    def erase_profile(self, *, actor, confirm) -> dict:
        """Erase everything personal in this profile (B-07, P-107): every item as
        erase_item does, every idle frame (promoted or not), every re-observation,
        containment row, cannot-link, correction payload, audit detail and packet,
        the CP5 telemetry windows, gap rows, daily coverage aggregates and
        maintenance counters, and the legacy v1 objects/candidates/observations/
        bindings rows (api_calls, the spend ledger, calibrations, retention and
        migration rows stay: none is personal). confirm must be True or the literal ERASE_PROFILE_CONFIRM
        (ValueError "confirmation required" otherwise; the server maps it to 409).
        After the transaction commits, the file is rebuilt with VACUUM INTO into a
        fresh private file and swapped in (os.replace), and the persisted journal
        is dropped, which reduces residue of the erased pages in the live files; it
        is not a guarantee about the filesystem, earlier journals or backups. When
        the swap is refused by the OS an in-place VACUUM is run instead and the
        report says swap: "in_place"."""
        _check_actor(actor)
        if confirm is not True and confirm != ERASE_PROFILE_CONFIRM:
            raise ValueError("confirmation required")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            now = self._now_ms()
            items = {row[0] for row in db.execute("SELECT DISTINCT item_id FROM local_observations WHERE profile_id=?", (self.profile_id,))}
            items |= {row[0] for row in db.execute("SELECT item_id FROM current_items WHERE profile_id=?", (self.profile_id,))}
            assign, _, _ = self._assignments(db)
            items |= set(assign.values())
            episodes = {(row[0], row[1]) for row in db.execute("SELECT DISTINCT device_id,episode_id FROM episode_revisions WHERE profile_id=?", (self.profile_id,))}
            counts = self._erase_items(db, items, episodes, assign, now)
            counts["idle_frames"] += db.execute("DELETE FROM idle_frames WHERE profile_id=?", (self.profile_id,)).rowcount
            counts["reobservations"] += db.execute("DELETE FROM reobservations WHERE profile_id=?", (self.profile_id,)).rowcount
            counts["containment"] += db.execute("DELETE FROM containment WHERE profile_id=?", (self.profile_id,)).rowcount
            counts["cannot_links"] += db.execute("DELETE FROM local_cannot_links WHERE profile_id=?", (self.profile_id,)).rowcount
            # CP5: frame-accounting windows and gap rows carry device and session ids,
            # so they go; the daily aggregates and maintenance counters go too
            # (Oversight pass 2), so the Status panel shows zeros after "Erase everything".
            counts["telemetry"] = db.execute("DELETE FROM frame_counters WHERE profile_id=?", (self.profile_id,)).rowcount
            counts["gaps"] = db.execute("DELETE FROM capture_gaps WHERE profile_id=?", (self.profile_id,)).rowcount
            counts["coverage_days"] = db.execute("DELETE FROM coverage_days WHERE profile_id=?", (self.profile_id,)).rowcount
            counts["maintenance_counters"] = db.execute("DELETE FROM maintenance_counters WHERE profile_id=?", (self.profile_id,)).rowcount
            counts["names"] += db.execute("UPDATE item_names SET name=NULL,erased=1 WHERE profile_id=? AND erased=0", (self.profile_id,)).rowcount
            counts["audit_rows"] += db.execute("UPDATE local_audit SET detail='{}',erased=1 WHERE profile_id=? AND erased=0", (self.profile_id,)).rowcount
            counts["corrections"] += db.execute("UPDATE corrections SET payload='{}',erased=1 WHERE profile_id=? AND erased=0", (self.profile_id,)).rowcount
            db.execute("DELETE FROM current_items WHERE profile_id=?", (self.profile_id,))
            # Remaining observation rows of this profile (none expected) become stubs too.
            for row in db.execute("SELECT observation_id,observed_at_ms FROM local_observations WHERE profile_id=? AND erased=0", (self.profile_id,)).fetchall():
                db.execute("UPDATE local_observations SET record=?,candidates=NULL,erased=1 WHERE profile_id=? AND observation_id=?",
                           (_json({"erased": True, "observed_at_ms": row["observed_at_ms"]}), self.profile_id, row["observation_id"]))
                counts["observations"] += 1
            db.execute("DELETE FROM embeddings WHERE profile_id=?", (self.profile_id,))
            # Legacy v1 personal rows; the spend ledger (api_calls) stays.
            legacy = {"objects": db.execute("DELETE FROM objects WHERE profile_id=?", (self.profile_id,)).rowcount,
                      "candidates": db.execute("DELETE FROM candidates WHERE profile_id=?", (self.profile_id,)).rowcount,
                      "observations": db.execute("DELETE FROM observations WHERE profile_id=?", (self.profile_id,)).rowcount,
                      "bindings": db.execute("DELETE FROM bindings WHERE profile_id=?", (self.profile_id,)).rowcount,
                      "decisions": db.execute("UPDATE decisions SET detail='{}' WHERE profile_id=?", (self.profile_id,)).rowcount}
            counts["legacy_rows"] = sum(legacy.values())
            # Calibrations measured on the household's own footage are personal;
            # synthetic / licensed-dataset ones are not and stay.
            counts["calibrations"] = db.execute("DELETE FROM calibrations WHERE profile_id=? AND source='own-footage'", (self.profile_id,)).rowcount
            # From now on any capture with a wall time before this instant is refused
            # (a browser mirror cannot re-add erased evidence).
            retention = self._retention_row(db)
            retention["erased_at_ms"] = now
            self._write_retention(db, retention, now)
            db.execute("INSERT INTO local_audit(profile_id,at_ms,action,item_id,detail) VALUES(?,?,?,?,?)",
                       (self.profile_id, now, "profile_erased", None, _json({"actor": actor, "counts": counts})))
        swap = self._vacuum_swap()
        return {"erased": True, "profile_id": self.profile_id, "counts": counts, "swap": swap,
                "scope": "logical", "forensic_erasure": False}

    def _vacuum_swap(self) -> str:
        """VACUUM INTO a fresh private file next to the database and replace the
        database with it; the PERSIST journal (which still holds the pages the
        erasure transaction overwrote) is removed so _connection recreates an empty
        private one. Falls back to an in-place VACUUM when the replace is refused.
        Returns "replaced" | "in_place"."""
        fresh = Path(str(self.path) + f".vacuum-{uuid.uuid4().hex[:12]}")
        journal = Path(str(self.path) + "-journal")
        try:
            # The target (and the journal SQLite could open beside it) exist with
            # private modes BEFORE VACUUM INTO writes a byte: SQLite reuses an
            # existing empty file instead of creating one with the umask.
            for path in (fresh, Path(str(fresh) + "-journal")):
                os.close(private_append_fd(path))
            db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
            try:
                db.execute("VACUUM INTO ?", (str(fresh),))
            finally:
                db.close()
            check = sqlite3.connect(str(fresh), timeout=10)
            try:
                ok = check.execute("PRAGMA quick_check").fetchone()[0] == "ok"
                version = check.execute("PRAGMA user_version").fetchone()[0]
            finally:
                check.close()
            if not ok or version != self._schema_version():
                raise OSError("vacuumed copy failed its check")
            with open(fresh, "rb+") as handle:
                os.fsync(handle.fileno())
            os.replace(fresh, self.path)
            # The persisted journal still holds the pages the erasure overwrote:
            # zero-length it, then remove it; _connection recreates an empty private one.
            for sidecar in (journal, Path(str(fresh) + "-journal")):
                self._drop_sidecar(sidecar)
            self._sync_directory()
            return "replaced"
        except Exception:
            # The erasure transaction is already committed; the rebuild is best
            # effort and its failure is reported, never raised over a done erasure.
            for leftover in (fresh, Path(str(fresh) + "-journal")):
                try:
                    os.unlink(leftover)
                except OSError:
                    pass
            try:
                db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
                try:
                    db.execute("VACUUM")
                finally:
                    db.close()
            except Exception:
                return "none"
            return "in_place"

    @staticmethod
    def _drop_sidecar(path):
        """Truncate a sidecar file to zero bytes (synced) and then unlink it, so its
        content is gone even where the unlink is refused. Missing is fine."""
        try:
            fd = os.open(path, os.O_RDWR)
        except OSError:
            return
        try:
            os.ftruncate(fd, 0)
            os.fsync(fd)
        except OSError:
            pass
        finally:
            os.close(fd)
        try:
            os.unlink(path)
        except OSError:
            pass

    def _schema_version(self) -> int:
        with self._connection() as db:
            return db.execute("PRAGMA user_version").fetchone()[0]

    def _sync_directory(self):
        if os.name == "nt":
            return
        try:
            fd = os.open(self.path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(fd)
        except OSError:
            pass
        finally:
            os.close(fd)

    # ------------------------------------------------------------- idle frames (CP4)
    def ingest_idle(self, raw: bytes) -> dict:
        """Store one idle keyframe in the rolling cache. Strict parsing
        (perception.episode.parse_idle: PacketTooLarge -> 413, ValueError -> 400,
        an implausible capture clock is a ValueError too). Returns {"frame_id",
        "retained": True, "expires_at_ms", "evicted"} or, over the per-device
        daily cap or a cache full of promoted frames, {"frame_id", "retained":
        False, "reason": "idle_cap" | "idle_cache_full"} without storing (not an
        exception). A resend of a stored frame_id is idempotent."""
        frame = parse_idle(raw)
        now = self._now_ms()
        wall = frame.wall_ms
        if wall <= 0 or wall > now + 300000:
            raise ValueError("Implausible idle frame clock")
        data = jpeg_bytes(frame.jpeg_b64)
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._capture_allowed(db, wall)
            existing = db.execute("SELECT expires_at_ms FROM idle_frames WHERE profile_id=? AND device_id=? AND frame_id=?",
                                  (self.profile_id, frame.device_id, frame.frame_id)).fetchone()
            if existing:
                return {"frame_id": frame.frame_id, "retained": True, "expires_at_ms": existing[0], "evicted": 0}
            day_count = db.execute("SELECT count(*) FROM idle_frames WHERE profile_id=? AND device_id=? AND received_ms>?",
                                   (self.profile_id, frame.device_id, now - 24 * 3600 * 1000)).fetchone()[0]
            if day_count >= IDLE_MAX_PER_DAY:
                return {"frame_id": frame.frame_id, "retained": False, "reason": "idle_cap"}
            ttl = self._retention_row(db)["idle_hours"] * 3600 * 1000
            total = db.execute("SELECT COALESCE(SUM(length(jpeg)),0) FROM idle_frames WHERE profile_id=?", (self.profile_id,)).fetchone()[0]
            evicted = 0
            while total + len(data) > IDLE_CACHE_BYTES:
                oldest = db.execute("SELECT device_id,frame_id,length(jpeg) FROM idle_frames WHERE profile_id=? AND promoted=0 ORDER BY received_ms,t_wall_ms,frame_id LIMIT 1", (self.profile_id,)).fetchone()
                if oldest is None:
                    return {"frame_id": frame.frame_id, "retained": False, "reason": "idle_cache_full"}
                db.execute("DELETE FROM idle_frames WHERE profile_id=? AND device_id=? AND frame_id=?", (self.profile_id, oldest[0], oldest[1]))
                total -= oldest[2] or 0
                evicted += 1
            expires = now + ttl
            db.execute("INSERT INTO idle_frames(profile_id,device_id,frame_id,session_id,t_wall_ms,received_ms,width,height,jpeg,motion_energy,expires_at_ms,promoted,consent_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,0,?)",
                       (self.profile_id, frame.device_id, frame.frame_id, frame.session_id, wall, now, frame.capture.width, frame.capture.height,
                        data, float(frame.motion_energy), expires, CONSENT_VERSION))
            return {"frame_id": frame.frame_id, "retained": True, "expires_at_ms": expires, "evicted": evicted}

    def expire_idle(self, now_ms=None) -> dict:
        """Hard-delete expired unpromoted idle frames (expires_at_ms <= now, or
        older than the retention row's idle_hours). Returns {"expired",
        "remaining", "promoted"}."""
        now = self._now_ms() if now_ms is None else now_ms
        if isinstance(now, bool) or type(now) is not int or now < 0:
            raise ValueError("now_ms must be nonnegative epoch milliseconds")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            ttl = self._retention_row(db)["idle_hours"] * 3600 * 1000
            expired = db.execute("DELETE FROM idle_frames WHERE profile_id=? AND promoted=0 AND (expires_at_ms<=? OR received_ms+?<=?)",
                                 (self.profile_id, now, ttl, now)).rowcount
            remaining = db.execute("SELECT count(*) FROM idle_frames WHERE profile_id=?", (self.profile_id,)).fetchone()[0]
            promoted = db.execute("SELECT count(*) FROM idle_frames WHERE profile_id=? AND promoted=1", (self.profile_id,)).fetchone()[0]
            return {"expired": expired, "remaining": remaining, "promoted": promoted}

    # --------------------------------------------------------- frame accounting (CP5)
    def ingest_telemetry(self, raw: bytes) -> dict:
        """Store one browser telemetry window (POST /api/telemetry) in
        frame_counters. Strict parsing (perception.episode.parse_telemetry:
        PacketTooLarge over MAX_TELEMETRY_BYTES -> 413, ValueError -> 400, an
        implausible window clock is a ValueError too). Counters are numbers only,
        so no consent acknowledgement is needed and nothing personal is stored.
        Returns {"retained": True, "t_ms"} with t_ms the window's wall-clock end
        time; a resend of the same (device, session, t_ms) is idempotent."""
        window = parse_telemetry(raw)
        now = self._now_ms()
        wall = window.wall_ms
        if wall <= 0 or wall > now + TELEMETRY_FUTURE_MS:
            raise ValueError("Implausible telemetry clock")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO frame_counters(profile_id,device_id,session_id,t_ms,received_ms,window_ms,counters,timing,settings) VALUES(?,?,?,?,?,?,?,?,?)",
                       (self.profile_id, window.device_id, window.session_id, wall, now, window.window_ms,
                        _json(window.counters.model_dump()), _json(window.timing.model_dump()), _json(window.settings.model_dump())))
            # A window that reports coverage loss is also a coverage-gap row (ruling 1):
            # items placed before its end then read gap_since, so the stored projection
            # is rebuilt when a new gap row lands.
            if window.counters.gap_ms > 0 and self._record_gap(db, window.device_id, window.session_id, "telemetry",
                                                                 wall - window.window_ms, wall, window.counters.gap_ms, now):
                self._rebuild_projection(db)
        return {"retained": True, "t_ms": wall}

    def bump_counter(self, name, value=1) -> float:
        """Add value to the per-profile, per-UTC-day maintenance counter `name`
        (MAINTENANCE_COUNTERS; the day is the injected clock's). value is a finite
        nonnegative number. Returns the counter's new value."""
        if name not in MAINTENANCE_COUNTERS:
            raise ValueError("Unknown maintenance counter")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("Invalid counter value")
        day = self._utc_day(self._now_ms())
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO maintenance_counters(profile_id,day,name,value) VALUES(?,?,?,?) "
                       "ON CONFLICT(profile_id,day,name) DO UPDATE SET value=value+excluded.value", (self.profile_id, day, name, float(value)))
            return float(db.execute("SELECT value FROM maintenance_counters WHERE profile_id=? AND day=? AND name=?", (self.profile_id, day, name)).fetchone()[0])

    @staticmethod
    def _utc_day(now_ms) -> str:
        return datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")

    @staticmethod
    def _day_window(day_utc):
        """(start_ms, end_ms) of a UTC calendar day; ValueError for a malformed day."""
        if not isinstance(day_utc, str) or not DAY_UTC.fullmatch(day_utc):
            raise ValueError("Invalid day")
        try:
            start = datetime.strptime(day_utc, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            raise ValueError("Invalid day") from None
        start_ms = int(start.timestamp() * 1000)
        return start_ms, start_ms + 24 * 3600 * 1000

    def _maintenance_counters(self, db, day_utc) -> dict:
        """{name: value} of the day's maintenance counters (every name, 0 when unset)."""
        values = {name: 0.0 for name in MAINTENANCE_COUNTERS}
        for row in db.execute("SELECT name,value FROM maintenance_counters WHERE profile_id=? AND day=?", (self.profile_id, day_utc)):
            if row["name"] in values:
                values[row["name"]] = float(row["value"])
        return values

    def _live_coverage(self, db, day_utc) -> dict | None:
        """The day's totals from the live frame_counters rows (None when the day has
        none): the seven plan keys plus effective_ms, packets_acked, episodes_started,
        frames_captured, frames_analysed, frames_dropped, bytes_sent and windows."""
        start_ms, end_ms = self._day_window(day_utc)
        rows = db.execute("SELECT session_id,window_ms,counters FROM frame_counters WHERE profile_id=? AND t_ms>=? AND t_ms<?",
                          (self.profile_id, start_ms, end_ms)).fetchall()
        if not rows:
            return None
        totals = {"camera_on_ms": 0, "gap_ms": 0, "episodes": 0, "packets": 0, "idle_sent": 0, "idle_dropped": 0, "sessions": 0,
                  "effective_ms": 0, "packets_acked": 0, "episodes_started": 0, "frames_captured": 0, "frames_analysed": 0,
                  "frames_dropped": 0, "bytes_sent": 0, "windows": 0}
        sessions = set()
        for row in rows:
            try:
                counters = json.loads(row["counters"])
            except ValueError:
                continue
            if not isinstance(counters, dict):
                continue
            def count(name):
                value = counters.get(name, 0)
                return value if type(value) is int and value >= 0 else 0
            sessions.add(row["session_id"])
            totals["windows"] += 1
            totals["camera_on_ms"] += int(row["window_ms"])
            totals["gap_ms"] += count("gap_ms")
            totals["episodes"] += count("episodes_finished")
            totals["episodes_started"] += count("episodes_started")
            totals["packets"] += count("packets_sent")
            totals["packets_acked"] += count("packets_acked")
            totals["idle_sent"] += count("idle_sent")
            totals["idle_dropped"] += count("idle_dropped")
            totals["frames_captured"] += count("frames_captured")
            totals["frames_analysed"] += count("frames_analysed")
            totals["frames_dropped"] += count("frames_skipped_busy") + count("frames_dropped_backpressure")
            totals["bytes_sent"] += count("bytes_sent")
        totals["sessions"] = len(sessions)
        totals["effective_ms"] = max(0, totals["camera_on_ms"] - totals["gap_ms"])
        return totals

    def _rollup_day(self, db, day_utc, now_ms):
        """Write the day's aggregate (coverage_days, numbers only: the live totals
        plus the maintenance counters, cpu seconds as integer milliseconds) from the
        live rows; returns the aggregate or None when the day has no live rows."""
        totals = self._live_coverage(db, day_utc)
        if totals is None:
            return None
        counters = self._maintenance_counters(db, day_utc)
        aggregates = dict(totals)
        aggregates.update(process_cpu_ms=int(round(counters["process_cpu_s"] * 1000)), reobs_cpu_ms=int(round(counters["reobs_cpu_s"] * 1000)),
                          chat_local=int(round(counters["chat_local"])), image_serves=int(round(counters["image_serves"])),
                          image_bytes=int(round(counters["image_bytes"])))
        db.execute("INSERT INTO coverage_days(profile_id,day,aggregates,updated_ms) VALUES(?,?,?,?) "
                   "ON CONFLICT(profile_id,day) DO UPDATE SET aggregates=excluded.aggregates,updated_ms=excluded.updated_ms",
                   (self.profile_id, day_utc, _json(aggregates), int(now_ms)))
        return aggregates

    def coverage(self, day_utc: str) -> dict:
        """Frame accounting for one UTC calendar day ("YYYY-MM-DD"): the telemetry
        windows whose wall-clock end falls in that day (a window straddling
        midnight counts for the day it ended in). camera_on_ms is the sum of
        window_ms over every session that day (the time the browser reported the
        camera running), gap_ms the reported coverage loss inside those windows,
        episodes the episodes the browser finished, packets the packets it sent,
        idle_sent / idle_dropped the idle keyframes, sessions the distinct capture
        sessions. Extra keys: effective_ms (camera_on_ms minus gap_ms, floored at
        0: the time capture actually ran), packets_acked, episodes_started,
        frames_captured, frames_analysed, frames_dropped (busy + backpressure),
        bytes_sent, windows (row count), day, counters (the day's maintenance
        counters: process_cpu_s, reobs_cpu_s, chat_local, image_serves,
        image_bytes) and source: "live" when the day still has telemetry rows (the
        daily aggregate in coverage_days is refreshed on the way), "rollup" when
        only the aggregate survives (telemetry rows expire with episodes_days), or
        "none". ValueError for a malformed day."""
        self._day_window(day_utc)
        now = self._now_ms()
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            live = self._live_coverage(db, day_utc)
            if live is not None:
                self._rollup_day(db, day_utc, now)
                result = dict(live, day=day_utc, counters=self._maintenance_counters(db, day_utc), source="live")
                return result
            row = db.execute("SELECT aggregates FROM coverage_days WHERE profile_id=? AND day=?", (self.profile_id, day_utc)).fetchone()
            counters = self._maintenance_counters(db, day_utc)
        zeros = {"camera_on_ms": 0, "gap_ms": 0, "episodes": 0, "packets": 0, "idle_sent": 0, "idle_dropped": 0, "sessions": 0,
                 "effective_ms": 0, "packets_acked": 0, "episodes_started": 0, "frames_captured": 0, "frames_analysed": 0,
                 "frames_dropped": 0, "bytes_sent": 0, "windows": 0}
        if row is None:
            return dict(zeros, day=day_utc, counters=counters, source="none")
        try:
            aggregates = json.loads(row["aggregates"])
        except ValueError:
            aggregates = {}
        result = {key: (aggregates.get(key) if type(aggregates.get(key)) is int and aggregates.get(key) >= 0 else 0) for key in zeros}
        rolled = {"process_cpu_s": aggregates.get("process_cpu_ms", 0) / 1000.0, "reobs_cpu_s": aggregates.get("reobs_cpu_ms", 0) / 1000.0,
                  "chat_local": float(aggregates.get("chat_local", 0)), "image_serves": float(aggregates.get("image_serves", 0)),
                  "image_bytes": float(aggregates.get("image_bytes", 0))}
        # The rollup carries the counters as they were when the live rows expired;
        # anything bumped since (a chat about that day's evidence) is still live.
        for name in MAINTENANCE_COUNTERS:
            counters[name] = max(counters[name], rolled.get(name, 0.0))
        return dict(result, day=day_utc, counters=counters, source="rollup")

    # --------------------------------------------------------------- retention (CP4)
    def _retention_row(self, db) -> dict:
        row = db.execute("SELECT * FROM retention WHERE profile_id=?", (self.profile_id,)).fetchone()
        if row is None:
            return dict(RETENTION_DEFAULTS, consent_version=CONSENT_VERSION, updated_ms=None, acknowledged_version=None, erased_at_ms=None)
        result = {key: row[key] for key in ("episodes_days", "idle_hours", "landmarks_hours", "updated_ms", "acknowledged_version", "erased_at_ms")}
        result["consent_version"] = CONSENT_VERSION
        return result

    def _write_retention(self, db, current, now):
        db.execute("INSERT INTO retention(profile_id,consent_version,episodes_days,idle_hours,landmarks_hours,updated_ms,acknowledged_version,erased_at_ms) VALUES(?,?,?,?,?,?,?,?) "
                   "ON CONFLICT(profile_id) DO UPDATE SET consent_version=excluded.consent_version,episodes_days=excluded.episodes_days,"
                   "idle_hours=excluded.idle_hours,landmarks_hours=excluded.landmarks_hours,updated_ms=excluded.updated_ms,"
                   "acknowledged_version=excluded.acknowledged_version,erased_at_ms=excluded.erased_at_ms",
                   (self.profile_id, CONSENT_VERSION, current["episodes_days"], current["idle_hours"], current["landmarks_hours"], now,
                    current.get("acknowledged_version"), current.get("erased_at_ms")))

    def get_retention(self) -> dict:
        """The retention row {consent_version (the build constant), episodes_days,
        idle_hours, landmarks_hours, updated_ms, acknowledged_version,
        erased_at_ms} (defaults with updated_ms None until set)."""
        with self._connection() as db:
            return self._retention_row(db)

    # Consent (CP4, Oversight rule). Capture is refused until the build's
    # CONSENT_VERSION has been acknowledged for this profile, and anything captured
    # before an erase_profile is refused for good (a browser mirror cannot re-add it).
    def consent_state(self) -> dict:
        """{required_version, acknowledged_version, ok}."""
        with self._connection() as db:
            return self._consent_state(db)

    def _consent_state(self, db) -> dict:
        row = self._retention_row(db)
        return {"required_version": CONSENT_VERSION, "acknowledged_version": row["acknowledged_version"],
                "ok": row["acknowledged_version"] == CONSENT_VERSION}

    def acknowledge_consent(self, version, actor) -> dict:
        """Record that the disclosure for `version` was acknowledged (audited).
        version must equal CONSENT_VERSION (ValueError "consent version mismatch"
        otherwise; the server maps it to 400). Returns consent_state()."""
        _check_actor(actor)
        if not isinstance(version, str) or version != CONSENT_VERSION:
            raise ValueError("consent version mismatch")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            now = self._now_ms()
            current = self._retention_row(db)
            current["acknowledged_version"] = version
            self._write_retention(db, current, now)
            db.execute("INSERT INTO local_audit(profile_id,at_ms,action,item_id,detail) VALUES(?,?,?,?,?)",
                       (self.profile_id, now, "consent_acknowledged", None, _json({"actor": actor, "version": version})))
            return self._consent_state(db)

    def _capture_allowed(self, db, wall_ms):
        """Refuse a capture (episode: its wall start; idle frame: its wall time)
        without a current consent acknowledgement (ValueError "consent required"
        -> 409 consent_required) or with a wall time earlier than the profile's
        last erase_profile minus ERASED_BEFORE_TOLERANCE_MS (ValueError "captured
        before erasure" -> 409 erased_before). The tolerance absorbs a phone clock
        lagging the laptop; a mirrored capture from the final minutes before the
        erasure is therefore not refused here, and the browser clears its mirror
        on erase-all to cover that window."""
        row = self._retention_row(db)
        if row["acknowledged_version"] != CONSENT_VERSION:
            raise ValueError("consent required")
        if row["erased_at_ms"] is not None and wall_ms < row["erased_at_ms"] - ERASED_BEFORE_TOLERANCE_MS:
            raise ValueError("captured before erasure")

    def retention_counts(self) -> dict:
        """Live counts for GET /api/retention: idle_cached, idle_promoted,
        revisions_expired, landmarks_reduced, revisions_erased."""
        with self._connection() as db:
            return {"idle_cached": db.execute("SELECT count(*) FROM idle_frames WHERE profile_id=? AND promoted=0", (self.profile_id,)).fetchone()[0],
                    "idle_promoted": db.execute("SELECT count(*) FROM idle_frames WHERE profile_id=? AND promoted=1", (self.profile_id,)).fetchone()[0],
                    "revisions_expired": db.execute("SELECT count(*) FROM episode_revisions WHERE profile_id=? AND redacted_reason='retention'", (self.profile_id,)).fetchone()[0],
                    "landmarks_reduced": db.execute("SELECT count(*) FROM episode_revisions WHERE profile_id=? AND reduced_ms IS NOT NULL", (self.profile_id,)).fetchone()[0],
                    "revisions_erased": db.execute("SELECT count(*) FROM episode_revisions WHERE profile_id=? AND redacted_reason='erasure'", (self.profile_id,)).fetchone()[0]}

    def set_retention(self, *, actor, **fields) -> dict:
        """Update the retention windows (audited, actor literal). Accepted fields:
        episodes_days (7..365), idle_hours (1..72), landmarks_hours (1..168); ints
        only, no bools. consent_version is a build constant and is refused here.
        Unknown field, bad value or empty update -> ValueError. Returns the row."""
        _check_actor(actor)
        if not fields or set(fields) - set(RETENTION_RANGES):
            raise ValueError("Invalid retention fields")
        for name, (low, high) in RETENTION_RANGES.items():
            if name in fields:
                value = fields[name]
                if isinstance(value, bool) or type(value) is not int or not low <= value <= high:
                    raise ValueError("Invalid retention window")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self._retention_row(db)
            # CP5 carried item: the audit detail records the old and the new value of
            # every window the call changed (ints only, never free text).
            old = {name: current[name] for name in fields}
            current.update(fields)
            now = self._now_ms()
            self._write_retention(db, current, now)
            db.execute("INSERT INTO local_audit(profile_id,at_ms,action,item_id,detail) VALUES(?,?,?,?,?)",
                       (self.profile_id, now, "retention_set", None, _json({"actor": actor, "fields": fields, "old": old, "new": dict(fields)})))
            return self._retention_row(db)

    def apply_retention(self, now_ms=None, *, limit=RETENTION_BATCH) -> dict:
        """Run the retention tiers at now_ms (default: the injected clock):
        (a) packets of revisions received more than episodes_days ago are
        replaced by NULL with redacted_reason "retention" (metadata, digests,
        observations and embeddings stay; the item then reads evidence_expired and
        its reference_image is null) and promoted idle frames that old are
        deleted; (b) idle expiry (expire_idle); (c) landmark reduction: at most
        `limit` packets older than landmarks_hours are rewritten with landmarks []
        and the server-only landmark_summary (hand_bbox + hand_busy verdict per
        hand), reduced_ms recorded, digest columns untouched. Returns counts."""
        now = self._now_ms() if now_ms is None else now_ms
        if isinstance(now, bool) or type(now) is not int or now < 0:
            raise ValueError("now_ms must be nonnegative epoch milliseconds")
        if type(limit) is not int or not 1 <= limit <= 1024:
            raise ValueError("Invalid retention batch")
        counts = {"revisions_expired": 0, "revisions_superseded": 0, "idle_promoted_expired": 0, "jobs_expired": 0,
                  "reobservations_expired": 0, "landmarks_reduced": 0, "reduction_checked": 0, "reduction_failed": 0,
                  "reduction_deferred": 0, "telemetry_expired": 0, "gaps_expired": 0, "coverage_days_rolled": 0,
                  "coverage_days_expired": 0}
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            retention = self._retention_row(db)
            cutoff = now - retention["episodes_days"] * 24 * 3600 * 1000
            expired = db.execute("SELECT device_id,episode_id,revision_no FROM episode_revisions WHERE profile_id=? AND packet IS NOT NULL AND received_at_ms<?",
                                 (self.profile_id, cutoff)).fetchall()
            for row in expired:
                key = (self.profile_id, row["device_id"], row["episode_id"], row["revision_no"])
                db.execute("UPDATE episode_revisions SET packet=NULL,redacted_reason='retention' WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no=?", key)
                counts["jobs_expired"] += db.execute("UPDATE episode_jobs SET status='expired',token=NULL,lease_until=NULL WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no=? AND status IN ('pending','processing')", key).rowcount
                counts["revisions_expired"] += 1
            # A superseded accepted revision (a newer accepted one exists) loses its
            # bytes after SUPERSEDED_TTL_MS; digests, metadata and observations stay.
            superseded = db.execute("""SELECT r.device_id,r.episode_id,r.revision_no FROM episode_revisions r
                WHERE r.profile_id=? AND r.packet IS NOT NULL AND r.accepted=1 AND r.received_at_ms<?
                AND EXISTS (SELECT 1 FROM episode_revisions n WHERE n.profile_id=r.profile_id AND n.device_id=r.device_id
                            AND n.episode_id=r.episode_id AND n.accepted=1 AND n.revision_no>r.revision_no)""",
                                    (self.profile_id, now - SUPERSEDED_TTL_MS)).fetchall()
            for row in superseded:
                key = (self.profile_id, row["device_id"], row["episode_id"], row["revision_no"])
                db.execute("UPDATE episode_revisions SET packet=NULL,redacted_reason='superseded' WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no=?", key)
                counts["jobs_expired"] += db.execute("UPDATE episode_jobs SET status='expired',token=NULL,lease_until=NULL WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no=? AND status IN ('pending','processing')", key).rowcount
                counts["revisions_superseded"] += 1
            counts["idle_promoted_expired"] = db.execute("DELETE FROM idle_frames WHERE profile_id=? AND promoted=1 AND received_ms<?", (self.profile_id, cutoff)).rowcount
            # CP5 (coordinator ruling 2): the most recent re-observation decision of
            # every item is kept whatever its age, so a stale item stays stale at the
            # episodes_days boundary; older decisions expire.
            counts["reobservations_expired"] = db.execute("""DELETE FROM reobservations WHERE profile_id=? AND t_wall_ms<?
                AND t_wall_ms<(SELECT max(r2.t_wall_ms) FROM reobservations r2 WHERE r2.profile_id=reobservations.profile_id AND r2.item_id=reobservations.item_id)""",
                                                          (self.profile_id, cutoff)).rowcount
            # CP5: telemetry windows expire with the episodes (by the time they were
            # received); each day they cover is rolled up into coverage_days first so
            # the day's numbers outlive the rows. Coverage-gap rows expire the same way.
            days = {self._utc_day(row[0]) for row in db.execute("SELECT t_ms FROM frame_counters WHERE profile_id=? AND received_ms<?", (self.profile_id, cutoff))}
            for day in sorted(days):
                if self._rollup_day(db, day, now) is not None:
                    counts["coverage_days_rolled"] += 1
            counts["telemetry_expired"] = db.execute("DELETE FROM frame_counters WHERE profile_id=? AND received_ms<?", (self.profile_id, cutoff)).rowcount
            counts["gaps_expired"] = db.execute("DELETE FROM capture_gaps WHERE profile_id=? AND t_to_ms<?", (self.profile_id, cutoff)).rowcount
            counts["coverage_days_expired"] = db.execute("DELETE FROM coverage_days WHERE profile_id=? AND day<?",
                                                         (self.profile_id, self._utc_day(now - COVERAGE_DAYS_RETENTION_DAYS * 24 * 3600 * 1000))).rowcount
            reduce_before = now - retention["landmarks_hours"] * 3600 * 1000
            # F2: a revision whose job is still pending/processing keeps its raw
            # landmarks (the hand hull needs them at processing time); it is deferred
            # and counted, not reduced.
            counts["reduction_deferred"] = db.execute("""SELECT count(*) FROM episode_revisions r JOIN episode_jobs j USING(profile_id,device_id,episode_id,revision_no)
                WHERE r.profile_id=? AND r.packet IS NOT NULL AND r.reduced_ms IS NULL AND r.received_at_ms<? AND j.status IN ('pending','processing')""",
                                                      (self.profile_id, reduce_before)).fetchone()[0]
            pending = db.execute("""SELECT r.device_id,r.episode_id,r.revision_no,r.packet FROM episode_revisions r
                LEFT JOIN episode_jobs j USING(profile_id,device_id,episode_id,revision_no)
                WHERE r.profile_id=? AND r.packet IS NOT NULL AND r.reduced_ms IS NULL AND r.received_at_ms<?
                AND (j.status IS NULL OR j.status NOT IN ('pending','processing'))
                ORDER BY r.received_at_ms,r.revision_no LIMIT ?""", (self.profile_id, reduce_before, limit)).fetchall()
            for row in pending:
                key = (self.profile_id, row["device_id"], row["episode_id"], row["revision_no"])
                counts["reduction_checked"] += 1
                reduced = self._reduce_landmarks(bytes(row["packet"]))
                if reduced is None:
                    counts["reduction_failed"] += 1
                    continue
                if reduced is not False:
                    db.execute("UPDATE episode_revisions SET packet=?,reduced_ms=? WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no=?", (reduced, now) + key)
                    counts["landmarks_reduced"] += 1
                else:
                    db.execute("UPDATE episode_revisions SET reduced_ms=? WHERE profile_id=? AND device_id=? AND episode_id=? AND revision_no=?", (now,) + key)
            if (counts["revisions_expired"] or counts["revisions_superseded"] or counts["idle_promoted_expired"]
                    or counts["reobservations_expired"] or counts["gaps_expired"]):
                self._rebuild_projection(db)
        idle = self.expire_idle(now)
        counts["idle_expired"] = idle["expired"]
        counts["idle_remaining"] = idle["remaining"]
        return counts

    @staticmethod
    def _reduce_landmarks(packet_bytes):
        """The packet bytes rewritten with landmarks [] and landmark_summary, or
        False when the packet has no landmarks (nothing to reduce), or None when
        the packet or its reduced form does not parse (left untouched, counted)."""
        try:
            packet = parse_packet(packet_bytes)
        except ValueError:
            return None
        if not packet.landmarks:
            return False
        summary = []
        for sample in packet.landmarks:
            hands = []
            for hand in sample.hands:
                try:
                    verdict = hand_busy([hand.model_dump()])
                except ValueError:
                    verdict = {"busy": None, "basis": "degenerate hand"}
                hands.append({"hand_bbox": [float(v) for v in hand.hand_bbox], "busy": verdict["busy"], "basis": str(verdict["basis"])[:40]})
            summary.append({"frame_id": sample.frame_id, "t_ms": sample.t_ms, "hands": hands})
        data = packet.model_dump()
        data["landmarks"] = []
        data["landmark_summary"] = summary
        reduced = json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        try:
            check = parse_packet(reduced)
        except ValueError:
            return None
        # The reduced bytes must still carry every keyframe (item_image) and the
        # summary; the stored digest columns are never recomputed from these bytes.
        if [f.frame_id for f in check.keyframes] != [f.frame_id for f in packet.keyframes] or check.landmark_summary is None or check.landmarks:
            return None
        return reduced

    # --------------------------------------------------------------- migration (CP4)
    @staticmethod
    def _legacy_media(payload) -> set:
        """Distinct media path strings (frames + crop) named by a v1 candidate
        payload or observation record; counted only, never opened."""
        try:
            value = json.loads(payload) if isinstance(payload, (str, bytes)) else {}
        except ValueError:
            return set()
        if not isinstance(value, dict):
            return set()
        paths = {p for p in value.get("frames") or [] if isinstance(p, str) and p}
        if isinstance(value.get("crop"), str) and value["crop"]:
            paths.add(value["crop"])
        return paths

    def migrate_v1(self, *, dry_run=True, actor) -> dict:
        """Explicit conversion of the legacy v1 ledger (B-10). Each observation of
        a user-confirmed ('tracked') legacy object becomes a local_observations
        row with source "legacy_v1", identity_state "provisional" (never trusted),
        outcome from the legacy action (placed -> placed_on_surface, picked_up ->
        picked_up, sighted -> sighted, anything else -> uncertain), location_text
        from the legacy scene description, observed_at_ms from its timestamp and no
        image (reference_image null; legacy frames were paths on disk). Every
        migrated row (local_observations.consent_version, the observation record
        and its legacy episode_revisions row) is stamped consent_version
        LEGACY_CONSENT_VERSION ("legacy-v1"); counts carries the number stamped as
        consent_stamped_legacy_v1. Legacy rows, budgets, unknown spend and leases
        are untouched. dry_run=True returns counts and up to 5 sample rows without
        writing; a real run is one transaction with a migrations row and is
        idempotent (a second run reports status "already_migrated"). Any exception
        rolls everything back."""
        _check_actor(actor)
        if type(dry_run) is not bool:
            raise ValueError("dry_run must be a bool")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            done = db.execute("SELECT * FROM migrations WHERE profile_id=? AND migration_id=?", (self.profile_id, MIGRATION_V1_ID)).fetchone()
            if done is not None:
                return {"status": "already_migrated", "dry_run": dry_run, "from_version": done["from_version"],
                        "migration": {"migration_id": done["migration_id"], "from_version": done["from_version"],
                                      "counts": json.loads(done["counts"]), "at_ms": done["at_ms"], "actor": done["actor"]}}
            objects = {row["object_id"]: dict(row) for row in db.execute("SELECT object_id,name,category,status,created_at FROM objects WHERE profile_id=?", (self.profile_id,))}
            counts = {"objects": len(objects), "objects_confirmed": sum(1 for o in objects.values() if o["status"] == "tracked"),
                      "observations": 0, "converted": 0, "skipped_unconfirmed": 0, "skipped_unknown_object": 0,
                      "candidates": db.execute("SELECT count(*) FROM candidates WHERE profile_id=?", (self.profile_id,)).fetchone()[0],
                      "decisions": db.execute("SELECT count(*) FROM decisions WHERE profile_id=?", (self.profile_id,)).fetchone()[0],
                      "api_calls": db.execute("SELECT count(*) FROM api_calls WHERE profile_id=?", (self.profile_id,)).fetchone()[0],
                      "legacy_media_files": 0}
            # Legacy frames/crops are JPEG paths on disk. They are counted so the
            # operator knows they exist, never read, moved, deleted or referenced.
            media = set()
            for (payload,) in db.execute("SELECT payload FROM candidates WHERE profile_id=?", (self.profile_id,)):
                media |= self._legacy_media(payload)
            rows = []
            device_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"pam-v1-device:{self.profile_id}"))
            for row in db.execute("SELECT event_id,object_id,observed_at,sequence,action,record FROM observations WHERE profile_id=? ORDER BY observed_at,sequence,event_id", (self.profile_id,)):
                counts["observations"] += 1
                media |= self._legacy_media(row["record"])
                legacy = objects.get(row["object_id"])
                if legacy is None:
                    counts["skipped_unknown_object"] += 1
                    continue
                if legacy["status"] != "tracked":
                    counts["skipped_unconfirmed"] += 1
                    continue
                try:
                    record_v1 = json.loads(row["record"])
                except ValueError:
                    record_v1 = {}
                # Location text comes from the scene's room / surface fields ONLY:
                # never the VLM's free-text description, lat/lon, media paths or its
                # actor verdict (the actor is always unknown after migration).
                scene = record_v1.get("scene") if isinstance(record_v1.get("scene"), dict) else {}
                parts = [str(scene.get(key)).strip() for key in ("surface", "room") if isinstance(scene.get(key), str) and scene.get(key).strip()]
                location = ", ".join(parts) or None
                observed_ms = int(round(float(row["observed_at"]) * 1000))
                event_id = row["event_id"]
                item_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"pam-v1-item:{self.profile_id}:{row['object_id']}"))
                episode_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"pam-v1-episode:{self.profile_id}:{event_id}"))
                observation_id = hashlib.sha256(_json([self.profile_id, "legacy_v1", event_id]).encode()).hexdigest()
                record = {"frame_id": "legacy-" + hashlib.sha256(event_id.encode()).hexdigest()[:32], "bbox": None,
                          "label": str(legacy["name"])[:100] or "unknown", "actor": "unknown",
                          "outcome": LEGACY_OUTCOMES.get(row["action"], "uncertain"), "continuity_id": None,
                          "identity_state": "provisional", "location_text": str(location)[:600] if location else None,
                          "confidence": 0.0, "confidence_basis": "legacy v1 cloud verification; migrated as provisional, never trusted",
                          "calibration": {}, "session_id": str(record_v1.get("session_id") or "")[:160], "clock_status": "ok",
                          "capture_mode": "manual", "observed_at_ms": observed_ms, "item_id": item_id, "observation_id": observation_id,
                          "device_id": device_id, "episode_id": episode_id, "revision_no": 1, "source": "legacy_v1",
                          "identity_source": "legacy_v1", "legacy_object_id": row["object_id"], "legacy_event_id": event_id,
                          "legacy_action": row["action"], "consent_version": LEGACY_CONSENT_VERSION}
                rows.append(record)
                counts["converted"] += 1
            counts["legacy_media_files"] = len(media)
            counts["consent_stamped_legacy_v1"] = len(rows)
            samples = [{key: record[key] for key in ("item_id", "label", "outcome", "location_text", "observed_at_ms", "identity_state", "legacy_event_id")} for record in rows[:5]]
            if dry_run:
                return {"status": "dry_run", "dry_run": True, "from_version": version, "counts": counts, "samples": samples, "mutates_data": False}
            now = self._now_ms()
            for record in rows:
                key = (self.profile_id, record["device_id"], record["episode_id"], record["revision_no"])
                digest = hashlib.sha256(("legacy:" + record["legacy_event_id"]).encode()).hexdigest()
                db.execute("INSERT INTO episode_revisions(profile_id,device_id,episode_id,revision_no,semantic_digest,transport_digest,packet,received_at_ms,accepted,clock_status,redacted,redacted_reason,consent_version) VALUES(?,?,?,?,?,?,NULL,?,0,'ok',0,'legacy_v1',?)",
                           key + (digest, digest, record["observed_at_ms"], LEGACY_CONSENT_VERSION))
                db.execute("INSERT INTO local_observations(profile_id,observation_id,item_id,device_id,episode_id,revision_no,observed_at_ms,decided_at_ms,record,candidates,erased,consent_version) VALUES(?,?,?,?,?,?,?,?,?,NULL,0,?)",
                           (self.profile_id, record["observation_id"], record["item_id"], record["device_id"], record["episode_id"], record["revision_no"],
                            record["observed_at_ms"], now, _json(record), LEGACY_CONSENT_VERSION))
            db.execute("INSERT INTO migrations(profile_id,migration_id,from_version,counts,at_ms,actor) VALUES(?,?,?,?,?,?)",
                       (self.profile_id, MIGRATION_V1_ID, version, _json(counts), now, actor))
            db.execute("INSERT INTO local_audit(profile_id,at_ms,action,item_id,detail) VALUES(?,?,?,?,?)",
                       (self.profile_id, now, "migrated_v1", None, _json({"actor": actor, "counts": counts})))
            self._rebuild_projection(db)
            return {"status": "migrated", "dry_run": False, "from_version": version, "counts": counts, "samples": samples, "mutates_data": True,
                    "migration": {"migration_id": MIGRATION_V1_ID, "from_version": version, "counts": counts, "at_ms": now, "actor": actor}}
