import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { hasChrome } from "./chrome";
import { CONSENTED, DRAFT_DATA, stubOnboarding } from "./onboarding-stubs";

test.skip(
  !hasChrome,
  "Google Chrome is not installed; e2e needs the local Chrome (channel: chrome)",
);

async function axeClean(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    results.violations.map(
      (v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
    ),
  ).toEqual([]);
}
const noHorizontalScroll = (page: Page) =>
  page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth,
  );

const resume = {
  name: "resume.pdf",
  mimeType: "application/pdf",
  buffer: Buffer.from("%PDF-1.4 fake resume"),
};

for (const scheme of ["light", "dark"] as const) {
  test(`main path: consent -> upload -> review -> preferences -> inbox (${scheme})`, async ({
    page,
  }) => {
    await page.addInitScript(
      (t) => localStorage.setItem("jc-theme", t),
      scheme,
    );
    const api = await stubOnboarding(page);

    // A signed-in user without consent is sent to the consent step first.
    await page.goto("/");
    await expect(page).toHaveURL(/\/onboarding\/consent$/);
    await expect(page.locator("html")).toHaveClass(
      scheme === "dark" ? /dark/ : /^(?!.*dark)/,
    );
    const agree = page.getByRole("button", { name: "Agree and continue" });
    await expect(agree).toBeDisabled();
    await axeClean(page);
    await page.getByRole("checkbox").check();
    await agree.click();
    await expect
      .poll(() => api.consent)
      .toMatchObject({ policy_version: "2026-01" });

    // No approved profile yet -> upload.
    await expect(page).toHaveURL(/\/onboarding\/upload$/);
    await expect(
      page.getByRole("heading", { level: 1, name: "Upload your resume" }),
    ).toBeVisible();
    await axeClean(page);

    // Images are rejected on the client with a clear message; nothing is sent.
    const input = page.getByLabel("Drop your resume here");
    await input.setInputFiles({
      name: "scan.png",
      mimeType: "image/png",
      buffer: Buffer.from("x"),
    });
    await expect(page.locator("p[role=alert]")).toContainText(
      "Images aren't supported",
    );
    expect(api.calls.filter((c) => c.includes("upload"))).toEqual([]);
    await axeClean(page);

    // Too large.
    await input.setInputFiles({
      name: "big.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.alloc(5 * 1024 * 1024 + 1, 1),
    });
    await expect(page.locator("p[role=alert]")).toContainText(
      "The limit is 5 MB",
    );

    await input.setInputFiles(resume);
    await page.getByRole("button", { name: "Read my resume" }).click();
    await expect(
      page.getByRole("status").filter({ hasText: "Reading your resume" }),
    ).toBeVisible();
    await axeClean(page);

    // Review: the missing end date must be confirmed before continuing.
    await expect(page).toHaveURL(/\/onboarding\/review$/);
    await expect(
      page.getByRole("heading", { level: 1, name: "Check your profile" }),
    ).toBeVisible();
    const approve = page.getByRole("button", { name: "Approve and continue" });
    await expect(approve).toBeDisabled();
    await expect(
      page.getByText(/1 item needs your confirmation/),
    ).toBeVisible();
    await axeClean(page);
    await page
      .getByRole("checkbox", { name: "This is my current role" })
      .check();
    await expect(approve).toBeEnabled();
    await page
      .getByLabel("Role 1 achievement 1", { exact: true })
      .fill("Cut p95 latency by 45% using React");
    await approve.click();

    // Preferences.
    await expect(page).toHaveURL(/\/onboarding\/preferences$/);
    expect(api.puts[0]).toMatchObject({
      experience: [
        {
          id: "e1",
          bullets: [{ id: "b1", text: "Cut p95 latency by 45% using React" }],
        },
      ],
    });
    expect(api.calls).toContain("POST /api/profile/approve");
    await page.getByLabel("Roles you're targeting").fill("Frontend Engineer");
    await page.getByRole("button", { name: "Add role" }).click();
    await page.getByRole("checkbox", { name: "Pune" }).check();
    await page.getByLabel("Current CTC (LPA)").fill("18.5");
    await page.getByLabel("Expected CTC (LPA)").fill("28");
    await page.getByLabel("Notice period (days)").fill("30");
    await page.getByRole("radio", { name: "2 pages" }).check({ force: true });
    await axeClean(page);
    await page.getByRole("button", { name: "Save and go to inbox" }).click();

    await expect(page).toHaveURL(/\/$/);
    await expect(
      page.getByRole("heading", { level: 1, name: "Inbox" }),
    ).toBeVisible();
    expect(api.settingsPuts).toHaveLength(1);
    expect(api.settingsPuts[0].ifMatch).toBe('"1"');
    expect(api.settingsPuts[0].body).toMatchObject({
      target_roles: ["Frontend Engineer"],
      cities: ["Pune"],
      current_ctc_lpa: 18.5,
      expected_ctc_lpa: 28,
      default_length: 2,
      daily_cap: 5,
      coverage_target: 0.7,
    });
    // No tokens or personal data in localStorage.
    expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([
      "jc-theme",
    ]);
  });
}

