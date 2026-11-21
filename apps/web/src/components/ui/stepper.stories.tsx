import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Stepper } from "./stepper";

const meta = { title: "UI/Stepper", component: Stepper } satisfies Meta<
  typeof Stepper
>;
export default meta;
type Story = StoryObj<typeof meta>;

export const AllStates: Story = {
  args: {
    label: "Tailoring progress",
    steps: [
      { label: "Fetch job", state: "done", detail: "2s" },
      { label: "Match profile", state: "done" },
      { label: "Draft bullets", state: "running", detail: "3 of 8" },
      { label: "Answer questions", state: "waiting", detail: "needs you" },
      { label: "Fact-check", state: "queued" },
      { label: "Render PDF", state: "queued" },
    ],
  },
};
