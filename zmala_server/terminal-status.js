// @ts-check
'use strict';
// Device telemetry has its own schema; it never changes account configuration.
// @llr LLR-SRV-MAINT-018
/** Reject malformed device diagnostics before they can break the administration UI.
 * @param {import('./types/contracts').JsonObject} update
 * @returns {import('./types/contracts').TerminalStatus} */
function terminalStatus(update) {
  // @llr LLR-SRV-MAINT-019
  /** @type {import('./types/contracts').TerminalStatus} */
  const status = { last_seen: new Date().toISOString() };
  for (const key of /** @type {const} */ ([
    'state',
    'camera',
    'microphone',
    'speaker',
    'ringer',
    'audio_profile',
    'requested_audio_profile',
    'auto_framing_status',
  ])) {
    const value = update[key];
    if (value === undefined) continue;
    if (typeof value !== 'string' || value.length > 256) throw Error('Invalid terminal status.');
    status[key] = value;
  }
  for (const [key, allowed] of /** @type {[string, string[]][]} */ ([
    [
      'remote_status',
      [
        'connected',
        'disconnected',
        'unpaired',
        'blocked',
        'bluetooth_unavailable',
        'input_unavailable',
        'unknown',
      ],
    ],
    [
      'camera_status',
      ['connected', 'disconnected', 'off', 'on', 'waking', 'switching', 'error', 'unknown'],
    ],
  ])) {
    if (update[key] !== undefined) {
      if (typeof update[key] !== 'string' || !allowed.includes(update[key]))
        throw Error('Invalid peripheral status.');
      Object.assign(status, { [key]: update[key] });
    }
  }
  if (update.remote_battery !== undefined) {
    const battery = update.remote_battery;
    if (
      battery !== null &&
      (typeof battery !== 'number' || !Number.isInteger(battery) || battery < 0 || battery > 100)
    )
      throw Error('Invalid remote battery.');
    status.remote_battery = battery;
  }
  for (const key of /** @type {const} */ ([
    'remote_charger_connected',
    'camera_powered',
    'camera_connected',
  ])) {
    const value = update[key];
    if (value !== undefined) {
      if (value !== null && typeof value !== 'boolean') throw Error('Invalid peripheral state.');
      status[key] = value;
    }
  }
  if (update.registered !== undefined) {
    if (typeof update.registered !== 'boolean') throw Error('Invalid registration status.');
    status.registered = update.registered;
  }
  if (update.configuration_version !== undefined) {
    if (
      typeof update.configuration_version !== 'number' ||
      !Number.isSafeInteger(update.configuration_version) ||
      update.configuration_version < 0
    )
      throw Error('Invalid configuration version.');
    status.configuration_version = update.configuration_version;
  }
  if (update.devices !== undefined) {
    if (!update.devices || typeof update.devices !== 'object' || Array.isArray(update.devices))
      throw Error('Invalid device list.');
    const devices = /** @type {import('./types/contracts').JsonObject} */ (update.devices);
    status.devices = {};
    for (const key of /** @type {const} */ (['camera', 'microphone', 'speaker'])) {
      const names = devices[key];
      if (names === undefined) continue;
      if (
        !Array.isArray(names) ||
        names.length > 100 ||
        names.some((name) => typeof name !== 'string' || name.length > 256)
      )
        throw Error('Invalid device list.');
      status.devices[key] = names;
    }
  }
  if (update.media !== undefined) {
    // Copy only known scalar counters/measurements; never retain the submitted object.
    const object = (/** @type {unknown} */ value) => {
      if (!value || typeof value !== 'object' || Array.isArray(value))
        throw Error('Invalid media status.');
      return /** @type {import('./types/contracts').JsonObject} */ (value);
    };
    const media = object(update.media);
    /** @type {import('./types/contracts').JsonObject} */
    const result = {};
    for (const kind of ['audio', 'video']) {
      if (media[kind] === undefined) continue;
      const source = object(media[kind]);
      /** @type {import('./types/contracts').JsonObject} */
      const stream = {};
      for (const key of [
        'download_kbps',
        'upload_kbps',
        'jitter_buffer_ms',
        'round_trip_seconds',
        'receiver_loss_percent',
        'sender_loss_percent',
        'received_fps',
        'sent_fps',
      ]) {
        if (source[key] === undefined) continue;
        const value = source[key];
        if (
          typeof value !== 'number' ||
          !Number.isFinite(value) ||
          value < 0 ||
          value > Number.MAX_SAFE_INTEGER
        )
          throw Error('Invalid media measurement.');
        stream[key] = value;
      }
      for (const key of ['sent_resolution', 'received_resolution']) {
        if (source[key] === undefined) continue;
        const value = source[key];
        if (
          !Array.isArray(value) ||
          value.length !== 2 ||
          value.some((n) => typeof n !== 'number' || !Number.isInteger(n) || n < 1 || n > 16384)
        )
          throw Error('Invalid media resolution.');
        stream[key] = [...value];
      }
      result[kind] = stream;
    }
    if (media.codecs !== undefined) {
      const codecs = object(media.codecs);
      /** @type {import('./types/contracts').JsonObject} */
      const counters = {};
      for (const kind of ['encoder', 'decoder']) {
        if (codecs[kind] === undefined) continue;
        const source = object(codecs[kind]);
        /** @type {import('./types/contracts').JsonObject} */
        const snapshot = {};
        for (const key of [
          'input_queued',
          'output_queued',
          'dropped',
          'display_dropped',
          'peak_input',
          'peak_output',
          'max_queue_ms',
          'produced',
        ]) {
          if (source[key] === undefined) continue;
          const value = source[key];
          if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0)
            throw Error('Invalid media counter.');
          snapshot[key] = value;
        }
        counters[kind] = snapshot;
      }
      result.codecs = counters;
    }
    status.media = result;
  }
  return status;
}

module.exports = { terminalStatus };
