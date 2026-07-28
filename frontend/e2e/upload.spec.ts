import { test, expect } from '@playwright/test';
import path from 'path';

test.describe('Upload Flow Test', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/upload');
  });

  test('should show error for invalid file type', async ({ page }) => {
    const buffer = Buffer.from('{"test": 1}');
    
    await page.locator('input[type="file"]').setInputFiles({
      name: 'test.json',
      mimeType: 'application/json',
      buffer
    });

    await expect(page.getByText(/unsupported/i, { exact: false })).toBeVisible({ timeout: 2000 });
  });

  test('should show error for oversized file', async ({ page }) => {
    const fs = require('fs');
    const path = require('path');
    const filePath = path.join(__dirname, 'large.pdf');
    if (!fs.existsSync(filePath)) {
      fs.writeFileSync(filePath, Buffer.alloc(51 * 1024 * 1024, 'a'));
    }
    
    await page.locator('input[type="file"]').setInputFiles(filePath);

    await expect(page.getByText(/File is too large/i, { exact: false })).toBeVisible({ timeout: 2000 });
  });

  test('should show loading state and handle network error', async ({ page }) => {
    await page.route('**/api/ingest/upload*', async route => {
      await new Promise(resolve => setTimeout(resolve, 1000));
      await route.abort('failed');
    });

    const buffer = Buffer.from('dummy pdf content');
    
    await page.locator('input[type="file"]').setInputFiles({
      name: 'resume.pdf',
      mimeType: 'application/pdf',
      buffer
    });

    await expect(page.locator('.animate-spin').first()).toBeVisible();
    await expect(page.getByText(/error|failed/i, { exact: false })).toBeVisible();
  });

  test('should successfully upload a valid file', async ({ page }) => {
    await page.route('**/api/ingest/upload*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: "completed",
          message: "Success",
          entity_id: "123",
          job_id: "test-job-123",
          filename: "resume.pdf",
          entities_extracted: 2,
          entities: [
            { id: "1", title: "Python", category: "skill", importance_score: 9 },
            { id: "2", title: "React", category: "skill", importance_score: 8 }
          ]
        })
      });
    });

    const buffer = Buffer.from('dummy pdf content');
    
    await page.locator('input[type="file"]').setInputFiles({
      name: 'resume.pdf',
      mimeType: 'application/pdf',
      buffer
    });

    await expect(page.locator('.animate-spin').first()).toBeVisible();
    await expect(page.getByText(/Extraction Complete/i, { exact: false })).toBeVisible();
  });
});
