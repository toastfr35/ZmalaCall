// @test S-LLT-021
// @requirements LLR-SRV-START-006, LLR-SRV-START-010, LLR-SRV-AUTH-019, LLR-SRV-AUTH-020, LLR-SRV-AUTH-021, LLR-SRV-AUTH-022, LLR-SRV-AUTH-023, LLR-SRV-AUTH-024, LLR-SRV-DIR-025, LLR-SRV-DIR-026, LLR-SRV-DIR-027, LLR-SRV-CONFIG-021, LLR-SRV-CONFIG-022, LLR-SRV-ENROLL-005, LLR-SRV-PRESENCE-005, LLR-SRV-CALLBACK-015, LLR-SRV-CALLBACK-016, LLR-SRV-CALLBACK-020, LLR-SRV-MAINT-013, LLR-SRV-MAINT-016, LLR-SRV-MAINT-018, LLR-SRV-MAINT-019, LLR-SRV-MAINT-020
// @environment portable
// Media status assertions cover detached supported snapshots, unknown fields, finite measurements,
// resolution bounds and integer counters; rejected reports preserve the previous snapshot.
// @plan Invoke HTTP controllers with in-memory request streams and response doubles; check Host/Origin/TLS and identity isolation, exact body bounds, persistence barriers, authenticated callback creation/cancellation and enrollment identity persistence, live delta callbacks, validated status receipt time, protected diagnostics and active-call reassociation rejection, including push-wake identity edits and deletion before a SIP dialog exists.
// Supply explicit interface subnets and TCP peer addresses to check LAN-only administration,
// including mapped IPv4, IPv6, spoofed forwarding headers and valid remote admin credentials.
// Exercise live, push-only and unavailable contacts through full configuration, delta and preflight routes at the same revision.
// @pass Every allowed and denied request must produce the expected status and state; no sockets, actual commands or remote devices are used.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { storeFixture, request, response, context } = require('../../support/server/unit-fixture');
const { createHandler } = require('../../../zmala_server/http/handler');
const { readJson } = require('../../../zmala_server/http/responses');
const { terminalStatus } = require('../../../zmala_server/terminal-status');
const os = require('node:os');
const fs = require('node:fs');
const path = require('node:path');
const { localAdmin } = require('../../../zmala_server/http/admin-network');
const lanInterfaces = {
  eth0: [{ address: '192.168.1.10', cidr: '192.168.1.10/24', internal: false }],
};

function fixture(t) {
  const store = storeFixture(t),
    ctx = context(store),
    handler = createHandler(ctx);
  const call = async (path, options) => {
    const res = response();
    await handler(request(path, options), res);
    return res;
  };
  const device = { authorization: `Bearer ${store.value.users.term1.device_token}` };
  const admin = { authorization: `Bearer ${ctx.adminSessions.create()}` };
  return { store, ctx, call, device, admin };
}

test('device callback, availability and command routes bind identity and await durable mutations', async (t) => {
  const { store, ctx, call, device } = fixture(t);
  const events = [];
  const id = '11111111-1111-1111-1111-111111111111';
  ctx.callbacks.create = (from, to) => {
    events.push(['create', from, to]);
    return { id, from, to };
  };
  ctx.callbacks.cancel = (job, owner) => events.push(['cancel', job, owner]);
  ctx.callbacks.flush = async () => events.push(['callback.flush']);
  ctx.consoleJobs.claim = (owner) => {
    events.push(['claim', owner]);
    return { id, command: 'true' };
  };
  ctx.consoleJobs.flush = async () => events.push(['console.flush']);
  const created = await call('/api/callbacks', {
    method: 'POST',
    headers: device,
    value: { to: 'phone1', from: 'forged' },
  });
  assert.equal(created.status, 201);
  assert.equal(created.json().from, 'term1');
  assert.deepEqual(events, [['create', 'term1', 'phone1'], ['callback.flush']]);
  assert.equal(
    (await call(`/api/callbacks/${id}/cancel`, { method: 'POST', headers: device })).status,
    200,
  );
  assert.deepEqual(events.slice(-2), [['cancel', id, 'term1'], ['callback.flush']]);
  assert.equal(
    (await call('/api/console/next', { method: 'POST', headers: device })).json().job.id,
    id,
  );
  assert.deepEqual(events.slice(-2), [['claim', 'term1'], ['console.flush']]);
  ctx.consoleJobs.flush = async () => {
    throw Error('disk unavailable');
  };
  assert.equal((await call('/api/console/next', { method: 'POST', headers: device })).status, 400);
  ctx.sipServer.registrations.set('phone1', { expires: Date.now() + 60000 });
  const allowed = (await call('/api/contacts/phone1/availability', { headers: device })).json();
  assert.equal(allowed.online, true);
  assert.equal(allowed.can_call, true);
  assert.equal(allowed.ring_timeout, store.ringTimeout('phone1'));
  store.deleteGroup('family');
  const denied = (await call('/api/contacts/phone1/availability', { headers: device })).json();
  assert.deepEqual(denied, {
    id: 'phone1',
    online: false,
    presence: 'offline',
    can_call: false,
    ring_timeout: 60,
  });
  for (const value of [
    {},
    { settings: [], expected: {} },
    { settings: {}, expected: [] },
    { settings: {}, expected: {}, terminal_id: 'forged' },
  ])
    assert.equal(
      (await call('/api/device/settings', { method: 'POST', headers: device, value })).status,
      400,
    );
});

