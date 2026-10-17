'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'),
  os = require('node:os'),
  path = require('node:path'),
  crypto = require('node:crypto');
const sip = require('sip'),
  proxy = require('sip/proxy'),
  digest = require('sip/digest');
const { Store } = require('../store');
const { SipServer } = require('../sip-server');

test('phone text notifications require digest and shared groups, preserve text, and receive terminal-specific proof', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'zmala-message-'));
  const send = proxy.send,
    encode = sip.encodeFlowUri;
  try {
    const store = new Store(dir),
      server = new SipServer(store),
      sent = [];
    const remote = { address: '127.0.0.1', port: 5100, protocol: 'UDP' };
    proxy.send = (message, respond) => sent.push({ message, respond });
    sip.encodeFlowUri = (flow) => {
      assert.equal(flow, remote);
      return 'sip:exact-flow';
    };
    server.registrations.set('term1', {
      expires: Date.now() + 60000,
      contact: { uri: 'sip:term1@127.0.0.1:5100' },
      remote,
    });
    const message = () => ({
      method: 'MESSAGE',
      uri: `sip:term1@${store.value.host}`,
      content: Buffer.from('Bonjour Evelyn!', 'utf8').toString('latin1'),
      headers: {
        from: { uri: `sip:phone1@${store.value.host}`, params: { tag: 'source' } },
        to: { uri: `sip:term1@${store.value.host}` },
        via: [
          { protocol: 'UDP', host: '127.0.0.1', port: 5099, params: { branch: 'z9hG4bK-test' } },
        ],
        cseq: { seq: 1, method: 'MESSAGE' },
        'call-id': 'text-one',
        'max-forwards': 70,
        'content-type': 'text/plain; charset=utf-8',
        'x-family-auth': 'forged',
        'x-zmala-message-id': 'forged',
      },
    });
    const request = message();
    server.message(request);
    const challenge = sent.pop().message;
    assert.equal(challenge.status, 407);
    digest.signRequest({}, request, challenge, {
      user: 'phone1',
      password: store.value.users.phone1.password,
    });
    server.message(request);
    const forward = sent.pop();
    assert.equal(forward.message.method, 'MESSAGE');
    assert.equal(forward.message.content, request.content);
    assert.equal(forward.message.uri, 'sip:term1@127.0.0.1:5100');
    assert.deepEqual(forward.message.headers.route, [{ uri: 'sip:exact-flow' }]);
    assert.equal(forward.message.headers['proxy-authorization'], undefined);
    assert.equal(forward.message.headers['max-forwards'], 69);
    assert.equal(forward.message.headers['x-zmala-message-id'], 'text-one:1');
    assert.equal(
      forward.message.headers['x-family-auth'],
      crypto
        .createHmac('sha256', store.value.users.term1.device_token)
        .update('message:text-one:1:phone1')
        .digest('hex'),
    );
    const response = sip.makeResponse(forward.message, 200, 'OK');
    response.headers.via.unshift({ host: 'proxy', params: {} });
    forward.respond(response);
    assert.equal(sent.pop().message.status, 200);
    assert.equal(server.dialogs.size, 0);
    assert.equal(
      server.events.some((e) => e.message.includes('Bonjour')),
      false,
    );
    server.message(request);
    assert.equal(sent.pop().message.status, 407, 'Digest replay rejected');

    server.auth.verify = () => 'phone1';
    function rejects(change, status) {
      const rq = message();
      change(rq);
      server.message(rq);
      assert.equal(sent.pop().message.status, status);
    }
    rejects((rq) => (rq.headers.from.uri = `sip:term1@${store.value.host}`), 403);
    rejects((rq) => (rq.headers.to.uri = `sip:phone1@${store.value.host}`), 403);
    rejects((rq) => (rq.headers['content-type'] = 'application/im-iscomposing+xml'), 415);
    rejects((rq) => (rq.content = ' '), 400);
    rejects((rq) => (rq.content = 'x'.repeat(16385)), 413);
    rejects((rq) => (rq.headers['call-id'] = ''), 400);
    rejects((rq) => (rq.headers.cseq.seq = -1), 400);
    rejects((rq) => (rq.headers['max-forwards'] = 0), 483);
    server.registrations.get('term1').reachable = false;
    rejects(() => {}, 480);
    server.registrations.get('term1').reachable = true;
    store.deleteGroup('family');
    rejects(() => {}, 403);
  } finally {
    proxy.send = send;
    if (encode) sip.encodeFlowUri = encode;
    else delete sip.encodeFlowUri;
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
