"""Identity stage (CP3): appearance embeddings, per-item banks, conformal same-object sets.

Nothing here is a recognizer on its own. An Embedder turns a localized crop into
an L2-normalised vector; an ItemBank holds the vectors already assigned to one
item; a ConformalMatcher turns cosine scores into a "same object" set whose size
decides new | match | ambiguous. The set is only as good as the calibration
quantile it was given, which is why the store keeps calibration records behind an
explicit approval gate (perception/episode_store.py). The production embedder is
DinoV2Embedder over ONNX Runtime; it is constructed only when the server's model
manifest gate allows it, and a missing file is a loud ValueError, never a
simulated result. Tests inject a deterministic Embedder subclass.

Initial, unmeasured values (to be replaced by P-104 measurements on the laptop):
the 50 % patch-overlap rule for mask pooling, the minimum of 4 qualifying
patches, alpha = 0.05 and the bank size of 32.
"""
from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

import numpy as np

# DINOv2 ViT-S/14 geometry: 224 px input, 14 px patches, 16 x 16 = 256 patch tokens, 384-d.
DINOV2_INPUT = 224
DINOV2_PATCH = 14
DINOV2_DIM = 384
DINOV2_GRID = DINOV2_INPUT // DINOV2_PATCH
DINOV2_PATCHES = DINOV2_GRID * DINOV2_GRID
# ImageNet normalisation, the DINOv2 preprocessing convention.
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
# Initial values (unmeasured): a patch counts as "on the object" when at least half
# of its pixels are inside the mask; fewer than 4 such patches is too thin a basis.
MASK_PATCH_OVERLAP = 0.5
MIN_MASK_PATCHES = 4
BANK_MAX_VECTORS = 32
DEFAULT_ALPHA = 0.05
MIN_CALIBRATION_PAIRS = 20
MAX_RLE_CHARS = 20000
TAG_PART = re.compile(r"[A-Za-z0-9._-]{1,80}")
RLE_SHAPE = re.compile(r"^(?:[0-9]+:[0-9]+(?:,[0-9]+:[0-9]+)*)?$")


def l2_normalise(vector) -> np.ndarray:
    """float32 copy of vector scaled to unit length; an all-zero vector stays zero
    (it then scores 0 against everything, never a match)."""
    out = np.asarray(vector, dtype=np.float32).reshape(-1)
    if not np.all(np.isfinite(out)):
        raise ValueError("Embedding is not finite")
    norm = float(np.linalg.norm(out))
    return out / norm if norm > 0 else out


def cosine(a, b) -> float:
    """Cosine similarity of two L2-normalised vectors, clamped to [-1, 1]."""
    a = np.asarray(a, dtype=np.float32).reshape(-1)
    b = np.asarray(b, dtype=np.float32).reshape(-1)
    if a.shape != b.shape:
        raise ValueError("Embedding dimensions differ")
    return max(-1.0, min(1.0, float(np.dot(a, b))))


def crop_box(bbox, width, height):
    """Integer pixel window [x1, y1, x2, y2) of a float capture-resolution bbox,
    clamped to the image (floor of the near edge, ceil of the far edge), with a
    minimum size of one pixel. Shared by the localizer (mask RLE geometry) and the
    store (embedding crop) so both agree on the mask's width and height."""
    x1, y1, x2, y2 = (float(v) for v in bbox)
    if not all(math.isfinite(v) for v in (x1, y1, x2, y2)):
        raise ValueError("Invalid region")
    ix1, iy1 = max(0, min(width - 1, math.floor(x1))), max(0, min(height - 1, math.floor(y1)))
    ix2, iy2 = max(ix1 + 1, min(width, math.ceil(x2))), max(iy1 + 1, min(height, math.ceil(y2)))
    return ix1, iy1, ix2, iy2


