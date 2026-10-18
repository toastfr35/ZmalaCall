'use strict';
const dgram = require('node:dgram');
const crypto = require('node:crypto');
const sip = require('../../../zmala_server/node_modules/sip');
const digest = require('../../../zmala_server/node_modules/sip/digest');

/** Real disposable SIP endpoint with bounded waits and no shared registration. */
async function udpPeer() {
  const socket = dgram.createSocket('udp4');
  await new Promise((resolve) => socket.bind(0, '127.0.0.1', resolve));
  const messages = [],
    waiters = new Set();
  socket.on('message', (bytes, remote) => {
    const message = sip.parse(bytes.toString('latin1'));
    if (!message) return;
    for (const waiter of waiters) {
      if (waiter.predicate(message)) {
        waiters.delete(waiter);
        clearTimeout(waiter.timer);
        waiter.resolve(message);
        return;
      }
    }
    messages.push(message);
    if (message.method === 'OPTIONS')
      socket.send(
        Buffer.from(sip.stringify(sip.makeResponse(message, 200, 'OK')), 'latin1'),
        remote.port,
        remote.address,
      );
  });
  return {
    socket,
    messages,
    get port() {
      return socket.address().port;
    },
    wait(predicate) {
      const index = messages.findIndex(predicate);
      if (index >= 0) return Promise.resolve(messages.splice(index, 1)[0]);
      return new Promise((resolve, reject) => {
        const waiter = {
          predicate,
          resolve,
          timer: setTimeout(() => {
            waiters.delete(waiter);
            reject(Error('Timed out waiting for SIP packet'));
          }, 3000),
        };
        waiters.add(waiter);
      });
    },
    send(message, port) {
      socket.send(Buffer.from(sip.stringify(message), 'latin1'), port, '127.0.0.1');
    },
    close() {
      for (const waiter of waiters) clearTimeout(waiter.timer);
      socket.close();
    },
  };
}

function request(peer, method, from, to = from, content = '') {
  return {
    method,
    uri: `sip:${to}@127.0.0.1`,
    content,
    headers: {
      from: { uri: `sip:${from}@127.0.0.1`, params: { tag: crypto.randomUUID() } },
      to: { uri: `sip:${to}@127.0.0.1` },
      via: [
        {
          protocol: 'UDP',
          host: '127.0.0.1',
          port: peer.port,
          params: { branch: 'z9hG4bK-' + crypto.randomUUID(), rport: null },
        },
      ],
      contact: [{ uri: `sip:${from}@127.0.0.1:${peer.port}` }],
      cseq: { seq: 1, method },
      'call-id': crypto.randomUUID(),
      'max-forwards': 70,
      'content-type': 'text/plain; charset=utf-8',
    },
  };
}

async function authenticate(peer, message, port, credentials) {
  const response = () =>
    peer.wait((m) => m.status >= 200 && m.headers['call-id'] === message.headers['call-id']);
  let reply = response();
  peer.send(message, port);
  const challenge = await reply;
  if (![401, 407].includes(challenge.status))
    throw Error(`Expected Digest challenge, received ${challenge.status}`);
  message.headers.via[0].params.branch = 'z9hG4bK-' + crypto.randomUUID();
  message.headers.cseq.seq++;
  digest.signRequest({}, message, challenge, credentials);
  reply = response();
  peer.send(message, port);
  return reply;
}

module.exports = { udpPeer, request, authenticate };
