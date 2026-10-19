// @test S-HLT-012
// @requirements HLR-SRV-AUTH-012
// @environment portable
// @plan Request device configuration and admin endpoints from LAN-like peers; assert enrollment credentials work while administration still requires a valid admin session.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { httpFixture } = require('../../support/server/http-fixture');
const { createHandler } = require('../../../zmala_server/http/handler');

test('LAN terminals can fetch config; administration requires an admin session', async (t) => {
  t.mock.method(require('node:os'), 'networkInterfaces', () => ({
    eth0: [{ address: '192.168.1.10', cidr: '192.168.1.10/24', internal: false }],
  }));
  const fixture = await httpFixture();
  try {
    const handler = createHandler({ ...fixture, terminalStatuses: {} });
    async function request(url, token, remote = '192.168.1.45', host, origin) {
      const req = {
        method: 'GET',
        url,
        socket: { remoteAddress: remote, localAddress: '192.168.1.10' },
        headers: {
          host: host || `${fixture.store.value.host}:${fixture.store.value.http_port}`,
          authorization: token ? `Bearer ${token}` : undefined,
          origin,
        },
      };
      const res = {
        writeHead(status) {
          this.status = status;
        },
        end(body) {
          this.body = body;
        },
      };
      await handler(req, res);
      return res;
    }
    const device = fixture.store.value.users.term1.device_token;
    assert.equal((await request('/api/config', device)).status, 200);
    assert.equal(JSON.parse((await request('/api/config', device)).body).sip.username, 'term1');
    assert.equal((await request('/api/config')).status, 401);
    assert.equal((await request('/api/admin', fixture.store.value.admin_token)).status, 401);
    assert.equal((await request('/api/admin', device)).status, 401);
    assert.equal((await request('/api/config', device, undefined, 'evil.example')).status, 403);
    assert.equal(
      (await request('/api/config', device, undefined, undefined, 'https://evil.example')).status,
      403,
    );
    assert.equal((await request('/', undefined, '127.0.0.1')).status, 200);
    assert.equal((await request('/')).status, 200, 'LAN browsers can reach the sign-in page');
    const session = fixture.adminSessions.create();
    assert.equal((await request('/api/admin', session)).status, 200);
    assert.match(
      fixture.store.bootstrap('term1', true).server_url,
      new RegExp(`^http://${fixture.store.value.host.replaceAll('.', '\\.')}:`),
    );
    assert.match(fixture.store.bootstrap().server_url, /^http:\/\/127\.0\.0\.1:/);
    for (const shell of ['sh', 'bash']) {
      fixture.store.setSettings('term1', {
        display_name: 'Linux',
        camera: '',
        microphone: '',
        speaker: '',
        command_shell: shell,
      });
      assert.equal(fixture.store.config('term1').command_shell, shell);
    }
  } finally {
    await fixture.close();
  }
});
