// @ts-check
'use strict';
// First-run configuration and per-terminal defaults. Generate credentials rather than shipping shared secrets.
const crypto = require('node:crypto');
const os = require('node:os');
const { defaultCallbackSettings, defaultSmtpSettings } = require('./callback-settings');
const random = () => crypto.randomBytes(18).toString('base64url');
function lanAddress() {
  const candidates = Object.entries(os.networkInterfaces()).flatMap(([name, addresses]) =>
    (addresses || [])
      .filter((a) => a.family === 'IPv4' && !a.internal)
      .map((a) => ({ name, ip: a.address })),
  );
  return (
    candidates.find(
      (a) =>
        /^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(a.ip) &&
        !/vpn|virtual|vethernet|wsl/i.test(a.name),
    )?.ip ||
    candidates[0]?.ip ||
    '127.0.0.1'
  );
}
/** @param {string} [name] @returns {import('./types/contracts').TerminalProfile} */
function profile(name = 'Family') {
  return {
    display_name: name,
    language: 'en',
    command_shell: 'powershell',
    audio_profile: 'normal',
    video_resolution: '720p',
    video_fps: 15,
    auto_framing: false,
    carousel_portraits: 3,
    tv_idle_seconds: 30,
    c20_speaker_volume: 50,
    terminal_settings: { camera: '', microphone: '', speaker: '' },
  };
}
// @llr SLLR002, SLLR012
/** @returns {import('./types/contracts').ServerState} */
function defaultState() {
  return {
    schema_version: 6,
    configuration_version: 1,
    host: lanAddress(),
    sip_port: 5060,
    http_port: 8080,
    admin_token: random(),
    callback_settings: defaultCallbackSettings(),
    smtp: defaultSmtpSettings(),
    users: {
      term1: {
        name: 'term1',
        type: 'terminal',
        emails: [],
        password: random(),
        device_id: 'windows-terminal',
        device_token: random(),
        auto_answer: false,
        auto_answer_seconds: 5,
      },
      phone1: { name: 'phone1', type: 'linphone', emails: [], password: random() },
    },
    profiles: { term1: profile('term1') },
    local_terminal_id: 'term1',
    groups: {
      family: {
        name: 'Family',
        description: 'The initial terminal and phone.',
        members: ['term1', 'phone1'],
      },
    },
  };
}
module.exports = { random, lanAddress, profile, defaultState };
