// @test S-HLT-013
// @requirements HLR-SRV-DIR-002, HLR-SRV-MAINT-001, HLR-SRV-DATA-001, HLR-SRV-MAINT-002
// @environment portable
// @plan Use HTTP device/admin polling while delaying persistence; assert live state remains responsive, cached contacts cannot leak mutations, claims wait for durable leases and callback notifications follow commit.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { httpFixture } = require('../../support/server/http-fixture');

test('versioned device polling keeps live updates separate and falls back after edits', async () => {
  const fixture = await httpFixture();
  const headers = { Authorization: 'Bearer ' + fixture.store.value.users.term1.device_token };
  const get = async (route) => {
    const response = await fetch(fixture.base + route, { headers });
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    return response.json();
  };
  try {
    const full = await get('/api/config');
    const route = '/api/config?delta=1&version=' + full.configuration_version;
    const delta = await get(route);
    assert.deepEqual(Object.keys(delta).sort(), ['configuration_version', 'live']);
    assert.deepEqual(
      delta.live.contacts,
      full.contacts.map(({ id, online }) => ({ id, online })),
    );
    fixture.sipServer.registrations.set('phone1', { expires: Date.now() + 60000 });
    assert.equal((await get(route)).live.contacts.find((c) => c.id === 'phone1').online, true);
    fixture.callbacks.create('term1', 'phone1');
    assert.equal((await get(route)).live.callbacks.length, 1);
    fixture.store.updateGroup('family', {
      ...fixture.store.value.groups.family,
      members: ['term1'],
    });
    const changed = await get(route);
    assert.equal(changed.contacts.find((c) => c.id === 'phone1').can_call, false);
    assert.ok(changed.sip);
    const unauthorized = await fetch(fixture.base + route);
    assert.equal(unauthorized.status, 401);
  } finally {
    await fixture.close();
  }
});

test('stable contact cache cannot leak live mutations and invalidates on account edits', async () => {
  const fixture = await httpFixture();
  try {
    const view = fixture.store.contacts('term1');
    view[0].name = 'Not shared';
    view[0].online = true;
    assert.notEqual(fixture.store.contacts('term1')[0].name, 'Not shared');
    assert.equal('online' in fixture.store.contacts('term1')[0], false);
    fixture.store.updateAccount('phone1', {
      name: 'Renamed',
      type: 'linphone',
      emails: ['a@example.test'],
    });
    assert.equal(fixture.store.contacts('term1').find((c) => c.id === 'phone1').name, 'Renamed');
  } finally {
    await fixture.close();
  }
});

test('admin live polling omits stable accounts; immutable photos stay authenticated', async () => {
  const fixture = await httpFixture();
  const headers = { Authorization: 'Bearer ' + fixture.store.value.admin_token };
  try {
    const response = await fetch(fixture.base + '/api/admin/live', { headers });
    assert.equal(response.status, 200);
    const live = await response.json();
    assert.equal('users' in live, false);
    assert.equal('profiles' in live, false);
    assert.ok(live.sip_status);
    assert.ok((await (await fetch(fixture.base + '/api/admin', { headers })).json()).users);
    await fs.mkdir(path.join(fixture.directory, 'photos'), { recursive: true });
    await fs.writeFile(path.join(fixture.directory, 'photos', 'abcd.png'), 'test image');
    const photo = await fetch(fixture.base + '/photos/abcd.png', { headers });
    assert.equal(photo.status, 200);
    assert.equal(photo.headers.get('cache-control'), 'private, max-age=31536000, immutable');
    assert.equal((await fetch(fixture.base + '/photos/abcd.png')).status, 401);
  } finally {
    await fixture.close();
  }
});

test('console claims yield to health requests and persist the lease before returning', async (t) => {
  const fixture = await httpFixture();
  const job = fixture.consoleJobs.create('term1', { command: 'echo durable', timeout_seconds: 5 });
  await fixture.consoleJobs.flush();
  let release, started;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const writing = new Promise((resolve) => {
    started = resolve;
  });
  const original = fs.writeFile;
  const mock = t.mock.method(fs, 'writeFile', async (file, ...args) => {
    if (file === fixture.consoleJobs.file + '.tmp') {
      started();
      await gate;
    }
    return original(file, ...args);
  });
  let completed = false;
  const request = fetch(fixture.base + '/api/console/next', {
    method: 'POST',
    headers: { Authorization: 'Bearer ' + fixture.store.value.users.term1.device_token },
  }).then((response) => {
    completed = true;
    return response;
  });
  try {
    await writing;
    assert.equal(completed, false);
    assert.equal(
      (await fetch(fixture.base + '/health', { signal: AbortSignal.timeout(2000) })).status,
      200,
    );
    release();
    const claimed = (await (await request).json()).job;
    assert.equal(claimed.id, job.id);
    const persisted = JSON.parse(await fs.readFile(fixture.consoleJobs.file, 'utf8')).find(
      (r) => r.id === job.id,
    );
    assert.equal(persisted.status, 'running');
    assert.equal(persisted.lease, claimed.lease);
  } finally {
    release();
    await request;
    mock.mock.restore();
    await fixture.close();
  }
});

test('callback notifications wait for the queued request snapshot', async (t) => {
  const fixture = await httpFixture();
  let release, started;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  const writing = new Promise((resolve) => {
    started = resolve;
  });
  const original = fs.writeFile;
  const mock = t.mock.method(fs, 'writeFile', async (file, ...args) => {
    if (file === fixture.callbacks.file + '.tmp') {
      started();
      await gate;
    }
    return original(file, ...args);
  });
  let notified = false;
  fixture.sipServer.registrations.set('phone1', { expires: Date.now() + 60000 });
  fixture.sipServer.notifyCallback = async () => {
    notified = true;
    return true;
  };
  try {
    const created = fixture.callbacks.create('term1', 'phone1');
    await writing;
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(notified, false);
    assert.equal((await fetch(fixture.base + '/health')).status, 200);
    release();
    while (fixture.callbacks.sending.size) await new Promise((resolve) => setImmediate(resolve));
    assert.equal(notified, true);
    await fixture.callbacks.flush();
    const saved = JSON.parse(await fs.readFile(fixture.callbacks.file, 'utf8'));
    assert.ok(saved.find((r) => r.id === created.id).notified_at);
  } finally {
    release();
    mock.mock.restore();
    await fixture.close();
  }
});
