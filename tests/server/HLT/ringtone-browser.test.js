// @test S-HLT-035
// @requirements HLR-SRV-CONFIG-015, HLR-SRV-UI-010, HLR-SRV-UI-011
// @environment display
// @plan Use the actual isolated server and Chromium to import a WAV through the file picker, verify normalized audio and saved selection, and play/pause its authenticated preview. Preserve an unsaved volume change across import, check phone/desktop layout bounds, and verify navigation stops playback. No API or media-control mocks.
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
    await page.goto(fixture.base + '/terminals');
    await page.waitForFunction(
      () =>
        document.querySelector('select[aria-label="Select terminal"]') ||
        document.querySelector('#error')?.textContent,
    );
    assert.equal(await page.locator('#error').innerText(), '', errors.join('; '));
    await page.getByLabel('Select terminal', { exact: true }).selectOption('term1');
    await page.locator('input[name="c20SpeakerVolume"]').fill('73');
    const upload = page.waitForResponse(
      (r) => r.url().includes('/api/ringtones?') && r.request().method() === 'POST',
    );
    await page
      .getByLabel('Add ringtone files', { exact: true })
      .setInputFiles({
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
    assert.equal(await page.locator('input[name="c20SpeakerVolume"]').inputValue(), '73');
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
    assert.equal(await page.locator('input[name="c20SpeakerVolume"]').inputValue(), '73');
    const saved = page.waitForResponse(
      (r) => r.url().endsWith('/api/settings') && r.request().method() === 'PUT',
    );
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    assert.equal((await saved).status(), 200);
    assert.equal(fixture.store.config('term1').ringtone, value);
    assert.equal(fixture.store.config('term1').c20_speaker_volume, 73);
    for (const width of [320, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
        true,
        width + ' ringtone layout',
      );
    }
    assert.deepEqual(errors, []);
  },
);
