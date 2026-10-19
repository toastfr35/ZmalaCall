// @test S-LLT-023
// @requirements LLR-SRV-BACKUP-003, LLR-SRV-BACKUP-004, LLR-SRV-BACKUP-005, LLR-SRV-BACKUP-006, LLR-SRV-BACKUP-007, LLR-SRV-BACKUP-008, LLR-SRV-BACKUP-009, LLR-SRV-BACKUP-010, LLR-SRV-BACKUP-011, LLR-SRV-BACKUP-012, LLR-SRV-APP-005
// @environment portable
// @plan Use isolated backup maps with fake live services; corrupt versions, schemas, hashes and sizes before decoding, then inject apply/rollback failures into journal recovery. Check unsafe photo types and exact byte/count limits before reading, preserve destinations on failed durable writes, and reject corrupt recovery journals. Check snapshot isolation, restore exclusion gates and revision/network preservation. Dispatch backup routes using bounded byte streams; verify busy gates, archive metadata, explicit restore confirmation, revision forwarding, durable stage before delayed restart and lock release on failure.
// @pass Rejections must leave live files unchanged; accepted snapshots and recovered transactions must match expected state without replaying commands.
// Push-specific assertion scope: exported snapshots omit app-push.json and restore rejects a pending app wake.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');
const { storeFixture } = require('../../support/server/unit-fixture');
const { ServerBackups } = require('../../../zmala_server/backups');
const { hashPassword } = require('../../../zmala_server/admin-sessions');
const {
  decodeBackup,
  encodeBackup,
  digest,
  MAX_BACKUP,
} = require('../../../zmala_server/backup-format');
const {
  recoverRestore,
  atomicWrite,
  readPhotos,
  applyFiles,
  stageRestore,
} = require('../../../zmala_server/backup-storage');
const { Store } = require('../../../zmala_server/store');
const { Readable } = require('node:stream');
const { backupRoutes } = require('../../../zmala_server/http/backup-routes');

test('backup HTTP routes serialize work, validate confirmation and restart after durable staging', async (t) => {
  const app = await fixture(t),
    archive = await app.backups.download();
  const service = {
    busy: false,
    status: () => ({ state: 'ready' }),
    download: async () => archive,
    stage: t.mock.fn(async () => {}),
    restart: t.mock.fn(),
  };
  const context = { backups: service, store: app.store };
  const run = async (method, pathname, bytes = Buffer.alloc(0), headers = {}) => {
    const req = Readable.from([bytes]);
    req.method = method;
    req.headers = headers;
    const res = {
      headers: {},
      setHeader(key, value) {
        this.headers[key] = value;
      },
      writeHead(code, fields) {
        this.code = code;
        Object.assign(this.headers, fields);
      },
      end(value) {
        this.body = value;
      },
    };
    const handled = await backupRoutes(req, res, new URL(pathname, 'http://server'), context);
    return { res, handled };
  };
  assert.equal((await run('GET', '/other')).handled, false);
  context.backups = null;
  await assert.rejects(run('GET', '/api/server/backup'), { status: 503 });
  context.backups = service;
  assert.equal((await run('DELETE', '/api/server/backup')).handled, false);
  service.busy = true;
  assert.equal((await run('GET', '/api/server/backup/status')).res.code, 200);
  await assert.rejects(run('GET', '/api/server/backup'), { status: 409 });
  service.busy = false;
  const download = (await run('GET', '/api/server/backup')).res;
  assert.equal(download.body, archive);
  assert.match(
    download.headers['Content-Disposition'],
    /attachment; filename="zmala-server-.*\.zmala-backup"/,
  );
  assert.equal(download.headers['Content-Type'], 'application/octet-stream');
  const summary = JSON.parse((await run('POST', '/api/server/backup/check', archive)).res.body);
  assert.equal(summary.accounts, Object.keys(app.store.value.users).length);
  assert.equal(summary.pictures, 1);
  await assert.rejects(run('POST', '/api/server/backup/restore', archive), { status: 400 });
  service.stage.mock.resetCalls();
  assert.equal(service.busy, false);
  await assert.rejects(run('POST', '/api/server/backup/check', Buffer.from('corrupt')));
  assert.equal(service.busy, false);
  const headers = { 'x-zmala-confirm-restore': 'replace', 'x-zmala-configuration-version': '77' };
  let restart;
  t.mock.method(global, 'setTimeout', (callback, delay) => {
    assert.equal(delay, 250);
    restart = callback;
    return { unref() {} };
  });
  const restored = await run('POST', '/api/server/backup/restore', archive, headers);
  assert.equal(restored.res.code, 202);
  assert.equal(service.stage.mock.calls[0].arguments[1], 77);
  assert.equal(service.stage.mock.calls[0].arguments[0].files.size, 5);
  assert.equal(service.restart.mock.calls.length, 0);
  restart();
  assert.equal(service.restart.mock.calls.length, 1);
  assert.equal(service.busy, false);
  service.stage = async () => {
    throw Error('journal failure');
  };
  await assert.rejects(
    run('POST', '/api/server/backup/restore', archive, headers),
    /journal failure/,
  );
  assert.equal(service.busy, false);
});

