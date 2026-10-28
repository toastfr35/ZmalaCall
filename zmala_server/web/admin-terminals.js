import {
  terminalSelect,
  terminalInput,
  terminalUser,
  buildCallFields,
  buildMediaFields,
  buildGeneralFields,
} from './admin-terminalfields.js';
import { query } from './admin-shared.js';
// Device association and settings editor. Serial numbers identify hardware independently of SIP usernames.
import {
  el,
  badge,
  online,
  registered,
  panel,
  submit,
  api,
  notice,
  actionButton,
  setView,
  empty,
  link,
  confirm,
} from './admin-shared.js';
import { state, $ } from './admin-state.js';
import { openWifi, serverPdf } from './admin-setup.js';
import { openConsole } from './admin-console.js';
/** @param {HTMLElement} card @param {string} title @param {string} kind @returns {import('../types/admin-dom').TerminalForm} */
export function terminalForm(card, title, kind) {
  const form = Object.assign(el('form', null, 'terminal-settings-form'), {
    fields: /** @type {Record<string, HTMLInputElement | HTMLSelectElement>} */ ({}),
    errorId: '',
  });
  form.dataset.kind = kind;
  form.setAttribute('aria-label', `${title} for ${terminalId(card)}`);
  form.append(el('h3', title));
  const error = el('p', null, 'banner error');
  error.id = `terminal-${kind}-error-${terminalId(card)}`;
  error.hidden = true;
  error.setAttribute('role', 'alert');
  form.errorId = error.id;
  form.append(error);
  form.addEventListener('input', () => {
    form.dataset.dirty = 'true';
    card.dataset.dirty = 'true';
    updateTerminalSaveState(card);
  });
  form.addEventListener('change', () => {
    form.dataset.dirty = 'true';
    card.dataset.dirty = 'true';
    updateTerminalSaveState(card);
  });
  return form;
}
/** @param {import('../types/admin-dom').TerminalForm} form @param {HTMLElement} card */
export function savedTerminalForm(form, card) {
  form.dataset.dirty = 'false';
  card.dataset.dirty = String(!!card.querySelector('form[data-dirty="true"]'));
  updateTerminalSaveState(card);
}
// @llr LLR-SRV-UI-017
/** @param {HTMLElement} card */
function updateTerminalSaveState(card) {
  const status = card.querySelector('.terminal-save-state');
  if (status)
    status.textContent = card.querySelector('form[data-kind=devices][data-dirty=true]')
      ? 'Unsaved settings'
      : 'Settings saved';
}
// @llr LLR-SRV-UI-017
/** @param {HTMLElement} summary @param {import('../types/contracts').TerminalStatus | undefined} status @param {boolean} fresh */
function appendTerminalHardware(summary, status, fresh) {
  if (!fresh) {
    summary.append(
      badge('Remote: status unavailable', 'neutral'),
      badge('C20: status unavailable', 'neutral'),
    );
    return;
  }
  /** @type {Record<string, string>} */
  const remote = {
    connected: 'connected',
    disconnected: 'disconnected',
    unpaired: 'not paired',
    blocked: 'blocked',
    bluetooth_unavailable: 'Bluetooth unavailable',
    input_unavailable: 'input unavailable',
  };
  /** @type {Record<string, string>} */
  const camera = {
    connected: 'connected',
    disconnected: 'disconnected',
    off: 'powered off',
    on: 'powered on (connection unknown)',
    waking: 'waking',
    switching: 'changing power',
    error: 'power/recovery error',
  };
  const battery = status?.remote_battery;
  summary.append(
    badge(
      'Remote: ' + (remote[status?.remote_status || ''] || 'unknown'),
      status?.remote_status === 'connected' ? 'success' : 'neutral',
    ),
    badge(
      'Remote battery: ' + (typeof battery === 'number' ? battery + '%' : 'unknown'),
      typeof battery === 'number' && battery > 20 ? 'success' : 'neutral',
    ),
    badge(
      'Remote charger: ' +
        (status?.remote_charger_connected === true
          ? 'connected'
          : status?.remote_charger_connected === false
            ? 'not connected'
            : 'unknown'),
      'neutral',
    ),
    badge(
      'C20: ' + (camera[status?.camera_status || ''] || 'unknown'),
      status?.camera_status === 'connected' ? 'success' : 'neutral',
    ),
    badge(
      'C20 power: ' +
        (status?.camera_powered === true
          ? 'on'
          : status?.camera_powered === false
            ? 'off'
            : 'unknown'),
      status?.camera_powered === true ? 'success' : 'neutral',
    ),
  );
}
/** @param {HTMLElement} card @param {string} id */
export function terminalCardState(card, id) {
  const u = state.model.users[id];
  query(card, 'h2').textContent = u.name;
  query(card, '.terminal-address').textContent = `sip:${id}@${state.model.host}`;
  const summary = query(card, '.terminal-summary');
  const connection = el('div', null, 'terminal-status-group');
  const hardware = el('div', null, 'terminal-status-group');
  const features = el('div', null, 'terminal-status-group');
  connection.append(el('h3', 'Connection'));
  hardware.append(el('h3', 'Remote & camera'));
  features.append(el('h3', 'Call features'));
  summary.replaceChildren(connection, hardware, features);
  connection.append(
    badge(online(id) ? 'Terminal online' : 'Terminal offline', online(id) ? 'success' : 'neutral'),
    badge(
      registered(id) ? 'SIP registered' : 'SIP offline',
      registered(id) ? 'success' : 'neutral',
    ),
  );
  if (id === state.model.local_terminal_id)
    connection.append(badge('Server-local terminal', 'accent'));
  const audioStatus = state.model.terminal_statuses[id];
  appendTerminalHardware(hardware, audioStatus, online(id));
  if (state.model.profiles[id].auto_framing === true) {
    const framingStatus = audioStatus?.auto_framing_status;
    /** @type {Record<string, string>} */
    const labels = {
      active: 'Automatic framing active',
      waiting: 'Automatic framing ready for a call',
      unavailable: 'Automatic framing unavailable · full view',
      unsupported: 'Automatic framing requires a Pi C20 terminal',
    };
    features.append(
      badge(
        labels[framingStatus || ''] || 'Automatic framing pending',
        framingStatus === 'active' ? 'accent' : 'neutral',
      ),
    );
  }
  if (
    (state.model.profiles[id].audio_profile || 'normal') === 'speech' &&
    audioStatus?.requested_audio_profile === 'speech'
  )
    features.append(
      badge(
        audioStatus.audio_profile === 'speech'
          ? 'Speech audio active'
          : 'Speech unavailable · normal audio',
        audioStatus.audio_profile === 'speech' ? 'accent' : 'neutral',
      ),
    );
  features.hidden = features.children.length === 1;
  card
    .querySelectorAll('form')
    .forEach((form) =>
      form.setAttribute(
        'aria-label',
        `${form.dataset.kind === 'association' ? 'Account association' : 'Terminal settings'} for ${id}`,
      ),
    );
}
/** @param {HTMLElement} card @param {string} id */
function buildDevicesForm(card, id) {
  // Keep the revision that produced these controls, even while polling updates state.model.
  const configurationVersion = state.model.configuration_version;
  const devices = terminalForm(card, 'Terminal settings', 'devices');
  devices.configurationVersion = configurationVersion;
  query(devices, 'h3').remove();
  // @llr LLR-SRV-UI-017
  // Keep saving beside the draft status while the long form scrolls.
  const saveBar = el('div', null, 'terminal-save-bar');
  const saveState = el('span', 'Settings saved', 'terminal-save-state');
  saveState.setAttribute('role', 'status');
  const save = el('button', 'Save changes', 'primary');
  save.type = 'submit';
  saveBar.append(saveState, save);
  devices.append(saveBar);
  // Separate visual groups share one form and one save action.
  /** @param {string} title @param {string} [className] */
  const group = (title, className = '') => {
    const section = el('section', null, 'terminal-setting-section ' + className);
    const fields = el('div', null, 'terminal-options');
    section.append(el('h3', title), fields);
    devices.append(section);
    return fields;
  };
  buildCallFields(devices, group('Calls', 'terminal-calls'), id);
  buildMediaFields(devices, group('Video & audio'), id);
  buildGeneralFields(devices, group('General'), id);
  const footer = el('div', null, 'terminal-tools');
  const tools = el('div', null, 'button-row');
  const setup = el('details', null, 'terminal-setup');
  setup.append(el('summary', 'Setup', 'secondary'));
  const menu = el('div', null, 'terminal-setup-menu');
  /** @param {import('../types/admin').Action} action */
  const setupAction = (action) => () => {
    setup.open = false;
    return action();
  };
  menu.append(
    actionButton('Download Wi-Fi QR PDF', setupAction(openWifi), 'secondary', 'down'),
    actionButton(
      'Download server QR PDF',
      setupAction(() => serverPdf(terminalId(card))),
      'secondary',
      'down',
    ),
  );
  setup.append(menu);
  tools.append(
    setup,
    actionButton('Console', () => openConsole(terminalId(card)), 'secondary', 'terminal'),
  );
  footer.append(tools);
  devices.append(footer);
  devices.onsubmit = (e) => {
    e.preventDefault();
    return submit(
      devices,
      async () => {
        const fields = devices.fields,
          currentId = terminalId(card);
        await api('/api/settings', 'PUT', {
          terminal_id: currentId,
          configuration_version: devices.configurationVersion,
          display_name: state.model.profiles[currentId].display_name,
          auto_answer: terminalInput(devices, 'autoAnswer').checked,
          auto_answer_seconds: Number(fields.countdown.value),
          language: fields.language.value,
          command_shell: state.model.profiles[currentId].command_shell || 'powershell',
          audio_profile: fields.audioProfile.value,
          video_resolution: fields.videoResolution.value,
          video_fps: Number(fields.videoFps.value),
          carousel_portraits: Number(fields.carouselPortraits.value),
          tv_idle_seconds: Number(fields.tvIdleSeconds.value),
          auto_framing: terminalInput(devices, 'autoFraming').checked,
          c20_speaker_volume: Number(fields.c20SpeakerVolume.value),
          ringtone_volume: Number(fields.ringtoneVolume.value),
          action_sound_volume: Number(fields.actionSoundVolume.value),
          // @llr LLR-SRV-CONFIG-024
          ringtone: fields.ringtone.value,
          camera: '',
          microphone: '',
          speaker: '',
        });
        savedTerminalForm(devices, card);
        await state.refresh(true);
        notice(`Saved terminal settings for ${currentId}.`);
      },
      devices.errorId,
    );
  };
  return devices;
}
/** @param {HTMLElement} card @param {string} id */
function buildAssociationForm(card, id) {
  // @llr LLR-SRV-UI-016
  const configurationVersion = state.model.configuration_version;
  const form = terminalForm(card, 'Account association', 'association');
  const serial = terminalUser(id).device_id;
  const row = el('div', null, 'terminal-association-row');
  const serialField = el('div', null, 'terminal-serial');
  serialField.append(el('span', 'Serial number'), el('code', serial));
  row.append(serialField);
  form.append(row);
  const choices = Object.keys(state.model.profiles).map((key) => [
    key,
    `${state.model.users[key].name} (${key})`,
  ]);
  row.append(terminalSelect(form, 'Associated account', 'accountId', choices, id));
  const change = el('button', 'Change association', 'secondary');
  change.type = 'submit';
  change.disabled = true;
  form.fields.accountId.onchange = () => {
    change.disabled = form.fields.accountId.value === id;
  };
  row.append(change);
  form.onsubmit = (event) => {
    event.preventDefault();
    const next = form.fields.accountId.value;
    if (next === id) return;
    confirm(
      'Change terminal account?',
      `Associate serial ${serial} with ${state.model.users[next].name} (${next})? The two terminals exchange account associations. Device settings remain with each serial. End any calls first.`,
      async () => {
        await api('/api/terminal-association', 'PUT', {
          serial_number: serial,
          account_id: next,
          configuration_version: configurationVersion,
        });
        state.terminalCards.clear();
        state.terminalId = next;
        await state.refresh(true);
        notice('Account association changed. Connected terminals update automatically.');
      },
      'Change association',
    );
  };
  return form;
}
/** @param {string} id */
export function buildTerminalCard(id) {
  const u = state.model.users[id],
    card = panel(u.name, `sip:${id}@${state.model.host}`);
  card.classList.add('terminal-card');
  card.dataset.terminalId = id;
  query(card, '.panel-heading p').classList.add('terminal-address');
  card.append(el('div', null, 'terminal-summary'));
  const forms = el('div', null, 'terminal-fields');
  forms.append(buildAssociationForm(card, id), buildDevicesForm(card, id));
  card.append(forms);
  terminalCardState(card, id);
  return card;
}
// @llr LLR-SRV-UI-017
export function renderTerminals() {
  $('page-actions').replaceChildren();
  const ids = Object.keys(state.model.profiles);
  if (!ids.length) {
    state.terminalCards.clear();
    setView(
      empty(
        'Add your first terminal',
        'Create an account with type Terminal to configure its devices and settings.',
        link('Go to accounts', '/accounts', 'primary'),
      ),
    );
    return;
  }
  for (const id of state.terminalCards.keys())
    if (!ids.includes(id)) state.terminalCards.delete(id);
  if (!ids.includes(state.terminalId))
    state.terminalId = ids.includes(state.model.local_terminal_id || '')
      ? state.model.local_terminal_id || ids[0]
      : ids[0];
  const chooser = el('label', 'Terminal', 'terminal-dropdown'),
    select = el('select');
  select.setAttribute('aria-label', 'Select terminal');
  for (const id of ids) {
    const option = el('option', `${state.model.users[id].name} (${id})`);
    option.value = id;
    select.append(option);
  }
  select.value = state.terminalId;
  select.onchange = () => {
    state.terminalId = select.value;
    renderTerminals();
  };
  chooser.append(select);
  let card = state.terminalCards.get(state.terminalId);
  if (!card || card.dataset.dirty !== 'true') {
    card = buildTerminalCard(state.terminalId);
    state.terminalCards.set(state.terminalId, card);
  }
  terminalCardState(card, state.terminalId);
  // Reuse dirty cards so switching terminals or saving another form preserves drafts.
  card.querySelector('.terminal-dropdown')?.remove();
  query(card, '.panel-heading').append(chooser);
  setView(card);
}

/** @param {HTMLElement} card @returns {string} */
function terminalId(card) {
  const id = card.dataset.terminalId;
  if (!id) throw Error('Terminal card has no account identity.');
  return id;
}
