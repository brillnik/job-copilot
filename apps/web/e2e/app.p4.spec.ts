import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { hasChrome } from "./chrome";
import { stubP4 } from "./p4-stubs";

test.skip(
  !hasChrome,
  "Google Chrome is not installed; e2e needs the local Chrome (channel: chrome)",
);

async function axeClean(page: Page) {
  const r = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    r.violations.map(
      (v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
    ),
  ).toEqual([]);
}

for (const scheme of ["light", "dark"] as const) {
  test.describe(`phase 4 (${scheme})`, () => {
    test.use({ viewport: { width: 1280, height: 900 } });

    test.beforeEach(async ({ page }) => {
      await page.addInitScript(
        (t) => localStorage.setItem("jc-theme", t),
        scheme,
      );
    });

    test("for you: score, reasons, save", async ({ page }) => {
      const st = await stubP4(page);
      await page.goto("/for-you");
      const card = page.getByRole("article", {
        name: "Senior Frontend Engineer",
      });
      await expect(card.getByText("86", { exact: true })).toBeVisible();
      await expect(
        card.getByText("Skills match: React, TypeScript"),
      ).toBeVisible();
      await axeClean(page);
      await card.getByRole("button", { name: /^Save/ }).click();
      await expect(
        page.getByRole("link", { name: "Open saved job" }),
      ).toBeVisible();
      expect(st.saved).toHaveLength(1);
    });

    test("for you: dismiss with a reason", async ({ page }) => {
      const st = await stubP4(page);
      await page.goto("/for-you");
      await page.getByRole("button", { name: /^Dismiss/ }).click();
      await page.getByLabel(/Reason/).fill("Too junior");
      await axeClean(page);
      await page.getByRole("button", { name: "Dismiss role" }).click();
      await expect(page.getByText("Nothing new for you today")).toBeVisible();
      expect(st.dismissed).toEqual([{ id: "rec1", reason: "Too junior" }]);
    });

    test("autopilot: acknowledge, turn on, per-site opt-in", async ({
      page,
    }) => {
      const st = await stubP4(page);
      await page.goto("/autopilot");
      await expect(
        page.getByRole("heading", { level: 1, name: "Autopilot" }),
      ).toBeVisible();
      const on = page.getByRole("button", { name: "Turn on Autopilot" });
      await expect(on).toBeDisabled();
      await axeClean(page);
      await page
        .getByRole("checkbox", { name: /applies to jobs on my behalf/ })
        .check();
      await on.click();
      await expect(
        page.getByRole("button", { name: "Turn off Autopilot" }),
      ).toBeVisible();
      expect(st.autopilotPuts[0]).toEqual({
        enabled: true,
        acknowledgement_version: "2026-11",
      });
      const nk = page.getByRole("region", { name: "Naukri" });
      await expect(
        nk.getByRole("button", { name: "Opt in to Naukri" }),
      ).toBeDisabled();
      await axeClean(page);
    });

    test("digest, applications list and detail", async ({ page }) => {
      await stubP4(page);
      await page.goto("/autopilot/digest");
      await expect(
        page.getByRole("region", { name: /Skipped/ }).getByText(/CAPTCHA/),
      ).toBeVisible();
      await axeClean(page);
      await page.goto("/applications");
      await expect(
        page.getByRole("list", { name: "Applications" }).getByText("Skipped"),
      ).toBeVisible();
      await axeClean(page);
      await page.getByRole("link", { name: /FE/ }).click();
      await expect(
        page.getByRole("link", { name: /Apply yourself/ }),
      ).toHaveAttribute("href", "https://beta.example/apply");
      await expect(page.getByText("a@b.co")).toBeVisible();
      await axeClean(page);
    });

    test("integrations: pairing code, gmail suggestion, training switch", async ({
      page,
    }) => {
      const st = await stubP4(page);
      await page.goto("/integrations");
      await expect(page.getByText("Notice period?", { exact: true })).toBeVisible();
      await page.getByRole("button", { name: "Get a pairing code" }).click();
      await expect(page.getByText("ABCD-1234")).toBeVisible();
      await expect(
        page.getByRole("heading", { name: "Move Acme to Interview?" }),
      ).toBeVisible();
      const sw = page.getByRole("switch");
      await expect(sw).toHaveAttribute("aria-checked", "false");
      await sw.click();
      await expect(sw).toHaveAttribute("aria-checked", "true");
      expect(st.training).toEqual([
        { enabled: true, policy_version: "2026-01" },
      ]);
      await axeClean(page);
    });
  });
}

test.describe("phase 4 (390px)", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  for (const path of [
    "/for-you",
    "/autopilot",
    "/applications",
    "/integrations",
  ]) {
    test(`${path} has no horizontal scroll and is axe-clean`, async ({
      page,
    }) => {
      await stubP4(page);
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
      await expect(page.getByRole("alert").filter({ hasText: /\S/ })).toHaveCount(0);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth > window.innerWidth,
        ),
      ).toBe(false);
      await axeClean(page);
    });
  }
});
