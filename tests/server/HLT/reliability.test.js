// @test S-HLT-015
// @requirements HLR-SRV-MAINT-011, HLR-SRV-DATA-012
// @environment portable
// @plan Reassign accounts during maintenance jobs and inject storage errors through the assembled HTTP application; assert execution ownership never follows a recycled name and result retries remain durable without blocking reads.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const { httpFixture } = require('../../support/server/http-fixture');
const { ConsoleJobs } = require('../../../zmala_server/console-jobs');

test('command ownership cannot follow a recycled username or account type', async () => {
  const f = await httpFixture();
  const request = (method, route, value) =>
    fetch(f.base + route, {
      method,
      headers: { Authorization: 'Bearer ' + f.store.value.admin_token },
      body: value && JSON.stringify(value),
    });
  try {
    for (const retirement of ['delete', 'convert']) {
      const job = f.consoleJobs.create('term1', { command: 'echo original device' });
      const serial = job.device_id;
      await f.consoleJobs.flush();
      if (retirement === 'delete') {
        assert.equal((await request('DELETE', '/api/users/term1')).status, 200);
        assert.equal(
          (
            await request('POST', '/api/users', {
              id: 'term1',
              name: 'Replacement',
              type: 'terminal',
              emails: ['fixture@example.test'],
            })
          ).status,
          201,
        );
      } else {
        assert.equal(
          (await request('PUT', '/api/users/term1', { name: 'Phone', type: 'linphone' })).status,
          200,
        );
        assert.equal(
          (await request('PUT', '/api/users/term1', { name: 'Replacement', type: 'terminal' }))
            .status,
          200,
        );
      }
      assert.notEqual(f.store.terminalAccount('term1').device_id, serial);
      assert.equal(f.consoleJobs.claim('term1'), null);
      assert.deepEqual(f.consoleJobs.list('term1'), []);
      assert.equal(job.status, 'cancelled');
    }
    const legacy = f.consoleJobs.create('term1', { command: 'echo legacy' });
    delete legacy.device_id;
    f.consoleJobs.save();
    await f.consoleJobs.flush();
    const reloaded = new ConsoleJobs(f.store);
    assert.equal(reloaded.claim('term1'), null);
    assert.deepEqual(reloaded.list('term1'), []);
    assert.equal(reloaded.jobs.at(-1).status, 'cancelled');
  } finally {
    await f.close();
  }
});

test('result retry commits after disk failure while unrelated device reads remain available', async (t) => {
  const f = await httpFixture();
  const token = f.store.value.users.term1.device_token;
  const request = (route, result) =>
    fetch(f.base + route, {
      method: result ? 'POST' : 'GET',
      headers: { Authorization: 'Bearer ' + token },
      body: result && JSON.stringify(result),
    });
  const write = fs.writeFile;
  let failing = false;
  const mock = t.mock.method(fs, 'writeFile', (file, ...args) => {
    if (failing && file === f.consoleJobs.file + '.tmp')
      return Promise.reject(Error('disk unavailable'));
    return write(file, ...args);
  });
  try {
    f.consoleJobs.create('term1', { command: 'echo once' });
    const job = f.consoleJobs.claim('term1');
    await f.consoleJobs.flush();
    const result = {
      lease: job.lease,
      status: 'completed',
      exit_code: 0,
      stdout: '\0'.repeat(65536),
      stderr: '',
      truncated: false,
    };
    const route = '/api/console/result/' + job.id;
    failing = true;
    assert.equal((await request(route, result)).status, 500);
    assert.equal((await request(route, result)).status, 500);
    assert.equal((await request('/api/config')).status, 200);
    assert.equal((await request('/health')).status, 200);
    assert.equal((await request('/ready')).status, 503);
    assert.equal(JSON.parse(await fs.readFile(f.consoleJobs.file)).at(-1).status, 'running');
    failing = false;
    const responses = await Promise.all([request(route, result), request(route, result)]);
    assert.deepEqual(
      responses.map((r) => r.status),
      [200, 200],
    );
    assert.equal((await request('/ready')).status, 200);
    assert.equal(new ConsoleJobs(f.store).list('term1')[0].stdout, result.stdout);
    const next = f.consoleJobs.create('term1', { command: 'echo next' });
    assert.equal(f.consoleJobs.claim('term1').id, next.id);
  } finally {
    failing = false;
    mock.mock.restore();
    await f.close();
  }
});
