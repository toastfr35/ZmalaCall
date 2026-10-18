// @ts-check
'use strict';
// Validate reminder/removal deadlines and SMTP settings before publishing administrator views.
const { validateEmails } = require('./validation');
const defaultCallbackSettings = () => ({ email_after_hours: 1, remove_after_hours: 4 });
const defaultSmtpSettings = () => ({
  enabled: false,
  host: '',
  port: 587,
  security: 'starttls',
  username: '',
  password: '',
  from: '',
});

/** @param {import('./types/contracts').JsonObject} update
 * @returns {import('./types/contracts').ServerState['callback_settings']} */
function validateCallbackSettings(update) {
  const { email_after_hours: emailDelay, remove_after_hours: removalDelay } = update;
  if (
    typeof emailDelay !== 'number' ||
    typeof removalDelay !== 'number' ||
    !Number.isFinite(emailDelay) ||
    !Number.isFinite(removalDelay) ||
    emailDelay < 0.01 ||
    removalDelay <= emailDelay ||
    removalDelay > 720
  )
    throw Error(
      'Enter hours: the email reminder must be at least 0.01 hours, and removal must be later (up to 720 hours).',
    );
  return { email_after_hours: emailDelay, remove_after_hours: removalDelay };
}

// @llr LLR-SRV-CALLBACK-011
/** @param {import('./types/contracts').JsonObject} update
 * @param {import('./types/contracts').ServerState['smtp']} current
 * @returns {import('./types/contracts').ServerState['smtp']} */
function validateSmtpSettings(update, current) {
  if (
    !update ||
    typeof update.enabled !== 'boolean' ||
    (update.security !== 'starttls' && update.security !== 'tls' && update.security !== 'none') ||
    typeof update.port !== 'number' ||
    !Number.isInteger(update.port) ||
    update.port < 1 ||
    update.port > 65535
  )
    throw Error('Choose valid SMTP connection settings.');
  const result = {
    enabled: update.enabled,
    port: update.port,
    security: update.security,
    host: '',
    username: '',
    from: '',
    password: '',
  };
  for (const [field, limit] of /** @type {const} */ ([
    ['host', 253],
    ['username', 254],
    ['from', 254],
  ])) {
    if (
      typeof update[field] !== 'string' ||
      update[field].length > limit ||
      /[\r\n\0]/.test(update[field])
    )
      throw Error('Invalid SMTP ' + field + '.');
    result[field] = update[field].trim();
  }
  if (result.host && !/^[A-Za-z0-9.-]+$/.test(result.host))
    throw Error('Enter an SMTP hostname or IPv4 address.');
  if (result.from) result.from = validateEmails([result.from])[0];
  if (
    update.password !== undefined &&
    (typeof update.password !== 'string' ||
      update.password.length > 1024 ||
      /[\r\n\0]/.test(update.password))
  )
    throw Error('Invalid SMTP password.');
  if (update.clear_password !== undefined && typeof update.clear_password !== 'boolean')
    throw Error('Invalid SMTP password setting.');
  result.password = update.clear_password
    ? ''
    : (typeof update.password === 'string' && update.password) || current.password;
  if (result.enabled && (!result.host || !result.from || (result.username && !result.password)))
    throw Error('Enter an SMTP host, sender email and credentials before enabling email delivery.');
  return result;
}
/** @param {import('./types/contracts').ServerState['smtp']} settings */
function smtpView(settings) {
  const { password, ...publicFields } = settings;
  return { ...publicFields, password_set: !!password };
}
module.exports = {
  defaultCallbackSettings,
  defaultSmtpSettings,
  validateCallbackSettings,
  validateSmtpSettings,
  smtpView,
};
