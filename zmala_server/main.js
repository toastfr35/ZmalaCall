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
const { createShutdown } = require('./shutdown');
/** @param {{store?: import('./types/contracts').StoreInstance, sipServer?: import('./types/contracts').SipInstance, callbackMailer?: import('./types/contracts').Mailer}} [options] */
function createApplication({
  store = new Store(),
  sipServer = new SipServer(store),
  callbackMailer,
} = {}) {
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
  // @llr SLLR102
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
  // @llr SLLR003
  const tlsCert = process.env.ZMALA_TLS_CERT;
  const tlsKey = process.env.ZMALA_TLS_KEY;
  /** @type {import('node:https').Server | undefined} */
  let tlsServer;
  let tlsPort = 8443;
  if (tlsCert || tlsKey) {
    if (!tlsCert || !tlsKey) throw Error('Set both ZMALA_TLS_CERT and ZMALA_TLS_KEY.');
    const port = Number(process.env.ZMALA_HTTPS_PORT || 8443);
    if (!Number.isInteger(port) || port < 1 || port > 65535 || port === v.http_port)
      throw Error('Choose a valid, separate ZMALA_HTTPS_PORT.');
    tlsServer = https.createServer(
      { cert: fs.readFileSync(tlsCert), key: fs.readFileSync(tlsKey) },
      handler,
    );
    tlsPort = port;
  }
  const shutdown = createShutdown([server, ...(tlsServer ? [tlsServer] : [])], sipServer, flush);
  // @llr SLLR005
  /** A failed listener must not leave its sibling serving a half-started app.
   * @param {unknown} error */
  function fail(error) {
    console.error(error instanceof Error ? error.message : 'Server startup failed');
    process.exitCode = 1;
    void shutdown().catch((failure) => console.error('Could not finish shutdown:', failure));
  }
  server.on('error', fail);
  tlsServer?.on('error', fail);
  try {
    sipServer.start();
    tlsServer?.listen(tlsPort, '0.0.0.0', () =>
      console.log(`HTTPS administration: https://${v.host}:${tlsPort}/`),
    );
    // @llr SLLR002
    server.listen(v.http_port, '0.0.0.0', () => {
      console.log(`Administration: http://${v.host}:${v.http_port}/`);
      console.log(`Phone SIP domain: ${v.host}:${v.sip_port}`);
    });
  } catch (error) {
    fail(error);
  }
  for (const signal of ['SIGINT', 'SIGTERM'])
    process.once(signal, async () => {
      try {
        await shutdown();
        process.exit(process.exitCode || 0);
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
