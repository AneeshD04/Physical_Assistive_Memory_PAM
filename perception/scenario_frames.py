"""Deterministic synthetic scenes for the CP5 scenario runner. SYNTHETIC ONLY.

Nothing here resembles a real camera frame; it exists so that the ledger, the
re-observation stage, the resolver and the rubric can be exercised end to end on
scripted cases before any footage exists (Part 1 section 10 item 5). The server
never imports this module.

A scene is a seeded smooth-blob texture (random 4 px cells upscaled with cubic
interpolation, so every neighbourhood has unique structure) with one painted
block per visible item. The CP4 tester measured that a periodic checkerboard
aliases under pyramidal Lucas-Kanade once a block is removed (the registration
then refuses the "gone" frame), which is why the texture is a blob field.

Each block is a white frame around a tagged core: the white frame gives the
registered region difference a large, tag-independent contrast (an absent block
reads "gone" under perception.reobservation's initial thresholds), and the core
carries an instance tag in the GREEN channel of a saturated blue, which
SyntheticTagEmbedder reads back. The tag convention (TAG_BASE + TAG_STEP * tag,
7 tags, pairs (0, 1) and (2, 4) lookalikes) matches the tester's CP3 fixture so
the same calibration quantiles apply; this module does not import the tests.
"""
from __future__ import annotations

import base64
import hashlib
import math

SCENE_W, SCENE_H = 160, 120
ANALYSIS_W, ANALYSIS_H = 80, 60
TEXTURE_SEED, TEXTURE_CELL, TEXTURE_PAD = 2026, 4, 16
JPEG_QUALITY = 90
TAG_BASE, TAG_STEP, TAG_COUNT = 30, 36, 7
# The white frame is this share of the block's width (and height) on each side;
# the tagged core is what remains. A 24 px block keeps a 12 px core.
BORDER_FRACTION = 0.25
# Block side bounds (pixels). Measured on this texture (2026-10-10, 160x120 scene):
# blocks of 16..40 px decode their tag at JPEG quality 50..90 and read present
# (<= 0.008) / gone (>= 0.25) under perception.reobservation's thresholds; a 60 px
# block (19 % of the frame) defeats the LK registration once it vanishes, so the
# cap keeps a block under ~12 % of the frame.
MIN_BLOCK = 16
MAX_BLOCK = 48
WHITE = (255, 255, 255)
LOOKALIKE_PAIRS = ((0, 1), (2, 4))
LOOKALIKE_COS = 0.90
NOISE_EPS = 0.1428  # 1 / (1 + eps^2) = 0.98: the same-tag cosine

_TEXTURES = {}


def tag_colour(tag) -> tuple:
    """BGR colour of the core carrying instance tag `tag` (0..TAG_COUNT-1)."""
    if type(tag) is not int or not 0 <= tag < TAG_COUNT:
        raise ValueError("tag out of range")
    return (230, TAG_BASE + TAG_STEP * tag, 30)


