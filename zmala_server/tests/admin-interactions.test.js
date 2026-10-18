'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

// Execute the actual controller modules with a small DOM boundary. Rendering and
// platform clipboard permissions are checked separately in the browser.
function load(name, context) {
  const source = fs
    .readFileSync(path.join(__dirname, '../web/admin-' + name + '.js'), 'utf8')
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
        users: { one: { name: 'First' }, two: { name: 'Second' } },
        profiles: { one: { command_shell: 'sh' }, two: { command_shell: 'sh' } },
      },
    },
    shellNames: { sh: 'POSIX shell' },
    el: (tag, text) => new Element(tag, text),
    badge: (text) => new Element('span', text),
    message: (id, text) => {
      if (text) errors.push({ id, text });
    },
    api: (url) => new Promise((resolve, reject) => requests.push({ url, resolve, reject })),
  });
  return { ...context, get, requests, errors };
}
const settle = () => new Promise((resolve) => setImmediate(resolve));
const content = (element) => [element.textContent, ...element.children.map(content)].join(' ');
const job = (stdout) => ({
  status: 'completed',
  created_at: new Date().toISOString(),
  exit_code: 0,
  shell: 'sh',
  command: 'test',
  stdout,
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
