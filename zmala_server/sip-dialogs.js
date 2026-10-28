// @ts-check
'use strict';
const sip = require('sip');
const proxy = require('sip/proxy');
const crypto = require('node:crypto');
const { maxForwards } = require('./sip-guards');

/** Forward only after SipServer has authenticated the exact dialog peer.
 * Media offers remain staged until an accepted response; queued responses preserve
 * SDP ordering, and every asynchronous boundary checks that the dialog still exists.
 * @param {import('./types/contracts').SipInstance} server
 * @param {import('sip').ValidRequest} rq @param {import('sip').Remote} remote
 * @param {import('./types/contracts').Dialog} dialog @param {number} side
 * @returns {Promise<void>} */
async function forwardDialog(server, rq, remote, dialog, side) {
  const v = server.store.value,
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
    server.reply(rq, 488, 'SDP Offer Required');
    return;
  }
  if (negotiates && dialog.mediaUpdate) {
    server.reply(rq, 491, 'Request Pending');
    return;
  }
  const mediaUpdate = negotiates ? server.media.begin(id) : undefined;
  if (mediaUpdate) dialog.mediaUpdate = mediaUpdate;
  const finishMedia = (accepted = false) => {
    if (!mediaUpdate) return;
    if (accepted) server.media.commit(mediaUpdate);
    else server.media.discard(mediaUpdate);
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
  const terminal = server.store.enrolledAccount(target.user);
  if (terminal)
    forward.headers['x-family-auth'] = crypto
      .createHmac('sha256', terminal.device_token)
      .update(`${id}:${dialog.peers[side].user}`)
      .digest('hex');
  const hops = maxForwards(forward.headers['max-forwards']);
  if (hops === null || hops === 0) {
    finishMedia();
    server.reply(
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
        uri: server.store.secureCalls
          ? `${server.store.secureCalls.proxy()};lr`
          : `sip:${v.host}:${v.sip_port};lr`,
      },
    ];
  if (forward.headers['content-type']?.toLowerCase() === 'application/sdp') {
    try {
      if (typeof forward.content !== 'string') throw Error('Missing SDP body.');
      forward.content = await server.media.rewrite(
        id,
        forward.content,
        side,
        remote.address,
        mediaUpdate,
      );
    } catch (e) {
      finishMedia();
      dialog.invites.delete(inviteKey);
      if (server.dialogs.get(id) !== dialog) return;
      server.log(e instanceof Error ? e.message : 'SDP rewrite failed.');
      server.reply(rq, 488, 'Not Acceptable Here');
      if (initial) {
        server.closeDialog(id);
      }
      return;
    }
  }
  // Binding media yields: a BYE, timeout or shutdown may have released this
  // dialog in the meantime. Never forward an offer for a dead/replaced call.
  if (server.dialogs.get(id) !== dialog) return;
  if (pending?.cancelled) {
    finishMedia();
    // The proxy has already acknowledged CANCEL, but media bind was still
    // pending. Finish the original INVITE without ringing the recipient.
    server.reply(rq, 487, 'Request Terminated');
    dialog.invites.delete(inviteKey);
    if (initial) server.closeDialog(id);
    return;
  }
  /** @type {import('sip').Response | undefined} */
  let finalResponse;
  proxy.send(forward, (rs) => {
    dialog.queue = dialog.queue
      .then(async () => {
        if (server.dialogs.get(id) !== dialog) return;
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
          response.content = await server.media.rewrite(
            id,
            response.content,
            1 - side,
            target.remote.address,
            mediaUpdate,
          );
        }
        if (server.dialogs.get(id) !== dialog) return;
        if (rs.status >= 200 && mediaUpdate?.active) finishMedia(rs.status < 300);
        if (rs.status >= 200 && rs.status < 300 && rq.method === 'INVITE') {
          dialog.connected = true;
          server.log('Call connected');
          server.callbacks?.connected(dialog.peers[0].user, dialog.peers[1].user);
        }
        if (rs.status >= 200) finalResponse = response;
        proxy.send(response);
        if ((initial && rs.status >= 300) || (rq.method === 'BYE' && rs.status >= 200)) {
          server.log(`Call ended (${rs.status})`);
          server.closeDialog(id);
        }
      })
      .catch((e) => {
        finishMedia();
        if (server.dialogs.get(id) !== dialog) return;
        server.log(`Relay failed: ${e.message}`);
        server.reply(rq, 488, 'Not Acceptable Here');
        if (initial) server.closeDialog(id);
      });
  });
}
module.exports = { forwardDialog };
