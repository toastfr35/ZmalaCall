// @ts-check
'use strict';
const fs = require('node:fs');
const { spawn } = require('node:child_process');
const helper = '/usr/local/libexec/zmala-developer-access';

// @llr LLR-SRV-HOST-007
/** @param {string} action @param {object} [request] @returns {Promise<import('./types/contracts').JsonObject | null>} */
function control(action, request = {}) {
  if (!fs.existsSync(helper))
    return Promise.resolve(action === 'config' ? null : { supported: false, terminal_id: null });
  return new Promise((resolve, reject) => {
    const child = spawn('/usr/bin/sudo', ['-n', helper, action], {
      stdio: ['pipe', 'pipe', 'ignore'],
    });
    let output = '';
    const timer = setTimeout(() => {
      child.kill();
      reject(Error('Developer access operation timed out.'));
    }, 60000);
    child.stdout.on('data', (data) => {
      output += data;
      if (output.length > 16384) child.kill();
    });
    child.on('error', () => {
      clearTimeout(timer);
      reject(Error('Developer access is unavailable.'));
    });
    child.on('close', (code) => {
      clearTimeout(timer);
      if (code !== 0)
        return reject(Error('Developer access operation failed. Check the server service.'));
      try {
        resolve(JSON.parse(output));
      } catch {
        reject(Error('Invalid developer access response.'));
      }
    });
    child.stdin.on('error', () => {});
    child.stdin.end(JSON.stringify(request));
  });
}
module.exports = { control };
