// @test S-LLT-007
// @requirements LLR-SRV-BOOT-005, LLR-SRV-BOOT-006
// @environment portable
// @plan Use controlled listener and persistence promises; assert shutdown drains both listeners once, tolerates partial startup and propagates persistence failure.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { once } = require('node:events');
const { createShutdown } = require('../../../zmala_server/shutdown');

test('shutdown drains both listeners before persistence and runs only once', async (t) => {
  let finishRequest;
  const handling = new Promise((resolve) => {
    finishRequest = resolve;
  });
  let response;
  const first = http.createServer((_request, reply) => {
    response = reply;
    finishRequest();
  });
  const second = http.createServer();
  t.after(() => {
    response?.end();
    first.closeAllConnections();
    first.close();
    second.close();
  });
  for (const listener of [first, second]) {
    listener.listen(0, '127.0.0.1');
    await once(listener, 'listening');
  }
  const requestDone = new Promise((resolve, reject) => {
    http
      .get(`http://127.0.0.1:${first.address().port}`, { agent: false }, (reply) => {
        reply.resume();
        reply.on('end', resolve);
      })
      .on('error', reject);
  });
  await handling;
  let sipStops = 0;
  let flushes = 0;
  const shutdown = createShutdown([first, second], { close: () => sipStops++ }, async () => {
    assert.equal(first.listening, false);
    assert.equal(second.listening, false);
    assert.equal(response.writableEnded, true);
    flushes++;
  });
  const pending = shutdown();
  assert.equal(shutdown(), pending);
  assert.equal(sipStops, 1);
  assert.equal(flushes, 0);
  response.end('saved');
  await Promise.all([pending, requestDone]);
  assert.equal(flushes, 1);
});

test('shutdown also handles an unstarted listener and preserves persistence failure', async () => {
  const failure = Error('disk unavailable');
  const shutdown = createShutdown([http.createServer()], { close() {} }, async () => {
    throw failure;
  });
  await assert.rejects(shutdown(), (error) => error === failure);
  await assert.rejects(shutdown(), (error) => error === failure);
});
