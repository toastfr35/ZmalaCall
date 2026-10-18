'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const { body } = require('./http/responses');
const convert = promisify(execFile);
/** @param {Buffer} bytes */
const digest = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');
const PNG_HEADER = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

/** Inspect dimensions before asking the native converter to decode pixels.
 * @param {Buffer} bytes @param {string} extension */
function checkDimensions(bytes, extension) {
  let width = 0,
    height = 0;
  if (extension === 'png' && bytes.length >= 33 && bytes.toString('ascii', 12, 16) === 'IHDR') {
    width = bytes.readUInt32BE(16);
    height = bytes.readUInt32BE(20);
  } else if (extension === 'jpg') {
    let offset = 2;
    while (offset + 4 <= bytes.length && bytes[offset] === 255) {
      while (bytes[offset] === 255) offset++;
      const marker = bytes[offset++];
      if (marker === 0xda || marker === 0xd9) break;
      if (marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) continue;
      if (offset + 2 > bytes.length) break;
      const size = bytes.readUInt16BE(offset);
      if (size < 2 || offset + size > bytes.length) break;
      if (marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker) && size >= 8) {
        height = bytes.readUInt16BE(offset + 3);
        width = bytes.readUInt16BE(offset + 5);
        break;
      }
      offset += size;
    }
  }
  if (!width || !height || width > 8192 || height > 8192 || width * height > 16000000)
    throw Error('Choose a photo up to 16 megapixels and 8192 pixels per side.');
}

class PhotoStore {
  /** @param {string} dataDir @param {typeof convert} [converter] */
  constructor(dataDir, converter = convert) {
    this.directory = path.join(dataDir, 'photos');
    this.convert = converter;
    /** @type {Map<string, Promise<void>>} */
    this.publishing = new Map();
    /** @type {Map<string, Promise<string>>} */
    this.converting = new Map();
    this.uploads = 0;
    this.active = 0;
    /** @type {(() => void)[]} */
    this.waiting = [];
  }

  /** @param {import('node:http').IncomingMessage} req */
  async upload(req) {
    if (this.uploads >= 10)
      throw Object.assign(Error('Photo queue is full. Try again shortly.'), { status: 429 });
    this.uploads++;
    try {
      const bytes = await body(req);
      const extension = bytes.subarray(0, 8).equals(PNG_HEADER)
        ? 'png'
        : bytes[0] === 255 && bytes[1] === 216
          ? 'jpg'
          : null;
      if (!extension) throw Error('Choose a PNG or JPEG photo (up to 2 MB).');
      checkDimensions(bytes, extension);
      const key = digest(bytes);
      let operation = this.converting.get(key);
      if (!operation) {
        operation = this.convertPhoto(bytes, extension);
        this.converting.set(key, operation);
      }
      try {
        return await operation;
      } finally {
        if (this.converting.get(key) === operation) this.converting.delete(key);
      }
    } finally {
      this.uploads--;
    }
  }
  /** @param {Buffer} bytes @param {string} extension */
  async convertPhoto(bytes, extension) {
    if (this.active >= 2)
      await new Promise((resolve) => this.waiting.push(() => resolve(undefined)));
    else this.active++;
    try {
      await fs.mkdir(this.directory, { recursive: true });
      // Unique intermediate files isolate simultaneous uploads of the same picture.
      const temporary = path.join(this.directory, crypto.randomUUID());
      const source = temporary + '.' + extension;
      const output = temporary + '.display.png';
      try {
        await fs.writeFile(source, bytes);
        // Decode in a separate process so photo uploads never block SIP timers.
        await this.convert(
          'python3',
          [
            path.resolve(__dirname, '../build_tools/convert-photo.py'),
            '-Source',
            source,
            '-Destination',
            output,
          ],
          { timeout: 10000 },
        );
        const name = digest(await fs.readFile(output)) + '.png';
        await this.publish(output, name);
        return '/photos/' + name;
      } finally {
        await Promise.all([source, output].map((file) => fs.rm(file, { force: true })));
      }
    } finally {
      const next = this.waiting.shift();
      if (next) next();
      else this.active--;
    }
  }
  /** @param {string} output @param {string} name */
  async publish(output, name) {
    let commit = this.publishing.get(name);
    if (!commit) {
      // Content-addressed names identify identical bytes; publish each only once.
      commit = (async () => {
        const destination = path.join(this.directory, name);
        try {
          await fs.access(destination);
          return;
        } catch (error) {
          if (!error || typeof error !== 'object' || !('code' in error) || error.code !== 'ENOENT')
            throw error;
        }
        await fs.rename(output, destination);
      })();
      this.publishing.set(name, commit);
    }
    try {
      await commit;
    } finally {
      if (this.publishing.get(name) === commit) this.publishing.delete(name);
    }
  }
}
module.exports = { PhotoStore };
