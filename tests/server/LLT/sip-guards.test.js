// @test S-LLT-009
// @requirements LLR-SRV-CALL-004, LLR-SRV-CALL-006, LLR-SRV-CALL-007, LLR-SRV-CALL-008, LLR-SRV-CALL-009
// @environment portable
// @plan Drive signaling with a fake transport and delayed SDP work; assert malformed/foreign requests fail, cancelled work cannot ring or forward late answers and renegotiation commits exactly once. Capture startup callbacks and the sweep timer to verify CANCEL header preservation, request-error replies, registration/dialog expiry and transport cleanup. Check authenticated admission against forged destinations, offline/busy recipients and missing contact, then reject malformed offers/answers and release failed initial calls and completed BYEs.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const sip = require('../../../zmala_server/node_modules/sip');
const proxy = require('../../../zmala_server/node_modules/sip/proxy');
const { maxForwards, validRequest, samePeer } = require('../../../zmala_server/sip-guards');
const { startProxy } = require('../../../zmala_server/sip-transport');
const { SipServer } = require('../../../zmala_server/sip-server');

// These helpers are installed dynamically by sip.start. Unit tests exercise the
// router without binding live SIP ports, so provide slots that mocks can replace.
sip.encodeFlowUri ??= () => '';
sip.send ??= () => {};
sip.stop ??= () => {};

test('startup wraps CANCEL headers, handles route failures and sweeps expired ownership', async (t) => {
  let options, route, sweep;
  t.mock.method(proxy, 'start', (config, callback) => {
    options = config;
    route = callback;
  });
  t.mock.method(global, 'setInterval', (callback, delay) => {
    assert.equal(delay, 5000);
    sweep = callback;
    return 'sweep';
  });
  const cleared = t.mock.method(global, 'clearInterval', () => {});
  const sent = t.mock.method(sip, 'send', () => 'sent');
  const stop = t.mock.method(sip, 'stop', () => {});
  const contexts = t.mock.method(proxy, 'clearContexts', () => {});
  const logged = t.mock.method(console, 'log', () => {});
  t.mock.method(Date, 'now', () => 20000000);
  const s = new SipServer({ value: { host: '192.0.2.1', sip_port: 5060 } });
  s.callbacks = { deliver: t.mock.fn() };
  s.presence.check = t.mock.fn();
  s.presence.cancel = t.mock.fn();
  s.presence.close = t.mock.fn();
  s.media.closeAll = t.mock.fn();
  s.start();
  try {
    assert.equal(options.address, '0.0.0.0');
    const cancel = { method: 'CANCEL', headers: {} };
    assert.equal(sip.send(cancel), 'sent');
    assert.equal(cancel.headers['max-forwards'], 70);
    cancel.headers['max-forwards'] = 12;
    sip.send(cancel);
    assert.equal(cancel.headers['max-forwards'], 12);
    assert.equal(sent.mock.calls.length, 2);
    const old = process.env.VIDEOCALL_DEBUG;
    try {
      process.env.VIDEOCALL_DEBUG = '1';
      options.logger.recv({ method: 'OPTIONS' }, caller);
      options.logger.send({ status: 200 }, caller);
      options.logger.error(Error('transport'));
    } finally {
      if (old === undefined) delete process.env.VIDEOCALL_DEBUG;
      else process.env.VIDEOCALL_DEBUG = old;
    }
    assert.ok(logged.mock.calls.some((c) => c.arguments[0] === 'SIP error: transport'));
    s.request = async () => {
      throw Error('route failure');
    };
    s.reply = t.mock.fn();
    const req = request('OPTIONS');
    route(req, caller);
    await Promise.resolve();
    assert.deepEqual(s.reply.mock.calls[0].arguments, [req, 500, 'Internal Server Error']);
    s.registrations.set('expired', { expires: 19999999 });
    s.registrations.set('current', { expires: 20000001 });
    s.dialogs.set('ringing', { touched: 0, connected: false, ringing_timeout: 10000 });
    s.dialogs.set('default-ringing', { touched: 0, connected: false });
    s.dialogs.set('old-call', { touched: 0, connected: true });
    s.dialogs.set('current-call', { touched: 19999999, connected: true });
    sweep();
    assert.deepEqual([...s.registrations.keys()], ['current']);
    assert.deepEqual([...s.dialogs.keys()], ['current-call']);
    assert.equal(s.presence.cancel.mock.calls[0].arguments[0], 'expired');
    assert.equal(s.callbacks.deliver.mock.calls.length, 1);
    assert.equal(s.presence.check.mock.calls.length, 1);
  } finally {
    s.close();
  }
  assert.equal(sip.send, sent);
  assert.equal(cleared.mock.calls[0].arguments[0], 'sweep');
  assert.equal(stop.mock.calls.length, 1);
  assert.equal(contexts.mock.calls.length, 1);
  assert.equal(s.dialogs.size, 0);
});

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
    enrolledAccount: () => null,
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

