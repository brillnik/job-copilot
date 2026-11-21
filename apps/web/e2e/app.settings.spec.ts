import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { hasChrome } from "./chrome";
import { stubSettings } from "./phase3-stubs";

test.skip(!hasChrome, "Google Chrome is not installed; e2e needs the local Chrome (channel: chrome)");

async function axeClean(page: Page) {
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(r.violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
}

test.describe("settings (desktop)", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("preferences validate, save with If-Match, keep input on error", async ({ page }) => {
    const state = await stubSettings(page);
    await page.goto("/settings");
    await expect(page.getByRole("heading", { level: 2, name: "Job preferences" })).toBeVisible();
    await expect(page.getByText(/Used today:/)).toContainText("2 of 5");
    await axeClean(page);

    await page.getByLabel("Notice period (days)").fill("400");
    await page.getByRole("button", { name: "Save preferences" }).click();
    await expect(page.getByText("At most 180 days")).toBeVisible();
    expect(state.puts).toHaveLength(0);
    await expect(page.getByLabel("Notice period (days)")).toHaveValue("400");

    await page.getByLabel("Notice period (days)").fill("45");
    await page.getByRole("textbox", { name: "Target roles" }).fill("Staff Engineer");
    await page.getByRole("button", { name: /Add role/ }).click();
    await page.getByLabel("Pune").check();
    await page.getByRole("radio", { name: "2 pages" }).check({ force: true });
    await page.getByRole("button", { name: "Save preferences" }).click();
    await expect.poll(() => state.puts.length).toBe(1);
    expect(state.puts[0].ifMatch).toBe('"1"');
    expect(state.puts[0].body).toMatchObject({
      notice_days: 45,
      target_roles: ["Frontend Engineer", "Staff Engineer"],
      cities: ["Bengaluru", "Pune"],
      default_length: 2,
      coverage_target: 0.8,
      theme: "system",
    });
    await expect(page.getByText("Preferences saved.")).toBeVisible();
  });

  test("export polls to ready and links through the proxy; device revoke", async ({ page }) => {
    const state = await stubSettings(page);
    await page.goto("/settings");
    await expect(page.getByText("Chrome on Mac")).toBeVisible();
    await page.getByRole("button", { name: "Revoke Chrome on Mac" }).click();
    await expect(page.getByText("No browser extension is connected.")).toBeVisible();
    expect(state.revoked).toEqual(["t1"]);

    await page.getByRole("button", { name: "Request export" }).click();
    const link = page.getByRole("link", { name: "Download export" });
    await expect(link).toBeVisible({ timeout: 10_000 });
    await expect(link).toHaveAttribute("href", "/api/files/abc.def");
  });

  test("delete account requires typing DELETE and prompts re-auth on 401", async ({ page }) => {
    const state = await stubSettings(page, { reauth: true });
    await page.goto("/settings");
    await page.getByRole("button", { name: "Delete my account" }).click();
    const confirm = page.getByRole("button", { name: "Delete account" });
    await expect(confirm).toBeDisabled();
    await page.getByLabel("Type DELETE to confirm").fill("DELETE");
    await axeClean(page);
    await confirm.click();
    await expect(page.getByRole("button", { name: "Sign in again" })).toBeVisible();
    expect(state.deletes).toBe(1);
    // Not bounced to /sign-in by the generic 401 handler.
    await expect(page).toHaveURL(/\/settings/);
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`settings is axe-clean in ${scheme}`, async ({ page }) => {
      await stubSettings(page);
      await page.emulateMedia({ colorScheme: scheme });
      await page.addInitScript((t) => localStorage.setItem("jc-theme", t), scheme);
      await page.goto("/settings");
      await expect(page.getByRole("heading", { level: 2, name: "Job preferences" })).toBeVisible();
      await axeClean(page);
    });
  }
});

test.describe("settings (390px)", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("fits the viewport and is axe-clean", async ({ page }) => {
    await stubSettings(page);
    await page.goto("/settings");
    await expect(page.getByRole("heading", { level: 2, name: "Job preferences" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
    await axeClean(page);
  });
});
