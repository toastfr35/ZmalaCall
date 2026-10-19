// @test S-HLT-032
// @requirements HLR-SRV-APP-004
// @environment portable
// @plan Use a disposable HTTP server and SIP router with captured push delivery. Register an App token through bearer auth, verify live terminal availability without a SIP registration, and hold an authorized INVITE until fresh registration. Deny terminal/admin token mutation, decline a waiting call through its recipient API, and prevent resumption after enrollment revocation. Exercise real UDP Digest INVITE/CANCEL transactions and require 200 for CANCEL plus 487 for the waiting INVITE, without late forwarding.
// @pass Only the App bearer manages its destination; permitted offline calls resume once, cancelled or revoked calls never forward, and availability follows token enrollment. Cloud delivery is separate.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { httpFixture } = require('../../support/server/http-fixture');
const { SipServer } = require('../../../zmala_server/sip-server');
const { AppPush } = require('../../../zmala_server/app-push');
const sip = require('../../../zmala_server/node_modules/sip');
const { udpPeer, request, authenticate } = require('../../support/server/udp-peer');
const { storeFixture } = require('../../support/server/unit-fixture');

test('real SIP CANCEL acknowledges a waiting wake before removing its transaction', async (t) => {
  const store = storeFixture(t);
  const caller = await udpPeer(),
    reservation = await udpPeer();
  const port = reservation.port;
  reservation.close();
  Object.assign(store.value, { host: '127.0.0.1', sip_port: port });
  const server = new SipServer(store);
  let notify;
  const sent = new Promise((resolve) => {
    notify = resolve;
  });
  server.appCalls.push = new AppPush(store, { enabled: true, send: async () => notify() });
  server.appCalls.push.register('phone1', 'wire-token-123456789012345');
  t.after(() => {
    server.close();
    caller.close();
  });
  server.start();
  const invite = request(caller, 'INVITE', 'term1', 'phone1');
  const response = authenticate(caller, invite, port, {
    user: 'term1',
    password: store.value.users.term1.password,
  });
  await sent;
  assert.equal(server.dialogs.size, 0);
  const cancel = sip.copyMessage(invite);
  cancel.method = 'CANCEL';
  cancel.headers.cseq.method = 'CANCEL';
  const acknowledged = caller.wait((m) => m.status === 200 && m.headers.cseq.method === 'CANCEL');
  caller.send(cancel, port);
  assert.equal((await acknowledged).status, 200);
  assert.equal((await response).status, 487);
  assert.equal(server.appCalls.waiting.size, 0);
  server.appCalls.registered('phone1');
  assert.equal(server.dialogs.size, 0);
});
test('HTTP enrollment and offline SIP wake, decline and revocation', async (t) => {
  const f = await httpFixture();
  const { store, sipServer, base } = f;
  const s = new SipServer(store),
    delivered = [],
    replies = [],
    forwarded = [];
  sipServer.appCalls = s.appCalls;
  s.appCalls.push = new AppPush(store, {
    enabled: true,
    send: async (token, data) => delivered.push(data),
  });
  s.reply = (rq, status) => replies.push(status);
  s.auth.verify = () => 'term1';
  s.forwardDialog = async (rq) => forwarded.push(rq.headers['call-id']);
  const token = store.value.users.phone1.device_token;
  const api = (route, body, credential = token) =>
    fetch(base + route, {
      method: body ? 'POST' : 'GET',
      headers: { Authorization: 'Bearer ' + credential, 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    });
  const req = (id) => ({
    method: 'INVITE',
    uri: 'sip:phone1@' + store.value.host,
    headers: {
      to: { uri: 'sip:phone1@' + store.value.host, params: {} },
      from: { uri: 'sip:term1@' + store.value.host, params: { tag: 'sender' } },
      'call-id': id,
      cseq: { seq: 1, method: 'INVITE' },
      via: [
        { protocol: 'UDP', host: '127.0.0.1', port: 5001, params: { branch: 'z9hG4bK-' + id } },
      ],
      contact: [{ uri: 'sip:term1@127.0.0.1:5001' }],
    },
  });
  const peer = { address: '127.0.0.1', port: 5001, protocol: 'UDP' };
  t.after(async () => {
    s.appCalls.close();
    await f.close();
  });
  for (const credential of [
    store.value.users.term1.device_token,
    store.value.admin_token,
    'wrong',
  ]) {
    const r = await api('/api/app/push', { token: 'fixture-token-123456789012' }, credential);
    assert.ok([401, 403].includes(r.status));
    await r.arrayBuffer();
  }
  let r = await api('/api/app/push', { token: 'fixture-token-123456789012', id: 'term1' });
  assert.equal(r.status, 200);
  assert.equal((await r.json()).push_enabled, true);
  assert.equal(s.appCalls.push.available('term1'), false);
  r = await api(
    '/api/config?delta=1&version=' + store.value.configuration_version,
    null,
    store.value.users.term1.device_token,
  );
  assert.equal((await r.json()).live.contacts.find((c) => c.id === 'phone1').online, true);
  const revision = store.value.configuration_version;
  let pending = s.request(req('wake-1'), peer);
  await new Promise(setImmediate);
  assert.equal(s.dialogs.size, 0);
  assert.equal(delivered[0].event, 'ring');
  assert.equal(replies.at(-1), 180);
  s.registrations.set('phone1', {
    expires: Date.now() + 60000,
    contact: { uri: 'sip:phone1@127.0.0.1:5002' },
    remote: { ...peer, port: 5002 },
  });
  s.appCalls.registered('phone1');
  await pending;
  assert.deepEqual(forwarded, ['wake-1']);
  s.dialogs.clear();
  pending = s.request(req('wake-2'), peer);
  await new Promise(setImmediate);
  r = await api('/api/app/call/decline', { call_id: 'wake-2' });
  assert.equal(r.status, 200);
  await r.arrayBuffer();
  await pending;
  assert.equal(replies.at(-1), 603);
  assert.deepEqual(forwarded, ['wake-1']);
  pending = s.request(req('wake-3'), peer);
  await new Promise(setImmediate);
  store.value.users.phone1.device_token += 'revoked';
  s.appCalls.registered('phone1');
  await pending;
  assert.equal(replies.at(-1), 480);
  r = await api('/api/app/push', { token: null });
  assert.equal(r.status, 401);
  await r.arrayBuffer();
  assert.equal(store.value.configuration_version, revision);
});
