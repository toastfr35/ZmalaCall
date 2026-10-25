// @test S-LLT-062
// @requirements LLR-SRV-CONFIG-024, LLR-SRV-BACKUP-003, LLR-SRV-BACKUP-005, LLR-SRV-BACKUP-009
// @environment portable
// @plan Validate PCM format, checksums, names, IDs, duration/catalog byte limits and version conflicts using temporary stores. Import and select a tone, reload state, and round-trip its bytes and selection through backup decoding and file restore. Reject missing/corrupt referenced audio and unsafe filenames; preserve default Nokia independently of private files.
// @pass All validation, persistence, isolation and backup assertions pass without a live server or audio device.
'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { storeFixture } = require('../../support/server/unit-fixture');
const {
  MAX_SOUND,
  MAX_LIBRARY,
  DEFAULT_SOUND,
  validateSound,
  ringtoneId,
} = require('../../../zmala_server/ringtones');
const { Store } = require('../../../zmala_server/store');
const { ServerBackups } = require('../../../zmala_server/backups');
const {
  encodeBackup,
  decodeBackup,
  validateFiles,
} = require('../../../zmala_server/backup-format');
const { applyFiles } = require('../../../zmala_server/backup-storage');
const sound = fs.readFileSync(DEFAULT_SOUND);

test('ringtone PCM, ID, duration and catalog limits reject malformed input', async (t) => {
  const store = storeFixture(t),
    id = validateSound(sound);
  assert.equal(id.length, 64);
  assert.equal(ringtoneId('nokia'), 'nokia');
  for (const value of [null, '../sound', 'nokia.wav', '__proto__'])
    assert.throws(() => ringtoneId(value));
  for (const bytes of [
    Buffer.alloc(0),
    sound.subarray(0, 43),
    sound.subarray(0, sound.length - 1),
    Buffer.alloc(MAX_SOUND + 2),
  ])
    assert.throws(() => validateSound(bytes));
  const rate = Buffer.from(sound);
  rate.writeUInt32LE(48000, 24);
  assert.throws(() => validateSound(rate));
  for (const name of ['', null, 'x'.repeat(81), 'bad\nname', 'bad\u0085name'])
    await assert.rejects(store.uploadRingtone(name, sound));
  store.value.ringtones = { ['a'.repeat(64)]: { name: 'Large', bytes: MAX_LIBRARY } };
  await assert.rejects(store.uploadRingtone('Nokia copy', sound), /full/);
  store.value.ringtones = Object.fromEntries(
    Array.from({ length: 64 }, (_, i) => [
      i.toString(16).padStart(64, '0'),
      { name: 'Tone', bytes: 44 },
    ]),
  );
  await assert.rejects(store.uploadRingtone('More', sound), /full/);
});

test('private audio and selection persist and restore with the backup', async (t) => {
  const store = storeFixture(t);
  store.adminPassword.setHash('a'.repeat(32) + ':' + 'b'.repeat(128));
  const initial = store.value.configuration_version;
  const choice = await store.uploadRingtone('Nokia copy', sound, initial);
  assert.equal(choice.configuration_version, initial + 1);
  assert.equal(store.config('term1').ringtone, 'nokia');
  assert.equal(store.config('term1').ringtones.find((x) => x.id === choice.id).name, 'Nokia copy');
  const revision = store.value.configuration_version;
  await store.uploadRingtone('Nokia copy', sound, revision);
  assert.equal(store.value.configuration_version, revision);
  await assert.rejects(store.uploadRingtone('Renamed', sound, initial), { status: 409 });
  store.setDeviceSettings('term1', { ringtone: choice.id }, { ringtone: 'nokia' });
  assert.equal(new Store(store.dir).config('term1').ringtone, choice.id);
  assert.throws(
    () => store.setDeviceSettings('term1', { ringtone: 'c'.repeat(64) }, { ringtone: choice.id }),
    /available/,
  );
  const backups = new ServerBackups(
    store,
    { requests: [] },
    { jobs: [] },
    { dialogs: new Map() },
    async () => {},
    () => {},
  );
  const files = await backups.snapshot(),
    name = `ringtones/${choice.id}.wav`;
  assert.deepEqual(files.get(name), sound);
  assert.equal(files.has('ringtones/nokia.wav'), false);
  const decoded = await decodeBackup(await encodeBackup(files));
  const obsolete = path.join(store.dir, 'ringtones', 'd'.repeat(64) + '.wav');
  fs.writeFileSync(obsolete, sound);
  fs.unlinkSync(path.join(store.dir, name));
  applyFiles(store.dir, store.adminPassword.file, decoded.files);
  assert.deepEqual(fs.readFileSync(path.join(store.dir, name)), sound);
  assert.equal(fs.existsSync(obsolete), false);
  assert.throws(
    () =>
      applyFiles(
        store.dir,
        store.adminPassword.file,
        new Map([['ringtones/../escape.wav', sound]]),
      ),
    /filename/,
  );
  const missing = new Map(files);
  missing.delete(name);
  assert.throws(() => validateFiles(missing), /ringtone/);
  const corrupt = new Map(files);
  corrupt.set(name, Buffer.from('bad'));
  assert.throws(() => validateFiles(corrupt));
});

test('configuration conflicts during audio import clean temporary and unreferenced files', async (t) => {
  const store = storeFixture(t),
    rename = fs.promises.rename.bind(fs.promises);
  t.mock.method(fs.promises, 'rename', async (from, to) => {
    await rename(from, to);
    store.changed();
  });
  await assert.rejects(
    store.uploadRingtone('Racing import', sound, store.value.configuration_version),
    { status: 409 },
  );
  assert.equal(store.value.ringtones, undefined);
  assert.deepEqual(fs.readdirSync(path.join(store.dir, 'ringtones')), []);
});
