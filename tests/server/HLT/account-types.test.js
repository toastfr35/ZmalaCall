// @test S-HLT-001
// @requirements HLR-SRV-DIR-001, HLR-SRV-DIR-002
// @environment portable
// @plan Use authenticated HTTP account edits and inspect persisted configuration; assert conversion revokes terminal enrollment while retaining personal fields and malformed selections cannot mutate state.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { httpFixture } = require('../../support/server/http-fixture');

test('account type changes preserve personal details and revoke terminal enrollment', async () => {
  const fixture = await httpFixture();
  const { store, base } = fixture;
  const request = async (pathname, method, body) => {
    const response = await fetch(base + pathname, {
      method,
      headers: {
        Authorization: `Bearer ${store.value.admin_token}`,
        'Content-Type': 'application/json',
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return { status: response.status, body: await response.json() };
  };
  try {
    const account = store.value.users.term1;
    const token = account.device_token;
    const serial = account.device_id;
    const password = account.password;
    account.emails = ['family@example.test'];
    account.photo = '/photos/abcd.png';
    assert.equal(
      (await request('/api/users/term1', 'PUT', { name: 'Family', type: 'linphone' })).status,
      200,
    );
    const phone = store.value.users.term1;
    assert.equal(phone.password, password);
    assert.deepEqual(phone.emails, ['family@example.test']);
    assert.equal(phone.photo, '/photos/abcd.png');
    for (const field of ['device_id', 'device_token', 'auto_answer', 'auto_answer_seconds'])
      assert.equal(Object.hasOwn(phone, field), false);
    assert.equal(store.deviceAccount(token), undefined);
    assert.equal(store.value.local_terminal_id, null);
    assert.equal((await request('/api/admin', 'GET')).status, 200);
    assert.equal(store.bootstrap().device_id, 'unassigned');
    assert.throws(() => store.config(), /Choose a terminal/);

    assert.equal(
      (
        await request('/api/users/term1', 'PUT', {
          name: 'Family',
          type: 'terminal',
          auto_answer: true,
          auto_answer_seconds: 12,
        })
      ).status,
      200,
    );
    const terminal = store.value.users.term1;
    assert.notEqual(terminal.device_id, serial);
    assert.notEqual(terminal.device_token, token);
    assert.equal(terminal.password, password);
    assert.equal(terminal.photo, phone.photo);
    assert.deepEqual(terminal.emails, phone.emails);
    assert.equal(store.config().auto_answer_seconds, 12);
    assert.equal(store.config().auto_answer, true);
    assert.equal(store.deviceAccount(terminal.device_token), 'term1');
  } finally {
    await fixture.close();
  }
});

test('non-string account selections fail without changing configuration', async () => {
  const fixture = await httpFixture();
  const { store, base } = fixture;
  try {
    const snapshot = JSON.stringify(store.value);
    for (const value of [null, true, 42, [], {}]) {
      for (const [pathname, body] of [
        ['/api/local-terminal', { id: value }],
        ['/api/terminal-association', { account_id: value, serial_number: 'windows-terminal' }],
        ['/api/settings', { terminal_id: value }],
      ]) {
        const response = await fetch(base + pathname, {
          method: 'PUT',
          headers: {
            Authorization: `Bearer ${store.value.admin_token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(body),
        });
        assert.equal(response.status, 400);
        await response.arrayBuffer();
        assert.equal(JSON.stringify(store.value), snapshot);
      }
    }
  } finally {
    await fixture.close();
  }
});
