// @test S-HLT-017
// @requirements SHLR006
// @environment portable
// @plan Create real UDP relay sockets with disposable signalling peers; negotiate audio and video SDP and verify rewritten endpoints, bidirectional RTP/RTCP delivery and forwarding counters.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const dgram = require('node:dgram');

const { MediaRelay } = require('../../../zmala_server/media');

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
