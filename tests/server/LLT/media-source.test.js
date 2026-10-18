// @test S-LLT-026
// @requirements SLLR037
// @environment portable
// @plan Inject event-emitting UDP socket doubles into a relay stream; send undersized, unknown-peer and forged-IP packets, then authenticated RTP and RTCP in both directions. Observe port learning and forwarded bytes.
// @pass Rejected packets must neither alter learned ports nor forward bytes; valid signaling peers must forward unchanged packets to the opposite learned destination.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const { MediaRelay } = require('../../../zmala_server/media');

test('only authenticated signaling peer can learn and forward RTP or RTCP', async () => {
  const relay = new MediaRelay('192.0.2.1'),
    sent = [];
  let port = 20000;
  relay.socket = async () => {
    const socket = new EventEmitter();
    socket.send = (...args) => sent.push(args);
    return { port: port++, socket };
  };
  const legs = await relay.stream(),
    packet = Buffer.from([128, 96, 0, 1]);
  for (const kind of ['rtp', 'rtcp'])
    for (const side of [0, 1]) {
      const leg = legs[side],
        other = legs[1 - side],
        key = kind + 'Target';
      leg.peer = '192.0.2.2';
      other.peer = undefined;
      const before = sent.length;
      leg[kind].socket.emit('message', packet, { address: leg.peer, port: 6000 });
      assert.equal(leg[key], undefined);
      other.peer = '192.0.2.3';
      other[key] = { address: other.peer, port: 7000 };
      leg[kind].socket.emit('message', packet, { address: '203.0.113.1', port: 6001 });
      leg[kind].socket.emit('message', packet.subarray(0, 3), { address: leg.peer, port: 6002 });
      assert.equal(sent.length, before);
      assert.equal(leg[key], undefined);
      leg[kind].socket.emit('message', packet, { address: leg.peer, port: 6003 });
      assert.deepEqual(leg[key], { address: leg.peer, port: 6003 });
      assert.deepEqual(sent.at(-1), [packet, 7000, other.peer]);
      delete leg[key];
      delete other[key];
    }
});
