// @ts-check
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { defaultState, lanAddress } = require('./defaults');
const { own, accountId, validateGroup, autoAnswerFields } = require('./validation');
const { terminalProfileFields } = require('./terminal-settings');
const { AccountStore } = require('./accounts');
const { ContactDirectory } = require('./contact-directory');
const { migrate } = require('./migrations');
const { readJson, writeJson } = require('./json-file');
const { SnapshotFile } = require('./snapshot-file');
const { loadSecureCalls } = require('./secure-calls');
const { AdminPassword, passwordFile } = require('./admin-password');
const { validateCallbackSettings, validateSmtpSettings, smtpView } = require('./callback-settings');
const DATA = path.resolve(__dirname, 'data');
const LANGUAGES = require('../zmala_terminal/common/shared/terminal-languages.json');
const { ringtoneList, validateSound, MAX_LIBRARY } = require('./ringtones');

/** Authoritative configuration and derived views. Mutations commit one versioned snapshot. */
class Store extends AccountStore {
  constructor(dataDir = DATA) {
    fs.mkdirSync(dataDir, { recursive: true });
    const file = path.join(dataDir, 'server.json');
    super(readJson(file, defaultState));
    this.secureCalls = loadSecureCalls();
    /** @type {InstanceType<typeof import('./snapshot-file').SnapshotFile> | undefined} */
    this.persistence = undefined;
    this.directory = new ContactDirectory(() => this.value);
    this.dir = dataDir;
    this.file = file;
    this.ringtoneUpload = false;
    // Custom stores (tests/setup tools) stay isolated from the real Pi boot partition.
    const credentialFile =
      dataDir === DATA ? process.env.ZMALA_ADMIN_PASSWORD_FILE || passwordFile(dataDir) : undefined;
    this.adminPassword = new AdminPassword(dataDir, this.value.admin_password_hash, credentialFile);
    delete this.value.admin_password_hash;
    migrate(this.value);
    this.save();
  }

