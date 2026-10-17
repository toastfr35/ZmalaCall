// Device field construction only; card identity, saving and navigation live in admin-terminals.
import { el } from './admin-shared.js';
import { state } from './admin-state.js';

/** @param {import('../types/admin-dom').TerminalForm} form @param {string} label @param {string} key @param {string | number} value @param {object} [options] */
export function terminalField(form, label, key, value, options = {}) {
  const wrapper = el('label', label),
    input = el('input');
  input.name = key;
  input.value = String(value ?? '');
  Object.assign(input, options);
  wrapper.append(input);
  form.fields[key] = input;
  return wrapper;
}
/** @param {import('../types/admin-dom').TerminalForm} form @param {string} label @param {string} key @param {string[][]} choices @param {string} value */
export function terminalSelect(form, label, key, choices, value) {
  const wrapper = el('label', label),
    select = el('select');
  select.name = key;
  for (const [key, text] of choices) {
    const option = el('option', text);
    option.value = key;
    select.append(option);
  }
  select.value = value;
  wrapper.append(select);
  form.fields[key] = select;
  return wrapper;
}
/** @param {string} id @returns {import('../types/contracts').TerminalAccount} */
export function terminalUser(id) {
  const user = state.model.users[id];
  if (!user || user.type !== 'terminal') throw Error('Choose a terminal account.');
  return user;
}
/** @param {import('../types/admin-dom').TerminalForm} form @param {string} key @returns {HTMLInputElement} */
export function terminalInput(form, key) {
  const field = form.fields[key];
  if (!(field instanceof HTMLInputElement)) throw Error('Missing terminal input: ' + key);
  return field;
}

/** @param {import('../types/admin-dom').TerminalForm} devices @param {HTMLElement} calls @param {string} id */
export function buildCallFields(devices, calls, id) {
  const user = terminalUser(id);
  const auto = terminalField(devices, 'Auto-answer incoming calls', 'autoAnswer', '', {
    type: 'checkbox',
    checked: user.auto_answer === true,
  });
  auto.classList.add('checkbox-row');
  auto.prepend(terminalInput(devices, 'autoAnswer'));
  terminalInput(devices, 'autoAnswer').setAttribute('role', 'switch');
  const countdown = terminalField(
    devices,
    'Answer delay (seconds)',
    'countdown',
    user.auto_answer_seconds || 5,
    {
      type: 'number',
      min: '5',
      max: '600',
      required: true,
    },
  );
  countdown.append(el('small', '5–600 seconds (up to 10 minutes)'));
  countdown.classList.add('terminal-answer-delay');
  terminalInput(devices, 'autoAnswer').onchange = () => {
    terminalInput(devices, 'countdown').disabled = !terminalInput(devices, 'autoAnswer').checked;
  };
  terminalInput(devices, 'countdown').disabled = !terminalInput(devices, 'autoAnswer').checked;
  calls.append(auto, countdown);
}

/** @param {import('../types/admin-dom').TerminalForm} devices @param {HTMLElement} media @param {string} id */
export function buildMediaFields(devices, media, id) {
  const profile = state.model.profiles[id];
  /** @param {keyof import('../types/contracts').TerminalSettings} key @param {string} label */
  const mediaField = (key, label) => {
    const current = profile.terminal_settings[key] || '';
    const available = state.model.terminal_statuses[id]?.devices?.[key] || [];
    const choices = [
      ['', 'System default'],
      ...[...new Set([...available, ...(current ? [current] : [])])].map((value) => [value, value]),
    ];
    return terminalSelect(devices, label, key, choices, current);
  };
  const resolution = terminalSelect(
    devices,
    'Video resolution',
    'videoResolution',
    [
      ['480p', '480p · 640 × 480'],
      ['720p', '720p · 1280 × 720'],
      ['1080p', '1080p · 1920 × 1080'],
    ],
    profile.video_resolution || '720p',
  );
  resolution.append(
    el('small', 'Applies when idle. Higher resolutions need more processing power.'),
  );
  const frameRate = terminalSelect(
    devices,
    'Video frame rate',
    'videoFps',
    [10, 15, 20, 25, 30].map((fps) => [String(fps), `${fps} fps`]),
    String(profile.video_fps ?? 15),
  );
  frameRate.append(
    el(
      'small',
      'Outgoing video target. Applies when idle; actual fps depends on camera and processing capacity. Higher rates use more bandwidth.',
    ),
  );
  const framing = terminalField(devices, 'Automatic framing', 'autoFraming', '', {
    type: 'checkbox',
    checked: profile.auto_framing === true,
  });
  framing.classList.add('checkbox-row');
  framing.prepend(terminalInput(devices, 'autoFraming'));
  terminalInput(devices, 'autoFraming').setAttribute('role', 'switch');
  framing.append(
    el(
      'small',
      'Experimental · Pi C20 camera. Keeps people in view, up to 2× zoom. Applies during calls.',
    ),
  );
  const audio = terminalSelect(
    devices,
    'Audio processing',
    'audioProfile',
    [
      ['normal', 'Normal audio'],
      ['speech', 'Speech · 16 kHz (Linux C20)'],
    ],
    profile.audio_profile || 'normal',
  );
  audio.append(el('small', 'Echo cancellation stays enabled.'));
  const info = el('details', null, 'terminal-help');
  info.append(
    el('summary', 'About audio processing'),
    el(
      'p',
      'Speech processing is available on Linux C20 terminals. Windows uses normal audio. Changes apply when idle.',
      'help',
    ),
  );
  audio.append(info);
  const volume = terminalField(
    devices,
    'C20 speaker volume (%)',
    'c20SpeakerVolume',
    profile.c20_speaker_volume ?? 50,
    { type: 'number', min: '0', max: '100', step: '1', required: true },
  );
  volume.append(el('small', 'Linux C20 · calls and ringing. Applies when idle. Default: 50%.'));
  media.append(
    mediaField('camera', 'Camera'),
    resolution,
    frameRate,
    framing,
    mediaField('microphone', 'Microphone'),
    mediaField('speaker', 'Speaker'),
    audio,
    volume,
  );
}

/** @param {import('../types/admin-dom').TerminalForm} devices @param {HTMLElement} general @param {string} id */
export function buildGeneralFields(devices, general, id) {
  const profile = state.model.profiles[id];
  const languages = [...state.model.terminal_languages]
    .sort((a, b) => a.name.localeCompare(b.name, 'en'))
    .map((l) => [l.code, l.name === l.native ? l.name : `${l.name} · ${l.native}`]);
  general.append(
    terminalSelect(devices, 'Language', 'language', languages, profile.language || 'en'),
    terminalSelect(
      devices,
      'Carousel portraits',
      'carouselPortraits',
      [
        ['3', '3 portraits'],
        ['5', '5 portraits'],
      ],
      String(profile.carousel_portraits ?? 3),
    ),
    terminalSelect(
      devices,
      'Return to TV after inactivity',
      'tvIdleSeconds',
      [
        ['30', '30 seconds'],
        ['60', '1 minute'],
        ['120', '2 minutes'],
        ['300', '5 minutes'],
        ['600', '10 minutes'],
        ['1200', '20 minutes'],
        ['0', 'Never'],
      ],
      String(profile.tv_idle_seconds ?? 30),
    ),
  );
}
