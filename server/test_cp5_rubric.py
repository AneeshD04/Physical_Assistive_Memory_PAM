"""CP5 acceptance: the five-outcome rubric (Part 1 section 9 / pilot criteria).

    python3 -B server/test_cp5_rubric.py -v

Authority: docs/BUILD_PLAN.md "CP5 in detail", *Rubric (A)*: perception.rubric.score(answer,
truth) -> one of correct | hedged-correct | hedged-wrong | confident-wrong | abstain, with
truth {item_id|None, location_status_now, location_text_now, moved_since, medication};
clarify and group score as abstain for accuracy and as asked for coverage; summarize(records)
reports accuracy among answered, coverage (answered / asked), the confident-wrong rate over
all queries, the same three over medication queries only, and the historical-fidelity vs
current-usefulness split (a confident answer with a truthful old photo of a moved item is
confident-wrong for usefulness and fidelity ok); the summary carries NO_CLAIM_SENTENCE.
Pure: no store, no clock. Answers here are built to the contract shape by
test_cp5_fixtures.answer; nothing is measured.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
import test_cp5_fixtures as cp5  # noqa: E402
from test_cp5_fixtures import ANCHOR_MS, HOUR_MS, OUTCOMES, answer, find_value, inferred_item, item, leaf_numbers, lookalike_pair, rubric_record, truth  # noqa: E402

TABLE, SHELF, DRAWER = "fixture cp5 table", "fixture cp5 shelf", "fixture cp5 drawer"
ACCURACY_CLAIM = re.compile(r"accuracy of (the )?(system|pam|model|answers?|resolver)|is \d+% accurate|measured accuracy", re.IGNORECASE)


def rubric():
    from perception import rubric as module
    return module


def score(answer_value, truth_value):
    return rubric().score(answer_value, truth_value)


def fidelity_ok(answer_value, truth_value):
    """Historical fidelity of one answer (was this truly the item at that time):
    the plan names the split but not the function; try the natural spellings, then
    the summary of a single record. Adapter: the one place to touch if Builder A's
    spelling differs."""
    module = rubric()
    for name in ("fidelity_ok", "fidelity", "score_fidelity", "historical_fidelity"):
        function = getattr(module, name, None)
        if callable(function):
            value = function(answer_value, truth_value)
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value in ("correct", "hedged-correct", "ok", "fidelity_ok")
    summary = module.summarize([rubric_record(answer_value, truth_value)])
    value = find_value(summary, r"fidelity")
    if value is None:
        raise AssertionError("perception.rubric exposes neither a fidelity function nor a fidelity entry in summarize()")
    leaves = leaf_numbers(value)
    return any(leaf in (1, 1.0) for leaf in leaves)


# --- answers of every shape, over one true item ---------------------------------------------
def fresh(serial=1, name="synthetic cp5 block", location=TABLE):
    return item(serial, name=name, location_text=location)


def confident(member):
    return answer("confident", [member])


def hedged(member, basis):
    return answer("hedged", [member], basis=basis)


class ScoreTests(unittest.TestCase):
    def test_outcome_vocabulary_is_the_plan_s_five(self):
        module = rubric()
        exposed = getattr(module, "OUTCOMES", None)
        self.assertIsNotNone(exposed, "perception.rubric.OUTCOMES names the five outcomes")
        self.assertEqual(set(exposed), set(OUTCOMES))
        self.assertIsInstance(module.NO_CLAIM_SENTENCE, str)
        lowered = module.NO_CLAIM_SENTENCE.lower()
        self.assertIn("software-correctness", lowered)
        self.assertIn("synthetic", lowered)
        self.assertIn("accuracy", lowered)
        self.assertRegex(lowered, r"never|not")

    def test_correct_is_confident_true_item_current_place(self):
        block = fresh()
        self.assertEqual(score(confident(block), truth(block["item_id"], location_text_now=TABLE)), "correct")
        self.assertEqual(score(confident(block), truth(block["item_id"], location_text_now=TABLE, medication=True)), "correct", "the medication flag never changes the outcome")

    def test_confident_wrong_for_a_wrong_item_or_a_non_current_place(self):
        block = fresh()
        self.assertEqual(score(confident(block), truth("cp5-item-099", location_text_now=TABLE)), "confident-wrong")
        self.assertEqual(score(confident(block), truth(None, location_status_now="unknown", location_text_now=None)), "confident-wrong", "a confident answer about an item that does not exist")
        moved = truth(block["item_id"], location_text_now=DRAWER, moved_since=True)
        self.assertEqual(score(confident(block), moved), "confident-wrong", "a truthful old photo of a moved item is still wrong for usefulness")
        self.assertEqual(score(confident(block), truth(block["item_id"], location_text_now=DRAWER, moved_since=True, medication=True)), "confident-wrong")

    def test_fidelity_split_on_a_truthful_old_photo(self):
        block = fresh()
        moved = truth(block["item_id"], location_text_now=DRAWER, moved_since=True)
        self.assertEqual(score(confident(block), moved), "confident-wrong")
        self.assertIs(fidelity_ok(confident(block), moved), True, "the photo truly showed the item at that time")
        wrong_item = truth("cp5-item-099", location_text_now=TABLE)
        self.assertIs(fidelity_ok(confident(block), wrong_item), False, "a wrong item is wrong on both axes")
        self.assertIs(fidelity_ok(confident(block), truth(block["item_id"], location_text_now=TABLE)), True)

    def test_hedged_correct_for_the_true_item_with_a_current_or_historical_place(self):
        aged = item(1, aged=True, stale_reason="age", observed_at_ms=ANCHOR_MS - 25 * HOUR_MS)
        self.assertEqual(score(hedged(aged, ["trusted_match", "placed", "aged"]), truth(aged["item_id"], location_text_now=TABLE)), "hedged-correct")
        gone = item(2, location_status="stale", stale_reason="negative_reobservation", stale_since_ms=ANCHOR_MS + 60000)
        historical = truth(gone["item_id"], location_text_now=DRAWER, moved_since=True)
        self.assertEqual(score(hedged(gone, ["trusted_match", "placed", "negative_reobservation"]), historical), "hedged-correct",
                         "the old place is truthfully marked historical")
        keys = inferred_item(3, "cp5-item-004", name="synthetic cp5 keys", container_name="synthetic cp5 basket", since_ms=ANCHOR_MS, location_text=SHELF)
        self.assertEqual(score(hedged(keys, ["trusted_match", "inferred"]), truth(keys["item_id"], location_status_now="placed", location_text_now=SHELF)), "hedged-correct")
        picked = item(5, location_status="stale", location_text=None, stale_reason=cp5.CP2_PICKUP_REASON)
        self.assertEqual(score(hedged(picked, ["trusted_match", "picked_up"]), truth(picked["item_id"], location_status_now="unknown", location_text_now=None, moved_since=True)),
                         "hedged-correct", "a hedge that claims no place cannot be wrong about the place")
        inferred_stale = inferred_item(6, "cp5-item-004", name="synthetic cp5 keys", container_name="synthetic cp5 basket", since_ms=ANCHOR_MS, location_text=None)
        self.assertEqual(score(hedged(inferred_stale, ["trusted_match", "inferred"]), truth(inferred_stale["item_id"], location_status_now="unknown", location_text_now=None, moved_since=True)),
                         "hedged-correct", "an inference without a place claims nothing about where it is now")

    def test_hedged_wrong_for_a_wrong_item_or_a_stale_place_presented_as_current(self):
        aged = item(1, aged=True, stale_reason="age", observed_at_ms=ANCHOR_MS - 25 * HOUR_MS)
        self.assertEqual(score(hedged(aged, ["trusted_match", "placed", "aged"]), truth("cp5-item-099", location_text_now=TABLE)), "hedged-wrong")
        # Part 1 pilot criteria: "a hedge that shows the wrong place is still a wrong
        # answer". An aged hedge still points at its recorded place (location_status
        # 'placed'; "it may have moved since" is a caveat, not a historical marker), so
        # once the item has moved it is hedged-wrong; so is the historical-location row
        # for an item that became ambiguous after its placement. A negative
        # re-observation or a pickup (location stale) is the truthful historical marker.
        presented_as_current = truth(aged["item_id"], location_text_now=DRAWER, moved_since=True)
        self.assertEqual(score(hedged(aged, ["trusted_match", "placed", "aged"]), presented_as_current), "hedged-wrong")
        ambiguous = item(4, identity_status="ambiguous", lookalikes=["cp5-item-009"])
        self.assertEqual(score(hedged(ambiguous, ["lookalikes", "placed"]), truth(ambiguous["item_id"], location_text_now=DRAWER, moved_since=True)), "hedged-wrong")
        self.assertEqual(score(hedged(ambiguous, ["lookalikes", "placed"]), truth(ambiguous["item_id"], location_text_now=TABLE)), "hedged-correct")
        provisional = item(2, identity_status="provisional", location_status="sighted", location_text=None)
        self.assertEqual(score(hedged(provisional, ["provisional_match", "sighted"]), truth("cp5-item-099", location_text_now=TABLE)), "hedged-wrong")
        keys = inferred_item(3, "cp5-item-004", name="synthetic cp5 keys", container_name="synthetic cp5 basket", since_ms=ANCHOR_MS, location_text=SHELF)
        self.assertEqual(score(hedged(keys, ["trusted_match", "inferred"]), truth("cp5-item-099", location_status_now="placed", location_text_now=SHELF)), "hedged-wrong")

    def test_abstain_clarify_and_group_score_as_abstain(self):
        block = fresh()
        self.assertEqual(score(answer("abstain"), truth(block["item_id"], location_text_now=TABLE)), "abstain")
        self.assertEqual(score(answer("abstain"), truth(None, location_status_now="unknown", location_text_now=None)), "abstain")
        spare = fresh(2, name="synthetic cp5 block spare", location=SHELF)
        self.assertEqual(score(answer("clarify", [block, spare]), truth(block["item_id"], location_text_now=TABLE)), "abstain", "clarify counts as abstain for accuracy")
        a, b = lookalike_pair()
        self.assertEqual(score(answer("group", [a, b]), truth(a["item_id"], location_text_now="fixture shelf left")), "abstain", "group counts as abstain for accuracy")

    def test_invalid_answers_and_truths_are_refused(self):
        block = fresh()
        good = truth(block["item_id"], location_text_now=TABLE)
        for bad_answer in ({}, dict(confident(block), shape="certain"), "confident", None):
            with self.subTest(answer=bad_answer), self.assertRaises((ValueError, TypeError, KeyError)):
                score(bad_answer, good)
        for bad_truth in ({}, {k: v for k, v in good.items() if k != "moved_since"}, dict(good, moved_since="no"), dict(good, extra=1), None):
            with self.subTest(truth=bad_truth), self.assertRaises((ValueError, TypeError, KeyError)):
                score(confident(block), bad_truth)


# --- summarize --------------------------------------------------------------------------------
def sample_records():
    """Ten records: 4 correct, 2 hedged-correct, 1 hedged-wrong, 1 confident-wrong (a
    truthful old photo), 1 abstain, 1 group. Four of them are medication queries:
    2 correct, 1 confident-wrong, 1 abstain."""
    block = fresh()
    aged = item(2, aged=True, stale_reason="age", observed_at_ms=ANCHOR_MS - 25 * HOUR_MS)
    gone = item(3, location_status="stale", stale_reason="negative_reobservation", stale_since_ms=ANCHOR_MS + 60000)
    pills = fresh(4, name="synthetic cp5 pills", location=SHELF)
    muddled = item(7, identity_status="ambiguous", lookalikes=["cp5-item-008"])
    a, b = lookalike_pair(5, 6)
    records = [
        rubric_record(confident(block), truth(block["item_id"], location_text_now=TABLE), query="q1"),
        rubric_record(confident(block), truth(block["item_id"], location_text_now=TABLE), query="q2"),
        rubric_record(confident(pills), truth(pills["item_id"], location_text_now=SHELF, medication=True), query="q3 medication"),
        rubric_record(confident(pills), truth(pills["item_id"], location_text_now=SHELF, medication=True), query="q4 medication"),
        rubric_record(hedged(aged, ["trusted_match", "placed", "aged"]), truth(aged["item_id"], location_text_now=TABLE), query="q5"),
        rubric_record(hedged(gone, ["trusted_match", "placed", "negative_reobservation"]), truth(gone["item_id"], location_text_now=DRAWER, moved_since=True), query="q6"),
        rubric_record(hedged(muddled, ["lookalikes", "placed"]), truth(muddled["item_id"], location_text_now=DRAWER, moved_since=True), query="q7"),
        rubric_record(confident(pills), truth(pills["item_id"], location_text_now=DRAWER, moved_since=True, medication=True), query="q8 medication"),
        rubric_record(answer("abstain"), truth(block["item_id"], location_text_now=TABLE, medication=True), query="q9 medication"),
        rubric_record(answer("group", [a, b]), truth(a["item_id"], location_text_now="fixture shelf left"), query="q10"),
    ]
    expected = ["correct", "correct", "correct", "correct", "hedged-correct", "hedged-correct", "hedged-wrong", "confident-wrong", "abstain", "abstain"]
    return records, expected


class SummarizeTests(unittest.TestCase):
    def assert_rate(self, summary, pattern, expected, *, within=None, what):
        value = find_value(summary, pattern, within=within)
        self.assertIsNotNone(value, f"summary has no entry matching {pattern!r}{' under ' + within if within else ''}: {json.dumps(summary, default=str)[:600]}")
        self.assertIsInstance(value, (int, float), f"{what}: {value!r}")
        self.assertAlmostEqual(float(value), expected, delta=0.00051, msg=f"{what} should be {expected} (rates may be rounded to four decimals): {value}")

    def test_arithmetic_over_all_and_medication_queries(self):
        records, expected = sample_records()
        self.assertEqual([r["outcome"] for r in records], expected)
        summary = rubric().summarize(records)
        self.assertIsInstance(summary, dict)
        # All queries: asked 10, answered 8 (confident + hedged), accurate 6 of 8.
        self.assert_rate(summary, r"^correct_among_answered$", 6 / 8, what="correct_among_answered")
        self.assert_rate(summary, r"^coverage", 8 / 10, what="coverage (answered / asked)")
        self.assert_rate(summary, r"confident.?wrong", 1 / 10, what="confident-wrong rate over all queries")
        # Medication queries only: asked 4, answered 3, accurate 2 of 3, confident-wrong 1 of 4.
        self.assert_rate(summary, r"^correct_among_answered$", 2 / 3, within=r"medication", what="medication correct_among_answered")
        self.assert_rate(summary, r"^coverage", 3 / 4, within=r"medication", what="medication coverage")
        self.assert_rate(summary, r"confident.?wrong", 1 / 4, within=r"medication", what="medication confident-wrong rate")
        # Counts, when the summary carries them: 10 queries, 8 answered, 1 asked back
        # (the group), 1 abstained. "asked" in the plan's "coverage = answered / asked"
        # is the denominator of every query; a summary may also count the questions
        # asked back (clarify/group) under that word, so only the total is pinned.
        total = find_value(summary, r"^(queries|total|n_queries)$")
        answered = find_value(summary, r"^answered$")
        if total is not None:
            self.assertEqual(total, 10)
        if answered is not None:
            self.assertEqual(answered, 8)
        self.assertNotIn("I have", json.dumps(summary), "the summary carries numbers and the no-claim sentence, not answer texts")

    def test_fidelity_versus_usefulness_split(self):
        # Every answered record here is historically faithful; one is a truthful old
        # photo of a moved item, so usefulness accuracy is 4/5 while fidelity is 5/5.
        block = fresh()
        records = [rubric_record(confident(block), truth(block["item_id"], location_text_now=TABLE), query=f"q{n}") for n in range(4)]
        records.append(rubric_record(confident(block), truth(block["item_id"], location_text_now=DRAWER, moved_since=True), query="q4 old photo"))
        records.append(rubric_record(answer("abstain"), truth(block["item_id"], location_text_now=TABLE), query="q5"))
        self.assertEqual([r["outcome"] for r in records], ["correct"] * 4 + ["confident-wrong", "abstain"])
        summary = rubric().summarize(records)
        self.assert_rate(summary, r"^correct_among_answered$", 4 / 5, what="usefulness: correct_among_answered")
        self.assert_rate(summary, r"confident.?wrong", 1 / 6, what="confident-wrong rate")
        fidelity = find_value(summary, r"fidelity")
        self.assertIsNotNone(fidelity, f"summary reports the fidelity axis: {json.dumps(summary, default=str)[:600]}")
        leaves = leaf_numbers(fidelity)
        self.assertTrue(leaves, f"fidelity entry carries a number: {fidelity!r}")
        self.assertTrue(any(leaf in (1.0, 5) for leaf in leaves), f"fidelity among the 5 answered records is 5/5 (1.0 or 5): {fidelity!r}")
        # Two wrong items are wrong on both axes: fidelity drops to 5 of 7.
        records.append(rubric_record(confident(block), truth("cp5-item-099", location_text_now=TABLE), query="q6 wrong item"))
        records.append(rubric_record(confident(block), truth("cp5-item-098", location_text_now=TABLE), query="q7 wrong item"))
        worse = find_value(rubric().summarize(records), r"fidelity")
        ok_count = find_value(worse, r"fidelity_ok$|^ok$") if isinstance(worse, dict) else None
        wrong_count = find_value(worse, r"fidelity_wrong$|^wrong$") if isinstance(worse, dict) else None
        if ok_count is not None:
            self.assertEqual(ok_count, 5, worse)
            self.assertEqual(wrong_count, 2, worse)
        else:
            self.assertTrue(any(abs(leaf - 5 / 7) < 1e-3 for leaf in leaf_numbers(worse)), f"fidelity among the 7 answered records is 5/7: {worse!r}")

    def test_summary_carries_the_no_claim_sentence_and_no_accuracy_claim(self):
        records, _ = sample_records()
        module = rubric()
        for value in (module.summarize(records), module.summarize([])):
            rendered = json.dumps(value, default=str)
            self.assertIn(module.NO_CLAIM_SENTENCE, rendered, "the summary prints the no-accuracy-claim sentence")
            stripped = rendered.replace(module.NO_CLAIM_SENTENCE, "")
            self.assertIsNone(ACCURACY_CLAIM.search(stripped), f"the summary must not read as an accuracy claim: {stripped[:400]}")
            # Coordinator ruling 1: the metric is correct_among_answered; the word
            # "accuracy" never appears outside the no-claim sentence.
            self.assertNotIn("accuracy", stripped.lower(), stripped[:400])
        full = module.summarize(records)
        self.assertIn("correct_among_answered", full, "the top-level metric is correct_among_answered")
        self.assertIsNotNone(find_value(full, r"^correct_among_answered$", within=r"medication"), "and so is the medication block's")
        empty = module.summarize([])
        self.assertIsInstance(empty, dict)
        for number in leaf_numbers(empty):
            self.assertGreaterEqual(number, 0, f"an empty run reports zeros, never a division error or a negative: {number}")

    def test_records_are_scored_chronologically_and_counts_are_integers(self):
        records, expected = sample_records()
        summary = rubric().summarize(records)
        for number in leaf_numbers(summary):
            self.assertGreaterEqual(number, 0)
        # Reversing the records changes no rate: every record is scored on its own.
        reversed_summary = rubric().summarize(list(reversed(records)))
        self.assertEqual(sorted(leaf_numbers(summary)), sorted(leaf_numbers(reversed_summary)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
