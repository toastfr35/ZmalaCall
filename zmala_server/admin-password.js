// @ts-check
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { readJson } = require('./json-file');

/** Detect hardware rather than CPU architecture: ordinary ARM Linux hosts
 * must keep the normal data path. Injectable reads keep tests off real boot files.
 * @param {string} directory
 * @param {string} [platform]
 * @param {(file: string) => string} [readModel] */
function passwordFile(
  directory,
  platform = process.platform,
  readModel = (file) => fs.readFileSync(file, 'utf8'),
) {
  if (platform === 'linux') {
    for (const file of ['/sys/firmware/devicetree/base/model', '/proc/device-tree/model']) {
      try {
        if (/^Raspberry Pi\b/.test(readModel(file)))
          return '/boot/firmware/zmalacall/admin-password.json';
      } catch (error) {
        if (!error || typeof error !== 'object' || !('code' in error) || error.code !== 'ENOENT')
          throw error;
      }
    }
  }
  return path.join(directory, 'admin-password.json');
}

/** Credentials live outside account state. Missing means first-time setup;
 * invalid content fails startup instead of silently reopening administration.
 * Deleting this file takes effect on restart, so a running session cannot
 * accidentally recreate a deleted password during an account settings save. */
class AdminPassword {
  /** @param {string} directory @param {string | undefined} legacyHash
   * @param {string} [file] */
  constructor(directory, legacyHash, file = path.join(directory, 'admin-password.json')) {
    this.file = file;
    /** @type {string | undefined} */
    this.hash = undefined;
    const localFile = path.join(directory, 'admin-password.json');
    // Installed releases reach persistent data through a directory symlink.
    // Compare resolved files before removing a supposedly obsolete copy.
    const localExists = fs.existsSync(localFile);
    const sameFile =
      file === localFile ||
      (localExists && fs.existsSync(file) && fs.realpathSync(file) === fs.realpathSync(localFile));
    const oldFile = !sameFile && localExists ? localFile : undefined;
    const saved = readJson(this.file, /** @type {{password_hash: string} | null} */ (null));
    if (saved !== null) {
      this.validate(saved.password_hash);
      this.hash = saved.password_hash;
    } else if (fs.existsSync(this.file)) {
      throw Error('Invalid admin password file.');
    } else if (oldFile || legacyHash) {
      // Persist before the caller removes the old field: migration must never
      // discard the only durable copy of an existing password.
      const previous = oldFile
        ? readJson(oldFile, { password_hash: '' }).password_hash
        : legacyHash;
      this.setHash(previous || '');
    }
    // Remove the migrated local copy so deleting the boot file cannot restore
    // the old password on the following startup. The target must be durable first.
    if (oldFile) fs.unlinkSync(oldFile);
  }
  /** @param {string} hash */
  validate(hash) {
    if (typeof hash !== 'string' || !/^[a-f0-9]{32}:[a-f0-9]{128}$/.test(hash))
      throw Error('Invalid admin password file.');
  }
  /** Atomic, immediate persistence; update memory only after the rename succeeds.
   * @param {string} hash */
  setHash(hash) {
    this.validate(hash);
    fs.mkdirSync(path.dirname(this.file), { recursive: true });
    const temporary = this.file + '.tmp';
    fs.writeFileSync(temporary, JSON.stringify({ password_hash: hash }, null, 2), { mode: 0o600 });
    fs.renameSync(temporary, this.file);
    this.hash = hash;
  }
}
module.exports = { AdminPassword, passwordFile };
