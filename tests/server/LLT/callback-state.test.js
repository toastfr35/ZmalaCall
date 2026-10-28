// @test S-LLT-016
// @requirements LLR-SRV-CALLBACK-015, LLR-SRV-CALLBACK-016, LLR-SRV-CALLBACK-017, LLR-SRV-CALLBACK-018, LLR-SRV-CALLBACK-019
// @environment portable
// @plan Drive callback storage with fake registration/notification responses; assert the 400-pending boundary, duplicate acceptance at capacity, deduplication, completion, expiry, permission changes, one notification after reconnect and retry with preserved renamed identity. Retire a requester and finish pending work without another creation; assert cancellation and a persisted 200-record completed-history cap. Exercise the real SIP notifier with a fake transport and clock: preserve UTF-8 and exact recipient flow, ignore provisional responses, accept only 2xx, and fail closed on rejection, timeout or send error.
// @pass Every named assertion must pass; failures or skips do not establish requirement verification.

'use strict';
const { Store } = require('../../../zmala_server/store');
const { Callbacks } = require('../../../zmala_server/callbacks');
const { test } = require('node:test'),
  assert = require('node:assert/strict');
const fs = require('node:fs'),
  os = require('node:os'),
  path = require('node:path');

const flush = () => new Promise((r) => setImmediate(r));

test('retired requester and completion trim history without waiting for another request', async (t) => {
  const { storeFixture } = require('../../support/server/unit-fixture');
  const store = storeFixture(t);
  const service = new Callbacks(store, { registrations: new Map() });
  const pending = service.create('term1', 'phone1');
  const sample = service.requests[0];
  service.requests = [
    ...Array.from({ length: 200 }, (_, i) => ({
      ...sample,
      id: `completed-${i}`,
      status: 'completed',
    })),
    sample,
  ];
  service.reconcile('term1');
  assert.equal(service.requests.find((r) => r.id === pending.id).status, 'cancelled');
  assert.equal(service.requests.length, 200);
  assert.equal(new Callbacks(store, { registrations: new Map() }).requests.length, 200);
  service.create('phone1', 'term1');
  service.connected('term1', 'phone1');
  assert.equal(service.requests.length, 200);
  assert.equal(service.requests.at(-1).status, 'completed');
  await flush();
});

test('400 pending requests allow duplicates but refuse a new pair until capacity is released', async (t) => {
  const { storeFixture } = require('../../support/server/unit-fixture');
  const store = storeFixture(t);
  for (let i = 1; i <= 19; i++)
    for (const type of ['terminal', 'app']) {
      store.createAccount({
        id: `${type}${i}`,
        type,
        name: `Fixture ${type} ${i}`,
        emails: ['fixture@example.test'],
      });
    }
  store.createGroup({ name: 'Capacity fixture', members: Object.keys(store.value.users) });
  const service = new Callbacks(store, { registrations: new Map() });
  service.create('term1', 'phone1');
  const template = structuredClone(service.requests[0]);
  const senders = Object.keys(store.value.users).filter((id) => store.terminal(id));
  const recipients = Object.keys(store.value.users).filter((id) => !store.terminal(id));
  service.requests = senders.flatMap((from) =>
    recipients.map((to) => ({
      ...structuredClone(template),
      id: `fixture-${from}-${to}`,
      from,
      to,
    })),
  );
  assert.equal(service.requests.length, 400);
  service.save();
  const snapshot = structuredClone(service.requests);
  assert.equal(service.create('term1', 'phone1').id, 'fixture-term1-phone1');
  assert.throws(() => service.create('term1', 'terminal1'), /Too many pending/);
  assert.deepEqual(service.requests, snapshot);
  service.cancel(service.requests.at(-1).id);
  assert.equal(service.create('term1', 'terminal1').status, 'pending');
  assert.equal(service.requests.filter((r) => r.status === 'pending').length, 400);
  await flush();
  const restored = new Callbacks(store, { registrations: new Map() });
  assert.equal(restored.requests.filter((r) => r.status === 'pending').length, 400);
  assert.equal(restored.create('term1', 'phone1').id, 'fixture-term1-phone1');
  await flush();
});

test('callback SIP delivery preserves UTF-8, exact flow and final acceptance with a bounded timeout', async (t) => {
  const sip = require('../../../zmala_server/node_modules/sip');
  const { SipMessages } = require('../../../zmala_server/sip-messages');
  sip.send ??= () => {};
  sip.encodeFlowUri ??= () => '';
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const store = { value: { host: '192.0.2.1' }, permitted: () => true };
  const service = new SipMessages(store);
  const request = { from: 'term1', to: 'phone1' };
  const remote = { address: '192.0.2.2', port: 5060, protocol: 'UDP' };
  const sent = [];
  t.mock.method(sip, 'encodeFlowUri', (flow) => {
    assert.equal(flow, remote);
    return 'sip:exact-flow';
  });
  const send = t.mock.method(sip, 'send', (message, callback) => sent.push({ message, callback }));
  assert.equal(await service.notifyCallback(request, 'absent'), false);
  service.registrations.set('phone1', {
    expires: Date.now() + 60000,
    contact: { uri: 'sip:phone@192.0.2.2' },
    remote,
  });
  store.permitted = () => false;
  assert.equal(await service.notifyCallback(request, 'forbidden'), false);
  assert.equal(sent.length, 0);
  store.permitted = () => true;
  const text = 'Rappelez Zoë — sip:term1@192.0.2.1';
  let resolved = false;
  const delivery = service.notifyCallback(request, text).then((ok) => {
    resolved = true;
    return ok;
  });
  const { message, callback } = sent.at(-1);
  assert.equal(Buffer.from(message.content, 'latin1').toString('utf8'), text);
  assert.equal(message.uri, 'sip:phone@192.0.2.2');
  assert.deepEqual(message.headers.route, [{ uri: 'sip:exact-flow' }]);
  assert.equal(message.headers.from.uri, 'sip:term1@192.0.2.1');
  assert.equal(message.headers.to.uri, 'sip:phone1@192.0.2.1');
  assert.match(message.headers['call-id'], /^callback-/);
  callback({ status: 180 });
  await Promise.resolve();
  assert.equal(resolved, false, 'A provisional response is not delivery');
  callback({ status: 202 });
  assert.equal(await delivery, true);
  const rejected = service.notifyCallback(request, text);
  sent.at(-1).callback({ status: 503 });
  assert.equal(await rejected, false);
  resolved = false;
  const timeout = service.notifyCallback(request, text).then((ok) => {
    resolved = true;
    return ok;
  });
  t.mock.timers.tick(9999);
  await Promise.resolve();
  assert.equal(resolved, false);
  t.mock.timers.tick(1);
  assert.equal(await timeout, false);
  const errors = t.mock.method(console, 'error', () => {});
  send.mock.mockImplementation(() => {
    throw Error('unavailable');
  });
  assert.equal(await service.notifyCallback(request, text), false);
  assert.deepEqual(errors.mock.calls.at(-1).arguments, [
    'Callback SIP message failed:',
    'unavailable',
  ]);
});
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
