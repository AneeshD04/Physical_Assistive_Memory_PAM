"""The five-outcome rubric (CP5; Part 1 section 9, "Pilot criteria").

Pure functions over Answer dicts (perception.resolver) and scripted truth; no
store, no clock. Every number a summary reports is a software-correctness check
on synthetic scenarios (NO_CLAIM_SENTENCE); nothing here measures accuracy.

truth = {"item_id": str | None, "location_status_now": placed | stale | unknown,
         "location_text_now": str | None, "moved_since": bool, "medication": bool}

  item_id              the physical item the question is about (None: no such item)
  location_status_now  whether the item is at a known resting place right now
  location_text_now    that place's text (None when unknown)
  moved_since          the item has moved since the evidence the system holds for it
                       (the historical-fidelity axis: an old photo can be truthful
                       for its time and still not useful now)
  medication           the question is a medication query (its own error bound)

Outcomes (OUTCOMES):
  correct          confident, the member is the true item, the place is current
  hedged-correct   hedged, the true item, and a place that is current or truthfully
                   marked historical (or no place claimed at all)
  hedged-wrong     hedged, but a wrong item, or a stale place presented as current
  confident-wrong  confident with a wrong item or a non-current place
  abstain          abstain; clarify and group count as abstain for accuracy and as
                   asked for coverage

"Truthfully marked historical" means the answer tells the user the item is no
longer at the place it shows: the member's location is stale (a negative
re-observation, a pickup), or the basis says negative_reobservation or
picked_up. An aged hedge ("it may have moved since") and the historical-location
row ("its current location is uncertain") still point the user at the recorded
place: the caveat is not a historical marker, so once the item has moved they
are hedged-wrong (Part 1 pilot criteria: a hedge that shows the wrong place is
still a wrong answer; the canonical hedge "I saw it here at 3 pm, but someone
may have moved it since" is exactly this case).

Two axes are kept apart: current usefulness (the outcome) and historical fidelity
(``fidelity``: fidelity_ok when the answered item is the true item and the place
offered was true at the evidence time, i.e. current now or moved since). A
confident answer with a truthful old photo of a moved item is confident-wrong
for usefulness and fidelity_ok.
"""
from __future__ import annotations

OUTCOMES = ("correct", "hedged-correct", "hedged-wrong", "confident-wrong", "abstain")
ANSWERED_SHAPES = ("confident", "hedged")
ASKED_SHAPES = ("clarify", "group")
TRUTH_KEYS = ("item_id", "location_status_now", "location_text_now", "moved_since", "medication")
# The Answer's location vocabulary (perception.resolver.LOCATION_STATUSES).
TRUTH_STATUSES = ("placed", "sighted", "inferred", "stale", "unknown")
FIDELITY = ("fidelity_ok", "fidelity_wrong", "no_claim")
# Basis tokens under which a hedged answer presents its place as history (the item
# was seen gone from it, or picked up), not as where the item is now. "aged" is a
# caveat on a place still offered as the best guess, so it is not one of them.
HISTORICAL_BASIS = ("negative_reobservation", "picked_up")
NO_CLAIM_SENTENCE = "These outcomes are software-correctness checks on synthetic scenarios, not accuracy measurements."
SUMMARY_KEYS = ("asked", "answered", "clarified", "abstained", "outcomes", "correct_among_answered", "coverage", "confident_wrong_rate",
                "hedged_wrong_rate", "medication", "fidelity", "no_claim")


def _check_truth(truth) -> dict:
    if not isinstance(truth, dict) or set(truth) != set(TRUTH_KEYS):
        raise ValueError("Invalid truth record")
    item_id = truth["item_id"]
    if item_id is not None and (not isinstance(item_id, str) or not item_id):
        raise ValueError("Invalid truth item_id")
    if truth["location_status_now"] not in TRUTH_STATUSES:
        raise ValueError("Invalid truth location_status_now")
    text = truth["location_text_now"]
    if text is not None and (not isinstance(text, str) or not text.strip()):
        raise ValueError("Invalid truth location_text_now")
    if type(truth["moved_since"]) is not bool or type(truth["medication"]) is not bool:
        raise ValueError("Invalid truth flags")
    return truth


def _check_answer(answer) -> dict:
    if not isinstance(answer, dict) or answer.get("shape") not in ANSWERED_SHAPES + ASKED_SHAPES + ("abstain",):
        raise ValueError("Invalid answer")
    members = answer.get("members")
    if not isinstance(members, list):
        raise ValueError("Invalid answer members")
    return answer


def _same_place(claimed, truth_text) -> bool:
    if not isinstance(claimed, str) or not isinstance(truth_text, str):
        return False
    return " ".join(claimed.casefold().split()) == " ".join(truth_text.casefold().split())


def answered_item(answer):
    """The item id a confident or hedged answer is about (its single member), else None."""
    if answer.get("shape") not in ANSWERED_SHAPES or len(answer.get("members") or ()) != 1:
        return None
    member = answer["members"][0]
    value = member.get("item_id") if isinstance(member, dict) else None
    return value if isinstance(value, str) and value else None


