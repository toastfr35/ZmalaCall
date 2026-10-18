// @test S-LLT-002
// @requirements SLLR017
// @environment portable
// @plan Use temporary credential files and synthetic Pi detection; assert one-time password migration and persistent credentials through a release symlink.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { AdminPassword, passwordFile } = require('../../../zmala_server/admin-password');
const { hashPassword } = require('../../../zmala_server/admin-sessions');

test('only Raspberry Pi hardware selects the FAT boot boot path', () => {
  const local = path.join('data', 'admin-password.json');
  const piModel = () => 'Raspberry Pi 3 Model B Rev 1.2\0';
  assert.equal(passwordFile('data', piModel), '/boot/firmware/zmalacall/admin-password.json');
  assert.equal(
    passwordFile('data', () => 'Other ARM board'),
    local,
  );
  const absent = () => {
    throw Object.assign(Error('missing'), { code: 'ENOENT' });
  };
  assert.equal(passwordFile('data', absent), local);
  assert.equal(
    passwordFile('data', (file) => (file.startsWith('/sys/') ? absent() : piModel())),
    '/boot/firmware/zmalacall/admin-password.json',
  );
});

test('moving credentials to boot removes the old copy so deletion stays a reset', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'zmala-password-path-'));
  try {
    const local = new AdminPassword(directory);
    const hash = await hashPassword('migration test password');
    local.setHash(hash);
    const bootFile = path.join(directory, 'boot', 'zmalacall', 'admin-password.json');
    const moved = new AdminPassword(directory, undefined, bootFile);
    assert.equal(moved.hash, hash);
    assert.equal(fs.existsSync(local.file), false);
    fs.unlinkSync(bootFile);
    assert.equal(new AdminPassword(directory, undefined, bootFile).hash, undefined);
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test(
  'release data symlink preserves credentials across repeated startups',
  { skip: process.platform !== 'linux' },
  async () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'zmala-password-link-'));
    try {
      const persistent = path.join(directory, 'persistent');
      fs.mkdirSync(persistent);
      const linked = path.join(directory, 'release-data');
      fs.symlinkSync(persistent, linked, 'dir');
      const credentials = new AdminPassword(persistent);
      const hash = await hashPassword('symlink migration test');
      credentials.setHash(hash);
      for (let startup = 0; startup < 3; startup++) {
        assert.equal(new AdminPassword(linked, undefined, credentials.file).hash, hash);
        assert.equal(fs.existsSync(credentials.file), true);
      }
    } finally {
      fs.rmSync(directory, { recursive: true, force: true });
    }
  },
);
