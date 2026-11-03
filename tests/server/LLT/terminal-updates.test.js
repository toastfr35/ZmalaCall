// @test S-LLT-068
// @requirements LLR-SRV-MAINT-022
// @environment portable
// @plan Use disposable public fetch responses and clocks to check shared in-flight caching, cache expiry, old releases, response/origin/redirect bounds, typed telemetry and maintenance expiry; render admin badges with a view double and invoke SIP with an authenticated updating target.
// @pass Feed requests share one bounded unauthenticated fetch, malformed telemetry is rejected, maintenance expires after 60 seconds, and new SIP calls receive 480 before forwarding to an updating terminal.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const vm = require('../../../build_tools/coverage-js.cjs');
const {
  TerminalUpdates,
  updateStatus,
  updateBusy,
  publicAsset,
} = require('../../../zmala_server/terminal-updates');
const { SipServer } = require('../../../zmala_server/sip-server');
const { storeFixture } = require('../../support/server/unit-fixture');
const proxy = require('../../../zmala_server/node_modules/sip/proxy');
const url =
  'https://github.com/toastfr35/ZmalaCall/releases/download/v1.2.3/ZmalaTerminal-Update.json';

test('admin version badges distinguish waiting, failure and stale status', () => {
  const context = { badge: (text, kind) => ({ text, kind }) };
  vm.runInNewContext(
    vm
      .source(path.join(__dirname, '../../../zmala_server/web/admin-terminals.js'))
      .replace(/^import[^;]+;\s*/gm, '')
      .replace(/^export /gm, ''),
    context,
  );
  const render = (update) => {
    const values = [];
    context.appendTerminalUpdate({ append: (value) => values.push(value) }, update, 1000000);
    return values;
  };
  assert.equal(render(undefined).length, 0);
  const status = {
    phase: 'checking',
    installed: '1.2.2',
    received_at: new Date(1000000).toISOString(),
  };
  assert.match(render(status)[0].text, /Version 1.2.2.*Checking update/);
  assert.match(
    render({ ...status, phase: 'idle', available: '1.2.3' })[0].text,
    /Update available/,
  );
  assert.match(render({ ...status, error: 'candidate_failed' })[0].text, /Update retry pending/);
  assert.match(
    render({ ...status, received_at: new Date(900000).toISOString() })[0].text,
    /status unavailable/,
  );
});

test('public manifest cache shares requests and enforces transport bounds', async () => {
  let now = 1000000,
    calls = 0;
  const cache = new TerminalUpdates({
    clock: () => now,
    transport: async (_url, options) => {
      calls++;
      assert.equal(options.redirect, 'manual');
      assert.equal(options.headers.Authorization, undefined);
      return new Response(
        JSON.stringify(
          calls % 2
            ? { assets: [{ name: 'ZmalaTerminal-Update.json', browser_download_url: url }] }
            : { payload: 'signed' },
        ),
      );
    },
  });
  assert.deepEqual(await Promise.all([cache.manifest(), cache.manifest()]), [
    { payload: 'signed' },
    { payload: 'signed' },
  ]);
  await cache.manifest();
  assert.equal(calls, 2);
  now += 300001;
  await cache.manifest();
  assert.equal(calls, 4);
  for (const invalid of ['http://github.com/a', 'https://evil.test/a', 'https://user@github.com/a'])
    assert.equal(publicAsset(invalid), false);
  const oversized = new TerminalUpdates({ transport: async () => new Response('x'.repeat(50)) });
  await assert.rejects(oversized.json(url, 10), /too large/);
  const redirected = new TerminalUpdates({
    transport: async () =>
      new Response(null, { status: 302, headers: { location: 'https://evil.test/file' } }),
  });
  await assert.rejects(redirected.json(url, 10), /redirect/);
  const old = new TerminalUpdates({
    transport: async () => new Response(JSON.stringify({ assets: [] })),
  });
  assert.equal(await old.manifest(), null);
});

test('telemetry receipt time and expiry are server owned', () => {
  const update = updateStatus(
    { phase: 'checking', installed: '1.2.2', available: '1.2.3', received_at: 'forged' },
    1000000,
  );
  assert.equal(update.received_at, new Date(1000000).toISOString());
  assert.equal(updateBusy({ update }, 1060000), true);
  assert.equal(updateBusy({ update }, 1060001), false);
  assert.equal(updateBusy({ update }, 999999), false);
  assert.equal(updateBusy({ update: { ...update, phase: 'request' } }, 1000000), false);
  for (const invalid of [
    { phase: 'invented' },
    { phase: 'idle', installed: true },
    { phase: 'idle', error: 'private URL /token' },
  ])
    assert.throws(() => updateStatus(invalid));
});

test('SIP refuses an updating target before forwarding', async (t) => {
  const store = storeFixture(t);
  const server = new SipServer(store);
  const replies = [];
  server.auth.verify = () => 'phone1';
  store.permitted = () => true;
  server.terminalUpdating = (id) => id === 'term1';
  t.mock.method(proxy, 'send', (message) => replies.push(message));
  await server.request(
    {
      method: 'INVITE',
      uri: 'sip:term1@family.test',
      headers: {
        to: { uri: 'sip:term1@family.test' },
        from: { uri: 'sip:phone1@family.test', params: { tag: 'tag' } },
        via: [],
        cseq: { seq: 1, method: 'INVITE' },
        'call-id': 'maintenance-call',
        contact: [{ uri: 'sip:phone1@127.0.0.1:50001' }],
      },
    },
    { address: '127.0.0.1', port: 50001, protocol: 'UDP' },
  );
  assert.equal(replies.at(-1).status, 480);
  assert.equal(server.dialogs.size, 0);
});
