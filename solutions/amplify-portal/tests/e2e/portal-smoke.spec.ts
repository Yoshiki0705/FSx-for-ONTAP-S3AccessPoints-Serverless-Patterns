/**
 * Portal Smoke Tests — E2E with Playwright
 *
 * Validates core UI rendering against a deployed backend.
 *
 * Every assertion here is on the far side of sign-in. `App` is wrapped in
 * `<Authenticator>` in `src/main.tsx`, so `nav` does not exist until a session does --
 * these tests used to open the page and wait for it, and the header claimed the auth
 * was "bypassed in test mode via amplify_outputs.json". No such mechanism exists. Run
 * without credentials, all six failed on the same 10s timeout while the page sat on
 * the sign-in form, which is the correct behaviour of a portal that requires a login.
 *
 * So credentials come from the environment and the suite skips without them, matching
 * `portal-mobile.spec.ts`. A skip says "not checked"; a timeout said "broken", and the
 * portal was not.
 *
 *     PORTAL_URL=https://... PORTAL_USER=... PORTAL_PASSWORD=... npm run e2e
 *
 * Requires the ONTAP-facing side of the deployment to answer, or the panels report a
 * connection failure instead -- which the last two tests accept, because whether ONTAP
 * is reachable is not what they are about.
 */
import { test, expect } from "@playwright/test";

const BASE_URL = process.env.PORTAL_URL || "http://localhost:5173";
const USER = process.env.PORTAL_USER;
const PASSWORD = process.env.PORTAL_PASSWORD;

test.describe("Portal Smoke Tests", () => {
  test.skip(
    !USER || !PASSWORD,
    "Set PORTAL_USER and PORTAL_PASSWORD to run the signed-in smoke checks."
  );

  test.beforeEach(async ({ page }) => {
    await page.goto(BASE_URL);

    // The sign-in card is the Authenticator's and is not translated, so the English
    // labels are the stable selectors. Skipped when a session is already restored.
    const password = page.locator('input[type="password"]');
    if (await password.count()) {
      await page.getByLabel(/email/i).fill(USER!);
      await password.first().fill(PASSWORD!);
      await page.getByRole("button", { name: /^sign in$/i }).click();
    }
    // The portal's own navigation, which exists only inside the Authenticator.
    await page.waitForSelector("nav", { timeout: 20000 });
  });

  test("renders sidebar navigation with all sections", async ({ page }) => {
    // Check all 4 navigation groups exist
    await expect(page.getByText("ブラウズ").or(page.getByText("Browse"))).toBeVisible();
    await expect(page.getByText("AI").first()).toBeVisible();
    await expect(page.getByText("データ保護").or(page.getByText("Data Protection"))).toBeVisible();
    await expect(page.getByText("管理").or(page.getByText("Admin"))).toBeVisible();
  });

  // Scoped to `main`, because the Authenticator's own card is a tablist too -- "Sign In"
  // and "Create Account". An unscoped `[role="tab"]` counted those, so this assertion
  // would have read 2 against a page that had never left the login screen and reported
  // the Lock panel as wrong.
  test("Lock panel renders 3 tabs", async ({ page }) => {
    await page.goto(`${BASE_URL}/#lock`);
    const tabs = page.locator('main [role="tab"]');
    await tabs.first().waitFor({ timeout: 20000 });

    await expect(tabs).toHaveCount(3);
    await expect(tabs.nth(0)).toContainText("SnapLock");
    await expect(tabs.nth(1)).toContainText("S3 Object Lock");
    await expect(tabs.nth(2)).toContainText("Tamperproof");
  });

  test("Lock panel S3 Object Lock tab shows status", async ({ page }) => {
    await page.goto(`${BASE_URL}/#lock`);
    const tabs = page.locator('main [role="tab"]');
    await tabs.first().waitFor({ timeout: 20000 });

    await tabs.filter({ hasText: "S3 Object Lock" }).click();

    // Either the bucket's Object Lock state, or a notice that no bucket is configured.
    const panel = page.locator('main [role="tabpanel"]');
    await expect(panel).toContainText(/Object Lock|未設定/, { timeout: 20000 });
  });

  test("Resource Management card grid renders", async ({ page }) => {
    await page.goto(`${BASE_URL}/#resources`);

    // `toContainText` retries until the timeout, so it waits for the grid to arrive
    // rather than for a fixed three seconds and then reading whatever is there.
    await expect(page.locator("main")).toContainText(/ストレージ|Storage/, { timeout: 20000 });
  });

  // The card has to be found rather than optionally found. These two tests were written
  // as `if (await button.count() > 0) { ...assert... }`, so a renamed or missing card
  // asserted nothing and the test passed -- the failure it exists to catch was the one
  // case it ignored.
  test("SMB Shares panel loads data or shows connection error", async ({ page }) => {
    await page.goto(`${BASE_URL}/#resources`);

    const smbBtn = page.locator("button").filter({ hasText: /SMB.*共有|SMB Shares/ });
    await expect(smbBtn.first(), "no SMB Shares card in the resource grid").toBeVisible({
      timeout: 20000,
    });
    await smbBtn.first().click();

    // A share list, an empty list, or ONTAP not answering. Which one is not the subject.
    await expect(page.locator("main")).toContainText(
      /共有名|Share Name|ONTAP connection|SMB 共有がありません/,
      { timeout: 20000 }
    );
  });

  test("Export Policy panel loads data or shows connection error", async ({ page }) => {
    await page.goto(`${BASE_URL}/#resources`);

    const policyBtn = page
      .locator("button")
      .filter({ hasText: /エクスポートポリシー|Export Polic/ });
    await expect(policyBtn.first(), "no Export Policy card in the resource grid").toBeVisible({
      timeout: 20000,
    });
    await policyBtn.first().click();

    await expect(page.locator("main")).toContainText(
      /ポリシー名|Policy Name|ONTAP connection/,
      { timeout: 20000 }
    );
  });
});
