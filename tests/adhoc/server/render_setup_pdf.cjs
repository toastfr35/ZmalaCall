const fs = require('node:fs'),
  path = require('node:path');
const canvas = require('../../../build_tools/runtime/pdf-render/node_modules/@napi-rs/canvas');
Object.assign(globalThis, {
  DOMMatrix: canvas.DOMMatrix,
  ImageData: canvas.ImageData,
  Path2D: canvas.Path2D,
});
(async () => {
  const pdfjs =
    await import('../../../build_tools/runtime/pdf-render/node_modules/pdfjs-dist/legacy/build/pdf.mjs');
  const entries = JSON.parse(
    fs.readFileSync(path.resolve('build_tools/tmp/pdfs/manifest.json'), 'utf8'),
  );
  for (const entry of entries) {
    const pdf = await pdfjs.getDocument({
      data: new Uint8Array(fs.readFileSync(`build_tools/tmp/pdfs/${entry.kind}-setup.pdf`)),
      useSystemFonts: true,
    }).promise;
    if (pdf.numPages !== 1) throw Error('PDF has unexpected extra pages');
    const page = await pdf.getPage(1),
      viewport = page.getViewport({ scale: 1.5 }),
      image = canvas.createCanvas(Math.ceil(viewport.width), Math.ceil(viewport.height));
    await page.render({ canvasContext: image.getContext('2d'), viewport }).promise;
    const file = path.resolve(`build_tools/tmp/pdfs/${entry.kind}-printed.png`);
    fs.writeFileSync(file, image.toBuffer('image/png'));
    entry.image = path.resolve(`build_tools/tmp/pdfs/${entry.kind}-printed.jpg`);
    fs.writeFileSync(entry.image, image.toBuffer('image/jpeg'));
    console.log('Rendered single A4 page:', entry.kind);
  }
  fs.writeFileSync('build_tools/tmp/pdfs/printed-manifest.json', JSON.stringify(entries));
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
