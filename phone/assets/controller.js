// Port of perception/episode_controller.py. Pure JSON state; no model or browser I/O.
import { motionEnergy as defaultMotionEnergy, motionStep as defaultMotionStep } from './motion.js';
import { handBusy as defaultHandBusy } from './hand-busy.js';
export const BUSY_MIN_MS = 200;
export const REST_MIN_MS = 600;
export const MAX_EPISODE_MS = 10000;
export function initialState() {
  return { phase: 'idle', last_ms: null, busy_since: null, rest_since: null, burst_taken: false };
}
export const initial_state = initialState;
export function step(previous, sample) {
  const state = { ...(previous ?? initialState()) };
  const t = sample.t_ms;
  if (!Number.isSafeInteger(t) || t < 0) throw new Error('Invalid controller time');
  if (state.last_ms !== null && t <= state.last_ms) throw new Error('Controller time must increase');
  const busy = sample.busy ?? null, motion = sample.motion ?? null;
  if ([busy, motion].some(value => value !== null && typeof value !== 'boolean')) throw new Error('Invalid controller measurement');
  const valid = sample.frame_valid === undefined ? false : sample.frame_valid;
  const gap = sample.gap === undefined ? false : sample.gap;
  if (typeof valid !== 'boolean' || typeof gap !== 'boolean') throw new Error('Invalid controller flags');
  state.last_ms = t;
  if (gap) return [{ ...initialState(), last_ms: t }, ['gap', ...(state.phase !== 'idle' ? ['abort'] : [])]];
  const actions = [];
  if (state.phase === 'idle') {
    if (busy === true) {
      Object.assign(state, { phase: 'busy', busy_since: t, rest_since: null, burst_taken: false });
      actions.push('start', 'select_pre_contact');
      if (valid) actions.push('select_hand_busy');
    }
  } else if (t - state.busy_since >= MAX_EPISODE_MS) {
    return [{ ...initialState(), last_ms: t }, ['gap', 'abort']];
  }
  if (state.phase !== 'idle') {
    if (busy === true) {
      Object.assign(state, { phase: 'busy', rest_since: null });
      if (motion === true && valid && !state.burst_taken) { actions.push('select_carry'); state.burst_taken = true; }
    } else if (busy === false && motion === false && valid && t - state.busy_since >= BUSY_MIN_MS) {
      if (state.rest_since === null) { Object.assign(state, { phase: 'settling', rest_since: t }); actions.push('select_release'); }
      else if (t - state.rest_since >= REST_MIN_MS) return [{ ...initialState(), last_ms: t }, [...actions, 'select_rest', 'finish']];
    } else Object.assign(state, { phase: 'busy', rest_since: null });
  }
  return [state, actions];
}
// Run step() over a whole trace from the initial state. Returns one record per
// sample, in order: {t_ms, actions: [...], phase: <phase after the step>}. The
// machine above is unchanged; this is only the entry point the tester diffs against
// perception/episode_controller.py replay(). An invalid sample throws the same Error
// step() throws, at the sample that is invalid; nothing is swallowed.
export function replay(samples) {
  if (!Array.isArray(samples)) throw new Error('Controller trace must be a list of samples');
  let state = null;
  const log = [];
  for (const sample of samples) {
    if (sample === null || typeof sample !== 'object' || Array.isArray(sample)) throw new Error('Invalid controller sample');
    const [next, actions] = step(state, sample);
    state = next;
    log.push({ t_ms: sample.t_ms, actions: [...actions], phase: state.phase });
  }
  return log;
}

