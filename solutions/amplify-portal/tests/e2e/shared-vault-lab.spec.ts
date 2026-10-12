// Real-environment run: recorded [V1][V2][V3][V4][V5][V6][V7]; not recorded [E13] (status source: docs/verification-record.md)
/**
 * Shared-vault lab: what the portal shows for a vault shared by another account.
 *
 * Started by infrastructure/shared-backup-vault-lab/scripts/07_portal_config.sh --ui, which
 * sets LAB_UI_EXPECT to one of the three states below and passes the sign-in credentials.
 * The spec is not part of the normal e2e run: with LAB_UI_EXPECT unset it registers no test
 * at all, so `npx playwright test` in the e2e workflow (which sets CI) neither signs in nor
 * fails on this file. Any other non-empty value throws when the file is loaded.
 *
 *   arn-missing  the vault ARN is not in the portal role's policy: the shared vault is
 *                offered, its recovery points are denied (rpAccessDeniedHint)
 *   arn-present  the ARN is in the policy: the rows show the air-gapped chip and the owner
 *                account, and the Restore dialog opens with its confirm button disabled
 *   revoked      the share was revoked: the shared group no longer offers the vault
 *
 * Environment: PORTAL_URL (default http://localhost:5173), PORTAL_USER, PORTAL_PASSWORD
 * (a user in the storage-admin group), LAB_LAG_VAULT_NAME, LAB_OWNER_ACCOUNT_ID, and the
 * optional LAB_SECOND_REGION and LAB_CAPTURE_DIR. A missing value FAILS the test: a check
 * that did not run must not look like a check that passed.
 *
 * The spec never starts a restore. It does not click the confirm button of the restore
 * dialog; starting a job costs money and belongs to 08_restore.sh.
 *
 * Not yet run in a browser against a real portal. The status line above refers to the record
 * of the lab: infrastructure/shared-backup-vault-lab/docs/verification-record.md.
 */
import { test, expect, type Page } from "@playwright/test";
import * as fs from "node:fs";
import * as path from "node:path";
import { en } from "../../src/i18n/locales/en";

const VALID_EXPECT = ["arn-missing", "arn-present", "revoked"] as const;
type Expectation = (typeof VALID_EXPECT)[number];

function readExpectation(raw: string | undefined): Expectation | null {
  const value = raw ?? "";
  if (value === "") return null;
  if (!(VALID_EXPECT as readonly string[]).includes(value)) {
    throw new Error(
      `LAB_UI_EXPECT must be one of ${VALID_EXPECT.join(", ")} or unset (got "${value}")`
    );
  }
  return value as Expectation;
}

const EXPECT = readExpectation(process.env.LAB_UI_EXPECT);

const BASE_URL = process.env.PORTAL_URL || "http://localhost:5173";
const USER = process.env.PORTAL_USER ?? "";
const PASSWORD = process.env.PORTAL_PASSWORD ?? "";
const LAG_VAULT = process.env.LAB_LAG_VAULT_NAME ?? "";
const OWNER_ACCOUNT = process.env.LAB_OWNER_ACCOUNT_ID ?? "";
const SECOND_REGION = process.env.LAB_SECOND_REGION ?? "";
const CAPTURE_DIR = process.env.LAB_CAPTURE_DIR ?? "";
const WAIT = 60_000;

/** Replace the owner account id in the page text with a dummy just before a capture. */
const DUMMY_ACCOUNT = "111122223333";

async function capture(page: Page, name: string): Promise<void> {
  if (!CAPTURE_DIR) return;
  fs.mkdirSync(CAPTURE_DIR, { recursive: true });
  // One evaluate() just before the screenshot (no addInitScript): the values on screen are
  // replaced once, in the state that is about to be captured.
  await page.evaluate(
    ({ owner, dummy }) => {
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (node.nodeValue && node.nodeValue.includes(owner)) {
          node.nodeValue = node.nodeValue.split(owner).join(dummy);
        }
      }
      for (const option of Array.from(document.querySelectorAll("option"))) {
        if (option.textContent && option.textContent.includes(owner)) {
          option.textContent = option.textContent.split(owner).join(dummy);
        }
      }
    },
    { owner: OWNER_ACCOUNT, dummy: DUMMY_ACCOUNT }
  );
  await page.screenshot({ path: path.join(CAPTURE_DIR, `${name}.png`), fullPage: true });
}

async function signIn(page: Page): Promise<void> {
  // Suppress the first-run welcome modal before the app loads. Its overlay covers the whole
  // viewport and intercepts pointer events, so a later Restore click would be blocked. The
  // app only shows it when this localStorage flag is absent (see components/WelcomeModal.tsx).
  await page.addInitScript(() => {
    try {
      window.localStorage.setItem("portal-welcome-dismissed", "true");
    } catch {
      /* localStorage unavailable: the test will surface the overlay instead */
    }
  });
  await page.goto(BASE_URL);
  // Either the portal's navigation (a session was restored) or the sign-in form.
  const landing = page.locator('nav, input[type="password"]').first();
  await landing.waitFor({ timeout: WAIT });
  const password = page.locator('input[type="password"]');
  if (await password.count()) {
    await page.getByLabel(/email/i).fill(USER);
    await password.first().fill(PASSWORD);
    await page.getByRole("button", { name: /^sign in$/i }).click();
  }
  await page.waitForSelector("nav", { timeout: WAIT });
}

