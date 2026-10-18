// @test S-HLT-016
// @requirements HLR-SRV-INSTALL-002, HLR-SRV-AUTH-001
// @environment portable
// @plan Exercise server SSH endpoints and Host validation through HTTP with a controlled SSH backend; assert admin-only boolean writes and acceptance only of the configured server identity. Physical firewall behavior is covered separately.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { httpFixture } = require('../../support/server/http-fixture');
const { setSsh } = require('../../../zmala_server/server-ssh');

test('SSH control requires administration and rejects non-boolean input', async () => {
  const fixture = await httpFixture();
  try {
    const url = fixture.base + '/api/server/ssh';
    assert.equal((await fetch(url)).status, 401);
    assert.equal(
      (
        await fetch(url, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: '{"enabled":false}',
        })
      ).status,
      401,
    );
    const headers = {
      Authorization: 'Bearer ' + fixture.store.value.admin_token,
      'Content-Type': 'application/json',
    };
    const response = await fetch(url, { headers });
    assert.equal(response.status, 200);
    assert.equal(typeof (await response.json()).supported, 'boolean');
    const invalid = await fetch(url, { method: 'PUT', headers, body: '{"enabled":"false"}' });
    assert.equal(invalid.status, 400);
    assert.match((await invalid.json()).error, /true or false/);
    await assert.rejects(setSsh('on; shutdown now'), /true or false/);
  } finally {
    await fixture.close();
  }
});

test('explicit server hostname is accepted but unrelated Host names remain rejected', async () => {
  const previous = process.env.ZMALA_SERVER_NAME;
  process.env.ZMALA_SERVER_NAME = 'zmalaserver.local';
  const fixture = await httpFixture();
  try {
    const port = new URL(fixture.base).port;
    const request = (host) =>
      new Promise((resolve, reject) => {
        http
          .get(fixture.base + '/health', { headers: { Host: host + ':' + port } }, (response) => {
            response.resume();
            response.on('end', () => resolve(response.statusCode));
          })
          .on('error', reject);
      });
    assert.equal(await request('zmalaserver.local'), 200);
    assert.equal(await request('untrusted.example'), 403);
  } finally {
    if (previous === undefined) delete process.env.ZMALA_SERVER_NAME;
    else process.env.ZMALA_SERVER_NAME = previous;
    await fixture.close();
  }
});
