import puppeteer from 'puppeteer';

const URL = process.env.SHOT_URL || 'http://localhost:4173/';

const browser = await puppeteer.launch({
  headless: 'new',
  args: [
    '--no-sandbox',
    '--enable-unsafe-swiftshader',
    '--use-gl=angle',
    '--use-angle=swiftshader',
    '--ignore-gpu-blocklist',
    '--window-size=1440,900'
  ]
});

const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });

const errors = [];
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', (e) => errors.push('PAGEERROR: ' + e.message));

await page.goto(URL, { waitUntil: 'networkidle0', timeout: 60000 });

// Confirm WebGL actually initialised.
const webglOk = await page.evaluate(() => {
  const c = document.querySelector('canvas.webgl');
  if (!c) return false;
  const gl = c.getContext('webgl2') || c.getContext('webgl');
  return !!gl;
});

// Let the loader counter + intro bloom-in finish.
await new Promise((r) => setTimeout(r, 5000));
await page.screenshot({ path: 'screenshots/01-hero.png' });

// Scroll to ~45% to capture the mid-scroll camera + palette shift.
await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight * 0.45));
await new Promise((r) => setTimeout(r, 2500));
await page.screenshot({ path: 'screenshots/02-midscroll.png' });

// Scroll near the end for the magenta palette + close camera.
await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
await new Promise((r) => setTimeout(r, 2500));
await page.screenshot({ path: 'screenshots/03-contact.png' });

console.log('WEBGL_OK:', webglOk);
console.log('CONSOLE_ERRORS:', errors.length ? JSON.stringify(errors, null, 2) : 'none');

await browser.close();
