// @test S-HLT-009
// @requirements HLR-SRV-MAINT-001
// @environment portable
// @plan Queue, claim and complete maintenance jobs through HTTP across two device identities; reload history and assert single leases, ownership isolation and bounded idempotent results.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { httpFixture } = require('../../support/server/http-fixture');
const test = require('node:test');
const assert = require('node:assert/strict');
const { ConsoleJobs } = require('../../../zmala_server/console-jobs');

test('console isolates terminal jobs, leases once, persists history and returns bounded results', async () => {
  const fixture = await httpFixture();
  const { store, base } = fixture;
  store.createAccount({
    emails: ['fixture@example.test'],
    id: 'second',
    name: 'Second',
    type: 'terminal',
  });
  const admin = store.value.admin_token,
    first = store.value.users.term1.device_token,
    second = store.value.users.second.device_token;
  async function req(route, method = 'GET', value, token = admin) {
    const r = await fetch(base + route, {
      method,
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: value ? JSON.stringify(value) : undefined,
    });
    return { status: r.status, body: await r.json() };
  }
  const route = '/api/terminals/term1/console';
  try {
    assert.equal((await req(route, 'POST', { command: 'Get-Date' }, first)).status, 401);
    assert.equal((await req(route, 'POST', { command: 'Get-Date' }, 'wrong')).status, 401);
    for (const bad of [
      { command: '' },
      { command: 'a'.repeat(8001) },
      { command: 'Get-Date', timeout_seconds: 121 },
    ])
      assert.equal((await req(route, 'POST', bad)).status, 400);
    const created = await req(route, 'POST', { command: 'Write-Output hello', timeout_seconds: 5 });
    assert.equal(created.status, 201);
    assert.equal((await req('/api/console/next', 'POST', {}, admin)).status, 401);
    assert.equal((await req('/api/console/next', 'POST', {}, second)).body.job, null);
    const claimed = (await req('/api/console/next', 'POST', {}, first)).body.job;
    assert.equal(claimed.id, created.body.id);
    assert.equal(claimed.shell, 'powershell');
    assert.equal((await req('/api/console/next', 'POST', {}, first)).body.job, null);
    const listed = (await req(route)).body.jobs[0];
    assert.equal(listed.status, 'running');
    assert.equal('lease' in listed, false);
    const resultRoute = '/api/console/result/' + claimed.id,
      result = {
        status: 'completed',
        exit_code: 0,
        stdout: 'hello\r\n',
        stderr: '',
        truncated: false,
        lease: claimed.lease,
      };
    assert.equal((await req(resultRoute, 'POST', result, second)).status, 400);
    assert.equal(
      (await req(resultRoute, 'POST', { ...result, lease: 'wrong' }, first)).status,
      400,
    );
    assert.equal(
      (await req(resultRoute, 'POST', { ...result, stdout: 'a'.repeat(71000) }, first)).status,
      400,
    );
    assert.equal((await req(resultRoute, 'POST', result, first)).status, 200);
    assert.equal((await req(resultRoute, 'POST', result, first)).status, 200);
    assert.equal(new ConsoleJobs(store).list('term1')[0].stdout, 'hello\r\n');
    const queued = await req(route, 'POST', { command: 'Get-Date' });
    assert.equal((await req(route + '/' + queued.body.id, 'DELETE')).status, 200);
    assert.equal((await req('/api/console/next', 'POST', {}, first)).body.job, null);
    store.setSettings('second', {
      display_name: 'Second',
      camera: '',
      microphone: '',
      speaker: '',
      command_shell: 'cmd',
    });
    const cmd = await req('/api/terminals/second/console', 'POST', { command: 'echo hello' });
    assert.equal(cmd.status, 201);
    store.setSettings('second', {
      display_name: 'Second',
      camera: '',
      microphone: '',
      speaker: '',
      command_shell: 'pwsh',
    });
    const cmdClaimed = (await req('/api/console/next', 'POST', {}, second)).body.job;
    assert.equal(cmdClaimed.shell, 'cmd');
    assert.equal((await req('/api/terminals/second/console')).body.jobs[0].shell, 'cmd');
    assert.equal(
      (
        await req(
          '/api/console/result/' + cmdClaimed.id,
          'POST',
          { ...result, lease: cmdClaimed.lease },
          second,
        )
      ).status,
      200,
    );
    await req('/api/terminals/second/console', 'POST', { command: '$PSVersionTable' });
    assert.equal((await req('/api/console/next', 'POST', {}, second)).body.job.shell, 'pwsh');
    const queue = new ConsoleJobs(store);
    queue.create('term1', { command: 'Write-Output once', timeout_seconds: 5 });
    queue.claim('term1');
    queue.jobs.at(-1).started_at = new Date(Date.now() - 60000).toISOString();
    queue.save();
    const reloaded = new ConsoleJobs(store);
    assert.equal(reloaded.list('term1').at(-1).status, 'lost');
    assert.equal(reloaded.claim('term1'), null);
  } finally {
    await fixture.close();
  }
});
