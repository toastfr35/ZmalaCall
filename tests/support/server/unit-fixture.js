'use strict';
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { Readable } = require('node:stream');
const { Store } = require('../../../zmala_server/store');
const { AdminSessions } = require('../../../zmala_server/admin-sessions');

function storeFixture(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'zmala-unit-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  return new Store(directory);
}

// No listener or network. Test the request/controller boundary with explicit
// transport properties and observable response/persistence doubles.
function request(url, { method = 'GET', value, headers = {}, socket = {} } = {}) {
  const req = Readable.from(
    value === undefined
      ? []
      : [Buffer.from(typeof value === 'string' ? value : JSON.stringify(value))],
  );
  Object.assign(req, {
    url,
    method,
    headers: { host: '127.0.0.1:8080', ...headers },
    socket: { remoteAddress: '127.0.0.1', localAddress: '127.0.0.1', localPort: 8080, ...socket },
  });
  return req;
}
function response() {
  return {
    status: null,
    headers: {},
    bytes: '',
    headersSent: false,
    setHeader(key, value) {
      this.headers[key] = value;
    },
    writeHead(status, headers) {
      this.status = status;
      Object.assign(this.headers, headers);
      this.headersSent = true;
    },
    end(value = '') {
      this.bytes = value;
    },
    json() {
      return JSON.parse(this.bytes);
    },
    destroy(error) {
      throw error;
    },
  };
}
function context(store) {
  return {
    store,
    adminSessions: new AdminSessions(),
    sipServer: {
      registrations: new Map(),
      dialogs: new Map(),
      events: [],
      active: () => false,
      isBusy: () => false,
      liveCalls: () => [],
    },
    callbacks: { list: () => [] },
    consoleJobs: {},
    terminalStatuses: {},
    writeBootstrap() {},
    persistenceReady: () => true,
  };
}
module.exports = { storeFixture, request, response, context };
