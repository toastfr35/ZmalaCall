// @test S-HLT-008
// @requirements HLR-SRV-CALLBACK-012, HLR-SRV-CALLBACK-013
// @environment portable
// @plan Exercise callback create/list/cancel endpoints through an isolated HTTP application with multiple device identities; assert device ownership, group permissions and authenticated administrator cancellation.
// Register an offline App push destination, request a callback through the authenticated terminal API,
// inspect its signed hint and private-field filtering, then cancel and require a reconciliation hint.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { Store } = require('../../../zmala_server/store');
const { createApplication } = require('../../../zmala_server/main');
const { test } = require('node:test'),
  assert = require('node:assert/strict');
const fs = require('node:fs'),
  os = require('node:os'),
  path = require('node:path');

const flush = () => new Promise((r) => setImmediate(r));

test('HTTP callbacks wake only the enrolled App destination and reconcile cancellation', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'zmala-callback-push-http-')),
    store = new Store(dir);
  const messages = [];
  const { AppPush } = require('../../../zmala_server/app-push');
  const push = new AppPush(store, {
    enabled: true,
    send: async (token, data) => {
      messages.push({ token, data });
    },
  });
  const sip = {
    dialogs: new Map(),
    registrations: new Map(),
    appCalls: { push },
    status: () => ({ registrations: [], active_calls: 0, events: [] }),
  };
  const app = createApplication({ store, sipServer: sip });
  await new Promise((r) => app.server.listen(0, '127.0.0.1', r));
  const origin = 'http://127.0.0.1:' + app.server.address().port;
  const request = async (route, token, method = 'GET', body) => {
    const response = await fetch(origin + route, {
      method,
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return { status: response.status, body: await response.json() };
  };
  try {
    const sender = store.value.users.term1.device_token,
      recipient = store.value.users.phone1.device_token;
    const created = await request('/api/callbacks', sender, 'POST', { to: 'phone1' });
    assert.equal(created.status, 201);
    await flush();
    assert.equal(messages.length, 0);
    assert.equal(
      (
        await request('/api/app/push', recipient, 'POST', {
          token: 'fixture-token-callback-12345678',
        })
      ).status,
      200,
    );
    for (let n = 0; n < 8; n++) await flush();
    assert.equal(messages.length, 1);
    assert.equal(messages[0].token, 'fixture-token-callback-12345678');
    assert.equal(messages[0].data.event, 'callback');
    assert.equal(messages[0].data.call_id, created.body.id);
    const config = await request('/api/app/config', recipient);
    assert.equal(config.status, 200);
    assert.equal(config.body.callbacks[0].id, created.body.id);
    assert.equal('push_notified_key' in config.body.callbacks[0], false);
    assert.equal(
      (await request('/api/callbacks/' + created.body.id + '/cancel', sender, 'POST', {})).status,
      200,
    );
    for (let n = 0; n < 8; n++) await flush();
    assert.equal(messages.length, 2);
    assert.equal((await request('/api/app/config', recipient)).body.callbacks.length, 0);
  } finally {
    await app.flush();
    await new Promise((r) => app.server.close(r));
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('HTTP callback endpoints isolate terminal accounts and admin cancellation', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'zmala-callback-http-')),
    store = new Store(dir);
  store.createAccount({
    emails: ['fixture@example.test'],
    id: 'lounge',
    name: 'Lounge',
    type: 'terminal',
  });
  store.createGroup({ name: 'Second terminal', members: ['term1', 'lounge'] });
  const sip = {
    dialogs: new Map(),
    registrations: new Map(),
    status: () => ({ registrations: [], active_calls: 0, events: [] }),
  };
  const { server } = createApplication({ store, sipServer: sip });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  store.value.http_port = server.address().port;
  async function req(route, method = 'GET', data, token = store.value.admin_token) {
    const response = await fetch(`http://127.0.0.1:${store.value.http_port}${route}`, {
      method,
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: data === undefined ? undefined : JSON.stringify(data),
    });
    return { status: response.status, body: await response.json() };
  }
  try {
    const token = store.value.users.term1.device_token,
      other = store.value.users.lounge.device_token;
    assert.equal((await req('/api/callbacks', 'POST', { to: 'phone1' })).status, 401);
    assert.equal((await req('/api/callbacks', 'POST', { to: 'phone1' }, 'wrong')).status, 401);
    const created = await req('/api/callbacks', 'POST', { to: 'phone1', from: 'lounge' }, token);
    assert.equal(created.status, 201);
    assert.equal(created.body.from, 'term1');
    const id = created.body.id;
    assert.equal((await req('/api/config', 'GET', undefined, other)).body.callbacks.length, 0);
    assert.equal((await req(`/api/callbacks/${id}/cancel`, 'POST', {}, other)).status, 404);
    assert.equal((await req('/api/callbacks', 'POST', { to: 'phone1' }, other)).status, 403);
    assert.equal((await req('/api/admin')).body.callbacks[0].id, id);
    assert.equal((await req(`/api/callbacks/${id}`, 'DELETE', undefined, token)).status, 401);
    assert.equal((await req(`/api/callbacks/${id}`, 'DELETE')).status, 200);
    assert.equal((await req('/api/config', 'GET', undefined, token)).body.callbacks.length, 0);
    const terminalRequest = await req('/api/callbacks', 'POST', { to: 'lounge' }, token);
    assert.equal(
      (await req('/api/config', 'GET', undefined, other)).body.callbacks[0].id,
      terminalRequest.body.id,
    );
    assert.equal((await fetch(`http://127.0.0.1:${store.value.http_port}/callbacks`)).status, 200);
  } finally {
    await flush();
    await new Promise((r) => server.close(r));
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
