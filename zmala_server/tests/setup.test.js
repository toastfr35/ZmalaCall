'use strict';
const { httpFixture } = require('./http-fixture');
const test = require('node:test'),
  assert = require('node:assert/strict'),
  fs = require('node:fs'),
  path = require('node:path');
const { wifiPayload, serverPayload, setupPdf } = require('../setup-pdf');
const { inflateSync } = require('node:zlib');
const QRCode = require('qrcode');

test('Wi-Fi QR escaping, validation and printable PDF', async () => {
  const input = { ssid: 'Cafe;Wi:Fi\\"', password: 'Secret;:\\,"', hidden: true };
  const payload = wifiPayload(input);
  assert.match(payload, /^WIFI:T:WPA;/);
  assert.ok(payload.includes('Cafe\\;Wi\\:Fi\\\\\\"'));
  assert.ok(payload.includes('H:true;;'));
  assert.match(wifiPayload({ ...input, ssid: 'Café 日本語' }), /^FAMILY-WIFI:1:/);
  assert.equal(
    wifiPayload({ ssid: 'Open', security: 'nopass' }),
    'WIFI:T:nopass;S:Open;P:;H:false;;',
  );
  for (const bad of [
    { ssid: '' },
    { ssid: '界'.repeat(11) },
    { ssid: 'Name', password: 'short' },
    { ssid: 'Name', password: '秘密密码' },
    { ssid: 'Name', security: 'nopass', password: 'secret' },
    { ssid: 'a\n', security: 'nopass' },
  ])
    assert.throws(() => wifiPayload(bad));
  const pdf = await setupPdf({ kind: 'wifi', label: input.ssid, payload });
  assert.equal(pdf.subarray(0, 5).toString(), '%PDF-');
  // PDF byte size says
  // nothing about whether the page and its QR code were actually generated.
  const source = pdf.toString('latin1');
  assert.match(source, /%%EOF\s*$/);
  assert.equal((source.match(/\/Type \/Page\b/g) || []).length, 1);
  assert.match(source, /\/MediaBox \[0 0 595\.28 841\.89\]/);
  const streams = [...source.matchAll(/<<(.*?)>>\s*stream\r?\n(.*?)\r?\nendstream/gs)]
    .filter((match) => match[1].includes('/FlateDecode'))
    .map((match) => inflateSync(Buffer.from(match[2], 'latin1')).toString('latin1'));
  const page = streams.find((stream) => stream.includes(' re\n'));
  assert.ok(page, 'Missing QR drawing commands');
  const qr = QRCode.create(payload, { errorCorrectionLevel: 'M' });
  const darkModules = [...qr.modules.data].filter(Boolean).length;
  assert.equal((page.match(/ re\n/g) || []).length, darkModules + 1);
  assert.match(page, /\bBT\b/); // The page also contains the setup instructions.
});
test('QR PDF endpoints require admin, target terminal accounts and do not persist Wi-Fi secrets', async () => {
  const fixture = await httpFixture();
  const { store, base, directory: dir } = fixture;
  async function req(route, method = 'GET', value, token = store.value.admin_token) {
    return fetch(base + route, {
      method,
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: value ? JSON.stringify(value) : undefined,
    });
  }
  try {
    assert.equal(
      (await req('/api/setup/server.pdf?id=term1', 'GET', undefined, 'wrong')).status,
      401,
    );
    assert.equal(
      (
        await req(
          '/api/setup/server.pdf?id=term1',
          'GET',
          undefined,
          store.value.users.term1.device_token,
        )
      ).status,
      401,
    );
    assert.equal((await req('/api/setup/server.pdf?id=phone1')).status, 400);
    const r = await req('/api/setup/server.pdf?id=term1');
    assert.equal(r.status, 200);
    assert.equal(r.headers.get('content-type'), 'application/pdf');
    assert.match(r.headers.get('content-disposition'), /attachment/);
    assert.equal(
      Buffer.from(await r.arrayBuffer())
        .subarray(0, 5)
        .toString(),
      '%PDF-',
    );
    const payload = JSON.parse(serverPayload(store.bootstrap('term1')));
    assert.equal(payload.device_token, store.value.users.term1.device_token);
    assert.equal(payload.device_id, store.value.users.term1.device_id);
    assert.equal(payload.type, 'family-call-server');
    assert.equal(payload.version, 1);
    const before = JSON.stringify(store.value),
      wifi = await req('/api/setup/wifi.pdf', 'POST', {
        ssid: 'Family Test',
        password: 'QrTestPassword',
      });
    assert.equal(wifi.status, 200);
    assert.equal(JSON.stringify(store.value), before);
    assert.equal(
      fs.readFileSync(path.join(dir, 'terminal.json'), 'utf8').includes('QrTestPassword'),
      false,
    );
    assert.equal(
      (await req('/api/setup/wifi.pdf', 'POST', { ssid: 'Test', password: 'wrong' })).status,
      400,
    );
  } finally {
    await fixture.close();
  }
});
