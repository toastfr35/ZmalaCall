'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { defaultState } = require('../defaults');
const { migrate } = require('../migrations');

test('legacy low video presets migrate once without changing other profiles', () => {
  const state = defaultState();
  state.profiles.other = structuredClone(state.profiles.term1);
  state.profiles.term1.video_resolution = '360p';
  const before = state.configuration_version;
  const other = structuredClone(state.profiles.other);
  migrate(state);
  assert.equal(state.profiles.term1.video_resolution, '480p');
  assert.deepEqual(state.profiles.other, other);
  assert.equal(state.configuration_version, before + 1);
  migrate(state);
  assert.equal(state.configuration_version, before + 1);
});
