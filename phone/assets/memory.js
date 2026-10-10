import { RetryQueue } from './memory-queue.js';
import { ManualCamera, idleSummary } from './memory-camera.js';
const $ = id => document.getElementById(id);
const text = (element, value) => { element.textContent = value == null ? '' : String(value); };
function node(tag, content, className) { const element = document.createElement(tag); if (content != null) text(element, content); if (className) element.className = className; return element; }
let authenticated = false, authGeneration = 0, currentView = 'chat', catalogueSequence = 0, detailSequence = 0;
let selectedId = null, detailTrigger = null, lastCatalogue = '', storageReady = false, camera = null;
// CP3: the item currently shown in the detail dialog (its DTO as last loaded) and
// the action a confirmation dialog is waiting on (null when none is open).
let detailItem = null, pendingConfirm = null;
// CP4: the server's consent state (GET /api/consent) and whether the camera may
// start; the retention row as last loaded; the camera's last reported state.
let consent = null, consentOk = false, consentBusy = false, retention = null, cameraState = null, privacySequence = 0, eraseBusy = false;
const CONSENT_FALLBACK = 'Disclosure unavailable; camera stays off.';
const ERASE_ALL_PHRASE = 'ERASE EVERYTHING';
const RETENTION_FIELDS = [
  { key: 'episodes_days', input: 'retention-episodes-days', min: 7, max: 365, label: 'Memories and their photos', unit: 'days' },
  { key: 'idle_hours', input: 'retention-idle-hours', min: 1, max: 72, label: 'Idle stills', unit: 'hours' },
  { key: 'landmarks_hours', input: 'retention-landmarks-hours', min: 1, max: 168, label: 'Hand positions', unit: 'hours' }];
