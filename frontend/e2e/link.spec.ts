import { test, expect } from '@playwright/test';

test.describe('Link Ingestion Flow', () => {
  test('should accept a URL and process it', async ({ page }) => {
    // Navigate to upload page
    await page.goto('/upload');
    await expect(page.getByText('Upload Document')).toBeVisible();

    // Fill in a link
    const input = page.getByPlaceholder(/https:\/\/github.com/);
    await input.fill('https://github.com/microsoft/playwright');

    // Mock the link ingest API
    await page.route('**/api/ingest/link*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          job_id: 'mock-job-123',
          status: 'completed',
          filename: 'https://github.com/microsoft/playwright',
          entities_extracted: 2,
          entities: [
            { id: '1', category: 'project', title: 'Playwright', data: {}, importance_score: 9, tags: [] },
            { id: '2', category: 'skill', title: 'TypeScript', data: {}, importance_score: 8, tags: [] },
          ],
        }),
      });
    });

    // Mock status endpoint if it polls
    await page.route('**/api/ingest/status/*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          job_id: 'mock-job-123',
          status: 'completed',
          progress: 'Done'
        }),
      });
    });

    // Mock profile fetch
    await page.route('**/api/identity/*', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          user_id: 'default',
          name: 'Demo User',
          summary: 'A user with skills',
          top_skills: ['TypeScript'],
          total_entities: 2
        })
      });
    });

    // Click submit
    await page.getByRole('button', { name: 'Process Link' }).click();

    // Verify loading state
    await expect(page.getByText('Processing with AI…')).toBeVisible();

    // Verify completion
    await expect(page.getByText('Extraction Complete')).toBeVisible();
    await expect(page.getByText('2', { exact: true })).toBeVisible(); // 2 entities
  });
});
