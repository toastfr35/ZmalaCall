'use strict';
const { test } = require('node:test'),
  assert = require('node:assert/strict');
const fs = require('node:fs'),
  os = require('node:os'),
  path = require('node:path');
const { Store } = require('../store'),
  { Callbacks } = require('../callbacks'),
  { createApplication } = require('../main');
const flush = () => new Promise((r) => setImmediate(r));
test('callback requests persist, deduplicate, expire, complete and obey changed groups', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'zmala-callbacks-')),
    store = new Store(dir),
    sip = { registrations: new Map() };
  try {
    const service = new Callbacks(store, sip),
      request = service.create('term1', 'phone1');
    assert.equal(service.create('term1', 'phone1').id, request.id);
    assert.equal(
      Date.parse(request.expires_at) - Date.parse(request.created_at),
      store.value.callback_settings.remove_after_hours * 3600000,
    );
    assert.equal(new Callbacks(store, sip).list('term1')[0].id, request.id);
    service.connected('phone1', 'term1');
    assert.equal(service.list()[0].status, 'completed');
    const next = service.create('term1', 'phone1');
    service.requests.find((r) => r.id === next.id).expires_at = new Date(
      Date.now() - 1,
    ).toISOString();
    assert.equal(
      service.list().some((r) => r.id === next.id),
      false,
    );
    assert.equal(
      JSON.parse(fs.readFileSync(service.file)).some((r) => r.id === next.id),
      false,
    );
    const revoked = service.create('term1', 'phone1');
    store.updateGroup('family', { ...store.value.groups.family, members: ['term1'] });
    assert.equal(service.list().find((r) => r.id === revoked.id).status, 'cancelled');
    assert.throws(() => service.create('term1', 'phone1'), /not permitted/);
    assert.throws(() => service.create('term1', '__proto__'), /not permitted/);
    await flush();
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
test('offline requests notify on reconnection once, retry failures and keep renamed usernames', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'zmala-notify-')),
    store = new Store(dir),
    sent = [];
  const sip = {
    registrations: new Map(),
    notifyCallback: async (r, text) => {
      sent.push(text);
      return true;
    },
  };
  try {
    const service = new Callbacks(store, sip);
    service.create('term1', 'phone1');
    await flush();
    assert.equal(sent.length, 0);
    store.updateAccount('term1', { id: 'lounge', name: 'Evelyn', type: 'terminal' });
    service.rename('term1', 'lounge');
    sip.registrations.set('phone1', { expires: Date.now() + 60000 });
    service.deliver('phone1');
    await flush();
    assert.equal(sent.length, 1);
    assert.match(sent[0], /Evelyn/);
    assert.match(sent[0], /sip:lounge@/);
    assert.ok(service.list()[0].notified_at);
    service.deliver('phone1');
    await flush();
    assert.equal(sent.length, 1);
    service.cancel(service.list()[0].id);
    const r = service.create('lounge', 'phone1');
    sip.notifyCallback = async () => false;
    await flush();
    assert.equal(service.list()[0].notified_at, null);
    sip.notifyCallback = async () => true;
    service.retry.set(r.id, 0);
    service.deliver();
    await flush();
    assert.ok(service.list()[0].notified_at);
    assert.equal(new Callbacks(store, sip).list()[0].notified_at, service.list()[0].notified_at);
  } finally {
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
