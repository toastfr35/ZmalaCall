// @test S-HLT-002
// @requirements HLR-SRV-AUTH-001
// @environment portable
// @plan Exercise first setup, login, CSRF, logout and password replacement over the assembled HTTP application; restart credential storage and assert old credentials/sessions are revoked and simultaneous setup cannot replace the winner.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { httpFixture } = require('../../support/server/http-fixture');
const { createHandler } = require('../../../zmala_server/http/handler');
const { Readable } = require('node:stream');
const { Store } = require('../../../zmala_server/store');
const { hashPassword, verifyPassword } = require('../../../zmala_server/admin-sessions');

test('password-only setup, login, CSRF, logout and password change revoke old credentials', async () => {
  const fixture = await httpFixture();
  const { base, store, adminSessions } = fixture;
  const password = 'test admin password 2026';
  async function request(route, method = 'GET', body, cookie) {
    const response = await fetch(base + '/api/auth/' + route, {
      method,
      headers: {
        'Content-Type': 'application/json',
        Origin: base,
        ...(cookie ? { Cookie: cookie } : {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    return {
      status: response.status,
      cookie: response.headers.get('set-cookie')?.split(';')[0],
      body: await response.json(),
    };
  }
  try {
    assert.equal((await request('status')).body.setup_required, true);
    assert.equal((await request('setup', 'POST', { password: 'short' })).status, 400);
    const setup = await request('setup', 'POST', { password });
    assert.equal(setup.status, 200);
    assert.equal(
      'session_token' in setup.body,
      false,
      'Browser login does not expose its session credential',
    );
    const serialized = fs.readFileSync(store.file, 'utf8');
    assert.equal(serialized.includes(password), false);
    assert.equal('admin_password_hash' in JSON.parse(serialized), false);
    assert.equal(fs.readFileSync(store.adminPassword.file, 'utf8').includes(password), false);
    assert.equal(await verifyPassword(password, store.adminPassword.hash), true);
    assert.equal((await request('status')).body.setup_required, false);
    assert.equal((await request('setup', 'POST', { password })).status, 403);
    let reply = await fetch(base + '/api/admin', { headers: { Cookie: setup.cookie } });
    assert.equal(reply.status, 200);
    const model = await reply.json();
    assert.equal('admin_password_hash' in model, false);
    assert.equal('admin_token' in model, false);
    assert.equal(
      (
        await fetch(base + '/api/admin', {
          headers: { Authorization: 'Bearer ' + store.value.admin_token },
        })
      ).status,
      401,
    );
    assert.equal(
      (await fetch(base + '/api/config', { headers: { Cookie: setup.cookie } })).status,
      401,
    );
    reply = await fetch(base + '/api/auth/logout', {
      method: 'POST',
      headers: { Cookie: setup.cookie },
    });
    assert.equal(reply.status, 403, 'Cookie mutations need an exact same origin');
    reply = await fetch(base + '/api/auth/login', {
      method: 'POST',
      headers: { Origin: 'http://evil.example' },
      body: JSON.stringify({ password }),
    });
    assert.equal(reply.status, 403);
    assert.equal((await request('logout', 'POST', {}, setup.cookie)).status, 200);
    assert.equal(
      (await fetch(base + '/api/admin', { headers: { Cookie: setup.cookie } })).status,
      401,
    );
    adminSessions.attempts.clear();
    assert.equal((await request('login', 'POST', { password: 'incorrect password' })).status, 401);
    const first = await request('login', 'POST', { password });
    const second = await request('login', 'POST', { password });
    assert.equal(first.status, 200);
    adminSessions.attempts.clear();
    const changed = await request(
      'password',
      'POST',
      { current_password: password, password: 'replacement admin password' },
      first.cookie,
    );
    assert.equal(changed.status, 200);
    assert.equal(
      (await fetch(base + '/api/admin', { headers: { Cookie: second.cookie } })).status,
      401,
    );
    assert.equal((await request('login', 'POST', { password })).status, 401);
    assert.equal(
      (await request('login', 'POST', { password: 'replacement admin password' })).status,
      200,
    );
    assert.equal(fs.existsSync(path.join(store.dir, 'open-admin.url')), false);
  } finally {
    await fixture.close();
  }
});

test('password file migrates once and deletion resets only authentication after restart', async () => {
  const fixture = await httpFixture();
  const { store } = fixture;
  try {
    const hash = await hashPassword('legacy admin password');
    await fixture.flush();
    const legacy = JSON.parse(fs.readFileSync(store.file, 'utf8'));
    legacy.admin_password_hash = hash;
    fs.writeFileSync(store.file, JSON.stringify(legacy));
    const migrated = new Store(store.dir);
    assert.equal(migrated.adminPassword.hash, hash);
    assert.equal('admin_password_hash' in JSON.parse(fs.readFileSync(store.file, 'utf8')), false);
    const accounts = JSON.stringify(migrated.value.users);
    const profiles = JSON.stringify(migrated.value.profiles);
    fs.unlinkSync(migrated.adminPassword.file);
    migrated.changed();
    assert.equal(
      fs.existsSync(migrated.adminPassword.file),
      false,
      'Account saves do not recreate the password file',
    );
    const restarted = new Store(store.dir);
    assert.equal(restarted.adminPassword.hash, undefined);
    assert.equal(JSON.stringify(restarted.value.users), accounts);
    assert.equal(JSON.stringify(restarted.value.profiles), profiles);
    fs.writeFileSync(restarted.adminPassword.file, '{broken');
    assert.throws(() => new Store(store.dir), /JSON|Unexpected/);
    fs.writeFileSync(restarted.adminPassword.file, '{}');
    assert.throws(() => new Store(store.dir), /Invalid admin password file/);
  } finally {
    await fixture.close();
  }
});

test('remote first setup is allowed once, including simultaneous requests; TLS sessions use secure cookies', async () => {
  const fixture = await httpFixture();
  try {
    const handler = createHandler({ ...fixture, terminalStatuses: {} });
    async function setup(password) {
      const req = Readable.from([Buffer.from(JSON.stringify({ password }))]);
      Object.assign(req, {
        method: 'POST',
        url: '/api/auth/setup',
        socket: { remoteAddress: '192.168.1.45', encrypted: true },
        headers: {
          host: `${fixture.store.value.host}:${fixture.store.value.http_port}`,
          origin: `https://${fixture.store.value.host}:${fixture.store.value.http_port}`,
        },
      });
      const res = {
        headers: {},
        setHeader(key, value) {
          this.headers[key] = value;
        },
        writeHead(status, headers) {
          this.status = status;
          Object.assign(this.headers, headers);
        },
        end(body) {
          this.body = JSON.parse(body);
        },
      };
      await handler(req, res);
      return res;
    }
    const replies = await Promise.all([
      setup('first remote password'),
      setup('other remote password'),
    ]);
    assert.deepEqual(replies.map((r) => r.status).sort(), [200, 409]);
    const winner = replies.find((r) => r.status === 200);
    assert.match(winner.headers['Set-Cookie'], /HttpOnly; SameSite=Strict; Max-Age=28800; Secure$/);
    assert.equal(
      await verifyPassword('first remote password', fixture.store.adminPassword.hash),
      replies[0].status === 200,
    );
    assert.equal((await setup('cannot replace password')).status, 403);
  } finally {
    await fixture.close();
  }
});
