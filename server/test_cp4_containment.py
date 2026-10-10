"""CP4 acceptance, store level: containment as `inferred`.

    python3 -B server/test_cp4_containment.py -v

Authority: docs/BUILD_PLAN.md "CP4 in detail", *Containment as `inferred`* (A):
a placed item A whose rest bbox lies at least 80 % inside the rest bbox of another
item B placed in the same frame gets a containment(profile_id, inner_item,
outer_item, since_ms, frame_id) row (most recent wins; a pickup of A clears it).
When B's location later changes (a new placement of B, or B becomes stale) A's
projection reads location_status "inferred", location_text = B's current text,
inference {"container": B, "since_ms"}; A's own last observation stays in history;
the answer is hedged: "I think {A} is with {B}, which I last saw at {location}."
A negative re-observation of A at its old place does not contradict an inferred
location. Nothing here needs an embedder: placements are trusted through the CP2
code-only fixture calibration and re-matched through continuity ids.
"""
from __future__ import annotations

from pathlib import Path
import sqlite3
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
import test_cp4_fixtures as fx  # noqa: E402

ANCHOR_MS = fx.ANCHOR_MS
KEYS, BASKET, TRAY = "synthetic keys", "synthetic basket", "synthetic tray"
ASK_KEYS = "where are my synthetic keys"
COUNTER, SHELF, DESK = "fixture counter", "fixture shelf", "fixture desk"
# Geometry on the reference golden: the basket IS the block (so an idle "gone" frame
# makes the basket stale), the keys sit fully inside it, the tray is elsewhere.
BASKET_BBOX = list(fx.BLOCK_BBOX)             # [60, 40, 100, 80]
KEYS_BBOX = [68.0, 48.0, 92.0, 72.0]          # 100 % inside the basket
KEYS_75_BBOX = [70.0, 48.0, 110.0, 72.0]      # 30 of 40 px inside the basket's x range: 75 % -> no containment
KEYS_80_BBOX = [80.0, 48.0, 105.0, 72.0]      # 20 of 25 px inside: exactly 80 % -> containment
TRAY_BBOX = [8.0, 8.0, 56.0, 36.0]            # plain texture: unchanged between goldens
CONTAINMENT_COLUMNS = {"profile_id", "inner_item", "outer_item", "since_ms", "frame_id"}


def hedged_text(inner, outer, location):
    return f"I think {inner} is with {outer}, which I last saw at {location}."


def assert_inference(case, value, *, container, since_ms, container_name=None):
    """Coordinator ruling 5: inference is {container, container_name, since_ms}
    (asserted as a superset: container and since_ms exact, container_name when given)."""
    case.assertIsInstance(value, dict, value)
    case.assertEqual(value.get("container"), container, value)
    case.assertEqual(value.get("since_ms"), since_ms, value)
    case.assertIn("container_name", value, value)
    if container_name is not None:
        case.assertEqual(value.get("container_name"), container_name, value)


class ContainmentFixture(fx.Cp4Fixture):
    def obs(self, label, bbox, location, continuity, **extra):
        return fx.observation(None, bbox, label=label, location=location, continuity_id=continuity, **extra)

    def nest(self, keys_bbox=KEYS_BBOX, *, location=COUNTER):
        """One rest frame: the basket placed at `location` with the keys inside it.
        Returns (packet, keys item, basket item)."""
        packet = self.place([self.obs(BASKET, BASKET_BBOX, location, "cont-basket"), self.obs(KEYS, keys_bbox, location, "cont-keys")])
        keys, basket = self.item_by_name(KEYS), self.item_by_name(BASKET)
        for item in (keys, basket):
            self.assertEqual((item["identity_status"], item["location_status"], item["location_text"]), ("trusted", "placed", location), item)
        return packet, keys, basket

    def move(self, label, bbox, location, continuity, *, outcome="placed_on_surface", **packet_kwargs):
        packet = self.place([self.obs(label, bbox, location, continuity, outcome=outcome)], **packet_kwargs)
        return packet, self.item_by_name(label)

    def current_containment(self, inner):
        """The most recent containment row of `inner` (the plan: most recent wins; the
        store may keep earlier rows as history)."""
        rows = [r for r in self.containment() if r["inner_item"] == inner]
        return max(rows, key=lambda r: (r["since_ms"], r.get("containment_no", 0))) if rows else None

    def containment(self):
        return self.rows("containment", "WHERE profile_id='local' ORDER BY since_ms, inner_item")

    def rebuild(self):
        connection = sqlite3.connect(str(self.db))
        with connection:
            connection.execute("DELETE FROM current_items WHERE profile_id='local'")
        connection.close()
        result = self.store.rebuild_all()
        self.assertIs(result["model_rerun"], False)
        return result


