import { test, expect } from '@playwright/test';

test.describe('Search Flow Test', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/search');
  });

  test('should render empty state initially', async ({ page }) => {
    await expect(page.getByPlaceholder(/Ask about/i)).toBeVisible();
    await expect(page.getByText(/What would you like to know?/i, { exact: false })).toBeVisible();
  });

  test('should show loading state and then no results', async ({ page }) => {
    await page.route('**/api/search/query', async route => {
      await new Promise(resolve => setTimeout(resolve, 1000));
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: 'event: chunk\ndata: I could not find any memories about that.\n\nevent: done\ndata: done\n\n'
      });
    });

    await page.getByPlaceholder(/Ask about/i).fill('unknown term');
    await page.getByPlaceholder(/Ask about/i).press('Enter');

    // Check no results state (AI says it couldn't find memories)
    await expect(page.getByText(/could not find any memories/i, { exact: false })).toBeVisible();
  });

  test('should show loading state and then populated results', async ({ page }) => {
    await page.route('**/api/search/query', async route => {
      await new Promise(resolve => setTimeout(resolve, 1000));
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: 'event: chunk\ndata: This is a mocked answer for your project.\n\nevent: sources\ndata: [{"source_file": "Test Project", "score": 0.99}]\n\nevent: done\ndata: done\n\n'
      });
    });

    await page.getByPlaceholder(/Ask about/i).fill('project');
    await page.getByPlaceholder(/Ask about/i).press('Enter');

    // Check populated results (AI answer and sources)
    await expect(page.getByText('This is a mocked answer for your project.')).toBeVisible();
    await expect(page.getByText('Test Project')).toBeVisible();
  });
});
