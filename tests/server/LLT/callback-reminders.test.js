// @test S-LLT-017
// @requirements LLR-SRV-DIR-023, LLR-SRV-CALLBACK-017, LLR-SRV-CALLBACK-018, LLR-SRV-CALLBACK-021, LLR-SRV-CALLBACK-022, LLR-SRV-DATA-016
// @environment portable
// @plan Inject time and per-address mailer success/failure into callback storage; assert reminder deadlines, durable per-recipient progress, no revival after completion/expiry, preserved email privacy and migration without changed credentials.
// @pass Every named assertion must pass; failures or skips do not establish requirement verification.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { Store } = require('../../../zmala_server/store');
const { Callbacks } = require('../../../zmala_server/callbacks');

const flush = () => new Promise((resolve) => setImmediate(resolve));
async function settled(service) {
  while (service.email.sending.size) await flush();
}
function callbackFixture(t, mailer) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'zmala-email-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const store = new Store(directory);
  store.updateAccount('phone1', {
    name: 'Noah',
    type: 'app',
    emails: ['daniel@example.test', 'family@example.test'],
  });
  store.setCallbackSettings({ email_after_hours: 1 / 60, remove_after_hours: 3 / 60 });
  const sip = { registrations: new Map(), notifyCallback: async () => true };
  return { store, sip, service: new Callbacks(store, sip, mailer) };
}

test('account emails validate atomically, survive rename/restart and stay out of terminal config', (t) => {
  const { store } = callbackFixture(t, { enabled: () => false });
  assert.throws(
    () => store.createAccount({ id: 'missing', name: 'Missing', type: 'app' }),
    /email addresses/,
  );
  const original = JSON.stringify(store.value);
  for (const emails of [
    [],
    ['bad'],
    ['a@example.test', 'A@EXAMPLE.TEST'],
    ['a@example.test\r\nBcc:bad@example.test'],
    ['<a@example.test>'],
    Array(11).fill('a@example.test'),
  ])
    assert.throws(
      () => store.updateAccount('phone1', { name: 'Changed', type: 'app', emails }),
      /email/,
    );
  assert.equal(JSON.stringify(store.value), original);
  store.updateAccount('phone1', {
    id: 'daniel',
    name: 'Noah',
    type: 'app',
    emails: ['Noah@EXAMPLE.TEST', 'family@example.test'],
  });
  assert.deepEqual(new Store(store.dir).value.users.daniel.emails, [
    'Noah@example.test',
    'family@example.test',
  ]);
  assert.equal(JSON.stringify(store.config()).includes('@example.test'), false);
});

test('reminder deadline emails every contact address once, including offline contacts and accepted SIP notifications; removal deadline deletes persisted requests', async (t) => {
  t.mock.timers.enable({ apis: ['Date'], now: 2000000000000 });
  const sent = [],
    mailer = {
      enabled: () => true,
      sendCallback: async (r, address) => {
        sent.push(address);
        return true;
      },
    };
  const { store, sip, service } = callbackFixture(t, mailer);
  const request = service.create('term1', 'phone1');
  // A SIP notification does not count as completing the requested callback.
  service.requests[0].notified_at = new Date().toISOString();
  service.deliver();
  await settled(service);
  assert.equal(sent.length, 0);
  t.mock.timers.tick(60000);
  service.deliver();
  await settled(service);
  assert.deepEqual(sent, store.value.users.phone1.emails);
  assert.equal(service.list('term1')[0].email_sent_to, undefined);
  assert.equal(service.list()[0].email_sent_to.length, 2);
  const restored = new Callbacks(store, sip, mailer);
  restored.deliver();
  await settled(restored);
  assert.equal(sent.length, 2);
  t.mock.timers.tick(120000);
  restored.deliver();
  assert.equal(restored.list().length, 0);
  assert.equal(
    JSON.parse(fs.readFileSync(restored.file)).some((r) => r.id === request.id),
    false,
  );
  await flush();
});

test('partial email success persists per recipient; retries skip successes and stop on completion or expiry', async (t) => {
  t.mock.timers.enable({ apis: ['Date'], now: 2000000000000 });
  const sent = [];
  let fail = true;
  const mailer = {
    enabled: () => true,
    sendCallback: async (r, address) => {
      sent.push(address);
      if (address.startsWith('family') && fail) throw Error('Temporary delivery failure.');
      return true;
    },
  };
  const { store, sip, service } = callbackFixture(t, mailer);
  const request = service.create('term1', 'phone1');
  t.mock.timers.tick(60000);
  service.deliver();
  await settled(service);
  assert.deepEqual(service.list()[0].email_sent_to, ['daniel@example.test']);
  assert.match(service.list()[0].email_error, /Temporary/);
  service.deliver();
  await settled(service);
  assert.equal(sent.length, 2);
  fail = false;
  const restored = new Callbacks(store, sip, mailer);
  restored.deliver();
  await settled(restored);
  assert.equal(sent.length, 2);
  t.mock.timers.tick(60000);
  restored.deliver();
  await settled(restored);
  assert.deepEqual(sent, ['daniel@example.test', 'family@example.test', 'family@example.test']);
  assert.equal(restored.list()[0].email_error, null);
  restored.connected('term1', 'phone1');
  restored.deliver();
  await settled(restored);
  assert.equal(sent.length, 3);
  const expiring = restored.create('term1', 'phone1');
  t.mock.timers.tick(180000);
  restored.deliver();
  await settled(restored);
  assert.equal(
    restored.requests.some((r) => r.id === expiring.id),
    false,
  );
  assert.equal(sent.length, 3);
  assert.equal(restored.requests.find((r) => r.id === request.id).status, 'completed');
  await flush();
});

