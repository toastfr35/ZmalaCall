'use strict';
// SMTP transport and safe error translation; delivery scheduling belongs to callback-emails.js.
const crypto = require('node:crypto');
const nodemailer = require('nodemailer');

class CallbackMailer {
  /** @param {import('./types/contracts').StoreInstance} store @param {typeof nodemailer.createTransport} [transportFactory] */
  constructor(store, transportFactory = nodemailer.createTransport) {
    this.store = store;
    this.transportFactory = transportFactory;
  }
  enabled() {
    return this.store.value.smtp.enabled;
  }
  transport() {
    const smtp = this.store.value.smtp;
    return this.transportFactory({
      host: smtp.host,
      port: smtp.port,
      secure: smtp.security === 'tls',
      requireTLS: smtp.security === 'starttls',
      ignoreTLS: smtp.security === 'none',
      auth: smtp.username ? { user: smtp.username, pass: smtp.password } : undefined,
      connectionTimeout: 10000,
      greetingTimeout: 10000,
      socketTimeout: 15000,
    });
  }
  // @llr SLLR051
  async verify() {
    if (!this.enabled()) throw Error('Enable and save SMTP settings first.');
    try {
      await this.transport().verify();
    } catch (error) {
      throw Error(mailError(error));
    }
  }
  /** @param {import('./types/contracts').CallbackRecord} request @param {string} address */
  async sendCallback(request, address) {
    const v = this.store.value;
    const name = v.users[request.from]?.name || request.from;
    const recipientHash = crypto
      .createHash('sha256')
      .update(address.toLowerCase())
      .digest('hex')
      .slice(0, 16);
    try {
      const result = await this.transport().sendMail({
        from: { name: 'ZmalaCall', address: v.smtp.from },
        to: address,
        subject: 'ZmalaCall: callback requested',
        messageId: `<${request.id}.${recipientHash}@zmalacall.local>`,
        text: `${name} would like you to call back.\n\nOpen Linphone and call sip:${request.from}@${v.host}.\nRequested: ${request.created_at}\nThis callback request will be removed at ${request.expires_at}.\n\nZmalaCall`,
        disableFileAccess: true,
        disableUrlAccess: true,
      });
      return result.accepted.some((item) => item.toLowerCase() === address.toLowerCase());
    } catch (error) {
      throw Error(mailError(error));
    }
  }
}
/** Provider responses may contain credentials or addresses; expose only a stable diagnosis. */
/** @param {unknown} error */
function mailError(error) {
  const code =
    error && typeof error === 'object' && 'code' in error && typeof error.code === 'string'
      ? error.code
      : '';
  /** @type {Record<string, string>} */
  const diagnoses = {
    EAUTH: 'SMTP authentication failed.',
    EDNS: 'SMTP hostname could not be resolved.',
    ECONNECTION: 'Could not connect to SMTP.',
    ETIMEDOUT: 'SMTP connection timed out.',
    ESOCKET: 'SMTP connection or TLS failed.',
    EENVELOPE: 'SMTP rejected the sender or recipient.',
    EMESSAGE: 'SMTP rejected the message.',
  };
  return diagnoses[code] || 'Email delivery failed. Check the SMTP settings.';
}
module.exports = { CallbackMailer };
