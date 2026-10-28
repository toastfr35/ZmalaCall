// @test S-LLT-027
// @requirements LLR-SRV-DIR-033, LLR-SRV-UI-012, LLR-SRV-UI-013, LLR-SRV-UI-014, LLR-SRV-UI-015, LLR-SRV-CONFIG-018
// @environment display
// @plan Render the actual admin HTML/CSS/controllers in headless Chromium with every API replaced by a deterministic fixture. Verify fixed C20 media information without camera, microphone or speaker selectors. Check GIF guidance and first-frame dimensions against accepted and rejected synthetic files. Check six English pages and sign-in at 320, 390, 700 and 1920 pixels, narrow labelled rows, touch sizes, modal scrolling, focused drafts and editor-local errors/cancellation.
// @pass All computed layout and interaction assertions must pass against the mocked API; no live service or account is changed.

'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const coverage = require('../../../build_tools/coverage-js.cjs');
const path = require('node:path');
const { chromium } = require('playwright');
const { storeFixture } = require('../../support/server/unit-fixture');

test('admin component fits phones and desktop and preserves modal drafts', async (t) => {
  const s = storeFixture(t),
    browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const navigate = page.goto.bind(page);
  page.goto = async (...args) => {
    await coverage.collectPage(page);
    return navigate(...args);
  };
  t.after(async () => {
    await coverage.collectPage(page);
    await browser.close();
  });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const model = {
    ...s.admin(),
    sip_status: {
      registrations: [],
      events: [{ time: new Date().toISOString(), message: 'Fixture event' }],
      active_calls: 0,
      calls: [],
    },
    terminal_statuses: {},
    callbacks: [],
  };
  let signedIn = true;
  let savedSettings;
  model.profiles.term1.terminal_settings = {
    camera: 'old camera',
    microphone: 'old microphone',
    speaker: 'HDMI',
  };
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url()),
      name = url.pathname;
    if (name.startsWith('/api/')) {
      let status = 200,
        body = {};
      if (name === '/api/auth/status') body = { setup_required: false, can_setup: false };
      else if (!signedIn) {
        status = 401;
        body = { error: 'Sign in' };
      } else if (route.request().method() !== 'GET') {
        if (name === '/api/settings') savedSettings = route.request().postDataJSON();
        status = 409;
        body = { error: 'Fixture conflict: reopen editor' };
      } else if (name.startsWith('/api/admin')) body = model;
      else if (name === '/api/server/ssh') body = { supported: false };
      else if (name === '/api/server/backup/status') body = { result: 'none' };
      await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
      return;
    }
    const file =
      name === '/zmala-icon.svg'
        ? path.resolve(__dirname, '../../../zmala_server/assets/zmala-icon.svg')
        : path.resolve(
            __dirname,
            '../../../zmala_server/web',
            /\.(js|css)$/.test(name) ? path.basename(name) : 'admin.html',
          );
    const contentType = file.endsWith('.js')
      ? 'text/javascript'
      : file.endsWith('.css')
        ? 'text/css'
        : file.endsWith('.svg')
          ? 'image/svg+xml'
          : 'text/html';
    await route.fulfill({ status: 200, contentType, body: coverage.browserSource(file) });
  });
  for (const width of [320, 390, 700, 1920]) {
    await page.setViewportSize({ width, height: 800 });
    for (const [route, title] of [
      ['/', ''],
      ['/accounts', 'Accounts'],
      ['/groups', 'Groups'],
      ['/terminals', 'Terminals'],
      ['/callbacks', 'Callbacks'],
      ['/activity', 'Activity'],
    ]) {
      await page.goto('http://zmala.test' + route);
      await page.locator('#view > *').first().waitFor();
      assert.equal(await page.locator('h1').innerText(), title);
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        true,
        `${route} overflow at ${width}`,
      );
      const color = await page
        .locator('body')
        .evaluate((el) => getComputedStyle(el).backgroundColor);
      assert.notEqual(color, 'rgb(255, 255, 255)');
      if (route === '/activity')
        assert.match(await page.locator('#view').innerText(), /Fixture event/);
      if (route === '/accounts' && width <= 700) {
        assert.equal(
          await page
            .locator('#account-rows td')
            .first()
            .evaluate((el) => getComputedStyle(el).display),
          'block',
        );
        assert.equal(
          await page.locator('#account-rows td').first().getAttribute('data-label'),
          'Account',
        );
      }
      if (route === '/terminals') {
        await page.getByText('Nuroum C20 supplies', { exact: false }).waitFor();
        for (const label of ['Camera', 'Microphone', 'Speaker']) {
          assert.equal(await page.getByLabel(label, { exact: true }).count(), 0);
        }
      }
      if (width <= 700) {
        const sizes = await page
          .locator('nav a, #page-actions button, .icon-button:visible')
          .evaluateAll((nodes) => nodes.map((el) => el.getBoundingClientRect().height));
        assert.ok(
          sizes.every((height) => height >= 44),
          `${route}: undersized touch target`,
        );
      }
    }
  }
  await page.goto('http://zmala.test/terminals');
  await page.locator('form[data-kind=devices] button[type=submit]').click();
  await page.getByText('Fixture conflict: reopen editor', { exact: true }).waitFor();
  assert.ok(savedSettings);
  for (const key of ['camera', 'microphone', 'speaker']) assert.equal(savedSettings[key], '');
  await page.setViewportSize({ width: 320, height: 640 });
  await page.goto('http://zmala.test/accounts');
  await page.getByRole('button', { name: 'New account', exact: true }).click();
  await page.locator('#edit-name').fill('Unsaved fixture');
  await page.locator('#edit-id').fill('fixture');
  await page.locator('#edit-emails').fill('fixture@example.test');
  const dialog = page.locator('#account-dialog');
  assert.equal(await dialog.evaluate((el) => getComputedStyle(el).overflowY), 'auto');
  assert.ok((await dialog.boundingBox()).height <= 640);
  assert.match(await page.locator('#portrait-help').innerText(), /480 × 480/);
  assert.match(await page.locator('#edit-photo').getAttribute('accept'), /image\/gif/);
  const { gif } = require('../../support/server/portrait-fixture');
  const invalid = gif();
  invalid.writeUInt16LE(479, 6);
  await page
    .locator('#edit-photo')
    .setInputFiles({ name: 'wrong.gif', mimeType: 'image/gif', buffer: invalid });
  await page.locator('#account-error').filter({ hasText: '479 × 480' }).waitFor();
  await page
    .locator('#edit-photo')
    .setInputFiles({ name: 'portrait.gif', mimeType: 'image/gif', buffer: gif() });
  await page.locator('#account-picture-preview img').waitFor();
  assert.equal(await page.locator('#account-error').innerText(), '');
  await page.locator('#edit-photo').setInputFiles([]);
  await page.locator('#account-save').click();
  await page.getByText('Fixture conflict: reopen editor', { exact: true }).waitFor();
  assert.equal(await page.locator('#edit-name').inputValue(), 'Unsaved fixture');
  assert.equal(await dialog.getAttribute('open'), '');
  await page.keyboard.press('Escape');
  assert.equal(await dialog.getAttribute('open'), null);
  await page.goto('http://zmala.test/groups');
  await page.getByRole('button', { name: 'New group', exact: true }).click();
  await page.locator('#group-name').fill('Unsaved group');
  await page.locator('#group-save').click();
  await page.locator('#group-error').filter({ hasText: 'Fixture conflict' }).waitFor();
  assert.equal(await page.locator('#group-name').inputValue(), 'Unsaved group');
  await page.keyboard.press('Escape');
  signedIn = false;
  for (const width of [320, 1920]) {
    await page.setViewportSize({ width, height: 800 });
    await page.goto('http://zmala.test/');
    await page.locator('.signin-card').waitFor();
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
      true,
    );
    if (width === 320) {
      assert.ok(
        (await page
          .locator('.signin-card input')
          .first()
          .evaluate((el) => parseFloat(getComputedStyle(el).fontSize))) >= 16,
      );
    }
  }
  assert.deepEqual(errors, []);
});
