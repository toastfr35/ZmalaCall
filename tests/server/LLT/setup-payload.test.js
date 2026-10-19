// @test S-LLT-022
// @requirements LLR-SRV-ENROLL-002, LLR-SRV-ENROLL-003, LLR-SRV-ENROLL-004
// @environment portable
// @plan Generate setup payloads and PDF bytes directly; reject invalid Wi-Fi input, decode compact UTF-8 identity and inspect current setup instruction/privacy text, one A4 page and QR module geometry with its four-module quiet border.
// @pass All payload fields, validation cases and PDF structure assertions must pass; physical print readability remains a system check.

'use strict';
const test = require('node:test'),
  assert = require('node:assert/strict');
const { wifiPayload, serverPayload, setupPdf } = require('../../../zmala_server/setup-pdf');
const { inflateSync } = require('node:zlib');
const QRCode = require('../../../zmala_server/node_modules/qrcode');

test('printed instructions match current English setup screens and explain privacy', async (t) => {
  const PDFDocument = require('node:module').createRequire(
    require.resolve('../../../zmala_server/setup-pdf'),
  )('pdfkit');
  const original = PDFDocument.prototype.text;
  const text = [];
  t.mock.method(PDFDocument.prototype, 'text', function (...args) {
    text.push(args[0]);
    return original.apply(this, args);
  });
  for (const [kind, prompt, privacy] of [
    ['wifi', 'Scan the Wi-Fi QR code', 'This code contains the Wi-Fi password.'],
    ['server', 'Scan the server QR code', 'This code grants access to this account.'],
  ]) {
    text.length = 0;
    const pdf = await setupPdf({ kind, label: 'Fixture', payload: 'fixture' });
    assert.equal(pdf.subarray(0, 5).toString(), '%PDF-');
    assert.ok(
      text.some((line) => line.includes(`"${prompt}"`)),
      kind,
    );
    assert.ok(
      text.some((line) => line.includes(privacy) && line.includes('Keep this page private.')),
    );
    assert.ok(text.some((line) => line.includes('Print at actual size (100%).')));
  }
});

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
  const rectangles = [...page.matchAll(/([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) re\n/g)].map((m) =>
    m.slice(1).map(Number),
  );
  const [background, ...modules] = rectangles;
  const [x, y, width, height] = background;
  assert.equal(width, height);
  const unit = width / (qr.modules.size + 8);
  assert.ok(Math.abs(Math.min(...modules.map((r) => r[0])) - x - 4 * unit) < 0.001);
  assert.ok(Math.abs(Math.min(...modules.map((r) => r[1])) - y - 4 * unit) < 0.001);
  for (const [left, top, w, h] of modules) {
    assert.ok(left >= x + 4 * unit - 0.001 && top >= y + 4 * unit - 0.001);
    assert.ok(left + w <= x + width - 4 * unit + 0.016);
    assert.ok(top + h <= y + height - 4 * unit + 0.016);
  }
  assert.match(page, /\bBT\b/); // The page also contains the setup instructions.
});
test('enrollment contains versioned QR identity and compact Wi-Fi preserves UTF-8', () => {
  const enrollment = {
    server_url: 'http://192.168.1.81:8080',
    device_id: 'fixture-serial',
    device_token: 'fixture-token',
  };
  assert.deepEqual(JSON.parse(serverPayload(enrollment)), {
    type: 'family-call-server',
    version: 1,
    ...enrollment,
  });
  const input = { ssid: 'Café 日本語', password: 'fixture-password', hidden: true };
  const encoded = wifiPayload(input);
  const bytes = Buffer.from(encoded.split(':')[2], 'base64url');
  assert.equal(bytes[0], 3);
  assert.equal(bytes.subarray(2, 2 + bytes[1]).toString('utf8'), input.ssid);
  assert.equal(bytes.subarray(2 + bytes[1]).toString('utf8'), input.password);
});
