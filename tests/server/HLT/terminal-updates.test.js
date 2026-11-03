// @test S-HLT-038
// @requirements HLR-SRV-MAINT-021
// @environment portable
// @plan Send updater and hardware reports through real authenticated HTTP endpoints on a disposable server; render returned telemetry through the admin badge owner with a view double, inspect the bound SIP admission predicate, then reject anonymous/app accounts and malformed status. This is functional UI integration, not browser layout qualification.
// @pass Updater reports preserve hardware receipt time, hardware reports preserve updater state, only terminal credentials can report, and fresh active maintenance blocks SIP admission without an administrator approval step.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const vm = require('../../../build_tools/coverage-js.cjs');
const { httpFixture } = require('../../support/server/http-fixture');

test('terminal-only updater reports remain independent of hardware diagnostics', async () => {
  const f = await httpFixture();
  try {
    const request = (path, body, id = 'term1') =>
      fetch(f.base + path, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer ' + (id ? f.store.value.users[id].device_token : 'wrong'),
        },
        body: JSON.stringify(body),
      });
    const status = async () =>
      (
        await (
          await fetch(f.base + '/api/admin', {
            headers: { Authorization: 'Bearer ' + f.store.value.admin_token },
          })
        ).json()
      ).terminal_status;
    assert.equal((await request('/api/status', { camera_status: 'off' })).status, 200);
    const hardware = await status();
    assert.equal(
      (await request('/api/terminal-updates/status', { phase: 'checking', installed: '1.2.3' }))
        .status,
      200,
    );
    let current = await status();
    assert.equal(current.last_seen, hardware.last_seen);
    assert.equal(current.camera_status, 'off');
    assert.equal(current.update.phase, 'checking');
    const view = { badge: (text) => text };
    vm.runInNewContext(
      vm
        .source(path.join(__dirname, '../../../zmala_server/web/admin-terminals.js'))
        .replace(/^import[^;]+;\s*/gm, '')
        .replace(/^export /gm, ''),
      view,
    );
    const badges = [];
    view.appendTerminalUpdate({ append: (text) => badges.push(text) }, current.update);
    assert.match(badges[0], /Version 1.2.3.*Checking update/);
    assert.equal(f.sipServer.terminalUpdating('term1'), true);
    assert.equal((await request('/api/status', { camera_status: 'connected' })).status, 200);
    current = await status();
    assert.equal(current.update.phase, 'checking');
    assert.equal(
      (await request('/api/terminal-updates/status', { phase: 'invented' })).status,
      400,
    );
    assert.equal(
      (await request('/api/terminal-updates/status', { phase: 'idle' }, 'phone1')).status,
      403,
    );
    assert.equal(
      (await request('/api/terminal-updates/status', { phase: 'idle' }, null)).status,
      401,
    );
    assert.equal(
      (await request('/api/terminal-updates/status', { phase: 'idle', installed: '1.2.3' })).status,
      200,
    );
    assert.equal(f.sipServer.terminalUpdating('term1'), false);
  } finally {
    await f.close();
  }
});
