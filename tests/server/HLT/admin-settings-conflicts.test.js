// @test S-HLT-003
// @requirements HLR-SRV-DIR-018, HLR-SRV-CONFIG-015
// @environment portable
// @plan Perform concurrent admin and terminal edits through HTTP; assert stale revisions receive conflicts without overwriting newer settings, accounts, credentials or groups.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { httpFixture } = require('../../support/server/http-fixture');
const { Store } = require('../../../zmala_server/store');

test('stale admin settings cannot overwrite another admin or local terminal edit', async () => {
  const fixture = await httpFixture();
  const { store, base, directory } = fixture;
  const save = (value) =>
    fetch(base + '/api/settings', {
      method: 'PUT',
      headers: {
        Authorization: 'Bearer ' + store.value.admin_token,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(value),
    });
  const draft = () => ({
    terminal_id: 'term1',
    configuration_version: store.value.configuration_version,
    ...store.value.profiles.term1,
    ...store.value.profiles.term1.terminal_settings,
  });
  try {
    const old = draft();
    const [first, second] = await Promise.all([
      save({ ...old, video_fps: 20 }),
      save({ ...old, video_fps: 30 }),
    ]);
    assert.deepEqual([first.status, second.status].sort(), [200, 409]);
    const accepted = await (first.status === 200 ? first : second).json();
    assert.equal(accepted.configuration_version, store.value.configuration_version);
    assert.equal(new Store(directory).config('term1').video_fps, store.config('term1').video_fps);

    const shellDraft = draft();
    store.setDeviceSettings(
      'term1',
      { language: 'fr' },
      { language: store.config('term1').language },
    );
    await store.flush();
    const current = JSON.stringify(store.value);
    const rejected = await save({ ...shellDraft, command_shell: 'bash' });
    assert.equal(rejected.status, 409);
    assert.match((await rejected.json()).error, /Configuration changed/);
    assert.equal(
      JSON.stringify(store.value),
      current,
      'Conflict must not mutate any profile fields',
    );
    assert.equal(new Store(directory).config('term1').language, 'fr');

    const fresh = await save({ ...draft(), command_shell: 'bash' });
    assert.equal(fresh.status, 200);
    assert.equal(store.config('term1').language, 'fr');
    assert.equal(store.value.profiles.term1.command_shell, 'bash');
  } finally {
    await fixture.close();
  }
});

test('account edits and delete confirmations reject stale revisions without changing credentials or groups', async () => {
  const fixture = await httpFixture();
  const { store, base } = fixture;
  const request = (method, data) =>
    fetch(base + '/api/users/phone1', {
      method,
      headers: {
        Authorization: 'Bearer ' + store.value.admin_token,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });
  try {
    const version = store.value.configuration_version;
    const draft = {
      ...store.value.users.phone1,
      emails: ['phone@example.test'],
      configuration_version: version,
    };
    assert.equal((await request('PUT', { ...draft, name: 'New name' })).status, 200);
    const saved = JSON.stringify(store.value);
    assert.equal((await request('PUT', { ...draft, name: 'Old editor' })).status, 409);
    assert.equal((await request('DELETE', { configuration_version: version })).status, 409);
    assert.equal(JSON.stringify(store.value), saved);
    assert.equal(
      (await request('DELETE', { configuration_version: store.value.configuration_version }))
        .status,
      200,
    );
    assert.equal(store.value.users.phone1, undefined);
  } finally {
    await fixture.close();
  }
});
