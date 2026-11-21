import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { hasChrome } from "./chrome";

test.skip(
  !hasChrome,
  "Google Chrome is not installed; e2e needs the local Chrome (channel: chrome)",
);

// Every Storybook story, light and dark, in real Chrome (so colour contrast is
// actually computed). Needs the built Storybook; see the `stories` web server.
test("every story is axe-clean in light and dark", async ({
  page,
  request,
}) => {
  test.setTimeout(1_200_000);
  const index = await (await request.get("/index.json")).json();
  const ids = Object.values<{ id: string; type: string }>(index.entries)
    .filter((e) => e.type === "story")
    .map((e) => e.id);
  expect(ids.length).toBeGreaterThan(30);

  const failures: string[] = [];
  for (const theme of ["light", "dark"]) {
    for (const id of ids) {
      await page.goto(
        `/iframe.html?id=${id}&viewMode=story&globals=theme:${theme}`,
      );
      await page.locator("#storybook-root > *").first().waitFor();
      // Storybook's own a11y addon runs axe in the same frame; retry if it is mid-run.
      let results;
      for (let attempt = 0; ; attempt++) {
        try {
          results = await new AxeBuilder({ page })
            .include("#storybook-root")
            .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
            .analyze();
          break;
        } catch (e) {
          if (attempt >= 4 || !String(e).includes("already running")) throw e;
          await page.waitForTimeout(500);
        }
      }
      for (const v of results.violations)
        failures.push(
          `${theme} ${id}: ${v.id} ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`,
        );
    }
  }
  expect(failures).toEqual([]);
});
