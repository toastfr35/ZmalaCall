// @ts-check
'use strict';
// Account mutations share Store validation and persistence; terminal identity remains device-owned.
const { random, profile } = require('./defaults');
const { randomUUID } = require('node:crypto');
const { own, accountId, accountFields, validateEmails } = require('./validation');
/** Account mutations validate before changing state; Store supplies persistence and group queries. */
class AccountStore {
  /** @param {import('./types/contracts').ServerState} value */
  constructor(value) {
    this.value = value;
  }
  /** Subclasses supply the persistence/version boundary. @abstract */
  changed() {
    throw Error('AccountStore requires a persistence implementation.');
  }
  /** @param {unknown} id */
  terminal(id) {
    return (
      typeof id === 'string' &&
      own(this.value.users, id) &&
      this.value.users[id].type === 'terminal'
    );
  }
  // @llr LLR-SRV-DIR-004
  /** @param {import('./types/contracts').JsonObject} update @returns {string} */
  createAccount(update) {
    const v = this.value,
      id = update.id;
    if (Object.keys(v.users).length >= 40) throw Error('At most 40 accounts are supported.');
    if (!accountId(id) || own(v.users, id))
      throw Error('Choose a unique username using lowercase letters, digits, - or _.');
    const fields = accountFields(update);
    const details = {
      name: fields.name,
      emails: validateEmails(update.emails),
      password: (typeof update.password === 'string' && update.password) || random(),
      photo: fields.photo || '',
    };
    v.users[id] =
      fields.type === 'terminal'
        ? this.makeTerminal(id, { ...fields, ...details })
        : { ...details, type: 'linphone' };
    this.changed();
    return id;
  }
  // @llr LLR-SRV-DIR-007
  /** Build a complete terminal before publishing it in the account map.
   * @param {string} id
   * @param {import('./types/contracts').AccountDetails & import('./types/contracts').AutoAnswerSettings} details
   * @returns {import('./types/contracts').TerminalAccount} */
  makeTerminal(id, details) {
    const account = {
      ...details,
      type: /** @type {const} */ ('terminal'),
      device_id: 'ZM-' + randomUUID(),
      device_token: random(),
      auto_answer: details.auto_answer ?? false,
      auto_answer_seconds: details.auto_answer_seconds ?? 5,
    };
    this.value.profiles[id] = profile(details.name);
    if (!this.value.local_terminal_id) this.value.local_terminal_id = id;
    return account;
  }
  // @llr LLR-SRV-DIR-005, LLR-SRV-DIR-008
  /** @param {string} id @param {import('./types/contracts').JsonObject} update @returns {string} */
  updateAccount(id, update) {
    const v = this.value;
    if (!accountId(id) || !own(v.users, id)) throw Error('Account not found.');
    const next = update.id === undefined ? id : update.id;
    if (!accountId(next) || (next !== id && own(v.users, next)))
      throw Error('Choose a unique username using lowercase letters, digits, - or _.');
    const fields = accountFields(update),
      u = v.users[id];
    const details = {
      name: fields.name,
      emails: fields.emails ?? u.emails,
      password: (typeof update.password === 'string' && update.password) || u.password,
      photo: fields.photo ?? u.photo,
    };
    if (fields.type === 'terminal') {
      if (u.type === 'terminal') Object.assign(u, fields, details);
      else v.users[id] = this.makeTerminal(id, { ...fields, ...details });
      v.profiles[id].display_name = details.name;
    } else if (u.type === 'linphone') Object.assign(u, details);
    else {
      // Replacing the discriminator also removes enrollment and auto-answer fields.
      const {
        device_id: _serial,
        device_token: _token,
        auto_answer: _answer,
        auto_answer_seconds: _delay,
        ...phone
      } = u;
      v.users[id] = { ...phone, ...details, type: 'linphone' };
      delete v.profiles[id];
      if (v.local_terminal_id === id)
        v.local_terminal_id = Object.keys(v.users).find((key) => this.terminal(key)) || null;
    }
    if (next !== id) {
      /** @template T @param {Record<string, T>} object @returns {Record<string, T>} */
      const rename = (object) =>
        Object.fromEntries(
          Object.entries(object).map(([key, value]) => [key === id ? next : key, value]),
        );
      v.users = rename(v.users);
      v.profiles = rename(v.profiles);
      for (const g of Object.values(v.groups))
        g.members = g.members.map((key) => (key === id ? next : key));
      for (const p of Object.values(v.profiles))
        for (const c of p.contacts || []) if (c.id === id) c.id = next;
      if (v.local_terminal_id === id) v.local_terminal_id = next;
    }
    this.changed();
    return next;
  }
  /** @param {string} id */
  deleteAccount(id) {
    const v = this.value;
    if (!accountId(id) || !own(v.users, id)) throw Error('Account not found.');
    delete v.users[id];
    delete v.profiles[id];
    for (const g of Object.values(v.groups)) g.members = g.members.filter((key) => key !== id);
    for (const p of Object.values(v.profiles))
      if (p.contacts) p.contacts = p.contacts.filter((c) => c.id !== id);
    if (v.local_terminal_id === id)
      v.local_terminal_id = Object.keys(v.users).find((key) => this.terminal(key)) || null;
    this.changed();
  }
}
module.exports = { AccountStore };
