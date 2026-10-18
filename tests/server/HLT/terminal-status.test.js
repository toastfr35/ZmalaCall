// @test S-HLT-021
// @requirements HLR-SRV-MAINT-012
// @environment portable
// @plan Post valid and malformed diagnostic payloads through device HTTP authentication; assert invalid fields do not replace the last valid status and the server owns receipt time.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { httpFixture } = require('../../support/server/http-fixture');

test('device diagnostics reject malformed fields without replacing the last valid status', async () => {
  const fixture = await httpFixture();
  const { store, base } = fixture;
  const token = store.value.users.term1.device_token;
  const post = (body) =>
    fetch(base + '/api/status', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  const status = async () => {
    const response = await fetch(base + '/api/admin', {
      headers: { Authorization: `Bearer ${store.value.admin_token}` },
    });
    return (await response.json()).terminal_status;
  };
  try {
    const accepted = await post({
      state: 'home',
      registered: true,
      configuration_version: 2,
      last_seen: 'forged',
      devices: { camera: ['Webcam'], microphone: ['Microphone'] },
    });
    assert.equal(accepted.status, 200);
    await accepted.arrayBuffer();
    const original = await status();
    assert.notEqual(original.last_seen, 'forged');
    assert.deepEqual(original.devices.camera, ['Webcam']);
    for (const update of [
      { devices: [] },
      { devices: { camera: 'bad' } },
      { devices: { microphone: [{}] } },
      { registered: 'yes' },
      { state: {} },
      { configuration_version: -1 },
      { configuration_version: '2' },
    ]) {
      const response = await post(update);
      assert.equal(response.status, 400);
      await response.arrayBuffer();
      assert.deepEqual(await status(), original);
    }
  } finally {
    await fixture.close();
  }
});