def rle_from_mask(mask) -> str:
    """Row-major run-length encoding of a boolean mask as "start:length,...".

    start is the flat index into the mask (row * width + column), length the run
    of True pixels. An empty mask encodes as "". The caller bounds the string
    (LocalObservation.mask_rle allows at most MAX_RLE_CHARS characters).
    """
    flat = np.asarray(mask).reshape(-1).astype(bool)
    if flat.size == 0:
        return ""
    padded = np.concatenate(([False], flat, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    starts, ends = edges[0::2], edges[1::2]
    return ",".join(f"{int(s)}:{int(e - s)}" for s, e in zip(starts, ends))


def mask_from_rle(rle: str, width, height) -> np.ndarray:
    """Decode rle_from_mask output into a bool array of shape (height, width).

    Runs must be in increasing order, non-overlapping and inside width*height;
    anything else raises ValueError (the caller decides whether a bad mask fails
    the job or just drops the mask).
    """
    if type(width) is not int or type(height) is not int or width < 1 or height < 1:
        raise ValueError("Invalid mask geometry")
    if not isinstance(rle, str) or len(rle) > MAX_RLE_CHARS or not RLE_SHAPE.fullmatch(rle):
        raise ValueError("Invalid mask RLE")
    flat = np.zeros(width * height, dtype=bool)
    cursor = 0
    for token in rle.split(",") if rle else ():
        start, length = (int(part) for part in token.split(":"))
        if length < 1 or start < cursor or start + length > flat.size:
            raise ValueError("Invalid mask RLE")
        flat[start:start + length] = True
        cursor = start + length
    return flat.reshape(height, width)


class Embedder:
    """The embedder protocol: name, version, dim and embed(crop, mask).

    crop is an RGB uint8 array [H, W, 3] at capture resolution (the store converts
    from the decoder's BGR); mask is a bool array [H, W] over the same window or
    None. embed returns a float32 vector of length dim, L2-normalised. The tag
    "name@version" names the embedding space: a calibration and a stored vector
    are only comparable within one tag.
    """
    name: str = "embedder"
    version: str = "0"
    dim: int = 0

    @property
    def tag(self) -> str:
        return f"{self.name}@{self.version}"

    def embed(self, crop: np.ndarray, mask: np.ndarray | None) -> np.ndarray:
        raise NotImplementedError


def validate_embedder(embedder):
    """Raise ValueError unless embedder satisfies the protocol above (or is None)."""
    if embedder is None:
        return None
    name, version, dim = getattr(embedder, "name", None), getattr(embedder, "version", None), getattr(embedder, "dim", None)
    if not isinstance(name, str) or not TAG_PART.fullmatch(name) or not isinstance(version, str) or not TAG_PART.fullmatch(version):
        raise ValueError("Invalid embedder name or version")
    if type(dim) is not int or dim < 1 or dim > 8192 or not callable(getattr(embedder, "embed", None)):
        raise ValueError("Invalid embedder")
    return embedder


def _patch_selection(mask, grid, patch):
    """Boolean [grid*grid] of patches whose MASK_PATCH_OVERLAP share of pixels is
    inside mask (already resized to grid*patch square), or None to use all."""
    if mask is None:
        return None
    coverage = mask.reshape(grid, patch, grid, patch).astype(np.float32).mean(axis=(1, 3)).reshape(-1)
    selected = coverage >= MASK_PATCH_OVERLAP
    return selected if int(selected.sum()) >= MIN_MASK_PATCHES else None


def pool_patch_tokens(tokens, mask=None, *, grid=DINOV2_GRID, patch=DINOV2_PATCH, dim=DINOV2_DIM):
    """Mean of the patch tokens under the mask, L2-normalised.

    tokens is the model output as [1, 1+N, dim] (CLS first, dropped) or
    [1, N, dim] with N = grid*grid; mask is a bool [grid*patch, grid*patch] array
    or None. Patches with at least MASK_PATCH_OVERLAP of their pixels in the mask
    are pooled; when the mask is None or fewer than MIN_MASK_PATCHES qualify, all
    patches are pooled (initial rule, unmeasured).
    """
    tokens = np.asarray(tokens, dtype=np.float32)
    count = grid * grid
    if tokens.ndim != 3 or tokens.shape[0] != 1 or tokens.shape[2] != dim:
        raise ValueError("Unexpected embedder output shape")
    if tokens.shape[1] == count + 1:
        patches = tokens[0, 1:, :]
    elif tokens.shape[1] == count:
        patches = tokens[0]
    else:
        raise ValueError("Unexpected number of patch tokens")
    selected = _patch_selection(mask, grid, patch)
    pooled = patches.mean(axis=0) if selected is None else patches[selected].mean(axis=0)
    return l2_normalise(pooled)


# Preprocessing recipe tag. It is part of DinoV2Embedder's default version
# ("<sha256[:16]>-<RECIPE>"), so the embedder tag names both the weights and the way
# pixels reach them. Any change to prepare_dinov2_input or pool_patch_tokens (resize
# interpolation, normalisation, patch-overlap rule, fallback) must bump RECIPE: a
# calibration quantile measured under the old recipe then no longer matches the tag
# and is never applied to vectors produced by the new one.
RECIPE = "r1"


def prepare_dinov2_input(crop, mask=None, *, size=DINOV2_INPUT):
    """RGB uint8 crop -> NCHW float32 [1, 3, size, size] normalised with ImageNet
    mean/std, plus the mask resized (nearest) to [size, size] bool or None.
    Recipe RECIPE: INTER_AREA when shrinking, INTER_LINEAR when enlarging, /255,
    (x - mean) / std per channel."""
    import cv2
    crop = np.asarray(crop)
    if crop.ndim != 3 or crop.shape[2] != 3 or crop.dtype != np.uint8 or crop.shape[0] < 1 or crop.shape[1] < 1:
        raise ValueError("Crop must be an RGB uint8 array")
    shrinking = crop.shape[0] > size or crop.shape[1] > size
    resized = cv2.resize(crop, (size, size), interpolation=cv2.INTER_AREA if shrinking else cv2.INTER_LINEAR)
    tensor = (resized.astype(np.float32) / 255.0 - IMAGENET_MEAN) / IMAGENET_STD
    tensor = np.ascontiguousarray(tensor.transpose(2, 0, 1)[None, :, :, :], dtype=np.float32)
    if mask is None:
        return tensor, None
    mask = np.asarray(mask)
    if mask.shape != crop.shape[:2]:
        raise ValueError("Mask does not match the crop")
    resized_mask = cv2.resize(mask.astype(np.uint8) * 255, (size, size), interpolation=cv2.INTER_NEAREST)
    return tensor, resized_mask > 0


class DinoV2Embedder(Embedder):
    """DINOv2 ViT-S/14 patch-token embedder over ONNX Runtime (CPU by default).

    model_path is the exported dinov2_vits14.onnx (input [1, 3, 224, 224] float32,
    output [1, 257, 384] with the CLS token first or [1, 256, 384] patch tokens).
    The version defaults to "<first 16 hex of the file's SHA-256>-<RECIPE>", so the
    tag changes whenever the export OR the preprocessing recipe changes and an old
    calibration can never be applied to vectors from a different model or recipe.
    onnxruntime is imported lazily here only; the constructor fails with
    ValueError when the file is missing or not loadable.
    """
    name = "dinov2_vits14"
    dim = DINOV2_DIM

    def __init__(self, model_path, providers=None, *, version=None):
        path = Path(model_path)
        if not path.is_file():
            raise ValueError(f"Identity model file is missing: {path.name}")
        if version is None:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            version = f"{digest.hexdigest()[:16]}-{RECIPE}"
        if not isinstance(version, str) or not TAG_PART.fullmatch(version):
            raise ValueError("Invalid embedder version")
        self.version = version
        try:
            import onnxruntime
        except ImportError as exc:
            raise ValueError("onnxruntime is not installed; identity model unavailable") from exc
        try:
            options = onnxruntime.SessionOptions()
            options.log_severity_level = 3
            self._session = onnxruntime.InferenceSession(str(path), sess_options=options,
                                                         providers=list(providers) if providers else ["CPUExecutionProvider"])
        except Exception as exc:  # the runtime's own error types are not stable across versions
            raise ValueError(f"Identity model could not be loaded: {path.name}") from exc
        inputs = self._session.get_inputs()
        if len(inputs) != 1 or len(inputs[0].shape) != 4:
            raise ValueError("Identity model must take one NCHW image input")
        for axis, expected in ((1, 3), (2, DINOV2_INPUT), (3, DINOV2_INPUT)):
            actual = inputs[0].shape[axis]
            if isinstance(actual, int) and actual != expected:
                raise ValueError("Identity model input is not [1, 3, 224, 224]")
        self._input = inputs[0].name
        self._output = self._session.get_outputs()[0].name

    def embed(self, crop, mask=None):
        tensor, square_mask = prepare_dinov2_input(crop, mask)
        tokens = self._session.run([self._output], {self._input: tensor})[0]
        return pool_patch_tokens(tokens, square_mask)


class ItemBank:
    """The vectors already assigned to one item, newest last, at most max_vectors
    (the oldest is evicted first). score(query, embedder) is the max cosine over
    the entries of that embedder tag (every entry when embedder is None); a bank
    with no eligible entry scores -1.0, the cosine floor, so it can never match."""
    def __init__(self, item_id, max_vectors=BANK_MAX_VECTORS):
        if type(max_vectors) is not int or max_vectors < 1:
            raise ValueError("Invalid bank size")
        self.item_id = item_id
        self.max_vectors = max_vectors
        self.entries = []

    def add(self, observation_id, frame_id, embedder, vector):
        if not isinstance(embedder, str) or not embedder:
            raise ValueError("Invalid embedder tag")
        self.entries.append({"observation_id": observation_id, "frame_id": frame_id,
                             "embedder": embedder, "vector": l2_normalise(vector)})
        if len(self.entries) > self.max_vectors:
            del self.entries[:len(self.entries) - self.max_vectors]

    def count(self, embedder=None) -> int:
        return sum(1 for entry in self.entries if embedder is None or entry["embedder"] == embedder)

    def score(self, query, embedder=None) -> float:
        best = -1.0
        for entry in self.entries:
            if embedder is None or entry["embedder"] == embedder:
                best = max(best, cosine(query, entry["vector"]))
        return best

    def __len__(self):
        return len(self.entries)


def calibrate(pairs, alpha=DEFAULT_ALPHA) -> float:
    """Split-conformal quantile of the same-pair nonconformities 1 - cosine.

    pairs is an iterable of (cosine, same: bool); only same-object pairs enter
    the quantile (different-object pairs are accepted and ignored, so a held-out
    file can be passed whole).

    Pinned definition (coordinator, CP3): with n same pairs and nonconformities
    1 - cosine sorted ascending, the quantile is the k-th smallest same-pair
    nonconformity with k = min(n, ceil((n + 1) * (1 - alpha))). That is the
    split-conformal finite-sample correction; when k would exceed n the largest
    nonconformity is used. The matcher's set is {items: 1 - score <= quantile},
    boundary inclusive. n < MIN_CALIBRATION_PAIRS raises ValueError. alpha = 0.05
    is the initial value from the build plan; coverage is to be measured (P-104).
    """
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)) or not math.isfinite(alpha) or not 0 < alpha < 1:
        raise ValueError("alpha must be in (0, 1)")
    scores = []
    for pair in pairs:
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError("Each pair is (cosine, same)")
        value, same = pair
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not -1 <= value <= 1:
            raise ValueError("cosine must be a finite number in [-1, 1]")
        if type(same) is not bool:
            raise ValueError("same must be a bool")
        if same:
            scores.append(1.0 - float(value))
    n = len(scores)
    if n < MIN_CALIBRATION_PAIRS:
        raise ValueError(f"At least {MIN_CALIBRATION_PAIRS} same-object pairs are required")
    scores.sort()
    k = min(n, math.ceil((n + 1) * (1 - alpha)))
    return float(scores[k - 1])


