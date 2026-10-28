'use strict';
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { listenHttp } = require('./listen-http');
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
  await listenHttp(server);
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
