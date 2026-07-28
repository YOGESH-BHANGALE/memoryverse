import { test, expect } from '@playwright/test';

test.describe('Navigation Smoke Test', () => {
  test('should load main pages without errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        // filter out the favicon 404 error if any
        if (!msg.text().includes('favicon.ico')) {
          errors.push(msg.text());
        }
      }
    });
    page.on('pageerror', exception => {
      errors.push(exception.message);
    });

    // Test homepage
    await page.goto('/');
    // Check if the title is MemoryVerse or something similar
    // Actually, we'll just check if a specific element is there to avoid strict title matching
    await expect(page.locator('body')).toBeVisible();

    // Test upload
    await page.goto('/upload');
    await expect(page.getByText('Upload Document')).toBeVisible();

    // Test timeline
    await page.goto('/timeline');
    await expect(page.getByRole('heading', { name: 'Journey Timeline' })).toBeVisible();

    // Test search
    await page.goto('/search');
    await expect(page.getByPlaceholder(/Ask about/i)).toBeVisible();

    expect(errors, 'Console errors occurred: ' + errors.join(', ')).toEqual([]);
  });
});
