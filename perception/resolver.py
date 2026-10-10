"""The answer contract (CP5; Part 1 rule 12 and section 7 "Answer (resolver)").

``resolve`` is a pure function from a question and the store's AGED projection
(what ``EpisodeStoreMixin._project`` returns: items carrying ``identity_status``,
``location_status``, ``location_text``, ``stale_reason``, ``stale_since_ms``,
``aged``, ``inference``, ``lookalikes``, ``evidence_expired``, ``reference_image``,
``observed_at_ms``) to one Answer dict. ``EpisodeStoreMixin.answer_text``
delegates to it; nothing here touches a database, a clock or a model.

The Answer has exactly these keys (ANSWER_KEYS), plus ``question``, ``options``
and ``unresolved_observation_id`` for the clarify and group shapes:

  shape              confident | hedged | abstain | group | clarify
  text               one sentence from the TEXT_* templates below
  members            the matched item DTOs (the projection entries, unchanged)
  reference_image    {frame_id, bbox}: the evidence image, or None (always None
                     for abstain, clarify and group, and when the image bytes
                     have expired)
  target_indicated   bool: the outline in the evidence image is a VERIFIED target,
                     i.e. reference_image is present AND the answered member's
                     identity is matched_trusted. A provisional or ambiguous
                     answer keeps its reference_image (the browser draws a
                     dashed "unverified" outline) with target_indicated false.
  capture_time_ms    the evidence time of the answered item; None for abstain.
                     The texts carry no time: the DTO's capture_time_ms is what
                     the UI renders as "Observed:" next to the answer
  identity_status    matched_trusted | matched_provisional | group | unknown
  location_status    placed | sighted | inferred | stale | unknown
  room               "room unknown" until room identification has a source
  index_pending      bool (a candidate is still unprocessed); carried on every shape
  basis              the BASIS tokens behind this shape, as a subsequence of BASIS
                     (its precedence order): the identity token first, the
                     cross-cutting flags (expired, index_pending, consent_pending) last

Members (and the options of a question, and the max_members cut) are ordered
newest evidence first, then item id, whatever order the projection arrived in,
so answer_text and a direct resolve() over list_items() agree.

Decision table, in precedence order (one helper per row; the tester maps one test
to each ROW_* name):

  ROW_NO_MATCH              no member matches the words          -> abstain
  ROW_GROUP                 >1 members, all mutual lookalikes     -> group
  ROW_CLARIFY               >1 members, distinct items            -> clarify
  ROW_PROVISIONAL           identity provisional                  -> hedged, no location claim;
                            a provisional sighting older than AGE_ABSTAIN_MS abstains
                            (certainty is monotone: the lowest wins) and one older
                            than AGE_STALE_MS carries the aged token too
  ROW_CONFIDENT             trusted + placed + not aged + no negative re-observation
                            + no coverage gap since the evidence -> confident
  ROW_COVERAGE_GAP          as ROW_CONFIDENT but the camera was off or interrupted
                            since the evidence (gap_since)        -> hedged
  ROW_INFERRED              location inferred from a container    -> hedged ("I think ...")
  ROW_NEGATIVE_REOBSERVATION seen gone from its recorded place    -> hedged (old place as history)
  ROW_AGED_ABSTAIN          placement older than AGE_ABSTAIN_MS   -> abstain (no members, no place)
  ROW_AGED_HEDGED           placement older than AGE_STALE_MS     -> hedged (old place as history)
  ROW_PICKED_UP             last event a pickup                   -> hedged, no current location
  ROW_HISTORICAL_LOCATION   a recorded place that is not current evidence -> hedged
  ROW_LOOKALIKES            one name matched but lookalikes exist -> hedged, no location
  ROW_SIGHTED_ONLY          trusted identity, a sighting, no place -> hedged
  evidence expired          (post-condition on every row) the same shape without an
                            image: reference_image None, target_indicated False

Truthfulness rules the templates obey: an abstention never says "the last time I
saw it" and shows no image; a hedged text never claims a sighting the store does
not have; the nearest candidate is never shown as a match.

AGE_STALE_MS and AGE_ABSTAIN_MS are the clock-only staleness windows (B-11): initial
values from the build plan, not measurements. ``policy`` may override them for a
test (``age_stale_ms``, ``age_abstain_ms``: positive ints, milliseconds) and set
``max_members`` (an int in 2..32, default 8); any other key or value is a
ValueError (never a TypeError). Everything else is fixed.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

SHAPES = ("confident", "hedged", "abstain", "group", "clarify")
IDENTITY_STATUSES = ("matched_trusted", "matched_provisional", "group", "unknown")
LOCATION_STATUSES = ("placed", "sighted", "inferred", "stale", "unknown")
# Closed basis vocabulary (the "Why this answer" list in the browser maps each token
# to plain words; see the interface notes in the CP5 report).
BASIS = ("trusted_match", "provisional_match", "placed", "sighted", "inferred", "aged", "expired",
         "negative_reobservation", "coverage_gap", "picked_up", "lookalikes", "name_ambiguous", "no_evidence",
         "index_pending", "consent_pending")
ANSWER_KEYS = ("shape", "text", "members", "reference_image", "target_indicated", "capture_time_ms",
               "identity_status", "location_status", "room", "index_pending", "basis")
CLARIFY_KEYS = ("question", "options", "unresolved_observation_id")
ROOM_UNKNOWN = "room unknown"

# Clock-only staleness (B-11, CP2). A 'placed' location ages by the evaluation clock
# alone; the stored projection never carries an evaluated age. Initial values from
# the build plan (a re-observation refreshes observed_at_ms, CP4).
AGE_STALE_MS = 24 * 3600 * 1000        # age > this: still 'placed', stale_reason "age", aged true, hedged
AGE_ABSTAIN_MS = 7 * 24 * 3600 * 1000  # age > this: location_status 'stale', location_text kept, abstain
DEFAULT_MAX_MEMBERS = 8
MAX_MEMBERS_LIMIT = 32
POLICY_KEYS = ("max_members", "age_stale_ms", "age_abstain_ms")

# Projection stale_reason values the store writes (machine tokens "age" and
# "negative_reobservation" plus the explanatory sentences for the other states).
# They are defined here so the resolver and the store agree byte for byte.
REASON_AGE = "age"
REASON_NEGATIVE_REOBSERVATION = "negative_reobservation"
REASON_PICKED_UP = "Observed pickup; resting location is unknown"
REASON_UNCERTAIN = "Episode outcome was uncertain; no resting location recorded"
REASON_SIGHTING_TRUSTED = "Only a sighting; no resting placement recorded"
REASON_SIGHTING_UNVERIFIED = "Only a sighting; placement and identity are unverified"
REASON_CLOCK = "Capture clock is implausible; location time is uncertain"

# Text templates. Every existing CP2-CP4 expectation is byte-identical to these.
TEXT_NO_MATCH = "I have no matching stored evidence."
TEXT_NO_MATCH_PENDING = "I have no matching stored evidence yet; recent events are still being processed."
TEXT_CLARIFY = "Which stored item do you mean?"
TEXT_GROUP = "I have {n} items that look alike; which one is yours?"
TEXT_CONFIDENT = "The recorded location of {name} is {location}."
TEXT_INFERRED = "I think {name} is with {container}, which I last saw at {location}."
TEXT_INFERRED_LOST = "I think {name} is with {container}, but I do not know where {container} is now."
TEXT_NEGATIVE_REOBSERVATION = ("I recorded {name} at {location} on {date}, "
                               "but it was no longer there when I looked on {since}.")
TEXT_AGED_ABSTAIN = "I have no recent evidence for {name}."
TEXT_AGED_HEDGED = "I recorded {name} at {location} on {date}, but that was more than a day ago; it may have moved since."
TEXT_PICKED_UP = "I recorded {name} being picked up on {date}, but I did not record where it was put down."
TEXT_HISTORICAL = "Earlier evidence recorded {name} at {location}; its current location is uncertain."
TEXT_LOOKALIKES = "I have evidence for {name}, but it looks like {n} other stored item{s} and I cannot tell them apart."
TEXT_PROVISIONAL = "I have a sighting that may be {name}, but I cannot confirm its identity or where it is now."
TEXT_PROVISIONAL_AGED = ("I have a sighting that may be {name}, but it was more than a day ago and "
                         "I cannot confirm its identity or where it is now.")
TEXT_COVERAGE_GAP = ("I recorded {name} at {location} on {date}, but the camera was off or interrupted "
                     "for a while since, so it may have moved.")
TEXT_SIGHTED_ONLY = "I have a sighting of {name} on {date}, but no recorded resting place for it."
QUESTION_CLARIFY = "Which stored item?"
QUESTION_GROUP = "Which one is yours?"

ROW_NO_MATCH = "ROW_NO_MATCH"
ROW_GROUP = "ROW_GROUP"
ROW_CLARIFY = "ROW_CLARIFY"
ROW_PROVISIONAL = "ROW_PROVISIONAL"
ROW_CONFIDENT = "ROW_CONFIDENT"
ROW_COVERAGE_GAP = "ROW_COVERAGE_GAP"
ROW_INFERRED = "ROW_INFERRED"
ROW_NEGATIVE_REOBSERVATION = "ROW_NEGATIVE_REOBSERVATION"
ROW_AGED_ABSTAIN = "ROW_AGED_ABSTAIN"
ROW_AGED_HEDGED = "ROW_AGED_HEDGED"
ROW_PICKED_UP = "ROW_PICKED_UP"
ROW_HISTORICAL_LOCATION = "ROW_HISTORICAL_LOCATION"
ROW_LOOKALIKES = "ROW_LOOKALIKES"
ROW_SIGHTED_ONLY = "ROW_SIGHTED_ONLY"
ROWS = (ROW_NO_MATCH, ROW_GROUP, ROW_CLARIFY, ROW_PROVISIONAL, ROW_CONFIDENT, ROW_COVERAGE_GAP, ROW_INFERRED,
        ROW_NEGATIVE_REOBSERVATION, ROW_AGED_ABSTAIN, ROW_AGED_HEDGED, ROW_PICKED_UP,
        ROW_HISTORICAL_LOCATION, ROW_LOOKALIKES, ROW_SIGHTED_ONLY)

STOP_WORDS = {"where", "is", "are", "my", "the", "a", "an", "did", "i", "leave", "find", "please", "can", "you", "me", "show"}


# --- query matching (shared with the catalogue search) -----------------------------
def query_words(query) -> set:
    """The content words of a question or an item name (casefolded, stop words out)."""
    return set(re.findall(r"[\w]+", query.casefold())) - STOP_WORDS


def matches(item, words, query) -> bool:
    """True when the item is what the words name: no words at all (catalogue
    listing), the item's own id typed verbatim, or every word in the name."""
    return not words or query.strip() == item["item_id"] or words <= query_words(item["name"])


