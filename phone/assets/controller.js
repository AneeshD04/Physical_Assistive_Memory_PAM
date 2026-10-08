// Port of perception/episode_controller.py. Pure JSON state; no model or browser I/O.
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
// Deliberately disabled seam. A future cleared adapter must supply actual measured
// busy/motion values and landmarks, plus rights/version/calibration review. A flag
// alone cannot enable automatic capture in this first checkpoint.
export function createAutomaticAdapter() {
  return { enabled: false, reason: 'Cleared hand-model weights and device validation are unavailable.', analyze: null };
}
