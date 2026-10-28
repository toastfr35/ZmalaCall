// @test S-HLT-024
// @requirements HLR-SRV-DATA-013
// @environment portable
// @plan Write a schema-3 server snapshot with fixed device and SIP credentials, mutual and one-way permission edges, and an obsolete video preset. Start the assembled HTTP application from that directory, authenticate as the retained terminal, and inspect its migrated configuration. Restart the Store and compare identity, permissions, defaults and revision to prove migration is idempotent.
// @pass HTTP configuration must preserve credentials and identity, normalize the old preset, and derive only direct mutual permission. A second startup must not change the migrated revision or invent email addresses.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { defaultState } = require('../../../zmala_server/defaults');
const { Store } = require('../../../zmala_server/store');
const { createApplication } = require('../../../zmala_server/main');
const { listenHttp } = require('../../support/server/listen-http');

test('older state migrates before HTTP configuration is served and stays stable after restart', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'zmala-migration-system-'));
  let application;
  try {
    const legacy = defaultState();
    legacy.schema_version = 3;
    delete legacy.groups;
    legacy.users.term1.device_id = 'ZM-fixture-kept';
    legacy.users.term1.device_token = 'fixture-device-token';
    legacy.users.term1.password = 'fixture-sip-password';
    legacy.users.visitor = { name: 'Visitor', type: 'app', password: 'fixture-visitor' };
    delete legacy.users.phone1.emails;
    legacy.permissions = {
      term1: { phone1: true, visitor: true },
      phone1: { term1: true, visitor: true },
      visitor: { phone1: true },
    };
    legacy.profiles.term1.video_resolution = '360p';
    delete legacy.profiles.term1.video_fps;
    fs.writeFileSync(path.join(directory, 'server.json'), JSON.stringify(legacy));
    const store = new Store(directory);
    application = createApplication({ store });
    await listenHttp(application.server);
    const base = `http://127.0.0.1:${application.server.address().port}`;
    const response = await fetch(base + '/api/config', {
      headers: { Authorization: 'Bearer fixture-device-token' },
    });
    assert.equal(response.status, 200);
    const config = await response.json();
    assert.equal(config.device_id, 'ZM-fixture-kept');
    assert.equal(config.sip.password, 'fixture-sip-password');
    assert.equal(config.video_resolution, '480p');
    assert.equal(config.video_fps, 15);
    assert.equal(config.contacts.find((contact) => contact.id === 'phone1').can_call, true);
    assert.equal(config.contacts.find((contact) => contact.id === 'visitor').can_call, false);
    await application.flush();
    const restored = new Store(directory);
    assert.equal(restored.value.schema_version, 7);
    assert.equal(restored.value.configuration_version, config.configuration_version);
    assert.deepEqual(config.callbacks, []);
    assert.ok(config.contacts.every((contact) => contact.online === false));
    assert.deepEqual(restored.config('term1'), store.config('term1'));
    assert.deepEqual(restored.value.users.phone1.emails, []);
    assert.deepEqual(restored.value.users.visitor.emails, []);
  } finally {
    if (application) {
      application.server.closeAllConnections();
      await new Promise((resolve) => application.server.close(resolve));
      await application.flush();
    }
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
