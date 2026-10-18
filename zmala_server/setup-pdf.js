'use strict';
// Payloads match zmala_terminal/common/provisioning.py; PDFs carry private Wi-Fi or enrollment credentials.
const QRCode = require('qrcode');
const PDFDocument = require('pdfkit');

// @llr LLR-SRV-ENROLL-003
/** @param {import('./types/contracts').JsonObject} update @returns {string} */
function wifiPayload({ ssid, password = '', security = 'WPA', hidden = false }) {
  if (
    typeof ssid !== 'string' ||
    !ssid ||
    Buffer.byteLength(ssid, 'utf8') > 32 ||
    /[\x00-\x1f\x7f]/.test(ssid)
  )
    throw Error('SSID must contain 1–32 UTF-8 bytes without control characters.');
  if ((security !== 'WPA' && security !== 'nopass') || typeof hidden !== 'boolean')
    throw Error('Choose WPA/WPA2/WPA3 or an open network.');
  if (typeof password !== 'string' || /[\x00-\x1f\x7f]/.test(password))
    throw Error('Invalid Wi-Fi password.');
  if (
    security === 'WPA' &&
    !(
      (password.length >= 8 && password.length <= 63 && /^[\x20-\x7e]+$/.test(password)) ||
      /^[a-fA-F0-9]{64}$/.test(password)
    )
  )
    throw Error('Wi-Fi passwords must be 8–63 ASCII characters, or a 64-digit hexadecimal key.');
  if (security === 'nopass' && password) throw Error('Open networks do not have a password.');
  /** @param {string} value */
  const escape = (value) => value.replace(/[\\;,:"]/g, '\\$&');
  const standard = `WIFI:T:${security};S:${escape(ssid)};P:${escape(password)};H:${hidden};;`;
  // The Windows SDK decoder has a 254-byte result and locale conversion.
  // ASCII packaging preserves every UTF-8 SSID without either limitation.
  if (/^[\x00-\x7f]+$/.test(standard) && Buffer.byteLength(standard) <= 254) return standard;
  const name = Buffer.from(ssid, 'utf8'),
    flags = (security === 'WPA' ? 1 : 0) | (hidden ? 2 : 0);
  return (
    'FAMILY-WIFI:1:' +
    Buffer.concat([
      Buffer.from([flags, name.length]),
      name,
      Buffer.from(password, 'utf8'),
    ]).toString('base64url')
  );
}
// @llr LLR-SRV-ENROLL-004
/** @param {import('./types/contracts').Enrollment} bootstrap */
function serverPayload(bootstrap) {
  return JSON.stringify({ type: 'family-call-server', version: 1, ...bootstrap });
}
// @llr LLR-SRV-ENROLL-002
/** @param {{kind: 'wifi' | 'server', label: string, payload: string, serverUrl?: string}} options
 * @returns {Promise<Buffer>} */
async function setupPdf({ kind, label, payload, serverUrl }) {
  const qr = QRCode.create(payload, { errorCorrectionLevel: 'M' }),
    doc = new PDFDocument({
      size: 'A4',
      margin: 48,
      info: { Title: `ZmalaCall - ${kind} setup`, Author: 'ZmalaCall' },
    });
  /** @type {Buffer[]} */
  const chunks = [];
  /** @type {Promise<Buffer>} */
  const result = new Promise((resolve, reject) => {
    doc.on('data', (c) => chunks.push(c));
    doc.on('end', () => resolve(Buffer.concat(chunks)));
    doc.on('error', reject);
  });
  const width = doc.page.width - 96;
  doc.fillColor('#586276').fontSize(11).text('ZMALACALL  /  TERMINAL SETUP', 48, 48, { width });
  doc
    .fillColor('#111827')
    .fontSize(30)
    .text(kind === 'wifi' ? '1. Wi-Fi connection' : '2. Server connection', 48, 85, { width });
  doc.fontSize(16).text(label, 48, 133, { width, height: 66, ellipsis: true });
  const size = 340,
    x = (doc.page.width - size) / 2,
    y = 220,
    unit = size / (qr.modules.size + 8);
  doc.rect(x, y, size, size).fill('#ffffff');
  doc.fillColor('#000000');
  for (let row = 0; row < qr.modules.size; row++)
    for (let col = 0; col < qr.modules.size; col++)
      if (qr.modules.get(row, col))
        doc.rect(x + (col + 4) * unit, y + (row + 4) * unit, unit + 0.015, unit + 0.015);
  doc.fill();
  doc
    .fillColor('#111827')
    .fontSize(17)
    .text('Show this QR code to the terminal camera.', 48, 595, { width, align: 'center' });
  doc
    .fillColor('#586276')
    .fontSize(11)
    .text(
      kind === 'wifi'
        ? 'Use when the screen says "Scan the Wi-Fi QR code".'
        : 'Use after Wi-Fi setup, when the screen says "Scan the server QR code".',
      48,
      630,
      { width, align: 'center' },
    );
  if (serverUrl) doc.fontSize(10).text(serverUrl, 48, 669, { width, align: 'center' });
  doc
    .fontSize(10)
    .text(
      'Print at actual size (100%). Keep the full code and its white border visible.',
      48,
      710,
      { width, align: 'center' },
    );
  doc
    .fontSize(10)
    .text(
      kind === 'wifi'
        ? 'This code contains the Wi-Fi password. Keep this page private.'
        : 'This code grants access to this terminal account. Keep this page private.',
      48,
      742,
      { width, align: 'center' },
    );
  doc.end();
  return result;
}
module.exports = { wifiPayload, serverPayload, setupPdf };