def date_text(observed_ms) -> str:
    """UTC calendar date of an evidence time for answer text (deterministic across
    machines; the store has no user time zone)."""
    try:
        return datetime.fromtimestamp(observed_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError, TypeError):
        return "an unknown date"


# --- ageing (B-11) --------------------------------------------------------------------
def age_item(item, eval_ms, *, stale_ms=AGE_STALE_MS, abstain_ms=AGE_ABSTAIN_MS) -> dict:
    """Clock-only ageing of one projected item, evaluated at eval_ms.

    Pure and idempotent: returns a copy. Only a 'placed' location ages (a
    pickup, an uncertain outcome or a bad capture clock already says so).
    age = eval_ms - observed_at_ms; age > abstain_ms -> location_status 'stale',
    stale_reason "age", location_text kept as history; otherwise age > stale_ms
    -> still 'placed', stale_reason "age". Both set aged=True; everything else
    reads aged=False. Fields a pre-CP3/CP4 projection lacks get their defaults."""
    aged = dict(item, aged=False)
    aged.setdefault("lookalikes", [])
    aged.setdefault("inference", None)
    aged.setdefault("stale_since_ms", None)
    aged.setdefault("evidence_expired", False)
    aged.setdefault("gap_since", False)  # CP5 field; a projection stored before CP5 lacks it
    observed = item.get("observed_at_ms")
    if eval_ms is None or observed is None:
        return aged
    age = eval_ms - observed
    if item.get("location_status") == "sighted":
        # CP5 (ruling 4): a sighting ages too, but it has no place to go stale; the
        # flag is the catalogue's signal and the resolver's provisional row decides.
        aged["aged"] = age > stale_ms
        return aged
    if item.get("location_status") != "placed":
        return aged
    if age > abstain_ms:
        aged.update(location_status="stale", stale_reason=REASON_AGE, stale_since_ms=observed + abstain_ms, aged=True)
    elif age > stale_ms:
        aged.update(stale_reason=REASON_AGE, aged=True)
    return aged


