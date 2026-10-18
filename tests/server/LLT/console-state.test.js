// @test S-LLT-020
// @requirements SLLR074, SLLR075, SLLR076, SLLR077, SLLR078
// @environment portable
// @plan Exercise the command queue with fixed device identities and injected time; check admission bounds, captured shell, exclusive leases, wrong-owner rejection, UTF-8 output limits, lost executions, cancellation and bounded redacted history.
// @pass All queue transitions and boundary assertions must pass without executing any command or contacting a terminal.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { storeFixture } = require('../../support/server/unit-fixture');
const { ConsoleJobs } = require('../../../zmala_server/console-jobs');

test('admission captures shell, limits pending jobs, and only one owned lease runs', (t) => {
  const s = storeFixture(t),
    q = new ConsoleJobs(s);
  s.createAccount({ id: 'second', type: 'terminal', name: 'Second', emails: ['a@example.test'] });
  for (const value of [
    { command: '' },
    { command: 'x\0' },
    { command: 'x'.repeat(8001) },
    ...[4, 121, 5.5, '5'].map((timeout_seconds) => ({ command: 'x', timeout_seconds })),
  ])
    assert.throws(() => q.create('term1', value));
  s.value.profiles.term1.command_shell = 'sh';
  const job = q.create('term1', { command: 'echo fixture', timeout_seconds: 5 });
  s.value.profiles.term1.command_shell = 'bash';
  assert.equal(q.claim('second'), null);
  const lease = q.claim('term1');
  assert.equal(lease.shell, 'sh');
  assert.ok(lease.lease.length >= 32);
  assert.equal(q.claim('term1'), null);
  assert.ok(!('lease' in q.list('term1')[0]));
  for (let n = 1; n < 10; n++) q.create('term1', { command: 'true', timeout_seconds: 120 });
  assert.throws(() => q.create('term1', { command: 'true' }), /10 pending/);
  assert.throws(() => q.cancel('term1', job.id), /queued/);
  q.cancel('term1', q.jobs.at(-1).id);
  assert.equal(q.jobs.at(-1).status, 'cancelled');
});

test('results enforce serial, lease and combined UTF-8 bytes; retries do not change result', (t) => {
  const s = storeFixture(t),
    q = new ConsoleJobs(s);
  s.createAccount({ id: 'second', type: 'terminal', name: 'Second', emails: ['a@example.test'] });
  q.create('term1', { command: 'true' });
  const job = q.claim('term1');
  const result = {
    ...job,
    status: 'completed',
    exit_code: 0,
    stdout: 'é'.repeat(32768),
    stderr: '',
    truncated: false,
  };
  assert.throws(() => q.finish('second', job.id, result));
  assert.throws(() => q.finish('term1', job.id, { ...result, lease: 'wrong' }));
  assert.throws(() => q.finish('term1', job.id, { ...result, stderr: 'x' }));
  assert.equal(q.jobs[0].status, 'running');
  q.finish('term1', job.id, result);
  q.finish('term1', job.id, { ...result, stdout: 'different' });
  assert.equal(q.jobs[0].stdout, result.stdout);
  assert.equal(new ConsoleJobs(s).jobs[0].status, 'completed');
});

test('unknown, retired and timed-out executions cannot be claimed again; history stays bounded', (t) => {
  const s = storeFixture(t),
    q = new ConsoleJobs(s);
  q.create('term1', { command: 'true', timeout_seconds: 5 });
  q.claim('term1');
  const start = Date.parse(q.jobs[0].started_at);
  const now = t.mock.method(Date, 'now', () => start + 50000);
  q.expire();
  assert.equal(q.jobs[0].status, 'running');
  now.mock.mockImplementation(() => start + 50001);
  q.expire();
  assert.equal(q.jobs[0].status, 'lost');
  assert.equal(q.claim('term1'), null);
  q.create('term1', { command: 'true' });
  delete q.jobs.at(-1).device_id;
  q.expire();
  assert.equal(q.jobs.at(-1).status, 'cancelled');
  q.jobs = Array.from({ length: 210 }, (_, n) => ({
    ...q.jobs[0],
    id: String(n),
    status: 'completed',
  }));
  q.create('term1', { command: 'pending' });
  assert.equal(q.jobs.filter((j) => j.status === 'completed').length, 200);
  assert.equal(q.jobs.filter((j) => j.status === 'queued').length, 1);
  assert.equal(q.list('term1').length, 50);
  s.value.users.term1.device_id = 'replacement';
  q.expire();
  assert.equal(q.jobs.at(-1).status, 'cancelled');
});
