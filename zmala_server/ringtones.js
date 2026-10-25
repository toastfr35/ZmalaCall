// @ts-check
'use strict';
const path = require('node:path');
const crypto = require('node:crypto');

const MAX_SOUND = 44 + 16000 * 2 * 30;
const MAX_LIBRARY = 40 * 1024 * 1024;
const SOUND = /^ringtones\/[a-f0-9]{64}\.wav$/;
const DEFAULT_SOUND = path.resolve(__dirname, '../zmala_terminal/common/assets/gentle-chime.wav');

// @llr LLR-SRV-CONFIG-024
/** Normalized PCM keeps decoding out of the server and bounds playback/storage.
 * @param {Buffer} bytes */
function validateSound(bytes) {
  if (
    bytes.length <= 44 ||
    bytes.length > MAX_SOUND ||
    bytes.length % 2 ||
    bytes.toString('ascii', 0, 4) !== 'RIFF' ||
    bytes.readUInt32LE(4) !== bytes.length - 8 ||
    bytes.toString('ascii', 8, 16) !== 'WAVEfmt ' ||
    bytes.readUInt32LE(16) !== 16 ||
    bytes.readUInt16LE(20) !== 1 ||
    bytes.readUInt16LE(22) !== 1 ||
    bytes.readUInt32LE(24) !== 16000 ||
    bytes.readUInt32LE(28) !== 32000 ||
    bytes.readUInt16LE(32) !== 2 ||
    bytes.readUInt16LE(34) !== 16 ||
    bytes.toString('ascii', 36, 40) !== 'data' ||
    bytes.readUInt32LE(40) !== bytes.length - 44
  )
    throw Error('Choose a valid PCM ringtone up to 30 seconds.');
  return crypto.createHash('sha256').update(bytes).digest('hex');
}

/** @param {unknown} value @returns {string} */
function ringtoneId(value) {
  if (typeof value !== 'string' || !/^(nokia|[a-f0-9]{64})$/.test(value))
    throw Error('Choose a ringtone from the list.');
  return value;
}

/** @param {import('./types/contracts').RingtoneLibrary | undefined} library */
function ringtoneList(library) {
  return [
    { id: 'nokia', name: 'Nokia', url: '/api/ringtones/nokia.wav' },
    ...Object.entries(library || {})
      .map(([id, sound]) => ({
        id,
        name: sound.name,
        url: `/api/ringtones/${id}.wav`,
      }))
      .sort((a, b) => a.name.localeCompare(b.name, 'en', { sensitivity: 'base' })),
  ];
}

module.exports = {
  MAX_SOUND,
  MAX_LIBRARY,
  SOUND,
  DEFAULT_SOUND,
  validateSound,
  ringtoneId,
  ringtoneList,
};
