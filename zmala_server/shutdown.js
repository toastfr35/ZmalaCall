// @ts-check
'use strict';

// @llr LLR-SRV-START-009
/** Drain listeners before flushing their last mutations. All error/signal paths
 * share one promise so concurrent shutdown requests cannot close SIP twice.
 * @param {import('node:http').Server[]} listeners
 * @param {{close(): void}} sipServer
 * @param {() => Promise<void>} flush
 * @param {() => Promise<void>} [stopBackground] */
function createShutdown(listeners, sipServer, flush, stopBackground = async () => {}) {
  /** @type {Promise<void> | undefined} */
  let pending;
  return () => {
    if (!pending)
      pending = (async () => {
        const background = stopBackground();
        const closed = Promise.all(
          listeners.map((listener) => new Promise((resolve) => listener.close(resolve))),
        );
        sipServer.close();
        await Promise.all([closed, background]);
        await flush();
      })();
    return pending;
  };
}

module.exports = { createShutdown };
