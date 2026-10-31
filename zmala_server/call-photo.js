// @ts-check
'use strict';
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { promisify } = require('node:util');
const execute = promisify(require('node:child_process').execFile);
const { body, httpError, requireDevice, send } = require('./http/responses');
const MAX_BYTES = 2 * 1024 * 1024;
const LEASE_MS = 12000;
let decoding = 0;

// @llr LLR-SRV-MEDIA-016
/** Decode outside Node's event loop. Temporary files never enter portrait storage.
 * @param {Buffer} bytes */
async function normalize(bytes) {
  const folder = await fs.mkdtemp(path.join(os.tmpdir(), 'zmala-call-photo-'));
  try {
    const source = path.join(folder, 'input'),
      output = path.join(folder, 'output.jpg');
    await fs.writeFile(source, bytes, { mode: 0o600 });
    await execute(
      process.platform === 'win32' ? 'python' : 'python3',
      [path.join(__dirname, 'call_photo.py'), source, output],
      { timeout: 10000 },
    );
    const result = await fs.readFile(output);
    if (result.length > MAX_BYTES) throw httpError(413, 'Photo is too large.');
    return result;
  } catch {
    throw httpError(400, 'Choose a supported JPEG or PNG photo.');
  } finally {
    await fs.rm(folder, { recursive: true, force: true });
  }
}

// @llr LLR-SRV-MEDIA-016
/** The dialog owns bytes; closing it releases shared state. A short sender lease
 * ensures a lost Stop request cannot leave a photo covering video indefinitely.
 * @param {import('node:http').IncomingMessage} req
 * @param {import('node:http').ServerResponse} res @param {URL} url
 * @param {import('./types/http').DeviceContext} context
 * @param {(bytes: Buffer) => Promise<Buffer>} [convert] */
async function callPhotoRoute(req, res, url, context, convert = normalize) {
  if (url.pathname !== '/api/call/photo') return false;
  const user = requireDevice(context.deviceId);
  const id = url.searchParams.get('call_id') || '';
  if (!id || id.length > 256) throw httpError(400, 'Invalid call.');
  const dialog = context.sipServer.dialogs.get(id);
  const account = context.store.enrolledAccount(user);
  if (!dialog?.connected || !account || !dialog.peers.some((p) => p.user === user))
    throw httpError(403, 'This connected call is unavailable.');
  const kinds = dialog.peers.map((p) => context.store.enrolledAccount(p.user)?.type);
  if (!kinds.includes('app') || !kinds.includes('terminal'))
    throw httpError(409, 'Photo sharing requires an app and a terminal.');
  const identities = dialog.peers.map((p) => [
    p.user,
    context.store.enrolledAccount(p.user)?.device_token,
  ]);
  const current = () =>
    context.sipServer.dialogs.get(id) === dialog &&
    dialog.connected &&
    identities.every(
      ([peer, token]) => context.store.enrolledAccount(peer)?.device_token === token,
    );
  const state = (dialog.photoShare ||= { revision: 0, bytes: null, expires: 0, uploading: false });
  if (state.bytes && state.expires <= Date.now()) {
    state.bytes = null;
    state.revision++;
  }
  const status = () => ({
    revision: state.revision,
    sharing: !!state.bytes,
    lease_ms: LEASE_MS,
    remaining_ms: Math.max(0, state.expires - Date.now()),
  });
  if (req.method === 'GET') {
    if (url.searchParams.get('image') === '1') {
      if (!state.bytes || url.searchParams.get('revision') !== String(state.revision))
        throw httpError(404, 'Photo no longer shared.');
      return send(res, 200, state.bytes, 'image/jpeg');
    }
    return send(res, 200, status());
  }
  if (account.type !== 'app') throw httpError(403, 'Only the app can share or stop sharing.');
  if (req.method === 'DELETE') {
    state.revision++;
    state.bytes = null;
    state.expires = 0;
    return send(res, 200, status());
  }
  if (req.method === 'POST') {
    if (state.bytes && url.searchParams.get('revision') === String(state.revision))
      state.expires = Date.now() + LEASE_MS;
    return send(res, 200, status());
  }
  if (req.method !== 'PUT') throw httpError(405, 'Unsupported photo action.');
  if (state.uploading || decoding >= 2) throw httpError(429, 'Photo processing is busy.');
  state.uploading = true;
  decoding++;
  const revision = ++state.revision;
  state.bytes = null;
  try {
    const bytes = await body(req, MAX_BYTES);
    if (!bytes.length) throw httpError(400, 'Choose a photo.');
    const photo = await convert(bytes);
    if (!current() || state.revision !== revision)
      throw httpError(409, 'Photo sharing was cancelled.');
    state.bytes = photo;
    state.expires = Date.now() + LEASE_MS;
    return send(res, 200, status());
  } finally {
    state.uploading = false;
    decoding--;
  }
}
module.exports = { callPhotoRoute, normalize, MAX_BYTES, LEASE_MS };
