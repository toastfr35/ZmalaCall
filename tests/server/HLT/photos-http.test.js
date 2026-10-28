// @test S-HLT-026
// @requirements HLR-SRV-DIR-020
// @environment portable
// @plan On Linux with Pillow, upload real generated image bytes through the authenticated HTTP service and its production converter subprocess. Fetch and decode the published pixels, race duplicate uploads, reject malformed/oversized images, and inspect the photo directory after failure. Upload a looping GIF, inspect normalized frames and MIME/authentication, and create an account using its URL.
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

test(
  'animated account portrait survives upload, publication and account creation',
  { skip: process.platform !== 'linux', timeout: 15000 },
  async (t) => {
    const fixture = await httpFixture();
    t.after(() => fixture.close());
    const headers = {
      Authorization: 'Bearer ' + fixture.store.value.admin_token,
      'Content-Type': 'application/octet-stream',
    };
    const input = execFileSync('python3', [
      '-c',
      "from PIL import Image; import sys; a=Image.new('RGB',(720,720),'red'); b=Image.new('RGB',(720,720),'blue'); a.save(sys.stdout.buffer,format='GIF',save_all=True,append_images=[b],duration=100,loop=0)",
    ]);
    const upload = await fetch(fixture.base + '/api/photos', {
      method: 'POST',
      headers,
      body: input,
    });
    assert.equal(upload.status, 201);
    const { photo } = await upload.json();
    assert.match(photo, /\.gif$/);
    assert.equal((await fetch(fixture.base + photo)).status, 401);
    const response = await fetch(fixture.base + photo, { headers });
    assert.equal(response.headers.get('content-type'), 'image/gif');
    const bytes = Buffer.from(await response.arrayBuffer());
    const decoded = JSON.parse(
      execFileSync(
        'python3',
        [
          '-c',
          "from PIL import Image; import sys,io,json; im=Image.open(io.BytesIO(sys.stdin.buffer.read())); print(json.dumps([im.size,im.n_frames,'loop' in im.info]))",
        ],
        { input: bytes },
      ),
    );
    assert.deepEqual(decoded, [[480, 480], 2, false]);
    const created = await fetch(fixture.base + '/api/users', {
      method: 'POST',
      headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: 'animated',
        name: 'Animated',
        type: 'app',
        emails: ['animated@example.test'],
        photo,
        configuration_version: fixture.store.value.configuration_version,
      }),
    });
    assert.equal(created.status, 201);
    assert.equal(fixture.store.value.users.animated.photo, photo);
  },
);
