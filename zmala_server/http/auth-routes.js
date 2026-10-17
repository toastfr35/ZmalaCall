'use strict';
const { send, readJson, httpError } = require('./responses');
const { hashPassword, verifyPassword } = require('../admin-sessions');

/** Public login routes are bounded and never disclose password hashes.
 * Initial setup works remotely once; changing a password requires the current one.
 * @param {import('node:http').IncomingMessage} req
 * @param {import('node:http').ServerResponse} res
 * @param {URL} url @param {import('../types/http').HttpContext} context
 * @param {{local: boolean, admin: boolean, secure: boolean, token?: string}} identity */
async function authRoutes(req, res, url, context, identity) {
  if (!url.pathname.startsWith('/api/auth/')) return false;
  const { store, adminSessions } = context;
  const configured = !!store.adminPassword.hash;
  if (url.pathname === '/api/auth/status' && req.method === 'GET')
    return send(res, 200, { setup_required: !configured, can_setup: !configured });
  if (url.pathname === '/api/auth/logout' && req.method === 'POST') {
    if (identity.token) adminSessions.sessions.delete(identity.token);
    adminSessions.setCookie(res, '', identity.secure, true);
    return send(res, 200, { ok: true });
  }
  const setup = url.pathname === '/api/auth/setup';
  const change = url.pathname === '/api/auth/password';
  if (req.method !== 'POST' || (!setup && !change && url.pathname !== '/api/auth/login'))
    return send(res, 404, { error: 'Not found.' });
  if (setup && configured)
    throw httpError(403, 'Admin password is already configured. Sign in first.');
  if (change && !identity.admin) throw httpError(401, 'Sign in first.');
  if (!setup && !configured) throw httpError(403, 'Set the initial admin password first.');
  if (!adminSessions.allowLogin(req.socket.remoteAddress || '')) {
    res.setHeader('Retry-After', '60');
    throw httpError(429, 'Too many attempts. Try again in one minute.');
  }
  const update = await readJson(req, 2048);
  if (adminSessions.changing) throw httpError(409, 'Password change already in progress.');
  const passwordHash = store.adminPassword.hash;
  if (
    !setup &&
    !(await verifyPassword(change ? update.current_password : update.password, passwordHash))
  )
    throw httpError(401, 'Incorrect admin password.');
  if (!setup && passwordHash !== store.adminPassword.hash)
    throw httpError(401, 'Password changed. Sign in again.');
  if (setup || change) {
    // Hold the guard across asynchronous hashing and persistence: two initial
    // setup requests must not race to replace one another's password.
    if (adminSessions.changing) throw httpError(409, 'Password change already in progress.');
    adminSessions.changing = true;
    try {
      if (setup && store.adminPassword.hash) throw httpError(409, 'Password already configured.');
      store.adminPassword.setHash(await hashPassword(update.password));
      adminSessions.sessions.clear();
    } finally {
      adminSessions.changing = false;
    }
  }
  const token = adminSessions.create();
  adminSessions.setCookie(res, token, identity.secure);
  // CLI tools can keep the same short-lived session as a bearer token. The UI
  // ignores it and relies on its HttpOnly cookie, never browser storage.
  return send(res, 200, {
    ok: true,
    ...(update.session_token === true ? { session_token: token } : {}),
  });
}
module.exports = { authRoutes };
