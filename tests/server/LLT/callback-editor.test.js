// @test S-LLT-030
// @requirements LLR-SRV-CALLBACK-016, LLR-SRV-CALLBACK-017, LLR-SRV-CALLBACK-021, LLR-SRV-CALLBACK-023, LLR-SRV-CALLBACK-024, LLR-SRV-UI-016
// @environment portable
// @plan Execute the callback controller with recording DOM/API boundaries. Verify deadline and SMTP payloads retain opening revisions, blank/explicit-clear secret intent, rejected saves retain drafts, close buttons remove dialogs, cancellation targets the selected request and delivery summaries distinguish missing, failed and partially accepted addresses.
// @pass Controller assertions must pass without network access; these checks verify UI requests and feedback, not actual SMTP delivery, server persistence or physical rendering.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const vm = require('../../../build_tools/coverage-js.cjs');

class Element {
  constructor(tag, text) {
    this.tag = tag;
    this.textContent = text || '';
    this.children = [];
    this.events = {};
    this.classList = { add() {} };
    this.attributes = {};
  }
  append(...children) {
    for (const child of children) {
      child.parentElement = this;
      this.children.push(child);
    }
  }
  prepend(child) {
    this.children = [child, ...this.children.filter((v) => v !== child)];
  }
  replaceChildren(...children) {
    this.children = children;
  }
  setAttribute(key, value) {
    this.attributes[key] = value;
  }
  addEventListener(key, value) {
    this.events[key] = value;
  }
  showModal() {
    this.open = true;
  }
  close() {
    this.open = false;
    this.events.close?.();
  }
  remove() {
    this.removed = true;
  }
}
const text = (node) => [node.textContent, ...node.children.map(text)].join(' ');

function fixture() {
  const elements = [],
    requests = [],
    pending = [],
    errors = [],
    notices = [],
    refreshed = [];
  const state = {
    model: {
      configuration_version: 7,
      callback_settings: { email_after_hours: 1, remove_after_hours: 4 },
      smtp: {
        enabled: true,
        host: 'mail.example.test',
        port: 587,
        security: 'starttls',
        username: 'user',
        password_set: true,
        from: 'sender@example.test',
      },
      users: {
        target: { name: 'Target', type: 'app', emails: ['a@example.test', 'B@example.test'] },
      },
      callbacks: [],
    },
    refresh: async (force) => refreshed.push(force),
  };
  const el = (tag, label) => {
    const node = new Element(tag, label);
    elements.push(node);
    return node;
  };
  const button = (label, action) => {
    const node = el('button', label);
    node.action = action;
    return node;
  };
  const context = {
    state,
    document: { body: el('body') },
    el,
    $: () => el('div'),
    panel: (label) => el('section', label),
    avatar: (user) => el('span', user.name),
    badge: (label, style) => {
      const node = el('span', label);
      node.style = style;
      return node;
    },
    setView: (...nodes) => {
      context.view = nodes;
    },
    actionButton: button,
    iconButton: (label, icon, action) => button(label, action),
    registered: () => context.connected,
    notice: (message) => notices.push(message),
    api: async (url, method, value) => {
      requests.push({ url, method, value });
      if (context.failure) throw Error(context.failure);
    },
    submit: (form, action, errorId) =>
      pending.push(action().catch((error) => errors.push({ errorId, message: error.message }))),
  };
  const file = path.resolve(__dirname, '../../../zmala_server/web/admin-callbacks.js');
  const source = vm
    .source(file)
    .replace(/^import[^;]+;\s*/gm, '')
    .replace(/^export /gm, '');
  vm.runInNewContext(source, context);
  return Object.assign(context, {
    elements,
    requests,
    pending,
    errors,
    notices,
    refreshed,
    find: (tag) => elements.findLast((node) => node.tag === tag),
    field: (name) => elements.findLast((node) => node.name === name),
    button: (label) =>
      elements.findLast((node) => node.tag === 'button' && node.textContent === label),
    save: async () => {
      context.find('form').onsubmit({ preventDefault() {} });
      await pending.at(-1);
    },
  });
}

test('deadline draft preserves fractional values and revision, rejected save stays open', async () => {
  const f = fixture();
  f.openCallbackDeadlines();
  const dialog = f.find('dialog');
  assert.equal(dialog.attributes['aria-label'], 'Callback deadlines');
  f.field('emailDelay').value = '0.5';
  f.field('removalDelay').value = '2.25';
  f.state.model.configuration_version = 99;
  f.failure = 'Configuration changed; reload the editor';
  await f.save();
  assert.equal(dialog.open, true);
  assert.equal(f.field('emailDelay').value, '0.5');
  assert.equal(f.errors[0].errorId, 'deadline-error');
  assert.equal(f.refreshed.length, 0);
  f.failure = null;
  await f.save();
  assert.deepEqual(JSON.parse(JSON.stringify(f.requests.at(-1))), {
    url: '/api/callback-settings',
    method: 'PUT',
    value: {
      email_after_hours: 0.5,
      remove_after_hours: 2.25,
      configuration_version: 7,
    },
  });
  assert.equal(dialog.open, false);
  assert.equal(dialog.removed, true);
  assert.deepEqual(f.refreshed, [true]);
  assert.match(f.notices[0], /Saved callback deadlines/);
});

