import { composeStories } from "@storybook/react";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axe } from "vitest-axe";
import * as jobs from "./jobs.stories";

const stories = composeStories(jobs as never) as Record<
  string,
  React.ComponentType
>;
describe("stories: jobs", () => {
  for (const [name, Story] of Object.entries(stories)) {
    it(`${name} is axe-clean`, async () => {
      const { container } = render(<Story />);
      const results = await axe(container, {
        rules: { "color-contrast": { enabled: false } },
      });
      expect(results).toHaveNoViolations();
    });
  }
});
