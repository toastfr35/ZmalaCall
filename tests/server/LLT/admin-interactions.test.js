// @test S-LLT-001
// @requirements LLR-SRV-BACKUP-012, LLR-SRV-UI-014, LLR-SRV-UI-016, LLR-SRV-UI-018, LLR-SRV-UI-019, LLR-SRV-HOST-004
// @environment portable
// @plan Execute admin handlers with a small DOM/API double; assert focused row-action preservation during polling, revision ownership, stale modal-result rejection, clipboard cleanup and explicit backup confirmation before restore. Check portrait cache bounds/retries and URL ownership, confirmation error recovery, backup validation/restart failures, live overview/activity and SSH toggle errors, console output rendering and queued-command deletion.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const vm = require('../../../build_tools/coverage-js.cjs');

// Execute the actual controller modules with a small DOM boundary. Rendering and
// platform clipboard permissions are checked separately in the browser.
function load(name, context) {
  const source = vm
    .source(path.join(__dirname, '../../../zmala_server/web/admin-' + name + '.js'), 'utf8')
    .replace(/^import[^;]+;\s*/gm, '')
    .replace(/^export /gm, '');
  vm.runInNewContext(source, context);
  return context;
}

class Element {
  constructor(tag = '', text = '') {
    this.tag = tag;
    this.textContent = text;
    this.children = [];
    this.events = {};
    this.style = {};
    this.isConnected = true;
    this.scrollTop = this.scrollHeight = this.clientHeight = 0;
  }
  append(...children) {
    this.children.push(...children);
  }
  replaceChildren(...children) {
    this.children = children;
  }
  addEventListener(name, handler) {
    this.events[name] = handler;
  }
  showModal() {
    this.open = true;
  }
  close() {
    this.open = false;
    this.events.close?.();
  }
  setAttribute() {}
  closest() {
    return null;
  }
  reset() {}
  focus() {
    this.focused = true;
  }
  select() {
    this.selected = true;
  }
  remove() {
    this.isConnected = false;
  }
}

function clipboardFixture(clipboard, result = true) {
  const previous = new Element(),
    parent = new Element(),
    fields = [];
  const context = load('clipboard', {
    navigator: { clipboard },
    HTMLElement: Element,
    document: {
      activeElement: previous,
      body: new Element(),
      createElement(tag) {
        const field = new Element(tag);
        fields.push(field);
        return field;
      },
      execCommand(command) {
        assert.equal(command, 'copy');
        return result;
      },
    },
  });
  return { ...context, previous, parent, fields, owner: { closest: () => parent } };
}

function sharedFixture() {
  const nodes = new Map(),
    requests = [],
    revoked = [];
  const $ = (id) => {
    if (!nodes.has(id)) nodes.set(id, node('div'));
    return nodes.get(id);
  };
  function node(tag, text = '') {
    const e = new Element(tag, text);
    e.classList = { add() {} };
    e.scrollIntoView = () => {
      e.scrolled = true;
    };
    e.contains = (child) => e.children.includes(child);
    return e;
  }
  const state = {
    model: {
      sip_status: { registrations: [{ user: 'term' }], events: [], active_calls: 1 },
      profiles: { term: {} },
      terminal_statuses: { term: { last_seen: new Date().toISOString(), state: 'idle' } },
      callbacks: [],
    },
    photoUrls: new Map(),
    terminalCards: new Map(),
    refresh: async () => {},
    renderConnection: () => {},
  };
  const context = load('shared', {
    Error,
    File: class File {},
    HTMLElement: Element,
    HTMLDialogElement: Element,
    HTMLButtonElement: Element,
    $,
    state,
    page: '/',
    routes: { '/': ['Overview', '', ''] },
    document: {
      createElement: node,
      createTextNode: (text) => node('text', text),
      createElementNS: (_, tag) => node(tag),
      querySelectorAll: () => [],
      querySelector: () => node('heading'),
    },
    URL: { createObjectURL: () => 'blob:unit', revokeObjectURL: (url) => revoked.push(url) },
    fetch: async (url) => {
      requests.push(url);
      return context.response;
    },
  });
  return { context, node, $, requests, revoked };
}

