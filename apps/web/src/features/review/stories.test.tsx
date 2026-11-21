import { composeStories } from "@storybook/react";
import { render } from "@testing-library/react";
import { axe } from "vitest-axe";
import { describe, expect, it } from "vitest";
import * as controls from "@/components/ui/form-controls.stories";
import * as review from "./review.stories";

for (const [name, mod] of Object.entries({ controls, review })) {
  const stories = composeStories(mod as never) as Record<string, React.ComponentType>;
  describe(`stories: ${name}`, () => {
    for (const [storyName, Story] of Object.entries(stories)) {
      it(`${storyName} renders and has no axe violations`, async () => {
        const { container } = render(<Story />);
        expect(await axe(container)).toHaveNoViolations();
      });
    }
  });
}
