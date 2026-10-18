// @test S-LLT-028
// @requirements LLR-SRV-START-005, LLR-SRV-START-006, LLR-SRV-START-007, LLR-SRV-START-008, LLR-SRV-ENROLL-005, LLR-SRV-DATA-014, LLR-SRV-DATA-015, LLR-SRV-BACKUP-007, LLR-SRV-BACKUP-008
// @environment portable
// @plan Load the real composition module with fake listeners and snapshot writers; assert default/overridden binds, optional TLS certificate checks, IPv4 advertised-host validation and revision persistence. Fail one bootstrap writer to prove per-file failure propagation without claiming a multi-file transaction. Trigger listener, shutdown and restore-restart failures with recording process hooks; verify drain-before-exit, failure codes and readiness tracking of failed writers.
// @pass Startup must bind only the requested listeners, invalid configuration must fail, and write failures must propagate while already completed independent files remain completed.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('../../../build_tools/coverage-js.cjs');
const { createRequire } = require('node:module');
const { storeFixture } = require('../../support/server/unit-fixture');

function fixture(t, env = {}, hooks = {}) {
  const store = storeFixture(t),
    calls = [],
    writers = [];
  const file = path.resolve(__dirname, '../../../zmala_server/main.js');
  const nativeRequire = createRequire(file);
  const signals = {},
    errors = {},
    handlers = [],
    exits = [],
    logs = [];
  const process = {
    env,
    once(name, callback) {
      signals[name] = callback;
    },
    exit(code) {
      exits.push(code);
    },
  };
  const listener = (kind) => ({
    on(name, callback) {
      errors[kind] = callback;
    },
    listen(port, address, ready) {
      calls.push([kind, port, address]);
      if (hooks.listenFailure) throw hooks.listenFailure;
      ready?.();
    },
  });
  const sip = {
    dialogs: new Map(),
    start() {
      calls.push(['sip', store.value.sip_port]);
    },
  };
  class Snapshot {
    constructor(file) {
      this.file = file;
      writers.push(this);
    }
    async write(value) {
      this.value = value;
      if (this.failed) throw Error('fixture disk failure');
    }
    async flush() {
      if (this.failed) throw Error('fixture disk failure');
    }
  }
  class Background {
    enableAsyncPersistence() {}
    async flush() {}
  }
  const shutdown = async () => {
    calls.push(['shutdown']);
    if (hooks.shutdownFailure) throw hooks.shutdownFailure;
  };
  const overrides = {
    './store': {
      Store: function () {
        return store;
      },
      DATA: 'unused-default-store',
    },
    './sip-server': {
      SipServer: function () {
        return sip;
      },
    },
    './snapshot-file': { SnapshotFile: Snapshot },
    './callbacks': { Callbacks: Background },
    './console-jobs': { ConsoleJobs: Background },
    './backup-storage': { recoverRestore: async () => {} },
    './admin-password': { passwordFile: () => 'unused' },
    './shutdown': { createShutdown: () => shutdown },
    './backups': {
      ServerBackups: function (...args) {
        this.restart = args.at(-1);
        hooks.backups = this;
      },
    },
    './http/handler': {
      createHandler: (options) => {
        calls.push(['handler', options.requireSecureAdmin]);
        handlers.push(options);
        return () => {};
      },
    },
    '../build_tools/build-admin.cjs': { buildAdmin() {} },
    'node:http': { createServer: () => listener('http') },
    'node:https': {
      createServer: (options) => {
        calls.push(['tls', String(options.cert), String(options.key)]);
        return listener('https');
      },
    },
  };
  const module = { exports: {} };
  const require = (name) => overrides[name] || nativeRequire(name);
  vm.runInNewContext(vm.source(file), {
    Error,
    require,
    module,
    __dirname: path.dirname(file),
    process,
    console: {
      log(...args) {
        logs.push(args);
      },
      error(...args) {
        logs.push(args);
      },
    },
  });
  return {
    ...module.exports,
    store,
    calls,
    writers,
    signals,
    errors,
    handlers,
    exits,
    logs,
    process,
  };
}

