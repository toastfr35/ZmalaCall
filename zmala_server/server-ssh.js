// @ts-check
'use strict';
const fs = require('node:fs');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const execute = promisify(execFile);
const helper = '/usr/local/libexec/zmala-server-ssh';
let changing = false;
function supported() {
  return process.platform === 'linux' && fs.existsSync(helper);
}
async function sshStatus() {
  if (!supported()) return { supported: false };
  const result = await execute('/usr/bin/python3', [helper, 'status'], { timeout: 10000 });
  return JSON.parse(result.stdout);
}
/** @param {unknown} enabled */
async function setSsh(enabled) {
  if (typeof enabled !== 'boolean') throw Error('SSH enabled must be true or false.');
  if (!supported()) throw Error('SSH control is available on installed Pi servers only.');
  if (changing) throw Error('Another SSH change is in progress.');
  changing = true;
  try {
    const result = await execute('/usr/bin/sudo', ['-n', helper, enabled ? 'on' : 'off'], {
      timeout: 60000,
    });
    const state = JSON.parse(result.stdout);
    if (state.enabled !== enabled || state.active !== enabled)
      throw Error('SSH state did not match the request.');
    return state;
  } finally {
    changing = false;
  }
}
module.exports = { sshStatus, setSsh };
