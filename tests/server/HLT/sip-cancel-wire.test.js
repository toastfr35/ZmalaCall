// @test S-HLT-019
// @requirements SHLR005
// @environment portable
// @plan Use real UDP signaling against the SIP server with delayed SDP allocation; send authorized and foreign CANCEL messages and assert only the caller cancels, with no late INVITE ringing.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const dgram = require('node:dgram');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const sip = require('../../../zmala_server/node_modules/sip');
const { Store } = require('../../../zmala_server/store');
const { SipServer } = require('../../../zmala_server/sip-server');

async function socket() {
  const value = dgram.createSocket('udp4');
  await new Promise((resolve) => value.bind(0, '127.0.0.1', resolve));
  return value;
}
function response(socket, status, method) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      socket.off('message', receive);
      reject(Error(`No ${status} ${method} response`));
    }, 3000);
    function receive(packet) {
      const message = sip.parse(packet.toString());
      if (message?.status === status && message.headers.cseq.method === method) {
        clearTimeout(timer);
        socket.off('message', receive);
        resolve(message);
      }
    }
    socket.on('message', receive);
  });
}

test(
  'real UDP CANCEL is peer-bound and cancels an INVITE waiting for SDP without ringing',
  { timeout: 10000 },
  async () => {
    const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'zmala-cancel-wire-'));
    const caller = await socket(),
      recipient = await socket(),
      foreign = await socket();
    const reservation = await socket();
    const port = reservation.address().port;
    reservation.close();
    const store = new Store(directory);
    Object.assign(store.value, { host: '127.0.0.1', sip_port: port });
    const server = new SipServer(store);
    server.auth.verify = () => 'phone1'; // Isolate transport cancellation from Digest tests.
    server.registrations.set('term1', {
      remote: {
        address: '127.0.0.1',
        port: recipient.address().port,
        protocol: 'UDP',
        local: { address: '127.0.0.1', port },
      },
      contact: { uri: `sip:term1@127.0.0.1:${recipient.address().port}` },
      expires: Date.now() + 60000,
    });
    let release, started;
    const pending = new Promise((resolve) => {
      release = resolve;
    });
    const allocation = new Promise((resolve) => {
      started = resolve;
    });
    server.media.rewrite = () => {
      started();
      return pending;
    };
    const received = [];
    recipient.on('message', (packet) => received.push(sip.parse(packet.toString())));
    const invite = {
      method: 'INVITE',
      uri: 'sip:term1@127.0.0.1',
      headers: {
        to: { uri: 'sip:term1@127.0.0.1', params: {} },
        from: { uri: 'sip:phone1@127.0.0.1', params: { tag: 'wire-caller' } },
        via: [
          {
            protocol: 'UDP',
            host: '127.0.0.1',
            port: caller.address().port,
            params: { branch: 'z9hG4bK-wire-cancel', rport: null },
          },
        ],
        contact: [{ uri: `sip:phone1@127.0.0.1:${caller.address().port}` }],
        cseq: { seq: 42, method: 'INVITE' },
        'call-id': 'wire-cancel',
        'max-forwards': 70,
        'content-type': 'application/sdp',
      },
      content: 'v=0\r\nm=audio 4000 RTP/AVP 0\r\n',
    };
    function send(source, message) {
      source.send(Buffer.from(sip.stringify(message)), port, '127.0.0.1');
    }
    try {
      server.start();
      // Let the asynchronous UDP bind finish before sending the first datagram.
      await new Promise((resolve) => setTimeout(resolve, 20));
      send(caller, invite);
      await Promise.race([
        allocation,
        new Promise((resolve, reject) => {
          const timeout = setTimeout(
            () => reject(Error('INVITE did not reach SDP allocation')),
            3000,
          );
          allocation.then(() => {
            clearTimeout(timeout);
            resolve();
          });
        }),
      ]);
      const cancel = structuredClone(invite);
      cancel.method = cancel.headers.cseq.method = 'CANCEL';
      delete cancel.headers['content-type'];
      cancel.content = '';
      const forbidden = response(foreign, 403, 'CANCEL');
      send(foreign, cancel);
      await forbidden;
      assert.equal(server.dialogs.get('wire-cancel').invites.get('0:42').cancelled, false);
      const accepted = response(caller, 200, 'CANCEL');
      const terminated = response(caller, 487, 'INVITE');
      send(caller, cancel);
      await accepted;
      release('v=0\r\n');
      await terminated;
      assert.equal(
        received.some((message) => message?.method === 'INVITE'),
        false,
      );
      assert.equal(server.dialogs.size, 0);
    } finally {
      release('v=0\r\n');
      server.close();
      caller.close();
      recipient.close();
      foreign.close();
      await fs.rm(directory, { recursive: true, force: true });
    }
  },
);
