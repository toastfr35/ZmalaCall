// @test S-HLT-006
// @requirements HLR-SRV-DATA-002
// @environment portable
// @plan Populate the assembled service with accounts, credentials, histories and pictures, export and restore it, then reopen storage; compare all records and photo bytes, verify restored credentials and command cancellation, and reject unsafe or unauthorized HTTP restores without mutation.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { httpFixture } = require('../../support/server/http-fixture');
const { hashPassword, verifyPassword } = require('../../../zmala_server/admin-sessions');
const { decodeBackup, encodeBackup, digest } = require('../../../zmala_server/backup-format');
const { recoverRestore, stageRestore } = require('../../../zmala_server/backup-storage');
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
