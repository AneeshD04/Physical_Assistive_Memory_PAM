"""Local image evidence only; no semantic model, cloud client or identity inference."""
from __future__ import annotations

from typing import Literal
from pydantic import Field, model_validator
try:
    from .episode import EpisodePacket, StrictModel, decode_jpeg
except ImportError:
    from episode import EpisodePacket, StrictModel, decode_jpeg


class LocalObservation(StrictModel):
    """Trusted processor output, never accepted in an HTTP packet.

    bbox is capture-resolution [x1,y1,x2,y2]. calibration is an explicit
    provenance record, not an accuracy claim inferred from a confidence number.
    Continuity identifiers are scoped to the packet's device and session.
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

    @model_validator(mode="after")
    def valid_box(self):
        x1, y1, x2, y2 = self.bbox
        if not (0 <= x1 < x2 and 0 <= y1 < y2):
            raise ValueError("Invalid region")
        return self


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
        image = decode_jpeg(frame.jpeg_b64)
        if image.ndim == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.resize(image, (packet.analysis.width, packet.analysis.height))
    before, after = gray(first), gray(last)
    if min(float(before.std()), float(after.std())) < 8:
        return []
    points = cv2.goodFeaturesToTrack(before, 250, .02, 7)
    if points is None or len(points) < 12:
        return []
    tracked, status, _ = cv2.calcOpticalFlowPyrLK(before, after, points, None)
    if tracked is None or status is None:
        return []
    keep = status.ravel() == 1
    if int(keep.sum()) < 12:
        return []
    matrix, inliers = cv2.estimateAffinePartial2D(points[keep], tracked[keep], method=cv2.RANSAC, ransacReprojThreshold=2)
    if matrix is None or inliers is None or float(inliers.mean()) < .8:
        return []
    scale = float(np.linalg.norm(matrix[:, 0]))
    if not .95 <= scale <= 1.05 or float(np.linalg.norm(matrix[:, 2])) > min(before.shape) * .1:
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
        observations.append(LocalObservation(frame_id=last.frame_id, bbox=[x*sx, y*sy, (x+w)*sx, (y+h)*sy],
                                             confidence_basis="registered OpenCV difference; not object or identity recognition"))
    return observations
