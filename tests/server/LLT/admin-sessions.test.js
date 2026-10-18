// @test S-LLT-015
// @requirements LLR-SRV-AUTH-002, LLR-SRV-AUTH-005, LLR-SRV-AUTH-006
// @environment portable
// @plan Hash the same password twice and inject expired sessions and repeated logins; assert distinct salts, correct verification, restart invalidation and bounded sessions/login work.
// @pass Every named assertion must pass; failures or skips do not establish requirement verification.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');

const {
  hashPassword,
  verifyPassword,
  AdminSessions,
} = require('../../../zmala_server/admin-sessions');

test('hashes use distinct salts; sessions expire and restart; login work and memory are bounded', async () => {
  const password = 'test shared password';
  const first = await hashPassword(password),
    second = await hashPassword(password);
  assert.notEqual(first, second);
  assert.equal(await verifyPassword(password, first), true);
  assert.equal(await verifyPassword('wrong', first), false);
  const sessions = new AdminSessions();
  const token = sessions.create();
  assert.equal(sessions.valid(token), true);
  assert.equal(new AdminSessions().valid(token), false);
  sessions.sessions.set(token, Date.now() - 1);
  assert.equal(sessions.valid(token), false);
  for (let i = 0; i < 5; i++) assert.equal(sessions.allowLogin('one'), true);
  assert.equal(sessions.allowLogin('one'), false);
  for (let i = 0; i < 25; i++) assert.equal(sessions.allowLogin('address-' + i), true);
  assert.equal(sessions.allowLogin('another'), false);
  for (let i = 0; i < 200; i++) sessions.create();
  assert.equal(sessions.sessions.size, 100);
});
