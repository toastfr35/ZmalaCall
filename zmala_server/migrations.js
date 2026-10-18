'use strict';
// Upgrade persisted snapshots in place before Store exposes them; preserve existing identities and credentials.
const { own } = require('./validation');
const { defaultCallbackSettings, defaultSmtpSettings } = require('./callback-settings');
/** @param {import('./types/migrations').MigrationState} v */
function migrateLegacy(v) {
  if ([4, 5, 6].includes(v.schema_version)) return;
  if (v.schema_version === 3) {
    migrateGroups(v);
    v.configuration_version++;
    return;
  }
  if (v.schema_version === 2) {
    migrateAccountSettings(v);
    migrateGroups(v);
    v.configuration_version++;
    return;
  }
  if (v.schema_version !== 1) throw Error('Unsupported server configuration schema.');
  const legacy = v.contacts || [];
  v.permissions = {};
  v.profiles = {};
  v.local_terminal_id = own(v.users, 'terminal') ? 'terminal' : null;
  for (const [id, u] of Object.entries(v.users)) {
    u.type = id === 'terminal' ? 'terminal' : 'linphone';
    v.permissions[id] = {};
    if (u.type === 'terminal') {
      u.device_id = v.device_id;
      u.device_token = v.device_token;
      v.profiles[id] = {
        display_name: v.display_name,
        auto_answer_seconds: v.auto_answer_seconds,
        terminal_settings: v.terminal_settings,
        contacts: legacy.map(({ id, name, auto_answer, photo }) => ({
          id,
          name,
          auto_answer,
          photo,
        })),
      };
    }
  }
  for (const from of Object.keys(v.users))
    for (const to of Object.keys(v.users)) v.permissions[from][to] = false;
  for (const c of legacy)
    if (own(v.users, c.id) && v.local_terminal_id) {
      v.permissions.terminal[c.id] = c.can_call;
      v.permissions[c.id].terminal = c.can_receive;
    }
  for (const field of /** @type {const} */ ([
    'device_id',
    'device_token',
    'display_name',
    'auto_answer_seconds',
    'terminal_settings',
    'contacts',
  ]))
    delete v[field];
  v.schema_version = 2;
  migrateAccountSettings(v);
  migrateGroups(v);
  v.configuration_version++;
}
/** @param {import('./types/migrations').MigrationState} v */
function migrateAccountSettings(v) {
  for (const [id, p] of Object.entries(v.profiles)) {
    const u = v.users[id];
    u.auto_answer = (p.contacts || []).some(
      (c) => c.auto_answer === true && v.permissions?.[c.id]?.[id] === true,
    );
    u.auto_answer_seconds = p.auto_answer_seconds || 5;
    delete p.auto_answer_seconds;
    for (const c of p.contacts || []) delete c.auto_answer;
  }
  v.schema_version = 3;
}
/** @param {import('./types/migrations').MigrationState} v */
function migrateGroups(v) {
  const ids = Object.keys(v.users),
    pairs = [];
  for (let i = 0; i < ids.length; i++)
    for (let j = i + 1; j < ids.length; j++)
      if (v.permissions?.[ids[i]]?.[ids[j]] === true && v.permissions?.[ids[j]]?.[ids[i]] === true)
        pairs.push([ids[i], ids[j]]);
  // Pair groups retain mutual permissions without creating transitive access.
  v.groups = Object.fromEntries(
    pairs.map((members, index) => [
      pairs.length === 1 ? 'family' : 'legacy-' + (index + 1),
      {
        name: pairs.length === 1 ? 'Family' : 'Shared calls ' + (index + 1),
        description: 'Shared calls for these accounts.',
        members,
      },
    ]),
  );
  delete v.permissions;
  v.schema_version = 4;
}
// @llr LLR-SRV-DATA-006
/** Upgrade the writable legacy staging view before runtime callers use current contracts.
 * @param {import('./types/contracts').ServerState} state */
function migrate(state) {
  const v = /** @type {import('./types/migrations').MigrationState} */ (state);
  migrateLegacy(v);
  let resolutionChanged = false;
  for (const profile of Object.values(v.profiles)) {
    if (profile.video_fps === undefined) {
      profile.video_fps = 15;
      resolutionChanged = true;
    }
    if (profile.video_resolution === '360p') {
      profile.video_resolution = '480p';
      resolutionChanged = true;
    }
  }
  if (resolutionChanged) v.configuration_version++;
  if (v.schema_version === 4) {
    for (const p of Object.values(v.profiles)) delete p.contacts;
    v.schema_version = 5;
    v.configuration_version++;
  }
  if (v.schema_version === 5) {
    // Existing accounts need real addresses supplied by their administrator.
    for (const account of Object.values(v.users)) account.emails ??= [];
    v.callback_settings = defaultCallbackSettings();
    v.smtp = defaultSmtpSettings();
    v.schema_version = 6;
    v.configuration_version++;
  }
  if (v.callback_settings.email_after_minutes !== undefined) {
    v.callback_settings = {
      email_after_hours: v.callback_settings.email_after_minutes / 60,
      remove_after_hours: (v.callback_settings.remove_after_minutes ?? 240) / 60,
    };
    v.configuration_version++;
  }
}
module.exports = { migrate };
