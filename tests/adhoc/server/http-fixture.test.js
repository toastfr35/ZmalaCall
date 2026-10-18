'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const { httpFixture } = require('../../support/server/http-fixture');

for (const code of ['EADDRINUSE', 'EACCES']) {
  test(`HTTP fixture retries ${code} and serves requests on another port`, async (t) => {
    const listen = http.Server.prototype.listen;
    let attempts = 0;
    t.mock.method(http.Server.prototype, 'listen', function (...args) {
      attempts++;
      if (attempts === 1) {
        queueMicrotask(() => this.emit('error', Object.assign(new Error(code), { code })));
        return this;
      }
      return listen.apply(this, args);
    });
    const fixture = await httpFixture();
    try {
      assert.ok(attempts >= 2);
      const response = await fetch(fixture.base + '/health');
      assert.equal(response.status, 200);
      await response.text();
    } finally {
      await fixture.close();
    }
  });
}
