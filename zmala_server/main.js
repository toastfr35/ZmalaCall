'use strict';
// Compose configuration, SIP, HTTP and background callback delivery; launchers own process supervision.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const https = require('node:https');
const { isIP } = require('node:net');
const { Store, DATA } = require('./store');
const { SipServer } = require('./sip-server');
const { createHandler } = require('./http/handler');
const { ConsoleJobs } = require('./console-jobs');
const { Callbacks } = require('./callbacks');
const { SnapshotFile } = require('./snapshot-file');
const { AdminSessions } = require('./admin-sessions');
/** @param {{store?: import('./types/contracts').StoreInstance, sipServer?: import('./types/contracts').SipInstance, callbackMailer?: import('./types/contracts').Mailer}} [options] */
function createApplication({
  store = new Store(),
  sipServer = new SipServer(store),
  callbackMailer,
} = {}) {
  const v = store.value;
  const bootstrapFiles = [path.join(store.dir, 'terminal.json')];
  if (store.dir === DATA) {
    const terminalData = path.resolve(__dirname, '../zmala_terminal/data');
    fs.mkdirSync(terminalData, { recursive: true });
    bootstrapFiles.push(path.join(terminalData, 'terminal.json'));
  }
  // Initial setup runs before serving requests. Later bootstrap updates share
  // an ordered queue per file and are awaited before acknowledging account edits.
  const bootstrapWriters = bootstrapFiles.map((file) => new SnapshotFile(file));
  async function writeBootstrap() {
    const bootstrap = JSON.stringify(store.bootstrap(), null, 2);
    await store.flush();
    await Promise.all(bootstrapWriters.map((writer) => writer.write(bootstrap)));
  }
  const bootstrap = JSON.stringify(store.bootstrap(), null, 2);
  for (const file of bootstrapFiles) fs.writeFileSync(file, bootstrap);
  fs.writeFileSync(
    path.join(store.dir, 'open-admin.url'),
    `[InternetShortcut]\r\nURL=http://127.0.0.1:${v.http_port}/\r\n`,
  );
  const terminalStatuses = {};
  const adminSessions = new AdminSessions();
  const consoleJobs = new ConsoleJobs(store);
  const callbacks = new Callbacks(store, sipServer, callbackMailer);
  sipServer.callbacks = callbacks;
  store.enableAsyncPersistence();
  callbacks.enableAsyncPersistence();
  consoleJobs.enableAsyncPersistence();
  async function flush() {
    await Promise.all([
      store.flush(),
      callbacks.flush(),
      consoleJobs.flush(),
      ...bootstrapWriters.map((writer) => writer.flush()),
    ]);
  }

  const handler = createHandler({
    store,
    sipServer,
    callbacks,
    consoleJobs,
    terminalStatuses,
    writeBootstrap,
    adminSessions,
    persistenceReady: () =>
      [
        store.persistence,
        callbacks.persistence,
        consoleJobs.persistence,
        ...bootstrapWriters,
      ].every((writer) => !writer?.failed),
    requireSecureAdmin: !!process.env.ZMALA_TLS_CERT,
  });
  const server = http.createServer(handler);
  return {
    server,
    handler,
    sipServer,
    store,
    writeBootstrap,
    callbacks,
    consoleJobs,
    flush,
    adminSessions,
  };
}
function start() {
  require('../build_tools/build-admin.cjs').buildAdmin();
  const store = new Store();
  if (process.env.VIDEOCALL_HOST) {
    if (isIP(process.env.VIDEOCALL_HOST) !== 4)
      throw Error('VIDEOCALL_HOST must be an IPv4 address');
    if (store.value.host !== process.env.VIDEOCALL_HOST) {
      store.value.host = process.env.VIDEOCALL_HOST;
      store.value.configuration_version++;
      store.save();
    }
  }
  const v = store.value;
  const { server, handler, sipServer, flush } = createApplication({ store });
  // Keep terminal HTTP available. An optional TLS listener uses the same
  // password/session boundary and marks browser cookies Secure on HTTPS.
  const tlsCert = process.env.ZMALA_TLS_CERT;
  const tlsKey = process.env.ZMALA_TLS_KEY;
  /** @type {import('node:https').Server | undefined} */
  let tlsServer;
  if (tlsCert || tlsKey) {
    if (!tlsCert || !tlsKey) throw Error('Set both ZMALA_TLS_CERT and ZMALA_TLS_KEY.');
    const port = Number(process.env.ZMALA_HTTPS_PORT || 8443);
    if (!Number.isInteger(port) || port < 1 || port > 65535 || port === v.http_port)
      throw Error('Choose a valid, separate ZMALA_HTTPS_PORT.');
    tlsServer = https.createServer(
      { cert: fs.readFileSync(tlsCert), key: fs.readFileSync(tlsKey) },
      handler,
    );
    tlsServer.listen(port, '0.0.0.0', () =>
      console.log(`HTTPS administration: https://${v.host}:${port}/`),
    );
    tlsServer.on('error', (error) => {
      console.error(error.message);
      server.close();
      sipServer.close();
      process.exitCode = 1;
    });
  }
  sipServer.start();
  server.listen(v.http_port, '0.0.0.0', () => {
    console.log(
      `Administration: http://127.0.0.1:${v.http_port}/ (open zmala_server/data/open-admin.url)`,
    );
    console.log(`Phone SIP domain: ${v.host}:${v.sip_port}`);
  });
  server.on('error', (e) => {
    console.error(e.message);
    sipServer.close();
    process.exitCode = 1;
  });
  for (const signal of ['SIGINT', 'SIGTERM'])
    process.once(signal, async () => {
      const closed = Promise.all(
        [server, ...(tlsServer ? [tlsServer] : [])].map(
          (listener) => new Promise((resolve) => listener.close(resolve)),
        ),
      );
      sipServer.close();
      try {
        await closed;
        await flush();
        process.exit(0);
      } catch (error) {
        console.error(
          'Could not finish saving configuration:',
          error instanceof Error ? error.message : 'Unknown error',
        );
        process.exit(1);
      }
    });
  return { server, sipServer, store };
}
if (require.main === module) start();
module.exports = { createApplication, start };
