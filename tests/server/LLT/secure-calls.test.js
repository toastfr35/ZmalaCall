// @test S-LLT-039
// @requirements LLR-SRV-MEDIA-015
// @environment portable
// @plan Use temporary certificate/secret files and a fixed clock. Check TLS-only listeners with default 443 and configured 5061/5349 public ports, signed expiring per-account credentials, rotation, invalid deployment rejection and unchanged encrypted ICE SDP. Reject plaintext, missing keys/ICE, unsupported sections and invalid ports; ensure no UDP sockets are allocated.
// @pass Every assertion passes. File fixtures do not qualify TLS handshakes; the network HLT performs those checks.
'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { SecureCalls, IceMedia, loadSecureCalls } = require('../../../zmala_server/secure-calls');

test('secure deployment validates endpoints and issues stable bounded credentials', (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'zmala-secure-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const file = path.join(dir, 'secret');
  fs.writeFileSync(file, 'a'.repeat(64));
  const value = {
    sip_host: 'sip.example.org',
    turn_host: 'turn.example.org',
    turn_realm: 'example.org',
    https_url: 'https://config.example.org',
    sip_cert: file,
    sip_key: file,
    turn_secret_file: file,
  };
  const policy = new SecureCalls(value);
  const credential = policy.configuration('a', 3600000);
  assert.equal(credential.expires, 32400);
  assert.equal(credential.turn_username, '32400:a');
  assert.equal(
    credential.turn_password,
    crypto.createHmac('sha1', 'a'.repeat(64)).update('32400:a').digest('base64'),
  );
  assert.deepEqual(credential, policy.configuration('a', 3600999));
  assert.notEqual(credential.turn_password, policy.configuration('b', 3600000).turn_password);
  assert.notEqual(credential.turn_password, policy.configuration('a', 7200000).turn_password);
  assert.equal(policy.listener().udp, false);
  assert.equal(policy.listener().tcp, false);
  assert.equal(policy.listener().port, 443);
  assert.equal(policy.listener().tls_port, 5061);
  assert.equal(policy.proxy(), 'sip:sip.example.org:443;transport=tls');
  const sharedIp = new SecureCalls({ ...value, sip_public_port: 5061, turn_public_port: 5349 });
  assert.equal(sharedIp.proxy(), 'sip:sip.example.org:5061;transport=tls');
  assert.equal(sharedIp.listener().port, 5061);
  assert.equal(sharedIp.configuration('a', 3600000).turn_server, 'turn.example.org:5349');
  assert.ok(!JSON.stringify(credential).includes('a'.repeat(64)));
  for (const invalid of [
    { sip_host: 'bad;transport=udp' },
    { turn_host: 'bad/path' },
    { turn_realm: '' },
    { https_url: 'http://host' },
    { https_url: 'https://user:pass@host' },
    { https_url: 'https://host/path' },
    { sip_listen_port: 0 },
    { sip_listen_port: 65536 },
    { sip_listen_port: 1.5 },
    { sip_public_port: 0 },
    { sip_public_port: '5061' },
    { turn_public_port: 65536 },
    { turn_public_port: 1.5 },
  ])
    assert.throws(() => new SecureCalls({ ...value, ...invalid }));
  fs.writeFileSync(file, 'short');
  assert.throws(() => new SecureCalls(value), /signing secret/);
  const previous = process.env.ZMALA_SECURE_CALLS_FILE;
  t.after(() => {
    if (previous === undefined) delete process.env.ZMALA_SECURE_CALLS_FILE;
    else process.env.ZMALA_SECURE_CALLS_FILE = previous;
  });
  process.env.ZMALA_SECURE_CALLS_FILE = '';
  assert.equal(loadSecureCalls(), null);
});

test('ICE media rejects insecure sections and preserves valid SDP without relay sockets', async () => {
  const relay = new IceMedia('192.0.2.1');
  const sdp =
    'v=0\r\na=ice-ufrag:abcd\r\na=ice-pwd:' +
    'x'.repeat(24) +
    '\r\nm=audio 1234 RTP/SAVPF 111\r\na=crypto:1 AES_CM_128_HMAC_SHA1_80 inline:' +
    'a'.repeat(40) +
    '\r\n';
  const update = relay.begin('call');
  assert.equal(await relay.rewrite('call', sdp, 0, '192.0.2.2', update), sdp);
  const gcm = sdp
    .replace('AES_CM_128_HMAC_SHA1_80', 'AEAD_AES_128_GCM')
    .replace('a'.repeat(40), Buffer.alloc(28).toString('base64'));
  assert.equal(await relay.rewrite('call', gcm, 0, '192.0.2.2', update), gcm);
  await assert.rejects(
    relay.rewrite('call', gcm.replace('AEAD_AES_128_GCM', 'AEAD_AES_256_GCM'), 0, '192.0.2.2'),
  );
  relay.commit(update);
  assert.equal(relay.used.size, 0);
  for (const invalid of [
    sdp.replace('SAVPF', 'AVPF'),
    sdp.replace('ice-pwd', 'wrong'),
    sdp.replace('a=crypto:', 'a=wrong:'),
    sdp.replace('1234', '65536'),
    sdp.replace('audio', 'application'),
    'v=0\r\n',
    'bad',
    sdp + 'm=video 1234 RTP/AVP 96\r\n',
  ])
    await assert.rejects(relay.rewrite('call', invalid, 0, '192.0.2.2'));
  assert.equal(
    await relay.rewrite('call', sdp + 'm=video 0 RTP/AVP 96\r\n', 0, '192.0.2.2'),
    sdp + 'm=video 0 RTP/AVP 96\r\n',
  );
  relay.close('call');
  assert.equal(relay.sessions.size, 0);
});