async function openRecoveryPoints(page: Page): Promise<void> {
  await signIn(page);
  await page.goto(`${BASE_URL}/#recovery`);
  await expect(page.getByText(en.rpTitle).first(), "the recovery points panel did not open").toBeVisible({
    timeout: WAIT,
  });
  await expect(page.locator("#rp-vault-scope"), "the vault selector is missing").toBeVisible({ timeout: WAIT });
}

/** The option of the shared group that names the lab vault. */
function sharedVaultOption(page: Page) {
  return page
    .locator(`#rp-vault-scope optgroup[label="${en.rpScopeSharedGroup}"] option`)
    .filter({ hasText: LAG_VAULT });
}

async function selectSharedVault(page: Page): Promise<void> {
  const option = sharedVaultOption(page);
  await expect(
    option,
    `the shared group of the vault selector has no vault named ${LAG_VAULT}: is the share accepted (05_accept_share.sh) and listed?`
  ).toHaveCount(1, { timeout: WAIT });
  const value = await option.getAttribute("value");
  expect(value, "the shared vault option has no value").toBeTruthy();
  await page.locator("#rp-vault-scope").selectOption(value as string);
}

if (EXPECT !== null) {
  test.describe(`shared vault lab: ${EXPECT}`, () => {
    test.use({ locale: "en-US" });
    test.setTimeout(180_000);

    test.beforeEach(() => {
      expect(USER && PASSWORD, "PORTAL_USER and PORTAL_PASSWORD are not set: nothing was checked").toBeTruthy();
      expect(LAG_VAULT, "LAB_LAG_VAULT_NAME is not set: nothing was checked").toBeTruthy();
      expect(OWNER_ACCOUNT, "LAB_OWNER_ACCOUNT_ID is not set: nothing was checked").toBeTruthy();
    });

    if (EXPECT === "arn-missing") {
      test("the shared vault is offered and its recovery points are denied", async ({ page }) => {
        await openRecoveryPoints(page);
        if (SECOND_REGION) {
          await expect
            .poll(async () => page.locator("#rp-region option").count(), {
              message: `the Region selector should offer at least two Regions (home and ${SECOND_REGION})`,
              timeout: WAIT,
            })
            .toBeGreaterThanOrEqual(2);
        } else {
          await expect(page.locator("#rp-region"), "LAB_SECOND_REGION is unset: no Region selector expected").toHaveCount(0);
        }
        await selectSharedVault(page);
        await expect(
          page.getByText(en.rpAccessDeniedHint, { exact: true }),
          "expected the access-denied hint for a shared vault whose ARN is not in the role policy"
        ).toBeVisible({ timeout: WAIT });
        await capture(page, "P01-arn-missing");
      });
    }

    if (EXPECT === "arn-present") {
      test("the shared vault rows show the air-gapped chip and the owner account", async ({ page }) => {
        await openRecoveryPoints(page);
        await selectSharedVault(page);
        await expect(page.getByText(en.rpVaultAirgapped).first(), "no air-gapped chip on a recovery point row").toBeVisible({
          timeout: WAIT,
        });
        await expect(
          page.getByText(`${en.rpVaultOwner}: ${OWNER_ACCOUNT}`).first(),
          "no owner account on a recovery point row"
        ).toBeVisible({ timeout: WAIT });
        await capture(page, "P02-arn-present");
      });

      test("the Restore dialog opens with its confirm button disabled and closes without a restore", async ({ page }) => {
        await openRecoveryPoints(page);
        await selectSharedVault(page);
        // Required, never a conditional skip: without this button the restore dialog was not
        // checked at all. It appears only for a user in the storage-admin group.
        const restore = page.getByRole("button", { name: en.rpRestore, exact: true }).first();
        await expect(
          restore,
          "no Restore button: PORTAL_USER is probably not in the storage-admin group. " +
            "Run `make portal-demo-user ARGS='--username <user> --groups storage-admin,internal'` again (granting groups is idempotent)"
        ).toBeVisible({ timeout: WAIT });
        await restore.click();
        const dialog = page.getByRole("dialog");
        await expect(dialog.getByText(en.rpRestoreTitle), "the restore dialog did not open").toBeVisible({ timeout: WAIT });
        const startButton = dialog.getByRole("button", { name: en.rpRestoreConfirm });
        await expect(startButton, "the start button must be disabled before the acknowledgement").toBeDisabled();
        await capture(page, "P03-restore-dialog");
        await dialog.getByRole("button", { name: en.rpRestoreCancel }).click();
        await expect(dialog, "the dialog should close on cancel").toHaveCount(0, { timeout: WAIT });
      });
    }

    if (EXPECT === "revoked") {
      test("the shared vault is no longer offered", async ({ page }) => {
        await openRecoveryPoints(page);
        // The shared list must have been answered before its absence means anything: either
        // the group exists (other vaults) or the empty notice is shown.
        const group = page.locator(`#rp-vault-scope optgroup[label="${en.rpScopeSharedGroup}"]`);
        const empty = page.getByText(en.rpNoSharedVaults);
        await expect
          .poll(async () => (await group.count()) + (await empty.count()), {
            message: "the list of shared vaults was not answered (neither a group nor the empty notice appeared)",
            timeout: WAIT,
          })
          .toBeGreaterThan(0);
        await expect(
          sharedVaultOption(page),
          `the shared group still offers ${LAG_VAULT}: the share may not be revoked yet, or the portal still lists it`
        ).toHaveCount(0);
        await capture(page, "P04-revoked");
      });
    }
  });
}
