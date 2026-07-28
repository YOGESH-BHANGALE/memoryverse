const { chromium } = require("@playwright/test");
const path = require("path");

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext();

  // Set user_id cookie to "default" so search queries run against seeded knowledge base
  await ctx.addCookies([{
    name: "memoryverse_user_id",
    value: "default",
    domain: "localhost",
    path: "/"
  }]);

  const page = await ctx.newPage();

  console.log("==================================================");
  console.log("TASK 1: Module 5 Example Search Queries Test");
  console.log("==================================================");

  await page.goto("http://localhost:3000/search");
  await page.waitForTimeout(2000);

  const runSearch = async (queryText, screenshotName) => {
    console.log(`Running search query: "${queryText}"...`);
    await page.goto("http://localhost:3000/search");
    await page.waitForTimeout(2000);

    const textarea = page.locator('textarea, input[type="text"]').first();
    await textarea.click();
    await textarea.fill(queryText);
    await page.waitForTimeout(500);

    // Click submit button
    const submitBtn = page.locator('button[type="submit"]').first();
    await submitBtn.click();

    // Wait 10s for SSE stream to complete
    await page.waitForTimeout(10000);

    const outPath = path.join(__dirname, `../docs/assets/${screenshotName}`);
    await page.screenshot({ path: outPath, fullPage: true });
    console.log(`Saved screenshot: docs/assets/${screenshotName}`);
  };

  // 1. "Show all my certificates"
  await runSearch("Show all my certificates", "search_query_1_certificates.png");

  // 2. "Show my internship documents"
  await runSearch("Show my internship documents", "search_query_2_internships.png");

  // 3. "Show my latest resume"
  await runSearch("Show my latest resume", "search_query_3_resume.png");

  // 4. "Show my AI projects"
  await runSearch("Show my AI projects", "search_query_4_ai_projects.png");


  console.log("\n==================================================");
  console.log("TASK 2: Project Report Ingestion Test");
  console.log("==================================================");

  await page.goto("http://localhost:3000/upload");
  await page.waitForTimeout(2000);

  const fileInputProj = page.locator('input[type="file"]');
  await fileInputProj.setInputFiles(path.join(__dirname, "../backend/Distributed_Stream_Processor_Project_Report.txt"));
  await page.waitForTimeout(1000);

  const submitProj = page.locator('button:has-text("Process Document")');
  if (await submitProj.isVisible()) await submitProj.click();
  await page.waitForTimeout(12000);

  await page.screenshot({ path: path.join(__dirname, "../docs/assets/project_report_extraction_result.png"), fullPage: true });
  console.log("Saved docs/assets/project_report_extraction_result.png");


  console.log("\n==================================================");
  console.log("TASK 3: Academics Category Ingestion Test");
  console.log("==================================================");

  await page.goto("http://localhost:3000/upload");
  await page.waitForTimeout(2000);

  const fileInputAcad = page.locator('input[type="file"]');
  await fileInputAcad.setInputFiles(path.join(__dirname, "../backend/Academic_Degree_Transcript_XYZ_University.txt"));
  await page.waitForTimeout(1000);

  const submitAcad = page.locator('button:has-text("Process Document")');
  if (await submitAcad.isVisible()) await submitAcad.click();
  await page.waitForTimeout(12000);

  await page.screenshot({ path: path.join(__dirname, "../docs/assets/academics_extraction_result.png"), fullPage: true });
  console.log("Saved docs/assets/academics_extraction_result.png");

  await browser.close();
  console.log("\n==================================================");
  console.log("ALL FOUR VERIFICATION CHECKS COMPLETED");
  console.log("==================================================");
})();
