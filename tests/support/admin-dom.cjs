'use strict';
const path = require('node:path');
const vm = require('../../build_tools/coverage-js.cjs');

// A recording DOM boundary: controllers remain real, no browser or network needed.
class Element {
  constructor(tag, text = '', className = '') {
    Object.assign(this, {
      tag,
      textContent: text || '',
      className,
      children: [],
      attributes: {},
      events: {},
      value: '',
      checked: false,
      files: [],
      dataset: {},
      open: false,
    });
  }
  append(...children) {
    for (const child of children) {
      child.parentElement = this;
      this.children.push(child);
    }
  }
  replaceChildren(...children) {
    this.children = [];
    this.append(...children);
  }
  setAttribute(name, value) {
    this.attributes[name] = value;
  }
  addEventListener(name, action) {
    this.events[name] = action;
  }
  showModal() {
    this.open = true;
  }
  close() {
    this.open = false;
    this.onclose?.();
    this.events.close?.();
  }
  remove() {
    this.removed = true;
    if (this.parentElement)
      this.parentElement.children = this.parentElement.children.filter((child) => child !== this);
  }
  click() {
    this.clicked = true;
    return this.onclick?.();
  }
  reset() {
    this.resets = (this.resets || 0) + 1;
  }
}

function fixture(filename, configure = () => {}) {
  const elements = [],
    requests = [],
    messages = [],
    timers = [],
    revoked = [],
    pending = [];
  const el = (tag, text, cls) => {
    const node = new Element(tag, text, cls);
    elements.push(node);
    return node;
  };
  const $ = (id) =>
    elements.find((node) => node.id === id && !node.removed) || Object.assign(el('div'), { id });
  const body = el('body');
  body.append(el('nav', '', 'sidebar'));
  const context = {
    Error,
    HTMLDialogElement: Element,
    state: { initialized: true },
    el,
    $,
    document: {
      body,
      getElementById: (id) => elements.find((node) => node.id === id && !node.removed),
      querySelector: (selector) =>
        elements.find(
          (node) => !node.removed && node.className.split(' ').includes(selector.slice(1)),
        ),
      querySelectorAll: () => elements.filter((node) => node.tag === 'dialog' && node.open),
    },
    icon: (name) => el('i', name),
    message: (kind, text) => messages.push({ kind, text }),
    notice: (text) => messages.push({ kind: 'notice', text }),
    setView: (node) => {
      context.view = node;
    },
    location: {
      reload: () => {
        context.reloaded = (context.reloaded || 0) + 1;
      },
    },
    api: async (url, method, value) => {
      requests.push({ url, method, value });
      if (context.failure !== undefined) throw context.failure;
      return context.reply || {};
    },
    fetch: async (url, options) => {
      requests.push({ url, ...options });
      return context.response;
    },
    URL: {
      createObjectURL: (blob) => {
        context.blob = blob;
        return 'blob:private';
      },
      revokeObjectURL: (url) => revoked.push(url),
    },
    link: (label, href) => Object.assign(el('a', label), { href }),
    setTimeout: (action, ms) => timers.push({ action, ms }),
    submit: (form, action, errorId) =>
      pending.push(
        action().catch((error) => messages.push({ kind: errorId, text: error.message })),
      ),
  };
  configure(context);
  const source = vm
    .source(path.resolve(__dirname, '../../zmala_server/web', filename))
    .replace(/^import[^;]+;\s*/gm, '')
    .replace(/^export /gm, '');
  vm.runInNewContext(source, context);
  return Object.assign(context, {
    elements,
    requests,
    messages,
    timers,
    revoked,
    pending,
    find: (tag) => elements.findLast((node) => node.tag === tag && !node.removed),
    button: (label) =>
      elements.findLast(
        (node) => node.tag === 'button' && node.textContent === label && !node.removed,
      ),
    inputs: () => elements.filter((node) => node.tag === 'input'),
    save: async () => context.find('form').onsubmit({ preventDefault() {} }),
  });
}
module.exports = { fixture };
