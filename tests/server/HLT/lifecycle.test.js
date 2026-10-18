// @test S-HLT-027
// @requirements HLR-SRV-START-001, HLR-SRV-START-002
// @environment portable
// @plan On Linux, start the production entrypoint in a disposable copied runtime, query HTTP and SIP without a terminal, save an account group and stop by SIGTERM. Occupy the HTTP port and check reported failure and sibling listener cleanup. Separately stop the assembled HTTP/SIP/media service twice while a real request is incomplete, then finish it and reload persisted state.
// @pass Clean stop preserves accepted state and releases listeners/media; duplicate stops share one operation; failed startup exits nonzero without retaining its SIP listener. Pi boot/service-manager activation remains a hardware acceptance check.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const net = require('node:net');
const { once } = require('node:events');
const { Store } = require('../../../zmala_server/store');
const { SipServer } = require('../../../zmala_server/sip-server');
const { createShutdown } = require('../../../zmala_server/shutdown');
const { httpFixture } = require('../../support/server/http-fixture');
const { runtimeProcess, unusedPort, waitFor } = require('../../support/server/runtime-process');
const { udpPeer, request, authenticate } = require('../../support/server/udp-peer');

async function tcpReachable(port) {
  return new Promise((resolve) => {
    const socket = net.connect(port, '127.0.0.1');
    socket.once('connect', () => {
      socket.destroy();
      resolve(true);
    });
    socket.once('error', () => resolve(false));
  });
}

test(
  'independent production process serves HTTP/SIP, persists changes and stops cleanly',
  { skip: process.platform !== 'linux', timeout: 15000 },
  async (t) => {
    const run = await runtimeProcess(t);
    await waitFor(
      () => run.output.includes('Administration:') || run.child.exitCode !== null,
      'HTTP startup',
    );
    assert.equal(run.child.exitCode, null, run.output);
    const value = run.store.value,
      base = `http://127.0.0.1:${value.http_port}`;
    assert.equal((await fetch(base)).status, 200);
    assert.equal(await tcpReachable(value.sip_port), true);
    const peer = await udpPeer();
    t.after(() => peer.close());
    assert.equal(
      (
        await authenticate(peer, request(peer, 'REGISTER', 'phone1'), value.sip_port, {
          user: 'phone1',
          password: value.users.phone1.password,
        })
      ).status,
      200,
    );
    const saved = await fetch(base + '/api/groups', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + value.admin_token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Restart proof', members: ['term1', 'phone1'] }),
    });
    assert.equal(saved.status, 201);
    const group = (await saved.json()).id;
    run.child.kill('SIGTERM');
    assert.deepEqual(await run.exited, { code: 0, signal: null });
    assert.equal(await tcpReachable(value.http_port), false);
    assert.equal(await tcpReachable(value.sip_port), false);
    assert.equal(new Store(run.store.dir).value.groups[group].name, 'Restart proof');
  },
);

test(
  'production startup reports occupied HTTP port and releases SIP sibling',
  { skip: process.platform !== 'linux', timeout: 15000 },
  async (t) => {
    const occupied = net.createServer();
    occupied.listen(0, '0.0.0.0');
    await once(occupied, 'listening');
    t.after(() => new Promise((resolve) => occupied.close(resolve)));
    const run = await runtimeProcess(t, { http_port: occupied.address().port });
    await waitFor(() => run.child.exitCode !== null, 'failed startup exit');
    assert.equal(run.child.exitCode, 1, run.output);
    assert.match(run.output, /EADDRINUSE|address already in use/);
    assert.equal(await tcpReachable(run.store.value.sip_port), false);
  },
);

test(
  'concurrent shutdown drains an admitted request, flushes its state and releases media',
  { timeout: 10000 },
  async (t) => {
    const fixture = await httpFixture();
    t.after(() => fixture.close());
    fixture.store.value.sip_port = await unusedPort();
    const sip = new SipServer(fixture.store);
    sip.start();
    t.after(() => sip.close());
    await sip.media.rewrite(
      'shutdown-media',
      'v=0\r\nc=IN IP4 127.0.0.1\r\nm=audio 9998 RTP/AVP 0\r\n',
      0,
      '127.0.0.1',
    );
    assert.ok(sip.media.used.size > 0);
    const body = JSON.stringify({ name: 'Drain proof', members: ['term1', 'phone1'] });
    const admitted = once(fixture.server, 'request');
    const request = http.request(fixture.base + '/api/groups', {
      method: 'POST',
      agent: false,
      headers: {
        Authorization: 'Bearer ' + fixture.store.value.admin_token,
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body),
        Connection: 'close',
      },
    });
    const response = new Promise((resolve, reject) => {
      request.once('error', reject);
      request.once('response', (reply) => {
        let data = '';
        reply.on('data', (bytes) => {
          data += bytes;
        });
        reply.on('end', () => resolve({ status: reply.statusCode, body: JSON.parse(data) }));
      });
    });
    request.write(body.slice(0, 8));
    await admitted;
    let flushes = 0,
      finished = false;
    const stop = createShutdown([fixture.server], sip, async () => {
      flushes++;
      await fixture.flush();
    });
    const first = stop();
    assert.equal(stop(), first);
    first.then(() => {
      finished = true;
    });
    assert.equal(sip.media.used.size, 0);
    assert.equal(
      await tcpReachable(fixture.server.address()?.port || new URL(fixture.base).port),
      false,
    );
    assert.equal(finished, false);
    request.end(body.slice(8));
    const reply = await response;
    assert.equal(reply.status, 201);
    await first;
    assert.equal(flushes, 1);
    assert.equal(new Store(fixture.directory).value.groups[reply.body.id].name, 'Drain proof');
  },
);
