// @test S-LLT-036
// @requirements LLR-SRV-UI-015, LLR-SRV-UI-016, LLR-SRV-UI-018, LLR-SRV-UI-019
// @environment portable
// @plan Execute real account controllers against recording DOM, image-upload, API, clipboard and URL boundaries. Verify search/filter state, draft revisions, rename/create/delete intent, delayed-upload and delayed-response invalidation, retained error drafts, private credential masking and copy feedback, bootstrap downloads and object-URL disposal. Exercise group member selection/counts and opening-revision conflicts, successful save and deletion intent.
// @pass Assertions verify controller requests and presentation state without actual network, clipboard or downloaded files; backend authorization and browser layout are separate checks.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { fixture } = require('../../support/admin-dom.cjs');
const plain = (value) => JSON.parse(JSON.stringify(value));
const text = (node) => [node.textContent, ...node.children.map(text)].join(' ');

test('group editor preserves opening revisions, selected members and explicit deletion intent', async () => {
  const f = fixture('admin-groups.js', (c) => {
    c.state = {
      model: {
        configuration_version: 4,
        groups: { family: { name: 'Family', members: ['a'] } },
        users: { a: { name: 'Alice', type: 'terminal' }, b: { name: 'Bob', type: 'app' } },
      },
      refresh: async () => {},
    };
    c.actionButton = (label, action) => Object.assign(c.el('button', label), { onclick: action });
    c.iconButton = (label, icon, action) => c.actionButton(label, action);
    c.avatar = (u) => c.el('img', u.name);
    c.badge = (label) => c.el('span', label);
    c.panel = (title) => {
      const p = c.el('section', title);
      p.append(c.el('header'));
      return p;
    };
    c.query = (node) => node.children[0];
    c.empty = (title, detail, action) => {
      const p = c.el('div', title);
      p.append(action);
      return p;
    };
    c.confirm = (title, detail, action) => {
      c.deletion = { title, detail, action };
    };
    c.$('group-members').querySelectorAll = () =>
      c
        .$('group-members')
        .children.flatMap((row) =>
          row.children.filter((child) => child.tag === 'input' && child.checked),
        );
  });
  f.renderGroups();
  await f.button('Edit group Family').click();
  assert.equal(f.$('group-selected-count').textContent, '1 selected');
  f.$('group-members').children[1].children[0].checked = true;
  f.$('group-members').children[1].children[0].onchange();
  assert.equal(f.$('group-selected-count').textContent, '2 selected');
  f.state.model.configuration_version = 5;
  f.failure = Error('revision conflict');
  f.$('group-form').onsubmit({ preventDefault() {} });
  await f.pending.at(-1);
  assert.equal(f.requests.at(-1).value.configuration_version, 4);
  assert.equal(f.$('group-dialog').open, true);
  delete f.failure;
  f.$('group-form').onsubmit({ preventDefault() {} });
  await f.pending.at(-1);
  assert.deepEqual(plain(f.requests.at(-1).value.members), ['a', 'b']);
  assert.equal(f.$('group-dialog').open, false);
  await f.button('Delete group Family').click();
  assert.match(f.deletion.detail, /Accounts remain/);
  f.state.model.configuration_version = 6;
  await f.deletion.action();
  assert.deepEqual(plain(f.requests.at(-1)), {
    url: '/api/groups/family',
    method: 'DELETE',
    value: { configuration_version: 5 },
  });
  f.state.model.groups = {};
  f.state.model.users = {};
  f.renderGroups();
  await f.button('New group').click();
  assert.match(text(f.$('group-members')), /Create accounts first/);
  f.$('group-form').onsubmit({ preventDefault() {} });
  await f.pending.at(-1);
  assert.equal(f.requests.at(-1).method, 'POST');
  assert.equal(f.requests.at(-1).url, '/api/groups');
});
function accounts() {
  const f = fixture('admin-accounts.js', (c) => {
    c.state = {
      accountSearch: '',
      accountFilter: 'all',
      model: {
        configuration_version: 7,
        host: 'server.test',
        sip_port: 5060,
        sip_proxy: 'sip:server.test:5060;transport=udp',
        call_transport: 'LAN UDP relay',
        local_terminal_id: '',
        users: {
          alice: {
            name: 'Alice',
            type: 'terminal',
            password: 'private',
            photo: '/photos/a.png',
            emails: ['alice@example.test'],
          },
          bob: { name: 'Bob', type: 'app', password: 'phone' },
        },
        account_groups: { alice: ['family'], bob: [] },
        groups: { family: { name: 'Family' } },
      },
      refresh: async (force) => c.refreshes.push(force),
    };
    c.refreshes = [];
    c.confirmations = [];
    c.pdfs = [];
    c.copies = [];
    c.Blob = Blob;
    c.avatar = (user) => c.el('img', user.name);
    c.badge = (label) => c.el('span', label);
    c.statusBadge = (id) => c.el('span', id);
    c.empty = (title, detail) => c.el('p', title + ' ' + detail);
    c.panel = (title) => c.el('section', title);
    c.actionButton = (label, action) => Object.assign(c.el('button', label), { onclick: action });
    c.iconButton = (label, icon, action) => c.actionButton(label, action);
    c.confirm = (title, detail, action) => c.confirmations.push({ title, detail, action });
    c.serverPdf = async (id) => c.pdfs.push(id);
    c.emailAddresses = (value) =>
      value
        .split(',')
        .map((v) => v.trim())
        .filter(Boolean);
    c.accountPicture = async (file, existing, remove) => (remove ? '' : existing);
    c.writeClipboard = async (value, button) => {
      c.copies.push({ value, button });
      return c.copySuccess;
    };
  });
  f.saveAccount = async () => {
    f.$('account-form').onsubmit({ preventDefault() {} });
    await f.pending.at(-1);
  };
  return f;
}

