import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { hasChrome } from "./chrome";
import { stubJobs } from "./jobs-stubs";

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

const noOverflow = (page: Page) =>
  page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth,
  );

for (const scheme of ["light", "dark"] as const) {
  test(`inbox -> add -> tailor -> detail -> review link (${scheme})`, async ({
    page,
  }) => {
    await page.addInitScript(
      (t) => localStorage.setItem("jc-theme", t),
      scheme,
    );
    const state = await stubJobs(page);
    await page.goto("/");
    await expect(
      page.getByRole("heading", { level: 1, name: "Inbox" }),
    ).toBeVisible();
    await expect(
      page.getByRole("link", { name: "Frontend Engineer" }),
    ).toBeVisible();
    await expect(page.getByText("Reading the posting…")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Submit text" }),
    ).toBeVisible();
    await expect(page.getByText("1 red flag")).toBeVisible();
    await expect(
      page.getByRole("meter", { name: /Match for Frontend/ }),
    ).toHaveAttribute("aria-valuenow", "82");
    await axeClean(page);

    // Add a duplicate by link: the modal says so and links to the existing job.
    await page.getByRole("button", { name: "Add job" }).first().click();
    const dialog = page.getByRole("dialog", { name: "Add a job" });
    await dialog.getByLabel("Job link").fill("https://acme.example/dup");
    await dialog.getByRole("button", { name: "Add job" }).click();
    await expect(
      dialog.getByRole("link", { name: "Open the existing job" }),
    ).toHaveAttribute("href", "/jobs/j2");
    await axeClean(page);
    // A new add closes the dialog and confirms.
    await dialog.getByLabel("Job link").fill("https://acme.example/new");
    await dialog.getByRole("button", { name: "Add job" }).click();
    await expect(page.getByText("Job added")).toBeVisible();
    expect(state.added).toHaveLength(2);

    // Multi-select tailor: one POST per job.
    await page
      .getByRole("checkbox", { name: /Select Backend Engineer/ })
      .check();
    await page.getByRole("button", { name: "Tailor selected (1)" }).click();
    await expect(
      page.getByRole("region", { name: "Tailoring results" }),
    ).toContainText("Tailoring started");
    expect(state.tailored.map((t) => t.id)).toEqual(["j2"]);
    state.tailored.length = 0;

    // Detail: structured JD, evidence tooltip, red-flag confirm, live progress, review link.
    await page.getByRole("link", { name: "Frontend Engineer" }).click();
    await expect(page).toHaveURL(/\/jobs\/j1$/);
    await expect(
      page.getByRole("heading", { level: 1, name: "Frontend Engineer" }),
    ).toBeVisible();
    await expect(page.getByText("meets your 28 LPA expectation")).toBeVisible();
    await expect(page.getByRole("button", { name: "abcdef01" })).toBeVisible();
    await axeClean(page);

    await page.getByRole("radio", { name: "2 pages" }).check({ force: true });
    await expect
      .poll(() => state.patches)
      .toContainEqual({ max_pages_override: 2 });

    await page.getByRole("button", { name: "Tailor resume" }).click();
    const flags = page.getByRole("dialog", {
      name: "This posting has red flags",
    });
    await expect(flags).toContainText("Unpaid trial period");
    await axeClean(page);
    await flags.getByRole("button", { name: "Tailor anyway" }).click();
    expect(state.tailored[0].body).toEqual({ confirm_red_flags: true });
    await expect(
      page.getByRole("link", { name: "Open review" }),
    ).toHaveAttribute("href", "/review/r1");
    await expect(page.getByText("Passed fact-check")).toBeVisible();
    await axeClean(page);
  });
}

test.describe("mobile (390px)", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("inbox and detail fit and are axe-clean", async ({ page }) => {
    await stubJobs(page);
    await page.goto("/");
    await expect(
      page.getByRole("link", { name: "Frontend Engineer" }),
    ).toBeVisible();
    expect(await noOverflow(page)).toBe(true);
    await axeClean(page);
    await page.goto("/jobs/j1");
    await expect(
      page.getByRole("heading", { level: 1, name: "Frontend Engineer" }),
    ).toBeVisible();
    expect(await noOverflow(page)).toBe(true);
    await axeClean(page);
  });
});

test("inbox shows an error with retry and the empty state", async ({
  page,
}) => {
  await stubJobs(page);
  let calls = 0;
  await page.route(/\/api\/jobs(\?.*)?$/, (r) => {
    calls += 1;
    if (calls <= 2)
      return r.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ code: "server_error", message: "Boom" }),
      });
    return r.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [], next_cursor: null }),
    });
  });
  await page.goto("/");
  await expect(
    page.getByRole("alert").filter({ hasText: "Couldn't load your jobs" }),
  ).toBeVisible();
  await axeClean(page);
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByText("Nothing in your inbox yet")).toBeVisible();
  await axeClean(page);
});
