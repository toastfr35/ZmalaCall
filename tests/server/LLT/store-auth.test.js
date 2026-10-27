// @test S-LLT-014
// @requirements LLR-SRV-DIR-021, LLR-SRV-DIR-022, LLR-SRV-DIR-025, LLR-SRV-DIR-029, LLR-SRV-DIR-030, LLR-SRV-DIR-031, LLR-SRV-CALL-003, LLR-SRV-DATA-016
// @environment portable
// @plan Use temporary stores and signed digest requests; assert account/group validation, direct membership, sorted derived contacts, credential-preserving migration and rejection of replay, wrong passwords and changed targets.
// @pass Every named assertion must pass; failures or skips do not establish requirement verification.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const digest = require('../../../zmala_server/node_modules/sip/digest');
const { DigestAuth } = require('../../../zmala_server/auth');
const { Store } = require('../../../zmala_server/store');
const { migrate } = require('../../../zmala_server/migrations');
const { defaultState } = require('../../../zmala_server/defaults');

test('removed terminal languages migrate once to English without changing identities', () => {
  const state = defaultState();
  state.profiles.term1.language = 'it';
  const accounts = structuredClone(state.users),
    revision = state.configuration_version;
  migrate(state);
  assert.equal(state.profiles.term1.language, 'en');
  assert.equal(state.configuration_version, revision + 1);
  assert.deepEqual(state.users, accounts);
  migrate(state);
  assert.equal(state.configuration_version, revision + 1);
});

test('digest rejects replay, wrong password, and a changed target', () => {
  const auth = new DigestAuth('family.test'),
    users = { alice: { password: 'correct' } };
  function signed(password = 'correct') {
    const rq = { method: 'REGISTER', uri: 'sip:family.test', headers: {} };
    const rs = auth.challenge(rq);
    digest.signRequest({}, rq, rs, { user: 'alice', password });
    return rq;
  }
  const rq = signed();
  assert.equal(auth.verify(rq, users), 'alice');
  assert.equal(auth.verify(rq, users), null);
  assert.equal(auth.verify(signed('wrong'), users), null);
  const malformed = signed();
  malformed.headers.authorization[0].response = 'é'.repeat(32);
  assert.equal(auth.verify(malformed, users), null, 'Non-hex digests must fail without throwing');
  const altered = signed();
  altered.uri = 'sip:elsewhere';
  assert.equal(auth.verify(altered, users), null);
});
test('group membership persists, denies unknown/self calls, and derives terminal contacts', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'family-call-'));
  try {
    const s = new Store(dir);
    assert.equal(s.permitted('phone1', 'term1'), true);
    assert.equal(s.permitted('term1', 'phone1'), true);
    assert.equal(s.permitted('unknown', 'term1'), false);
    assert.equal(s.permitted('phone1', 'phone1'), false);
    assert.equal(s.permitted('constructor', 'term1'), false);
    s.deleteGroup('family');
    const second = new Store(dir);
    assert.equal(second.permitted('phone1', 'term1'), false);
    assert.equal(second.value.users.phone1.password, s.value.users.phone1.password);
    assert.equal(second.config().contacts[0].can_call, false);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
test('legacy migrations retain credentials and metadata, and convert only mutual edges without transitive access', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'family-migration-'));
  try {
    const legacy = {
      schema_version: 1,
      configuration_version: 7,
      host: '192.168.1.8',
      sip_port: 5060,
      http_port: 8080,
      admin_token: 'admin',
      device_id: 'existing-device',
      device_token: 'existing-token',
      display_name: 'Grandma',
      auto_answer_seconds: 8,
      terminal_settings: { camera: 'camera', microphone: '', speaker: '' },
      users: {
        terminal: { name: 'Terminal', password: 'terminal-secret' },
        test: { name: 'Alice', password: 'test' },
      },
      contacts: [
        {
          id: 'test',
          name: 'Alice',
          can_call: true,
          can_receive: true,
          auto_answer: true,
          photo: '/photos/abcd.png',
        },
      ],
    };
    fs.writeFileSync(path.join(dir, 'server.json'), JSON.stringify(legacy));
    const s = new Store(dir);
    assert.equal(s.value.schema_version, 7);
    assert.equal(s.value.users.test.password, 'test');
    assert.equal(s.config().sip.password, 'terminal-secret');
    assert.equal(s.config().device_id, 'existing-device');
    assert.equal(s.config().call_auth_key, 'existing-token');
    assert.equal(s.config().contacts[0].photo, '');
    assert.equal(s.config().auto_answer, true);
    assert.equal(s.config().auto_answer_seconds, 8);
    assert.equal(s.permitted('test', 'terminal'), true);
    assert.equal(s.config().video_fps, 15);
    assert.equal(s.value.configuration_version, 12);
    assert.equal(new Store(dir).value.configuration_version, 12);
    s.createAccount({ emails: ['fixture@example.test'], id: 'bob', name: 'Bob', type: 'app' });
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'carol',
      name: 'Carol',
      type: 'app',
    });
    const v = s.value;
    v.schema_version = 3;
    v.permissions = Object.fromEntries(
      Object.keys(v.users).map((id) => [
        id,
        Object.fromEntries(Object.keys(v.users).map((other) => [other, false])),
      ]),
    );
    v.permissions.test.terminal = v.permissions.terminal.test = true;
    v.permissions.test.bob = v.permissions.bob.test = true;
    v.permissions.bob.carol = true;
    delete v.groups;
    s.save();
    const migrated = new Store(dir);
    assert.equal(migrated.permitted('test', 'bob'), true);
    assert.equal(migrated.permitted('terminal', 'bob'), false);
    assert.equal(migrated.permitted('bob', 'carol'), false);
    assert.equal('permissions' in migrated.value, false);
    assert.equal(migrated.accountGroups('test').length, 2);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