test('snapshot freezes all in-memory records and excludes operational files', async (t) => {
  const app = await fixture(t);
  fs.writeFileSync(path.join(app.directory, 'server.log'), 'private log');
  fs.writeFileSync(path.join(app.directory, 'app-push.json'), '{"private":"push-token"}');
  const before = structuredClone(app.store.value);
  const pending = app.backups.snapshot();
  app.store.value.users.term1.name = 'Changed after snapshot';
  app.callbacks.requests.push({ invalid: 'after snapshot' });
  const files = await pending;
  assert.deepEqual(JSON.parse(files.get('server.json')), before);
  assert.deepEqual(JSON.parse(files.get('callbacks.json')), []);
  assert.deepEqual(
    [...files.keys()].sort(),
    [
      'admin-password.json',
      'callbacks.json',
      'console-jobs.json',
      'photos/' + digest(PNG) + '.png',
      'server.json',
    ].sort(),
  );
  const roundtrip = await decodeBackup(await encodeBackup(files));
  assert.deepEqual(roundtrip.state, before);
});

test('restore gates reject unsafe activity; failed flush reopens service without a journal', async (t) => {
  const app = await fixture(t),
    b = app.backups;
  const backup = await decodeBackup(await b.download()),
    version = app.store.value.configuration_version;
  await assert.rejects(b.stage(backup, version + 1), { status: 409 });
  const gates = [
    [
      () => {
        b.requests = 2;
      },
      () => {
        b.requests = 0;
      },
    ],
    [() => app.sipServer.dialogs.set('call', {}), () => app.sipServer.dialogs.clear()],
    [
      () => {
        app.sipServer.appCalls = { waiting: new Map([['pending', {}]]) };
      },
      () => {
        delete app.sipServer.appCalls;
      },
    ],
    [() => app.callbacks.sending.add('request'), () => app.callbacks.sending.clear()],
    [() => app.callbacks.email.sending.add('email'), () => app.callbacks.email.sending.clear()],
    [
      () => app.consoleJobs.jobs.push({ status: 'running' }),
      () => {
        app.consoleJobs.jobs = [];
      },
    ],
  ];
  for (const [occupy, clear] of gates) {
    occupy();
    await assert.rejects(b.stage(backup, version), { status: 409 });
    clear();
    assert.equal(b.restoring, false);
  }
  b.flush = async () => {
    throw Error('disk failure');
  };
  await assert.rejects(b.stage(backup, version), /disk failure/);
  assert.equal(b.restoring, false);
  assert.equal(app.sipServer.maintenance, false);
  assert.equal(app.callbacks.paused, false);
  assert.equal(fs.existsSync(path.join(app.directory, 'restore-recovery')), false);
});

const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a/A8AAAAASUVORK5CYII=',
  'base64',
);
async function fixture(t) {
  const store = storeFixture(t);
  store.adminPassword.setHash(await hashPassword('Private-backup-test-password'));
  const name = digest(PNG) + '.png';
  fs.mkdirSync(path.join(store.dir, 'photos'));
  fs.writeFileSync(path.join(store.dir, 'photos', name), PNG);
  store.value.users.term1.photo = '/photos/' + name;
  const callbacks = { requests: [], sending: new Set(), email: { sending: new Set() } };
  const consoleJobs = { jobs: [] };
  const sipServer = { dialogs: new Map() };
  const backups = new ServerBackups(
    store,
    callbacks,
    consoleJobs,
    sipServer,
    async () => {},
    () => {},
  );
  return { store, directory: store.dir, backups, callbacks, consoleJobs, sipServer };
}