test('deadline edits apply from creation time to pending requests, validate before mutation and remove old requests immediately', async (t) => {
  t.mock.timers.enable({ apis: ['Date'], now: 2000000000000 });
  const { store, service } = callbackFixture(t, { enabled: () => false });
  const request = service.create('term1', 'phone1');
  const original = JSON.stringify(store.value);
  for (const settings of [
    { email_after_hours: 3, remove_after_hours: 2 },
    { email_after_hours: 0, remove_after_hours: 2 },
    { email_after_hours: NaN, remove_after_hours: 4 },
    { email_after_hours: 1, remove_after_hours: 721 },
    { email_after_hours: '1', remove_after_hours: 4 },
  ])
    assert.throws(() => service.updateSettings(settings), /Enter hours/);
  assert.equal(JSON.stringify(store.value), original);
  service.updateSettings({ email_after_hours: 2 / 60, remove_after_hours: 5 / 60 });
  assert.equal(
    Date.parse(service.requests[0].email_due_at) - Date.parse(request.created_at),
    120000,
  );
  t.mock.timers.tick(240000);
  service.updateSettings({ email_after_hours: 1 / 60, remove_after_hours: 3 / 60 });
  assert.equal(service.list().length, 0);
  assert.equal(new Callbacks(new Store(store.dir), { registrations: new Map() }).list().length, 0);
  await flush();
});

test('an in-flight SMTP result cannot revive expired, completed or revoked requests', async (t) => {
  t.mock.timers.enable({ apis: ['Date'], now: 2000000000000 });
  let accept;
  const sent = [];
  const mailer = {
    enabled: () => true,
    sendCallback: (r, address) => {
      sent.push(address);
      return new Promise((resolve) => {
        accept = resolve;
      });
    },
  };
  const { store, service } = callbackFixture(t, mailer);
  service.create('term1', 'phone1');
  t.mock.timers.tick(60000);
  service.deliver();
  store.updateGroup('family', { ...store.value.groups.family, members: ['term1'] });
  service.reconcile();
  accept(true);
  await settled(service);
  assert.equal(sent.length, 1);
  assert.equal(service.list()[0].status, 'cancelled');
  assert.equal(service.list()[0].email_sent_to.length, 0);
  store.updateGroup('family', { ...store.value.groups.family, members: ['term1', 'phone1'] });
  service.create('term1', 'phone1');
  t.mock.timers.tick(60000);
  service.deliver();
  t.mock.timers.tick(180000);
  service.reconcile();
  accept(true);
  await settled(service);
  assert.equal(service.list().filter((r) => r.status === 'pending').length, 0);
  service.create('term1', 'phone1');
  t.mock.timers.tick(60000);
  service.deliver();
  service.connected('term1', 'phone1');
  accept(true);
  await settled(service);
  assert.equal(service.list()[0].status, 'completed');
  assert.equal(service.list()[0].email_sent_to.length, 0);
  await flush();
});

test('one rejected address does not block other recipients; disabled reminders catch up after enabling', async (t) => {
  t.mock.timers.enable({ apis: ['Date'], now: 2000000000000 });
  let enabled = false;
  const sent = [],
    mailer = {
      enabled: () => enabled,
      sendCallback: async (r, address) => {
        sent.push(address);
        return !address.startsWith('daniel');
      },
    };
  const { service } = callbackFixture(t, mailer);
  service.create('term1', 'phone1');
  t.mock.timers.tick(60000);
  service.deliver();
  await settled(service);
  assert.equal(sent.length, 0);
  enabled = true;
  service.deliver();
  await settled(service);
  assert.deepEqual(service.list()[0].email_sent_to, ['family@example.test']);
  assert.match(service.list()[0].email_error, /rejected/);
  t.mock.timers.tick(60000);
  service.deliver();
  await settled(service);
  assert.deepEqual(sent, ['daniel@example.test', 'family@example.test', 'daniel@example.test']);
  await flush();
});

test('earlier minute-based deadline settings migrate to hours without changing delays or credentials', (t) => {
  const { store } = callbackFixture(t, { enabled: () => false });
  store.value.callback_settings = { email_after_minutes: 90, remove_after_minutes: 300 };
  const password = store.value.users.phone1.password;
  store.save();
  const restored = new Store(store.dir);
  assert.deepEqual(restored.value.callback_settings, {
    email_after_hours: 1.5,
    remove_after_hours: 5,
  });
  assert.equal(restored.value.users.phone1.password, password);
  assert.equal(restored.value.schema_version, 7);
});
