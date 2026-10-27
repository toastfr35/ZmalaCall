'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

// @llr LLR-SRV-APP-005
/** FCM HTTP v1 sender. The service-account key stays on the server outside application state. */
class FcmSender {
  constructor(file = process.env.ZMALA_FCM_CREDENTIALS) {
    /** @type {{project_id: string, client_email: string, private_key: string} | null} */
    this.credentials = file ? JSON.parse(fs.readFileSync(file, 'utf8')) : null;
    this.access = '';
    this.expires = 0;
    /** @type {Promise<string> | null} */
    this.authorizationPending = null;
  }
  get enabled() {
    return !!this.credentials;
  }
  async authorization() {
    if (this.access && this.expires > Date.now() + 60000) return this.access;
    // Concurrent incoming calls share one bounded OAuth request. Clear only
    // this promise: a rejected refresh must not strand a later retry.
    const pending = this.authorizationPending || this.refreshAuthorization();
    this.authorizationPending = pending;
    try {
      return await pending;
    } finally {
      if (this.authorizationPending === pending) this.authorizationPending = null;
    }
  }
  async refreshAuthorization() {
    if (!this.credentials) throw Error('Push sender is not configured.');
    const now = Math.floor(Date.now() / 1000);
    const encode = (/** @type {unknown} */ value) =>
      Buffer.from(JSON.stringify(value)).toString('base64url');
    const assertion =
      encode({ alg: 'RS256', typ: 'JWT' }) +
      '.' +
      encode({
        iss: this.credentials.client_email,
        scope: 'https://www.googleapis.com/auth/firebase.messaging',
        aud: 'https://oauth2.googleapis.com/token',
        iat: now,
        exp: now + 3600,
      });
    const signature = crypto
      .sign('RSA-SHA256', Buffer.from(assertion), this.credentials.private_key)
      .toString('base64url');
    const response = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST',
      signal: AbortSignal.timeout(8000),
      body: new URLSearchParams({
        grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        assertion: assertion + '.' + signature,
      }),
    });
    if (!response.ok) throw Error('Firebase sender authorization failed.');
    const result = await response.json();
    const expires = Number(result?.expires_in);
    if (
      typeof result?.access_token !== 'string' ||
      !result.access_token ||
      !Number.isFinite(expires) ||
      expires <= 0
    )
      throw Error('Firebase sender authorization failed.');
    this.access = result.access_token;
    this.expires = Date.now() + Math.min(3600, expires) * 1000;
    return this.access;
  }
  /** @param {string} token @param {Record<string,string>} data */
  async send(token, data) {
    const authorization = await this.authorization();
    const response = await fetch(
      `https://fcm.googleapis.com/v1/projects/${encodeURIComponent(this.credentials?.project_id || '')}/messages:send`,
      {
        method: 'POST',
        signal: AbortSignal.timeout(8000),
        headers: { Authorization: 'Bearer ' + authorization, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: { token, data, android: { priority: 'high', ttl: '60s' } },
        }),
      },
    );
    // A late failure for an old access token must not clear a newer refresh.
    if (response.status === 401 && this.access === authorization) {
      this.access = '';
      this.expires = 0;
    }
    if (!response.ok) {
      const result = await response.json().catch(() => ({}));
      const invalid = result.error?.details?.some(
        (/** @type {{errorCode?: string}} */ d) => d.errorCode === 'UNREGISTERED',
      );
      throw Object.assign(Error('Firebase delivery failed.'), { invalid: !!invalid });
    }
  }
}

// @llr LLR-SRV-APP-005
/** Push registrations are separate from backups and scoped to the current enrollment identity. */
class AppPush {
  /** @param {import('./types/contracts').StoreInstance} store */
  constructor(store, sender = new FcmSender()) {
    this.store = store;
    this.sender = sender;
    this.file = store.dir ? path.join(store.dir, 'app-push.json') : null;
    /** @type {Record<string, {device: string, token: string, updated: number}>} */
    this.tokens =
      this.file && fs.existsSync(this.file) ? JSON.parse(fs.readFileSync(this.file, 'utf8')) : {};
  }
  save() {
    if (!this.file) return;
    fs.writeFileSync(this.file + '.tmp', JSON.stringify(this.tokens), { mode: 0o600 });
    fs.renameSync(this.file + '.tmp', this.file);
  }
  /** @param {string} id @param {unknown} token */
  register(id, token) {
    const account = this.store.enrolledAccount(id);
    if (!account || account.type !== 'app') throw Error('An app account is required.');
    if (token === null) delete this.tokens[id];
    else {
      if (typeof token !== 'string' || !/^[A-Za-z0-9_:-]{20,4096}$/.test(token))
        throw Error('Invalid push token.');
      // A fresh Android installation/token can belong to only one enrolled account.
      for (const [other, registration] of Object.entries(this.tokens))
        if (registration.token === token) delete this.tokens[other];
      this.tokens[id] = { device: account.device_id, token, updated: Date.now() };
    }
    this.save();
  }
  /** @param {string} id */
  available(id) {
    const account = this.store.enrolledAccount?.(id),
      token = this.tokens[id];
    return (
      this.sender.enabled &&
      account?.type === 'app' &&
      !!token &&
      token.device === account.device_id &&
      token.updated > Date.now() - 30 * 86400000
    );
  }
  // @llr LLR-SRV-CALLBACK-025
  /** @param {string} id @param {string} callId @param {string} caller @param {'ring'|'cancel'|'callback'} event @param {number} expires */
  async notify(id, callId, caller, event, expires) {
    if (!this.available(id)) throw Error('Push destination unavailable.');
    const account = this.store.enrolledAccount(id),
      registration = this.tokens[id];
    if (!account || account.type !== 'app') throw Error('Push destination revoked.');
    const data = {
      event,
      call_id: callId,
      caller,
      expires: String(expires),
      device_id: account.device_id,
    };
    const proof = crypto
      .createHmac('sha256', account.device_token)
      .update(JSON.stringify([event, callId, caller, data.expires, account.device_id]))
      .digest('hex');
    try {
      await this.sender.send(registration.token, { ...data, proof });
    } catch (error) {
      if (
        error &&
        typeof error === 'object' &&
        'invalid' in error &&
        error.invalid &&
        this.tokens[id] === registration
      ) {
        delete this.tokens[id];
        this.save();
      }
      throw error;
    }
  }
}
module.exports = { FcmSender, AppPush };
