# Oversight review: CP3 (identity), pass 1: the plan

Oversight agent, 2026-10-09, on `docs/BUILD_PLAN.md` "CP3 in detail: identity" and
"CP3 acceptance" (working tree over `c795556`), with the builders implementing in
parallel. Read-only; no git state changed. This pass reviews the plan and the gate
code the plan relies on; the diff review follows when the coordinator asks. Where I
looked at builder files that had already appeared (`perception/identity.py`, the
`perception/episode_store.py` diff), I say so; those are not verdicts on the diff.

Inputs read: `docs/BUILD_PLAN.md` §3 (CP3), `docs/LICENSES.md` (my CP2 register),
`docs/OVERSIGHT_CP2.md` §3-§4, `docs/RESEARCH_LOG.md` C-03, C-05, D-008, B-03, B-05,
B-14, B-15, `docs/MEMORY_SYSTEM_V4.md` Part 1 identity lines (L82, L97, L123, L128,
L197, L316, L338), `docs/review-inputs-20261006/review/MEMORY.md` §C (external input,
not authority), `server/memory_app.py` (manifest, licence and route gates),
`scripts/fetch_models.py`, `scripts/model_pins.json`, `.gitignore`, the two
requirements files, `docs/CONTINUATION_HANDOFF.md` §11.

