'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { AdminPassword, passwordFile } = require('../admin-password');
const { hashPassword } = require('../admin-sessions');

test('only Raspberry Pi hardware selects the Windows-accessible boot path', () => {
  const local = path.join('data', 'admin-password.json');
  const piModel = () => 'Raspberry Pi 3 Model B Rev 1.2\0';
  assert.equal(
    passwordFile('data', 'linux', piModel),
    '/boot/firmware/zmalacall/admin-password.json',
  );
  assert.equal(passwordFile('data', 'win32', piModel), local);
  assert.equal(
    passwordFile('data', 'linux', () => 'Other ARM board'),
    local,
  );
  const absent = () => {
    throw Object.assign(Error('missing'), { code: 'ENOENT' });
  };
  assert.equal(passwordFile('data', 'linux', absent), local);
  assert.equal(
    passwordFile('data', 'linux', (file) => (file.startsWith('/sys/') ? absent() : piModel())),
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
