// Shared DOM, API and dialog helpers. Account-provided text is inserted as textContent, never HTML.
import { state, page, routes, $ } from './admin-state.js';
export function liveSignature() {
  return JSON.stringify([
    state.model.sip_status.registrations.map((r) => r.user),
    state.model.sip_status.active_calls,
    state.model.sip_status.events.at(-1)?.time,
    Object.keys(state.model.profiles).map((id) => [
      id,
      online(id),
      state.model.terminal_statuses[id]?.state,
    ]),
    state.model.callbacks,
  ]);
}
/** @type {Record<string, string>} */
const icons = {
  video: 'M15 10l6-3v10l-6-3M4 5h9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z',
  overview: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  accounts:
    'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M16 3a4 4 0 0 1 0 8M22 21v-2a4 4 0 0 0-3-3.87M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
  grid: 'M3 3h18v18H3zM3 9h18M3 15h18M9 3v18M15 3v18',
  terminal: 'M3 4h18v13H3zM8 21h8M12 17v4M7 8l3 3-3 3M13 14h4',
  activity: 'M3 12h4l3-8 4 16 3-8h4',
  moon: 'M20.9 13A9 9 0 0 1 11 3.1 9 9 0 1 0 20.9 13Z',
  plus: 'M12 5v14M5 12h14',
  close: 'M6 6l12 12M6 18L18 6',
  edit: 'M12 20H4v-8M16 3l5 5-11 11-6 1 1-6Z',
  trash: 'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7',
  link: 'M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2',
  phone: 'M8 2h8v20H8zM11 18h2',
  server: 'M3 3h18v7H3zM3 14h18v7H3zM7 6h.01M7 17h.01M11 6h6M11 17h6',
  copy: 'M9 9h12v12H9zM5 15H3V3h12v2',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12ZM15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
  up: 'M12 19V5M5 12l7-7 7 7',
  down: 'M12 5v14M5 12l7 7 7-7',
  settings:
    'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1Z',
  check: 'M5 12l4 4L19 6',
  search: 'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z',
};
/** @template {keyof HTMLElementTagNameMap} K @param {K} tag @param {unknown} [text] @param {string} [cls] @returns {HTMLElementTagNameMap[K]} */
export function el(tag, text = null, cls = '') {
  const e = document.createElement(tag);
  if (text !== undefined && text !== null) e.textContent = String(text);
  if (cls) e.className = cls;
  return e;
}
/** @param {string} [name] */
export function icon(name) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  svg.classList.add('icon');
  const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  p.setAttribute('d', icons[name || ''] || icons.accounts);
  svg.append(p);
  return svg;
}
/** @type {NodeListOf<HTMLElement>} */ (document.querySelectorAll('[data-icon]')).forEach((e) =>
  e.prepend(icon(e.dataset.icon)),
);
document.querySelectorAll('nav a').forEach((a) => {
  if (a.getAttribute('href') === page) {
    a.classList.add('active');
    a.setAttribute('aria-current', 'page');
  }
});
const [title, eyebrow, description] = routes[page];
$('page-title').textContent = title;
$('eyebrow').textContent = eyebrow;
$('eyebrow').hidden = !eyebrow;
$('page-description').textContent = description;
$('page-description').hidden = !description;
query(document, '.page-heading').hidden = page === '/';
document.title = title ? title + ' · ZmalaCall' : 'ZmalaCall';
/** @param {string} id @param {string} text */
export function message(id, text) {
  $(id).textContent = text;
  $(id).hidden = !text;
}
/** @param {string} text */
export function notice(text) {
  message('notice', text);
}
/** @param {string} text @param {import('../types/admin').Action} action @param {string} [cls] @param {string} [glyph] */
export function actionButton(text, action, cls = 'secondary', glyph) {
  const b = el('button', null, cls);
  b.type = 'button';
  if (glyph) b.append(icon(glyph));
  if (text) b.append(document.createTextNode(text));
  b.onclick = () => run(action);
  return b;
}
// @llr LLR-SRV-UI-014
/** @param {string} label @param {string} glyph @param {import('../types/admin').Action} action */
export function iconButton(label, glyph, action) {
  const b = actionButton('', action, 'icon-button', glyph);
  b.setAttribute('aria-label', label);
  b.title = label;
  return b;
}
/** @param {string} text @param {string} url @param {string} [cls] */
export function link(text, url, cls = 'text-link') {
  const a = el('a', text, cls);
  a.href = url;
  return a;
}
/** @param {string | undefined} text @param {string} [cls] */
export function badge(text, cls = '') {
  return el('span', text, 'badge ' + cls);
}
/** @type {Map<string, Promise<Blob>>} */
const photoRequests = new Map();
/** Share a bounded immutable blob cache across account row rebuilds.
 * @param {string} path */