test("a finished account is not sent back to onboarding", async ({ page }) => {
  await stubOnboarding(page, {
    consent: CONSENTED,
    approved: {
      id: "p",
      status: "approved",
      version: 2,
      resume_id: null,
      data: DRAFT_DATA,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      approved_at: "2026-01-02T00:00:00Z",
    },
    configured: true,
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { level: 1, name: "Inbox" }),
  ).toBeVisible();
});

test.describe("profile page", () => {
  const approved = {
    id: "p",
    status: "approved",
    version: 2,
    resume_id: null,
    data: DRAFT_DATA,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    approved_at: "2026-01-02T00:00:00Z",
  };

  for (const scheme of ["light", "dark"] as const) {
    test(`edit a bullet, see it flagged as unapproved, approve (${scheme})`, async ({
      page,
    }) => {
      await page.addInitScript(
        (t) => localStorage.setItem("jc-theme", t),
        scheme,
      );
      const api = await stubOnboarding(page, {
        consent: CONSENTED,
        approved,
        configured: true,
      });
      await page.goto("/profile");
      await expect(page.getByText("Approved · v2")).toBeVisible();
      await expect(
        page.getByText("Cut p95 latency by 40% using React"),
      ).toBeVisible();
      await expect(
        page
          .getByRole("list", { name: "Numbers in the text" })
          .getByText("40%"),
      ).toBeVisible();
      await axeClean(page);

      await page.getByRole("button", { name: /^Edit: Cut p95/ }).click();
      const box = page.getByLabel(/Edit achievement/);
      await box.fill("Cut p95 latency by 45% using React");
      await page.getByRole("button", { name: "Save" }).click();

      await expect(
        page.getByRole("region", { name: "Unapproved changes" }),
      ).toBeVisible();
      await expect(page.getByText("Unapproved", { exact: true })).toBeVisible();
      expect(api.puts[0]).toMatchObject({
        experience: [
          {
            id: "e1",
            bullets: [{ id: "b1", text: "Cut p95 latency by 45% using React" }],
          },
        ],
      });
      await axeClean(page);

      await page.getByRole("button", { name: "Approve changes" }).click();
      await expect(
        page.getByRole("region", { name: "Unapproved changes" }),
      ).toBeHidden();
      expect(api.calls).toContain("POST /api/profile/approve");
    });
  }

  test("mobile 390px: no horizontal scroll on sign-up steps and profile", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const api = await stubOnboarding(page, {
      consent: CONSENTED,
      approved,
      configured: true,
    });
    await page.goto("/profile");
    await expect(page.getByText("Approved · v2")).toBeVisible();
    expect(await noHorizontalScroll(page)).toBe(true);
    await axeClean(page);

    api.approved = null;
    api.draft = {
      ...approved,
      status: "draft",
      version: null,
      approved_at: null,
    };
    await page.goto("/onboarding/review");
    await expect(
      page.getByRole("heading", { level: 1, name: "Check your profile" }),
    ).toBeVisible();
    expect(await noHorizontalScroll(page)).toBe(true);
    await axeClean(page);

    await page.goto("/onboarding/preferences");
    await expect(
      page.getByRole("heading", { level: 1, name: "Your preferences" }),
    ).toBeVisible();
    await expect(page.getByLabel("Current CTC (LPA)")).toBeVisible();
    expect(await noHorizontalScroll(page)).toBe(true);
    await axeClean(page);

    await page.goto("/onboarding/upload");
    await expect(page.getByLabel("Drop your resume here")).toBeAttached();
    expect(await noHorizontalScroll(page)).toBe(true);
    await axeClean(page);
  });
});
