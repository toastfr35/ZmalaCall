// Rasterize the code-native SVG for Tk's Windows window/taskbar icon.
const fs = require('node:fs'),
  path = require('node:path');
const { createCanvas, loadImage } = require('./runtime/pdf-render/node_modules/@napi-rs/canvas');
(async () => {
  const root = path.resolve(__dirname, '..'),
    image = await loadImage(fs.readFileSync(path.join(root, 'zmala_server/assets/zmala-icon.svg'))),
    canvas = createCanvas(256, 256);
  canvas.getContext('2d').drawImage(image, 0, 0, 256, 256);
  fs.writeFileSync(
    path.join(root, 'zmala_terminal/assets/zmala-icon.png'),
    canvas.toBuffer('image/png'),
  );
})();
