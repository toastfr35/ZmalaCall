'use strict';
// SIP registration reachability and contact parsing shared by call routing and device availability.
const sip = require('sip');
const crypto = require('node:crypto');
/** @template {{expires: number; reachable?: boolean}} T
 * @param {T | undefined} r @returns {r is T} */
const registrationOnline = (r) => Boolean(r && r.expires > Date.now() && r.reachable !== false);
/** Probe exact registration objects; late replies cannot change a newly registered flow. */
class RegistrationMonitor {
  /** @param {import('./types/contracts').SipInstance} server */
  constructor(server) {
    this.server = server;
    /** @type {Map<string, {registration: import('./types/contracts').SipRegistration; timer: NodeJS.Timeout | null}>} */
    this.probes = new Map();
  }
  /** @param {string} user */
  cancel(user) {
    const probe = this.probes.get(user);
    if (probe) {
      if (probe.timer) clearTimeout(probe.timer);
      this.probes.delete(user);
    }
  }
  // @llr SLLR040
  check() {
    for (const [user, registration] of this.server.registrations) {
      if (this.probes.has(user) || registration.expires <= Date.now()) continue;
      /** @type {{registration: import('./types/contracts').SipRegistration; timer: NodeJS.Timeout | null}} */
      const probe = { registration, timer: null };
      this.probes.set(user, probe);
      // @llr SLLR041
      /** @param {boolean} online */
      const finish = (online) => {
        if (this.probes.get(user) !== probe) return;
        this.cancel(user);
        if (this.server.registrations.get(user) !== registration) return;
        const wasOnline = registration.reachable !== false;
        registration.reachable = online;
        if (!online && wasOnline) this.server.log(`${user} went offline (SIP reachability check)`);
        if (online && !wasOnline) {
          this.server.log(`${user} is reachable again`);
          this.server.callbacks?.deliver(user);
        }
      };
      probe.timer = setTimeout(() => finish(false), 5000);
      const request = {
        method: 'OPTIONS',
        uri: registration.contact.uri,
        headers: {
          to: { uri: `sip:${user}@${this.server.store.value.host}` },
          from: {
            uri: `sip:presence@${this.server.store.value.host}`,
            params: { tag: crypto.randomBytes(8).toString('hex') },
          },
          via: [],
          route: [{ uri: sip.encodeFlowUri(registration.remote) }],
          cseq: { seq: 1, method: 'OPTIONS' },
          'call-id': 'presence-' + crypto.randomUUID(),
          'max-forwards': 70,
        },
      };
      try {
        sip.send(request, (response) => {
          if (response.status >= 200) finish(response.status !== 408 && response.status !== 503);
        });
      } catch {
        finish(false);
      }
    }
  }
  close() {
    for (const user of this.probes.keys()) this.cancel(user);
  }
}
module.exports = { RegistrationMonitor, registrationOnline };
