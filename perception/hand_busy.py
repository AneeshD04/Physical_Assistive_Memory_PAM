"""Hand-busy heuristic over packet landmark samples (CP2).

Pure function, no model and no OpenCV. ``busy`` means "the hand looks like it is
doing something", not contact and not ownership; the basis string says which rule
fired. The browser port (phone/assets/hand-busy.js, Builder C) implements the
identical arithmetic and the tester runs both on the same landmark fixtures.

Input is the packet format (perception.episode.Hand): each hand is
{"landmarks": [{x, y, z} x 21], "world_landmarks": [...] or None,
"hand_bbox": [x1, y1, x2, y2] normalised 0..1, "handedness": str}. Landmarks use
MediaPipe's 21-point index convention (0 wrist; 1-4 thumb; 5-8 index; 9-12 middle;
13-16 ring; 17-20 little; 5/9/13/17 are the MCP knuckles, 4/8/12/16/20 the tips).

Arithmetic, normative for both languages (image-normalised x and y only; z and
world_landmarks are ignored, so the measure lives in the stretched image space of
a non-square frame; that is a known limitation of this heuristic, not a bug):

1. The hand considered is the one with the largest bbox area
   (x2 - x1) * (y2 - y1); the first wins a tie.
2. palm_centre = mean of landmarks 0, 5, 9, 13, 17 (sum in that order, / 5).
3. reference = sqrt(dx*dx + dy*dy) between landmark 0 and landmark 9, with
   sqrt() not hypot() so both languages round identically.
4. curl_ratio = (sum over tips 4, 8, 12, 16, 20 of dist(tip, palm_centre) /
   reference) / 5, in that order. curled = curl_ratio < CURL_RATIO.
5. lower = (y1 + y2) / 2 > LOWER_FRAME_Y and (x2 - x1) * (y2 - y1) >= LOWER_FRAME_MIN_AREA.
6. busy = curled or lower; basis "curled" | "lower-frame" | "curled+lower-frame" |
   "open hand". No hand: present False, busy None, basis "no hand". reference below
   DEGENERATE_REFERENCE: busy None, basis "degenerate hand" (a missing measurement
   never settles the controller).

CURL_RATIO, LOWER_FRAME_Y and LOWER_FRAME_MIN_AREA are INITIAL VALUES from the
build plan, not measurements; they await the rig experiments (P-101/P-103).
"""
from __future__ import annotations

import math

# Initial values pending rig measurement. Mirrored in phone/assets/hand-busy.js.
CURL_RATIO = 0.55
LOWER_FRAME_Y = 0.40          # bbox centre y above this is "the lower 60% of the frame"
LOWER_FRAME_MIN_AREA = 0.02   # bbox area as a fraction of the frame
DEGENERATE_REFERENCE = 1e-6

WRIST = 0
MIDDLE_MCP = 9
PALM_INDICES = (0, 5, 9, 13, 17)
FINGERTIP_INDICES = (4, 8, 12, 16, 20)
LANDMARK_COUNT = 21


def _number(value, what):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"Invalid {what}")
    return float(value)


def _validate_hand(hand) -> tuple[list[tuple[float, float]], tuple[float, float, float, float]]:
    if not isinstance(hand, dict):
        raise ValueError("Invalid hand sample")
    landmarks = hand.get("landmarks")
    if not isinstance(landmarks, list) or len(landmarks) != LANDMARK_COUNT:
        raise ValueError("Hand must carry exactly 21 landmarks")
    points = []
    for point in landmarks:
        if not isinstance(point, dict):
            raise ValueError("Invalid hand landmark")
        x, y = _number(point.get("x"), "landmark x"), _number(point.get("y"), "landmark y")
        if "z" in point:
            _number(point.get("z"), "landmark z")
        points.append((x, y))
    bbox = hand.get("hand_bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ValueError("Invalid hand box")
    x1, y1, x2, y2 = (_number(value, "hand box") for value in bbox)
    if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
        raise ValueError("Invalid hand box")
    return points, (x1, y1, x2, y2)


def _distance(a, b) -> float:
    dx, dy = a[0] - b[0], a[1] - b[1]
    return math.sqrt(dx * dx + dy * dy)


def hand_metrics(hand: dict) -> dict:
    """The intermediate numbers behind hand_busy for one hand, for cross-language
    comparison: reference, palm_centre [x, y], curl_ratio (None when degenerate),
    bbox_centre_y and bbox_area."""
    points, (x1, y1, x2, y2) = _validate_hand(hand)
    # Explicit left-to-right accumulation in index order, never builtin sum():
    # CPython >= 3.12 compensates float sum() (Neumaier), 3.11 does not, and the
    # JS port adds plainly. This keeps every interpreter bit-identical.
    palm_x = 0.0
    palm_y = 0.0
    for i in PALM_INDICES:
        palm_x += points[i][0]
        palm_y += points[i][1]
    palm_x /= 5
    palm_y /= 5
    reference = _distance(points[WRIST], points[MIDDLE_MCP])
    curl_ratio = None
    if reference >= DEGENERATE_REFERENCE:
        total = 0.0
        for i in FINGERTIP_INDICES:
            total += _distance(points[i], (palm_x, palm_y)) / reference
        curl_ratio = total / 5
    return {"reference": reference, "palm_centre": [palm_x, palm_y], "curl_ratio": curl_ratio,
            "bbox_centre_y": (y1 + y2) / 2, "bbox_area": (x2 - x1) * (y2 - y1)}


def hand_busy(hands: list[dict]) -> dict:
    """{"present": bool, "busy": bool | None, "basis": str} for a landmark sample.

    Raises ValueError on malformed input (wrong landmark count, non-finite or
    non-numeric coordinates, an invalid bbox). An empty list is not malformed: it
    is the honest "no hand" measurement.
    """
    if not isinstance(hands, list):
        raise ValueError("Hands must be a list")
    if not hands:
        return {"present": False, "busy": None, "basis": "no hand"}
    validated = [_validate_hand(hand) for hand in hands]
    chosen, chosen_area = None, -1.0
    for hand, (_, (x1, y1, x2, y2)) in zip(hands, validated):
        area = (x2 - x1) * (y2 - y1)
        if area > chosen_area:
            chosen, chosen_area = hand, area
    metrics = hand_metrics(chosen)
    if metrics["curl_ratio"] is None:
        return {"present": True, "busy": None, "basis": "degenerate hand"}
    curled = metrics["curl_ratio"] < CURL_RATIO
    lower = metrics["bbox_centre_y"] > LOWER_FRAME_Y and metrics["bbox_area"] >= LOWER_FRAME_MIN_AREA
    if curled and lower:
        basis = "curled+lower-frame"
    elif curled:
        basis = "curled"
    elif lower:
        basis = "lower-frame"
    else:
        basis = "open hand"
    return {"present": True, "busy": curled or lower, "basis": basis}
