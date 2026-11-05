// Browser shaping preserves Arabic/Urdu bidi, Indic clusters, Thai and CJK.
/* global document */
const fs = require('node:fs');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');

async function main() {
  const jobs = JSON.parse(fs.readFileSync(0, 'utf8'));
  const browser = await chromium.launch({
    headless: true,
    ...(process.argv[2] ? { executablePath: process.argv[2] } : {}),
  });
  try {
    const page = await browser.newPage();
    for (const job of jobs) {
      await page.goto(pathToFileURL(job.html).href);
      await page.emulateMedia({ media: 'print' });
      await page.evaluate(async () => {
        await document.fonts.ready;
        await Promise.all(Array.from(document.images, (img) => img.decode()));
      });
      const problems = await page.evaluate(() => {
        const errors = [];
        for (const [index, sheet] of Array.from(document.querySelectorAll('.page')).entries()) {
          const area = sheet.querySelector('main').getBoundingClientRect();
          const footer = sheet.querySelector('footer').getBoundingClientRect();
          if (area.bottom > footer.top - 6)
            errors.push(
              `page ${index + 1}: content reaches footer (${Math.ceil((area.bottom - footer.top + 6) / 3.7795)} mm too tall)`,
            );
          for (const item of sheet.querySelectorAll('main *')) {
            const rect = item.getBoundingClientRect();
            const bounds = sheet.getBoundingClientRect();
            if (rect.left < bounds.left || rect.right > bounds.right + 1)
              errors.push(`page ${index + 1}: horizontal overflow`);
            if (item.clientWidth && item.scrollWidth > item.clientWidth + 1)
              errors.push(`page ${index + 1}: text overflows its container`);
            if (item.tagName === 'IMG' && (!item.complete || !item.naturalWidth))
              errors.push(`page ${index + 1}: image failed`);
          }
        }
        return errors;
      });
      if (problems.length) throw new Error(`${job.html}: ${problems.join('; ')}`);
      await page.pdf({
        path: job.pdf,
        preferCSSPageSize: true,
        printBackground: true,
        displayHeaderFooter: false,
      });
      console.log(`Rendered ${job.pdf}`);
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
