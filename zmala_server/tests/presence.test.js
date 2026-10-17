'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'),
  os = require('node:os'),
  path = require('node:path');
const sip = require('sip');
const { Store } = require('../store');
const { SipServer, registrationOnline } = require('../sip-server');
const { Callbacks } = require('../callbacks');

test('SIP reachability timeout hides unexpired devices, blocks callbacks and recovers on their exact flow', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'], now: 100000 });
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'zmala-presence-'));
  const send = sip.send,
    encode = sip.encodeFlowUri;
  try {
    const store = new Store(dir),
      server = new SipServer(store),
      sent = [],
      delivered = [];
    const remote = { address: '127.0.0.1', port: 5099, protocol: 'UDP' };
    const registration = {
      expires: Date.now() + 600000,
      contact: { uri: 'sip:phone1@127.0.0.1:5099' },
      remote,
    };
    server.registrations.set('phone1', registration);
    server.callbacks = { deliver: (user) => delivered.push(user) };
    sip.encodeFlowUri = (flow) => {
      assert.equal(flow, remote);
      return 'sip:exact-flow';
    };
    sip.send = (request, respond) => sent.push({ request, respond });
    const callbacks = new Callbacks(store, server);
    server.probeRegistrations();
    server.probeRegistrations();
    assert.equal(sent.length, 1, 'Never overlap checks for the same flow');
    assert.equal(sent[0].request.method, 'OPTIONS');
    assert.equal(sent[0].request.uri, registration.contact.uri);
    assert.deepEqual(sent[0].request.headers.route, [{ uri: 'sip:exact-flow' }]);
    sent[0].respond({ status: 100 });
    t.mock.timers.tick(4999);
    assert.equal(registrationOnline(registration), true);
    t.mock.timers.tick(1);
    assert.equal(registrationOnline(registration), false);
    assert.equal(callbacks.online('phone1'), false);
    assert.deepEqual(server.status().registrations, []);
    assert.equal(
      server.registrations.get('phone1'),
      registration,
      'Keep the flow to detect reconnection',
    );
    assert.equal(server.probes.size, 0);
    sent[0].respond({ status: 200 });
    assert.equal(
      registrationOnline(registration),
      false,
      'Ignore late replies from expired checks',
    );
    server.probeRegistrations();
    sent[1].respond({ status: 405 });
    assert.equal(
      registrationOnline(registration),
      true,
      'Any real endpoint response proves reachability',
    );
    assert.equal(callbacks.online('phone1'), true);
    assert.deepEqual(delivered, ['phone1']);
    assert.equal(server.status().registrations[0].user, 'phone1');
    t.mock.timers.tick(5000);
    assert.equal(registrationOnline(registration), true);
    server.probeRegistrations();
    sent[2].respond({ status: 408 });
    assert.equal(registrationOnline(registration), false);
    server.probeRegistrations();
    sip.send = () => {
      throw Error('Transport unavailable');
    };
    server.cancelProbe('phone1');
    server.probeRegistrations();
    assert.equal(registrationOnline(registration), false);
    assert.equal(server.probes.size, 0);
  } finally {
    sip.send = send;
    if (encode) sip.encodeFlowUri = encode;
    else delete sip.encodeFlowUri;
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('an old unanswered flow cannot mark a newly registered phone offline', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'], now: 100000 });
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'zmala-presence-reregister-'));
  const send = sip.send,
    encode = sip.encodeFlowUri;
  try {
    const server = new SipServer(new Store(dir)),
      responses = [];
    sip.encodeFlowUri = () => 'sip:flow';
    sip.send = (request, respond) => responses.push(respond);
    const old = {
      expires: Date.now() + 600000,
      contact: { uri: 'sip:phone1@127.0.0.1:5099' },
      remote: { address: '127.0.0.1', port: 5099, protocol: 'UDP' },
    };
    server.registrations.set('phone1', old);
    server.probeRegistrations();
    const fresh = { ...old, remote: { ...old.remote, port: 5100 } };
    server.cancelProbe('phone1');
    server.registrations.set('phone1', fresh);
    responses[0]({ status: 503 });
    t.mock.timers.tick(5000);
    assert.equal(registrationOnline(fresh), true);
    assert.equal(server.probes.size, 0);
    server.probeRegistrations();
    responses[1]({ status: 200 });
    assert.equal(registrationOnline(fresh), true);
    assert.equal(server.probes.size, 0);
    fresh.expires = Date.now() - 1;
    server.probeRegistrations();
    assert.equal(responses.length, 2);
    assert.equal(registrationOnline(fresh), false);
  } finally {
    sip.send = send;
    if (encode) sip.encodeFlowUri = encode;
    else delete sip.encodeFlowUri;
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
