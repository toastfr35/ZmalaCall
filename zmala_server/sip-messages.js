'use strict';
// Deliver authenticated SIP notifications using the recipient registration and Digest challenge flow.
const sip = require('sip');
const proxy = require('sip/proxy');
const crypto = require('node:crypto');
const { DigestAuth } = require('./auth');
const { registrationOnline } = require('./registrations');
/** @param {string} uri */
const username = (uri) => sip.parseUri(uri)?.user;
/** Authenticated text notifications and deferred callback delivery, sharing the SIP transport. */
class SipMessages {
  /** @param {import('./types/contracts').StoreInstance} store */
  constructor(store) {
    this.store = store;
    this.auth = new DigestAuth(store.value.host);
    /** @type {Map<string, import('./types/contracts').SipRegistration>} */
    this.registrations = new Map();
  }
  /** @param {import('sip').Message} rq @param {number} status @param {string} reason */
  reply(rq, status, reason) {
    if (rq.method !== 'ACK') proxy.send(sip.makeResponse(rq, status, reason));
  }
  /** Subclasses may retain bounded events. @param {string} message */
  log(message) {
    console.log(message);
  }
  /** @param {import('./types/contracts').CallbackRecord} request @param {string} text */
  notifyCallback(request, text) {
    const target = this.registrations.get(request.to),
      v = this.store.value;
    if (!registrationOnline(target) || !this.store.permitted(request.from, request.to))
      return Promise.resolve(false);
    const message = {
      method: 'MESSAGE',
      uri: target.contact.uri,
      headers: {
        to: { uri: `sip:${request.to}@${v.host}` },
        from: {
          uri: `sip:${request.from}@${v.host}`,
          params: { tag: crypto.randomBytes(8).toString('hex') },
        },
        via: [],
        route: [{ uri: sip.encodeFlowUri(target.remote) }],
        cseq: { seq: 1, method: 'MESSAGE' },
        'call-id': 'callback-' + crypto.randomUUID(),
        'max-forwards': 70,
        'content-type': 'text/plain; charset=utf-8',
      },
      content: Buffer.from(text, 'utf8').toString('latin1'),
    };
    return new Promise((resolve) => {
      const timer = setTimeout(() => resolve(false), 10000);
      try {
        sip.send(message, (rs) => {
          if (rs.status >= 200) {
            clearTimeout(timer);
            resolve(rs.status < 300);
          }
        });
      } catch (e) {
        clearTimeout(timer);
        resolve(false);
        console.error(
          'Callback SIP message failed:',
          e instanceof Error ? e.message : 'Unknown error',
        );
      }
    });
  }
  // @llr SLLR053
  /** @param {import('sip').ValidRequest} rq */
  message(rq) {
    const v = this.store.value,
      user = this.auth.verify(rq, v.users, true);
    if (!user) {
      proxy.send(this.auth.challenge(rq, true));
      return;
    }
    const from = username(rq.headers.from.uri),
      to = username(rq.headers.to.uri);
    if (
      !to ||
      from !== user ||
      v.users[user].type !== 'linphone' ||
      !this.store.terminal(to) ||
      !this.store.permitted(from, to)
    ) {
      this.reply(rq, 403, 'Messaging Not Permitted');
      return;
    }
    // @llr SLLR054
    const type = (rq.headers['content-type'] || '').split(';')[0].trim().toLowerCase();
    if (!['text/plain', 'message/cpim'].includes(type)) {
      this.reply(rq, 415, 'Unsupported Media Type');
      return;
    }
    if (typeof rq.content !== 'string' || !rq.content.trim()) {
      this.reply(rq, 400, 'Empty Message');
      return;
    }
    if (rq.content.length > 16384) {
      this.reply(rq, 413, 'Message Too Large');
      return;
    }
    const id = rq.headers['call-id'],
      seq = rq.headers.cseq?.seq;
    if (
      typeof id !== 'string' ||
      !id ||
      id.length > 200 ||
      typeof seq !== 'number' ||
      !Number.isSafeInteger(seq) ||
      seq < 1
    ) {
      this.reply(rq, 400, 'Invalid Message Identity');
      return;
    }
    const target = this.registrations.get(to);
    if (!registrationOnline(target)) {
      this.reply(rq, 480, 'Temporarily Unavailable');
      return;
    }
    const hops = Number(rq.headers['max-forwards'] ?? 70);
    if (!Number.isInteger(hops) || hops <= 0) {
      this.reply(rq, 483, 'Too Many Hops');
      return;
    }
    const forward = sip.copyMessage(rq, true),
      messageId = `${id}:${seq}`;
    forward.uri = target.contact.uri;
    forward.headers.route = [{ uri: sip.encodeFlowUri(target.remote) }];
    forward.headers['max-forwards'] = hops - 1;
    delete forward.headers['proxy-authorization'];
    delete forward.headers.authorization;
    forward.headers['x-zmala-message-id'] = messageId;
    const terminal = this.store.terminalAccount(to);
    if (!terminal) {
      this.reply(rq, 403, 'Messaging Not Permitted');
      return;
    }
    // @llr SLLR055
    forward.headers['x-family-auth'] = crypto
      .createHmac('sha256', terminal.device_token)
      .update(`message:${messageId}:${from}`)
      .digest('hex');
    proxy.send(forward, (rs) => {
      const response = sip.copyMessage(rs, true);
      response.headers.via?.shift();
      proxy.send(response);
    });
    this.log(`${from} sent a text notification to ${to}`);
  }
}
module.exports = { SipMessages };