def _unaged(item) -> dict:
    """The item with a clock-only age removed (so a policy override can re-age it)."""
    if item.get("stale_reason") != REASON_AGE:
        return dict(item, aged=False) if item.get("aged") else item
    return dict(item, location_status="placed", stale_reason=None, stale_since_ms=None, aged=False)


# --- validation -----------------------------------------------------------------------
def _check_policy(policy) -> dict:
    if policy is None:
        policy = {}
    if not isinstance(policy, dict) or set(policy) - set(POLICY_KEYS):
        raise ValueError("Invalid resolver policy")
    out = {"max_members": DEFAULT_MAX_MEMBERS, "age_stale_ms": None, "age_abstain_ms": None}
    for key in POLICY_KEYS:
        if key not in policy:
            continue
        value = policy[key]
        # Always ValueError, never TypeError: max_members an int in 2..MAX_MEMBERS_LIMIT
        # (a clarify or group question needs at least two candidates), the age_*
        # overrides positive ints (milliseconds).
        if isinstance(value, bool) or type(value) is not int or value < 1:
            raise ValueError("Invalid resolver policy")
        if key == "max_members" and not 2 <= value <= MAX_MEMBERS_LIMIT:
            raise ValueError("Invalid resolver policy")
        out[key] = value
    if out["age_stale_ms"] is not None and out["age_abstain_ms"] is not None and out["age_stale_ms"] > out["age_abstain_ms"]:
        raise ValueError("Invalid resolver policy")
    return out


