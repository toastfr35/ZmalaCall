// @ts-check
'use strict';

/** Drain listeners before flushing their last mutations. All error/signal paths
 * share one promise so concurrent shutdown requests cannot close SIP twice.
 * @param {import('node:http').Server[]} listeners
 * @param {{close(): void}} sipServer
 * @param {() => Promise<void>} flush */
function createShutdown(listeners, sipServer, flush) {
  /** @type {Promise<void> | undefined} */
  let pending;
  return () => {
    if (!pending)
      pending = (async () => {
        const closed = Promise.all(
          listeners.map((listener) => new Promise((resolve) => listener.close(resolve))),
        );
        sipServer.close();
        await closed;
        await flush();
      })();
    return pending;
  };
}

module.exports = { createShutdown };