test('account filters retain input state and expose responsive column labels', () => {
  const f = accounts();
  f.renderAccounts();
  assert.equal(f.$('account-count').textContent, '2 accounts');
  const rows = f.$('account-rows').children;
  assert.match(text(rows[0]), /Alice.*Family/);
  assert.match(text(rows[1]), /Email address needed.*No groups/);
  assert.deepEqual(
    rows[0].children.map((n) => n.attributes['data-label']),
    ['Account', 'Type', 'Groups', 'SIP status', 'Actions'],
  );
  const input = f.inputs()[0];
  input.value = 'ALICE';
  input.oninput();
  assert.equal(f.$('account-count').textContent, '1 account');
  const filter = f.find('select');
  filter.value = 'app';
  filter.onchange();
  assert.equal(f.$('account-count').textContent, '0 accounts');
  assert.match(text(f.$('account-rows')), /No accounts found/);
  f.button('New account').click();
  assert.equal(f.$('account-title').textContent, 'New account');
  assert.equal(f.$('edit-remove-photo').disabled, true);
});

test('account drafts freeze opening revision, retain failures and report renamed identity', async () => {
  const f = accounts();
  f.openAccount('alice');
  assert.equal(f.$('edit-name').value, 'Alice');
  assert.match(f.$('edit-password').placeholder, /keep current/);
  f.$('edit-id').value = 'alice2';
  f.$('edit-id').oninput();
  assert.equal(f.$('rename-help').hidden, false);
  f.$('edit-name').value = 'New Alice';
  f.$('edit-emails').value = 'one@example.test, two@example.test';
  f.$('edit-remove-photo').checked = true;
  f.state.model.configuration_version = 99;
  f.failure = Error('Version conflict');
  await f.saveAccount();
  assert.equal(f.$('account-dialog').open, true);
  assert.equal(f.$('edit-name').value, 'New Alice');
  assert.equal(f.messages.at(-1).kind, 'account-error');
  assert.equal(f.refreshes.length, 0);
  delete f.failure;
  f.reply = { id: 'alice2' };
  await f.saveAccount();
  assert.deepEqual(plain(f.requests.at(-1)), {
    url: '/api/users/alice',
    method: 'PUT',
    value: {
      configuration_version: 7,
      id: 'alice2',
      name: 'New Alice',
      emails: ['one@example.test', 'two@example.test'],
      type: 'terminal',
      password: '',
      photo: '',
    },
  });
  assert.equal(f.$('account-dialog').open, false);
  assert.deepEqual(f.refreshes, [true]);
  assert.match(f.messages.at(-1).text, /SIP address has changed/);
  f.openAccount();
  f.$('edit-id').value = 'new';
  f.$('edit-name').value = 'New';
  f.reply = { id: 'new' };
  await f.saveAccount();
  assert.equal(f.requests.at(-1).method, 'POST');
  assert.match(f.messages.at(-1).text, /Created new/);
});

test('photo replacement revokes earlier previews and stale upload cannot save a closed editor', async () => {
  const f = accounts();
  f.openAccount('alice');
  f.$('edit-photo').onchange();
  assert.equal(f.revoked.length, 0);
  f.$('edit-photo').files = [{}];
  f.$('edit-photo').onchange();
  f.$('edit-photo').onchange();
  assert.deepEqual(f.revoked, ['blob:private']);
  assert.equal(f.$('account-picture-preview').children[0].alt, 'New account picture preview');
  let finish;
  f.accountPicture = () =>
    new Promise((resolve) => {
      finish = resolve;
    });
  f.$('account-form').onsubmit({ preventDefault() {} });
  f.$('account-dialog').close();
  finish('/photos/new.png');
  await f.pending.at(-1);
  assert.equal(f.requests.length, 0);
  assert.equal(f.state.accountPreviewUrl, undefined);
  assert.equal(f.revoked.length, 2);
});

