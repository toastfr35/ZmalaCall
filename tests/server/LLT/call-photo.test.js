// @test S-LLT-066
// @requirements LLR-SRV-MEDIA-016
// @environment portable
// @plan Exercise the live-call route with bounded streams and delayed decoding. Check participants, account kinds, connected state, sender-only mutations, image revision, expiry, stop/end/revocation races and failure recovery.
// @pass Only current authorized participants retrieve photos; stop, expiry and late work cannot resurrect a share or affect another call. No media operation is invoked.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { Readable } = require('node:stream');
const { callPhotoRoute, MAX_BYTES } = require('../../../zmala_server/call-photo');
const { response, storeFixture } = require('../../support/server/unit-fixture');

function fixture() {
  const users = {
    app: { type: 'app', device_token: 'a' },
    term: { type: 'terminal', device_token: 't' },
    other: { type: 'app', device_token: 'x' },
  };
  const dialog = { peers: [{ user: 'app' }, { user: 'term' }], connected: true };
  const context = {
    store: { enrolledAccount: (id) => users[id] },
    sipServer: { dialogs: new Map([['call', dialog]]) },
  };
  const invoke = async (
    method = 'GET',
    user = 'app',
    query = '',
    bytes = Buffer.from('image'),
    convert = async (b) => b,
  ) => {
    const req = Readable.from([bytes]);
    req.method = method;
    const res = response();
    await callPhotoRoute(
      req,
      res,
      new URL('http://local/api/call/photo?call_id=call' + query),
      { ...context, deviceId: user },
      convert,
    );
    return res;
  };
  return { users, dialog, context, invoke };
}
test('participants alone see leased photo; only sender mutates; stop invalidates revision', async () => {
  const { invoke, dialog } = fixture();
  await assert.rejects(invoke('GET', 'other'), { status: 403 });
  await assert.rejects(invoke('PUT', 'term'), { status: 403 });
  const status = (await invoke('PUT')).json();
  assert.equal(status.sharing, true);
  const image = await invoke('GET', 'term', '&image=1&revision=' + status.revision);
  assert.equal(image.bytes.toString(), 'image');
  assert.equal(image.headers['Cache-Control'], 'no-store');
  await assert.rejects(invoke('GET', 'term', '&image=1&revision=999'), { status: 404 });
  await invoke('POST', 'app', '&revision=' + status.revision);
  assert.ok(dialog.photoShare.expires > Date.now());
  await invoke('DELETE');
  assert.equal((await invoke()).json().sharing, false);
  await assert.rejects(invoke('GET', 'term', '&image=1&revision=' + status.revision), {
    status: 404,
  });
});
test('expiry, unconnected and app-to-app calls never expose photo', async () => {
  const f = fixture();
  await f.invoke('PUT');
  f.dialog.photoShare.expires = 0;
  assert.equal((await f.invoke()).json().sharing, false);
  f.dialog.connected = false;
  await assert.rejects(f.invoke(), { status: 403 });
  f.dialog.connected = true;
  f.users.term.type = 'app';
  await assert.rejects(f.invoke(), { status: 409 });
});
test('stop, call closure and token revocation fence delayed decoding', async () => {
  for (const action of ['stop', 'end', 'revoke', 'revoke-peer']) {
    const f = fixture();
    let resolve, started;
    const ready = new Promise((r) => (started = r));
    const pending = f.invoke('PUT', 'app', '', Buffer.from('image'), () => {
      started();
      return new Promise((r) => (resolve = r));
    });
    await ready;
    if (action === 'stop') await f.invoke('DELETE');
    if (action === 'end') f.context.sipServer.dialogs.clear();
    if (action === 'revoke') f.users.app.device_token = 'changed';
    if (action === 'revoke-peer') f.users.term.device_token = 'changed';
    resolve(Buffer.from('normalized'));
    await assert.rejects(pending, { status: 409 });
    assert.equal(f.dialog.photoShare.bytes, null);
  }
});
test('oversized and failed uploads release the processing slot', async () => {
  const f = fixture();
  await assert.rejects(f.invoke('PUT', 'app', '', Buffer.alloc(MAX_BYTES + 1)), { status: 413 });
  await assert.rejects(
    f.invoke('PUT', 'app', '', Buffer.from('bad'), async () => {
      throw Error('invalid');
    }),
  );
  assert.equal((await f.invoke('PUT')).json().sharing, true);
});

test('configuration advertises sharing and contact account types', (t) => {
  const store = storeFixture(t);
  assert.equal(store.appConfig('phone1').call_photo_sharing, true);
  assert.equal(store.config('term1').call_photo_sharing, true);
  assert.equal(
    store.appConfig('phone1').contacts.find((c) => c.id === 'term1').account_type,
    'terminal',
  );
});
