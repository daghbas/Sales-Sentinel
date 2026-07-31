import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const datasetId = '9c87bd42ct';
const datasetUrl = `https://data.mendeley.com/datasets/${datasetId}/1`;
const legacyZipUrl = `https://api.data.mendeley.com/datasets/${datasetId}/zip/file_downloaded?version=1`;
const outputDir = path.resolve('data/raw');
const outputFile = path.join(outputDir, 'Redsea-Dataset.zip');
await fs.mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ acceptDownloads: true });
const page = await context.newPage();
page.setDefaultTimeout(45_000);

let authorization = null;
const candidateUrls = new Set([legacyZipUrl]);

function collectUrls(value) {
  if (typeof value === 'string') {
    if (/^https?:\/\//i.test(value) && /(download|file|zip|dataset)/i.test(value)) candidateUrls.add(value);
    return;
  }
  if (Array.isArray(value)) {
    for (const item of value) collectUrls(item);
    return;
  }
  if (value && typeof value === 'object') {
    for (const item of Object.values(value)) collectUrls(item);
  }
}

page.on('request', async request => {
  const url = request.url();
  if (!url.includes('mendeley.com')) return;
  try {
    const headers = await request.allHeaders();
    if (headers.authorization) authorization = headers.authorization;
  } catch {}
});

page.on('response', async response => {
  const url = response.url();
  if (!url.includes('mendeley.com')) return;
  candidateUrls.add(url);
  try {
    const contentType = response.headers()['content-type'] || '';
    if (contentType.includes('json')) collectUrls(await response.json());
  } catch {}
});

async function saveApiResponse(response, label) {
  if (!response || !response.ok()) return false;
  const body = await response.body();
  const contentType = response.headers()['content-type'] || '';
  const isZip = body.length > 4 && body[0] === 0x50 && body[1] === 0x4b;
  if (!isZip && !contentType.includes('zip') && !contentType.includes('octet-stream')) return false;
  await fs.writeFile(outputFile, body);
  console.log(`Saved ${outputFile} from ${label}; bytes=${body.length}`);
  return true;
}

try {
  await page.goto(datasetUrl, { waitUntil: 'domcontentloaded', timeout: 90_000 });
  await page.waitForLoadState('networkidle', { timeout: 30_000 }).catch(() => {});

  for (const label of ['Accept all cookies', 'Accept All Cookies', 'Accept', 'I agree']) {
    const candidate = page.getByRole('button', { name: label, exact: true });
    if (await candidate.count()) {
      await candidate.first().click({ timeout: 5_000 }).catch(() => {});
      break;
    }
  }

  const storedValues = await page.evaluate(() => {
    const values = [];
    for (const storage of [window.localStorage, window.sessionStorage]) {
      for (let index = 0; index < storage.length; index += 1) {
        const key = storage.key(index);
        values.push(storage.getItem(key));
      }
    }
    return values.filter(Boolean);
  }).catch(() => []);
  for (const value of storedValues) {
    const match = String(value).match(/Bearer\s+[A-Za-z0-9._~+\/-]+/i);
    if (match) authorization = match[0];
  }

  const headers = {
    Referer: datasetUrl,
    'User-Agent': 'Sales-Sentinel-Academic/1.0',
    ...(authorization ? { Authorization: authorization } : {}),
  };

  for (const url of [...candidateUrls]) {
    if (!url.startsWith('http')) continue;
    try {
      const response = await context.request.get(url, { headers, timeout: 60_000 });
      console.log(`Candidate ${response.status()} ${url}`);
      await saveApiResponse(response, url);
      if (await fs.stat(outputFile).then(() => true).catch(() => false)) break;
    } catch (error) {
      console.log(`Candidate failed ${url}: ${error.message}`);
    }
  }

  if (!(await fs.stat(outputFile).then(() => true).catch(() => false))) {
    const buttons = [
      page.getByRole('button', { name: /download all/i }),
      page.getByRole('link', { name: /download all/i }),
      page.getByText(/download all/i, { exact: true }),
    ];
    let trigger = null;
    for (const candidate of buttons) {
      if (await candidate.count()) {
        trigger = candidate.first();
        break;
      }
    }
    if (!trigger) throw new Error('The public Mendeley page did not expose a Download All control.');

    const href = await trigger.getAttribute('href').catch(() => null);
    if (href) candidateUrls.add(new URL(href, page.url()).toString());

    const downloadPromise = page.waitForEvent('download', { timeout: 30_000 }).catch(() => null);
    const popupPromise = page.waitForEvent('popup', { timeout: 30_000 }).catch(() => null);
    await trigger.click();
    const download = await downloadPromise;
    if (download) {
      await download.saveAs(outputFile);
      console.log(`Saved ${outputFile} from browser download`);
    } else {
      const popup = await popupPromise;
      if (popup) {
        await popup.waitForLoadState('domcontentloaded', { timeout: 30_000 }).catch(() => {});
        candidateUrls.add(popup.url());
      }
      candidateUrls.add(page.url());
      for (const url of [...candidateUrls].reverse()) {
        try {
          const response = await context.request.get(url, { headers, timeout: 60_000 });
          console.log(`Post-click candidate ${response.status()} ${url}`);
          if (await saveApiResponse(response, url)) break;
        } catch {}
      }
    }
  }

  const stat = await fs.stat(outputFile).catch(() => null);
  if (!stat || stat.size < 1000) throw new Error('Unable to retrieve the public Redsea dataset archive.');
} finally {
  await browser.close();
}