test('Host, Origin, cookie mutations and HTTPS policy reject before dispatch', async (t) => {
  t.mock.method(os, 'networkInterfaces', () => lanInterfaces);
  const { ctx, call, device } = fixture(t);
  assert.equal((await call('/health', { headers: { host: 'attacker:8080' } })).status, 403);
  assert.equal((await call('/health', { headers: { origin: 'https://elsewhere' } })).status, 403);
  const cookie = `zmala-admin=${ctx.adminSessions.create()}`;
  assert.equal(
    (await call('/api/auth/logout', { method: 'POST', headers: { cookie } })).status,
    403,
  );
  assert.equal(
    (
      await call('/api/auth/logout', {
        method: 'POST',
        headers: { cookie, origin: 'http://127.0.0.1:8080' },
      })
    ).status,
    200,
  );
  ctx.requireSecureAdmin = true;
  const socket = { remoteAddress: '192.168.1.20', localAddress: '192.168.1.10' };
  assert.equal((await call('/api/auth/status', { socket })).status, 403);
  assert.equal(
    (await call('/api/auth/status', { socket: { ...socket, encrypted: true } })).status,
    200,
  );
  assert.equal((await call('/api/config', { socket, headers: device })).status, 200);
});

test('admin network matches the receiving private subnet and fails closed', () => {
  for (const peer of ['192.168.1.20', '::ffff:192.168.1.20'])
    assert.equal(
      localAdmin({ remoteAddress: peer, localAddress: '::ffff:192.168.1.10' }, lanInterfaces),
      true,
    );
  for (const peer of ['192.168.2.20', '10.0.0.2', '203.0.113.2', '', 'invalid'])
    assert.equal(
      localAdmin({ remoteAddress: peer, localAddress: '192.168.1.10' }, lanInterfaces),
      false,
      peer,
    );
  assert.equal(localAdmin({ remoteAddress: '192.168.1.20' }, lanInterfaces), false);
  assert.equal(
    localAdmin({ remoteAddress: '192.168.1.20', localAddress: '192.168.1.10' }, {}),
    false,
  );
  for (const peer of ['127.0.0.1', '::1', '::ffff:127.0.0.1'])
    assert.equal(localAdmin({ remoteAddress: peer }, {}), true);
  const ipv6 = { eth0: [{ address: 'fd12:3456::1', cidr: 'fd12:3456::1/64', internal: false }] };
  assert.equal(
    localAdmin({ remoteAddress: 'fd12:3456::2', localAddress: 'fd12:3456::1' }, ipv6),
    true,
  );
  assert.equal(
    localAdmin({ remoteAddress: 'fd12:3457::2', localAddress: 'fd12:3456::1' }, ipv6),
    false,
  );
  assert.equal(
    localAdmin({ remoteAddress: '2001:db8::2', localAddress: 'fd12:3456::1' }, ipv6),
    false,
  );
});

