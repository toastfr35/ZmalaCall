// @test S-HLT-034
// @requirements HLR-SRV-CONFIG-014, HLR-SRV-CONFIG-015
// @environment portable
// @plan Through real isolated HTTP, import normalized audio as administrator, reject unauthenticated/device writes and app/anonymous audio reads, fetch exact bytes as a terminal and administrator, select from the device and server, reject stale/unknown choices, reload durable state, and enforce malformed/oversized upload rejection.
// @pass All named assertions pass without contacting the user's Pi or playing sound. Browser media controls and C20 playback require separate display/hardware checks.
'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { httpFixture } = require('../../support/server/http-fixture');
const { DEFAULT_SOUND, MAX_SOUND } = require('../../../zmala_server/ringtones');
const { Store } = require('../../../zmala_server/store');

test('ringtone library, authenticated bytes and both settings editors agree', async () => {
  const fixture = await httpFixture(),
    { store, base, directory } = fixture;
  const admin = store.value.admin_token,
    terminal = store.value.users.term1.device_token;
  store.createAccount({ id: 'phone', name: 'Phone', type: 'app', emails: ['phone@example.test'] });
  const app = store.value.users.phone.device_token,
    bytes = fs.readFileSync(DEFAULT_SOUND);
  const headers = (token) => ({ Authorization: 'Bearer ' + token });
  const upload = (data = bytes, token = admin) =>
    fetch(
      `${base}/api/ringtones?name=Fixture%20chime&version=${store.value.configuration_version}`,
      {
        method: 'POST',
        headers: headers(token),
        body: data,
      },
    );
  try {
    assert.equal((await upload(bytes, 'wrong')).status, 401);
    assert.equal((await upload(bytes, terminal)).status, 401);
    const response = await upload();
    assert.equal(response.status, 201);
    const choice = await response.json();
    for (const [token, status] of [
      ['wrong', 401],
      [app, 403],
    ])
      assert.equal((await fetch(base + choice.url, { headers: headers(token) })).status, status);
    for (const token of [terminal, admin]) {
      const sound = await fetch(base + choice.url, { headers: headers(token) });
      assert.equal(sound.status, 200);
      assert.equal(sound.headers.get('content-type'), 'audio/wav');
      assert.deepEqual(Buffer.from(await sound.arrayBuffer()), bytes);
    }
    assert.equal(
      (
        await fetch(base + '/api/ringtones/' + 'a'.repeat(64) + '.wav', {
          headers: headers(terminal),
        })
      ).status,
      404,
    );
    const settings = (value, expected) =>
      fetch(base + '/api/device/settings', {
        method: 'POST',
        headers: { ...headers(terminal), 'Content-Type': 'application/json' },
        body: JSON.stringify({ settings: { ringtone: value }, expected: { ringtone: expected } }),
      });
    const accepted = await settings(choice.id, 'nokia');
    assert.equal(accepted.status, 200);
    assert.equal((await accepted.json()).ringtone, choice.id);
    assert.equal(new Store(directory).config('term1').ringtone, choice.id);
    assert.equal((await settings('nokia', 'nokia')).status, 409);
    assert.equal((await settings('f'.repeat(64), choice.id)).status, 400);
    const profile = store.value.profiles.term1;
    const saved = await fetch(base + '/api/settings', {
      method: 'PUT',
      headers: { ...headers(admin), 'Content-Type': 'application/json' },
      body: JSON.stringify({
        terminal_id: 'term1',
        configuration_version: store.value.configuration_version,
        ...profile,
        ...profile.terminal_settings,
        auto_answer: store.value.users.term1.auto_answer,
        auto_answer_seconds: store.value.users.term1.auto_answer_seconds,
        ringtone: 'nokia',
      }),
    });
    assert.equal(saved.status, 200);
    assert.equal(new Store(directory).config('term1').ringtone, 'nokia');
    assert.equal((await upload(Buffer.from('bad'))).status, 400);
    assert.equal((await upload(Buffer.alloc(MAX_SOUND + 1))).status, 413);
  } finally {
    await fixture.close();
  }
});