test('SMTP editor sends explicit secret intent and never sends stored secret content', async () => {
  for (const passwordSet of [false, true]) {
    const f = fixture();
    f.state.model.smtp.password_set = passwordSet;
    f.openCallbackSmtp();
    assert.equal(f.field('password').value, '');
    assert.match(
      f.field('password').placeholder,
      passwordSet ? /keep current/ : /Provider password/,
    );
    f.field('enabled').checked = false;
    f.field('host').value = 'relay.example.test';
    f.field('port').value = '465';
    f.find('select').value = 'tls';
    f.field('username').value = 'new-user';
    f.field('clearPassword').checked = true;
    f.field('from').value = 'new@example.test';
    f.state.model.configuration_version = 42;
    f.failure = 'Invalid mail settings';
    await f.save();
    assert.equal(f.find('dialog').open, true);
    assert.equal(f.errors[0].errorId, 'smtp-error');
    f.failure = null;
    await f.save();
    const sent = JSON.parse(JSON.stringify(f.requests.at(-1)));
    assert.deepEqual(sent, {
      url: '/api/smtp-settings',
      method: 'PUT',
      value: {
        enabled: false,
        host: 'relay.example.test',
        port: 465,
        security: 'tls',
        username: 'new-user',
        password: '',
        clear_password: true,
        from: 'new@example.test',
        configuration_version: 7,
      },
    });
    assert.equal(f.find('dialog').removed, true);
    assert.match(f.notices[0], /Saved email server/);
  }
});

test('closing or cancelling either editor removes it without issuing a write', async () => {
  for (const method of ['openCallbackDeadlines', 'openCallbackSmtp']) {
    for (const label of [
      'Cancel',
      method === 'openCallbackSmtp' ? 'Close Email server' : 'Close Callback deadlines',
    ]) {
      const f = fixture();
      f[method]();
      await f.button(label).action();
      assert.equal(f.find('dialog').removed, true);
      assert.equal(f.requests.length, 0);
    }
  }
});

test('callback rows distinguish delivery progress, cancellation and connection-only checks', async () => {
  const f = fixture();
  const base = {
    id: 'request-1',
    from: 'source',
    from_name: 'Source',
    to: 'target',
    to_name: 'Target',
    created_at: '2026-10-18T00:00:00Z',
    expires_at: '2026-10-19T00:00:00Z',
    email_due_at: '2026-10-18T01:00:00Z',
    status: 'pending',
  };
  assert.equal(f.callbackEmailStatus({ ...base, status: 'completed' }), '');
  assert.match(f.callbackEmailStatus({ ...base, email_error: 'Try later.' }), /Try later.*retry/);
  assert.match(
    f.callbackEmailStatus({ ...base, email_sent_to: ['A@EXAMPLE.TEST'] }),
    /1 address.*1 more/,
  );
  assert.match(
    f.callbackEmailStatus({ ...base, email_sent_to: ['A@EXAMPLE.TEST', 'b@example.test'] }),
    /2 addresses/,
  );
  f.state.model.smtp.enabled = false;
  assert.match(f.callbackEmailStatus(base), /disabled/);
  f.state.model.smtp.enabled = true;
  assert.match(f.callbackEmailStatus(base), /Email reminder/);
  f.state.model.users.target.emails = [];
  assert.match(f.callbackEmailStatus(base), /needs an email address/);
  for (const [kind, connected, notified, ready, status, expected] of [
    ['app', false, null, false, 'pending', 'Push can still deliver'],
    ['app', true, null, false, 'pending', 'Waiting for the phone'],
    ['app', true, 'now', true, 'pending', 'does not confirm it was read'],
    ['terminal', true, null, true, 'pending', 'receiving terminal'],
    ['terminal', true, null, false, 'completed', 'completed'],
  ]) {
    f.state.model.users.target.type = kind;
    f.connected = connected;
    f.state.model.callbacks = [{ ...base, notified_at: notified, ready, status }];
    f.renderCallbacks();
    assert.doesNotMatch(
      f.view.map(text).join(' '),
      /does not yet display|when both people are available/,
    );
    assert.match(f.view.map(text).join(' '), new RegExp(expected));
    if (ready) assert.match(f.view.map(text).join(' '), /Both online/);
  }
  f.state.model.callbacks = [base];
  f.renderCallbacks();
  await f.button('Cancel').action();
  assert.equal(f.requests.at(-1).url, '/api/callbacks/request-1');
  assert.equal(f.requests.at(-1).method, 'DELETE');
  assert.deepEqual(f.refreshed, [true]);
  await f.button('Check connection').action();
  assert.equal(f.requests.at(-1).url, '/api/smtp-settings/verify');
  assert.equal(f.requests.length, 2);
  assert.match(f.notices.at(-1), /authentication succeeded/);
  await f.button('Edit deadlines').action();
  assert.equal(f.find('dialog').open, true);
  await f.button('Email server').action();
  assert.equal(f.find('dialog').open, true);
  f.state.model.callback_settings.email_after_hours = 0.5;
  f.state.model.smtp.enabled = false;
  delete f.state.model.callbacks;
  f.renderCallbacks();
  assert.match(f.view.map(text).join(' '), /0.5 hours.*disabled.*No callback requests/s);
});
