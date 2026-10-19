// @test S-LLT-043
// @requirements LLR-SRV-APP-003, LLR-SRV-CALLBACK-015
// @environment portable
// @plan Submit callbacks through the real device-route handler as app and terminal identities;
// reject forged identity fields and forbidden recipients. Restart callback storage, deduplicate,
// inspect app-scoped configuration and complete the pair through the shared callback lifecycle.
// @pass App requests persist once per authorized pair, private views exclude other pairs, and
// connected calls remove pending requests without permitting app access to terminal settings.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { storeFixture, context, request, response } = require('../../support/server/unit-fixture');
const { deviceRoutes } = require('../../../zmala_server/http/device-routes');
const { Callbacks } = require('../../../zmala_server/callbacks');

test('apps use shared callbacks with bearer identity and scoped views', async (t) => {
  const store = storeFixture(t),
    ctx = context(store);
  store.value.users.phone2 = { ...store.value.users.phone1, name: 'Other phone' };
  store.value.groups.family.members.push('phone2');
  ctx.deviceId = 'phone1';
  ctx.callbacks = new Callbacks(store, ctx.sipServer);
  async function route(path, body) {
    const res = response();
    await deviceRoutes(
      request(path, body === undefined ? {} : { method: 'POST', value: body }),
      res,
      new URL(path, 'http://localhost'),
      ctx,
    );
    return res;
  }
  const created = (await route('/api/app/callbacks', { to: 'term1' })).json().callback;
  assert.equal(created.from, 'phone1');
  assert.equal((await route('/api/app/callbacks', { to: 'term1' })).json().callback.id, created.id);
  await assert.rejects(
    route('/api/app/callbacks', { to: 'term1', from: 'term1' }),
    /only the recipient/,
  );
  await assert.rejects(route('/api/app/callbacks', { to: 'missing' }), /not permitted/);
  await new Promise((resolve) => setImmediate(resolve));
  ctx.callbacks = new Callbacks(store, ctx.sipServer);
  assert.equal(ctx.callbacks.list('term1')[0].id, created.id);
  let config = (await route('/api/app/config')).json();
  assert.equal(config.callbacks_enabled, true);
  assert.equal(config.callbacks[0].id, created.id);
  ctx.callbacks.create('phone2', 'term1');
  config = (await route('/api/app/config')).json();
  assert.deepEqual(
    config.callbacks.map((entry) => entry.id),
    [created.id],
  );
  await assert.rejects(
    route('/api/device/settings', { settings: {}, expected: {} }),
    /not available/,
  );
  ctx.callbacks.connected('term1', 'phone1');
  assert.deepEqual((await route('/api/app/config')).json().callbacks, []);
  ctx.deviceId = 'term1';
  await assert.rejects(route('/api/app/callbacks', { to: 'phone1' }), /app account/);
});