test('overlapping groups allow direct shared membership, all types, removal, rename and optional account pictures', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'family-groups-'));
  try {
    const s = new Store(dir);
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'alice',
      name: 'Alice',
      type: 'app',
      photo: '/photos/abcd.png',
    });
    s.createAccount({ emails: ['fixture@example.test'], id: 'bob', name: 'Bob', type: 'app' });
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'lounge',
      name: 'Lounge',
      type: 'terminal',
      auto_answer: true,
      auto_answer_seconds: 7,
    });
    assert.equal(s.permitted('alice', 'lounge'), false);
    const a = s.createGroup({ name: 'Family A', members: ['alice', 'lounge'] }),
      b = s.createGroup({ name: 'Family B', members: ['alice', 'bob'] });
    assert.equal(s.accountGroups('alice').length, 2);
    assert.equal(s.permitted('alice', 'bob'), true);
    assert.equal(s.permitted('bob', 'alice'), true);
    assert.equal(s.permitted('bob', 'lounge'), false);
    assert.equal(s.config('lounge').contacts.find((c) => c.id === 'alice').auto_answer, true);
    assert.equal(
      s.config('lounge').contacts.find((c) => c.id === 'alice').photo,
      '/photos/abcd.png',
    );
    const another = s.createGroup({ name: 'Another', members: ['alice', 'lounge'] });
    s.deleteGroup(a);
    assert.equal(s.permitted('alice', 'lounge'), true);
    s.updateGroup(another, { name: 'Another edited', members: ['lounge'] });
    assert.equal(s.permitted('alice', 'lounge'), false);
    assert.equal(s.value.users.lounge.auto_answer, true);
    s.updateGroup(another, { name: 'Another edited', members: ['alice', 'lounge'] });
    s.selectTerminal('lounge');
    const identity = s.value.users.lounge.device_id,
      token = s.value.users.lounge.device_token,
      password = s.value.users.lounge.password;
    const before = JSON.stringify(s.value);
    assert.throws(() => s.updateAccount('lounge', { id: 'alice', name: 'Bad', type: 'app' }));
    assert.equal(JSON.stringify(s.value), before);
    s.updateAccount('lounge', { id: 'livingroom', name: 'Living room', type: 'terminal' });
    assert.equal(s.deviceAccount(token), 'livingroom');
    assert.equal(s.config().sip.username, 'livingroom');
    assert.equal(s.value.users.livingroom.device_id, identity);
    assert.equal(s.value.users.livingroom.password, password);
    assert.equal(s.permitted('alice', 'livingroom'), true);
    assert.equal(s.permitted('alice', 'lounge'), false);
    assert.equal(s.contacts('term1').find((c) => c.id === 'livingroom').name, 'Living room');
    assert.equal(s.contacts('term1').find((c) => c.id === 'livingroom').photo, '');
    s.deleteAccount('alice');
    assert.deepEqual(s.value.groups[b].members, ['bob']);
    assert.equal(s.permitted('alice', 'livingroom'), false);
    assert.equal(
      s.config().contacts.some((c) => c.id === 'alice'),
      false,
    );
    assert.equal(new Store(dir).config().sip.username, 'livingroom');
    s.updateAccount('bob', { name: 'Bob terminal', type: 'terminal' });
    const bobToken = s.value.users.bob.device_token;
    s.updateAccount('bob', { name: 'Bob phone', type: 'app' });
    assert.equal(s.deviceAccount(bobToken), undefined);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
