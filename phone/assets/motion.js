// Port of perception/motion.py (CP2). Pure functions over plain pixel buffers; no
// DOM, no model, no I/O. Runs unchanged in Node, in the page and in a Worker.
//
// Arithmetic, normative for both languages (the Python file is the reference):
// 1. boxBlur3: for every pixel, the integer sum of its 3x3 neighbourhood with the
//    border re-using the nearest in-image pixel (edge replication; a 1x1 frame blurs
//    to itself), floor divided by 9. Output 0..255. No floating point.
// 2. motionEnergy: S = sum over pixels of |blur(next) - blur(prev)| (exact integer),
//    D = width * height * 255. scaled = floor((2*S*1e6 + D) / (2*D)) in integer
//    arithmetic (BigInt, so ties round half up identically to Python's //), then
//    energy = scaled / 1000000 as one float64 division. moving = energy >= MOTION_ON
//    on the rounded value. Never Math.round(x * 1e6) / 1e6 or toFixed.
// 3. motionStep: explicit hysteresis. Not moving -> moving at energy >= MOTION_ON;
//    moving -> not moving at energy < MOTION_OFF; otherwise unchanged.
//
// MOTION_ON and MOTION_OFF are INITIAL VALUES pending rig measurement (P-105).
// Mirrored in perception/motion.py; the tester's golden arrays pin the arithmetic.
export const MOTION_ON = 0.035;
export const MOTION_OFF = 0.015;
// Same bounds as the packet's Dimensions, so a frame that fits a packet fits here.
export const MAX_SIDE = 1920;
export const MAX_AREA = 2073600;

function dimension(value, name) {
  if (!Number.isInteger(value) || value < 1 || value > MAX_SIDE) throw new Error(`Invalid frame ${name}`);
  return value;
}

function flatten(rows, width, height, name) {
  if (rows.length !== height) throw new Error(`${name} frame shape does not match width and height`);
  const pixels = new Array(width * height);
  for (let y = 0; y < height; y++) {
    const row = rows[y];
    if (!(Array.isArray(row) || ArrayBuffer.isView(row)) || row.length !== width) throw new Error(`${name} frame shape does not match width and height`);
    for (let x = 0; x < width; x++) pixels[y * width + x] = row[x];
  }
  return pixels;
}

// Coerce a flat Uint8Array / Uint8ClampedArray / ArrayBuffer / array (or an array of
// rows) into a Uint8Array of exactly width*height pixels, each an integer 0..255.
function frame(value, width, height, name) {
  let pixels;
  if (value instanceof Uint8Array || value instanceof Uint8ClampedArray) pixels = value;
  else if (value instanceof ArrayBuffer) pixels = new Uint8Array(value);
  else if (Array.isArray(value) && value.length && (Array.isArray(value[0]) || ArrayBuffer.isView(value[0]))) pixels = flatten(value, width, height, name);
  else if (Array.isArray(value) || ArrayBuffer.isView(value)) pixels = value;
  else throw new Error(`Unsupported ${name} frame type`);
  if (pixels.length !== width * height) throw new Error(`${name} frame length does not match width and height`);
  if (pixels instanceof Uint8Array) return pixels;
  const out = new Uint8Array(pixels.length);
  for (let i = 0; i < pixels.length; i++) {
    const pixel = pixels[i];
    if (typeof pixel !== 'number' || !Number.isInteger(pixel) || pixel < 0 || pixel > 255) throw new Error(`${name} frame pixels must be integers 0..255`);
    out[i] = pixel;
  }
  return out;
}

export function boxBlur3(gray, width, height) {
  width = dimension(width, 'width'); height = dimension(height, 'height');
  if (width * height > MAX_AREA) throw new Error('Frame area too large');
  const pixels = frame(gray, width, height, 'blur');
  const out = new Uint8Array(width * height);
  for (let y = 0; y < height; y++) {
    const above = (y > 0 ? y - 1 : 0) * width, row = y * width, below = (y < height - 1 ? y + 1 : height - 1) * width;
    for (let x = 0; x < width; x++) {
      const left = x > 0 ? x - 1 : 0, right = x < width - 1 ? x + 1 : width - 1;
      const sum = pixels[above + left] + pixels[above + x] + pixels[above + right]
        + pixels[row + left] + pixels[row + x] + pixels[row + right]
        + pixels[below + left] + pixels[below + x] + pixels[below + right];
      out[row + x] = Math.floor(sum / 9);
    }
  }
  return out;
}

export function motionEnergy(prev, next, width, height) {
  width = dimension(width, 'width'); height = dimension(height, 'height');
  if (width * height > MAX_AREA) throw new Error('Frame area too large');
  const before = boxBlur3(frame(prev, width, height, 'prev'), width, height);
  const after = boxBlur3(frame(next, width, height, 'next'), width, height);
  let total = 0;
  for (let i = 0; i < before.length; i++) total += Math.abs(after[i] - before[i]);
  const denominator = BigInt(width * height * 255);
  const scaled = (2n * BigInt(total) * 1000000n + denominator) / (2n * denominator);
  const energy = Number(scaled) / 1000000;
  return { energy, moving: energy >= MOTION_ON };
}

export function motionStep(state, energy) {
  let moving;
  if (state === null || state === undefined) moving = false;
  else if (state !== null && typeof state === 'object' && !Array.isArray(state) && typeof state.moving === 'boolean') moving = state.moving;
  else throw new Error('Invalid motion state');
  if (typeof energy !== 'number' || !Number.isFinite(energy)) throw new Error('Invalid motion energy');
  if (moving) moving = !(energy < MOTION_OFF);
  else moving = energy >= MOTION_ON;
  return [{ moving }, moving];
}
