import { uuid } from './memory-queue.js';
import { MAX_EPISODE_MS, createAutomaticAdapter, step } from './controller.js';
import { encodeGrayJPEG } from './grayscale-jpeg.js';
export const RING_MAX = 20, PIN_MAX = 8, BURST_MAX = 10, RING_MS = 2000;
export const BITMAP_BYTE_CAP = 64 * 1024 * 1024;
// Packet contract: at most 128 landmark samples per episode; the worker gets frames
// no wider than this (the model resizes internally; this bounds pixel transfer).
export const LANDMARK_SAMPLES_MAX = 128, HAND_FRAME_MAX = 640;
// The hand worker is created from this same-origin URL (a classic worker). A test
// can substitute a fake by replacing globalThis.Worker before the camera is built.
export const HAND_WORKER_URL = '/assets/hand-worker.js';
export const MANUAL_STATUS = 'Camera on · manual marks only. Nothing is automatically recognized.';
// CP4 idle keyframes: in automatic mode, with the controller idle, motion off and no
// hand present for IDLE_QUIET_MS, one capture-resolution JPEG (quality
// IDLE_JPEG_QUALITY, target <= 64 KiB) is posted to /api/idle at most once per
// IDLE_KEYFRAME_MS. There is no IndexedDB mirror for idle frames: a frame that is
// not posted or not retained is coverage, not evidence, and is only counted.
export const IDLE_KEYFRAME_MS = 30000, IDLE_QUIET_MS = 2000, IDLE_JPEG_QUALITY = 0.5, MAX_IDLE_BYTES = 256 * 1024;
// A valid no-hand measurement must be no older than this for the quiet condition to
// hold (a missing landmark result is never read as "no hand").
export const IDLE_VALID_MAX_AGE_MS = 1000;
// CP5 frame accounting. Every counter site in this file feeds two ledgers: the
// running totals of the current capture session (shown in the Status panel) and the
// current telemetry WINDOW, whose values are the deltas since the previous post. The
// window is posted to /api/telemetry every TELEMETRY_INTERVAL_MS while the camera
// runs and once more at stop; a post resets the window. Counts and bounded timings
// only: no reason text, no image, no landmark ever travels in a telemetry body.
//   frames_captured            a frame was drawn from the video and entered the ring
//   frames_analysed            a captured frame went through motion + hand analysis
//   frames_skipped_busy        the 100 ms tick fired while the previous frame was still
//                              being processed (no frame was captured)
//   frames_dropped_backpressure a captured frame was not analysed because a packet was
//                              being saved or waited unsaved, or was not handed to the
//                              hand worker because it still had a frame in flight
//   landmark_results           the worker answered for the frame within the timeout
//   landmark_timeouts          the frame was handed to the worker and no result came
//   episodes_started           a manual "before" mark or an automatic start
//   episodes_finished          a packet was built (released, or interrupted with a gap)
//   episodes_aborted           an episode ended without a packet (discarded, cancelled,
//                              or the packet could not be encoded)
//   packets_sent / packets_acked / bytes_sent   upload attempts of episode packets, their
//                              durable acknowledgements, and the bytes of every packet or
//                              idle still handed to the local service
//   idle_sent / idle_dropped   idle stills retained by the server / not retained
//   gaps / gap_ms              gap entries recorded, and the part of their duration that
//                              lies inside the window (never more than window_ms)
export const TELEMETRY_INTERVAL_MS = 60000, TELEMETRY_SAMPLE_MAX = 600, MAX_TELEMETRY_BYTES = 64 * 1024, TELEMETRY_WINDOW_MAX_MS = 3600000;
export const COUNTER_KEYS = ['frames_captured', 'frames_analysed', 'frames_skipped_busy', 'frames_dropped_backpressure', 'landmark_results', 'landmark_timeouts',
  'episodes_started', 'episodes_finished', 'episodes_aborted', 'packets_sent', 'packets_acked', 'idle_sent', 'idle_dropped', 'gaps', 'gap_ms', 'bytes_sent'];
