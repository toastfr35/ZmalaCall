// @ts-check
'use strict';
const fs = require('node:fs');
/** Only a missing file uses the default. Corrupt persisted state must surface to the operator.
 * @template T @param {string} file @param {T | (() => T)} fallback @returns {T} */
function readJson(file, fallback) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (error) {
    if (!error || typeof error !== 'object' || !('code' in error) || error.code !== 'ENOENT')
      throw error;
    return typeof fallback === 'function' ? /** @type {() => T} */ (fallback)() : fallback;
  }
}
// @llr SLLR083
/** Startup/setup tools use an immediate rename; HTTP configuration uses SnapshotFile.
 * @param {string} file @param {unknown} value */
function writeJson(file, value) {
  const temporary = file + '.tmp';
  fs.writeFileSync(temporary, JSON.stringify(value, null, 2));
  fs.renameSync(temporary, file);
}
module.exports = { readJson, writeJson };