test('listener and signal failures drain the application and report failure without leaving a sibling running', async (t) => {
  for (const failure of [Error('bind failed'), 'unknown listener failure']) {
    const a = fixture(t, {}, { listenFailure: failure });
    await a.start();
    assert.equal(a.process.exitCode, 1);
    assert.ok(a.calls.some((c) => c[0] === 'shutdown'));
    await a.signals.SIGTERM();
    assert.deepEqual(a.exits, [1]);
  }
  const a = fixture(t);
  await a.start();
  a.errors.http(Error('socket closed'));
  await Promise.resolve();
  assert.equal(a.process.exitCode, 1);
  assert.ok(a.logs.some((c) => c[0] === 'socket closed'));
  const failed = fixture(t, {}, { shutdownFailure: Error('save failed') });
  await failed.start();
  failed.errors.http(Error('bind failed'));
  await Promise.resolve();
  assert.ok(failed.logs.some((c) => c[0] === 'Could not finish shutdown:'));
  await failed.signals.SIGINT();
  assert.deepEqual(failed.exits, [1]);
  assert.ok(failed.logs.some((c) => c[1] === 'save failed'));
  const clean = fixture(t);
  await clean.start();
  await clean.signals.SIGINT();
  assert.deepEqual(clean.exits, [0]);
});

test('restore restart drains persistence before exit and persistence readiness follows every writer', async (t) => {
  for (const shutdownFailure of [null, Error('flush failed')]) {
    const hooks = { shutdownFailure },
      a = fixture(t, {}, hooks);
    await a.start();
    assert.equal(a.handlers[0].persistenceReady(), true);
    a.writers[0].failed = true;
    assert.equal(a.handlers[0].persistenceReady(), false);
    hooks.backups.restart();
    await Promise.resolve();
    assert.deepEqual(a.exits, [shutdownFailure ? 1 : 75]);
    assert.equal(a.calls.at(-1)[0], 'shutdown');
  }
});

test('default/overridden ports and advertised address persist a single changed revision', async (t) => {
  const a = fixture(t, { VIDEOCALL_HOST: '192.0.2.44' }),
    before = a.store.value.configuration_version;
  await a.start();
  assert.ok(a.calls.some((c) => c[0] === 'http' && c[1] === 8080 && c[2] === '0.0.0.0'));
  assert.ok(a.calls.some((c) => c[0] === 'sip' && c[1] === 5060));
  assert.equal(a.store.value.host, '192.0.2.44');
  assert.equal(a.store.value.configuration_version, before + 1);
  assert.equal(JSON.parse(fs.readFileSync(a.store.file)).host, '192.0.2.44');
  a.store.value.http_port = 8089;
  a.store.value.sip_port = 5090;
  await a.start();
  assert.ok(a.calls.some((c) => c[0] === 'http' && c[1] === 8089));
  assert.ok(a.calls.some((c) => c[0] === 'sip' && c[1] === 5090));
  assert.equal(a.store.value.configuration_version, before + 1);
  for (const host of ['example.test', '::1', '999.1.1.1'])
    await assert.rejects(fixture(t, { VIDEOCALL_HOST: host }).start(), /IPv4/);
});

test('TLS requires certificate/key and separate valid port then binds on all IPv4', async (t) => {
  await assert.rejects(fixture(t, { ZMALA_TLS_CERT: 'missing' }).start(), /both/);
  for (const port of ['8080', '0', '65536', 'invalid'])
    await assert.rejects(
      fixture(t, { ZMALA_TLS_CERT: 'cert', ZMALA_TLS_KEY: 'key', ZMALA_HTTPS_PORT: port }).start(),
      /separate/,
    );
  const a = fixture(t),
    cert = path.join(a.store.dir, 'test-cert'),
    key = path.join(a.store.dir, 'test-key');
  fs.writeFileSync(cert, 'certificate fixture');
  fs.writeFileSync(key, 'key fixture');
  const secure = fixture(t, { ZMALA_TLS_CERT: cert, ZMALA_TLS_KEY: key, ZMALA_HTTPS_PORT: '8444' });
  await secure.start();
  assert.ok(secure.calls.some((c) => c[0] === 'handler' && c[1] === true));
  assert.ok(secure.calls.some((c) => c[0] === 'https' && c[1] === 8444 && c[2] === '0.0.0.0'));
});

test('bootstrap follows selected identity and independent file failure is propagated', async (t) => {
  const a = fixture(t),
    app = a.createApplication({ store: a.store });
  a.store.value.local_terminal_id = null;
  await app.writeBootstrap();
  assert.equal(JSON.parse(a.writers[0].value).device_token, '');
  a.writers[0].failed = true;
  a.store.value.host = '192.0.2.1';
  a.store.changed();
  await assert.rejects(app.writeBootstrap(), /disk failure/);
  await a.store.flush();
  assert.equal(JSON.parse(fs.readFileSync(a.store.file)).host, '192.0.2.1');
  await assert.rejects(app.flush(), /disk failure/);
});
