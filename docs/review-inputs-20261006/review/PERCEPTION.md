# PERCEPTION review of MEMORY_SYSTEM_V4 (final, round 2)

Reviewer: PERCEPTION (vision methods). Materials read: `spec/MEMORY_SYSTEM_V4.md` Part 1 (section 7 tiers L107-L135, browser rig L136-L167, stage contracts L169-L189), `final/ARCH.md` (round-2 revision, BL-1..BL-11, R1..R7, sections 6-7), `final/MEMORY.md` (sections C, D, E, Answers to PERCEPTION, Questions for PERCEPTION), `final/COMMERCIAL.md` (sections 1-4, Answers to PERCEPTION, Reactions to PERCEPTION), `code/perception/{interaction,capture,memory_pipeline}.py`, `code/CLAUDE.md` L170-L200, L285-L320, L420-L435.

Marking: `[V: url]` is a page I opened; `[V-peer: url]` is a page a peer opened that I did not; `[B]` is a belief. Every license is `[V]` or `[V-peer]` from the LICENSE file, model card or terms page unless it says `[B]`.

---

## Round 2 changes

What changed from the round-1 final, and which peer answer drove it.

1. **Section G rewritten (COMMERCIAL A1).** Evaluation-only use of non-commercial footage during product development is not defensible: CC BY-NC's test is the primary purpose of the use [V-peer: https://wiki.creativecommons.org/NonCommercial_interpretation] and Aria Digital Twin says so outright [V: https://www.projectaria.com/datasets/adt/license/]. My round-1 `[B]` on this is now `[V-peer]`. Every "Evaluate during product development?" cell for an NC dataset is now No; `data/epic/P02_102.MP4` and `blockers/eval_epic.py` must be licensed (£7,000 micro licence) or deleted. HOT3D sequences: COMMERCIAL would not evaluate on ShareAlike material either; accepted, nothing in the build needs them.
2. **Section F corrected (COMMERCIAL A3, register §3).** Roboflow private projects grant Roboflow an internal-training licence on uploaded content unless the Core-plan opt-out is exercised [V-peer: https://www.roboflow.com/terms §4(b); https://roboflow.com/pricing]; weight download is "for select models", in-app on Enterprise and through the Inference package elsewhere [V-peer: pricing]. PML 1.0 text is now `[V-peer: https://roboflow.com/platform-model-license-1-0]`: account-bound, usage tracking, no extraction of pre-training weights. Edge Impulse is rejected for anything touching household footage (its §3.9 perpetual irrevocable Customer Data licence [V-peer: https://edgeimpulse.com/legal/terms-of-service]), not merely "not relevant". The labeling default becomes self-hosted CVAT (MIT [V: https://raw.githubusercontent.com/cvat-ai/cvat/develop/LICENSE]) or Label Studio (Apache-2.0 [V: https://raw.githubusercontent.com/HumanSignal/label-studio/develop/LICENSE]); Labelbox only with a written no-training clause.
3. **DINOv3 fallback stands (COMMERCIAL A2).** Approved with conditions (fallback only, licence snapshot at acceptance, counsel's initial before a shipped build depends on it). No change to D except the condition text.
4. **MediaPipe weights `[B]` → `[V-peer, secondary]`** (COMMERCIAL register §1: Luxonis model-zoo entry lists Apache-2.0; Google's own page gives no licence line; the model-card PDF is still unread). The npm package's MediaPipe privacy-notice pointer must be read before the pilot.
5. **Localizer contract changes (MEMORY A1, A4, A5; ARCH BL-6, BL-9.9).** `target_region` becomes `target_regions[]` of at most two rival regions with `rival_of`; every identity crop carries a foreground mask; the OCR source crop is stored per episode; a new optional-null `container_region`, with the condition in section 3 below that the localizer fills its geometry and the identity stage fills its `item_id`.
6. **Re-observation (MEMORY E) accepted with conditions**, and RepViT-SAM is now on the query path (bounded to 3 calls, 2 s timeout). The write-time mask requirement is what makes MEMORY's masked-token index possible; section C says where each mask comes from.
7. **BL-10 accepted with two additions** (section 3): the hand-busy rule tolerates a Worker that delivers under 6 fps, and the localizer interpolates `hand_bbox` across burst frames that have no landmarks and flags it.
8. **BL-11 accepted with one condition** (section 3): raw landmarks are retained at least as long as MEMORY's `episode_revisions` window, because a superset revision re-runs the localizer and the carry hull needs the 21 points.
9. **Teacher for the week-4 pseudo-labels named (COMMERCIAL A1/A4).** The L243 "teacher" must have clean terms: SAM 2 (Apache-2.0 [V]) for masks, MediaPipe for hands, humans for contact state. Never the public 100DOH, Hands23 or EgoHOS checkpoints, whose outputs would carry their NC provenance into our labels [B on the legal question; the practical answer is not to find out].
10. **Answers to MEMORY's three questions to PERCEPTION** added (masks at write time; 518 px index cost and the pooling loss; SigLIP 2 zero-shot category at indexing).
11. **Positions section** added for BL-10, BL-11, MEMORY's re-observation and `container_region`, and COMMERCIAL's training-data verdict.

Nothing in round 2 changed a primary/fallback choice in the decisions table; what changed is conditions, contract fields and the data policy.

---

## Decisions in one table

| Item | Primary | Fallback | Not this |
| --- | --- | --- | --- |
| A. Hand presence + landmarks (phone, Safari JS) | MediaPipe Hand Landmarker, `@mediapipe/tasks-vision` 1.1.0 (Apache-2.0), VIDEO mode, `numHands=1` in Idle/Escalating, GPU delegate in a Worker, gated by a frame-difference energy test | Same task, CPU/WASM delegate; or the OpenCV Zoo ONNX ports of the same palm detector and landmark model (Apache-2.0) under onnxruntime-web | A separate "cheap palm detector": it does not exist as a cheaper model (the palm detector is the heavier of the two) |
| B. Grasp/contact | Phone: landmark-only "hand busy" heuristic as a capture trigger (no published P/R exists; tuned for recall). Laptop, tier 4: the localizer's pre/rest difference is the contact decision that reaches the ledger | Laptop, tier 4 only, if week 4 says contact is the bottleneck: a 100DOH-ontology hand+contact-state detector (RF-DETR Apache tier or D-FINE COCO-only) trained on HoloAssist + own footage | Running any image contact model on the phone in v1; shipping or pseudo-labeling with the public 100DOH/EgoHOS/Hands23 checkpoints |
| C. Localization | `pre_rest_diff` with the existing `ego_homography` registration, on a structure/gradient difference not raw intensity; up to two rival regions, each with a mask | `carry_flow` on a 10-frame `carry_burst[]` (sparse LK, OpenCV); proposer of last resort: RepViT-SAM (Apache-2.0) point/box-prompted from the hand's last position; SAM 2 on the charger/teacher tier, and on the event path only if week 1 measures it under 300 ms on a crop | EdgeSAM (S-Lab non-commercial), FastSAM (AGPL), YOLO-World (GPL-3.0), anything via `ultralytics` (AGPL), OWLv2/Grounding DINO per event (CPU seconds) |
| D. Identity embedding | DINOv2 ViT-S/14 (Apache-2.0), foreground-masked mean-patch, CLS kept as a second vector; conformal set per MEMORY C, the 0.15 margin only as the logged interim | DINOv3 ViT-S/16 (DINOv3 License; commercial allowed, fallback only with COMMERCIAL's conditions) if the separation in MEMORY A3 is not met; SigLIP 2 (Apache-2.0) stays the text space | DINOv2 CLS alone; any margin treated as a constant |
| E. OCR on label crops | Rig: PaddleOCR PP-OCRv5 mobile (Apache-2.0), Python, CPU. Native iOS: Apple Vision `RecognizeTextRequest` accurate path | Rig on a Mac: Apple Vision via a small Swift helper; Tesseract + tessdata (Apache-2.0) as the zero-dependency last resort. Native Android: ML Kit on-device text recognition with the metrics disclosure | docTR (fine, but a second stack for no gain); Tesseract as primary |
| F. Buy vs build | Buy nothing for perception in v1. Label the audited teacher batch in self-hosted CVAT or Label Studio | Local `rfdetr` training on a rented GPU for the Sentinel; Roboflow hosted only on Core with the data-use opt-out exercised in writing, Apache-tier RF-DETR only, weights exported | Ultralytics (AGPL covers trained weights), Edge Impulse (perpetual Customer Data licence), PML-tier RF-DETR (account-bound), Landing AI / HF Inference on the write path |
| G. Data | Train: HoloAssist (CDLA-Permissive-2.0) + own footage; Ego4D only after COMMERCIAL reads the PDF and the company signs. Evaluate: CUTE (CC BY 4.0) for identity; own scripted footage for everything else | Buy the EPIC-KITCHENS-100 commercial licence (£7,000, 5 or fewer employees) after reading its permitted-use text, if kitchen footage is wanted for anything | EPIC-KITCHENS unlicensed (CC BY-NC), Aria Digital Twin (non-commercial, bars product development explicitly), HOT3D (hand labels NC; sequences ShareAlike), Assembly101 (CC BY-NC), HOI4D (CC BY-NC per secondary), EgoObjects (research-only until its PDF is read), PerMIR (no licence) |

---

## A. Hand presence and landmarks in the browser

### What the task actually is

MediaPipe Hand Landmarker is two models: a palm detector on the full image returning an oriented box, then a landmark model on the crop returning 21 points; in VIDEO mode the crop is derived from the previous frame's landmarks and "only when the landmark model could no longer identify hand presence is palm detection invoked to relocalize the hand" [V: https://raw.githubusercontent.com/google-ai-edge/mediapipe/master/docs/solutions/hands.md]. The Tasks web guide says the same: "if the tracking fails, Hand Landmarker triggers hand detection. Otherwise, it skips the hand detection"; `detect()`/`detectForVideo()` "run synchronously and block the user interface thread", hence the Worker [V: https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/web_js]. Options: `numHands` (default 1), `minHandDetectionConfidence`, `minHandPresenceConfidence`, `minTrackingConfidence`, all default 0.5 [V: same]. Output: 21 normalised `landmarks`, `worldLandmarks` in metres, `handedness` [V: same]. The landmark model emits "a hand flag indicating the probability of hand presence" used to decide when to re-run the detector [V: https://arxiv.org/pdf/2006.10214].

Input sizes: palm detector 192×192, landmark model 224×224 (the OpenCV Zoo ONNX ports of the same models are benchmarked at those sizes) [V: https://raw.githubusercontent.com/opencv/opencv_zoo/main/benchmark/README.md]. The Tasks page says the bundle accepts 192×192 or 224×224 and was trained on about 30K real images plus synthetic hands [V: https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker].

Consequence for the spec's "256 px downscale" (L112): the task resizes to 192/224 internally. Sending 256 px buys nothing over 224 px, and a hand 0.7 m from a chest mount is tens of pixels in a 224 px image (ARCH R1). The analysis size is chosen by ARCH's R1 experiment (256 vs 384), not fixed at 256; ARCH has adopted this (BL-4).

### Licenses

- Code: `@mediapipe/tasks-vision` 1.1.0 on npm declares `Apache-2.0` [V: https://registry.npmjs.org/@mediapipe/tasks-vision/latest]. The MediaPipe repo LICENSE is Apache-2.0 [V: https://raw.githubusercontent.com/google-ai-edge/mediapipe/master/LICENSE].
- Weights (`hand_landmarker.task`): the model card PDF on `storage.googleapis.com` is the authoritative statement and was unreachable for both me and COMMERCIAL. A third-party model zoo attributes the model to Google under Apache 2.0 [V-peer, secondary: https://models.luxonis.com/luxonis/mediapipe-hand-landmarker/aim_RzL7sdeEnsZ9Kbi1XDbXqb]; Google's own task page gives no licence line for the bundle [V]. The OpenCV Zoo's ONNX conversions are Apache-2.0 [V: https://huggingface.co/opencv/opencv_zoo/blob/07ad80ff0aec935e1401f56f5c68b7deb1c3400e/models/handpose_estimation_mediapipe/README.md; https://raw.githubusercontent.com/opencv/opencv_zoo/main/LICENSE]. COMMERCIAL's condition stands: record the model-card line when someone can open the PDF; ship the Apache-2.0 text and "Copyright Google LLC" on a third-party-notices page; keep the licence header in the served bundle; read the MediaPipe privacy notice the npm package points at [V-peer: COMMERCIAL register §1].
- Training data: Google's own, not redistributed; no terms flow [V: Tasks page].

### Is there a cheap "hand present" signal for tier 1? (ARCH question 4; BL-7 resolved)

No cheaper model exists inside the task, and the cost structure is the opposite of what L112 assumes:

- In a frame with no hand, the task runs the palm detector on the full image and skips the landmark model [V: hands.md and web_js pages above]. "Idle, no hand" already costs exactly one palm-detector pass.
- The palm detector is the heavier of the two models: Intel 12700K with OpenCV DNN, palm detector 192×192 = 5.35 ms, landmark model 224×224 = 2.40 ms; Raspberry Pi 4, 97 ms vs 42.6 ms [V: https://raw.githubusercontent.com/opencv/opencv_zoo/main/benchmark/README.md]. A standalone palm detector (the `hand_detection_mobile.pbtxt` graph natively [V: hands.md], or the OpenCV Zoo ONNX under onnxruntime-web) is not a saving.
- The JS API does not expose the palm-detector score separately [B]; "hand present" is a non-empty `HandLandmarkerResult`, thresholded by `minHandDetectionConfidence` [V: web_js page].

The tier-1 check is therefore non-neural, as ARCH wrote into BL-7:

1. Frame-difference energy on the downscaled canvas (sub-millisecond) gates the landmarker; a 1 Hz heartbeat call runs regardless. ARCH's condition on the energy region is accepted: initial region is the lower 80% of the frame including both edges (hands on a wheelchair mount enter from the sides), checked in week 1 against side entries; the skip rate is a counter.
2. `numHands=1` while Idle/Escalating; with `numHands=2` and one hand tracked, the legacy graph re-runs palm detection every frame looking for the second hand [B, from the graph's design]; raise to 2 only in Active. The runtime cost of the `setOptions` switch is a week-1 measurement (ARCH 4.8).

### Realistic Safari ms/frame (BL-10)

There is no published Safari number for the current Tasks API. The only published browser measurements are Google's 2021 TF.js blog for the previous `@mediapipe/hands` solution: iPhone 11, MediaPipe runtime (WASM + GPU) 8 fps lite / 5 fps full; TF.js WebGL runtime 15 fps lite / 12 fps full; MacBook Pro 15" 2019 62/48 fps [V: https://blog.tensorflow.org/2021/11/3D-handpose.html]. The same iPhone 11 runs the landmark model natively in 1.1 ms (lite) / 5.3 ms (full) [V: https://arxiv.org/pdf/2006.10214]: a 15 to 40 times gap between native and browser on one phone, the strongest evidence for L23's "a measurement of the rig implementation, not a bound on the target".

Planning numbers: 60 to 150 ms per analysed frame on a 2021-era iPhone in Safari, possibly 30 to 60 ms on a 2024-era iPhone with the WebGL delegate working in the Worker [B]. The spec's "20 to 40 ms" (Part 2 L345) has no source. ARCH's BL-10 (10 fps capture into the ring buffer is the hard floor; landmark rate measured; L180 becomes "3 consecutive analysed frames within 500 ms") is accepted; two additions are in section 3 below.

Google's native numbers for reference: 17.12 ms CPU / 12.27 ms GPU on a Pixel 6 for the full task [V: https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker].

---

## B. Grasp/contact detection

### Landmark-only (ARCH question 5)

No published precision/recall exists for a landmark-only "holding an object" classifier in egocentric household footage. The closest geometry-based work needs the object's pose as well as the hand's: contact detection from grasp-quality metrics reaches "approaching 90%" accuracy on DexYCB with object and hand poses as input and is not real-time [V: https://arxiv.org/abs/2501.06987]. MediaPipe's Gesture Recognizer has a closed-fist class, a gesture, not contact [B]. The finger-curl heuristic in Part 2 L346 is unvalidated in the literature; acceptable for v1 only with its role narrowed (below). ARCH 4.3's suggestion to compute the curl on `worldLandmarks` (metres, scale-free) rather than image-space distances is right.

### Image-based models with reported numbers

- 100DOH hand-object detector (Faster R-CNN ResNet-101): `handobj_100K+ego` scores Hand AP 90.4, Hand+Side 88.4, Hand+State 73.2, Hand+Object 47.6, All 39.8 on the authors' 100K+ego test set; `handobj_100K` 89.8 / 65.8 / 62.4 / 27.9 / 20.9 [V: https://raw.githubusercontent.com/ddshan/hand_object_detector/master/README.md]. The paper's 100DOH test set: Hand AP 89.6, Hand+State AP 64.0, Hand+Object AP 46.9; no per-state precision/recall; egocentric hand side is a named failure mode [V: https://arxiv.org/pdf/2006.06669]. Code MIT [V: https://raw.githubusercontent.com/ddshan/hand_object_detector/master/LICENSE]; weights on Google Drive with no licence line [V: README]; the `+ego` model's extra egocentric frames come from NC sources (EPIC-KITCHENS, EGTEA, Charades-Ego) [B]; 100DOH frames are 27.3K YouTube videos [V: arXiv] with no redistribution licence [B].
- Hands23 (NeurIPS 2023): 257K images, 401K hands, 288K objects, 19K second objects spanning four datasets; hand and in-contact object boxes and masks, contact and grasp type [V: https://fouheylab.eecs.umich.edu/~dandans/projects/hands23/]. Code MIT [V: https://raw.githubusercontent.com/EvaCheng-cty/hands23_detector/main/LICENSE]; weights served from the authors' server with no stated licence [V: README]; sources include EPIC-KITCHENS and Ego4D frames [B].
- EgoHOS (ECCV 2022): code MIT [V: https://raw.githubusercontent.com/owenzlz/EgoHOS/main/LICENSE]; dataset by script with no licence file in the repo [V: README]; sourced from Ego4D, EPIC-KITCHENS, THU-READ and others [B].
- HOT3D: hand annotations CC BY-NC-SA; sequences CC BY-SA; object models CC BY-SA with a no-sale clause [V: https://projectaria.com/datasets/hot3D/license]. Not usable for a commercial contact model.
- 2025: a real-time industrial egocentric HOI system (EfficientNetV2 + Mamba, fine-tuned YOLO-World) reports 85.13% AP for hand and object and 38.52% p-AP for interaction on ENIGMA-51 at 30 fps; no code or licence stated [V: https://arxiv.org/abs/2507.13326]. YOLO-World is GPL-3.0 [V: https://raw.githubusercontent.com/AILab-CVC/YOLO-World/master/LICENSE].

### Decision (BL-1 confirmed by ARCH)

- The phone's Escalating→Active decision stays on landmarks; its meaning is "hand busy" (closed or pinching, for 3 analysed frames), a capture trigger tuned for recall. A false trigger costs a packet; a missed one costs an episode. It is not called contact anywhere in the contract.
- The decision that reaches the ledger ("an object changed place while a hand was near it") is the laptop localizer's pre/rest difference (section C), and it is what the week-4 Sentinel decision scores.
- If week 4 shows contact is the bottleneck, the image contact model is a tier-4 stage on the packet's `grasp`/`carry` keyframes, trained from scratch (RF-DETR Nano/Small, Apache tier [V: https://raw.githubusercontent.com/roboflow/rf-detr/develop/README.md]; or D-FINE COCO-only checkpoints [V: https://raw.githubusercontent.com/Peterande/D-FINE/master/README.md L137]) on HoloAssist plus own footage with the 100DOH label ontology (hand box, side, contact state, object box). It never runs on the phone in v1.
- The teacher for L243's "pseudo-label one hour" is SAM 2 for masks [V: https://raw.githubusercontent.com/facebookresearch/sam2/main/LICENSE] plus MediaPipe for hand boxes plus human contact-state labels in CVAT/Label Studio; the public 100DOH/Hands23/EgoHOS checkpoints are not used even as teachers.

---

## C. Object-region localization per episode

### `pre_rest_diff` (primary)

Mechanism already in the code: `ego_homography` masks the boxes, `goodFeaturesToTrack` 300 corners, pyramidal LK, RANSAC homography [V: code/perception/memory_pipeline.py L74-L87]; measured 7.6 ms per frame pair on the Mac and 13 to 39 ms on the Windows laptop at 640 px [V: code/CLAUDE.md L182, L427]. Changes for R2 (ARCH's localization risk) and MEMORY A1:

1. Difference a structure map, not intensity: per-pixel gradient-orientation or local-SSIM difference after registration, which survives the auto-exposure and white-balance shift between pre-contact and rest frames. Cost is one Sobel pass [B].
2. Two regions are expected (where the object left, where it arrived) and sometimes a brushed second item. Output `target_regions[]` of at most two entries, each `{frame_id, bbox, mask, region_confidence, rival_of}`; identity runs on both crops; MEMORY's resolution rule applies (two singleton matches to different items split the episode; both matching one item keeps the region nearest the release point; an ambiguous crop writes nothing to the bank) [V-peer: final/MEMORY.md Answers to PERCEPTION 1]. ARCH has written this as BL-9.9.
3. Every region carries a foreground mask (MEMORY question 1 to PERCEPTION). Where it comes from: for `pre_rest_diff`, the connected component of the thresholded structure difference is itself the mask; for `carry_flow`, the co-moving pixel set minus the hand hull; for `proposer`, the SAM mask. Only a region that arrives as a bare bbox (none of the three sources does) would need GrabCut; GrabCut (OpenCV, Apache-2.0 [V: https://raw.githubusercontent.com/opencv/opencv/4.x/LICENSE]) inside the bbox is acceptable there. Masks are stored with the exemplar so MEMORY's foreground-pooled tokens and the re-observation index use the same vector.
4. `release_point {frame_id, x, y}`: the hand's centroid at the frame where "hand busy" went negative, already needed for the rest-region tie-break; also the geometry `container_region` needs (section 3).

### `carry_flow` (ARCH question 1; BL-2 resolved)

The pyramidal LK bound is formal: "dmax final = (2^(Lm+1) − 1) dmax", a gain of 15 at three levels [V: https://www.cs.ucf.edu/courses/cap4453/bouguetopticalflow.pdf]; with OpenCV's default 21-px window and 3 levels that is about 150 px at analysis resolution, so the search radius is not the binding constraint. What binds is the appearance assumption: across 300 ms a hand-held object rotates, scales and is re-occluded by the fingers; the code base already saw the homography fit fail at 333 ms spacing on a moving chair [V: code/CLAUDE.md L185-L190].

Geometry at 256 px analysis width with a 26 mm-equivalent rear camera (about 69° horizontal): focal length about 186 px; a hand 0.5 m from a chest mount moving 0.3 to 1.0 m/s projects to 110 to 370 px/s, i.e. 11 to 37 px per frame at 10 fps and 37 to 124 px per frame at 3 fps [B, arithmetic]. At 10 fps the displacement is inside the comfortable LK regime; at keyframe spacing it is not. Maximum dependable spacing: about 100 ms.

Decision (agreed with ARCH): `carry_burst[]` of up to 10 consecutive analysis-resolution grayscale JPEGs at 10 fps, centred on the carry midpoint, quality 80, about 8 to 12 KB each [B], present only when the controller saw a carry of at least 0.5 s; `region_source = none` for `carry_flow` whenever the burst's actual spacing exceeds 150 ms. ARCH's note that the burst is cut from the ring buffer's bitmaps at encode time is right: it costs ten small encodes and nothing on the analysis path. Burst at 320 px if the Worker budget allows: a pill bottle at 0.5 m is about 25×50 px at 256 px width [B], close to L175's 400 px² acceptance threshold.

BL-10 consequence: burst frames will often have no landmarks of their own. The localizer linearly interpolates `hand_bbox` and the hull between the nearest analysed frames and sets `hand_bbox_interpolated = true` on those frames; if the nearest analysed frames are more than 300 ms apart, the hull subtraction is skipped and the carry region is accepted only if it is at least 2× the 400 px² threshold [B as an initial rule].

### Class-agnostic proposer (ARCH question 2)

"Class-agnostic" here means: we hold a geometric prompt (the hand's last position, the diff blob) and need the extent of the thing at that position. That is a prompted segmenter, not an open-vocabulary detector.

| Model | Weights/code licence | Latency evidence | Verdict |
| --- | --- | --- | --- |
| RepViT-SAM | Apache-2.0 [V: https://raw.githubusercontent.com/THU-MIG/RepViT/main/LICENSE]; `repvit_sam.pt` from the repo release under the same licence [V-peer: https://raw.githubusercontent.com/THU-MIG/RepViT/main/sam/README.md] | 44.8 ms at 1024×1024 on a MacBook M1 Pro via Core ML; 48.9 ms on iPhone 12 [V: https://arxiv.org/pdf/2312.05760] | Primary fallback proposer; also MEMORY's query-time refiner (≤3 calls) |
| MobileSAM | Apache-2.0 [V: https://raw.githubusercontent.com/ChaoningZhang/MobileSAM/master/LICENSE] | 8 ms encoder + 4 ms decoder on one GPU [V: README]; 482.2 ms on M1 Pro via Core ML [V: RepViT-SAM PDF] | Second choice; original repo only, never the `ultralytics` wrapper |
| EfficientSAM | Apache-2.0 [V: https://raw.githubusercontent.com/yformer/EfficientSAM/main/LICENSE] | none found on CPU | Third |
| SAM 2 (hiera-tiny/small) | Apache-2.0 code and checkpoints [V: https://raw.githubusercontent.com/facebookresearch/sam2/main/LICENSE; README L198] | A100 fps only [V: README] | Teacher/charger tier; COMMERCIAL prefers it on the event path because licensor and releaser are one party; adopted conditionally (below) |
| EdgeSAM | S-Lab License 1.0, non-commercial [V: https://raw.githubusercontent.com/chongzhou96/EdgeSAM/master/LICENSE] | 38 FPS on iPhone 14 [V: README] | Excluded |
| FastSAM | AGPL-3.0 [V: https://raw.githubusercontent.com/CASIA-IVA-Lab/FastSAM/main/LICENSE] | | Excluded |
| RF-DETR Nano/Small/Medium/Large, all Seg sizes | Apache-2.0 [V: README; LICENSE]; Atto/Femto/Pico/XL/2XL are PML 1.0, account-bound: usable only while holding a Roboflow plan, licence ends when the account is not in good standing, no circumventing usage tracking, no extracting pre-training weights [V-peer: https://roboflow.com/platform-model-license-1-0]; "require a Roboflow account to run and fine-tune" [V: https://pypi.org/pypi/rfdetr_plus/json] | T4 TensorRT ms only [V: README] | COCO-vocabulary detector, not class-agnostic; a Sentinel fine-tune target |
| D-FINE | Apache-2.0 [V: LICENSE]; Objects365 checkpoints "should not be assumed to be commercially cleared" [V: README L137] | | Same role; COCO-only checkpoints |
| RT-DETR | Apache-2.0 [V: https://raw.githubusercontent.com/lyuwenyu/RT-DETR/main/LICENSE] | | Same role |
| YOLO-World | GPL-3.0 [V] | | Excluded |
| OWLv2 | Scenic code Apache-2.0 [V: https://raw.githubusercontent.com/google-research/scenic/main/LICENSE]; HF weights Apache-2.0 [B] | | Excluded per event (L124); offline labeler at most |
| Grounding DINO | Apache-2.0 [V: https://raw.githubusercontent.com/IDEA-Research/GroundingDINO/main/LICENSE] | | Excluded per event (L124) |

Training-data provenance: RepViT-SAM, MobileSAM and EfficientSAM are distilled from SAM on SA-1B, which Meta lists as "Research purposes only" [V-peer: https://ai.meta.com/datasets/segment-anything/]; the authors' Apache-2.0 is the term we receive, and COMMERCIAL records the provenance in its register [V-peer: final/COMMERCIAL.md §1]. SAM 2's training data (SA-V) is Meta's own, so COMMERCIAL prefers SAM 2 "wherever the latency allows". Position: the per-event proposer stays RepViT-SAM because SAM 2's CPU latency is unmeasured (only A100 numbers exist) and the event path has a 0.3 to 1 s budget shared with everything else; week 1 measures SAM 2.1 hiera-tiny on a 512 px crop on the laptop CPU, and if it is under 300 ms it replaces RepViT-SAM on the event path. SAM 2 is the teacher-tier segmenter either way.

Cost reality check: RepViT-SAM's 44.8 ms is M1 Pro via Core ML, not pure CPU; a pure-CPU ONNX run at 1024 px will be a few hundred ms [B]; encoding a 2.5× hand-box crop at 512 px roughly quarters it [B]. The spec's tier-4 budget is 0.3 to 1 s per event, localization included (L115), and the proposer runs only when differencing fails. Under 100 ms is nice, not required.

---

## D. Instance identity embeddings

### Models and terms

- DINOv2 ViT-S/14: Apache-2.0 for code and weights [V: https://raw.githubusercontent.com/facebookresearch/dinov2/main/LICENSE; README L660]; MODEL_CARD "License: Apache License 2.0" [V-peer: https://raw.githubusercontent.com/facebookresearch/dinov2/main/MODEL_CARD.md L32]; HF `facebook/dinov2-small` apache-2.0, 22.1M params [V: https://huggingface.co/facebook/dinov2-small]. Pin `dinov2_vits14` by name and hash: the same repo hosts XRay-DINO and Cell-DINO under the FAIR Noncommercial Research License [V: README L159-L160, L754-L757].
- DINOv3 ViT-S/16: "DINOv3 code and model weights are released under the DINOv3 License" [V: https://raw.githubusercontent.com/facebookresearch/dinov3/main/README.md L864]; royalty-free use, modification and distribution with no non-commercial clause; derivatives redistributed under the same Agreement with a copy attached; Meta may modify the Agreement with immediate effect; delete-and-cease on termination; indemnity and patent retaliation; no reverse engineering [V: https://raw.githubusercontent.com/facebookresearch/dinov3/main/LICENSE.md]. COMMERCIAL A2: fallback only, licence snapshot at acceptance, counsel's initial before a shipped build depends on it. Accepted as written.
- SigLIP 2: `google/siglip2-base-patch16-256` apache-2.0, trained on WebLI [V: https://huggingface.co/google/siglip2-base-patch16-256]; big_vision Apache-2.0 [V: https://raw.githubusercontent.com/google-research/big_vision/main/LICENSE]. Query-time text space (L119) and, per MEMORY D, zero-shot category and `is_container` at indexing (section 4, answer 3).

### CLS vs mean-patch, and the evidence on lookalikes (ARCH question 3)

CUTE (NeurIPS 2023 Datasets and Benchmarks; 18,000 images of 180 objects from 50 categories, mostly 2 instances per category; studio, pose and in-the-wild conditions; CC BY 4.0): with DINOv2 ViT-B/14 at 336 px and foreground filtering plus patch-level foreground pooling (which beat the class token), paired-object top-1 is 89.0% under illumination change, 96.6% under pose change, 61.8% in the wild (mAP 88.8 / 81.9 / 75.1) [V: https://arxiv.org/pdf/2311.00750]. Plain DINOv2 scores 29.7 mAP on PerMIR, built so that several instances of one category share a frame [V: https://arxiv.org/pdf/2405.18025], and 34.1 mAP / 45.7 Rank-1 on ShopID10K, 47.3 mAP on MVImageNet [V: https://openaccess.thecvf.com/content/ICCV2025/papers/Huang_Generalizable_Object_Re-Identification_via_Visual_In-Context_Prompting_ICCV_2025_paper.pdf].

What this means, now in MEMORY's terms:

1. Foreground-masked mean-patch is the matching vector, CLS a second vector for tie-breaks (CUTE evidence [V]). MEMORY adopted it and the localizer emits the mask (section C).
2. Two near-identical instances will have near-zero separation at any backbone size; that is the `group` path (rule 11, MEMORY C), not a threshold problem.
3. MEMORY A3 states what the tiering needs: at α = 0.05 a conformal singleton rate of at least 0.80 on distinct-instance queries; in cosine terms the 5th percentile of intra-instance similarity exceeding the 95th percentile of nearest-other-instance similarity by at least 0.05, EER at most 10%; in CUTE terms at least 0.85 top-1 on the in-the-wild non-lookalike subset at our crop size [V-peer: final/MEMORY.md Answers to PERCEPTION 3]. My estimate for ViT-S/14 mean-patch on 224 px native-resolution crops of visually distinct same-category items: intra 0.75 to 0.95, nearest-other 0.55 to 0.80 [B], so the 0.05 gap at the 5th/95th percentiles is plausible but not assured, and the ≥0.85 CUTE non-lookalike top-1 is plausible given 89.0/96.6% on the easier conditions with ViT-B [V]. If ViT-S misses it, the order of escalation is: 336 px crops (CUTE's setting), then DINOv3 ViT-S/16 under COMMERCIAL's conditions, then DINOv2 ViT-B/14 (86M; about 4× the cost, still within tier 4 on the laptop, not on a phone [B]).
4. The 0.15 margin survives only as MEMORY's logged interim (`calibration_id = margin_0.15_initial`); the conformal set replaces it once CUTE calibration exists (week 1, needs no footage) and the rig's 10-item set follows in week 2. ARCH's conditions in its section 7(d) are consistent with this.

Resolution: identity crops are cut from the 720p keyframe at native resolution and padded, never upsampled from the analysis frame; ARCH has written this into 2.2.

---

## E. OCR on label crops

- PaddleOCR: Apache-2.0 [V: https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/LICENSE]. PP-OCRv5 mobile on the project's CPU test rig averages 1.75 s per full image at default side length 736 (server 4.34 s) [V: https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/docs/version3.x/algorithm/PP-OCRv5/PP-OCRv5.en.md]; a label crop is a fraction of that [B]. The README lists PP-OCRv6 with a 1.5M tiny tier and "5.2× CPU speedup", and a browser SDK `PaddleOCR.js` [V: https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/README.md L49, L79, L102].
- Tesseract: Apache-2.0 [V: https://raw.githubusercontent.com/tesseract-ocr/tesseract/main/LICENSE]; tessdata Apache-2.0 [V-peer: https://raw.githubusercontent.com/tesseract-ocr/tessdata/main/LICENSE]. Needs dewarping on curved labels [B].
- docTR: Apache-2.0 [V: https://raw.githubusercontent.com/mindee/doctr/main/LICENSE]; not needed.
- Apple Vision `RecognizeTextRequest`: fast and accurate paths, language correction, per-observation confidence; iOS 18 / Xcode 16 for the Swift API [V: https://developer.apple.com/documentation/vision/locating-and-displaying-recognized-text.md]. An OS API under the platform agreements; the research-only language the spec worried about is in the Apple Machine Learning Research Model License on released checkpoints (MobileCLIP, FastViT), not in Vision [V-peer: https://raw.githubusercontent.com/apple/ml-mobileclip/main/LICENSE_MODELS]. My round-1 `[B]` is confirmed by COMMERCIAL A3.
- Google ML Kit text recognition: on-device, "ML Kit does not send that data and the resultant outputs to Google servers", but Google collects metrics and the app must disclose it; no reverse engineering [V: https://developers.google.com/ml-kit/terms]. Android/iOS apps only; native-Android target only.
- VLM-OCR (PaddleOCR-VL 0.9B and similar): charger tier at most [B].

Accuracy on curved pharmacy labels: no public benchmark exists; a 2025 survey gives document numbers only [V: https://intuitionlabs.ai/articles/non-llm-ocr-technologies]. Plan: 50 real labels on 10 bottles from the rig camera at 0.3 to 0.6 m, scored per field (drug name, patient name, Rx number, fill date) for PaddleOCR mobile, Apple Vision accurate, Tesseract with and without a cylindrical dewarp; half a day. Per-field confidence is stored; anything under threshold is absent, not a weak identifier (MEMORY reactions 8 agrees). The OCR source crop is stored per episode, not per item (MEMORY A4).

---

## F. Outsourced or hosted options (corrected against COMMERCIAL's register)

| Vendor | What it would replace in the spec | Terms | Cost and lock-in | Commercially usable output? | Position |
| --- | --- | --- | --- | --- | --- |
| Roboflow (RF-DETR, hosted training, Annotate, Workflows) | The week-4 Sentinel training and the labeling tool (L243); nothing on the v1 write path | RF-DETR Nano/Small/Medium/Large and Seg weights Apache-2.0; Atto/Femto/Pico/XL/2XL PML 1.0 [V: README; pypi rfdetr_plus]; PML 1.0 is account-bound with usage tracking and no extraction of pre-training weights [V-peer: https://roboflow.com/platform-model-license-1-0]. Licensing page: RF-DETR Apache-2.0, NAS models PML 1.0, Roboflow 3.0 AGPL-3.0, Roboflow 2.0 GPL-3.0 with plan-bound commercial licences [V: https://roboflow.com/licensing]. ToS §4(b), private projects: perpetual royalty-free licence to Roboflow for service provision and "internal business purposes, such as internal research, optimization, training and improving the Services" [V-peer: https://www.roboflow.com/terms]; Core plan "Data used to license and improve products", "Opt-out available"; Enterprise "Never" [V-peer: https://roboflow.com/pricing]. Weight download: "for select models", in-app on Enterprise, via the Inference package or MCP server elsewhere [V-peer: pricing]; Feb 2025 changelog said "Basic and Growth plans" [V: https://roboflow.com/changelog/download-trained-model-weights-from-roboflow] | Core $39/month [V-peer: pricing]; local `rfdetr` training is free. Lock-in only with PML-tier models or hosted Workflows | Yes for Apache-tier RF-DETR trained locally or exported; no for PML tier | Local `rfdetr` on a rented GPU is the default (uploads nothing). Hosted only on Core with the data-use opt-out exercised in writing before any household frame is uploaded, Apache tier only, weights exported and kept; never with agency frames unless Enterprise + BAA (COMMERCIAL A3) |
| Ultralytics | Nothing (L248 removes it) | "All Ultralytics YOLO trained models fall under the AGPL-3.0 License by default", including models trained from scratch; Enterprise License required for "Any commercial product or service" and "Embedded deployments in hardware, edge devices" [V: https://ultralytics.com/license] | Enterprise by quote | No without Enterprise; also excludes `ultralytics`-wrapped MobileSAM/FastSAM/YOLO-World | Rejected; the two AGPL lines are in `perception/requirements.txt` (ARCH's correction) and go in the day-1 purge |
| Edge Impulse | An MCU hand-presence model if a microcontroller wearable ever appears | Output assigned to the customer (§3.8), but the platform licence is "royalty free, limited, personal, revocable" and ends with the term; §3.9 grants Edge Impulse a "non-exclusive, worldwide, perpetual, transferable, irrevocable, sublicensable" licence over Customer Data [V-peer: https://edgeimpulse.com/legal/terms-of-service] | Plan-based [B] | Not with household footage | Rejected for anything touching household footage; irrelevant to the phone rig (corrected from "not relevant") |
| Landing AI (LandingLens) | Hosted labeling and classifier training | Not opened by me or COMMERCIAL [B] | Hosted inference per project [B] | A hosted endpoint on the write path contradicts L103 | Not now; nothing it offers beats self-hosted labeling plus local `rfdetr` |
| Hugging Face Inference Endpoints | Running DINOv2/SigLIP 2 remotely | CPU from $0.033/h, T4 $0.50/h, billed per minute [V-peer: https://huggingface.co/docs/inference-endpoints/support/pricing]; staff state no payload storage, 30-day access logs [V-peer, secondary] | None (our weights) | Yes | Not on the write path; a charger-tier batch would need the disclosure changed for about $2.50/month per household (COMMERCIAL §3), so not worth it at pilot scale |
| Scale AI / Labelbox | The labeling line ($8 to 15k, L206) | Scale: custom pricing, no public rates [V-peer, secondary]; Labelbox: free 5,000 rows/month, Starter $500/month, managed labeling $10/h [V-peer, secondary: costbench]; Labelbox data-use terms not opened [B] | Low; export COCO JSON | Yes (we own labels) | Default: self-hosted CVAT (MIT [V]) or Label Studio (Apache-2.0 [V]) for the one-hour audited batch, which uploads nothing. Labelbox only after a written no-training clause and a BAA if agency frames are involved; Scale not now |

Decision unchanged: buy no perception component for v1.

---

## G. Data (corrected against COMMERCIAL's register)

The governing rule, now verified: NonCommercial "depends on the primary purpose for which the work is used, not on the category or class of reuser" [V-peer: https://wiki.creativecommons.org/NonCommercial_interpretation; SPDX CC-BY-NC-4.0 §1]; evaluating a component we intend to ship is a commercial purpose; Aria Digital Twin says it outright [V: https://www.projectaria.com/datasets/adt/license/]. Bristol selling a commercial licence for EPIC-KITCHENS is itself evidence that company-internal use is not NonCommercial [V: https://express-licences.bristol.ac.uk/product/epic-kitchens-100---dataset]. What remains defensible is citing published numbers from papers that used NC benchmarks, which is what this review does.

| Dataset | Licence (primary where opened) | Train a commercial contact model? | Evaluate during product development? | Note |
| --- | --- | --- | --- | --- |
| HoloAssist (Microsoft) | CDLA-Permissive-2.0 [V: https://raw.githubusercontent.com/Ember-HoloAssist/holoassist-release/main/README.md]; §3.1 "This agreement does not impose any restriction or obligations with respect to the use, modification, or sharing of Results"; §5.4 Results include "machine learning models" [V-peer: https://raw.githubusercontent.com/spdx/license-list-data/main/text/CDLA-Permissive-2.0.txt] | Yes | Yes | Head-mounted HoloLens 2 egocentric video with hand pose streams (`Hands/Pose_sync.txt`) and fine/coarse action labels [V: README]; no contact-state labels, so the 100DOH ontology still has to be annotated by us; viewpoint differs from a chest or wheelchair mount, so own footage will dominate |
| CUTE | CC BY 4.0 [V: https://arxiv.org/pdf/2311.00750] | Yes (not needed) | Yes | 180 objects, paired lookalikes, in-the-wild condition; the identity calibration set (week 1, no footage needed) |
| Ego4D | Repo code MIT [V: https://raw.githubusercontent.com/facebookresearch/Ego4d/main/LICENSE]; dataset under a bespoke licence whose PDF neither I nor COMMERCIAL could open; a secondary source says it permits "qualifying machine learning research, training, evaluation, and product development" and bars resale or redistribution of footage [V, secondary: https://www.cloudpano.com/blog/is-ego4d-free-for-commercial-use] | Probably, pending the primary text [B] | Probably [B] | Hold: counsel reads the PDF; the company, not a lab, signs (COMMERCIAL §2) |
| Ego-Exo4D | Same licence family [B] | As Ego4D | As Ego4D | Same hold; it has hand pose annotations, which would matter for the Sentinel |
| EPIC-KITCHENS-100 | "Creative Commons Attribution-NonCommerial 4.0 International License"; "You may not use the material for commercial purposes" [V: https://data.bris.ac.uk/datasets/3h91syskeag572hl6tvuovwv4d/readme.txt]. Commercial licence: £7,000 (5 or fewer employees), £19,000 (SME), £49,000 (large), perpetual, non-exclusive, non-transferable [V: Bristol express-licences page]; permitted-use text behind "Preview terms" not opened | No without the paid licence | No (corrected from round 1) | `data/epic/P02_102.MP4` and `blockers/eval_epic.py` are licensed before week 4 or deleted in the day-1 purge; the Bristol permitted-use text is read before paying |
| HOT3D | Sequences CC BY-SA; hand annotations CC BY-NC-SA; object models CC BY-SA with a no-sale clause [V: https://projectaria.com/datasets/hot3D/license]; API code Apache-2.0 [V: https://raw.githubusercontent.com/facebookresearch/hot3d/main/LICENSE] | No (hand labels NC) | No: COMMERCIAL would not evaluate on ShareAlike sequences either, since an adapted model is arguably adapted material [B]; accepted, nothing needs them | |
| Aria Digital Twin | "non-commercial research" only; "you may not use the Dataset to develop any product that is currently (or that you intend to make or that becomes) available for any commercial use" [V] | No | No, explicitly | |
| Assembly101 | CC BY-NC 4.0 [V: https://raw.githubusercontent.com/assembly-101/assembly101-download-scripts/main/LICENSE] | No | No | |
| HOI4D | Repo code MIT [V: https://raw.githubusercontent.com/leolyliu/HOI4D-Instructions/main/LICENSE]; dataset CC BY-NC 4.0 per a secondary source [V, secondary: https://www.cloudpano.com/blog/egocentric-video-datasets-commercial-model-training]; not in COMMERCIAL's register | No | No | |
| 100DOH / Hands23 / EgoHOS | Code MIT [V: three LICENSE files in section B]; frames from YouTube, EPIC-KITCHENS, Ego4D and others with no redistribution licence [B] | No | No; ontology and label format only | The 100DOH ontology is our annotation schema (L243); the checkpoints are not teachers either |
| EgoObjects | Repo code MIT [V: https://raw.githubusercontent.com/facebookresearch/EgoObjects/main/LICENSE]; dataset page links a licence agreement neither of us could open; intended use "Research on continual learning ... Open-source for CVPR 2022 CLVision workshop" [V: https://ai.meta.com/datasets/egoobjects-dataset/] | Assume no [B] | Assume no [B] (corrected from "unknown") | CUTE covers the identity evaluation need |
| PerMIR | No licence stated; "We intend to make our generated datasets publicly available" [V: https://arxiv.org/pdf/2405.18025] | No | Cite, do not download | Evidence only |
| SA-1B | "Research purposes only" [V-peer: https://ai.meta.com/datasets/segment-anything/] | Not for us | n/a | Provenance of the SAM-family distilled weights (section C) |

Decision (COMMERCIAL's verdict, accepted): the Hand Sentinel, if trained, trains on HoloAssist plus our own audited footage, with Ego4D added only after the PDF is read and signed by the company; identity is calibrated on CUTE; no NC footage anywhere in the repo, CI, or the week-1/week-4 decisions.

---

## Answers to ARCH (round 1, unchanged; status after ARCH's round 2)

1. **carry_flow spacing.** About 100 ms; `carry_burst[]` as specified in section C. ARCH: BL-2 resolved.
2. **Fallback proposer.** RepViT-SAM; terms and the SA-1B provenance in section C; SAM 2 replaces it on the event path only if week 1 measures it under 300 ms on a 512 px crop. ARCH: 2.2 names it.
3. **DINOv2 margins.** Mean-patch foreground-masked; lookalikes are `group`; 0.15 is the logged interim; MEMORY's conformal set and separation bar replace it (section D). ARCH: R4 reframed.
4. **Cheap hand present.** None; non-neural gate; 60 to 150 ms planning number. ARCH: BL-7 resolved, BL-10 created, R1 reordered.
5. **Landmark-only grasp.** None published; "hand busy" trigger; contact is the laptop's pre/rest difference. ARCH: BL-1 confirmed.

## Answers to MEMORY's questions to PERCEPTION

1. **Masks for every identity crop.** Yes, from all three region sources at no extra cost: the connected component of the structure difference for `pre_rest_diff`, the co-moving pixel set minus the hand hull for `carry_flow`, the SAM mask for `proposer` (section C). GrabCut inside the bbox (OpenCV, Apache-2.0 [V]) is acceptable for the no-source case and costs tens of ms [B]; RepViT-SAM is not needed per episode for the mask. Masks are stored with the exemplar at crop resolution and downsampled to the patch grid when tokens are pooled.
2. **DINOv2 ViT-S/14 at 518 px on a laptop CPU.** No measured number exists in this review. Arithmetic: 777 tokens vs 256 at 224 px; the linear layers scale 3× and attention about 9×, so roughly 4 to 6× the 224 px cost; ViT-S/14 at 224 is about 4.6 GFLOPs, so about 20 to 28 GFLOPs per frame [B]; on a 4-core laptop CPU under PyTorch that is 60 to 200 ms [B], consistent with your 100 to 250 ms. Once per 30 s it is negligible; measure it in week 1 alongside the proposer. 2×2 pooling plus PCA-64: acceptable for frame-level scoring, because the refinement step recomputes unpooled tokens on the three shortlisted frames anyway and an unpooled fp16 index would be about 600 KB per frame, 1.7 GB per day [B]. Condition: verify on CUTE in-the-wild retrieval that the pooled/PCA index keeps at least 95% of the unpooled recall@3 before freezing the index format; if it does not, keep 2×2 pooling and raise PCA to 128.
3. **SigLIP 2 zero-shot category and `is_container` at indexing.** Yes. The text embeddings of the household and container vocabularies are computed once at startup (one text forward each, cached); each new candidate costs one SigLIP 2 image forward on its best crop, which L120 already schedules, plus a dot product. Tens of milliseconds per item on CPU for the base model [B]. Store the top-3 category scores and the container score as soft fields rather than a hard flag; set `is_container` true above a threshold calibrated on the rig set, and let user naming override. One caution: SigLIP 2 at 224 to 256 px on a 60 px object is a category guess, not a label; the ledger should treat it as a relevance prior, as L72 treats place.

---

## Positions on the contested items

**ARCH BL-10 (60 to 150 ms landmarker; 10 fps capture kept; landmark rate measured separately).** Accept, with two additions. (a) The hand-busy rule degrades gracefully: "3 consecutive analysed frames within 500 ms" holds down to a Worker rate of about 6 fps; below that, 2 consecutive analysed frames with a stricter curl threshold open Active, and the pre-roll plus burst from the 10 fps ring buffer supply the evidence the landmarks could not. The Worker's delivered rate is a per-episode field in the packet (`landmark_fps`) so the localizer and the pilot report can see it. (b) Burst frames without landmarks get interpolated `hand_bbox` and hull with a flag (section C); the localizer never treats an interpolated hull as observed. I do not accept lowering the capture rate; ARCH's reading of L134 as "capture is the hard floor" is the right one.

**ARCH BL-11 (reduce persisted landmarks after localization).** Accept the retention rule; the packet contract is unchanged. One condition: raw landmarks must outlive MEMORY's `episode_revisions` window, because a superset revision re-runs the localizer and the carry hull needs the 21 points; so `retention_until` for the raw landmark file is max(localization complete, the revision window, initial 72 h) [B as an initial value], and in any case before any training export. After that the stored record is `hand_bbox`, `handedness`, per-frame `hand_present`, `release_point`, the entry-edge flags rule 8 uses, and the wearer hand-size scalar. ARCH's development-phase exemption (weeks 1 to 4 on the team's own consented footage keep raw landmarks for the controller equivalence tests) is necessary and accepted. The wearer-only appearance bank with a written release and no template for anyone else are perception-neutral: nothing in sections A to D needs a non-wearer hand template.

**MEMORY's re-observation design (DINOv2-S at 518 px arrival index of idle frames, no proposer at arrival, at most 3 RepViT-SAM refinements at query, conformal singleton, 2 s timeout).** Accept, with conditions. (a) The arrival index and the exemplar bank must use the same masked-token recipe, which section C now guarantees. (b) The 28 px floor (about a 12 cm object within about 1.2 m at 518 px [V-peer: final/MEMORY.md E]) is a stated product limit; the pilot reports the distance distribution of visible relocations, and 1036 px indexing is the lever if the data says so. (c) RepViT-SAM on the query path is bounded to 3 calls; its CPU cost is the same week-1 measurement as the event-path proposer. (d) The co-visibility check needs a homography between X's last rest frame and the query frame; on a wheelchair that fit will fail often (CLAUDE.md L185-L190), so it must degrade to "no refusal, logged" rather than "refuse on failure" (ARCH's point to MEMORY; I agree). (e) Negative re-observation depends on the global vector matching the same surface view; a kettle moved on the same counter changes the global vector enough to miss the match [B], so it is a hedge input only, as MEMORY already says.

**MEMORY's `container_region` request (ARCH BL-6 resolved as optional-null).** Accept the field in the day-1 freeze, with one restructuring condition: the localizer runs before identity and cannot know `item_id` or `is_container`. The localizer therefore fills the geometry (`{frame_id, bbox, mask, confidence}` of the region in the rest frame that encloses `release_point` and persists from pre-contact to rest, when no target region was accepted), and the identity stage fills `item_id` and checks `is_container`. MEMORY's three required conditions map onto that: (a) is the localizer's "no accepted rest region plus the object left its pre-contact position"; (b) and (c) are the enclosing-region geometry plus the identity stage's match. Automatic containment is reported, not gated, and case 5 is scored on hand-labelled containment events in v1; agreed with both peers.

**COMMERCIAL's training-data verdict (HoloAssist plus own footage only; CUTE for identity evaluation).** Accept without condition, and with two consequences for the perception plan: (a) the L243 teacher is SAM 2 plus MediaPipe plus human contact labels, never the public NC-trained contact checkpoints; (b) because HoloAssist is a head-mounted viewpoint with no contact-state labels, the Sentinel's training set will be mostly our own footage, which raises the value of the correction loop's audited labels (L87) and of recording the mount-specific footage early (ARCH's week-1 track b). Ego4D joins only after the PDF is read and the company signs.

---

## Reactions to peers

ARCH's round-2 items addressed to PERCEPTION (its "To PERCEPTION" 1 to 6) are all acceptances of round-1 content; the energy-region condition is taken up in section A. MEMORY's answers 1 to 4 and COMMERCIAL's answers 1 to 3 plus its reactions 1 to 7 are reconciled below.

### Peer answers to my questions: resolved, changed, or disputed

| Peer | Question | Status | Effect |
| --- | --- | --- | --- |
| MEMORY 1 | Two candidate regions | Resolved: both, as rival hypotheses with `rival_of` | Localizer output `target_regions[]` (section C); ARCH BL-9.9 |
| MEMORY 2 | Re-observation without a proposer | Changed my recommendation: the arrival index needs no proposer, but RepViT-SAM is on the query path (≤3 calls); idle frames at capture resolution, indexed at 518 px | Positions above; masks at write time (section C) |
| MEMORY 3 | Separation the tiering needs | Resolved as a bar to measure (0.05 gap at 5th/95th percentiles, EER ≤ 10%, ≥ 0.85 CUTE non-lookalike top-1); plausible for ViT-S but unverified [B] | Escalation order in section D; week-1 CUTE calibration |
| MEMORY 4 | Per-member crops | Resolved | OCR source crop per episode |
| COMMERCIAL 1 | Eval-only use of NC data | Resolved against my round-1 hedge: not defensible | Section G rewritten; EPIC fixtures licensed or deleted |
| COMMERCIAL 2 | DINOv3 terms | Resolved: usable as a fallback with conditions | Section D condition text |
| COMMERCIAL 3 | Roboflow export and data terms | Resolved, with the data-use opt-out condition I had not seen | Section F rewritten; local `rfdetr` is the default |

Disputed: none. One difference of emphasis with COMMERCIAL: it prefers SAM 2 over RepViT-SAM on the event path for provenance reasons; I keep RepViT-SAM until SAM 2's CPU latency is measured (section C), because the event budget is shared and no CPU number exists for either in this review.

### Corrections to my round-1 tags, after checking every licence in F and G against COMMERCIAL's register

- MediaPipe weights: `[B]` → `[V-peer, secondary]`, primary still outstanding.
- Apple Vision vs Apple model terms: `[B]` → `[V-peer: LICENSE_MODELS]`.
- "Evaluation inside product development is commercial use": `[B]` → `[V-peer: CC interpretation; ADT licence]`.
- Roboflow: the ToS data-use clause and the pricing-page download rule were not in my round-1 file; added as `[V-peer]`. My `[V]` changelog line ("Basic and Growth plans") stands but is superseded by the pricing page's current wording.
- Edge Impulse: my `[V]` read of the ToS missed §3.9; verdict changed to rejected for household footage.
- HOT3D sequences: my "sequences only" evaluation cell changed to No, per COMMERCIAL's ShareAlike reasoning (marked `[B]` by COMMERCIAL; accepted because nothing needs them).
- EgoObjects: "Unknown" → "assume research-only".
- Tesseract: tessdata licence added `[V-peer]`.
- No licence in my F or G differs from COMMERCIAL's register on the facts; HOI4D and Landing AI are in mine and not in COMMERCIAL's, both flagged as secondary or unopened.

### Other reactions

1. ARCH 7(b): agreed that the capture rate is not lowered; the two additions in the positions section make the controller robust to a slow Worker rather than lowering anything.
2. ARCH 7(d)(iii), the query-time homography budget inside 2 s: fine on a still camera; the degrade-to-no-refusal rule above covers the wheelchair case.
3. MEMORY reactions 6 and 7: adopted as written.
4. COMMERCIAL reactions 2 (SA-1B provenance): recorded in section C; the provenance note travels with the proposer in the register.
5. COMMERCIAL reactions 6: agreed that the only non-Apache term in perception is the DINOv3 fallback; the speech-side NC items (openWakeWord models, Piper's Blizzard voices, espeak-ng GPL-3) are MEMORY's section and are not touched here.
6. COMMERCIAL §4.4 on hand geometry: section A's recommendations do not require storing any hand template; the wearer hand-size scalar is computed from `worldLandmarks` at localization time and stored as a number.

## Exchanges

- Round 1: `ListAgents` listed only this process's own subagent; questions were queued to `main` for relay; no peer message arrived.
- Round 2: the coordinator reported all three finals; I read `final/ARCH.md` (round-2 revision), `final/MEMORY.md` and `final/COMMERCIAL.md` in full. Their answers to PERCEPTION are reconciled above; no direct peer message was exchanged.
