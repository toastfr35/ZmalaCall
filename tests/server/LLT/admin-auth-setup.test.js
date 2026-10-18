// @test S-LLT-035
// @requirements LLR-SRV-AUTH-014, LLR-SRV-AUTH-016, LLR-SRV-AUTH-018, LLR-SRV-AUTH-019, LLR-SRV-UI-019
// @environment portable
// @plan Run real authentication and provisioning controllers against recording DOM, HTTP and timer boundaries. Check initial-password confirmation, ordinary login, logout and password-change requests; reject mismatches without HTTP, retain errors and re-enable controls, remove closed dialogs, and clear successful credentials. Check authenticated PDF download payloads, Wi-Fi open-network secret clearing, failed-download feedback and delayed object-URL disposal.
// @pass Every request, visible state and cleanup assertion passes without a real browser or server. Backend authentication, PDF contents and browser rendering are covered separately.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { fixture } = require('../../support/admin-dom.cjs');
const plain = (value) => JSON.parse(JSON.stringify(value));

test('initial password setup validates confirmation and clears credentials only on success', async () => {
  const f = fixture('admin-auth.js');
  f.reply = { setup_required: true };
  const old = f.el('dialog');
  old.showModal();
  f.$('page-actions').append(f.el('button'));
  const controls = f.$('admin-auth-controls');
  await f.signIn();
  await f.signIn();
  assert.equal(f.requests.length, 1);
  assert.equal(old.open, false);
  assert.equal(controls.removed, true);
  assert.equal(f.$('page-actions').children.length, 0);
  assert.equal(f.state.initialized, false);
  const [password, confirmation] = f.inputs();
  assert.equal(password.type, 'password');
  assert.equal(password.minLength, 12);
  assert.equal(password.maxLength, 256);
  assert.equal(password.autocomplete, 'new-password');
  assert.equal(password.required, true);
  password.value = 'a sufficiently long secret';
  confirmation.value = 'different';
  await f.save();
  assert.equal(f.requests.length, 1);
  assert.match(f.find('p').textContent, /do not match/);
  assert.equal(f.button('Set password').disabled, false);
  confirmation.value = password.value;
  await f.save();
  assert.deepEqual(plain(f.requests.at(-1)), {
    url: '/api/auth/setup',
    method: 'POST',
    value: { password: 'a sufficiently long secret' },
  });
  assert.equal(password.value, '');
  assert.equal(confirmation.value, '');
  assert.equal(f.reloaded, 1);
});

test('ordinary login retains drafts and reports typed or untyped request failure', async () => {
  const f = fixture('admin-auth.js');
  f.reply = { setup_required: false };
  await f.signIn();
  const password = f.inputs()[0];
  assert.equal(password.autocomplete, 'current-password');
  assert.equal(password.minLength, undefined);
  password.value = 'existing secret';
  for (const [failure, expected] of [
    [Error('Rate limited'), 'Rate limited'],
    ['offline', 'Sign-in failed.'],
  ]) {
    f.failure = failure;
    await f.save();
    assert.equal(f.find('p').textContent, expected);
    assert.equal(f.find('p').hidden, false);
    assert.equal(f.button('Sign in').disabled, false);
    assert.equal(password.value, 'existing secret');
    assert.equal(f.reloaded, undefined);
  }
  delete f.failure;
  await f.save();
  assert.equal(f.requests.at(-1).url, '/api/auth/login');
  assert.equal(f.reloaded, 1);
  assert.equal(password.value, '');
});

test('auth controls are idempotent and logout failures do not reload the page', async () => {
  const f = fixture('admin-auth.js');
  f.authControls();
  f.authControls();
  assert.equal(f.elements.filter((node) => node.id === 'admin-auth-controls').length, 1);
  for (const [failure, expected] of [
    [Error('Offline'), 'Offline'],
    [null, 'Sign-out failed.'],
  ]) {
    f.failure = failure;
    await f.button('Sign out').click();
    assert.equal(f.messages.at(-1).text, expected);
    assert.equal(f.reloaded, undefined);
  }
  delete f.failure;
  await f.button('Sign out').click();
  assert.deepEqual(plain(f.requests.at(-1)), { url: '/api/auth/logout', method: 'POST' });
  assert.equal(f.reloaded, 1);
});

