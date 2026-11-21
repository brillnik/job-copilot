import { composeStories } from "@storybook/react";
import { render } from "@testing-library/react";
import { axe } from "vitest-axe";
import { describe, expect, it, vi } from "vitest";
import * as p4 from "./p4.stories";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...p
  }: {
    href: string;
    children: React.ReactNode;
  }) => (
    <a href={href} {...p}>
      {children}
    </a>
  ),
}));

const stories = composeStories(p4 as never) as Record<
  string,
  React.ComponentType
>;
describe("stories: phase 4", () => {
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
