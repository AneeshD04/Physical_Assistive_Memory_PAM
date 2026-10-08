"""CP2 acceptance: clock-only staleness and as_of replay (B-11).

    python3 -B server/test_cp2_staleness.py -v

Reuses bootstrap.MemoryApiFixture (real app + store, temp DB, injected clock
`self.now` in epoch seconds, fixture processor, egress and private-file guards).
A trusted `placed` item is seeded once; nothing is written afterwards. Every
change below comes from moving the clock or passing as_of: that is the whole
point of B-11 ("no write is needed for an answer to age").

Expected values follow perception/episode_store.py constants AGE_STALE_MS (24 h)
and AGE_ABSTAIN_MS (7 d) as named in docs/BUILD_PLAN.md; the observation time is
the packet's wall anchor + t_end_ms = bootstrap.ANCHOR_MS + 2200.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
import test_memory_bootstrap as bootstrap  # noqa: E402

ORIGIN = bootstrap.ORIGIN
HOUR_MS = 3600 * 1000
DAY_MS = 24 * HOUR_MS
OBSERVED_MS = bootstrap.ANCHOR_MS + 2200  # wall anchor + t_end_ms of the seeded packet
QUESTION = "where is my synthetic red block"


class StalenessFixture(bootstrap.MemoryApiFixture):
    def seed(self):
        packet, item = self.seeded_item()
        self.assertEqual(item["location_status"], "placed")
        self.assertEqual(item["identity_status"], "trusted")
        self.assertEqual(item["observed_at_ms"], OBSERVED_MS)
        self.assertEqual(item["location_text"], "fixture left")
        return packet, item

    def items(self, **params):
        response = self.client.get("/api/items", params=params)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        return response.json()["items"]

    def item(self, ident, **params):
        return self.client.get(f"/api/items/{ident}", params=params)

    def chat(self, text=QUESTION, **extra):
        response = self.client.post("/api/chat", json={"text": text, **extra}, headers={"origin": ORIGIN})
        return response

    def answer(self, text=QUESTION, **extra):
        response = self.chat(text, **extra)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        return response.json()

    def store(self):
        from perception.object_memory import ObjectStore
        return ObjectStore(self.db, profile_id="local", clock=self.clock)

    def advance(self, seconds):
        """Move the injected clock. Sessions last 8 h, so a jump past that needs a
        fresh sign-in; the sign-in is the only request made and writes nothing to
        the ledger (the egress/private-file guards still apply)."""
        self.now += seconds
        self.login()

    def set_clock(self, seconds):
        self.now = seconds
        self.login()


class ClockOnlyStalenessTests(StalenessFixture):
    def test_constants_match_the_plan(self):
        from perception import episode_store
        self.assertEqual(episode_store.AGE_STALE_MS, 24 * HOUR_MS)
        self.assertEqual(episode_store.AGE_ABSTAIN_MS, 7 * DAY_MS)

    def test_fresh_item_is_not_aged_and_answer_is_confident(self):
        _, item = self.seed()
        self.assertIn("aged", item, "the catalogue item must carry the evaluated 'aged' flag")
        self.assertIs(item["aged"], False)
        self.assertIsNone(item["stale_reason"])
        self.assertLess(int(self.now * 1000) - OBSERVED_MS, HOUR_MS)
        answer = self.answer()
        self.assertEqual(answer["shape"], "confident")
        self.assertEqual([m["item_id"] for m in answer["members"]], [item["item_id"]])
        self.assertIn("fixture left", answer["text"])

    def test_after_25_hours_catalogue_ages_and_chat_hedges_without_a_write(self):
        _, item = self.seed()
        ident = item["item_id"]
        self.advance(25 * 3600)
        aged = self.items()
        self.assertEqual(len(aged), 1)
        aged = aged[0]
        self.assertIs(aged["aged"], True)
        self.assertEqual(aged["stale_reason"], "age")
        self.assertEqual(aged["location_status"], "placed", "between 24 h and 7 d the location is still 'placed'")
        self.assertEqual(aged["location_text"], "fixture left")
        self.assertEqual(aged["observed_at_ms"], OBSERVED_MS, "ageing must not move the observation time")
        single = self.item(ident)
        self.assertEqual(single.status_code, 200, single.text)
        self.assertEqual(single.json()["aged"], True)
        self.assertEqual(single.json()["stale_reason"], "age")
        answer = self.answer()
        self.assertEqual(answer["shape"], "hedged")
        self.assertEqual(len(answer["members"]), 1)
        self.assertEqual(answer["members"][0]["item_id"], ident)
        self.assertIs(answer["members"][0]["aged"], True)
        self.assertNotIn("last saw", answer["text"].lower())
        self.assertIn("fixture left", answer["text"])
        self.assertEqual(len(self.processor.calls), 1, "ageing must not reprocess anything")

    def test_after_8_days_location_is_stale_and_chat_abstains_with_no_members(self):
        _, item = self.seed()
        self.advance(8 * 86400)
        aged = self.items()[0]
        self.assertIs(aged["aged"], True)
        self.assertEqual(aged["stale_reason"], "age")
        self.assertEqual(aged["location_status"], "stale")
        self.assertEqual(aged["observed_at_ms"], OBSERVED_MS)
        self.assertEqual(self.item(item["item_id"]).json()["location_status"], "stale")
        answer = self.answer()
        self.assertEqual(answer["shape"], "abstain")
        self.assertEqual(answer["members"], [])
        self.assertNotIn("last saw", answer["text"].lower())
        self.assertNotIn("fixture left", answer["text"], "an abstained answer must not leak the stale location as evidence")

    def test_age_thresholds_are_strict(self):
        # Exactly 24 h old is not aged; one millisecond more is. Same at 7 d.
        _, item = self.seed()
        self.set_clock((OBSERVED_MS + DAY_MS) / 1000)
        self.assertIs(self.items()[0]["aged"], False)
        self.assertEqual(self.answer()["shape"], "confident")
        self.set_clock((OBSERVED_MS + DAY_MS + 1) / 1000)
        self.assertIs(self.items()[0]["aged"], True)
        self.assertEqual(self.items()[0]["location_status"], "placed")
        self.assertEqual(self.answer()["shape"], "hedged")
        self.set_clock((OBSERVED_MS + 7 * DAY_MS) / 1000)
        self.assertEqual(self.items()[0]["location_status"], "placed")
        self.assertEqual(self.answer()["shape"], "hedged")
        self.set_clock((OBSERVED_MS + 7 * DAY_MS + 1) / 1000)
        self.assertEqual(self.items()[0]["location_status"], "stale")
        self.assertEqual(self.answer()["shape"], "abstain")

    def test_stored_projection_does_not_change_with_the_clock(self):
        _, item = self.seed()
        store = self.store()
        before = store.list_items(as_of=None)
        self.assertEqual(len(before), 1)
        self.now += 8 * 86400
        after = store.list_items(as_of=None)
        self.assertEqual(len(after), 1)
        for key in ("observation_id", "observed_at_ms", "item_id", "name", "identity_status", "location_text", "reference_image"):
            self.assertEqual(before[0][key], after[0][key], key)
        self.assertEqual(before[0]["aged"], False)
        self.assertEqual(after[0]["aged"], True)
        # The rows in current_items themselves are byte-identical at both clocks.
        rows_after = self.current_rows()
        self.now -= 8 * 86400
        rows_before = self.current_rows()
        self.assertEqual(rows_before, rows_after)
        self.assertEqual(len(rows_after), 1)
        record = json.loads(rows_after[0])
        self.assertIs(record["aged"], False, "stored projection never carries an evaluated age")
        self.assertEqual(record["location_status"], "placed")
        self.assertIsNone(record["stale_reason"])

    def current_rows(self):
        import sqlite3
        connection = sqlite3.connect(str(self.db))
        try:
            return [row[0] for row in connection.execute("SELECT record FROM current_items WHERE profile_id='local' ORDER BY item_id")]
        finally:
            connection.close()

    def test_rename_after_ageing_does_not_refresh_the_age(self):
        _, item = self.seed()
        self.advance(25 * 3600)
        response = self.client.post(f"/api/items/{item['item_id']}/name", json={"name": "Named block"}, headers={"origin": ORIGIN})
        self.assertEqual(response.status_code, 200, response.text)
        renamed = response.json()
        self.assertEqual(renamed["name"], "Named block")
        self.assertIs(renamed["aged"], True, "a user note is not a re-observation")
        self.assertEqual(renamed["observed_at_ms"], OBSERVED_MS)


class AsOfReplayTests(StalenessFixture):
    def test_as_of_just_after_observation_shows_fresh_item_even_when_now_is_old(self):
        _, item = self.seed()
        self.advance(8 * 86400)
        self.assertEqual(self.items()[0]["location_status"], "stale")
        at = OBSERVED_MS + 60 * 1000
        replayed = self.items(as_of=str(at))
        self.assertEqual(len(replayed), 1)
        self.assertIs(replayed[0]["aged"], False)
        self.assertEqual(replayed[0]["location_status"], "placed")
        self.assertIsNone(replayed[0]["stale_reason"])
        single = self.item(item["item_id"], as_of=str(at))
        self.assertEqual(single.status_code, 200, single.text)
        self.assertIs(single.json()["aged"], False)
        answer = self.answer(as_of=at)
        self.assertEqual(answer["shape"], "confident")
        self.assertEqual([m["item_id"] for m in answer["members"]], [item["item_id"]])
        # as_of 25 h after the observation: hedged, regardless of the wall clock.
        self.assertEqual(self.answer(as_of=OBSERVED_MS + 25 * HOUR_MS)["shape"], "hedged")
        self.assertIs(self.items(as_of=str(OBSERVED_MS + 25 * HOUR_MS))[0]["aged"], True)

    def test_as_of_before_observation_hides_the_item(self):
        _, item = self.seed()
        at = OBSERVED_MS - 1
        self.assertEqual(self.items(as_of=str(at)), [])
        response = self.item(item["item_id"], as_of=str(at))
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        answer = self.answer(as_of=at)
        self.assertEqual(answer["shape"], "abstain")
        self.assertEqual(answer["members"], [])
        # Exactly at the observation time the item is visible.
        self.assertEqual(len(self.items(as_of=str(OBSERVED_MS))), 1)
        self.assertEqual(self.item(item["item_id"], as_of=str(OBSERVED_MS)).status_code, 200)
        # as_of=0 (epoch) is valid syntax and shows nothing.
        self.assertEqual(self.items(as_of="0"), [])

    def test_as_of_is_read_only(self):
        _, item = self.seed()
        store = self.store()
        rows = store.list_items(as_of=None)
        self.items(as_of=str(OBSERVED_MS - 1))
        self.answer(as_of=OBSERVED_MS + 25 * HOUR_MS)
        self.item(item["item_id"], as_of=str(OBSERVED_MS + 8 * DAY_MS))
        self.assertEqual(store.list_items(as_of=None), rows)
        self.assertEqual(len(self.processor.calls), 1)

    def test_invalid_as_of_values_are_400_for_items_item_and_chat(self):
        _, item = self.seed()
        bad = ["-1", "1.5", "abc", "1e3", " 1", "1 ", "", "12345678901234567", "0x10", "１２３", "1_000", "+1", "nan"]
        for value in bad:
            with self.subTest(as_of=value):
                for path in ("/api/items", f"/api/items/{item['item_id']}"):
                    response = self.client.get(path, params={"as_of": value})
                    self.assertEqual(response.status_code, 400, f"{path} as_of={value!r}: {response.text}")
                    self.assertEqual(response.json(), {"detail": "Invalid as_of value."})
                    self.assert_safe_error(response)
        for value in (-1, 1.5, "1", True, False, [1], {"ms": 1}, 10 ** 16, 1e3):
            with self.subTest(chat_as_of=value):
                response = self.chat(as_of=value)
                self.assertEqual(response.status_code, 400, f"chat as_of={value!r}: {response.text}")
                self.assertEqual(response.json(), {"detail": "Invalid as_of value."})
                self.assert_safe_error(response)
        # null as_of means absent (evaluated now), and a 16-digit value is accepted.
        self.assertEqual(self.answer(as_of=None)["shape"], "confident")
        self.assertEqual(self.chat(as_of=10 ** 16 - 1).status_code, 200)
        self.assertEqual(self.client.get("/api/items", params={"as_of": "9" * 16}).status_code, 200)

    def test_as_of_requires_authentication_like_everything_else(self):
        response = self.client.get("/api/items", params={"as_of": str(OBSERVED_MS)})
        self.assertEqual(response.status_code, 401)
        response = self.client.post("/api/chat", json={"text": QUESTION, "as_of": OBSERVED_MS}, headers={"origin": ORIGIN})
        self.assertEqual(response.status_code, 401)

    def test_as_of_hides_a_later_relocation(self):
        # Two observations: the item moves at phase 1 (observed at ANCHOR + 12200).
        self.login()
        first = self.packet()
        self.assert_ack(self.post_packet(first), first, status="stored")
        self.wait_items()
        second = self.packet(phase=1)
        self.assert_ack(self.post_packet(second), second, status="stored")
        moved = self.wait_items()[0]
        self.assertEqual(moved["location_text"], "fixture right")
        self.assertEqual(moved["observed_at_ms"], bootstrap.ANCHOR_MS + 12200)
        earlier = self.items(as_of=str(bootstrap.ANCHOR_MS + 12199))
        self.assertEqual(len(earlier), 1)
        self.assertEqual(earlier[0]["location_text"], "fixture left")
        self.assertEqual(earlier[0]["observed_at_ms"], OBSERVED_MS)
        answer = self.answer(as_of=bootstrap.ANCHOR_MS + 12199)
        self.assertEqual(answer["shape"], "confident")
        self.assertIn("fixture left", answer["text"])
        self.assertIn("fixture right", self.answer()["text"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
