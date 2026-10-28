'use strict';
// SIP signalling and call lifecycle; encoded audio/video packets are handled by MediaRelay.
const sip = require('sip');
const proxy = require('sip/proxy');
const crypto = require('node:crypto');
const { MediaRelay } = require('./media');
const { IceMedia } = require('./secure-calls');
/** @param {string} uri */
const username = (uri) => sip.parseUri(uri)?.user;
const { RegistrationMonitor, registrationOnline } = require('./registrations');
const { SipMessages } = require('./sip-messages');
const { validRequest, maxForwards, samePeer } = require('./sip-guards');
const { startProxy } = require('./sip-transport');
const { AppCalls } = require('./app-calls');
/** SIP transport and dialog ownership. Presence and messaging have separate controllers. */
class SipServer extends SipMessages {
  /** @param {import('./types/contracts').StoreInstance} store */
  constructor(store) {
    super(store);
    /** @type {Map<string, import('./types/contracts').Dialog>} */
    this.dialogs = new Map();
    this.appCalls = new AppCalls(this);
    this.maintenance = false;
    /** @type {{time: string; message: string}[]} */
    this.events = [];
    /** @type {import('./types/contracts').CallbackInstance | undefined} */
    this.callbacks = undefined;
    /** @type {NodeJS.Timeout | undefined} */
    this.sweep = undefined;
    this.originalSend = sip.send;
    this.sendWithCancelHeaders = sip.send;
    this.presence = new RegistrationMonitor(this);
    this.probes = this.presence.probes;
    this.media = store.secureCalls
      ? new IceMedia(store.value.host)
      : new MediaRelay(store.value.host);
  }
  // @llr LLR-SRV-MAINT-020
  /** @param {string} message */
  log(message) {
    this.events.push({ time: new Date().toISOString(), message });
    this.events = this.events.slice(-80);
    console.log(message);
  }
  start() {
    const v = this.store.value;
    startProxy(
      {
        address: '0.0.0.0',
        publicAddress: v.host,
        port: v.sip_port,
        tcp: true,
        udp: true,
        ...this.store.secureCalls?.listener(),
        logger: {
          error: (e) => this.log(`SIP error: ${e.message}`),
          recv: (m, r) => {
            if (process.env.VIDEOCALL_DEBUG)
              console.log('SIP received', m.method || m.status, r.address, r.port);
          },
          send: (m, r) => {
            if (process.env.VIDEOCALL_DEBUG)
              console.log('SIP sent', m.method || m.status, r.address, r.port);
          },
        },
      },
      (rq, remote) => {
        this.request(rq, remote).catch((e) => {
          this.log(`Request failed: ${e.message}`);
          this.reply(rq, 500, 'Internal Server Error');
        });
      },
      (rq, remote) => this.cancelStatus(rq, remote),
    );
    // start() installs sip.send. Wrap it afterward: sip/proxy generates CANCEL
    // without Max-Forwards, which Liblinphone rejects while continuing to ring.
    this.originalSend = sip.send;
    /** @type {typeof sip.send} */
    this.sendWithCancelHeaders = (message, ...args) => {
      if (message.method === 'CANCEL' && message.headers['max-forwards'] === undefined)
        message.headers['max-forwards'] = 70;
      return this.originalSend.call(sip, message, ...args);
    };
    sip.send = this.sendWithCancelHeaders;
    // @llr LLR-SRV-CALL-009
    this.sweep = setInterval(() => {
      for (const [u, r] of this.registrations)
        if (r.expires < Date.now()) {
          this.cancelProbe(u);
          this.registrations.delete(u);
        }
      for (const [id, d] of this.dialogs)
        if (Date.now() - d.touched > (d.connected ? 4 * 3600000 : (d.ringing_timeout ?? 90000))) {
          this.closeDialog(id);
        }
      this.callbacks?.deliver();
      this.probeRegistrations();
    }, 5000);
    this.log(
      this.store.secureCalls
        ? `SIP TLS listener ${this.store.secureCalls.listenPort}; public ${this.store.secureCalls.sipHost}:${this.store.secureCalls.sipPort}; ICE/SRTP media`
        : `SIP listening on ${v.host}:${v.sip_port} (UDP/TCP)`,
    );
  }
  /** @param {string} user */
  cancelProbe(user) {
    this.presence.cancel(user);
  }
  probeRegistrations() {
    this.presence.check();
  }

