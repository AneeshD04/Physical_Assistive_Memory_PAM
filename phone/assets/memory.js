import { RetryQueue } from './memory-queue.js';
import { ManualCamera } from './memory-camera.js';
const $ = id => document.getElementById(id);
const text = (element, value) => { element.textContent = value == null ? '' : String(value); };
function node(tag, content, className) { const element = document.createElement(tag); if (content != null) text(element, content); if (className) element.className = className; return element; }
let authenticated = false, authGeneration = 0, currentView = 'chat', catalogueSequence = 0, detailSequence = 0;
let selectedId = null, detailTrigger = null, lastCatalogue = '', storageReady = false, camera = null;
function notice(message) { text($('app-status'), message); $('app-status').hidden = !message; }
function dateLabel(value) {
  if (!Number.isSafeInteger(value) || value <= 0) return 'Time not recorded';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Time not recorded' : date.toLocaleString();
}
function safeImageURL(item) {
  if (typeof item.image_url !== 'string' || !item.image_url.startsWith('/api/items/') || item.image_url.startsWith('//')) return null;
  try {
    const url = new URL(item.image_url, location.origin);
    const expected = `/api/items/${encodeURIComponent(item.item_id)}/image`;
    return url.origin === location.origin && !url.username && !url.password && !url.search && !url.hash && url.pathname === expected ? expected : null;
  } catch { return null; }
}
function image(item) {
  const url = safeImageURL(item);
  if (!url) return node('p', 'No evidence image available.', 'muted');
  const img = node('img'); img.src = url; img.alt = `Recorded evidence for ${item.name || 'unnamed item'}; not a live view.`; img.loading = 'lazy'; img.decoding = 'async'; img.className = 'evidence';
  img.addEventListener('error', () => img.replaceWith(node('p', 'Evidence image is unavailable or your session has expired.', 'muted')), { once: true });
  return img;
}
function describe(item, target) {
  target.append(node('p', `Identity: ${item.identity_status || 'unknown'}`, 'badge'));
  target.append(node('p', `Location: ${item.location_status || 'unknown'}`));
  target.append(node('p', item.location_text || 'No supported location is recorded.'));
  target.append(node('p', `Observed: ${dateLabel(item.observed_at_ms)}`, 'muted'));
  if (item.stale_reason) target.append(node('p', `Older evidence: ${item.stale_reason}`, 'notice'));
  if (item.index_pending) target.append(node('p', 'Processing pending. New evidence may change this record.', 'notice'));
  target.append(node('p', `Relevance: ${item.relevance || 'unknown'} · Source: ${item.source || 'not recorded'}`, 'muted'));
}
function itemCard(item) {
  const card = node('article', null, 'card item-card'); card.dataset.itemId = item.item_id;
  card.append(node('h2', item.name || 'Unnamed item'), image(item)); describe(item, card);
  const button = node('button', 'View evidence & history', 'secondary'); button.dataset.itemId = item.item_id;
  button.addEventListener('click', () => openDetail(item.item_id, button)); card.append(button); return card;
}
async function api(path, options = {}) {
  const generation = authGeneration;
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(path, { ...options, credentials: 'same-origin', cache: 'no-store', signal: controller.signal, headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...options.headers } });
    if (generation !== authGeneration) throw new Error('This session changed. Please try again.');
    if (response.status === 401 && !path.endsWith('/login')) { expire(); throw new Error('Your session expired. Sign in again; saved captures remain queued.'); }
    if (!response.ok) {
      const messages = { 400: 'Please check the information and try again.', 401: 'That PIN was not accepted.', 403: 'Access was refused. Use the same-origin local application.', 404: 'This record is no longer available.', 409: 'The request conflicts with retained evidence.', 413: 'This request is too large.', 429: 'Too many attempts. Wait a moment before trying again.', 503: path === '/api/chat' ? 'Optional cloud chat is unavailable. Choose Local; capture and storage are unaffected.' : 'The local service is unavailable. Existing evidence has not been replaced.' };
      throw new Error(messages[response.status] || `The request could not complete (HTTP ${response.status}). Try again.`);
    }
    return await response.json();
  } catch (error) {
    if (error.name === 'AbortError' || error instanceof TypeError) throw new Error('The local service could not be reached. Check the connection and try again.');
    throw error;
  } finally { clearTimeout(timer); }
}
const queue = new RetryQueue({
  notify: message => text($('queue-status'), message),
  unauthorized: () => expire(),
  retained: result => {
    if (!authenticated) return;
    const ack = result.ack;
    notice(ack.status === 'conflict' ? 'The server retained a conflicting packet for review; it was not accepted as a new interpretation.' : `Capture durably retained. Processing: ${result.processing?.status || 'pending'}. Retention does not mean an item was recognized.`);
    if (currentView === 'items') void refreshItems();
  }
});
function resetPrivateUI() {
  authGeneration++; catalogueSequence++; detailSequence++;
  authenticated = false; queue.setAuthenticated(false);
  if (camera) void camera.stop('Signed out or session expired');
  $('item-dialog').close(); selectedId = null;
  $('detail-body').replaceChildren(); $('history').replaceChildren(); $('item-name').value = '';
  $('items-grid').replaceChildren(); $('conversation').replaceChildren(); $('chat-text').value = ''; $('search').value = '';
  $('capabilities').replaceChildren(); lastCatalogue = ''; $('app').hidden = true; $('logout').hidden = true; $('signin').hidden = false;
  $('cloud-option').disabled = true; $('chat-mode').value = 'local'; notice('');
}
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
        $('camera-start').disabled = !authenticated || state.running || state.starting || state.saving || state.unsaved;
        $('camera-pause').disabled = !state.running; $('camera-stop').disabled = !(state.running || state.starting);
        $('mark-before').disabled = !state.running || state.episode || state.saving || state.unsaved;
        $('mark-rest').disabled = !state.running || !state.episode || state.saving;
        $('mark-cancel').disabled = !state.episode || state.saving;
        text($('camera-summary'), state.running ? `Camera on · manual mode${state.episode ? ' · episode in progress' : ''}` : state.starting ? 'Waiting for camera permission' : 'Camera off');
        $('preview-placeholder').hidden = state.running;
      },
      gap: gap => {
        const li = node('li', `${gap.reason} · ${((gap.t_to_ms - gap.t_from_ms) / 1000).toFixed(1)} seconds recorded as a gap.`);
        $('coverage-log').prepend(li); while ($('coverage-log').children.length > 12) $('coverage-log').lastElementChild.remove();
      }
    });
    camera.update();
  } catch (error) { text($('storage-status'), `${error.message} Capture is disabled; local queries and browsing still work.`); $('camera-start').disabled = true; }
}
async function signedIn() {
  authenticated = true; authGeneration++; $('signin').hidden = true; $('app').hidden = false; $('logout').hidden = false; $('pin').value = '';
  const generation = authGeneration;
  showView(currentView, false);
  void refreshHealth(); void refreshItems();
  await setupStorage();
  if (authenticated && generation === authGeneration) { queue.setAuthenticated(true); camera?.update(); }
}
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
}
for (const button of document.querySelectorAll('[data-view]')) button.addEventListener('click', () => showView(button.dataset.view));
function renderCapabilities(capabilities) {
  $('capabilities').replaceChildren();
  for (const cap of Array.isArray(capabilities) ? capabilities : []) $('capabilities').append(node('li', `${cap.name || 'Capability'}: ${cap.enabled ? 'available' : 'unavailable'}${cap.reason ? ` — ${cap.reason}` : ''}`));
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
async function loadDetail(id) {
  const sequence = ++detailSequence; text($('detail-status'), 'Loading evidence and history…'); $('name-save').disabled = true;
  try {
    const [item, history] = await Promise.all([api(`/api/items/${encodeURIComponent(id)}`), api(`/api/items/${encodeURIComponent(id)}/history`)]);
    if (!authenticated || sequence !== detailSequence || selectedId !== id) return;
    text($('detail-title'), item.name || 'Unnamed item'); $('detail-body').replaceChildren(image(item)); describe(item, $('detail-body'));
    $('item-name').value = item.name || ''; $('history').replaceChildren();
    const observations = Array.isArray(history.observations) ? history.observations : [];
    for (const observation of observations) {
      const li = node('li'); li.append(node('p', `${dateLabel(observation.observed_at_ms)} · ${observation.outcome || 'Outcome not recorded'}`));
      li.append(node('p', observation.location_text || observation.location || 'Location unknown'));
      li.append(node('p', `Identity: ${observation.identity_state || observation.identity_status || 'unknown'} · Actor: ${observation.actor || 'unknown'}`, 'muted'));
      $('history').append(li);
    }
    text($('detail-status'), observations.length ? 'Evidence loaded. This is recorded history, not a live location.' : 'No recorded observations are available.'); $('name-save').disabled = false;
  } catch (error) { if (authenticated && sequence === detailSequence) text($('detail-status'), error.message); }
}
function openDetail(id, trigger) {
  selectedId = id; detailTrigger = trigger; $('detail-body').replaceChildren(); $('history').replaceChildren(); $('item-name').value = '';
  text($('detail-title'), 'Item details'); $('item-dialog').showModal(); void loadDetail(id);
}
$('detail-close').addEventListener('click', () => $('item-dialog').close());
$('item-dialog').addEventListener('close', () => {
  detailSequence++; selectedId = null;
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
async function ask(question) {
  if (!question.trim() || $('chat-send').disabled) return;
  $('chat-send').disabled = true; text($('chat-status'), 'Checking stored evidence…');
  const generation = authGeneration; addMessage('user', question);
  try {
    const result = await api('/api/chat', { method: 'POST', body: JSON.stringify({ text: question, mode: $('chat-mode').value }) });
    if (!authenticated || generation !== authGeneration) return;
    const entry = addMessage('assistant', result.text || 'No answer is available from the stored evidence.');
    entry.append(node('p', `Answer type: ${result.shape || 'unknown'}${result.index_pending ? ' · processing pending' : ''}`, 'muted'));
    if (result.shape !== 'abstain' && Array.isArray(result.members) && result.members.length) {
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
$('camera-start').addEventListener('click', () => cameraAction(camera => camera.start()));
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
