'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { SnapshotFile } = require('../snapshot-file');
const { httpFixture } = require('./http-fixture');

test('snapshot writes commit in order and recover after a failed save', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'zmala-snapshot-'));
  try {
    const file = path.join(directory, 'server.json');
    const writer = new SnapshotFile(file);
    const first = writer.write('{"revision":1}');
    const second = writer.write('{"revision":2}');
    await Promise.all([first, second, writer.flush()]);
    assert.deepEqual(JSON.parse(await fs.readFile(file, 'utf8')), { revision: 2 });
    await assert.rejects(fs.stat(file + '.tmp'), { code: 'ENOENT' });

    const unavailable = path.join(directory, 'unavailable');
    const retry = new SnapshotFile(path.join(unavailable, 'state.json'));
    await assert.rejects(retry.write('old'), { status: 500 });
    await assert.rejects(retry.flush(), { status: 500 });
    await fs.mkdir(unavailable);
    await retry.write('new');
    await retry.flush();
    assert.equal(await fs.readFile(retry.file, 'utf8'), 'new');
  } finally {
    await fs.rm(directory, { recursive: true, force: true });
  }
});

test('slow storage retains only the latest queued snapshot and delays every acknowledgement', async (t) => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'zmala-coalesce-'));
  const writer = new SnapshotFile(path.join(directory, 'state.json'));
  let release,
    entered,
    writes = 0;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const started = new Promise((resolve) => {
    entered = resolve;
  });
  const original = fs.writeFile;
  const mock = t.mock.method(fs, 'writeFile', async (file, ...args) => {
    if (file === writer.file + '.tmp') {
      writes++;
      if (writes === 1) {
        entered();
        await gate;
      }
    }
    return original(file, ...args);
  });
  try {
    const first = writer.write('first');
    await started;
    const pending = Array.from({ length: 200 }, (_, revision) => writer.write(String(revision)));
    assert.equal(new Set(pending).size, 1);
    assert.equal(writer.queued.contents, '199');
    let acknowledged = false;
    pending.at(-1).then(() => {
      acknowledged = true;
    });
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(acknowledged, false);
    release();
    await Promise.all([first, ...pending]);
    assert.equal(writes, 2);
    assert.equal(await fs.readFile(writer.file, 'utf8'), '199');
  } finally {
    release();
    await writer.flush();
    mock.mock.restore();
    await fs.rm(directory, { recursive: true, force: true });
  }
});

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