def _check_as_of(as_of_ms) -> int:
    if isinstance(as_of_ms, bool) or type(as_of_ms) is not int or as_of_ms < 0:
        raise ValueError("as_of_ms must be nonnegative epoch milliseconds")
    return as_of_ms


# --- answer assembly ------------------------------------------------------------------
def _identity_status(item) -> str:
    return {"trusted": "matched_trusted", "provisional": "matched_provisional", "ambiguous": "group"}.get(item.get("identity_status"), "unknown")


def _location_status(item) -> str:
    status = item.get("location_status")
    return status if status in LOCATION_STATUSES else "unknown"


def _reference_image(item):
    value = item.get("reference_image")
    if item.get("evidence_expired") or not isinstance(value, dict):
        return None
    bbox = value.get("bbox")
    if not isinstance(value.get("frame_id"), str) or not isinstance(bbox, list) or len(bbox) != 4:
        return None
    return {"frame_id": value["frame_id"], "bbox": list(bbox)}


def _answer(shape, text, *, members=(), index_pending=False, basis=(), item=None, abstain_members=True):
    """One Answer dict. With an item, the evidence fields come from it; otherwise
    (abstain, clarify, group) they are null/unknown."""
    if shape not in SHAPES:
        raise ValueError("Invalid answer shape")
    reference = _reference_image(item) if item is not None and shape != "abstain" else None
    identity = _identity_status(item) if item is not None and shape != "abstain" else ("group" if shape == "group" else "unknown")
    answer = {
        "shape": shape, "text": text, "members": list(members),
        "reference_image": reference,
        # The outline is a verified target only for a trusted identity (Oversight
        # pass 2); an unverified sighting keeps its image with the flag false.
        "target_indicated": reference is not None and identity == "matched_trusted",
        "capture_time_ms": (item.get("observed_at_ms") if item is not None and shape != "abstain" else None),
        "identity_status": identity,
        "location_status": _location_status(item) if item is not None and shape != "abstain" else "unknown",
        "room": ROOM_UNKNOWN, "index_pending": bool(index_pending),
        "basis": [token for token in basis if token in BASIS],
    }
    return answer


