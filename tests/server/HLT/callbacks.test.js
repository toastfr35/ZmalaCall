// @test S-HLT-008
// @requirements HLR-SRV-CALLBACK-012, HLR-SRV-CALLBACK-013
// @environment portable
// @plan Exercise callback create/list/cancel endpoints through an isolated HTTP application with multiple device identities; assert device ownership, group permissions and authenticated administrator cancellation.
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
