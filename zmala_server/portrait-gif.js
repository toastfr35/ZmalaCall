// Inspect GIF blocks without decoding compressed pixels; Pillow validates pixels later.
'use strict';
const MAX_GIF_BYTES = 16 * 1024 * 1024;
const GIF_RULES =
  'GIF must be square, 480–1024 pixels per side, 2–72 frames and at most 5 seconds (up to 16 MiB).';
// @llr LLR-SRV-DIR-033
/** @param {Buffer} data */
function checkGif(data) {
  const invalid = () => {
    throw Error(GIF_RULES);
  };
  if (
    data.length < 14 ||
    data.length > MAX_GIF_BYTES ||
    !/^GIF8[79]a$/.test(data.toString('ascii', 0, 6))
  )
    invalid();
  const width = data.readUInt16LE(6),
    height = data.readUInt16LE(8);
  if (width !== height || width < 480 || width > 1024) invalid();
  let offset = 13 + (data[10] & 128 ? 3 * 2 ** ((data[10] & 7) + 1) : 0);
  let frames = 0,
    duration = 0,
    delay = 100;
  const blocks = () => {
    let size;
    do {
      if (offset >= data.length) invalid();
      size = data[offset++];
      offset += size;
      if (offset > data.length) invalid();
    } while (size);
  };
  while (offset < data.length) {
    const kind = data[offset++];
    if (kind === 0x3b) {
      if (offset !== data.length || frames < 2) invalid();
      return { width, height, frames, duration };
    }
    if (kind === 0x21) {
      if (offset >= data.length) invalid();
      const label = data[offset++];
      if (label === 0xf9) {
        if (offset + 6 > data.length || data[offset] !== 4 || data[offset + 5] !== 0) invalid();
        delay = data.readUInt16LE(offset + 2) * 10 || 100;
        if (delay < 20 || delay > 2000) invalid();
        offset += 6;
      } else blocks();
    } else if (kind === 0x2c) {
      if (offset + 9 > data.length) invalid();
      const left = data.readUInt16LE(offset),
        top = data.readUInt16LE(offset + 2);
      const w = data.readUInt16LE(offset + 4),
        h = data.readUInt16LE(offset + 6),
        packed = data[offset + 8];
      if (!w || !h || left + w > width || top + h > height) invalid();
      offset += 9 + (packed & 128 ? 3 * 2 ** ((packed & 7) + 1) : 0);
      if (offset >= data.length || data[offset] < 2 || data[offset] > 8) invalid();
      offset++;
      blocks();
      if (++frames > 72 || (duration += delay) > 5000) invalid();
      delay = 100;
    } else invalid();
  }
  return invalid();
}
module.exports = { checkGif, MAX_GIF_BYTES, GIF_RULES };