def _with_flags(answer, *, index_pending, consent_pending, item=None):
    """Add the cross-cutting basis tokens (expired when the answered item's image
    bytes are gone; coverage_gap on a hedged answer whose evidence a gap followed;
    index_pending; consent_pending), carry index_pending on every shape, and
    order the basis as a subsequence of BASIS (its precedence order)."""
    basis = list(answer["basis"])
    if item is not None and answer["shape"] != "abstain" and item.get("evidence_expired") and "expired" not in basis:
        basis.append("expired")
    if item is not None and answer["shape"] == "hedged" and item.get("gap_since") and "coverage_gap" not in basis:
        basis.append("coverage_gap")
    if index_pending and "index_pending" not in basis:
        basis.append("index_pending")
    if consent_pending and "consent_pending" not in basis:
        basis.append("consent_pending")
    answer["basis"] = sorted(set(basis), key=BASIS.index)
    answer["index_pending"] = bool(index_pending)
    return answer


def member_order(item):
    """Members, options and the max_members cut follow this order: newest evidence
    first, then item id (the catalogue's own order), whatever order the caller
    handed the projection in."""
    return (-(item.get("observed_at_ms") or 0), str(item.get("item_id")))


def _identity_basis(item) -> list:
    status = item.get("identity_status")
    if status == "trusted":
        return ["trusted_match"]
    if status == "provisional":
        return ["provisional_match"]
    if status == "ambiguous":
        return ["lookalikes"]
    return []


# --- decision table rows (each returns an Answer or None) ------------------------------
def row_no_match(members, *, index_pending):
    """ROW_NO_MATCH: nothing matched the words. Abstain: no image, no sighting
    claimed, and no "last saw". With a candidate still pending the text says so."""
    if members:
        return None
    text = TEXT_NO_MATCH_PENDING if index_pending else TEXT_NO_MATCH
    return _answer("abstain", text, members=[], index_pending=index_pending, basis=["no_evidence"])


def row_group(members, parked):
    """ROW_GROUP: several members that are mutual lookalikes (each lists every
    other). The question is which physical one, not which name; every member keeps
    its own evidence and certainty (per-member provenance) and nobody is upgraded.
    unresolved_observation_id names the newest parked observation whose candidates
    are exactly these members (what assign_observation resolves), else null."""
    if len(members) < 2:
        return None
    ids = {x["item_id"] for x in members}
    if not all(ids - {x["item_id"]} <= set(x.get("lookalikes") or ()) for x in members):
        return None
    group = [dict(x, provenance={"observation_id": x.get("observation_id"), "identity_status": x["identity_status"]}) for x in members]
    options = [{"item_id": x["item_id"], "name": x["name"]} for x in members]
    unresolved = next((entry["observation_id"] for entry in reversed(list(parked)) if set(entry.get("candidates") or ()) == ids), None)
    answer = _answer("group", TEXT_GROUP.format(n=len(group)), members=group, basis=["lookalikes"])
    answer.update(question=QUESTION_GROUP, options=options, unresolved_observation_id=unresolved)
    return answer


def row_clarify(members):
    """ROW_CLARIFY: several distinct items match the words. Ask which."""
    if len(members) < 2:
        return None
    options = [{"item_id": x["item_id"], "name": x["name"]} for x in members]
    answer = _answer("clarify", TEXT_CLARIFY, members=members, basis=["name_ambiguous"])
    answer.update(question=QUESTION_CLARIFY, options=options)
    return answer


def row_provisional(item, members, *, as_of_ms, stale_ms=AGE_STALE_MS, abstain_ms=AGE_ABSTAIN_MS):
    """ROW_PROVISIONAL: the identity is only provisional. Hedged, and no location is
    claimed (a provisional sighting carries no recorded surface). Certainty is
    monotone (ruling 4): a provisional sighting older than abstain_ms abstains
    (basis provisional_match + aged, no image, no sighting claimed); one older than
    stale_ms is hedged with the aged token as well."""
    if item.get("identity_status") != "provisional":
        return None
    observed = item.get("observed_at_ms")
    age = as_of_ms - observed if observed is not None else None
    if age is not None and age > abstain_ms:
        return _answer("abstain", TEXT_AGED_ABSTAIN.format(name=item["name"]), members=[], basis=["provisional_match", "aged"])
    basis = ["provisional_match", "sighted"]
    text = TEXT_PROVISIONAL
    if age is not None and age > stale_ms:
        basis.append("aged")
        text = TEXT_PROVISIONAL_AGED
    if item.get("lookalikes"):
        basis.append("lookalikes")
    return _answer("hedged", text.format(name=item["name"]), members=members, basis=basis, item=item)