function photoBlob(path) {
  let request = photoRequests.get(path);
  if (!request) {
    request = fetch(path)
      .then((response) => {
        if (!response.ok) throw Error('Photo unavailable');
        return response.blob();
      })
      .catch((error) => {
        photoRequests.delete(path);
        throw error;
      });
    if (photoRequests.size >= 40) {
      const oldest = photoRequests.keys().next().value;
      if (oldest !== undefined) photoRequests.delete(oldest);
    }
  }
  photoRequests.delete(path);
  photoRequests.set(path, request);
  return request;
}
/** @param {Pick<import('../types/contracts').Account, 'name' | 'type' | 'photo'>} u */
export function avatar(u) {
  const a = el(
    'span',
    u.name.charAt(0).toUpperCase(),
    'avatar ' + (u.type === 'terminal' ? 'terminal-avatar' : ''),
  );
  if (u.photo)
    photoBlob(u.photo)
      .then((blob) => {
        if (!a.isConnected) return;
        const url = URL.createObjectURL(blob);
        const img = el('img');
        state.photoUrls.set(img, url);
        img.src = url;
        img.alt = u.name;
        a.replaceChildren(img);
      })
      .catch(() => {});
  return a;
}
/** @param {string} title @param {string} text @param {Node} [action] */
export function empty(title, text, action) {
  const c = el('div', null, 'empty-state');
  c.append(icon('accounts'), el('h3', title), el('p', text));
  if (action) c.append(action);
  return c;
}
/** @param {string} title @param {string} [subtitle] */
export function panel(title, subtitle) {
  const p = el('section', null, 'panel'),
    h = el('div', null, 'panel-heading'),
    t = el('div');
  t.append(el('h2', title));
  if (subtitle) t.append(el('p', subtitle, 'muted'));
  h.append(t);
  p.append(h);
  return p;
}
/** @param {string} id */
export function online(id) {
  const s = state.model.terminal_statuses[id];
  return !!s?.last_seen && Date.now() - Date.parse(s.last_seen) < 20000;
}
/** @param {string} id */
export function registered(id) {
  return state.model.sip_status.registrations.some((r) => r.user === id);
}
/** @param {string} id */
export function statusBadge(id) {
  return badge(registered(id) ? 'Registered' : 'Offline', registered(id) ? 'success' : 'neutral');
}
/** The server's typed route snapshots define these same-origin JSON responses.
 * @template {string} U @param {U} url @param {string} [method]
 * @param {import('../types/contracts').JsonObject | File} [value]
 * @returns {Promise<import('../types/contracts').ApiResult<U>>} */
export async function api(url, method = 'GET', value) {
  /** @type {Record<string, string>} */
  const headers = {};
  /** @type {BodyInit | undefined} */
  let body = value instanceof File ? value : undefined;
  if (value && !(value instanceof File)) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(value);
  }
  const response = await fetch(url, { method, headers, body });
  const data = await response.json();
  if (!response.ok) {
    const e = Object.assign(Error(data.error || 'Request failed.'), { status: response.status });
    throw e;
  }
  return /** @type {import('../types/contracts').ApiResult<U>} */ (data);
}
/** @param {import('../types/admin').Action} action @param {string} [errorId] */
export async function run(action, errorId = 'error') {
  if (state.busy) return;
  state.busy = true;
  message(errorId, '');
  try {
    await action();
  } catch (e) {
    message(errorId, e instanceof Error ? e.message : 'Request failed.');
    // A form may be scrolled to its Save button, leaving the error above view.
    $(errorId).scrollIntoView({ block: 'nearest' });
  } finally {
    state.busy = false;
  }
}
/** @param {HTMLFormElement} form @param {import('../types/admin').Action} action @param {string} [errorId] */
export async function submit(form, action, errorId) {
  const b = form.querySelector(/** @type {string} */ ('button[type="submit"]'));
  if (b instanceof HTMLButtonElement) b.disabled = true;
  try {
    await run(action, errorId);
  } finally {
    if (b instanceof HTMLButtonElement) b.disabled = false;
  }
}
document.querySelectorAll('[data-close]').forEach((b) => {
  if (b instanceof HTMLElement)
    b.onclick = () => {
      const dialog = document.getElementById(b.dataset.close || '');
      if (dialog instanceof HTMLDialogElement) dialog.close();
    };
});
for (const dialog of document.querySelectorAll('dialog'))
  dialog.addEventListener('click', (e) => {
    if (e.target === dialog) {
      const r = dialog.getBoundingClientRect();
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom)
        dialog.close();
    }
  });