test('restore rolls back partial application and resumes an interrupted rollback before serving', async (t) => {
  const app = await fixture(t),
    old = await app.backups.snapshot();
  const next = new Map(old),
    state = JSON.parse(next.get('server.json'));
  state.users.term1.name = 'Restored name';
  next.set('server.json', Buffer.from(JSON.stringify(state)));
  await stageRestore(app.directory, old, next);
  let attempts = 0;
  await recoverRestore(app.directory, app.store.adminPassword.file, (dir, password, files) => {
    if (++attempts === 1) {
      fs.writeFileSync(path.join(dir, 'server.json'), files.get('server.json'));
      throw Error('Simulated write failure');
    }
    applyFiles(dir, password, files);
  });
  assert.equal(new Store(app.directory).value.users.term1.name, app.store.value.users.term1.name);
  assert.equal(app.backups.status().result, 'rolled_back');
  await stageRestore(app.directory, old, next);
  await assert.rejects(
    recoverRestore(app.directory, app.store.adminPassword.file, () => {
      throw Error('Disk unavailable');
    }),
  );
  const journal = path.join(app.directory, 'restore-recovery', 'pending.json');
  assert.equal(JSON.parse(fs.readFileSync(journal)).phase, 'rollback');
  await recoverRestore(app.directory, app.store.adminPassword.file);
  assert.equal(fs.existsSync(journal), false);
  assert.equal(new Store(app.directory).value.users.term1.name, app.store.value.users.term1.name);
});

test('decoder rejects corrupt, oversized, unsafe and incomplete backups before changing files', async (t) => {
  const app = await fixture(t),
    files = await app.backups.snapshot();
  const bytes = await encodeBackup(files);
  await assert.rejects(decodeBackup(Buffer.from('not gzip')));
  await assert.rejects(decodeBackup(Buffer.alloc(MAX_BACKUP + 1)));
  await assert.rejects(decodeBackup(zlib.gzipSync(Buffer.alloc(MAX_BACKUP + 1))), /valid Zmala/);
  for (const change of [
    (data) => {
      data.version = 99;
    },
    (data) => {
      data.files[0].name = '../server.json';
    },
    (data) => {
      data.files[0].sha256 = 'invalid';
    },
    (data) => {
      data.files.push(data.files[0]);
    },
    (data) => {
      data.files.pop();
    },
  ]) {
    const data = JSON.parse(zlib.gunzipSync(bytes));
    change(data);
    await assert.rejects(decodeBackup(zlib.gzipSync(JSON.stringify(data))));
  }
  for (const change of [
    (state) => {
      state.profiles.term1.video_fps = 999;
    },
    (state) => {
      state.users.term1.device_token = '';
    },
    (state) => {
      state.groups.family.members.push('absent');
    },
    (state) => {
      state.profiles.term1.terminal_settings = null;
    },
  ]) {
    const altered = new Map(files),
      state = JSON.parse(altered.get('server.json'));
    change(state);
    altered.set('server.json', Buffer.from(JSON.stringify(state)));
    await assert.rejects(decodeBackup(await encodeBackup(altered)));
  }
  const unsafe = new Map(files);
  unsafe.set('server.json', Buffer.from('{"__proto__":{}}'));
  await assert.rejects(decodeBackup(await encodeBackup(unsafe)));
  assert.equal(fs.existsSync(path.join(app.directory, 'restore-recovery')), false);
});

test('staging advances revisions, preserves this server address and prevents saved command replay', async (t) => {
  const app = await fixture(t);
  const backup = await decodeBackup(await app.backups.download());
  backup.state.host = 'old.example.test';
  backup.state.http_port = 9999;
  backup.state.sip_port = 9998;
  backup.state.configuration_version = 100;
  const { ConsoleJobs } = require('../../../zmala_server/console-jobs');
  const commands = new ConsoleJobs(app.store);
  for (const status of ['queued', 'running', 'completed']) {
    const job = commands.create('term1', { command: 'echo fixture' });
    job.status = status;
    job.lease = 'fixture-private-lease';
  }
  backup.files.set('console-jobs.json', Buffer.from(JSON.stringify(commands.jobs)));
  const version = app.store.value.configuration_version;
  await app.backups.stage(backup, version);
  assert.equal(app.backups.restoring, true);
  assert.equal(app.sipServer.maintenance, true);
  assert.equal(app.callbacks.paused, true);
  await recoverRestore(app.directory, app.store.adminPassword.file);
  const restored = JSON.parse(fs.readFileSync(path.join(app.directory, 'server.json')));
  assert.equal(restored.configuration_version, 101);
  for (const key of ['host', 'http_port', 'sip_port'])
    assert.equal(restored[key], app.store.value[key]);
  const jobs = JSON.parse(fs.readFileSync(path.join(app.directory, 'console-jobs.json')));
  assert.deepEqual(
    jobs.map((job) => job.status),
    ['cancelled', 'lost', 'completed'],
  );
  assert.ok(jobs.every((job) => !Object.hasOwn(job, 'lease')));
});

