// @test S-HLT-026
// @requirements HLR-SRV-DIR-020
// @environment portable
// @plan On Linux with Pillow, upload real generated image bytes through the authenticated HTTP service and its production converter subprocess. Fetch and decode the published pixels, race duplicate uploads, reject malformed/oversized images, and inspect the photo directory after failure.
// @pass Published images retain expected pixels and fit 480 pixels; duplicates share a complete resource, invalid input never becomes a portrait, and converter failures leave no temporary files. Queue scheduling bounds are covered separately by LLT.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs/promises');
const path = require('node:path');
const { httpFixture } = require('../../support/server/http-fixture');

test(
  'HTTP portrait upload converts real pixels, deduplicates and cleans rejected input',
  { skip: process.platform !== 'linux', timeout: 15000 },
  async (t) => {
    const fixture = await httpFixture();
    t.after(() => fixture.close());
    const headers = {
      Authorization: 'Bearer ' + fixture.store.value.admin_token,
      'Content-Type': 'application/octet-stream',
    };
    const bytes = execFileSync('python3', [
      '-c',
      "from PIL import Image; import sys; Image.new('RGB',(960,480),(23,119,201)).save(sys.stdout.buffer,format='PNG')",
    ]);
    const upload = (body) => fetch(fixture.base + '/api/photos', { method: 'POST', headers, body });
    const responses = await Promise.all(Array.from({ length: 6 }, () => upload(bytes)));
    const names = [];
    for (const response of responses) {
      assert.equal(response.status, 201);
      names.push((await response.json()).photo);
    }
    assert.equal(new Set(names).size, 1);
    const downloaded = await fetch(fixture.base + names[0], { headers });
    assert.equal(downloaded.status, 200);
    const result = Buffer.from(await downloaded.arrayBuffer());
    const decoded = JSON.parse(
      execFileSync(
        'python3',
        [
          '-c',
          "from PIL import Image; import sys,io,json; im=Image.open(io.BytesIO(sys.stdin.buffer.read())); im.load(); print(json.dumps([im.size,im.convert('RGB').getpixel((0,0))]))",
        ],
        { input: result },
      ).toString(),
    );
    assert.deepEqual(decoded, [
      [480, 240],
      [23, 119, 201],
    ]);
    assert.equal((await upload(Buffer.from('not an image'))).status, 400);
    assert.equal((await upload(Buffer.alloc(2 * 1024 * 1024 + 1))).status, 413);
    // A valid dimension header with invalid compressed pixels reaches the real decoder.
    const corrupt = Buffer.from(bytes);
    corrupt.fill(0, 41, corrupt.length - 12);
    assert.equal((await upload(corrupt)).status, 400);
    assert.deepEqual(await fs.readdir(path.join(fixture.directory, 'photos')), [
      path.basename(names[0]),
    ]);
  },
);
