"""Consent constants (CP4, Oversight rule adopted by the coordinator).

CONSENT_VERSION is a build constant: the store refuses to ingest episodes and
idle frames until this exact version has been acknowledged
(EpisodeStoreMixin.acknowledge_consent / consent_state), and every stored
episode revision and idle frame records the version it was captured under. A
change to what the system stores, for how long, or who can see it, must bump the
version, which makes every profile re-acknowledge before capture resumes.

DISCLOSURE_TEXT is the plain-language disclosure the browser shows before the
acknowledgement (served by the server, rendered verbatim by the Privacy view).
It is bounded at MAX_DISCLOSURE_CHARS and must stay truthful to the retention
constants in perception/episode_store.py; numbers here are the defaults, the
Privacy view shows the profile's current windows next to it.
"""
from __future__ import annotations

# The wording below was corrected in the Oversight pass-2 round (what expires versus
# what stays until erased) WITHOUT bumping the version: the first rig session has
# not happened, so nobody has acknowledged the earlier wording. Once a profile has
# acknowledged a version, any change to this text bumps it.
CONSENT_VERSION = "rig-2026-10"
MAX_DISCLOSURE_CHARS = 1200

DISCLOSURE_TEXT = (
    "Pam keeps camera stills on this laptop, not in the cloud. When a hand moves "
    "something, a few stills of that moment are saved with the memory. While nothing "
    "is happening, one still is taken every 30 seconds and kept for 24 hours, unless it "
    "confirms where an item still is; then it is kept with that item. Hand positions "
    "are kept for 72 hours and then reduced to a plain box around the hand. The photos "
    "and hand positions expire after the retention window, 30 days unless you change "
    "it. The written record of where an item was, any name you gave it, and its "
    "numeric appearance signature stay until you erase that item or erase everything. "
    "\"Erase this item\" and \"Erase everything\" remove memories from the app's "
    "database; traces may remain on the device or in backups, so complete removal is "
    "not guaranteed. Other household members and visitors may appear in the stills and "
    "must be told about the camera. Nothing is sent to the cloud unless you turn cloud "
    "chat on."
)

assert len(DISCLOSURE_TEXT) <= MAX_DISCLOSURE_CHARS, "disclosure text exceeds its bound"
