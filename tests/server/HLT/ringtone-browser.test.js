// @test S-HLT-035
// @requirements HLR-SRV-CONFIG-015, HLR-SRV-UI-010, HLR-SRV-UI-011
// @environment display
// @plan Use the actual isolated server and Chromium to import a WAV through the file picker, verify normalized audio and saved selection, and play/pause its authenticated preview. Verify all 5-percent speaker-volume choices and preserve an unsaved volume change across import, check phone/desktop layout bounds, and verify navigation stops playback. Post real device peripheral reports, check live badges while edits remain unsaved, then age the browser clock to verify stale hardware status is unavailable. No API or media-control mocks.
// @pass Accepted imports and edits persist, preview decodes, navigation pauses it, both layouts fit and no page errors occur. This does not establish physical speaker audibility.
'use strict';
/* global document, innerWidth */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require('playwright');
const { httpFixture } = require('../../support/server/http-fixture');
const { DEFAULT_SOUND, validateSound } = require('../../../zmala_server/ringtones');

test(
  'browser ringtone import, retained edits, audio preview and narrow layout',
  { timeout: 40000 },
  async (t) => {
    const fixture = await httpFixture();
    t.after(() => fixture.close());
    fixture.store.createAccount({
      id: 'other',
      name: 'Other terminal',
      type: 'terminal',
      emails: ['other@example.test'],
    });
    const browser = await chromium.launch({ headless: true });
    t.after(() => browser.close());
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    page.setDefaultTimeout(8000);
    const errors = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.goto(fixture.base);
    await page.getByLabel('Admin password', { exact: true }).fill('ringtone-browser-password');
    await page
      .getByLabel('Confirm admin password', { exact: true })
      .fill('ringtone-browser-password');
    await page.getByRole('button', { name: 'Set password', exact: true }).click();
    await page.getByRole('button', { name: 'Sign out', exact: true }).waitFor();
    const report = async (status) => {
      const response = await fetch(fixture.base + '/api/status', {
        method: 'POST',
        headers: {
          Authorization: 'Bearer ' + fixture.store.value.users.term1.device_token,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(status),
      });
      assert.equal(response.status, 200);
      await response.arrayBuffer();
    };
    const hardware = {
      remote_status: 'connected',
      remote_battery: 75,
      remote_charger_connected: true,
      camera_status: 'connected',
      camera_powered: true,
      camera_connected: true,
    };
    await report(hardware);
    await page.goto(fixture.base + '/terminals');
    await page.waitForFunction(
      () =>
        document.querySelector('select[aria-label="Select terminal"]') ||
        document.querySelector('#error')?.textContent,
    );
    assert.equal(await page.locator('#error').innerText(), '', errors.join('; '));
    await page.getByLabel('Select terminal', { exact: true }).selectOption('term1');
    await page.locator('select[name="c20SpeakerVolume"]').selectOption('75');
    await page.getByText('Remote battery: 75%', { exact: true }).waitFor();
    await page.getByText('Remote charger: connected', { exact: true }).waitFor();
    await page.getByText('C20: connected', { exact: true }).waitFor();
    await report({
      ...hardware,
      remote_battery: 31,
      remote_charger_connected: false,
      camera_status: 'off',
      camera_powered: false,
      camera_connected: false,
    });
    await page.getByText('Remote battery: 31%', { exact: true }).waitFor();
    await page.getByText('Remote charger: not connected', { exact: true }).waitFor();
    await page.getByText('C20: powered off', { exact: true }).waitFor();
    assert.equal(await page.locator('select[name="c20SpeakerVolume"]').inputValue(), '75');

    assert.deepEqual(
      await page
        .locator('select[name="c20SpeakerVolume"]')
        .evaluate((el) => Array.from(el.options, (option) => option.value)),
      Array.from({ length: 21 }, (_, i) => String(i * 5)),
    );
    const upload = page.waitForResponse(
      (r) => r.url().includes('/api/ringtones?') && r.request().method() === 'POST',
    );
    await page.getByLabel('Add ringtone files', { exact: true }).setInputFiles({
      name: 'Fixture tone.wav',
      mimeType: 'audio/wav',
      buffer: fs.readFileSync(DEFAULT_SOUND),
    });
    assert.equal((await upload).status(), 201);
    await page
      .getByText('Ringtones added. Choose a tone and save changes.', { exact: true })
      .waitFor();
    const select = page.getByLabel('Ringtone', { exact: true }),
      value = await select.inputValue();
    assert.match(value, /^[a-f0-9]{64}$/);
    assert.equal(await page.locator('select[name="c20SpeakerVolume"]').inputValue(), '75');
    const file = require('node:path').join(fixture.directory, 'ringtones', value + '.wav');
    assert.equal(validateSound(fs.readFileSync(file)), value);
    const audio = page.getByLabel('Ringtone preview', { exact: true });
    await audio.evaluate(async (element) => {
      await element.play();
    });
    assert.equal(await audio.evaluate((element) => element.paused), false);
    const element = await audio.elementHandle();
    await page.getByLabel('Select terminal', { exact: true }).selectOption('other');
    await page.waitForFunction((element) => element.paused, element);
    await page.getByLabel('Select terminal', { exact: true }).selectOption('term1');
    assert.equal(await page.getByLabel('Ringtone', { exact: true }).inputValue(), value);
    assert.equal(await page.locator('select[name="c20SpeakerVolume"]').inputValue(), '75');
    const saved = page.waitForResponse(
      (r) => r.url().endsWith('/api/settings') && r.request().method() === 'PUT',
    );
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    assert.equal((await saved).status(), 200);
    assert.equal(fixture.store.config('term1').ringtone, value);
    assert.equal(fixture.store.config('term1').c20_speaker_volume, 75);
    for (const width of [320, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        true,
        width + ' ringtone layout',
      );
    }
    await page.evaluate(() => {
      const now = Date.now();
      Date.now = () => now + 21000;
    });
    await page.getByText('Remote: status unavailable', { exact: true }).waitFor();
    await page.getByText('C20: status unavailable', { exact: true }).waitFor();
    assert.deepEqual(errors, []);
  },
);
