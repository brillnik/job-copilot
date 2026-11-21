import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { hasChrome } from "./chrome";
import { stubReview } from "./phase3-stubs";

test.skip(!hasChrome, "Google Chrome is not installed; e2e needs the local Chrome (channel: chrome)");

async function axeClean(page: Page) {
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}

test.describe("review (desktop)", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("queue -> detail -> refused edit keeps text -> save -> approve", async ({ page }) => {
    const state = await stubReview(page);
    await page.goto("/review");
    await expect(page.getByRole("heading", { level: 1, name: "Review queue" })).toBeVisible();
    await expect(page.getByText("Led with design-system work")).toBeVisible();
    await axeClean(page);

    await page.getByRole("link", { name: /Open draft/ }).click();
    await expect(page).toHaveURL(/\/review\/run1$/);
    await expect(page.getByRole("heading", { level: 1, name: /Frontend Engineer at Acme/ })).toBeVisible();
    await expect(page.getByText(/The rewrite introduced a number/)).toBeVisible();
    await expect(page.getByText("Flagged for your attention")).toBeVisible();
    await expect(page.getByTitle("Resume PDF preview")).toBeVisible();
    await axeClean(page);

    const summary = page.getByLabel("Edit summary");
    await summary.fill("Engineer with 10 years");
    await page.getByRole("button", { name: /Save 1 edit/ }).click();
    await expect(page.getByText("10 is not in your profile").first()).toBeVisible();
    await expect(summary).toHaveValue("Engineer with 10 years");
    expect(state.puts[0].ifMatch).toBe('"3"');

    await summary.fill("Frontend engineer, 6 years, design systems.");
    await page.getByLabel("Edit cover note").fill("Hello Acme team! Thanks.");
    await page.getByRole("button", { name: /Save 2 edits/ }).click();
    await expect(page.getByText(/2 edits saved/).first()).toBeVisible();
    expect(state.puts[1].ifMatch).toBe('"3"');

    await page.getByRole("button", { name: "Approve" }).click();
    await expect(page.getByText("Approved as frontend-engineer.pdf.")).toBeVisible();
    expect(state.approves).toBe(1);
  });

  test("reject sends reasons and note, regenerate sends the chosen length", async ({ page }) => {
    const state = await stubReview(page);
    await page.goto("/review/run1");
    await page.getByRole("radio", { name: "3 pages" }).check({ force: true });
    await page.getByRole("button", { name: "Regenerate at 3 pages" }).click();
    await expect.poll(() => state.regenerates.length).toBe(1);
    expect(state.regenerates[0]).toMatchObject({ max_pages: 3 });
    await expect(page).toHaveURL(/\/jobs\/job1$/);

    await page.goto("/review/run1");
    await page.getByRole("button", { name: "Reject", exact: true }).click();
    await page.getByLabel("Too generic").check();
    await page.getByLabel("Note (optional)").fill("Needs more impact");
    await page.getByRole("button", { name: "Reject draft" }).click();
    await expect.poll(() => state.rejects.length).toBe(1);
    expect(state.rejects[0]).toEqual({ reasons: ["too_generic"], note: "Needs more impact" });
    await expect(page).toHaveURL(/\/review$/);
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`detail is axe-clean in ${scheme}`, async ({ page }) => {
      await stubReview(page);
      await page.emulateMedia({ colorScheme: scheme });
      await page.addInitScript((t) => localStorage.setItem("jc-theme", t), scheme);
      await page.goto("/review/run1");
      await expect(page.getByRole("heading", { level: 2, name: "Fact check" })).toBeVisible();
      await axeClean(page);
    });
  }
});

test.describe("review (390px)", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("card stack and detail fit without horizontal scroll", async ({ page }) => {
    await stubReview(page);
    for (const path of ["/review", "/review/run1"]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expect(page.getByRole("heading", { level: 1 })).not.toHaveText("");
      expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
      await axeClean(page);
    }
  });
});
