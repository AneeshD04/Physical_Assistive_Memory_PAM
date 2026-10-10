// Exact transport bytes are retained; retries never regenerate a packet or UUID.
export const MAX_PACKET_BYTES = 4 * 1024 * 1024;
export const MAX_QUEUE_BYTES = 48 * 1024 * 1024;
export const MAX_QUEUE_EPISODES = 32;
export const uuid = () => crypto.randomUUID();
export async function transportDigest(body) {
  const bytes = typeof body === 'string' ? new TextEncoder().encode(body) : body;
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(hash)].map(value => value.toString(16).padStart(2, '0')).join('');
}
export function matchesAck(record, ack) {
  return ack?.retained === true && ack.episode_id === record.episode_id &&
    ack.device_id === record.device_id && ack.digest === record.digest &&
    ['stored', 'duplicate', 'revised', 'conflict'].includes(ack.status);
}
function requestResult(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(new Error('Local storage is unavailable.'));
  });
}
function finished(transaction) {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = resolve;
    transaction.onerror = transaction.onabort = () => reject(new Error('Local storage could not retain this capture.'));
  });
}
// CP4 refusal codes on POST /api/episodes (409): consent_required keeps the packet
// queued until the disclosure is acknowledged; erased_before means the packet was
// captured before "Erase everything" and is dropped (reported as a coverage gap).
export const CONSENT_REQUIRED = 'consent_required', ERASED_BEFORE = 'erased_before';
export class RetryQueue {
  // CP5 frame accounting: `sent(record)` is called once per upload attempt (the
  // record carries its exact byte size), `acked(record)` once per matching durable
  // acknowledgement, `reported({count, bytes})` whenever the queue re-counts what is
  // still waiting (also kept as `pending` for the Status panel). Counts only.
  constructor({ notify = () => {}, unauthorized = () => {}, retained = () => {}, dropped = () => {}, consentRequired = () => {}, sent = () => {}, acked = () => {}, reported = () => {} } = {}) {
    this.notify = notify; this.unauthorized = unauthorized; this.retained = retained; this.dropped = dropped; this.consentRequired = consentRequired;
    this.sent = sent; this.acked = acked; this.reported = reported; this.pending = { count: 0, bytes: 0 };
    this.enabled = false; this.flushing = false; this.db = null; this.abort = null;
  }
  async open() {
    if (!globalThis.indexedDB || !globalThis.crypto?.subtle || !globalThis.crypto?.randomUUID) {
      throw new Error('Secure browser storage is unavailable. Capture is disabled to avoid losing evidence.');
    }
    const opening = indexedDB.open('pam-memory-mirror-v1', 1);
    opening.onupgradeneeded = () => {
      const db = opening.result;
      db.createObjectStore('episodes', { keyPath: 'episode_id' });
      db.createObjectStore('meta');
    };
    this.db = await new Promise((resolve, reject) => {
      opening.onsuccess = () => resolve(opening.result);
      opening.onerror = opening.onblocked = () => reject(new Error('Local retry storage is blocked. Close other Pam tabs and try again.'));
    });
    this.db.onversionchange = () => { this.db.close(); this.enabled = false; this.notify('Local storage changed. Reload before capturing; coverage is interrupted.'); };
    const tx = this.db.transaction('meta', 'readwrite');
    const done = finished(tx);
    const store = tx.objectStore('meta');
    const request = store.get('device_id');
    // Write inside the IndexedDB callback so Safari cannot auto-close the transaction.
    request.onsuccess = () => {
      this.deviceId = request.result || uuid();
      if (!request.result) store.put(this.deviceId, 'device_id');
    };
    await done;
    await this.report();
    return this.deviceId;
  }
  async records() {
    if (!this.db) throw new Error('Local retry storage is not ready.');
    return requestResult(this.db.transaction('episodes', 'readonly').objectStore('episodes').getAll());
  }
  async enqueue(packet) {
    const body = JSON.stringify(packet);
    const size = new TextEncoder().encode(body).byteLength;
    if (size > MAX_PACKET_BYTES) throw new Error('Capture exceeds the 4 MiB packet limit. No upload was attempted; mark a shorter episode.');
    const digest = await transportDigest(body);
    const record = { episode_id: packet.episode_id, device_id: packet.device_id, body, digest, size, created_at: Date.now() };
    const tx = this.db.transaction('episodes', 'readwrite');
    const done = finished(tx); const store = tx.objectStore('episodes');
    let full = false;
    const request = store.getAll();
    request.onsuccess = () => {
      const rows = request.result;
      if (rows.some(row => row.episode_id === record.episode_id) || rows.length >= MAX_QUEUE_EPISODES || rows.reduce((sum, row) => sum + row.size, 0) + size > MAX_QUEUE_BYTES) {
        full = true; tx.abort(); return;
      }
      store.add(record);
    };
    try { await done; } catch (error) {
      if (full) throw new Error('Retry storage is full. Existing episodes are retained; this new episode was not saved. Sync captures before continuing.');
      throw error;
    }
    await this.report();
    void this.flush();
    return record;
  }
  setAuthenticated(value) {
    this.enabled = value;
    if (!value) this.abort?.abort();
    else void this.flush();
  }
  // Delete one queued record (used for a packet the server refuses for good).
  async remove(episodeId) {
    const tx = this.db.transaction('episodes', 'readwrite');
    const done = finished(tx);
    tx.objectStore('episodes').delete(episodeId);
    await done;
  }
  // CP4: after a successful "Erase everything" the local mirror is emptied so no
  // queued capture from before the erasure is ever uploaded. Returns the number of
  // records removed.
  async clear() {
    if (!this.db) throw new Error('Local retry storage is not ready.');
    this.abort?.abort();
    const tx = this.db.transaction('episodes', 'readwrite');
    const done = finished(tx); const store = tx.objectStore('episodes');
    let count = 0;
    const request = store.count();
    request.onsuccess = () => { count = request.result; store.clear(); };
    await done;
    await this.report();
    return count;
  }
  async report() {
    const rows = await this.records();
    const bytes = rows.reduce((sum, row) => sum + row.size, 0);
    const old = rows.some(row => Date.now() - row.created_at > 7 * 86400000);
    this.notify(rows.length ? `${rows.length} capture${rows.length === 1 ? '' : 's'} awaiting durable acknowledgement · ${(bytes / 1048576).toFixed(1)} MiB.${old ? ' Some are over 7 days old; still retained here. Browser eviction would cause coverage loss.' : ''}` : 'No captures waiting to sync.');
    this.pending = { count: rows.length, bytes };
    try { this.reported({ ...this.pending }); } catch { /* a listener failure never blocks the queue */ }
    return { count: rows.length, bytes };
  }
  async flush() {
    if (!this.enabled || !this.db || this.flushing) return;
    this.flushing = true;
    try {
      const records = await this.records();
      for (const record of records) {
        if (!this.enabled) break;
        if (await transportDigest(record.body) !== record.digest) {
          this.notify('A local capture failed its integrity check. It is retained, but will not be uploaded.');
          break;
        }
        this.abort = new AbortController();
        const timer = setTimeout(() => this.abort?.abort(), 20000);
        let response;
        try { this.sent(record); } catch { /* accounting never blocks an upload */ }
        try {
          response = await fetch('/api/episodes', { method: 'POST', credentials: 'same-origin', cache: 'no-store', headers: { 'Content-Type': 'application/json' }, body: record.body, signal: this.abort.signal });
        } finally { clearTimeout(timer); }
        if (response.status === 401) { this.enabled = false; this.unauthorized(); break; }
        let result;
        try { result = await response.json(); } catch { result = null; }
        const code = response.status === 409 && result && typeof result.code === 'string' ? result.code : null;
        if (code === ERASED_BEFORE) {
          // Captured before "Erase everything": the server will never accept it, and a
          // browser mirror must not re-add erased evidence. Dropped and counted as a gap.
          await this.remove(record.episode_id);
          this.dropped(record, 'captured before erasure');
          await this.report();
          continue;
        }
        if (code === CONSENT_REQUIRED) {
          this.notify('Saved captures stay in this browser until the camera disclosure is acknowledged (Privacy view).');
          this.consentRequired();
          break;
        }
        if (!matchesAck(record, result?.ack)) {
          this.notify(`Capture retained locally: ${response.ok ? 'the server acknowledgement did not match.' : `upload not acknowledged (HTTP ${response.status}).`} Retry after the service is available.`);
          break;
        }
        await this.remove(record.episode_id);
        try { this.acked(record); } catch { /* accounting never blocks the queue */ }
        this.retained(result);
        await this.report();
      }
    } catch (error) {
      if (this.enabled) this.notify('Capture sync interrupted. Saved packets remain in this browser for retry; no server retention is assumed.');
    } finally { this.abort = null; this.flushing = false; }
  }
}
