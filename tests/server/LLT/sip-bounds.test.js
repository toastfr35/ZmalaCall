// @test S-LLT-008
// @requirements LLR-SRV-CALL-010
// @environment portable
// @plan Feed fragmented, pipelined and malformed stream frames and fake proxy traffic; assert byte/deadline/context bounds, CRLF keepalives and quota cleanup.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const sip = require('../../../zmala_server/node_modules/sip');

function wire(length, body = '') {
  return (
    'OPTIONS sip:x@localhost SIP/2.0\r\nVia: SIP/2.0/TCP localhost;branch=z9hG4bK-x\r\nTo: <sip:x@localhost>\r\nFrom: <sip:y@localhost>;tag=y\r\nCall-ID: test\r\nCSeq: 1 OPTIONS\r\nContent-Length: ' +
    length +
    '\r\n\r\n' +
    body
  );
}

test('stream framing rejects invalid and duplicate lengths and stops retaining input', () => {
  for (const value of ['NaN', '-1', '1.5', '3x', '999999999999999999999', '21', '0\r\nl: 0']) {
    let floods = 0,
      messages = 0;
    const parse = sip.makeStreamParser(
      () => messages++,
      () => floods++,
      1024,
      20,
    );
    parse(wire(value));
    parse('x'.repeat(100000));
    assert.equal(floods, 1, value);
    assert.equal(messages, 0, value);
  }
});

test('stream framing supports fragments, pipelines and idle CRLF keepalives', () => {
  const messages = [];
  const parse = sip.makeStreamParser(
    (m) => messages.push(m),
    () => assert.fail('unexpected flood'),
    1024,
    20,
  );
  parse('\r');
  parse('\n\r\n');
  const first = wire('4', 'test');
  parse(first.slice(0, 50));
  parse(first.slice(50, -2));
  assert.equal(messages.length, 0);
  parse(first.slice(-2) + '\r\n' + wire('0'));
  assert.deepEqual(
    messages.map((m) => m.content),
    ['test', ''],
  );
  parse.close();
});

test('unfinished stream bodies expire even if more bytes arrive', async () => {
  let floods = 0;
  const parse = sip.makeStreamParser(
    () => assert.fail('incomplete message'),
    () => floods++,
    1024,
    20,
    30,
  );
  parse(wire('20', 'x'));
  await new Promise((resolve) => setTimeout(resolve, 20));
  parse('x');
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(floods, 1);
});

test('ACKs retain no proxy contexts; outstanding requests have peer quotas and expiry', () => {
  let receive;
  const timers = new Set(),
    sent = [],
    routed = [];
  const fakeSip = {
    start: (_options, handler) => {
      receive = handler;
    },
    copyMessage: (m) => structuredClone(m),
    send: (m) => sent.push(m),
    makeResponse: (m, status) => ({ ...m, method: undefined, status }),
    stop() {},
  };
  const context = {
    exports: {},
    require: (name) => (name === 'sip' ? fakeSip : require(name)),
    setTimeout: (fn) => {
      const timer = { fn, unref() {} };
      timers.add(timer);
      return timer;
    },
    clearTimeout: (timer) => timers.delete(timer),
  };
  vm.runInNewContext(
    fs.readFileSync(require.resolve('../../../zmala_server/vendor/sip/proxy'), 'utf8'),
    context,
  );
  context.exports.start({}, (rq) => routed.push(rq));
  const peer = { protocol: 'UDP', address: '127.0.0.1', port: 5000 };
  const request = (seq, method) => ({
    method,
    headers: {
      via: [{ params: { branch: 'b' + seq }, protocol: 'UDP', host: 'localhost', port: 5000 }],
      'call-id': 'call',
      cseq: { seq, method },
    },
  });
  for (let i = 0; i < 5000; i++) receive(request(i, 'ACK'), peer);
  assert.equal(timers.size, 0);
  for (let i = 0; i < 129; i++) receive(request(i, 'INVITE'), peer);
  assert.equal(timers.size, 128);
  assert.equal(sent.at(-1).status, 503);
  for (const timer of [...timers]) timer.fn();
  assert.equal(timers.size, 0);
  receive(request(200, 'INVITE'), peer);
  assert.equal(timers.size, 1);
  context.exports.clearContexts();
  assert.equal(timers.size, 0);
});
