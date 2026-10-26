'use strict';
const { AppPush } = require('./app-push');
const { samePeer } = require('./sip-guards');

// @llr LLR-SRV-APP-005
/** Bounded authenticated INVITEs awaiting an app's fresh registration. No media is allocated yet. */
class AppCalls {
  /** @param {import('./types/contracts').SipInstance} server */
  constructor(server) {
    this.server = server;
    this.push = new AppPush(server.store);
    /** @type {Map<string, {rq: import('sip').ValidRequest, remote: import('sip').Remote, from: string, to: string, expires: number, identity: string, timer: NodeJS.Timeout, resolve: (ready: boolean) => void}>} */
    this.waiting = new Map();
  }
  /** @param {string} from @param {string} to */
  identity(from, to) {
    return JSON.stringify([
      this.server.store.value.users[from]?.password,
      this.server.store.value.users[to]?.device_id,
      this.server.store.value.users[to]?.device_token,
    ]);
  }
  /** @param {string} user */
  busy(user) {
    return [...this.waiting.values()].some((p) => p.from === user || p.to === user);
  }
  /** @param {import('sip').ValidRequest} rq @param {import('sip').Remote} remote @param {string} from @param {string} to */
  wait(rq, remote, from, to) {
    const id = rq.headers['call-id'];
    if (this.waiting.has(id)) {
      this.server.reply(rq, 482, 'Loop Detected');
      return Promise.resolve(false);
    }
    const expires =
      Date.now() + Math.min(60, Math.max(15, this.server.store.ringTimeout(to))) * 1000;
    return new Promise((resolve) => {
      const timer = setTimeout(() => this.finish(id, 480), expires - Date.now());
      timer.unref();
      const entry = {
        rq,
        remote,
        from,
        to,
        expires,
        identity: this.identity(from, to),
        timer,
        resolve,
      };
      this.waiting.set(id, entry);
      this.server.reply(rq, 100, 'Trying');
      this.push
        .notify(to, id, from, 'ring', expires)
        .then(() => {
          if (this.waiting.get(id) === entry) this.server.reply(rq, 180, 'Ringing');
        })
        .catch(() => {
          if (this.waiting.get(id) === entry) this.finish(id, 480);
        });
    });
  }
  /** @param {string} user */
  registered(user) {
    for (const [id, entry] of this.waiting) {
      if (entry.to !== user) continue;
      const valid =
        entry.expires > Date.now() &&
        !this.server.maintenance &&
        entry.identity === this.identity(entry.from, entry.to) &&
        this.server.store.permitted(entry.from, entry.to);
      if (!valid) {
        this.finish(id, 480);
        continue;
      }
      clearTimeout(entry.timer);
      this.waiting.delete(id);
      entry.resolve(true);
    }
  }
  /** @param {string} id @param {number} status @param {boolean} deferReply */
  finish(id, status, deferReply = false) {
    const entry = this.waiting.get(id);
    if (!entry) return;
    this.waiting.delete(id);
    clearTimeout(entry.timer);
    const reply = () =>
      this.server.reply(
        entry.rq,
        status,
        status === 487
          ? 'Request Terminated'
          : status === 603
            ? 'Decline'
            : 'Temporarily Unavailable',
      );
    // Let the proxy acknowledge CANCEL before the final INVITE response removes its context.
    if (deferReply) setImmediate(reply);
    else reply();
    entry.resolve(false);
    this.push.notify(entry.to, id, entry.from, 'cancel', Date.now() + 60000).catch(() => {});
  }
  /** @param {import('sip').ValidRequest} rq @param {import('sip').Remote} remote */
  cancel(rq, remote) {
    const entry = this.waiting.get(rq.headers['call-id']);
    if (!entry) return null;
    if (
      !samePeer(remote, entry.remote) ||
      rq.headers.from.params?.tag !== entry.rq.headers.from.params?.tag
    )
      return 403;
    if (
      rq.headers.cseq.seq !== entry.rq.headers.cseq.seq ||
      rq.headers.via?.[0]?.params?.branch !== entry.rq.headers.via?.[0]?.params?.branch
    )
      return 481;
    this.finish(rq.headers['call-id'], 487, true);
    return 0;
  }
  /** @param {string} user @param {unknown} id */
  decline(user, id) {
    if (typeof id !== 'string') throw Error('Invalid call.');
    const entry = this.waiting.get(id);
    if (entry?.to === user) this.finish(id, 603);
  }
  close() {
    for (const id of this.waiting.keys()) this.finish(id, 480);
  }
}
module.exports = { AppCalls };
