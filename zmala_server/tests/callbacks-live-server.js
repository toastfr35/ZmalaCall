'use strict';
// Isolated SIP/HTTP service for the native callback integration test.
const fs = require('node:fs'),
  path = require('node:path');
const { Store } = require('../store'),
  { SipServer } = require('../sip-server'),
  { MediaRelay } = require('../media'),
  { createApplication } = require('../main');
const store = new Store(path.resolve(process.argv[2]));
Object.assign(store.value, { host: '127.0.0.1', sip_port: Number(process.argv[3]), http_port: 0 });
store.value.users.term1.name = 'Evelyn';
store.value.users.phone1.name = 'Noah';
store.value.profiles.term1.terminal_settings.camera = 'StaticImage: Static picture';
store.save();
const sipServer = new SipServer(store);
sipServer.media = new MediaRelay('127.0.0.1', 26000, 26099);
const { server, writeBootstrap, callbacks, flush } = createApplication({ store, sipServer });
sipServer.start();
server.listen(0, '127.0.0.1', async () => {
  store.value.http_port = server.address().port;
  await store.save();
  await writeBootstrap();
  fs.writeFileSync(path.join(store.dir, 'ready'), 'ready');
});
async function close() {
  server.close();
  sipServer.close();
  await flush();
  process.exit(0);
}
if (process.argv[4] === '--preview') {
  callbacks.create('term1', 'phone1');
  setTimeout(close, 120000);
} else {
  process.stdin.resume();
  process.stdin.on('end', close);
}
