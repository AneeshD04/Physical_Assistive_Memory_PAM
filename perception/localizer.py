"""Local image evidence only; no semantic model, cloud client or identity inference."""
from __future__ import annotations

from typing import Literal
from pydantic import Field, model_validator
try:
    from .episode import EpisodePacket, StrictModel, decode_jpeg
    from .identity import MAX_RLE_CHARS, RLE_SHAPE, crop_box, rle_from_mask
except ImportError:
    from episode import EpisodePacket, StrictModel, decode_jpeg
    from identity import MAX_RLE_CHARS, RLE_SHAPE, crop_box, rle_from_mask


class LocalObservation(StrictModel):
    """Trusted processor output, never accepted in an HTTP packet.

    bbox is capture-resolution [x1,y1,x2,y2]. calibration is an explicit
    provenance record, not an accuracy claim inferred from a confidence number.
    Continuity identifiers are scoped to the packet's device and session.
    mask_rle (CP3, optional) is the changed-pixel mask inside the bbox as
    identity.rle_from_mask output over the integer window identity.crop_box
    gives for this bbox at capture resolution; it only steers embedding pooling
    and is not stored with the observation.
    """
    frame_id: str = Field(min_length=1, max_length=100)
    bbox: list[float] = Field(min_length=4, max_length=4)
    label: str = Field(default="unknown", min_length=1, max_length=100)
    actor: Literal["wearer", "other_person", "unknown"] = "unknown"
    outcome: Literal["sighted", "placed_on_surface", "picked_up", "uncertain"] = "sighted"
    continuity_id: str | None = Field(default=None, max_length=160)
    identity_state: Literal["provisional", "ambiguous", "trusted"] = "provisional"
    location_text: str | None = Field(default=None, max_length=600)
    confidence: float = Field(default=0, ge=0, le=1)
    confidence_basis: str = Field(default="uncalibrated image region", max_length=600)
    calibration: dict = Field(default_factory=dict)
    mask_rle: str | None = Field(default=None, max_length=MAX_RLE_CHARS)

    @model_validator(mode="after")
    def valid_box(self):
        x1, y1, x2, y2 = self.bbox
        if not (0 <= x1 < x2 and 0 <= y1 < y2):
            raise ValueError("Invalid region")
        if self.mask_rle is not None and not RLE_SHAPE.fullmatch(self.mask_rle):
            raise ValueError("Invalid mask RLE")
        return self


# Registration bounds (initial values, unmeasured; shared by localize and the CP4
# re-observation stage so both accept exactly the same background registrations):
# flat frames, sparse features, a failed LK track, a poor RANSAC consensus, a scale
# outside 0.95..1.05 or a translation over 10 % of the short side all abstain.
MIN_STD = 8
MIN_FEATURES = 12
MIN_INLIER_RATIO = .8
SCALE_BOUNDS = (.95, 1.05)
MAX_TRANSLATION = .1


def register_frames(gray_a, gray_b):
    """Partial-affine registration of gray_a onto gray_b (both uint8 grayscale
    arrays of one shape): (matrix, inliers) with matrix the 2x3 cv2 affine that
    maps a-coordinates to b-coordinates and inliers the RANSAC inlier count, or
    (None, 0) when the registration is unsupported under the bounds above.
    Pure OpenCV LK + estimateAffinePartial2D; no model, no identity inference."""
    import cv2
    import numpy as np
    before, after = np.asarray(gray_a), np.asarray(gray_b)
    if before.ndim != 2 or before.shape != after.shape or before.dtype != np.uint8 or after.dtype != np.uint8 or before.size == 0:
        return None, 0
    if min(float(before.std()), float(after.std())) < MIN_STD:
        return None, 0
    points = cv2.goodFeaturesToTrack(before, 250, .02, 7)
    if points is None or len(points) < MIN_FEATURES:
        return None, 0
    tracked, status, _ = cv2.calcOpticalFlowPyrLK(before, after, points, None)
    if tracked is None or status is None:
        return None, 0
    keep = status.ravel() == 1
    if int(keep.sum()) < MIN_FEATURES:
        return None, 0
    matrix, inliers = cv2.estimateAffinePartial2D(points[keep], tracked[keep], method=cv2.RANSAC, ransacReprojThreshold=2)
    if matrix is None or inliers is None or float(inliers.mean()) < MIN_INLIER_RATIO:
        return None, 0
    scale = float(np.linalg.norm(matrix[:, 0]))
    if not SCALE_BOUNDS[0] <= scale <= SCALE_BOUNDS[1] or float(np.linalg.norm(matrix[:, 2])) > min(before.shape) * MAX_TRANSLATION:
        return None, 0
    return matrix, int(inliers.sum())


def gray_at(encoded, width, height):
    """A keyframe's JPEG decoded to grayscale and resized to (width, height)."""
    import cv2
    image = decode_jpeg(encoded)
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.resize(image, (width, height))


def localize(packet: EpisodePacket) -> list[LocalObservation]:
    """Conservative registered frame differences, or none.

    Require a supported background registration and a bounded changed region.
    A region is only a provisional sighting: light, hands and clutter may change.
    Identical/flat frames, sparse features, camera cuts and broad motion abstain.
    """
    import cv2
    import numpy as np
    if len(packet.keyframes) < 2:
        return []
    first, last = packet.keyframes[0], packet.keyframes[-1]
    def gray(frame):
        return gray_at(frame.jpeg_b64, packet.analysis.width, packet.analysis.height)
    before, after = gray(first), gray(last)
    matrix, _ = register_frames(before, after)
    if matrix is None:
        return []
    warped = cv2.warpAffine(before, matrix, (before.shape[1], before.shape[0]))
    valid = cv2.warpAffine(np.full_like(before, 255), matrix, (before.shape[1], before.shape[0]))
    valid = cv2.erode(valid, np.ones((7, 7), np.uint8))
    delta = cv2.absdiff(warped, after)
    mask = ((delta > 30) & (valid == 255)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    if not .002 <= float(np.count_nonzero(mask)) / mask.size <= .2:
        return []
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    observations = []
    sx, sy = packet.capture.width / before.shape[1], packet.capture.height / before.shape[0]
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:4]:
        if cv2.contourArea(contour) < max(12, mask.size * .002):
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if w * h > mask.size * .25:
            continue
        bbox = [x*sx, y*sy, (x+w)*sx, (y+h)*sy]
        # CP3: the diff mask inside this region, resized (nearest) to the integer
        # capture-resolution window the store will crop, as a bounded RLE. It only
        # steers which patches the identity embedder pools; a mask too long to
        # bound is dropped (None) and the embedder then pools every patch.
        cx1, cy1, cx2, cy2 = crop_box(bbox, packet.capture.width, packet.capture.height)
        region = cv2.resize(mask[y:y+h, x:x+w], (cx2 - cx1, cy2 - cy1), interpolation=cv2.INTER_NEAREST)
        rle = rle_from_mask(region > 0)
        observations.append(LocalObservation(frame_id=last.frame_id, bbox=bbox,
                                             confidence_basis="registered OpenCV difference; not object or identity recognition",
                                             mask_rle=rle if len(rle) <= MAX_RLE_CHARS else None))
    return observations
