import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const datasetUrl = 'https://data.mendeley.com/datasets/9c87bd42ct/1';
const outputDir = path.resolve('data/raw');
await fs.mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ acceptDownloads: true });
const page = await context.newPage();
page.setDefaultTimeout(45_000);

try {
  await page.goto(datasetUrl, { waitUntil: 'domcontentloaded', timeout: 90_000 });

  for (const label of ['Accept all cookies', 'Accept All Cookies', 'Accept', 'I agree']) {
    const candidate = page.getByRole('button', { name: label, exact: true });
    if (await candidate.count()) {
      await candidate.first().click({ timeout: 5_000 }).catch(() => {});
      break;
    }
  }

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
  if (!trigger) {
    throw new Error('The public Mendeley page did not expose a Download All control.');
  }

  const downloadPromise = page.waitForEvent('download', { timeout: 90_000 });
  await trigger.click();
  const download = await downloadPromise;
  const suggested = download.suggestedFilename() || 'Redsea-Dataset.zip';
  const target = path.join(outputDir, suggested.toLowerCase().endsWith('.zip') ? 'Redsea-Dataset.zip' : suggested);
  await download.saveAs(target);
  console.log(`Saved ${target}`);
} finally {
  await browser.close();
}
