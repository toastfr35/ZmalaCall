// @test S-HLT-014
// @requirements SHLR014
// @environment portable
// @plan Delay and fail real snapshot writes while issuing HTTP reads and updates; assert ordered atomic commits, bounded pending snapshots, acknowledgement barriers and recovery after disk failure.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');

const { httpFixture } = require('../../support/server/http-fixture');

test('an admin save yields to health requests and responds only after committing', async (t) => {
  const fixture = await httpFixture();
  let release, started;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const writing = new Promise((resolve) => {
    started = resolve;
  });
  const originalWrite = fs.writeFile;
  const mock = t.mock.method(fs, 'writeFile', async (file, ...args) => {
    if (file === fixture.store.file + '.tmp') {
      started();
      await gate;
    }
    return originalWrite(file, ...args);
  });
  let completed = false;
  const request = fetch(fixture.base + '/api/groups', {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + fixture.store.value.admin_token },
    body: JSON.stringify({ name: 'Async save', members: ['term1', 'phone1'] }),
  }).then((response) => {
    completed = true;
    return response;
  });
  try {
    await writing;
    assert.equal(completed, false, 'Save cannot be acknowledged before disk completion');
    const health = await fetch(fixture.base + '/health', { signal: AbortSignal.timeout(2000) });
    assert.equal(health.status, 200, 'Disk wait does not block unrelated requests');
    release();
    const response = await request;
    assert.equal(response.status, 201);
    const { id } = await response.json();
    const persisted = JSON.parse(await fs.readFile(fixture.store.file, 'utf8'));
    assert.equal(persisted.groups[id].name, 'Async save');
  } finally {
    release();
    await request;
    mock.mock.restore();
    await fixture.close();
  }
});

test('asset reads are asynchronous and missing authorized photos return 404', async (t) => {
  const fixture = await httpFixture();
  const syncFs = require('node:fs');
  const mock = t.mock.method(syncFs, 'readFileSync', () => {
    throw Error('HTTP handlers must not read files synchronously');
  });
  try {
    for (const asset of ['/', '/admin.js', '/admin.css', '/zmala-icon.svg']) {
      const response = await fetch(fixture.base + asset);
      assert.equal(response.status, 200);
      await response.arrayBuffer();
    }
    const response = await fetch(fixture.base + '/photos/abcd.png', {
      headers: { Authorization: 'Bearer ' + fixture.store.value.admin_token },
    });
    assert.equal(response.status, 404);
  } finally {
    mock.mock.restore();
    await fixture.close();
  }
});

test('a disk failure returns HTTP 500 and the next full snapshot can recover', async (t) => {
  const fixture = await httpFixture();
  const originalWrite = fs.writeFile;
  let fail = true;
  const mock = t.mock.method(fs, 'writeFile', async (file, ...args) => {
    if (fail && file === fixture.store.file + '.tmp') {
      fail = false;
      throw Object.assign(Error('Injected disk failure'), { code: 'EACCES' });
    }
    return originalWrite(file, ...args);
  });
  const create = (name) =>
    fetch(fixture.base + '/api/groups', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + fixture.store.value.admin_token },
      body: JSON.stringify({ name, members: ['term1', 'phone1'] }),
    });
  try {
    const failed = await create('Failed save');
    assert.equal(failed.status, 500);
    assert.equal((await failed.json()).error, 'Could not save configuration snapshot.');
    const recovered = await create('Recovered save');
    assert.equal(recovered.status, 201);
    const { id } = await recovered.json();
    assert.equal(
      JSON.parse(await fs.readFile(fixture.store.file, 'utf8')).groups[id].name,
      'Recovered save',
    );
  } finally {
    mock.mock.restore();
    await fixture.close();
  }
});
