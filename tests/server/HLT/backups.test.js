// @test S-HLT-006
// @requirements SHLR019
// @environment portable
// @plan Populate the assembled service with accounts, credentials, histories and pictures, export and restore it, then reopen storage; compare all records and photo bytes, inject partial-write failures to verify rollback, and reject unsafe or unauthorized restores without mutation.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');
const { httpFixture } = require('../../support/server/http-fixture');
const { hashPassword, verifyPassword } = require('../../../zmala_server/admin-sessions');
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

const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a/A8AAAAASUVORK5CYII=',
  'base64',
);
async function fixture(t) {
  const app = await httpFixture();
  t.after(() => app.close());
  app.store.adminPassword.setHash(await hashPassword('Private-backup-test-password'));
  app.backups.restart = () => {};
  const name = digest(PNG) + '.png';
  fs.mkdirSync(path.join(app.directory, 'photos'));
  fs.writeFileSync(path.join(app.directory, 'photos', name), PNG);
  app.store.value.users.term1.photo = '/photos/' + name;
  app.store.value.smtp.password = 'private smtp password';
  app.store.changed();
  await app.flush();
  const token = app.adminSessions.create();
  return { ...app, headers: { Authorization: 'Bearer ' + token } };
}

test('backup round trip restores complete config, histories and pictures; credentials survive and jobs never replay', async (t) => {
  const app = await fixture(t);
  app.callbacks.create('term1', 'phone1');
  app.consoleJobs.create('term1', { command: 'echo never replay' });
  const bytes = await app.backups.download(),
    backup = await decodeBackup(bytes);
  const original = structuredClone(app.store.value);
  app.store.value.users.term1.name = 'Changed';
  app.store.value.profiles.term1.language = 'fr';
  app.store.value.configuration_version += 9;
  app.store.save();
  const newerVersion = app.store.value.configuration_version;
  await app.backups.stage(backup, newerVersion);
  assert.equal(app.sipServer.maintenance, true);
  assert.equal(
    new Store(app.directory).value.users.term1.name,
    'Changed',
    'Staging does not alter live data',
  );
  await recoverRestore(app.directory, app.store.adminPassword.file);
  const restored = new Store(app.directory);
  assert.equal(restored.value.configuration_version, newerVersion + 1);
  assert.deepEqual(
    { ...restored.value, configuration_version: original.configuration_version },
    original,
  );
  assert.equal(
    await verifyPassword('Private-backup-test-password', restored.adminPassword.hash),
    true,
  );
  assert.deepEqual(
    fs.readFileSync(path.join(app.directory, original.users.term1.photo.slice(1))),
    PNG,
  );
  const jobs = JSON.parse(fs.readFileSync(path.join(app.directory, 'console-jobs.json')));
  assert.equal(jobs[0].status, 'cancelled');
  assert.equal(jobs[0].lease, undefined);
  assert.equal(JSON.parse(fs.readFileSync(path.join(app.directory, 'callbacks.json'))).length, 1);
  assert.equal(app.backups.status().result, 'restored');
  assert.equal(
    fs.existsSync(path.join(app.directory, 'restore-recovery', 'previous.zmala-backup')),
    true,
  );
  await recoverRestore(app.directory, app.store.adminPassword.file);
  assert.equal(new Store(app.directory).value.configuration_version, newerVersion + 1);
});

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

test('admin HTTP backup requires authentication, confirmation, current version and an idle server', async (t) => {
  const app = await fixture(t),
    url = app.base + '/api/server/backup';
  assert.equal((await fetch(url)).status, 401);
  assert.equal(
    (
      await fetch(url, {
        headers: { Authorization: 'Bearer ' + app.store.value.users.term1.device_token },
      })
    ).status,
    401,
  );
  const response = await fetch(url, { headers: app.headers });
  assert.equal(response.status, 200);
  assert.match(response.headers.get('content-disposition'), /attachment.*\.zmala-backup/);
  const bytes = Buffer.from(await response.arrayBuffer());
  const preview = await fetch(url + '/check', {
    method: 'POST',
    headers: app.headers,
    body: bytes,
  });
  assert.equal(preview.status, 200);
  assert.equal((await preview.json()).pictures, 1);
  const options = {
    method: 'POST',
    body: bytes,
    headers: {
      ...app.headers,
      'X-Zmala-Configuration-Version': String(app.store.value.configuration_version),
    },
  };
  assert.equal((await fetch(url + '/restore', options)).status, 400);
  options.headers['X-Zmala-Confirm-Restore'] = 'replace';
  app.sipServer.dialogs.set('call', { peers: [] });
  assert.equal((await fetch(url + '/restore', options)).status, 409);
  app.sipServer.dialogs.clear();
  const command = app.consoleJobs.create('term1', { command: 'echo active' });
  app.consoleJobs.claim('term1');
  assert.equal((await fetch(url + '/restore', options)).status, 409);
  command.status = 'completed';
  app.store.changed();
  assert.equal((await fetch(url + '/restore', options)).status, 409);
  options.headers['X-Zmala-Configuration-Version'] = String(app.store.value.configuration_version);
  assert.equal((await fetch(url + '/restore', options)).status, 202);
  assert.equal((await fetch(app.base + '/ready')).status, 503);
  assert.equal((await fetch(url + '/restore', options)).status, 503);
});

test('restore uses the locally configured external password path and accepts legacy history without a shell', async (t) => {
  const app = await fixture(t);
  const job = app.consoleJobs.create('term1', { command: 'echo legacy' });
  job.status = 'completed';
  delete job.shell;
  delete job.device_id;
  const files = await app.backups.snapshot();
  await decodeBackup(await encodeBackup(files));
  const external = path.join(app.directory, 'credential-volume', 'admin.json');
  await stageRestore(app.directory, files, files);
  await recoverRestore(app.directory, external);
  assert.equal(JSON.parse(fs.readFileSync(external)).password_hash, app.store.adminPassword.hash);
  if (process.platform !== 'win32') assert.equal(fs.statSync(external).mode & 0o777, 0o600);
});