export const TIMING_KEYS = ['fps_observed', 'infer_ms_p50', 'infer_ms_p95', 'tick_ms_p95'];
export const SETTING_KEYS = ['width', 'height', 'frame_rate'];
export function emptyCounters() { const counters = {}; for (const key of COUNTER_KEYS) counters[key] = 0; return counters; }
// Nearest-rank percentile of a sample list (0 when there is no sample).
export function percentile(samples, q) {
  if (!Array.isArray(samples) || !samples.length) return 0;
  const sorted = samples.filter(Number.isFinite).sort((a, b) => a - b);
  if (!sorted.length) return 0;
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.ceil(q * sorted.length) - 1))];
}
const tenths = value => Math.round(value * 10) / 10;
const bounded = (value, max) => Number.isFinite(value) ? Math.min(max, Math.max(0, tenths(value))) : 0;
function emptyWindow(start) { return { start_ms: start, counters: emptyCounters(), infer: [], ticks: [], seen: { infer: 0, ticks: 0 } }; }
const now = () => Math.floor(performance.now());
// Default transport for a telemetry window: same-origin POST, never retried. The page
// may supply its own (same result shape) to share its session handling. The final
// window at stop is sent with keepalive so a page being hidden can still deliver it.
async function defaultPostTelemetry(body, { final = false } = {}) {
  const response = await fetch('/api/telemetry', { method: 'POST', credentials: 'same-origin', cache: 'no-store', keepalive: final === true, headers: { 'Content-Type': 'application/json' }, body });
  return { ok: response.ok, status: response.status };
}
function createHandWorker() {
  try { return typeof Worker === 'function' ? new Worker(HAND_WORKER_URL) : null; } catch { return null; }
}
// Default transport for an idle frame: same-origin POST, no retry. The page may
// supply its own (same result shape) to share its session handling.
async function defaultPostIdle(body) {
  const response = await fetch('/api/idle', { method: 'POST', credentials: 'same-origin', cache: 'no-store', headers: { 'Content-Type': 'application/json' }, body });
  let result = null;
  try { result = await response.json(); } catch { result = null; }
  return { ok: response.ok, status: response.status, code: typeof result?.code === 'string' ? result.code : null, retained: result?.retained === true };
}
function idleCounters() { return { sent: 0, dropped: 0, oversize: 0, capped: 0, failed: 0 }; }
// "idle stills: N sent · M dropped" (plus the reasons when any) for the summaries.
export function idleSummary(idle = idleCounters()) {
  const count = key => Number.isSafeInteger(idle?.[key]) ? idle[key] : 0;
  const reasons = [count('oversize') ? `${count('oversize')} over size` : null, count('capped') ? `${count('capped')} not retained by the server` : null, count('failed') ? `${count('failed')} failed` : null].filter(Boolean);
  return `idle stills: ${count('sent')} sent · ${count('dropped')} dropped${reasons.length ? ` (${reasons.join(', ')})` : ''}`;
}
// Class name kept from the first checkpoint: manual marking is unchanged, and the
// automatic path (CP2) is layered on the same ring/pin/burst machinery.
export class ManualCamera {
  constructor({ video, queue, status = () => {}, changed = () => {}, gap = () => {}, worker, createWorker, postIdle, postTelemetry, consentRequired = () => {}, unauthorized = () => {} } = {}) {
    this.video = video; this.queue = queue; this.status = status; this.changed = changed; this.onGap = gap;
    this.postIdle = typeof postIdle === 'function' ? postIdle : defaultPostIdle;
    this.sendTelemetry = typeof postTelemetry === 'function' ? postTelemetry : defaultPostTelemetry;
    this.onConsentRequired = consentRequired; this.onUnauthorized = unauthorized;
    // CP5 frame accounting: totals for the current capture session, the window of
    // deltas since the previous telemetry post, the negotiated capture settings, how
    // many windows reached the server / were refused, and the interruptions this page
    // saw (a stop that was not the user's choice, until the next start).
    this.totals = emptyCounters(); this.window = emptyWindow(null); this.settings = { width: 0, height: 0, frame_rate: 0 };
    this.telemetry = { sent: 0, dropped: 0 }; this.interruptions = []; this.telemetryTimer = null;
    // CP4 idle keyframes: counters shown in the camera summary and the Privacy view;
    // quietSince is the start of the current no-hand/no-motion run (null when not
    // quiet), lastQuietValid the newest valid frame that confirmed it, lastIdleMs the
    // time of the last post (the 30 s spacing holds across toggles and restarts).
    this.idle = idleCounters(); this.quietSince = null; this.lastQuietValid = null; this.lastIdleMs = null; this.idleInFlight = false;
    this.sessionId = uuid(); this.anchor = { mono_ms: now(), wall_ms: Date.now() };
    this.ring = []; this.pins = []; this.burst = []; this.gaps = []; this.episode = null;
    this.stream = null; this.running = false; this.starting = false; this.generation = 0; this.lastTime = null;
    this.canvas = document.createElement('canvas'); this.analysisCanvas = document.createElement('canvas');
    this.handCanvas = document.createElement('canvas');
    // Automatic capture: off by default (a user toggle), usable only when the worker
    // reports a provisioned hand model AND the server's capability allows it.
    this.automatic = false; this.policy = { enabled: true, reason: null };
    this.controller = null; this.samples = []; this.landmarks = []; this.burstStarted = false; this.previousGray = null;
    this.worker = worker ?? (typeof createWorker === 'function' ? createWorker() : createHandWorker());
    this.adapter = createAutomaticAdapter({ worker: this.worker, changed: () => this.adapterChanged() });
    this.unsaved = null; this.saving = false;
  }
  automaticAvailable() { return this.adapter.enabled === true && this.policy.enabled !== false; }
  automaticActive() { return this.running && this.automatic && this.automaticAvailable(); }
  automaticStatus() { return `Camera on · automatic capture (hand model ${this.adapter.version || 'unknown version'})`; }
  adapterState() {
    const available = this.automaticAvailable();
    return { enabled: available, reason: available ? null : (this.policy.enabled === false ? this.policy.reason : this.adapter.reason), version: this.adapter.version, state: this.adapter.state };
  }
  update() {
    this.changed({ running: this.running, starting: this.starting, episode: !!this.episode, saving: this.saving, unsaved: !!this.unsaved,
      automatic: this.automatic, automaticActive: this.automaticActive(), automaticEpisode: !!this.episode?.automatic, adapter: this.adapterState(), idle: { ...this.idle },
      totals: { ...this.totals }, telemetry: { ...this.telemetry }, settings: { ...this.settings } });
  }
  idleSummary() { return idleSummary(this.idle); }
  // --- CP5 frame accounting ---------------------------------------------------------------
  count(key, n = 1) {
    if (!Object.hasOwn(this.totals, key) || !Number.isSafeInteger(n) || n <= 0) return;
    this.totals[key] += n; this.window.counters[key] += n;
  }
  // Bounded reservoir sample of a window timing ('infer' or 'ticks'), in milliseconds.
  sample(name, value) {
    const list = this.window[name], seen = this.window.seen;
    if (!Array.isArray(list) || !Number.isFinite(value)) return;
    const ms = Math.max(0, value); seen[name]++;
    if (list.length < TELEMETRY_SAMPLE_MAX) list.push(ms);
    else { const index = Math.floor(Math.random() * seen[name]); if (index < TELEMETRY_SAMPLE_MAX) list[index] = ms; }
  }
  // The timing block for a window of `windowMs`: observed capture rate over the part
  // of the window with capture, inference and tick percentiles. These measure this
  // rig's implementation, never recognition.
  timing(windowMs) {
    const { counters, infer, ticks } = this.window;
    const covered = Math.max(0, windowMs - Math.min(windowMs, counters.gap_ms));
    return { fps_observed: bounded(covered > 0 ? counters.frames_captured * 1000 / covered : 0, 240),
      infer_ms_p50: bounded(percentile(infer, .5), 60000), infer_ms_p95: bounded(percentile(infer, .95), 60000), tick_ms_p95: bounded(percentile(ticks, .95), 60000) };
  }
  // The current window as the Status panel shows it (not a post): its timings so far.
  timingNow() { return this.window.start_ms === null ? this.timing(0) : this.timing(Math.max(0, now() - this.window.start_ms)); }
  telemetryBody(t) {
    const windowMs = this.window.start_ms === null ? 0 : Math.round(t - this.window.start_ms);
    if (!(windowMs >= 1) || !this.queue?.deviceId) return null;
    const counters = {};
    for (const key of COUNTER_KEYS) counters[key] = Math.min(Number.MAX_SAFE_INTEGER, Math.max(0, Math.round(this.window.counters[key])));
    counters.gap_ms = Math.min(counters.gap_ms, windowMs);
    return { schema_version: 1, device_id: this.queue.deviceId, session_id: this.sessionId, t_ms: Math.max(0, Math.round(t)), clock_anchor: { ...this.anchor },
      window_ms: windowMs, counters, timing: this.timing(windowMs), settings: { ...this.settings } };
  }
  // Post the current window and start the next one. 2xx counts as sent; a 4xx (the
  // server refused the body) is counted as dropped and never retried; a network
  // failure or a 5xx folds the window's counters into the next window so the
  // coverage it describes is not lost, unless the combined window would exceed the
  // longest one the server accepts. Never blocks capture.
  async postTelemetry(final = false) {
    const t = now();
    const previous = this.window, body = this.telemetryBody(t);
    if (!body) return;
    this.window = emptyWindow(t);
    const encoded = JSON.stringify(body);
    if (new TextEncoder().encode(encoded).byteLength > MAX_TELEMETRY_BYTES) { this.telemetry.dropped++; this.update(); return; }
    let result;
    try { result = await this.sendTelemetry(encoded, { final }); } catch { result = { ok: false, status: 0 }; }
    const status = Number.isSafeInteger(result?.status) ? result.status : 0;
    if (result?.ok) this.telemetry.sent++;
    else if (status >= 400 && status < 500) { this.telemetry.dropped++; if (status === 401) this.onUnauthorized(); }
    else if (now() - previous.start_ms <= TELEMETRY_WINDOW_MAX_MS) this.fold(previous);
    else this.telemetry.dropped++;
    this.update();
  }
  fold(previous) {
    const current = this.window;
    for (const key of COUNTER_KEYS) current.counters[key] += previous.counters[key];
    if (current.start_ms === null || previous.start_ms < current.start_ms) current.start_ms = previous.start_ms;
    for (const name of ['infer', 'ticks']) for (const value of previous[name]) this.sample(name, value);
  }
  // Interruptions this page saw since `sinceWallMs` (default: all): stops that were
  // not the user's choice, each lasting until the next start (or now while still
  // off). {count, ms}; the Status panel turns it into one plain sentence.
  interrupted(sinceWallMs = 0) {
    let count = 0, ms = 0;
    for (const entry of this.interruptions) {
      const to = entry.to_ms ?? Date.now(), from = Math.max(entry.from_ms, sinceWallMs);
      if (to <= from) continue;
      count++; ms += to - from;
    }
    return { count, ms };
  }
  adapterChanged() {
    if (this.running && this.episode?.automatic && !this.automaticAvailable()) this.feedGap(`Hand model became unavailable: ${this.adapter.reason || 'no reason given'}`);
    if (this.running && !this.episode) { this.controller = null; this.status(this.automaticActive() ? this.automaticStatus() : MANUAL_STATUS); }
    this.update();
  }
  // Server-side truth about the capability (GET /api/health capabilities); the page
  // passes it through so the toggle never promises more than the service does.
  setServerPolicy({ enabled, reason } = {}) {
    const policy = { enabled: enabled !== false, reason: typeof reason === 'string' && reason ? reason : 'The server reports automatic hand recognition as unavailable.' };
    if (policy.enabled === this.policy.enabled && policy.reason === this.policy.reason) return;
    this.policy = policy;
    this.adapterChanged();
  }
  setAutomatic(on) {
    const next = !!on;
    if (next === this.automatic) return;
    if (this.running && this.episode?.automatic && !next) this.feedGap('Automatic capture turned off during an episode');
    this.automatic = next; this.controller = null; this.adapter.reset?.(); this.resetQuiet();
    if (this.running && !this.episode) this.status(this.automaticActive() ? this.automaticStatus() : MANUAL_STATUS);
    this.update();
  }
  async start() {
    if (this.running || this.starting || this.saving || this.unsaved) return;
    if (!navigator.mediaDevices?.getUserMedia || !globalThis.createImageBitmap) throw new Error('Camera capture requires a secure, supported browser. No capture has started.');
    if (!this.queue.db) throw new Error('Local retry storage must be available before capture.');
    const usage = await this.queue.report();
    if (usage.count >= 32 || usage.bytes >= 44 * 1024 * 1024) throw new Error('Retry storage is nearly full. Sync saved captures before starting.');
    const generation = ++this.generation; this.starting = true; this.update();
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 10, max: 15 } } });
      if (generation !== this.generation || document.hidden) { stream.getTracks().forEach(track => track.stop()); return; }
      this.stream = stream; this.video.srcObject = stream;
      for (const track of stream.getTracks()) {
        track.addEventListener('ended', () => { if (this.running) void this.stop('Camera track ended'); });
        track.addEventListener('mute', () => { if (this.running) void this.stop('Camera track interrupted'); });
      }
      await this.video.play();
      if (generation !== this.generation) return;
      const width = this.video.videoWidth, height = this.video.videoHeight;
      if (!width || !height) throw new Error('The camera did not provide a valid image.');
      // CP5: a new capture session: its own random id, fresh totals, the first
      // telemetry window starting now (deltas not yet posted carry into it), and the
      // negotiated settings from the track (the camera mode, never an image).
      this.sessionId = uuid(); this.totals = emptyCounters(); this.window.start_ms = now();
      const open = this.interruptions.at(-1); if (open && open.to_ms === null) open.to_ms = Date.now();
      let negotiated = {};
      try { negotiated = stream.getVideoTracks()[0]?.getSettings?.() || {}; } catch { negotiated = {}; }
      const dimension = (value, fallback) => Math.min(8192, Number.isFinite(value) && value > 0 ? Math.round(value) : fallback);
      this.settings = { width: dimension(negotiated.width, width), height: dimension(negotiated.height, height),
        frame_rate: Number.isFinite(negotiated.frameRate) && negotiated.frameRate > 0 ? Math.min(240, tenths(negotiated.frameRate)) : 0 };
      const scale = Math.min(1, 1280 / width, 720 / height);
      this.capture = { width: Math.max(1, Math.floor(width * scale)), height: Math.max(1, Math.floor(height * scale)) };
      const analysisScale = Math.min(1, 320 / this.capture.width, 320 / this.capture.height);
      this.analysis = { width: Math.max(1, Math.floor(this.capture.width * analysisScale)), height: Math.max(1, Math.floor(this.capture.height * analysisScale)) };
      const handScale = Math.min(1, HAND_FRAME_MAX / this.capture.width, HAND_FRAME_MAX / this.capture.height);
      this.hand = { width: Math.max(1, Math.floor(this.capture.width * handScale)), height: Math.max(1, Math.floor(this.capture.height * handScale)) };
      Object.assign(this.canvas, this.capture); Object.assign(this.analysisCanvas, this.analysis); Object.assign(this.handCanvas, this.hand);
      this.context = this.canvas.getContext('2d', { alpha: false });
      this.analysisContext = this.analysisCanvas.getContext('2d', { alpha: false, willReadFrequently: true });
      this.handContext = this.handCanvas.getContext('2d', { alpha: false });
      if (!this.context || !this.analysisContext || !this.handContext) throw new Error('Camera image processing is unavailable.');
      if (this.gapStart !== undefined) { this.recordGap(this.gapStart, now(), 'Capture resumed after a gap'); this.gapStart = undefined; }
      this.running = true; this.lastTime = null; this.controller = null; this.samples = []; this.adapter.reset?.();
      this.status(this.automaticActive() ? this.automaticStatus() : MANUAL_STATUS);
      this.timer = setInterval(() => { void this.tick().catch(() => this.stop('Frame processing failed')); }, 100);
      this.telemetryTimer = setInterval(() => { void this.postTelemetry(false); }, TELEMETRY_INTERVAL_MS);
      await this.tick();
    } catch (error) {
      await this.stop('Camera could not start', { interrupted: false });
      throw new Error(error.name === 'NotAllowedError' ? 'Camera permission was not granted. Capture remains off.' : 'Camera unavailable. Check permission and your secure connection, then try again.');
    } finally { this.starting = false; this.update(); }
  }
  async tick() {
    if (this.framePromise) { if (this.running) this.count('frames_skipped_busy'); return this.framePromise; }
    if (!this.running || this.video.readyState < 2) return;
    const generation = this.generation, t = now();
    if (this.lastTime !== null && t <= this.lastTime) return;
    if (this.lastTime !== null && t - this.lastTime > 1000) { await this.stop('Frame delivery gap'); return; }
    this.framePromise = (async () => {
      this.context.drawImage(this.video, 0, 0, this.capture.width, this.capture.height);
      const bitmap = await createImageBitmap(this.canvas);
      if (!this.running || generation !== this.generation) { bitmap.close(); return; }
      const frame = { frame_id: uuid(), t_ms: t, bitmap };
      this.lastTime = t; this.ring.push(frame); this.trim(t); this.count('frames_captured');
      if (this.episode && !this.episode.automatic) {
        if (t - this.episode.t_start_ms >= MAX_EPISODE_MS) { await this.stop('Manual episode reached the 10 second limit'); return; }
        this.captureBurst(frame);
      } else if (this.automaticActive()) {
        await this.automaticTick(frame, generation);
      }
      this.sample('ticks', now() - t);
    })();
    try { await this.framePromise; } finally { this.framePromise = null; }
  }
  trim(t) {
    const bytesPerFrame = this.capture.width * this.capture.height * 4;
    while (this.ring.length && (this.ring.length > RING_MAX || t - this.ring[0].t_ms > RING_MS || (this.ring.length + this.pins.length) * bytesPerFrame > BITMAP_BYTE_CAP)) this.ring.shift().bitmap.close();
  }
  pin(frame, role) {
    if (!frame || this.pins.length >= PIN_MAX || this.pins.some(pin => pin.frame_id === frame.frame_id)) return false;
    const index = this.ring.indexOf(frame);
    if (index < 0) return false;
    this.ring.splice(index, 1); this.pins.push({ ...frame, role }); return true;
  }
  async before() {
    if (!this.running || this.episode || this.saving || this.unsaved) return;
    await this.tick();
    if (!this.running) return;
    const frame = this.ring.at(-1);
    if (!frame || now() - frame.t_ms > 400) throw new Error('Waiting for a fresh camera frame. Try the mark again.');
    this.pin(frame, 'pre_contact');
    this.episode = { episode_id: uuid(), t_start_ms: frame.t_ms };
    this.burst = []; this.burstStarted = false; this.previousGray = null; this.controller = null; this.adapter.reset?.(); this.resetQuiet();
    this.count('episodes_started');
    this.status('Before-move frame pinned. Move the item, then mark at rest within 10 seconds.'); this.update();
  }
  // Analysis-resolution grayscale of a frame, computed once and kept on the frame
  // (the same plane feeds the burst JPEG and the motion energy).
  grayOf(frame) {
    if (frame.gray) return frame.gray;
    const { width, height } = this.analysis;
    this.analysisContext.drawImage(frame.bitmap, 0, 0, width, height);
    const rgba = this.analysisContext.getImageData(0, 0, width, height).data;
    const gray = new Uint8Array(width * height);
    for (let i = 0; i < gray.length; i++) gray[i] = Math.round(.299 * rgba[i * 4] + .587 * rgba[i * 4 + 1] + .114 * rgba[i * 4 + 2]);
    frame.gray = gray;
    return gray;
  }
  captureBurst(frame) {
    if (this.burst.length >= BURST_MAX || frame.t_ms <= this.episode.t_start_ms) return;
    const { width, height } = this.analysis;
    const gray = this.grayOf(frame); let difference = 0;
    if (this.previousGray) for (let i = 0; i < gray.length; i++) difference += Math.abs(gray[i] - this.previousGray[i]);
    // User-marked busy interval plus measured image motion, not hand recognition.
    // Pin the first valid motion window causally; never a future midpoint.
    const motion = this.previousGray && difference / gray.length > 6;
    this.previousGray = gray;
    if (!this.burstStarted && !motion) return;
    this.burstStarted = true;
    this.burst.push({ frame_id: frame.frame_id, t_ms: frame.t_ms, jpeg_b64: encodeGrayJPEG(gray, width, height), width, height });
  }
  // --- automatic path (CP2): the controller's actions drive the same ring/pin/burst machinery.
  async handBitmap(frame) {
    this.handContext.drawImage(frame.bitmap, 0, 0, this.hand.width, this.hand.height);
    return createImageBitmap(this.handCanvas);
  }
  async automaticTick(frame, generation) {
    const t = frame.t_ms;
    // While a packet is being saved or waits unsaved, no new automatic episode may
    // start; the controller restarts from idle when the gate reopens.
    if (this.saving || this.unsaved) { this.controller = null; this.count('frames_dropped_backpressure'); return; }
    const gray = this.grayOf(frame);
    let bitmap = null;
    try { bitmap = await this.handBitmap(frame); } catch { bitmap = null; }
    const analyze = this.adapter.analyze;
    if (!this.running || generation !== this.generation || !this.automaticActive() || typeof analyze !== 'function') { bitmap?.close(); return; }
    // Counted before the analysis so a window never shows more frames analysed than
    // captured; the landmark result or timeout is counted when it arrives.
    this.count('frames_analysed');
    const analysis = await analyze(t, { data: gray, width: this.analysis.width, height: this.analysis.height }, bitmap);
    if (analysis.frame_valid === true) this.count('landmark_results');
    else if (analysis.posted === true) this.count('landmark_timeouts');
    else if (bitmap) this.count('frames_dropped_backpressure');
    if (Number.isFinite(analysis.infer_ms)) this.sample('infer', analysis.infer_ms);
    if (!this.running || generation !== this.generation || !this.automaticActive()) return;
    if (this.saving || this.unsaved || (this.episode && !this.episode.automatic)) { this.controller = null; return; }
    if (Array.isArray(analysis.hands)) this.rememberSample({ frame_id: frame.frame_id, t_ms: t, hands: analysis.hands });
    this.feed({ t_ms: t, busy: analysis.busy, motion: analysis.motion, frame_valid: analysis.frame_valid }, frame, gray, null);
    if (this.episode?.automatic && this.burstStarted && this.burst.at(-1)?.frame_id !== frame.frame_id) this.pushBurst(frame, gray);
    if (this.running && generation === this.generation) this.idleTick(analysis, frame);
  }
  // --- idle keyframes (CP4) -------------------------------------------------------------
  // Called once per analysed frame, after the controller step. The quiet run starts
  // at the first valid frame with no hand present and motion off; any valid frame
  // with a hand, any frame with motion, an episode or a gap ends it. A frame without
  // a landmark result neither starts nor ends the run (a missing measurement is not
  // evidence either way), but the post needs a valid confirmation within
  // IDLE_VALID_MAX_AGE_MS. Posting is rate-limited to one per IDLE_KEYFRAME_MS.
  idleTick(analysis, frame) {
    const t = frame.t_ms;
    const controllerIdle = !this.episode && (this.controller === null || this.controller.phase === 'idle');
    const noHand = analysis.present === false || (analysis.present == null && Array.isArray(analysis.hands) && analysis.hands.length === 0);
    const measured = analysis.frame_valid === true && typeof analysis.motion === 'boolean' && Number.isFinite(analysis.energy);
    if (!controllerIdle || analysis.motion !== false) { this.quietSince = null; this.lastQuietValid = null; return; }
    if (measured) {
      if (!noHand) { this.quietSince = null; this.lastQuietValid = null; return; }
      if (this.quietSince === null) this.quietSince = t;
      this.lastQuietValid = t;
    }
    if (this.quietSince === null || this.lastQuietValid === null) return;
    if (t - this.quietSince < IDLE_QUIET_MS || t - this.lastQuietValid > IDLE_VALID_MAX_AGE_MS) return;
    if (this.lastIdleMs !== null && t - this.lastIdleMs < IDLE_KEYFRAME_MS) return;
    if (this.idleInFlight || !this.queue?.deviceId) return;
    this.lastIdleMs = t;
    let body;
    try { body = this.idlePacket(frame, analysis.energy); }
    catch { this.idle.failed++; this.idleDropped(); return; }
    const bytes = new TextEncoder().encode(body).byteLength;
    if (bytes > MAX_IDLE_BYTES) { this.idle.oversize++; this.idleDropped(); return; }
    void this.sendIdle(body, bytes);
  }
  idleDropped() { this.idle.dropped++; this.count('idle_dropped'); this.update(); }
  // The frame's bitmap re-drawn on the capture canvas (the same canvas the packet
  // keyframes use) and encoded at IDLE_JPEG_QUALITY; capture-resolution pixels.
  idlePacket(frame, energy) {
    this.context.drawImage(frame.bitmap, 0, 0, this.capture.width, this.capture.height);
    const data = this.canvas.toDataURL('image/jpeg', IDLE_JPEG_QUALITY);
    if (!data.startsWith('data:image/jpeg;base64,')) throw new Error('JPEG encoding failed.');
    const motion = Math.min(1, Math.max(0, Number.isFinite(energy) ? energy : 0));
    return JSON.stringify({ schema_version: 1, device_id: this.queue.deviceId, session_id: this.sessionId, frame_id: frame.frame_id, t_ms: frame.t_ms,
      clock_anchor: this.anchor, capture: { width: this.capture.width, height: this.capture.height }, jpeg_b64: data.slice(data.indexOf(',') + 1), motion_energy: motion });
  }
  async sendIdle(body, bytes = 0) {
    this.idleInFlight = true;
    this.count('bytes_sent', bytes);
    try {
      const result = await this.postIdle(body);
      if (result && result.ok && result.retained) { this.idle.sent++; this.count('idle_sent'); }
      else if (result && result.ok) { this.idle.capped++; this.idle.dropped++; this.count('idle_dropped'); }
      else {
        this.idle.failed++; this.idle.dropped++; this.count('idle_dropped');
        if (result && result.status === 401) this.onUnauthorized();
        else if (result && result.status === 409 && result.code === 'consent_required') this.onConsentRequired();
      }
    } catch { this.idle.failed++; this.idle.dropped++; this.count('idle_dropped'); }
    finally { this.idleInFlight = false; this.update(); }
  }
  resetQuiet() { this.quietSince = null; this.lastQuietValid = null; }
  rememberSample(sample) {
    this.samples.push(sample);
    while (this.samples.length && (this.samples.length > RING_MAX || sample.t_ms - this.samples[0].t_ms > RING_MS)) this.samples.shift();
    if (this.episode?.automatic && this.landmarks.length < LANDMARK_SAMPLES_MAX && sample.t_ms >= this.episode.t_start_ms && sample.t_ms > (this.landmarks.at(-1)?.t_ms ?? -1)) this.landmarks.push(sample);
  }
  feedGap(reason) {
    this.resetQuiet();
    const t = Math.max(now(), (this.controller?.last_ms ?? -1) + 1);
    this.feed({ t_ms: t, busy: null, motion: null, frame_valid: false, gap: true }, null, null, reason);
    // A gap always ends an automatic episode, even if the controller had already been
    // reset (then the step above emitted 'gap' without 'abort'; the gap is recorded).
    if (this.episode?.automatic) this.discardAutomatic(reason);
  }
  feed(sample, frame, gray, reason) {
    let actions;
    try { [this.controller, actions] = step(this.controller, sample); }
    catch {
      // Only a non-increasing time can throw here (measurements are validated by the
      // adapter). Restart from idle; an automatic episode in progress is a gap.
      this.controller = null;
      this.abortAutomatic(sample.t_ms, 'controller clock did not advance');
      return;
    }
    for (const action of actions) this.apply(action, sample, frame, gray, reason);
  }
  apply(action, sample, frame, gray, reason) {
    const t = sample.t_ms;
    switch (action) {
      case 'start':
        this.episode = { episode_id: uuid(), t_start_ms: t, automatic: true };
        this.burst = []; this.burstStarted = false; this.landmarks = []; this.resetQuiet();
        this.count('episodes_started');
        break;
      case 'select_pre_contact': {
        // The oldest retained frame before the busy frame (the ring holds about 2 s).
        const pre = this.ring.find(candidate => candidate.t_ms < t) ?? frame;
        if (pre) { this.pin(pre, 'pre_contact'); this.episode.t_start_ms = pre.t_ms; }
        this.landmarks = this.samples.filter(candidate => candidate.t_ms >= this.episode.t_start_ms).slice(0, LANDMARK_SAMPLES_MAX);
        this.status('Automatic episode started: a hand looks busy. Keep the item in view until it rests.'); this.update();
        break;
      }
      case 'select_hand_busy': this.pin(frame, 'hand_busy'); break;
      case 'select_carry':
        // Carry is an optional single pin: the controller emits it at most once per episode.
        this.pin(frame, 'carry'); this.burstStarted = true; this.pushBurst(frame, gray);
        this.status('Automatic episode: motion with a busy hand; recording the carry burst.');
        break;
      case 'select_release':
        // The controller legitimately re-emits select_release when settling was reset
        // by a missing measurement. Keep only the latest release frame so the pin
        // budget (PIN_MAX) can never crowd out the rest keyframe.
        this.replacePin(frame, 'release'); this.status('Automatic episode: hand released; waiting for the item to rest.');
        break;
      case 'select_rest':
        if (!this.pin(frame, 'rest')) this.abortAutomatic(t, 'rest frame unavailable');
        break;
      case 'finish':
        // An automatic packet never ships without its rest keyframe.
        if (!this.episode?.automatic) break;
        if (this.pins.at(-1)?.role === 'rest') void this.finish('released', t);
        else this.abortAutomatic(t, 'rest frame unavailable');
        break;
      case 'gap': this.recordGap(this.episode?.automatic ? this.episode.t_start_ms : t, t, reason || `Automatic episode exceeded ${MAX_EPISODE_MS / 1000} seconds without a rest`); break;
      case 'abort': this.discardAutomatic(reason || `no rest within ${MAX_EPISODE_MS / 1000} seconds`); break;
      default: break;
    }
  }
  pushBurst(frame, gray) {
    if (!this.episode?.automatic || !this.burstStarted || !gray || this.burst.length >= BURST_MAX || frame.t_ms <= this.episode.t_start_ms) return;
    const { width, height } = this.analysis;
    this.burst.push({ frame_id: frame.frame_id, t_ms: frame.t_ms, jpeg_b64: encodeGrayJPEG(gray, width, height), width, height });
  }
  // Pin `frame` under `role`, dropping an earlier pin of the same role (its bitmap
  // left the ring when it was pinned, so it is closed here). Returns pin()'s result.
  replacePin(frame, role) {
    if (!frame || this.ring.indexOf(frame) < 0) return false;
    const index = this.pins.findIndex(pin => pin.role === role);
    if (index >= 0) this.pins.splice(index, 1)[0].bitmap.close();
    return this.pin(frame, role);
  }
  // Abort an automatic episode at time t: a gap entry [episode start, t] with the
  // reason, pins discarded, no packet.
  abortAutomatic(t, reason) {
    if (!this.episode?.automatic) return;
    this.recordGap(this.episode.t_start_ms, t, reason);
    this.discardAutomatic(reason);
  }
  discardAutomatic(reason) {
    if (!this.episode?.automatic) return;
    this.clearEpisode(); this.count('episodes_aborted');
    this.status(`Automatic episode discarded (${reason}). Its frames were not stored as a memory.`); this.update();
  }
  async rest() {
    if (!this.running || !this.episode || this.saving) return;
    if (this.episode.automatic) throw new Error('An automatic episode is in progress; it ends when the item rests. Cancel it to mark manually.');
    await this.tick();
    if (!this.running || !this.episode) return;
    const frame = this.ring.at(-1);
    if (!frame || frame.t_ms <= this.pins.at(-1).t_ms || now() - frame.t_ms > 400) throw new Error('Waiting for a distinct, fresh rest frame. Try again.');
    this.pin(frame, 'rest');
    await this.finish('released', frame.t_ms);
  }
  packet(hint, end) {
    const keyframes = this.pins.map(frame => {
      this.context.drawImage(frame.bitmap, 0, 0, this.capture.width, this.capture.height);
      const data = this.canvas.toDataURL('image/jpeg', .72);
      if (!data.startsWith('data:image/jpeg;base64,')) throw new Error('JPEG encoding failed.');
      return { frame_id: frame.frame_id, t_ms: frame.t_ms, role: frame.role, jpeg_b64: data.slice(data.indexOf(',') + 1) };
    });
    const automatic = this.episode.automatic === true;
    return { schema_version: 1, episode_id: this.episode.episode_id, device_id: this.queue.deviceId, session_id: this.sessionId,
      t_start_ms: this.episode.t_start_ms, t_end_ms: Math.max(end, this.pins.at(-1).t_ms), clock_anchor: this.anchor,
      capture: this.capture, analysis: this.analysis, keyframes, carry_burst: this.burst,
      landmarks: automatic ? this.landmarks.slice(0, LANDMARK_SAMPLES_MAX).map(sample => ({ frame_id: sample.frame_id, t_ms: sample.t_ms, hands: sample.hands.slice(0, 2) })) : [],
      gaps: this.gaps.slice(-32), outcome_hint: hint, capture_mode: automatic ? 'automatic' : 'manual' };
  }
  async finish(hint, end = now()) {
    if (!this.episode || this.saving) return;
    const automatic = this.episode.automatic === true;
    this.saving = true; this.update();
    try {
      const packet = this.packet(hint, end);
      this.unsaved = packet; this.count('episodes_finished');
      this.clearEpisode();
      await this.queue.enqueue(packet);
      this.unsaved = null;
      this.status(hint === 'gap' ? 'Interrupted episode saved locally with a coverage gap; no rest was confirmed.' : `${automatic ? 'Automatic' : 'Manual'} episode saved locally. Server processing may yield context only, not a recognized item.`);
    } catch (error) {
      // No packet could be built: the episode ended without one (aborted). A packet
      // that could not be saved stays in this.unsaved and was counted as finished.
      if (!this.unsaved) this.count('episodes_aborted');
      this.clearEpisode();
      this.release();
      this.status(`${error.message} Coverage is interrupted.${this.unsaved ? ' One unsaved packet remains in this page; use Retry saved captures before closing.' : ' This episode could not be encoded and was lost.'}`);
    } finally { this.saving = false; this.update(); }
  }
  async retryUnsaved() {
    if (!this.unsaved || this.saving) return;
    this.saving = true; this.update();
    try { await this.queue.enqueue(this.unsaved); this.unsaved = null; this.status('The unsaved episode is now in durable browser retry storage.'); }
    finally { this.saving = false; this.update(); }
  }
  // CP4: after "Erase everything" a packet captured before the erasure must not be
  // re-added (the server would refuse it as erased_before); drop it here.
  discardUnsaved() {
    if (!this.unsaved || this.saving) return false;
    this.unsaved = null; this.update(); return true;
  }
  clearEpisode() {
    this.pins.forEach(frame => frame.bitmap.close()); this.pins = []; this.burst = []; this.previousGray = null; this.episode = null;
    this.landmarks = []; this.burstStarted = false;
  }
  cancel() {
    const automatic = this.episode?.automatic === true;
    if (this.episode) this.count('episodes_aborted');
    this.clearEpisode(); this.ring.forEach(frame => frame.bitmap.close()); this.ring = []; this.controller = null; this.resetQuiet();
    this.status(`${automatic ? 'Automatic' : 'Manual'} episode cancelled. Its unsaved frames were discarded, not stored as a memory.`); this.update();
  }
  // `counted` (CP5): whether the entry counts toward the telemetry gaps/gap_ms. It
  // then counts only by the part of it inside the current window, and only when
  // that part is longer than zero: the time the camera was off before a start adds
  // nothing, and the reason text never leaves the packet's gaps[].
  recordGap(from, to, reason, { counted = true } = {}) {
    const gap = { t_from_ms: Math.max(0, from), t_to_ms: Math.max(from, to), reason: String(reason).slice(0, 160) };
    this.gaps.push(gap); this.gaps = this.gaps.slice(-32);
    const start = this.window.start_ms === null ? gap.t_to_ms : this.window.start_ms;
    const inside = Math.max(0, Math.round(gap.t_to_ms - Math.max(gap.t_from_ms, start)));
    if (counted && inside > 0) { this.count('gaps'); this.count('gap_ms', inside); }
    this.onGap(gap);
  }
  release() {
    this.running = false; this.starting = false; this.generation++;
    clearInterval(this.timer); clearInterval(this.telemetryTimer); this.telemetryTimer = null;
    this.stream?.getTracks().forEach(track => track.stop()); this.stream = null;
    this.video.pause(); this.video.srcObject = null;
    this.ring.forEach(frame => frame.bitmap.close()); this.ring = [];
    this.controller = null; this.samples = []; this.adapter.reset?.(); this.resetQuiet();
  }
  // `interrupted` (CP5): false when the stop was the user's or the page's own choice
  // (pause, stop, sign-out, erasure, consent); true (the default) for anything that
  // took the camera away, which the Status panel reports as an interruption until
  // the next start.
  async stop(reason = 'Stopped by user', { interrupted = true } = {}) {
    const wasActive = this.running || this.starting, wasRunning = this.running;
    const t = now();
    this.release();
    // The stop ends the telemetry window; the tail since the last captured frame
    // counts as a gap inside it only when it exceeds the frame-delivery threshold
    // (a frozen page), never the sub-interval remainder of an ordinary stop.
    if (wasActive) { this.recordGap(this.lastTime ?? t, t, reason, { counted: this.lastTime !== null && t - this.lastTime > 1000 }); this.gapStart = t; }
    if (wasRunning && interrupted) { this.interruptions.push({ from_ms: Date.now(), to_ms: null }); this.interruptions = this.interruptions.slice(-64); }
    if (this.episode) await this.finish('gap', t);
    this.clearEpisode();
    this.canvas.width = this.canvas.height = this.analysisCanvas.width = this.analysisCanvas.height = this.handCanvas.width = this.handCanvas.height = 1;
    // The final telemetry window of the session (keepalive: a hidden page may still
    // deliver it); never awaited, never retried.
    if (wasRunning) void this.postTelemetry(true);
    if (wasActive && !this.unsaved) this.status(`${reason}. Camera off; coverage is interrupted. Start again explicitly to resume.`);
    this.update();
  }
}