test('password change validates, exposes failure, and disposes success or cancelled dialogs', async () => {
  const f = fixture('admin-auth.js');
  f.authControls();
  await f.button('Change password').click();
  let dialog = f.find('dialog');
  assert.equal(dialog.open, true);
  const [current, password, confirmation] = f.inputs();
  current.value = 'old secret';
  password.value = 'a new long secret';
  confirmation.value = 'wrong';
  await f.save();
  assert.equal(f.requests.length, 0);
  assert.match(f.find('p').textContent, /do not match/);
  confirmation.value = password.value;
  for (const [failure, expected] of [
    [Error('Current password incorrect'), 'Current password incorrect'],
    [false, 'Password change failed.'],
  ]) {
    f.failure = failure;
    await f.save();
    assert.equal(f.find('p').textContent, expected);
    assert.equal(dialog.open, true);
    assert.equal(f.button('Change password').disabled, false);
  }
  delete f.failure;
  await f.save();
  assert.deepEqual(plain(f.requests.at(-1)), {
    url: '/api/auth/password',
    method: 'POST',
    value: { current_password: 'old secret', password: 'a new long secret' },
  });
  assert.equal(dialog.removed, true);
  assert.equal(dialog.open, false);
  assert.match(f.messages.at(-1).text, /Other sessions/);
  // Reopen using the persistent sidebar control, not a detached modal descendant.
  f.elements
    .find((node) => node.tag === 'button' && node.textContent === 'Change password')
    .click();
  dialog = f.find('dialog');
  await f.button('Cancel').click();
  assert.equal(dialog.removed, true);
});

test('server PDF uses an encoded identity and revokes its private URL after download', async () => {
  const f = fixture('admin-setup.js');
  const blob = { private: true };
  f.response = { ok: true, blob: async () => blob };
  await f.serverPdf('room/1');
  assert.equal(f.requests[0].url, '/api/setup/server.pdf?id=room%2F1');
  assert.equal(f.requests[0].method, 'GET');
  assert.equal(f.requests[0].body, undefined);
  const link = f.elements.find((node) => node.tag === 'a');
  assert.equal(link.download, 'zmalacall-server-room/1.pdf');
  assert.equal(link.clicked, true);
  assert.equal(link.removed, true);
  assert.equal(f.blob, blob);
  assert.equal(f.timers[0].ms, 30000);
  assert.equal(f.revoked.length, 0);
  f.timers[0].action();
  assert.deepEqual(f.revoked, ['blob:private']);
  for (const error of ['Permission denied', '']) {
    f.response = { ok: false, json: async () => ({ error }) };
    await assert.rejects(f.downloadPdf('/private', 'x.pdf'), {
      message: error || 'PDF generation failed.',
    });
  }
});

test('Wi-Fi PDF editor clears open-network secrets, preserves failed drafts and closes after success', async () => {
  const f = fixture('admin-setup.js');
  f.openWifi();
  assert.equal(f.$('wifi-dialog').open, true);
  assert.equal(f.$('wifi-password').required, true);
  f.$('wifi-password').value = 'private secret';
  f.$('wifi-security').value = 'nopass';
  f.$('wifi-security').onchange();
  assert.equal(f.$('wifi-password').value, '');
  assert.equal(f.$('wifi-password').required, false);
  assert.equal(f.$('wifi-password-field').hidden, true);
  f.$('wifi-security').value = 'WPA';
  f.$('wifi-security').onchange();
  assert.equal(f.$('wifi-password').required, true);
  assert.equal(f.$('wifi-password-field').hidden, false);
  f.$('wifi-ssid').value = 'Private network';
  f.$('wifi-password').value = 'private secret';
  f.$('wifi-hidden').checked = true;
  const save = async () => {
    f.$('wifi-form').onsubmit({ preventDefault() {} });
    await f.pending.at(-1);
  };
  f.response = { ok: false, json: async () => ({ error: 'Session expired' }) };
  await save();
  assert.equal(f.messages.at(-1).kind, 'wifi-error');
  assert.equal(f.$('wifi-dialog').open, true);
  assert.equal(f.$('wifi-password').value, 'private secret');
  f.response = { ok: true, blob: async () => ({}) };
  await save();
  assert.deepEqual(JSON.parse(f.requests.at(-1).body), {
    ssid: 'Private network',
    password: 'private secret',
    security: 'WPA',
    hidden: true,
  });
  assert.equal(f.requests.at(-1).headers['Content-Type'], 'application/json');
  assert.equal(f.$('wifi-dialog').open, false);
  assert.equal(f.$('wifi-form').resets, 2);
});
