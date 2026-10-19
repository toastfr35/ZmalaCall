// @ts-check
'use strict';
// Device API routes use the bearer token identity, not a terminal ID supplied by the request.
const { terminalStatus } = require('../validation');
const { registrationOnline } = require('../registrations');
const { send, readJson, requireDevice, httpError } = require('./responses');
// @llr LLR-SRV-CONFIG-022
/** Full snapshots after reads and writes must expose the same live fields.
 * @param {string} id @param {import('../types/http').DeviceContext} context */
function liveConfiguration(id, { store, sipServer, callbacks }) {
  const config = store.config(id);
  config.contacts = config.contacts.map((contact) => ({
    ...contact,
    online:
      registrationOnline(sipServer.registrations.get(contact.id)) ||
      !!sipServer.appCalls?.push.available(contact.id),
  }));
  config.callbacks = callbacks.list(id);
  return config;
}

/** Identity comes exclusively from the bearer token, never from a requested terminal ID.
 * @param {import('node:http').IncomingMessage} req
 * @param {import('node:http').ServerResponse} res @param {URL} url
 * @param {import('../types/http').DeviceContext} context */
async function deviceRoutes(req, res, url, context) {
  const { store, sipServer, callbacks, consoleJobs, terminalStatuses } = context;
  let { deviceId } = context;
  // @llr LLR-SRV-APP-005
  if (['/api/app/push', '/api/app/call/decline'].includes(url.pathname) && req.method === 'POST') {
    const id = requireDevice(deviceId);
    if (store.enrolledAccount(id)?.type !== 'app')
      throw httpError(403, 'An app account is required.');
    if (!sipServer.appCalls) throw httpError(503, 'Push calling is unavailable.');
    const update = await readJson(req, 8192);
    if (url.pathname === '/api/app/push') sipServer.appCalls.push.register(id, update.token);
    else sipServer.appCalls.decline(id, update.call_id);
    return send(res, 200, { ok: true, push_enabled: sipServer.appCalls.push.sender.enabled });
  }
  // @llr LLR-SRV-APP-003
  if (url.pathname === '/api/app/config' && req.method === 'GET') {
    const id = requireDevice(deviceId);
    if (store.enrolledAccount(id)?.type !== 'app')
      throw httpError(403, 'An app account is required.');
    const config = store.appConfig(id);
    config.contacts = config.contacts.map((contact) => ({
      ...contact,
      online:
        registrationOnline(sipServer.registrations.get(contact.id)) ||
        !!sipServer.appCalls?.push.available(contact.id),
    }));
    return send(res, 200, { ...config, push_enabled: !!sipServer.appCalls?.push.sender.enabled });
  }
  if (
    deviceId &&
    store.enrolledAccount(deviceId)?.type === 'app' &&
    url.pathname.startsWith('/api/') &&
    !url.pathname.startsWith('/api/contacts/')
  ) {
    throw httpError(403, 'This API is not available to app accounts.');
  }
  if (url.pathname === '/api/config' && req.method === 'GET') {
    deviceId = requireDevice(deviceId);
    if (
      // @llr LLR-SRV-PRESENCE-005
      !store.secureCalls &&
      url.searchParams.get('delta') === '1' &&
      url.searchParams.get('version') === String(store.value.configuration_version)
    )
      return send(res, 200, {
        configuration_version: store.value.configuration_version,
        live: {
          contacts: store.contacts(deviceId).map(({ id }) => ({
            id,
            online:
              registrationOnline(sipServer.registrations.get(id)) ||
              !!sipServer.appCalls?.push.available(id),
          })),
          callbacks: callbacks.list(deviceId),
        },
      });
    return send(res, 200, liveConfiguration(deviceId, context));
  }
  if (url.pathname === '/api/device/settings' && req.method === 'POST') {
    deviceId = requireDevice(deviceId);
    const update = await readJson(req, 4096);
    if (
      Object.keys(update).some((key) => !['settings', 'expected'].includes(key)) ||
      !update.settings ||
      typeof update.settings !== 'object' ||
      Array.isArray(update.settings) ||
      !update.expected ||
      typeof update.expected !== 'object' ||
      Array.isArray(update.expected)
    )
      throw Error('Send settings and their previous values.');
    store.setDeviceSettings(
      deviceId,
      /** @type {Record<string, unknown>} */ (update.settings),
      /** @type {Record<string, unknown>} */ (update.expected),
    );
    await store.flush();
    return send(res, 200, liveConfiguration(deviceId, context));
  }
  if (url.pathname === '/api/callbacks' && req.method === 'POST') {
    deviceId = requireDevice(deviceId);
    const update = await readJson(req, 4096);
    const callback = callbacks.create(deviceId, update.to);
    await callbacks.flush();
    return send(res, 201, callback);
  }
  const callbackCancel = url.pathname.match(/^\/api\/callbacks\/([a-f0-9-]{36})\/cancel$/);
  if (callbackCancel && req.method === 'POST') {
    deviceId = requireDevice(deviceId);
    callbacks.cancel(callbackCancel[1], deviceId);
    await callbacks.flush();
    return send(res, 200, { ok: true });
  }
  const presencePath = url.pathname.match(
    /^\/api\/contacts\/([a-z][a-z0-9_-]{0,30})\/availability$/,
  );
  if (presencePath && req.method === 'GET') {
    deviceId = requireDevice(deviceId);
    const id = presencePath[1],
      allowed = store.permitted(deviceId, id);
    return send(res, 200, {
      id,
      online:
        allowed &&
        (registrationOnline(sipServer.registrations.get(id)) ||
          !!sipServer.appCalls?.push.available(id)),
      can_call: allowed,
      ring_timeout: allowed ? store.ringTimeout(id) : 60,
    });
  }
  if (url.pathname === '/api/status' && req.method === 'POST') {
    deviceId = requireDevice(deviceId);
    const update = await readJson(req, 32000);
    terminalStatuses[deviceId] = terminalStatus(update);
    return send(res, 200, { ok: true });
  }
  if (url.pathname === '/api/console/next' && req.method === 'POST') {
    deviceId = requireDevice(deviceId);
    const job = consoleJobs.claim(deviceId);
    await consoleJobs.flush();
    return send(res, 200, { job });
  }
  const resultPath = url.pathname.match(/^\/api\/console\/result\/([a-f0-9-]{36})$/);
  if (resultPath && req.method === 'POST') {
    deviceId = requireDevice(deviceId);
    // JSON escaping can use six bytes per retained output byte (e.g. NUL).
    const result = consoleJobs.finish(deviceId, resultPath[1], await readJson(req, 400000));
    await consoleJobs.flush();
    return send(res, 200, result);
  }
  return false;
}
module.exports = { deviceRoutes };
