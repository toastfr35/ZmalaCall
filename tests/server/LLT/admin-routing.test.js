// @test S-LLT-034
// @requirements LLR-SRV-DIR-025, LLR-SRV-DIR-026, LLR-SRV-DIR-027, LLR-SRV-DIR-029, LLR-SRV-CONFIG-023, LLR-SRV-ENROLL-004, LLR-SRV-ENROLL-005, LLR-SRV-MAINT-013, LLR-SRV-MAINT-017, LLR-SRV-MAINT-020, LLR-SRV-HOST-004
// @environment portable
// @plan Dispatch real admin routes with bounded in-memory HTTP streams and recording store/SIP/persistence boundaries. Verify revision conflicts precede mutations, including account creation with a stale opening revision, active-call guards, rename/reassociation cleanup and durable flush-before-response. Check requester retirement only on type conversion and command reconciliation before acknowledgement. Check console cancellation/admission, selected bootstrap/QR ownership, live views and SSH toggle delegation. Central authentication, PDF layout and store validation have separate tests. Inject SSH helper outcomes to verify supported-target checks, single-change admission, bounded subprocess calls, post-change state validation and unlock after failures.
// @pass Routing arguments and ordering assertions pass; rejected updates cannot mutate state or acknowledge success and disk failures cannot emit HTTP 200.
'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { Readable } = require('node:stream');
const { createRequire } = require('node:module');
const path = require('node:path');
const vm = require('../../../build_tools/coverage-js.cjs');

test('SSH adapter validates state, serializes changes and unlocks after failure', async () => {
  const file = path.resolve(__dirname, '../../../zmala_server/server-ssh.js');
  const module = { exports: {} },
    calls = [];
  let supported = false,
    output = '{"enabled":true,"active":true}',
    pending;
  const execute = (...args) => {
    calls.push(args);
    if (output === 'pending')
      return new Promise((resolve, reject) => {
        pending = { resolve, reject };
      });
    return Promise.resolve({ stdout: output });
  };
  vm.runInNewContext(vm.source(file), {
    module,
    require: (name) =>
      ({
        'node:fs': { existsSync: () => supported },
        'node:child_process': { execFile() {} },
        'node:util': { promisify: () => execute },
      })[name],
  });
  const { sshStatus, setSsh } = module.exports;
  assert.equal((await sshStatus()).supported, false);
  await assert.rejects(setSsh('on'), /true or false/);
  await assert.rejects(setSsh(true), /installed Pi/);
  assert.equal(calls.length, 0);
  supported = true;
  assert.equal((await sshStatus()).enabled, true);
  assert.equal(calls.at(-1)[0], '/usr/bin/python3');
  assert.equal(calls.at(-1)[2].timeout, 10000);
  output = 'pending';
  const first = setSsh(true);
  await assert.rejects(setSsh(false), /in progress/);
  pending.reject(Error('helper failed'));
  await assert.rejects(first, /helper failed/);
  output = '{"enabled":false,"active":false}';
  assert.equal((await setSsh(false)).active, false);
  assert.equal(calls.at(-1)[1].at(-1), 'off');
  assert.equal(calls.at(-1)[2].timeout, 60000);
  await assert.rejects(setSsh(true), /did not match/);
  output = 'invalid';
  await assert.rejects(setSsh(false), /JSON/);
  output = '{"enabled":true,"active":true}';
  assert.equal((await setSsh(true)).active, true);
});

