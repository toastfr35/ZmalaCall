// @test S-LLT-028
// @requirements SLLR002, SLLR003, SLLR083, SLLR101, SLLR102
// @environment portable
// @plan Load the real composition module with fake listeners and snapshot writers; assert default/overridden binds, optional TLS certificate checks, IPv4 advertised-host validation and revision persistence. Fail one bootstrap writer to prove per-file failure propagation without claiming a multi-file transaction.
// @pass Startup must bind only the requested listeners, invalid configuration must fail, and write failures must propagate while already completed independent files remain completed.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');
const { storeFixture } = require('../../support/server/unit-fixture');

function fixture(t, env = {}) {
  const store = storeFixture(t),
    calls = [],
    writers = [];
  const file = path.resolve(__dirname, '../../../zmala_server/main.js');
  const nativeRequire = createRequire(file);
  const listener = (kind) => ({
    on() {},
    listen(port, address) {
      calls.push([kind, port, address]);
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
    './shutdown': { createShutdown: () => async () => {} },
    './http/handler': {
      createHandler: (options) => {
        calls.push(['handler', options.requireSecureAdmin]);
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
  vm.runInNewContext(fs.readFileSync(file, 'utf8'), {
    require,
    module,
    __dirname: path.dirname(file),
    process: {
      env,
      once() {},
      exit() {
        assert.fail('unexpected exit');
      },
    },
    console: { log() {}, error() {} },
  });
  return { ...module.exports, store, calls, writers };
}

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