  save() {
    if (this.persistence) return this.persistence.write(JSON.stringify(this.value, null, 2));
    writeJson(this.file, this.value);
  }
  /** Production HTTP enables asynchronous writes after synchronous startup/migration.
   * Standalone setup tools retain their immediate save contract. */
  enableAsyncPersistence() {
    this.persistence ??= new SnapshotFile(this.file);
  }
  // @llr LLR-SRV-DATA-015
  async flush() {
    await this.persistence?.flush();
  }
  changed() {
    this.value.configuration_version++;
    this.save();
  }
  /** @param {unknown} id @returns {import('./types/contracts').TerminalProfile} */
  requireTerminal(id) {
    if (typeof id !== 'string' || !this.terminal(id)) throw Error('Choose a terminal account.');
    return this.value.profiles[id];
  }
  /** Return a narrowed account only after checking the persisted discriminator.
   * @param {unknown} id @returns {import('./types/contracts').TerminalAccount | null} */
  terminalAccount(id) {
    if (typeof id !== 'string' || !own(this.value.users, id)) return null;
    const account = this.value.users[id];
    return account.type === 'terminal' ? account : null;
  }
  // @llr LLR-SRV-APP-003
  /** @param {unknown} id @returns {import('./types/contracts').Account | null} */
  enrolledAccount(id) {
    return typeof id === 'string' && own(this.value.users, id) ? this.value.users[id] : null;
  }
  // @llr LLR-SRV-APP-003
  /** App views contain no Pi controls or other accounts' credentials. @param {string} id */
  appConfig(id) {
    const user = this.enrolledAccount(id);
    if (!user || user.type !== 'app') throw Error('Choose an app account.');
    const v = this.value;
    return {
      schema_version: 1,
      configuration_version: v.configuration_version,
      account_type: 'app',
      call_photo_sharing: true,
      device_id: user.device_id,
      display_name: user.name,
      call_auth_key: user.device_token,
      sip: {
        username: id,
        password: user.password,
        domain: v.host,
        proxy: this.secureCalls?.proxy() || `sip:${v.host}:${v.sip_port};transport=udp`,
      },
      ...(this.secureCalls ? { secure_calls: this.secureCalls.configuration(id) } : {}),
      contacts: this.directory
        .contacts(id)
        .filter((c) => c.can_call || c.can_receive)
        .map((c) => ({ ...c, account_type: v.users[c.id].type, sip_uri: `sip:${c.id}@${v.host}` })),
    };
  }
  /** @param {string | undefined} token */
  // @llr LLR-SRV-AUTH-020
  deviceAccount(token) {
    return token
      ? Object.keys(this.value.users).find((id) => this.enrolledAccount(id)?.device_token === token)
      : undefined;
  }
  /** @param {unknown} from @param {unknown} to */
  permitted(from, to) {
    return this.directory.permitted(from, to);
  }
  /** @param {string} id */
  accountGroups(id) {
    return Object.entries(this.value.groups)
      .filter(([, g]) => g.members.includes(id))
      .map(([key]) => key);
  }
  /** @param {import('./types/contracts').JsonObject} update */
  createGroup(update) {
    if (Object.keys(this.value.groups).length >= 1000)
      throw Error('At most 1000 groups are supported.');
    const fields = this.groupFields(update),
      id = 'group-' + crypto.randomBytes(8).toString('hex');
    this.value.groups[id] = fields;
    this.changed();
    return id;
  }
  /** @param {import('./types/contracts').JsonObject} update @param {string} [id] */
  groupFields(update, id) {
    const fields = validateGroup(update, this.value.users);
    if (
      Object.entries(this.value.groups).some(
        ([key, g]) => key !== id && g.name.toLowerCase() === fields.name.toLowerCase(),
      )
    )
      throw Error('Choose a unique group name.');
    return fields;
  }
  /** @param {string} id @param {import('./types/contracts').JsonObject} update */
  updateGroup(id, update) {
    if (!accountId(id) || !own(this.value.groups, id)) throw Error('Group not found.');
    this.value.groups[id] = this.groupFields(update, id);
    this.changed();
  }
  /** @param {string} id */
  deleteGroup(id) {
    if (!accountId(id) || !own(this.value.groups, id)) throw Error('Group not found.');
    delete this.value.groups[id];
    this.changed();
  }
  /** @param {string} id */
  contacts(id) {
    this.requireTerminal(id);
    return this.directory.contacts(id);
  }
  // @llr LLR-SRV-CONFIG-022
  /** @param {string | null} [id] @returns {import('./types/contracts').TerminalConfiguration} */
  config(id = this.value.local_terminal_id) {
    const p = this.requireTerminal(id),
      v = this.value,
      u = this.terminalAccount(id);
    if (!u || id === null) throw Error('Choose a terminal account.');
    return {
      schema_version: 1,
      configuration_version: v.configuration_version,
      device_id: u.device_id,
      account_type: 'terminal',
      call_photo_sharing: true,
      display_name: p.display_name,
      language: p.language || 'en',
      command_shell: p.command_shell || 'powershell',
      audio_profile: p.audio_profile || 'normal',
      video_resolution: p.video_resolution || '720p',
      video_fps: p.video_fps ?? 15,
      auto_framing: p.auto_framing === true,
      carousel_portraits: p.carousel_portraits ?? 3,
      tv_idle_seconds: p.tv_idle_seconds ?? 30,
      c20_speaker_volume: p.c20_speaker_volume ?? 50,
      ringtone_volume: p.ringtone_volume ?? p.c20_speaker_volume ?? 50,
      action_sound_volume: p.action_sound_volume ?? 20,
      ringtone: p.ringtone ?? 'nokia',
      ringtones: ringtoneList(v.ringtones),
      server_host: v.host,
      sip_port: v.sip_port,
      auto_answer: u.auto_answer,
      auto_answer_seconds: u.auto_answer_seconds,
      call_auth_key: u.device_token,
      sip: {
        username: id,
        password: u.password,
        domain: v.host,
        proxy: this.secureCalls?.proxy() || `sip:${v.host}:${v.sip_port};transport=udp`,
      },
      ...(this.secureCalls ? { secure_calls: this.secureCalls.configuration(id) } : {}),
      contacts: this.contacts(id).map((c) => ({ ...c, sip_uri: `sip:${c.id}@${v.host}` })),
      terminal_settings: p.terminal_settings,
    };
  }
  // @llr LLR-SRV-ENROLL-005
  /** @param {string | null} [id] @param {boolean} [lan]
   * @returns {import('./types/contracts').Enrollment} */
  bootstrap(id = this.value.local_terminal_id, lan = false) {
    const u = this.enrolledAccount(id);
    return {
      ...(u?.type === 'app' ? { account_type: /** @type {const} */ ('app') } : {}),
      server_url:
        this.secureCalls?.httpsUrl ||
        `http://${lan ? this.value.host : '127.0.0.1'}:${this.value.http_port}`,
      device_id: u?.device_id || 'unassigned',
      device_token: u?.device_token || '',
    };
  }

