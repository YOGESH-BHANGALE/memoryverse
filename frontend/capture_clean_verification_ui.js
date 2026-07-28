const { chromium } = require("@playwright/test");
const path = require("path");

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext();

  await ctx.addCookies([{
    name: "memoryverse_user_id",
    value: "default",
    domain: "localhost",
    path: "/"
  }]);

  const page = await ctx.newPage();
  await page.setViewportSize({ width: 1280, height: 800 });

  await page.goto("http://localhost:3000/search");
  await page.waitForTimeout(2000);
  await page.evaluate(() => {
    localStorage.setItem("memoryverse_user_id", "default");
  });

  console.log("=== CAPTURING SEARCH QUERY UI SCREENSHOTS ===");

  const searchQueries = [
    { q: "Show all my certificates", file: "search_query_1_certificates.png" },
    { q: "Show my internship documents", file: "search_query_2_internships.png" },
    { q: "Show my latest resume", file: "search_query_3_resume.png" },
    { q: "Show my AI projects", file: "search_query_4_ai_projects.png" }
  ];

  for (const item of searchQueries) {
    console.log(`Searching for: "${item.q}"...`);
    await page.goto("http://localhost:3000/search");
    await page.waitForTimeout(2000);

    const searchInput = page.locator('form textarea, form input').first();
    await searchInput.waitFor({ state: "visible", timeout: 5000 });
    await searchInput.fill(item.q);
    await page.waitForTimeout(500);

    const submitBtn = page.locator('form button[type="submit"]').first();
    await submitBtn.click();
    await page.waitForTimeout(9000);

    await page.screenshot({ path: path.join(__dirname, `../docs/assets/${item.file}`) });
    console.log(`Saved screenshot: docs/assets/${item.file}`);
  }

  console.log("\n=== CAPTURING PROJECT REPORT EXTRACTION UI ===");
  await page.goto("http://localhost:3000/upload");
  await page.waitForTimeout(2000);
  const fileInputProj = page.locator('input[type="file"]');
  await fileInputProj.setInputFiles(path.join(__dirname, "../backend/Distributed_Stream_Processor_Project_Report.txt"));
  await page.waitForTimeout(1000);
  const submitProj = page.locator('button:has-text("Process Document")');
  if (await submitProj.isVisible()) await submitProj.click();
  await page.waitForTimeout(12000);
  await page.screenshot({ path: path.join(__dirname, "../docs/assets/project_report_extraction_result.png") });
  console.log("Saved docs/assets/project_report_extraction_result.png");

  console.log("\n=== CAPTURING ACADEMICS EXTRACTION UI ===");
  await page.goto("http://localhost:3000/upload");
  await page.waitForTimeout(2000);
  const fileInputAcad = page.locator('input[type="file"]');
  await fileInputAcad.setInputFiles(path.join(__dirname, "../backend/Academic_Degree_Transcript_XYZ_University.txt"));
  await page.waitForTimeout(1000);
  const submitAcad = page.locator('button:has-text("Process Document")');
  if (await submitAcad.isVisible()) await submitAcad.click();
  await page.waitForTimeout(12000);
  await page.screenshot({ path: path.join(__dirname, "../docs/assets/academics_extraction_result.png") });
  console.log("Saved docs/assets/academics_extraction_result.png");

  await browser.close();
  console.log("=== ALL UI SCREENSHOTS CAPTURED CLEANLY ===");
})();