test('photo snapshot checks regular-file type and size/count bounds before reading bytes', async (t) => {
  const directory = storeFixture(t).dir;
  const files = new Map();
  await assert.doesNotReject(readPhotos(directory, files));
  assert.equal(files.size, 0);
  fs.mkdirSync(path.join(directory, 'photos'));
  const name = 'a'.repeat(64) + '.png';
  const read = t.mock.method(fs.promises, 'readFile', async () => Buffer.from('photo'));
  t.mock.method(fs.promises, 'readdir', async () => ['notes.txt', name]);
  const stat = t.mock.method(fs.promises, 'lstat', async () => ({ isFile: () => false, size: 1 }));
  await assert.rejects(readPhotos(directory, files), /Pictures must be regular files/);
  assert.equal(read.mock.calls.length, 0);
  stat.mock.mockImplementation(async () => ({ isFile: () => true, size: 47 * 1024 * 1024 + 1 }));
  await assert.rejects(readPhotos(directory, files), /Backup is too large/);
  assert.equal(read.mock.calls.length, 0);
  stat.mock.mockImplementation(async () => ({ isFile: () => true, size: 47 * 1024 * 1024 }));
  await assert.doesNotReject(readPhotos(directory, files));
  assert.deepEqual(files.get('photos/' + name), Buffer.from('photo'));
  assert.equal(read.mock.calls.length, 1);
  files.clear();
  for (let index = 0; index < 1004; index++) files.set('item' + index, Buffer.alloc(0));
  stat.mock.mockImplementation(async () => ({ isFile: () => true, size: 0 }));
  await assert.rejects(readPhotos(directory, files), /Backup is too large/);
  assert.equal(read.mock.calls.length, 1);
  files.delete('item0');
  await assert.doesNotReject(readPhotos(directory, files));
  assert.equal(files.size, 1004);
  assert.equal(read.mock.calls.length, 2);
});

test('failed fsync closes the temporary file and never replaces the live destination', (t) => {
  const file = path.join(storeFixture(t).dir, 'server.json');
  const previous = fs.readFileSync(file);
  const close = t.mock.method(fs, 'closeSync');
  t.mock.method(fs, 'fsyncSync', () => {
    throw Error('simulated full disk');
  });
  assert.throws(() => atomicWrite(file, 'replacement'), /simulated full disk/);
  assert.equal(close.mock.calls.length, 1);
  assert.deepEqual(fs.readFileSync(file), previous);
});

test('restore rejects unknown destinations and journals, and removes only obsolete photos', async (t) => {
  const app = await fixture(t);
  const original = fs.readFileSync(path.join(app.directory, 'server.json'));
  assert.throws(
    () =>
      applyFiles(
        app.directory,
        app.store.adminPassword.file,
        new Map([['../escape', Buffer.from('no')]]),
      ),
    /Invalid restore filename/,
  );
  assert.deepEqual(fs.readFileSync(path.join(app.directory, 'server.json')), original);
  const current = 'photos/' + digest(PNG) + '.png';
  const unrelated = path.join(app.directory, 'photos', 'notes.txt');
  fs.writeFileSync(unrelated, 'keep me');
  applyFiles(app.directory, app.store.adminPassword.file, new Map());
  assert.equal(fs.existsSync(path.join(app.directory, current)), false);
  assert.equal(fs.readFileSync(unrelated, 'utf8'), 'keep me');
  fs.mkdirSync(path.join(app.directory, 'callbacks.json'));
  assert.throws(
    () =>
      applyFiles(
        app.directory,
        app.store.adminPassword.file,
        new Map([['callbacks.json', Buffer.from('[]')]]),
      ),
    /Invalid restore destination/,
  );
  const recovery = path.join(app.directory, 'restore-recovery');
  fs.mkdirSync(recovery);
  const journal = path.join(recovery, 'pending.json');
  fs.writeFileSync(journal, JSON.stringify({ phase: 'unexpected' }));
  const apply = t.mock.fn();
  await assert.rejects(
    recoverRestore(app.directory, app.store.adminPassword.file, apply),
    /Invalid restore recovery journal/,
  );
  assert.equal(apply.mock.calls.length, 0);
  assert.equal(fs.existsSync(journal), true);
  await assert.rejects(
    stageRestore(app.directory, new Map(), new Map()),
    /restore is already pending/,
  );
  assert.deepEqual(fs.readFileSync(path.join(app.directory, 'server.json')), original);
});