Fetched today (primary sources, hashed in the review scratchpad, not committed):
`raw.githubusercontent.com` (DINOv2 at `main` and at the pinned commit, torch, onnx,
onnxruntime, CC BY 4.0 text via SPDX, the CUTE authors' datasheet), `pypi.org` JSON
and `files.pythonhosted.org` (the onnxruntime 1.30.0 wheel), and `git ls-remote` to
GitHub. **Not reachable** (egress HTTP 403 on CONNECT): `dl.fbaipublicfiles.com`
(the weights), `purl.stanford.edu`, `searchworks.stanford.edu`, `cute.stanford.edu`,
`arxiv.org`, `creativecommons.org`, `github.com` HTML and API. WebFetch of the CUTE
PURL page needed a permission that was not granted in time (twice). Nothing below
is guessed from an unreachable host; those items say so and name the URL.

Verdict in one line: **the CP3 plan is commercially clean on paper (DINOv2 ViT-S/14
is Apache-2.0 for code and weights at the primary source, re-confirmed today at
commit `7764ea0f`; ONNX Runtime is MIT; CUTE is CC BY 4.0; the conformal method is
unlicensed mathematics), but the export cannot run in the sandbox, two gate functions
written for CP2 will fail closed on a `.onnx` file unless Builder B separates the
server-side model directory from the browser one (§1.5), and the correction API must
not let a request body choose the `actor` (§3.5).** `physical_instance_recognition`
is a no-go until the human steps in §0 are done; the deterministic-embedder path is
unaffected.

## 0. Human actions required (the sandbox cannot run the export)

All on the user's laptop, in the PAM checkout, after Builder B lands
`scripts/export_dinov2_onnx.py`, `requirements-dev.txt` and the pins entry (§1.4).
Linux/macOS commands; PowerShell equivalents in brackets. Nothing is optional for
a go.

1. **Dev environment, separate from the served app.** `torch` and `onnx` are
   development dependencies only; they never enter `server/requirements.txt` and the
   served app never imports them.
   ```
   python -m venv .venv-export && . .venv-export/bin/activate      [.venv-export\Scripts\Activate.ps1]
   python -m pip install -r requirements-dev.txt
   # requirements-dev.txt pins (recommended, §1.6): torch==2.14.1 from the CPU index
   #   (pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu),
   #   onnx==1.23.1, onnxruntime==1.30.0 (the same runtime version as the server)
   ```
2. **Clone the DINOv2 repository at the pinned commit** (the licence texts and the
   hub code were read at exactly this commit today; `main` moves):
   ```
   git clone https://github.com/facebookresearch/dinov2.git ../dinov2
   git -C ../dinov2 checkout 7764ea0f912e53c92e82eb78a2a1631e92725fc8
   git -C ../dinov2 rev-parse HEAD        # must print 7764ea0f912e53c92e82eb78a2a1631e92725fc8
   ```
3. **Download and hash the upstream weights** (the LVD-142M ViT-S/14 backbone, not the
   `_reg4_` file, not anything from the XRay-DINO or Cell-DINO sections):
   ```
   curl -L -o ../dinov2_vits14_pretrain.pth "https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth"
   sha256sum ../dinov2_vits14_pretrain.pth          [Get-FileHash ..\dinov2_vits14_pretrain.pth -Algorithm SHA256]
   ```
   Paste the 64-hex value into `scripts/model_pins.json` (`upstream_sha256` of the
   `dinov2_vits14.onnx` entry) and into `docs/LICENSES.md` §3b (the `.pth` field of
   the ONNX row), with the file size in bytes and the date.
4. **Export** (dev-time only; `XFORMERS_DISABLED=1` keeps the export on the plain
   PyTorch attention path, see §1.3):
   ```
   XFORMERS_DISABLED=1 python scripts/export_dinov2_onnx.py \
       --repo ../dinov2 --weights ../dinov2_vits14_pretrain.pth \
       --expect-weights-sha256 <the hash from step 3> \
       --out server/models/dinov2_vits14.onnx
   sha256sum server/models/dinov2_vits14.onnx       [Get-FileHash .\server\models\dinov2_vits14.onnx -Algorithm SHA256]
   ```
   The script writes `server/models/dinov2_vits14.onnx.provenance.json` (commit,
   weight hash, versions, opset, shapes, parity result, output hash). Paste the ONNX
   SHA-256 into `scripts/model_pins.json` (`sha256`) and into `docs/LICENSES.md` §3b.
   The parity line in the sidecar must read `max_abs_diff` below `1e-3`; if it does
   not, stop and report it, do not record the hash.
5. **Register and manifest under the gates:**
   ```
   python scripts/fetch_models.py --dry-run                     # before the export: "refused ... sha256 is null" (exit 2); after filling the hash
                                                                #   but before the file exists: "missing" (exit 1); with the file: "present ... local export"
   python scripts/fetch_models.py --only dinov2_vits14.onnx     # writes server/models/MANIFEST.json (no download for a local export)
   git status --short server/models ../dinov2_vits14_pretrain.pth   # expect nothing listed (coordinator adds server/models/ and *.pth to .gitignore)
   ```
6. **Verify and enable, explicitly:** start the app with `PAM_ENABLE_IDENTITY_MODEL=1`,
   confirm `GET /api/health` lists `dinov2_vits14.onnx` with `provisioned: true,
   licence_recorded: true` and `physical_instance_recognition` enabled with a reason
   that still says "accuracy unmeasured"; confirm `GET /assets/models/dinov2_vits14.onnx`
   is a 404 (the file must never be reachable from the browser route); run the CP3
   suites and `phone/test/test_ui_smoke.py` (no-egress assertion) with the model
   present. Then record the run in `docs/RESEARCH_EXPERIMENTS.md` as the start of
   P-104, not as an accuracy result.
7. **Calibration for real use** waits for a data source (§2): a synthetic calibration
   must never be approved on the rig. By coordinator decision the capability reads
   `enabled: false` with "no approved calibration: identity stays provisional" until
   a record exists for the exact tag shown in `/api/health` (`dinov2_vits14@<hash16>-r1`);
   the model still runs for P-104 measurement in that state. When the set exists:
   `store.register_calibration({...,"source": "cute"|"own-footage"|"holoassist"})`
   then `store.approve_calibration(calibration_id, "operator")` on the laptop
   (there is no route for approval, by design), and record the held-out coverage
   in `docs/RESEARCH_EXPERIMENTS.md`.

## 1. Provenance plan for the identity model

### 1.1 Primary-source re-confirmation (2026-10-09)

`git ls-remote https://github.com/facebookresearch/dinov2.git` resolved `main` and
`HEAD` to **`7764ea0f912e53c92e82eb78a2a1631e92725fc8`**. Every file below was fetched
twice, once from `main` and once from that commit, with identical bytes:

| File (at `7764ea0f`) | SHA-256 | What it says (verbatim) |
| --- | --- | --- |
| `LICENSE` | `600cc67cc4cb2f5ea317dcfc687ad1c74dc4bec8782bbe9db0afd83513b935b7` (11,359 B; unchanged since the CP2 read) | Apache License, Version 2.0, full text |
| `README.md` | `d1bc2e9686522bbd66ed6123dc81eb36b3a98e8ea9a2ca97778f54a1c641c9e1` (unchanged) | L658-660: "## License / DINOv2 code and model weights are released under the Apache License 2.0. See [LICENSE](LICENSE) for additional details." L59: the ViT-S/14 "backbone only" link `https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth`; L67: the `_reg4_` variant (not pinned). **Traps unchanged:** L159-160 (XRay-DINO) "Model weights are released under the FAIR Noncommercial Research License"; L754-757 (Cell-DINO) "Code is released under the CC BY NC License ... Model weights are released under the FAIR Noncommercial Research License" |
| `MODEL_CARD.md` | `70ca59606bee0a5fbb1baec80e7e29a93cd7cfbe26ca1910c52a852c4aab09d0` (unchanged) | L32: "**License:** Apache License 2.0"; L13: "The model takes an image as input and returns a class token and patch tokens, and optionally 4 register tokens."; L15-16: "The embedding dimension is: 384 for ViT-S."; L24: "For a 224x224 image, this results in 1 class token + 256 patch tokens"; L88: "**Training data:** LVD-142M (see paper)" |
| `hubconf.py` | `c1f5090e78ff940b72c076d2bf9c0310d1707c946b3d10e2d6f2b0bdf56a6f64` | Imports `dinov2_vits14` from `dinov2.hub.backbones` **and also** `dinov2.hub.cell_dino.backbones` and `dinov2.hub.xray_dino.backbones` (see §1.3 on why the export must not go through `torch.hub.load`) |
| `dinov2/hub/backbones.py` | `871fca671b12a9ff02e810654baf509e97ccf461bf8196ce5ddeefff2fd87d3e` | `dinov2_vits14(pretrained=True, weights=Weights.LVD142M)` builds `vit_small(img_size=518, patch_size=14, init_values=1.0, ffn_layer="mlp", block_chunks=0, num_register_tokens=0, interpolate_antialias=False, interpolate_offset=0.1)` and loads `_DINOV2_BASE_URL + "/dinov2_vits14/dinov2_vits14_pretrain.pth"` with `strict=True` |
| `dinov2/hub/utils.py` | `579613e3d7b82c2a387eddc215ad9f076b8740f9618229628395fe5755dbd131` | `_DINOV2_BASE_URL = "https://dl.fbaipublicfiles.com/dinov2"`; loads with `weights_only=True` on torch >= 2.1 |
| `dinov2/models/vision_transformer.py` | `7799a260f2d7d0fe197331d08502fb8c542f9b7424723650f6a39b64fa2639ea` | `forward_features(x)` returns `{"x_norm_clstoken": x_norm[:, 0], "x_norm_regtokens": ..., "x_norm_patchtokens": x_norm[:, num_register_tokens + 1:], "x_prenorm": x, "masks": masks}` (L257-272); the default `forward()` returns `self.head(ret["x_norm_clstoken"])` (L348-353), i.e. only the CLS token; `vit_small` has `embed_dim=384, depth=12, num_heads=6` (L364-377); positional embeddings are interpolated for a 224 input from the 518 training grid (L182-214) |
| `dinov2/layers/attention.py` | `79c7be7a452b3aad96698ec38d5d5150b9f4d8ac084fa93324510dc9f624775d` | `XFORMERS_ENABLED = os.environ.get("XFORMERS_DISABLED") is None`; without xFormers `MemEffAttention` falls back to `nn.functional.scaled_dot_product_attention` (L69-90). `block.py` and `swiglu_ffn.py` guard their xFormers imports the same way |
| `NOTICE` | none (404 for `NOTICE`, `NOTICE.md`, `NOTICE.txt` at the commit) | Apache-2.0 §4(d) adds nothing beyond the licence text and the copyright line in the source headers, "Copyright (c) Meta Platforms, Inc. and affiliates." |

The weights themselves (`dl.fbaipublicfiles.com`) were not reachable (HTTP 403 at
the egress proxy), so their SHA-256 is **not** in this document. It is step 3 of §0.

### 1.2 What ships, under what grant

| Artifact | Grant | Ships to the customer? | Obligation |
| --- | --- | --- | --- |
| `dinov2_vits14_pretrain.pth` (upstream weights, 2023 LVD-142M distilled ViT-S/14) | Apache-2.0 (README L660, MODEL_CARD L32) | No: dev-time input to the export only; never in the repo, never in the served tree | None beyond keeping the record |
| `dinov2_vits14.onnx` (our export of those weights) | Apache-2.0 derivative work of the weights, produced by our MIT script; redistribution permitted under §4 with notices | Yes in a laptop installer; in the rig it stays on the user's laptop; never served to the browser | Apache-2.0 text + Meta copyright line in the notices page; a §4(b) modification notice ("exported from the PyTorch checkpoint to ONNX by PAM, `scripts/export_dinov2_onnx.py`, commit `7764ea0f`"); the upstream hash and commit recorded |
| `dinov2` repository code | Apache-2.0 (`LICENSE`) | No: imported only by the export script at dev time; the ONNX graph contains tensors and ops, not Python | None at runtime; the export script's docstring cites the repository and commit |
| `onnxruntime` 1.30.0 wheel | MIT (§5) | Yes (server side) | MIT text + `ThirdPartyNotices.txt` from the wheel in the notices page |
| Calibration quantile | not a licensed object (§2.2) | Yes, as a number in the `calibrations` table | Voluntary attribution of the calibration source (§2.1) |

Training data LVD-142M is not redistributed by Meta and the model card attaches no
data terms to weight users (CP2 finding, unchanged).

### 1.3 The export procedure (required design; Builder B owns the file)

`scripts/export_dinov2_onnx.py`, dev-time only, standard library plus `torch`, `onnx`
and `onnxruntime` (the last for the parity check), never imported by anything under
`server/` or `perception/`. Required behaviour:

1. **Source pin.** `--repo` is a local clone; the script runs `git rev-parse HEAD` in
   it and refuses unless it equals `EXPECTED_COMMIT =
   "7764ea0f912e53c92e82eb78a2a1631e92725fc8"` (override only with an explicit
   `--allow-commit <sha>`, which is then recorded). It `sys.path.insert(0, repo)` and
   imports **`from dinov2.hub.backbones import dinov2_vits14`**, not
   `torch.hub.load('facebookresearch/dinov2', 'dinov2_vits14')`: the hub entry runs
   `hubconf.py`, which imports the Cell-DINO and XRay-DINO hub modules (README L756:
   Cell-DINO *code* is CC BY NC). Nothing from those modules reaches the ONNX file
   either way, but the export process should not execute non-commercial code at all,
   and the direct import closure (`dinov2.hub.backbones` -> `dinov2.models.vision_transformer`
   -> `dinov2.layers.*`) needs only `torch`; the xFormers imports are guarded
   (`attention.py:21-32`, `block.py:27-34`, `swiglu_ffn.py:37-44`). The script sets
   `os.environ.setdefault("XFORMERS_DISABLED", "1")` before the import so the
   exported graph is the plain `scaled_dot_product_attention` path.
2. **Weights.** `--weights` is the downloaded `.pth`; the script hashes it, refuses
   on mismatch with `--expect-weights-sha256` when given, builds
   `dinov2_vits14(pretrained=False)` and loads with `torch.load(path, map_location="cpu",
   weights_only=True)` + `load_state_dict(..., strict=True)`. Strict loading is the
   architecture check: the 2023 checkpoint must load without missing or unexpected
   keys into the 2026 code (the `channel_adaptive=False` default keeps the LVD-142M
   path unchanged, `vision_transformer.py:69,107,364-377`).
3. **What is exported.** A wrapper module whose forward is
   `model.forward_features(x)["x_norm_patchtokens"]`, i.e. the **layer-normalised
   patch tokens, shape `[1, 256, 384]`**, one output named `patch_tokens`, one input
   named `image` of shape `[1, 3, 224, 224]` float32 (static batch of 1; no dynamic
   axes). Not the default `forward()` (that is the CLS token through an identity head,
   `[1, 384]`, useless for the plan's mean-patch pooling), not `x_prenorm`, not the
   `_reg4` variant (a different weights file, different interpolation flags, a new
   embedding space). This matches `perception/identity.py:204-254` as written by
   Builder A (`DinoV2Embedder` accepts `[1, 256, 384]` or `[1, 257, 384]` and takes
   `get_outputs()[0]`; a single output removes the ambiguity).
4. **Exporter and opset.** `torch.onnx.export(wrapper, torch.zeros(1, 3, 224, 224),
   out, input_names=["image"], output_names=["patch_tokens"], opset_version=17,
   do_constant_folding=True, dynamo=False)` under `torch.no_grad()` and `eval()`.
   Opset 17 has native `LayerNormalization`, bicubic `Resize` (the 518 -> 224 positional
   embedding interpolation, which should constant-fold because it depends only on
   parameters and a fixed input size; if it stays a `Resize` node that is still
   valid), `Erf` for the exact GELU, and the SDPA decomposition. `dynamo=False`
   selects the TorchScript exporter explicitly (the default moved to the dynamo
   exporter in recent torch); if the installed torch rejects the keyword the script
   records which exporter ran. Then `onnx.checker.check_model(out, full_check=True)`.
5. **Parity check, mandatory.** On a fixed-seed random input, compare the torch
   wrapper output with an `onnxruntime` CPU session on the exported file; write
   `max_abs_diff` and `mean_abs_diff` into the sidecar; exit non-zero above `1e-3`
   (fp32 both sides; the threshold is an engineering tolerance, not an accuracy claim).
6. **Sidecar provenance** `<out>.provenance.json`: repository URL and commit, weights
   URL, weights SHA-256 and size, export script SHA-256, `torch.__version__`,
   `onnx.__version__`, `onnxruntime.__version__`, Python version, platform, opset,
   exporter, input/output names and shapes, parity numbers, output SHA-256 and size,
   `exported_at` (UTC). This file is what a reviewer or an acquirer reads; it stays
   next to the model (gitignored with the model directory).
7. **No preprocessing in the graph.** Resize, RGB order and ImageNet mean/std stay in
   `perception/identity.py:184-201` (`prepare_dinov2_input`). That is a provenance
   gap the embedder tag must close (§1.4 item 4).

A reference implementation is in Appendix A; Builder B may use it as is.

### 1.4 Recording the artifact (register, pins, manifest, tag)

1. **`docs/LICENSES.md` §3b** (added in this pass): one row naming
   `dinov2_vits14.onnx` with `Apache-2.0` and `status: VERIFIED-COMMERCIAL` (the
   licence of the source weights and of our export is verified at the primary
   source, §1.1), and with the artifact fields the human fills in §0: upstream `.pth`
   SHA-256 and size, ONNX SHA-256 and size, export date, torch/onnx versions. Until
   those are filled, the artifact cannot be used anyway, because:
2. **`scripts/model_pins.json`** keeps `"sha256": null` for the entry, which
   `check_pin` refuses (`scripts/fetch_models.py:126-128`), the second, independent
   gate (register rule 2). Proposed entry (new keys `source`, `dest`,
   `upstream_sha256`, `export` are documentation to the script's existing readers and
   the inputs of the local-export mode of §1.5):
   ```json
   {
     "name": "dinov2_vits14.onnx",
     "version": "dinov2_vits14@7764ea0f-opset17-224",
     "source": "local-export",
     "dest": "server",
     "url": "https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth",
     "upstream_sha256": null,
     "sha256": null,
     "licence": "Apache-2.0",
     "export": {
       "script": "scripts/export_dinov2_onnx.py",
       "repo": "https://github.com/facebookresearch/dinov2",
       "commit": "7764ea0f912e53c92e82eb78a2a1631e92725fc8",
       "entry": "dinov2.hub.backbones.dinov2_vits14 (pretrained=False + strict load_state_dict of the .pth)",
       "output": "forward_features(x)['x_norm_patchtokens']",
       "opset": 17, "input": [1, 3, 224, 224], "output_shape": [1, 256, 384]
     },
     "notes": "DINOv2 ViT-S/14 (LVD-142M, no registers), Apache-2.0 code and weights (README L660, MODEL_CARD L32 at the pinned commit). Produced locally by the export script; never downloaded as ONNX from anywhere. url is the upstream weights for provenance only; upstream_sha256 and sha256 are filled by the human after docs/OVERSIGHT_CP3.md section 0. Never pin the _reg4_, XRay-DINO or Cell-DINO files."
   }
   ```
3. **Manifest.** `server/models/MANIFEST.json` (not `phone/assets/models/`, §1.5), the
   same `{name, version, sha256, url, licence, fetched_at}` shape, written only by
   `scripts/fetch_models.py` after verifying the file's hash against the pin.
4. **Embedding-space tag.** `DinoV2Embedder.version` defaults to the first 16 hex of
   the ONNX file's SHA-256 (`perception/identity.py:221-226`), so a re-export changes
   the tag and silently invalidates nothing: calibrations are keyed by tag and a
   stale one simply never applies. Good. But the tag is bound to the graph bytes
   only, while the embedding space also depends on the preprocessing and pooling code
   in `identity.py` (resize mode, RGB order, mean/std, the 50 % patch rule, the
   4-patch minimum). **Recommendation to Builder A:** make the tag
   `<hash16>-r<N>` with `RECIPE = "r1"` a module constant that is bumped on any
   change to `prepare_dinov2_input`/`pool_patch_tokens` (the external review's
   `token_recipe_id`, in one line; `TAG_PART` already allows the hyphen). Record the
   recipe constant in the health `models` entry's `version` next to the pins version.

### 1.5 Gate code that will fail closed on a `.onnx` file (plan-level findings)

The plan says the ONNX model is "loaded only through the model manifest gate (same
`scripts/fetch_models.py` + `docs/LICENSES.md` rule as CP2)". Read literally against
the CP2 code, that breaks the hand model:

1. **`server/memory_app.py:81-89` (`_model_name`) rejects any name whose suffix is not
   in `MODEL_MEDIA_TYPES` (`.task .wasm .js .mjs .cjs .json`), and
   `load_model_manifest` (`:100-144`) returns `None` for the whole manifest on one
   invalid entry, by design ("fail closed: a manifest with one bad entry serves
   nothing").** Appending `dinov2_vits14.onnx` to `phone/assets/models/MANIFEST.json`
   therefore makes `hand_landmarker.task` "unprovisioned" and stops the worker
   assets being served. Adding `.onnx` to `MODEL_MEDIA_TYPES` instead would make an
   ~85 MB server-side model (21 M parameters in fp32, README L55) publicly
   downloadable from `/assets/models/` (the route is deliberately public, `:623-650`). **Required:** a separate server-side directory
   and manifest, `server/models/MANIFEST.json`, read by a second inventory
   (`model_inventory(SERVER_MODELS_DIR, suffixes={".onnx"})`); health `models` lists
   both inventories; the browser route never looks at the server directory; a test
   asserts `GET /assets/models/dinov2_vits14.onnx` is 404 even when provisioned and
   enabled.
2. **`scripts/fetch_models.py:60` (`ALLOWED_SUFFIXES`) lacks `.onnx`, and `check_pin`
   (`:111-137`) requires an `https` URL to download from.** The ONNX file is produced
   locally; there is no primary URL for it and there must never be one (a converted
   copy from a model zoo is exactly what C-03 rejects). **Required:** a
   `source: "local-export"` mode: no network; the file must already exist at
   `<dest dir>/<name>`; its SHA-256 must equal the pin's `sha256` (null still refuses);
   on success the entry is manifested with `fetched_at` = the sidecar's `exported_at`
   if present. `dest: "server"` maps to `server/models/`; the default stays
   `phone/assets/models/`. The licence-row check (`:129-136`) stays exactly as it is:
   a line naming `dinov2_vits14.onnx` with `VERIFIED-COMMERCIAL` and `Apache-2.0`.
3. **`.gitignore`** already has `*.onnx`; it lacks `server/models/` (the manifest and
   the provenance sidecar) and `*.pth` (`*.pt` does not match `.pth`). Coordinator
   owns the file, as at CP2.
4. **The served app must never import `torch` or `onnx`.** `onnxruntime` is imported
   lazily inside `DinoV2Embedder.__init__` only (`identity.py:230-233`), which is
   right. The bootstrap suite's module-graph test
   (`server/test_memory_bootstrap.py:573`) is the place to assert that `torch`,
   `onnx` and `ultralytics` are absent from `sys.modules` after importing and
   exercising `server.memory_app`.
5. **Capability policy.** Mirror `hand_model_capability` (`memory_app.py:225-240`):
   unprovisioned -> unlicensed -> disabled (`PAM_ENABLE_IDENTITY_MODEL`) -> enabled
   with "accuracy unmeasured on this device"; the store's own report
   (`episode_store.py` diff, `identity_capability`) must be overridden by the server
   policy the way `with_hand_policy` does, so health and items never disagree. The
   store report already distinguishes "no approved calibration: identity stays
   provisional", which is the honest reason string when the model is loaded but
   uncalibrated; keep it.

### 1.6 Dev dependencies (never shipped)

| Package | Version to pin | Licence (primary source, fetched 2026-10-09) | Note |
| --- | --- | --- | --- |
| torch | 2.14.1 (PyPI 2026-09-30; the Windows laptop already runs 2.14.0+cpu per `CLAUDE.md`) | Repository `LICENSE` is the BSD-3-Clause text ("From PyTorch: Copyright (c) 2016- Facebook, Inc ..."), SHA-256 `bd018feef8825e88181c84eb7e3aa4eafb8f08a20d9fd6ef948569610c4a3e43`; the wheel's PyPI `license_expression` is `Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT` (bundled components) | Dev only: no notice obligation to customers because nothing of it ships |
| onnx | 1.23.1 (2026-09-29; 1.23.2 is three days old) | Apache-2.0, `LICENSE` SHA-256 `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30` | Dev only (checker + export) |
| onnxruntime | 1.30.0 (also the runtime pin, §5) | MIT | Used by the parity check |
| Playwright | still unpinned (tester) | Apache-2.0 (CP2 note) | Add the row when the version is known |

`requirements-dev.txt` (Builder B, repo root) carries these four and nothing the
served app needs; `server/requirements.txt` gains only `onnxruntime==1.30.0`.

## 2. Calibration data

### 2.1 CUTE (CC BY 4.0): status today and the attribution text

- **Primary source:** `https://purl.stanford.edu/gj714cj0414`, read through WebFetch on
  2026-10-08 (register §4 quotes it: "This work is licensed under a Creative Commons
  Attribution 4.0 International license (CC BY)" and the use statement about not
  identifying individuals). **Today it could not be re-read**: curl gets HTTP 403 at
  the egress proxy and WebFetch's permission request was not answered. The 2026-10-08
  read stands; a human should open the URL once more before the first calibration
  run and confirm the licence line is unchanged.
- **Author-published corroboration, fetched today:** the authors' code repository
  `s-tian/CUTE` (`README.md`, SHA-256 `44502182e5f44466a9c7f8b69dda3416a334f677f76111cccfaa4dbe573fab44`:
  "The CUTE dataset is available for download at the following link:
  https://purl.stanford.edu/gj714cj0414") ships `datasheet.md` (SHA-256
  `8c0fcabce74f3b89d60c78d584a20fa73b12843c6f8011b2306702d1bfc56f4f`): "The dataset
  will be distributed under the CC-BY-4.0 license."; "Does the dataset relate to
  people? No."; "Have any third parties imposed IP-based or other restrictions on the
  data associated with the instances? No."; "The dataset has been distributed as of
  June 13, 2023."; instances are "images of objects ... in pairs based on similarity";
  "There are 10,000 images in total." The repository's own `LICENSE` is MIT,
  "Copyright (c) 2023 Klemen Kotar, Stephen Tian, Hong-Xing Yu, Daniel L.K. Yamins,
  Jiajun Wu" (SHA-256 `9b04efaa045e2e47b23a945a4dee7555370be3dfa39a9ab1757d609568060e60`);
  that covers the FFA code, not the images. The datasheet is a secondary source
  (same authors, different host); it corroborates, it does not replace, the PURL read.
- **Attribution text PAM carries if CUTE is used for calibration** (CC BY 4.0
  §3(a)(1)(A)-(C), text fetched from the SPDX copy today, SHA-256
  `d557539df68e771cc1eedcc91d13f70fca930e508d11eedcafa4b15db49e3744`; satisfiable "in
  any reasonable manner based on the medium", §3(a)(2)):

  > Same-object calibration data: CUTE ("Common paired objects Under differenT
  > Extrinsics"), the dataset accompanying "Are These the Same Apple? Comparing Images
  > Based on Object Intrinsics" by Klemen Kotar, Stephen Tian, Hong-Xing Yu, Daniel
  > L. K. Yamins and Jiajun Wu, Stanford Digital Repository, 2023,
  > https://purl.stanford.edu/gj714cj0414 (doi:10.25740/gj714cj0414), licensed under
  > the Creative Commons Attribution 4.0 International License,
  > https://creativecommons.org/licenses/by/4.0/. The dataset is provided without
  > warranties (see the licence). PAM used cropped and resized copies of these
  > images to estimate one similarity threshold; no CUTE image is included in PAM.

  Place it in the third-party notices page (still to be built, CP2 §2) and in the
  `calibrations` record's `source` provenance (a `source_note` string next to
  `source: "cute"`), so the attribution travels with the number.

### 2.2 Is a calibration quantile derived from CUTE itself a "derivative"?

Reasoning from the licence text (CC BY 4.0, SPDX copy):

- The attribution condition is triggered by *sharing the Licensed Material*:
  §3(a)(1) "If You Share the Licensed Material (including in modified form), You
  must ...". A quantile is not the Licensed Material in any form; it is one number
  computed from nonconformity scores of image pairs.
- "Adapted Material" (§1(a)) is "material subject to Copyright and Similar Rights
  that is derived from or based upon the Licensed Material and in which the Licensed
  Material is translated, altered, arranged, transformed, or otherwise modified in a
  manner requiring permission under the Copyright and Similar Rights held by the
  Licensor." A threshold contains no expression from any photograph and reproduces
  nothing a copyright holder can control; it is a fact about the data, like a
  reported accuracy. It is not Adapted Material.
- Database right (§4, EU sui generis): the conditions apply "if You Share all or a
  substantial portion of the contents of the database" (§4(c)). A quantile shares no
  contents. (§4(a) even grants extraction and reuse "for the avoidance of doubt".)
- Nothing CC-licensed is stored in PAM: the `calibrations` row holds
  `{calibration_id, embedder, alpha, quantile, n, source, created_ms, approved}`;
  no image, no embedding of a CUTE image, no file path.

**Recommendation:** treat the quantile as **not** a derivative, so no attribution is
*legally* required for shipping it; **attribute anyway**, with the §2.1 text, because
(a) it costs nothing, (b) the C-05 obligation to state "the calibration set and the
empirical coverage, not just α" needs the source named in the record regardless, and
(c) a reviewer or acquirer asking "where did this number come from" gets the answer
from the product itself. The same reasoning applies to an EER or coverage figure in a
report. It does **not** apply to anything that stores image content: a bank of CUTE
embeddings, a cached CUTE crop or a figure in a UI would be Shared material and
need the full attribution (and the privacy use statement from the PURL page). The
CP3 design stores none of these. This is a licence reading, not legal advice
(register preamble).

### 2.3 HoloAssist (CDLA-Permissive-2.0) as the alternative source

Register §4 row (fetched 2026-10-08): CDLA-Permissive-2.0 §3.1 "This agreement does
not impose any restriction or obligations with respect to the use, modification, or
sharing of Results"; §5.4 "'Results' means any outcome obtained by computational
analysis of Data, including for example machine learning models". A calibration
quantile is a Result: **no obligation at all**, not even attribution. Two caveats
that are not licence questions: (a) HoloAssist is egocentric video of people doing
tasks, with hands and sometimes faces in frame; any crops cut from it for same-object
pairs are processed on the laptop and never stored in PAM, and the Data itself may
only be shared with the agreement text (§2.1); (b) whether it yields enough
*same-instance* object pairs across views and time for a calibration is a question
for the tester and Builder A (P-104), not answered here. If used, record `source:
"holoassist"` (the plan's enumeration has `synthetic | cute | own-footage`; add it)
and the release version read from the authors' README.

### 2.4 Own footage (`source: "own-footage"`)

Calibration pairs from the user's own objects are the distribution the rig will see
(the external review's week-2 set), and they are household footage: the
recording-consent and bystander analysis of `docs/OVERSIGHT_CP2.md` §3.2 and the
handoff §11 ("No IRB filing ... recruitment or household recording was performed")
apply. **Gate:** no own-footage calibration before G-PILOT is authorised
(`RESEARCH_LOG.md` gate table: "Institutional/IRB determination, consent and
bystander plan, safety/retention/data-flow review and explicit authorization"),
with one exception the plan already allows: the **user's own device and own objects**
in the user's own rig session, where the user is the only person in frame and
has started the camera page knowingly (`memory.html` consent sentence). Even then
the calibration crops are derived from stored keyframes the user already consented
to, the record must carry `consent_version` once CP4 introduces it, and the
`approve_calibration` audit row must say which session role approved it (§3.5).
No calibration from anyone else's household until the pilot gate.

### 2.5 What every calibration record must carry (for C-05)

`calibration_id`, `embedder` tag (with the recipe id, §1.4 item 4), `alpha`,
`quantile`, `n` (same-pairs only; `calibrate()` already ignores different-pairs),
`source` and a `source_note` with the attribution or release identifier, the
**held-out empirical coverage** measured when the record was made (the tester's
synthetic check proves the arithmetic; the real number comes from the real set), the
crop-size bucket if the external review's per-bucket calibration is adopted later,
`created_ms`, `approved`/`approved_by` (role string)/`approved_ms`. A record with
`source: "synthetic"` is for tests and must never be approved on a rig database
(§6 condition 4).

## 3. Privacy and commercial path of embeddings and corrections

### 3.1 Are DINOv2 object embeddings biometric-adjacent data?

Briefly: **no, by definition; incidentally, possibly, by content.** Illinois BIPA
(740 ILCS 14/10) defines a biometric identifier as "a retina or iris scan,
fingerprint, voiceprint, or scan of hand or face geometry"; GDPR Art. 4(14) defines
biometric data as personal data from specific technical processing of a natural
person's physical, physiological or behavioural characteristics which allow or
confirm unique identification. A 384-float appearance vector of a pill bottle or a
pair of glasses is neither. The vector is still **personal data** in the GDPR sense
(it is linked to a household and describes that person's belongings) and the C-04
list already names "embeddings" among the things erasure must reach; it is not
anonymous and must not be declared so (BUILD_CONTRACT retention line).

The incidental case is real: the identity crop is the localizer's changed-region
bbox on the rest frame (`localizer.py` diff; `episode_store.py` `_embed_region`), and
a rest frame can still contain the user's hand (a late release), a bystander's hand,
or a face in the background. A crop that is mostly hand produces a vector that
describes a hand. That vector is not a "scan of hand geometry" either, but it is the
kind of fact a plaintiff's expert argues about, and it is useless for identity.
**Recommendations (Builder A, CP3 if cheap, otherwise CP4 with the landmark
reduction):**

1. **Exclude the hand hull from the identity mask.** The packet already carries
   per-sample `hands[].hand_bbox` (and 21 landmarks) with timestamps; take the
   landmark sample nearest in time to the embedded keyframe, and clear the mask (and
   the pooled patches) under each hand bbox, or under the convex hull of the 21
   points when present. The mask already steers pooling (`pool_patch_tokens`), so
   this is a mask edit, not a new path.
2. **Refuse to embed a crop the hand dominates.** If the hand bbox covers more than
   an initial 50 % of the crop window (unmeasured value, to be set by P-104), store
   no embedding for that observation (`identity_state` stays `provisional`, reason
   "hand in region"); never embed a hand and call it an object.
3. **Only rest-frame regions in CP3** (as the localizer does today): no pre-contact
   or carry crops, which are the ones most likely to contain the hand, until the
   hull exclusion exists.
4. Faces: no face detector is planned and none is wanted; the mitigation is the
   consent sentence on the camera page plus (1)-(3), and the CP4 data-class map
   naming "identity crop embedding" as a class derived from keyframes with the same
   consent and retention as the keyframe.

### 3.2 Embeddings never leave the device in the rig (requirements)

The plan asks Oversight to "confirm no embedding leaves the device in the rig". On
the plan and the store diff: embeddings are written to the `embeddings` table as
float32 bytes and read back only by `process_pending`/bank reconstruction; no
existing route returns them. To keep it that way, Builder B and the tester:

1. No route serialises `embeddings` rows, bank vectors or scores: `present_item`
   strips any `vector`, `bank`, `scores` key; `/api/items/{id}/evidence` returns the
   plan's fields only; `/api/chat` `group` members carry `provenance:
   {observation_id, identity_status}` and nothing numeric.
2. The cloud chat path (currently 503 "not configured") must, when it is configured,
   send text only: FINANCE cap 1 already says "no images to the provider"; extend it
   to "no embeddings, no scores" in the policy text.
3. Tester assertion: every JSON response of the CP3 API suite contains no array of
   64 or more numbers and no key named `vector`/`embedding`/`embeddings`; the
   Playwright no-egress assertion runs with the model present.
4. The ONNX file itself is not reachable from the browser (§1.5 item 1).
5. `health` reports model names and versions only, never paths (CP2 §1.7 rule,
   unchanged).

### 3.3 Retention question for CP4 (recorded, not decided)

G-PRIV must answer, for the new tables: (a) `embeddings` rows are derived from a
keyframe and must be deleted or redacted with it (C-04); after erasure of an
observation, `rebuild_all` must not resurrect its vector from any other table
(the plan's "replays stored embeddings and decisions, never re-embeds" is right, and
the tombstone check must cover `embeddings`); (b) bank membership is a view over
`embeddings`, so erasing a row shrinks the bank, which can change later matches;
that is accepted and must be stated; (c) the `calibrations` table holds no personal
data when the source is CUTE/HoloAssist, but an own-footage record is tied to a
household and inherits its consent and retention; (d) `corrections` rows carry the
role string and item/observation ids only (no names, §3.5) and are audit metadata
that survives item tombstoning; whether they survive a full household erasure is a
CP4 decision; (e) retention window for embeddings defaults to the keyframe's (90
days pending G-PRIV, CP2 decision 9); (f) exports: an embedding export is a
personal-data export, never "model data".

### 3.4 Commercial path

Nothing in CP3 adds a copyleft, non-commercial or research-only component: DINOv2
(Apache-2.0), ONNX Runtime (MIT; its wheel's `ThirdPartyNotices.txt` lists permissive
and public-domain components plus the Intel MKL Simplified Software License and
others that only apply to builds that include them; the CPU wheel ships
`libonnxruntime.so.1.30.0`, `libonnxruntime_providers_shared.so` and the pybind
module), flatbuffers (Apache-2.0), packaging (Apache-2.0 OR BSD-2-Clause), protobuf
(BSD-3-Clause), CUTE (CC BY 4.0, attribution), HoloAssist (CDLA-Permissive-2.0,
results free). The conformal procedure carries no licence (§4). The trademark,
copyright-holder and App-Store findings of `OVERSIGHT_CP2.md` §3.4-3.6 are unchanged
and are not repeated.

### 3.5 The `actor` rule (B-15) in the correction API

B-15: "Caregiver PIN is not named-person identity. Distinguish role/session
authorization from attribution to a particular caregiver." The plan says `actor` is
"the session role string ("caregiver_pin"), never a named person". Findings on what
exists today, and the required design for what does not yet:

- `perception/episode_store.py` (diff): `link_items`, `unlink_observation` and
  `approve_calibration` validate `actor` against `ACTOR = re.compile(r"[A-Za-z0-9._-]{1,80}")`
  and write it into `corrections.actor`, `calibrations.approved_by` and the
  `local_audit` detail. That accepts `mary.smith` as readily as `caregiver_pin`.
  **Required:** a closed set, e.g. `ACTORS = {"caregiver_pin", "operator", "test"}`
  (the server passes the first; a CLI or fixture the other two), `ValueError`
  otherwise. One line, and it makes the B-15 rule a property of the store, not of
  every caller.
- Server routes (Builder B, not yet written): `POST /api/items/{id}/link` takes
  `json_body(request, {"other_item_id"})` and `POST .../unlink` takes no body;
  **the request body must not carry `actor`** (the CP2 `json_body` allowlist pattern,
  `memory_app.py:590`, already rejects unknown keys; keep `actor` out of the allowed
  set). The handler passes the literal `"caregiver_pin"`; there is no other role in
  the one-profile app. 409 on `CannotLinkError` with a fixed safe message, never the
  item ids of third parties.
- Audit and corrections rows: role string, correction id, item/observation ids,
  timestamps. No free text from the request, no device name, no IP.
- UI copy (Builder C): "Marked as the same item" / "Marked as a different item", never
  "Mary marked ...". Provenance shown to the user is "corrected by the caregiver
  session", which is true.
- `approve_calibration(calibration_id, actor)`: there is no route for it in the plan,
  which is right for CP3 (an operator action on the laptop); if a route is added
  later it needs its own confirmation step and the same role literal.

## 4. The conformal method: commercial path and truthful claims

### 4.1 Licence

Split conformal prediction is a statistical procedure (a quantile of calibration
nonconformity scores with the finite-sample correction, `identity.py:291-320`). A
method is not copyrightable; the implementation here is PAM's own code under the
repository MIT licence; the papers the external review cites (Angelopoulos and
Bates 2021, the retrieval-set papers) are read, not copied. No patent search was
performed and none is claimed; that is a counsel question if it ever matters, and
nothing in the method is specific enough to this product to be a likely target.
**No licence obligation attaches to the conformal matcher.**

### 4.2 Caveats that must appear in any product claim (C-05, D-008)

Any sentence that mentions "95 %", "α", "calibrated" or "guarantee" must be read
against these, and the UI/marketing text in §4.3 is written so that it needs none
of them spelled out:

1. Coverage is **marginal** over the calibration distribution, and **conditional on
   the true item being in the bank** ("if the true item is in the bank, P(true ∉ C) ≤
   α"). It says nothing about an item never stored, a missed capture, a wrong
   localisation, a stale location or a later move.
2. It holds under **exchangeability** between calibration pairs and rig crops; a
   CUTE-calibrated quantile applied to a kitchen at night is a transfer, and the
   number must be re-estimated on rig crops and checked per home before any
   per-home claim.
3. It is not a per-query guarantee: "post-selection/conditional singleton risk" is
   not bounded; the empty-set rate (fragmentation) and the set-size distribution are
   reported numbers, not controlled ones.
4. It is **not an end-to-end medication-safety guarantee**: the answer chain
   (capture, localisation, identity, staleness, resolver, UI) has other failure
   modes and the pilot scores all queries and medication queries separately; "No
   calibrated model or guarantee exists at this checkpoint" stays true until a real
   calibration record is approved and its empirical coverage is measured.
5. Every answer that used the matcher records its `calibration_id` and embedder tag
   so a claim can be traced to a calibration set and version (B-11-style
   determinism applies to identity decisions too: replay uses stored decisions).

### 4.3 Capability statement the UI and marketing may use (one paragraph)

> PAM can recognise some of your own belongings by how they look. When PAM has seen
> an item before, it compares a new photo with the earlier ones and reports a match
> only when the two are at least as similar as a threshold set during a calibration
> step; when two of your things look alike, it says so and shows you both instead of
> guessing. This is a statistical check with known limits: it was calibrated on a
> reference set of photographs rather than on your home, it can only match items it
> has already stored, it does not read labels or text, and it does not know whether
> an item has moved since the last photo it took. PAM is a memory aid, not a safety
> system: it is not a medical device, it does not verify medication, and you should
> check the physical item before taking anything.

Words that must not appear next to this feature until the corresponding gate has
passed: "95 % accurate", "guaranteed", "never confuses", "verified identity",
"medication safety", "biometric".

## 5. Dependencies: register changes made in this pass (`docs/LICENSES.md`)

| Change | Where | Status token |
| --- | --- | --- |
| `onnxruntime` becomes a **runtime dependency**, pinned **1.30.0** (2026-09-10; 1.31.0 was published today, 2026-10-09, inside the 7-day rule). Wheel `onnxruntime-1.30.0-cp311-cp311-manylinux_2_28_x86_64.whl` downloaded from `files.pythonhosted.org`, SHA-256 `fd54b314ea385bcecac69ab431f020ba503e3878dad4ebb645fec5a24b041242` = PyPI digest; bundles `onnxruntime/LICENSE` (MIT, SHA-256 `2f07c72751aed99790b8a4869cf2311df85a860b22ded05fa22803587a48922c`, identical to the repository file) and `onnxruntime/ThirdPartyNotices.txt` (338,088 B, SHA-256 `143764b952fdb1a7c69ce653bfba74a7744d6a8a573bfb73e235fba356c83de3`); `Requires-Dist: flatbuffers, numpy>=1.21.6, packaging, protobuf>=4.25.8` | §1 (moved from §3) | `VERIFIED-COMMERCIAL` |
| Transitive runtime deps of onnxruntime: flatbuffers 25.12.19 (Apache-2.0), packaging 26.3 (Apache-2.0 OR BSD-2-Clause), protobuf 7.36.2 (BSD-3-Clause), PyPI declarations | §1 | `VERIFIED-COMMERCIAL` (declaration-level) |
| numpy 2.5.3 and opencv-python-headless 5.0.0.93 rows: confirmed unchanged (PyPI re-read today: same versions, same declared licences); `cv2.resize` is now also on the identity path | §1 | unchanged |
| Dev-only rows: torch 2.14.1 (BSD-3-Clause repository `LICENSE`), onnx 1.23.1 (Apache-2.0), Playwright (version pending), Node 22 | new §1b | `VERIFIED-COMMERCIAL` (dev; never shipped) |
| DINOv2 ViT-S/14 row: commit pin `7764ea0f`, today's re-read, hub/ViT file hashes | §3 | unchanged |
| New §3b: `dinov2_vits14.onnx` (our export) with the provenance fields the human fills | §3b | `VERIFIED-COMMERCIAL` (licence); pins `sha256: null` until the export |
| CUTE row: datasheet corroboration, the attribution text, today's unreachable note | §4 | unchanged |
| Notices table: DINOv2 ONNX (Apache text + modification notice), onnxruntime (MIT + `ThirdPartyNotices.txt`), CUTE attribution when used | §5 | n/a |
| Evidence hashes of today's fetches | §7 | n/a |

No AGPL/GPL/NC/research-only component is added by CP3. `ultralytics` and the AGPL
`CLIP` fork are still declared in `perception/requirements.txt` (CP2 finding 7; purge
still awaiting the user's authorisation).

## 6. Go/no-go for enabling `physical_instance_recognition` on the rig

**No-go today**, for the same structural reason as CP2's hand model: the artifact
does not exist yet and only a human can make it. Conditions, all required:

1. **Export done per §1.3 and recorded per §1.4**: pinned commit, strict weight load,
   `patch_tokens [1, 256, 384]`, opset 17, parity `max_abs_diff < 1e-3` in the
   sidecar, upstream `.pth` SHA-256 and ONNX SHA-256 in `scripts/model_pins.json` and
   `docs/LICENSES.md` §3b, `scripts/fetch_models.py` exit 0 in local-export mode,
   `server/models/MANIFEST.json` written by the script.
2. **Gate code separated** (§1.5): server-side manifest and inventory; the hand
   model still provisioned after the ONNX is manifested; `/assets/models/dinov2_vits14.onnx`
   404; `torch`/`onnx` absent from the served app's module graph; health and items
   agree through one policy function; `PAM_ENABLE_IDENTITY_MODEL=1` explicit, default
   off, reason "accuracy unmeasured on this device".
3. **Tester's CP3 suites green** with the deterministic embedder (new -> match ->
   ambiguous -> group -> correction -> replay; cannot-link exclusion; unapproved
   calibration never `trusted`; embedder absent -> `provisional` only, capability
   false, no `embeddings` rows), all CP1/CP2 suites still green, no new runtime
   dependency beyond `onnxruntime` and its three declared transitive packages, no
   request leaving the origin with the model present.
4. **A real, approved calibration record** for the exact embedder tag (hash + recipe)
   from `cute` or `own-footage` (user's own objects only, §2.4) with its held-out
   empirical coverage recorded; **never a `synthetic` record on a rig database**.
   Until then the model may be enabled for P-104 measurement with identity staying
   `provisional`, which the store already does, and the UI must not show a
   "recognised" badge for a provisional match.
5. **Actor rule enforced** in the store (closed set) and the routes (no `actor` in
   any request body) (§3.5), with the tester's 409 and audit assertions.
6. **No embedding leaves the device** assertions in place (§3.2).
7. **Hand-in-crop guard** (§3.1 items 2-3) before any use with other people in
   frame; for the user's own single-person rig test, item 3 (rest-frame regions
   only) is enough.

Meeting 1-7 gives a **go for the rig on the user's own device** for P-104
measurement, with the enable remaining an explicit operator action. Any claim about
recognition accuracy waits for P-104 numbers; any use in another household waits for
G-PILOT and the CP4 retention deliverable.

## 7. Open questions for the coordinator

1. **Register convention for a verified-licence, unhashed artifact.** I recorded
   `dinov2_vits14.onnx` as `VERIFIED-COMMERCIAL` (the licence is verified at the
   primary source) with the artifact hash pending in the pins file (`sha256: null`,
   the independent refusal). The CP2 hand-model row used `UNVERIFIED` because the
   *licence* was unread, which is a different situation. If you prefer the stricter
   "no token until the hash exists" convention, say so and I will flip the row; the
   gates behave identically either way until the human finishes §0.
2. **Server-side model directory.** `server/models/` with its own manifest (§1.5
   item 1) is my recommendation; Builder B may prefer `perception/models/`. Either
   is fine as long as it is outside `phone/` and gitignored (coordinator adds the
   directory and `*.pth` to `.gitignore`).
3. **`fetch_models.py` local-export mode** (§1.5 item 2): extend the script, or add a
   sibling `scripts/register_local_model.py` that shares `check_pin`? One script and
   one gate is cleaner; your call.
4. **Embedder tag with a recipe id** (§1.4 item 4): accept for CP3, or defer to the
   first preprocessing change? Deferring risks a calibration surviving a
   preprocessing edit unnoticed.
5. **Closed `ACTORS` set** in the store (§3.5): accept for CP3?
6. **`source` enumeration** in calibration records: add `"holoassist"` now so the
   alternative is representable.
7. **Hand-hull exclusion** (§3.1): CP3 or CP4? It is a mask edit in Builder A's
   `_embed_region`; the hand bbox is already in the packet.
8. **Preprocessing geometry.** The plan says "224 px"; Builder A resizes the crop to a
   224 x 224 square without preserving aspect ratio (`identity.py:191-192`); the
   external review proposed padding to square first. Not a licence question and not
   a blocker; flagging so the tester's goldens pin whichever you choose before a
   calibration is made (changing it later is a new tag and a re-calibration).
9. **Third-party notices page** still does not exist (CP2 §2). CP3 adds three entries
   (§5). Is it a CP4 or CP5 deliverable, and whose?
10. **onnxruntime 1.30.0 vs 1.31.0**: 1.31.0 was released today; I pinned 1.30.0 by
    the 7-day rule. Re-pin at CP4 if nothing in 1.30.0 blocks the laptop.

## Diff review, pass 2 (2026-10-09, after the coordinator's decisions)

Reviewed read-only in the working tree over `c795556`: `git status` (15 modified, 7
new paths), `git diff`, and the files named by the coordinator. The tester's suites
are the tester's verdict; where I ran something I say so. Coordinator decisions
received and checked against the code: (1) ONNX row stays `VERIFIED-COMMERCIAL`,
pin `sha256: null`; (2) `server/models/`; (3) local-export inside
`fetch_models.py`; (4) tag `<hash16>-r1`; (5) closed `ACTORS`; (6) `holoassist`
source; (7) hand hull to CP4; (8) crop geometry pinned at CP4; (9) notices page at
CP5; (10) onnxruntime re-pin at CP4; plus `enabled` requires an approved calibration,
`unresolved_observation_id` on group answers and the `assign_observation` correction.

**Verdict in one line: the diff implements the CP3 interfaces and every §1-§6
requirement that was in scope for CP3, with no fabricated capability, no vector on
any route, no new runtime dependency beyond `onnxruntime`, and the export script
matching Appendix A; two medium findings in the correction flow (one wrong safe
message, one over-strong inference on `assign`) should be fixed before the rig but
block nothing in the deterministic-embedder path; the real model remains a no-go
until the human steps in §0 are done.**

### P2.1 Plan adherence (BUILD_PLAN "CP3 in detail" against the tree)

| Plan item | Owner | Status | Evidence (file:line in the working tree) |
| --- | --- | --- | --- |
| `Embedder` protocol (name, version, dim, `embed(crop, mask)` L2-normalised) | A | done | `perception/identity.py:117-147` (`Embedder`, `validate_embedder`) |
| `DinoV2Embedder` over ONNX Runtime, 224 px, mean of patch tokens with ≥ 50 % mask overlap, fallback to all patches under 4 patches; lazy `onnxruntime` import; missing file is a loud `ValueError` | A | done, plus the recipe tag (decision 4) | `identity.py:37-38` (rules), `:150-181` (`pool_patch_tokens`), `:190` (`RECIPE = "r1"`), `:193-212` (`prepare_dinov2_input`), `:215-266` (`DinoV2Embedder`, version `f"{sha256[:16]}-{RECIPE}"` at `:238`) |
| `ItemBank` (max 32, oldest evicted, max cosine) | A | done | `identity.py:39`, `:269-300` |
| `ConformalMatcher` (nonconformity `1 - cosine`, set = ≤ q minus excluded, 0/1/>1 → new/match/ambiguous); `calibrate()` split-conformal quantile with the finite-sample correction | A | done | `identity.py:303-336` (`calibrate`, k = min(n, ceil((n+1)(1−α))), ≥ 20 same pairs), `:339-366` (`ConformalMatcher.match`) |
| Calibration records in a `calibrations` table; approved only via `approve_calibration(id, actor)`, audited; processor dict `fixture_only` kept as code-only injection | A | done | `episode_store.py:113-117` (table), `:232-266` (`register_calibration`, always unapproved, `CALIBRATION_SOURCES` incl. `holoassist` `:31`), `:268-285` (`approve_calibration`, `_check_actor`), `:291-297` (`_active_calibration`), `:299-` (`_observation_trusted`: CP2 dict rule or an approved stored record for the current tag) |
| Cannot-links (B-03): co-visible items excluded during matching; failed embedding never removes a link | A | done | `episode_store.py:455-459` (`_co_visible_items` ∪ this packet's outputs as `excluded`), `:483-484` and `:500-503` (co-visible outputs never collapse; links written), `:650-` (`_co_visible_items`); embedding failure → `match = {"state": "new", ...}` with no link removal `:443-445` |
| Integration in `process_pending`: crop at capture resolution, mask from `LocalObservation.mask_rle`, embed, match; trusted only with an approved calibration for the embedder's tag; ambiguous → observation parked with `candidates`, candidates marked lookalikes; `embeddings` table; rebuild replays, never re-embeds | A | done | `localizer.py:20-43`, `:103-110` (mask RLE over the integer crop window, bounded, dropped when too long); `episode_store.py:393-408` (embed before the write lock; failures counted, never persisted as text), `:434` (`mask_rle` excluded from the stored record), `:446-482` (match → reuse item, trusted only if `calibration["approved"]`; ambiguous → parked, candidates), `:494-497` (`local_observations.candidates`, `embeddings` row as `<f4` bytes), `:118-121` (table), `:805-823` (lookalikes from parked candidates), `rebuild_all` `:1184-` (replays stored decisions and corrections) |
| Answers: `group` when members are mutual lookalikes, text "I have N items that look alike; which one is yours?", per-member `reference_image`, `observed_at_ms`, `location_text` only when that member's own location is placed/sighted, `provenance {observation_id, identity_status}`; group never upgrades a member; `clarify` for distinct name matches; `confident` needs single, trusted, placed, not aged | A | done, plus `unresolved_observation_id` (coordinator) | `episode_store.py:1133-1149` (group vs clarify; `question`, `options`, `unresolved_observation_id` from the newest parked observation whose candidate set equals the members), `:1150-1173` (single-member shapes; a lookalike-bearing single match hedges without a location `:1166-1170`) |
| Corrections: `link_items` (refuses on cannot-link, merges, tombstones, audit `user_linked`), `unlink_observation` (new item + cannot-link, audit `user_unlinked`), `corrections` table replayed in order; `actor` a role string | A | done, plus `assign_observation` (coordinator) and the closed `ACTORS` set (decision 5) | `episode_store.py:35-42` (`ACTORS = ("caregiver_pin", "operator", "test")`, `_check_actor`), `:123-` (table), `:989-1024` (`link_items`, `CannotLinkError` `:1008-1009`, cannot-links of the retired item transfer `:1015-1019`), `:1026-1060` (`unlink_observation`, refuses the only observation `:1048-1049`), `:1062-1118` (`assign_observation`; see finding F2), `:570-` (`_corrections` replay) |
| Server: `POST /api/items/{id}/link {other_item_id}`, `POST .../observations/{obs}/unlink`, `GET .../evidence`, `GET .../observations/{obs}/image`, 409 with a safe message, group shape through `/api/chat`, health `models` + `physical_instance_recognition` from the CP2 policy pattern (`dinov2_vits14.onnx` provisioned + licence recorded + `PAM_ENABLE_IDENTITY_MODEL=1`) | B | done, plus `.../assign` and the server-side inventory (decision 2) | `server/memory_app.py:87-91` (constants), `:121-132` (`_model_name` with per-inventory suffixes), `:143-157` (`load_model_manifest(suffixes=)`: a `.onnx` in the browser manifest or a `.task` in the server manifest invalidates that manifest only), `:262-266` (`server_model_inventory`), `:324-382` (gate + capability: unprovisioned → unlicensed → disabled → load error → store's own reason → enabled "provisioned and calibrated; accuracy unmeasured on this device"), `:445-466` (`sync_embedder`: constructs `DinoV2Embedder` only when the gate is open; a construction error becomes the reason, never a fallback), `:502-527` (`call_correction`: actor literal `CORRECTION_ACTOR = "caregiver_pin"` `:31`, 409 codes `:106-111`), `:884-889` (`/history` scrubbed), `:891-897` (`/evidence`), `:907-915` (observation image), `:925-957` (link/unlink/assign; bodies `{"other_item_id"}` or empty), `:959-975` (`/chat` → `present_answer` `:762-778`), `:834-848` (health lists both inventories), `:1007-1008` (`/assets/models/` refuses server suffixes before any lookup) |
| Browser: group members' photos side by side with "I can't tell these apart — which one is yours?", tapping resubmits as a clarify selection; evidence list with photo/time/status; "Same as another item…" (pick, confirm, link) and "Not this one" (confirm, unlink); 409 shows the safe reason; `ambiguous` badge with lookalike count | C | done | `phone/memory.html:80-83` (evidence section, confirm dialog with the link select), `phone/assets/memory.js:97-102` (badge + notice), `:300-325` (`evidenceRow` with "Not this one", disabled for a lone observation), `confirmUnlink`, the `link-item` handler (catalogue fetched unfiltered, lookalikes first, explicit confirmation sentence), `groupMember`/`chooseMember` (assign first when `unresolved_observation_id` is present, then re-ask by item id; failure is reported and the question is still asked), `refusalReason` (409 `detail` shown only when it is one short sentence) |
| Tester: `server/test_cp3_identity.py`, `server/test_cp3_api.py`, smoke extension | Tester | present; 41 tests green in my read-only run (`python3 -B -m unittest server.test_cp3_identity server.test_cp3_api`); the five existing server suites 161/161 green in the same run; `phone/test/test_ui_smoke.py` not run here (Playwright) | `server/test_cp3_api.py:56-57,186` (no key matching vector, embedding, bank or scores, and no long numeric list, in any JSON response), `:602` (bodies never carry an actor), `:734` (`/assets/models/dinov2_vits14.onnx` is 404), `:390` (409 safe message); `server/fixtures/cp3/calibration_pairs.json` |
| Oversight: provenance plan, CUTE attribution, no embedding leaves the device, this file | Oversight | done (§1-§6, this section) | `docs/LICENSES.md` §1, §1b, §3, §3b, §4, §5, §7 |
| `scripts/export_dinov2_onnx.py`, `requirements-dev.txt`, `onnxruntime` in `server/requirements.txt`, pins entry, local-export mode | B | done | see P2.3; `requirements-dev.txt` (torch 2.14.1 CPU index, onnx 1.23.1, onnxruntime 1.30.0, playwright 1.63.0: exactly §1.6); `server/requirements.txt` +1 line `onnxruntime==1.30.0`; `scripts/model_pins.json` entry `dinov2_vits14.onnx` (`source: local-export`, `dest: server`, `url: null`, `upstream_url`, `upstream_sha256: null`, `sha256: null`, `export{commit 7764ea0f, opset 17, [1,3,224,224] → [1,256,384]}`); `scripts/fetch_models.py:31-43` (rules), `:66,:75-78` (server dir, `SERVER_SUFFIXES = {".onnx"}`), `:100-105` (`valid_name(name, dest)`), `:130-172` (`check_pin`: local pins carry no url, `sha256: null` still refuses), `:244-253` (sidecar `exported_at`), `:293-365` (one manifest per destination; a missing local export is `missing`, exit 1, never a download) |
| `.gitignore`: `server/models/`, `*.pth` | Coordinator | **not on disk at review time** (`*.onnx` is) | `.gitignore` tail; decision 2 says it is being added; §0 step 5 checks before the first export |
| Not in CP3 (hand hull, crop geometry pin, notices page, re-pin) | - | deferred by decisions 7-10 | tracked in §7 |

Deviations from the plan text, all accepted or benign: `analyze`-style signature
extensions are none this time; `unlink_observation` takes an optional `item_id`
keyword the route uses to scope the observation to the item in the URL
(`episode_store.py:1026`, `memory_app.py:948`), stricter than the plan; `ItemBank`
entries are reconstructed from the `embeddings` table per `process_pending` call
(`_banks`, `:615`) rather than persisted as a bank object, which is what "projection
rebuild replays stored embeddings" implies; the group `members` cap is 8
(`:1134`), the external review's "at most three spoken" is a CP5 UI matter.

### P2.2 Confirmations asked for by the coordinator

1. **No route returns vectors, scores or banks.** `/api/items` and `/api/items/{id}`
   go through `present_item` (whitelist of ten scalar fields + `aged`,
   `reference_image`, `image_url`, `lookalikes` ids, `provenance` ids;
   `memory_app.py:719-744`). `/api/items/{id}/evidence` goes through
   `present_evidence` (whitelist; `candidates` are item ids, `embedded` a bool;
   `:746-760`). `/api/chat` goes through `present_answer` → `present_item` and
   `options` ids (`:762-778`). `/api/items/{id}/history` returns the stored record
   through `without_identity_internals` (recursive key drop of
   `vector|vectors|embedding|embeddings|bank|banks|scores`, `:780-788`); the record's
   `match` dict then keeps `state`, `set`/`excluded` (item ids), `calibration_id`,
   `calibration_approved`, `reason` and nothing numeric (`episode_store.py:444-465`
   is the only writer; `scores` are the only numbers and are dropped). `/api/health`
   returns names, versions, booleans and reason strings (the reason carries the
   embedder tag `dinov2_vits14@<hash16>-r1` and a calibration id, no path:
   `identity_load_failure` strips anything with a separator `:385-392`). The two
   image routes return keyframe JPEG bytes under the item-assignment rule. The
   store's `capabilities()` reason strings are the same (`episode_store.py:199-211`).
   The tester's regex assertion covers every JSON route (`test_cp3_api.py:56-57,186`).
   **Confirmed.**
2. **No fake inference.** `embedder is None` → `vectors` all `None`, no `embeddings`
   row, no match, identity never above `provisional`, store capability `enabled:
   False` "No identity model provisioned" (`episode_store.py:186-189,:201-202,:398`).
   An embedding exception → `embedding_failed` counter, `trusted = False`, `match`
   state `new` with reason "embedding failed; identity provisional" (`:406-408,
   :425-429, :443-445`). A model that fails to construct → capability `enabled:
   False` with the class name or a path-free message (`memory_app.py:457-463`). An
   embedder with no approved calibration → matching runs, identity stays provisional,
   capability `enabled: False` with the honest reason (`episode_store.py:209-211`;
   coordinator decision). The server policy wins over the store's report
   (`with_identity_policy`, `:378-382`, and `policy()` `:709-711`). **Confirmed.**
3. **No new runtime dependency beyond `onnxruntime`.** `server/requirements.txt`
   gains exactly `onnxruntime==1.30.0`; `perception/requirements.txt` is untouched;
   `identity.py` imports `numpy` at module level and `cv2`/`onnxruntime` lazily.
   Read-only check: after `import server.memory_app`, `perception.identity` and
   `perception.episode_store`, `sys.modules` holds none of `torch`, `onnx`,
   `onnxruntime`, `ultralytics`, `anthropic`, `httpx`. onnxruntime's own declared
   dependencies (`flatbuffers`, `packaging`, `protobuf`) are recorded in
   `docs/LICENSES.md` §1. **Confirmed.**
4. **No network in the export script at import.** Module level is stdlib only
   (`argparse, hashlib, json, os, platform, subprocess, sys, time, pathlib`);
   `torch`/`onnx`/`onnxruntime`/`numpy` are imported inside `main()` after the
   commit and weight-hash checks (`scripts/export_dinov2_onnx.py:95-102`); the only
   subprocess is `git rev-parse HEAD` on the local clone; `WEIGHTS_URL` and
   `REPO_URL` are string constants written into the sidecar, never fetched; no
   `urllib`, `requests`, `socket` or `torch.hub` anywhere. Read-only check: the
   module imports and `--help` runs with `torch`, `onnx` and `onnxruntime` blocked
   in `sys.modules`. **Confirmed.**
5. **The browser cannot reach the `.onnx`.** `/assets/models/{name}` refuses any
   name with a server suffix before touching the manifest
   (`memory_app.py:1007-1008`); the browser inventory rejects a `.onnx` entry
   (whole manifest invalid, `:143-157`); the server directory is never under
   `phone/`; `PUBLIC_ASSETS` is unchanged; the tester asserts the 404 even when the
   model is provisioned and enabled (`test_cp3_api.py:734`). **Confirmed.**

### P2.3 Export script against Appendix A

| Appendix A requirement | `scripts/export_dinov2_onnx.py` | Status |
| --- | --- | --- |
| Commit pin, `git rev-parse HEAD` must equal `7764ea0f…`; `--allow-commit` recorded | `:45`, `:80-89` (refuses on mismatch; override lower-cased and recorded as `source.commit` = actual HEAD `:154`) | done |
| Import `dinov2.hub.backbones.dinov2_vits14`, never `torch.hub.load` (NC hub modules) | `:101-102`, docstring `:16-18` | done |
| `XFORMERS_DISABLED=1` before the import | `:79` (`setdefault`, before the dinov2 import at `:102`) | done |
| Weights hashed, `--expect-weights-sha256` refusal; `pretrained=False` + `torch.load(weights_only=True)` + `load_state_dict(strict=True)` | `:90-93`, `:104-107` | done |
| Wrapper returning `forward_features(x)["x_norm_patchtokens"]`, input `image [1,3,224,224]`, output `patch_tokens`, static shapes, opset 17, `dynamo=False` with a fallback that records the exporter | `:109-129` | done |
| `onnx.checker.check_model(full_check=True)` | `:130` | done |
| Parity check (seeded probe, ORT CPU session, shape `[1,256,384]`, `max_abs_diff ≤ 1e-3`, temp file discarded on failure) | `:132-147` | done; improvement: the shape is checked on both sides |
| Sidecar `<out>.provenance.json` with repo/commit/entry, weights URL/hash/bytes, script hash, exporter, opset, shapes, versions, platform, parity, output hash, `exported_at`, preprocessing note | `:151-167` | done |
| Checks before heavy imports; `--out` must end in `.onnx`; temp file then atomic replace | `:70-78`, `:120`, `:148-149` | done (improvements over the appendix) |

Not run here (no torch, no weights); the human runs it in §0 step 4. The two
things only that run can show: that the 2023 checkpoint loads strictly into the
2026 code, and the parity number.

### P2.4 Browser correction flow: what could mislead

- **F1 (medium, server + browser copy): the `cannot_link` refusal overstates the
  evidence.** `CORRECTION_REFUSALS["cannot_link"]` (`memory_app.py:108`) says "These
  were seen together as two different objects, so they cannot be the same item."
  and the link confirmation sentence (`memory.js`, `link-item` handler) says "Pam
  refuses when the two were ever seen together in one photo." Cannot-links now
  have three origins: co-visibility (`episode_store.py:500-503`), the user's own
  "Not this one" (`:1055-1056`) and `assign` exclusions (`:1106-1114`). After an
  unlink or an assign, a later "Same as" is refused with a sentence claiming the
  two were seen together, which is false. Fix: one message that covers all
  origins, e.g. "Pam has these recorded as two different objects (seen together in
  one photo, or separated by an earlier correction), so they cannot be merged.",
  and the matching confirmation sentence. One string each; no logic change.
- **F2 (medium, store design): `assign_observation` infers more than the user
  said.** Tapping a group member records "this sighting is A" and the store also
  writes permanent cannot-links between A and every other candidate
  (`episode_store.py:1099-1108`, "the user said it is not those"). The user was
  asked "which one is yours?", not "are these different objects?"; on a day-one
  bank where the group exists because of fragmentation (two items that are one
  object, C-05 empty-set case), the tap makes the later repair ("Same as another
  item…") impossible with a 409. The group prompt and the "Your choice was
  recorded for that sighting." note do not say that the tap also separates the
  items. Recommendation: keep only the placeholder's co-visibility links on
  assign (`:1110-1114`) and drop the candidate exclusions (`:1099-1108`), so a
  group can still be merged; or, if the coordinator wants the exclusion, say so in
  the prompt ("Tapping also tells Pam the others are different objects") and in
  the recorded note. Coordinator decision; the tester's
  `test_assign_resolves_the_parked_observation_and_dissolves_the_group` pins the
  current behaviour and would change with it.
- Not misleading, checked: the group prompt "I can't tell these apart — which one
  is yours? Tap the photo of your item." presents the members as the user's own
  stored items with their own photo, location text and date (each member's own
  evidence, no shared location); tapping re-asks the chat by item id, so the
  follow-up answer is that item's own shape and never upgraded by the tap
  (`chooseMember` → `ask(member.item_id)`; `answer_text` single-member path
  `episode_store.py:1150-1173`). "Same as another item…" is an explicit user
  assertion ("Tell Pam that … are the same physical object"), confirmed in a
  dialog, with lookalikes listed first but never pre-selected, and the kept
  record described as "retired, not deleted". "Not this one" is likewise
  confirmed and the lone-observation case is disabled with a reason. The identity
  badge says `ambiguous · N lookalikes` and the notice says Pam "will ask which
  one is yours rather than guess". The alt text for a trusted outline says "The
  recorded item is outlined", for anything else "the item identity is unverified";
  `trusted` here means a calibrated match, which the capability reason still
  labels "accuracy unmeasured on this device". A refused correction shows only the
  server's one-sentence `detail`. CSS adds a `badge-ambiguous` colour and a bold
  `group-prompt`; nothing is hidden.
- **F3 (low, test convenience):** `create_app(models_dir=X)` without
  `server_models_dir` makes both inventories read `X/MANIFEST.json`
  (`memory_app.py:419-421`); a manifest that lists both a `.task` and a `.onnx`
  is then invalid for both. Production defaults are distinct directories, so this
  only matters to a test that wants both models provisioned at once: pass both
  arguments.
- **F4 (low):** the `calibrations` record has no `source_note` field
  (`register_calibration` allowed keys `episode_store.py:238`), so the CUTE
  attribution of §2.1 has nowhere to live in the database yet; it lives in
  `docs/LICENSES.md` §4/§5 until the first real calibration is made (CP4, with
  decision 8).
- **F5 (low):** `server/requirements.txt` is still otherwise unpinned and still
  lists dead dependencies (CP2 finding 7, unchanged; purge pending the user).

### P2.5 §0 and §6, updated

§0 stands as written with two refinements: in step 5, `python scripts/fetch_models.py
--dry-run` now reports the ONNX entry as `missing` (exit 1) before the export and
`present … local export` (exit 0) after it, and the `.gitignore` check must also
cover `*.pth`; and before enabling, the operator must also **register and approve a
real calibration** for the exact tag printed in `GET /api/health` (`dinov2_vits14@<hash16>-r1`),
because by coordinator decision `physical_instance_recognition.enabled` is false
until one exists (an enabled model without it still runs and reports
"no approved calibration: identity stays provisional", which is the correct state
for P-104 measurement).

§6 go/no-go, what remains after this diff:

| Condition (§6) | State after pass 2 |
| --- | --- |
| 1. Export done and recorded | **open**, human (§0 steps 1-5); script, pins and register are ready |
| 2. Gate code separated | **done** (P2.2 items 2-5); `.gitignore` additions pending on disk (coordinator) |
| 3. Tester's suites green, no new runtime dep, no egress | **done** for the server suites in my read-only run (41 + 161); the smoke test with the model present waits for the model |
| 4. Real approved calibration, never `synthetic` on the rig | **open**, human: `register_calibration` + `approve_calibration(actor="operator")` with `source` `cute`/`own-footage`/`holoassist`; the server now also makes `enabled` depend on it |
| 5. Actor rule enforced | **done** (`ACTORS`, literal in `call_correction`, bodies without `actor`, tester `:602`) |
| 6. No embedding leaves the device | **done** (P2.2 item 1) |
| 7. Hand-in-crop guard | **deferred to CP4** (decision 7); rest-frame regions only in CP3 holds (`localizer.py` emits regions on the last keyframe only) |
| New: F1 and F2 | **recommended before the rig**, not blockers for the deterministic path |

**Still no-go for the real model** (conditions 1 and 4 are human actions); **go for
CP3 acceptance on the deterministic embedder** from Oversight's side, subject to the
tester's verdict and the coordinator's call on F1/F2.

## Interface notes

- `docs/LICENSES.md` now has a `VERIFIED-COMMERCIAL` row naming `dinov2_vits14.onnx`
  with `Apache-2.0` on the same line (§3b), which is what `check_pin` and
  `licence_verified` look for; the pins entry must keep `sha256: null` until the
  export has run on the laptop. `onnxruntime` is a runtime row in §1 at 1.30.0.
- The ONNX model must live in a server-side directory with its own manifest, never
  under `phone/assets/models/` (the CP2 manifest validator rejects `.onnx` and fails
  closed for every asset; the browser route is public).
- Export contract: input `image [1,3,224,224]` float32, output `patch_tokens
  [1,256,384]` = `forward_features(x)["x_norm_patchtokens"]`, opset 17, static shapes,
  no preprocessing in the graph; preprocessing lives in `perception/identity.py` and
  should be part of the embedder tag.
- `actor` is a closed set of role strings chosen by the server, never a request field.
- No route returns vectors, scores or banks; cloud chat sends text only.
- CUTE attribution text for any calibration made from it is in §2.1; a quantile is
  not a derivative but is attributed anyway.

## Open questions

See §7 (ten items, numbered for the coordinator's relay).

## Appendix A. Reference implementation of `scripts/export_dinov2_onnx.py`

Builder B owns the file; this listing is the specification in executable form and
has **not** been run (no torch, no weights in the sandbox).

```python
#!/usr/bin/env python3
"""Export DINOv2 ViT-S/14 (facebookresearch/dinov2, Apache-2.0) to ONNX for PAM's identity stage.

Dev-time only: requires requirements-dev.txt (torch, onnx, onnxruntime). Never imported by the served app.
Pins: repository commit EXPECTED_COMMIT, upstream weights dinov2_vits14_pretrain.pth (hash recorded in
scripts/model_pins.json), output patch_tokens [1, 256, 384] = forward_features(x)["x_norm_patchtokens"],
opset 17, static input image [1, 3, 224, 224]. Provenance is written next to the model as
<out>.provenance.json. See docs/OVERSIGHT_CP3.md section 1.3.
"""
from __future__ import annotations

import argparse, hashlib, json, os, platform, subprocess, sys, time
from pathlib import Path

EXPECTED_COMMIT = "7764ea0f912e53c92e82eb78a2a1631e92725fc8"
REPO_URL = "https://github.com/facebookresearch/dinov2"
WEIGHTS_URL = "https://dl.fbaipublicfiles.com/dinov2/dinov2_vits14/dinov2_vits14_pretrain.pth"
OPSET, SIDE, DIM, PATCHES = 17, 224, 384, 256
PARITY_TOL = 1e-3


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", type=Path, required=True, help="local clone of facebookresearch/dinov2")
    ap.add_argument("--weights", type=Path, required=True, help="dinov2_vits14_pretrain.pth")
    ap.add_argument("--out", type=Path, required=True, help="destination, e.g. server/models/dinov2_vits14.onnx")
    ap.add_argument("--expect-weights-sha256", default=None, help="refuse unless the .pth hashes to this")
    ap.add_argument("--allow-commit", default=None, help="override EXPECTED_COMMIT (recorded in the sidecar)")
    args = ap.parse_args()

    os.environ.setdefault("XFORMERS_DISABLED", "1")  # plain scaled_dot_product_attention path
    head = subprocess.run(["git", "-C", str(args.repo), "rev-parse", "HEAD"], check=True,
                          capture_output=True, text=True).stdout.strip()
    expected = args.allow_commit or EXPECTED_COMMIT
    if head != expected:
        print(f"refused: repository HEAD {head} is not {expected}")
        return 2
    weights_sha = sha256_of(args.weights)
    if args.expect_weights_sha256 and weights_sha != args.expect_weights_sha256.lower():
        print("refused: weights SHA-256 mismatch")
        return 2

    import numpy as np
    import onnx
    import onnxruntime
    import torch

    sys.path.insert(0, str(args.repo.resolve()))
    from dinov2.hub.backbones import dinov2_vits14  # not torch.hub.load: hubconf imports NC siblings' code

    model = dinov2_vits14(pretrained=False)
    state = torch.load(str(args.weights), map_location="cpu", weights_only=True)
    model.load_state_dict(state, strict=True)  # the architecture check
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
    tmp = args.out.with_suffix(".onnx.tmp")
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

    generator = torch.Generator().manual_seed(1234)
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
        "parity": {"max_abs_diff": max_abs, "mean_abs_diff": mean_abs, "tolerance": PARITY_TOL, "seed": 1234},
        "preprocessing": "none in the graph; perception/identity.py prepare_dinov2_input (RGB, 224x224 resize, ImageNet mean/std)",
    }
    args.out.with_name(args.out.name + ".provenance.json").write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"exported {args.out.name} ({sidecar['bytes']} bytes) sha256 {sidecar['sha256']} parity max_abs {max_abs:.2e}")
    print("next: record sha256 in scripts/model_pins.json and docs/LICENSES.md section 3b, then python scripts/fetch_models.py --only dinov2_vits14.onnx")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```
