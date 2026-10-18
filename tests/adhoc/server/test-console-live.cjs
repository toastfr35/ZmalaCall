'use strict';
// Opt-in integration check against a real Linux terminal. Commands are read-only
// apart from their short-lived child processes; results remain in console history.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { setTimeout: delay } = require('node:timers/promises');

async function main() {
  const id = process.argv[2];
  assert(id, 'Usage: node tests/adhoc/server/test-console-live.cjs <terminal-account>');
  const settings = JSON.parse(
    fs.readFileSync(path.join(__dirname, '../../../zmala_server/data/server.json'), 'utf8'),
  );
  const base = `http://127.0.0.1:${settings.http_port}`;
  let credential = settings.admin_token;
  const authStatus = await fetch(base + '/api/auth/status', {
    signal: AbortSignal.timeout(5000),
  });
  assert(authStatus.ok, 'Could not check admin authentication status.');
  if (!(await authStatus.json()).setup_required) {
    assert(process.env.ZMALA_ADMIN_PASSWORD, 'Set ZMALA_ADMIN_PASSWORD for this opt-in check.');
    const login = await fetch(base + '/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: process.env.ZMALA_ADMIN_PASSWORD, session_token: true }),
      signal: AbortSignal.timeout(5000),
    });
    assert(login.ok, 'Admin sign-in failed.');
    credential = (await login.json()).session_token;
  }
  async function request(route, method = 'GET', body) {
    const reply = await fetch(base + route, {
      method,
      headers: {
        Authorization: `Bearer ${credential}`,
        'Content-Type': 'application/json',
      },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    });
    assert(reply.ok, `Console request failed: ${reply.status}`);
    return reply.json();
  }
  const model = await request('/api/admin');
  assert.equal(model.sip_status.active_calls, 0, 'End calls before testing');
  assert(['sh', 'bash'].includes(model.profiles[id]?.command_shell), 'Select a Linux shell first');
  const route = `/api/terminals/${encodeURIComponent(id)}/console`;
  const report = [];
  for (const check of [
    {
      name: 'stdout and Unicode',
      command: "printf 'console-live: café\\n'; uname -m",
      status: 'completed',
      exit: 0,
    },
    {
      name: 'stderr and failure',
      command: "printf 'expected test error\\n' >&2; exit 7",
      status: 'failed',
      exit: 7,
    },
    { name: 'timeout', command: 'sleep 30', status: 'timed_out', exit: null },
    {
      name: 'output limit',
      command: 'python3 -c \'print("x" * 70000)\'',
      status: 'completed',
      exit: 0,
    },
    {
      name: 'queue continues',
      command: "printf 'console-live: recovered\\n'",
      status: 'completed',
      exit: 0,
    },
  ]) {
    const created = await request(route, 'POST', { command: check.command, timeout_seconds: 5 });
    const deadline = Date.now() + 35000;
    let result;
    while (Date.now() < deadline) {
      result = (await request(route)).jobs.find((job) => job.id === created.id);
      if (result && !['queued', 'running'].includes(result.status)) break;
      await delay(500);
    }
    assert.equal(result?.status, check.status, check.name);
    assert.equal(result.exit_code, check.exit, check.name);
    assert.equal('lease' in result, false, 'History must not expose the execution lease');
    if (check.name === 'stdout and Unicode')
      assert.match(result.stdout, /^console-live: café\n[^\n]+\n$/);
    if (check.name === 'stderr and failure') assert.match(result.stderr, /expected test error/);
    if (check.name === 'output limit') {
      assert.equal(result.truncated, true);
      assert.equal(Buffer.byteLength(result.stdout), 65536);
    }
    if (check.name === 'queue continues') assert.match(result.stdout, /console-live: recovered/);
    report.push({ check: check.name, status: result.status, exit_code: result.exit_code });
    console.log(JSON.stringify(report.at(-1)));
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
