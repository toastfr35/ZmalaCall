// @ts-check
'use strict';
const { own } = require('./validation');
const LANGUAGES = require('../zmala_terminal/common/shared/terminal-languages.json');

/** Undefined preserves an existing setting; explicit null remains invalid.
 * @param {import('./types/contracts').JsonObject} update
 * @param {string} key @param {unknown} fallback */
const proposed = (update, key, fallback) => (update[key] === undefined ? fallback : update[key]);

/** @template {string | number | boolean} T
 * @param {unknown} value @param {readonly T[]} choices @param {string} message @returns {T} */
function choice(value, choices, message) {
  const match = choices.find((candidate) => candidate === value);
  if (match === undefined) throw Error(message);
  return match;
}

/** @param {unknown} value @returns {number} */
function speakerVolume(value) {
  if (typeof value !== 'number' || !Number.isInteger(value) || value < 0 || value > 100)
    throw Error('C20 speaker volume must be 0–100 percent.');
  return value;
}

// @llr LLR-SRV-CONFIG-005
/** @param {import('./types/contracts').JsonObject} update
 * @returns {import('./types/contracts').TerminalSettings} */
function mediaDevices(update) {
  const devices = { camera: '', microphone: '', speaker: '' };
  for (const key of /** @type {const} */ (['camera', 'microphone', 'speaker'])) {
    const value = update[key];
    if (typeof value !== 'string' || value.length > 256) throw Error('Invalid media device.');
    devices[key] = value;
  }
  return devices;
}

/** Return validated fields without mutating the profile or the request.
 * Store commits these and the separately validated account fields together.
 * @param {import('./types/contracts').TerminalProfile} profile
 * @param {import('./types/contracts').JsonObject} update
 * @returns {import('./types/contracts').TerminalProfile} */
function terminalProfileFields(profile, update) {
  if (
    typeof update.display_name !== 'string' ||
    !update.display_name.trim() ||
    update.display_name.length > 80
  )
    throw Error('Enter a display name.');
  // @llr LLR-SRV-CONFIG-004
  const language = proposed(update, 'language', profile.language || 'en');
  if (typeof language !== 'string' || !own(LANGUAGES, language))
    throw Error('Choose a supported terminal language.');
  return {
    display_name: update.display_name.trim(),
    language,
    // @llr LLR-SRV-CONFIG-009
    command_shell: choice(
      proposed(update, 'command_shell', profile.command_shell || 'powershell'),
      /** @type {const} */ (['powershell', 'pwsh', 'cmd', 'sh', 'bash']),
      'Choose a supported command shell.',
    ),
    audio_profile: choice(
      proposed(update, 'audio_profile', profile.audio_profile || 'normal'),
      /** @type {const} */ (['normal', 'speech']),
      'Choose a supported audio profile.',
    ),
    // @llr LLR-SRV-CONFIG-003
    video_resolution: choice(
      proposed(update, 'video_resolution', profile.video_resolution || '720p'),
      /** @type {const} */ (['480p', '720p', '1080p']),
      'Choose a supported video resolution.',
    ),
    video_fps: choice(
      proposed(update, 'video_fps', profile.video_fps ?? 15),
      /** @type {const} */ ([10, 15, 20, 25, 30]),
      'Choose a video frame rate of 10, 15, 20, 25 or 30 fps.',
    ),
    auto_framing: choice(
      proposed(update, 'auto_framing', profile.auto_framing === true),
      [false, true],
      'Automatic framing must be enabled or disabled.',
    ),
    carousel_portraits: choice(
      proposed(update, 'carousel_portraits', profile.carousel_portraits ?? 3),
      /** @type {const} */ ([3, 5]),
      'Choose 3 or 5 carousel portraits.',
    ),
    tv_idle_seconds: choice(
      proposed(update, 'tv_idle_seconds', profile.tv_idle_seconds ?? 30),
      /** @type {const} */ ([0, 30, 60, 120, 300, 600, 1200]),
      'Choose a supported TV idle timeout.',
    ),
    c20_speaker_volume: speakerVolume(
      proposed(update, 'c20_speaker_volume', profile.c20_speaker_volume ?? 50),
    ),
    terminal_settings: mediaDevices(update),
  };
}
module.exports = { terminalProfileFields };
