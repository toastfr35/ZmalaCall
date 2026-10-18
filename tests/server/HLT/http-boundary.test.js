// @test S-HLT-011
// @requirements HLR-SRV-AUTH-001
// @environment portable
// @plan Send foreign-Origin, invalid-object and oversized HTTP requests to an isolated application; assert rejection before any store mutation.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { httpFixture } = require('../../support/server/http-fixture');

test('HTTP boundary rejects foreign origins, invalid objects and oversized bodies without mutations', async () => {
  const fixture = await httpFixture();
  const { base, store } = fixture;
  const snapshot = JSON.stringify(store.value);
  const headers = { Authorization: 'Bearer ' + store.value.admin_token };
  try {
    for (const body of ['null', '[]', '1', '{invalid']) {
      const response = await fetch(base + '/api/users', { method: 'POST', headers, body });
      assert.equal(response.status, 400);
      assert.match((await response.json()).error, /JSON object/);
    }
    const large = await fetch(base + '/api/groups', {
      method: 'POST',
      headers,
      body: JSON.stringify({ name: 'x'.repeat(17000) }),
    });
    assert.equal(large.status, 413);
    const foreign = await fetch(base + '/api/admin', {
      headers: { ...headers, Origin: 'https://unrelated.example' },
    });
    assert.equal(foreign.status, 403);
    // fetch normalizes Host from its URL; exercise the actual HTTP header via node:http.
    const spoofed = await new Promise((resolve, reject) => {
      http
        .get(
          base + '/api/admin',
          { headers: { ...headers, Host: 'unrelated.example' } },
          (response) => {
            response.resume();
            response.on('end', () => resolve(response.statusCode));
          },
        )
        .on('error', reject);
    });
    assert.equal(spoofed, 403);
    assert.equal(JSON.stringify(store.value), snapshot);
    const config = await fetch(base + '/api/config', { headers });
    assert.equal(config.status, 401, 'Admin tokens are not terminal identities');
    const module = await fetch(base + '/admin-terminals.js');
    assert.equal(module.status, 200);
    assert.match(module.headers.get('content-type'), /javascript/);
    assert.match(module.headers.get('content-security-policy'), /script-src 'self'/);
  } finally {
    await fixture.close();
  }
});
