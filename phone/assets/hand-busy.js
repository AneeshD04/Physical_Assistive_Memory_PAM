// Port of perception/hand_busy.py (CP2). Pure heuristic over packet landmark samples;
// no model, no DOM. "busy" means "the hand looks like it is doing something", not
// contact and not ownership; the basis string says which rule fired.
//
// Input is the packet format: each hand is {landmarks: [{x, y, z} x 21],
// world_landmarks: [...] | null, hand_bbox: [x1, y1, x2, y2] normalised 0..1,
// handedness}. MediaPipe's 21-point convention: 0 wrist; 1-4 thumb; 5-8 index;
// 9-12 middle; 13-16 ring; 17-20 little; 5/9/13/17 MCP knuckles; 4/8/12/16/20 tips.
//
// Arithmetic, normative for both languages (image x and y only; z and
// world_landmarks are ignored, so the measure lives in the stretched image space of
// a non-square frame; a known limitation of the heuristic, not a bug):
// 1. The hand considered has the largest bbox area (x2-x1)*(y2-y1); first wins a tie.
// 2. palm_centre = mean of landmarks 0, 5, 9, 13, 17 (summed in that order, / 5).
// 3. reference = Math.sqrt(dx*dx + dy*dy) between landmarks 0 and 9 (sqrt, not
//    hypot, so both languages round identically).
// 4. curl_ratio = (sum over tips 4, 8, 12, 16, 20 of dist(tip, palm_centre) /
//    reference) / 5, accumulated in that order. curled = curl_ratio < CURL_RATIO.
// 5. lower = (y1+y2)/2 > LOWER_FRAME_Y && (x2-x1)*(y2-y1) >= LOWER_FRAME_MIN_AREA.
// 6. busy = curled || lower; basis "curled" | "lower-frame" | "curled+lower-frame" |
//    "open hand". No hand: {present:false, busy:null, basis:"no hand"}. reference
//    below DEGENERATE_REFERENCE: {present:true, busy:null, basis:"degenerate hand"}
//    (a missing measurement never settles the controller).
//
// CURL_RATIO, LOWER_FRAME_Y and LOWER_FRAME_MIN_AREA are INITIAL VALUES from the
// build plan, not measurements; they await the rig experiments (P-101/P-103).
export const CURL_RATIO = 0.55;
export const LOWER_FRAME_Y = 0.40;          // bbox centre y above this is "the lower 60% of the frame"
export const LOWER_FRAME_MIN_AREA = 0.02;   // bbox area as a fraction of the frame
export const DEGENERATE_REFERENCE = 1e-6;

const WRIST = 0, MIDDLE_MCP = 9;
const PALM_INDICES = [0, 5, 9, 13, 17];
const FINGERTIP_INDICES = [4, 8, 12, 16, 20];
export const LANDMARK_COUNT = 21;

const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);

function number(value, what) {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(`Invalid ${what}`);
  return value;
}

function validateHand(hand) {
  if (!isObject(hand)) throw new Error('Invalid hand sample');
  const landmarks = hand.landmarks;
  if (!Array.isArray(landmarks) || landmarks.length !== LANDMARK_COUNT) throw new Error('Hand must carry exactly 21 landmarks');
  const points = [];
  for (const point of landmarks) {
    if (!isObject(point)) throw new Error('Invalid hand landmark');
    const x = number(point.x, 'landmark x'), y = number(point.y, 'landmark y');
    if (Object.prototype.hasOwnProperty.call(point, 'z')) number(point.z, 'landmark z');
    points.push([x, y]);
  }
  const bbox = hand.hand_bbox;
  if (!Array.isArray(bbox) || bbox.length !== 4) throw new Error('Invalid hand box');
  const [x1, y1, x2, y2] = bbox.map(value => number(value, 'hand box'));
  if (!(0 <= x1 && x1 < x2 && x2 <= 1 && 0 <= y1 && y1 < y2 && y2 <= 1)) throw new Error('Invalid hand box');
  return [points, [x1, y1, x2, y2]];
}

function distance(a, b) {
  const dx = a[0] - b[0], dy = a[1] - b[1];
  return Math.sqrt(dx * dx + dy * dy);
}

// The intermediate numbers behind handBusy for one hand, mirroring Python's
// hand_metrics: {reference, palm_centre: [x, y], curl_ratio (null when degenerate),
// bbox_centre_y, bbox_area}.
export function handMetrics(hand) {
  const [points, [x1, y1, x2, y2]] = validateHand(hand);
  // Plain left-to-right accumulation in index order 0, 5, 9, 13, 17, exactly as the
  // Python reference does (it deliberately avoids builtin sum(), which CPython >= 3.12
  // compensates); both languages then agree bit for bit on every interpreter.
  let palmX = 0.0, palmY = 0.0;
  for (const i of PALM_INDICES) { palmX += points[i][0]; palmY += points[i][1]; }
  palmX /= 5; palmY /= 5;
  const reference = distance(points[WRIST], points[MIDDLE_MCP]);
  let curlRatio = null;
  if (reference >= DEGENERATE_REFERENCE) {
    let total = 0.0;
    for (const i of FINGERTIP_INDICES) total += distance(points[i], [palmX, palmY]) / reference;
    curlRatio = total / 5;
  }
  return { reference, palm_centre: [palmX, palmY], curl_ratio: curlRatio, bbox_centre_y: (y1 + y2) / 2, bbox_area: (x2 - x1) * (y2 - y1) };
}

// {present, busy: bool | null, basis} for one landmark sample. Throws on malformed
// input (wrong landmark count, non-finite or non-numeric coordinates, an invalid
// bbox). An empty list is not malformed: it is the honest "no hand" measurement.
export function handBusy(hands) {
  if (!Array.isArray(hands)) throw new Error('Hands must be a list');
  if (!hands.length) return { present: false, busy: null, basis: 'no hand' };
  const validated = hands.map(validateHand);
  let chosen = null, chosenArea = -1.0;
  for (let i = 0; i < hands.length; i++) {
    const [, [x1, y1, x2, y2]] = validated[i];
    const area = (x2 - x1) * (y2 - y1);
    if (area > chosenArea) { chosen = hands[i]; chosenArea = area; }
  }
  const metrics = handMetrics(chosen);
  if (metrics.curl_ratio === null) return { present: true, busy: null, basis: 'degenerate hand' };
  const curled = metrics.curl_ratio < CURL_RATIO;
  const lower = metrics.bbox_centre_y > LOWER_FRAME_Y && metrics.bbox_area >= LOWER_FRAME_MIN_AREA;
  let basis;
  if (curled && lower) basis = 'curled+lower-frame';
  else if (curled) basis = 'curled';
  else if (lower) basis = 'lower-frame';
  else basis = 'open hand';
  return { present: true, busy: curled || lower, basis };
}
