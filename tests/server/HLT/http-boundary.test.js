// @test S-HLT-011
// @requirements HLR-SRV-AUTH-013
// @environment portable
// @plan Send foreign-Origin, invalid-object and oversized HTTP requests to an isolated application; assert rejection before any store mutation.
// Through the assembled HTTP listener, supply simulated LAN/WAN socket metadata and verify that
// WAN peers cannot use UI, login or valid admin sessions, while enrolled device configuration remains available.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { httpFixture } = require('../../support/server/http-fixture');

test('assembled server separates LAN administration from internet device access', async (t) => {
  t.mock.method(require('node:os'), 'networkInterfaces', () => ({
    eth0: [{ address: '192.168.1.10', cidr: '192.168.1.10/24', internal: false }],
  }));
  const fixture = await httpFixture();
  let peer = '192.168.1.20';
  // The listener and dispatch are real; ingress addresses are simulated, not an external-network test.
  fixture.server.prependListener('request', (req) => {
    Object.defineProperty(req.socket, 'remoteAddress', { value: peer, configurable: true });
    Object.defineProperty(req.socket, 'localAddress', {
      value: '192.168.1.10',
      configurable: true,
    });
  });
  const admin = { Authorization: 'Bearer ' + fixture.adminSessions.create() };
  try {
    assert.equal((await fetch(fixture.base + '/')).status, 200);
    assert.equal((await fetch(fixture.base + '/api/admin', { headers: admin })).status, 200);
    peer = '203.0.113.22';
    for (const route of ['/', '/admin.css', '/api/auth/status', '/api/admin', '/api/backup/export'])
      assert.equal(
        (
          await fetch(fixture.base + route, {
            headers: { ...admin, 'X-Forwarded-For': '127.0.0.1', Forwarded: 'for=192.168.1.20' },
          })
        ).status,
        403,
        route,
      );
    assert.equal(
      (await fetch(fixture.base + '/api/auth/login', { method: 'POST', body: '{}' })).status,
      403,
    );
    assert.equal(
      (
        await fetch(fixture.base + '/api/config', {
          headers: { Authorization: 'Bearer ' + fixture.store.value.users.term1.device_token },
        })
      ).status,
      200,
    );
    assert.equal((await fetch(fixture.base + '/api/config', { headers: admin })).status, 401);
    assert.equal((await fetch(fixture.base + '/health')).status, 200);
  } finally {
    await fixture.close();
  }
});

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
