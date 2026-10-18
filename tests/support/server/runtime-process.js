'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const net = require('node:net');
const { spawn } = require('node:child_process');
const { Store } = require('../../../zmala_server/store');
const root = path.resolve(__dirname, '../../..');

async function unusedPort() {
  const server = net.createServer();
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise((resolve) => server.close(resolve));
  return port;
}

/** Copy authored runtime into a disposable root so main.js cannot touch real state. */
async function runtimeProcess(t, overrides = {}) {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'zmala-runtime-'));
  const serverRoot = path.join(directory, 'zmala_server');
  await fs.cp(path.join(root, 'zmala_server'), serverRoot, {
    recursive: true,
    filter: (source) =>
      !['node_modules', 'data', 'test-portraits', '__pycache__'].includes(path.basename(source)),
  });
  await fs.symlink(
    path.join(root, 'zmala_server/node_modules'),
    path.join(serverRoot, 'node_modules'),
    'junction',
  );
  await fs.mkdir(path.join(directory, 'build_tools'), { recursive: true });
  await fs.copyFile(
    path.join(root, 'build_tools/build-admin.cjs'),
    path.join(directory, 'build_tools/build-admin.cjs'),
  );
  await fs.cp(
    path.join(root, 'zmala_terminal/common/shared'),
    path.join(directory, 'zmala_terminal/common/shared'),
    { recursive: true },
  );
  const store = new Store(path.join(serverRoot, 'data'));
  Object.assign(store.value, {
    host: '127.0.0.1',
    http_port: await unusedPort(),
    sip_port: await unusedPort(),
    ...overrides,
  });
  store.save();
  const env = { ...process.env, VIDEOCALL_HOST: '127.0.0.1' };
  for (const key of [
    'ZMALA_TLS_CERT',
    'ZMALA_TLS_KEY',
    'ZMALA_HTTPS_PORT',
    'ZMALA_ADMIN_PASSWORD_FILE',
  ])
    delete env[key];
  const child = spawn(process.execPath, [path.join(serverRoot, 'main.js')], {
    cwd: directory,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let output = '';
  child.stdout.on('data', (bytes) => {
    output += bytes;
  });
  child.stderr.on('data', (bytes) => {
    output += bytes;
  });
  const exited = new Promise((resolve) =>
    child.once('exit', (code, signal) => resolve({ code, signal })),
  );
  t.after(async () => {
    if (child.exitCode === null && child.signalCode === null) {
      child.kill('SIGKILL');
      await exited;
    }
    await fs.rm(directory, { recursive: true, force: true });
  });
  return {
    directory,
    store,
    child,
    exited,
    get output() {
      return output;
    },
  };
}

async function waitFor(predicate, describe) {
  const until = Date.now() + 5000;
  while (!predicate()) {
    if (Date.now() > until) throw Error(`Timed out: ${describe}`);
    await new Promise((resolve) => setTimeout(resolve, 20));
  }
}

module.exports = { runtimeProcess, unusedPort, waitFor };