  /** @param {string | null} id @param {import('./types/contracts').JsonObject} update */
  setSettings(id, update) {
    const p = this.requireTerminal(id),
      account = this.terminalAccount(id);
    if (!account) throw Error('Choose a terminal account.');
    const fields = terminalProfileFields(p, update);
    if (fields.ringtone !== 'nokia' && !own(this.value.ringtones || {}, fields.ringtone || ''))
      throw Error('Choose an available ringtone.');
    const answer = autoAnswerFields(update);
    Object.assign(p, fields);
    // Auto-answer remains stored on the account for existing terminal clients.
    Object.assign(account, answer);
    this.changed();
  }
  /** @param {string} id */
  // @llr LLR-SRV-CONFIG-019
  ringTimeout(id) {
    const account = this.terminalAccount(id);
    return account?.auto_answer ? Math.max(60, (account.auto_answer_seconds || 5) + 30) : 60;
  }
  // @llr LLR-SRV-CONFIG-021
  /** Device-scoped, field-level compare-and-set; never accepts account/media credentials.
   * @param {string} id @param {import('./types/contracts').JsonObject} changes
   * @param {import('./types/contracts').JsonObject} expected */
  setDeviceSettings(id, changes, expected) {
    const allowed = [
      'language',
      'auto_answer',
      'auto_answer_seconds',
      'auto_framing',
      'c20_speaker_volume',
      'ringtone_volume',
      'action_sound_volume',
      'carousel_portraits',
      'tv_idle_seconds',
      'ringtone',
    ];
    const keys = Object.keys(changes);
    if (
      !keys.length ||
      keys.some((key) => !allowed.includes(key)) ||
      Object.keys(expected).length !== keys.length ||
      keys.some((key) => !own(expected, key))
    )
      throw Error('Invalid local terminal settings.');
    const current = /** @type {unknown} */ (this.config(id));
    const values = /** @type {Record<string, unknown>} */ (current);
    if (keys.some((key) => values[key] !== expected[key] && values[key] !== changes[key]))
      throw Object.assign(Error('This setting changed on the server. Try again.'), { status: 409 });
    // A retry after a lost HTTP acknowledgement still reaches the route's
    // persistence barrier, but must not create another revision or SD write.
    if (keys.every((key) => values[key] === changes[key])) return;
    const p = this.requireTerminal(id);
    this.setSettings(id, { display_name: p.display_name, ...p.terminal_settings, ...changes });
  }
  // @llr LLR-SRV-DIR-027
  /** @param {unknown} serial @param {string} accountId */
  associateTerminal(serial, accountId) {
    const v = this.value;
    this.requireTerminal(accountId);
    const previous = Object.keys(v.profiles).find(
      (id) => this.terminalAccount(id)?.device_id === serial,
    );
    if (!previous) throw Error('Terminal serial number not found.');
    if (previous === accountId) return previous;
    // Enrollment and device settings follow the serial; SIP identity and groups stay on accounts.
    const first = this.terminalAccount(previous),
      second = this.terminalAccount(accountId);
    if (!first || !second) throw Error('Choose a terminal account.');
    /** @param {import('./types/contracts').TerminalAccount} account */
    const enrollment = ({ device_id, device_token, auto_answer, auto_answer_seconds }) => ({
      device_id,
      device_token,
      auto_answer,
      auto_answer_seconds,
    });
    const oldEnrollment = enrollment(first);
    Object.assign(first, enrollment(second));
    Object.assign(second, oldEnrollment);
    [v.profiles[previous], v.profiles[accountId]] = [v.profiles[accountId], v.profiles[previous]];
    // The display name belongs to the account, unlike its media/device preferences.
    [v.profiles[previous].display_name, v.profiles[accountId].display_name] = [
      v.profiles[accountId].display_name,
      v.profiles[previous].display_name,
    ];
    if (v.local_terminal_id === previous) v.local_terminal_id = accountId;
    else if (v.local_terminal_id === accountId) v.local_terminal_id = previous;
    this.changed();
    return previous;
  }
  /** @param {string} id */
  selectTerminal(id) {
    this.requireTerminal(id);
    this.value.local_terminal_id = id;
    this.changed();
  }
  // @llr LLR-SRV-CONFIG-024
  /** @param {unknown} name @param {Buffer} bytes @param {number} [expectedVersion] */
  async uploadRingtone(name, bytes, expectedVersion) {
    if (typeof name !== 'string' || !name.trim() || name.trim().length > 80 || /\p{Cc}/u.test(name))
      throw Error('Enter a ringtone name of up to 80 characters.');
    const id = validateSound(bytes);
    if (this.ringtoneUpload)
      throw Object.assign(Error('Another ringtone is uploading. Try again.'), { status: 409 });
    this.ringtoneUpload = true;
    try {
      const checkVersion = () => {
        if (expectedVersion !== undefined && expectedVersion !== this.value.configuration_version)
          throw Object.assign(Error('Configuration changed. Reopen settings before importing.'), {
            status: 409,
          });
      };
      checkVersion();
      const library = this.value.ringtones || {};
      const entries = Object.entries(library).filter(([key]) => key !== id);
      if (
        entries.length >= 64 ||
        entries.reduce((sum, [, sound]) => sum + sound.bytes, bytes.length) > MAX_LIBRARY
      )
        throw Error('The ringtone library is full (64 sounds or 40 MB).');
      const folder = path.join(this.dir, 'ringtones');
      await fs.promises.mkdir(folder, { recursive: true });
      const temporary = path.join(folder, crypto.randomUUID() + '.tmp');
      try {
        const handle = await fs.promises.open(temporary, 'wx', 0o600);
        try {
          await handle.writeFile(bytes);
          await handle.sync();
        } finally {
          await handle.close();
        }
        checkVersion();
        await fs.promises.rename(temporary, path.join(folder, id + '.wav'));
        if (process.platform !== 'win32') {
          const directory = await fs.promises.open(folder, 'r');
          try {
            await directory.sync();
          } finally {
            await directory.close();
          }
        }
      } finally {
        await fs.promises.rm(temporary, { force: true });
      }
      if (library[id]?.name !== name.trim() || library[id]?.bytes !== bytes.length) {
        try {
          checkVersion();
        } catch (error) {
          if (!this.value.ringtones?.[id])
            await fs.promises.rm(path.join(folder, id + '.wav'), { force: true });
          throw error;
        }
        this.value.ringtones = { ...library, [id]: { name: name.trim(), bytes: bytes.length } };
        this.changed();
      }
      const configuration_version = this.value.configuration_version;
      await this.flush();
      return { id, name: name.trim(), url: `/api/ringtones/${id}.wav`, configuration_version };
    } finally {
      this.ringtoneUpload = false;
    }
  }

