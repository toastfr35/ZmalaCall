// @test S-LLT-010
// @requirements LLR-SRV-UI-016, LLR-SRV-UI-017, LLR-SRV-UI-019
// @environment portable
// @plan Render terminal field definitions with DOM/API doubles; assert controls attach to the intended sections, frame-rate choices are present and drafts/download errors retain ownership.
// @pass All named assertion cases must pass; skips and visual/hardware checks are recorded separately.

'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const vm = require('../../../build_tools/coverage-js.cjs');
const { defaultState } = require('../../../zmala_server/defaults');

// A tree fixture checks that controls actually join the rendered form, not
// merely the field registry. Browser layout remains a separate visual check.
class Element {
  constructor(tag, text) {
    this.tag = tag;
    this.text = text;
    this.children = [];
    this.dataset = {};
    this.classList = { add() {} };
  }
  append(...children) {
    this.children.push(...children);
  }
  prepend(...children) {
    for (const child of children) this.children = this.children.filter((item) => item !== child);
    this.children.unshift(...children);
  }
  setAttribute() {}
  addEventListener() {}
  pause() {}
  remove() {}
  querySelector() {
    return null;
  }
  contains(target) {
    return this === target || this.children.some((child) => child.contains(target));
  }
}

test('every terminal setting is attached to its visible section, including frame rate', () => {
  const model = {
    ...defaultState(),
    terminal_statuses: {},
    terminal_languages: [],
    ringtone_choices: [{ id: 'nokia', name: 'Nokia' }],
  };
  model.profiles.term1.video_fps = 20;
  const context = {
    state: { model },
    el: (tag, text) => new Element(tag, text),
    HTMLInputElement: Element,
  };
  const source = ['ringtones', 'terminalfields']
    .map((name) =>
      vm
        .source(path.join(__dirname, `../../../zmala_server/web/admin-${name}.js`), 'utf8')
        .replace(/^import[^;]+;\s*/gm, '')
        .replace(/^export /gm, ''),
    )
    .join('\n');
  vm.runInNewContext(source, context);
  const form = { fields: {} };
  const sections = new Element('form');
  context.buildCallFields(form, sections, 'term1');
  context.buildMediaFields(form, sections, 'term1');
  context.buildGeneralFields(form, sections, 'term1');
  for (const [name, field] of Object.entries(form.fields))
    assert.ok(sections.contains(field), `${name} must be attached to the visible form`);
  assert.equal(form.fields.videoFps.value, '20');
  assert.deepEqual(
    Array.from(form.fields.videoFps.children, (option) => option.value),
    ['10', '15', '20', '25', '30'],
  );
  assert.equal(form.fields.tvIdleSeconds.value, '30');
});

test('terminal drafts retain their original revision and setup downloads propagate failures', async () => {
  const requests = [],
    actions = [];
  const model = {
    ...defaultState(),
    terminal_statuses: {},
    terminal_languages: [],
    ringtone_choices: [{ id: 'nokia', name: 'Nokia' }],
  };
  const context = {
    state: { model, refresh: async () => {} },
    el: (tag, text) => new Element(tag, text),
    HTMLInputElement: Element,
    query: (form) => form.children[0],
    submit: (_form, action) => action(),
    api: async (_url, _method, value) => {
      requests.push(value);
    },
    notice() {},
    openWifi() {},
    openConsole() {},
    serverPdf: async () => {
      throw Error('Download failed');
    },
    actionButton: (text, action) => {
      actions.push({ text, action });
      return new Element('button', text);
    },
  };
  for (const name of ['ringtones', 'terminalfields', 'terminals']) {
    const source = vm
      .source(path.join(__dirname, `../../../zmala_server/web/admin-${name}.js`), 'utf8')
      .replace(/^import[^;]+;\s*/gm, '')
      .replace(/^export /gm, '');
    vm.runInNewContext(source, context);
  }
  const card = new Element('section');
  card.dataset.terminalId = 'term1';
  const revision = model.configuration_version;
  const form = context.buildDevicesForm(card, 'term1');
  model.configuration_version += 10;
  form.fields.videoFps.value = '20';
  await form.onsubmit({ preventDefault() {} });
  assert.equal(requests[0].configuration_version, revision);
  assert.equal(requests[0].video_fps, 20);
  await assert.rejects(
    actions.find(({ text }) => text === 'Download server QR PDF').action(),
    /Download failed/,
  );
});
