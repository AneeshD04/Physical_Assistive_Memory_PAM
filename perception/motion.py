"""Non-neural motion energy on the analysis-resolution grayscale frame (CP2).

Pure functions over plain pixel buffers; numpy only, no OpenCV. The browser port
(phone/assets/motion.js, Builder C) implements the identical arithmetic and the
tester's golden two-frame arrays pin that arithmetic bit for bit, not the product
thresholds.

Arithmetic, normative for both languages:

1. ``box_blur3``: for every pixel, the integer sum of its 3x3 neighbourhood with
   edge pixels replicated (the border re-uses the nearest in-image pixel), floor
   divided by 9. Output is uint8 again (the sum of nine 0..255 values divided by 9
   never exceeds 255). No floating point is involved.
2. ``motion_energy``: S = sum over pixels of |blur(next) - blur(prev)| (an exact
   integer), D = width * height * 255. The energy is S / D rounded half up to six
   decimals, done as an exact integer operation so both languages agree on ties::

       scaled = floor((2 * S * 1000000 + D) / (2 * D))      # integer arithmetic
       energy = scaled / 1000000                            # one float64 division

   ``moving`` is the memoryless threshold ``energy >= MOTION_ON``.
3. ``motion_step``: explicit hysteresis. Not moving -> moving when
   ``energy >= MOTION_ON``; moving -> not moving when ``energy < MOTION_OFF``.

MOTION_ON and MOTION_OFF are INITIAL VALUES, not measurements. They are to be
measured on the rig (experiment P-105) and will change; nothing in this module
claims they separate real hand motion from noise on any device.
"""
from __future__ import annotations

import math

import numpy as np

# Initial values pending rig measurement (P-105). Mirrored in phone/assets/motion.js.
MOTION_ON = 0.035
MOTION_OFF = 0.015

# Same bounds as perception.episode.Dimensions, so a frame that fits a packet fits here
# and the JS port's integer arithmetic stays inside Number.MAX_SAFE_INTEGER.
MAX_SIDE = 1920
MAX_AREA = 2073600


def _dimension(value, name):
    if type(value) is not int or not 1 <= value <= MAX_SIDE:
        raise ValueError(f"Invalid frame {name}")
    return value


def _frame(value, width, height, name) -> np.ndarray:
    """Coerce bytes/bytearray/list/ndarray into a uint8 (height, width) array."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        pixels = np.frombuffer(bytes(value), dtype=np.uint8)
    elif isinstance(value, (list, tuple)):
        pixels = np.asarray(value)
    elif isinstance(value, np.ndarray):
        pixels = value
    else:
        raise ValueError(f"Unsupported {name} frame type")
    if pixels.ndim == 2:
        if pixels.shape != (height, width):
            raise ValueError(f"{name} frame shape does not match width and height")
    elif pixels.ndim == 1:
        if pixels.size != width * height:
            raise ValueError(f"{name} frame length does not match width and height")
        pixels = pixels.reshape(height, width)
    else:
        raise ValueError(f"{name} frame must be a flat buffer or a height x width array")
    if pixels.dtype != np.uint8:
        if pixels.size and (not np.issubdtype(pixels.dtype, np.integer)
                            or int(pixels.min()) < 0 or int(pixels.max()) > 255):
            raise ValueError(f"{name} frame pixels must be integers 0..255")
        pixels = pixels.astype(np.uint8)
    return pixels


def box_blur3(gray: np.ndarray) -> np.ndarray:
    """3x3 box blur, integer sum floor-divided by 9, edges replicated.

    gray: uint8 array of shape (height, width). Returns a new uint8 array of the
    same shape. Deterministic and integer-exact; the JS port must produce the
    same bytes.
    """
    pixels = np.asarray(gray)
    if pixels.ndim != 2 or pixels.dtype != np.uint8 or pixels.size == 0:
        raise ValueError("box_blur3 expects a non-empty uint8 height x width array")
    padded = np.pad(pixels, 1, mode="edge").astype(np.int32)
    total = np.zeros(pixels.shape, dtype=np.int32)
    height, width = pixels.shape
    for dy in range(3):
        for dx in range(3):
            total += padded[dy:dy + height, dx:dx + width]
    return (total // 9).astype(np.uint8)


def motion_energy(prev, next, width, height) -> dict:
    """Blurred mean absolute difference over the frame, in 0..1, plus the
    memoryless threshold verdict.

    prev/next: bytes, bytearray, list or numpy array of exactly width*height
    grayscale pixels (0..255), or a (height, width) array. Raises ValueError on
    any shape, length, type or range mismatch. Returns
    {"energy": float rounded to 6 decimals, "moving": energy >= MOTION_ON}.
    """
    width = _dimension(width, "width")
    height = _dimension(height, "height")
    if width * height > MAX_AREA:
        raise ValueError("Frame area too large")
    before = box_blur3(_frame(prev, width, height, "prev")).astype(np.int32)
    after = box_blur3(_frame(next, width, height, "next")).astype(np.int32)
    total = int(np.abs(after - before).sum())
    denominator = width * height * 255
    scaled = (2 * total * 1000000 + denominator) // (2 * denominator)
    energy = scaled / 1000000
    return {"energy": energy, "moving": energy >= MOTION_ON}


def motion_step(state: dict | None, energy: float) -> tuple[dict, bool]:
    """Explicit hysteresis over successive energies.

    state: None (initial, not moving) or {"moving": bool}. Returns the new state
    and the moving flag. Off -> on at energy >= MOTION_ON; on -> off at
    energy < MOTION_OFF; otherwise the previous verdict holds. The thresholds are
    initial values (P-105).
    """
    if state is None:
        moving = False
    elif isinstance(state, dict) and type(state.get("moving")) is bool:
        moving = state["moving"]
    else:
        raise ValueError("Invalid motion state")
    if isinstance(energy, bool) or not isinstance(energy, (int, float)) or not math.isfinite(energy):
        raise ValueError("Invalid motion energy")
    if moving:
        moving = not energy < MOTION_OFF
    else:
        moving = energy >= MOTION_ON
    return {"moving": moving}, moving
