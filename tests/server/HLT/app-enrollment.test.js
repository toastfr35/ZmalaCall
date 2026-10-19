// @test S-HLT-031
// @requirements HLR-SRV-APP-001
// @environment portable
// @plan Fetch app configuration and QR PDFs from a disposable HTTP server, attempt terminal and administrator APIs with an app token, convert the account and retry both old and new credentials.
// Inspect the App PDF's clickable latest APK URL and one-page structure.
// @pass App enrollment succeeds only for its account type and all forbidden or revoked access attempts fail.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { httpFixture } = require('../../support/server/http-fixture');
test('HTTP app enrollment is isolated from terminal and administrative control', async () => {
  const fixture = await httpFixture();
  const { store, base } = fixture;
  const token = store.value.users.phone1.device_token;
  const get = (route, credential = token) =>
    fetch(base + route, { headers: { Authorization: 'Bearer ' + credential } });
  try {
    let response = await get('/api/app/config');
    assert.equal(response.status, 200);
    const config = await response.json();
    assert.equal(config.sip.username, 'phone1');
    assert.equal(config.account_type, 'app');
    assert.ok(config.contacts.every((c) => typeof c.online === 'boolean'));
    for (const route of [
      '/api/config',
      '/api/status',
      '/api/console/next',
      '/api/device/settings',
      '/api/callbacks',
    ]) {
      response = await get(route);
      assert.equal(response.status, 403, route);
      await response.arrayBuffer();
    }
    response = await get('/api/admin');
    assert.ok([401, 403].includes(response.status));
    await response.arrayBuffer();
    response = await get('/api/app/config', store.value.users.term1.device_token);
    assert.equal(response.status, 403);
    await response.arrayBuffer();
    response = await get('/api/setup/server.pdf?id=phone1', store.value.admin_token);
    assert.equal(response.status, 200);
    const pdf = Buffer.from(await response.arrayBuffer());
    assert.equal(pdf.subarray(0, 5).toString(), '%PDF-');
    assert.match(
      pdf.toString('latin1'),
      /\/URI \(https:\/\/github.com\/toastfr35\/ZmalaCall\/releases\/latest\/download\/ZmalaPhone.apk\)/,
    );
    assert.equal((pdf.toString('latin1').match(/\/Type \/Page\b/g) || []).length, 1);
    store.updateAccount('phone1', { name: 'Converted', type: 'terminal' });
    response = await get('/api/app/config');
    assert.equal(response.status, 401);
    await response.arrayBuffer();
    response = await get('/api/config', store.value.users.phone1.device_token);
    assert.equal(response.status, 200);
    await response.arrayBuffer();
  } finally {
    await fixture.close();
  }
});
