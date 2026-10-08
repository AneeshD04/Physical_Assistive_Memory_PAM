"""Strict, untrusted wire packets. No identity or processor fields cross this boundary."""
from __future__ import annotations

import base64
import hashlib
import json
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_PACKET_BYTES = 4 * 1024 * 1024
MAX_TIME = 9007199254740991
Millis = Annotated[int, Field(ge=0, le=MAX_TIME)]


class PacketTooLarge(ValueError):
    pass


class RevisionLimitError(ValueError):
    pass


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class Dimensions(StrictModel):
    width: int = Field(ge=1, le=1920)
    height: int = Field(ge=1, le=1920)

    @model_validator(mode="after")
    def area(self):
        if self.width * self.height > 2073600:
            raise ValueError("Image dimensions too large")
        return self


class ClockAnchor(StrictModel):
    mono_ms: Millis
    wall_ms: int = Field(gt=0, le=MAX_TIME)


class Keyframe(StrictModel):
    frame_id: str = Field(min_length=1, max_length=100)
    t_ms: Millis
    role: Literal["pre_contact", "hand_busy", "carry", "release", "rest"]
    jpeg_b64: str = Field(min_length=1, max_length=MAX_PACKET_BYTES)


class BurstFrame(Dimensions):
    frame_id: str = Field(min_length=1, max_length=100)
    t_ms: Millis
    jpeg_b64: str = Field(min_length=1, max_length=MAX_PACKET_BYTES)


class Point(StrictModel):
    x: float
    y: float
    z: float


class ImagePoint(Point):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class Hand(StrictModel):
    landmarks: list[ImagePoint] = Field(min_length=21, max_length=21)
    world_landmarks: list[Point] | None = Field(default=None, min_length=21, max_length=21)
    hand_bbox: list[float] = Field(min_length=4, max_length=4)
    handedness: Literal["left", "right", "unknown"]

    @model_validator(mode="after")
    def box(self):
        x1, y1, x2, y2 = self.hand_bbox
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise ValueError("Invalid hand box")
        return self


class LandmarkSample(StrictModel):
    frame_id: str = Field(min_length=1, max_length=100)
    t_ms: Millis
    hands: list[Hand] = Field(default_factory=list, max_length=2)


class Gap(StrictModel):
    t_from_ms: Millis
    t_to_ms: Millis
    reason: str = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def ordered(self):
        if self.t_from_ms > self.t_to_ms:
            raise ValueError("Invalid gap interval")
        return self


def jpeg_bytes(encoded: str) -> bytes:
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Invalid JPEG base64") from exc
    if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        raise ValueError("Invalid JPEG")
    return data


def decode_jpeg(encoded: str):
    import cv2
    import numpy as np
    data = jpeg_bytes(encoded)
    # Inspect SOF before allocating a decoder buffer: a small transport body can
    # otherwise advertise enormous dimensions. JPEG has big-endian segment lengths.
    offset, dimensions = 2, None
    while offset < len(data):
        if data[offset] != 255:
            raise ValueError("Invalid JPEG header")
        while offset < len(data) and data[offset] == 255:
            offset += 1
        if offset >= len(data):
            raise ValueError("Invalid JPEG header")
        marker = data[offset]
        offset += 1
        if marker in (0xDA, 0xD9):
            break
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(data):
            raise ValueError("Invalid JPEG header")
        length = int.from_bytes(data[offset:offset+2], "big")
        if length < 2 or offset + length > len(data):
            raise ValueError("Invalid JPEG segment")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            if length < 8 or dimensions is not None:
                raise ValueError("Invalid JPEG dimensions")
            height = int.from_bytes(data[offset+3:offset+5], "big")
            width = int.from_bytes(data[offset+5:offset+7], "big")
            if not 1 <= width <= 1920 or not 1 <= height <= 1920 or width*height > 2073600:
                raise ValueError("JPEG dimensions too large")
            dimensions = (height, width)
        offset += length
    if dimensions is None:
        raise ValueError("Missing JPEG dimensions")
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError("Invalid JPEG")
    return image


class EpisodePacket(StrictModel):
    schema_version: Literal[1]
    episode_id: str
    device_id: str
    session_id: str
    t_start_ms: Millis
    t_end_ms: Millis
    clock_anchor: ClockAnchor
    capture: Dimensions
    analysis: Dimensions
    keyframes: list[Keyframe] = Field(min_length=1, max_length=8)
    carry_burst: list[BurstFrame] = Field(default_factory=list, max_length=10)
    landmarks: list[LandmarkSample] = Field(default_factory=list, max_length=128)
    gaps: list[Gap] = Field(default_factory=list, max_length=32)
    outcome_hint: Literal["released", "hand_gone", "gap"]
    capture_mode: Literal["manual", "automatic"]

    @model_validator(mode="before")
    @classmethod
    def strict_version(cls, value):
        if isinstance(value, dict) and type(value.get("schema_version")) is not int:
            raise ValueError("Schema version must be an integer")
        return value

    @model_validator(mode="after")
    def evidence(self):
        for value in (self.episode_id, self.device_id, self.session_id):
            if str(uuid.UUID(value)) != value.lower():
                raise ValueError("Invalid UUID")
        if self.t_start_ms > self.t_end_ms:
            raise ValueError("Invalid episode interval")
        if self.analysis.width > self.capture.width or self.analysis.height > self.capture.height:
            raise ValueError("Analysis exceeds capture dimensions")
        for frames in (self.keyframes, self.carry_burst, self.landmarks):
            ids = set()
            last = -1
            for frame in frames:
                if frame.frame_id in ids or not self.t_start_ms <= frame.t_ms <= self.t_end_ms or frame.t_ms <= last:
                    raise ValueError("Invalid frame ordering or duplicate frame ID")
                ids.add(frame.frame_id)
                last = frame.t_ms
        for frame in self.keyframes:
            image = decode_jpeg(frame.jpeg_b64)
            if image.shape[:2] != (self.capture.height, self.capture.width):
                raise ValueError("JPEG dimensions do not match capture")
        for frame in self.carry_burst:
            if (frame.width, frame.height) != (self.analysis.width, self.analysis.height):
                raise ValueError("Burst dimensions do not match analysis")
            image = decode_jpeg(frame.jpeg_b64)
            if image.ndim != 2 or image.shape != (frame.height, frame.width):
                raise ValueError("Burst must be analysis-resolution grayscale JPEG")
        return self

    def semantic_digest(self) -> str:
        body = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(body.encode()).hexdigest()


def parse_packet(raw: bytes) -> EpisodePacket:
    if not isinstance(raw, bytes):
        raise ValueError("Packet must be bytes")
    if len(raw) > MAX_PACKET_BYTES:
        raise PacketTooLarge("Packet exceeds 4 MiB")
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
        return EpisodePacket.model_validate(value)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid packet JSON") from exc
