// @test S-HLT-007
// @requirements HLR-SRV-CALLBACK-001
// @environment portable
// @plan Use authenticated HTTP SMTP settings with an isolated SMTP service; assert secret retention/privacy, connection checks without sending mail, and reminder delivery through the configured mailer.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');

const { CallbackMailer } = require('../../../zmala_server/callback-mailer');
const { httpFixture } = require('../../support/server/http-fixture');
const { smtpFixture } = require('../../support/server/smtp-fixture');
const flush = () => new Promise((resolve) => setImmediate(resolve));
async function settled(service) {
  while (service.email.sending.size) await flush();
}

test('SMTP settings and deadlines require admin; secrets are retained privately and connection checks send no mail', async (t) => {
  const fixture = await httpFixture();
  t.after(() => fixture.close());
  const smtp = await smtpFixture();
  t.after(() => smtp.close());
  const { store, callbacks } = fixture;
  async function request(route, value, token = store.value.admin_token) {
    const response = await fetch(fixture.base + route, {
      method: 'PUT',
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify(value),
    });
    return { status: response.status, body: await response.json() };
  }
  const settings = {
    enabled: true,
    host: '127.0.0.1',
    port: smtp.port,
    security: 'none',
    username: 'test',
    password: 'private-test-password',
    from: 'sender@example.test',
  };
  assert.equal(
    (await request('/api/smtp-settings', settings, store.value.users.term1.device_token)).status,
    401,
  );
  assert.equal(
    (
      await request(
        '/api/callback-settings',
        { email_after_hours: 1, remove_after_hours: 2 },
        'wrong',
      )
    ).status,
    401,
  );
  assert.equal((await request('/api/smtp-settings', settings)).status, 200);
  assert.equal(store.admin().smtp.password, undefined);
  assert.equal(store.admin().smtp.password_set, true);
  assert.equal(store.value.smtp.password, settings.password);
  assert.equal((await request('/api/smtp-settings', { ...settings, password: '' })).status, 200);
  assert.equal(store.value.smtp.password, settings.password);
  const original = JSON.stringify(store.value);
  assert.equal((await request('/api/smtp-settings', { ...settings, from: 'invalid' })).status, 400);
  assert.equal(JSON.stringify(store.value), original);
  const verify = await fetch(fixture.base + '/api/smtp-settings/verify', {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + store.value.admin_token },
  });
  assert.equal(verify.status, 200);
  assert.equal(smtp.messages.length, 0);
  store.updateAccount('phone1', {
    name: 'Noah',
    type: 'linphone',
    emails: ['daniel@example.test'],
  });
  const pending = callbacks.create('term1', 'phone1');
  callbacks.requests[0].email_due_at = new Date(Date.now() - 1).toISOString();
  callbacks.deliver();
  await settled(callbacks);
  assert.equal(smtp.messages.length, 1);
  assert.match(smtp.messages[0].body, /sip:term1@/);
  assert.match(smtp.messages[0].body, new RegExp(pending.id));
  assert.deepEqual(smtp.messages[0].recipients, ['daniel@example.test']);
  assert.equal(callbacks.list()[0].email_sent_to.length, 1);
  const mailer = new CallbackMailer(store);
  await mailer.verify();
  assert.equal(smtp.messages.length, 1);
  store.value.smtp.password = 'wrong-password';
  await assert.rejects(mailer.verify(), /SMTP authentication failed/);
  store.value.smtp.password = settings.password;
  assert.equal(
    (
      await request('/api/smtp-settings', {
        ...settings,
        enabled: false,
        password: '',
        clear_password: true,
      })
    ).status,
    200,
  );
  assert.equal(store.value.smtp.password, '');
  assert.equal(store.admin().smtp.password_set, false);
  assert.equal((await request('/api/smtp-settings', { ...settings, password: '' })).status, 400);
  const missingEmail = await fetch(fixture.base + '/api/users', {
    method: 'POST',
    headers: {
      Authorization: 'Bearer ' + store.value.admin_token,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ id: 'noemail', name: 'No email', type: 'linphone' }),
  });
  assert.equal(missingEmail.status, 400);
  assert.equal(store.value.users.noemail, undefined);
});