def claimed_place(answer):
    """The place a confident or hedged answer offers (the member's location_text
    for a placed, stale or inferred location), or None when it offers none."""
    if answer.get("shape") not in ANSWERED_SHAPES or len(answer.get("members") or ()) != 1:
        return None
    member = answer["members"][0]
    if not isinstance(member, dict) or member.get("location_status") not in ("placed", "stale", "inferred"):
        return None
    text = member.get("location_text")
    return text if isinstance(text, str) and text.strip() else None


def marked_historical(answer) -> bool:
    """True when a hedged answer presents its place as history: the answer's (or
    its member's) location is stale, or the basis carries one of HISTORICAL_BASIS
    (negative_reobservation, picked_up). An aged hedge is not historical."""
    member = answer["members"][0] if len(answer.get("members") or ()) == 1 else {}
    if answer.get("location_status") == "stale" or (isinstance(member, dict) and member.get("location_status") == "stale"):
        return True
    basis = answer.get("basis") or ()
    return any(token in basis for token in HISTORICAL_BASIS)


def score(answer, truth) -> str:
    """One of OUTCOMES for an Answer against the scripted truth (ValueError for a
    malformed input)."""
    answer = _check_answer(answer)
    truth = _check_truth(truth)
    shape = answer["shape"]
    if shape == "abstain" or shape in ASKED_SHAPES:
        return "abstain"
    item_ok = truth["item_id"] is not None and answered_item(answer) == truth["item_id"]
    claimed = claimed_place(answer)
    current = claimed is not None and _same_place(claimed, truth["location_text_now"])
    if shape == "confident":
        return "correct" if item_ok and current else "confident-wrong"
    if not item_ok:
        return "hedged-wrong"
    if claimed is None or current:
        return "hedged-correct"
    return "hedged-correct" if marked_historical(answer) else "hedged-wrong"


def fidelity(answer, truth) -> str:
    """Historical fidelity, separate from usefulness: "no_claim" when the answer
    names no item and no place (abstain, clarify, group, or a hedge without a
    place), "fidelity_ok" when the answered item is the true item and the place it
    offers was true at the evidence time (current now, or moved since), else
    "fidelity_wrong"."""
    answer = _check_answer(answer)
    truth = _check_truth(truth)
    item = answered_item(answer)
    claimed = claimed_place(answer)
    if item is None or claimed is None:
        return "no_claim"
    if truth["item_id"] is None or item != truth["item_id"]:
        return "fidelity_wrong"
    if _same_place(claimed, truth["location_text_now"]) or truth["moved_since"]:
        return "fidelity_ok"
    return "fidelity_wrong"


def _rate(numerator, denominator):
    """An exact ratio (None over an empty denominator); display rounding is the caller's."""
    return numerator / denominator if denominator else None


def _block(records) -> dict:
    """The rubric arithmetic over a list of records (each {answer, truth, outcome}):
    asked (every query), answered (confident + hedged), clarified (clarify + group:
    asked but not answered), abstained (abstain shape), the outcome counts,
    correct_among_answered (correct + hedged-correct over answered), coverage =
    answered / asked, and the confident-wrong and hedged-wrong rates over ALL
    queries asked."""
    outcomes = {name: 0 for name in OUTCOMES}
    answered = clarified = abstained = 0
    for record in records:
        outcomes[record["outcome"]] += 1
        shape = record["answer"]["shape"]
        if shape in ANSWERED_SHAPES:
            answered += 1
        elif shape in ASKED_SHAPES:
            clarified += 1
        else:
            abstained += 1
    asked = len(records)
    right = outcomes["correct"] + outcomes["hedged-correct"]
    return {"asked": asked, "answered": answered, "clarified": clarified, "abstained": abstained, "outcomes": outcomes,
            "correct_among_answered": _rate(right, answered), "coverage": _rate(answered, asked),
            "confident_wrong_rate": _rate(outcomes["confident-wrong"], asked),
            "hedged_wrong_rate": _rate(outcomes["hedged-wrong"], asked)}


def summarize(records) -> dict:
    """The rubric summary of records = [{"answer", "truth", "outcome"?}]: counts and
    rates over all queries, the same over medication queries only, and the
    historical-fidelity vs current-usefulness split. A missing outcome is scored
    here; a present one is checked against score() (ValueError on disagreement).
    Every summary carries NO_CLAIM_SENTENCE under "no_claim"."""
    if not isinstance(records, (list, tuple)):
        raise ValueError("Invalid records")
    scored = []
    split = {"fidelity_ok": 0, "fidelity_wrong": 0, "no_claim": 0, "useful": 0, "fidelity_ok_not_useful": 0}
    for record in records:
        if not isinstance(record, dict) or "answer" not in record or "truth" not in record:
            raise ValueError("Invalid record")
        outcome = score(record["answer"], record["truth"])
        if record.get("outcome") is not None and record["outcome"] != outcome:
            raise ValueError("Record outcome disagrees with the rubric")
        scored.append({"answer": record["answer"], "truth": record["truth"], "outcome": outcome})
        axis = fidelity(record["answer"], record["truth"])
        split[axis] += 1
        useful = outcome in ("correct", "hedged-correct")
        split["useful"] += useful
        split["fidelity_ok_not_useful"] += axis == "fidelity_ok" and not useful
    summary = _block(scored)
    summary["medication"] = _block([record for record in scored if record["truth"]["medication"]])
    summary["fidelity"] = split
    summary["no_claim"] = NO_CLAIM_SENTENCE
    return summary