def row_confident(item, members):
    """ROW_CONFIDENT: identity trusted, location placed, not aged, no negative
    re-observation (the projection turns one into stale) and no coverage gap
    since the evidence (gap_since, ruling 1)."""
    if not (item.get("identity_status") == "trusted" and item.get("location_status") == "placed" and not item.get("aged")):
        return None
    if item.get("gap_since"):
        return None
    return _answer("confident", TEXT_CONFIDENT.format(name=item["name"], location=item["location_text"]),
                   members=members, basis=["trusted_match", "placed"], item=item)


def row_coverage_gap(item, members):
    """ROW_COVERAGE_GAP (ruling 1): everything ROW_CONFIDENT needs except that the
    camera was off or interrupted (a packet gap or a telemetry window with
    gap_ms > 0 on the same device) after the evidence: hedged, the recorded place
    offered with the caveat, basis trusted_match + placed + coverage_gap."""
    if not (item.get("identity_status") == "trusted" and item.get("location_status") == "placed" and not item.get("aged") and item.get("gap_since")):
        return None
    text = TEXT_COVERAGE_GAP.format(name=item["name"], location=item["location_text"], date=date_text(item.get("observed_at_ms")))
    return _answer("hedged", text, members=members, basis=["trusted_match", "placed", "coverage_gap"], item=item)


def row_inferred(item, members):
    """ROW_INFERRED (CP4 containment): never confident; the location is the
    container's, and the text says so."""
    if item.get("location_status") != "inferred" or not isinstance(item.get("inference"), dict):
        return None
    container = item["inference"].get("container_name") or "another stored item"
    if item.get("location_text"):
        text = TEXT_INFERRED.format(name=item["name"], container=container, location=item["location_text"])
    else:
        text = TEXT_INFERRED_LOST.format(name=item["name"], container=container)
    return _answer("hedged", text, members=members, basis=_identity_basis(item) + ["inferred"], item=item)


def row_negative_reobservation(item, members):
    """ROW_NEGATIVE_REOBSERVATION (rule 13): the place is known, the item was seen
    to be gone from it; the old place is given as history, never as current."""
    if item.get("stale_reason") != REASON_NEGATIVE_REOBSERVATION or not item.get("location_text"):
        return None
    text = TEXT_NEGATIVE_REOBSERVATION.format(name=item["name"], location=item["location_text"],
                                              date=date_text(item.get("observed_at_ms")), since=date_text(item.get("stale_since_ms")))
    return _answer("hedged", text, members=members, basis=_identity_basis(item) + ["placed", "negative_reobservation"], item=item)


def row_aged_abstain(item):
    """ROW_AGED_ABSTAIN: the placement is older than AGE_ABSTAIN_MS; the historical
    place is not usable evidence, so the answer abstains without members, image or
    the stale place."""
    if item.get("stale_reason") != REASON_AGE or not item.get("location_text") or item.get("location_status") != "stale":
        return None
    return _answer("abstain", TEXT_AGED_ABSTAIN.format(name=item["name"]), members=[], basis=_identity_basis(item) + ["aged"])


def row_aged_hedged(item, members):
    """ROW_AGED_HEDGED: the placement is between AGE_STALE_MS and AGE_ABSTAIN_MS old:
    hedged with its observed date, and the place marked as possibly moved."""
    if item.get("stale_reason") != REASON_AGE or not item.get("location_text"):
        return None
    text = TEXT_AGED_HEDGED.format(name=item["name"], location=item["location_text"], date=date_text(item.get("observed_at_ms")))
    return _answer("hedged", text, members=members, basis=_identity_basis(item) + ["placed", "aged"], item=item)


