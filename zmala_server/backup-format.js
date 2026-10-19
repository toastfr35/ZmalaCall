// @ts-check
'use strict';
// A versioned, bounded file map; no archive paths or executable restore content.
const crypto = require('node:crypto');
const { isIP } = require('node:net');
const { promisify } = require('node:util');
const zlib = require('node:zlib');
const {
  accountId,
  accountFields,
  autoAnswerFields,
  validateGroup,
  validateEmails,
} = require('./validation');
const { terminalProfileFields } = require('./terminal-settings');
const { validateCallbackSettings, validateSmtpSettings } = require('./callback-settings');
const { checkDimensions } = require('./photos');
const MAX_BACKUP = 64 * 1024 * 1024;
const FILES = ['server.json', 'admin-password.json', 'callbacks.json', 'console-jobs.json'];
const PHOTO = /^photos\/[a-f0-9]{64}\.(png|jpg)$/;
/** @param {Buffer} bytes */
const digest = (bytes) => crypto.createHash('sha256').update(bytes).digest('hex');
/** @param {unknown} value @param {string} message @returns {asserts value} */
function requireValue(value, message = 'Invalid backup contents.') {
  if (!value) throw Error(message);
}
/** @param {unknown} value @returns {Record<string, any>} */
function object(value) {
  requireValue(value && typeof value === 'object' && !Array.isArray(value));
  return /** @type {Record<string, any>} */ (value);
}
/** @param {Buffer | string} bytes */
function parse(bytes) {
  return JSON.parse(bytes.toString(), (key, value) => {
    requireValue(!['__proto__', 'constructor', 'prototype'].includes(key));
    return value;
  });
}
/** @param {unknown} value @param {number} [limit] */
const text = (value, limit = 256) => typeof value === 'string' && value.length <= limit;
/** @param {unknown} value */
const date = (value) => text(value, 40) && Number.isFinite(Date.parse(String(value)));

// @llr LLR-SRV-BACKUP-004, LLR-SRV-BACKUP-005
/** Validate every field consumed at startup or by a terminal before staging.
 * @param {Map<string, Buffer>} files */
function validateFiles(files) {
  for (const name of FILES) requireValue(files.has(name), 'Backup is missing ' + name);
  const state = object(parse(files.get('server.json') || ''));
  requireValue([6, 7].includes(state.schema_version), 'Unsupported server configuration version.');
  requireValue(
    Number.isSafeInteger(state.configuration_version) && state.configuration_version >= 0,
  );
  requireValue(isIP(state.host) === 4 && text(state.admin_token) && state.admin_token.length >= 16);
  for (const port of [state.http_port, state.sip_port])
    requireValue(Number.isInteger(port) && port > 0 && port <= 65535);
  requireValue(state.http_port !== state.sip_port);
  const users = object(state.users),
    profiles = object(state.profiles),
    groups = object(state.groups);
  requireValue(Object.keys(users).length <= 40 && Object.keys(groups).length <= 1000);
  const identities = new Set(),
    tokens = new Set();
  for (const [id, raw] of Object.entries(users)) {
    requireValue(accountId(id));
    const user = object(raw);
    accountFields({
      ...user,
      type: state.schema_version === 6 && user.type === 'linphone' ? 'app' : user.type,
      emails: undefined,
    });
    requireValue(Array.isArray(user.emails));
    if (user.emails.length) validateEmails(user.emails);
    requireValue(text(user.password, 128) && user.password.length > 0);
    if (user.photo)
      requireValue(files.has(user.photo.slice(1)), 'A referenced picture is missing.');
    if (user.type === 'terminal' || (state.schema_version === 7 && user.type === 'app')) {
      requireValue(
        text(user.device_id, 128) && user.device_id.length > 0 && !identities.has(user.device_id),
      );
      requireValue(
        text(user.device_token) && user.device_token.length >= 16 && !tokens.has(user.device_token),
      );
      identities.add(user.device_id);
      tokens.add(user.device_token);
    }
    if (user.type === 'terminal') {
      requireValue(
        typeof user.auto_answer === 'boolean' && typeof user.auto_answer_seconds === 'number',
      );
      autoAnswerFields(user);
      const profile = object(profiles[id]);
      terminalProfileFields(/** @type {import('./types/contracts').TerminalProfile} */ (profile), {
        ...profile,
        ...object(profile.terminal_settings),
      });
    } else requireValue(!Object.hasOwn(profiles, id));
  }
  for (const id of Object.keys(profiles))
    requireValue(accountId(id) && users[id]?.type === 'terminal');
  requireValue(
    state.local_terminal_id === null || Object.hasOwn(profiles, state.local_terminal_id),
  );
  for (const [id, group] of Object.entries(groups)) {
    requireValue(accountId(id));
    validateGroup(object(group), users);
  }
  validateCallbackSettings(object(state.callback_settings));
  const smtp = object(state.smtp);
  validateSmtpSettings(smtp, /** @type {import('./types/contracts').ServerState['smtp']} */ (smtp));
  const password = object(parse(files.get('admin-password.json') || ''));
  requireValue(
    typeof password.password_hash === 'string' &&
      /^[a-f0-9]{32}:[a-f0-9]{128}$/.test(password.password_hash),
    'Backup must contain an administrator password.',
  );
  for (const name of ['callbacks.json', 'console-jobs.json']) {
    const records = parse(files.get(name) || '');
    requireValue(Array.isArray(records) && records.length <= 10000);
    const ids = new Set();
    for (const raw of records) {
      const row = object(raw);
      requireValue(
        typeof row.id === 'string' &&
          /^[a-f0-9-]{36}$/.test(row.id) &&
          !ids.has(row.id) &&
          date(row.created_at),
      );
      ids.add(row.id);
      if (name === 'callbacks.json') {
        requireValue(
          accountId(row.from) &&
            accountId(row.to) &&
            ['pending', 'completed', 'cancelled', 'expired'].includes(row.status),
        );
        for (const key of ['email_due_at', 'expires_at']) requireValue(date(row[key]));
        for (const key of ['notified_at', 'emailed_at', 'finished_at', 'email_retry_at'])
          requireValue(row[key] == null || date(row[key]));
        requireValue(Array.isArray(row.email_sent_to) && row.email_sent_to.every((v) => text(v)));
        requireValue(row.email_error == null || text(row.email_error, 10000));
      } else {
        requireValue(
          accountId(row.terminal_id) && (row.device_id === undefined || text(row.device_id, 128)),
        );
        requireValue(
          text(row.command, 16000) && text(row.stdout, 200000) && text(row.stderr, 200000),
        );
        requireValue(
          ['queued', 'running', 'lost', 'completed', 'failed', 'timed_out', 'cancelled'].includes(
            row.status,
          ),
        );
        requireValue(
          row.shell === undefined ||
            ['sh', 'bash', 'cmd', 'pwsh', 'powershell'].includes(row.shell),
        );
        requireValue(
          Number.isInteger(row.timeout_seconds) &&
            row.timeout_seconds >= 1 &&
            row.timeout_seconds <= 300,
        );
        requireValue(
          typeof row.truncated === 'boolean' &&
            (row.exit_code === null || Number.isInteger(row.exit_code)),
        );
        for (const key of ['started_at', 'finished_at'])
          requireValue(row[key] === undefined || date(row[key]));
        requireValue(row.lease === undefined || text(row.lease));
      }
    }
  }
  return state;
}

