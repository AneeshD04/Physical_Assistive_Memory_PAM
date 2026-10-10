"""CP5 acceptance: the resolver (the answer contract, Part 1 rule 12 and section 7).

    python3 -B server/test_cp5_resolver.py -v

Authority: docs/BUILD_PLAN.md "CP5 in detail", *Resolver (A)*: a pure function
perception.resolver.resolve(query, items, *, as_of_ms, index_pending, policy=None)
over the aged projection, returning an Answer dict with exactly the contract's keys
and vocabularies; answer_text delegates to it. One test per decision-table row, in
the plan's precedence order, each driven BOTH directly (hand-built projection items,
test_cp5_fixtures.item) and through the real store (the CP4 fixture states), plus the
B-14 per-member precedence fixtures, the key set and vocabularies, the basis order
and the answer_text parity sample. Nothing here measures recognition: every item is
a synthetic placement on the CP4 scene.
"""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
import test_cp3_identity as identity  # noqa: E402
import test_cp4_fixtures as fx  # noqa: E402
import test_cp5_fixtures as cp5  # noqa: E402
from test_cp5_fixtures import (ANCHOR_MS, BASIS_VOCABULARY, DAY_MS, HOUR_MS, ROOM_UNKNOWN, check_answer, inferred_item,  # noqa: E402
                               item, lookalike_pair, resolve, strip_internal)

NOW_MS = ANCHOR_MS + 100 * 1000              # the fixture clock: 100 s after the anchor
ASK = "where is my synthetic cp5 block"
ASK_KEYS = "where are my synthetic cp5 keys"
BLOCK = "synthetic cp5 block"


