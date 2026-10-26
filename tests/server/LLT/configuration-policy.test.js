// @test S-LLT-037
// @requirements LLR-SRV-CONFIG-016, LLR-SRV-CONFIG-017, LLR-SRV-CONFIG-018, LLR-SRV-CONFIG-019, LLR-SRV-CONFIG-020
// @environment portable
// @plan Exercise the real Store with isolated files. Check fresh defaults, each permitted setting, invalid types and boundary values. Reject an entire update without changing configuration, revision or saved bytes. Check auto-answer ring deadlines, media-selector limits, preserved omitted fields and state after restart.
// @pass Accepted choices must be returned and persisted; every invalid candidate must leave the entire previous state unchanged.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { Store } = require('../../../zmala_server/store');
const { storeFixture } = require('../../support/server/unit-fixture');

const base = { display_name: 'Settings fixture', camera: '', microphone: '', speaker: '' };

test('fresh terminal settings and accepted choices survive save and restart', (t) => {
  const store = storeFixture(t);
  const initial = store.config('term1');
  for (const [key, expected] of Object.entries({
    video_resolution: '720p',
    video_fps: 15,
    language: 'en',
    auto_framing: false,
    carousel_portraits: 3,
    tv_idle_seconds: 30,
    c20_speaker_volume: 50,
    ringtone_volume: 50,
    action_sound_volume: 20,
    audio_profile: 'normal',
  }))
    assert.equal(initial[key], expected, key);
  const choices = {
    video_resolution: ['480p', '720p', '1080p'],
    video_fps: [10, 15, 20, 25, 30],
    language: ['fr', 'en', 'ja'],
    auto_framing: [true, false],
    carousel_portraits: [5, 3],
    tv_idle_seconds: [0, 30, 60, 120, 300, 600, 1200],
    c20_speaker_volume: [0, 1, 99, 100],
    ringtone_volume: [0, 5, 50, 100],
    action_sound_volume: [0, 5, 20, 100],
    audio_profile: ['speech', 'normal'],
    command_shell: ['sh', 'bash'],
    auto_answer: [false, true],
    auto_answer_seconds: [5, 10, 30, 60, 120, 300, 600],
  };
  for (const [key, values] of Object.entries(choices))
    for (const value of values) {
      store.setSettings('term1', { ...base, [key]: value });
      assert.equal(store.config('term1')[key], value, `${key}=${value}`);
    }
  const saved = store.config('term1');
  store.setSettings('term1', base);
  for (const key of Object.keys(choices)) assert.equal(store.config('term1')[key], saved[key]);
  assert.deepEqual(new Store(store.dir).config('term1'), store.config('term1'));
  assert.equal(store.ringTimeout('term1'), 630);
  store.setSettings('term1', { ...base, auto_answer_seconds: 5 });
  assert.equal(store.ringTimeout('term1'), 60);
  store.setSettings('term1', { ...base, auto_answer: false, auto_answer_seconds: 600 });
  assert.equal(store.ringTimeout('term1'), 60);
});

test('invalid settings reject the whole candidate before any change or disk write', (t) => {
  const store = storeFixture(t);
  const invalid = {
    video_resolution: ['360p', '2160p', 1080, null],
    video_fps: [0, 14, 60, 15.5, '20', null],
    language: ['xx', 'constructor', '', null, 1],
    auto_framing: [0, 1, 'true', null],
    carousel_portraits: [0, 4, 6, '5', null],
    tv_idle_seconds: [-1, 10, 1800, '30', null],
    c20_speaker_volume: [-1, 101, 50.5, '50', null, NaN],
    ringtone_volume: [-1, 101, 50.5, '50', null, NaN],
    action_sound_volume: [-1, 101, 20.5, '20', null, NaN],
    audio_profile: ['music', '', null],
    command_shell: ['sh -c', '', null, false],
    auto_answer: [0, 'true', null],
    auto_answer_seconds: [4, 601, 30.5, '10', null],
    display_name: ['', ' ', 'a'.repeat(81), null],
  };
  const snapshot = structuredClone(store.value),
    bytes = fs.readFileSync(store.file);
  for (const [key, values] of Object.entries(invalid))
    for (const value of values) {
      assert.throws(() => store.setSettings('term1', { ...base, [key]: value }), undefined, key);
      assert.deepEqual(store.value, snapshot, `${key} must not partially commit`);
      assert.deepEqual(fs.readFileSync(store.file), bytes, `${key} must not write`);
    }
});

test('all three media selectors accept empty or 256 characters and reject invalid values', (t) => {
  const store = storeFixture(t);
  for (const key of ['camera', 'microphone', 'speaker']) {
    for (const value of ['', 'x'.repeat(256)]) {
      store.setSettings('term1', { ...base, [key]: value });
      assert.equal(store.config('term1').terminal_settings[key], value);
    }
    const snapshot = structuredClone(store.value);
    for (const value of ['x'.repeat(257), undefined, null, 1, {}]) {
      assert.throws(() => store.setSettings('term1', { ...base, [key]: value }));
      assert.deepEqual(store.value, snapshot);
    }
  }
});
