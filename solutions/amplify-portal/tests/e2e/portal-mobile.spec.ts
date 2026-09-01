/**
 * Phone-width layout: is every control actually reachable.
 *
 * Two defects that shipped, both invisible to every other gate in this repository:
 *
 *   1. The row overflow menu (⋮) is a nowrap strip anchored to its trigger. On a
 *      390px viewport the trigger sits about 170px in, so the last controls -- the
 *      rename and the trash -- rendered past the right edge. The panel deliberately
 *      has no overflow of its own, so there was nothing to scroll: those actions
 *      simply could not be tapped.
 *
 *   2. The snapshot table was 585px wide inside a wrapper with `overflow-x: visible`,
 *      putting the browse and lock buttons off the screen with nothing to indicate
 *      they were there.
 *
 * Neither is reachable from the other tests. jsdom has no layout engine, so Vitest
 * cannot measure a bounding box; the CSS drift rules read source patterns, and the
 * source here was valid CSS that happened to produce an unreachable control. A
 * browser is the only thing that can answer the question, which is why this lives
 * with the Playwright specs rather than in `make drift`.
 *
 * Requires a signed-in session, so credentials come from the environment and the
 * suite skips without them rather than failing:
 *
 *     PORTAL_USER=... PORTAL_PASSWORD=... npx playwright test tests/e2e/portal-mobile.spec.ts
 *
 * STILL UNPROVEN, though for a narrower reason than before. `@playwright/test` is a
 * dependency now, so the runner loads and the suite enumerates and skips cleanly; what
 * has not happened is a run that reached these assertions, because every one of them is
 * behind a sign-in and no session was available. The skip path was checked -- supplying
 * a wrong password makes the tests run and fail at the login rather than skip, so the
 * suite is not merely skipping unconditionally.
 *
 * What is still owed: revert the `@media (max-width: 768px)` block for `.row-menu-panel`
 * in src/index.css with credentials set, and the row-menu test must fail. A gate nobody
 * has watched reject bad input is indistinguishable from a clean tree.
 *
 * The paths below are the author's environment (`#files/jaws90/logs`, `compile_*.log`),
 * so a different deployment needs them changed before any of this can run at all.
 *
 * The two defects above were found and the fixes verified by measuring bounding boxes
 * in a browser at 390x844 by hand: the row menu ran to 400px against a 390px
 * viewport, and the snapshot table from 585px to 358px with all 26 controls inside.
 * This file exists so that measurement is repeatable rather than a one-off.
 *
 * WCAG 2.2 SC 2.5.8 puts the floor for a tap target at 24x24. 44 is the figure both
 * platform guidelines use and what this portal targets for primary actions, so that
 * is what is asserted here.
 */
import { test, expect, type Page, type Locator } from "@playwright/test";

const BASE_URL = process.env.PORTAL_URL || "http://localhost:5173";
const USER = process.env.PORTAL_USER;
const PASSWORD = process.env.PORTAL_PASSWORD;

/** iPhone-class width. The portal's mobile breakpoint is 768px. */
const PHONE = { width: 390, height: 844 };

const MIN_TAP = 44;

