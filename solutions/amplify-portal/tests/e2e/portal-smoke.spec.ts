/**
 * Portal Smoke Tests — E2E with Playwright
 *
 * Validates core UI rendering after deployment.
 * Requires: npm run dev (localhost:5173) + deployed sandbox backend.
 *
 * Run: npx playwright test tests/e2e/
 * CI:  .github/workflows/e2e-portal.yml (manual trigger, requires sandbox)
 */
import { test, expect } from "@playwright/test";

const BASE_URL = process.env.PORTAL_URL || "http://localhost:5173";

test.describe("Portal Smoke Tests", () => {
  test.beforeEach(async ({ page }) => {
    // Portal uses Cognito auth — in test mode we bypass via amplify_outputs.json
    // For CI, set PORTAL_URL to a deployed Amplify Hosting URL with test user
    await page.goto(BASE_URL);
    // Wait for app to load (sidebar navigation appears)
    await page.waitForSelector("nav", { timeout: 10000 });
  });

  test("renders sidebar navigation with all sections", async ({ page }) => {
    // Check all 4 navigation groups exist
    await expect(page.getByText("ブラウズ").or(page.getByText("Browse"))).toBeVisible();
    await expect(page.getByText("AI").first()).toBeVisible();
    await expect(page.getByText("データ保護").or(page.getByText("Data Protection"))).toBeVisible();
    await expect(page.getByText("管理").or(page.getByText("Admin"))).toBeVisible();
  });

  test("Lock panel renders 3 tabs", async ({ page }) => {
    await page.goto(`${BASE_URL}/#lock`);
    await page.waitForSelector('[role="tablist"]', { timeout: 10000 });

    const tabs = page.locator('[role="tab"]');
    await expect(tabs).toHaveCount(3);
    await expect(tabs.nth(0)).toContainText("SnapLock");
    await expect(tabs.nth(1)).toContainText("S3 Object Lock");
    await expect(tabs.nth(2)).toContainText("Tamperproof");
  });

  test("Lock panel S3 Object Lock tab shows status", async ({ page }) => {
    await page.goto(`${BASE_URL}/#lock`);
    await page.waitForSelector('[role="tablist"]', { timeout: 10000 });

    // Click S3 Object Lock tab
    await page.locator('[role="tab"]').filter({ hasText: "S3 Object Lock" }).click();
    await page.waitForTimeout(3000);

    // Should show either "有効" (enabled) or "未設定" (not configured)
    const panel = page.locator('[role="tabpanel"]');
    const text = await panel.textContent();
    expect(text?.includes("Object Lock") || text?.includes("未設定")).toBeTruthy();
  });

  test("Resource Management card grid renders", async ({ page }) => {
    await page.goto(`${BASE_URL}/#resources`);
    await page.waitForTimeout(3000);

    // Should show category headings
    const main = page.locator("main");
    const text = await main.textContent();
    expect(
      text?.includes("ストレージ") || text?.includes("Storage")
    ).toBeTruthy();
  });

  test("SMB Shares panel loads data or shows connection error", async ({ page }) => {
    await page.goto(`${BASE_URL}/#resources`);
    await page.waitForTimeout(2000);

    // Click SMB Shares card
    const smbBtn = page.locator("button").filter({ hasText: /SMB.*共有|SMB Shares/ });
    if (await smbBtn.count() > 0) {
      await smbBtn.first().click();
      await page.waitForTimeout(3000);

      const main = page.locator("main");
      const text = await main.textContent();
      // Either shows share list OR "ONTAP connection not configured"
      expect(
        text?.includes("共有名") ||
        text?.includes("Share Name") ||
        text?.includes("ONTAP connection") ||
        text?.includes("SMB 共有がありません")
      ).toBeTruthy();
    }
  });

  test("Export Policy panel loads data or shows connection error", async ({ page }) => {
    await page.goto(`${BASE_URL}/#resources`);
    await page.waitForTimeout(2000);

    const policyBtn = page.locator("button").filter({ hasText: /エクスポートポリシー|Export Polic/ });
    if (await policyBtn.count() > 0) {
      await policyBtn.first().click();
      await page.waitForTimeout(3000);

      const main = page.locator("main");
      const text = await main.textContent();
      expect(
        text?.includes("ポリシー名") ||
        text?.includes("Policy Name") ||
        text?.includes("ONTAP connection")
      ).toBeTruthy();
    }
  });
});
