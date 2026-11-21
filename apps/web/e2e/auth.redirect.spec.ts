import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { hasChrome } from "./chrome";

test.skip(
  !hasChrome,
  "Google Chrome is not installed; e2e needs the local Chrome (channel: chrome)",
);

// Runs against a server WITHOUT the auth stub, i.e. the real proxy.ts middleware.
test("unauthenticated users are redirected to /sign-in", async ({ page }) => {
  for (const path of ["/", "/tracker", "/settings"]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/sign-in$/);
  }
});

test("/signin redirects to /sign-in and the page is axe-clean", async ({
  page,
}) => {
  await page.goto("/signin");
  await expect(page).toHaveURL(/\/sign-in$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Sign in to Job Copilot" }),
  ).toBeVisible();
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    results.violations.map(
      (v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
    ),
  ).toEqual([]);
});

test("the API proxy answers 401 JSON (no redirect) without a session", async ({
  request,
}) => {
  const res = await request.get("/api/me", { maxRedirects: 0 });
  expect(res.status()).toBe(401);
});
