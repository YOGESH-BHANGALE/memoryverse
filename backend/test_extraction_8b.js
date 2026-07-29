const { chromium } = require('@playwright/test');
const path = require('path');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  console.log('Navigating to http://localhost:3000/upload...');
  await page.goto('http://localhost:3000/upload');

  const fileToUpload = path.resolve(__dirname, 'AWS_Certified_Solutions_Architect.txt');
  console.log('Uploading file:', fileToUpload);

  await page.locator('input[type="file"]').setInputFiles(fileToUpload);

  console.log('Waiting for extraction completion...');
  await page.waitForSelector('text="Extraction Complete"', { timeout: 30000 });

  const artifactPath = path.resolve(__dirname, 'screenshot_extraction_8b_model.png');
  await page.screenshot({ path: artifactPath, fullPage: true });
  console.log('Saved screenshot to:', artifactPath);

  await browser.close();
})();
