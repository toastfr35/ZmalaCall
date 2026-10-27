'use strict';
const crypto = require('node:crypto');

// @llr LLR-SRV-CALLBACK-025
/** Durable, bounded state-change hints; Android fetches current authorized state. */
class CallbackPush {
  /** @param {import('./types/contracts').CallbackInstance} owner @param {import('./types/contracts').CallbackPushTransport} [push] */
  constructor(owner, push) {
    this.owner = owner;
    this.push = push;
    /** @type {Set<string>} */
    this.sending = new Set();
    /** @type {Map<string,number>} */
    this.retry = new Map();
  }
  /** @param {import('./types/contracts').CallbackRecord} request */
  key(request) {
    const account = this.owner.store.enrolledAccount(request.to);
    if (account?.type !== 'app') return null;
    return crypto
      .createHash('sha256')
      .update(
        JSON.stringify([
          request.status,
          request.expires_at,
          account.device_id,
          account.device_token,
        ]),
      )
      .digest('hex');
  }
  deliver() {
    if (!this.push || this.owner.paused) return;
    const requests = this.owner.requests;
    const ids = new Set(requests.map((r) => r.id));
    for (const id of this.retry.keys()) if (!ids.has(id)) this.retry.delete(id);
    for (const request of requests) {
      const key = this.key(request);
      if (
        !key ||
        request.push_notified_key === key ||
        this.sending.has(request.id) ||
        (this.retry.get(request.id) || 0) > Date.now() ||
        !this.push.available(request.to)
      )
        continue;
      if (request.status === 'pending') {
        if (
          Date.parse(request.expires_at) <= Date.now() ||
          !this.owner.store.permitted(request.from, request.to)
        )
          continue;
      } else if (!request.push_notified_key) continue;
      this.sending.add(request.id);
      this.retry.set(request.id, Date.now() + 60000);
      Promise.resolve()
        .then(async () => {
          await this.owner.flush();
          if (
            this.owner.paused ||
            !this.owner.requests.includes(request) ||
            this.key(request) !== key
          )
            return;
          if (
            request.status === 'pending' &&
            (Date.parse(request.expires_at) <= Date.now() ||
              !this.owner.store.permitted(request.from, request.to))
          )
            return;
          await this.push?.notify(
            request.to,
            request.id,
            request.from,
            'callback',
            Date.now() + 60000,
          );
          // Retain the sent state even if cancellation raced delivery. The next
          // pass then sends a fresh hint, rather than leaving an old alert visible.
          if (this.owner.requests.includes(request)) {
            request.push_notified_key = key;
            this.owner.save();
            await this.owner.flush();
            this.retry.delete(request.id);
          }
        })
        .catch(() => {
          console.error('Callback push delivery failed; retrying later.');
        })
        .finally(() => {
          this.sending.delete(request.id);
          // Another state may have arrived during the asynchronous send.
          if (request.push_notified_key && this.key(request) !== request.push_notified_key)
            this.deliver();
        });
    }
  }
}
module.exports = { CallbackPush };