test('shared photo cache deduplicates, bounds entries, retries failures and retains owned URLs', async () => {
  const f = sharedFixture(),
    c = f.context;
  c.response = { ok: true, blob: async () => ({ bytes: 'picture' }) };
  const account = { name: 'Alice', type: 'terminal', photo: '/photos/a.png' };
  const first = c.avatar(account),
    second = c.avatar(account);
  await new Promise(setImmediate);
  assert.equal(f.requests.length, 1);
  assert.equal(first.children[0].alt, 'Alice');
  assert.equal(second.children[0].src, 'blob:unit');
  const detached = c.avatar(account);
  detached.isConnected = false;
  await new Promise(setImmediate);
  assert.equal(detached.children.length, 0);
  for (let i = 0; i < 41; i++) await c.photoBlob('/photos/' + i + '.png');
  await c.photoBlob(account.photo);
  assert.equal(f.requests.filter((p) => p === account.photo).length, 2);
  c.response = { ok: false };
  c.avatar({ ...account, photo: '/bad' });
  await new Promise(setImmediate);
  c.response = { ok: true, blob: async () => ({}) };
  await c.photoBlob('/bad');
  assert.equal(f.requests.filter((p) => p === '/bad').length, 2);
  const removed = f.node('img'),
    cached = f.node('img');
  removed.isConnected = cached.isConnected = false;
  c.state.photoUrls.set(removed, 'blob:removed');
  c.state.photoUrls.set(cached, 'blob:cached');
  const card = f.node('section');
  card.append(cached);
  c.state.terminalCards.set('term', card);
  c.setView(f.node('main'));
  assert.deepEqual(f.revoked, ['blob:removed']);
  assert.equal(c.state.photoUrls.get(cached), 'blob:cached');
  assert.ok(c.liveSignature().includes('term'));
  assert.equal(c.registered('term'), true);
  assert.equal(c.empty('No accounts', 'Create one', card).children.at(-1), card);
});

test('shared confirmation retains errors, refreshes only after success and restores submit controls', async () => {
  const f = sharedFixture(),
    c = f.context;
  let fail = true,
    refreshed = 0,
    rendered = 0;
  c.state.refresh = async (force) => {
    assert.equal(force, true);
    refreshed++;
  };
  c.state.renderConnection = () => {
    rendered++;
  };
  f.$('connection-dialog').open = true;
  c.confirm(
    'Delete account',
    'This removes it',
    async () => {
      if (fail) throw Error('conflict');
    },
    'Delete account',
  );
  assert.equal(f.$('confirm-action').className, 'danger');
  assert.equal(f.$('confirm-dialog').open, true);
  await f.$('confirm-action').onclick();
  assert.equal(f.$('confirm-error').textContent, 'conflict');
  assert.equal(f.$('confirm-dialog').open, true);
  assert.equal(refreshed, 0);
  fail = false;
  await f.$('confirm-action').onclick();
  assert.equal(f.$('confirm-dialog').open, false);
  assert.equal(refreshed, 1);
  assert.equal(rendered, 1);
  const button = f.node('button'),
    form = { querySelector: () => button };
  await c.submit(form, async () => {
    assert.equal(button.disabled, true);
    throw Error('invalid');
  });
  assert.equal(button.disabled, false);
  assert.equal(f.$('error').scrolled, true);
  c.notice('Ready');
  assert.equal(f.$('notice').textContent, 'Ready');
});

test('a late action error cannot target a removed or closed dialog', async () => {
  for (const detached of [true, false]) {
    const f = sharedFixture(),
      c = f.context,
      feedback = f.$('dialog-error');
    let reject;
    const pending = c.run(
      () =>
        new Promise((_, fail) => {
          reject = fail;
        }),
      'dialog-error',
    );
    if (detached) feedback.isConnected = false;
    else feedback.closest = () => ({ open: false });
    reject(Error('late failure'));
    await pending;
    assert.equal(feedback.textContent, '');
    assert.equal(feedback.scrolled, undefined);
    assert.equal(c.state.busy, false);
  }
});

