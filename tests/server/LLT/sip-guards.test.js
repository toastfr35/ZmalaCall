// @test S-LLT-009
// @requirements LLR-SRV-SIP-006, LLR-SRV-SIP-008, LLR-SRV-SIP-009, LLR-SRV-SIP-010, LLR-SRV-SIP-011
// @environment portable
// @plan Drive signaling with a fake transport and delayed SDP work; assert malformed/foreign requests fail, cancelled work cannot ring or forward late answers and renegotiation commits exactly once.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const sip = require('../../../zmala_server/node_modules/sip');
const proxy = require('../../../zmala_server/node_modules/sip/proxy');
const { maxForwards, validRequest } = require('../../../zmala_server/sip-guards');
const { startProxy } = require('../../../zmala_server/sip-transport');
const { SipServer } = require('../../../zmala_server/sip-server');

// These helpers are installed dynamically by sip.start. Unit tests exercise the
// router without binding live SIP ports, so provide slots that mocks can replace.
sip.encodeFlowUri ??= () => '';
sip.send ??= () => {};
sip.stop ??= () => {};

const caller = { address: '127.0.0.1', port: 51001, protocol: 'UDP' };
const recipient = { address: '127.0.0.1', port: 51002, protocol: 'UDP' };
function request(method = 'INVITE') {
  return {
    method,
    content: 'v=0\r\n',
    uri: 'sip:term1@127.0.0.1',
    headers: {
      to: { uri: 'sip:term1@127.0.0.1', params: {} },
      from: { uri: 'sip:phone1@127.0.0.1', params: { tag: 'caller-tag' } },
      cseq: { seq: 12, method },
      'call-id': 'guard-test',
      via: [
        { protocol: 'UDP', host: '127.0.0.1', port: 51001, params: { branch: 'z9hG4bK-test' } },
      ],
      contact: [{ uri: 'sip:phone1@127.0.0.1:51001' }],
    },
  };
}
function server() {
  const s = new SipServer({
    value: { host: '127.0.0.1', users: {} },
    terminal: () => false,
    terminalAccount: () => null,
  });
  const dialog = {
    peers: [
      {
        user: 'phone1',
        remote: caller,
        tag: 'caller-tag',
        contact: { uri: 'sip:phone1@127.0.0.1:51001' },
      },
      {
        user: 'term1',
        remote: recipient,
        tag: null,
        contact: { uri: 'sip:term1@127.0.0.1:51002' },
      },
    ],
    touched: Date.now(),
    connected: false,
    queue: Promise.resolve(),
    invites: new Map(),
  };
  s.dialogs.set('guard-test', dialog);
  return { s, dialog };
}

test('SIP field and hop validation rejects malformed input before routing', async (t) => {
  for (const bad of ['NaN', '1.5', '-1', '', 256, Infinity, true, null, [70], {}])
    assert.equal(maxForwards(bad), null);
  assert.equal(maxForwards(undefined), 70);
  assert.equal(maxForwards('0'), 0);
  assert.equal(maxForwards('70'), 70);
  assert.equal(validRequest(request()), true);
  assert.equal(validRequest({ ...request(), headers: {} }), false);
  const { s } = server();
  s.dialogs.clear();
  const sent = [];
  t.mock.method(proxy, 'send', (response) => sent.push(response));
  for (const [hops, status] of [
    ['NaN', 400],
    [0, 483],
  ]) {
    const rq = request();
    rq.headers['max-forwards'] = hops;
    await s.request(rq, caller);
    assert.equal(sent.pop().status, status);
    assert.equal(s.dialogs.size, 0);
  }
});

test('CANCEL during SDP allocation cannot forward a late INVITE; foreign peers cannot cancel', async (t) => {
  const { s, dialog } = server();
  const sent = [];
  t.mock.method(proxy, 'send', (message) => sent.push(message));
  t.mock.method(sip, 'encodeFlowUri', () => 'sip:127.0.0.1:51002');
  let ready;
  const allocation = new Promise((resolve) => {
    ready = resolve;
  });
  s.media.rewrite = () => allocation;
  const rq = request();
  rq.headers['content-type'] = 'application/sdp';
  rq.content = 'v=0\r\n';
  const forwarding = s.forwardDialog(rq, caller, dialog, 0);
  const cancel = request('CANCEL');
  assert.equal(s.cancelStatus(cancel, { ...caller, port: 59999 }), 403);
  const unrelated = structuredClone(cancel);
  unrelated.headers.via[0].params.branch = 'z9hG4bK-unrelated';
  assert.equal(s.cancelStatus(unrelated, caller), 481);
  assert.equal(s.cancelStatus(cancel, caller), 0);
  ready('v=0\r\n');
  await forwarding;
  assert.deepEqual(
    sent.map((message) => message.status),
    [487],
  );
  assert.equal(s.dialogs.size, 0);
});

test('closing a dialog during SDP rewrite prevents forwarding and late responses', async (t) => {
  const { s, dialog } = server();
  const sent = [];
  t.mock.method(proxy, 'send', (message) => sent.push(message));
  t.mock.method(sip, 'encodeFlowUri', () => 'sip:127.0.0.1:51002');
  let ready;
  s.media.rewrite = () =>
    new Promise((resolve) => {
      ready = resolve;
    });
  const rq = request();
  rq.headers['content-type'] = 'application/sdp';
  const forwarding = s.forwardDialog(rq, caller, dialog, 0);
  s.closeDialog('guard-test');
  ready('v=0\r\n');
  await forwarding;
  assert.equal(sent.length, 0);
});