class ContainmentTests(ContainmentFixture):
    def test_nested_placement_records_containment_without_changing_the_projection(self):
        self.assertTrue(fx.table_exists(self.db, "containment"), "containment table")
        self.assertTrue(CONTAINMENT_COLUMNS <= set(fx.columns(self.db, "containment")), fx.columns(self.db, "containment"))
        packet, keys, basket = self.nest()
        rows = self.containment()
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual((rows[0]["inner_item"], rows[0]["outer_item"]), (keys["item_id"], basket["item_id"]))
        self.assertEqual(rows[0]["since_ms"], fx.rest_wall_ms(packet))
        self.assertEqual(rows[0]["frame_id"], fx.rest_frame_id(packet))
        # Nothing is inferred while the container has not moved.
        for item in (self.store.get_item(keys["item_id"]), self.store.get_item(basket["item_id"])):
            self.assertEqual(item["location_status"], "placed")
            self.assertIsNone(item.get("inference"))
            self.assertIsNone(item.get("stale_since_ms"))
        answer = self.store.answer_text(ASK_KEYS)
        self.assertEqual(answer["shape"], "confident", answer)
        self.assertEqual([m["item_id"] for m in answer["members"]], [keys["item_id"]])

    def test_eighty_percent_rule_is_inclusive(self):
        self.nest(KEYS_75_BBOX)
        self.assertEqual(self.containment(), [], "75 % inside is not containment")
        other = self.make_store(profile="other-profile")
        self.assertEqual(fx.table_rows(self.db, "containment", "WHERE profile_id='other-profile'"), [])
        self.assertEqual(other.list_items(), [])
        # A fresh pair in another session at exactly 80 %.
        packet = self.place([fx.observation(None, BASKET_BBOX, label="synthetic bowl", location=DESK, continuity_id="cont-bowl"),
                             fx.observation(None, KEYS_80_BBOX, label="synthetic coin", location=DESK, continuity_id="cont-coin")],
                            session="44444444-4444-4444-8444-444444444444")
        rows = self.containment()
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual((rows[0]["inner_item"], rows[0]["outer_item"]), (self.item_by_name("synthetic coin")["item_id"], self.item_by_name("synthetic bowl")["item_id"]))
        self.assertEqual(rows[0]["frame_id"], fx.rest_frame_id(packet))
        # Only trusted placements take part: a provisional sighting inside a placed item is not contained.
        self.place([fx.observation(None, BASKET_BBOX, label="synthetic box", location=SHELF, continuity_id="cont-box"),
                    fx.observation(None, KEYS_BBOX, label="synthetic pebble", location=None, outcome="sighted", identity_state="provisional", calibration={})])
        self.assertEqual(len(self.containment()), 1, "a provisional sighting is not a contained placement")

    def test_container_relocation_infers_the_inner_item_with_a_hedged_answer(self):
        nest_packet, keys, basket = self.nest()
        since = fx.rest_wall_ms(nest_packet)
        move_packet, moved_basket = self.move(BASKET, BASKET_BBOX, SHELF, "cont-basket")
        self.assertEqual(moved_basket["item_id"], basket["item_id"], "continuity re-matches the basket")
        self.assertEqual((moved_basket["location_status"], moved_basket["location_text"]), ("placed", SHELF))
        inferred = self.store.get_item(keys["item_id"])
        self.assertEqual(inferred["location_status"], "inferred", inferred)
        self.assertEqual(inferred["location_text"], SHELF, "the container's current location")
        assert_inference(self, inferred["inference"], container=basket["item_id"], since_ms=since, container_name=BASKET)
        self.assertEqual(inferred["identity_status"], "trusted")
        self.assertEqual(inferred["observed_at_ms"], keys["observed_at_ms"], "A's own last observation time is kept")
        self.assertIsNone(inferred["stale_reason"])
        self.assertIsNone(inferred.get("stale_since_ms"))
        listed = {i["item_id"]: i for i in self.items()}
        self.assertEqual(listed[keys["item_id"]]["location_status"], "inferred")
        assert_inference(self, listed[keys["item_id"]]["inference"], container=basket["item_id"], since_ms=since, container_name=BASKET)
        self.assertIsNone(listed[basket["item_id"]].get("inference"))
        # History keeps A's own last-observed place.
        history = self.store.item_history(keys["item_id"])
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["location_text"], COUNTER)
        evidence = self.store.item_evidence(keys["item_id"])
        self.assertEqual([row["location_text"] for row in evidence], [COUNTER])
        # The hedged answer, in the plan's words.
        answer = self.store.answer_text(ASK_KEYS)
        self.assertEqual(answer["shape"], "hedged", answer)
        self.assertEqual(answer["text"], hedged_text(KEYS, BASKET, SHELF))
        self.assertTrue(answer["text"].startswith("I think"))
        self.assertEqual([m["item_id"] for m in answer["members"]], [keys["item_id"]])
        self.assertEqual(answer["members"][0]["location_status"], "inferred")
        self.assertEqual(answer["members"][0]["inference"]["container"], basket["item_id"])
        # A user name for either item flows into the sentence.
        self.store.rename_item(keys["item_id"], "My keys")
        self.store.rename_item(basket["item_id"], "The basket")
        self.assertEqual(self.store.answer_text("where are my keys")["text"], hedged_text("My keys", "The basket", SHELF))
        self.assertEqual(self.store.get_item(keys["item_id"])["inference"]["container_name"], "The basket")
        # The basket itself is answered confidently.
        self.assertEqual(self.store.answer_text("where is the basket")["shape"], "confident")

    def test_container_going_stale_by_negative_reobservation_also_infers(self):
        nest_packet, keys, basket = self.nest()
        since = fx.rest_wall_ms(nest_packet)
        gone, _ = self.idle("gone", wall_ms=since + 60000)
        self.now += 120
        self.reobserve()
        stale = self.store.get_item(basket["item_id"])
        self.assertEqual((stale["location_status"], stale["stale_reason"]), ("stale", "negative_reobservation"), stale)
        self.assertEqual(stale["stale_since_ms"], fx.idle_wall_ms(gone))
        self.assertEqual(stale["location_text"], COUNTER, "the container's last known place is kept")
        inferred = self.store.get_item(keys["item_id"])
        self.assertEqual(inferred["location_status"], "inferred", "the keys are expected to have left with the basket")
        self.assertEqual(inferred["location_text"], COUNTER)
        assert_inference(self, inferred["inference"], container=basket["item_id"], since_ms=since, container_name=BASKET)
        self.assertNotEqual(inferred["stale_reason"], "negative_reobservation", "the inner item's own negative frame does not override the inference")
        answer = self.store.answer_text(ASK_KEYS)
        self.assertEqual(answer["shape"], "hedged")
        self.assertEqual(answer["text"], hedged_text(KEYS, BASKET, COUNTER))

    def test_pickup_of_the_inner_item_clears_containment(self):
        nest_packet, keys, basket = self.nest()
        self.assertEqual(len(self.containment()), 1)
        pickup_packet, picked = self.move(KEYS, KEYS_BBOX, None, "cont-keys", outcome="picked_up")
        self.assertEqual(picked["item_id"], keys["item_id"])
        self.assertEqual(picked["location_status"], "stale", "an observed pickup")
        # The pickup clears the containment: whether the row is deleted or kept as history,
        # the basket moving afterwards must not infer the keys.
        self.move(BASKET, BASKET_BBOX, SHELF, "cont-basket")
        after = self.store.get_item(keys["item_id"])
        self.assertEqual(after["location_status"], "stale", "no container any more: the pickup stands")
        self.assertIsNone(after.get("inference"))
        self.assertNotEqual(self.store.answer_text(ASK_KEYS)["shape"], "confident")
        self.assertNotIn("I think", self.store.answer_text(ASK_KEYS)["text"])

    def test_most_recent_containment_wins(self):
        nest_packet, keys, basket = self.nest()
        # The keys are placed again, inside the tray on the desk.
        tray_packet = self.place([self.obs(TRAY, BASKET_BBOX, DESK, "cont-tray"), self.obs(KEYS, KEYS_BBOX, DESK, "cont-keys")])
        tray = self.item_by_name(TRAY)
        current = self.current_containment(keys["item_id"])
        self.assertIsNotNone(current, self.containment())
        self.assertEqual(current["outer_item"], tray["item_id"], "the most recent containment wins")
        self.assertEqual(current["since_ms"], fx.rest_wall_ms(tray_packet))
        # The old container moving changes nothing for the keys; the current one does.
        self.move(BASKET, BASKET_BBOX, SHELF, "cont-basket")
        keys_now = self.store.get_item(keys["item_id"])
        self.assertEqual((keys_now["location_status"], keys_now["location_text"]), ("placed", DESK))
        self.assertIsNone(keys_now.get("inference"))
        self.move(TRAY, TRAY_BBOX, COUNTER, "cont-tray")
        keys_now = self.store.get_item(keys["item_id"])
        self.assertEqual((keys_now["location_status"], keys_now["location_text"]), ("inferred", COUNTER))
        assert_inference(self, keys_now["inference"], container=tray["item_id"], since_ms=fx.rest_wall_ms(tray_packet), container_name=TRAY)
        self.assertEqual(self.store.answer_text(ASK_KEYS)["text"], hedged_text(KEYS, TRAY, COUNTER))

    def test_negative_reobservation_of_the_inner_item_does_not_contradict_an_inference(self):
        nest_packet, keys, basket = self.nest()
        since = fx.rest_wall_ms(nest_packet)
        # The basket is placed again on plain texture (unchanged between the goldens), so an
        # idle "gone" frame leaves the basket present and only the keys' old place changed.
        move_packet, _ = self.move(BASKET, TRAY_BBOX, SHELF, "cont-basket")
        inferred = self.store.get_item(keys["item_id"])
        self.assertEqual((inferred["location_status"], inferred["location_text"]), ("inferred", SHELF))
        gone, _ = self.idle("gone", wall_ms=fx.rest_wall_ms(move_packet) + 60000)
        self.now += 120
        self.reobserve()
        after = self.store.get_item(keys["item_id"])
        self.assertEqual(after["location_status"], "inferred", after)
        self.assertEqual(after["location_text"], SHELF)
        assert_inference(self, after["inference"], container=basket["item_id"], since_ms=since, container_name=BASKET)
        self.assertNotEqual(after["stale_reason"], "negative_reobservation")
        self.assertIsNone(after.get("stale_since_ms"))
        basket_now = self.store.get_item(basket["item_id"])
        self.assertEqual((basket_now["location_status"], basket_now["location_text"]), ("placed", SHELF))
        self.assertEqual(self.store.answer_text(ASK_KEYS)["text"], hedged_text(KEYS, BASKET, SHELF))

    def test_container_seen_present_by_an_idle_frame_before_relocation_still_infers(self):
        # Coordinator investigation (Builder C's smoke order report): containment, then an
        # idle frame that shows the container (and the keys) present at the old place,
        # then the container is placed elsewhere -> the keys must still read inferred.
        nest_packet, keys, basket = self.nest()
        since = fx.rest_wall_ms(nest_packet)
        seen, _ = self.idle("present", wall_ms=since + 60000)      # T1: both still at the counter
        self.now += 120
        self.reobserve()
        rows = {r["item_id"]: r["result"] for r in self.rows("reobservations")}
        self.assertEqual(rows, {keys["item_id"]: "present", basket["item_id"]: "present"}, rows)
        self.assertEqual([(r["inner_item"], r["outer_item"]) for r in self.containment()], [(keys["item_id"], basket["item_id"])],
                         "a positive re-observation of both at the same place must not clear or shadow the containment row")
        # T2 > T1: the basket moves (the packet is dated after the idle sighting; chronology,
        # not posting order, decides).
        move_packet, moved = self.move(BASKET, TRAY_BBOX, SHELF, "cont-basket", wall_ms=since + 120000)
        self.assertGreater(fx.rest_wall_ms(move_packet), fx.idle_wall_ms(seen))
        self.assertEqual((moved["location_status"], moved["location_text"]), ("placed", SHELF))
        inferred = self.store.get_item(keys["item_id"])
        self.assertEqual(inferred["location_status"], "inferred", inferred)
        self.assertEqual(inferred["location_text"], SHELF)
        assert_inference(self, inferred["inference"], container=basket["item_id"], since_ms=since, container_name=BASKET)
        self.assertEqual(inferred["observed_at_ms"], fx.idle_wall_ms(seen), "the keys' own last sighting is the idle frame")
        self.assertEqual(self.store.answer_text(ASK_KEYS)["text"], hedged_text(KEYS, BASKET, SHELF))
        # Chronology matters, not posting order: a frame dated AFTER the move that shows
        # the keys still at the old place is a positive sighting after the move, so the
        # keys read placed at the counter again (they did not leave with the basket).
        later, _ = self.idle("present", wall_ms=fx.rest_wall_ms(move_packet) + 60000)
        self.now += 120
        self.reobserve()
        after = self.store.get_item(keys["item_id"])
        self.assertEqual((after["location_status"], after["location_text"]), ("placed", COUNTER), after)
        self.assertIsNone(after.get("inference"))

    def test_inference_is_replayed_by_rebuild_all_and_as_of(self):
        nest_packet, keys, basket = self.nest()
        since = fx.rest_wall_ms(nest_packet)
        move_packet, _ = self.move(BASKET, BASKET_BBOX, SHELF, "cont-basket")
        moved_at = fx.rest_wall_ms(move_packet)
        current = {i["item_id"]: i for i in self.items()}
        self.assertEqual(current[keys["item_id"]]["location_status"], "inferred")
        self.rebuild()
        rebuilt = {i["item_id"]: i for i in self.items()}
        for item_id, item in current.items():
            for key in ("location_status", "location_text", "inference", "observed_at_ms", "stale_reason", "identity_status", "name"):
                self.assertEqual(rebuilt[item_id].get(key), item.get(key), (item_id, key))
        earlier = self.store.get_item(keys["item_id"], as_of=moved_at - 1)
        self.assertEqual((earlier["location_status"], earlier["location_text"]), ("placed", COUNTER))
        self.assertIsNone(earlier.get("inference"))
        self.assertEqual(self.store.answer_text(ASK_KEYS, as_of=moved_at - 1)["shape"], "confident")
        later = self.store.get_item(keys["item_id"], as_of=moved_at)
        self.assertEqual((later["location_status"], later["location_text"]), ("inferred", SHELF))
        assert_inference(self, later["inference"], container=basket["item_id"], since_ms=since, container_name=BASKET)
        self.assertEqual(self.store.answer_text(ASK_KEYS, as_of=moved_at)["text"], hedged_text(KEYS, BASKET, SHELF))
        # A fresh store instance derives the same from storage.
        fresh = self.make_store()
        assert_inference(self, fresh.get_item(keys["item_id"])["inference"], container=basket["item_id"], since_ms=since)


if __name__ == "__main__":
    unittest.main(verbosity=2)
