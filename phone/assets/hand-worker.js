// Hand landmarker worker (CP2). Classic (non-module) worker on purpose: the MediaPipe
// Tasks Vision runtime loads its WASM glue with importScripts(), which module workers
// forbid; the ESM bundle itself is loaded with a dynamic import() from here.
//
// Every byte this worker loads comes from THIS origin under the model base path the
// page sends (normally /assets/models/): the manifest, the vision bundle, the WASM
// loader and binary, and the hand_landmarker .task file. No CDN URL exists in this
// file or anywhere in the page; if an asset is not provisioned, the worker says so
// and stays idle. A missing model is a visible "unavailable" capability, never a
// simulated result.
//
// Protocol (see controller.js createAutomaticAdapter):
//   main -> {type:'init', base:'/assets/models/'}
//   worker -> {type:'ready', version, delegate:'GPU'|'CPU', runtime}
//          |  {type:'unavailable', reason}        (reason is a fixed, safe sentence)
//   main -> {type:'frame', t_ms, bitmap}          (ImageBitmap, transferred)
//   worker -> {type:'hands', t_ms, hands:[{landmarks:[{x,y,z} x 21], world_landmarks:[...]|null,
//                                           hand_bbox:[x1,y1,x2,y2], handedness:'left'|'right'|'unknown'}], infer_ms}
//          |  {type:'unavailable', reason}        (once; every later frame is closed and ignored)
//
// Manifest (MANIFEST.json under the base path, written by scripts/fetch_models.py).
// The CANONICAL shape, the only one the server emits, is {"assets": [...]}: a list of
// entries each with a file name (name|file|filename|path) and version, sha256,
// licence, url, fetched_at. The parser below also tolerates "files"/"models"/
// "entries" lists and objects keyed by file name purely as a defensive reading of
// hand-written manifests; nothing depends on those. The files looked up by name are:
//   hand_landmarker.task          (any *.task whose name contains "hand_landmarker")
//   vision_bundle.mjs             (or vision_bundle.js / vision_bundle.cjs, loaded via importScripts)
//   vision_wasm_internal.js       (WASM loader)   + vision_wasm_internal.wasm
//   vision_wasm_nosimd_internal.js + .wasm        (optional; used only when the browser lacks WASM SIMD)
'use strict';

const REASON_NO_MODEL = 'Hand model assets are not provisioned on this server.';
const REASON_NO_RUNTIME = 'Hand model runtime files are not provisioned on this server.';
const REASON_NO_SIMD = 'This browser lacks WebAssembly SIMD and no fallback runtime is provisioned.';
const REASON_MANIFEST = 'The hand model manifest on this server is unreadable.';
const REASON_BASE = 'The hand model location is not a same-origin path.';
const REASON_LOAD = 'The hand model could not be loaded in this browser.';
const REASON_RUN = 'The hand model failed during analysis; automatic capture stopped.';
const REASON_WORKER = 'This browser cannot run the hand analysis worker.';
// A relative path of safe segments (so a nested "wasm/" layout works too); no
// leading slash, no "..", no backslashes, no query or fragment.
const FILE_PATH = /^(?:[A-Za-z0-9][A-Za-z0-9._-]{0,63}\/){0,4}[A-Za-z0-9][A-Za-z0-9._-]{0,119}$/;
const LANDMARK_COUNT = 21, MAX_HANDS = 2;

let state = 'idle';          // idle | loading | ready | unavailable
let landmarker = null;
let lastTimestamp = -1;

function post(message) { self.postMessage(message); }
function closeBitmap(bitmap) { try { bitmap?.close?.(); } catch { /* already closed */ } }
function unavailable(reason, error) {
  if (state === 'unavailable') return;
  state = 'unavailable';
  if (error !== undefined) { try { console.warn('hand-worker unavailable:', reason, error); } catch { /* no console */ } }
  try { landmarker?.close?.(); } catch { /* ignore */ }
  landmarker = null;
  post({ type: 'unavailable', reason });
}

