// @test S-LLT-025
// @requirements LLR-SRV-START-005, LLR-SRV-PRESENCE-002, LLR-SRV-CALL-005, LLR-SRV-MAINT-020
// @environment portable
// @plan Replace SIP transport with a capture double; check default/configured UDP/TCP binding options, destination-specific HMAC replacement, authenticated registration identity, expiry/query/deregistration transitions and bounded recent activity history.
// @pass All signaling assertions must pass without binding sockets or sending packets to real devices.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const sip = require('../../../zmala_server/node_modules/sip');

const { Store } = require('../../../zmala_server/store');
const { SipServer } = require('../../../zmala_server/sip-server');
const proxy = require('../../../zmala_server/node_modules/sip/proxy');
const crypto = require('node:crypto');
const { storeFixture } = require('../../support/server/unit-fixture');

test('registration clamps lifetime, binds actual flow and rejects identity/expiry errors', async (t) => {
  const s = new SipServer(storeFixture(t)),
    sent = [];
  s.auth.verify = () => 'term1';
  s.log = () => {};
  t.mock.method(proxy, 'send', (r) => sent.push(r));
  t.mock.method(Date, 'now', () => 1000000);
  const peer = { address: '192.0.2.1', port: 54001, protocol: 'TCP' };
  const req = {
    method: 'REGISTER',
    uri: 'sip:family.test',
    headers: {
      from: { uri: 'sip:term1@family.test' },
      to: { uri: 'sip:term1@family.test' },
      via: [],
      cseq: { seq: 1, method: 'REGISTER' },
      'call-id': 'register',
      contact: [{ uri: 'sip:term1@fake-address', params: { expires: 900 } }],
    },
  };
  s.callbacks = { deliver: t.mock.fn() };
  s.auth.verify = () => null;
  s.auth.challenge = () => ({ status: 401 });
  await s.request(req, peer);
  assert.equal(sent.at(-1).status, 401);
  s.auth.verify = () => 'term1';
  s.register(req, peer);
  await new Promise(setImmediate);
  assert.equal(s.callbacks.deliver.mock.calls[0].arguments[0], 'term1');
  assert.equal(sent.at(-1).status, 200);
  assert.equal(sent.at(-1).headers.expires, 600);
  assert.equal(s.registrations.get('term1').remote, peer);
  assert.equal(s.registrations.get('term1').expires, 1600000);
  const saved = s.registrations.get('term1');
  delete req.headers.contact;
  s.register(req, peer);
  assert.equal(s.registrations.get('term1'), saved);
  assert.equal(sent.at(-1).headers.contact[0].params.expires, 600);
  req.headers.contact = [{ uri: 'sip:term1@new-address', params: { expires: 'NaN' } }];
  s.register(req, peer);
  assert.equal(sent.at(-1).status, 400);
  assert.equal(s.registrations.get('term1'), saved);
  req.headers.to.uri = 'sip:other@family.test';
  s.register(req, peer);
  assert.equal(sent.at(-1).status, 403);
  req.headers.to.uri = 'sip:term1@family.test';
  for (const contact of [
    { uri: '*', params: { expires: 600 } },
    { uri: 'sip:term1@new', params: { expires: 0 } },
  ]) {
    s.registrations.set('term1', saved);
    req.headers.contact = [contact];
    s.register(req, peer);
    assert.equal(s.registrations.size, 0);
  }
});

test('activity retains only the newest eighty events', (t) => {
  const s = new SipServer(storeFixture(t));
  t.mock.method(console, 'log', () => {});
  for (let i = 0; i < 100; i++) s.log('event-' + i);
  assert.equal(s.events.length, 80);
  assert.equal(s.events[0].message, 'event-20');
  assert.equal(s.events.at(-1).message, 'event-99');
});

test('SIP routing enforces groups and authenticates every terminal recipient', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'family-routing-')),
    send = proxy.send,
    encodeFlowUri = sip.encodeFlowUri;
  try {
    const s = new Store(dir);
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'alice',
      name: 'Alice',
      type: 'linphone',
    });
    s.createAccount({ emails: ['fixture@example.test'], id: 'bob', name: 'Bob', type: 'linphone' });
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'lounge',
      name: 'Lounge',
      type: 'terminal',
    });
    const server = new SipServer(s),
      sent = [];
    proxy.send = (message) => sent.push(message);
    sip.encodeFlowUri = (flow) => `sip:${flow.address}:${flow.port}`;
    server.auth.verify = () => 'alice';
    const peer = { address: '127.0.0.1', port: 50001, protocol: 'UDP' },
      target = { address: '127.0.0.1', port: 50002, protocol: 'UDP' };
    for (const id of ['bob', 'lounge'])
      server.registrations.set(id, {
        contact: { uri: `sip:${id}@127.0.0.1:50002` },
        remote: target,
        expires: Date.now() + 60000,
      });
    const request = (to) => ({
      method: 'INVITE',
      uri: `sip:${to}@${s.value.host}`,
      headers: {
        to: { uri: `sip:${to}@${s.value.host}`, params: {} },
        from: { uri: `sip:alice@${s.value.host}`, params: { tag: 'alice-tag' } },
        via: [],
        cseq: { seq: 1, method: 'INVITE' },
        'call-id': 'test-' + to,
        contact: [{ uri: 'sip:alice@127.0.0.1:50001' }],
        'x-family-auth': 'forged',
      },
      content: '',
    });
    await server.request(request('bob'), peer);
    assert.equal(sent.pop().status, 403);
    const group = s.createGroup({ name: 'Peers', members: ['alice', 'bob', 'lounge'] });
    await server.request(request('bob'), peer);
    const phone = sent.pop();
    assert.equal(phone.method, 'INVITE');
    assert.equal(phone.headers['x-family-auth'], undefined);
    await server.request(request('lounge'), peer);
    assert.equal(sent.pop().status, 486);
    server.dialogs.clear();
    await server.request(request('lounge'), peer);
    const terminal = sent.pop();
    const proof = crypto
      .createHmac('sha256', s.value.users.lounge.device_token)
      .update('test-lounge:alice')
      .digest('hex');
    assert.equal(terminal.headers['x-family-auth'], proof);
    assert.notEqual(
      proof,
      crypto
        .createHmac('sha256', s.value.users.term1.device_token)
        .update('test-lounge:alice')
        .digest('hex'),
    );
    server.dialogs.clear();
    s.deleteGroup(group);
    await server.request(request('bob'), peer);
    assert.equal(sent.pop().status, 403);
  } finally {
    proxy.send = send;
    if (encodeFlowUri) sip.encodeFlowUri = encodeFlowUri;
    else delete sip.encodeFlowUri;
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('SIP binds both transports on all IPv4 interfaces with configured port', (t) => {
  const options = [];
  t.mock.method(proxy, 'start', (value) => options.push(value));
  t.mock.method(console, 'log', () => {});
  const originalSend = sip.send;
  t.after(() => {
    sip.send = originalSend;
  });
  const store = storeFixture(t);
  for (const port of [5060, 5091]) {
    store.value.sip_port = port;
    const server = new SipServer(store);
    try {
      server.start();
      assert.equal(options.at(-1).address, '0.0.0.0');
      assert.equal(options.at(-1).port, port);
      assert.equal(options.at(-1).udp, true);
      assert.equal(options.at(-1).tcp, true);
    } finally {
      clearInterval(server.sweep);
      sip.send = originalSend;
    }
  }
});
