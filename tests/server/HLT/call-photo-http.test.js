// @test S-HLT-037
// @requirements HLR-SRV-MEDIA-008
// @environment portable
// @plan Run the real HTTP handler and image converter against disposable accounts and a connected SIP-dialog fixture. Upload from the app, retrieve from its terminal, stop and close the dialog; reject unauthenticated/third-party reads and verify no portrait is stored.
// @pass Authenticated peers exchange a normalized private JPEG only during the share, and clearing/closure removes access without media operations. Real SIP/media quality is covered separately.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { httpFixture } = require('../../support/server/http-fixture');
test('call photo HTTP boundary normalizes and scopes a disposable image', async () => {
  const f = await httpFixture();
  try {
    const users = f.store.value.users;
    f.store.createAccount({
      id: 'outsider',
      name: 'Other',
      type: 'app',
      emails: ['other@example.test'],
    });
    f.sipServer.dialogs.set('share-http', {
      connected: true,
      peers: [{ user: 'phone1' }, { user: 'term1' }],
    });
    const token = (id) => f.store.enrolledAccount(id).device_token;
    async function request(method, id, extra = '', bytes) {
      return fetch(f.base + '/api/call/photo?call_id=share-http' + extra, {
        method,
        headers: id ? { Authorization: 'Bearer ' + token(id) } : {},
        body: bytes,
      });
    }
    assert.equal((await request('GET')).status, 401);
    assert.equal((await request('GET', 'outsider')).status, 403);
    const png = Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAIAAAABCAIAAAB7QOjdAAAAD0lEQVR4nGNkYPjPwMAAAAQKAQHOAd3hAAAAAElFTkSuQmCC',
      'base64',
    );
    const uploaded = await request('PUT', 'phone1', '', png);
    assert.equal(uploaded.status, 200, await uploaded.clone().text());
    const status = await uploaded.json();
    const photo = await request('GET', 'term1', '&image=1&revision=' + status.revision);
    assert.equal(photo.status, 200);
    assert.equal(photo.headers.get('content-type'), 'image/jpeg');
    assert.equal(photo.headers.get('cache-control'), 'no-store');
    assert.equal(Buffer.from(await photo.arrayBuffer()).readUInt16BE(0), 0xffd8);
    await request('DELETE', 'phone1');
    assert.equal((await (await request('GET', 'term1')).json()).sharing, false);
    f.sipServer.dialogs.clear();
    assert.equal((await request('GET', 'term1')).status, 403);
    assert.ok(
      !fs.existsSync(path.join(f.store.dir, 'photos')) ||
        fs.readdirSync(path.join(f.store.dir, 'photos')).length === 0,
    );
    assert.ok(users.phone1);
  } finally {
    await f.close();
  }
});