/** @param {Node[]} elements */
export function setView(...elements) {
  $('view').replaceChildren(...elements);
  // Detached terminal cards retain unsaved forms and their photos when switching
  // the dropdown. Revoke only pictures no longer owned by a live or cached view.
  for (const [image, url] of state.photoUrls) {
    if (image.isConnected || [...state.terminalCards.values()].some((card) => card.contains(image)))
      continue;
    URL.revokeObjectURL(url);
    state.photoUrls.delete(image);
  }
}

// @llr LLR-SRV-DIR-033
/** Check the selected file before uploading; the server revalidates its bytes.
 * @param {File} file */
export async function validatePicture(file) {
  const header = new Uint8Array(await file.slice(0, 8).arrayBuffer());
  const gif = /^GIF8[79]a/.test(String.fromCharCode(...header));
  const png = header.slice(0, 8).join(',') === '137,80,78,71,13,10,26,10';
  const jpeg = header[0] === 255 && header[1] === 216;
  if (!gif && !png && !jpeg) throw Error('Choose a PNG, JPG or animated GIF picture.');
  if (file.size > (gif ? 16 : 2) * 1024 * 1024)
    throw Error(gif ? 'GIF must be at most 16 MiB.' : 'PNG/JPG must be at most 2 MiB.');
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    await new Promise((resolve, reject) => {
      image.onload = resolve;
      image.onerror = () => reject(Error('The picture could not be read.'));
      image.src = url;
    });
    const w = image.naturalWidth,
      h = image.naturalHeight;
    if (gif && (w !== h || w < 480 || w > 1024))
      throw Error(`GIF is ${w} × ${h}. Choose a square GIF, 480–1024 pixels per side.`);
    if (!gif && (!w || !h || w > 8192 || h > 8192 || w * h > 16000000))
      throw Error('PNG/JPG must be at most 8192 pixels per side and 16 megapixels.');
  } finally {
    URL.revokeObjectURL(url);
  }
}
/** @param {File | undefined} file @param {string} current @param {boolean} remove */
export async function accountPicture(file, current, remove) {
  if (!file) return remove ? '' : current || '';
  await validatePicture(file);
  return (await api('/api/photos', 'POST', file)).photo;
}
/** @param {string} value */
export function emailAddresses(value) {
  return value
    .split(',')
    .map((address) => address.trim())
    .filter(Boolean);
}
/** @param {string} title @param {string} description @param {import('../types/admin').Action} action @param {string} [text] */
export function confirm(title, description, action, text = 'Confirm') {
  $('confirm-title').textContent = title;
  $('confirm-description').textContent = description;
  $('confirm-action').textContent = text;
  $('confirm-action').className = text.startsWith('Delete') ? 'danger' : 'primary';
  message('confirm-error', '');
  $('confirm-action').onclick = () =>
    run(async () => {
      await action();
      $('confirm-dialog').close();
      await state.refresh(true);
      if ($('connection-dialog').open) state.renderConnection();
    }, 'confirm-error');
  $('confirm-dialog').showModal();
}

/** @template {string} S @param {ParentNode} root @param {S} selector @returns {import('../types/admin-dom').SelectedElement<S>} */
export function query(root, selector) {
  const element = root.querySelector(selector);
  if (!(element instanceof HTMLElement)) throw Error('Missing administration element: ' + selector);
  return /** @type {import('../types/admin-dom').SelectedElement<S>} */ (element);
}
