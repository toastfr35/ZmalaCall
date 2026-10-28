// @test S-LLT-064
// @requirements LLR-SRV-DIR-033, LLR-SRV-DIR-035
// @environment portable
// @plan Build valid GIF blocks and corrupt headers, dimensions, frame rectangles, delays, trailer and subblocks. Check upload bypasses conversion on invalid input and publishes GIF output through a deduplicated converter.
// @pass Valid bounded frames pass inspection; malformed, excessive or truncated GIFs never reach conversion; immutable output retains its GIF extension and temporary files are removed.
'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { Readable } = require('node:stream');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { checkGif } = require('../../../zmala_server/portrait-gif');
const { PhotoStore } = require('../../../zmala_server/photos');
const { gif } = require('../../support/server/portrait-fixture');
test('GIF bounds inspect complete blocks before conversion', async () => {
  assert.deepEqual(checkGif(gif()), { width: 480, height: 480, frames: 2, duration: 200 });
  const bad = [
    gif(1),
    gif(73, 2),
    gif(3, 200),
    gif(2, 1),
    gif().subarray(0, -1),
    Buffer.concat([gif(), Buffer.from([0])]),
  ];
  for (const at of [6, 8, 19, 21, 27, 31, 33, 37, 38, 41]) {
    const bytes = Buffer.from(gif());
    bytes[at] = 255;
    bad.push(bytes);
  }
  const store = new PhotoStore('unused', async () => assert.fail('invalid GIF reached decoder'));
  for (const bytes of bad) {
    assert.throws(() => checkGif(bytes), /GIF/);
    await assert.rejects(store.upload(Readable.from([bytes])), /GIF/);
  }
});
test('GIF publication preserves format and shares duplicate conversion', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'zmala-gif-'));
  try {
    let calls = 0;
    const store = new PhotoStore(dir, async (_cmd, args) => {
      calls++;
      await new Promise((r) => setTimeout(r, 10));
      await fs.writeFile(args[args.indexOf('-Destination') + 1], gif());
    });
    const names = await Promise.all([
      store.upload(Readable.from([gif()])),
      store.upload(Readable.from([gif()])),
    ]);
    assert.equal(calls, 1);
    assert.equal(names[0], names[1]);
    assert.match(names[0], /^\/photos\/[a-f0-9]{64}\.gif$/);
    assert.deepEqual(await fs.readFile(path.join(dir, names[0])), gif());
    assert.equal((await fs.readdir(path.join(dir, 'photos'))).length, 1);
  } finally {
    await fs.rm(dir, { recursive: true, force: true });
  }
});
