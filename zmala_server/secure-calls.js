// @ts-check
'use strict';
const fs = require('node:fs');
const crypto = require('node:crypto');
const { MediaRelay } = require('./media');

/** Deployment policy is separate from account backups. Never send the TURN
 * signing secret to a terminal or fall back to plaintext after a TLS failure.
 */
// @llr LLR-SRV-MEDIA-015
class SecureCalls {
  /** @param {Record<string, any>} value */
  constructor(value) {
    /** @param {string} name */
    const host = (name) => {
      const v = value[name];
      if (typeof v !== 'string' || !/^[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}$/.test(v))
        throw Error(`Invalid secure-call ${name}`);
      return v;
    };
    this.sipHost = host('sip_host');
    this.turnHost = host('turn_host');
    this.realm = host('turn_realm');
    /** @param {string} name @param {number} fallback */
    const port = (name, fallback) => {
      const result = value[name] ?? fallback;
      if (!Number.isInteger(result) || result < 1 || result > 65535)
        throw Error(`Invalid secure-call ${name}`);
      return result;
    };
    this.listenPort = port('sip_listen_port', 5061);
    this.sipPort = port('sip_public_port', 443);
    this.turnPort = port('turn_public_port', 443);
    const url = new URL(value.https_url);
    if (
      url.protocol !== 'https:' ||
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      url.pathname !== '/'
    )
      throw Error('Secure calls require an HTTPS origin');
    this.httpsUrl = url.origin;
    this.tls = {
      cert: fs.readFileSync(value.sip_cert),
      key: fs.readFileSync(value.sip_key),
      minVersion: 'TLSv1.2',
    };
    this.secret = fs.readFileSync(value.turn_secret_file, 'utf8').trim();
    if (this.secret.length < 32)
      throw Error('TURN signing secret must contain at least 32 characters');
  }

  /** @param {string} identity @param {number} [now] */
  configuration(identity, now = Date.now()) {
    // Stable for one hour: refresh at idle without restarting the core on every
    // poll. Eight hours covers the server's four-hour maximum call plus renewal.
    const expires = Math.floor(now / 3600000) * 3600 + 8 * 3600;
    const username = `${expires}:${identity}`;
    return {
      mode: 'tls-relay',
      turn_server: `${this.turnHost}:${this.turnPort}`,
      turn_realm: this.realm,
      turn_username: username,
      turn_password: crypto.createHmac('sha1', this.secret).update(username).digest('base64'),
      expires,
    };
  }

  listener() {
    return {
      publicAddress: this.sipHost,
      port: this.sipPort,
      udp: false,
      tcp: false,
      tls_port: this.listenPort,
      tls: this.tls,
    };
  }
  proxy() {
    return `sip:${this.sipHost}:${this.sipPort};transport=tls`;
  }
}

/** @returns {SecureCalls | null} */
function loadSecureCalls() {
  const file = process.env.ZMALA_SECURE_CALLS_FILE;
  return file ? new SecureCalls(JSON.parse(fs.readFileSync(file, 'utf8'))) : null;
}

// @llr LLR-SRV-MEDIA-015
/** Retain the existing transaction/session lifecycle without allocating UDP
 * sockets. ICE authenticates the selected path; SRTP authenticates its media.
 * Reject a plaintext or incomplete active section before forwarding its SDP. */
class IceMedia extends MediaRelay {
  /** @param {string} id @param {string} sdp @param {number} side @param {string} peer
   * @param {import('./types/contracts').MediaUpdate} [update] */
  async rewrite(id, sdp, side, peer, update) {
    if (typeof sdp !== 'string' || !sdp.startsWith('v=0\r\n') || sdp.length > 65536)
      throw Error('Invalid secure SDP');
    const sections = sdp.trim().split(/\r?\nm=/);
    const session = sections.shift() || '';
    if (!sections.length) throw Error('Missing secure media');
    for (const section of sections) {
      const [kind, port, protocol] = section.split(/\s+/, 3);
      if (!/^\d+$/.test(port) || Number(port) > 65535) throw Error('Invalid secure media port');
      if (Number(port) === 0) continue;
      if (!['audio', 'video'].includes(kind) || !/^RTP\/SAVPF?$/.test(protocol))
        throw Error('Secure calls require SRTP audio/video');
      const attributes = session + '\n' + section;
      const suites = new Map([
        ['AES_CM_128_HMAC_SHA1_80', 30],
        ['AES_CM_128_HMAC_SHA1_32', 30],
        ['AEAD_AES_128_GCM', 28],
        ['AEAD_AES_256_GCM', 44],
      ]);
      const cryptoValid = attributes.split(/\r?\n/).some((line) => {
        const match = /^a=crypto:\d+ (\S+) inline:([A-Za-z0-9+/]+={0,2})$/.exec(line);
        if (!match) return false;
        const key = Buffer.from(match[2], 'base64');
        return key.length === suites.get(match[1]) && key.toString('base64') === match[2];
      });
      if (
        !/^a=ice-ufrag:\S{4,256}\r?$/m.test(attributes) ||
        !/^a=ice-pwd:\S{22,256}\r?$/m.test(attributes) ||
        !cryptoValid
      )
        throw Error('Secure calls require ICE credentials and SRTP keys');
    }
    return sdp;
  }
}
module.exports = { SecureCalls, loadSecureCalls, IceMedia };
