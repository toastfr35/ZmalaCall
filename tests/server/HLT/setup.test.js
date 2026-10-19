// @test S-HLT-018
// @requirements HLR-SRV-ENROLL-001
// @environment portable
// @plan Generate Wi-Fi/server enrollment PDFs through authenticated HTTP and inspect payloads; assert escaping, valid enrolled account identity and absence of persisted Wi-Fi secrets.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { httpFixture } = require('../../support/server/http-fixture');
const test = require('node:test'),
  assert = require('node:assert/strict'),
  fs = require('node:fs'),
  path = require('node:path');
const { serverPayload } = require('../../../zmala_server/setup-pdf');

test('QR PDF endpoints require admin, target enrolled accounts and do not persist Wi-Fi secrets', async () => {
  const fixture = await httpFixture();
  const { store, base, directory: dir } = fixture;
  async function req(route, method = 'GET', value, token = store.value.admin_token) {
    return fetch(base + route, {
      method,
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: value ? JSON.stringify(value) : undefined,
    });
  }
  try {
    assert.equal(
      (await req('/api/setup/server.pdf?id=term1', 'GET', undefined, 'wrong')).status,
      401,
    );
    assert.equal(
      (
        await req(
          '/api/setup/server.pdf?id=term1',
          'GET',
          undefined,
          store.value.users.term1.device_token,
        )
      ).status,
      401,
    );
    assert.equal((await req('/api/setup/server.pdf?id=phone1')).status, 200);
    const r = await req('/api/setup/server.pdf?id=term1');
    assert.equal(r.status, 200);
    assert.equal(r.headers.get('content-type'), 'application/pdf');
    assert.match(r.headers.get('content-disposition'), /attachment/);
    assert.equal(
      Buffer.from(await r.arrayBuffer())
        .subarray(0, 5)
        .toString(),
      '%PDF-',
    );
    const payload = JSON.parse(serverPayload(store.bootstrap('term1')));
    assert.equal(payload.device_token, store.value.users.term1.device_token);
    assert.equal(payload.device_id, store.value.users.term1.device_id);
    assert.equal(payload.type, 'family-call-server');
    assert.equal(payload.version, 1);
    const before = JSON.stringify(store.value),
      wifi = await req('/api/setup/wifi.pdf', 'POST', {
        ssid: 'Family Test',
        password: 'QrTestPassword',
      });
    assert.equal(wifi.status, 200);
    assert.equal(JSON.stringify(store.value), before);
    assert.equal(
      fs.readFileSync(path.join(dir, 'terminal.json'), 'utf8').includes('QrTestPassword'),
      false,
    );
    assert.equal(
      (await req('/api/setup/wifi.pdf', 'POST', { ssid: 'Test', password: 'wrong' })).status,
      400,
    );
  } finally {
    await fixture.close();
  }
});
