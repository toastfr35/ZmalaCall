// Run only on an explicitly selected test Pi, from its active zmala_server directory.
'use strict';
const path = require('node:path');
const dgram = require('node:dgram');
const fs = require('node:fs');
const tls = require('node:tls');
const crypto = require('node:crypto');
const sip = require(path.join(process.cwd(), 'node_modules/sip'));
const digest = require(path.join(process.cwd(), 'node_modules/sip/digest'));
const { Store } = require(path.join(process.cwd(), 'store'));
const store = new Store('/var/lib/zmalacall-server');
const [from, to] = process.argv.slice(2);
if (!store.permitted(from, to)) throw Error('Test accounts cannot call each other.');
const id = 'push-check-' + crypto.randomUUID();
const policyFile = process.env.ZMALA_SECURE_CALLS_FILE || '/etc/zmalacall-server/secure-calls.json';
const secure = fs.existsSync(policyFile) ? JSON.parse(fs.readFileSync(policyFile, 'utf8')) : null;
const socket = secure
  ? tls.connect({
      host: '127.0.0.1',
      port: secure.sip_listen_port || 5061,
      servername: secure.sip_host,
      rejectUnauthorized: true,
    })
  : dgram.createSocket('udp4');
let request,
  challenged = false,
  cancelled = false,
  cancelOk = false,
  ended = false,
  answered = false,
  byeOk = false;
const send = (message) => {
  const bytes = Buffer.from(sip.stringify(message), 'latin1');
  if (secure) socket.write(bytes);
  else socket.send(bytes, store.value.sip_port, '127.0.0.1');
};
function receive(bytes) {
  const response = sip.parse(bytes.toString('latin1'));
  if (response?.headers?.['call-id'] !== id) return;
  console.log('SIP', response.status, response.headers.cseq.method);
  if (response.status === 407 && !challenged) {
    const ack = sip.copyMessage(request, true);
    ack.method = 'ACK';
    ack.headers.cseq.method = 'ACK';
    ack.headers.to = response.headers.to;
    ack.content = '';
    delete ack.headers['content-type'];
    send(ack);
    challenged = true;
    request.headers.via[0].params.branch = 'z9hG4bK-' + crypto.randomUUID();
    request.headers.cseq.seq++;
    digest.signRequest({}, request, response, {
      user: from,
      password: store.value.users[from].password,
    });
    send(request);
  } else if (response.headers.cseq.method === 'BYE' && response.status === 200) byeOk = true;
  else if (response.headers.cseq.method === 'CANCEL' && response.status === 200) cancelOk = true;
  else if (
    response.headers.cseq.method === 'INVITE' &&
    response.status >= 200 &&
    response.status !== 407
  ) {
    ended = true;
    const ack = sip.copyMessage(request, true);
    ack.method = 'ACK';
    ack.headers.cseq.method = 'ACK';
    ack.headers.to = response.headers.to;
    ack.content = '';
    delete ack.headers['content-type'];
    if (response.status === 200) {
      ack.uri = response.headers.contact?.[0]?.uri || request.uri;
      ack.headers.via[0].params.branch = 'z9hG4bK-' + crypto.randomUUID();
      send(ack);
      if (!answered) {
        answered = true;
        const bye = sip.copyMessage(ack, true);
        bye.method = 'BYE';
        bye.headers.cseq = { seq: request.headers.cseq.seq + 1, method: 'BYE' };
        bye.headers.via[0].params.branch = 'z9hG4bK-' + crypto.randomUUID();
        setTimeout(() => send(bye), 1000);
      }
    } else send(ack);
    // This fixture has no media source. If answered, acknowledge and end cleanly.
    console.log('FINAL', response.status);
  }
}
if (secure) {
  let pending = '';
  socket.on('data', (bytes) => {
    pending += bytes.toString('latin1');
    if (pending.length > 131072) throw Error('Oversized SIP test response');
    while (pending) {
      if (pending.startsWith('\r\n')) {
        pending = pending.slice(2);
        continue;
      }
      const end = pending.indexOf('\r\n\r\n');
      if (end < 0) return;
      const length = Number(/^Content-Length:\s*(\d+)/im.exec(pending.slice(0, end))?.[1] || 0);
      const size = end + 4 + length;
      if (pending.length < size) return;
      receive(Buffer.from(pending.slice(0, size), 'latin1'));
      pending = pending.slice(size);
    }
  });
} else socket.on('message', receive);
function begin() {
  const srtp = crypto.randomBytes(30).toString('base64');
  const security = `a=ice-ufrag:pushcheck\r\na=ice-pwd:${crypto.randomBytes(20).toString('hex')}\r\na=crypto:1 AES_CM_128_HMAC_SHA1_80 inline:${srtp}\r\n`;
  request = {
    method: 'INVITE',
    uri: `sip:${to}@${store.value.host}`,
    content:
      'v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\ns=Push test\r\nc=IN IP4 127.0.0.1\r\nt=0 0\r\nm=audio 44000 RTP/AVP 0\r\na=rtpmap:0 PCMU/8000\r\nm=video 44002 RTP/AVP 96\r\na=rtpmap:96 VP8/90000\r\n',
    headers: {
      from: { uri: `sip:${from}@${store.value.host}`, params: { tag: crypto.randomUUID() } },
      to: { uri: `sip:${to}@${store.value.host}`, params: {} },
      via: [
        {
          protocol: secure ? 'TLS' : 'UDP',
          host: '127.0.0.1',
          port: socket.address().port,
          params: { branch: 'z9hG4bK-' + crypto.randomUUID(), rport: null },
        },
      ],
      contact: [{ uri: `sip:${from}@127.0.0.1:${socket.address().port}` }],
      cseq: { seq: 1, method: 'INVITE' },
      'call-id': id,
      'max-forwards': 70,
      'content-type': 'application/sdp',
    },
  };
  if (secure)
    request.content = request.content
      .replaceAll('RTP/AVP', 'RTP/SAVP')
      .replace('a=rtpmap:0 PCMU/8000\r\n', 'a=rtpmap:0 PCMU/8000\r\n' + security)
      .replace(
        'a=rtpmap:96 VP8/90000\r\n',
        'a=rtpmap:96 H264/90000\r\na=fmtp:96 packetization-mode=1;profile-level-id=42e01f\r\n' +
          security,
      );
  console.log('CALL_ID', id);
  send(request);
  setTimeout(() => {
    if (ended) return;
    cancelled = true;
    const cancel = sip.copyMessage(request, true);
    cancel.method = 'CANCEL';
    cancel.headers.cseq.method = 'CANCEL';
    cancel.content = '';
    delete cancel.headers['content-type'];
    send(cancel);
  }, 20000);
  setTimeout(() => {
    console.log('RESULT', JSON.stringify({ cancelled, cancelOk, ended, answered, byeOk }));
    if (secure) socket.end();
    else socket.close();
    process.exitCode = (cancelled && cancelOk && ended) || (answered && byeOk) ? 0 : 1;
  }, 25000);
}
if (secure) socket.once('secureConnect', begin);
else socket.bind(0, '127.0.0.1', begin);
