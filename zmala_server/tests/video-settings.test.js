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

test('missing frame rate defaults to 15 once and preserves explicit rates', () => {
  const state = defaultState();
  delete state.profiles.term1.video_fps;
  state.profiles.other = { ...state.profiles.term1, video_fps: 30 };
  const before = state.configuration_version;
  migrate(state);
  assert.equal(state.profiles.term1.video_fps, 15);
  assert.equal(state.profiles.other.video_fps, 30);
  assert.equal(state.configuration_version, before + 1);
  migrate(state);
  assert.equal(state.configuration_version, before + 1);
});