test('backup dialog handles download/check failures, changed files and a delayed restart', async () => {
  const { fixture } = require('../../support/admin-dom.cjs');
  const f = fixture('admin-backups.js', (c) => {
    c.panel = (title) => c.el('section', title);
    c.actionButton = (label, action) => Object.assign(c.el('button', label), { onclick: action });
    c.window = { confirm: () => true };
  });
  for (const result of ['restored', 'rolled_back']) {
    f.reply = { result, completed_at: '2026-01-01T00:00:00Z' };
    const panel = f.backupPanel();
    await new Promise(setImmediate);
    assert.equal(panel.children[0].children[1].hidden, false);
    assert.match(panel.children[0].children[1].textContent, /Last restore/);
  }
  f.openBackups();
  const dialog = f.find('dialog'),
    input = f.find('input');
  const status = f.elements.find((node) => node.attributes.role === 'status');
  const check = f.button('Check backup'),
    restore = f.button('Replace configuration'),
    download = f.button('Download backup');
  await restore.click();
  assert.equal(f.requests.length, 2);
  await check.click();
  assert.match(status.textContent, /Choose a backup/);
  input.files = [{ size: 65 * 1024 * 1024 }];
  await check.click();
  assert.match(status.textContent, /64 MB/);
  input.files = [{ size: 10 }];
  f.response = { ok: false, json: async () => ({ error: 'invalid backup' }) };
  await check.click();
  assert.equal(status.textContent, 'invalid backup');
  assert.equal(input.disabled, false);
  await download.click();
  assert.equal(status.textContent, 'invalid backup');
  f.response = {
    ok: true,
    blob: async () => ({}),
    headers: { get: () => 'attachment; filename="unit.zmala-backup"' },
  };
  await download.click();
  assert.equal(status.textContent, 'Backup download started.');
  const anchor = f.elements.find((node) => node.tag === 'a');
  assert.equal(anchor.download, 'unit.zmala-backup');
  assert.equal(anchor.clicked, true);
  assert.equal(anchor.removed, true);
  f.timers.at(-1).action();
  assert.deepEqual(f.revoked, ['blob:private']);
  f.response = {
    ok: true,
    json: async () => ({
      created_at: '2026-01-01',
      accounts: 1,
      terminals: 1,
      groups: 1,
      pictures: 0,
      configuration_version: 8,
    }),
  };
  await check.click();
  assert.equal(restore.disabled, false);
  input.onchange();
  assert.equal(restore.disabled, true);
  await check.click();
  f.response = { ok: false, json: async () => ({}) };
  await restore.click();
  assert.equal(status.textContent, 'Backup operation failed.');
  assert.equal(input.disabled, false);
  f.response = { ok: true, status: 200 };
  f.setTimeout = (callback) => callback();
  await restore.click();
  assert.equal(f.state.restoring, true);
  assert.match(status.textContent, /has not returned yet/);
  let cancelled = false;
  dialog.oncancel({
    preventDefault() {
      cancelled = true;
    },
  });
  assert.equal(cancelled, true);
  await f.button('Close').click();
  assert.equal(dialog.removed, true);
});

test('backup restore uses explicit browser confirmation despite bundled helper names and waits for new login', async () => {
  const elements = [],
    actions = new Map(),
    requests = [];
  let confirmed = false,
    confirmations = 0,
    reloaded = false;
  const context = load('backups', {
    state: {},
    document: { body: new Element() },
    el(tag, text) {
      const node = new Element(tag, text);
      elements.push(node);
      return node;
    },
    actionButton(label, action) {
      const node = new Element('button', label);
      actions.set(label, { node, action });
      return node;
    },
    // The generated bundle contains this shared helper in the same scope.
    confirm() {
      throw Error('Do not call the shared modal helper as window.confirm.');
    },
    window: {
      confirm() {
        confirmations++;
        return confirmed;
      },
    },
    location: {
      reload() {
        reloaded = true;
      },
    },
    setTimeout(callback) {
      callback();
    },
    async fetch(url, options) {
      requests.push({ url, options });
      if (url.endsWith('/check'))
        return {
          ok: true,
          json: async () => ({
            created_at: '2026-10-18T00:00:00Z',
            accounts: 2,
            terminals: 1,
            groups: 1,
            pictures: 1,
            configuration_version: 8,
          }),
        };
      if (url.endsWith('/restore')) return { ok: true };
      return { status: 401 };
    },
  });
  context.openBackups();
  const input = elements.find((e) => e.tag === 'input');
  input.files = [{ size: 10 }];
  const restore = actions.get('Replace configuration');
  assert.equal(restore.node.disabled, true);
  await actions.get('Check backup').action();
  assert.equal(restore.node.disabled, false);
  await restore.action();
  assert.equal(confirmations, 1);
  assert.equal(
    requests.some((r) => r.url.endsWith('/restore')),
    false,
  );
  confirmed = true;
  await restore.action();
  const sent = requests.find((r) => r.url.endsWith('/restore'));
  assert.equal(sent.options.headers['X-Zmala-Confirm-Restore'], 'replace');
  assert.equal(sent.options.headers['X-Zmala-Configuration-Version'], '8');
  assert.equal(context.state.restoring, true);
  assert.equal(reloaded, true);
});

