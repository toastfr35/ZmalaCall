'use strict';
const { randomInt } = require('node:crypto');

/** Bind fixture HTTP to fetch-safe ports, retrying parallel test collisions. */
async function listenHttp(server) {
  // Windows can assign an ephemeral port that fetch forbids (e.g. 10080).
  // Choose a high port and retry parallel-fixture collisions or ports that
  // Windows reserves and rejects with EACCES.
  for (let attempt = 0; ; attempt++) {
    try {
      await new Promise((resolve, reject) => {
        const failed = (error) => {
          server.off('listening', listening);
          reject(error);
        };
        const listening = () => {
          server.off('error', failed);
          resolve();
        };
        server.once('error', failed);
        server.once('listening', listening);
        server.listen(randomInt(49152, 65535), '127.0.0.1');
      });
      break;
    } catch (error) {
      if (!['EADDRINUSE', 'EACCES'].includes(error.code) || attempt >= 20) throw error;
    }
  }
}
module.exports = { listenHttp };
