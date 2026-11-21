import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { hasChrome } from "./chrome";
import { stubApi } from "./stubs";

test.skip(
  !hasChrome,
  "Google Chrome is not installed; e2e needs the local Chrome (channel: chrome)",
);

async function expectNoAxeViolations(page: import("@playwright/test").Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    results.violations.map(
      (v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
    ),
  ).toEqual([]);
}

test.describe("desktop shell", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("renders the sidebar with a review-queue badge and navigates", async ({
    page,
  }) => {
    await stubApi(page, { reviewCount: 2 });
    await page.goto("/");
    const nav = page.getByRole("navigation", { name: "Main" });
    await expect(nav.getByRole("link")).toHaveText([
      /Inbox/,
      /For you/,
      /Review queue/,
      /Tracker/,
      /Applications/,
      /Autopilot/,
      /Profile/,
      /Integrations/,
      /Settings/,
    ]);
    await expect(nav.getByRole("link", { name: /Review queue/ })).toContainText(
      "2 awaiting review",
    );
    await expect(
      page.getByRole("heading", { level: 1, name: "Inbox" }),
    ).toBeVisible();
    await expectNoAxeViolations(page);

    await nav.getByRole("link", { name: "Tracker" }).click();
    await expect(page).toHaveURL(/\/tracker$/);
    await expect(
      page.getByRole("heading", { level: 1, name: "Tracker" }),
    ).toBeVisible();
    await expect(nav.getByRole("link", { name: "Tracker" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    // The bottom tab bar exists in the DOM but is mobile-only.
    await expect(page.locator("nav[aria-label=Main]")).toHaveCount(2);
    await expect(page.locator("nav[aria-label=Main]").last()).toBeHidden();
  });

  for (const scheme of ["light", "dark"] as const) {
    test(`all main pages are axe-clean in ${scheme}`, async ({
      page,
    }) => {
      await stubApi(page, { theme: scheme }); // the saved account theme wins over the local one
      await page.addInitScript(
        (t) => localStorage.setItem("jc-theme", t),
        scheme,
      );
      for (const path of [
        "/",
        "/for-you",
        "/review",
        "/tracker",
        "/profile",
        "/settings",
      ]) {
        await page.goto(path);
        await expect(page.locator("html")).toHaveClass(
          scheme === "dark" ? /dark/ : /^(?!.*dark)/,
        );
        await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
        await expectNoAxeViolations(page);
      }
    });
  }

  test("theme switch applies, persists locally and PUTs /settings with If-Match", async ({
    page,
  }) => {
    const state = await stubApi(page);
    await page.emulateMedia({ colorScheme: "light" });
    await page.goto("/settings");
    const html = page.locator("html");
    await expect(html).not.toHaveClass(/dark/);

    await page.getByRole("radio", { name: "Dark" }).check({ force: true });
    await expect(html).toHaveClass(/dark/);
    await expect.poll(() => state.puts.length).toBe(1);
    expect(state.puts[0].body.theme).toBe("dark");
    expect(state.puts[0].ifMatch).toBe('"1"');
    // Full replace: every preference field is sent, not just theme.
    expect(Object.keys(state.puts[0].body)).toContain("expected_ctc_lpa");
    await expectNoAxeViolations(page);

    // No flash on reload: the class is set before hydration, from localStorage.
    await page.reload();
    await expect(html).toHaveClass(/dark/);
    expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([
      "jc-theme",
    ]);

    await page.getByRole("radio", { name: "System" }).check({ force: true });
    await expect(html).not.toHaveClass(/dark/); // emulated OS = light
    await page.getByRole("radio", { name: "Light" }).check({ force: true });
    await expect(html).not.toHaveClass(/dark/);
  });
});

test.describe("mobile shell (390px)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("shows the bottom tab bar, hides the sidebar, no horizontal scroll", async ({
    page,
  }) => {
    await stubApi(page, { reviewCount: 3 });
    await page.goto("/");
    const nav = page.getByRole("navigation", { name: "Main" });
    await expect(nav).toBeVisible();
    await expect(nav.getByRole("link")).toHaveText([
      /Inbox/,
      /Review/,
      /Tracker/,
      /Profile/,
      /Settings/,
    ]);
    await expect(nav.getByRole("link", { name: /Review/ })).toContainText(
      "3 awaiting review",
    );
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > window.innerWidth,
    );
    expect(overflow).toBe(false);
    // Touch targets >= 44px.
    for (const link of await nav.getByRole("link").all()) {
      const box = await link.boundingBox();
      expect(box!.height).toBeGreaterThanOrEqual(44);
      expect(box!.width).toBeGreaterThanOrEqual(44);
    }
    await nav.getByRole("link", { name: "Profile" }).click();
    await expect(page).toHaveURL(/\/profile$/);
    await expectNoAxeViolations(page);

    await page.unroute("**/api/settings");
    await stubApi(page, { reviewCount: 3, theme: "dark" });
    await page.reload();
    await expect(page.locator("html")).toHaveClass(/dark/);
    await expectNoAxeViolations(page);
  });
});