test('the transport applies pre-transaction validation only to CANCEL', (t) => {
  let options, route;
  const dispatch = () => {};
  t.mock.method(proxy, 'start', (settings, handler) => {
    options = settings;
    route = handler;
  });
  startProxy({ port: 5060 }, dispatch, (rq, peer) => (peer.port === caller.port ? 0 : 403));
  assert.equal(route, dispatch);
  assert.equal(options.port, 5060);
  assert.equal(options.requestGuard(request('CANCEL'), { ...caller, port: 59999 }), 403);
  assert.equal(options.requestGuard(request('CANCEL'), caller), 0);
  assert.equal(options.requestGuard(request('INVITE'), { ...caller, port: 59999 }), 0);
});

test('server shutdown invalidates dialogs before pending SDP work resumes', async (t) => {
  const { s, dialog } = server();
  const sent = [];
  t.mock.method(proxy, 'send', (message) => sent.push(message));
  t.mock.method(sip, 'stop', () => {});
  t.mock.method(sip, 'encodeFlowUri', () => 'sip:127.0.0.1:51002');
  let ready;
  s.media.rewrite = () =>
    new Promise((resolve) => {
      ready = resolve;
    });
  const rq = request();
  rq.headers['content-type'] = 'application/sdp';
  const forwarding = s.forwardDialog(rq, caller, dialog, 0);
  s.close();
  ready('v=0\r\n');
  await forwarding;
  assert.equal(s.dialogs.size, 0);
  assert.equal(s.registrations.size, 0);
  assert.equal(sent.length, 0);
});

test('a late SDP answer cannot connect or forward a response after the dialog closes', async (t) => {
  const { s, dialog } = server();
  const sent = [];
  let reply, ready, rewriting;
  const started = new Promise((resolve) => {
    rewriting = resolve;
  });
  t.mock.method(proxy, 'send', (message, callback) => {
    sent.push(message);
    reply = callback;
  });
  t.mock.method(sip, 'encodeFlowUri', () => 'sip:127.0.0.1:51002');
  s.media.rewrite = () => {
    rewriting();
    return new Promise((resolve) => {
      ready = resolve;
    });
  };
  await s.forwardDialog(request(), caller, dialog, 0);
  const answer = sip.makeResponse(sent[0], 200, 'OK');
  answer.headers['content-type'] = 'application/sdp';
  answer.content = 'v=0\r\n';
  reply(answer);
  await started;
  s.closeDialog('guard-test');
  ready('v=0\r\n');
  await dialog.queue;
  assert.equal(sent.length, 1, 'Only the original INVITE was forwarded');
  assert.equal(dialog.connected, false);
});

test('rejected renegotiation discards staged media and overlapping offers receive 491', async (t) => {
  const { s, dialog } = server();
  dialog.connected = true;
  const sent = [];
  let reply;
  t.mock.method(proxy, 'send', (message, callback) => {
    sent.push(message);
    if (callback) reply = callback;
  });
  t.mock.method(sip, 'encodeFlowUri', () => 'sip:127.0.0.1:51002');
  const discard = t.mock.method(s.media, 'discard');
  const commit = t.mock.method(s.media, 'commit');
  const rq = request();
  rq.headers.to.params.tag = 'callee-tag';
  rq.headers['content-type'] = 'application/sdp';
  await s.forwardDialog(rq, caller, dialog, 0);
  assert.ok(dialog.mediaUpdate);
  await s.forwardDialog(rq, recipient, dialog, 1);
  assert.equal(sent.at(-1).status, 491);
  reply(sip.makeResponse(sent[0], 488, 'Not Acceptable Here'));
  await dialog.queue;
  assert.equal(discard.mock.callCount(), 1);
  assert.equal(commit.mock.callCount(), 0);
  assert.equal(dialog.mediaUpdate, undefined);
  assert.equal(s.dialogs.get('guard-test'), dialog);
  s.closeDialog('guard-test');
});

test('successful renegotiation commits once and retransmits the rewritten final response', async (t) => {
  const { s, dialog } = server();
  dialog.connected = true;
  const sent = [];
  let reply;
  t.mock.method(proxy, 'send', (message, callback) => {
    sent.push(message);
    if (callback) reply = callback;
  });
  t.mock.method(sip, 'encodeFlowUri', () => 'sip:127.0.0.1:51002');
  const commit = t.mock.method(s.media, 'commit');
  const rq = request();
  rq.headers.to.params.tag = 'callee-tag';
  rq.headers['content-type'] = 'application/sdp';
  await s.forwardDialog(rq, caller, dialog, 0);
  const answer = sip.makeResponse(sent[0], 200, 'OK');
  answer.headers['content-type'] = 'application/sdp';
  answer.content = 'v=0\r\n';
  reply(answer);
  await dialog.queue;
  reply(answer);
  await dialog.queue;
  assert.equal(commit.mock.callCount(), 1);
  assert.deepEqual(sent[1], sent[2]);
  assert.equal(dialog.mediaUpdate, undefined);
  s.closeDialog('guard-test');
});
