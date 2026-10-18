// @test S-LLT-003
// @requirements SLLR035, SLLR036, SLLR038, SLLR039
// @environment portable
// @plan Defer relay allocation and close/update streams at controlled points; assert shared allocation, valid RTCP bounds, transactional endpoints and reclamation of late sockets.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { MediaRelay } = require('../../../zmala_server/media');

const sdp = 'v=0\r\nc=IN IP4 127.0.0.1\r\nm=audio 4000 RTP/AVP 0\r\n';
function deferredStream(relay) {
  let complete,
    allocations = 0,
    closed = 0;
  const sockets = [21000, 21001, 21002, 21003].map((port) => {
    relay.used.add(port);
    return {
      port,
      socket: {
        close() {
          closed++;
        },
      },
    };
  });
  relay.stream = () => {
    allocations++;
    return new Promise((resolve) => {
      complete = () =>
        resolve([
          { rtp: sockets[0], rtcp: sockets[1] },
          { rtp: sockets[2], rtcp: sockets[3] },
        ]);
    });
  };
  return { complete: () => complete(), allocations: () => allocations, closed: () => closed };
}

test('simultaneous SDP rewrites share an allocation and closing during bind reclaims every socket', async () => {
  const relay = new MediaRelay('127.0.0.1');
  const pending = deferredStream(relay);
  const a = relay.rewrite('call', sdp, 0, '127.0.0.1');
  const b = relay.rewrite('call', sdp, 1, '127.0.0.1');
  assert.equal(pending.allocations(), 1);
  relay.close('call');
  pending.complete();
  await Promise.all([assert.rejects(a, /session closed/), assert.rejects(b, /session closed/)]);
  assert.equal(pending.closed(), 4);
  assert.equal(relay.used.size, 0);
  assert.equal(relay.sessions.size, 0);
});

test('last UDP port does not synthesize an invalid RTCP destination; explicit RTCP remains usable', async () => {
  const relay = new MediaRelay('127.0.0.1');
  const pending = deferredStream(relay);
  const offer = relay.rewrite('call', sdp.replace('4000', '65535'), 0, '127.0.0.1');
  pending.complete();
  await offer;
  const leg = relay.sessions.get('call').streams[0][0];
  assert.equal(leg.rtcpTarget, null);
  await relay.rewrite(
    'call',
    sdp.replace('4000', '65535') + 'a=rtcp:62000 IN IP4 127.0.0.1\r\n',
    0,
    '127.0.0.1',
  );
  assert.equal(leg.rtcpTarget.port, 62000);
  relay.closeAll();
  assert.equal(pending.closed(), 4);
});

test('media updates validate before mutation, stage until accepted and release disabled streams', async () => {
  const relay = new MediaRelay('127.0.0.1');
  const pending = deferredStream(relay);
  const offer = relay.rewrite('call', sdp, 0, '127.0.0.1');
  pending.complete();
  await offer;
  await relay.rewrite('call', sdp, 1, '127.0.0.2');
  const legs = relay.sessions.get('call').streams[0];
  await assert.rejects(
    relay.rewrite(
      'call',
      sdp.replace('4000', '6000') + 'm=video NaN RTP/AVP 96\r\n',
      0,
      '127.0.0.1',
    ),
    /Invalid media port/,
  );
  assert.equal(legs[0].rtpTarget.port, 4000);
  const rejected = relay.begin('call');
  await relay.rewrite('call', sdp.replace('4000', '6000'), 0, '127.0.0.1', rejected);
  assert.equal(legs[0].rtpTarget.port, 4000);
  relay.discard(rejected);
  assert.equal(legs[0].rtpTarget.port, 4000);
  const accepted = relay.begin('call');
  await relay.rewrite('call', sdp.replace('4000', '6000'), 0, '127.0.0.1', accepted);
  relay.commit(accepted);
  assert.equal(legs[0].rtpTarget.port, 6000);
  const disabled = relay.begin('call');
  await relay.rewrite('call', sdp.replace('4000', '0'), 0, '127.0.0.1', disabled);
  assert.equal(pending.closed(), 0);
  relay.commit(disabled);
  assert.equal(pending.closed(), 4);
  assert.equal(relay.used.size, 0);
  assert.equal(legs[0].peer, undefined);
  assert.equal(legs[1].peer, undefined);
  relay.closeAll();
});

test('discarding a staged update while binding reclaims late sockets', async () => {
  const relay = new MediaRelay('127.0.0.1');
  const pending = deferredStream(relay),
    update = relay.begin('call');
  const offer = relay.rewrite('call', sdp, 0, '127.0.0.1', update);
  relay.discard(update);
  pending.complete();
  await assert.rejects(offer, /Media update closed/);
  assert.equal(pending.closed(), 4);
  assert.equal(relay.used.size, 0);
  relay.closeAll();
});