class ResolverRowTests(unittest.TestCase):
    """The decision table, one row per test, on hand-built projection items."""
    def resolve(self, query, items, **kwargs):
        kwargs.setdefault("as_of_ms", NOW_MS)
        return resolve(query, items, **kwargs)

    # row 1: no matching member -> abstain (no "last saw", no image)
    def test_row_no_match_abstains_without_image_or_sighting_claim(self):
        items = [item(1), item(2, name="synthetic cp5 cup")]
        answer = check_answer(self, self.resolve("where is my unseen thing", items), shape="abstain")
        self.assertEqual(answer["basis"], ["no_evidence"])
        self.assertEqual(answer["location_status"], "unknown")
        self.assertEqual(answer["capture_time_ms"], None)
        self.assertNotIn("fixture cp5 table", answer["text"], "an abstention names no stored place")
        # The catalogue listing question (no content words) is not a match either.
        self.assertEqual(check_answer(self, self.resolve("where is my", items), shape="abstain")["members"], [])
        # An empty projection abstains too.
        self.assertEqual(check_answer(self, self.resolve(ASK, []), shape="abstain")["basis"], ["no_evidence"])

    # row 2: several distinct items match the words -> clarify
    def test_row_clarify_for_distinct_items_sharing_the_words(self):
        items = [item(1, location_text="fixture cp5 table"), item(2, name="synthetic cp5 block spare", location_text="fixture cp5 desk")]
        answer = check_answer(self, self.resolve(ASK, items), shape="clarify", members=["cp5-item-001", "cp5-item-002"])
        self.assertEqual(answer["basis"], ["name_ambiguous"])
        self.assertEqual(answer["identity_status"], "unknown")
        self.assertEqual(answer["location_status"], "unknown")
        self.assertIsNone(answer["reference_image"], "a question shows no single item's photo as the answer")
        self.assertIs(answer["target_indicated"], False)
        self.assertEqual(answer["options"], [{"item_id": "cp5-item-001", "name": BLOCK}, {"item_id": "cp5-item-002", "name": "synthetic cp5 block spare"}])
        # The members are the projection entries themselves (nothing upgraded or dropped).
        for member, original in zip(answer["members"], items):
            for key in ("identity_status", "location_status", "location_text", "reference_image", "observed_at_ms"):
                self.assertEqual(member[key], original[key], key)
        # Asking for one of them by its exact id is not a clarify.
        single = check_answer(self, self.resolve("cp5-item-002", items), members=["cp5-item-002"])
        self.assertNotEqual(single["shape"], "clarify")

    # row 3: members are mutual lookalikes -> group (no upgrade, per-member provenance)
    def test_row_group_for_mutual_lookalikes_keeps_every_member_as_it_is(self):
        a, b = lookalike_pair()
        answer = check_answer(self, self.resolve(identity.ASK_GLASSES, [a, b]), shape="group", members=[a["item_id"], b["item_id"]])
        self.assertEqual(answer["text"], identity.GROUP_TEXT.format(n=2))
        self.assertEqual(answer["basis"], ["lookalikes"])
        self.assertEqual(answer["question"], "Which one is yours?")
        self.assertEqual(answer["identity_status"], "group")
        self.assertEqual(answer["location_status"], "unknown")
        self.assertIsNone(answer["reference_image"], "a group shows no single member's photo as the answer (rule 12)")
        self.assertIs(answer["target_indicated"], False)
        for member, original in zip(answer["members"], (a, b)):
            self.assertEqual(member["identity_status"], "ambiguous", "a group never upgrades a member (B-14)")
            self.assertEqual(member["provenance"], {"observation_id": original["observation_id"], "identity_status": "ambiguous"})
            self.assertEqual(member["location_text"], original["location_text"], "each member keeps its own place")
            self.assertEqual(member["reference_image"], original["reference_image"], "each member keeps its own photo")
        self.assertIn("unresolved_observation_id", answer)
        # Three mutual lookalikes are still one group; a distinct third item breaks mutuality.
        c = item(3, name=identity.GLASSES, identity_status="ambiguous", location_text="fixture shelf back")
        c["lookalikes"] = [a["item_id"], b["item_id"]]
        a3, b3 = copy.deepcopy(a), copy.deepcopy(b)
        a3["lookalikes"], b3["lookalikes"] = [b["item_id"], c["item_id"]], [a["item_id"], c["item_id"]]
        self.assertEqual(check_answer(self, self.resolve(identity.ASK_GLASSES, [a3, b3, c]), shape="group")["text"], identity.GROUP_TEXT.format(n=3))
        distinct = item(4, name=identity.GLASSES, location_text="fixture shelf front")
        mixed = check_answer(self, self.resolve(identity.ASK_GLASSES, [a, b, distinct]), shape="clarify")
        self.assertEqual(len(mixed["members"]), 3)

    # row 4: single member, identity provisional -> hedged ("may be {name}")
    def test_row_provisional_identity_hedges_without_a_location_claim(self):
        pebble = item(1, name="synthetic cp5 pebble", identity_status="provisional", location_status="sighted", location_text=None,
                      stale_reason="Only a sighting; placement and identity are unverified")
        answer = check_answer(self, self.resolve("where is my synthetic cp5 pebble", [pebble]), shape="hedged", members=[pebble["item_id"]])
        self.assertEqual(answer["identity_status"], "matched_provisional")
        self.assertEqual(answer["location_status"], "sighted")
        self.assertEqual(answer["basis"][:2], ["provisional_match", "sighted"])
        self.assertIn("may be synthetic cp5 pebble", answer["text"])
        self.assertNotIn("recorded location", answer["text"].lower())
        self.assertEqual(answer["reference_image"], pebble["reference_image"], "a provisional sighting still has its photo")
        self.assertIs(answer["target_indicated"], False, "pin c: the photo is shown, the target is not indicated as verified")
        self.assertEqual(answer["capture_time_ms"], pebble["observed_at_ms"])
        # Provisional beats every later row: a provisional item with a recorded place is still hedged by this row.
        placed = item(2, name="synthetic cp5 pebble", identity_status="provisional", location_status="placed")
        self.assertEqual(check_answer(self, self.resolve("where is my synthetic cp5 pebble", [placed]), shape="hedged")["basis"][0], "provisional_match")
        # Coordinator ruling 3 (monotone certainty): a provisional sighting between 24 h
        # and 7 d old is hedged with both tokens; over 7 d it abstains.
        day_old = dict(pebble, observed_at_ms=NOW_MS - 25 * HOUR_MS)
        aged = check_answer(self, self.resolve("where is my synthetic cp5 pebble", [day_old]), shape="hedged")
        self.assertEqual(aged["basis"][:3], ["provisional_match", "sighted", "aged"])
        self.assertEqual(aged["identity_status"], "matched_provisional")
        week_old = dict(pebble, observed_at_ms=NOW_MS - 8 * DAY_MS)
        gone = check_answer(self, self.resolve("where is my synthetic cp5 pebble", [week_old]), shape="abstain")
        self.assertEqual(gone["basis"], ["provisional_match", "aged"])
        self.assertIsNone(gone["reference_image"])
        boundary = dict(pebble, observed_at_ms=NOW_MS - DAY_MS)
        self.assertNotIn("aged", self.resolve("where is my synthetic cp5 pebble", [boundary])["basis"], "exactly 24 h is not aged")

    # row 5: trusted + placed + not aged + no negative re-observation -> confident
    def test_row_confident_for_a_fresh_trusted_placement(self):
        block = item(1)
        answer = check_answer(self, self.resolve(ASK, [block]), shape="confident", members=[block["item_id"]])
        self.assertEqual(answer["basis"], ["trusted_match", "placed"])
        self.assertEqual(answer["identity_status"], "matched_trusted")
        self.assertEqual(answer["location_status"], "placed")
        self.assertEqual(answer["reference_image"], block["reference_image"])
        self.assertIs(answer["target_indicated"], True, "a trusted placement supports the target outline")
        self.assertEqual(answer["capture_time_ms"], block["observed_at_ms"])
        self.assertEqual(answer["room"], ROOM_UNKNOWN)
        self.assertIn(BLOCK, answer["text"])
        self.assertIn("fixture cp5 table", answer["text"])
        self.assertEqual(strip_internal(answer["members"][0]), dict(strip_internal(block), index_pending=False), "the member is the projection entry")
        # Exactly 24 h old is not aged (the projection decides; the resolver trusts the aged flag).
        boundary = item(2, observed_at_ms=NOW_MS - DAY_MS)
        self.assertEqual(self.resolve(ASK, [boundary])["shape"], "confident")

    # row 5b (coordinator ruling 2): trusted + placed + not aged + a coverage gap since -> hedged
    def test_row_coverage_gap_hedges_a_fresh_placement_the_camera_may_have_missed(self):
        block = item(1, gap_since=True)
        answer = check_answer(self, self.resolve(ASK, [block]), shape="hedged", members=[block["item_id"]])
        self.assertEqual(answer["basis"], ["trusted_match", "placed", "coverage_gap"])
        self.assertEqual(answer["identity_status"], "matched_trusted")
        self.assertEqual(answer["location_status"], "placed")
        self.assertEqual(answer["text"], f"I recorded {BLOCK} at fixture cp5 table on 2026-09-21, but the camera was off or interrupted for a while since, so it may have moved.")
        self.assertEqual(answer["reference_image"], block["reference_image"], "the placement photo is still the evidence")
        self.assertEqual(answer["capture_time_ms"], block["observed_at_ms"])
        # The token is appended to every other hedged row of an item with a gap since
        # its evidence, in vocabulary order; it never reaches a confident answer.
        aged = item(2, observed_at_ms=NOW_MS - 25 * HOUR_MS, aged=True, stale_reason="age", gap_since=True)
        self.assertEqual(self.resolve(ASK, [aged])["basis"], ["trusted_match", "placed", "aged", "coverage_gap"])
        gone = item(3, location_status="stale", stale_reason="negative_reobservation", stale_since_ms=NOW_MS - HOUR_MS, gap_since=True)
        self.assertEqual(self.resolve(ASK, [gone])["basis"], ["trusted_match", "placed", "negative_reobservation", "coverage_gap"])
        picked = item(4, location_status="stale", location_text=None, stale_reason=cp5.CP2_PICKUP_REASON, gap_since=True)
        self.assertEqual(self.resolve(ASK, [picked])["basis"], ["trusted_match", "coverage_gap", "picked_up"])
        self.assertEqual(self.resolve(ASK, [item(5, gap_since=False)])["shape"], "confident")
        self.assertNotIn("coverage_gap", self.resolve("where is my unseen thing", [block])["basis"])

    # row 6: inferred -> hedged ("I think ...")
    def test_row_inferred_location_hedges_with_the_container(self):
        keys = inferred_item(1, "cp5-item-002", name="synthetic cp5 keys", container_name="synthetic cp5 basket", since_ms=ANCHOR_MS + 2200,
                             location_text="fixture cp5 shelf")
        answer = check_answer(self, self.resolve(ASK_KEYS, [keys]), shape="hedged", members=[keys["item_id"]])
        self.assertTrue(answer["text"].startswith("I think"), answer["text"])
        self.assertIn("synthetic cp5 basket", answer["text"])
        self.assertIn("fixture cp5 shelf", answer["text"])
        self.assertEqual(answer["location_status"], "inferred")
        self.assertEqual(answer["identity_status"], "matched_trusted")
        self.assertEqual(answer["basis"], ["trusted_match", "inferred"])
        self.assertEqual(answer["reference_image"], keys["reference_image"], "the keys' own last photo is the evidence")
        lost = inferred_item(3, "cp5-item-002", name="synthetic cp5 keys", container_name="synthetic cp5 basket", since_ms=ANCHOR_MS, location_text=None)
        answer = check_answer(self, self.resolve(ASK_KEYS, [lost]), shape="hedged")
        self.assertTrue(answer["text"].startswith("I think"), answer["text"])
        self.assertNotIn("fixture", answer["text"], "no place is claimed when the container's place is unknown")

    # row 7: negative re-observation -> hedged (the old place as history)
    def test_row_negative_reobservation_hedges_with_the_old_place_as_history(self):
        gone_at = ANCHOR_MS + 2200 + 60000
        block = item(1, location_status="stale", stale_reason="negative_reobservation", stale_since_ms=gone_at)
        answer = check_answer(self, self.resolve(ASK, [block]), shape="hedged", members=[block["item_id"]])
        self.assertEqual(answer["location_status"], "stale")
        self.assertIn("negative_reobservation", answer["basis"])
        self.assertEqual(answer["basis"][0], "trusted_match")
        self.assertIn("fixture cp5 table", answer["text"], "the old place is named")
        self.assertIn("no longer there", answer["text"])
        self.assertNotIn("recorded location of", answer["text"], "the old place is history, not the current location")
        self.assertEqual(answer["reference_image"], block["reference_image"], "the placement photo is the evidence")
        self.assertEqual(answer["capture_time_ms"], block["observed_at_ms"])

    # row 8: aged 24 h - 7 d -> hedged
    def test_row_aged_placement_hedges(self):
        block = item(1, observed_at_ms=NOW_MS - 25 * HOUR_MS, aged=True, stale_reason="age")
        answer = check_answer(self, self.resolve(ASK, [block]), shape="hedged", members=[block["item_id"]])
        self.assertIn("aged", answer["basis"])
        self.assertEqual(answer["basis"][0], "trusted_match")
        self.assertEqual(answer["location_status"], "placed")
        self.assertIn("more than a day ago", answer["text"])
        self.assertIn("fixture cp5 table", answer["text"])
        self.assertEqual(answer["reference_image"], block["reference_image"])
        self.assertIs(answer["members"][0]["aged"], True)

    # row 9: aged over 7 d -> abstain
    def test_row_aged_over_a_week_abstains_without_the_stale_place(self):
        block = item(1, observed_at_ms=NOW_MS - 8 * DAY_MS, aged=True, stale_reason="age", location_status="stale",
                     stale_since_ms=NOW_MS - DAY_MS)
        answer = check_answer(self, self.resolve(ASK, [block]), shape="abstain")
        self.assertIn("aged", answer["basis"])
        self.assertEqual(answer["members"], [])
        self.assertNotIn("fixture cp5 table", answer["text"], "a stale place is not usable evidence")
        self.assertIn(BLOCK, answer["text"])
        self.assertIsNone(answer["reference_image"])

    # row 10: picked_up / stale by pickup -> hedged without a current location
    def test_row_picked_up_hedges_without_a_current_location(self):
        picked = item(1, location_status="stale", location_text=None, stale_reason=cp5.CP2_PICKUP_REASON, stale_since_ms=ANCHOR_MS + 12200,
                      observed_at_ms=ANCHOR_MS + 12200)
        answer = check_answer(self, self.resolve(ASK, [picked]), shape="hedged", members=[picked["item_id"]])
        self.assertIn("picked_up", answer["basis"])
        self.assertEqual(answer["basis"][0], "trusted_match")
        self.assertEqual(answer["location_status"], "stale")
        self.assertNotIn("fixture", answer["text"], "no current location is claimed after a pickup")
        self.assertNotIn("recorded location of", answer["text"].lower())
        self.assertIn(BLOCK, answer["text"])
        if answer["reference_image"] is not None:
            self.assertEqual(answer["capture_time_ms"], picked["observed_at_ms"])

    # row 11: evidence expired -> the same shape without an image (target_indicated false)
    def test_row_expired_evidence_keeps_the_shape_without_an_image(self):
        fresh = item(1, evidence_expired=True, reference_image=None)
        answer = check_answer(self, self.resolve(ASK, [fresh]), shape="confident", members=[fresh["item_id"]])
        self.assertIsNone(answer["reference_image"])
        self.assertIs(answer["target_indicated"], False)
        self.assertIn("expired", answer["basis"])
        self.assertEqual(answer["basis"][:2], ["trusted_match", "placed"])
        self.assertEqual(answer["capture_time_ms"], fresh["observed_at_ms"], "expired evidence keeps its capture time (coordinator ruling 4)")
        aged = item(2, observed_at_ms=NOW_MS - 25 * HOUR_MS, aged=True, stale_reason="age", evidence_expired=True, reference_image=None)
        hedged = check_answer(self, self.resolve(ASK, [aged]), shape="hedged")
        self.assertIsNone(hedged["reference_image"])
        self.assertIs(hedged["target_indicated"], False)
        self.assertTrue({"aged", "expired"} <= set(hedged["basis"]), hedged["basis"])
        # A projection that still carries the bbox but flags the bytes gone: no image either.
        stale_bytes = item(3, evidence_expired=True)
        self.assertIsNone(self.resolve(ASK, [stale_bytes])["reference_image"])

    # sighting only (trusted identity, no recorded place) -> hedged, no location claim
    def test_trusted_sighting_without_a_place_hedges(self):
        sighted = item(1, location_status="sighted", location_text=None, stale_reason="Only a sighting; no resting placement recorded")
        answer = check_answer(self, self.resolve(ASK, [sighted]), shape="hedged")
        self.assertEqual(answer["location_status"], "sighted")
        self.assertEqual(answer["basis"][:2], ["trusted_match", "sighted"])
        self.assertNotIn("fixture", answer["text"])

    # one name matched but the item has lookalikes that did not -> hedged, no location
    def test_single_ambiguous_member_hedges_and_is_never_confident(self):
        a, b = lookalike_pair()
        answer = check_answer(self, self.resolve(a["item_id"], [a, b]), members=[a["item_id"]])
        self.assertEqual(answer["shape"], "hedged")
        self.assertIn("lookalikes", answer["basis"])
        self.assertNotEqual(answer["identity_status"], "matched_trusted", "an ambiguous identity is never presented as a trusted match")

    # B-14 per-member precedence: a group of members in different states keeps each state
    def test_b14_group_members_keep_their_own_state_and_the_group_shape_wins(self):
        fresh, aged = lookalike_pair()
        aged.update(observed_at_ms=NOW_MS - 25 * HOUR_MS, aged=True, stale_reason="age")
        stale = item(3, name=identity.GLASSES, identity_status="ambiguous", location_status="stale", stale_reason="negative_reobservation",
                     stale_since_ms=NOW_MS - HOUR_MS, location_text="fixture shelf back")
        expired = item(4, name=identity.GLASSES, identity_status="ambiguous", evidence_expired=True, reference_image=None, location_text="fixture shelf front")
        inferred = inferred_item(5, "cp5-item-009", name=identity.GLASSES, identity_status="ambiguous", container_name="synthetic basket",
                                 since_ms=ANCHOR_MS, location_text="fixture counter")
        members = [fresh, aged, stale, expired, inferred]
        ids = [m["item_id"] for m in members]
        for member in members:
            member["lookalikes"] = [other for other in ids if other != member["item_id"]]
        answer = check_answer(self, self.resolve(identity.ASK_GLASSES, members), shape="group")
        self.assertEqual({m["item_id"] for m in answer["members"]}, set(ids), "every member of the group is listed")
        by_id = {m["item_id"]: m for m in answer["members"]}
        self.assertIs(by_id[aged["item_id"]]["aged"], True)
        self.assertEqual(by_id[aged["item_id"]]["stale_reason"], "age")
        self.assertEqual(by_id[stale["item_id"]]["location_status"], "stale")
        self.assertEqual(by_id[stale["item_id"]]["stale_reason"], "negative_reobservation")
        self.assertIs(by_id[expired["item_id"]]["evidence_expired"], True)
        self.assertIsNone(by_id[expired["item_id"]]["reference_image"])
        self.assertEqual(by_id[inferred["item_id"]]["location_status"], "inferred")
        self.assertEqual(by_id[inferred["item_id"]]["inference"]["container"], "cp5-item-009")
        self.assertEqual(by_id[fresh["item_id"]]["location_status"], "placed")
        self.assertEqual({m["identity_status"] for m in answer["members"]}, {"ambiguous"}, "no member is upgraded, none downgraded")
        self.assertEqual({m["provenance"]["identity_status"] for m in answer["members"]}, {"ambiguous"})
        # The group's own evidence fields never borrow one member's.
        self.assertIsNone(answer["reference_image"])
        self.assertIsNone(answer["capture_time_ms"])
        self.assertEqual(answer["location_status"], "unknown")
        # Precedence: a member that would be confident alone does not make the group
        # confident. The member order is deterministic: newest evidence first (the
        # catalogue's order), ties in projection order.
        order = [m["item_id"] for m in answer["members"]]
        self.assertEqual(order, [m["item_id"] for m in self.resolve(identity.ASK_GLASSES, members)["members"]], "deterministic")
        times = [by_id[item_id]["observed_at_ms"] for item_id in order]
        self.assertEqual(times, sorted(times, reverse=True), f"newest first: {order}")
        self.assertEqual(order[-1], aged["item_id"])

    def test_precedence_clarify_and_group_beat_every_single_member_row(self):
        fresh = item(1)
        picked = item(2, name=BLOCK + " twin", location_status="stale", location_text=None, stale_reason=cp5.CP2_PICKUP_REASON)
        self.assertEqual(check_answer(self, self.resolve(ASK, [fresh, picked]))["shape"], "clarify")
        a, b = lookalike_pair(name=BLOCK)
        b.update(location_status="stale", stale_reason="negative_reobservation", stale_since_ms=NOW_MS - HOUR_MS)
        self.assertEqual(check_answer(self, self.resolve(ASK, [a, b]))["shape"], "group")

    # the exact key set and vocabularies, over every shape
    def test_answer_key_sets_and_vocabularies(self):
        a, b = lookalike_pair()
        shaped = {"abstain": self.resolve("where is my unseen thing", [item(1)]),
                  "clarify": self.resolve(ASK, [item(1), item(2, name=BLOCK + " spare")]),
                  "group": self.resolve(identity.ASK_GLASSES, [a, b]),
                  "confident": self.resolve(ASK, [item(1)]),
                  "hedged": self.resolve(ASK, [item(1, aged=True, stale_reason="age", observed_at_ms=NOW_MS - 25 * HOUR_MS)])}
        for shape, answer in shaped.items():
            with self.subTest(shape=shape):
                check_answer(self, answer, shape=shape)
                expected = {"group": cp5.GROUP_KEYS, "clarify": cp5.CLARIFY_KEYS}.get(shape, cp5.ANSWER_KEYS)
                self.assertTrue(expected <= set(answer), sorted(expected - set(answer)))
                self.assertTrue(set(answer) <= cp5.GROUP_KEYS, sorted(set(answer) - cp5.GROUP_KEYS))
                self.assertIn(answer["identity_status"], cp5.IDENTITY_STATUSES)
                self.assertIn(answer["location_status"], cp5.LOCATION_STATUSES)
                self.assertTrue(set(answer["basis"]) <= set(BASIS_VOCABULARY))
        self.assertEqual(set(shaped["abstain"]), cp5.ANSWER_KEYS)
        self.assertEqual(set(shaped["confident"]), cp5.ANSWER_KEYS)
        self.assertEqual(set(shaped["group"]), cp5.GROUP_KEYS)

    def test_basis_follows_the_vocabulary_precedence_order_in_every_row(self):
        """The plan's basis vocabulary is listed in precedence order; every answer's
        basis is a subsequence of it, whichever row produced it and whichever
        cross-cutting token (expired, index_pending) was added."""
        a, b = lookalike_pair()
        cases = {
            "confident": self.resolve(ASK, [item(1)]),
            "expired confident": self.resolve(ASK, [item(1, evidence_expired=True, reference_image=None)]),
            "negative + expired": self.resolve(ASK, [item(1, location_status="stale", stale_reason="negative_reobservation", stale_since_ms=NOW_MS - HOUR_MS, evidence_expired=True, reference_image=None)]),
            "pickup + expired": self.resolve(ASK, [item(1, location_status="stale", location_text=None, stale_reason=cp5.CP2_PICKUP_REASON, evidence_expired=True, reference_image=None)]),
            "ambiguous with a place": self.resolve(a["item_id"], [dict(a, location_status="placed"), b]),
            "pending abstain": self.resolve("where is my unseen thing", [item(1)], index_pending=True),
            "pending group": self.resolve(identity.ASK_GLASSES, [a, b], index_pending=True),
        }
        for name, answer in cases.items():
            with self.subTest(case=name):
                self.assertTrue(cp5.in_vocabulary_order(answer["basis"]), f"{name}: basis {answer['basis']} is not in the vocabulary's precedence order {BASIS_VOCABULARY}")

    def test_index_pending_is_carried_and_never_denies_a_pending_candidate(self):
        answer = check_answer(self, self.resolve("where is my unseen thing", [item(1)], index_pending=True), shape="abstain")
        self.assertIs(answer["index_pending"], True)
        self.assertEqual(answer["basis"], ["no_evidence", "index_pending"])
        lowered = answer["text"].lower()
        for phrase in cp5.PENDING_DENIALS:
            self.assertNotIn(phrase, lowered, "never 'I haven't seen it' while a candidate is pending (Part 1, immediate indexing)")
        confident = check_answer(self, self.resolve(ASK, [item(1)], index_pending=True), shape="confident")
        self.assertIs(confident["index_pending"], True)
        self.assertEqual(confident["basis"], ["trusted_match", "placed", "index_pending"])
        self.assertIs(confident["members"][0]["index_pending"], True)
        self.assertIs(self.resolve(ASK, [item(1)], index_pending=False)["index_pending"], False)

    def test_policy_max_members_bounds_a_question_and_defaults_to_eight(self):
        items = [item(n, name=f"{BLOCK} number {n}") for n in range(1, 13)]
        answer = check_answer(self, self.resolve(ASK, items), shape="clarify")
        self.assertEqual(len(answer["members"]), 8, "default max_members is 8")
        self.assertEqual(len(answer["options"]), 8)
        three = check_answer(self, self.resolve(ASK, items, policy={"max_members": 3}), shape="clarify")
        self.assertEqual({m["item_id"] for m in three["members"]}, {m["item_id"] for m in answer["members"][:3]}, "the cut keeps the first three of the same order")
        two = check_answer(self, self.resolve(ASK, items, policy={"max_members": 2}), shape="clarify")
        self.assertEqual(len(two["members"]), 2, "two is the smallest question")
        self.assertEqual(check_answer(self, self.resolve(ASK, items, policy=None), shape="clarify")["members"], answer["members"])
        self.assertEqual(check_answer(self, self.resolve(ASK, items, policy={}), shape="clarify")["members"], answer["members"])
        wide = check_answer(self, self.resolve(ASK, items, policy={"max_members": 32}), shape="clarify")
        self.assertEqual({m["item_id"] for m in wide["members"]}, {i["item_id"] for i in items}, "the upper bound lists every match")
        # Coordinator pin d: a question needs at least two candidates, so max_members 1 is
        # refused like 0, a string or a bool, always with ValueError (never TypeError).
        for bad in ({"max_members": 1}, {"max_members": 0}, {"max_members": "8"}, {"max_members": True}, {"max_members": -1}, {"max_members": 33}, {"members": 8}):
            with self.subTest(policy=bad), self.assertRaises(ValueError):
                self.resolve(ASK, items, policy=bad)
        with self.subTest(policy="max_members 1, single match"), self.assertRaises(ValueError):
            self.resolve(ASK, items[:1], policy={"max_members": 1})

    def test_invalid_query_and_clock_are_refused(self):
        for query in ("", " ", "x" * 2001, None, 7):
            with self.subTest(query=query), self.assertRaises((ValueError, TypeError)):
                self.resolve(query, [item(1)])
        for as_of in (-1, None, "now", 1.5, True):
            with self.subTest(as_of=as_of), self.assertRaises((ValueError, TypeError)):
                resolve(ASK, [item(1)], as_of_ms=as_of)

    def test_resolver_is_pure_and_does_not_mutate_its_inputs(self):
        items = [item(1), item(2, name=BLOCK + " spare")]
        before = copy.deepcopy(items)
        from perception.resolver import resolve as builder_resolve
        first = builder_resolve(ASK, items, as_of_ms=NOW_MS, index_pending=False)
        second = builder_resolve(ASK, items, as_of_ms=NOW_MS, index_pending=False)
        self.assertEqual(items, before, "resolve() must not mutate the projection")
        self.assertEqual(first, second, "resolve() is deterministic")
        import perception.resolver as module
        self.assertNotIn("sqlite3", module.__dict__, "the resolver touches no database")
        self.assertFalse(any(name in module.__dict__ for name in ("time", "ObjectStore", "cv2", "numpy")), "the resolver reads no clock and no model")


