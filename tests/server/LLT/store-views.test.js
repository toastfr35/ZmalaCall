// @test S-LLT-019
// @requirements LLR-SRV-START-007, LLR-SRV-DIR-024, LLR-SRV-DIR-027, LLR-SRV-DIR-028, LLR-SRV-DIR-032, LLR-SRV-CONFIG-021, LLR-SRV-CONFIG-022, LLR-SRV-ENROLL-005
// @environment portable
// @plan Create isolated accounts, mutate revisions and reassign serials; assert random independent credentials, private cached directory views, compare-and-set settings, device-owned profiles and bootstrap identity. Feed network-interface fixtures to check LAN address preference and fallback.
// @pass Every identity, privacy, invalidation and rejected-write assertion must pass; HTTP active-call exclusion is checked separately.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const os = require('node:os');
const { storeFixture } = require('../../support/server/unit-fixture');
const { defaultState, lanAddress } = require('../../../zmala_server/defaults');

test('first run and new accounts use independent credentials, never directory secrets', (t) => {
  const s = storeFixture(t),
    fresh = defaultState();
  assert.deepEqual(Object.keys(fresh.users), ['term1', 'phone1']);
  assert.deepEqual(fresh.groups.family.members, ['term1', 'phone1']);
  assert.equal(fresh.users.term1.device_id, 'windows-terminal');
  assert.equal(fresh.profiles.term1.command_shell, 'powershell');
  const secrets = [
    fresh.admin_token,
    fresh.users.term1.password,
    fresh.users.phone1.password,
    fresh.users.term1.device_token,
    s.value.users.term1.device_token,
  ];
  assert.equal(new Set(secrets).size, secrets.length);
  assert.ok(secrets.every((value) => value.length >= 24));
  s.createAccount({
    id: 'second',
    type: 'terminal',
    name: 'Other',
    emails: ['private@example.test'],
  });
  const second = { ...s.value.users.second };
  assert.notEqual(second.device_id, 'second');
  s.updateAccount('second', { id: 'renamed', type: 'terminal', name: 'New name' });
  assert.equal(s.value.users.renamed.device_id, second.device_id);
  assert.equal(s.value.users.renamed.device_token, second.device_token);
  const config = s.config('term1');
  assert.equal(config.sip.password, s.value.users.term1.password);
  for (const contact of config.contacts) {
    assert.ok(!('emails' in contact || 'password' in contact || 'device_token' in contact));
    assert.notEqual(contact.id, 'term1');
  }
  assert.ok(!JSON.stringify(config).includes('private@example.test'));
});

test('derived views reuse stable computation and invalidate after edits without live-field leakage', (t) => {
  const s = storeFixture(t);
  const build = t.mock.method(s, 'buildContacts');
  const first = s.contacts('term1');
  first[0].online = true;
  first[0].name = 'Not persisted';
  assert.equal(s.contacts('term1')[0].name, 'phone1');
  assert.equal(s.contacts('term1')[0].online, undefined);
  assert.equal(build.mock.callCount(), 1);
  s.updateAccount('phone1', { name: 'Changed', type: 'app' });
  assert.equal(s.contacts('term1')[0].name, 'Changed');
  assert.equal(build.mock.callCount(), 2);
  s.deleteGroup('family');
  assert.equal(s.contacts('term1')[0].can_call, false);
});

test('local settings reject protected fields and stale values, accept idempotent retries', (t) => {
  const s = storeFixture(t),
    version = s.value.configuration_version;
  for (const key of ['password', 'device_id', 'camera', 'command_shell', 'video_fps'])
    assert.throws(() => s.setDeviceSettings('term1', { [key]: 'x' }, { [key]: '' }));
  assert.throws(() => s.setDeviceSettings('term1', { language: 'fr' }, { language: 'de' }), {
    status: 409,
  });
  assert.equal(s.value.configuration_version, version);
  s.setDeviceSettings(
    'term1',
    { language: 'fr', c20_speaker_volume: 25 },
    { language: 'en', c20_speaker_volume: 50 },
  );
  assert.equal(s.config().language, 'fr');
  assert.equal(s.config().c20_speaker_volume, 25);
  const applied = s.value.configuration_version;
  s.setDeviceSettings('term1', { language: 'fr' }, { language: 'en' });
  assert.equal(s.value.configuration_version, applied);
});

test('reassociation carries serial credentials and profile, leaves personal identity and groups', (t) => {
  const s = storeFixture(t);
  s.createAccount({
    id: 'second',
    type: 'terminal',
    name: 'Second',
    emails: ['other@example.test'],
  });
  const first = { ...s.value.users.term1 },
    second = { ...s.value.users.second };
  s.value.profiles.term1.language = 'fr';
  s.associateTerminal(first.device_id, 'second');
  assert.equal(s.deviceAccount(first.device_token), 'second');
  assert.equal(s.value.users.second.password, second.password);
  assert.equal(s.value.users.second.name, second.name);
  assert.equal(s.value.users.term1.device_id, second.device_id);
  assert.equal(s.config('second').language, 'fr');
  assert.deepEqual(s.value.groups.family.members, ['term1', 'phone1']);
  assert.equal(s.bootstrap().device_id, first.device_id);
  assert.equal(s.bootstrap('second', true).server_url, `http://${s.value.host}:8080`);
  assert.deepEqual(s.bootstrap(null), {
    server_url: 'http://127.0.0.1:8080',
    device_id: 'unassigned',
    device_token: '',
  });
});

test('LAN selection prefers physical private IPv4 then external IPv4 then loopback', (t) => {
  const address = (ip, internal = false, family = 'IPv4') => ({ address: ip, internal, family });
  const network = t.mock.method(os, 'networkInterfaces', () => ({
    lo: [address('127.0.0.1', true)],
    vpn: [address('10.0.0.2')],
    eth0: [address('fe80::1', false, 'IPv6'), address('192.168.1.81')],
  }));
  assert.equal(lanAddress(), '192.168.1.81');
  network.mock.mockImplementation(() => ({ eth0: [address('203.0.113.7')] }));
  assert.equal(lanAddress(), '203.0.113.7');
  network.mock.mockImplementation(() => ({}));
  assert.equal(lanAddress(), '127.0.0.1');
});
