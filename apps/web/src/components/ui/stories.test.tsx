import { composeStories } from "@storybook/react";
import { render } from "@testing-library/react";
import { axe } from "vitest-axe";
import { describe, expect, it } from "vitest";
import * as button from "./button.stories";
import * as card from "./card.stories";
import * as chip from "./chip.stories";
import * as controls from "./controls.stories";
import * as diff from "./diff-line.stories";
import * as dropzone from "./dropzone.stories";
import * as feedback from "./feedback.stories";
import * as field from "./field.stories";
import * as kanban from "./kanban-card.stories";
import * as longTask from "./long-task-status.stories";
import * as modal from "./modal.stories";
import * as score from "./score-bar.stories";
import * as stepper from "./stepper.stories";

// Every story renders without crashing and has no axe violations in jsdom.
// (jsdom cannot compute colour contrast; that is checked in contrast.test.ts
// from the token values and in the Playwright axe run in a real browser.)
const modules = {
  button,
  card,
  chip,
  controls,
  diff,
  dropzone,
  feedback,
  field,
  kanban,
  longTask,
  modal,
  score,
  stepper,
};

for (const [name, mod] of Object.entries(modules)) {
  const stories = composeStories(mod as never) as Record<
    string,
    React.ComponentType
  >;
  describe(`stories: ${name}`, () => {
    for (const [storyName, Story] of Object.entries(stories)) {
      it(`${storyName} is axe-clean`, async () => {
        const { container } = render(<Story />);
        const results = await axe(container, {
          rules: { "color-contrast": { enabled: false } },
        });
        expect(results).toHaveNoViolations();
      });
    }
  });
}