// @llr LLR-SRV-BACKUP-004, LLR-SRV-BACKUP-005
/** @param {Buffer} bytes */
async function decodeBackup(bytes) {
  requireValue(bytes.length <= MAX_BACKUP, 'Backup exceeds 64 MB.');
  let archive;
  try {
    archive = object(parse(await promisify(zlib.gunzip)(bytes, { maxOutputLength: MAX_BACKUP })));
  } catch {
    throw Error('Choose a valid Zmala server backup (up to 64 MB expanded).');
  }
  requireValue(
    archive.format === 'zmalacall-server-backup' && archive.version === 1,
    'Unsupported backup format.',
  );
  requireValue(
    date(archive.created_at) && Array.isArray(archive.files) && archive.files.length <= 1004,
  );
  /** @type {Map<string, Buffer>} */
  const files = new Map();
  for (const raw of archive.files) {
    const entry = object(raw),
      name = entry.name;
    requireValue(
      typeof name === 'string' && (FILES.includes(name) || PHOTO.test(name)) && !files.has(name),
    );
    requireValue(typeof entry.data === 'string' && /^[A-Za-z0-9+/]*={0,2}$/.test(entry.data));
    const data = Buffer.from(entry.data, 'base64');
    requireValue(
      data.toString('base64') === entry.data && digest(data) === entry.sha256,
      'Backup checksum failed.',
    );
    if (PHOTO.test(name)) {
      requireValue(
        name.split('/')[1].split('.')[0] === digest(data),
        'Picture filename checksum failed.',
      );
      checkDimensions(data, name.endsWith('.png') ? 'png' : 'jpg');
    }
    files.set(name, data);
  }
  const state = validateFiles(files);
  return { files, state, created_at: String(archive.created_at) };
}

// @llr LLR-SRV-BACKUP-004
/** @param {Map<string, Buffer>} files */
async function encodeBackup(files) {
  const archive = {
    format: 'zmalacall-server-backup',
    version: 1,
    created_at: new Date().toISOString(),
    files: [...files].map(([name, data]) => ({
      name,
      sha256: digest(data),
      data: data.toString('base64'),
    })),
  };
  const bytes = Buffer.from(JSON.stringify(archive));
  requireValue(bytes.length <= MAX_BACKUP, 'Backup exceeds the 64 MB expanded limit.');
  return promisify(zlib.gzip)(bytes);
}
module.exports = {
  MAX_BACKUP,
  FILES,
  PHOTO,
  digest,
  parse,
  validateFiles,
  decodeBackup,
  encodeBackup,
};