test('late response or failure cannot close or overwrite a newly opened editor', async () => {
  for (const rejected of [false, true]) {
    const f = accounts();
    f.openAccount('alice');
    let finish, started;
    const requestStarted = new Promise((resolve) => {
      started = resolve;
    });
    f.api = () =>
      new Promise((resolve, reject) => {
        finish = rejected ? reject : resolve;
        started();
      });
    f.$('account-form').onsubmit({ preventDefault() {} });
    await requestStarted;
    f.openAccount('bob');
    finish(rejected ? Error('stale failure') : { id: 'alice' });
    await f.pending.at(-1);
    assert.equal(f.$('account-dialog').open, true);
    assert.equal(f.state.editingId, 'bob');
    assert.equal(f.$('edit-name').value, 'Bob');
    assert.equal(f.refreshes.length, 0);
    assert.equal(f.messages.filter((m) => m.text.includes('stale')).length, 0);
  }
});

test('delete confirmation captures revision and credential copying reports failure or temporary success', async () => {
  const f = accounts();
  f.deleteAccount('alice');
  assert.equal(f.requests.length, 0);
  f.state.model.configuration_version = 99;
  await f.confirmations[0].action();
  assert.deepEqual(plain(f.requests[0]), {
    url: '/api/users/alice',
    method: 'DELETE',
    value: { configuration_version: 7 },
  });
  const row = f.credential('Password', 'private', true);
  const code = row.children[0].children[1],
    feedback = row.children[0].children[2];
  assert.equal(code.textContent, '••••••••••••');
  const reveal = f.button('Show password');
  await reveal.click();
  assert.equal(code.textContent, 'private');
  assert.equal(reveal.attributes['aria-label'], 'Hide password');
  await reveal.click();
  assert.equal(code.textContent, '••••••••••••');
  const copy = f.button('Copy Password');
  f.copySuccess = false;
  await copy.click();
  assert.match(feedback.textContent, /manually/);
  assert.equal(f.timers.length, 0);
  f.copySuccess = true;
  await copy.click();
  assert.equal(feedback.textContent, 'Copied.');
  assert.equal(feedback.hidden, false);
  assert.equal(copy.attributes['aria-label'], 'Copied');
  assert.equal(f.timers[0].ms, 1600);
  f.timers[0].action();
  assert.equal(copy.attributes['aria-label'], 'Copy Password');
  assert.equal(f.copies[0].value, 'private');
});

test('connection view handles terminal assignment downloads and removed accounts', async () => {
  const f = accounts();
  f.openConnection('alice');
  assert.equal(f.$('connection-dialog').open, true);
  assert.equal(f.$('details-title').textContent, 'Alice');
  assert.match(text(f.$('details-content')), /sip:alice@server.test/);
  f.button('Use on server machine').click();
  await f.confirmations[0].action();
  assert.deepEqual(plain(f.requests.at(-1)), {
    url: '/api/local-terminal',
    method: 'PUT',
    value: { id: 'alice' },
  });
  f.state.model.local_terminal_id = 'alice';
  f.renderConnection();
  assert.equal(f.button('Use on server machine').disabled, true);
  f.reply = { device_id: 'from-server', device_token: 'private' };
  await f.button('Download setup').click();
  assert.equal(f.requests.at(-1).url, '/api/terminal-bootstrap?id=alice');
  assert.equal(f.blob.type, 'application/json');
  assert.deepEqual(JSON.parse(await f.blob.text()), f.reply);
  const download = f.find('a');
  assert.equal(download.download, 'terminal-alice.json');
  assert.equal(download.clicked, true);
  assert.equal(f.timers.at(-1).ms, 1000);
  f.timers.at(-1).action();
  assert.equal(f.revoked.at(-1), 'blob:private');
  await f.button('Download server QR PDF').click();
  assert.deepEqual(f.pdfs, ['alice']);
  f.openConnection('bob');
  assert.match(
    text(f.$('details-content')),
    /Install ZmalaPhone.*cannot also be assigned to a Pi terminal/,
  );
  f.state.model.sip_proxy = 'sip:secure.example.org:443;transport=tls';
  f.renderConnection();
  assert.match(text(f.$('details-content')), /ZmalaPhone preview supports LAN calling only/);
  assert.ok(!text(f.$('details-content')).includes('Use UDP'));
  delete f.state.model.users.bob;
  f.renderConnection();
  assert.equal(f.$('connection-dialog').open, false);
});