test('credential copying uses the Clipboard API when available', async () => {
  const copied = [];
  const f = clipboardFixture({ writeText: async (text) => copied.push(text) });
  assert.equal(await f.writeClipboard('example', f.owner), true);
  assert.deepEqual(copied, ['example']);
  assert.equal(f.fields.length, 0);
});

test('plain HTTP copying selects inside the modal and restores focus without retaining the secret', async () => {
  const f = clipboardFixture(undefined);
  assert.equal(await f.writeClipboard('test-only-secret', f.owner), true);
  const field = f.fields[0];
  assert.equal(f.parent.children[0], field);
  assert.equal(field.value, 'test-only-secret');
  assert.equal(field.selected, true);
  assert.equal(field.isConnected, false);
  assert.equal(f.previous.focused, true);
});

test('blocked clipboard access returns failure and cleans up the fallback', async () => {
  const f = clipboardFixture(
    {
      writeText: async () => {
        throw Error('Denied');
      },
    },
    false,
  );
  assert.equal(await f.writeClipboard('example', f.owner), false);
  assert.equal(f.fields[0].isConnected, false);
  assert.equal(f.previous.focused, true);
});

test('account polling retains a focused row action but still updates rows while searching', async () => {
  let model = { configuration_version: 1 },
    renders = 0,
    rowUpdates = 0;
  const document = {
    activeElement: null,
    getElementById: () => ({ contains: (element) => element === 'row-action' }),
    querySelector: () => null,
  };
  const state = { model, terminalCards: new Map(), initialized: false };
  const context = load('main', {
    page: '/accounts',
    state,
    document,
    setInterval() {},
    authControls() {},
    message() {},
    signIn() {},
    terminalCardState() {},
    renderConnection() {},
    api: async () => model,
    liveSignature: () => String(state.model.configuration_version),
    renderAccounts: () => {
      renders++;
    },
    accountRows: () => {
      rowUpdates++;
    },
    renderOverview() {},
    renderActivity() {},
    renderCallbacks() {},
    renderGroups() {},
    renderTerminals() {},
  });
  await context.refresh();
  assert.equal(renders, 1);
  model = { configuration_version: 2 };
  document.activeElement = 'row-action';
  await context.refresh();
  assert.equal(rowUpdates, 0);
  assert.equal(state.renderedVersion, 1);
  document.activeElement = 'search';
  await context.refresh();
  assert.equal(rowUpdates, 1);
  assert.equal(state.renderedVersion, 2);
});

function consoleFixture() {
  const elements = new Map(),
    requests = [],
    errors = [];
  const get = (id) => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  };
  const context = load('console', {
    $: get,
    setInterval() {},
    online: () => true,
    state: {
      model: {
        configuration_version: 1,
        users: { one: { name: 'First' }, two: { name: 'Second' } },
        profiles: { one: { command_shell: 'sh' }, two: { command_shell: 'sh' } },
      },
    },
    shellNames: { sh: 'POSIX shell' },
    el: (tag, text) => new Element(tag, text),
    badge: (text) => new Element('span', text),
    iconButton: (label, icon, action) =>
      Object.assign(new Element('button', label), { onclick: action }),
    Error,
    message: (id, text) => {
      if (text) errors.push({ id, text });
    },
    api: (url, method, value) =>
      new Promise((resolve, reject) => requests.push({ url, method, value, resolve, reject })),
    submit: (_form, action) => action(),
    notice() {},
  });
  return { ...context, get, requests, errors };
}
const settle = () => new Promise((resolve) => setImmediate(resolve));
const content = (element) => [element.textContent, ...element.children.map(content)].join(' ');

