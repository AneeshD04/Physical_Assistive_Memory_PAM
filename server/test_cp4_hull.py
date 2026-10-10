"""CP4 acceptance, store level: the hand hull in the identity crop (CP3 deferral,
recipe r2; Oversight T2 / coordinator F1).

    python3 -B server/test_cp4_hull.py -v

Authority: docs/BUILD_PLAN.md "CP4 in detail", *Hand hull and crop geometry*: the
convex hull of the 21 image-normalised points of each hand in the landmark sample
nearest in time (<= HAND_HULL_WINDOW_MS = 150 ms) to the keyframe, dilated by
HULL_DILATION = 3 % of the frame width, is excluded from the identity crop's pooling
mask; the crop is the bbox padded by CROP_PAD = 0.10 on each side. F1 (coordinator):
when the hull leaves less than MIN_MASK_SHARE (25 %) of the padded crop, the
observation is NOT embedded at all (count embedding_skipped_hand, match reason
"hand covers the region", no embeddings row, identity provisional) rather than
pooled over the hand. A hull touching only a corner, or a sample outside the time
window, leaves the embedding to run normally (with the hull-shaped mask).
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
import test_cp3_identity as identity  # noqa: E402
import test_cp4_fixtures as fx  # noqa: E402

SKIPPED_REASON = "hand covers the region"


def hand_over(x1, y1, x2, y2, *, width=fx.SCENE_W, height=fx.SCENE_H):
    """One packet-shaped hand whose 21 landmarks spread over the pixel rectangle
    [x1, x2] x [y1, y2] (image-normalised as hand_hull_mask reads them: pixel =
    value * (side - 1)), so its convex hull is that rectangle."""
    xs = np.linspace(x1, x2, 7)
    ys = np.linspace(y1, y2, 3)
    points = [{"x": round(float(x) / (width - 1), 5), "y": round(float(y) / (height - 1), 5), "z": -0.01} for y in ys for x in xs]
    assert len(points) == 21
    return {"landmarks": points, "world_landmarks": None,
            "hand_bbox": [x1 / width, y1 / height, min(1.0, x2 / width), min(1.0, y2 / height)], "handedness": "right"}


class HandHullTests(fx.Cp4Fixture):
    EMBEDDER = True

    def setUp(self):
        super().setUp()
        self.register_calibration()

    def place_tagged_with_hand(self, hand, *, offset_ms):
        """A trusted placement of the tagged square at TAG_LEFT whose packet carries one
        landmark sample `offset_ms` before the rest keyframe with `hand` (or no hand)."""
        packet = self.next_packet(rest=fx.golden("tagged_reference"))
        rest_t = packet["t_end_ms"]
        sample = {"frame_id": f"lm-{packet['episode_id']}", "t_ms": rest_t - offset_ms, "hands": [hand] if hand else []}
        packet["landmarks"] = [sample]
        packet["capture_mode"] = "automatic"
        self.scripted.observations[packet["episode_id"]] = [fx.observation(fx.rest_frame_id(packet), fx.TAGGED_BBOX, label=identity.GLASSES,
                                                                           location="fixture cp4 shelf", calibration=identity.cp3_calibration())]
        self.ingest(packet)
        counts = self.store.process_pending(processor=self.scripted)
        self.assertEqual((counts["failed"], counts["pending"]), (0, 0), counts)
        return packet, counts

    def crop_window(self):
        from perception.identity import padded_crop_box
        return padded_crop_box(fx.TAGGED_BBOX, fx.SCENE_W, fx.SCENE_H)

    def test_geometry_of_the_recipe(self):
        from perception import hand_hull
        from perception.identity import CROP_PAD
        self.assertEqual(CROP_PAD, 0.10)
        self.assertEqual(hand_hull.HULL_DILATION, 0.03)
        self.assertEqual(hand_hull.HAND_HULL_WINDOW_MS, 150)
        px1, py1, px2, py2 = self.crop_window()
        self.assertEqual((px1, py1, px2, py2), (17, 37, 47, 67), "the 24 px square padded by 10 % on each side, floor/ceil")
        # The covering hand's dilated hull covers the whole padded crop; the corner hand's
        # dilated hull covers well under 25 % of it.
        covering = hand_hull.hand_hull_mask([hand_over(8, 28, 58, 78)], fx.SCENE_W, fx.SCENE_H)
        corner = hand_hull.hand_hull_mask([hand_over(8, 28, 18, 38)], fx.SCENE_W, fx.SCENE_H)
        self.assertEqual(float(covering[py1:py2, px1:px2].mean()), 1.0)
        corner_share = float(corner[py1:py2, px1:px2].mean())
        self.assertGreater(corner_share, 0.0, "the corner hull touches the crop")
        self.assertLess(corner_share, 0.25)

    def test_hull_covering_the_crop_refuses_the_embedding_and_stays_provisional(self):
        packet, counts = self.place_tagged_with_hand(hand_over(8, 28, 58, 78), offset_ms=50)
        self.assertEqual(counts.get("embedding_skipped_hand"), 1, counts)
        self.assertEqual(counts.get("embedded"), 0, counts)
        self.assertEqual(counts.get("embedding_failed"), 0, counts)
        self.assertEqual(self.embedder.calls, [], "the embedder is never asked to pool over a hand")
        self.assertEqual(self.rows("embeddings"), [], "no embeddings row")
        item = self.item_by_name(identity.GLASSES)
        self.assertEqual(item["identity_status"], "provisional", item)
        self.assertNotEqual(item["location_status"], "placed")
        self.assertIsNone(item["location_text"])
        record = self.store.item_history(item["item_id"])[0]
        self.assertEqual(record.get("match", {}).get("reason"), SKIPPED_REASON, record.get("match"))
        self.assertEqual(record.get("match", {}).get("state"), "new")
        evidence = self.store.item_evidence(item["item_id"])
        self.assertEqual([row["embedded"] for row in evidence], [False])
        self.assertNotEqual(self.store.answer_text(identity.ASK_GLASSES)["shape"], "confident")

    def test_hull_touching_only_a_corner_embeds_with_the_hull_masked_out(self):
        packet, counts = self.place_tagged_with_hand(hand_over(8, 28, 18, 38), offset_ms=50)
        self.assertEqual(counts.get("embedding_skipped_hand", 0), 0, counts)
        self.assertEqual(counts.get("embedded"), 1, counts)
        self.assertEqual(len(self.embedder.calls), 1)
        call = self.embedder.calls[0]
        self.assertEqual(call["tag"], 0)
        px1, py1, px2, py2 = self.crop_window()
        self.assertEqual(call["shape"], (py2 - py1, px2 - px1, 3), "the padded crop (recipe r2)")
        self.assertEqual(call["mask"], (py2 - py1, px2 - px1), "a hull-shaped mask travels with the crop")
        self.assertEqual(len(self.rows("embeddings")), 1)
        item = self.item_by_name(identity.GLASSES)
        self.assertEqual((item["identity_status"], item["location_status"]), ("trusted", "placed"), item)
        self.assertNotEqual(self.store.item_history(item["item_id"])[0].get("match", {}).get("reason"), SKIPPED_REASON)

    def test_a_sample_outside_the_window_applies_no_hull(self):
        # The covering hand, but 200 ms before the keyframe: outside HAND_HULL_WINDOW_MS,
        # so no hull applies and the embedding runs without a mask.
        packet, counts = self.place_tagged_with_hand(hand_over(8, 28, 58, 78), offset_ms=200)
        self.assertEqual(counts.get("embedding_skipped_hand", 0), 0, counts)
        self.assertEqual(counts.get("embedded"), 1, counts)
        self.assertEqual(len(self.embedder.calls), 1)
        self.assertIsNone(self.embedder.calls[0]["mask"], "no sample within 150 ms: no hull mask")
        self.assertEqual(self.item_by_name(identity.GLASSES)["identity_status"], "trusted")
        # And a sample inside the window with no hand is no hull either.
        self.scripted = identity.Cp3Processor()
        packet, counts = self.place_tagged_with_hand(None, offset_ms=50)
        self.assertEqual(counts.get("embedded"), 1, counts)
        self.assertIsNone(self.embedder.calls[-1]["mask"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
