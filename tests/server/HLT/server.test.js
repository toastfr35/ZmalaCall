// @test S-HLT-017
// @requirements SHLR003, SHLR005, SHLR006
// @environment portable
// @plan Compose SIP routing and real UDP relay sockets with disposable accounts; assert shared-group routing, authenticated terminal recipients, rewritten endpoints and bidirectional RTP/RTCP forwarding.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const dgram = require('node:dgram');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const sip = require('../../../zmala_server/node_modules/sip');

const { Store } = require('../../../zmala_server/store');
const { MediaRelay } = require('../../../zmala_server/media');
const { SipServer } = require('../../../zmala_server/sip-server');
const proxy = require('../../../zmala_server/node_modules/sip/proxy');
const crypto = require('node:crypto');

test('SIP routing enforces groups and authenticates every terminal recipient', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'family-routing-')),
    send = proxy.send,
    encodeFlowUri = sip.encodeFlowUri;
  try {
    const s = new Store(dir);
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'alice',
      name: 'Alice',
      type: 'linphone',
    });
    s.createAccount({ emails: ['fixture@example.test'], id: 'bob', name: 'Bob', type: 'linphone' });
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'lounge',
      name: 'Lounge',
      type: 'terminal',
    });
    const server = new SipServer(s),
      sent = [];
    proxy.send = (message) => sent.push(message);
    sip.encodeFlowUri = (flow) => `sip:${flow.address}:${flow.port}`;
    server.auth.verify = () => 'alice';
    const peer = { address: '127.0.0.1', port: 50001, protocol: 'UDP' },
      target = { address: '127.0.0.1', port: 50002, protocol: 'UDP' };
    for (const id of ['bob', 'lounge'])
      server.registrations.set(id, {
        contact: { uri: `sip:${id}@127.0.0.1:50002` },
        remote: target,
        expires: Date.now() + 60000,
      });
    const request = (to) => ({
      method: 'INVITE',
      uri: `sip:${to}@${s.value.host}`,
      headers: {
        to: { uri: `sip:${to}@${s.value.host}`, params: {} },
        from: { uri: `sip:alice@${s.value.host}`, params: { tag: 'alice-tag' } },
        via: [],
        cseq: { seq: 1, method: 'INVITE' },
        'call-id': 'test-' + to,
        contact: [{ uri: 'sip:alice@127.0.0.1:50001' }],
        'x-family-auth': 'forged',
      },
      content: '',
    });
    await server.request(request('bob'), peer);
    assert.equal(sent.pop().status, 403);
    const group = s.createGroup({ name: 'Peers', members: ['alice', 'bob', 'lounge'] });
    await server.request(request('bob'), peer);
    const phone = sent.pop();
    assert.equal(phone.method, 'INVITE');
    assert.equal(phone.headers['x-family-auth'], undefined);
    await server.request(request('lounge'), peer);
    assert.equal(sent.pop().status, 486);
    server.dialogs.clear();
    await server.request(request('lounge'), peer);
    const terminal = sent.pop();
    const proof = crypto
      .createHmac('sha256', s.value.users.lounge.device_token)
      .update('test-lounge:alice')
      .digest('hex');
    assert.equal(terminal.headers['x-family-auth'], proof);
    assert.notEqual(
      proof,
      crypto
        .createHmac('sha256', s.value.users.term1.device_token)
        .update('test-lounge:alice')
        .digest('hex'),
    );
    server.dialogs.clear();
    s.deleteGroup(group);
    await server.request(request('bob'), peer);
    assert.equal(sent.pop().status, 403);
  } finally {
    proxy.send = send;
    if (encodeFlowUri) sip.encodeFlowUri = encodeFlowUri;
    else delete sip.encodeFlowUri;
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
test('audio/video SDP uses relay ports and actual signalling peers, with bidirectional RTP and RTCP', async () => {
  const relay = new MediaRelay('127.0.0.1', 24000, 24050),
    peers = [];
  async function peer() {
    const s = dgram.createSocket('udp4');
    await new Promise((r) => s.bind(0, '127.0.0.1', r));
    peers.push(s);
    return s;
  }
  try {
    const a = await peer(),
      b = await peer();
    const sdp = (port) =>
      `v=0\r\no=- 1 1 IN IP4 8.8.8.8\r\ns=-\r\nc=IN IP4 8.8.8.8\r\nt=0 0\r\nm=audio ${port} RTP/AVP 0\r\na=rtcp-mux\r\na=ice-ufrag:test\r\na=candidate:bad\r\nm=video ${port} RTP/AVP 96\r\na=rtpmap:96 VP8/90000\r\n`;
    const offer = await relay.rewrite('test', sdp(a.address().port), 0, '127.0.0.1');
    const answer = await relay.rewrite('test', sdp(b.address().port), 1, '127.0.0.1');
    assert.match(offer, /c=IN IP4 127.0.0.1/);
    assert.doesNotMatch(offer, /rtcp-mux|ice-ufrag|candidate/);
    const leg = relay.sessions.get('test').streams[0];
    assert.match(offer, new RegExp(`m=audio ${leg[1].rtp.port} `));
    assert.match(answer, new RegExp(`m=audio ${leg[0].rtp.port} `));
    for (const kind of ['rtp', 'rtcp']) {
      leg[0][kind + 'Target'] = { address: '127.0.0.1', port: a.address().port };
      leg[1][kind + 'Target'] = { address: '127.0.0.1', port: b.address().port };
      for (const [sender, receiver, side] of [
        [a, b, 0],
        [b, a, 1],
      ]) {
        const packet = Buffer.from([128, 96, 1, 2, 3, 4, 5, 6]);
        const received = new Promise((resolve, reject) => {
          const timer = setTimeout(() => reject(Error('relay timeout')), 2000);
          receiver.once('message', (bytes) => {
            clearTimeout(timer);
            resolve(bytes);
          });
        });
        sender.send(packet, leg[side][kind].port, '127.0.0.1');
        assert.deepEqual(await received, packet);
      }
    }
    relay.close('test');
    assert.equal(relay.used.size, 0);
    await assert.rejects(
      relay.rewrite('bundle', sdp(2000) + 'a=group:BUNDLE 0 1\r\n', 0, '127.0.0.1'),
    );
  } finally {
    relay.closeAll();
    for (const s of peers) s.close();
  }
});
