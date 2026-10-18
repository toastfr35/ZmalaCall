// @test S-HLT-005
// @requirements SHLR011
// @environment portable
// @plan Change auto-framing through authenticated HTTP and fetch terminal configuration; assert default-off behavior, strict validation and persisted device delivery.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { httpFixture } = require('../../support/server/http-fixture');

test('automatic framing is opt-in, validated, persisted and sent to its terminal', async () => {
  const fixture = await httpFixture();
  const { store, base } = fixture;
  try {
    const id = store.value.local_terminal_id;
    const p = store.value.profiles[id];
    const body = {
      terminal_id: id,
      display_name: p.display_name,
      auto_answer: false,
      auto_answer_seconds: 5,
      camera: '',
      microphone: '',
      speaker: '',
    };
    const put = (extra) =>
      fetch(base + '/api/settings', {
        method: 'PUT',
        headers: {
          Authorization: 'Bearer ' + store.value.admin_token,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ ...body, ...extra }),
      });
    assert.equal(store.config(id).auto_framing, false);
    assert.equal((await put({ auto_framing: true })).status, 200);
    assert.equal(store.config(id).auto_framing, true);
    const configuration = await fetch(base + '/api/config', {
      headers: { Authorization: 'Bearer ' + store.value.users[id].device_token },
    });
    assert.equal(configuration.status, 200);
    assert.equal((await configuration.json()).auto_framing, true);
    assert.equal((await put({})).status, 200);
    assert.equal(store.config(id).auto_framing, true);
    for (const bad of ['true', 1, null, {}]) {
      assert.equal((await put({ auto_framing: bad })).status, 400);
      assert.equal(store.config(id).auto_framing, true);
    }
    assert.equal((await put({ auto_framing: false })).status, 200);
    assert.equal(store.config(id).auto_framing, false);
  } finally {
    await fixture.close();
  }
});