test('remote HTTPS blocks admin UI, authentication and APIs even with a valid session', async (t) => {
  t.mock.method(os, 'networkInterfaces', () => lanInterfaces);
  const { call, admin, device, ctx, store } = fixture(t);
  const socket = { remoteAddress: '203.0.113.2', localAddress: '192.168.1.10', encrypted: true };
  for (const route of [
    '/',
    '/accounts',
    '/permissions',
    '/admin.js',
    '/admin.css',
    '/zmala-icon.svg',
    '/api/auth/status',
    '/api/admin',
    '/api/backups/export',
    '/api/users',
  ]) {
    for (const credential of [
      admin,
      device,
      { cookie: `zmala-admin=${ctx.adminSessions.create()}` },
    ])
      assert.equal(
        (
          await call(route, {
            socket,
            headers: {
              ...credential,
              'x-forwarded-for': '192.168.1.20',
              forwarded: 'for=127.0.0.1',
            },
          })
        ).status,
        403,
        route,
      );
  }
  for (const route of ['/api/auth/login', '/api/auth/setup', '/api/auth/password', '/api/users'])
    assert.equal(
      (await call(route, { socket, method: 'POST', headers: admin, value: {} })).status,
      403,
      route,
    );
  assert.equal((await call('/api/config', { socket, headers: device })).status, 200);
  const app = { authorization: `Bearer ${store.value.users.phone1.device_token}` };
  assert.equal((await call('/api/app/config', { socket, headers: app })).status, 200);
  fs.mkdirSync(path.join(store.dir, 'photos'), { recursive: true });
  fs.writeFileSync(path.join(store.dir, 'photos/abcd.png'), 'portrait-fixture');
  assert.equal((await call('/photos/abcd.png', { socket, headers: app })).status, 200);
  assert.equal((await call('/photos/abcd.png', { socket, headers: admin })).status, 401);
  assert.equal((await call('/api/config', { socket, headers: admin })).status, 401);
  assert.equal((await call('/health', { socket })).status, 200);
  assert.equal((await call('/ready', { socket })).status, 200);
  assert.equal(
    (await call('/api/auth/status', { socket: { ...socket, remoteAddress: '192.168.1.20' } }))
      .status,
    200,
  );
});

test('private endpoints reject device tokens while health stays minimal and security headers apply', async (t) => {
  const { call, device, ctx, admin } = fixture(t);
  ctx.sipServer.status = () => ({ calls: [{ id: 'fixture' }], events: ['fixture event'] });
  for (const path of [
    '/api/admin',
    '/api/admin/live',
    '/api/terminal-bootstrap?id=term1',
    '/api/terminals/term1/console',
  ])
    assert.equal((await call(path, { headers: device })).status, 401, path);
  assert.equal(
    (
      await call('/api/terminals/term1/console', {
        method: 'POST',
        headers: device,
        value: { command: 'true' },
      })
    ).status,
    401,
  );
  assert.equal((await call('/api/config', { headers: admin })).status, 401);
  assert.equal((await call('/photos/abcd.png')).status, 401);
  assert.equal((await call('/photos/abcd.png', { headers: device })).status, 404);
  const publicState = await call('/health');
  assert.deepEqual(publicState.json(), { ok: true });
  assert.equal(publicState.headers['Cache-Control'], 'no-store');
  assert.equal(publicState.headers['X-Content-Type-Options'], 'nosniff');
  assert.match(publicState.headers['Content-Security-Policy'], /frame-ancestors 'none'/);
  assert.equal(publicState.headers['Referrer-Policy'], 'no-referrer');
  assert.equal(
    (await call('/api/admin/live', { headers: admin })).json().sip_status.calls[0].id,
    'fixture',
  );
  assert.equal(
    (await call('/api/terminal-bootstrap?id=term1', { headers: admin })).json().device_id,
    'windows-terminal',
  );
});

test('JSON object validation and byte limits reject at the boundary', async () => {
  for (const value of ['{', '[]', 'null', '"string"', 'true'])
    await assert.rejects(readJson(request('/', { value }), 32), { status: 400 });
  assert.deepEqual(await readJson(request('/', { value: '{}' }), 2), {});
  await assert.rejects(readJson(request('/', { value: '{ }' }), 2), { status: 413 });
});

