// Optional PDF/native-decoder QA fixtures; no real credentials are included.
const fs = require('node:fs'),
  path = require('node:path'),
  QRCode = require('qrcode');
const {
  createCanvas,
  loadImage,
} = require('../../build_tools/runtime/pdf-render/node_modules/@napi-rs/canvas');
const { wifiPayload, serverPayload, setupPdf } = require('../setup-pdf');
(async () => {
  fs.mkdirSync('build_tools/tmp/pdfs', { recursive: true });
  const entries = [
    {
      kind: 'wifi',
      label: 'Café Test Network',
      payload: wifiPayload({ ssid: 'Café;Test 日本語', password: 'Test;Password123' }),
    },
    {
      kind: 'server',
      label: 'Test terminal',
      payload: serverPayload({
        server_url: 'http://127.0.0.1:8080',
        device_id: 'qr-test',
        device_token: 'test-device-token-0123456789abcdef',
      }),
    },
  ];
  for (const entry of entries) {
    const image = await loadImage(
        await QRCode.toBuffer(entry.payload, { width: 640, margin: 4, errorCorrectionLevel: 'M' }),
      ),
      canvas = createCanvas(640, 640);
    canvas.getContext('2d').drawImage(image, 0, 0);
    entry.image = path.resolve(`build_tools/tmp/pdfs/${entry.kind}-qr.jpg`);
    fs.writeFileSync(entry.image, canvas.toBuffer('image/jpeg'));
    fs.writeFileSync(`build_tools/tmp/pdfs/${entry.kind}-setup.pdf`, await setupPdf(entry));
  }
  fs.writeFileSync('build_tools/tmp/pdfs/manifest.json', JSON.stringify(entries));
  console.log('Created Wi-Fi and server PDF/QR QA fixtures.');
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