function fixture() {
  const calls = [];
  const fn =
    (name, value) =>
    (...args) => {
      calls.push([name, ...args]);
      return typeof value === 'function' ? value(...args) : value;
    };
  const bootstrap = { server_url: 'http://pi:8080', device_id: 'serial', device_token: 'secret' };
  const store = {
    enrolledAccount: () => ({ type: 'terminal' }),
    value: {
      configuration_version: 7,
      users: {
        alice: { type: 'phone', password: 'old' },
        term1: { name: 'First' },
        term2: { name: 'Second' },
      },
      profiles: { term1: {}, term2: {} },
      local_terminal_id: 'term1',
    },
  };
  for (const name of [
    'flush',
    'requireTerminal',
    'setSmtpSettings',
    'updateGroup',
    'deleteGroup',
    'associateTerminal',
    'setSettings',
    'deleteAccount',
    'selectTerminal',
  ])
    store[name] = fn(name);
  store.admin = fn('admin', { users: 'private admin view' });
  store.bootstrap = fn('bootstrap', bootstrap);
  store.terminalAccount = fn('terminalAccount', (id) => ({
    device_id: id === 'term1' ? 'serial' : 'second',
  }));
  store.createGroup = fn('createGroup', 'group');
  store.createAccount = fn('createAccount', 'created');
  store.updateAccount = fn('updateAccount', (id, update) => update.id || id);
  const callbacks = {},
    consoleJobs = {};
  for (const name of [
    'flush',
    'list',
    'updateSettings',
    'deliver',
    'cancel',
    'rename',
    'reconcile',
  ])
    callbacks[name] = fn('callback.' + name, name === 'list' ? ['pending'] : undefined);
  callbacks.email = { mailer: { verify: fn('verifySMTP') } };
  for (const name of ['flush', 'list', 'create', 'cancel', 'rename', 'swapTerminals', 'expire'])
    consoleJobs[name] = fn('console.' + name, name === 'create' ? { id: 'job' } : []);
  const sipServer = {
    dialogs: new Map(),
    registrations: new Map([
      ['alice', {}],
      ['term1', {}],
      ['term2', {}],
    ]),
    cancelProbe: fn('cancelProbe'),
    status: fn('status', { calls: ['live'] }),
  };
  const context = {
    store,
    callbacks,
    consoleJobs,
    sipServer,
    terminalStatuses: { alice: {}, term1: {}, term2: {} },
    writeBootstrap: fn('writeBootstrap'),
  };
  const file = path.resolve(__dirname, '../../../zmala_server/http/admin-routes.js');
  const nativeRequire = createRequire(file);
  const scope = {
    module: { exports: {} },
    URL,
    Buffer,
    require: (name) => {
      if (name === '../setup-pdf')
        return {
          wifiPayload: fn('wifiPayload', 'wifi'),
          serverPayload: fn('serverPayload', 'server'),
          setupPdf: fn('setupPdf', Buffer.from('%PDF')),
        };
      if (name === '../server-ssh')
        return {
          sshStatus: fn('sshStatus', { enabled: true }),
          setSsh: fn('setSsh', { enabled: false }),
        };
      return nativeRequire(name);
    },
  };
  vm.runInNewContext(vm.source(file), scope);
  async function request(method, route, body) {
    const req = Readable.from(body === undefined ? [] : [Buffer.from(JSON.stringify(body))]);
    req.method = method;
    const res = {
      status: 0,
      headers: {},
      writeHead(status, headers) {
        this.status = status;
        Object.assign(this.headers, headers);
      },
      setHeader(name, value) {
        this.headers[name] = value;
      },
      end(body) {
        this.body = body;
        calls.push(['response', this.status]);
      },
    };
    res.handled = await scope.module.exports.adminRoutes(
      req,
      res,
      new URL(route, 'http://server'),
      context,
    );
    return res;
  }
  return { context, calls, request };
}

test('account creation checks the opening revision before publishing or writing bootstrap', async () => {
  const f = fixture();
  const candidate = { id: 'newperson', configuration_version: 6 };
  await assert.rejects(f.request('POST', '/api/users', candidate), (error) => error.status === 409);
  assert.deepEqual(f.calls, [], 'A stale create must not invoke any mutation or persistence hook');
  for (const version of [7, undefined]) {
    f.calls.length = 0;
    const response = await f.request('POST', '/api/users', {
      ...candidate,
      configuration_version: version,
    });
    assert.equal(response.status, 201);
    assert.deepEqual(
      f.calls.map((call) => call[0]),
      ['createAccount', 'writeBootstrap', 'flush', 'response'],
    );
  }
});

test('live/admin snapshots and bootstrap use the selected terminal and private route', async () => {
  const f = fixture();
  assert.deepEqual(JSON.parse((await f.request('GET', '/api/admin/live')).body).sip_status.calls, [
    'live',
  ]);
  assert.equal(JSON.parse((await f.request('GET', '/api/admin')).body).users, 'private admin view');
  await f.request('GET', '/api/terminal-bootstrap?id=term2');
  assert.ok(f.calls.some((c) => c[0] === 'requireTerminal' && c[1] === 'term2'));
  assert.ok(f.calls.some((c) => c[0] === 'bootstrap' && c[1] === 'term2' && c[2] === true));
  await f.request('PUT', '/api/local-terminal', { id: 'term2' });
  assert.deepEqual(
    f.calls.slice(-4).map((c) => c[0]),
    ['selectTerminal', 'writeBootstrap', 'flush', 'response'],
  );
  await assert.rejects(f.request('PUT', '/api/local-terminal', { id: 7 }), /Choose a terminal/);
  assert.equal((await f.request('PATCH', '/unknown')).handled, false);
});