// --- manifest -------------------------------------------------------------------
function sameOriginURL(base, name) {
  const url = new URL(base + name, self.location.href);
  if (url.origin !== self.location.origin || url.username || url.password) throw new Error('cross-origin');
  return url.href;
}
function manifestEntries(manifest) {
  const entries = [];
  const add = (name, value) => {
    const entry = value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    const file = [name, entry.name, entry.file, entry.filename, entry.path].find(candidate => typeof candidate === 'string' && candidate);
    if (!file || !FILE_PATH.test(file) || file.split('/').includes('..')) return;
    // name: the bare file name the lookups below match; path: what is requested.
    entries.push({ ...entry, name: file.slice(file.lastIndexOf('/') + 1), path: file });
  };
  if (!manifest || typeof manifest !== 'object') return entries;
  if (Array.isArray(manifest)) { manifest.forEach(entry => add(null, entry)); return entries; }
  // Canonical: manifest.assets is the list (scripts/fetch_models.py); the rest is tolerance.
  const listed = ['assets', 'files', 'models', 'entries'].map(key => manifest[key]).find(value => value && typeof value === 'object');
  if (Array.isArray(listed)) listed.forEach(entry => add(null, entry));
  else if (listed) Object.entries(listed).forEach(([name, entry]) => add(name, entry));
  else Object.entries(manifest).forEach(([name, entry]) => { if (entry && typeof entry === 'object' && !Array.isArray(entry)) add(name, entry); });
  return entries;
}
function findEntry(entries, test) { return entries.find(entry => test(entry.name)) || null; }
function versionOf(entry) {
  const version = entry && [entry.version, entry.tag, entry.release].find(value => typeof value === 'string' && value.trim());
  return version ? version.trim().slice(0, 80) : 'unknown version';
}

// WebAssembly SIMD feature test (a minimal module using v128 ops); MediaPipe ships a
// nosimd runtime for browsers that lack it.
function supportsSIMD() {
  try {
    return WebAssembly.validate(new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0, 1, 5, 1, 96, 0, 1, 123, 3, 2, 1, 0, 10, 10, 1, 8, 0, 65, 0, 253, 15, 253, 98, 11]));
  } catch { return false; }
}

async function loadBundle(url) {
  if (url.endsWith('.mjs')) return import(url);
  // A CommonJS/UMD build: give it module/exports globals and read them back.
  const previous = { module: self.module, exports: self.exports };
  self.module = { exports: {} }; self.exports = self.module.exports;
  try { importScripts(url); return self.module.exports; }
  finally { self.module = previous.module; self.exports = previous.exports; }
}

async function init(base) {
  if (state !== 'idle') return;
  state = 'loading';
  if (typeof base !== 'string' || !base.startsWith('/') || base.startsWith('//') || base.includes('..') || !base.endsWith('/')) { unavailable(REASON_BASE); return; }
  let entries;
  try {
    const response = await fetch(sameOriginURL(base, 'MANIFEST.json'), { credentials: 'same-origin', cache: 'no-store', redirect: 'error' });
    if (response.status === 404) { unavailable(REASON_NO_MODEL); return; }
    if (!response.ok) { unavailable(REASON_MANIFEST); return; }
    entries = manifestEntries(await response.json());
  } catch (error) { unavailable(REASON_MANIFEST, error); return; }
  const model = findEntry(entries, name => name.endsWith('.task') && name.includes('hand_landmarker'));
  if (!model) { unavailable(REASON_NO_MODEL); return; }
  const bundle = ['vision_bundle.mjs', 'vision_bundle.js', 'vision_bundle.cjs'].map(name => findEntry(entries, candidate => candidate === name)).find(Boolean);
  const simd = supportsSIMD();
  let loader = findEntry(entries, name => name === 'vision_wasm_internal.js'), binary = findEntry(entries, name => name === 'vision_wasm_internal.wasm');
  if (!simd) {
    loader = findEntry(entries, name => name === 'vision_wasm_nosimd_internal.js'); binary = findEntry(entries, name => name === 'vision_wasm_nosimd_internal.wasm');
    if (!loader || !binary) { unavailable(bundle ? REASON_NO_SIMD : REASON_NO_RUNTIME); return; }
  }
  if (!bundle || !loader || !binary) { unavailable(REASON_NO_RUNTIME); return; }
  let urls;
  try {
    urls = { bundle: sameOriginURL(base, bundle.path), loader: sameOriginURL(base, loader.path), binary: sameOriginURL(base, binary.path), model: sameOriginURL(base, model.path) };
  } catch { unavailable(REASON_BASE); return; }
  let HandLandmarker;
  try {
    const runtime = await loadBundle(urls.bundle);
    HandLandmarker = runtime?.HandLandmarker || runtime?.default?.HandLandmarker;
    if (typeof HandLandmarker?.createFromOptions !== 'function') throw new Error('bundle exports no HandLandmarker');
  } catch (error) { unavailable(REASON_LOAD, error); return; }
  const fileset = { wasmLoaderPath: urls.loader, wasmBinaryPath: urls.binary };
  const options = delegate => ({
    baseOptions: { modelAssetPath: urls.model, delegate },
    runningMode: 'VIDEO', numHands: MAX_HANDS,
    minHandDetectionConfidence: 0.5, minHandPresenceConfidence: 0.5, minTrackingConfidence: 0.5,
  });
  let delegate = null;
  const attempts = typeof OffscreenCanvas === 'function' ? ['GPU', 'CPU'] : ['CPU'];
  let lastError = null;
  for (const candidate of attempts) {
    try {
      const extra = candidate === 'GPU' ? { canvas: new OffscreenCanvas(1, 1) } : {};
      landmarker = await HandLandmarker.createFromOptions(fileset, { ...options(candidate), ...extra });
      delegate = candidate; break;
    } catch (error) { lastError = error; landmarker = null; }
  }
  if (!landmarker) { unavailable(REASON_LOAD, lastError); return; }
  if (state !== 'loading') { try { landmarker.close(); } catch { /* ignore */ } landmarker = null; return; }
  state = 'ready';
  post({ type: 'ready', version: versionOf(model), delegate, runtime: versionOf(bundle) });
}

