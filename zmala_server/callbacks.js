'use strict';
// Persist callback lifecycle separately from configuration; SIP delivery and email reminders share these records.
const { readJson, writeJson } = require('./json-file');
const { SnapshotFile } = require('./snapshot-file');
const { retainHistory } = require('./history');
const path = require('node:path'),
  crypto = require('node:crypto');
const { registrationOnline } = require('./registrations');
const { CallbackMailer } = require('./callback-mailer');
const { CallbackEmails } = require('./callback-emails');
class Callbacks {
  /** @param {import('./types/contracts').StoreInstance} store @param {Pick<import('./types/contracts').SipInstance, 'registrations' | 'notifyCallback'>} sipServer @param {import('./types/contracts').Mailer} [mailer] */
  constructor(store, sipServer, mailer = new CallbackMailer(store)) {
    this.store = store;
    this.sip = sipServer;
    this.file = path.join(store.dir, 'callbacks.json');
    /** @type {import('./types/contracts').CallbackRecord[]} */
    this.requests = readJson(this.file, []);
    /** @type {Set<string>} */
    this.sending = new Set();
    /** @type {Map<string, number>} */
    this.retry = new Map();
    this.email = new CallbackEmails(this, mailer);
    // Recover consistently if shutdown interrupted the settings/request snapshot writes.
    let migrated = false;
    for (const request of this.requests)
      if (request.status === 'pending') {
        const deadlines = this.deadlines(Date.parse(request.created_at));
        if (
          request.email_due_at !== deadlines.email_due_at ||
          request.expires_at !== deadlines.expires_at
        ) {
          Object.assign(request, deadlines);
          migrated = true;
        }
      }
    if (migrated) this.save();
    this.reconcile();
  }
  save() {
    if (this.persistence) return this.persistence.write(JSON.stringify(this.requests, null, 2));
    writeJson(this.file, this.requests);
  }
  enableAsyncPersistence() {
    this.persistence = new SnapshotFile(this.file);
  }
  async flush() {
    await this.persistence?.flush();
  }
  // @llr SLLR045
  /** @param {number} created */
  deadlines(created) {
    const settings = this.store.value.callback_settings;
    return {
      email_due_at: new Date(created + settings.email_after_hours * 3600000).toISOString(),
      expires_at: new Date(created + settings.remove_after_hours * 3600000).toISOString(),
    };
  }
  reconcile() {
    let changed = false;
    this.requests = this.requests.filter((request) => {
      if (
        request.status === 'expired' ||
        (request.status === 'pending' && Date.parse(request.expires_at) <= Date.now())
      ) {
        this.retry.delete(request.id);
        this.email.forget(request.id);
        changed = true;
        return false;
      }
      return true;
    });
    for (const r of this.requests)
      if (r.status === 'pending') {
        if (!this.store.terminal(r.from) || !this.store.permitted(r.from, r.to)) {
          r.status = 'cancelled';
          changed = true;
        }
        if (r.status !== 'pending') r.finished_at = new Date().toISOString();
      }
    const pending = new Set(
      this.requests.filter((request) => request.status === 'pending').map((request) => request.id),
    );
    for (const retries of [this.retry, this.email.retry])
      for (const id of retries.keys()) if (!pending.has(id)) retries.delete(id);
    if (changed) this.save();
  }
  /** @param {string} id */
  online(id) {
    return registrationOnline(this.sip.registrations.get(id));
  }
  // @llr SLLR043
  /** @param {string} from @param {unknown} to */
  create(from, to) {
    this.store.requireTerminal(from);
    this.reconcile();
    if (typeof to !== 'string' || !this.store.permitted(from, to)) {
      const e = Object.assign(Error('Callback request is not permitted.'), { status: 403 });
      throw e;
    }
    let request = this.requests.find(
      (r) => r.status === 'pending' && r.from === from && r.to === to,
    );
    if (!request) {
      if (this.requests.filter((r) => r.status === 'pending').length >= 400)
        throw Error('Too many pending callback requests.');
      const now = Date.now();
      request = {
        id: crypto.randomUUID(),
        from,
        to,
        status: 'pending',
        created_at: new Date(now).toISOString(),
        ...this.deadlines(now),
        notified_at: null,
        email_sent_to: [],
        emailed_at: null,
        email_error: null,
      };
      this.requests.push(request);
      this.requests = retainHistory(this.requests, (r) => r.status === 'pending');
      this.save();
    }
    setImmediate(() => this.deliver(to));
    return this.view(request);
  }
  /** @param {import('./types/contracts').CallbackRecord} r @param {boolean} [admin] @returns {import('./types/contracts').CallbackView} */
  view(r, admin = false) {
    const { email_sent_to, email_error, ...fields } = r;
    return {
      ...fields,
      ...(admin ? { email_sent_to: email_sent_to || [], email_error: email_error || null } : {}),
      from_name: this.store.value.users[r.from]?.name || r.from,
      to_name: this.store.value.users[r.to]?.name || r.to,
      ready: r.status === 'pending' && this.online(r.from) && this.online(r.to),
    };
  }
  // @llr SLLR048
  /** @param {string} [account] */
  list(account) {
    this.reconcile();
    return this.requests
      .filter(
        (r) =>
          account === undefined ||
          (r.status === 'pending' && (r.from === account || r.to === account)),
      )
      .slice()
      .reverse()
      .map((r) => this.view(r, account === undefined));
  }
  // @llr SLLR044
  /** @param {string} id @param {string} [account] */
  cancel(id, account) {
    this.reconcile();
    const r = this.requests.find((r) => r.id === id);
    if (!r || (account !== undefined && r.from !== account)) {
      const e = Object.assign(Error('Callback request not found.'), { status: 404 });
      throw e;
    }
    if (r.status === 'pending') {
      r.status = 'cancelled';
      r.finished_at = new Date().toISOString();
      this.save();
    }
  }
  // @llr SLLR044
  /** @param {string} a @param {string} b */
  connected(a, b) {
    this.reconcile();
    let changed = false;
    for (const r of this.requests)
      if (
        r.status === 'pending' &&
        ((r.from === a && r.to === b) || (r.from === b && r.to === a))
      ) {
        r.status = 'completed';
        r.finished_at = new Date().toISOString();
        changed = true;
      }
    if (changed) this.save();
  }
  /** @param {string} oldId @param {string} newId */
  rename(oldId, newId) {
    let changed = false;
    for (const r of this.requests)
      for (const field of /** @type {const} */ (['from', 'to']))
        if (r[field] === oldId) {
          r[field] = newId;
          changed = true;
        }
    if (changed) this.save();
  }
  // @llr SLLR047
  /** @param {string} [account] */
  deliver(account) {
    this.reconcile();
    this.email.deliver();
    for (const r of this.requests) {
      if (
        r.status !== 'pending' ||
        r.notified_at ||
        (account !== undefined && r.to !== account) ||
        !this.online(r.to) ||
        this.store.terminal(r.to) ||
        this.sending.has(r.id) ||
        (this.retry.get(r.id) || 0) > Date.now()
      )
        continue;
      this.sending.add(r.id);
      this.retry.set(r.id, Date.now() + 60000);
      const text = `ZmalaCall: ${this.store.value.users[r.from].name} would like you to call back.\nCall sip:${r.from}@${this.store.value.host}\nRequest expires at ${r.expires_at}.`;
      Promise.resolve()
        .then(async () => {
          await this.flush();
          if (
            !this.requests.includes(r) ||
            r.status !== 'pending' ||
            Date.parse(r.expires_at) <= Date.now() ||
            !this.store.permitted(r.from, r.to)
          )
            return false;
          return this.sip.notifyCallback(r, text);
        })
        .then(async (ok) => {
          if (
            ok &&
            this.requests.includes(r) &&
            r.status === 'pending' &&
            Date.parse(r.expires_at) > Date.now()
          ) {
            r.notified_at = new Date().toISOString();
            this.save();
            await this.flush();
          }
        })
        .catch((e) => console.error('Callback notification failed:', e.message))
        .finally(() => this.sending.delete(r.id));
    }
  }
  /** @param {import('./types/contracts').JsonObject} update */
  updateSettings(update) {
    this.store.setCallbackSettings(update);
    for (const request of this.requests)
      if (request.status === 'pending') {
        Object.assign(request, this.deadlines(Date.parse(request.created_at)));
      }
    this.save();
    this.reconcile();
    this.deliver();
  }
}
module.exports = { Callbacks };
