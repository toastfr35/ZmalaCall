'use strict';
// LAB ONLY: preserve authenticated SIP routing, negotiate endpoint-owned ICE/SRTP.
// The production UDP relay and its source-IP checks are not changed.
const fs = require('node:fs');
const transport = require('../../../zmala_server/sip-transport');
const original = transport.startProxy;
transport.startProxy = (options, ...args) =>
  original(
    {
      ...options,
      udp: false,
      tcp: false,
      port: 443,
      tls_port: 5061,
      tls: { key: fs.readFileSync('/lab/server.key'), cert: fs.readFileSync('/lab/server.pem') },
    },
    ...args,
  );
const proxy = require('../../../zmala_server/node_modules/sip/proxy');
const sip = require('../../../zmala_server/node_modules/sip');
const send = proxy.send;
proxy.send = (message, ...args) => {
  for (const route of message.headers?.['record-route'] || [])
    if (sip.stringifyUri(route.uri).startsWith('sip:10.231.100.13:5060'))
      route.uri = 'sip:10.231.100.13:443;transport=tls;lr';
  return send(message, ...args);
};
const { MediaRelay } = require('../../../zmala_server/media');
// ICE connectivity checks bind peers to SDP credentials; SRTP protects media.
// This adapter is deliberately restricted to synthetic test identities and ICE offers.
MediaRelay.prototype.rewrite = async function (id, sdp) {
  if (!sdp.startsWith('v=0') || !/a=ice-ufrag:/.test(sdp) || !/a=ice-pwd:/.test(sdp))
    throw Error('TLS prototype requires ICE');
  if (!/m=audio \d+ RTP\/SAVP/.test(sdp) || !/a=crypto:/.test(sdp))
    throw Error('TLS prototype requires SRTP');
  return sdp;
};
require('../../../zmala_server/main')
  .start()
  .catch(() => {
    process.exitCode = 1;
  });