test('invalid groups and account settings do not partially change permissions or credentials', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'family-validation-'));
  try {
    const s = new Store(dir),
      before = JSON.stringify(s.value);
    for (const g of [
      { name: '', members: [] },
      { name: 'Family', members: [] },
      { name: 'Bad', members: ['unknown'] },
      { name: 'Bad', members: ['phone1', 'phone1'] },
      { name: 'Bad', members: 'phone1' },
      { name: 'Bad', members: ['constructor'] },
      { name: 'Bad', members: [], description: 5 },
    ])
      assert.throws(() => s.createGroup(g));
    assert.throws(() => s.updateGroup('family', { name: 'Bad', members: ['unknown'] }));
    assert.throws(() => s.deleteGroup('constructor'));
    assert.throws(() =>
      s.updateAccount('phone1', { name: 'phone1', type: 'app', auto_answer: true }),
    );
    assert.throws(() =>
      s.updateAccount('term1', { name: 'term1', type: 'terminal', auto_answer_seconds: 2 }),
    );
    assert.throws(() =>
      s.updateAccount('phone1', {
        name: 'phone1',
        type: 'app',
        photo: 'https://example.com/photo.png',
      }),
    );
    assert.equal(JSON.stringify(s.value), before);
    const empty = s.createGroup({ name: 'Empty', members: [] });
    assert.deepEqual(s.value.groups[empty].members, []);
    s.updateAccount('phone1', { name: 'phone1', type: 'app', photo: '/photos/abcd.png' });
    assert.equal(s.config().contacts[0].photo, '/photos/abcd.png');
    s.updateAccount('phone1', { name: 'phone1', type: 'app', photo: '/photos/ffff.png' });
    assert.equal(s.config().contacts[0].photo, '/photos/ffff.png');
    s.updateAccount('phone1', { name: 'phone1', type: 'app', photo: '' });
    assert.equal(s.config().contacts[0].photo, '');
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('contacts always follow account names and pictures, sort alphabetically, and ignore legacy overrides', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'zmala-contacts-'));
  try {
    const s = new Store(dir);
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'zoe',
      name: 'Zoë',
      type: 'app',
      photo: '/photos/abcd.png',
    });
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'alice',
      name: 'alice',
      type: 'app',
    });
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'emile',
      name: 'Émile',
      type: 'app',
    });
    s.createAccount({
      emails: ['fixture@example.test'],
      id: 'alicia',
      name: 'Alice',
      type: 'app',
    });
    s.createGroup({ name: 'Contacts', members: ['term1', 'zoe', 'alice', 'emile', 'alicia'] });
    s.value.profiles.term1.contacts = [
      { id: 'zoe', name: 'A custom name', photo: '/photos/ffff.png' },
      { id: 'alice', name: 'Z custom name', photo: '/photos/aaaa.png' },
    ];
    s.save();
    const config = new Store(dir).config('term1');
    assert.deepEqual(
      config.contacts.filter((c) => c.can_call).map((c) => c.id),
      ['alice', 'alicia', 'emile', 'phone1', 'zoe'],
    );
    const zoe = config.contacts.find((c) => c.id === 'zoe');
    assert.equal(zoe.name, 'Zoë');
    assert.equal(zoe.photo, '/photos/abcd.png');
    assert.equal('photo_override' in zoe, false);
    assert.equal(config.contacts.find((c) => c.id === 'alice').photo, '');
    s.updateAccount('zoe', { name: 'Aaron', type: 'app', photo: '/photos/bbbb.png' });
    assert.equal(s.config().contacts[0].name, 'Aaron');
    assert.equal(s.config().contacts[0].photo, '/photos/bbbb.png');
    s.updateAccount('zoe', { name: 'Aaron', type: 'app', photo: '' });
    assert.equal(s.config().contacts[0].photo, '');
    s.deleteAccount('emile');
    assert.equal(
      s.contacts('term1').some((c) => c.id === 'emile'),
      false,
    );
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
