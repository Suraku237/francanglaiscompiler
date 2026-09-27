const { chromium } = require('../frontend/node_modules/playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');

const root = path.resolve(__dirname, '..');
const output = path.join(root, 'docs', 'presentation', 'screenshots');
const origin = 'https://camfranglais.duckdns.org';

async function main() {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const captures = [];
  const denied = [];
  const errors = [];
  const context = await browser.newContext({
    viewport: { width: 1440, height: 960 },
    deviceScaleFactor: 1.5,
    locale: 'en-GB',
    reducedMotion: 'reduce',
  });
  await context.route('**/api/**', async (route) => {
    const request = route.request();
    if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method())) {
      denied.push(`${request.method()} ${new URL(request.url()).pathname}`);
      await route.abort('blockedbyclient');
      return;
    }
    await route.continue();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(60000);
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('response', (response) => {
    if (response.status() >= 400) {
      errors.push(`HTTP ${response.status()} ${new URL(response.url()).pathname}`);
    }
  });

  async function capture(file, description) {
    await page.waitForFunction(() => ![...document.querySelectorAll('[role="status"]')]
      .some((element) => element.getClientRects().length > 0
        && /loading|preparing|looking up/i.test(element.textContent)));
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: path.join(output, file), fullPage: false });
    const bytes = await fs.readFile(path.join(output, file));
    captures.push({
      file,
      description,
      url: page.url(),
      captured_at: new Date().toISOString(),
      viewport_css_pixels: page.viewportSize(),
      device_scale_factor: 1.5,
      sha256: crypto.createHash('sha256').update(bytes).digest('hex'),
    });
  }

  try {
    const response = await page.goto(`${origin}/#compiler`, { waitUntil: 'domcontentloaded', timeout: 90000 });
    if (!response || response.status() !== 200) throw new Error('Public app did not load with HTTP 200.');
    await page.getByRole('heading', { name: 'Franc Analyzer', exact: true }).waitFor();
    await capture('analyzer-desktop.png', 'Public Analyzer, no test submitted.');
    for (const [hash, heading, filename] of [
      ['analysis', 'Analysis', 'analysis-desktop.png'],
      ['collection', 'Collection', 'collection-desktop.png'],
      ['dictionary', 'Dictionary', 'dictionary-desktop.png'],
      ['examples', 'Synthetic examples', 'examples-desktop.png'],
    ]) {
      await page.goto(`${origin}/#${hash}`, { waitUntil: 'domcontentloaded' });
      await page.getByRole('heading', { name: heading, exact: true }).waitFor();
      await capture(filename, `Real deployed ${heading} page; retained data only.`);
    }
    await page.goto(`${origin}/#dictionary`, { waitUntil: 'domcontentloaded' });
    const searchResponse = page.waitForResponse((response) =>
      response.url().includes('/api/dictionary') && response.url().includes('kass'));
    await page.getByRole('searchbox', { name: 'Search reference dictionary' }).fill('kass');
    await searchResponse;
    await capture('dictionary-search.png', 'Read-only dictionary search for kass.');

    await page.setViewportSize({ width: 420, height: 900 });
    for (const [hash, heading, filename] of [
      ['compiler', 'Franc Analyzer', 'analyzer-mobile.png'],
      ['collection', 'Collection', 'collection-mobile.png'],
    ]) {
      await page.goto(`${origin}/#${hash}`, { waitUntil: 'domcontentloaded' });
      await page.getByRole('heading', { name: heading, exact: true }).waitFor();
      await capture(filename, `Real responsive ${heading} page at 420 CSS pixels.`);
    }
    if (denied.length || errors.length) {
      throw new Error(JSON.stringify({ blocked_non_read_requests: denied, browser_or_http_errors: errors }));
    }
    const manifest = {
      source_url: origin,
      method: 'Local headless Playwright Chromium with real API responses; no DOM alterations or mocks.',
      new_tests_submitted: 0,
      non_read_api_requests_permitted: false,
      images: captures,
      evidence_boundary: 'Working software, not proof of authentic original fieldwork. Counts reflect capture time.',
    };
    await fs.writeFile(path.join(output, 'captures.json'), JSON.stringify(manifest, null, 2) + '\n');
    console.log(JSON.stringify({ images: captures.length, errors, new_tests_submitted: 0 }));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