test('call admission rejects forged, offline, busy and contactless callers before creating a dialog', async (t) => {
  const { s } = server();
  s.dialogs.clear();
  const sent = [];
  t.mock.method(proxy, 'send', (message) => sent.push(message));
  t.mock.method(console, 'log', () => {});
  s.auth.verify = () => 'phone1';
  s.store.permitted = () => true;
  s.store.ringTimeout = () => 90;
  async function rejected(rq, status) {
    await s.request(rq, caller);
    assert.equal(sent.at(-1).status, status);
  }
  await rejected({ ...request(), headers: {} }, 400);
  await rejected(request('OPTIONS'), 200);
  const message = t.mock.method(s, 'message', () => {});
  await s.request(request('MESSAGE'), caller);
  assert.equal(message.mock.callCount(), 1);
  await rejected(request('BYE'), 481);
  s.auth.verify = () => null;
  s.auth.challenge = () => ({ status: 407 });
  await rejected(request(), 407);
  s.auth.verify = () => 'phone1';
  const forged = request();
  forged.uri = 'sip:other@127.0.0.1';
  await rejected(forged, 403);
  await rejected(request(), 480);
  s.registrations.set('term1', {
    expires: Date.now() + 60000,
    contact: { uri: 'sip:term1@127.0.0.1' },
    remote: recipient,
  });
  for (let i = 0; i < 24; i++) s.dialogs.set(String(i), {});
  await rejected(request(), 486);
  s.dialogs.clear();
  s.dialogs.set('busy', { peers: [{ user: 'term1' }] });
  await rejected(request(), 486);
  s.dialogs.clear();
  const contactless = request();
  delete contactless.headers.contact;
  await rejected(contactless, 400);
  assert.equal(s.dialogs.size, 0);
  const forward = t.mock.method(s, 'forwardDialog', async () => {});
  await s.request(request(), caller);
  assert.equal(forward.mock.callCount(), 1);
  const dialog = s.dialogs.get('guard-test');
  assert.equal(dialog.ringing_timeout, 120000);
  assert.deepEqual(
    dialog.peers.map((p) => p.user),
    ['phone1', 'term1'],
  );
  assert.equal(dialog.peers[0].remote, caller);
});

test('dialog methods, offer and answer failures preserve ownership and close failed initial calls', async (t) => {
  const sent = [];
  t.mock.method(proxy, 'send', (message, reply) => sent.push({ message, reply }));
  t.mock.method(sip, 'encodeFlowUri', () => 'sip:flow');
  t.mock.method(console, 'log', () => {});
  let { s, dialog } = server();
  await s.request(request('SUBSCRIBE'), caller);
  assert.equal(sent.at(-1).message.status, 405);
  await s.request(request(), { ...caller, port: 12345 });
  assert.equal(sent.at(-1).message.status, 403);
  assert.equal(s.cancelStatus({ headers: {} }, caller), 400);
  const unknown = request('CANCEL');
  unknown.headers['call-id'] = 'absent';
  assert.equal(s.cancelStatus(unknown, caller), 481);
  dialog.connected = true;
  await s.forwardDialog(request(), caller, dialog, 0);
  assert.equal(sent.at(-1).message.status, 488);
  dialog.connected = false;
  for (const hops of [0, 'invalid']) {
    const rq = request();
    rq.headers['max-forwards'] = hops;
    await s.forwardDialog(rq, caller, dialog, 0);
    assert.equal(sent.at(-1).message.status, hops === 0 ? 483 : 400);
  }
  for (const body of [undefined, 'bad SDP']) {
    ({ s, dialog } = server());
    const rq = request();
    rq.headers['content-type'] = 'application/sdp';
    rq.content = body;
    s.media.rewrite = async () => {
      throw Error('bad SDP');
    };
    await s.forwardDialog(rq, caller, dialog, 0);
    assert.equal(sent.at(-1).message.status, 488);
    assert.equal(s.dialogs.size, 0);
    assert.equal(dialog.invites.size, 0);
  }
  ({ s, dialog } = server());
  await s.forwardDialog(request(), caller, dialog, 0);
  const forward = sent.at(-1);
  const answer = sip.makeResponse(forward.message, 200, 'OK');
  answer.headers['content-type'] = 'application/sdp';
  answer.content = undefined;
  forward.reply(answer);
  await dialog.queue;
  assert.equal(sent.at(-1).message.status, 488);
  assert.equal(s.dialogs.size, 0);
  ({ s, dialog } = server());
  dialog.connected = true;
  await s.forwardDialog(request('BYE'), caller, dialog, 0);
  const bye = sent.at(-1);
  bye.reply(sip.makeResponse(bye.message, 200, 'OK'));
  await dialog.queue;
  assert.equal(s.dialogs.size, 0);
});

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

test('call ownership requires the same address, port and transport protocol', () => {
  const peer = { address: '192.0.2.1', port: 5060, protocol: 'TCP' };
  assert.equal(samePeer(peer, { ...peer }), true);
  for (const change of [{ address: '192.0.2.2' }, { port: 5061 }, { protocol: 'UDP' }])
    assert.equal(samePeer(peer, { ...peer, ...change }), false);
});
