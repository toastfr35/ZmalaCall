// @test S-HLT-020
// @requirements SHLR002
// @environment portable
// @plan Reassign a serial through HTTP and reload device state; assert enrollment, device settings and maintenance job ownership follow the physical terminal.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { httpFixture } = require('../../support/server/http-fixture');

test('serial reassignment preserves enrollment, device settings and console jobs', async () => {
  const fixture = await httpFixture();
  const { store, sipServer, base } = fixture;
  const request = async (route, data, token = store.value.admin_token, method) => {
    const response = await fetch(base + route, {
      method: method || (data ? 'PUT' : 'GET'),
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: data ? JSON.stringify(data) : undefined,
    });
    return { status: response.status, body: await response.json() };
  };
  try {
    store.createAccount({
      id: 'other',
      name: 'Other',
      type: 'terminal',
      emails: ['other@example.test'],
    });
    const first = { ...store.value.users.term1 };
    const second = { ...store.value.users.other };
    const firstProfile = structuredClone(store.value.profiles.term1);
    const job = (
      await request(
        '/api/terminals/term1/console',
        { command: 'hostname' },
        store.value.admin_token,
        'POST',
      )
    ).body;
    const update = { serial_number: first.device_id, account_id: 'other' };
    assert.equal((await request('/api/terminal-association', update, 'bad-token')).status, 401);
    const snapshot = JSON.stringify(store.value);
    assert.equal(
      (await request('/api/terminal-association', { ...update, serial_number: 'missing' })).status,
      400,
    );
    assert.equal(JSON.stringify(store.value), snapshot);
    sipServer.dialogs.set('busy', { peers: [{ user: 'term1' }] });
    assert.equal((await request('/api/terminal-association', update)).status, 409);
    assert.equal(JSON.stringify(store.value), snapshot);
    sipServer.dialogs.clear();
    assert.equal((await request('/api/terminal-association', update)).status, 200);
    const config = await request('/api/config', undefined, first.device_token);
    assert.equal(config.body.device_id, first.device_id);
    assert.equal(config.body.sip.username, 'other');
    assert.equal(config.body.sip.password, second.password);
    assert.deepEqual(store.value.profiles.other, { ...firstProfile, display_name: second.name });
    assert.equal(config.body.display_name, second.name);
    assert.equal(store.value.users.term1.device_id, second.device_id);
    assert.equal(store.value.users.term1.name, first.name);
    assert.equal(store.value.local_terminal_id, 'other');
    assert.equal((await request('/api/terminals/other/console')).body.jobs[0].id, job.id);
    assert.equal(
      (await request('/api/config', undefined, second.device_token)).body.sip.username,
      'term1',
    );
    // A second swap returns enrollment to its original account without changing serials.
    assert.equal(
      (await request('/api/terminal-association', { ...update, account_id: 'term1' })).status,
      200,
    );
    assert.equal(store.value.users.term1.device_id, first.device_id);
    store.updateAccount('term1', { name: 'Renamed account', type: 'terminal' });
    assert.equal(store.config('term1').display_name, 'Renamed account');
    assert.equal(store.config('term1').device_id, first.device_id);
  } finally {
    await fixture.close();
  }
});
