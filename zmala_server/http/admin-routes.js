// @ts-check
'use strict';
// Administrator-only operations; handler.js authenticates the caller before dispatching here.
const { wifiPayload, serverPayload, setupPdf } = require('../setup-pdf');
const { send: sendResponse, readJson, httpError } = require('./responses');
const developerAccess = require('../developer-access');
const { sshStatus, setSsh } = require('../server-ssh');
/** Called only after the central handler has verified administration credentials.
 * @param {import('node:http').IncomingMessage} req
 * @param {import('node:http').ServerResponse} res @param {URL} url
 * @param {import('../types/http').HttpContext} context */
async function adminRoutes(req, res, url, context) {
  const { store, sipServer, callbacks, consoleJobs, terminalStatuses, writeBootstrap } = context;
  const v = store.value;
  if (url.pathname === '/api/server/ssh') {
    if (req.method === 'GET') return sendResponse(res, 200, await sshStatus());
    if (req.method === 'PUT') {
      const update = await readJson(req, 1024);
      return sendResponse(res, 200, await setSsh(update.enabled));
    }
  }
  // @llr LLR-SRV-HOST-007
  if (url.pathname === '/api/developer-access') {
    if (req.method === 'GET')
      return sendResponse(res, 200, await developerAccess.control('status'));
    if (req.method === 'PUT') {
      const update = await readJson(req, 1024);
      if (update.terminal_id === null)
        return sendResponse(res, 200, await developerAccess.control('off'));
      const account = store.terminalAccount(update.terminal_id);
      if (!account || !account.device_id) throw httpError(400, 'Choose an enrolled terminal.');
      if (!store.secureCalls) throw httpError(400, 'Developer access requires HTTPS.');
      const current = await developerAccess.control('status');
      if (!current?.supported)
        throw httpError(503, 'Install developer access on the server first.');
      if (current.terminal_id && current.terminal_id !== update.terminal_id)
        throw httpError(409, 'Deactivate developer access on the other terminal first.');
      return sendResponse(
        res,
        200,
        await developerAccess.control('on', {
          terminal_id: update.terminal_id,
          device_id: account.device_id,
          host: new URL(store.secureCalls.httpsUrl).hostname,
        }),
      );
    }
  }
  /** @param {Parameters<typeof sendResponse>} args */
  async function send(...args) {
    // A success response promises that every queued configuration revision is
    // saved. Disk waits yield to SIP/UDP processing instead of blocking it.
    if (req.method !== 'GET') {
      const route = url.pathname;
      if (route.startsWith('/api/terminals/')) await consoleJobs.flush();
      else if (route.startsWith('/api/callbacks/')) await callbacks.flush();
      else if (!route.startsWith('/api/setup/')) {
        await store.flush();
        if (route.startsWith('/api/users/') || route === '/api/terminal-association')
          await Promise.all([callbacks.flush(), consoleJobs.flush()]);
        else if (route === '/api/callback-settings') await callbacks.flush();
      }
    }
    return sendResponse(...args);
  }
  // @llr LLR-SRV-DIR-025, LLR-SRV-DIR-026
  /** @param {string} id */
  function idleAccount(id) {
    // A push-wake INVITE owns both accounts before it becomes a SIP dialog.
    if (
      sipServer.appCalls?.busy(id) ||
      [...sipServer.dialogs.values()].some((d) => d.peers.some((p) => p.user === id))
    ) {
      throw httpError(409, "End this account's active call before changing or deleting it.");
    }
  }
  /** @param {string} id */
  function forgetAccount(id) {
    sipServer.cancelProbe?.(id);
    sipServer.registrations.delete(id);
    delete terminalStatuses[id];
  }
  // @llr LLR-SRV-CONFIG-023
  /** @param {import('../types/contracts').JsonObject} update */
  function version(update) {
    if (
      update.configuration_version !== undefined &&
      update.configuration_version !== v.configuration_version
    ) {
      throw httpError(
        409,
        'Configuration changed. Reload the page and reopen the editor before saving.',
      );
    }
  }
  const consolePath = url.pathname.match(
    /^\/api\/terminals\/([a-z][a-z0-9_-]{0,30})\/console(?:\/([a-f0-9-]{36}))?$/,
  );
  if (consolePath) {
    const [, id, jobId] = consolePath;
    if (req.method === 'GET' && !jobId) return send(res, 200, { jobs: consoleJobs.list(id) });
    if (req.method === 'POST' && !jobId) {
      const job = consoleJobs.create(id, await readJson(req, 32000));
      return send(res, 201, { id: job.id });
    }
    if (req.method === 'DELETE' && jobId) {
      consoleJobs.cancel(id, jobId);
      return send(res, 200, { ok: true });
    }
  }
  if (url.pathname === '/api/setup/wifi.pdf' && req.method === 'POST') {
    const update = await readJson(req, 4096);
    const payload = wifiPayload(update),
      pdf = await setupPdf({ kind: 'wifi', label: String(update.ssid), payload });
    res.setHeader('Content-Disposition', 'attachment; filename="zmalacall-wifi.pdf"');
    return send(res, 200, pdf, 'application/pdf');
  }
  if (url.pathname === '/api/setup/server.pdf' && req.method === 'GET') {
    const id = url.searchParams.get('id') || '';
    if (!store.enrolledAccount(id)) throw Error('Choose an app or terminal account.');
    const bootstrap = store.bootstrap(id, true),
      pdf = await setupPdf({
        kind: 'server',
        label: `${store.value.users[id].name} (${id})`,
        payload: serverPayload(bootstrap),
        serverUrl: bootstrap.server_url,
        app: bootstrap.account_type === 'app',
      });
    res.setHeader('Content-Disposition', `attachment; filename="zmalacall-server-${id}.pdf"`);
    return send(res, 200, pdf, 'application/pdf');
  }
  if (['/api/admin', '/api/admin/live'].includes(url.pathname) && req.method === 'GET') {
    const live = {
      configuration_version: v.configuration_version,
      sip_status: sipServer.status(),
      terminal_statuses: terminalStatuses,
      terminal_status: terminalStatuses[v.local_terminal_id || ''] || {},
      callbacks: callbacks.list(),
    };
    if (url.pathname === '/api/admin/live') return send(res, 200, live);
    /** @type {import('../types/contracts').AdminModel} */
    const snapshot = {
      ...store.admin(),
      ...live,
    };
    return send(res, 200, snapshot);
  }
  const callbackPath = url.pathname.match(/^\/api\/callbacks\/([a-f0-9-]{36})$/);
  if (url.pathname === '/api/callback-settings' && req.method === 'PUT') {
    const update = await readJson(req, 4096);
    version(update);
    callbacks.updateSettings(update);
    return send(res, 200, { ok: true });
  }
  if (url.pathname === '/api/smtp-settings' && req.method === 'PUT') {
    const update = await readJson(req, 4096);
    version(update);
    store.setSmtpSettings(update);
    callbacks.deliver();
    return send(res, 200, { ok: true });
  }
  if (url.pathname === '/api/smtp-settings/verify' && req.method === 'POST') {
    await callbacks.email.mailer.verify();
    return send(res, 200, { ok: true });
  }
  if (callbackPath && req.method === 'DELETE') {
    callbacks.cancel(callbackPath[1]);
    return send(res, 200, { ok: true });
  }
  if (url.pathname === '/api/groups' && req.method === 'POST') {
    const update = await readJson(req, 16000);
    version(update);
    const id = store.createGroup(update);
    return send(res, 201, { ok: true, id, configuration_version: v.configuration_version });
  }
  const groupPath = url.pathname.match(/^\/api\/groups\/([a-z][a-z0-9_-]{0,30})$/);
  if (groupPath && ['PUT', 'DELETE'].includes(req.method || '')) {
    const update = await readJson(req, 16000, true);
    version(update);
    if (req.method === 'PUT') store.updateGroup(groupPath[1], update);
    else store.deleteGroup(groupPath[1]);
    return send(res, 200, { ok: true, configuration_version: v.configuration_version });
  }
  if (url.pathname === '/api/terminal-association' && req.method === 'PUT') {
    const update = await readJson(req, 4096);
    version(update);
    if (typeof update.account_id !== 'string') throw Error('Choose a terminal account.');
    store.requireTerminal(update.account_id);
    const previous = Object.keys(v.profiles).find(
      (id) => store.terminalAccount(id)?.device_id === update.serial_number,
    );
    if (!previous) throw Error('Terminal serial number not found.');
    idleAccount(previous);
    idleAccount(update.account_id);
    store.associateTerminal(update.serial_number, update.account_id);
    if (previous !== update.account_id) {
      // Commands must remain attached to the same physical terminal after reassignment.
      consoleJobs.swapTerminals(previous, update.account_id);
      forgetAccount(previous);
      forgetAccount(update.account_id);
    }
    await writeBootstrap();
    return send(res, 200, { ok: true, id: update.account_id });
  }
  if (url.pathname === '/api/settings' && req.method === 'PUT') {
    const update = await readJson(req, 10000);
    version(update);
    const id = update.terminal_id || v.local_terminal_id;
    if (id !== null && typeof id !== 'string') throw Error('Choose a terminal account.');
    store.setSettings(id, update);
    return send(res, 200, { ok: true, configuration_version: v.configuration_version });
  }
  if (url.pathname === '/api/users' && req.method === 'POST') {
    const update = await readJson(req, 10000);
    version(update);
    const id = store.createAccount(update);
    await writeBootstrap();
    return send(res, 201, { ok: true, id });
  }
  const accountPath = url.pathname.match(/^\/api\/users\/([a-z][a-z0-9_-]{0,30})$/);
  if (accountPath && ['PUT', 'DELETE'].includes(req.method || '')) {
    const id = accountPath[1];
    let credentialsChanged = true,
      typeChanged = false,
      next = id;
    if (req.method === 'DELETE') {
      version(await readJson(req, 10000, true));
      idleAccount(id);
      store.deleteAccount(id);
    } else {
      const update = await readJson(req, 10000),
        old = v.users[id];
      version(update);
      typeChanged = !!old && old.type !== update.type;
      credentialsChanged =
        !!old &&
        ((update.id !== undefined && update.id !== id) ||
          old.type !== update.type ||
          (!!update.password && old.password !== update.password));
      if (credentialsChanged) idleAccount(id);
      next = store.updateAccount(id, update);
    }
    if (next !== id) {
      consoleJobs.rename(id, next);
      callbacks.rename(id, next);
    }
    callbacks.reconcile(typeChanged ? next : undefined);
    consoleJobs.expire();
    if (credentialsChanged) forgetAccount(id);
    await writeBootstrap();
    return send(res, 200, { ok: true, id: next });
  }
  if (url.pathname === '/api/local-terminal' && req.method === 'PUT') {
    const update = await readJson(req, 10000);
    if (typeof update.id !== 'string') throw Error('Choose a terminal account.');
    store.selectTerminal(update.id);
    await writeBootstrap();
    return send(res, 200, { ok: true, restart_terminal: true });
  }
  if (url.pathname === '/api/terminal-bootstrap' && req.method === 'GET') {
    store.requireTerminal(url.searchParams.get('id') || '');
    return send(res, 200, store.bootstrap(url.searchParams.get('id') || '', true));
  }
  return false;
}
module.exports = { adminRoutes };