test('overview and activity reflect live accounts and the SSH toggle recovers after errors', async () => {
  const elements = new Map(),
    calls = [],
    errors = [],
    views = [];
  const get = (id) => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  };
  let enabled = true,
    failure = false,
    refreshes = 0;
  const context = load('pages', {
    Error,
    $: get,
    state: {
      model: {
        users: { term: { name: 'Screen', type: 'terminal' } },
        profiles: { term: {} },
        host: 'unit.test',
        sip_port: 5060,
        terminal_statuses: { term: { state: 'idle' } },
        sip_status: {
          active_calls: 1,
          registrations: [{ user: 'term', address: '192.0.2.3' }, { user: 'deleted' }],
          events: [
            { time: '2026-01-01T00:00:00Z', message: 'Older' },
            { time: '2026-01-01T00:01:00Z', message: 'Newer' },
          ],
        },
      },
      refresh: async () => refreshes++,
    },
    online: () => true,
    el: (tag, text) => new Element(tag, text),
    icon: () => new Element('i'),
    link: (text, href) => Object.assign(new Element('a', text), { href }),
    panel: (title) => {
      const node = new Element('section', title);
      node.append(new Element('header'));
      return node;
    },
    query: (node, selector) =>
      selector === 'time' ? node.children.find((n) => n.tag === 'time') : node.children[0],
    avatar: (user) => new Element('img', user.name),
    badge: (text) => new Element('span', text),
    actionButton: (text, action) => Object.assign(new Element('button', text), { onclick: action }),
    backupPanel: () => new Element('section', 'Backups'),
    setView: (...nodes) => views.push(nodes),
    api: async (url, method, value) => {
      calls.push({ url, method, value });
      if (failure) throw Error('maintenance unavailable');
      if (method === 'PUT') enabled = value.enabled;
      return { supported: true, enabled, active: enabled };
    },
    message: (id, text) => errors.push({ id, text }),
  });
  context.renderOverview();
  await settle();
  const tree = views.at(-1),
    collect = (nodes) => nodes.flatMap((n) => [n, ...collect(n.children)]);
  let button = collect(tree).find((n) => n.tag === 'button' && n.textContent === 'Turn SSH off');
  assert.ok(button);
  failure = true;
  await button.onclick();
  assert.equal(button.disabled, false);
  assert.equal(errors.at(-1).text, 'maintenance unavailable');
  failure = false;
  await button.onclick();
  assert.equal(calls.findLast((c) => c.method === 'PUT').value.enabled, false);
  button = collect(tree).find((n) => n.textContent === 'Turn SSH on');
  assert.ok(button);
  await button.onclick();
  assert.equal(enabled, true);
  assert.match(tree.map(content).join(' '), /Active calls\s+1/);
  context.renderActivity();
  assert.match(views.at(-1).map(content).join(' '), /Screen term · 192.0.2.3/);
  assert.equal(content(context.eventList(1)).includes('Older'), false);
  await get('page-actions').children[0].onclick();
  assert.equal(refreshes, 1);
  context.state.model.sip_status.events = [];
  context.state.model.sip_status.registrations = [];
  context.state.model.users = {};
  context.state.model.profiles = {};
  failure = true;
  context.renderOverview();
  await settle();
  assert.match(views.at(-1).map(content).join(' '), /No terminals yet/);
  assert.match(views.at(-1).map(content).join(' '), /SSH status unavailable/);
  context.renderActivity();
  assert.match(views.at(-1).map(content).join(' '), /No accounts registered/);
  assert.match(content(context.eventList(1)), /No events yet/);
});
const job = (stdout) => ({
  status: 'completed',
  created_at: new Date().toISOString(),
  exit_code: 0,
  shell: 'sh',
  command: 'test',
  stdout,
});

test('console renders failure output, deletes only queued jobs and submits bounded command intent', async () => {
  const f = consoleFixture();
  f.openConsole('one');
  f.requests[0].resolve({
    jobs: [
      { ...job('out'), id: 'queued-id', status: 'queued', exit_code: null },
      { ...job(''), status: 'failed', exit_code: 2, stderr: 'failed output', truncated: true },
    ],
  });
  await settle();
  const history = f.get('console-history');
  assert.match(content(history), /failed output/);
  assert.match(content(history), /Exit 2/);
  assert.match(content(history), /Output truncated at 64 KiB/);
  const button = history.children[0].children[0].children.find((n) => n.tag === 'button');
  const deletion = button.onclick();
  assert.equal(f.requests[1].method, 'DELETE');
  assert.equal(f.requests[1].url, '/api/terminals/one/console/queued-id');
  f.requests[1].resolve({});
  await settle();
  f.requests[2].resolve({ jobs: [] });
  await deletion;
  assert.match(content(history), /No commands yet/);
  f.get('console-command').value = 'printf test';
  f.get('console-timeout').value = '15';
  f.get('console-form').onsubmit({ preventDefault() {} });
  assert.deepEqual(JSON.parse(JSON.stringify(f.requests[3].value)), {
    command: 'printf test',
    timeout_seconds: 15,
  });
  f.requests[3].resolve({});
  await settle();
  assert.equal(f.get('console-command').value, '');
  f.requests[4].resolve({ jobs: [job('test')] });
  await settle();
  assert.match(content(history), /test/);
  const refresh = f.refreshConsole();
  f.requests[5].reject(Error('request failed'));
  await refresh;
  assert.deepEqual(f.errors.at(-1), { id: 'console-error', text: 'request failed' });
});