// --- frames ---------------------------------------------------------------------
const round6 = value => Math.round(value * 1e6) / 1e6;
const clamp01 = value => (value < 0 ? 0 : value > 1 ? 1 : value);
function finitePoint(point) {
  return point && Number.isFinite(point.x) && Number.isFinite(point.y) && Number.isFinite(point.z);
}
function convertHand(result, index) {
  const image = result.landmarks?.[index];
  if (!Array.isArray(image) || image.length !== LANDMARK_COUNT || !image.every(finitePoint)) return null;
  const landmarks = image.map(point => ({ x: clamp01(round6(point.x)), y: clamp01(round6(point.y)), z: round6(point.z) }));
  let x1 = 1, y1 = 1, x2 = 0, y2 = 0;
  for (const point of landmarks) { x1 = Math.min(x1, point.x); y1 = Math.min(y1, point.y); x2 = Math.max(x2, point.x); y2 = Math.max(y2, point.y); }
  // A box must have positive width and height (packet contract); a hand whose
  // landmarks are collinear gets the smallest box that still encloses them.
  if (!(x2 > x1)) { if (x2 < 1) x2 = round6(Math.min(1, x1 + 1e-6)); else x1 = round6(x2 - 1e-6); }
  if (!(y2 > y1)) { if (y2 < 1) y2 = round6(Math.min(1, y1 + 1e-6)); else y1 = round6(y2 - 1e-6); }
  if (!(0 <= x1 && x1 < x2 && x2 <= 1 && 0 <= y1 && y1 < y2 && y2 <= 1)) return null;
  const world = result.worldLandmarks?.[index];
  const world_landmarks = Array.isArray(world) && world.length === LANDMARK_COUNT && world.every(finitePoint)
    ? world.map(point => ({ x: round6(point.x), y: round6(point.y), z: round6(point.z) })) : null;
  const categories = (result.handedness ?? result.handednesses)?.[index];
  const label = Array.isArray(categories) && categories[0] && typeof categories[0].categoryName === 'string' ? categories[0].categoryName.toLowerCase() : '';
  const handedness = label === 'left' || label === 'right' ? label : 'unknown';
  return { landmarks, world_landmarks, hand_bbox: [x1, y1, x2, y2], handedness };
}
function frame(message) {
  const bitmap = message.bitmap;
  if (state !== 'ready' || !landmarker) { closeBitmap(bitmap); return; }
  const t_ms = message.t_ms;
  if (!bitmap || !Number.isSafeInteger(t_ms) || t_ms < 0) { closeBitmap(bitmap); return; }
  try {
    // The VIDEO running mode needs strictly increasing timestamps; a repeated or
    // earlier monotonic time is nudged for the model but echoed back unchanged.
    const timestamp = t_ms > lastTimestamp ? t_ms : lastTimestamp + 1;
    lastTimestamp = timestamp;
    const started = performance.now();
    const result = landmarker.detectForVideo(bitmap, timestamp);
    const infer_ms = Math.round((performance.now() - started) * 10) / 10;
    const hands = [];
    const count = Array.isArray(result?.landmarks) ? Math.min(result.landmarks.length, MAX_HANDS) : 0;
    for (let index = 0; index < count; index++) { const hand = convertHand(result, index); if (hand) hands.push(hand); }
    post({ type: 'hands', t_ms, hands, infer_ms });
  } catch (error) {
    unavailable(REASON_RUN, error);
  } finally { closeBitmap(bitmap); }
}

self.addEventListener('message', event => {
  const message = event.data;
  if (!message || typeof message !== 'object' || typeof message.type !== 'string') return;
  if (message.type === 'init') { void init(message.base); return; }
  if (message.type === 'frame') { frame(message); return; }
});
self.addEventListener('error', () => unavailable(REASON_WORKER));
