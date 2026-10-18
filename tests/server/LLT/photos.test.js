// @test S-LLT-005
// @requirements LLR-SRV-DIR-033, LLR-SRV-DIR-034, LLR-SRV-DIR-035
// @environment portable
// @plan Inject delayed converters and malformed/oversized image input into PhotoStore; assert concurrency and queue limits, deduplicated atomic output and temporary-file cleanup. Probe JPEG marker lengths, standalone markers, truncated frames and excessive dimensions; assert access failures propagate and pending publication state clears.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { Readable } = require('node:stream');
const { PhotoStore } = require('../../../zmala_server/photos');
const { checkDimensions } = require('../../../zmala_server/photos');
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a/A8AAAAASUVORK5CYII=',
  'base64',
);

test('JPEG marker parsing accepts frame dimensions and rejects truncated, missing or excessive frames', async () => {
  const frame = (width, height) => {
    const bytes = Buffer.from([255, 192, 0, 8, 8, 0, 0, 0, 0, 0]);
    bytes.writeUInt16BE(height, 5);
    bytes.writeUInt16BE(width, 7);
    return bytes;
  };
  const jpeg = (...segments) => Buffer.concat([Buffer.from([255, 216]), ...segments]);
  const valid = jpeg(Buffer.from([255, 224, 0, 4, 0, 0, 255, 1, 255, 208]), frame(1920, 1080));
  checkDimensions(valid, 'jpg');
  checkDimensions(jpeg(Buffer.from([255]), frame(640, 480)), 'jpg');
  for (const bytes of [
    jpeg(Buffer.from([255, 218, 0, 2])),
    jpeg(Buffer.from([255, 217, 0, 2])),
    jpeg(Buffer.from([255, 224, 0, 1])),
    jpeg(Buffer.from([255, 224, 0, 8])),
    jpeg(Buffer.from([255, 255, 255, 224, 0])),
    jpeg(frame(0, 480)),
    jpeg(frame(8193, 10)),
    jpeg(frame(4096, 4096)),
    Buffer.from([255, 216]),
  ])
    assert.throws(() => checkDimensions(bytes, 'jpg'), /16 megapixels/);
  const store = new PhotoStore('unused', async () =>
    assert.fail('invalid input reached converter'),
  );
  await assert.rejects(store.upload(Readable.from([Buffer.from('not an image')])), /PNG or JPEG/);
  assert.equal(store.uploads, 0);
});

test('photo publication propagates access errors and clears the pending commit', async (t) => {
  const store = new PhotoStore('unused');
  t.mock.method(fs, 'access', async () => {
    throw Object.assign(Error('read denied'), { code: 'EACCES' });
  });
  const rename = t.mock.method(fs, 'rename', async () => {});
  await assert.rejects(store.publish('temporary.png', 'target.png'), /read denied/);
  assert.equal(rename.mock.callCount(), 0);
  assert.equal(store.publishing.size, 0);
});

test('concurrent photo conversion yields to other work, deduplicates output and cleans temporary files', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'zmala-photo-'));
  const sources = new Set();
  const gates = [];
  const store = new PhotoStore(directory, async (_executable, args) => {
    assert.equal(_executable, 'python3');
    assert.equal(path.basename(args[0]), 'convert-photo.py');
    const source = args[args.indexOf('-Source') + 1];
    const destination = args[args.indexOf('-Destination') + 1];
    sources.add(source);
    await new Promise((resolve) => gates.push(resolve));
    await fs.writeFile(destination, PNG);
  });
  try {
    const first = store.upload(Readable.from([PNG]));
    const second = store.upload(Readable.from([PNG]));
    await new Promise((resolve, reject) => {
      const deadline = Date.now() + 2000;
      const inspect = () =>
        gates.length === 1
          ? resolve()
          : Date.now() > deadline
            ? reject(Error('Photo conversion did not yield'))
            : setTimeout(inspect, 5);
      inspect();
    });
    assert.equal(sources.size, 1, 'Identical uploads must share one conversion');
    gates.forEach((resolve) => resolve());
    const [a, b] = await Promise.all([first, second]);
    assert.equal(a, b);
    assert.match(a, /^\/photos\/[a-f0-9]{64}\.png$/);
    assert.equal((await fs.readdir(store.directory)).length, 1);
    const cached = path.join(directory, a.slice(1));
    const original = await fs.stat(cached);
    await fs.chmod(cached, 0o444);
    const repeat = new PhotoStore(directory, async (_executable, args) => {
      await fs.writeFile(args[args.indexOf('-Destination') + 1], PNG);
    });
    try {
      assert.equal(await repeat.upload(Readable.from([PNG])), a);
      assert.equal(
        (await fs.stat(cached)).mtimeMs,
        original.mtimeMs,
        'A repeated upload must reuse the existing photo',
      );
    } finally {
      await fs.chmod(cached, 0o666);
    }
    const failing = new PhotoStore(directory, async () => {
      throw Error('conversion failed');
    });
    await assert.rejects(failing.upload(Readable.from([PNG])), /conversion failed/);
    assert.equal((await fs.readdir(store.directory)).length, 1);
  } finally {
    await fs.rm(directory, { recursive: true, force: true });
  }
});

test('photo bursts cap subprocesses and outstanding uploads and reject oversized dimensions', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'zmala-photo-bounds-'));
  let release,
    started,
    active = 0,
    peak = 0;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const ready = new Promise((resolve) => {
    started = resolve;
  });
  const store = new PhotoStore(directory, async (_executable, args) => {
    active++;
    peak = Math.max(peak, active);
    if (active === 2) started();
    await gate;
    await fs.writeFile(args[args.indexOf('-Destination') + 1], PNG);
    active--;
  });
  const uploads = Array.from({ length: 10 }, (_, index) =>
    store.upload(Readable.from([Buffer.concat([PNG, Buffer.from([index])])])),
  );
  try {
    await ready;
    await assert.rejects(store.upload(Readable.from([PNG])), { status: 429 });
    release();
    await Promise.all(uploads);
    assert.equal(peak, 2);
    assert.equal(store.uploads, 0);
    assert.equal(store.converting.size, 0);
    const huge = Buffer.from(PNG);
    huge.writeUInt32BE(100000, 16);
    await assert.rejects(store.upload(Readable.from([huge])), /16 megapixels/);
    assert.equal((await fs.readdir(store.directory)).length, 1);
  } finally {
    release();
    await Promise.allSettled(uploads);
    await fs.rm(directory, { recursive: true, force: true });
  }
});