test('late console responses cannot display another terminal’s commands', async () => {
  const f = consoleFixture();
  f.openConsole('one');
  f.get('console-dialog').close();
  f.openConsole('two');
  assert.match(content(f.get('console-history')), /Loading commands/);
  f.requests[0].resolve({ jobs: [job('old-output')] });
  await settle();
  assert.equal(f.requests[1].url, '/api/terminals/two/console');
  assert.doesNotMatch(content(f.get('console-history')), /old-output/);
  f.requests[1].resolve({ jobs: [job('new-output')] });
  await settle();
  assert.match(content(f.get('console-history')), /new-output/);
  assert.doesNotMatch(content(f.get('console-history')), /old-output/);
});

test('closing and reopening the same console discards stale errors and fetches again', async () => {
  const f = consoleFixture();
  f.openConsole('one');
  f.get('console-dialog').close();
  f.openConsole('one');
  f.requests[0].reject(Error('Old request failed'));
  await settle();
  assert.equal(f.errors.length, 0);
  assert.equal(f.requests.length, 2);
  f.get('console-dialog').close();
  f.requests[1].reject(Error('Closed request failed'));
  await settle();
  assert.equal(f.errors.length, 0);
  assert.equal(f.state.consoleFetching, false);
  assert.equal(f.state.consoleId, '');
});

test('shell editor keeps its opening revision and adopts only its saved revision', async () => {
  const f = consoleFixture();
  f.state.refresh = async () => {
    f.state.model.configuration_version = 99;
  };
  f.openConsole('one');
  f.requests[0].resolve({ jobs: [] });
  await settle();
  f.state.model.configuration_version = 42; // Polling must not rebase an unsubmitted draft.
  const save = f.get('console-shell-form').onsubmit({ preventDefault() {} });
  assert.equal(f.requests[1].value.configuration_version, 1);
  f.requests[1].resolve({ configuration_version: 2 });
  await settle();
  f.requests[2].resolve({ jobs: [] });
  await save;
  const second = f.get('console-shell-form').onsubmit({ preventDefault() {} });
  assert.equal(f.requests[3].value.configuration_version, 2);
  f.requests[3].resolve({ configuration_version: 3 });
  await settle();
  f.requests[4].resolve({ jobs: [] });
  await second;
});

test('account drafts keep their opening revision and a late photo cannot save a different dialog', async () => {
  const elements = new Map(),
    requests = [];
  const get = (id) => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  };
  const f = load('accounts', {
    $: get,
    state: {
      model: {
        configuration_version: 1,
        users: {
          one: { name: 'First', type: 'app', emails: ['one@example.test'] },
          two: { name: 'Second', type: 'app', emails: ['two@example.test'] },
        },
      },
      refresh: async () => {},
    },
    avatar: () => new Element(),
    message() {},
    notice() {},
    emailAddresses: (value) => [value],
    accountPicture: async () => '',
    submit: (_form, action) => action(),
    api: async (url, method, value) => {
      requests.push({ url, method, value });
      return { id: value.id };
    },
  });
  f.openAccount('one');
  f.state.model.configuration_version = 42;
  await get('account-form').onsubmit({ preventDefault() {} });
  assert.equal(requests[0].value.configuration_version, 1);
  assert.equal(requests[0].url, '/api/users/one');
  let finishPicture;
  f.accountPicture = () =>
    new Promise((resolve) => {
      finishPicture = resolve;
    });
  f.openAccount('one');
  const pending = get('account-form').onsubmit({ preventDefault() {} });
  get('account-dialog').close();
  f.openAccount('two');
  finishPicture('/photos/example.png');
  await pending;
  assert.equal(requests.length, 1, 'Changing the editor cancels a save still awaiting its upload');
  assert.equal(get('account-dialog').open, true);
  assert.equal(get('edit-id').value, 'two');
});