def row_picked_up(item, members):
    """ROW_PICKED_UP: the last event was a pickup (stale by pickup): hedged with no
    current location."""
    if item.get("stale_reason") != REASON_PICKED_UP or item.get("location_text"):
        return None
    text = TEXT_PICKED_UP.format(name=item["name"], date=date_text(item.get("observed_at_ms")))
    return _answer("hedged", text, members=members, basis=_identity_basis(item) + ["picked_up"], item=item)


def row_historical_location(item, members):
    """ROW_HISTORICAL_LOCATION: a recorded place survives (an ambiguous identity
    with a placement, or a placement under an implausible capture clock) but is not
    current evidence: hedged, the place as earlier evidence."""
    if not item.get("location_text"):
        return None
    basis = _identity_basis(item) + (["placed"] if item.get("location_status") == "placed" else [])
    return _answer("hedged", TEXT_HISTORICAL.format(name=item["name"], location=item["location_text"]), members=members, basis=basis, item=item)


def row_lookalikes(item, members):
    """ROW_LOOKALIKES: one name matched, but the item has lookalikes that did not;
    the identity is not separable, so the answer hedges without a location."""
    if not item.get("lookalikes"):
        return None
    count = len(item["lookalikes"])
    text = TEXT_LOOKALIKES.format(name=item["name"], n=count, s="s" if count != 1 else "")
    return _answer("hedged", text, members=members, basis=["lookalikes"], item=item)


def row_sighted_only(item, members):
    """ROW_SIGHTED_ONLY: a trusted identity with a sighting (or an uncertain
    outcome) and no recorded resting place: hedged, no location claimed."""
    text = TEXT_SIGHTED_ONLY.format(name=item["name"], date=date_text(item.get("observed_at_ms")))
    return _answer("hedged", text, members=members, basis=_identity_basis(item) + ["sighted"], item=item)


def resolve(query, items, *, as_of_ms, index_pending, policy=None, parked=(), consent_pending=False) -> dict:
    """The Answer for `query` over the aged projection `items` evaluated at
    as_of_ms (epoch ms). index_pending: a candidate is still unprocessed.

    Optional: `parked` is the store's list of unattributed (B-14) observations
    ({observation_id, observed_at_ms, candidates}) used only to name
    unresolved_observation_id on a group; `consent_pending` appends the
    consent_pending basis token. Both default to "none". ValueError for a bad
    query, as_of_ms or policy."""
    if not isinstance(query, str) or not 1 <= len(query.strip()) <= 2000:
        raise ValueError("Invalid question")
    eval_ms = _check_as_of(as_of_ms)
    rules = _check_policy(policy)
    if not isinstance(items, (list, tuple)):
        raise ValueError("Invalid projection")
    words = query_words(query)
    members = [dict(item, index_pending=bool(index_pending)) for item in items if isinstance(item, dict) and matches(item, words, query)] if words else []
    members.sort(key=member_order)
    stale = AGE_STALE_MS if rules["age_stale_ms"] is None else rules["age_stale_ms"]
    abstain = AGE_ABSTAIN_MS if rules["age_abstain_ms"] is None else rules["age_abstain_ms"]
    if rules["age_stale_ms"] is not None or rules["age_abstain_ms"] is not None:
        members = [age_item(_unaged(item), eval_ms, stale_ms=stale, abstain_ms=abstain) for item in members]
    answer = row_no_match(members, index_pending=index_pending)
    if answer is not None:
        return _with_flags(answer, index_pending=index_pending, consent_pending=consent_pending)
    if len(members) > 1:
        members = members[:rules["max_members"]]
        answer = row_group(members, parked) or row_clarify(members)
        return _with_flags(answer, index_pending=index_pending, consent_pending=consent_pending)
    item = members[0]
    answer = (row_provisional(item, members, as_of_ms=eval_ms, stale_ms=stale, abstain_ms=abstain)
              or row_confident(item, members) or row_coverage_gap(item, members) or row_inferred(item, members)
              or row_negative_reobservation(item, members) or row_aged_abstain(item) or row_aged_hedged(item, members)
              or row_picked_up(item, members) or row_historical_location(item, members)
              or row_lookalikes(item, members) or row_sighted_only(item, members))
    return _with_flags(answer, index_pending=index_pending, consent_pending=consent_pending, item=item)
