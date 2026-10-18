'use strict';
/** Independent of SIP delivery: persist each accepted recipient before trying the next.
 * SMTP acceptance is not proof that the message reached the recipient's inbox.
 */
class CallbackEmails {
  /** @param {import('./types/contracts').CallbackInstance} callbacks @param {import('./types/contracts').Mailer} mailer */
  constructor(callbacks, mailer) {
    this.callbacks = callbacks;
    this.mailer = mailer;
    this.sending = new Set();
    this.retry = new Map();
  }
  /** @param {import('./types/contracts').CallbackRecord} request */
  current(request) {
    const service = this.callbacks;
    return (
      service.requests.includes(request) &&
      request.status === 'pending' &&
      Date.parse(request.expires_at) > Date.now() &&
      service.store.permitted(request.from, request.to)
    );
  }
  /** @param {import('./types/contracts').CallbackRecord} request */
  remaining(request) {
    const sent = new Set((request.email_sent_to || []).map((address) => address.toLowerCase()));
    return (this.callbacks.store.value.users[request.to]?.emails || []).filter(
      (address) => !sent.has(address.toLowerCase()),
    );
  }
  // @llr SLLR050
  deliver() {
    if (!this.mailer.enabled()) return;
    for (const request of this.callbacks.requests) {
      if (this.sending.size >= 3) break;
      if (
        !this.current(request) ||
        Date.parse(request.email_due_at) > Date.now() ||
        this.sending.has(request.id) ||
        (this.retry.get(request.id) || 0) > Date.now() ||
        (Date.parse(request.email_retry_at || '') || 0) > Date.now() ||
        !this.remaining(request).length
      )
        continue;
      this.sending.add(request.id);
      this.retry.set(request.id, Date.now() + 60000);
      this.send(request)
        .catch(() => console.error('Could not persist callback email delivery state.'))
        .finally(() => {
          // Long SMTP attempts must not cause an immediate retry at completion.
          if (this.current(request)) this.retry.set(request.id, Date.now() + 60000);
          this.sending.delete(request.id);
        });
    }
  }
  // @llr SLLR049
  /** @param {import('./types/contracts').CallbackRecord} request */
  async send(request) {
    // A queued reminder must survive a restart before any external delivery.
    if (this.callbacks.persistence) await this.callbacks.flush();
    /** @type {string | null} */
    let failure = null;
    for (const address of this.remaining(request)) {
      // Completion, expiry, permission and address edits can occur while awaiting SMTP.
      if (
        !this.current(request) ||
        !this.mailer.enabled() ||
        Date.parse(request.email_due_at) > Date.now()
      )
        break;
      if (!this.remaining(request).includes(address)) continue;
      try {
        const accepted = await this.mailer.sendCallback(request, address);
        if (!this.current(request)) break;
        if (!accepted) throw Error('SMTP rejected the recipient.');
        request.email_sent_to ??= [];
        request.email_sent_to.push(address);
        request.emailed_at = new Date().toISOString();
      } catch (error) {
        if (!this.current(request)) break;
        failure = error instanceof Error ? error.message : 'Email delivery failed.';
        request.email_retry_at = new Date(Date.now() + 60000).toISOString();
      }
      // One rejected mailbox must not prevent reminders reaching the others.
      request.email_error = failure;
      if (!failure) request.email_retry_at = null;
      this.callbacks.save();
      // Persist this recipient before proceeding, even when writes are async.
      await this.callbacks.flush();
    }
  }
  /** @param {string} id */
  forget(id) {
    this.retry.delete(id);
  }
}
module.exports = { CallbackEmails };