class ResolverStoreTests(cp5.Cp5Fixture):
    """The same rows through the real store: answer_text delegates to the resolver,
    and resolve() on the store's own projection gives the same answer."""
    def both(self, question, store=None, **kwargs):
        """(store answer, direct answer): answer_text and resolve() on the projection."""
        stored = self.answer(question, store)
        direct = self.direct(question, store, **kwargs)
        check_answer(self, stored)
        check_answer(self, direct)
        self.assert_parity(stored, direct)
        return stored, direct

    def assert_parity(self, stored, direct):
        a = {k: v for k, v in stored.items() if k != "unresolved_observation_id"}
        b = {k: v for k, v in direct.items() if k != "unresolved_observation_id"}
        self.assertEqual(a, b, "answer_text must equal resolve() on the same projection")

    def test_store_no_match_abstains(self):
        self.place_block()
        stored, _ = self.both("where is my unseen thing")
        self.assertEqual(stored["shape"], "abstain")
        self.assertEqual(stored["basis"], ["no_evidence"])

    def test_store_clarify_for_distinct_items(self):
        self.place_block(BLOCK, "fixture cp5 table", continuity="cp5-a")
        self.place_block(BLOCK + " spare", "fixture cp5 desk", continuity="cp5-b")
        stored, _ = self.both(ASK)
        self.assertEqual(stored["shape"], "clarify")
        self.assertEqual(len(stored["members"]), 2)

    def test_store_group_for_lookalikes_with_the_parked_observation(self):
        a, b, store = self.lookalike_group()
        stored, direct = self.both(identity.ASK_GLASSES, store)
        self.assertEqual(stored["shape"], "group")
        self.assertEqual({m["item_id"] for m in stored["members"]}, {a, b})
        self.assertRegex(stored["unresolved_observation_id"], r"^[0-9a-f]{64}$", "the store names the parked observation")
        for member in stored["members"]:
            self.assertEqual(member["identity_status"], "ambiguous")
            self.assertIn(member["provenance"]["observation_id"], [row["observation_id"] for row in store.item_evidence(member["item_id"])])
        single = self.answer(a, store)
        check_answer(self, single, members=[a])
        self.assertNotEqual(single["shape"], "confident")

    def test_store_provisional_sighting_hedges(self):
        _, pebble = self.provisional_sighting()
        stored, _ = self.both("where is my synthetic cp5 pebble")
        self.assertEqual(stored["shape"], "hedged")
        self.assertEqual(stored["identity_status"], "matched_provisional")
        self.assertEqual(stored["basis"][0], "provisional_match")
        self.assertEqual(stored["reference_image"], pebble["reference_image"])
        self.assertIsNotNone(stored["reference_image"])
        self.assertIs(stored["target_indicated"], False, "pin c: provisional keeps the photo, never a verified target")

    def test_store_fresh_placement_is_confident_with_the_photo(self):
        packet, block = self.place_block()
        stored, _ = self.both(ASK)
        self.assertEqual(stored["shape"], "confident")
        self.assertEqual(stored["basis"], ["trusted_match", "placed"])
        self.assertEqual(stored["reference_image"], {"frame_id": fx.rest_frame_id(packet), "bbox": fx.BLOCK_BBOX})
        self.assertIs(stored["target_indicated"], True)
        self.assertEqual(stored["capture_time_ms"], fx.rest_wall_ms(packet))
        self.assertEqual(stored["room"], ROOM_UNKNOWN)
        self.assertIn("fixture cp5 table", stored["text"])

    def test_store_coverage_gap_from_a_telemetry_window_hedges_the_placement(self):
        packet, block = self.place_block()
        placed_ms = fx.rest_wall_ms(packet)
        self.assertEqual(self.answer(ASK)["shape"], "confident")
        # A window of another device ending after the placement changes nothing.
        self.store.ingest_telemetry(cp5.encode(cp5.telemetry_packet(device=fx.OTHER_DEVICE, wall_ms=placed_ms, t_ms=60000, window_ms=60000, counters={"gaps": 1, "gap_ms": 20000})))
        self.assertEqual(self.answer(ASK)["shape"], "confident")
        # A window of the same device with no gap changes nothing either.
        self.store.ingest_telemetry(cp5.encode(cp5.telemetry_packet(wall_ms=placed_ms, t_ms=60000, window_ms=60000)))
        self.assertEqual(self.answer(ASK)["shape"], "confident")
        # The same device reports a gap in a window ending after the placement: hedged.
        self.store.ingest_telemetry(cp5.encode(cp5.telemetry_packet(wall_ms=placed_ms, t_ms=120000, window_ms=60000, counters={"gaps": 1, "gap_ms": 15000})))
        stored, _ = self.both(ASK)
        self.assertEqual(stored["shape"], "hedged")
        self.assertEqual(stored["basis"], ["trusted_match", "placed", "coverage_gap"])
        self.assertIs(stored["members"][0]["gap_since"], True)
        self.assertIn("camera was off or interrupted", stored["text"])
        self.assertIs(self.store.get_item(block["item_id"])["gap_since"], True)
        # Fresh evidence after the gap clears it: a positive re-observation refreshes the placement.
        self.idle("present", wall_ms=placed_ms + 180000)
        self.now += 300
        self.reobserve()
        cleared, _ = self.both(ASK)
        self.assertEqual(cleared["shape"], "confident")
        self.assertIs(cleared["members"][0]["gap_since"], False)
        # as_of before the gap window replays the confident answer.
        self.assertEqual(self.answer(ASK, as_of=placed_ms + 1000)["shape"], "confident")

    def test_store_provisional_sighting_ages_monotonically(self):
        packet, pebble = self.provisional_sighting()
        observed = fx.rest_wall_ms(packet)
        self.now = (observed + 25 * HOUR_MS) / 1000
        stored, _ = self.both("where is my synthetic cp5 pebble")
        self.assertEqual(stored["shape"], "hedged")
        self.assertEqual(stored["basis"][:3], ["provisional_match", "sighted", "aged"])
        self.now = (observed + 8 * DAY_MS) / 1000
        stored, _ = self.both("where is my synthetic cp5 pebble")
        self.assertEqual(stored["shape"], "abstain")
        self.assertEqual(stored["basis"], ["provisional_match", "aged"])

    def test_store_containment_infers_with_a_hedge(self):
        self.nest()
        self.move_outer()
        stored, _ = self.both(ASK_KEYS)
        self.assertEqual(stored["shape"], "hedged")
        self.assertEqual(stored["basis"], ["trusted_match", "inferred"])
        self.assertEqual(stored["location_status"], "inferred")
        self.assertTrue(stored["text"].startswith("I think"))
        self.assertIn("fixture cp5 shelf", stored["text"])

    def test_store_negative_reobservation_hedges(self):
        placement, _ = self.place_block()
        gone = self.negative_reobservation(placement)
        stored, _ = self.both(ASK)
        self.assertEqual(stored["shape"], "hedged")
        self.assertIn("negative_reobservation", stored["basis"])
        self.assertEqual(stored["location_status"], "stale")
        self.assertEqual(stored["members"][0]["stale_since_ms"], fx.idle_wall_ms(gone))
        self.assertIn("no longer there", stored["text"])

    def test_store_ageing_hedges_then_abstains_by_the_clock_alone(self):
        packet, _ = self.place_block()
        observed = fx.rest_wall_ms(packet)
        self.now = (observed + 25 * HOUR_MS) / 1000
        stored, _ = self.both(ASK)
        self.assertEqual(stored["shape"], "hedged")
        self.assertIn("aged", stored["basis"])
        self.assertIn("more than a day ago", stored["text"])
        self.now = (observed + 8 * DAY_MS) / 1000
        stored, _ = self.both(ASK)
        self.assertEqual(stored["shape"], "abstain")
        self.assertIn("aged", stored["basis"])
        self.assertNotIn("fixture cp5 table", stored["text"])
        # as_of replays the same table at an earlier clock.
        replayed = self.answer(ASK, as_of=observed + 60000)
        check_answer(self, replayed, shape="confident")
        self.assert_parity(replayed, resolve(ASK, self.store.list_items(limit=200, as_of=observed + 60000), as_of_ms=observed + 60000, index_pending=False))

    def test_store_pickup_hedges_without_a_place(self):
        self.place_block("synthetic cp5 cup", "fixture cp5 desk", continuity="cp5-cup")
        self.pickup_block("synthetic cp5 cup", continuity="cp5-cup")
        stored, _ = self.both("where is my synthetic cp5 cup")
        self.assertEqual(stored["shape"], "hedged")
        self.assertIn("picked_up", stored["basis"])
        self.assertNotIn("fixture cp5 desk", stored["text"])

    def test_store_expired_evidence_keeps_the_shape_without_an_image(self):
        packet, _ = self.place_block()
        self.expire(packet)
        stored, _ = self.both(ASK)
        self.assertEqual(stored["shape"], "confident")
        self.assertIsNone(stored["reference_image"])
        self.assertIs(stored["target_indicated"], False)
        self.assertIn("expired", stored["basis"])
        self.assertIs(stored["members"][0]["evidence_expired"], True)

    def test_store_index_pending_while_a_job_waits(self):
        packet = self.next_packet(rest=fx.golden("reference"))
        self.scripted.observations[packet["episode_id"]] = [fx.observation(fx.rest_frame_id(packet), fx.BLOCK_BBOX, label=BLOCK, location="fixture cp5 table")]
        self.ingest(packet)
        stored = self.answer(ASK)
        check_answer(self, stored, shape="abstain")
        self.assertIs(stored["index_pending"], True)
        self.assertIn("index_pending", stored["basis"])
        for phrase in cp5.PENDING_DENIALS:
            self.assertNotIn(phrase, stored["text"].lower())
        self.assert_parity(stored, self.direct(ASK, index_pending=True))
        self.process()
        drained = self.answer(ASK)
        check_answer(self, drained, shape="confident")
        self.assertIs(drained["index_pending"], False)

    def test_answer_text_parity_over_a_sample_of_states(self):
        """One projection with every state at once: the store's answer for each
        question equals resolve() on the same projection, member by member. The
        expired item is placed and expired first (apply_retention expires every
        packet received before its cutoff); the item the idle 'gone' frame shows
        gone is the only one at the block region (every other placement sits on
        plain texture, which the same frame re-observes as present)."""
        expired_packet, _ = self.place_block("synthetic cp5 mug", "fixture cp5 sink", continuity="cp5-mug")
        self.expire(expired_packet)
        self.place([fx.observation(None, [8.0, 8.0, 56.0, 36.0], label="synthetic cp5 fresh", location="fixture cp5 table", continuity_id="cp5-fresh")])
        gone_packet, _ = self.place_block("synthetic cp5 gone", "fixture cp5 shelf", continuity="cp5-gone")
        self.negative_reobservation(gone_packet)
        self.place([fx.observation(None, [100.0, 8.0, 140.0, 36.0], label="synthetic cp5 cup", location="fixture cp5 desk", continuity_id="cp5-cup")])
        self.place([fx.observation(None, [100.0, 8.0, 140.0, 36.0], label="synthetic cp5 cup", location=None, outcome="picked_up", continuity_id="cp5-cup")])
        self.provisional_sighting("synthetic cp5 pebble")
        self.nest()
        self.move_outer()
        for side in ("left", "right"):
            self.place([fx.observation(None, [8.0, 84.0, 48.0, 112.0], label="synthetic cp5 twin", location=f"fixture cp5 {side}", continuity_id=f"cp5-twin-{side}")])
        a, b, store = self.lookalike_group()
        questions = ["where is my synthetic cp5 fresh", "where is my synthetic cp5 gone", "where is my synthetic cp5 cup",
                     "where is my synthetic cp5 pebble", ASK_KEYS, "where is my synthetic cp5 basket", "where is my synthetic cp5 mug",
                     "where is my synthetic cp5 twin", identity.ASK_GLASSES, a, "where is my unseen thing"]
        shapes = {}
        for question in questions:
            with self.subTest(question=question):
                stored, direct = self.both(question, store)
                shapes[question] = stored["shape"]
        self.assertEqual(shapes["where is my synthetic cp5 fresh"], "confident")
        self.assertEqual(shapes["where is my synthetic cp5 gone"], "hedged")
        self.assertEqual(shapes["where is my synthetic cp5 cup"], "hedged")
        self.assertEqual(shapes["where is my synthetic cp5 pebble"], "hedged")
        self.assertEqual(shapes[ASK_KEYS], "hedged")
        self.assertEqual(shapes["where is my synthetic cp5 basket"], "confident")
        self.assertEqual(shapes["where is my synthetic cp5 mug"], "confident")
        self.assertIsNone(self.answer("where is my synthetic cp5 mug", store)["reference_image"], "expired evidence: no image")
        self.assertEqual(shapes["where is my synthetic cp5 twin"], "clarify")
        self.assertEqual(shapes[identity.ASK_GLASSES], "group")
        self.assertEqual(shapes["where is my unseen thing"], "abstain")
        # Aged at a later clock, the same sample still agrees.
        self.now += 25 * 3600
        for question in questions:
            with self.subTest(question=question, clock="25h later"):
                self.both(question, store)
        self.assertEqual(self.answer("where is my synthetic cp5 fresh", store)["shape"], "hedged")


if __name__ == "__main__":
    unittest.main(verbosity=2)
