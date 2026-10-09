#!/usr/bin/env python3
"""Export DINOv2 ViT-S/14 (facebookresearch/dinov2, Apache-2.0) to ONNX for PAM's identity stage.

Dev-time only: requires requirements-dev.txt (torch, onnx, onnxruntime). Never imported
by the served app, never run by tests; torch, onnx and onnxruntime are imported inside
main() only after the source pin and the weights hash have been checked.

    XFORMERS_DISABLED=1 python scripts/export_dinov2_onnx.py \\
        --repo ../dinov2 --weights ../dinov2_vits14_pretrain.pth \\
        --expect-weights-sha256 <sha256 of the .pth> \\
        --out server/models/dinov2_vits14.onnx

Pins (docs/OVERSIGHT_CP3.md section 1.3, the specification this file implements):
  * repository commit EXPECTED_COMMIT (git rev-parse HEAD of --repo must equal it;
    --allow-commit overrides and is recorded in the sidecar);
  * the import is `from dinov2.hub.backbones import dinov2_vits14`, never
    torch.hub.load: hubconf.py at the commit imports the Cell-DINO and XRay-DINO hub
    modules, whose code and weights are non-commercial; nothing of theirs may run;
  * XFORMERS_DISABLED=1 keeps the export on the plain scaled_dot_product_attention path;
  * upstream weights dinov2_vits14_pretrain.pth (hash recorded in scripts/model_pins.json
    as upstream_sha256) loaded with weights_only=True and strict=True (the architecture check);
  * output patch_tokens [1, 256, 384] = forward_features(x)["x_norm_patchtokens"], one
    input image [1, 3, 224, 224] float32, static shapes, opset 17, TorchScript exporter;
  * mandatory parity check against an onnxruntime CPU session (max_abs_diff <= 1e-3);
  * provenance written next to the model as <out>.provenance.json (commit, weights hash,
    versions, opset, shapes, parity, output hash). No preprocessing is in the graph:
    perception/identity.py prepare_dinov2_input owns resize, RGB order and mean/std.

After a successful export: paste the printed SHA-256 into scripts/model_pins.json
(sha256) and docs/LICENSES.md section 3b, then run
`python scripts/fetch_models.py --only dinov2_vits14.onnx` to write server/models/MANIFEST.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

EXPECTED_COMMIT = "7764ea0f912e53c92e82eb78a2a1631e92725fc8"
REPO_URL = "https://github.com/facebookresearch/dinov2"
WEIGHTS_URL = "https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth"
OPSET, SIDE, DIM, PATCHES = 17, 224, 384, 256
PARITY_TOL = 1e-3
PARITY_SEED = 1234


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", type=Path, required=True, help="local clone of facebookresearch/dinov2 at EXPECTED_COMMIT")
    ap.add_argument("--weights", type=Path, required=True, help="dinov2_vits14_pretrain.pth (downloaded from WEIGHTS_URL)")
    ap.add_argument("--out", type=Path, required=True, help="destination, e.g. server/models/dinov2_vits14.onnx")
    ap.add_argument("--expect-weights-sha256", default=None, help="refuse unless the .pth hashes to this")
    ap.add_argument("--allow-commit", default=None, help="override EXPECTED_COMMIT (recorded in the sidecar)")
    args = ap.parse_args(argv)

    if not args.repo.is_dir():
        print("refused: --repo is not a directory")
        return 2
    if not args.weights.is_file():
        print("refused: --weights is not a file")
        return 2
    if args.out.suffix.lower() != ".onnx":
        print("refused: --out must end in .onnx")
        return 2
    os.environ.setdefault("XFORMERS_DISABLED", "1")  # plain scaled_dot_product_attention path
    try:
        head = subprocess.run(["git", "-C", str(args.repo), "rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"refused: cannot read the repository HEAD ({type(exc).__name__})")
        return 2
    expected = (args.allow_commit or EXPECTED_COMMIT).lower()
    if head.lower() != expected:
        print(f"refused: repository HEAD {head} is not {expected}")
        return 2
    weights_sha = sha256_of(args.weights)
    if args.expect_weights_sha256 and weights_sha != args.expect_weights_sha256.lower():
        print("refused: weights SHA-256 mismatch")
        return 2

    # Dev dependencies, imported only here (the served app never sees them).
    import numpy as np
    import onnx
    import onnxruntime
    import torch

    sys.path.insert(0, str(args.repo.resolve()))
    from dinov2.hub.backbones import dinov2_vits14  # not torch.hub.load: hubconf imports NC siblings' code

    model = dinov2_vits14(pretrained=False)
    state = torch.load(str(args.weights), map_location="cpu", weights_only=True)
    model.load_state_dict(state, strict=True)  # the architecture check: no missing or unexpected keys
    model.eval()

    class PatchTokens(torch.nn.Module):
        def __init__(self, backbone):
            super().__init__()
            self.backbone = backbone

        def forward(self, image):
            return self.backbone.forward_features(image)["x_norm_patchtokens"]

    wrapper = PatchTokens(model).eval()
    example = torch.zeros(1, 3, SIDE, SIDE, dtype=torch.float32)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_name(args.out.name + ".tmp")
    exporter = "torchscript"
    with torch.no_grad():
        try:
            torch.onnx.export(wrapper, example, str(tmp), input_names=["image"], output_names=["patch_tokens"],
                              opset_version=OPSET, do_constant_folding=True, dynamo=False)
        except TypeError:  # older torch without the dynamo keyword
            torch.onnx.export(wrapper, example, str(tmp), input_names=["image"], output_names=["patch_tokens"],
                              opset_version=OPSET, do_constant_folding=True)
            exporter = "torchscript (no dynamo kwarg)"
    onnx.checker.check_model(str(tmp), full_check=True)

    generator = torch.Generator().manual_seed(PARITY_SEED)
    probe = torch.randn(1, 3, SIDE, SIDE, generator=generator, dtype=torch.float32)
    with torch.no_grad():
        reference = wrapper(probe).numpy()
    session = onnxruntime.InferenceSession(str(tmp), providers=["CPUExecutionProvider"])
    produced = session.run(["patch_tokens"], {"image": probe.numpy()})[0]
    if produced.shape != (1, PATCHES, DIM) or reference.shape != (1, PATCHES, DIM):
        print(f"refused: output shape {produced.shape}, expected (1, {PATCHES}, {DIM})")
        tmp.unlink(missing_ok=True)
        return 1
    max_abs = float(np.max(np.abs(produced - reference)))
    mean_abs = float(np.mean(np.abs(produced - reference)))
    if max_abs > PARITY_TOL:
        print(f"refused: parity max_abs_diff {max_abs:.3e} exceeds {PARITY_TOL}")
        tmp.unlink(missing_ok=True)
        return 1
    del session
    os.replace(tmp, args.out)

    sidecar = {
        "artifact": args.out.name, "sha256": sha256_of(args.out), "bytes": args.out.stat().st_size,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": {"repo": REPO_URL, "commit": head, "entry": "dinov2.hub.backbones.dinov2_vits14",
                   "weights_url": WEIGHTS_URL, "weights_sha256": weights_sha, "weights_bytes": args.weights.stat().st_size,
                   "licence": "Apache-2.0 (code and weights; README L660, MODEL_CARD.md L32 at the commit)"},
        "export": {"script_sha256": sha256_of(Path(__file__)), "exporter": exporter, "opset": OPSET,
                   "input": {"name": "image", "shape": [1, 3, SIDE, SIDE], "dtype": "float32"},
                   "output": {"name": "patch_tokens", "shape": [1, PATCHES, DIM], "dtype": "float32",
                              "meaning": "forward_features(x)['x_norm_patchtokens']"},
                   "xformers_disabled": os.environ.get("XFORMERS_DISABLED") == "1",
                   "torch": torch.__version__, "onnx": onnx.__version__, "onnxruntime": onnxruntime.__version__,
                   "python": platform.python_version(), "platform": platform.platform()},
        "parity": {"max_abs_diff": max_abs, "mean_abs_diff": mean_abs, "tolerance": PARITY_TOL, "seed": PARITY_SEED},
        "preprocessing": "none in the graph; perception/identity.py prepare_dinov2_input (RGB, 224x224 resize, ImageNet mean/std)",
    }
    args.out.with_name(args.out.name + ".provenance.json").write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"exported {args.out.name} ({sidecar['bytes']} bytes) sha256 {sidecar['sha256']} parity max_abs {max_abs:.2e}")
    print("next: record sha256 in scripts/model_pins.json and docs/LICENSES.md section 3b, then python scripts/fetch_models.py --only dinov2_vits14.onnx")
    return 0


if __name__ == "__main__":
    sys.exit(main())
