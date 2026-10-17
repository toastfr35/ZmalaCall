'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { defaultState } = require('../defaults');

// A tree fixture checks that controls actually join the rendered form, not
// merely the field registry. Browser layout remains a separate visual check.
class Element {
  constructor(tag, text) {
    this.tag = tag;
    this.text = text;
    this.children = [];
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
  contains(target) {
    return this === target || this.children.some((child) => child.contains(target));
  }
}

test('every terminal setting is attached to its visible section, including frame rate', () => {
  const model = { ...defaultState(), terminal_statuses: {}, terminal_languages: [] };
  model.profiles.term1.video_fps = 20;
  const context = {
    state: { model },
    el: (tag, text) => new Element(tag, text),
    HTMLInputElement: Element,
  };
  const source = fs
    .readFileSync(path.join(__dirname, '../web/admin-terminalfields.js'), 'utf8')
    .replace(/^import[^;]+;\s*/gm, '')
    .replace(/^export /gm, '');
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
