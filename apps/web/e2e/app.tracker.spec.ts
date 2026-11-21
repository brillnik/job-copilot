import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { hasChrome } from "./chrome";
import { stubTracker } from "./phase3-stubs";

test.skip(!hasChrome, "Google Chrome is not installed; e2e needs the local Chrome (channel: chrome)");

async function axeClean(page: Page) {
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}

test.describe("tracker (desktop)", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("stats, keyboard move (optimistic), 409 rollback, notes", async ({ page }) => {
    const state = await stubTracker(page);
    await page.goto("/tracker");
    await expect(page.getByText("Applied this week")).toBeVisible();
    await expect(page.getByText("25%")).toBeVisible();
    await axeClean(page);

    const card = page.getByRole("button", { name: /Frontend Engineer, Acme/ });
    await card.focus();
    await page.keyboard.press("Space");
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("Space");
    await expect(page.getByRole("list", { name: "Response cards" }).getByRole("button", { name: /Frontend Engineer, Acme/ })).toBeVisible();
    expect(state.patches[0]).toMatchObject({ id: "c1", ifMatch: '"2"', body: { column: "response" } });

    // 409: the card goes back.
    state.failNext = true;
    const moved = page.getByRole("button", { name: /Frontend Engineer, Acme/ });
    await moved.focus();
    await page.keyboard.press("Space");
    await page.keyboard.press("ArrowRight");
    await page.keyboard.press("Space");
    await expect(page.getByText(/changed somewhere else/).first()).toBeVisible();
    await expect(page.getByRole("list", { name: "Response cards" }).getByRole("button", { name: /Frontend Engineer, Acme/ })).toBeVisible();
    await expect(page.getByRole("list", { name: "Interview cards" }).getByRole("button", { name: /Frontend Engineer, Acme/ })).toHaveCount(0);

    await page.getByRole("button", { name: /Details for Frontend Engineer/ }).click();
    await page.getByLabel("Notes").fill("Spoke to recruiter. Follow up Monday.");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect.poll(() => state.patches.some((p) => p.body.notes)).toBe(true);
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`board is axe-clean in ${scheme}`, async ({ page }) => {
      await stubTracker(page);
      await page.emulateMedia({ colorScheme: scheme });
      await page.addInitScript((t) => localStorage.setItem("jc-theme", t), scheme);
      await page.goto("/tracker");
      await expect(page.getByText("Applied this week")).toBeVisible();
      await axeClean(page);
    });
  }
});

test.describe("tracker (390px)", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("board scrolls inside its region, the page does not", async ({ page }) => {
    await stubTracker(page);
    await page.goto("/tracker");
    await expect(page.getByText("Applied this week")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
    await axeClean(page);
    // The touch-friendly route: stage select in the details dialog.
    await page.getByRole("button", { name: /Details for Frontend Engineer/ }).click();
    await page.getByLabel("Stage").selectOption("interview");
    await expect(page.getByRole("list", { name: "Interview cards" }).getByRole("button", { name: /Frontend Engineer, Acme/ })).toBeVisible();
  });
});