const COUNT_KEYS = ['idle_cached', 'idle_promoted', 'revisions_expired', 'landmarks_reduced', 'revisions_erased'];
// The server's own verdict on automatic hand recognition (GET /api/health
// capabilities); null until a health response names that capability.
let handPolicy = null;
const HAND_CAPABILITY = 'automatic_hand_recognition';
function notice(message) { text($('app-status'), message); $('app-status').hidden = !message; }
function dateLabel(value) {
  if (!Number.isSafeInteger(value) || value <= 0) return 'Time not recorded';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Time not recorded' : date.toLocaleString();
}
// A server-supplied image URL is used only when it is exactly the same-origin
// path this page expects for that record: no other host, credentials, query,
// fragment or path. Anything else renders as "no image", never as a request.
function safePath(candidate, expected) {
  if (typeof candidate !== 'string' || !candidate.startsWith('/api/items/') || candidate.startsWith('//')) return null;
  try {
    const url = new URL(candidate, location.origin);
    return url.origin === location.origin && !url.username && !url.password && !url.search && !url.hash && url.pathname === expected ? expected : null;
  } catch { return null; }
}
function safeImageURL(item) {
  if (!item || typeof item.item_id !== 'string') return null;
  return safePath(item.image_url, `/api/items/${encodeURIComponent(item.item_id)}/image`);
}
// CP3: an evidence row's photo is that observation's own keyframe,
// GET /api/items/{id}/observations/{obs}/image, under the same discipline.
function safeObservationImageURL(itemId, observation) {
  if (typeof itemId !== 'string' || !observation || typeof observation.observation_id !== 'string' || observation.observation_id.length > 100) return null;
  return safePath(observation.image_url, `/api/items/${encodeURIComponent(itemId)}/observations/${encodeURIComponent(observation.observation_id)}/image`);
}
function targetBox(item) {
  // reference_image.bbox is [x1, y1, x2, y2] in the evidence image's own pixels.
  const reference = item.reference_image;
  const box = reference && typeof reference === 'object' ? reference.bbox : null;
  if (!Array.isArray(box) || box.length !== 4 || !box.every(value => Number.isFinite(value) && value >= 0)) return null;
  const [x1, y1, x2, y2] = box;
  return x2 > x1 && y2 > y1 ? { x1, y1, x2, y2 } : null;
}
// One evidence photo with the recorded region outlined on it (dashed when the
// identity is unverified). Shared by item cards, the detail view and CP3
// evidence rows; the figure is sized to the image so the overlay is exact.
function evidenceFigure({ url, box, verified, alt, maxHeight = 340, lazy = true }) {
  const figure = node('figure', null, 'evidence-figure');
  const img = node('img'); img.src = url; if (lazy) img.loading = 'lazy'; img.decoding = 'async'; img.className = 'evidence';
  img.alt = alt;
  img.addEventListener('error', () => figure.replaceWith(node('p', 'Evidence image is unavailable or your session has expired.', 'muted')), { once: true });
  img.addEventListener('load', () => {
    const width = img.naturalWidth, height = img.naturalHeight;
    if (!(width > 0 && height > 0)) return;
    // Size the figure to the image itself so the overlay percentages are exact.
    figure.style.aspectRatio = `${width} / ${height}`;
    figure.style.width = `min(100%, ${(maxHeight * width / height).toFixed(1)}px)`;
    if (!box || box.x2 > width || box.y2 > height) return;
    const target = node('div', null, verified ? 'target' : 'target target-unverified');
    target.setAttribute('aria-hidden', 'true');
    target.style.left = `${(100 * box.x1 / width).toFixed(2)}%`; target.style.top = `${(100 * box.y1 / height).toFixed(2)}%`;
    target.style.width = `${(100 * (box.x2 - box.x1) / width).toFixed(2)}%`; target.style.height = `${(100 * (box.y2 - box.y1) / height).toFixed(2)}%`;
    figure.append(target);
  }, { once: true });
  figure.append(img);
  return figure;
}
// CP4 (Oversight F3): a photo whose observation came from a promoted idle still is
// labelled as such wherever it is shown; it records that nothing had changed, not
// a hand placing anything.
const IDLE_SOURCE = 'reobservation';
const IDLE_SOURCE_TEXT = 'Seen while idle (automatic still), not a hand event';
const LEGACY_SOURCE_TEXT = 'Imported from the earlier app, unverified';
function idleBadge() { return node('p', IDLE_SOURCE_TEXT, 'badge badge-idle'); }
function image(item) {
  // CP4 retention: the packet bytes of an old revision were replaced by NULL; the
  // observation stays, its photo does not.
  if (item && item.evidence_expired === true) return node('p', 'Evidence image expired: the photo was removed by the retention window; the observation itself is kept.', 'muted evidence-expired');
  const url = safeImageURL(item);
  if (!url) return node('p', 'No evidence image available.', 'muted');
  const box = targetBox(item);
  const verified = item.identity_status === 'trusted';
  const idle = item.source === IDLE_SOURCE;
  const alt = `Recorded evidence for ${item.name || 'unnamed item'}; not a live view.` + (box ? (verified ? ' The recorded item is outlined.' : ' The outlined region is where a change was recorded; the item identity is unverified.') : '') + (idle ? ` ${IDLE_SOURCE_TEXT}.` : '');
  const figure = evidenceFigure({ url, box, verified, alt });
  if (!idle) return figure;
  // The caption sits under the figure (the figure itself is sized to the image).
  const fragment = document.createDocumentFragment();
  fragment.append(figure, idleBadge());
  return fragment;
}
function lookalikeCount(item) {
  return Array.isArray(item.lookalikes) ? item.lookalikes.filter(id => typeof id === 'string').length : 0;
}
// Clock-only staleness (CP2): the server ages a placed location by evaluation time
// and sets stale_reason "age" with aged: true. "aged" may be absent on an older
// server; its absence means nothing more than "not reported".
function ageNotice(item) {
  if (item.stale_reason === 'age' || item.aged === true) {
    return item.location_status === 'stale'
      ? 'Older evidence: recorded more than a week ago; this location is no longer relied on and the item may have moved.'
      : 'Older evidence: recorded more than a day ago; it may have moved.';
  }
  // CP4 rule 13: an idle still registered to the placement showed the item gone.
  if (item.stale_reason === 'negative_reobservation') return `It was no longer there when Pam looked at ${dateLabel(item.stale_since_ms)}. The last recorded place is kept as history, not as where it is now.`;
  return item.stale_reason ? `Note: ${item.stale_reason}` : null;
}
// CP4 containment: an inferred location names the container the item was last seen
// inside and where that container was last seen; nothing about the item itself was
// observed since. Null when the item is not inferred or the DTO lacks the inference.
// item_id -> name from the latest catalogue, so an inferred item can name its
// container even when the DTO carries only the container's id.
const catalogueNames = new Map();
function inferredText(item) {
  if (item.location_status !== 'inferred') return null;
  const inference = item.inference && typeof item.inference === 'object' ? item.inference : {};
  const known = typeof inference.container === 'string' ? catalogueNames.get(inference.container) : null;
  const container = typeof inference.container_name === 'string' && inference.container_name.trim() ? inference.container_name.trim() : (known || 'another stored item');
  return typeof item.location_text === 'string' && item.location_text.trim()
    ? `Probably with ${container}, last seen at ${item.location_text.trim()}.`
    : `Probably with ${container}, but Pam does not know where ${container} is now.`;
}
function describe(item, target) {
  // CP3 identity badge: an ambiguous item names how many stored items it cannot
  // be told apart from ("Identity: ambiguous · 1 lookalike"). A group never
  // upgrades anyone; the badge only withholds confidence.
  const lookalikes = lookalikeCount(item);
  const ambiguous = item.identity_status === 'ambiguous';
  target.append(node('p', `Identity: ${item.identity_status || 'unknown'}${lookalikes ? ` · ${lookalikes} lookalike${lookalikes === 1 ? '' : 's'}` : ''}`, ambiguous ? 'badge badge-ambiguous' : 'badge'));
  if (ambiguous) target.append(node('p', `Pam cannot tell this item apart from ${lookalikes ? `${lookalikes} other stored item${lookalikes === 1 ? '' : 's'}` : 'another stored item'}, so it will ask which one is yours rather than guess. Open the details to correct a mix-up.`, 'notice'));
  target.append(node('p', `Location: ${item.location_status || 'unknown'}${item.aged === true ? ' · older evidence' : ''}`));
  const inferred = inferredText(item);
  if (inferred) target.append(node('p', inferred, 'inferred'));
  else target.append(node('p', item.location_text || 'No supported location is recorded.'));
  target.append(node('p', `Observed: ${dateLabel(item.observed_at_ms)}`, 'muted'));
  const age = ageNotice(item);
  if (age) target.append(node('p', age, item.stale_reason === 'age' || item.aged === true ? 'notice aged' : 'notice'));
  if (item.index_pending) target.append(node('p', 'Processing pending. New evidence may change this record.', 'notice'));
  // CP4 migration: a row converted from the earlier app is provisional for good.
  if (item.source === 'legacy_v1') target.append(node('p', LEGACY_SOURCE_TEXT, 'badge badge-legacy'));
  target.append(node('p', `Relevance: ${item.relevance || 'unknown'} · Source: ${item.source || 'not recorded'}`, 'muted'));
}
function itemCard(item) {
  const card = node('article', null, 'card item-card'); card.dataset.itemId = item.item_id;
  card.append(node('h2', item.name || 'Unnamed item'), image(item)); describe(item, card);
  const button = node('button', 'View evidence & history', 'secondary'); button.dataset.itemId = item.item_id;
  button.addEventListener('click', () => openDetail(item.item_id, button)); card.append(button); return card;
}
// CP3: a refused correction (409) carries the server's own plain-language reason
// as {detail}; it is shown verbatim when it is a short sentence and nothing else
// (never a status code, a code token or a traceback). Anything else falls back
// to the generic text.
async function refusalBody(response) {
  try {
    const body = await response.json();
    if (!body || typeof body !== 'object') return { detail: null, code: null };
    const detail = typeof body.detail === 'string' ? body.detail.trim() : '';
    return { detail: detail && detail.length <= 400 && !/traceback|\n/i.test(detail) ? detail : null, code: typeof body.code === 'string' && body.code.length <= 40 ? body.code : null };
  } catch { return { detail: null, code: null }; }
}
// CP4 refusal codes (409) with their plain-language meaning. The server's own
// `detail` sentence wins when it gives one; a code never reaches the screen.
const REFUSALS = {
  consent_required: 'The camera disclosure must be acknowledged on this server first. Open the Privacy view.',
  erased_before: 'This capture was made before everything was erased, so the server will not keep it.',
  confirm_mismatch: 'The confirmation phrase did not match. Nothing was erased.',
  pin_mismatch: 'That PIN was not accepted. Nothing was erased.'
};
// Errors thrown by api() carry .status (HTTP) and .code (the server's refusal
// code when it gave one) so a caller can act on a refusal without parsing text.
async function api(path, options = {}) {
  const generation = authGeneration;
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(path, { ...options, credentials: 'same-origin', cache: 'no-store', signal: controller.signal, headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers } });
    if (generation !== authGeneration) throw new Error('This session changed. Please try again.');
    if (response.status === 401 && !path.endsWith('/login')) { expire(); throw Object.assign(new Error('Your session expired. Sign in again; saved captures remain queued.'), { status: 401, code: null }); }
    if (!response.ok) {
      const messages = { 400: 'Please check the information and try again.', 401: 'That PIN was not accepted.', 403: 'Access was refused. Use the same-origin local application.', 404: 'This record is no longer available.', 409: 'The request conflicts with retained evidence.', 413: 'This request is too large.', 429: 'Too many attempts. Wait a moment before trying again.', 503: path === '/api/chat' ? 'Optional cloud chat is unavailable. Choose Local; capture and storage are unaffected.' : 'The local service is unavailable. Existing evidence has not been replaced.' };
      const refusal = response.status === 409 || response.status === 400 ? await refusalBody(response) : { detail: null, code: null };
      const message = (response.status === 409 && (refusal.detail || REFUSALS[refusal.code])) || messages[response.status] || `The request could not complete (HTTP ${response.status}). Try again.`;
      throw Object.assign(new Error(message), { status: response.status, code: refusal.code });
    }
    return await response.json();
  } catch (error) {
    if (error.name === 'AbortError' || error instanceof TypeError) throw Object.assign(new Error('The local service could not be reached. Check the connection and try again.'), { status: 0, code: null });
    throw error;
  } finally { clearTimeout(timer); }
}
// A coverage gap entry in the Camera view's log (camera gaps and, CP4, a queued
// capture the server refused for good).
function logGap(line) {
  const li = node('li', line);
  $('coverage-log').prepend(li); while ($('coverage-log').children.length > 12) $('coverage-log').lastElementChild.remove();
}
const queue = new RetryQueue({
  notify: message => text($('queue-status'), message),
  unauthorized: () => expire(),
  retained: result => {
    if (!authenticated) return;
    const ack = result.ack;
    notice(ack.status === 'conflict' ? 'The server retained a conflicting packet for review; it was not accepted as a new interpretation.' : `Capture durably retained. Processing: ${result.processing?.status || 'pending'}. Retention does not mean an item was recognized.`);
    if (currentView === 'items') void refreshItems();
  },
  dropped: (record, reason) => {
    logGap(`A saved capture was ${reason}; the server will not keep it, so it was removed from this browser and counts as a coverage gap.`);
    if (authenticated) notice(`One saved capture was ${reason} and was dropped. Nothing from before the erasure is re-added.`);
  },
  consentRequired: () => { if (authenticated) void refreshConsent(); }
});
function resetPrivateUI() {
  authGeneration++; catalogueSequence++; detailSequence++;
  authenticated = false; queue.setAuthenticated(false);
  if (camera) void camera.stop('Signed out or session expired');
  closeConfirm(); $('item-dialog').close(); selectedId = null; detailItem = null;
  $('detail-body').replaceChildren(); $('history').replaceChildren(); $('evidence-list').replaceChildren(); $('link-target').replaceChildren(); $('item-name').value = '';
  $('link-item').disabled = true; $('erase-item').disabled = true;
  $('items-grid').replaceChildren(); $('conversation').replaceChildren(); $('chat-text').value = ''; $('search').value = '';
  $('capabilities').replaceChildren(); lastCatalogue = ''; catalogueNames.clear(); $('app').hidden = true; $('logout').hidden = true; $('signin').hidden = false;
  $('cloud-option').disabled = true; $('chat-mode').value = 'local'; notice('');
  resetPrivacyUI();
}
// CP4: nothing from the Privacy view or the consent gate survives a sign-out.
function resetPrivacyUI() {
  privacySequence++; consent = null; consentOk = false; retention = null;
  renderConsent();
  for (const field of RETENTION_FIELDS) { $(field.input).value = ''; $(field.input).disabled = true; }
  $('retention-save').disabled = true; text($('retention-consent'), 'unknown'); text($('retention-status'), 'Loading retention settings…');
  for (const key of COUNT_KEYS) text($('retention-counts').querySelector(`[data-count="${key}"]`), '–');
  text($('counts-status'), 'Loading counts…'); text($('idle-counters'), 'This browser: idle stills: 0 sent · 0 dropped');
  $('erase-all-phrase').value = ''; $('erase-all-pin').value = ''; $('erase-all').disabled = true;
  text($('erase-all-status'), 'The button enables once the exact phrase and your PIN are entered. The PIN is sent with the request and never stored in this page.');
  privacyNotice('');
}
function privacyNotice(message) { text($('privacy-status'), message); $('privacy-status').hidden = !message; }
function expire() {
  if (!authenticated) return;
  resetPrivateUI(); text($('auth-status'), 'Your session expired. Sign in again. Local queued captures were not deleted.'); $('pin').focus();
}
async function setupStorage() {
  if (storageReady) return;
  try {
    await queue.open(); storageReady = true;
    text($('storage-status'), 'Local retry storage ready · up to 32 episodes / 48 MiB. It contains sensitive evidence. Storage is not a backup.');
    camera = new ManualCamera({ video: $('preview'), queue,
      status: message => { text($('camera-status'), message); text($('episode-status'), message); },
      changed: state => {
        cameraState = state;
        $('camera-start').disabled = !authenticated || !consentOk || state.running || state.starting || state.saving || state.unsaved;
        $('camera-pause').disabled = !state.running; $('camera-stop').disabled = !(state.running || state.starting);
        $('mark-before').disabled = !state.running || state.episode || state.saving || state.unsaved;
        $('mark-rest').disabled = !state.running || !state.episode || state.saving || state.automaticEpisode;
        $('mark-cancel').disabled = !state.episode || state.saving;
        // CP4: the idle keyframe counter sits in the summary while automatic capture
        // runs, and stays once any idle still was sent or dropped in this session.
        const idle = state.idle || { sent: 0, dropped: 0 };
        const idleText = state.automaticActive || idle.sent || idle.dropped ? ` · ${idleSummary(idle)}` : '';
        text($('camera-summary'), state.running ? `Camera on · ${state.automaticActive ? 'automatic' : 'manual'} mode${state.episode ? ' · episode in progress' : ''}${idleText}` : state.starting ? 'Waiting for camera permission' : `Camera off${idle.sent || idle.dropped ? idleText : ''}`);
        text($('idle-counters'), `This browser: ${idleSummary(idle)}`);
        $('preview-placeholder').hidden = state.running;
        renderAutomatic(state);
      },
      gap: gap => logGap(`${gap.reason} · ${((gap.t_to_ms - gap.t_from_ms) / 1000).toFixed(1)} seconds recorded as a gap.`),
      // The idle post shares api()'s session handling (401 expires the session) but
      // reports the outcome instead of throwing: the camera only counts it.
      postIdle: async body => {
        try { const result = await api('/api/idle', { method: 'POST', body }); return { ok: true, status: 200, code: null, retained: result && result.retained === true }; }
        catch (error) { return { ok: false, status: error.status || 0, code: error.code || null, retained: false }; }
      },
      consentRequired: () => { if (authenticated) { void refreshConsent(); void camera?.stop('Consent acknowledgement required'); } },
      unauthorized: () => expire()
    });
    if (handPolicy) camera.setServerPolicy(handPolicy);
    camera.update();
  } catch (error) {
    text($('storage-status'), `${error.message} Capture is disabled; local queries and browsing still work.`); $('camera-start').disabled = true;
    renderAutomatic({ automatic: false, saving: false, adapter: { enabled: false, reason: 'capture is disabled in this browser, so no hand model was loaded.', version: null } });
  }
}
// Automatic capture UI: the toggle is usable only when the worker reported a ready
// hand model and the server does not deny the capability; otherwise it is disabled
// with the reason. Everything shown is the camera's reported state, never a promise.
function renderAutomatic(state) {
  const adapter = state.adapter || { enabled: false, reason: 'Checking whether a hand model is provisioned on this server.', version: null };
  const on = adapter.enabled && state.automatic;
  $('automatic-toggle').disabled = !adapter.enabled || state.saving;
  $('automatic-toggle').checked = on;
  text($('automatic-description'), !adapter.enabled
    ? `Unavailable: ${adapter.reason || 'no hand model is available.'} Manual marking still works.`
    : on ? `On · hand model ${adapter.version}. An episode starts when a hand looks busy and ends when the item rests; it is saved locally before upload. Turn off to return to manual marks only.`
      : `Off · hand model ${adapter.version} is loaded from this server. Turn on to let Pam pin episodes automatically; manual marks keep working.`);
  text($('camera-mode-badge'), on ? 'Automatic capture mode' : 'Manual mark mode');
  text($('automatic-notice'), adapter.enabled
    ? `A hand model is provisioned on this server (hand model ${adapter.version}). Automatic capture is ${on ? 'on: a busy-hand heuristic, not verified recognition.' : 'off until you turn it on below.'} Manual marking remains available.`
    : `Automatic hand recognition is unavailable: ${adapter.reason || 'no hand model is available.'} Manual marking is a first checkpoint, not automatic daily tracking.`);
}
$('automatic-toggle').addEventListener('change', () => {
  const wanted = $('automatic-toggle').checked;
  if (camera && authenticated) camera.setAutomatic(wanted); else $('automatic-toggle').checked = false;
});
async function signedIn() {
  authenticated = true; authGeneration++; $('signin').hidden = true; $('app').hidden = false; $('logout').hidden = false; $('pin').value = '';
  const generation = authGeneration;
  showView(currentView, false);
  renderConsent();
  void refreshHealth(); void refreshItems(); void refreshConsent();
  await setupStorage();
  if (authenticated && generation === authGeneration) { queue.setAuthenticated(true); camera?.update(); }
}
// --- CP4 consent gate --------------------------------------------------------------
// The disclosure text comes from the server and is rendered verbatim (textContent);
// until GET /api/consent says ok the camera cannot start, manually or automatically.
// A failed request shows the fallback sentence and keeps the camera off.
function renderConsent() {
  const ok = consentOk;
  const disclosure = consent && typeof consent.disclosure_text === 'string' && consent.disclosure_text.trim() ? consent.disclosure_text.trim().slice(0, 4000) : null;
  const version = consent && typeof consent.required_version === 'string' ? consent.required_version : null;
  const canAcknowledge = authenticated && !ok && !!disclosure && !!version && !consentBusy;
  $('consent-gate').hidden = ok;
  text($('consent-text'), disclosure || (consent === null ? 'Checking the camera disclosure…' : CONSENT_FALLBACK));
  text($('consent-status'), ok ? '' : (disclosure ? 'The camera stays off until this disclosure is acknowledged on this server.' : (consent === null ? 'Waiting for the local service.' : 'The camera stays off because the disclosure could not be loaded. Refresh to try again.')));
  $('consent-acknowledge').disabled = !canAcknowledge;
  text($('privacy-disclosure'), disclosure || (consent === null ? 'Checking the camera disclosure…' : CONSENT_FALLBACK));
  const acknowledged = consent && typeof consent.acknowledged_version === 'string' ? consent.acknowledged_version : null;
  text($('privacy-consent-state'), consent === null ? 'Checking the acknowledgement state…'
    : ok ? `Acknowledged: version ${acknowledged || version || 'unknown'}. The camera may start.`
      : disclosure ? `Not acknowledged${acknowledged ? ` (version ${acknowledged} was acknowledged; version ${version} is now required)` : ''}. The camera stays off until "I understand" is chosen.`
        : CONSENT_FALLBACK);
  $('privacy-acknowledge').disabled = !canAcknowledge;
  if (cameraState) $('camera-start').disabled = !authenticated || !ok || cameraState.running || cameraState.starting || cameraState.saving || cameraState.unsaved;
  else $('camera-start').disabled = true;
}
function applyConsent(result) {
  consent = result && typeof result === 'object' ? result : {};
  consentOk = consent.ok === true && typeof consent.required_version === 'string' && consent.acknowledged_version === consent.required_version;
  renderConsent();
}
async function refreshConsent() {
  if (!authenticated) return;
  const generation = authGeneration;
  try {
    const result = await api('/api/consent');
    if (!authenticated || generation !== authGeneration) return;
    applyConsent(result);
  } catch (error) {
    if (!authenticated || generation !== authGeneration) return;
    applyConsent({});
    if (camera?.running || camera?.starting) void camera.stop('Consent state could not be confirmed');
    if (currentView === 'camera' || currentView === 'privacy') notice(`${CONSENT_FALLBACK} ${error.message}`);
  }
}
async function acknowledgeConsent(opener) {
  if (!authenticated || consentBusy || consentOk) return;
  const version = consent && typeof consent.required_version === 'string' ? consent.required_version : null;
  if (!version) return;
  const generation = authGeneration; consentBusy = true; renderConsent();
  text($('consent-status'), 'Recording your acknowledgement…'); text($('privacy-consent-state'), 'Recording your acknowledgement…');
  try {
    const result = await api('/api/consent', { method: 'POST', body: JSON.stringify({ acknowledge: version }) });
    if (!authenticated || generation !== authGeneration) return;
    consentBusy = false; applyConsent(result);
    if (!consentOk) await refreshConsent();
    if (consentOk) notice(`Disclosure version ${version} acknowledged. The camera can now be started from the Camera view.`);
  } catch (error) {
    if (!authenticated || generation !== authGeneration) return;
    consentBusy = false; renderConsent();
    text($('consent-status'), error.message); text($('privacy-consent-state'), error.message);
  } finally {
    consentBusy = false;
    if (authenticated && generation === authGeneration && opener?.isConnected && !opener.disabled) opener.focus({ preventScroll: true });
  }
}
$('consent-acknowledge').addEventListener('click', () => { void acknowledgeConsent($('consent-acknowledge')); });
$('privacy-acknowledge').addEventListener('click', () => { void acknowledgeConsent($('privacy-acknowledge')); });
async function session() {
  $('session-retry').hidden = true;
  try {
    const result = await api('/api/auth/session');
    $('login').disabled = !result.configured; $('pin').disabled = !result.configured;
    if (result.authenticated) await signedIn();
    else { text($('auth-status'), result.configured ? 'Use the PIN configured for this local service.' : 'Setup required: no access PIN is configured on the local service. Access is closed until an administrator configures it.'); $('session-retry').hidden = result.configured; }
  } catch (error) { text($('auth-status'), error.message); $('session-retry').hidden = false; }
}
$('login-form').addEventListener('submit', async event => {
  event.preventDefault(); $('login').disabled = true; text($('auth-status'), 'Signing in…');
  try { await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ pin: $('pin').value }) }); await signedIn(); $('chat-title').focus(); }
  catch (error) { text($('auth-status'), error.message); $('pin').value = ''; $('pin').focus(); }
  finally { $('login').disabled = false; }
});
$('session-retry').addEventListener('click', session);
$('logout').addEventListener('click', async () => {
  $('logout').disabled = true; queue.setAuthenticated(false); await camera?.stop('Signed out by user');
  try { await api('/api/auth/logout', { method: 'POST' }); resetPrivateUI(); text($('auth-status'), 'Signed out. Server session revoked. Unsynced captures remain on this trusted browser.'); $('pin').focus(); }
  catch (error) { notice(`Sign-out was not confirmed by the server. ${error.message} Try signing out again.`); }
  finally { $('logout').disabled = false; }
});
function showView(view, focus = true) {
  currentView = view;
  for (const button of document.querySelectorAll('[data-view]')) {
    if (button.dataset.view === view) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
    $(`view-${button.dataset.view}`).hidden = button.dataset.view !== view;
  }
  if (focus) $(`${view}-title`).focus();
  if (view === 'items' && authenticated) void refreshItems();
  if (view === 'privacy' && authenticated) void refreshPrivacy();
}
for (const button of document.querySelectorAll('[data-view]')) button.addEventListener('click', () => showView(button.dataset.view));
// --- CP4 Privacy view: retention windows, live counts, erase everything ------------------
// GET /api/retention answers {retention: {...}, counts: {...}}; an older shape with
// the row's fields and counts at the top level is read the same way.
function retentionRow(result) {
  const row = result && typeof result.retention === 'object' && result.retention ? result.retention : result;
  return row && typeof row === 'object' ? row : {};
}
function retentionCounts(result) {
  const counts = result && typeof result.counts === 'object' && result.counts ? result.counts : result;
  return counts && typeof counts === 'object' ? counts : {};
}
function renderRetention(row) {
  retention = row;
  for (const field of RETENTION_FIELDS) {
    const value = row[field.key];
    $(field.input).value = Number.isSafeInteger(value) ? String(value) : '';
    $(field.input).disabled = false;
  }
  $('retention-save').disabled = false;
  text($('retention-consent'), typeof row.consent_version === 'string' && row.consent_version ? row.consent_version : (consent && typeof consent.required_version === 'string' ? consent.required_version : 'unknown'));
}
function renderCounts(counts) {
  for (const key of COUNT_KEYS) {
    const value = counts[key];
    text($('retention-counts').querySelector(`[data-count="${key}"]`), Number.isSafeInteger(value) && value >= 0 ? String(value) : '–');
  }
}
// Load the retention row and the live counts. `saved` names a status line to show
// in place of "loaded" (after a successful PUT the message stays "saved").
async function refreshPrivacy(saved = null) {
  if (!authenticated) return;
  const sequence = ++privacySequence, generation = authGeneration;
  if (!saved) text($('retention-status'), 'Loading retention settings…');
  text($('counts-status'), 'Loading counts…');
  try {
    const result = await api('/api/retention');
    if (!authenticated || generation !== authGeneration || sequence !== privacySequence) return;
    renderRetention(retentionRow(result)); renderCounts(retentionCounts(result));
    const updated = retention && Number.isSafeInteger(retention.updated_ms) && retention.updated_ms > 0 ? ` Last changed ${dateLabel(retention.updated_ms)}.` : '';
    text($('retention-status'), `${saved || 'Current retention settings loaded.'}${updated}`);
    text($('counts-status'), `Counts read ${new Date().toLocaleTimeString()}. Expiry runs on the local service, not in this browser.`);
  } catch (error) {
    if (!authenticated || generation !== authGeneration || sequence !== privacySequence) return;
    text($('retention-status'), `${saved ? `${saved} ` : ''}${error.message} The settings shown may be stale.`); text($('counts-status'), error.message);
  }
}
$('refresh-privacy').addEventListener('click', () => { void refreshPrivacy(); void refreshConsent(); });
// Validate the three windows in the page: a whole number within the server's range.
// Out-of-range values are never sent. Returns {changes} or {error}.
function retentionChanges() {
  const changes = {};
  for (const field of RETENTION_FIELDS) {
    const raw = $(field.input).value.trim();
    const value = /^\d{1,4}$/.test(raw) ? Number(raw) : NaN;
    if (!Number.isSafeInteger(value) || value < field.min || value > field.max) return { error: `${field.label} must be a whole number of ${field.unit} between ${field.min} and ${field.max}. Nothing was changed.`, field };
    if (!retention || retention[field.key] !== value) changes[field.key] = value;
  }
  return { changes };
}
$('retention-form').addEventListener('submit', event => {
  event.preventDefault();
  if (!authenticated || !retention) { text($('retention-status'), 'Retention settings have not loaded yet. Refresh and try again.'); return; }
  const { changes, error, field } = retentionChanges();
  if (error) { text($('retention-status'), error); $(field.input).focus(); return; }
  const keys = Object.keys(changes);
  if (!keys.length) { text($('retention-status'), 'No change to save: the settings already match.'); return; }
  const described = keys.map(key => { const field = RETENTION_FIELDS.find(entry => entry.key === key); return `${field.label.toLowerCase()} to ${changes[key]} ${field.unit}`; }).join(', ');
  openConfirm({ title: 'Change retention windows', opener: $('retention-save'),
    sentence: `Set ${described}. A shorter window removes older photos, idle stills or hand positions the next time the local service runs its retention pass; a longer one keeps them longer. The change is recorded in the audit log.`,
    run: () => saveRetention(changes) });
});
async function saveRetention(changes) {
  const sequence = ++privacySequence, generation = authGeneration;
  $('retention-save').disabled = true; text($('retention-status'), 'Saving retention settings…');
  try {
    const result = await api('/api/retention', { method: 'PUT', body: JSON.stringify(changes) });
    if (!authenticated || generation !== authGeneration || sequence !== privacySequence) return;
    const row = retentionRow(result);
    renderRetention(RETENTION_FIELDS.every(field => Number.isSafeInteger(row[field.key])) ? row : { ...retention, ...changes });
    text($('retention-status'), 'Retention settings saved on the local service.');
    void refreshPrivacy('Retention settings saved on the local service.');
  } catch (error) {
    if (!authenticated || generation !== authGeneration || sequence !== privacySequence) return;
    $('retention-save').disabled = false; text($('retention-status'), `${error.message} The settings were not changed.`);
  }
}
// Erase everything: the button enables only when the phrase is exactly
// ERASE_ALL_PHRASE and a PIN is present; the PIN is read when the request is built
// and cleared right after, never kept.
function eraseAllReady() {
  $('erase-all').disabled = !authenticated || eraseBusy || $('erase-all-phrase').value !== ERASE_ALL_PHRASE || !$('erase-all-pin').value;
}
$('erase-all-phrase').addEventListener('input', eraseAllReady);
$('erase-all-pin').addEventListener('input', eraseAllReady);
$('erase-all-form').addEventListener('submit', event => {
  event.preventDefault();
  if (!authenticated || eraseBusy || $('erase-all-phrase').value !== ERASE_ALL_PHRASE || !$('erase-all-pin').value) { eraseAllReady(); return; }
  openConfirm({ title: 'Erase everything', opener: $('erase-all'),
    sentence: 'Every stored memory, photo, idle still, hand position, name, correction and appearance record will be removed from the local database, and the captures waiting in this browser will be discarded. This cannot be undone. Traces may remain on the device or in backups.',
    run: () => eraseEverything() });
});
async function eraseEverything() {
  if (!authenticated || eraseBusy) return;
  const generation = authGeneration; eraseBusy = true; eraseAllReady();
  text($('erase-all-status'), 'Erasing everything on the local service…'); privacyNotice('');
  try {
    // The camera stops first: anything captured from now on carries a wall time
    // after the erasure, and a running episode would otherwise be refused later.
    if (camera && (camera.running || camera.starting)) await camera.stop('Stopped for erasure');
    const pin = $('erase-all-pin').value; $('erase-all-pin').value = '';
    const report = await api('/api/erase-all', { method: 'POST', body: JSON.stringify({ confirm: ERASE_ALL_PHRASE, pin }) });
    if (!authenticated || generation !== authGeneration) return;
    $('erase-all-phrase').value = '';
    // The local mirror and anything unsaved in the page go too: a capture from
    // before the erasure must never be re-added.
    let cleared = 0;
    try { camera?.discardUnsaved(); cleared = storageReady ? await queue.clear() : 0; }
    catch (error) { logGap(`Saved captures could not be cleared after the erasure: ${error.message}`); }
    lastCatalogue = ''; catalogueNames.clear(); $('items-grid').replaceChildren(); $('conversation').replaceChildren();
    if ($('item-dialog').open) $('item-dialog').close();
    text($('erase-all-status'), 'The button enables once the exact phrase and your PIN are entered. The PIN is sent with the request and never stored in this page.');
    privacyNotice(`${eraseReport(report)} ${cleared ? `${cleared} capture${cleared === 1 ? '' : 's'} waiting in this browser ${cleared === 1 ? 'was' : 'were'} discarded.` : 'No capture was waiting in this browser.'} The chat log on this page was cleared. Traces may remain on the device or in backups.`);
    void refreshItems(); void refreshPrivacy(); void refreshHealth();
  } catch (error) {
    if (!authenticated || generation !== authGeneration) return;
    text($('erase-all-status'), error.message);
  } finally {
    eraseBusy = false;
    if (authenticated && generation === authGeneration) {
      eraseAllReady();
      if (currentView === 'privacy') ($('erase-all').disabled ? $('erase-all-phrase') : $('erase-all')).focus({ preventScroll: true });
    }
  }
}
// The server's erase report in plain words: counts only, never ids or names.
function eraseReport(report) {
  const counts = report && typeof report.counts === 'object' && report.counts ? report.counts : {};
  const parts = [];
  for (const [key, label] of [['items', 'item'], ['observations', 'observation'], ['episodes', 'episode'], ['idle_frames', 'idle still'], ['appearance_signatures', 'appearance record'], ['names', 'name'], ['corrections', 'correction'], ['legacy_rows', 'row from the earlier app']]) {
    const value = counts[key];
    if (Number.isSafeInteger(value) && value > 0) parts.push(`${value} ${label}${value === 1 ? '' : 's'}`);
  }
  const swap = report && report.swap === 'replaced' ? ' The database file was then rebuilt into a fresh file, which reduces leftover residue in it.'
    : report && report.swap === 'in_place' ? ' The database file was then compacted in place, which reduces leftover residue in it.' : '';
  return `Erased on the local service${parts.length ? `: ${parts.join(', ')}` : ''}.${swap}`;
}
function renderCapabilities(capabilities) {
  $('capabilities').replaceChildren();
  for (const cap of Array.isArray(capabilities) ? capabilities : []) $('capabilities').append(node('li', `${cap.name || 'Capability'}: ${cap.enabled ? 'available' : 'unavailable'}${cap.reason ? ` — ${cap.reason}` : ''}`));
  const hand = (Array.isArray(capabilities) ? capabilities : []).find(cap => cap && cap.name === HAND_CAPABILITY);
  if (hand && typeof hand === 'object') {
    handPolicy = { enabled: hand.enabled === true, reason: typeof hand.reason === 'string' ? hand.reason : null };
    camera?.setServerPolicy(handPolicy);
  }
}
async function refreshHealth() {
  try {
    const health = await api('/api/health'); if (!authenticated) return;
    const cloud = health.chat?.configured === true && health.chat?.enabled === true;
    $('cloud-option').disabled = !cloud; text($('cloud-option'), cloud ? 'Cloud · optional, explicitly requested' : 'Cloud · unavailable');
    if (!cloud) $('chat-mode').value = 'local';
    text($('cloud-status'), cloud ? 'Optional cloud chat is configured with a server policy. It is used only when you select Cloud and send a question. Local evidence certainty still applies.' : 'Optional cloud chat is unavailable. A configured provider and bounded policy are required. Local answers and capture need no chatbot key.');
    renderCapabilities(health.capabilities);
  } catch (error) { if (authenticated) notice(error.message); }
}
async function refreshItems() {
  if (!authenticated) return;
  const sequence = ++catalogueSequence, query = $('search').value.trim();
  try {
    const result = await api(`/api/items?q=${encodeURIComponent(query)}&limit=50`);
    if (!authenticated || sequence !== catalogueSequence) return;
    const items = Array.isArray(result.items) ? result.items : [];
    for (const item of items) if (item && typeof item.item_id === 'string' && typeof item.name === 'string') catalogueNames.set(item.item_id, item.name);
    const signature = JSON.stringify(items);
    if (signature !== lastCatalogue) {
      const active = document.activeElement;
      const focusId = $('items-grid').contains(active) ? active.dataset.itemId : null;
      $('items-grid').replaceChildren(...items.map(itemCard));
      if (!items.length) $('items-grid').append(node('p', query ? 'No stored items match this search. Try a different name.' : 'No stored items yet. Captures that contain only context will not appear as recognized objects.', 'empty'));
      if (focusId) [...$('items-grid').querySelectorAll('button')].find(button => button.dataset.itemId === focusId)?.focus({ preventScroll: true });
      lastCatalogue = signature;
    }
    text($('items-status'), `${items.length}${items.length === 50 ? ' (up to 50 shown; search to narrow)' : ''} stored item${items.length === 1 ? '' : 's'}${items.some(item => item.index_pending) ? ' · processing pending' : ''}. Updated ${new Date().toLocaleTimeString()}.`);
    renderCapabilities(result.capabilities);
  } catch (error) { if (authenticated && sequence === catalogueSequence) text($('items-status'), `${error.message} Previously displayed items may be stale.`); }
}
$('search-form').addEventListener('submit', event => { event.preventDefault(); void refreshItems(); });
$('refresh-items').addEventListener('click', () => { void refreshItems(); void refreshHealth(); });
const OUTCOMES = { placed_on_surface: 'placed on a surface', picked_up: 'picked up', sighted: 'sighted', uncertain: 'outcome uncertain' };
// CP3 evidence row: one observation of the item with its own photo (the recorded
// region outlined), time, outcome, location and identity, plus "Not this one".
function evidenceRow(item, observation, count) {
  const li = node('li', null, 'evidence-row'); li.dataset.observationId = observation.observation_id;
  const when = dateLabel(observation.observed_at_ms);
  const url = safeObservationImageURL(item.item_id, observation);
  const verified = observation.identity_status === 'trusted';
  const idle = observation.source === IDLE_SOURCE;
  li.append(url
    ? evidenceFigure({ url, box: targetBox(observation), verified, maxHeight: 200, lazy: false, alt: `Photo recorded ${when}; not a live view.${verified ? ' The recorded item is outlined.' : ' The outlined region is where a change was recorded; the identity is unverified.'}${idle ? ` ${IDLE_SOURCE_TEXT}.` : ''}` })
    : node('p', 'No photo is available for this observation.', 'muted'));
  const body = node('div', null, 'evidence-body');
  body.append(node('p', `${when} · ${OUTCOMES[observation.outcome] || observation.outcome || 'outcome not recorded'}`, 'evidence-when'));
  // CP4 source labels: a promoted idle still (Oversight F3) or a migrated v1 row.
  if (idle) body.append(idleBadge());
  else if (observation.source === 'legacy_v1') body.append(node('p', LEGACY_SOURCE_TEXT, 'badge badge-legacy'));
  body.append(node('p', observation.location_text || 'No supported location is recorded for this observation.'));
  const candidates = Array.isArray(observation.candidates) ? observation.candidates.length : 0;
  body.append(node('p', `Identity: ${observation.identity_status || 'unknown'}${candidates ? ` · could also be ${candidates} other stored item${candidates === 1 ? '' : 's'}` : ''}${observation.embedded === false ? ' · no appearance record' : ''}`, 'muted'));
  const button = node('button', 'Not this one', 'secondary unlink-observation'); button.type = 'button'; button.dataset.observationId = observation.observation_id;
  if (count < 2) { button.disabled = true; button.dataset.lone = '1'; body.append(node('p', 'This is the only observation of this item, so there is nothing to separate it from.', 'muted')); }
  button.addEventListener('click', () => confirmUnlink(item, observation));
  body.append(button); li.append(body);
  return li;
}
async function loadDetail(id, outcome = null) {
  const sequence = ++detailSequence; text($('detail-status'), 'Loading evidence and history…'); $('name-save').disabled = true; $('link-item').disabled = true; $('erase-item').disabled = true; detailItem = null;
  try {
    const [item, history, evidence] = await Promise.all([
      api(`/api/items/${encodeURIComponent(id)}`), api(`/api/items/${encodeURIComponent(id)}/history`),
      // The evidence list is CP3; an older server without the route still shows the rest.
      api(`/api/items/${encodeURIComponent(id)}/evidence`).catch(error => ({ error: error.message }))]);
    if (!authenticated || sequence !== detailSequence || selectedId !== id) return;
    detailItem = item;
    text($('detail-title'), item.name || 'Unnamed item'); $('detail-body').replaceChildren(image(item)); describe(item, $('detail-body'));
    $('item-name').value = item.name || ''; $('history').replaceChildren();
    const observations = Array.isArray(history.observations) ? history.observations : [];
    for (const observation of observations) {
      const li = node('li'); li.append(node('p', `${dateLabel(observation.observed_at_ms)} · ${observation.outcome || 'Outcome not recorded'}`));
      li.append(node('p', observation.location_text || observation.location || 'Location unknown'));
      li.append(node('p', `Identity: ${observation.identity_state || observation.identity_status || 'unknown'} · Actor: ${observation.actor || 'unknown'}`, 'muted'));
      $('history').append(li);
    }
    const rows = Array.isArray(evidence.observations) ? evidence.observations.filter(row => row && typeof row.observation_id === 'string').slice(0, 64) : [];
    $('evidence-list').replaceChildren(...rows.map(row => evidenceRow(item, row, rows.length)));
    if (!rows.length) $('evidence-list').append(node('li', evidence.error ? `The evidence list is unavailable: ${evidence.error}` : 'No recorded observations are available for this item.', 'muted'));
    text($('detail-status'), `${outcome ? `${outcome} ` : ''}${observations.length || rows.length ? 'Evidence loaded. This is recorded history, not a live location.' : 'No recorded observations are available.'}`);
    $('name-save').disabled = false; $('link-item').disabled = false; $('detail-refresh').disabled = false; $('erase-item').disabled = false;
  } catch (error) { if (authenticated && sequence === detailSequence) text($('detail-status'), error.message); }
}
function openDetail(id, trigger) {
  selectedId = id; detailTrigger = trigger; detailItem = null; $('detail-body').replaceChildren(); $('history').replaceChildren(); $('evidence-list').replaceChildren(); $('item-name').value = '';
  $('link-item').disabled = true; $('erase-item').disabled = true; $('detail-refresh').disabled = false; text($('detail-title'), 'Item details'); $('item-dialog').showModal(); void loadDetail(id);
}
// --- CP3 corrections: every correction is confirmed in #confirm-dialog first -------------
// openConfirm shows one plain-language sentence (and, for a link, the target
// select); #confirm-ok runs the action, #confirm-cancel or Escape discards it.
let confirmOpener = null;
function openConfirm({ title, sentence, link = false, run, opener = document.activeElement }) {
  text($('confirm-title'), title); text($('confirm-text'), sentence);
  $('confirm-link-field').hidden = !link; pendingConfirm = run; confirmOpener = opener;
  $('confirm-dialog').showModal();
  (link ? $('link-target') : $('confirm-ok')).focus();
}
function closeConfirm() { pendingConfirm = null; if ($('confirm-dialog').open) $('confirm-dialog').close(); }
$('confirm-cancel').addEventListener('click', closeConfirm);
$('confirm-dialog').addEventListener('close', () => {
  pendingConfirm = null;
  // A nested modal does not hand focus back by itself: return it to the control
  // that opened the confirmation (or the Evidence heading once that control is gone).
  const opener = confirmOpener; confirmOpener = null;
  if (document.activeElement !== document.body && !$('confirm-dialog').contains(document.activeElement)) return;
  const usable = opener?.isConnected && !opener.disabled;
  if ($('item-dialog').open) { (usable && $('item-dialog').contains(opener) ? opener : $('evidence-title')).focus({ preventScroll: true }); return; }
  // CP4: a confirmation opened from a view (retention save, erase everything)
  // returns focus to its own control.
  if (usable && !$('item-dialog').contains(opener)) opener.focus({ preventScroll: true });
});
$('confirm-ok').addEventListener('click', () => { const run = pendingConfirm; closeConfirm(); if (run) void run(); });
function correctionBusy(busy) {
  for (const button of [$('link-item'), $('name-save'), $('detail-refresh'), $('erase-item')]) button.disabled = busy;
  for (const button of $('evidence-list').querySelectorAll('.unlink-observation')) button.disabled = busy || button.dataset.lone === '1';
}
// --- CP4 erase this item: confirmed with the item's name, POST .../erase with the
// item id as the confirmation, then the dialog closes and the catalogue refreshes.
$('erase-item').addEventListener('click', () => {
  const id = selectedId, item = detailItem; if (!id) return;
  if (!item || item.item_id !== id) { text($('detail-status'), 'Refresh the details before erasing this item.'); return; }
  const name = item.name || 'this unnamed item';
  openConfirm({ title: 'Erase this item', opener: $('erase-item'),
    sentence: `Erase "${name}" from the local database: its photos, observations, name, corrections and appearance record, and those of any item Pam cannot separate from it. This cannot be undone. Traces may remain on the device or in backups.`,
    run: () => eraseItem(id, name) });
});
async function eraseItem(id, name) {
  if (!authenticated || selectedId !== id) return;
  const sequence = ++detailSequence, generation = authGeneration; correctionBusy(true); text($('detail-status'), 'Loading: erasing this item on the local service…');
  try {
    const report = await api(`/api/items/${encodeURIComponent(id)}/erase`, { method: 'POST', body: JSON.stringify({ confirm: id }) });
    if (!authenticated || generation !== authGeneration || sequence !== detailSequence || selectedId !== id) return;
    const affected = Number.isSafeInteger(report?.affected_items) ? report.affected_items : null;
    lastCatalogue = ''; catalogueNames.delete(id);
    if ($('item-dialog').open) $('item-dialog').close();
    notice(`Erased "${name}"${affected && affected > 1 ? ` and ${affected - 1} related item${affected === 2 ? '' : 's'}` : ''} from the local database. Traces may remain on the device or in backups.`);
    void refreshItems(); if (currentView === 'privacy') void refreshPrivacy();
  } catch (error) {
    if (!authenticated || generation !== authGeneration || sequence !== detailSequence || selectedId !== id) return;
    correctionBusy(false); text($('detail-status'), `${error.message} Nothing was erased.`); $('erase-item').focus({ preventScroll: true });
  }
}
// POST a correction for the item on show; on success reload the detail (which
// may now be a different item) and the catalogue; on refusal show the server's
// reason in #detail-status. The text while waiting says "Loading" so a reader
// can tell it from a result.
async function correct(path, body, { success, follow }) {
  const id = selectedId; if (!id) return;
  const sequence = ++detailSequence; correctionBusy(true); text($('detail-status'), 'Loading: checking this correction with the local service…');
  try {
    const item = await api(path, { method: 'POST', body: JSON.stringify(body) });
    if (!authenticated || sequence !== detailSequence || selectedId !== id) return;
    const next = follow && item && typeof item.item_id === 'string' ? item.item_id : id;
    selectedId = next;
    await loadDetail(next, success(item));
    if (!authenticated || selectedId !== next) return;
    correctionBusy(false); $('evidence-title').focus({ preventScroll: true }); void refreshItems();
  } catch (error) {
    if (!authenticated || sequence !== detailSequence || selectedId !== id) return;
    text($('detail-status'), error.message); correctionBusy(false); $('evidence-title').focus({ preventScroll: true });
  }
}
function confirmUnlink(item, observation) {
  if (!selectedId || selectedId !== item.item_id) return;
  const name = item.name || 'this item';
  openConfirm({ title: 'Not this one',
    sentence: `Tell Pam that the photo recorded ${dateLabel(observation.observed_at_ms)} does not show "${name}". That observation becomes a separate stored item, and Pam will keep the two apart from now on. Nothing is deleted.`,
    run: () => correct(`/api/items/${encodeURIComponent(item.item_id)}/observations/${encodeURIComponent(observation.observation_id)}/unlink`, {},
      { success: created => `Moved that observation to a new stored item${created && created.name ? ` ("${created.name}")` : ''}; it is no longer evidence for this item.` }) });
}
$('link-item').addEventListener('click', async () => {
  const id = selectedId, item = detailItem; if (!id) return;
  if (!item || item.item_id !== id) { text($('detail-status'), 'Refresh the details before linking this item.'); return; }
  const opener = $('link-item'); opener.disabled = true;
  try {
    // A fresh, unfiltered catalogue so the choice is not limited by the search box.
    const result = await api('/api/items?q=&limit=50');
    if (!authenticated || selectedId !== id) return;
    const lookalikes = new Set(Array.isArray(item.lookalikes) ? item.lookalikes : []);
    const others = (Array.isArray(result.items) ? result.items : []).filter(other => other && typeof other.item_id === 'string' && other.item_id !== id);
    others.sort((a, b) => Number(lookalikes.has(b.item_id)) - Number(lookalikes.has(a.item_id)));
    if (!others.length) { text($('detail-status'), 'There is no other stored item to link with.'); return; }
    $('link-target').replaceChildren(...others.map(other => {
      const option = node('option', `${other.name || 'Unnamed item'} · ${other.location_text || `location ${other.location_status || 'unknown'}`} · ${dateLabel(other.observed_at_ms)}${lookalikes.has(other.item_id) ? ' · looks alike' : ''}`);
      option.value = other.item_id; return option;
    }));
    openConfirm({ title: 'Same as another item', link: true, opener,
      // Oversight F1: say what the action does, never why a refusal might come
      // (a 409 shows the server's own reason verbatim).
      sentence: `Pam will treat "${item.name || 'this item'}" and the item you choose below as one item and combine their evidence. You can undo this by marking an observation "Not this one". Nothing is deleted.`,
      run: () => {
        const other = $('link-target').value;
        if (!other || other === selectedId) { text($('detail-status'), 'Choose a different stored item to link with.'); return; }
        return correct(`/api/items/${encodeURIComponent(selectedId)}/link`, { other_item_id: other },
          { follow: true, success: kept => `Linked: the two are now one stored item${kept && kept.name ? ` ("${kept.name}")` : ''}.` });
      } });
  } catch (error) { if (authenticated && selectedId === id) text($('detail-status'), error.message); }
  finally { if (selectedId === id && detailItem) $('link-item').disabled = false; }
});
$('detail-close').addEventListener('click', () => $('item-dialog').close());
$('item-dialog').addEventListener('close', () => {
  detailSequence++; selectedId = null; detailItem = null; closeConfirm();
  if (!authenticated) return;
  if (document.activeElement !== document.body && !$('item-dialog').contains(document.activeElement)) return;
  const replacement = detailTrigger?.isConnected ? detailTrigger : [...$('items-grid').querySelectorAll('button')].find(button => button.dataset.itemId === detailTrigger?.dataset.itemId);
  (replacement || $('items-title')).focus({ preventScroll: true });
});
$('detail-refresh').addEventListener('click', () => { if (selectedId) void loadDetail(selectedId); });
$('name-form').addEventListener('submit', async event => {
  event.preventDefault(); if (!selectedId) return;
  const id = selectedId, name = $('item-name').value.trim(); if (!name) return;
  $('name-save').disabled = true;
  try { await api(`/api/items/${encodeURIComponent(id)}/name`, { method: 'POST', body: JSON.stringify({ name }) }); if (selectedId === id) await loadDetail(id); void refreshItems(); }
  catch (error) { text($('detail-status'), error.message); }
  finally { $('name-save').disabled = false; }
});
function addMessage(role, message) {
  const entry = node('article', null, `message ${role}`); entry.append(node('p', role === 'user' ? 'You' : 'Pam', 'eyebrow'), node('p', message)); $('conversation').append(entry);
  while ($('conversation').children.length > 40) $('conversation').firstElementChild.remove();
  return entry;
}
// CP3 group answer: the lookalike members' photos side by side, each a button.
// Tapping one is the user's answer to "which one is yours": when the group names
// an unresolved observation the choice is recorded (assign) first, then the chat
// is re-asked with that member's item id (an exact-id question, the existing
// clarify mechanism). Selecting a member never upgrades its certainty.
function groupMember(member, state) {
  const button = node('button', null, 'group-member'); button.type = 'button'; button.dataset.itemId = member.item_id;
  const name = member.name || 'Unnamed item';
  const url = safeImageURL(member);
  if (url) { const img = node('img'); img.src = url; img.decoding = 'async'; img.alt = ''; button.append(img); }
  else button.append(node('span', 'No photo available', 'muted'));
  const meta = [member.location_text || (member.location_status ? `location ${member.location_status}` : null), dateLabel(member.observed_at_ms)].filter(Boolean).join(' · ');
  button.append(node('span', name, 'member-name'), node('span', meta, 'member-meta'));
  button.setAttribute('aria-label', `This one: ${name}, ${meta}`);
  button.addEventListener('click', () => chooseMember(member, state, button));
  return button;
}
async function chooseMember(member, state, button) {
  if (!authenticated || $('chat-send').disabled) return;
  const generation = authGeneration; let note = null;
  if (typeof state.unresolved === 'string' && state.unresolved) {
    $('chat-send').disabled = true; text($('chat-status'), 'Recording your choice…');
    try {
      await api(`/api/items/${encodeURIComponent(member.item_id)}/observations/${encodeURIComponent(state.unresolved)}/assign`, { method: 'POST', body: JSON.stringify({}) });
      if (!authenticated || generation !== authGeneration) return;
      state.unresolved = null; note = 'Your choice was recorded for that sighting.';
    } catch (error) {
      if (!authenticated || generation !== authGeneration) return;
      note = `Your choice could not be recorded: ${error.message} Asking about the item you chose anyway.`;
    } finally { $('chat-send').disabled = false; }
  }
  for (const other of button.parentElement?.querySelectorAll('.group-member') || []) other.setAttribute('aria-pressed', other === button ? 'true' : 'false');
  await ask(member.item_id, { display: `${member.name || 'Unnamed item'} — this one`, note });
}
// question is the text sent; options.display is what the user's bubble shows
// (a member tap sends the item id but reads as the chosen name); options.note
// is a muted line under it.
async function ask(question, options = {}) {
  if (!question.trim() || $('chat-send').disabled) return;
  $('chat-send').disabled = true; text($('chat-status'), 'Checking stored evidence…');
  const generation = authGeneration; const asked = addMessage('user', options.display || question);
  if (options.note) asked.append(node('p', options.note, 'muted'));
  try {
    const result = await api('/api/chat', { method: 'POST', body: JSON.stringify({ text: question, mode: $('chat-mode').value }) });
    if (!authenticated || generation !== authGeneration) return;
    const entry = addMessage('assistant', result.text || 'No answer is available from the stored evidence.');
    entry.append(node('p', `Answer type: ${result.shape || 'unknown'}${result.index_pending ? ' · processing pending' : ''}`, 'muted'));
    if (result.shape === 'group') {
      entry.append(node('p', "I can't tell these apart — which one is yours? Tap the photo of your item.", 'group-prompt'));
      const state = { unresolved: typeof result.unresolved_observation_id === 'string' ? result.unresolved_observation_id : null };
      const members = node('div', null, 'group-members'); members.setAttribute('role', 'group'); members.setAttribute('aria-label', 'Items that look alike; choose yours');
      for (const member of (Array.isArray(result.members) ? result.members : []).filter(member => member && typeof member.item_id === 'string').slice(0, 8)) members.append(groupMember(member, state));
      entry.append(members);
    } else if (result.shape !== 'abstain' && Array.isArray(result.members) && result.members.length) {
      const members = node('div', null, 'items-grid'); for (const item of result.members.slice(0, 8)) members.append(itemCard(item)); entry.append(members);
    }
    if (result.shape === 'clarify') {
      if (result.question) entry.append(node('p', result.question));
      for (const option of (Array.isArray(result.options) ? result.options.slice(0, 8) : [])) {
        const value = typeof option === 'string' ? option : option.name || option.text || option.label;
        if (typeof value !== 'string') continue;
        const button = node('button', value, 'secondary'); button.addEventListener('click', () => { $('chat-text').value = value.slice(0, 2000); $('chat-text').focus(); }); entry.append(button);
      }
    }
    text($('chat-status'), 'Answer received.');
  } catch (error) { if (authenticated && generation === authGeneration) text($('chat-status'), error.message); }
  finally { $('chat-send').disabled = false; }
}
$('chat-form').addEventListener('submit', event => { event.preventDefault(); void ask($('chat-text').value.trim()); });
async function cameraAction(action) { try { if (camera && authenticated) await action(camera); } catch (error) { text($('camera-status'), error.message); } }
$('camera-start').disabled = true;
// CP4: the consent gate is checked at the click as well as in the button state,
// so a stale enabled button can never start capture before the acknowledgement.
$('camera-start').addEventListener('click', () => cameraAction(camera => {
  if (!consentOk) throw new Error('The camera disclosure must be acknowledged before the camera can start. Choose "I understand" above or in the Privacy view.');
  return camera.start();
}));
$('camera-pause').addEventListener('click', () => cameraAction(camera => camera.stop('Paused by user')));
$('camera-stop').addEventListener('click', () => cameraAction(camera => camera.stop('Stopped by user')));
$('mark-before').addEventListener('click', () => cameraAction(camera => camera.before()));
$('mark-rest').addEventListener('click', () => cameraAction(camera => camera.rest()));
$('mark-cancel').addEventListener('click', () => cameraAction(camera => camera.cancel()));
$('retry-queue').addEventListener('click', async () => { await cameraAction(camera => camera.retryUnsaved()); if (authenticated) { queue.setAuthenticated(true); void queue.flush(); } });
document.addEventListener('visibilitychange', () => { if (document.hidden) void camera?.stop('Page hidden or screen locked'); else if (authenticated) { void refreshItems(); void queue.flush(); } });
window.addEventListener('pagehide', () => { queue.setAuthenticated(false); void camera?.stop('Page closed or suspended'); });
window.addEventListener('pageshow', event => { if (event.persisted) { resetPrivateUI(); void session(); } });
window.addEventListener('beforeunload', event => { if (camera?.unsaved || camera?.episode || camera?.saving) { event.preventDefault(); event.returnValue = ''; } });
window.addEventListener('online', () => { if (authenticated) void queue.flush(); });
setInterval(() => { if (authenticated && !document.hidden) { void queue.flush(); if (currentView === 'items') void refreshItems(); } }, 8000);
void session();
