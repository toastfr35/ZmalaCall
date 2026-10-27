// @test S-LLT-063
// @requirements LLR-SRV-CALLBACK-025
// @environment portable
// @plan Use real callback persistence/AppPush proofs with a substituted FCM transport and offline SIP.
// Create, repeat, restart, cancel and complete requests; inspect accepted fingerprints and API filtering.
// Control failed sends, the minute retry boundary, queued persistence, revocation and in-flight cancellation.
// @pass Only eligible App recipients receive signed state hints; duplicate/current states do not resend,
// state changes survive races/restart, closed state is reconciled and internal fingerprints stay private.
'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { Callbacks } = require('../../../zmala_server/callbacks');
const { AppPush } = require('../../../zmala_server/app-push');
const { storeFixture } = require('../../support/server/unit-fixture');
const flush = async () => {
  for (let n = 0; n < 8; n++) await new Promise((r) => setImmediate(r));
};
function fixture(t, send) {
  const store = storeFixture(t),
    messages = [];
  const push = new AppPush(store, {
    enabled: true,
    send: async (token, data) => {
      messages.push(data);
      if (send) await send(data);
    },
  });
  push.register('phone1', 'fixture-push-token-1234567890');
  const sip = {
    registrations: new Map(),
    notifyCallback: async () => {
      throw Error('offline SIP must not be used');
    },
  };
  const callbacks = new Callbacks(store, sip, undefined, push);
  callbacks.email.deliver = () => {};
  return { store, push, sip, callbacks, messages };
}
test('offline App callback hints are signed, deduplicated, durable and removed after cancellation/completion', async (t) => {
  const { store, push, sip, callbacks, messages } = fixture(t);
  const request = callbacks.create('term1', 'phone1');
  await flush();
  assert.equal(messages.length, 1);
  const data = messages[0];
  assert.equal(data.event, 'callback');
  assert.equal(data.call_id, request.id);
  assert.equal(data.caller, 'term1');
  assert.equal(data.device_id, store.value.users.phone1.device_id);
  const body = JSON.stringify([
    data.event,
    data.call_id,
    data.caller,
    data.expires,
    data.device_id,
  ]);
  assert.equal(
    data.proof,
    crypto.createHmac('sha256', store.value.users.phone1.device_token).update(body).digest('hex'),
  );
  assert.ok(Number(data.expires) > Date.now() && Number(data.expires) <= Date.now() + 60000);
  assert.equal(callbacks.create('term1', 'phone1').id, request.id);
  await flush();
  assert.equal(messages.length, 1);
  assert.equal(callbacks.requests[0].status, 'pending');
  assert.ok(callbacks.requests[0].push_notified_key);
  assert.equal('push_notified_key' in callbacks.list('phone1')[0], false);
  const restored = new Callbacks(store, sip, undefined, push);
  restored.email.deliver = () => {};
  restored.deliver();
  await flush();
  assert.equal(messages.length, 1);
  restored.cancel(request.id, 'term1');
  await flush();
  assert.equal(messages.length, 2);
  assert.equal(restored.list('phone1').length, 0);
  const next = restored.create('term1', 'phone1');
  await flush();
  assert.equal(messages.length, 3);
  restored.connected('term1', 'phone1');
  await flush();
  assert.equal(messages.length, 4);
  assert.equal(restored.requests.find((r) => r.id === next.id).status, 'completed');
});
test('failed hints retry at the minute boundary without changing callback state', async (t) => {
  let now = Date.now(),
    fail = true;
  t.mock.method(Date, 'now', () => now);
  t.mock.method(console, 'error', () => {});
  const { callbacks, messages } = fixture(t, async () => {
    if (fail) throw Error('provider secret must not be logged');
  });
  const request = callbacks.create('term1', 'phone1');
  await flush();
  assert.equal(messages.length, 1);
  callbacks.deliver();
  await flush();
  assert.equal(messages.length, 1);
  now += 59999;
  callbacks.deliver();
  await flush();
  assert.equal(messages.length, 1);
  now++;
  fail = false;
  callbacks.deliver();
  await flush();
  assert.equal(messages.length, 2);
  assert.equal(callbacks.requests.find((r) => r.id === request.id).status, 'pending');
  callbacks.deliver();
  await flush();
  assert.equal(messages.length, 2);
});
test('cancellation racing a successful pending hint sends the latest state afterward', async (t) => {
  let release;
  let first = true;
  const { callbacks, messages } = fixture(t, () =>
    first
      ? ((first = false),
        new Promise((r) => {
          release = r;
        }))
      : Promise.resolve(),
  );
  const request = callbacks.create('term1', 'phone1');
  await flush();
  assert.equal(messages.length, 1);
  callbacks.cancel(request.id, 'term1');
  await flush();
  assert.equal(messages.length, 1);
  release();
  await flush();
  assert.equal(messages.length, 2);
  assert.equal(callbacks.push.sending.size, 0);
  assert.equal(callbacks.requests[0].push_notified_key, callbacks.push.key(callbacks.requests[0]));
});
test('queued persistence is rechecked for permission, expiry and recipient identity', async (t) => {
  const { store, callbacks, messages } = fixture(t);
  let release;
  callbacks.flush = () =>
    new Promise((r) => {
      release = r;
    });
  callbacks.create('term1', 'phone1');
  await flush();
  const original = store.value.users.phone1.device_token;
  store.value.users.phone1.device_token = 'replacement-fixture-token';
  release();
  await flush();
  assert.equal(messages.length, 0);
  store.value.users.phone1.device_token = original;
  callbacks.push.retry.clear();
  callbacks.deliver();
  await flush();
  callbacks.requests[0].expires_at = new Date(Date.now() - 1).toISOString();
  release();
  await flush();
  assert.equal(messages.length, 0);
  callbacks.requests[0].expires_at = new Date(Date.now() + 600000).toISOString();
  callbacks.push.retry.clear();
  callbacks.deliver();
  await flush();
  t.mock.method(store, 'permitted', () => false);
  release();
  await flush();
  assert.equal(messages.length, 0);
});