test('revision conflicts reject all editable drafts before any mutation', async () => {
  for (const route of [
    '/api/groups',
    '/api/groups/family',
    '/api/settings',
    '/api/smtp-settings',
    '/api/callback-settings',
    '/api/users/alice',
    '/api/terminal-association',
  ]) {
    const f = fixture();
    await assert.rejects(
      f.request(route === '/api/groups' ? 'POST' : 'PUT', route, { configuration_version: 6 }),
      { status: 409 },
    );
    assert.deepEqual(f.calls, []);
  }
});

test('group and settings mutations flush before acknowledgement, including failures', async () => {
  for (const [method, route, name] of [
    ['POST', '/api/groups', 'createGroup'],
    ['PUT', '/api/groups/family', 'updateGroup'],
    ['DELETE', '/api/groups/family', 'deleteGroup'],
    ['PUT', '/api/settings', 'setSettings'],
  ]) {
    const f = fixture();
    const res = await f.request(method, route, { configuration_version: 7 });
    assert.equal(f.calls[0][0], name);
    assert.deepEqual(
      f.calls.slice(-2).map((c) => c[0]),
      ['flush', 'response'],
    );
    assert.equal(res.status, method === 'POST' ? 201 : 200);
  }
  const f = fixture();
  await assert.rejects(f.request('PUT', '/api/settings', { terminal_id: 22 }), /Choose a terminal/);
  f.context.store.flush = async () => {
    throw Error('disk failure');
  };
  await assert.rejects(f.request('PUT', '/api/settings', {}), /disk failure/);
  assert.ok(!f.calls.some((c) => c[0] === 'response'));
});

test('active-call account changes are blocked; rename preserves dependent ownership', async () => {
  for (const [method, update] of [
    ['DELETE', {}],
    ['PUT', { type: 'phone', password: 'new' }],
    ['PUT', { type: 'terminal' }],
  ]) {
    const f = fixture();
    f.context.sipServer.dialogs.set('call', { peers: [{ user: 'alice' }] });
    await assert.rejects(f.request(method, '/api/users/alice', update), { status: 409 });
    assert.deepEqual(f.calls, []);
  }
  const f = fixture();
  await f.request('PUT', '/api/users/alice', {
    type: 'phone',
    id: 'renamed',
    configuration_version: 7,
  });
  assert.deepEqual(
    f.calls.slice(0, 6).map((c) => c[0]),
    [
      'updateAccount',
      'console.rename',
      'callback.rename',
      'callback.reconcile',
      'console.expire',
      'cancelProbe',
    ],
  );
  assert.equal(f.context.sipServer.registrations.has('alice'), false);
  assert.equal(f.context.terminalStatuses.alice, undefined);
  assert.deepEqual(
    f.calls.slice(-4).map((c) => c[0]),
    ['flush', 'callback.flush', 'console.flush', 'response'],
  );
  const unchanged = fixture();
  unchanged.context.sipServer.dialogs.set('call', { peers: [{ user: 'alice' }] });
  await unchanged.request('PUT', '/api/users/alice', { type: 'phone', name: 'New name' });
  assert.equal(unchanged.context.sipServer.registrations.has('alice'), true);
  assert.equal(unchanged.calls.find((c) => c[0] === 'callback.reconcile')[1], undefined);
  const converted = fixture();
  await converted.request('PUT', '/api/users/alice', { type: 'terminal', id: 'renamed' });
  assert.deepEqual(
    converted.calls.find((c) => c[0] === 'callback.reconcile'),
    ['callback.reconcile', 'renamed'],
  );
  assert.ok(
    converted.calls.findIndex((c) => c[0] === 'console.expire') <
      converted.calls.findIndex((c) => c[0] === 'console.flush'),
  );
  const deleted = fixture();
  await deleted.request('DELETE', '/api/users/alice');
  assert.equal(deleted.calls[0][0], 'deleteAccount');
  const created = fixture();
  assert.equal((await created.request('POST', '/api/users', { id: 'created' })).status, 201);
});