def texture(seed=TEXTURE_SEED, width=SCENE_W, height=SCENE_H):
    """The padded grey blob texture for a scene size (cached per seed and size)."""
    import cv2
    import numpy as np
    key = (seed, width, height)
    if key not in _TEXTURES:
        rng = np.random.default_rng(seed)
        shape = ((height + 2 * TEXTURE_PAD) // TEXTURE_CELL, (width + 2 * TEXTURE_PAD) // TEXTURE_CELL)
        coarse = rng.integers(20, 236, shape).astype(np.uint8)
        _TEXTURES[key] = cv2.resize(coarse, (width + 2 * TEXTURE_PAD, height + 2 * TEXTURE_PAD), interpolation=cv2.INTER_CUBIC)
    return _TEXTURES[key]


def check_bbox(bbox, width=SCENE_W, height=SCENE_H) -> list:
    """An item bbox as four ints [x1, y1, x2, y2] inside the scene, at least
    MIN_BLOCK on each side (ValueError otherwise)."""
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise ValueError("bbox must be [x1, y1, x2, y2]")
    try:
        x1, y1, x2, y2 = (int(v) for v in bbox)
    except (TypeError, ValueError):
        raise ValueError("bbox must be numeric") from None
    if any(isinstance(v, bool) or not math.isfinite(float(v)) or float(v) != int(v) for v in bbox):
        raise ValueError("bbox must be whole pixels")
    if not (0 <= x1 and 0 <= y1 and x2 <= width and y2 <= height):
        raise ValueError("bbox outside the scene")
    if not (MIN_BLOCK <= x2 - x1 <= MAX_BLOCK and MIN_BLOCK <= y2 - y1 <= MAX_BLOCK):
        raise ValueError("block side must be between MIN_BLOCK and MAX_BLOCK pixels")
    return [x1, y1, x2, y2]


def render_scene(blocks=(), *, width=SCENE_W, height=SCENE_H, seed=TEXTURE_SEED, dx=0, dy=0):
    """BGR uint8 scene: the texture shifted by (dx, dy) pixels (|dx|, |dy| <=
    TEXTURE_PAD) and one block per (bbox, tag) in `blocks`, painted in order."""
    import numpy as np
    if not (abs(dx) <= TEXTURE_PAD and abs(dy) <= TEXTURE_PAD):
        raise ValueError("translation exceeds the texture padding")
    grey = texture(seed, width, height)[TEXTURE_PAD - dy:TEXTURE_PAD - dy + height, TEXTURE_PAD - dx:TEXTURE_PAD - dx + width]
    image = np.repeat(grey[:, :, None], 3, axis=2).copy()
    for bbox, tag in blocks:
        x1, y1, x2, y2 = check_bbox(bbox, width, height)
        bx, by = int(round((x2 - x1) * BORDER_FRACTION)), int(round((y2 - y1) * BORDER_FRACTION))
        image[y1 + dy:y2 + dy, x1 + dx:x2 + dx] = WHITE
        image[y1 + by + dy:y2 - by + dy, x1 + bx + dx:x2 - bx + dx] = tag_colour(tag)
    return image


def encode_jpeg(image, quality=JPEG_QUALITY) -> bytes:
    import cv2
    ok, data = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("JPEG encoding failed")
    return data.tobytes()


def scene_jpeg(blocks=(), *, quality=JPEG_QUALITY, **kwargs) -> bytes:
    return encode_jpeg(render_scene(blocks, **kwargs), quality)


def scene_jpeg_b64(blocks=(), **kwargs) -> str:
    return base64.b64encode(scene_jpeg(blocks, **kwargs)).decode("ascii")


def read_tag(crop, mask=None) -> int:
    """The instance tag painted in an RGB or BGR uint8 crop (the green channel is
    the middle one either way), or ValueError when no tagged core is in view.
    Tagged pixels have max(B, R) >= 150 and min(B, R) <= 90, which excludes the
    grey texture (B == R) and the white frame."""
    import numpy as np
    if not isinstance(crop, np.ndarray) or crop.ndim != 3 or crop.shape[2] != 3 or crop.dtype != np.uint8:
        raise ValueError("expected an HxWx3 uint8 crop")
    pixels = crop.reshape(-1, 3).astype(int)
    if mask is not None:
        mask = np.asarray(mask).astype(bool)
        if mask.shape != crop.shape[:2]:
            raise ValueError("mask does not match the crop")
        if mask.any():
            pixels = crop[mask].astype(int)
    outer = np.maximum(pixels[:, 0], pixels[:, 2])
    inner = np.minimum(pixels[:, 0], pixels[:, 2])
    tagged = pixels[(outer >= 150) & (inner <= 90)]
    if len(tagged) < 4:
        raise ValueError("no tagged core in the crop")
    green = float(np.median(tagged[:, 1]))
    tag = int(round((green - TAG_BASE) / TAG_STEP))
    if not 0 <= tag < TAG_COUNT or abs(green - (TAG_BASE + TAG_STEP * tag)) > 12:
        raise ValueError("tag could not be decoded")
    return tag


class SyntheticTagEmbedder:
    """A deterministic stand-in for the identity embedder, for scenarios only.

    It recognises PAINTED TAGS, not objects: the vector is a seeded prototype
    for the tag plus bounded noise in a disjoint subspace, so cosines are fixed
    by construction (same tag ~0.98, lookalike pairs ~0.88, otherwise ~0.0). It
    satisfies perception.identity.Embedder (name, version, dim, embed) and is
    attached through the store's embedder hook by the scenario runner; the server
    never constructs it, and a calibration it is used with must say source
    "synthetic".
    """
    name = "synthetic-scenario"
    version = "1"

    def __init__(self, dim=16, eps=NOISE_EPS):
        import numpy as np
        if type(dim) is not int or dim < 16:
            raise ValueError("SyntheticTagEmbedder needs dim >= 16")
        self.dim, self.eps = dim, eps
        self.calls = 0
        basis = np.eye(dim, dtype=np.float64)
        side = math.sqrt(1 - LOOKALIKE_COS ** 2)
        self.prototypes = {0: basis[0], 1: LOOKALIKE_COS * basis[0] + side * basis[1],
                           2: basis[2], 3: basis[3], 4: LOOKALIKE_COS * basis[2] + side * basis[4],
                           5: basis[5], 6: basis[6]}

    @property
    def tag(self) -> str:
        return f"{self.name}@{self.version}"

    def vector(self, tag, draw):
        import numpy as np
        rng = np.random.default_rng(int(draw) & 0xFFFFFFFF)
        noise = np.zeros(self.dim)
        direction = rng.standard_normal(self.dim - 8)
        noise[8:] = direction / np.linalg.norm(direction)
        value = self.prototypes[tag] + self.eps * noise
        return (value / np.linalg.norm(value)).astype(np.float32)

    def embed(self, crop, mask=None):
        import numpy as np
        self.calls += 1
        tag = read_tag(crop, mask)
        draw = int(hashlib.sha256(np.ascontiguousarray(crop).tobytes()).hexdigest()[:8], 16)
        return self.vector(tag, draw)
