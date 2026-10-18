'use strict';
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { randomInt } = require('node:crypto');
const { Store } = require('../../../zmala_server/store');
const { createApplication } = require('../../../zmala_server/main');

/** Private store and ephemeral HTTP port; never edits the user's accounts or SIP service. */
async function httpFixture() {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'zmala-http-'));
  const store = new Store(directory);
  const sipServer = {
    dialogs: new Map(),
    registrations: new Map(),
    async notifyCallback() {
      return true;
    },
    status() {
      return { registrations: [], active_calls: 0, events: [] };
    },
  };
  const application = createApplication({ store, sipServer });
  const { server } = application;
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
  store.value.http_port = server.address().port;
  return {
    ...application,
    directory,
    base: `http://127.0.0.1:${store.value.http_port}`,
    async close() {
      server.closeAllConnections();
      await new Promise((resolve) => server.close(resolve));
      await application.flush();
      fs.rmSync(directory, { recursive: true, force: true });
    },
  };
}
module.exports = { httpFixture };