  /** CANCEL authenticates against the original INVITE's exact transport, From
   * tag, CSeq and Via branch. It must not consume another Digest nonce count. */
  // @llr LLR-SRV-CALL-007
  /** @param {import('sip').Message} rq @param {import('sip').Remote} remote */
  cancelStatus(rq, remote) {
    if (!validRequest(rq)) return 400;
    // @llr LLR-SRV-APP-005
    const waitingStatus = this.appCalls.cancel(rq, remote);
    if (waitingStatus !== null) return waitingStatus;
    const dialog = this.dialogs.get(rq.headers['call-id']);
    if (!dialog) return 481;
    const side = dialog.peers.findIndex(
      (p) => samePeer(p.remote, remote) && p.tag === rq.headers.from.params?.tag,
    );
    if (side < 0) return 403;
    const pending = dialog.invites?.get(`${side}:${rq.headers.cseq.seq}`);
    const branch = rq.headers.via?.[0]?.params?.branch;
    if (!pending || !branch || branch !== pending.branch) return 481;
    pending.cancelled = true;
    return 0;
  }

  // @llr LLR-SRV-PRESENCE-002
  /** @param {import('sip').ValidRequest} rq @param {import('sip').Remote} remote */
  register(rq, remote) {
    const v = this.store.value;

    const user = this.auth.verify(rq, v.users);
    if (!user) {
      proxy.send(this.auth.challenge(rq));
      return;
    }
    if (username(rq.headers.to.uri) !== user || username(rq.headers.from.uri) !== user) {
      this.reply(rq, 403, 'Forbidden');
      return;
    }
    const contact = rq.headers.contact?.[0];
    const requestedExpiry = Number(contact?.params?.expires ?? rq.headers.expires ?? 600);
    // Validate before clamping: Infinity must not become a valid 600-second lease.
    if (!Number.isFinite(requestedExpiry)) {
      this.reply(rq, 400, 'Invalid Expires');
      return;
    }
    const expires = Math.max(0, Math.min(600, requestedExpiry));
    const rs = sip.makeResponse(rq, 200, 'OK');
    if (!contact) {
      const r = this.registrations.get(user);
      if (r)
        rs.headers.contact = [
          {
            ...r.contact,
            params: { expires: Math.max(0, Math.floor((r.expires - Date.now()) / 1000)) },
          },
        ];
    } else if (!expires || contact.uri === '*') {
      this.cancelProbe(user);
      this.registrations.delete(user);
      this.log(`${user} signed out`);
    } else {
      this.cancelProbe(user);
      this.registrations.set(user, { contact, remote, expires: Date.now() + expires * 1000 });
      rs.headers.contact = [{ ...contact, params: { ...contact.params, expires } }];
      rs.headers.expires = expires;
      this.log(`${user} registered from ${remote.address}`);
    }
    proxy.send(rs);
    if (contact && expires && contact.uri !== '*')
      setImmediate(() => {
        this.appCalls.registered(user);
        this.callbacks?.deliver(user);
      });
    return;
  }
  /** @param {import('sip').Message} rq @param {import('sip').Remote} remote */
  async request(rq, remote) {
    const v = this.store.value;
    if (!validRequest(rq)) {
      this.reply(rq, 400, 'Malformed Request');
      return;
    }

    // @llr LLR-SRV-BACKUP-007
    if (this.maintenance) {
      this.reply(rq, 503, 'Server Restoring');
      return;
    }
    const hops = maxForwards(rq.headers['max-forwards']);
    if (hops === null || hops === 0) {
      this.reply(
        rq,
        hops === null ? 400 : 483,
        hops === null ? 'Invalid Max-Forwards' : 'Too Many Hops',
      );
      return;
    }
    if (rq.method === 'REGISTER') return this.register(rq, remote);
    if (rq.method === 'OPTIONS') {
      this.reply(rq, 200, 'OK');
      return;
    }
    if (rq.method === 'MESSAGE') {
      this.message(rq);
      return;
    }
    const id = rq.headers['call-id'];
    let dialog = this.dialogs.get(id);
    let side;
    if (dialog) {
      // @llr LLR-SRV-CALL-006
      side = dialog.peers.findIndex(
        (p) => samePeer(p.remote, remote) && p.tag === rq.headers.from.params?.tag,
      );
      if (side === -1) {
        this.reply(rq, 403, 'Forbidden');
        return;
      }
      if (!['ACK', 'BYE', 'INVITE', 'UPDATE', 'INFO', 'PRACK'].includes(rq.method)) {
        this.reply(rq, 405, 'Method Not Allowed');
        return;
      }
    } else {
      if (rq.method !== 'INVITE') {
        this.reply(rq, 481, 'Call Does Not Exist');
        return;
      }
      // @llr LLR-SRV-CALL-004
      const user = this.auth.verify(rq, v.users, true);
      if (!user) {
        proxy.send(this.auth.challenge(rq, true));
        return;
      }
      const to = username(rq.headers.to.uri),
        from = username(rq.headers.from.uri);
      if (
        !from ||
        !to ||
        from !== user ||
        username(rq.uri) !== to ||
        !this.store.permitted(from, to)
      ) {
        this.reply(rq, 403, 'Calling Not Permitted');
        return;
      }
      if (this.dialogs.size + this.appCalls.waiting.size >= 24) {
        this.reply(rq, 486, 'Busy Here');
        return;
      }
      if (
        this.appCalls.busy(from) ||
        this.appCalls.busy(to) ||
        [...this.dialogs.values()].some((d) =>
          d.peers.some((p) => p.user === from || p.user === to),
        )
      ) {
        this.reply(rq, 486, 'Busy Here');
        return;
      }
      const fromContact = rq.headers.contact?.[0];
      if (!fromContact) {
        this.reply(rq, 400, 'Contact Required');
        return;
      }
      // @llr LLR-SRV-APP-005
      // Even a stale registration must not hide a sleeping app from FCM.
      if (this.appCalls.push.available(to)) {
        if (!(await this.appCalls.wait(rq, remote, from, to))) return;
      }
      const target = this.registrations.get(to);
      if (!registrationOnline(target) || this.maintenance || !this.store.permitted(from, to)) {
        this.reply(rq, 480, 'Temporarily Unavailable');
        return;
      }
      side = 0;
      dialog = {
        peers: [
          { user: from, remote, contact: fromContact, tag: rq.headers.from.params?.tag },
          { user: to, remote: target.remote, contact: target.contact, tag: null },
        ],
        touched: Date.now(),
        connected: false,
        ringing_timeout: (this.store.ringTimeout(to) + 30) * 1000,
        queue: Promise.resolve(),
        invites: new Map(),
      };
      this.dialogs.set(id, dialog);
      this.log(`${from} calling ${to}`);
    }
    return this.forwardDialog(rq, remote, dialog, side);
  }
  /** @param {import('sip').ValidRequest} rq @param {import('sip').Remote} remote @param {import('./types/contracts').Dialog} dialog @param {number} side */
  async forwardDialog(rq, remote, dialog, side) {
    const v = this.store.value,
      id = rq.headers['call-id'];
    dialog.touched = Date.now();
    const initial = rq.method === 'INVITE' && !rq.headers.to.params?.tag;
    // @llr LLR-SRV-CALL-008
    const negotiates = dialog.connected && ['INVITE', 'UPDATE'].includes(rq.method);
    // Delayed offers require staging an answer from ACK, which this relay does
    // not implement. Reject them without changing the established media graph.
    if (
      negotiates &&
      rq.method === 'INVITE' &&
      rq.headers['content-type']?.toLowerCase() !== 'application/sdp'
    ) {
      this.reply(rq, 488, 'SDP Offer Required');
      return;
    }
    if (negotiates && dialog.mediaUpdate) {
      this.reply(rq, 491, 'Request Pending');
      return;
    }
    const mediaUpdate = negotiates ? this.media.begin(id) : undefined;
    if (mediaUpdate) dialog.mediaUpdate = mediaUpdate;
    const finishMedia = (accepted = false) => {
      if (!mediaUpdate) return;
      if (accepted) this.media.commit(mediaUpdate);
      else this.media.discard(mediaUpdate);
      if (dialog.mediaUpdate === mediaUpdate) delete dialog.mediaUpdate;
    };
    const inviteKey = `${side}:${rq.headers.cseq.seq}`;
    const pending =
      rq.method === 'INVITE'
        ? {
            branch: rq.headers.via?.[0]?.params?.branch,
            cancelled: false,
          }
        : null;
    if (pending) dialog.invites.set(inviteKey, pending);
    const target = dialog.peers[1 - side];
    const forward = sip.copyMessage(rq, true);
    // Keep every subsequent request on the exact authenticated registration flow.
    forward.uri = target.contact.uri;
    forward.headers.route = [{ uri: sip.encodeFlowUri(target.remote) }];
    delete forward.headers['proxy-authorization'];
    delete forward.headers.authorization;
    // @llr LLR-SRV-CALL-005
    delete forward.headers['x-family-auth'];
    const terminal = this.store.enrolledAccount(target.user);
    if (terminal)
      forward.headers['x-family-auth'] = crypto
        .createHmac('sha256', terminal.device_token)
        .update(`${id}:${dialog.peers[side].user}`)
        .digest('hex');
    const hops = maxForwards(forward.headers['max-forwards']);
    if (hops === null || hops === 0) {
      finishMedia();
      this.reply(
        rq,
        hops === null ? 400 : 483,
        hops === null ? 'Invalid Max-Forwards' : 'Too Many Hops',
      );
      return;
    }
    forward.headers['max-forwards'] = hops - 1;
    if (initial)
      forward.headers['record-route'] = [
        {
          uri: this.store.secureCalls
            ? `${this.store.secureCalls.proxy()};lr`
            : `sip:${v.host}:${v.sip_port};lr`,
        },
      ];
    if (forward.headers['content-type']?.toLowerCase() === 'application/sdp') {
      try {
        if (typeof forward.content !== 'string') throw Error('Missing SDP body.');
        forward.content = await this.media.rewrite(
          id,
          forward.content,
          side,
          remote.address,
          mediaUpdate,
        );
      } catch (e) {
        finishMedia();
        dialog.invites.delete(inviteKey);
        if (this.dialogs.get(id) !== dialog) return;
        this.log(e instanceof Error ? e.message : 'SDP rewrite failed.');
        this.reply(rq, 488, 'Not Acceptable Here');
        if (initial) {
          this.closeDialog(id);
        }
        return;
      }
    }
    // Binding media yields: a BYE, timeout or shutdown may have released this
    // dialog in the meantime. Never forward an offer for a dead/replaced call.
    if (this.dialogs.get(id) !== dialog) return;
    if (pending?.cancelled) {
      finishMedia();
      // The proxy has already acknowledged CANCEL, but media bind was still
      // pending. Finish the original INVITE without ringing the recipient.
      this.reply(rq, 487, 'Request Terminated');
      dialog.invites.delete(inviteKey);
      if (initial) this.closeDialog(id);
      return;
    }
    /** @type {import('sip').Response | undefined} */
    let finalResponse;
    proxy.send(forward, (rs) => {
      dialog.queue = dialog.queue
        .then(async () => {
          if (this.dialogs.get(id) !== dialog) return;
          if (finalResponse && rs.status >= 200) {
            proxy.send(sip.copyMessage(finalResponse, true));
            return;
          }
          if (pending && rs.status >= 200) dialog.invites.delete(inviteKey);
          const response = sip.copyMessage(rs, true);
          response.headers.via?.shift();
          if (rs.headers.to?.params?.tag) target.tag = rs.headers.to.params.tag;
          if (rs.headers.contact?.[0]) target.contact = rs.headers.contact[0];
          if (
            rs.status < 300 &&
            response.headers['content-type']?.toLowerCase() === 'application/sdp'
          ) {
            if (typeof response.content !== 'string') throw Error('Missing SDP body.');
            response.content = await this.media.rewrite(
              id,
              response.content,
              1 - side,
              target.remote.address,
              mediaUpdate,
            );
          }
          if (this.dialogs.get(id) !== dialog) return;
          if (rs.status >= 200 && mediaUpdate?.active) finishMedia(rs.status < 300);
          if (rs.status >= 200 && rs.status < 300 && rq.method === 'INVITE') {
            dialog.connected = true;
            this.log('Call connected');
            this.callbacks?.connected(dialog.peers[0].user, dialog.peers[1].user);
          }
          if (rs.status >= 200) finalResponse = response;
          proxy.send(response);
          if ((initial && rs.status >= 300) || (rq.method === 'BYE' && rs.status >= 200)) {
            this.log(`Call ended (${rs.status})`);
            this.closeDialog(id);
          }
        })
        .catch((e) => {
          finishMedia();
          if (this.dialogs.get(id) !== dialog) return;
          this.log(`Relay failed: ${e.message}`);
          this.reply(rq, 488, 'Not Acceptable Here');
          if (initial) this.closeDialog(id);
        });
    });
  }
  // @llr LLR-SRV-CALL-009
  /** @param {string} id */
  closeDialog(id) {
    const update = this.dialogs.get(id)?.mediaUpdate;
    if (update) this.media.discard(update);
    this.media.close(id);
    this.dialogs.delete(id);
  }
  status() {
    return {
      registrations: [...this.registrations]
        .filter(([, r]) => registrationOnline(r))
        .map(([user, r]) => ({
          user,
          address: r.remote.address,
          expires_at: new Date(r.expires).toISOString(),
        })),
      active_calls: this.dialogs.size + this.appCalls.waiting.size,
      relay_sessions: this.media.sessions.size,
      events: this.events,
    };
  }
  close() {
    this.appCalls.close();
    clearInterval(this.sweep);
    this.presence.close();
    // Invalidate dialog ownership before releasing relays: pending SDP work can
    // resume after shutdown and must never forward a request or response.
    this.dialogs.clear();
    this.registrations.clear();
    this.media.closeAll();
    sip.stop();
    proxy.clearContexts();
    if (sip.send === this.sendWithCancelHeaders) sip.send = this.originalSend;
  }
}
module.exports = { SipServer, registrationOnline };
