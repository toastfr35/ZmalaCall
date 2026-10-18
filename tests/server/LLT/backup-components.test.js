// @test S-LLT-023
// @requirements LLR-SRV-DATA-008, LLR-SRV-DATA-009, LLR-SRV-DATA-010
// @environment portable
// @plan Use isolated backup maps with fake live services; corrupt versions, schemas, hashes and sizes before decoding, then inject apply/rollback failures into journal recovery. Check snapshot isolation, restore exclusion gates and revision/network preservation.
// @pass Rejections must leave live files unchanged; accepted snapshots and recovered transactions must match expected state without replaying commands.

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
  applyFiles,
  stageRestore,
} = require('../../../zmala_server/backup-storage');
const { Store } = require('../../../zmala_server/store');

test('snapshot freezes all in-memory records and excludes operational files', async (t) => {
  const app = await fixture(t);
  fs.writeFileSync(path.join(app.directory, 'server.log'), 'private log');
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