test('delta polling refreshes presence and callbacks at an unchanged revision', async (t) => {
  const { store, ctx, call, device } = fixture(t);
  let callbacks = [{ id: 'pending', from: 'phone1', to: 'term1', status: 'pending' }];
  ctx.callbacks.list = (id) => {
    assert.equal(id, 'term1');
    return callbacks;
  };
  const version = store.value.configuration_version;
  const route = `/api/config?delta=1&version=${version}`;
  assert.equal((await call(route, { headers: device })).json().live.contacts[0].online, false);
  ctx.sipServer.registrations.set('phone1', { expires: Date.now() + 60000 });
  const delta = (await call(route, { headers: device })).json();
  assert.equal(delta.configuration_version, version);
  assert.equal(delta.live.contacts[0].online, true);
  assert.deepEqual(delta.live.callbacks, callbacks);
  callbacks = [];
  assert.deepEqual((await call('/api/config', { headers: device })).json().callbacks, []);
  assert.equal(store.value.configuration_version, version);
});

test('idempotent local writes and completed results still await persistence before acknowledgement', async (t) => {
  const { store, ctx, call, device } = fixture(t);
  let release,
    finished = false;
  store.flush = () =>
    new Promise((resolve) => {
      release = resolve;
    });
  const version = store.value.configuration_version;
  const pending = call('/api/device/settings', {
    method: 'POST',
    headers: device,
    value: { settings: { language: 'en' }, expected: { language: 'en' } },
  }).then((r) => {
    finished = true;
    return r;
  });
  await new Promise(setImmediate);
  assert.equal(finished, false);
  assert.equal(store.value.configuration_version, version);
  release();
  assert.equal((await pending).status, 200);
  let flushes = 0;
  ctx.consoleJobs.finish = (id, job, result) => {
    assert.equal(id, 'term1');
    assert.equal(result.lease, 'test');
    return { ok: true };
  };
  ctx.consoleJobs.flush = async () => {
    flushes++;
  };
  const route = '/api/console/result/11111111-1111-1111-1111-111111111111';
  for (let n = 0; n < 2; n++)
    assert.equal(
      (await call(route, { method: 'POST', headers: device, value: { lease: 'test' } })).status,
      200,
    );
  assert.equal(flushes, 2);
  assert.equal(
    (await call(route, { method: 'POST', headers: device, value: ' '.repeat(400001) })).status,
    413,
  );
});

test('accepted status is device scoped and server timestamped; rejected updates preserve it', async (t) => {
  const { ctx, call, device } = fixture(t);
  const accepted = {
    state: 'HOME',
    registered: true,
    configuration_version: 4,
    devices: { camera: ['C20'] },
    last_seen: 'spoofed',
    remote_status: 'connected',
    remote_battery: 75,
    remote_charger_connected: true,
    camera_status: 'connected',
    camera_powered: true,
    camera_connected: true,
    media: {
      video: { received_fps: 20, received_resolution: [480, 480] },
      codecs: {
        decoder: { input_queued: 0, output_queued: 1, dropped: 2, produced: 30 },
      },
    },
  };
  assert.equal(
    (await call('/api/status', { method: 'POST', headers: device, value: accepted })).status,
    200,
  );
  const saved = ctx.terminalStatuses.term1;
  assert.notEqual(saved.last_seen, 'spoofed');
  assert.equal(saved.remote_battery, 75);
  assert.equal(saved.remote_charger_connected, true);
  assert.equal(saved.camera_powered, true);
  assert.deepEqual(saved.media, accepted.media);
  const copied = terminalStatus(accepted);
  assert.notEqual(copied.media, accepted.media);
  assert.deepEqual(terminalStatus({ media: {} }).media, {});
  assert.deepEqual(terminalStatus({ media: { unknown: 3 } }).media, {});
  for (const media of [
    null,
    [],
    { video: [] },
    { audio: { upload_kbps: Infinity } },
    { video: { received_fps: -1 } },
    { video: { received_resolution: [0, 480] } },
    { codecs: [] },
    { codecs: { encoder: null } },
    { codecs: { decoder: { dropped: 1.5 } } },
  ])
    assert.throws(() => terminalStatus({ media }));
  const unknown = terminalStatus({
    remote_status: 'unknown',
    remote_battery: null,
    remote_charger_connected: null,
    camera_connected: null,
    camera_powered: null,
    camera_status: 'unknown',
  });
  assert.equal(unknown.remote_battery, null);
  assert.equal(unknown.camera_powered, null);
  assert.ok(Number.isFinite(Date.parse(saved.last_seen)));
  for (const invalid of [
    { state: [] },
    { registered: 'yes' },
    { remote_status: 'invented' },
    { camera_status: [] },
    { camera_status: 'ready-but-unknown' },
    { remote_battery: true },
    { remote_battery: -1 },
    { remote_battery: 101 },
    { remote_battery: 4.5 },
    { remote_charger_connected: 'yes' },
    { camera_powered: 1 },
    { camera_connected: 'yes' },
    { configuration_version: -1 },
    { devices: [] },
    { media: { video: { received_fps: '20' } } },
    { devices: { camera: [1] } },
    { devices: { camera: Array(101).fill('C20') } },
  ]) {
    assert.throws(() => terminalStatus(invalid));
    assert.equal(
      (await call('/api/status', { method: 'POST', headers: device, value: invalid })).status,
      400,
    );
    assert.equal(ctx.terminalStatuses.term1, saved);
  }
  assert.equal(
    (await call('/api/status', { method: 'POST', headers: device, value: ' '.repeat(32001) }))
      .status,
    413,
  );
  assert.equal(ctx.sipServer.registrations.size, 0);
});