class ConformalMatcher:
    """Turns bank scores into a "same object" set at nonconformity <= quantile.

    Only banks holding at least one vector of this matcher's embedder tag are
    considered (their scores are reported); the set is those with 1 - score <=
    quantile minus `excluded`, sorted by descending score. Size 0 -> "new",
    1 -> "match", more -> "ambiguous". calibration_id is carried for provenance.
    """
    def __init__(self, quantile, embedder, calibration_id=None):
        if isinstance(quantile, bool) or not isinstance(quantile, (int, float)) or not math.isfinite(quantile) or not 0 <= quantile <= 2:
            raise ValueError("quantile must be a finite number in [0, 2]")
        if not isinstance(embedder, str) or not embedder:
            raise ValueError("Invalid embedder tag")
        self.quantile = float(quantile)
        self.embedder = embedder
        self.calibration_id = calibration_id

    def match(self, query, banks, excluded=()) -> dict:
        excluded = set(excluded)
        scores = {}
        for item_id, bank in banks.items():
            if bank.count(self.embedder) == 0:
                continue
            scores[item_id] = bank.score(query, self.embedder)
        inside = [item_id for item_id, score in scores.items() if 1.0 - score <= self.quantile and item_id not in excluded]
        inside.sort(key=lambda item_id: (-scores[item_id], item_id))
        state = "new" if not inside else ("match" if len(inside) == 1 else "ambiguous")
        return {"set": inside, "scores": scores, "state": state}