// Automatic adapter (CP2). The measured inputs the controller needs come from two
// places: motion from the frame-difference energy of consecutive analysis-resolution
// grayscale frames (motion.js), and busy from the hand-busy heuristic (hand-busy.js)
// over landmark samples produced by the hand worker (hand-worker.js). The worker is
// the only part that touches a model, and it loads it only from this origin.
//
// Protocol with the worker (main -> worker, worker -> main):
//   {type:'init', base:'/assets/models/'}  ->  {type:'ready', version, delegate, runtime}
//                                          |   {type:'unavailable', reason}
//   {type:'frame', t_ms, bitmap} (bitmap transferred)
//                                          ->  {type:'hands', t_ms, hands:[...], infer_ms}
//                                          |   {type:'unavailable', reason} (once; later frames ignored)
//
// The adapter object is returned synchronously and mutates in place:
//   {enabled:false, reason, analyze:null}                 until the worker is ready
//   {enabled:true, reason:null, version, analyze(...)}     when ready
//   {enabled:false, reason, analyze:null}                 after an unavailable report
// analyze(t_ms, analysisGray, bitmap) -> Promise<{busy, motion, frame_valid, hands, basis, energy, infer_ms}>
//   analysisGray: {data: Uint8Array, width, height} at the packet's analysis resolution
//   bitmap: an ImageBitmap for the worker (transferred and closed there; closed here
//           when it cannot be posted). frame_valid is true only when this frame's
//           landmark result arrived within ANALYSIS_TIMEOUT_MS; otherwise busy is the
//           latest value (possibly null) and hands is null. motion is null until two
//           consecutive analysis frames exist. A missing measurement is null, never a guess.
export const ANALYSIS_TIMEOUT_MS = 250;
export const NO_WORKER_REASON = 'Cleared hand-model weights and device validation are unavailable.';
const safeReason = value => typeof value === 'string' && value.trim() ? value.trim().slice(0, 240) : 'The hand model is unavailable.';
// Deliberately disabled seam. A future cleared adapter must supply actual measured
// busy/motion values and landmarks, plus rights/version/calibration review. A flag
// alone cannot enable automatic capture in this first checkpoint.
//
// CP2: with a worker, the seam becomes the real adapter described above. Without one
// (no worker supplied, e.g. the browser cannot create workers) it stays disabled.
export function createAutomaticAdapter({ worker = null, motion = null, hands = null, base = '/assets/models/', timeoutMs = ANALYSIS_TIMEOUT_MS, changed = () => {} } = {}) {
  const adapter = { enabled: false, reason: NO_WORKER_REASON, version: null, delegate: null, state: 'unavailable', analyze: null, reset() {}, close() {} };
  if (!worker || typeof worker.postMessage !== 'function' || typeof worker.addEventListener !== 'function') return adapter;
  const energyOf = motion?.motionEnergy ?? defaultMotionEnergy, stepMotion = motion?.motionStep ?? defaultMotionStep;
  const busyOf = hands?.handBusy ?? hands ?? defaultHandBusy;
  let motionState = null, previousGray = null, inFlight = 0, postedAt = 0, closed = false;
  const HUNG_MS = Math.max(2000, timeoutMs * 8);
  const clock = () => (globalThis.performance?.now ? performance.now() : Date.now());
  let latest = { busy: null, basis: 'no landmark result yet', t_ms: null };
  const waiters = new Map();
  adapter.state = 'starting'; adapter.reason = 'Checking for hand model assets on this server.';
  function notify() { try { changed(adapter); } catch { /* a listener failure must not break analysis */ } }
  function settle(t_ms, result) {
    const waiter = waiters.get(t_ms);
    if (!waiter) return false;
    waiters.delete(t_ms); clearTimeout(waiter.timer); waiter.resolve(result); return true;
  }
  function unavailable(reason) {
    if (adapter.state === 'unavailable') return;
    adapter.state = 'unavailable'; adapter.enabled = false; adapter.reason = safeReason(reason); adapter.analyze = null;
    for (const t_ms of [...waiters.keys()]) settle(t_ms, null);
    inFlight = 0;
    notify();
  }
  function onMessage(event) {
    const message = event?.data;
    if (!message || typeof message !== 'object' || typeof message.type !== 'string') return;
    if (message.type === 'ready') {
      if (adapter.state !== 'starting') return;
      adapter.state = 'ready'; adapter.enabled = true; adapter.reason = null; adapter.analyze = analyze;
      adapter.version = typeof message.version === 'string' && message.version ? message.version.slice(0, 80) : 'unknown version';
      adapter.delegate = typeof message.delegate === 'string' ? message.delegate.slice(0, 20) : null;
      notify();
    } else if (message.type === 'unavailable') {
      unavailable(message.reason);
    } else if (message.type === 'hands') {
      if (inFlight > 0) inFlight--;
      const t_ms = message.t_ms;
      let verdict = null, sample = null;
      try {
        if (!Array.isArray(message.hands)) throw new Error('Invalid landmark sample');
        verdict = busyOf(message.hands); sample = message.hands;
      } catch { verdict = null; }
      if (verdict) latest = { busy: verdict.busy, basis: verdict.basis, t_ms };
      settle(t_ms, verdict ? { hands: sample, busy: verdict.busy, basis: verdict.basis, present: verdict.present, infer_ms: Number.isFinite(message.infer_ms) ? message.infer_ms : null } : null);
    }
  }
  function onError() { unavailable('The hand analysis worker failed in this browser.'); }
  worker.addEventListener('message', onMessage);
  worker.addEventListener('error', onError);
  try { worker.postMessage({ type: 'init', base }); } catch { unavailable('The hand analysis worker could not be started.'); }
  function closeBitmap(bitmap) { try { bitmap?.close?.(); } catch { /* already closed */ } }
  async function analyze(t_ms, analysisGray, bitmap) {
    let motionFlag = null, energy = null;
    const gray = analysisGray && analysisGray.data instanceof Uint8Array ? analysisGray : null;
    if (gray && previousGray && previousGray.width === gray.width && previousGray.height === gray.height && previousGray.data.length === gray.data.length) {
      try {
        energy = energyOf(previousGray.data, gray.data, gray.width, gray.height).energy;
        [motionState, motionFlag] = stepMotion(motionState, energy);
      } catch { motionFlag = null; energy = null; }
    }
    if (gray) previousGray = gray;
    let result = null;
    // One frame in flight at a time bounds the worker's backlog; a worker that has
    // not replied for HUNG_MS is reported unavailable rather than silently
    // invalidating every frame from then on.
    if (adapter.enabled && inFlight >= 1 && clock() - postedAt > HUNG_MS) unavailable('The hand model stopped responding in this browser; automatic capture stopped.');
    if (adapter.enabled && bitmap && inFlight < 1 && Number.isSafeInteger(t_ms) && !waiters.has(t_ms)) {
      result = await new Promise(resolve => {
        const timer = setTimeout(() => settle(t_ms, null), timeoutMs);
        waiters.set(t_ms, { resolve, timer });
        try { inFlight++; postedAt = clock(); worker.postMessage({ type: 'frame', t_ms, bitmap }, [bitmap]); }
        catch { inFlight--; closeBitmap(bitmap); settle(t_ms, null); }
      });
    } else closeBitmap(bitmap);
    if (result) return { busy: result.busy, motion: motionFlag, frame_valid: true, hands: result.hands, basis: result.basis, present: result.present, energy, infer_ms: result.infer_ms };
    return { busy: latest.busy, motion: motionFlag, frame_valid: false, hands: null, basis: `${latest.basis}; no landmark result for this frame within ${timeoutMs} ms`, present: null, energy, infer_ms: null };
  }
  adapter.reset = () => { motionState = null; previousGray = null; latest = { busy: null, basis: 'no landmark result yet', t_ms: null }; };
  adapter.close = () => {
    if (closed) return; closed = true;
    worker.removeEventListener('message', onMessage); worker.removeEventListener('error', onError);
    for (const t_ms of [...waiters.keys()]) settle(t_ms, null);
    adapter.state = 'unavailable'; adapter.enabled = false; adapter.analyze = null; adapter.reason = 'Hand analysis was closed.';
    try { worker.terminate?.(); } catch { /* already gone */ }
  };
  return adapter;
}