test('readiness tracks persistence failure independently of process liveness', async (t) => {
  const { ctx, call } = fixture(t);
  ctx.persistenceReady = () => false;
  assert.equal((await call('/health')).status, 200);
  assert.equal((await call('/ready')).status, 503);
  ctx.persistenceReady = () => true;
  assert.equal((await call('/ready')).status, 200);
});

test('reassociation during an active call is rejected before any ownership mutation', async (t) => {
  const { store, ctx, call, admin } = fixture(t);
  store.createAccount({
    id: 'second',
    name: 'Second',
    type: 'terminal',
    emails: ['a@example.test'],
  });
  const before = JSON.stringify(store.value);
  ctx.sipServer.dialogs.set('call', { peers: [{ user: 'term1' }, { user: 'phone1' }] });
  assert.equal(
    (
      await call('/api/terminal-association', {
        method: 'PUT',
        headers: admin,
        value: { serial_number: 'windows-terminal', account_id: 'second' },
      })
    ).status,
    409,
  );
  assert.equal(JSON.stringify(store.value), before);
});

test('contact presence distinguishes live activity, push eligibility and offline without changing revision', async (t) => {
  const { store, ctx, call, device } = fixture(t);
  const version = store.value.configuration_version;
  let push = false;
  ctx.sipServer.appCalls = { push: { available: (id) => id === 'phone1' && push } };
  for (const [presence, registration, canPush] of [
    ['offline', undefined, false],
    ['push', undefined, true],
    ['available', { expires: Date.now() + 60000 }, true],
    ['push', { expires: Date.now() + 60000, reachable: false }, true],
    ['offline', { expires: Date.now() - 1 }, false],
  ]) {
    push = canPush;
    ctx.sipServer.registrations.delete('phone1');
    if (registration) ctx.sipServer.registrations.set('phone1', registration);
    const full = (await call('/api/config', { headers: device })).json();
    const delta = (
      await call(`/api/config?delta=1&version=${version}`, { headers: device })
    ).json();
    const check = (await call('/api/contacts/phone1/availability', { headers: device })).json();
    for (const contact of [
      full.contacts.find((c) => c.id === 'phone1'),
      delta.live.contacts.find((c) => c.id === 'phone1'),
      check,
    ]) {
      assert.equal(contact.presence, presence);
      assert.equal(contact.online, presence !== 'offline');
    }
    assert.equal(store.value.configuration_version, version);
  }
});

test('push-wake calls protect both accounts from identity edits, deletion and reassociation', async (t) => {
  const { store, ctx, call, admin } = fixture(t);
  store.createAccount({
    id: 'second',
    name: 'Second',
    type: 'terminal',
    emails: ['a@example.test'],
  });
  ctx.sipServer.appCalls = { busy: (id) => ['term1', 'phone1'].includes(id) };
  const before = JSON.stringify(store.value);
  for (const id of ['term1', 'phone1']) {
    assert.equal(
      (await call(`/api/users/${id}`, { method: 'DELETE', headers: admin })).status,
      409,
    );
    assert.equal(
      (
        await call(`/api/users/${id}`, {
          method: 'PUT',
          headers: admin,
          value: { id: 'renamed', name: 'Renamed', type: store.value.users[id].type },
        })
      ).status,
      409,
    );
  }
  assert.equal(
    (
      await call('/api/terminal-association', {
        method: 'PUT',
        headers: admin,
        value: { serial_number: 'windows-terminal', account_id: 'second' },
      })
    ).status,
    409,
  );
  assert.equal(JSON.stringify(store.value), before);
});
