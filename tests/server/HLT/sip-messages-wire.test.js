// @test S-HLT-025
// @requirements HLR-SRV-MESSAGE-001
// @environment portable
// @plan Start the real SIP transport and disposable UDP phone/terminal endpoints. Register through Digest, send authenticated Unicode MESSAGE traffic and verify recipient identity proof and relayed acknowledgement. Exercise wrong password, unsupported content, removed group and unreachable recipient; inspect activity records for body/credential leakage.
// @pass Only permitted authenticated text reaches the registered terminal, the proof matches its credential, failure responses are delivered to the sender, and activity records contain no message body or secret.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const sip = require('../../../zmala_server/node_modules/sip');
const { SipServer } = require('../../../zmala_server/sip-server');
const { storeFixture } = require('../../support/server/unit-fixture');
const { udpPeer, request, authenticate } = require('../../support/server/udp-peer');

test(
  'real SIP text delivery authenticates both registration and sender and keeps activity private',
  { timeout: 15000 },
  async (t) => {
    const store = storeFixture(t);
    const phone = await udpPeer(),
      terminal = await udpPeer(),
      reservation = await udpPeer();
    const port = reservation.port;
    reservation.close();
    Object.assign(store.value, { host: '127.0.0.1', sip_port: port });
    const server = new SipServer(store);
    t.after(() => {
      server.close();
      phone.close();
      terminal.close();
    });
    server.start();
    const register = request(terminal, 'REGISTER', 'term1');
    register.headers.expires = 600;
    assert.equal(
      (
        await authenticate(terminal, register, port, {
          user: 'term1',
          password: store.value.users.term1.password,
        })
      ).status,
      200,
    );
    const text = 'Private message: Bonjour — 日本語';
    const message = request(
      phone,
      'MESSAGE',
      'phone1',
      'term1',
      Buffer.from(text).toString('latin1'),
    );
    const arriving = terminal.wait((m) => m.method === 'MESSAGE');
    const acknowledged = authenticate(phone, message, port, {
      user: 'phone1',
      password: store.value.users.phone1.password,
    });
    const forwarded = await arriving;
    assert.equal(Buffer.from(forwarded.content, 'latin1').toString('utf8'), text);
    assert.equal(forwarded.headers['x-zmala-message-id'], message.headers['call-id'] + ':2');
    assert.equal(
      forwarded.headers['x-family-auth'],
      crypto
        .createHmac('sha256', store.value.users.term1.device_token)
        .update(`message:${forwarded.headers['x-zmala-message-id']}:phone1`)
        .digest('hex'),
    );
    assert.equal(forwarded.headers['proxy-authorization'], undefined);
    terminal.send(sip.makeResponse(forwarded, 200, 'OK'), port);
    assert.equal((await acknowledged).status, 200);
    const rejected = async (
      status,
      mutate = () => {},
      password = store.value.users.phone1.password,
    ) => {
      const next = request(phone, 'MESSAGE', 'phone1', 'term1', 'private-body');
      mutate(next);
      assert.equal(
        (await authenticate(phone, next, port, { user: 'phone1', password })).status,
        status,
      );
    };
    await rejected(407, () => {}, 'incorrect-fixture-password');
    await rejected(415, (m) => {
      m.headers['content-type'] = 'application/json';
    });
    await rejected(400, (m) => {
      m.content = ' ';
    });
    await rejected(413, (m) => {
      m.content = 'x'.repeat(16385);
    });
    store.updateGroup('family', { name: 'Family', members: ['term1'] });
    await rejected(403);
    store.updateGroup('family', { name: 'Family', members: ['term1', 'phone1'] });
    server.registrations.delete('term1');
    await rejected(480);
    assert.equal(terminal.messages.filter((m) => m.method === 'MESSAGE').length, 0);
    for (const secret of [
      text,
      'private-body',
      store.value.users.phone1.password,
      store.value.users.term1.device_token,
    ])
      assert.equal(JSON.stringify(server.events).includes(secret), false);
  },
);