test('reassociation rejects unknown or busy devices and swaps console ownership once', async () => {
  const f = fixture();
  await assert.rejects(
    f.request('PUT', '/api/terminal-association', { account_id: 5 }),
    /Choose a terminal/,
  );
  await assert.rejects(
    f.request('PUT', '/api/terminal-association', {
      account_id: 'term2',
      serial_number: 'missing',
    }),
    /serial number/,
  );
  f.context.sipServer.dialogs.set('call', { peers: [{ user: 'term1' }] });
  await assert.rejects(
    f.request('PUT', '/api/terminal-association', { account_id: 'term2', serial_number: 'serial' }),
    { status: 409 },
  );
  assert.ok(!f.calls.some((c) => c[0] === 'associateTerminal'));
  f.context.sipServer.dialogs.clear();
  f.calls.length = 0;
  await f.request('PUT', '/api/terminal-association', {
    account_id: 'term2',
    serial_number: 'serial',
  });
  assert.deepEqual(
    f.calls.find((c) => c[0] === 'console.swapTerminals'),
    ['console.swapTerminals', 'term1', 'term2'],
  );
  assert.equal(f.context.sipServer.registrations.has('term1'), false);
  assert.equal(f.context.sipServer.registrations.has('term2'), false);
  const same = fixture();
  await same.request('PUT', '/api/terminal-association', {
    account_id: 'term1',
    serial_number: 'serial',
  });
  assert.ok(!same.calls.some((c) => c[0] === 'console.swapTerminals'));
});

test('console and callbacks route exact IDs, flush their own stores and verify SMTP', async () => {
  const id = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
  const f = fixture();
  await f.request('GET', '/api/terminals/term1/console');
  await f.request('POST', '/api/terminals/term1/console', { command: 'uptime' });
  assert.deepEqual(
    f.calls.slice(-2).map((c) => c[0]),
    ['console.flush', 'response'],
  );
  await f.request('DELETE', '/api/terminals/term1/console/' + id);
  assert.deepEqual(
    f.calls.find((c) => c[0] === 'console.cancel'),
    ['console.cancel', 'term1', id],
  );
  await f.request('DELETE', '/api/callbacks/' + id);
  assert.deepEqual(
    f.calls.slice(-3).map((c) => c[0]),
    ['callback.cancel', 'callback.flush', 'response'],
  );
  await f.request('PUT', '/api/callback-settings', { configuration_version: 7 });
  assert.deepEqual(
    f.calls.slice(-4).map((c) => c[0]),
    ['callback.updateSettings', 'flush', 'callback.flush', 'response'],
  );
  await f.request('PUT', '/api/smtp-settings', { configuration_version: 7 });
  assert.deepEqual(
    f.calls.slice(-4).map((c) => c[0]),
    ['setSmtpSettings', 'callback.deliver', 'flush', 'response'],
  );
  await f.request('POST', '/api/smtp-settings/verify');
  assert.ok(f.calls.some((c) => c[0] === 'verifySMTP'));
});

test('setup downloads pass intended terminal payload and SSH routes delegate control', async () => {
  const f = fixture();
  let res = await f.request('GET', '/api/setup/server.pdf?id=term2');
  assert.equal(res.headers['Content-Type'], 'application/pdf');
  assert.match(res.headers['Content-Disposition'], /term2/);
  assert.equal(f.calls.find((c) => c[0] === 'setupPdf')[1].label, 'Second (term2)');
  const rejected = fixture();
  rejected.context.store.enrolledAccount = () => null;
  await assert.rejects(
    rejected.request('GET', '/api/setup/server.pdf?id=unknown'),
    /Choose an app or terminal account/,
  );
  assert.ok(!rejected.calls.some((c) => c[0] === 'setupPdf'));
  res = await f.request('POST', '/api/setup/wifi.pdf', { ssid: 'Network', password: 'private' });
  assert.equal(res.status, 200);
  assert.ok(!f.calls.some((c) => c[0] === 'flush'));
  assert.equal(JSON.parse((await f.request('GET', '/api/server/ssh')).body).enabled, true);
  await f.request('PUT', '/api/server/ssh', { enabled: false });
  assert.deepEqual(
    f.calls.find((c) => c[0] === 'setSsh'),
    ['setSsh', false],
  );
});
