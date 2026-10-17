'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { httpFixture } = require('./http-fixture');
const { Store } = require('../store');

test('local settings are device-scoped, validated, durable and conflict-aware', async () => {
  const fixture = await httpFixture();
  const { store, base, directory } = fixture;
  try {
    store.createAccount({
      id: 'other',
      name: 'Other',
      type: 'terminal',
      emails: ['other@example.test'],
    });
    assert.equal(store.config('term1').tv_idle_seconds, 30);
    delete store.value.profiles.term1.tv_idle_seconds;
    assert.equal(store.config('term1').tv_idle_seconds, 30); // Existing installations.
    const token = store.value.users.term1.device_token;
    const untouched = JSON.stringify(store.config('other'));
    const post = (body, bearer = token) =>
      fetch(base + '/api/device/settings', {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + bearer, 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    assert.equal(
      (await post({ settings: { language: 'fr' }, expected: { language: 'en' } }, 'wrong')).status,
      401,
    );
    for (const settings of [
      { language: 'fr' },
      { auto_framing: true },
      { carousel_portraits: 5 },
      { c20_speaker_volume: 76 },
      ...[0, 30, 60, 120, 300, 600, 1200].map((seconds) => ({ tv_idle_seconds: seconds })),
      ...[10, 30, 60, 120, 300, 600].map((seconds) => ({
        auto_answer: true,
        auto_answer_seconds: seconds,
      })),
      { auto_answer: false },
    ]) {
      const previous = store.config('term1');
      const expected = Object.fromEntries(Object.keys(settings).map((key) => [key, previous[key]]));
      const reply = await post({ settings, expected });
      assert.equal(reply.status, 200);
      const config = await reply.json();
      for (const [key, value] of Object.entries(settings)) {
        assert.equal(config[key], value);
        assert.equal(new Store(directory).config('term1')[key], value);
      }
    }
    // Other terminal's configuration version is global; all its actual fields stay unchanged.
    const other = JSON.parse(untouched);
    other.configuration_version = store.value.configuration_version;
    assert.deepEqual(store.config('other'), other);
    const invalid = [
      { settings: { sip: {} }, expected: { sip: {} } },
      { settings: { language: 'en' }, expected: { language: 'fr' }, terminal_id: 'other' },
      { settings: { auto_answer_seconds: 601 }, expected: { auto_answer_seconds: 600 } },
      { settings: { carousel_portraits: 4 }, expected: { carousel_portraits: 5 } },
      { settings: { auto_framing: 'yes' }, expected: { auto_framing: true } },
      { settings: { c20_speaker_volume: -1 }, expected: { c20_speaker_volume: 76 } },
      ...[-1, 31, 1201, true, '30', null].map((value) => ({
        settings: { tv_idle_seconds: value },
        expected: { tv_idle_seconds: 1200 },
      })),
      { settings: {}, expected: {} },
      { settings: [], expected: {} },
    ];
    const before = JSON.stringify(store.value);
    for (const body of invalid) assert.equal((await post(body)).status, 400);
    assert.equal(JSON.stringify(store.value), before);
    assert.equal(
      (await post({ settings: { language: 'de' }, expected: { language: 'en' } })).status,
      409,
    );
    assert.equal(store.config('term1').language, 'fr');
    // A lost acknowledgement can safely retry the same field/value.
    assert.equal(
      (await post({ settings: { language: 'fr' }, expected: { language: 'en' } })).status,
      200,
    );
  } finally {
    await fixture.close();
  }
});

test('ringing budget covers a ten-minute answer delay, with normal manual-call timeout', async () => {
  const fixture = await httpFixture();
  try {
    const { store } = fixture;
    assert.equal(store.ringTimeout('term1'), 60);
    store.value.users.term1.auto_answer = true;
    store.value.users.term1.auto_answer_seconds = 600;
    assert.equal(store.ringTimeout('term1'), 630);
    assert.equal(store.ringTimeout('phone1'), 60);
  } finally {
    await fixture.close();
  }
});
