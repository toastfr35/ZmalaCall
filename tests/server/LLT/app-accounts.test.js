// @test S-LLT-040
// @requirements LLR-SRV-APP-002, LLR-SRV-APP-003
// @environment portable
// @plan Create and convert app accounts, compare credentials and profile ownership, migrate a schema-six Linphone account twice, then inspect app QR and filtered configuration for credential and Pi-setting isolation.
// @pass Every conversion, migration, rejection and private-view assertion passes without using live accounts.
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { storeFixture } = require('../../support/server/unit-fixture');
const { Store } = require('../../../zmala_server/store');
const { serverPayload } = require('../../../zmala_server/setup-pdf');
test('app and terminal identities are exclusive and conversion revokes both credentials', (t) => {
  const store = storeFixture(t);
  const before = { ...store.value.users.phone1 };
  assert.equal(before.type, 'app');
  assert.match(before.device_id, /^ZP-/);
  assert.equal(store.value.profiles.phone1, undefined);
  store.updateAccount('phone1', { name: 'Converted', type: 'terminal', password: before.password });
  const terminal = { ...store.value.users.phone1 };
  assert.notEqual(terminal.password, before.password);
  assert.notEqual(terminal.device_token, before.device_token);
  assert.equal(store.deviceAccount(before.device_token), undefined);
  assert.ok(store.value.profiles.phone1);
  store.updateAccount('phone1', { name: 'Converted', type: 'app' });
  assert.notEqual(store.value.users.phone1.password, terminal.password);
  assert.equal(store.value.profiles.phone1, undefined);
  assert.equal(store.deviceAccount(terminal.device_token), undefined);
  assert.throws(
    () => store.createAccount({ id: 'bad', name: 'Bad', type: 'linphone' }),
    /App or Terminal/,
  );
});
test('legacy phone migration preserves identity and SIP credentials and generates enrollment once', (t) => {
  const store = storeFixture(t);
  const legacy = structuredClone(store.value);
  legacy.schema_version = 6;
  legacy.users.phone1.type = 'linphone';
  delete legacy.users.phone1.device_id;
  delete legacy.users.phone1.device_token;
  fs.writeFileSync(path.join(store.dir, 'server.json'), JSON.stringify(legacy));
  const first = new Store(store.dir),
    second = new Store(store.dir);
  assert.equal(first.value.schema_version, 7);
  assert.equal(first.value.users.phone1.type, 'app');
  assert.equal(first.value.users.phone1.password, legacy.users.phone1.password);
  assert.deepEqual(second.value, first.value);
  assert.equal(first.value.configuration_version, legacy.configuration_version + 1);
  assert.deepEqual(first.value.groups, legacy.groups);
});
test('app QR and config expose only the app and permitted directory', (t) => {
  const store = storeFixture(t);
  store.createAccount({
    id: 'outsider',
    name: 'Private',
    type: 'app',
    emails: ['private@example.test'],
  });
  const qr = JSON.parse(serverPayload(store.bootstrap('phone1', true)));
  assert.equal(qr.account_type, 'app');
  assert.equal(qr.device_token, store.value.users.phone1.device_token);
  assert.equal(store.bootstrap('term1').account_type, undefined);
  const config = store.appConfig('phone1');
  assert.equal(config.account_type, 'app');
  assert.equal(config.sip.username, 'phone1');
  assert.ok(config.contacts.some((c) => c.id === 'term1'));
  assert.ok(!config.contacts.some((c) => c.id === 'outsider'));
  for (const field of ['video_resolution', 'ssh', 'settings', 'admin_token', 'emails'])
    assert.equal(config[field], undefined);
  assert.ok(!JSON.stringify(config).includes(store.value.users.term1.device_token));
  assert.ok(!JSON.stringify(config).includes(store.value.users.term1.password));
  assert.throws(() => store.appConfig('term1'), /app account/);
  assert.throws(() => store.config('phone1'), /terminal/);
});
