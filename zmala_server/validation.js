// @ts-check
'use strict';
// Validate untrusted configuration fields before they reach persistent state or derived API responses.
/** @param {object} object @param {PropertyKey} key */
const own = (object, key) => Object.hasOwn(object, key);
/** @param {unknown} id @returns {id is string} */
const accountId = (id) =>
  typeof id === 'string' &&
  /^[a-z][a-z0-9_-]{0,30}$/.test(id) &&
  !['constructor', 'prototype', '__proto__'].includes(id);
/** @param {import('./types/contracts').JsonObject} update
 * @param {import('./types/contracts').ServerState['users']} users
 * @returns {import('./types/contracts').Group} */
function validateGroup(update, users) {
  if (!update || typeof update.name !== 'string' || !update.name.trim() || update.name.length > 80)
    throw Error('Enter a group name (1–80 characters).');
  if (
    update.description !== undefined &&
    (typeof update.description !== 'string' || update.description.length > 240)
  )
    throw Error('Group descriptions must be at most 240 characters.');
  if (
    !Array.isArray(update.members) ||
    update.members.length > 40 ||
    update.members.some((id) => typeof id !== 'string' || !own(users, id)) ||
    new Set(update.members).size !== update.members.length
  )
    throw Error('Select unique, existing accounts as group members.');
  return {
    name: update.name.trim(),
    description: (update.description || '').trim(),
    members: [...update.members],
  };
}
/** @param {unknown} photo @returns {photo is string} */
function validPhoto(photo) {
  return typeof photo === 'string' && (!photo || /^\/photos\/[a-f0-9]+\.(png|jpg)$/.test(photo));
}
/** @param {import('./types/contracts').JsonObject} update
 * @returns {import('./types/contracts').AccountFields} */
function accountFields(update) {
  if (typeof update.name !== 'string' || !update.name.trim() || update.name.length > 80)
    throw Error('Enter an account name (1–80 characters).');
  if (update.type !== 'linphone' && update.type !== 'terminal')
    throw Error('Account type must be Linphone or Terminal.');
  if (
    update.password !== undefined &&
    (typeof update.password !== 'string' ||
      update.password.length > 128 ||
      /[\r\n\0]/.test(update.password))
  )
    throw Error('Invalid password (at most 128 characters).');
  /** @type {import('./types/contracts').AccountFields} */
  const fields = { name: update.name.trim(), type: update.type };
  if (update.emails !== undefined) fields.emails = validateEmails(update.emails);
  if (update.photo !== undefined) {
    if (!validPhoto(update.photo)) throw Error('Invalid account picture.');
    fields.photo = update.photo;
  }
  if (
    update.type === 'linphone' &&
    (update.auto_answer !== undefined || update.auto_answer_seconds !== undefined)
  )
    throw Error('Auto-answer is available for terminal accounts only.');
  return Object.assign(fields, autoAnswerFields(update));
}
/** Shared validation keeps terminal settings and legacy account API consistent.
 * @param {import('./types/contracts').JsonObject} update
 * @returns {import('./types/contracts').AutoAnswerSettings} */
function autoAnswerFields(update) {
  /** @type {import('./types/contracts').AutoAnswerSettings} */
  const fields = {};
  if (update.auto_answer !== undefined) {
    if (typeof update.auto_answer !== 'boolean') throw Error('Auto-answer must be true or false.');
    fields.auto_answer = update.auto_answer;
  }
  if (update.auto_answer_seconds !== undefined) {
    if (
      typeof update.auto_answer_seconds !== 'number' ||
      !Number.isInteger(update.auto_answer_seconds) ||
      update.auto_answer_seconds < 5 ||
      update.auto_answer_seconds > 600
    )
      throw Error('Countdown must be 5–600 seconds.');
    fields.auto_answer_seconds = update.auto_answer_seconds;
  }
  return fields;
}
/** Accept plain mailbox addresses only; never SMTP headers or display-name syntax.
 * @param {unknown} values @returns {string[]} */
function validateEmails(values) {
  if (!Array.isArray(values) || values.length < 1 || values.length > 10)
    throw Error('Enter between one and ten email addresses.');
  const emails = values.map((value) => {
    if (typeof value !== 'string') throw Error('Enter valid email addresses.');
    const address = value.trim();
    const [local, domain, extra] = address.split('@');
    if (
      !local ||
      !domain ||
      extra !== undefined ||
      address.length > 254 ||
      local.length > 64 ||
      !/^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+$/.test(local) ||
      local.startsWith('.') ||
      local.endsWith('.') ||
      local.includes('..') ||
      !domain.includes('.') ||
      domain
        .split('.')
        .some((label) => !/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$/.test(label))
    )
      throw Error('Enter valid email addresses, without names or brackets.');
    return local + '@' + domain.toLowerCase();
  });
  if (new Set(emails.map((address) => address.toLowerCase())).size !== emails.length)
    throw Error('Each email address must be unique within the account.');
  return emails;
}
module.exports = {
  own,
  accountId,
  validateGroup,
  accountFields,
  autoAnswerFields,
  validateEmails,
  terminalStatus,
};

/** Reject malformed device diagnostics before they can break the administration UI.
 * @param {import('./types/contracts').JsonObject} update
 * @returns {import('./types/contracts').TerminalStatus} */
function terminalStatus(update) {
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
  return status;
}
