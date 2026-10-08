import { uuid } from './memory-queue.js';
import { MAX_EPISODE_MS, createAutomaticAdapter } from './controller.js';
import { encodeGrayJPEG } from './grayscale-jpeg.js';
export const RING_MAX = 20, PIN_MAX = 8, BURST_MAX = 10, RING_MS = 2000;
export const BITMAP_BYTE_CAP = 64 * 1024 * 1024;
const now = () => Math.floor(performance.now());
export class ManualCamera {
  constructor({ video, queue, status = () => {}, changed = () => {}, gap = () => {} }) {
    this.video = video; this.queue = queue; this.status = status; this.changed = changed; this.onGap = gap;
    this.sessionId = uuid(); this.anchor = { mono_ms: now(), wall_ms: Date.now() };
    this.ring = []; this.pins = []; this.burst = []; this.gaps = []; this.episode = null;
    this.stream = null; this.running = false; this.starting = false; this.generation = 0; this.lastTime = null;
    this.canvas = document.createElement('canvas'); this.analysisCanvas = document.createElement('canvas');
    this.adapter = createAutomaticAdapter(); this.unsaved = null; this.saving = false;
  }
  update() { this.changed({ running: this.running, starting: this.starting, episode: !!this.episode, saving: this.saving, unsaved: !!this.unsaved }); }
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
      Object.assign(this.canvas, this.capture); Object.assign(this.analysisCanvas, this.analysis);
      this.context = this.canvas.getContext('2d', { alpha: false });
      this.analysisContext = this.analysisCanvas.getContext('2d', { alpha: false, willReadFrequently: true });
      if (!this.context || !this.analysisContext) throw new Error('Camera image processing is unavailable.');
      if (this.gapStart !== undefined) { this.recordGap(this.gapStart, now(), 'Capture resumed after a gap'); this.gapStart = undefined; }
      this.running = true; this.lastTime = null;
      this.status('Camera on · manual marks only. Nothing is automatically recognized.');
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
      if (this.episode) {
        if (t - this.episode.t_start_ms >= MAX_EPISODE_MS) { await this.stop('Manual episode reached the 10 second limit'); return; }
        this.captureBurst(frame);
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
    this.burst = []; this.burstStarted = false; this.previousGray = null;
    this.status('Before-move frame pinned. Move the item, then mark at rest within 10 seconds.'); this.update();
  }
  captureBurst(frame) {
    if (this.burst.length >= BURST_MAX || frame.t_ms <= this.episode.t_start_ms) return;
    const { width, height } = this.analysis;
    this.analysisContext.drawImage(frame.bitmap, 0, 0, width, height);
    const rgba = this.analysisContext.getImageData(0, 0, width, height).data;
    const gray = new Uint8Array(width * height); let difference = 0;
    for (let i = 0; i < gray.length; i++) {
      gray[i] = Math.round(.299 * rgba[i * 4] + .587 * rgba[i * 4 + 1] + .114 * rgba[i * 4 + 2]);
      if (this.previousGray) difference += Math.abs(gray[i] - this.previousGray[i]);
    }
    // User-marked busy interval plus measured image motion, not hand recognition.
    // Pin the first valid motion window causally; never a future midpoint.
    const motion = this.previousGray && difference / gray.length > 6;
    this.previousGray = gray;
    if (!this.burstStarted && !motion) return;
    this.burstStarted = true;
    this.burst.push({ frame_id: frame.frame_id, t_ms: frame.t_ms, jpeg_b64: encodeGrayJPEG(gray, width, height), width, height });
  }
  async rest() {
    if (!this.running || !this.episode || this.saving) return;
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
    return { schema_version: 1, episode_id: this.episode.episode_id, device_id: this.queue.deviceId, session_id: this.sessionId,
      t_start_ms: this.episode.t_start_ms, t_end_ms: Math.max(end, this.pins.at(-1).t_ms), clock_anchor: this.anchor,
      capture: this.capture, analysis: this.analysis, keyframes, carry_burst: this.burst, landmarks: [], gaps: this.gaps.slice(-32), outcome_hint: hint, capture_mode: 'manual' };
  }
  async finish(hint, end = now()) {
    if (!this.episode || this.saving) return;
    this.saving = true; this.update();
    try {
      const packet = this.packet(hint, end);
      this.unsaved = packet;
      this.clearEpisode();
      await this.queue.enqueue(packet);
      this.unsaved = null;
      this.status(hint === 'gap' ? 'Interrupted episode saved locally with a coverage gap; no rest was confirmed.' : 'Manual episode saved locally. Server processing may yield context only, not a recognized item.');
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
  }
  cancel() {
    this.clearEpisode(); this.ring.forEach(frame => frame.bitmap.close()); this.ring = [];
    this.status('Manual episode cancelled. Its unsaved frames were discarded, not stored as a memory.'); this.update();
  }
  recordGap(from, to, reason) {
    const gap = { t_from_ms: Math.max(0, from), t_to_ms: Math.max(from, to), reason };
    this.gaps.push(gap); this.gaps = this.gaps.slice(-32); this.onGap(gap);
  }
  release() {
    this.running = false; this.starting = false; this.generation++;
    clearInterval(this.timer);
    this.stream?.getTracks().forEach(track => track.stop()); this.stream = null;
    this.video.pause(); this.video.srcObject = null;
    this.ring.forEach(frame => frame.bitmap.close()); this.ring = [];
  }
  async stop(reason = 'Stopped by user') {
    const wasActive = this.running || this.starting;
    const t = now();
    this.release();
    if (wasActive) { this.recordGap(this.lastTime ?? t, t, reason); this.gapStart = t; }
    if (this.episode) await this.finish('gap', t);
    this.clearEpisode();
    this.canvas.width = this.canvas.height = this.analysisCanvas.width = this.analysisCanvas.height = 1;
    if (wasActive && !this.unsaved) this.status(`${reason}. Camera off; coverage is interrupted. Start again explicitly to resume.`);
    this.update();
  }
}
