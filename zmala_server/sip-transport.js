'use strict';
const proxy = require('sip/proxy');

/** sip/proxy consumes CANCEL before invoking the application router. The
 * vendored transport adds a pre-transaction guard so a rejected CANCEL cannot
 * reserve/cache the legitimate caller's transaction ID. All other SIP transport
 * and retransmission behavior stays in the pinned stack. */
/** @param {import('sip').Options} options @param {(rq: import('sip').Message, remote: import('sip').Remote) => void} route @param {(rq: import('sip').Message, remote: import('sip').Remote) => number} cancelStatus */
function startProxy(options, route, cancelStatus) {
  proxy.start(
    {
      ...options,
      requestGuard: (request, remote) =>
        request.method === 'CANCEL' ? cancelStatus(request, remote) : 0,
    },
    route,
  );
}
module.exports = { startProxy };
