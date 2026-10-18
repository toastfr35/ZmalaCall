// @test S-LLT-016
// @requirements LLR-SRV-CALLBACK-002, LLR-SRV-CALLBACK-003, LLR-SRV-CALLBACK-004, LLR-SRV-CALLBACK-005, LLR-SRV-CALLBACK-006
// @environment portable
// @plan Drive callback storage with fake registration/notification responses; assert deduplication, completion, expiry, permission changes, one notification after reconnect and retry with preserved renamed identity.
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
