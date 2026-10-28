// @ts-check
'use strict';
const fs = require('node:fs');
const asyncFs = require('node:fs/promises');
const path = require('node:path');
const { send } = require('./responses');
const { deviceRoutes } = require('./device-routes');
const { backupRoutes } = require('./backup-routes');
const { adminRoutes } = require('./admin-routes');
const { PhotoStore } = require('../photos');
const { authRoutes } = require('./auth-routes');
const { localAdmin } = require('./admin-network');
const { DEFAULT_SOUND, MAX_SOUND } = require('../ringtones');
const { body } = require('./responses');
const WEB = path.resolve(__dirname, '../web');
const assets = Object.fromEntries(
  ['/', '/accounts', '/groups', '/terminals', '/activity', '/callbacks'].map((route) => [
    route,
    ['admin.html', 'text/html; charset=utf-8'],
  ]),
);
for (const file of fs.readdirSync(WEB)) {
  if (/^admin(?:-[a-z]+)?\.js$/.test(file)) assets['/' + file] = [file, 'text/javascript'];
}
assets['/admin.css'] = ['admin.css', 'text/css'];
/** Host/origin, browser sessions and terminal bearer tokens meet at this boundary. */
/** @param {import('../types/http').HttpContext} context */
function createHandler(context) {
  const { store } = context;
  const v = store.value;
  const photos = new PhotoStore(store.dir);
  /** @param {import('node:http').IncomingMessage} req
   * @param {import('node:http').ServerResponse} res */
  return async (req, res) => {
    const backups = context.backups;
    if (backups) backups.requests++;
    try {
      // @llr LLR-SRV-BACKUP-007
      if (backups?.restoring)
        return send(res, 503, { error: 'Server is restarting to restore a backup.' });
      // @llr LLR-SRV-AUTH-021
      const host = req.headers.host;
      const secure = 'encrypted' in req.socket && req.socket.encrypted === true;
      // @llr LLR-SRV-MEDIA-015
      if (store.secureCalls && !secure && req.url !== '/health' && req.url !== '/ready')
        return send(res, 403, { error: 'This deployment requires HTTPS.' });
      const port = req.socket.localPort || v.http_port;
      const protocol = secure ? 'https' : 'http';
      const interfaceAddress = req.socket.localAddress?.replace(/^::ffff:/, '');
      const allowedHosts = [`127.0.0.1:${port}`, `localhost:${port}`, `${v.host}:${port}`];
      if (secure && store.secureCalls) allowedHosts.push(new URL(store.secureCalls.httpsUrl).host);
      if (interfaceAddress) allowedHosts.push(`${interfaceAddress}:${port}`);
      if (process.env.ZMALA_SERVER_NAME)
        allowedHosts.push(`${process.env.ZMALA_SERVER_NAME}:${port}`);
      if (!allowedHosts.includes(host || ''))
        return send(res, 403, { error: 'Use the configured server address.' });
      if (req.headers.origin && req.headers.origin !== `${protocol}://${host}`)
        return send(res, 403, { error: 'Invalid origin.' });
      const url = new URL(req.url || '/', `${protocol}://${host}`),
        token = req.headers.authorization?.replace(/^Bearer /, '');
      const local = ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(
        req.socket.remoteAddress || '',
      );
      const onAdminNetwork = localAdmin(req.socket);
      const cookie = context.adminSessions.cookie(req);
      const admin =
          (onAdminNetwork && context.adminSessions.valid(cookie || token)) ||
          // Compatibility for existing local maintenance tools during initial
          // setup only. The old shortcut token stops working once a password exists.
          (!store.adminPassword.hash && local && token === v.admin_token),
        // @llr LLR-SRV-AUTH-019, LLR-SRV-AUTH-020
        deviceId = store.deviceAccount(token),
        device = !!deviceId;
      // @llr LLR-SRV-START-006
      if (context.requireSecureAdmin && !secure && !local && !device)
        return send(res, 403, { error: 'Use HTTPS for administration.' });
      // Cookie-authenticated mutations require an exact same-origin request,
      // including logout/login. Non-browser terminal clients use bearer tokens.
      if (cookie && !['GET', 'HEAD'].includes(req.method || '') && !req.headers.origin)
        return send(res, 403, { error: 'A same-origin request is required.' });
      if (url.pathname === '/health') return send(res, 200, { ok: true });
      // @llr LLR-SRV-START-010
      if (url.pathname === '/ready') {
        const persistence = context.persistenceReady?.() ?? true;
        return send(res, persistence ? 200 : 503, { ok: persistence, persistence });
      }
      const identity = { ...context, deviceId };
      if (await deviceRoutes(req, res, url, identity)) return;
      // @llr LLR-SRV-CONFIG-024
      const sound = url.pathname.match(/^\/api\/ringtones\/(nokia|[a-f0-9]{64})\.wav$/);
      if (sound && req.method === 'GET') {
        if (!admin && (!deviceId || !store.terminalAccount(deviceId)))
          return send(res, 401, { error: 'Terminal or administrator authentication required.' });
        if (sound[1] !== 'nokia' && !Object.hasOwn(store.value.ringtones || {}, sound[1]))
          return send(res, 404, { error: 'Ringtone not found.' });
        const file =
          sound[1] === 'nokia'
            ? DEFAULT_SOUND
            : path.join(store.dir, 'ringtones', sound[1] + '.wav');
        let bytes;
        try {
          bytes = await asyncFs.readFile(file);
        } catch {
          return send(res, 404, { error: 'Ringtone file unavailable.' });
        }
        return send(res, 200, bytes, 'audio/wav', 'private, max-age=31536000, immutable');
      }
      if (/^\/photos\/[a-f0-9]+\.(png|jpg|gif)$/.test(url.pathname) && req.method === 'GET') {
        if (!device && !admin) return send(res, 401, { error: 'Authentication required.' });
        const file = path.join(store.dir, url.pathname.slice(1));
        let contents;
        try {
          // One async read avoids an exists/read race if a photo is removed.
          contents = await asyncFs.readFile(file);
        } catch (error) {
          if (error && typeof error === 'object' && 'code' in error && error.code === 'ENOENT')
            return send(res, 404, { error: 'Photo not found.' });
          throw error;
        }
        // Hash-named photo bytes are immutable. Only a private browser cache
        // may retain them; authentication still gates every server request.
        return send(
          res,
          200,
          contents,
          file.endsWith('.gif') ? 'image/gif' : file.endsWith('.png') ? 'image/png' : 'image/jpeg',
          'private, max-age=31536000, immutable',
        );
      }
      // @llr LLR-SRV-AUTH-021
      if (!onAdminNetwork)
        return send(res, 403, {
          error: 'Administration is only available on the server local network.',
        });
      if (
        await authRoutes(req, res, url, context, {
          local,
          admin,
          secure,
          token: cookie || token,
        })
      )
        return;
      if (req.method === 'GET' && url.pathname === '/permissions') {
        res.writeHead(302, { Location: '/groups' });
        return res.end();
      }
      if (req.method === 'GET' && url.pathname === '/zmala-icon.svg')
        return send(
          res,
          200,
          await asyncFs.readFile(path.resolve(__dirname, '../assets/zmala-icon.svg')),
          'image/svg+xml',
        );
      // @llr LLR-SRV-AUTH-023
      if (req.method === 'GET' && assets[url.pathname]) {
        const [file, type] = assets[url.pathname];
        return send(res, 200, await asyncFs.readFile(path.join(WEB, file)), type);
      }
      if (!admin) return send(res, 401, { error: 'Sign in with the admin password.' });
      // @llr LLR-SRV-CONFIG-024
      if (url.pathname === '/api/ringtones' && req.method === 'POST') {
        const version = Number(url.searchParams.get('version'));
        if (!Number.isSafeInteger(version) || version < 1)
          throw Error('Send the current configuration version.');
        const bytes = await body(req, MAX_SOUND);
        return send(
          res,
          201,
          await store.uploadRingtone(url.searchParams.get('name'), bytes, version),
        );
      }
      if (await backupRoutes(req, res, url, context)) return;
      if (await adminRoutes(req, res, url, context)) return;
      if (url.pathname === '/api/photos' && req.method === 'POST')
        return send(res, 201, { photo: await photos.upload(req) });
      send(res, 404, { error: 'Not found.' });
    } catch (error) {
      const failure = error instanceof Error ? error : Error('Request failed.');
      const status =
        'status' in failure && typeof failure.status === 'number' ? failure.status : 400;
      if (!res.headersSent) send(res, status, { error: failure.message });
      else res.destroy(failure);
    } finally {
      if (backups) backups.requests--;
    }
  };
}
module.exports = { createHandler };
