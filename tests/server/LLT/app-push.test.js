// @test S-LLT-061
// @requirements LLR-SRV-APP-005
// @environment portable
// @plan Register and replace push destinations in a private store; check account/enrollment scope, expiry, HMAC payloads and invalid-token removal. Mock Google's endpoints to verify signed OAuth scope, caching and high-priority data-only sends. Drive pending calls through registration, foreign/valid CANCEL, decline, expiry, revocation, failure and shutdown without allocating media.
// @pass Only current App enrollments receive signed pushes; cancelled/expired/revoked waits cannot resume, deadlines and duplicate call IDs are bounded, and credentials remain outside backups.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { Store } = require('../../../zmala_server/store');
const { AppPush, FcmSender } = require('../../../zmala_server/app-push');
const { AppCalls } = require('../../../zmala_server/app-calls');
const peer = { address: '127.0.0.1', port: 5001, protocol: 'UDP' };
const request = (id = 'push-call') => ({
  method: 'INVITE',
  headers: {
    'call-id': id,
    from: { params: { tag: 'a' } },
    cseq: { seq: 1 },
    via: [{ params: { branch: 'z9hG4bK-a' } }],
  },
});
function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'zmala-push-'));
  const store = new Store(dir);
  const sent = [],
    replies = [];
  const sender = { enabled: true, send: async (token, data) => sent.push({ token, data }) };
  const server = {
    store,
    reply: (rq, status) => replies.push({ id: rq.headers['call-id'], status }),
    maintenance: false,
  };
  const calls = new AppCalls(server);
  calls.push = new AppPush(store, sender);
  t.after(() => {
    calls.close();
    fs.rmSync(dir, { recursive: true, force: true });
  });
  return { dir, store, sender, sent, replies, calls, push: calls.push };
}
test('push token scope, persistence, renewal, revocation and signed payload', async (t) => {
  const { dir, store, push, sent, sender } = fixture(t);
  const token = 'test-token-123456789012345';
  assert.throws(() => push.register('term1', token));
  assert.throws(() => push.register('phone1', 'bad'));
  push.register('phone1', token);
  assert.equal(new AppPush(store, sender).available('phone1'), true);
  assert.equal(push.available('term1'), false);
  const expires = Date.now() + 60000;
  await push.notify('phone1', 'c1', 'term1', 'ring', expires);
  const data = sent[0].data;
  assert.equal(
    data.proof,
    crypto
      .createHmac('sha256', store.value.users.phone1.device_token)
      .update(
        JSON.stringify([
          'ring',
          'c1',
          'term1',
          String(expires),
          store.value.users.phone1.device_id,
        ]),
      )
      .digest('hex'),
  );
  assert.deepEqual(Object.keys(data).sort(), [
    'call_id',
    'caller',
    'device_id',
    'event',
    'expires',
    'proof',
  ]);
  assert.equal(sent[0].token, token);
  assert.ok(fs.existsSync(path.join(dir, 'app-push.json')));
  push.tokens.phone1.updated -= 31 * 86400000;
  assert.equal(push.available('phone1'), false);
  push.register('phone1', token);
  store.value.users.phone1.device_id = 'replacement';
  assert.equal(push.available('phone1'), false);
  push.register('phone1', token);
  sender.send = async () => {
    throw Object.assign(Error('gone'), { invalid: true });
  };
  await assert.rejects(push.notify('phone1', 'c1', 'term1', 'ring', expires));
  assert.equal(push.available('phone1'), false);
  push.register('phone1', token);
  push.register('phone1', null);
  assert.equal(push.available('phone1'), false);
  push.register('phone1', token);
  store.updateAccount('phone1', { name: 'Converted', type: 'terminal' });
  assert.equal(push.available('phone1'), false);
});
test('FCM uses scoped signed OAuth and high-priority data messages without exposing failures', async (t) => {
  const { dir } = fixture(t);
  const pair = crypto.generateKeyPairSync('rsa', { modulusLength: 2048 });
  const file = path.join(dir, 'sender.json');
  fs.writeFileSync(
    file,
    JSON.stringify({
      project_id: 'test-project',
      client_email: 'sender@example.invalid',
      private_key: pair.privateKey.export({ type: 'pkcs8', format: 'pem' }),
    }),
  );
  let auth = 0,
    sends = 0;
  t.mock.method(global, 'fetch', async (url, options) => {
    if (url === 'https://oauth2.googleapis.com/token') {
      auth++;
      const jwt = options.body.get('assertion').split('.');
      const claims = JSON.parse(Buffer.from(jwt[1], 'base64url'));
      assert.equal(claims.scope, 'https://www.googleapis.com/auth/firebase.messaging');
      assert.equal(claims.exp - claims.iat, 3600);
      assert.ok(
        crypto.verify(
          'RSA-SHA256',
          Buffer.from(jwt.slice(0, 2).join('.')),
          pair.publicKey,
          Buffer.from(jwt[2], 'base64url'),
        ),
      );
      return { ok: true, json: async () => ({ access_token: 'private-access', expires_in: 3600 }) };
    }
    assert.equal(url, 'https://fcm.googleapis.com/v1/projects/test-project/messages:send');
    assert.equal(options.headers.Authorization, 'Bearer private-access');
    const body = JSON.parse(options.body).message;
    assert.deepEqual(body.android, { priority: 'high', ttl: '60s' });
    assert.equal(body.notification, undefined);
    sends++;
    return sends === 1
      ? { ok: true }
      : {
          ok: false,
          status: 404,
          json: async () => ({ error: { details: [{ errorCode: 'UNREGISTERED' }] } }),
        };
  });
  const sender = new FcmSender(file);
  await sender.send('destination', { event: 'ring' });
  await assert.rejects(
    sender.send('destination', { event: 'ring' }),
    (e) => e.invalid && e.message === 'Firebase delivery failed.',
  );
  assert.equal(auth, 1);
  assert.equal(new FcmSender('').enabled, false);
  await assert.rejects(new FcmSender('').authorization());
});
test('waiting calls resume once and reject duplicate IDs, cancellation and changed ownership', async (t) => {
  const { calls, push, replies, store } = fixture(t);
  push.register('phone1', 'test-token-123456789012345');
  const wait = () => calls.wait(request(), peer, 'term1', 'phone1');
  let pending = wait();
  assert.ok(calls.busy('term1'));
  assert.ok(calls.busy('phone1'));
  assert.equal(await wait(), false);
  assert.equal(replies.at(-1).status, 482);
  assert.ok(calls.waiting.get('push-call').expires <= Date.now() + 60000);
  calls.registered('phone1');
  assert.equal(await pending, true);
  assert.equal(calls.waiting.size, 0);
  pending = wait();
  assert.equal(calls.cancel(request(), { ...peer, port: 6001 }), 403);
  const wrong = request();
  wrong.headers.cseq.seq = 2;
  assert.equal(calls.cancel(wrong, peer), 481);
  assert.equal(calls.cancel(request(), peer), 0);
  assert.equal(await pending, false);
  calls.registered('phone1');
  await new Promise(setImmediate);
  assert.equal(replies.at(-1).status, 487);
  pending = wait();
  calls.decline('term1', 'push-call');
  assert.equal(calls.waiting.size, 1);
  calls.decline('phone1', 'push-call');
  assert.equal(await pending, false);
  assert.equal(replies.at(-1).status, 603);
  for (const change of [
    () => {
      store.value.users.phone1.device_token += 'x';
    },
    () => {
      calls.waiting.get('push-call').expires = 0;
    },
    () => {
      calls.server.maintenance = true;
    },
    () => {
      store.permitted = () => false;
    },
  ]) {
    calls.server.maintenance = false;
    pending = wait();
    change();
    calls.registered('phone1');
    assert.equal(await pending, false);
    assert.equal(replies.at(-1).status, 480);
  }
  pending = wait();
  calls.close();
  assert.equal(await pending, false);
});
test('sender failure and the real deadline close pending calls', async (t) => {
  const { calls, push, sender, replies } = fixture(t);
  push.register('phone1', 'test-token-123456789012345');
  sender.send = async () => {
    throw Error('offline');
  };
  assert.equal(await calls.wait(request(), peer, 'term1', 'phone1'), false);
  assert.equal(replies.at(-1).status, 480);
  sender.send = async () => {};
  let expire;
  t.mock.method(global, 'setTimeout', (callback, delay) => {
    assert.ok(delay >= 14990 && delay <= 60000);
    expire = callback;
    return { unref() {} };
  });
  t.mock.method(global, 'clearTimeout', () => {});
  const pending = calls.wait(request(), peer, 'term1', 'phone1');
  expire();
  assert.equal(await pending, false);
  assert.equal(calls.waiting.size, 0);
});