  admin() {
    const v = this.value;
    return {
      ...v,
      ringtone_choices: ringtoneList(v.ringtones),
      sip_proxy: this.secureCalls?.proxy() || `sip:${v.host}:${v.sip_port};transport=udp`,
      call_transport: this.secureCalls ? 'TLS with encrypted TURN relay' : 'LAN UDP relay',
      // Administrative views include account provisioning credentials, but
      // never the admin password hash or the retired shortcut credential.
      admin_token: undefined,
      smtp: smtpView(v.smtp),
      terminal_languages: Object.entries(LANGUAGES).map(([code, { name, native }]) => ({
        code,
        name,
        native,
      })),
      account_groups: Object.fromEntries(
        Object.keys(v.users).map((id) => [id, this.accountGroups(id)]),
      ),
      terminal_contacts: Object.fromEntries(
        Object.keys(v.profiles).map((id) => [id, this.contacts(id)]),
      ),
    };
  }
  /** @param {import('./types/contracts').JsonObject} update */
  setCallbackSettings(update) {
    this.value.callback_settings = validateCallbackSettings(update);
    this.changed();
  }
  /** @param {import('./types/contracts').JsonObject} update */
  setSmtpSettings(update) {
    this.value.smtp = validateSmtpSettings(update, this.value.smtp);
    this.changed();
  }
}
module.exports = { Store, DATA, validateGroup, lanAddress };
