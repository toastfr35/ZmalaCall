// @test S-LLT-018
// @requirements LLR-SRV-DATA-014, LLR-SRV-DATA-015
// @environment portable
// @plan Delay and fail snapshot-file writes using temporary files and controlled promises; assert ordered atomic replacement, bounded latest pending snapshot, commit barriers and recovery on the next save.
// @pass Every named assertion must pass; failures or skips do not establish requirement verification.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { SnapshotFile } = require('../../../zmala_server/snapshot-file');

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