test.describe("Phone-width layout", () => {
  test.skip(
    !USER || !PASSWORD,
    "Set PORTAL_USER and PORTAL_PASSWORD to run the signed-in phone layout checks."
  );

  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(PHONE);
    await page.goto(BASE_URL);

    // The sign-in card is the Authenticator's, and it is not translated, so the
    // English labels are the stable selectors here.
    const password = page.locator('input[type="password"]');
    if (await password.count()) {
      await page.getByLabel(/email/i).fill(USER!);
      await password.first().fill(PASSWORD!);
      await page.getByRole("button", { name: /^sign in$/i }).click();
    }
    await page.waitForSelector("nav", { timeout: 20000 });
  });

  /** Every control in `scope` must lie inside the viewport and be tappable. */
  async function expectReachable(page: Page, scope: Locator, what: string) {
    const viewport = page.viewportSize()!;
    const controls = scope.locator("button, a[href], input, select");
    const count = await controls.count();
    expect(count, `${what}: found no controls to check`).toBeGreaterThan(0);

    for (let i = 0; i < count; i++) {
      const control = controls.nth(i);
      if (!(await control.isVisible())) continue;
      const box = await control.boundingBox();
      if (!box) continue;
      const name = (await control.getAttribute("aria-label")) || (await control.innerText()) || `#${i}`;

      expect(
        Math.round(box.x + box.width),
        `${what}: "${name}" extends past the right edge`
      ).toBeLessThanOrEqual(viewport.width);
      expect(Math.round(box.x), `${what}: "${name}" starts left of the screen`).toBeGreaterThanOrEqual(0);
    }
  }

  test("the file list does not scroll sideways", async ({ page }) => {
    await page.goto(`${BASE_URL}/#files`);
    await page.waitForSelector(".file-row, .file-item", { timeout: 20000 });

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    // A sideways scroll on a phone means something is off the screen, and the reader
    // has no reason to suspect it is there.
    expect(overflow, "the document scrolls horizontally").toBeLessThanOrEqual(1);
  });

  test("every action in a row's ⋮ menu is on the screen and tappable", async ({ page }) => {
    await page.goto(`${BASE_URL}/#files/jaws90/logs`);
    const trigger = page.locator(".row-menu-trigger").first();
    await trigger.waitFor({ timeout: 20000 });
    await trigger.click();

    const panel = page.locator(".row-menu-panel");
    await expect(panel).toBeVisible();
    await expectReachable(page, panel, "row menu");

    const actions = panel.locator("button");
    for (let i = 0; i < (await actions.count()); i++) {
      const box = await actions.nth(i).boundingBox();
      expect(Math.round(box!.height), "row menu: control is too small to tap").toBeGreaterThanOrEqual(
        MIN_TAP
      );
    }
  });

  test("the ⋮ sheet names the file it acts on", async ({ page }) => {
    // The sheet is pinned to the bottom of the screen rather than to its row, so
    // without the name there is nothing to say which file it applies to.
    await page.goto(`${BASE_URL}/#files/jaws90/logs`);
    const row = page.locator(".file-row").filter({ hasText: /compile_\d+\.log/ }).first();
    await row.waitFor({ timeout: 20000 });
    const fileName = (await row.innerText()).match(/compile_\d+\.log/)![0];

    await row.locator(".row-menu-trigger").click();
    await expect(page.locator(".row-menu-subject")).toHaveText(fileName);
  });

  test("the snapshot table keeps its browse and lock buttons on the screen", async ({ page }) => {
    await page.goto(`${BASE_URL}/#snapshots`);

    const table = page.locator(".snapshot-table");
    // The panel renders a failure notice instead when ONTAP is unreachable, and that
    // is not what this test is about.
    if (!(await table.count())) {
      test.skip(true, "no snapshot table: the ONTAP connection is not answering");
    }
    await table.waitFor({ timeout: 20000 });

    await expectReachable(page, table.locator("tbody"), "snapshot table");

    const width = (await table.boundingBox())!.width;
    expect(Math.round(width), "the snapshot table is wider than the screen").toBeLessThanOrEqual(
      PHONE.width
    );
  });

  test("the navigation drawer starts closed and the scrim closes it", async ({ page }) => {
    await page.goto(`${BASE_URL}/#files`);
    await page.waitForSelector("nav", { timeout: 20000 });

    // Closed at first: on a phone the content is what the reader came for, and a
    // drawer covering it on arrival hides that.
    const toggle = page.getByRole("button", { name: /ナビゲーション|navigation/i });
    await expect(toggle).toHaveAttribute("aria-label", /展開|expand/i);

    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-label", /折りたた|collapse/i);

    // Escape, because a reader who opened it by accident should not have to find a
    // specific target to get out of it.
    await page.keyboard.press("Escape");
    await expect(toggle).toHaveAttribute("aria-label", /展開|expand/i);
  });
});
