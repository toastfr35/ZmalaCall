// @test S-LLT-024
// @requirements LLR-SRV-AUTH-015, LLR-SRV-AUTH-016, LLR-SRV-AUTH-019, LLR-SRV-CALLBACK-023, LLR-SRV-CALLBACK-024
// @environment portable
// @plan Feed malformed credential files and password-change races into authentication units; assert fail-closed startup, current-password verification, durable replacement and session revocation. Inject SMTP transport to check secret retention, certificate-safe options and verify-only behavior.
// @pass All failure cases must preserve credentials and sessions; successful changes revoke old sessions and transport tests never send email.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { storeFixture, context, request, response } = require('../../support/server/unit-fixture');
const { AdminPassword } = require('../../../zmala_server/admin-password');
const { hashPassword, verifyPassword } = require('../../../zmala_server/admin-sessions');
const { authRoutes } = require('../../../zmala_server/http/auth-routes');
const { CallbackMailer } = require('../../../zmala_server/callback-mailer');
const { validateSmtpSettings, smtpView } = require('../../../zmala_server/callback-settings');

test('malformed existing password state never reopens setup; deliberate removal does', (t) => {
  const s = storeFixture(t),
    file = s.adminPassword.file;
  for (const contents of ['{', 'null', '{}', '{"password_hash":"invalid"}']) {
    fs.writeFileSync(file, contents);
    assert.throws(() => new AdminPassword(s.dir));
  }
  fs.unlinkSync(file);
  assert.equal(new AdminPassword(s.dir).hash, undefined);
});

test('password replacement checks current value, serializes changes and revokes sessions only after save', async (t) => {
  const s = storeFixture(t),
    ctx = context(s);
  s.adminPassword.setHash(await hashPassword('fixture old password'));
  const original = s.adminPassword.hash,
    session = ctx.adminSessions.create();
  const change = async (value) => {
    const res = response(),
      url = new URL('http://localhost/api/auth/password');
    await authRoutes(request(url.pathname, { method: 'POST', value }), res, url, ctx, {
      local: true,
      secure: false,
      admin: true,
    });
    return res;
  };
  await assert.rejects(change({ current_password: 'wrong', password: 'fixture new password' }), {
    status: 401,
  });
  ctx.adminSessions.changing = true;
  await assert.rejects(
    change({ current_password: 'fixture old password', password: 'fixture new password' }),
    { status: 409 },
  );
  ctx.adminSessions.changing = false;
  const save = t.mock.method(s.adminPassword, 'setHash', () => {
    throw Error('disk failed');
  });
  await assert.rejects(
    change({ current_password: 'fixture old password', password: 'fixture new password' }),
    /disk failed/,
  );
  assert.equal(s.adminPassword.hash, original);
  assert.equal(ctx.adminSessions.valid(session), true);
  assert.equal(ctx.adminSessions.changing, false);
  save.mock.restore();
  const result = await change({
    current_password: 'fixture old password',
    password: 'fixture new password',
  });
  assert.equal(result.status, 200);
  assert.equal(ctx.adminSessions.valid(session), false);
  assert.equal(await verifyPassword('fixture new password', new AdminPassword(s.dir).hash), true);
  assert.equal(result.json().session_token, undefined);
});

test('ordinary login uses cookie; explicitly requested API session returns a valid bearer', async (t) => {
  const ctx = context(storeFixture(t));
  ctx.store.adminPassword.setHash(await hashPassword('fixture password'));
  for (const requested of [false, true]) {
    const res = response(),
      url = new URL('http://localhost/api/auth/login');
    await authRoutes(
      request(url.pathname, {
        method: 'POST',
        value: { password: 'fixture password', session_token: requested },
      }),
      res,
      url,
      ctx,
      { local: false, admin: false, secure: true },
    );
    assert.match(res.headers['Set-Cookie'], /HttpOnly; SameSite=Strict;.*Secure/);
    assert.equal(ctx.adminSessions.valid(res.json().session_token), requested);
  }
});

test('SMTP validates configuration, preserves blank secrets and verifies without sending', async (t) => {
  const s = storeFixture(t);
  const settings = {
    enabled: true,
    host: 'smtp.example.test',
    port: 587,
    security: 'starttls',
    username: 'fixture',
    password: 'private',
    from: 'a@example.test',
  };
  const kept = validateSmtpSettings({ ...settings, password: '' }, settings);
  assert.equal(kept.password, 'private');
  assert.equal('password' in smtpView(kept), false);
  assert.equal(
    validateSmtpSettings({ ...settings, enabled: false, clear_password: true }, settings).password,
    '',
  );
  for (const invalid of [
    { port: 0 },
    { port: 65536 },
    { security: 'invalid' },
    { host: 'host\nsecret' },
    { clear_password: 'yes' },
  ])
    assert.throws(() => validateSmtpSettings({ ...settings, ...invalid }, settings));
  let verified = 0;
  const options = [];
  const mailer = new CallbackMailer(s, (option) => {
    options.push(option);
    return {
      verify: async () => {
        verified++;
      },
      sendMail: () => assert.fail('verify must not send mail'),
    };
  });
  for (const security of ['starttls', 'tls', 'none']) {
    s.value.smtp = { ...settings, security };
    await mailer.verify();
    const option = options.at(-1);
    assert.equal(option.secure, security === 'tls');
    assert.equal(option.requireTLS, security === 'starttls');
    assert.equal(option.ignoreTLS, security === 'none');
    assert.notEqual(option.tls?.rejectUnauthorized, false);
    assert.deepEqual(option.auth, { user: 'fixture', pass: 'private' });
  }
  assert.equal(verified, 3);
  mailer.transportFactory = () => ({
    verify: async () => {
      throw Object.assign(Error('provider secret'), { code: 'EAUTH' });
    },
  });
  await assert.rejects(mailer.verify(), { message: 'SMTP authentication failed.' });
});
