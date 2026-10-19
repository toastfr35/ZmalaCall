// @test S-LLT-038
// @requirements LLR-SRV-DIR-021, LLR-SRV-DIR-022, LLR-SRV-DIR-023, LLR-SRV-DIR-029
// @environment portable
// @plan Use an isolated Store to accept boundary-length account/group fields and reject invalid identifiers, duplicates and over-capacity collections. Check blank-password preservation, mandatory email validation, group membership bounds and unchanged state after rejection. Seed only large collection preconditions directly; execute the real mutation and validation methods.
// @pass The last permitted item must succeed, the next must fail, and rejected edits must preserve the complete state and revision.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { storeFixture } = require('../../support/server/unit-fixture');

const phone = {
  id: 'fixture',
  type: 'app',
  name: 'Fixture',
  emails: ['fixture@example.test'],
};

test('account bounds reject invalid edits without altering the accepted record', (t) => {
  const store = storeFixture(t);
  const id = 'a'.repeat(31),
    password = 'p'.repeat(128);
  store.createAccount({ ...phone, id, name: 'N'.repeat(80), password });
  store.updateAccount(id, { ...phone, id, password: '' });
  assert.equal(store.value.users[id].password, password);
  const snapshot = structuredClone(store.value);
  for (const update of [
    { id: 'a'.repeat(32) },
    { id: 'Bad' },
    { id: '__proto__' },
    { id: 'constructor' },
    { id: 'prototype' },
    { id: 'term1' },
    { id: '' },
    { name: 'N'.repeat(81) },
    { name: ' ' },
    { password: 'p'.repeat(129) },
    { password: 'a\nb' },
    { password: 'a\rb' },
    { password: 'a\0b' },
    { emails: [] },
    { emails: null },
    { emails: ['a@example.test', 'A@EXAMPLE.TEST'] },
  ]) {
    assert.throws(() => store.updateAccount(id, { ...phone, id, ...update }));
    assert.deepEqual(store.value, snapshot);
  }
  assert.throws(() => store.createAccount({ ...phone, emails: undefined }));
  assert.deepEqual(store.value, snapshot);
  for (let i = 0; i < 37; i++) store.createAccount({ ...phone, id: `f${i}` });
  assert.equal(Object.keys(store.value.users).length, 40);
  const full = structuredClone(store.value);
  assert.throws(() => store.createAccount(phone), /40 accounts/);
  assert.deepEqual(store.value, full);
});

test('group names, descriptions, members and total count have enforced bounds', (t) => {
  const store = storeFixture(t);
  for (let i = 0; i < 38; i++) store.createAccount({ ...phone, id: `f${i}` });
  const members = Object.keys(store.value.users);
  const group = { name: 'G'.repeat(80), description: 'D'.repeat(240), members };
  const id = store.createGroup(group);
  assert.deepEqual(store.value.groups[id], group);
  const snapshot = structuredClone(store.value);
  for (const update of [
    { name: 'G'.repeat(81) },
    { name: ' ' },
    { description: 'D'.repeat(241) },
    { members: [...members, members[0]] },
    { members: ['missing'] },
    { members: ['term1', 'term1'] },
    { members: null },
    { name: 'family' },
  ]) {
    assert.throws(() => store.updateGroup(id, { ...group, ...update }));
    assert.deepEqual(store.value, snapshot);
  }
  assert.throws(() => store.createGroup({ ...group, name: group.name.toLowerCase() }), /unique/);
  store.value.groups = Object.fromEntries(
    Array.from({ length: 999 }, (_, i) => [
      `g${i}`,
      { name: `Group ${i}`, description: '', members: [] },
    ]),
  );
  store.createGroup({ name: 'Last group', members: [] });
  assert.equal(Object.keys(store.value.groups).length, 1000);
  const full = structuredClone(store.value);
  assert.throws(() => store.createGroup({ name: 'Overflow', members: [] }), /1000 groups/);
  assert.deepEqual(store.value, full);
});
