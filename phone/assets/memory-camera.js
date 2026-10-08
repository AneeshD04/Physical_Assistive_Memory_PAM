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
const now = () => Math.floor(performance.now());
function createHandWorker() {
  try { return typeof Worker === 'function' ? new Worker(HAND_WORKER_URL) : null; } catch { return null; }
}
// Class name kept from the first checkpoint: manual marking is unchanged, and the
// automatic path (CP2) is layered on the same ring/pin/burst machinery.
export class ManualCamera {
  constructor({ video, queue, status = () => {}, changed = () => {}, gap = () => {}, worker, createWorker } = {}) {
    this.video = video; this.queue = queue; this.status = status; this.changed = changed; this.onGap = gap;
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
      automatic: this.automatic, automaticActive: this.automaticActive(), automaticEpisode: !!this.episode?.automatic, adapter: this.adapterState() });
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
    this.automatic = next; this.controller = null; this.adapter.reset?.();
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
      await this.tick();
    } catch (error) {
      await this.stop('Camera could not start');
      throw new Error(error.name === 'NotAllowedError' ? 'Camera permission was not granted. Capture remains off.' : 'Camera unavailable. Check permission and your secure connection, then try again.');
    } finally { this.starting = false; this.update(); }
  }
  async tick() {
    if (this.framePromise) return this.framePromise;
    if (!this.running || this.video.readyState < 2) return;
    const generation = this.generation, t = now();
    if (this.lastTime !== null && t <= this.lastTime) return;
    if (this.lastTime !== null && t - this.lastTime > 1000) { await this.stop('Frame delivery gap'); return; }
    this.framePromise = (async () => {
      this.context.drawImage(this.video, 0, 0, this.capture.width, this.capture.height);
      const bitmap = await createImageBitmap(this.canvas);
      if (!this.running || generation !== this.generation) { bitmap.close(); return; }
      const frame = { frame_id: uuid(), t_ms: t, bitmap };
      this.lastTime = t; this.ring.push(frame); this.trim(t);
      if (this.episode && !this.episode.automatic) {
        if (t - this.episode.t_start_ms >= MAX_EPISODE_MS) { await this.stop('Manual episode reached the 10 second limit'); return; }
        this.captureBurst(frame);
      } else if (this.automaticActive()) {
        await this.automaticTick(frame, generation);
      }
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
    this.burst = []; this.burstStarted = false; this.previousGray = null; this.controller = null; this.adapter.reset?.();
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
    if (this.saving || this.unsaved) { this.controller = null; return; }
    const gray = this.grayOf(frame);
    let bitmap = null;
    try { bitmap = await this.handBitmap(frame); } catch { bitmap = null; }
    const analyze = this.adapter.analyze;
    if (!this.running || generation !== this.generation || !this.automaticActive() || typeof analyze !== 'function') { bitmap?.close(); return; }
    const analysis = await analyze(t, { data: gray, width: this.analysis.width, height: this.analysis.height }, bitmap);
    if (!this.running || generation !== this.generation || !this.automaticActive()) return;
    if (this.saving || this.unsaved || (this.episode && !this.episode.automatic)) { this.controller = null; return; }
    if (Array.isArray(analysis.hands)) this.rememberSample({ frame_id: frame.frame_id, t_ms: t, hands: analysis.hands });
    this.feed({ t_ms: t, busy: analysis.busy, motion: analysis.motion, frame_valid: analysis.frame_valid }, frame, gray, null);
    if (this.episode?.automatic && this.burstStarted && this.burst.at(-1)?.frame_id !== frame.frame_id) this.pushBurst(frame, gray);
  }
  rememberSample(sample) {
    this.samples.push(sample);
    while (this.samples.length && (this.samples.length > RING_MAX || sample.t_ms - this.samples[0].t_ms > RING_MS)) this.samples.shift();
    if (this.episode?.automatic && this.landmarks.length < LANDMARK_SAMPLES_MAX && sample.t_ms >= this.episode.t_start_ms && sample.t_ms > (this.landmarks.at(-1)?.t_ms ?? -1)) this.landmarks.push(sample);
  }
  feedGap(reason) {
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
        this.burst = []; this.burstStarted = false; this.landmarks = [];
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
    this.clearEpisode();
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
      this.unsaved = packet;
      this.clearEpisode();
      await this.queue.enqueue(packet);
      this.unsaved = null;
      this.status(hint === 'gap' ? 'Interrupted episode saved locally with a coverage gap; no rest was confirmed.' : `${automatic ? 'Automatic' : 'Manual'} episode saved locally. Server processing may yield context only, not a recognized item.`);
    } catch (error) {
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
  clearEpisode() {
    this.pins.forEach(frame => frame.bitmap.close()); this.pins = []; this.burst = []; this.previousGray = null; this.episode = null;
    this.landmarks = []; this.burstStarted = false;
  }
  cancel() {
    const automatic = this.episode?.automatic === true;
    this.clearEpisode(); this.ring.forEach(frame => frame.bitmap.close()); this.ring = []; this.controller = null;
    this.status(`${automatic ? 'Automatic' : 'Manual'} episode cancelled. Its unsaved frames were discarded, not stored as a memory.`); this.update();
  }
  recordGap(from, to, reason) {
    const gap = { t_from_ms: Math.max(0, from), t_to_ms: Math.max(from, to), reason: String(reason).slice(0, 160) };
    this.gaps.push(gap); this.gaps = this.gaps.slice(-32); this.onGap(gap);
  }
  release() {
    this.running = false; this.starting = false; this.generation++;
    clearInterval(this.timer);
    this.stream?.getTracks().forEach(track => track.stop()); this.stream = null;
    this.video.pause(); this.video.srcObject = null;
    this.ring.forEach(frame => frame.bitmap.close()); this.ring = [];
    this.controller = null; this.samples = []; this.adapter.reset?.();
  }
  async stop(reason = 'Stopped by user') {
    const wasActive = this.running || this.starting;
    const t = now();
    this.release();
    if (wasActive) { this.recordGap(this.lastTime ?? t, t, reason); this.gapStart = t; }
    if (this.episode) await this.finish('gap', t);
    this.clearEpisode();
    this.canvas.width = this.canvas.height = this.analysisCanvas.width = this.analysisCanvas.height = this.handCanvas.width = this.handCanvas.height = 1;
    if (wasActive && !this.unsaved) this.status(`${reason}. Camera off; coverage is interrupted. Start again explicitly to resume.`);
    this.update();
  }
}
