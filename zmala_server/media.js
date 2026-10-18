// @ts-check
'use strict';
const dgram = require('node:dgram');
// Each media stream has a distinct RTP and RTCP socket facing each participant.
// The relay forwards encoded packets unchanged; no transcoding or recording.
class MediaRelay {
  /** @param {string} host @param {number} [start] @param {number} [end] */
  constructor(host, start = 20000, end = 20199) {
    this.host = host;
    this.start = start;
    this.end = end;
    /** @type {Set<number>} */
    this.used = new Set();
    /** @type {Map<string, import('./types/contracts').MediaSession>} */
    this.sessions = new Map();
  }
  async socket() {
    for (let port = this.start; port <= this.end; port++) {
      if (this.used.has(port)) continue;
      // Reserve before awaiting bind: simultaneous SDP rewrites must not select the same port.
      this.used.add(port);
      const socket = dgram.createSocket('udp4');
      try {
        await new Promise((resolve, reject) => {
          socket.once('error', reject);
          socket.bind(port, '0.0.0.0', () => resolve(undefined));
        });
        socket.removeAllListeners('error');
        socket.on('error', (e) => console.error('Media socket:', e.message));
        return { socket, port };
      } catch {
        this.used.delete(port);
        socket.close();
      }
    }
    throw Error('Media relay capacity reached');
  }
  // @llr LLR-SRV-MEDIA-002
  /** @returns {Promise<import('./types/contracts').MediaLeg[]>} */
  async stream() {
    const sockets = [];
    try {
      for (let i = 0; i < 4; i++) sockets.push(await this.socket());
    } catch (e) {
      for (const s of sockets) {
        s.socket.close();
        this.used.delete(s.port);
      }
      throw e;
    }
    /** @type {import('./types/contracts').MediaLeg[]} */
    const legs = [
      { rtp: sockets[0], rtcp: sockets[1] },
      { rtp: sockets[2], rtcp: sockets[3] },
    ];
    for (let side = 0; side < 2; side++)
      for (const kind of /** @type {const} */ (['rtp', 'rtcp'])) {
        legs[side][kind].socket.on('message', (packet, remote) => {
          const leg = legs[side],
            other = legs[1 - side];
          // Only packets from the authenticated signalling peer can latch a media port.
          // @llr LLR-SRV-MEDIA-004
          if (!leg.peer || !other.peer || remote.address !== leg.peer || packet.length < 4) return;
          const targetKey = kind === 'rtp' ? 'rtpTarget' : 'rtcpTarget';
          leg[targetKey] = { address: remote.address, port: remote.port };
          const target = other[targetKey];
          if (target) other[kind].socket.send(packet, target.port, target.address);
        });
      }
    return legs;
  }
  /** @param {string} id @returns {import('./types/contracts').MediaUpdate} */
  begin(id) {
    let session = this.sessions.get(id);
    if (!session) {
      session = { streams: [], allocations: new Map(), closed: false, created: Date.now() };
      this.sessions.set(id, session);
    }
    session.touched = Date.now();
    return { session, changes: new Map(), allocated: new Set(), active: true };
  }
  // @llr LLR-SRV-MEDIA-005
  /** @param {import('./types/contracts').MediaUpdate} update */
  commit(update) {
    if (!update.active || update.session.closed) throw Error('Media update closed');
    const disabled = new Set();
    for (const { index, side, state } of update.changes.values()) {
      if (!state.peer) disabled.add(index);
      const legs = update.session.streams[index];
      if (legs) Object.assign(legs[side], state);
    }
    for (const index of disabled) {
      const legs = update.session.streams[index];
      if (legs) {
        for (const leg of legs) leg.peer = undefined;
        this.closeStream(legs);
        delete update.session.streams[index];
      }
    }
    update.active = false;
  }
  /** @param {import('./types/contracts').MediaUpdate} update */
  discard(update) {
    if (!update.active) return;
    update.active = false;
    if (update.session.closed) return;
    for (const index of update.allocated) {
      const legs = update.session.streams[index];
      if (legs && legs.every((leg) => !leg.peer)) {
        this.closeStream(legs);
        delete update.session.streams[index];
      }
    }
  }
  // @llr LLR-SRV-MEDIA-003
  /** @param {string} id @param {string} sdp @param {number} side @param {string} peer
   * @param {import('./types/contracts').MediaUpdate} [update] */
  async rewrite(id, sdp, side, peer, update) {
    if (typeof sdp !== 'string' || !sdp.startsWith('v=0')) throw Error('Invalid SDP');
    const lines = sdp.trim().split(/\r?\n/);
    if (lines.some((l) => /^a=(group:BUNDLE|bundle-only)/.test(l)))
      throw Error('Bundled media is not supported; disable BUNDLE/ICE in the client.');
    // Validate every supported section before allocating or changing any leg.
    for (const line of lines.filter((line) => line.startsWith('m='))) {
      const [kind, value, protocol] = line.slice(2).split(/\s+/);
      const port = Number(value);
      if (
        ['audio', 'video'].includes(kind) &&
        /^RTP\/S?AVPF?$/.test(protocol) &&
        (!Number.isInteger(port) || (port !== 0 && (port < 1024 || port > 65535)))
      )
        throw Error('Invalid media port');
    }
    const change = update || this.begin(id),
      session = change.session;
    if (!change.active || session.closed) throw Error('Media update closed');
    const out = [];
    let index = -1;
    try {
      for (const line of lines) {
        if (line.startsWith('m=')) {
          index++;
          const fields = line.slice(2).split(/\s+/),
            port = Number(fields[1]);
          const state = { peer: undefined, rtpTarget: null, rtcpTarget: null };
          /** @type {import('./types/contracts').MediaUpdate['changes'] extends Map<string, infer T> ? T : never} */
          const entry = { index, side, state };
          change.changes.set(`${side}:${index}`, entry);
          if (
            !['audio', 'video'].includes(fields[0]) ||
            !/^RTP\/AVP(F)?$|^RTP\/SAVP(F)?$/.test(fields[2])
          ) {
            fields[1] = '0';
            out.push('m=' + fields.join(' '));
            continue;
          }
          if (port === 0) {
            out.push(line);
            continue;
          }
          if (!Number.isInteger(port) || port < 1024 || port > 65535)
            throw Error('Invalid media port');
          if (!session.streams[index]) change.allocated.add(index);
          const legs = await this.streamFor(session, index);
          if (!change.active) {
            if (change.allocated.has(index) && legs.every((leg) => !leg.peer)) {
              this.closeStream(legs);
              delete session.streams[index];
            }
            throw Error('Media update closed');
          }
          const leg = entry.state,
            facing = legs[1 - side];
          leg.peer = peer;
          // SDP is the initial destination; authenticated-peer packets later latch the NAT port.
          leg.rtpTarget = { address: peer, port };
          leg.rtcpTarget = port < 65535 ? { address: peer, port: port + 1 } : null;
          fields[1] = String(facing.rtp.port);
          out.push('m=' + fields.join(' '));
          out.push(`a=rtcp:${facing.rtcp.port} IN IP4 ${this.host}`);
        } else if (line.startsWith('c=')) out.push(`c=IN IP4 ${this.host}`);
        else if (/^a=rtcp:/.test(line)) {
          const port = Number(line.slice(7).split(' ')[0]);
          const entry = change.changes.get(`${side}:${index}`);
          if (entry?.state.peer && Number.isInteger(port) && port >= 1024 && port <= 65535)
            entry.state.rtcpTarget = { address: peer, port };
        } else if (/^a=(candidate:|ice-|end-of-candidates|rtcp-mux|remote-candidates:)/.test(line))
          continue;
        else out.push(line);
      }
      if (!update) this.commit(change);
      return out.join('\r\n') + '\r\n';
    } catch (error) {
      this.discard(change);
      throw error;
    }
  }
  // @llr LLR-SRV-MEDIA-006
  /** @param {import('./types/contracts').MediaSession} session @param {number} index */
  async streamFor(session, index) {
    if (session.closed) throw Error('Media session closed');
    if (session.streams[index]) return session.streams[index];
    let allocation = session.allocations.get(index);
    if (!allocation) {
      // Offers and answers may arrive together while UDP bind is asynchronous.
      // Share the allocation, and reclaim sockets if the call ended during bind.
      allocation = this.stream()
        .then((legs) => {
          if (session.closed) {
            this.closeStream(legs);
            throw Error('Media session closed');
          }
          session.streams[index] = legs;
          return legs;
        })
        .finally(() => session.allocations.delete(index));
      session.allocations.set(index, allocation);
    }
    return allocation;
  }
  /** @param {import('./types/contracts').MediaLeg[]} legs */
  closeStream(legs) {
    for (const leg of legs)
      for (const kind of /** @type {const} */ (['rtp', 'rtcp'])) {
        leg[kind].socket.close();
        this.used.delete(leg[kind].port);
      }
  }
  /** @param {string} id */
  close(id) {
    const session = this.sessions.get(id);
    if (!session) return;
    session.closed = true;
    for (const legs of session.streams) if (legs) this.closeStream(legs);
    this.sessions.delete(id);
  }
  closeAll() {
    for (const id of this.sessions.keys()) this.close(id);
  }
}
module.exports = { MediaRelay };
