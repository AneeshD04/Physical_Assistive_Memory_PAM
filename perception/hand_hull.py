"""Hand hull exclusion for the identity crop (CP4, CP3 deferral 7).

A hand that is still touching or occluding the object at the rest keyframe would
otherwise be pooled into the item's appearance embedding. ``hand_hull_mask`` turns
the 21 image-normalised landmarks of each hand into a filled convex hull, dilated
by HULL_DILATION of the frame width with an elliptical kernel, and the store
removes that region from the crop's pooling mask (perception/episode_store.py,
``_embed_region``). The rule is part of embedder recipe r2 (perception/identity.py).

Initial, unmeasured values: the 3 % dilation and the 150 ms sample window
(HAND_HULL_WINDOW_MS) come from the build plan and await the rig experiments.
Nothing here recognises a hand: the landmarks are whatever the packet carried.
"""
from __future__ import annotations

import math

import numpy as np

HULL_DILATION = 0.03          # of the frame width, each side
HAND_HULL_WINDOW_MS = 150     # a landmark sample this close to the keyframe applies
LANDMARK_COUNT = 21


def _point(value):
    if hasattr(value, "x") and hasattr(value, "y"):
        x, y = value.x, value.y
    elif isinstance(value, dict):
        x, y = value.get("x"), value.get("y")
    else:
        raise ValueError("Invalid hand landmark")
    for coordinate in (x, y):
        if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)) or not math.isfinite(coordinate):
            raise ValueError("Invalid hand landmark")
    return float(x), float(y)


def _landmarks(hand):
    points = hand.landmarks if hasattr(hand, "landmarks") else hand.get("landmarks") if isinstance(hand, dict) else None
    if not isinstance(points, (list, tuple)) or len(points) != LANDMARK_COUNT:
        raise ValueError("Hand must carry exactly 21 landmarks")
    return [_point(point) for point in points]


def hand_hull_mask(hands, width, height) -> np.ndarray:
    """bool array (height, width): True inside the dilated convex hull of any hand.

    hands: a list of perception.episode.Hand models or packet-shaped dicts
    ({"landmarks": [{x, y, z} x 21], ...}); x and y are image-normalised 0..1.
    An empty list gives an all-False mask. ValueError on malformed input.
    """
    import cv2
    if type(width) is not int or type(height) is not int or width < 1 or height < 1:
        raise ValueError("Invalid frame size")
    if not isinstance(hands, (list, tuple)):
        raise ValueError("Hands must be a list")
    mask = np.zeros((height, width), dtype=np.uint8)
    for hand in hands:
        points = _landmarks(hand)
        pixels = np.array([[min(max(x, 0.0), 1.0) * (width - 1), min(max(y, 0.0), 1.0) * (height - 1)]
                           for x, y in points], dtype=np.float32).reshape(-1, 1, 2)
        hull = cv2.convexHull(pixels)
        cv2.fillConvexPoly(mask, np.round(hull).astype(np.int32), 255)
    if not mask.any():
        return mask.astype(bool)
    radius = int(round(HULL_DILATION * width))
    if radius > 0:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
        mask = cv2.dilate(mask, kernel)
    return mask > 0


def nearest_sample(samples, t_ms, window_ms=HAND_HULL_WINDOW_MS):
    """The landmark sample whose t_ms is nearest to t_ms within window_ms (ties:
    the earlier one), or None. samples are perception.episode.LandmarkSample
    models or dicts with t_ms; a sample without hands still counts (no hull)."""
    best, best_gap = None, None
    for sample in samples or ():
        value = sample.t_ms if hasattr(sample, "t_ms") else sample.get("t_ms") if isinstance(sample, dict) else None
        if type(value) is not int:
            continue
        gap = abs(value - t_ms)
        if gap <= window_ms and (best_gap is None or gap < best_gap):
            best, best_gap = sample, gap
    return best
